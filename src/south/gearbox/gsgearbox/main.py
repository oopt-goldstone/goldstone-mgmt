import sysrepo
import libyang
import logging
import taish
import asyncio
import argparse
import json
import signal
from aiohttp import web

logger = logging.getLogger(__name__)


class Server(object):
    def __init__(self, taish_server):
        self.ataish = taish.AsyncClient(*taish_server.split(":"))
        self.taish = taish.Client(*taish_server.split(":"))
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.notif_q = asyncio.Queue()

        routes = web.RouteTableDef()

        @routes.get("/healthz")
        async def probe(request):
            return web.Response()

        app = web.Application()
        app.add_routes(routes)

        self.runner = web.AppRunner(app)
        self.event_obj = {}

    async def stop(self):
        logger.info(f"stop server")
        for v in self.event_obj.values():
            v["event"].set()
            await v["task"]

        await self.runner.cleanup()
        self.sess.stop()
        self.conn.disconnect()
        self.ataish.close()
        self.taish.close()

    def get_sr_data(
        self, xpath, datastore, default=None, include_implicit_defaults=False
    ):
        self.sess.switch_datastore(datastore)
        try:
            v = self.sess.get_data(
                xpath, include_implicit_defaults=include_implicit_defaults
            )
        except sysrepo.errors.SysrepoNotFoundError:
            logger.debug(
                f"xpath: {xpath}, ds: {datastore}, not found. returning {default}"
            )
            return default
        v = libyang.xpath_get(v, xpath, default)
        logger.debug(f"xpath: {xpath}, ds: {datastore}, value: {v}")
        return v

    def get_running_data(self, xpath, default=None, include_implicit_defaults=False):
        return self.get_sr_data(xpath, "running", default, include_implicit_defaults)

    def get_operational_data(
        self, xpath, default=None, include_implicit_defaults=False
    ):
        return self.get_sr_data(
            xpath, "operational", default, include_implicit_defaults
        )

    def get_ifname_list(self):
        modules = self.taish.list()

        interfaces = []
        for loc, module in modules.items():
            m = self.taish.get_module(loc)
            for hostif in m.obj.hostifs:
                interfaces.append(f"Ethernet{loc}/0/{hostif.index+1}")
            for netif in m.obj.netifs:
                interfaces.append(f"Ethernet{loc}/1/{netif.index+1}")

        return interfaces

    def gearbox_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")
            return

    async def gearbox_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")

    def ifname2taiobj(self, ifname):
        v = [int(v) for v in ifname.replace("Ethernet", "").split("/")]
        m = self.taish.get_module(str(v[0]))
        if v[1] == 0:  # hostif
            return m.get_hostif(v[2] - 1)
        elif v[1] == 1:  # netif
            return m.get_netif(v[2] - 1)
        return None

    def parse_intf_change_req(self, xpath):
        xpath = list(libyang.xpath_split(xpath))
        if len(xpath) < 2:
            return None, None

        if xpath[1][2][0][0] != "name":
            return None, None

        obj = self.ifname2taiobj(xpath[1][2][0][1])
        if not obj:
            return None, None

        if len(xpath) < 4:
            return obj, None

        if xpath[2][1] != "config":
            return obj, None

        return obj, xpath[3][1]

    def interface_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change"]:
            logger.warn(f"no-op event: {event}")
            return

        for change in changes:
            logger.debug(f"event: {event}, type: {type(change)}, change: {change}")
            obj, key = self.parse_intf_change_req(change.xpath)
            logger.debug(f"obj: {obj}, key: {key}")
            if key == "admin-status":
                key = "tx-dis"
                value = "false" if change.value == "UP" else "true"
                obj.set(key, value)
            elif key in [None, "name"]:
                pass
            else:
                logger.warn(f"{key} not implemented yet")
                # raise sysrepo.SysrepoInvalArgError(f"{key} not implemented")

    async def interface_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        xpath = list(libyang.xpath_split(req_xpath))
        logger.debug(f"xpath: {xpath}")

        if len(xpath) < 2 or len(xpath[1][2]) < 1:
            ifnames = self.get_ifname_list()
        else:
            if xpath[1][2][0][0] != "name":
                logger.warn(f"invalid request: {xpath}")
                return
            ifnames = [xpath[1][2][0][1]]

        interfaces = []
        for ifname in ifnames:
            i = {"name": ifname, "config": {"name": ifname}}
            if len(xpath) == 3 and xpath[2][1] == "name":
                interfaces.append(i)
                continue

            obj = self.ifname2taiobj(ifname)
            state = {}
            leaves = [
                (
                    "admin-status",
                    lambda: "DOWN" if obj.get("tx-dis") == "true" else "UP",
                ),
                (
                    "oper-status",
                    lambda: "UP" if "ready" in obj.get("pcs-status") else "DOWN",
                ),
                ("fec", lambda: obj.get("fec-type").upper()),
                (
                    "speed",
                    lambda: "SPEED_100G"
                    if obj.get("signal-rate") == "100-gbe"
                    else "SPEED_UNKNOWN",
                ),
            ]
            for l in leaves:
                try:
                    state[l[0]] = l[1]()
                except taish.TAIException:
                    pass

            i["state"] = state

            interfaces.append(i)

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

    def get_default(self, key, model="goldstone-interfaces"):
        ctx = self.sess.get_ly_ctx()
        if model == "goldstone-interfaces":
            keys = ["interfaces", "interface", "config", key]
        elif model == "goldstone-gearbox":
            keys = ["gearboxes", "gearbox", "config", key]
        else:
            return None

        xpath = "".join(f"/{model}:{v}" for v in keys)

        for node in ctx.find_path(xpath):
            return node.default()

    async def reconcile(self):
        self.sess.switch_datastore("running")

        modules = await self.ataish.list()
        for loc in modules.keys():
            module = await self.ataish.get_module(loc)
            admin_status = self.get_running_data(
                f"/goldstone-gearbox:gearboxes/gearbox[name='{loc}']/config/admin-status",
                self.get_default("admin-status", "goldstone-gearbox"),
            )
            await module.set("admin-status", admin_status.lower())

        ifnames = self.get_ifname_list()
        for ifname in ifnames:
            admin_status = self.get_running_data(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status",
                self.get_default("admin-status"),
            )
            obj = self.ifname2taiobj(ifname)
            obj.set("tx-dis", "false" if admin_status == "UP" else "true")

    async def start(self):

        with self.sess.lock("goldstone-interfaces"):

            await self.reconcile()

            self.sess.switch_datastore("running")

            self.sess.subscribe_module_change(
                "goldstone-interfaces",
                None,
                self.interface_change_cb,
            )

            self.sess.subscribe_oper_data_request(
                "goldstone-interfaces",
                "/goldstone-interfaces:interfaces",
                self.interface_oper_cb,
                asyncio_register=True,
            )

            self.sess.subscribe_module_change(
                "goldstone-gearbox",
                None,
                self.gearbox_change_cb,
            )

            self.sess.subscribe_oper_data_request(
                "goldstone-gearbox",
                "/goldstone-gearbox:gearboxes",
                self.gearbox_oper_cb,
                asyncio_register=True,
            )

        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()

        async def ping():
            while True:
                await asyncio.sleep(5)
                try:
                    await asyncio.wait_for(self.ataish.list(), timeout=2)
                except Exception as e:
                    logger.error(f"ping failed {e}")
                    return

        return [ping()]


def main():
    async def _main(taish_server):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server(taish_server)

        try:
            tasks = await server.start()
            tasks.append(stop_event.wait())
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            await server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-s", "--taish-server", default="127.0.0.1:50051")

    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        # hpack debug log is too verbose. change it INFO level
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
    #        sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main(args.taish_server))


if __name__ == "__main__":
    main()
