"""OpenConfig translator for openconfig-interfaces.

Target OpenConfig object is interface ("openconfig-interfaces:interfaces/interface") is represented as the Interface
class. OpenConfig interface has various types (based on "ietf-interfaces:interface-type") and they implemented as
subclasse of the Interface. e.g. EthernetCSMACD for "ethernetCsmacd".

Currently, we only support one type of device with gearboxes. So, it is probably too early to generalize/specialize
InterfaceFactory.
"""


from abc import abstractmethod
import logging
from goldstone.lib.core import NoOp
from .lib import (
    OpenConfigChangeHandler,
    OpenConfigObjectFactory,
    OpenConfigServer,
)
from .platform import ComponentNameResolver


logger = logging.getLogger(__name__)


GS_INTERFACES_IF = "/goldstone-interfaces:interfaces/interface[name='{}']"
GS_INTERFACES_IF_NAME = GS_INTERFACES_IF + "/config/name"
GS_INTERFACES_IF_ADMIN_STATUS = GS_INTERFACES_IF + "/config/admin-status"
GS_INTERFACES_IF_ETHERNET_FEC = GS_INTERFACES_IF + "/ethernet/config/fec"


class IfChangeHandler(OpenConfigChangeHandler):
    """ChangeHandler base for openconfig-interfaces:interfaces/interface object."""

    def __init__(self, server, change):
        super().__init__(server, change)
        assert self.xpath[0][0] == "openconfig-interfaces"
        assert self.xpath[0][1] == "interfaces"
        assert self.xpath[1][1] == "interface"
        assert self.xpath[1][2][0][0] == "name"
        self.ifname = self.xpath[1][2][0][1]


class EnabledHandler(IfChangeHandler):
    """ChangeHandler for config/enabled."""

    def _admin_status(self, enabled):
        """
        Args:
            enabled (bool): /openconfig-interfaces:interfaces/interface/config/enabled.

        Returns:
            str: /goldstone-interfaces:interfaces/interface/config/admin-status.
                UP, DOWN
        """
        return "UP" if enabled else "DOWN"

    def _setup(self, user):
        self.if_created = False
        self.if_xpath = GS_INTERFACES_IF.format(self.ifname)
        self.if_name_xpath = GS_INTERFACES_IF_NAME.format(self.ifname)
        self.if_admin_status_xpath = GS_INTERFACES_IF_ADMIN_STATUS.format(self.ifname)

    def _get_item(self, user):
        return self._get(user, self.if_admin_status_xpath)

    def _set_item(self, user, value):
        self._set(user, self.if_name_xpath, self.ifname)
        self._set(user, self.if_admin_status_xpath, value)

    def _delete_item(self, user):
        if self.if_created:
            self._delete(user, self.if_xpath)
        else:
            self._delete(user, self.if_admin_status_xpath)

    def _translate(self, user, value):
        return self._admin_status(value)

    def _validate_parent(self, user):
        if self._get(user, self.if_xpath) is None:
            self.if_created = True


class FECModeHandler(IfChangeHandler):
    """ChangeHandler for ethernet/config/fec-mode."""

    def _fec(self, fec_mode):
        """
        Args:
            fec_mode (str): /openconfig-interfaces:interfaces/interface/ethernet/config/fec-mode.
                FEC_FC, FEC_RS528, FEC_RS544, FEC_RS544_2X_INTERLEAVE, FEC_DISABLED

        Returns:
            str: /goldstone-interfaces:interfaces/interface/ethernet/config/fec.
                FC, RS, NONE
        """
        fec_mode = fec_mode.replace("openconfig-if-ethernet:", "")
        if fec_mode == "FEC_FC":
            return "FC"
        elif fec_mode in ["FEC_RS528", "FEC_RS544", "FEC_RS544_2X_INTERLEAVE"]:
            return "RS"
        elif fec_mode == "FEC_DISABLED":
            return "NONE"

    def _setup(self, user):
        self.if_created = False
        self.if_xpath = GS_INTERFACES_IF.format(self.ifname)
        self.if_name_xpath = GS_INTERFACES_IF_NAME.format(self.ifname)
        self.if_ethernet_fec_xpath = GS_INTERFACES_IF_ETHERNET_FEC.format(self.ifname)

    def _get_item(self, user):
        return self._get(user, self.if_ethernet_fec_xpath)

    def _set_item(self, user, value):
        self._set(user, self.if_name_xpath, self.ifname)
        self._set(user, self.if_ethernet_fec_xpath, value)

    def _delete_item(self, user):
        if self.if_created:
            self._delete(user, self.if_xpath)
        else:
            self._delete(user, self.if_ethernet_fec_xpath)

    def _translate(self, user, value):
        return self._fec(value)

    def _validate_parent(self, user):
        if self._get(user, self.if_xpath) is None:
            self.if_created = True


