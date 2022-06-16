import libyang
import logging
import asyncio
import os
import time

from .server_connector import create_server_connector
from .errors import InvalArgError, InternalError, UnsupportedError
from .util import call

logger = logging.getLogger(__name__)

DEFAULT_REVERT_TIMEOUT = int(os.getenv("GOLDSTONE_DEFAULT_REVERT_TIMEOUT", 6))


class ChangeHandler(object):
    def __init__(self, server, change):
        self.server = server
        self.change = change
        self.type = self.change.type

    def setup_cache(self, user):
        cache = user.get("cache")
        if not user.get("cache"):
            cache = self.server.conn.get_config_cache(user["changes"])
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
    def __init__(self, conn, module, revert_timeout=DEFAULT_REVERT_TIMEOUT):
        self.conn = create_server_connector(conn, module)
        self.handlers = {}
        self._current_handlers = None  # (req_id, handlers, user)
        self._stop_event = asyncio.Event()
        self.revert_timeout = revert_timeout
        self.lock = asyncio.Lock()

    def get_running_data(
        self, xpath, default=None, strip=True, include_implicit_defaults=False
    ):
        return self.conn.get(
            xpath,
            default=default,
            strip=strip,
            include_implicit_defaults=include_implicit_defaults,
        )

    def get_operational_data(
        self, xpath, default=None, strip=True, include_implicit_defaults=False
    ):
        return self.conn.get_operational(
            xpath,
            default=default,
            strip=strip,
            include_implicit_defaults=include_implicit_defaults,
        )

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
        self.conn.subscribe_module_change(self.change_cb)
        self.conn.subscribe_oper_data_request(self._oper_cb)

        return [self._stop_event.wait()]

    def stop(self):
        self._stop_event.set()
        self.conn.stop()

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
    #
    # ## Client side timeout handling
    # When timeout of client expired during 'change' event handling, sysrepo doesn't issue any event.
    # We create a task that waits for "done" or "abort" event after finishing "change" event handling.
    # If no event arrives within certain amount of time, assume it as client timeout happens then clal revert()
    # of the stored handlers.
    # If "done" or "abort" event arrives within the time window, cancel this task.

    async def change_cb(self, event, req_id, changes, priv):
        logger.debug(f"id: {req_id}, event: {event}, changes: {changes}")

        async with self.lock:

            if event not in ["change", "done", "abort"]:
                logger.warning(f"unsupported event: {event}")
                return

            if event in ["done", "abort"]:
                if self._current_handlers == None:
                    logger.error(f"current_handlers is null")
                    self._stop_event.set()
                    raise InternalError("fatal error happened")

                id, handlers, user, revert_task = self._current_handlers
                revert_task.cancel()
                try:
                    await revert_task
                except asyncio.CancelledError:
                    pass

                if id != req_id:
                    logger.error(f"{id=} != {req_id=}")
                    self._stop_event.set()
                    raise InternalError("fatal error happened")

                if event == "abort":
                    for done in reversed(handlers):
                        await call(done.revert, user)
                self._current_handlers = None
                return

            if self._current_handlers != None:
                id, handlers, user, revert_task = self._current_handlers
                raise InternalError(
                    f"waiting 'done' or 'abort' event for id {id}. got '{event}' event for id {req_id}"
                )

            handlers = []

            user = {"changes": changes}

            await call(self.pre, user)

            for change in changes:
                cls = self.get_handler(change.xpath)
                if not cls:
                    if change.type == "deleted":
                        continue
                    raise UnsupportedError(f"{change.xpath} not supported")

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

            async def do_revert():
                await asyncio.sleep(self.revert_timeout)
                logging.warning("client timeout happens? reverting changes we made")
                for done in reversed(handlers):
                    await call(done.revert, user)
                self._current_handlers = None

            revert_task = asyncio.create_task(do_revert())
            self._current_handlers = (req_id, handlers, user, revert_task)

    def pre(self, user):
        pass

    def post(self, user):
        pass

    async def _oper_cb(self, xpath, priv):
        logger.debug(f"xpath: {xpath}")
        time_start = time.perf_counter_ns()
        data = await call(self.oper_cb, xpath, priv)
        time_end = time.perf_counter_ns()
        elapsed = (time_end - time_start) / 1000_1000_10
        logger.debug(f"xpath: {xpath}, elapsed: {elapsed}sec")
        return data

    def oper_cb(self, xpath, priv):
        pass

    def send_notification(self, name, notification):
        return self.conn.send_notification(name, notification)
