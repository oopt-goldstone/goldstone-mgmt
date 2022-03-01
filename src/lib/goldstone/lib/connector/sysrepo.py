from .base import (
    Connector as BaseConnector,
    Session as BaseSession,
    Error,
    DatastoreLocked,
)

import sysrepo
import libyang
import logging

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 60_000


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
            raise DatastoreLocked(f"{target} is locked", error)
        except sysrepo.SysrepoError as error:
            sess.discard_changes()
            raise Error(error.details[0][1])
        except libyang.LibyangError as error:
            sess.discard_changes()
            raise Error(str(error))

    return f


class Session(BaseSession):
    def __init__(self, conn, ds):
        self.conn = conn
        self.session = conn.conn.start_session(ds)
        self.ds = ds

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
                0,
                timeout_ms=DEFAULT_TIMEOUT_MS,
                include_implicit_defaults=include_implicit_defaults,
            )
        except (sysrepo.SysrepoNotFoundError, sysrepo.SysrepoInvalArgError):
            logger.debug(
                f"xpath: {xpath}, ds: {self.ds}, not found. returning {default}"
            )
            return default
        except sysrepo.SysrepoError as e:
            raise Error(e)

        if strip:
            data = libyang.xpath_get(
                data,
                xpath,
                default,
                filter=self.ds == "operational",
            )
            if data and one:
                if len(data) == 1:
                    data = data[0]
                elif len(data) > 1:
                    raise Error(f"{xpath} matches more than one item")
        logger.debug(f"xpath: {xpath}, ds: {self.ds}, value: {data}")
        return data

    @wrap_sysrepo_error
    def set(self, xpath, value):
        return self.session.set_item(xpath, value)

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

    def subscribe_notifications(self, callback):
        ctx = self.conn.ctx
        f = lambda xpath, notif_type, value, timestamp, priv: callback(
            {xpath: value, "eventTime": timestamp}
        )

        for model in self.conn.models:
            module = ctx.get_module(model)
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
        self.ctx = self.conn.get_ly_ctx()

    @property
    def type(self):
        return "sysrepo"

    def new_session(self, ds="running"):
        return Session(self, ds)

    @property
    def models(self):
        ctx = self.conn.get_ly_ctx()
        return [m.name() for m in ctx]

    def save(self, model):
        try:
            self.startup_session.copy_config("running", model)
        except sysrepo.SysrepoError as e:
            raise Error(str(e))

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

    def discard_changes(self, model):
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
        return sess.get(xpath, default, include_implicit_defaults, strip, one)

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
