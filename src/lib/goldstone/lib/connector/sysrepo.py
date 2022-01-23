from .base import (
    Connector as BaseConnector,
    Session as BaseSession,
    Node as BaseNode,
    Error,
    DatastoreLocked,
)

import sysrepo
import libyang
import logging

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 10_000


def wrap_sysrepo_error(func):
    def f(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except sysrepo.SysrepoError as error:
            sess = args[0].session
            sess.discard_changes()
            raise Error(error.details[0][1])
        except sysrepo.SysrepoLockedError as error:
            sess = args[0].session
            sess.discard_changes()
            raise DatastoreLocked(f"{xpath} is locked", error)

    return f


class Node(BaseNode):
    def __init__(self, node):
        self.node = node

    def name(self):
        return self.node.name()

    def children(self):
        return [Node(v) for v in self.node]

    def type(self):
        return str(self.node.type())

    def enums(self):
        return self.node.type().all_enums()

    def range(self):
        return self.node.type().range()


class Session(BaseSession):
    def __init__(self, conn, ds):
        self.conn = conn
        self.session = conn.start_session(ds)
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
                DEFAULT_TIMEOUT_MS,
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
        return self.session.replace_config({}, model)

    @wrap_sysrepo_error
    def apply(self):
        return self.session.apply_changes()

    @wrap_sysrepo_error
    def discard_changes(self):
        return self.session.discard_changes()

    def subscribe_notifications(self, model, callback):
        ctx = self.conn.get_ly_ctx()
        module = ctx.get_module(model)
        notif = list(module.children(types=(libyang.SNode.NOTIF,)))
        if len(notif) > 0:
            self.session.subscribe_notification_tree(
                model, f"/{model}:*", 0, 0, callback
            )

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

    def new_session(self, ds="running"):
        return Session(self.conn, ds)

    @property
    def models(self):
        ctx = self.conn.get_ly_ctx()
        return [m.name() for m in ctx]

    def find_node(self, xpath):
        ctx = self.conn.get_ly_ctx()
        node = [n for n in ctx.find_path(xpath)]
        assert len(node) == 1
        return Node(node[0])

    def save(self, model):
        try:
            self.startup_session.copy_config("running", m)
        except sysrepo.SysrepoError as e:
            raise Error(str(e))

    def rpc(self, xpath, args):
        return self.running_session.rpc(xpath, args)

    def set(self, xpath, value):
        return self.running_session.set(xpath, value)

    def delete(self, xpath):
        return self.running_session.delete(xpath)

    def delete_all(self, model):
        return self.running_session.replace_config({}, model)

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
        return self.operational_session.get(
            xpath, default, include_implicit_defaults, strip, one
        )

    def get_startup(self, xpath):
        return self.startup_session.get(xpath)
