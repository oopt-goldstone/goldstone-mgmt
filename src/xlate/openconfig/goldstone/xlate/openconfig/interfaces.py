import logging
import sysrepo
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
            sess.set_item(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                name,
            )
            sess.set_item(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                "UP" if self.change.value else "DOWN",
            )
        else:
            sess.delete_item(
                f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
            )


class InterfaceServer(ServerBase):
    def __init__(self, conn, reconciliation_interval=10):
        super().__init__(conn, "openconfig-interfaces")
        self.conn = conn
        self.sess = self.conn.start_session()
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
            self.sess.switch_datastore("running")
            for config in data:
                name = config["name"]

                c = config.get("config")
                if c == None:
                    continue

                self.sess.set_item(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/name",
                    name,
                )

                enabled = c.get("enabled")
                if enabled != None:
                    self.sess.set_item(
                        f"/goldstone-interfaces:interfaces/interface[name='{name}']/config/admin-status",
                        "UP" if enabled else "DOWN",
                    )
            self.sess.apply_changes()

    async def start(self):
        tasks = await super().start()
        if self.reconciliation_interval > 0:
            self.reconcile_task = asyncio.create_task(self.reconcile_loop())
            tasks.append(self.reconcile_task)

        return tasks

    async def stop(self):
        if self.reconcile_task:
            self.reconcile_task.cancel()
            while True:
                if self.reconcile_task.done():
                    break
                await asyncio.sleep(0.1)
        self.sess.stop()

    def pre(self, user):
        sess = self.conn.start_session()
        sess.switch_datastore("running")
        user["sess"] = sess

    async def post(self, user):
        user["sess"].apply_changes()
        user["sess"].stop()

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
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