class Interface:
    """Interface represents openconfig-interfaces:interfaces/interface object.

    Args:
        name (str): Interface name.
        port_name (str): Associated PORT component (openconfig-platform/components/component) name.

    Attributes:
        name (str): Interface name.
        port_name (str): Associated PORT component (openconfig-platform/components/component) name.
        data (dict): Operational state data of the interface.
    """

    def __init__(self, name, port_name):
        self.name = name
        self.port_name = port_name
        self.data = {
            "name": self.name,
            "state": {
                "name": self.name,
            },
        }
        if self.port_name is not None:
            self.data["state"]["hardware-port"] = self.port_name

    @abstractmethod
    def translate(self):
        """Set interface operational state data from Goldstone operational state data."""
        pass


class EthernetCSMACD(Interface):
    """OpenConfig Interface for ethernetCsmacd (RFC3635) interface.

    Args:
        interface (dict): goldstone-platform:interfaces/interface object to create the interface.

    Attributes:
        interface (dict): goldstone-platform:interfaces/interface object to create the interface.
    """

    def __init__(self, name, port_name, interface):
        super().__init__(name, port_name)
        self.interface = interface
        self.data["state"]["type"] = "iana-if-type:ethernetCsmacd"

    def _enabled(self, admin_status):
        """
        Args:
            admin_status (str): /goldstone-interfaces:interfaces/interface/state/admin-status.
                UP, DOWN

        Returns:
            bool: /openconfig-interfaces:interfaces/interface/state/enabled.
        """
        return admin_status == "UP"

    def _admin_status(self, admin_status):
        """
        Args:
            admin_status (str): /goldstone-interfaces:interfaces/interface/state/admin-status.
                UP, DOWN

        Returns:
            str: /openconfig-interfaces:interfaces/interface/state/admin-status.
                UP, DOWN, TESTING
        """
        if admin_status in ["UP", "DOWN", "TESTING"]:
            return admin_status
        else:
            return "DOWN"

    def _oper_status(self, oper_status):
        """
        Args:
            oper_status (str): /goldstone-interfaces:interfaces/interface/state/oper-status.
                UP, DOWN, DORMANT

        Returns:
            str: /openconfig-interfaces:interfaces/interface/state/oper-status.
                UP, DOWN, TESTING, UNKNOWN, DORMANT, NOT_PRESENT, LOWER_LAYER_DOWN
        """
        if oper_status in [
            "UP",
            "DOWN",
            "TESTING",
            "UNKNOWN",
            "DORMANT",
            "NOT_PRESENT",
            "LOWER_LAYER_DOWN",
        ]:
            return oper_status
        else:
            return "UNKNOWN"

    def _in_pkts(
        self, unicasts, broadcasts, multicasts, discards, errors, unknown_protos
    ):
        """
        Args:
            unicasts (int): /goldstone-interfaces:interfaces/interface/state/counters/in-unicast-pkts.
                uint64
            broadcasts (int): /goldstone-interfaces:interfaces/interface/state/counters/in-broadcast-pkts.
                uint64
            multicasts (int): /goldstone-interfaces:interfaces/interface/state/counters/in-multicast-pkts.
                uint64
            discards (int): /goldstone-interfaces:interfaces/interface/state/counters/in-discards.
                uint64
            errors (int): /goldstone-interfaces:interfaces/interface/state/counters/in-errors.
                uint64
            unknown_protos (int): /goldstone-interfaces:interfaces/interface/state/counters/in-unknown-protos.
                uint64

        Returns:
            int: /openconfig-interfaces:interfaces/interface/state/counters/in-pkts
                uint64
        """
        pkts = 0
        if unicasts is not None:
            pkts += unicasts
        if broadcasts is not None:
            pkts += broadcasts
        if multicasts is not None:
            pkts += multicasts
        if discards is not None:
            pkts += discards
        if errors is not None:
            pkts += errors
        if unknown_protos is not None:
            pkts += unknown_protos
        maximum = 18446744073709551616
        return pkts % maximum

    def _out_pkts(self, unicasts, broadcasts, multicasts, discards, errors):
        """
        Args:
            unicasts (int): /goldstone-interfaces:interfaces/interface/state/counters/out-unicast-pkts.
                uint64
            broadcasts (int): /goldstone-interfaces:interfaces/interface/state/counters/out-broadcast-pkts.
                uint64
            multicasts (int): /goldstone-interfaces:interfaces/interface/state/counters/out-multicast-pkts.
                uint64
            discards (int): /goldstone-interfaces:interfaces/interface/state/counters/out-discards.
                uint64
            errors (int): /goldstone-interfaces:interfaces/interface/state/counters/out-errors.
                uint64

        Returns:
            int: /openconfig-interfaces:interfaces/interface/state/counters/out-pkts
                uint64
        """
        pkts = 0
        if unicasts is not None:
            pkts += unicasts
        if broadcasts is not None:
            pkts += broadcasts
        if multicasts is not None:
            pkts += multicasts
        if discards is not None:
            pkts += discards
        if errors is not None:
            pkts += errors
        maximum = 18446744073709551616
        return pkts % maximum

    def _fec_mode(self, fec):
        """
        Args:
            fec (str): /goldstone-interfaces:interfaces/interface/ethernet/state/fec.
                FC, RS, NONE

        Returns:
            str: /openconfig-interfaces:interfaces/interface/ethernet/state/fec-mode.
                FEC_FC, FEC_RS528, FEC_RS544, FEC_RS544_2X_INTERLEAVE, FEC_DISABLED
        """
        if fec == "FC":
            return "FEC_FC"
        elif fec == "RS":
            # NOTE: We should add more parameters from the goldstone data to select FEC_RS528, FEC_RS544 or
            #     FEC_RS544_2X_INTERLEAVE. What types of information are needed?
            return "FEC_RS528"
        elif fec == "NONE":
            return "FEC_DISABLED"
        else:
            return "FEC_DISABLED"

    def translate(self):
        if self.interface is None:
            return
        state = self.interface.get("state")
        if state is not None:
            description = state.get("description")
            if description is not None:
                self.data["state"]["description"] = description
            admin_status = state.get("admin-status")
            if admin_status is not None:
                self.data["state"]["enabled"] = self._enabled(admin_status)
                self.data["state"]["admin-status"] = self._admin_status(admin_status)
            oper_status = state.get("oper-status")
            if oper_status is not None:
                self.data["state"]["oper-status"] = self._oper_status(oper_status)
            counters = state.get("counters")
            if counters is not None:
                in_octets = counters.get("in-octets")
                in_unicast_pkts = counters.get("in-unicast-pkts")
                in_broadcast_pkts = counters.get("in-broadcast-pkts")
                in_multicast_pkts = counters.get("in-multicast-pkts")
                in_discards = counters.get("in-discards")
                in_errors = counters.get("in-errors")
                in_unknown_protos = counters.get("in-unknown-protos")
                out_octets = counters.get("out-octets")
                out_unicast_pkts = counters.get("out-unicast-pkts")
                out_broadcast_pkts = counters.get("out-broadcast-pkts")
                out_multicast_pkts = counters.get("out-multicast-pkts")
                out_discards = counters.get("out-discards")
                out_errors = counters.get("out-errors")
                counters = {
                    "in-octets": in_octets,
                    "in-unicast-pkts": in_unicast_pkts,
                    "in-broadcast-pkts": in_broadcast_pkts,
                    "in-multicast-pkts": in_multicast_pkts,
                    "in-discards": in_discards,
                    "in-errors": in_errors,
                    "in-unknown-protos": in_unknown_protos,
                    "out-octets": out_octets,
                    "out-unicast-pkts": out_unicast_pkts,
                    "out-broadcast-pkts": out_broadcast_pkts,
                    "out-multicast-pkts": out_multicast_pkts,
                    "out-discards": out_discards,
                    "out-errors": out_errors,
                }
                if not (
                    in_unicast_pkts is None
                    and in_broadcast_pkts is None
                    and in_multicast_pkts is None
                    and in_discards is None
                    and in_errors is None
                    and in_unknown_protos is None
                ):
                    counters["in-pkts"] = self._in_pkts(
                        in_unicast_pkts,
                        in_broadcast_pkts,
                        in_multicast_pkts,
                        in_discards,
                        in_errors,
                        in_unknown_protos,
                    )
                if not (
                    out_unicast_pkts is None
                    and out_broadcast_pkts is None
                    and out_multicast_pkts is None
                    and out_discards is None
                    and out_errors is None
                ):
                    counters["out-pkts"] = self._out_pkts(
                        out_unicast_pkts,
                        out_broadcast_pkts,
                        out_multicast_pkts,
                        out_discards,
                        out_errors,
                    )
                counters = {k: v for k, v in counters.items() if v is not None}
                if len(counters) > 0:
                    self.data["state"]["counters"] = counters
        ethernet = self.interface.get("ethernet")
        if ethernet is not None:
            eth_state = ethernet.get("state")
            if eth_state is not None:
                mtu = eth_state.get("mtu")
                if mtu is not None:
                    self.data["state"]["mtu"] = mtu
                fec = eth_state.get("fec")
                if fec is not None:
                    self.data["ethernet"] = {"state": {"fec-mode": self._fec_mode(fec)}}


