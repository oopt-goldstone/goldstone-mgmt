from .core import *


class VLANChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-vlan"
        assert xpath[0][1] == "vlans"
        assert xpath[1][1] == "vlan"
        assert xpath[1][2][0][0] == "vlan-id"
        vid = xpath[1][2][0][1]

        self.vid = vid


class VLANIDHandler(VLANChangeHandler):
    def validate(self, user):
        if self.type != "deleted":
            return

        if len(self.server.sonic.get_vlan_members(self.vid)) > 0:
            raise sysrepo.SysrepoInvalArgError(f"vlan {self.vid} has dependencies")
        config = self.server.sonic.hgetall("CONFIG_DB", f"VLAN|Vlan{self.vid}")
        if not config:
            raise sysrepo.SysrepoInvalArgError(f"vlan {self.vid} not found")

    def apply(self, user):
        if self.type in ["created", "modified"]:
            self.server.sonic.create_vlan(self.vid)
        else:
            self.server.sonic.remove_vlan(self.vid)


class VLANServer(ServerBase):
    def __init__(self, conn, sonic):
        super().__init__(conn, "goldstone-vlan")
        self.sonic = sonic
        self.handlers = {
            "vlans": {
                "vlan": {
                    "vlan-id": NoOp,
                    "config": {
                        "vlan-id": VLANIDHandler,
                        "name": NoOp,
                    },
                    "members": NoOp,
                }
            }
        }

    def pre(self, user):
        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        if self.sonic.is_rebooting:
            return {}

        vlans = [
            {"vlan-id": vid, "config": {"vlan-id": vid}, "state": {"vlan-id": vid}}
            for vid in self.sonic.get_vids()
        ]

        for vlan in vlans:
            members = self.sonic.get_vlan_members(vlan["vlan-id"])
            if members:
                vlan["members"] = {"member": members}

        return {"goldstone-vlan:vlans": {"vlan": vlans}}

    async def reconcile(self):
        vlans = self.get_running_data("/goldstone-vlan:vlans/vlan", [])

        for vlan in vlans:
            self.sonic.create_vlan(vlan["vlan-id"])

        prefix = "/goldstone-interfaces:interfaces/interface"
        for ifname in self.sonic.get_ifnames():
            xpath = f"{prefix}[name='{ifname}']"
            data = self.get_running_data(xpath, {})
            config = data.get("config", {})

            vlan_config = data.get("switched-vlan", {}).get("config", {})

            if vlan_config:
                mode = vlan_config.get("interface-mode")
                if mode == "TRUNK":
                    for vid in vlan_config.get("trunk-vlans", []):
                        self.sonic.set_vlan_member(ifname, vid, "tagged")
                elif mode == "ACCESS":
                    vid = vlan_config.get("access-vlan")
                    if vid:
                        self.sonic.set_vlan_member(ifname, vid, "untagged")
