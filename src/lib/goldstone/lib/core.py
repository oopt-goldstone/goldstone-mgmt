import sysrepo
import libyang
import logging
from aiohttp import web

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

    def get_sr_data(self, xpath, datastore, default=None, strip=True):
        self.sess.switch_datastore(datastore)
        try:
            v = self.sess.get_data(xpath)
        except sysrepo.errors.SysrepoNotFoundError:
            logger.debug(
                f"xpath: {xpath}, ds: {datastore}, not found. returning {default}"
            )
            return default
        if strip:
            v = libyang.xpath_get(v, xpath, default)
        logger.debug(f"xpath: {xpath}, ds: {datastore}, value: {v}")
        return v

    def get_running_data(self, xpath, default=None, strip=True):
        return self.get_sr_data(xpath, "running", default, strip)

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
        self.sess.subscribe_module_change(self.module, None, self.change_cb)
        self.sess.subscribe_oper_data_request(
            self.module, self.top, self.oper_cb, oper_merge=True
        )

        return []

    def stop(self):
        self.sess.stop()

    async def reconcile(self):
        logger.debug("reconcile")

    # no 'abort' event handing since this is the only subscriber of the module
    # do the actual change handing in 'change' event
    # 'done' event is no-op
    # 'change' event handling
    # 1. iterate through the changes, do basic validation, degenerate changes if possible
    # 2. do the actual change handling, if any error happens, revert the changes made in advance and raise error
    def change_cb(self, event, req_id, changes, priv):

        if event not in ["change", "done"]:
            logger.warn(f"unsupported event: {event}, id: {req_id}, changes: {changes}")
            return

        if event == "done":
            return

        logger.debug(f"id: {req_id}, changes: {changes}")

        handlers = []

        user = {"changes": changes}

        self.pre(user)

        for change in changes:
            cls = self.get_handler(change.xpath)
            if not cls:
                raise sysrepo.SysrepoUnsupportedError(f"{change.xpath} not supported")

            h = cls(self, change)
            h.validate(user)
            handlers.append(h)

        for i, handler in enumerate(handlers):
            try:
                handler.apply(user)
            except Exception as e:
                for done in reversed(handlers[:i]):
                    done.revert(user)
                raise e

        self.post(user)

    def pre(self, user):
        pass

    def post(self, user):
        pass

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        return
