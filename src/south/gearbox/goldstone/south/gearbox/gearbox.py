from goldstone.lib.core import ServerBase
import libyang
import asyncio
import sysrepo
import logging
import json
from .interfaces import IfChangeHandler

logger = logging.getLogger(__name__)


class GearboxChangeHandler(IfChangeHandler):
    async def _init(self, user):
        xpath = self.change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-gearbox"
        assert xpath[0][1] == "gearboxes"
        assert xpath[1][1] == "gearbox"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        self.module_name = xpath[1][2][0][1]

        l = await self.server.ifserver.list_modules()
        if self.module_name not in l.keys():
            raise sysrepo.SysrepoInvalArgError(
                f"Invalid Gearbox name: {self.module_name}"
            )

        self.obj = await self.server.taish.get_module(self.module_name)
        self.tai_attr_name = None


class AdminStatusHandler(GearboxChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "admin-status"

    def to_tai_value(self, v, attr_name):
        return "up" if v == "UP" else "down"


class UpdateTributaryMapping(GearboxChangeHandler):
    async def validate(self, user):
        self.setup_cache(user)
        user["update-tributary-mapping"] = True


class GearboxServer(ServerBase):
    def __init__(self, conn, interface_server):
        super().__init__(conn, "goldstone-gearbox")
        self.ifserver = interface_server
        self.taish = self.ifserver.taish
        self.oidmap = {}  # key: oid, value: obj
        self.ifnamemap = {}  # key: ifname, value: oid
        self.handlers = {
            "gearboxes": {
                "gearbox": {
                    "name": GearboxChangeHandler,
                    "config": {
                        "admin-status": AdminStatusHandler,
                        "name": GearboxChangeHandler,
                        "enable-flexible-connection": UpdateTributaryMapping,
                    },
                    "connections": {
                        "connection": {
                            "client-interface": UpdateTributaryMapping,
                            "line-interface": UpdateTributaryMapping,
                            "config": UpdateTributaryMapping,
                        }
                    },
                }
            }
        }

    def get_default_mapping(self, module):
        mapping = []
        for netif, hostif in zip(module.obj.netifs, module.obj.hostifs):
            mapping.append({f"oid:0x{netif.oid:08x}": [f"oid:0x{hostif.oid:08x}"]})
        return json.dumps(mapping)

    def get_default(self, key):
        ctx = self.sess.get_ly_ctx()
        keys = [["gearboxes", "gearbox", "config", key]]

        for k in keys:
            xpath = "".join(f"/goldstone-gearbox:{v}" for v in k)
            try:
                for node in ctx.find_path(xpath):
                    if node.type().name() == "boolean":
                        return node.default() == "true"
                    return node.default()
            except libyang.util.LibyangError:
                pass

        return None

    async def post(self, user):
        if not user.get("update-tributary-mapping"):
            return

        cache = user.get("cache")

        modules = await self.ifserver.list_modules()
        prefix = "/goldstone-gearbox:gearboxes/gearbox"
        for loc in modules.keys():
            m = await self.taish.get_module(loc)
            xpath = f"{prefix}[name='{loc}']/config/enable-flexible-connection"
            flex = libyang.xpath_get(cache, xpath, False)

            if not flex:
                mapping = self.get_default_mapping(m)
                logger.debug(f"setting the default mapping({loc}): {mapping}")
            else:
                xpath = f"{prefix}[name='{loc}']/connections/connection"
                connections = libyang.xpath_get(cache, xpath, [])
                mapping = []
                for c in connections:
                    line = self.ifnamemap[c["config"]["line-interface"]]
                    client = self.ifnamemap[c["config"]["client-interface"]]
                    mapping.append({f"oid:0x{line:08x}": [f"oid:0x{client:08x}"]})
                mapping = json.dumps(mapping)
                logger.debug(f"setting mapping({loc}): {mapping}")

            await m.set("tributary-mapping", mapping)

    async def reconcile(self):
        self.taish._ignored_module = []  # modules to ignore
        modules = await self.ifserver.list_modules()
        prefix = "/goldstone-gearbox:gearboxes/gearbox"

        for loc in modules.keys():
            m = await self.taish.get_module(loc)
            for i in range(len(m.obj.netifs)):
                obj = m.get_netif(i)
                self.oidmap[obj.oid] = obj
                name = f"Interface{loc}/1/{i+1}"
                self.ifnamemap[name] = obj.oid

            for i in range(len(m.obj.hostifs)):
                obj = m.get_hostif(i)
                self.oidmap[obj.oid] = obj
                name = f"Interface{loc}/0/{i+1}"
                self.ifnamemap[name] = obj.oid

        async def init(loc):
            m = await self.taish.get_module(loc)
            xpath = f"{prefix}[name='{loc}']/config/enable-flexible-connection"
            flex = self.get_running_data(xpath, False)

            if not flex:
                mapping = self.get_default_mapping(m)
                logger.debug(f"setting the default mapping({loc}): {mapping}")
            else:
                xpath = f"{prefix}[name='{loc}']/connections/connection"
                connections = self.get_running_data(xpath, [])
                mapping = []
                for c in connections:
                    line = self.ifnamemap[c["config"]["line-interface"]]
                    client = self.ifnamemap[c["config"]["client-interface"]]
                    mapping.append({f"oid:0x{line:08x}": [f"oid:0x{client:08x}"]})
                mapping = json.dumps(mapping)
                logger.debug(f"setting mapping({loc}): {mapping}")

            await m.set("tributary-mapping", mapping)

            xpath = f"{prefix}[name='{loc}']/config/admin-status"
            admin_status = self.get_running_data(xpath, "UP")
            await m.set("admin-status", admin_status.lower())

            if admin_status == "UP":
                while True:
                    v = await m.get("oper-status")
                    logger.debug(f"oper-status(loc:{loc}): {v}")
                    if v == "ready":
                        return
                    elif v == "unknown":
                        logger.warning(
                            f"module(loc:{loc}) malfunctioning. ignore this module"
                        )
                        self.taish._ignored_module.append(loc)
                        return
                    await asyncio.sleep(1)

        done, pending = await asyncio.wait(
            [asyncio.create_task(init(loc)) for loc in modules.keys()],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        for task in done:
            if task.exception():
                raise task.exception()

    async def start(self):

        await self.reconcile()

        await self.ifserver.reconcile()

        return await super().start()

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        xpath = list(libyang.xpath_split(req_xpath))
        logger.debug(f"xpath: {xpath}")

        if len(xpath) < 2 or len(xpath[1][2]) < 1:
            module_names = (await self.ifserver.list_modules()).keys()
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

            prefix = "/goldstone-gearbox:gearboxes/gearbox"
            xpath = f"{prefix}[name='{name}']/config/enable-flexible-connection"
            flex = self.get_running_data(xpath, False)

            g["state"] = {
                "admin-status": admin_status.upper(),
                "oper-status": oper_status,
                "enable-flexible-connection": flex,
            }

            connections = []

            for v in json.loads(await m.get("tributary-mapping", json=True)):
                if len(v) != 1:
                    logger.warning(f"invalid tributary-mapping item: {v}")
                    continue
                for netif, hostif in v.items():
                    if len(hostif) != 1:
                        logger.warning(f"invalid tributary-mapping item: {v}")
                        continue
                    hostif = hostif[0]

                obj = self.oidmap.get(int(netif.replace("oid:", ""), 0))
                if not obj:
                    logger.warning(f"not found {netif}")
                    continue
                netif = await self.ifserver.taiobj2ifname(m.obj.location, 1, obj)

                obj = self.oidmap.get(int(hostif.replace("oid:", ""), 0))
                if not obj:
                    logger.warning(f"not found {hostif}")
                    continue
                hostif = await self.ifserver.taiobj2ifname(m.obj.location, 0, obj)

                connections.append(
                    {
                        "client-interface": hostif,
                        "line-interface": netif,
                    }
                )

            g["connections"] = {"connection": connections}

            gearboxes.append(g)

        return {"goldstone-gearbox:gearboxes": {"gearbox": gearboxes}}