class InterfaceFactory(OpenConfigObjectFactory):
    """Create OpenConfig interfaces from Goldstone operational state data.

    An interface may has reference to a associated port component (openconfig-platform:components/component).

    Args:
        cnr (ComponentNameResolver): OpenConfig component name resolver.

    Attributes:
        cnr (ComponentNameResolver): OpenConfig component name resolver.
        gs (dict): Operational state data from Goldstone native/primitive models.
    """

    DEFAULT_IFTYPE = "IF_ETHERNET"

    def __init__(self, cnr):
        self.cnr = cnr

    def _initialize(self):
        self.gs = None

    def _create_interfaces(self):
        interfaces = []
        for gs_if in self.gs["interfaces"]:
            try:
                component_name = gs_if["component-connection"]["platform"]["component"]
                gs_comp = self.gs["components"][component_name]
                port_name = self.cnr.get_terminal_client_port(gs_comp)
            except (KeyError, TypeError):
                port_name = None
            try:
                iftype = gs_if["state"]["interface-type"]
            except (KeyError, TypeError):
                iftype = self.DEFAULT_IFTYPE
            if iftype == "IF_ETHERNET":
                interface = EthernetCSMACD(gs_if["name"], port_name, gs_if)
                interfaces.append(interface)
            # TODO: Support "IF_OTN".
        return interfaces

    def required_data(self):
        return [
            {
                "name": "components",
                "xpath": "/goldstone-platform:components/component",
                "default": [],
            },
            {
                "name": "interfaces",
                "xpath": "/goldstone-interfaces:interfaces/interface",
                "default": [],
            },
        ]

    def create(self, gs):
        self._initialize()
        self.gs = gs
        interfaces = self._create_interfaces()
        result = []
        for interface in interfaces:
            interface.translate()
            result.append(interface.data)
        return result


