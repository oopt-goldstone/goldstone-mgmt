from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
import libyang
import asyncio
import sysrepo
import logging
import json

logger = logging.getLogger(__name__)


class IfChangeHandler(ChangeHandler):
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

        self.module = await self.server.taish.get_module(module_name)


class AdminStatusHandler(IfChangeHandler):
    async def apply(self, user):
        self.original_value = await self.module.get("admin-status")
        await self.module.set("admin-status", self.value.lower())

    async def revert(self, user):
        logger.warning(f"reverting: admin-status {self.value} => {self.original_value}")
        await self.module.set("admin-status", self.original_value)


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
