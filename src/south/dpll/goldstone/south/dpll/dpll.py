from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
import libyang
import taish
import asyncio
import sysrepo
import logging
import json

logger = logging.getLogger(__name__)


class DPLLChangeHandler(ChangeHandler):
    async def _init(self, user):
        xpath = self.change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-dpll"
        assert xpath[0][1] == "dplls"
        assert xpath[1][1] == "dpll"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        self.module_name = xpath[1][2][0][1]

        l = await self.server.taish.list()
        if self.module_name not in l.keys():
            raise sysrepo.SysrepoInvalArgError(f"Invalid DPLL name: {self.module_name}")

        self.obj = await self.server.taish.get_module(self.module_name)
        self.tai_attr_name = None

    async def validate(self, user):
        if not self.tai_attr_name:
            return

        if type(self.tai_attr_name) != list:
            self.tai_attr_name = [self.tai_attr_name]

        self.value = []

        if "cap-cache" not in user:
            user["cap-cache"] = {}

        for name in self.tai_attr_name:
            cap = user["cap-cache"].get(name)
            if cap == None:
                try:
                    cap = await self.obj.get_attribute_capability(name)
                except taish.TAIException as e:
                    logger.error(f"failed to get capability: {name}")
                    raise sysrepo.SysrepoInvalArgError(e.msg)
                logger.info(f"cap {name}: {cap}")
                user["cap-cache"][name] = cap
            else:
                logger.info(f"cached cap {name}: {cap}")

            if self.type == "deleted":
                leaf = self.xpath[-1][1]
                d = self.server.get_default(leaf)
                if d != None:
                    self.value.append(self.to_tai_value(d, name))
                elif cap.default_value == "":  # and is_deleted
                    raise sysrepo.SysrepoInvalArgError(
                        f"no default value. cannot remove the configuration"
                    )
                else:
                    self.value.append(cap.default_value)
            else:
                v = self.to_tai_value(self.change.value, name)
                if cap.min != "" and float(cap.min) > float(v):
                    raise sysrepo.SysrepoInvalArgError(
                        f"minimum {k} value is {cap.min}. given {v}"
                    )

                if cap.max != "" and float(cap.max) < float(v):
                    raise sysrepo.SysrepoInvalArgError(
                        f"maximum {k} value is {cap.max}. given {v}"
                    )

                valids = cap.supportedvalues
                if len(valids) > 0 and v not in valids:
                    raise sysrepo.SysrepoInvalArgError(
                        f"supported values are {valids}. given {v}"
                    )

                self.value.append(v)

    async def apply(self, user):
        if not self.tai_attr_name:
            return
        self.original_value = await self.obj.get_multiple(self.tai_attr_name)
        _v = []
        for i, name in enumerate(self.tai_attr_name):
            if str(self.original_value[i]) != str(self.value[i]):
                logger.debug(
                    f"applying: {name} {self.original_value[i]} => {self.value[i]}"
                )
                _v.append((name, self.value[i]))
        await self.obj.set_multiple(_v)

    async def revert(self, user):
        if not self.tai_attr_name:
            return
        _v = []
        for i, name in enumerate(self.tai_attr_name):
            if str(self.original_value[i]) != str(self.value[i]):
                logger.warning(
                    f"reverting: {self.name} {self.value[i]} => {self.original_value[i]}"
                )
                _v.append((name, self.original_value[i]))
        await self.obj.set_multiple(_v)


class ModeChangeHandler(DPLLChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "dpll-mode"

    def to_tai_value(self, v, attr_name):
        return v


class DPLLServer(ServerBase):
    def __init__(self, conn, taish_server, platform_info):
        super().__init__(conn, "goldstone-dpll")
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.handlers = {
            "dplls": {
                "dpll": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                        "mode": ModeChangeHandler,
                    },
                },
            },
        }

    def get_default(self, leaf):
        if leaf == "mode":
            return "freerun"

    async def oper_cb(self, xpath, priv):
        xpath = list(libyang.xpath_split(xpath))
        modules = await self.taish.list()

        if len(xpath) < 2 or len(xpath[1][2]) < 1:
            module_names = (await self.taish.list()).keys()
        else:
            if xpath[1][2][0][0] != "name":
                logger.warn(f"invalid request: {xpath}")
                return
            module_names = [xpath[1][2][0][1]]

        dplls = []
        for name in module_names:
            d = {"name": name, "config": {"name": name}}
            if len(xpath) == 3 and xpath[2][1] == "name":
                dplls.append(d)
                continue

            m = await self.taish.get_module(name)
            v = await m.get_multiple(["dpll-mode", "dpll-state"])

            d["state"] = {"mode": v[0], "state": v[1]}

            dplls.append(d)

        return {"goldstone-dpll:dplls": {"dpll": dplls}}
