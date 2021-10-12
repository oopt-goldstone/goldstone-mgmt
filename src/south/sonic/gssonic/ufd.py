from .core import *

logger = logging.getLogger(__name__)


class UFDChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-uplink-failure-detection"
        assert xpath[0][1] == "ufd-groups"
        assert xpath[1][1] == "ufd-group"
        assert xpath[1][2][0][0] == "ufd-id"
        self.uid = xpath[1][2][0][1]
        self.xpath = xpath


class UFDUplinkHandler(UFDChangeHandler):
    def validate(self, user):
        ifname = self.xpath[-1][2][0][1]
        if ifname not in self.server.sonic.get_ifnames():
            raise sysrepo.SysrepoInvalArgError("Invalid Interface name")

        cache = self.setup_cache(user)
        xpath = f"/goldstone-uplink-failure-detection:ufd-groups/ufd-group[ufd-id='{self.uid}']/config"
        cache = libyang.xpath_get(cache, xpath, {})
        if len(cache.get("uplink", [])) > 1:
            raise sysrepo.SysrepoInvalArgError("Only one uplink can be configured")
        if ifname in cache.get("downlink", []):
            raise sysrepo.SysrepoInvalArgError(f"{ifname} configured as a downlink")

        self.ifname = ifname

    def apply(self, user):
        cache = self.setup_cache(user)
        xpath = f"/goldstone-uplink-failure-detection:ufd-groups/ufd-group[ufd-id='{self.uid}']/config"
        cache = libyang.xpath_get(cache, xpath, {})
        if self.type == "created":
            if self.server.sonic.get_oper_status(self.ifname) == "down":
                for downlink in cache.get("downlink", []):
                    self.server.sonic.set_config_db(downlink, "admin_status", "down")
        elif self.type == "deleted":
            for downlink in cache.get("downlink", []):
                xpath = f"/goldstone-interfaces:interfaces/interface[name='{downlink}']/config/admin-status"
                admin_status = self.server.get_running_data(xpath, "down")
                self.server.sonic.set_config_db(downlink, "admin_status", admin_status)


class UFDDownlinkHandler(UFDChangeHandler):
    def validate(self, user):
        cache = self.setup_cache(user)
        ifname = self.xpath[-1][2][0][1]
        if ifname not in self.server.sonic.get_ifnames():
            raise sysrepo.SysrepoInvalArgError("Invalid Interface name")

        cache = self.setup_cache(user)
        xpath = f"/goldstone-uplink-failure-detection:ufd-groups/ufd-group[ufd-id='{self.uid}']/config"
        cache = libyang.xpath_get(cache, xpath, {})
        if ifname in cache.get("uplink", []):
            raise sysrepo.SysrepoInvalArgError(f"{ifname} configured as an uplink")

        self.ifname = ifname

    def apply(self, user):
        cache = self.setup_cache(user)
        xpath = f"/goldstone-uplink-failure-detection:ufd-groups/ufd-group[ufd-id='{self.uid}']/config"
        cache = libyang.xpath_get(cache, xpath, {})
        if self.type == "created":
            uplink = list(cache.get("uplink", []))
            if uplink and self.server.sonic.get_oper_status(uplink[0]) == "down":
                self.server.sonic.set_config_db(self.ifname, "admin_status", "down")
        elif self.type == "deleted":
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{self.ifname}']/config/admin-status"
            admin_status = self.server.get_running_data(xpath, "down")
            self.server.sonic.set_config_db(self.ifname, "admin_status", admin_status)


class UFDServer(ServerBase):
    def __init__(self, conn, sonic):
        super().__init__(conn, "goldstone-uplink-failure-detection")
        self.sonic = sonic
        self.handlers = {
            "ufd-groups": {
                "ufd-group": {
                    "ufd-id": NoOp,
                    "config": {
                        "ufd-id": NoOp,
                        "uplink": UFDUplinkHandler,
                        "downlink": UFDDownlinkHandler,
                    },
                }
            }
        }

    def pre(self, user):
        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
