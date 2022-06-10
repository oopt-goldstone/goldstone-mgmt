import libyang
import taish
import asyncio
import logging
import json

from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.errors import *

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
            raise InvalArgError(f"Invalid DPLL name: {self.module_name}")

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
                    raise InvalArgError(e.msg)
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
                    raise InvalArgError(
                        f"no default value. cannot remove the configuration"
                    )
                else:
                    self.value.append(cap.default_value)
            else:
                v = self.to_tai_value(self.change.value, name)
                if cap.min != "" and float(cap.min) > float(v):
                    raise InvalArgError(f"minimum {k} value is {cap.min}. given {v}")

                if cap.max != "" and float(cap.max) < float(v):
                    raise InvalArgError(f"maximum {k} value is {cap.max}. given {v}")

                valids = cap.supportedvalues
                if len(valids) > 0 and v not in valids:
                    raise InvalArgError(f"supported values are {valids}. given {v}")

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


class PhaseSlopeLimitHandler(DPLLChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "phase-slope-limit"

    def to_tai_value(self, v, attr_name):
        if v == "unlimitted":
            return "0"
        return str(v)


class LoopBandwidthHandler(DPLLChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "loop-bandwidth"

    def to_tai_value(self, v, attr_name):
        return str(v)


class PriorityChangeHandler(DPLLChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        assert self.xpath[3][2][0][0] == "name"
        self.ref_name = int(self.xpath[3][2][0][1])
        self.tai_attr_name = ["input-reference-priority"]

    async def validate(self, user):
        prio = user.get("current-input-reference-priority")
        if not prio:
            prio = (await self.obj.get("input-reference-priority")).split(",")

        if self.type == "deleted":
            prio[self.ref_name] = str(self.ref_name)  # TODO proper default handling
        else:
            prio[self.ref_name] = str(self.change.value)

        self.value = [",".join(prio)]
        user["current-input-reference-priority"] = prio


class DPLLServer(ServerBase):
    def __init__(self, conn, taish_server, platform_info):
        super().__init__(conn, "goldstone-dpll")
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.refinfo = {}
        for i in platform_info:
            if "input-reference" in i:
                c = i["input-reference"]
                dpll = c["dpll"]["name"]
                if dpll not in self.refinfo:
                    self.refinfo[dpll] = {}

                try:
                    self.refinfo[dpll][int(c["name"])] = i
                except ValueError as e:
                    logger.error("input-reference name must be int")
                    raise

        self.handlers = {
            "dplls": {
                "dpll": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                        "mode": ModeChangeHandler,
                        "phase-slope-limit": PhaseSlopeLimitHandler,
                        "loop-bandwidth": LoopBandwidthHandler,
                    },
                    "input-references": {
                        "input-reference": {
                            "name": NoOp,
                            "config": {"name": NoOp, "priority": PriorityChangeHandler},
                        },
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
            mode, psl, bw, state, prios, selected = await m.get_multiple(
                [
                    "dpll-mode",
                    "phase-slope-limit",
                    "loop-bandwidth",
                    "dpll-state",
                    "input-reference-priority",
                    "selected-reference",
                ]
            )

            if psl == "0":
                psl = "unlimitted"

            d["state"] = {
                "mode": mode,
                "phase-slope-limit": psl,
                "loop-bandwidth": float(bw),
                "state": state,
            }

            prios = prios.split(",")
            refs = []

            for ref in self.refinfo.get(name, {}).keys():
                r = {"name": str(ref), "config": {"name": str(ref)}}
                try:
                    prio = prios[ref]
                    state = {"priority": int(prio)}
                    v = await m.get(f"ref-alarm-{ref}")
                    if v:
                        state["alarm"] = v.split("|")
                    r["state"] = state
                except:
                    pass
                refs.append(r)

            if int(selected) in self.refinfo.get(name, {}):
                d["state"]["selected-reference"] = selected

            d["input-references"] = {"input-reference": refs}
            dplls.append(d)

        return {"goldstone-dpll:dplls": {"dpll": dplls}}
