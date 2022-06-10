import json
import inspect
import sysrepo

from .base import ServerConnector as BaseServerConnector
import goldstone.lib.errors
from goldstone.lib.errors import *


class Change:
    def __init__(self, change):
        self._raw = change

    def __repr__(self):
        return self._raw.__repr__()

    @property
    def type(self):
        if isinstance(self._raw, sysrepo.ChangeCreated):
            return "created"
        elif isinstance(self._raw, sysrepo.ChangeModified):
            return "modified"
        elif isinstance(self._raw, sysrepo.ChangeDeleted):
            return "deleted"

        raise InvalArgError(f"unsupported change type: {type(self._raw)}")

    def __getattr__(self, name):
        return getattr(self._raw, name)


# create a map which maps goldstone.lib.errors and sysrepo.errors
_errors = [(v, getattr(goldstone.lib.errors, v)) for v in dir(goldstone.lib.errors)]
_errors = [(n, t) for n, t in _errors if type(t) == type]
_error_map = {t: getattr(sysrepo, f"Sysrepo{n}") for n, t in _errors}

# convert goldstone.lib.errors to sysrepo.errors
def convert2sysrepo(e):
    sr_e = _error_map.get(type(e))
    if sr_e:
        return sr_e(e.msg)
    return sysrepo.SysrepoError(e.msg)


class ServerConnector(BaseServerConnector):
    def __init__(self, conn, module):
        self.conn = conn
        self.session = conn.new_session("running")

        self.ctx = self.session.session.get_ly_ctx()
        m = self.ctx.get_module(module)
        v = [n.name() for n in m if n.keyword() == "container"]
        assert len(v) == 1
        self.module = module
        self.top = f"/{self.module}:{v[0]}"
        self.change_cb = None

    @property
    def type(self):
        return self.conn.type

    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        return self.conn.get(xpath, default, include_implicit_defaults, strip, one, ds)

    def send_notification(self, name: str, notification: dict):
        return self.session.send_notification(name, notification)

    def subscribe_module_change(self, change_cb, priv=None):
        if self.change_cb:
            raise Error("already subscribed")
        self.change_cb = change_cb
        self.session.session.subscribe_module_change(
            self.module, None, self._change_cb, asyncio_register=True, private_data=priv
        )

    async def _change_cb(self, event, req_id, changes, priv):
        try:
            await self.change_cb(event, req_id, [Change(c) for c in changes], priv)
        except Error as e:
            raise convert2sysrepo(e) from None

    def subscribe_oper_data_request(self, oper_cb):
        asyncio_register = inspect.iscoroutinefunction(oper_cb)
        self.session.session.subscribe_oper_data_request(
            self.module,
            self.top,
            oper_cb,
            oper_merge=True,
            asyncio_register=asyncio_register,
        )

    def get_config_cache(self, changes):
        cache = self.get(
            self.top,
            default={},
            strip=False,
            include_implicit_defaults=True,
        )
        sysrepo.update_config_cache(cache, [c._raw for c in changes])
        return cache

    def subscribe_notification(self, module, xpath, cb, priv=None):
        asyncio_register = inspect.iscoroutinefunction(cb)
        return self.session.session.subscribe_notification(
            module, xpath, cb, asyncio_register=asyncio_register, private_data=priv
        )

    def subscribe_rpc_call(self, xpath, cb):
        asyncio_register = inspect.iscoroutinefunction(cb)
        return self.session.session.subscribe_rpc_call(
            xpath, cb, asyncio_register=asyncio_register
        )

    def find_node(self, xpath):
        return self.conn.find_node(xpath)

    def stop(self):
        self.session.stop()
