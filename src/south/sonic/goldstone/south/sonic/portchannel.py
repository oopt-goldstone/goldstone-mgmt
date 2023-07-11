from goldstone.lib.core import *
from .sonic import *

from goldstone.lib.errors import (
    InvalArgError,
    CallbackFailedError,
)


def _decode(string):
    if hasattr(string, "decode"):
        return string.decode("utf-8")
    return str(string)


class PortChannelChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-portchannel"
        assert xpath[0][1] == "portchannel"
        assert xpath[1][1] == "portchannel-group"
        assert xpath[1][2][0][0] == "portchannel-id"
        self.xpath = xpath
        pid = xpath[1][2][0][1]

        self.pid = pid


class PortChannelIDHandler(PortChannelChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            self.mode = self.change.value
            admin = self.server.get_default("admin-status")
            mtu = value = self.server.get_default("mtu")
            if self.mode == "dynamic":
                self.server.sonic.set_config_db(self.pid, "mode", self.mode, "PORTMODE")
                self.server.sonic.set_config_db(
                    self.pid, "admin-status", admin, "PORTCHANNEL"
                )
                self.server.sonic.set_config_db(self.pid, "mtu", mtu, "PORTCHANNEL")
            elif self.mode == "static":
                self.server.sonic.set_config_db(
                    self.pid, "static", "true", "PORTCHANNEL"
                )
                self.server.sonic.set_config_db(self.pid, "mode", self.mode, "PORTMODE")
                self.server.sonic.set_config_db(
                    self.pid, "admin-status", admin, "PORTCHANNEL"
                )
                self.server.sonic.set_config_db(self.pid, "mtu", mtu, "PORTCHANNEL")
        else:
            self.server.sonic.sonic_db.delete(
                self.server.sonic.sonic_db.CONFIG_DB, f"PORTMODE|{self.pid}"
            )
            self.server.sonic.sonic_db.delete(
                self.server.sonic.sonic_db.CONFIG_DB, f"PORTCHANNEL|{self.pid}"
            )


class AdminStatusHandler(PortChannelChangeHandler):
    def apply(self, user):
        self.mode = _decode(
            self.server.sonic.sonic_db.get(
                self.server.sonic.sonic_db.CONFIG_DB, f"PORTMODE|{self.pid}", "mode"
            )
        )
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            value = self.server.get_default("admin-status")
        logger.debug(f"set {self.pid}'s admin-status to {value}")
        if self.type not in ["deleted"] and self.mode in ["dynamic", "static"]:
            self.server.sonic.set_config_db(
                self.pid, "admin-status", value, "PORTCHANNEL"
            )

    def revert(self, user):
        # TODO
        pass


class MTUHandler(PortChannelChangeHandler):
    def apply(self, user):
        self.mode = _decode(
            self.server.sonic.sonic_db.get(
                self.server.sonic.sonic_db.CONFIG_DB, f"PORTMODE|{self.pid}", "mode"
            )
        )
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            value = self.server.get_default("mtu")
        logger.debug(f"set {self.pid}'s mtu to {value}")
        if self.type not in ["deleted"] and self.mode in ["dynamic", "static"]:
            self.server.sonic.set_config_db(self.pid, "mtu", value, "PORTCHANNEL")


class InterfaceHandler(PortChannelChangeHandler):
    def validate(self, user):
        if self.type == "created":
            if self.server.is_portchannel_intf(self.change.value):
                raise InvalArgError(
                    f"{self.change.value}:Interface is already part of LAG"
                )

    def apply(self, user):
        if self.type in ["created", "modified"]:
            ifname = self.xpath[-1][2][0][1]
            self.server.sonic.set_config_db(
                self.pid, "admin-status", "up", "PORTCHANNEL"
            )
            self.server.sonic.sonic_db.set(
                self.server.sonic.sonic_db.CONFIG_DB,
                f"PORTCHANNEL_MEMBER|{self.pid}|{ifname}",
                "NULL",
                "NULL",
            )
        else:
            ifname = self.xpath[-1][2][0][1]
            self.server.sonic.sonic_db.delete(
                self.server.sonic.sonic_db.CONFIG_DB,
                f"PORTCHANNEL_MEMBER|{self.pid}|{ifname}",
            )


class PortChannelServer(ServerBase):
    def __init__(self, conn, sonic):
        super().__init__(conn, "goldstone-portchannel")
        self.sonic = sonic
        self.handlers = {
            "portchannel": {
                "portchannel-group": {
                    "portchannel-id": NoOp,
                    "config": {
                        "portchannel-id": NoOp,
                        "mode": PortChannelIDHandler,
                        "admin-status": AdminStatusHandler,
                        "mtu": MTUHandler,
                        "interface": InterfaceHandler,
                    },
                }
            }
        }

    def get_portchannels(self):
        xpath = "/goldstone-portchannel:portchannel/portchannel-group"
        return self.get_running_data(xpath, [])

    def is_portchannel_intf(self, intf):
        portchannel_list = self.get_portchannels()
        for pid in portchannel_list:
            if intf in pid.get("config", {}).get("interface", []):
                return True
        return False

    def pre(self, user):
        if self.sonic.is_rebooting:
            raise LockedError("uSONiC is rebooting")

    def oper_cb(self, xpath, priv):
        logger.debug(f"xpath: {xpath}")
        if self.sonic.is_rebooting:
            raise CallbackFailedError("uSONiC is rebooting")

        keys = self.sonic.get_keys("LAG_TABLE:PortChannel*", "APPL_DB")

        r = []

        for key in keys:
            name = key.split(":")[1]
            state = self.sonic.hgetall("APPL_DB", key)
            state = {k.replace("_", "-"): v.upper() for k, v in state.items()}
            members = self.sonic.get_keys(f"LAG_MEMBER_TABLE:{name}:*", "APPL_DB")
            members = [m.split(":")[-1] for m in members]
            state["interface"] = members
            r.append({"portchannel-id": name, "state": state})

        logger.debug(f"portchannel: {r}")

        return {"goldstone-portchannel:portchannel": {"portchannel-group": r}}

    def get_default(self, key):
        keys = [
            ["interfaces", "interface", "config", key],
            ["interfaces", "interface", "ethernet", "config", key],
            ["interfaces", "interface", "ethernet", "auto-negotiate", "config", key],
        ]

        for k in keys:
            xpath = "".join(f"/goldstone-interfaces:{v}" for v in k)
            node = self.conn.find_node(xpath)
            if not node:
                continue

            if node.type() == "boolean":
                return node.default() == "true"
            return node.default()

        raise Exception(f"default value not found for {key}")

    async def reconcile(self):
        pc_list = self.get_running_data(
            "/goldstone-portchannel:portchannel/portchannel-group", []
        )
        for pc in pc_list:
            pid = pc["portchannel-id"]
            mode = pc["config"].get("mode", "")
            if mode in ["dynamic", "static"]:
                for leaf in ["admin-status", "mtu"]:
                    default = self.get_default(leaf)
                    value = pc["config"].get(leaf, default)
                    self.sonic.set_config_db(pid, "mode", mode, "PORTMODE")
                    if mode == "static":
                        self.sonic.set_config_db(pid, "static", "true", "PORTCHANNEL")
                    self.sonic.set_config_db(pid, leaf, value, "PORTCHANNEL")
            for intf in pc["config"].get("interface", []):
                self.sonic.set_config_db(
                    pid + "|" + intf, "NULL", "NULL", "PORTCHANNEL_MEMBER"
                )
            else:
                logger.debug(f"no interface configured on {pid}")