class InterfaceServer(OpenConfigServer):
    """InterfaceServer provides a service for the openconfig-interfaces module to central datastore."""

    def __init__(self, conn, reconciliation_interval=10):
        super().__init__(conn, "openconfig-interfaces", reconciliation_interval)
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "enabled": EnabledHandler,
                        "name": NoOp,
                        "type": NoOp,
                        "loopback-mode": NoOp,
                    },
                    "hold-time": NoOp,
                    "ethernet": {
                        "config": {
                            "fec-mode": FECModeHandler,
                            "auto-negotiate": NoOp,
                            "standalone-link-training": NoOp,
                            "enable-flow-control": NoOp,
                        },
                    },
                }
            }
        }
        self.objects = {
            "interfaces": {"interface": InterfaceFactory(ComponentNameResolver())}
        }

    async def reconcile(self):
        # NOTE: This should be implemented as a separated class of function to remove the dependency from the
        #     InterfaceServer to specific data models and their details.
        data = self.get_running_data("/openconfig-interfaces:interfaces/interface", [])
        sess = self.conn.conn.new_session()
        for configs in data:
            name = configs["name"]

            config = configs.get("config")
            if config is None:
                continue

            sess.set(GS_INTERFACES_IF_NAME.format(name), name)

            enabled = config.get("enabled")
            if enabled is not None:
                sess.set(
                    GS_INTERFACES_IF_ADMIN_STATUS.format(name),
                    "UP" if enabled else "DOWN",
                )
        sess.apply()
        sess.stop()
