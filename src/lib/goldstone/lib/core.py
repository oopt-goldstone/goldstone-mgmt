import sysrepo
import libyang
import logging
from aiohttp import web
import inspect
import json

logger = logging.getLogger(__name__)


async def start_probe(route, host, port):
    routes = web.RouteTableDef()

    @routes.get(route)
    async def probe(request):
        return web.Response()

    app = web.Application()
    app.add_routes(routes)

    runner = web.AppRunner(app)

    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    return runner


async def call(f, *args, **kwargs):
    if inspect.iscoroutinefunction(f):
        return await f(*args, **kwargs)
    else:
        return f(*args, **kwargs)


class ChangeHandler(object):
    def __init__(self, server, change):
        self.server = server
        self.change = change
        if isinstance(change, sysrepo.ChangeCreated):
            self.type = "created"
        elif isinstance(change, sysrepo.ChangeModified):
            self.type = "modified"
        elif isinstance(change, sysrepo.ChangeDeleted):
            self.type = "deleted"
        else:
            raise sysrepo.SysrepoInvalArgError(
                f"unsupported change type: {type(change)}"
            )

    def setup_cache(self, user):
        cache = user.get("cache")
        if not cache:
            cache = self.server.get_running_data(
                self.server.top, default={}, strip=False
            )
            sysrepo.update_config_cache(cache, user["changes"])
            user["cache"] = cache
        return cache

    def validate(self, user):
        pass

    def apply(self, user):
        pass

    def revert(self, user):
        pass


NoOp = ChangeHandler


class ServerBase(object):
    def __init__(self, conn, module):
        self.sess = conn.start_session()
        ctx = self.sess.get_ly_ctx()
        m = ctx.get_module(module)
        v = [n.name() for n in m if n.keyword() == "container"]
        assert len(v) == 1
        self.module = module
        self.top = f"/{self.module}:{v[0]}"
        self.handlers = {}
        self._current_handlers = None  # (req_id, handlers, user)

    def get_sr_data(
        self,
        xpath,
        datastore,
        default=None,
        strip=True,
        include_implicit_defaults=False,
    ):
        self.sess.switch_datastore(datastore)
        try:
            v = self.sess.get_data(
                xpath, include_implicit_defaults=include_implicit_defaults
            )
        except sysrepo.errors.SysrepoNotFoundError:
            logger.debug(
                f"xpath: {xpath}, ds: {datastore}, not found. returning {default}"
            )
            return default
        if strip:
            v = libyang.xpath_get(v, xpath, default, filter=datastore == "operational")
        logger.debug(f"xpath: {xpath}, ds: {datastore}, value: {v}")
        return v

    def get_running_data(
        self, xpath, default=None, strip=True, include_implicit_defaults=False
    ):
        return self.get_sr_data(
            xpath, "running", default, strip, include_implicit_defaults
        )

    def get_operational_data(self, xpath, default=None, strip=True):
        return self.get_sr_data(xpath, "operational", default, strip)

    def get_handler(self, xpath):
        xpath = libyang.xpath_split(xpath)
        cursor = self.handlers
        for x in xpath:
            v = cursor.get(x[1])
            if v == None:
                return None
            if type(v) == type and issubclass(v, ChangeHandler):
                return v
            cursor = v
        return NoOp

    async def start(self):
        self.sess.switch_datastore("running")
        asyncio_register = inspect.iscoroutinefunction(self.change_cb)
        self.sess.subscribe_module_change(
            self.module, None, self.change_cb, asyncio_register=asyncio_register
        )
        asyncio_register = inspect.iscoroutinefunction(self.oper_cb)
        self.sess.subscribe_oper_data_request(
            self.module,
            self.top,
            self.oper_cb,
            oper_merge=True,
            asyncio_register=asyncio_register,
        )

        return []

    def stop(self):
        self.sess.stop()

    async def reconcile(self):
        logger.debug("reconcile")

    # In Goldstone Management Layer, one model is subcribed by one Server.
    # When a sysrepo transction only includes changes for one model, 'abort' event
    # never happens. However, when a sysrepo transaction includes changes for more than one model,
    # change_cb() may get an 'abort' event if error happens in a change_cb() of other servers.
    #
    # We store the handlers created in the 'change' event, and discard them if we get a succeeding 'done' event.
    # If we get 'abort' event, call revert() of the stored handlers then discard them.
    #
    # - 'change' event handling
    #   - 1. iterate through the changes, do basic validation, degenerate changes if possible
    #   - 2. do the actual change handling, if any error happens, revert the changes made in advance and raise error
    #   - 3. store the handlers for 'abort' event
    # - 'done' event handling
    #   - 1. discard the stored handlers
    # - 'abort' event handling
    #   - 1. call revert() of the stored handlers
    #   - 2. discard the stored handlers
    async def change_cb(self, event, req_id, changes, priv):
        logger.debug(f"id: {req_id}, event: {event}, changes: {changes}")
        if event not in ["change", "done", "abort"]:
            logger.warning(f"unsupported event: {event}")
            return

        if event in ["done", "abort"]:
            id, handlers, user = self._current_handlers
            assert id == req_id
            if event == "abort":
                for done in reversed(handlers):
                    await call(done.revert, user)
            self._current_handlers = None
            return

        assert self._current_handlers == None

        handlers = []

        user = {"changes": changes}

        await call(self.pre, user)

        for change in changes:
            cls = self.get_handler(change.xpath)
            if not cls:
                if isinstance(change, sysrepo.ChangeDeleted):
                    continue
                raise sysrepo.SysrepoUnsupportedError(f"{change.xpath} not supported")

            h = cls(self, change)

            # to support async initialization
            init = getattr(h, "_init", None)
            if init:
                await call(init, user)

            await call(h.validate, user)
            handlers.append(h)

        for i, handler in enumerate(handlers):
            try:
                await call(handler.apply, user)
            except Exception as e:
                for done in reversed(handlers[:i]):
                    await call(done.revert, user)
                raise e

        await call(self.post, user)
        self._current_handlers = (req_id, handlers, user)

    def pre(self, user):
        pass

    def post(self, user):
        pass

    def oper_cb(self, xpath, priv):
        logger.debug(f"{xpath=}")
        return

    def send_notification(self, name, notification):
        ly_ctx = self.sess.get_ly_ctx()
        n = json.dumps({name: notification})
        dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
        logger.debug(dnode.print_dict())
        return self.sess.notification_send_ly(dnode)
