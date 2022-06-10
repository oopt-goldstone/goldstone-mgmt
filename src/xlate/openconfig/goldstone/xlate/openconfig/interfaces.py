import logging
import libyang
import asyncio
from goldstone.lib.core import *

logger = logging.getLogger(__name__)


class IfChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "openconfig-interfaces"
        assert xpath[0][1] == "interfaces"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        self.ifname = xpath[1][2][0][1]


class AdminStatusHandler(IfChangeHandler):
    def apply(self, user):
        sess = user["sess"]
        name = self.ifname
        logger.info(f"value: {self.change.value}")
        if self.type in ["created", "modified"]:
            sess.set(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            sess.set(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                "UP" if self.change.value else "DOWN",
            )
        else:
            sess.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
            )


class InterfaceServer(ServerBase):
    def __init__(self, conn, reconciliation_interval=10):
        super().__init__(conn, "openconfig-interfaces")
        self.reconciliation_interval = reconciliation_interval
        self.reconcile_task = None
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "enabled": AdminStatusHandler,
                        "name": NoOp,
                        "type": NoOp,
                        "loopback-mode": NoOp,
                    },
                    "hold-time": NoOp,
                    "ethernet": NoOp,
                    #                    "ethernet": {
                    #                        "config": {
                    #                            "auto-negotiate": AutoNegotiateHandler,
                    #                            "standalone-link-training": StandaloneLineTrainingHandler,
                    #                            "enable-flow_control": FlowControlHandler,
                    #                        }
                    #                    },
                }
            }
        }

    async def reconcile_loop(self):
        while True:
            await asyncio.sleep(self.reconciliation_interval)
            data = self.get_running_data(
                "/openconfig-interfaces:interfaces/interface", []
            )
            sess = self.conn.conn.new_session()
            for config in data:
                name = config["name"]

                c = config.get("config")
                if c == None:
                    continue

                sess.set(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                    name,
                )

                enabled = c.get("enabled")
                if enabled != None:
                    sess.set(
                        f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                        "UP" if enabled else "DOWN",
                    )
            sess.apply()
            sess.stop()

    async def start(self):
        tasks = await super().start()
        if self.reconciliation_interval > 0:
            self.reconcile_task = self.reconcile_loop()
            tasks.append(self.reconcile_task)

        return tasks

    def stop(self):
        self.conn.stop()

    def pre(self, user):
        sess = self.conn.conn.new_session()
        user["sess"] = sess

    async def post(self, user):
        user["sess"].apply()
        user["sess"].stop()

    def oper_cb(self, xpath, priv):
        xpath = "/goldstone-interfaces:interfaces/interface"
        data = self.get_operational_data(xpath, [])
        interfaces = []

        for i in data:
            intf = {
                "name": i["name"],
                "state": {
                    "name": i["name"],
                    "type": "iana-if-type:ethernetCsmacd",
                },
            }
            for v in ["mtu", "admin-status", "oper-status", "description", "counters"]:
                value = i["state"].get(v)
                if value:
                    intf["state"][v] = value

            interfaces.append(intf)

        return {"interfaces": {"interface": interfaces}}
