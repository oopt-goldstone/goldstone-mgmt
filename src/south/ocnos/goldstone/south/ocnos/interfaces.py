from goldstone.lib.core import *
import sysrepo
import ncclient
from ncclient.xml_ import *
import libyang
from lxml import etree
from .util import *

logger = logging.getLogger(__name__)


class IfChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath_list = list(libyang.xpath_split(xpath))

        assert xpath_list[0][0] == "goldstone-interfaces"
        assert xpath_list[0][1] == "interfaces"
        assert xpath_list[1][1] == "interface"
        assert xpath_list[1][2][0][0] == "name"
        self.ifname = xpath_list[1][2][0][1]


class AdminStatusHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
            if type(value) is dict:
                return
        else:
            # admin-status is DOWN in default in Goldstone
            value = self.server.get_default("admin-status")

        try:
            self.set_admin_status(value)
        except ncclient.operations.RPCError as e:
            self.server.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Edit-config of admin-status failed in OcNOS due: {e.message}"
            )
        logger.debug(f"set {self.ifname}'s admin-status to {value}")

    def set_admin_status(self, value):
        assert value in ["UP", "DOWN"]

        # We only send operation=delete if the previous value of interface is DOWN.
        # Otherwise, it tries to delete something that does not exist in OcNOS. This leads to commit fail.
        if self.type == "modified":
            if self.change.prev_val == "UP" and value == "UP":
                return
        if self.type == "created":
            if value == "UP":
                return

        delete_oper = value == "UP"
        xpath_shutdown = IPI_INTERFACE_CONFIG_SHUTDOWN.format(self.ifname, self.ifname)
        xml_shutdown = self.server.ocnos_conn.xpath2xml(
            xpath_shutdown, delete_oper=delete_oper
        )
        config = new_ele("config")
        config.append(xml_shutdown)
        logger.debug(
            f"Sending xml for admin status configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class DescriptionHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
            if type(value) is dict:
                return
        else:
            value = None

        try:
            self.set_description(value)
        except ncclient.operations.RPCError as e:
            self.server.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Edit-config of description failed in OcNOS due: {e.message}"
            )
        logger.debug(f"set {self.ifname}'s description to {value}")

    def set_description(self, value):
        xpath_desc = IPI_INTERFACE_CONFIG_DESCRIPTION.format(self.ifname, self.ifname)

        if not value:
            xml_desc = self.server.ocnos_conn.xpath2xml(xpath_desc, delete_oper=True)
        else:
            xml_desc = self.server.ocnos_conn.xpath2xml(xpath_desc, value)
        config = new_ele("config")
        config.append(xml_desc)
        logger.debug(
            f"Sending xml for description configuration: {etree.tostring(config, pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class MTUHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
            if type(value) is dict:
                return
        else:
            value = self.server.get_default("mtu")

        try:
            self.set_mtu(value)
        except ncclient.operations.RPCError as e:
            self.server.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Edit-config of mtu failed in OcNOS due: {e.message}"
            )
        logger.debug(f"set {self.ifname}'s mtu to {value}")

    def set_mtu(self, value):
        xpath_mtu = IPI_INTERFACE_CONFIG_MTU.format(self.ifname, self.ifname)

        if not value:
            xml_mtu = self.server.ocnos_conn.xpath2xml(xpath_mtu, delete_oper=True)
        else:
            xml_mtu = self.server.ocnos_conn.xpath2xml(xpath_mtu, value)
        config = new_ele("config")
        config.append(xml_mtu)
        logger.debug(
            f"Sending xml for ethernet mtu configuration: {etree.tostring(config, pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class SpeedHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
            if type(value) is dict:
                return
        else:
            # If the auto-negotiate is configured to true, cannot remove port-speed, as in
            # OcNOS the autonegotiate and speed are the same attribute.
            cache = self.setup_cache(user)
            xpath_gs_auto_neg = GS_IF_AUTO_NEGOTIATE_CONFIG.format(self.ifname)
            autoneg = libyang.xpath_get(cache, xpath_gs_auto_neg, None)
            if autoneg:
                return
            value = None

        try:
            self.set_speed(value)
        except ncclient.operations.RPCError as e:
            self.server.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Edit-config of speed failed in OcNOS due: {e.message}"
            )
        logger.debug(f"set {self.ifname}'s speed to {value}")

    def set_speed(self, value):
        xpath_port_speed = IPI_INTERFACE_ETHERNET_CONFIG_PORT_SPEED.format(self.ifname)
        if not value:
            xml_port_speed = self.server.ocnos_conn.xpath2xml(
                xpath_port_speed, delete_oper=True
            )
        else:
            mapped_value = SPEED_MAP.get(value)
            xml_port_speed = self.server.ocnos_conn.xpath2xml(
                xpath_port_speed, mapped_value
            )

        config = new_ele("config")
        config.append(xml_port_speed)
        logger.debug(
            f"Sending xml for interface speed configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def validate(self, user):
        if self.type in ["created", "modified"]:
            if self.change.value not in SPEED_MAP:
                raise sysrepo.SysrepoInvalArgError(
                    f"OcNOS does not support this speed: {self.change.value}, candidates: {','.join(speed_map)}"
                )


class AutonegotiateEnabledHandler(IfChangeHandler):
    def apply(self, user):
        cache = self.setup_cache(user)
        if self.type in ["created", "modified"]:
            value = self.change.value
            if type(value) is dict:
                return

            xpath_gs_auto_neg = GS_IF_AUTO_NEGOTIATE_CONFIG.format(self.ifname)
            xpath_gs_eth_speed = GS_IF_ETH_SPEED.format(self.ifname)
            autoneg = libyang.xpath_get(cache, xpath_gs_auto_neg, None)
            speed = libyang.xpath_get(cache, xpath_gs_eth_speed, None)
            if autoneg == False and speed is not None:
                return
        else:
            value = self.server.get_default("enabled")

        try:
            self.set_autonegotiate(value)
        except ncclient.operations.RPCError as e:
            self.server.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Edit-config of auto-negotiate failed in OcNOS due: {e.message}"
            )
        logger.debug(f"set {self.ifname}'s auto-negotiate to {value}")

    def set_autonegotiate(self, value):
        assert value in [True, False]

        if self.type == "modified":
            if self.change.prev_val == False and value == False:
                return
        if self.type == "created":
            if value == False:
                return

        xpath_eth_speed = IPI_INTERFACE_ETHERNET_CONFIG_PORT_SPEED.format(self.ifname)

        delete_oper = value == False
        value = "auto" if value else None
        xml_eth_speed = self.server.ocnos_conn.xpath2xml(
            xpath_eth_speed, value, delete_oper=delete_oper
        )
        config = new_ele("config")
        config.append(xml_eth_speed)
        logger.debug(
            f"Sending xml for interface auto-negotiate configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class InterfaceModeHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            try:
                value = self.change.value
                self.set_interface_mode(value)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for set interface-mode: {e.message}"
                )
            self.server.gs_if_mode[self.ifname] = value.lower()
            logger.debug(f"set {self.ifname} interface-mode with {value}")
        else:
            try:
                self.unset_interface_mode(user)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for unset access-vlans: {e.message}"
                )
            logger.debug(f"unset {self.ifname} interface-mode")

    def set_interface_mode(self, value):
        assert value in ["ACCESS", "TRUNK"]
        value = "access" if value == "ACCESS" else "trunk"
        # Add /interfaces/interface[name=ifname]/config[name=ifname]/enable-switchport
        xpath_if_swport = IPI_INTERFACE_CONFIG_SWITCHPORT.format(
            self.ifname, self.ifname
        )
        xml_if_swport = self.server.ocnos_conn.xpath2xml(xpath_if_swport)
        xpath_if_mode = IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE.format(value)
        xml_if_mode = self.server.ocnos_conn.xpath2xml(xpath_if_mode, value=value)
        insert_xml(xml_if_mode, xml_if_swport, TAG_IPI_INTERFACE)

        # Add /network-instances/network-instance/bridge-ports/interface[name=ifname]/config[name=ifname]
        xpath_ni = IPI_NETWORK_INSTANCE.format(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE
        )
        xml_ni = self.server.ocnos_conn.xpath2xml(xpath_ni)
        xpath_bridge_ports = IPI_BRIDGE_PORTS_INTERFACE_CONFIG_INTERFACE.format(
            self.ifname, self.ifname
        )
        xml_bridge_ports = self.server.ocnos_conn.xpath2xml(xpath_bridge_ports)
        insert_xml(xml_bridge_ports, xml_ni, TAG_IPI_NETWORK_INSTANCE)

        config = new_ele("config")
        config.append(xml_if_swport)
        config.append(xml_ni)
        logger.debug(
            f"Sending xml for interface-mode configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def unset_interface_mode(self, user):
        running_config = self.server.get_running_data(
            GOLDSTONE_INTERFACE_TOP,
            default={},
            strip=False,
            include_implicit_defaults=True,
        )
        xpath_gs_if_mode = GS_IF_MODE_CONFIG.format(self.ifname)
        if_mode = libyang.xpath_get(running_config, xpath_gs_if_mode, None)
        if if_mode is None:
            if self.type == "deleted":
                if_mode = self.server.gs_if_mode.get(self.ifname)
        elif if_mode == "ACCESS":
            if_mode = "access"
        else:
            if_mode = "trunk"

        # Add /interfaces/interface[name=ifname]/config[name=ifname]/enable-switchport
        xpath_if_swport = IPI_INTERFACE_CONFIG_SWITCHPORT.format(
            self.ifname, self.ifname
        )
        xml_if_swport = self.server.ocnos_conn.xpath2xml(
            xpath_if_swport, delete_oper=True
        )
        xpath_if_mode = IPI_PORT_VLAN_SWITCHED_VLAN.format(if_mode)
        xml_if_mode = self.server.ocnos_conn.xpath2xml(xpath_if_mode, delete_oper=True)
        insert_xml(xml_if_mode, xml_if_swport, TAG_IPI_INTERFACE)

        # Add /network-instances/network-instance/bridge-ports/interface[name=ifname]/config[name=ifname]
        xpath_ni = IPI_NETWORK_INSTANCE.format(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE
        )
        xml_ni = self.server.ocnos_conn.xpath2xml(xpath_ni)
        xpath_bridge_ports = IPI_BRIDGE_PORTS_INTERFACE.format(self.ifname)
        xml_bridge_ports = self.server.ocnos_conn.xpath2xml(
            xpath_bridge_ports, delete_oper=True
        )
        insert_xml(xml_bridge_ports, xml_ni, TAG_IPI_NETWORK_INSTANCE)

        config = new_ele("config")
        config.append(xml_if_swport)
        config.append(xml_ni)
        logger.debug(
            f"Sending xml for interface-mode configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def validate(self, user):
        cache = self.setup_cache(user)
        if self.type in ["created", "modified"]:
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{self.ifname}']"
            cache = libyang.xpath_get(cache, xpath, None)
            try:
                ip_config = cache["ipv4"]["address"]
                if ip_config:
                    raise sysrepo.SysrepoInvalArgError(
                        "Cannot have IP Address and switched-vlan at same time. Only one of them can be configured"
                    )
            except KeyError:
                return


class AccessVlansHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            try:
                value = self.change.value
                self.set_access_vlan(value, user)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for set access-vlans: {e.message}"
                )
            logger.debug(f"set {self.ifname} access-vlans with value {value}")
        else:
            try:
                self.unset_access_vlan(user)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for unset access-vlans: {e.message}"
                )
            logger.debug(f"unset {self.ifname} access-vlans")

    def set_access_vlan(self, value, user):
        cache = self.setup_cache(user)

        xpath_gs_if_mode = GS_IF_MODE_CONFIG.format(self.ifname)
        if_mode = libyang.xpath_get(cache, xpath_gs_if_mode, None)
        assert if_mode == "ACCESS"
        if_mode = "access"

        xpath_if = IPI_INTERFACE.format(self.ifname)
        xml_if = self.server.ocnos_conn.xpath2xml(xpath_if)
        xpath_if_mode = IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE.format(
            if_mode
        )
        xml_if_mode = self.server.ocnos_conn.xpath2xml(xpath_if_mode, value=if_mode)
        insert_xml(xml_if_mode, xml_if, TAG_IPI_INTERFACE)

        xpath_switched_vlan_config = IPI_SWITCHED_VLAN_CONFIG
        xml_switched_vlan_config = self.server.ocnos_conn.xpath2xml(
            xpath_switched_vlan_config, value=value
        )
        insert_xml(xml_switched_vlan_config, xml_if, TAG_IPI_SWITCHED_VLAN)

        config = new_ele("config")
        config.append(xml_if)
        logger.debug(
            f"Sending xml for access-vlans configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def unset_access_vlan(self, user):
        cache = self.server.get_running_data(
            GOLDSTONE_INTERFACE_TOP,
            default={},
            strip=False,
            include_implicit_defaults=True,
        )
        candidate = self.setup_cache(user)

        xpath_gs_if_mode = GS_IF_MODE_CONFIG.format(self.ifname)
        if_mode_running = libyang.xpath_get(cache, xpath_gs_if_mode, None)
        if_mode_candidate = libyang.xpath_get(candidate, xpath_gs_if_mode, None)
        assert if_mode_running == "ACCESS"

        # The Goldstone try to remove the access-vlan also, when there is a interface-mode change
        # from ACCESS to TRUNK, or when the switched-vlan container is removed.
        # But, for OcNOS only the interface-mode change is enough
        # to remove access-vlan.
        if if_mode_running != if_mode_candidate:
            return

        if_mode = "access"
        xpath_if = IPI_INTERFACE.format(self.ifname)
        xml_if = self.server.ocnos_conn.xpath2xml(xpath_if)

        xpath_sw_vlan = IPI_PORT_VLAN_SWITCHED_VLAN_VLANS_CONFIG.format(if_mode)
        xml_sw_vlan = self.server.ocnos_conn.xpath2xml(xpath_sw_vlan, delete_oper=True)

        insert_xml(xml_sw_vlan, xml_if, TAG_IPI_INTERFACE)
        config = new_ele("config")
        config.append(xml_if)
        logger.debug(
            f"Sending xml for access-vlan configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class TrunkVlansHandler(IfChangeHandler):
    def apply(self, user):
        cache = self.setup_cache(user)
        if self.type in ["created", "modified"]:
            try:
                value = self.change.value
                xpath = GS_TRUNK_VLANS_CONFIG.format(self.ifname)
                trunk_vlans = libyang.xpath_get(cache, xpath, None)
                self.set_trunk_vlan(value, user)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for set trunk-vlans: {e.message}"
                )
            logger.debug(f"set {self.ifname} trunk-vlans with values {value}")
        else:
            try:
                self.unset_trunk_vlan(user)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for unset trunk-vlans: {e.message}"
                )
            logger.debug(f"unset {self.ifname} trunk-vlans")

    def set_trunk_vlan(self, value, user):
        cache = self.setup_cache(user)
        xpath_gs_if_mode = GS_IF_MODE_CONFIG.format(self.ifname)
        if_mode = libyang.xpath_get(cache, xpath_gs_if_mode, None)
        assert if_mode == "TRUNK"
        if_mode = "trunk"

        xpath_if = IPI_INTERFACE.format(self.ifname)
        xml_if = self.server.ocnos_conn.xpath2xml(xpath_if)
        xpath_if_mode = IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE.format(
            if_mode
        )
        xml_if_mode = self.server.ocnos_conn.xpath2xml(xpath_if_mode, value=if_mode)
        insert_xml(xml_if_mode, xml_if, TAG_IPI_INTERFACE)

        xpath_allowed_vlan_config = IPI_ALLOWED_VLAN_CONFIG
        xml_allowed_vlan_config = self.server.ocnos_conn.xpath2xml(
            xpath_allowed_vlan_config, value=value
        )
        insert_xml(xml_allowed_vlan_config, xml_if, TAG_IPI_SWITCHED_VLAN)

        config = new_ele("config")
        config.append(xml_if)
        logger.debug(
            f"Sending xml for trunk-vlans configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def unset_trunk_vlan(self, user):
        cache = self.server.get_running_data(
            GOLDSTONE_INTERFACE_TOP,
            default={},
            strip=False,
            include_implicit_defaults=True,
        )
        candidate = self.setup_cache(user)
        xpath_list = list(libyang.xpath_split(self.change.xpath))
        assert xpath_list[4][1] == "trunk-vlans"
        value = xpath_list[4][2][0][1]

        xpath_gs_if_mode = GS_IF_MODE_CONFIG.format(self.ifname)
        if_mode_running = libyang.xpath_get(cache, xpath_gs_if_mode, None)
        if_mode_candidate = libyang.xpath_get(candidate, xpath_gs_if_mode, None)
        assert if_mode_running == "TRUNK"

        # The Goldstone try to remove the access-vlan also, when there is a interface-mode change
        # from TRUNK to ACCESS, or when the switched-vlan container is removed.
        # But, for OcNOS only the interface-mode change is enough
        # to remove the allowed-vlan container.
        if if_mode_running != if_mode_candidate:
            return

        if_mode = "trunk"
        xpath_if = IPI_INTERFACE.format(self.ifname)
        xml_if = self.server.ocnos_conn.xpath2xml(xpath_if)
        xpath_sw_vlan = IPI_PORT_VLAN_SWITCHED_VLAN_ALLOWED_VLAN_CONFIG.format(if_mode)
        xml_sw_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_sw_vlan, value=value, delete_oper=True
        )

        insert_xml(xml_sw_vlan, xml_if, TAG_IPI_INTERFACE)
        config = new_ele("config")
        config.append(xml_if)
        logger.debug(
            f"Sending xml for trunk-vlans delete: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class InterfaceServer(ServerBase):
    def __init__(self, sr_conn, ocnos_conn):
        super().__init__(sr_conn, "goldstone-interfaces")
        self.sr_conn = sr_conn
        self.ocnos_conn = ocnos_conn
        # TODO: other handlers should be implemented in future.
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "admin-status": AdminStatusHandler,
                        "name": NoOp,
                        "description": DescriptionHandler,
                        "interface-type": NoOp,
                        "pin-mode": NoOp,
                        "loopback-mode": NoOp,
                        "prbs-mode": NoOp,
                    },
                    "ethernet": {
                        "config": {
                            "mtu": MTUHandler,
                            "fec": NoOp,
                            "interface-type": NoOp,
                            "speed": SpeedHandler,
                        },
                        "breakout": {"config": NoOp},
                        "auto-negotiate": {
                            "config": {
                                "enabled": AutonegotiateEnabledHandler,
                                "advertised-speeds": NoOp,
                            }
                        },
                    },
                    "switched-vlan": {
                        "config": {
                            "interface-mode": InterfaceModeHandler,
                            "access-vlan": AccessVlansHandler,
                            "trunk-vlans": TrunkVlansHandler,
                        }
                    },
                    "component-connection": NoOp,
                }
            }
        }
        self.gs_if_mode = {}

    async def start(self):
        await self.reconcile()
        tasks = await super().start()

        return tasks

    def stop(self):
        self.ocnos_conn.stop()
        super().stop()

    async def post(self, user):
        try:
            self.ocnos_conn.apply()
        except ncclient.operations.RPCError as e:
            self.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Commit failed in OcNOS due: {e.message}"
            )

    def reconcile_edit_config(self, msg, xpath, value=None):
        v = self.ocnos_conn.xpath2xml(xpath, value)
        xml = new_ele("config")
        xml.append(v)
        logger.debug(
            f"Sending xml for {msg} configuration: {etree.tostring(xml,pretty_print=True).decode()}"
        )
        self.ocnos_conn.conn.edit_config(xml)

    async def reconcile(self):
        data = self.get_running_data(GOLDSTONE_INTERFACE_TOP, [])

        logger.info(f"RECONCILE CONFIG:{data}")
        if not data:
            return
        for d in data:
            ifname = d["name"]
            config = d.get("config")
            if config:
                admin_status = config.get("admin-status")
                if admin_status == "DOWN":
                    xpath = IPI_INTERFACE_CONFIG_SHUTDOWN.format(ifname, ifname)
                    self.reconcile_edit_config("admin status", xpath)

                description = config.get("description")
                if description:
                    xpath = IPI_INTERFACE_CONFIG_DESCRIPTION.format(ifname, ifname)
                    self.reconcile_edit_config("description", xpath, description)

            if "ethernet" in d:
                ethernet_config = d.get("ethernet").get("config")
                if ethernet_config:
                    mtu = ethernet_config.get("mtu")
                    if mtu:
                        xpath = IPI_INTERFACE_CONFIG_MTU.format(ifname, ifname)
                        self.reconcile_edit_config("ethernet mtu", xpath, mtu)

                    speed = ethernet_config.get("speed")
                    if speed:
                        xpath = IPI_INTERFACE_ETHERNET_CONFIG_PORT_SPEED.format(ifname)
                        mapped_value = SPEED_MAP.get(speed)
                        self.reconcile_edit_config("speed", xpath, mapped_value)
                    else:
                        autoneg = (
                            d.get("ethernet")
                            .get("auto-negotiate")
                            .get("config")
                            .get("enabled")
                        )

                        if autoneg:
                            xpath = IPI_INTERFACE_ETHERNET_CONFIG_PORT_SPEED.format(
                                ifname
                            )

                            if autoneg == True:
                                autoneg = "auto"
                                self.reconcile_edit_config(
                                    "auto-negotiate", xpath, autoneg
                                )

            if "switched-vlan" in d:
                switched_vlan_config = d.get("switched-vlan").get("config")
                if switched_vlan_config:
                    interface_mode = switched_vlan_config.get("interface-mode")
                    if interface_mode:
                        interface_mode = (
                            "access" if interface_mode == "ACCESS" else "trunk"
                        )

                        xpath_if_swport = IPI_INTERFACE_CONFIG_SWITCHPORT.format(
                            ifname, ifname
                        )
                        xml_if_swport = self.ocnos_conn.xpath2xml(xpath_if_swport)
                        xpath_if_mode = (
                            IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE.format(
                                interface_mode
                            )
                        )
                        xml_if_mode = self.ocnos_conn.xpath2xml(
                            xpath_if_mode, interface_mode
                        )
                        insert_xml(xml_if_mode, xml_if_swport, TAG_IPI_INTERFACE)
                        # Add /network-instances/network-instance/bridge-ports/interface[name=ifname]/config[name=ifname]
                        xpath_ni = IPI_NETWORK_INSTANCE.format(
                            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE
                        )
                        xml_ni = self.ocnos_conn.xpath2xml(xpath_ni)
                        xpath_bridge_ports = (
                            IPI_BRIDGE_PORTS_INTERFACE_CONFIG_INTERFACE.format(
                                ifname, ifname
                            )
                        )
                        xml_bridge_ports = self.ocnos_conn.xpath2xml(xpath_bridge_ports)
                        insert_xml(xml_bridge_ports, xml_ni, TAG_IPI_NETWORK_INSTANCE)
                        xml = new_ele("config")
                        xml.append(xml_if_swport)
                        xml.append(xml_ni)
                        logger.debug(
                            f"Sending xml for interface-mode configuration: {etree.tostring(xml,pretty_print=True).decode()}"
                        )
                        self.ocnos_conn.conn.edit_config(xml)
                        self.gs_if_mode[ifname] = interface_mode

                    access_vlan = switched_vlan_config.get("access-vlan")
                    if access_vlan:
                        xpath_if = IPI_INTERFACE.format(ifname)
                        xml_if = self.ocnos_conn.xpath2xml(xpath_if)
                        if_mode = "access"
                        xpath_if_mode = (
                            IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE.format(
                                if_mode
                            )
                        )
                        xml_if_mode = self.ocnos_conn.xpath2xml(xpath_if_mode, if_mode)
                        insert_xml(xml_if_mode, xml_if, TAG_IPI_INTERFACE)

                        xpath_switched_vlan_config = IPI_SWITCHED_VLAN_CONFIG
                        xml_switched_vlan_config = self.ocnos_conn.xpath2xml(
                            xpath_switched_vlan_config, access_vlan
                        )
                        insert_xml(
                            xml_switched_vlan_config, xml_if, TAG_IPI_SWITCHED_VLAN
                        )

                        xml = new_ele("config")
                        xml.append(xml_if)
                        logger.debug(
                            f"Sending xml for access-vlans configuration: {etree.tostring(xml,pretty_print=True).decode()}"
                        )
                        self.ocnos_conn.conn.edit_config(xml)

                    for trunk_vlan in switched_vlan_config.get("trunk-vlans", []):
                        if_mode = "trunk"

                        xpath_if = IPI_INTERFACE.format(ifname)
                        xml_if = self.ocnos_conn.xpath2xml(xpath_if)
                        xpath_if_mode = (
                            IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE.format(
                                if_mode
                            )
                        )
                        xml_if_mode = self.ocnos_conn.xpath2xml(xpath_if_mode, if_mode)
                        insert_xml(xml_if_mode, xml_if, TAG_IPI_INTERFACE)

                        xpath_allowed_vlan_config = IPI_ALLOWED_VLAN_CONFIG
                        xml_allowed_vlan_config = self.ocnos_conn.xpath2xml(
                            xpath_allowed_vlan_config, trunk_vlan
                        )
                        insert_xml(
                            xml_allowed_vlan_config, xml_if, TAG_IPI_SWITCHED_VLAN
                        )

                        xml = new_ele("config")
                        xml.append(xml_if)
                        logger.debug(
                            f"Sending xml for trunk-vlans configuration: {etree.tostring(xml,pretty_print=True).decode()}"
                        )
                        self.ocnos_conn.conn.edit_config(xml)

            # commit all configs
            try:
                self.ocnos_conn.apply()
            except ncclient.operations.RPCError as e:
                self.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Reconcile Commit failed in OcNOS due: {e.message}"
                )
            logger.debug(f"Reconcile finished for interface")

    async def oper_cb(self, xpath, priv):
        logger.info(f"oper_cb xpath: {xpath}")
        req_xpath = list(libyang.xpath_split(xpath))

        ifnames = self.ocnos_conn.get(
            "/ipi-interface:interfaces/interface/name", ds="operational"
        )

        if (
            len(req_xpath) == 3
            and req_xpath[1][1] == "interface"
            and req_xpath[2][1] == "name"
        ):
            interfaces = [{"name": name} for name in ifnames]
            return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

        if (
            len(req_xpath) > 1
            and req_xpath[1][1] == "interface"
            and len(req_xpath[1][2]) == 1
        ):
            cond = req_xpath[1][2][0]
            assert cond[0] == "name"
            if cond[1] not in ifnames:
                return None
            ifnames = [cond[1]]

        interfaces = []
        for name in ifnames:
            interface = {
                "name": name,
                "config": {"name": name},
                "state": {"name": name, "counters": {}},
                "ethernet": {
                    "state": {},
                    "breakout": {"state": {}},
                    "auto-negotiate": {"state": {}},
                },
                "switched-vlan": {"state": {}},
            }
            oper_data = self.ocnos_conn.get(
                f"/ipi-interface:interfaces/interface[name='{name}']", ds="operational"
            )

            # TODO: add other attributes
            interface["state"]["admin-status"] = oper_data["state"][
                "admin-status"
            ].upper()
            interface["state"]["oper-status"] = oper_data["state"][
                "oper-status"
            ].upper()
            if "description" in oper_data["state"]:
                interface["state"]["description"] = oper_data["state"]["description"]

            if "mtu" in oper_data["state"]:
                interface["ethernet"]["state"]["mtu"] = oper_data["state"]["mtu"]

            if "counters" in oper_data["state"]:
                interface["state"]["counters"] = oper_data["state"]["counters"]

            if "ethernet" in oper_data:
                if "port-speed" in oper_data["ethernet"]["state"]:
                    port_speed = [
                        key
                        for key, value in SPEED_MAP.items()
                        if value == oper_data["ethernet"]["state"]["port-speed"]
                    ][0]

                    if port_speed is not None:
                        if port_speed == "auto-negotiate":
                            interface["ethernet"]["auto-negotiate"]["state"][
                                "enabled"
                            ] = True
                        else:
                            interface["ethernet"]["auto-negotiate"]["state"][
                                "enabled"
                            ] = False
                            interface["ethernet"]["state"]["speed"] = port_speed

            if "port-vlan" in oper_data:
                if "switched-vlan" in oper_data["port-vlan"]:
                    switched_vlan = oper_data["port-vlan"]["switched-vlan"]
                    if_mode = switched_vlan["interface-mode"]
                    if if_mode == "access":
                        interface["switched-vlan"]["state"]["interface-mode"] = "ACCESS"
                        if "vlans" in switched_vlan:
                            access_vlan = switched_vlan["vlans"]["state"]["vlan-id"]
                            interface["switched-vlan"]["state"][
                                "access-vlan"
                            ] = access_vlan
                    elif if_mode == "trunk":
                        interface["switched-vlan"]["state"] = {
                            "interface-mode": "TRUNK"
                        }
                        if "allowed-vlan" in switched_vlan:
                            trunk_vlans = switched_vlan["allowed-vlan"]["state"][
                                "allowed-vlan-id"
                            ]
                            trunk_vlans = get_all_trunk_vlans_id(trunk_vlans)
                            interface["switched-vlan"]["state"][
                                "trunk-vlans"
                            ] = trunk_vlans
            interfaces.append(interface)
        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

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
