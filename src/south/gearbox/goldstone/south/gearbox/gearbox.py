from goldstone.lib.core import ServerBase, NoOp
import libyang
import asyncio
import sysrepo
import logging

from .interfaces import IfChangeHandler

logger = logging.getLogger(__name__)


class ChangeHandler(IfChangeHandler):
    async def _init(self, user):
        xpath = self.change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-gearbox"
        assert xpath[0][1] == "gearboxes"
        assert xpath[1][1] == "gearbox"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        module_name = xpath[1][2][0][1]

        l = await self.server.taish.list()
        if module_name not in l.keys():
            raise sysrepo.SysrepoInvalArgError("Invalid Gearbox name")

        self.obj = await self.server.taish.get_module(module_name)


class AdminStatusHandler(ChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "admin-status"

    def to_tai_value(self, v):
        return "up" if v == "UP" else "down"


class GearboxServer(ServerBase):
    def __init__(self, conn, interface_server):
        super().__init__(conn, "goldstone-gearbox")
        self.ifserver = interface_server
        self.taish = self.ifserver.taish
        self.handlers = {
            "gearboxes": {
                "gearbox": {
                    "name": NoOp,
                    "config": {
                        "admin-status": AdminStatusHandler,
                        "name": NoOp,
                    },
                }
            }
        }

    async def reconcile(self):
        modules = await self.taish.list()
        prefix = "/goldstone-gearbox:gearboxes/gearbox"

        async def init(loc):
            m = await self.taish.get_module(loc)
            xpath = f"{prefix}[name='{loc}']/config/admin-status"
            admin_status = self.get_running_data(xpath)
            if admin_status == None:
                admin_status = "UP"
            await m.set("admin-status", admin_status.lower())

            if admin_status == "UP":
                while True:
                    v = await m.get("oper-status")
                    logger.debug(f"oper-status(loc:{loc}): {v}")
                    if v == "ready":
                        return
                    await asyncio.sleep(1)

        await asyncio.wait([asyncio.create_task(init(loc)) for loc in modules.keys()])

    async def start(self):

        await self.reconcile()

        await self.ifserver.reconcile()

        return await super().start()

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        xpath = list(libyang.xpath_split(req_xpath))
        logger.debug(f"xpath: {xpath}")

        if len(xpath) < 2 or len(xpath[1][2]) < 1:
            module_names = (await self.taish.list()).keys()
        else:
            if xpath[1][2][0][0] != "name":
                logger.warn(f"invalid request: {xpath}")
                return
            module_names = [xpath[1][2][0][1]]

        gearboxes = []
        for name in module_names:
            g = {"name": name, "config": {"name": name}}
            if len(xpath) == 3 and xpath[2][1] == "name":
                gearboxes.append(g)
                continue

            m = await self.taish.get_module(name)
            admin_status = "UP" if (await m.get("admin-status")) == "up" else "DOWN"
            oper_status = "UP" if (await m.get("oper-status")) == "ready" else "DOWN"

            g["state"] = {
                "admin-status": admin_status.upper(),
                "oper-status": oper_status,
            }

            gearboxes.append(g)

        return {"goldstone-gearbox:gearboxes": {"gearbox": gearboxes}}
