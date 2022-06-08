from .base import (
    Connector as BaseConnector,
    Session as BaseSession,
)

import goldstone.lib.errors
from goldstone.lib.errors import NotFoundError, Error, LockedError, CallbackFailedError

import sysrepo
import libyang
import logging
import inspect

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 60_000

# create a map which maps sysrepo.errors and goldstone.lib.errors
_errors = [(v, getattr(goldstone.lib.errors, v)) for v in dir(goldstone.lib.errors)]
_errors = [(n, t) for n, t in _errors if type(t) == type]
_error_map = {getattr(sysrepo, f"Sysrepo{n}"): t for n, t in _errors}


def wrap_sysrepo_error(func):
    def f(*args, **kwargs):
        sess = args[0].session
        try:
            return func(*args, **kwargs)
        except sysrepo.SysrepoLockedError as error:
            sess.discard_changes()
            target = "datastore"
            if len(args) >= 2:
                target = args[1]
            raise LockedError(f"{target} is locked") from None
        except sysrepo.SysrepoError as error:
            sess.discard_changes()
            gs_e = _error_map.get(type(error))
            if gs_e:
                msg = error.err_info[0] if error.err_info else error.msg
                raise gs_e(msg) from None
            raise Error(error.msg) from None
        except libyang.LibyangError as error:
            sess.discard_changes()
            raise Error(str(error)) from error

    return f


class Session(BaseSession):
    def __init__(self, conn, ds):
        self.conn = conn
        self.session = conn.conn.start_session(ds)
        self.ds = ds

    @wrap_sysrepo_error
    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
    ):
        try:
            data = self.session.get_data(
                xpath,
                timeout_ms=DEFAULT_TIMEOUT_MS,
                include_implicit_defaults=include_implicit_defaults,
            )
        except (sysrepo.SysrepoNotFoundError, sysrepo.SysrepoInvalArgError):
            logger.debug(
                f"xpath: {xpath}, ds: {self.ds}, not found. returning {default}"
            )
            return default

        if strip:
            data = libyang.xpath_get(
                data,
                xpath,
                default,
                filter=self.ds == "operational",
            )
            if data and one:
                if len(data) == 1:
                    data = list(data)[0]
                elif len(data) > 1:
                    raise Error(f"{xpath} matches more than one item")
        logger.debug(f"xpath: {xpath}, ds: {self.ds}, value: {data}")
        return data

    @wrap_sysrepo_error
    def set(self, xpath, value):
        x = self.conn.find_node(xpath)
        # if the node is leaf-list and the value is list, replace the whole list with the given value
        # setting to the same leaf-list multiple time is currently not supported
        if x.node.keyword() == "leaf-list" and type(value) == list:
            v = set(self.get(xpath, []))
            for remove in v - set(value):
                x = f"{xpath}[.='{remove}']"
                self.delete(x)
            for add in set(value) - v:
                self.session.set_item(xpath, add)
        else:
            return self.session.set_item(xpath, value)

    @wrap_sysrepo_error
    def copy_config(self, datastore, model):
        return self.session.copy_config(datastore, model)

    @wrap_sysrepo_error
    def delete(self, xpath):
        return self.session.delete_item(xpath)

    @wrap_sysrepo_error
    def delete_all(self, model):
        return self.session.replace_config({}, model, timeout_ms=DEFAULT_TIMEOUT_MS)

    @wrap_sysrepo_error
    def apply(self):
        return self.session.apply_changes(timeout_ms=DEFAULT_TIMEOUT_MS)

    @wrap_sysrepo_error
    def discard_changes(self):
        return self.session.discard_changes()

    @wrap_sysrepo_error
    def send_notification(self, name: str, notification: dict):
        logger.debug(f"sending notification {name}: {notification}")
        self.session.notification_send(name, notification)

    def subscribe_notification(self, xpath, callback):
        model = xpath.split("/")[1].split(":")[0]
        asyncio_register = inspect.iscoroutinefunction(callback)
        self.session.subscribe_notification(
            model, xpath, callback, asyncio_register=asyncio_register
        )

    def subscribe_notifications(self, callback):
        f = lambda xpath, notif_type, value, timestamp, priv: callback(
            {xpath: value, "eventTime": timestamp}
        )

        for model in self.conn.models:
            module = self.conn.get_module(model)
            notif = list(module.children(types=(libyang.SNode.NOTIF,)))
            if len(notif) == 0:
                continue

            self.session.subscribe_notification(model, f"/{model}:*", f)

    def stop(self):
        self.session.stop()

    def rpc(self, xpath, args):
        return self.session.rpc_send(xpath, args)


class Connector(BaseConnector):
    def __init__(self):
        self.conn = sysrepo.SysrepoConnection()
        self.running_session = self.new_session()
        self.operational_session = self.new_session("operational")
        self.startup_session = self.new_session("startup")
        self.ctx = self.conn.acquire_context()

    @property
    def type(self):
        return "sysrepo"

    def new_session(self, ds="running"):
        return Session(self, ds)

    @property
    def models(self):
        with self.conn.get_ly_ctx() as ctx:
            return [m.name() for m in ctx]

    def get_module(self, name):
        with self.conn.get_ly_ctx() as ctx:
            return ctx.get_module(name)

    def save(self, model):
        try:
            self.startup_session.copy_config("running", model)
        except sysrepo.SysrepoError as e:
            raise Error(str(e)) from e

    def rpc(self, xpath, args):
        return self.running_session.rpc(xpath, args)

    def set(self, xpath, value):
        return self.running_session.set(xpath, value)

    def delete(self, xpath):
        return self.running_session.delete(xpath)

    def delete_all(self, model):
        return self.running_session.delete_all(model)

    def apply(self):
        return self.running_session.apply()

    def discard_changes(self):
        return self.running_session.discard_changes()

    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        if ds == "running":
            sess = self.running_session
        elif ds == "operational":
            sess = self.operational_session
        elif ds == "startup":
            sess = self.startup_session
        else:
            raise Error(f"unsupported ds: {ds}")

        try:
            return sess.get(xpath, default, include_implicit_defaults, strip, one)
        except sysrepo.SysrepoNotFoundError as e:
            raise NotFoundError(e.msg) from e

    def get_operational(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
    ):
        return self.get(
            xpath, default, include_implicit_defaults, strip, one, ds="operational"
        )

    def get_startup(self, xpath):
        return self.get(xpath, ds="startup")

    def send_notification(self, name: str, notification: dict):
        return self.running_session.send_notification(name, notification)

    def stop(self):
        self.running_session.stop()
        self.operational_session.stop()
        self.startup_session.stop()
        self.conn.release_context()
        self.conn.disconnect()
