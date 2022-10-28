"""OpenConfig translator for openconfig-platform.

Target OpenConfig object is component ("openconfig-platform:components/component") that is represented as the Component
class. OpenConfig component has various types (based on "openconfig-platform-types:OPENCONFIG_HARDWARE_COMPONENT" and
"openconfig-platform-types:OPENCONFIG_SOFTWARE_COMPONENT") and they implemented as subclasses of the Component.
e.g. Chassis for "CHASSIS".

ComponentNameResolver has a knowledge about Component naming. The knowledge may be corresponding to a device type. You
may implement a ComponentNameResolver for each device type.

Currently, we only support one type of device with gearboxes. So, it is probably too early to generalize/specialize
ComponentFactory and ComponentNameResolver.
"""


from abc import abstractmethod
import logging
from goldstone.lib.core import NoOp
from goldstone.lib.errors import NotFoundError
from .lib import (
    OpenConfigChangeHandler,
    OpenConfigObjectFactory,
    OpenConfigServer,
)


logger = logging.getLogger(__name__)


GS_TRANSPONDER_MODULE = "/goldstone-transponder:modules/module[name='{}']"
GS_TRANSPONDER_MODULE_NAME = GS_TRANSPONDER_MODULE + "/config/name"
GS_TRANSPONDER_MODULE_ADMIN_STATUS = GS_TRANSPONDER_MODULE + "/config/admin-status"
GS_TRANSPONDER_NETIF = GS_TRANSPONDER_MODULE + "/network-interface[name='{}']"
GS_TRANSPONDER_NETIF_NAME = GS_TRANSPONDER_NETIF + "/config/name"
GS_TRANSPONDER_NETIF_TX_LASER_FREQ = GS_TRANSPONDER_NETIF + "/config/tx-laser-freq"
GS_TRANSPONDER_NETIF_OUTPUT_POWER = GS_TRANSPONDER_NETIF + "/config/output-power"
GS_TRANSPONDER_NETIF_LINE_RATE = GS_TRANSPONDER_NETIF + "/config/line-rate"
GS_TRANSPONDER_NETIF_MODULATION_FORMAT = (
    GS_TRANSPONDER_NETIF + "/config/modulation-format"
)
GS_TRANSPONDER_NETIF_FEC_TYPE = GS_TRANSPONDER_NETIF + "/config/fec-type"
GS_TRANSPONDER_NETIF_CLIENT_SIGNAL_MAPPING_TYPE = (
    GS_TRANSPONDER_NETIF + "/config/client-signal-mapping-type"
)
GS_INTERFACES_IFS = "/goldstone-interfaces:interfaces/interface"
GS_INTERFACES_IF = "/goldstone-interfaces:interfaces/interface[name='{}']"
GS_INTERFACES_IF_NAME = GS_INTERFACES_IF + "/config/name"
GS_INTERFACES_IF_ADMIN_STATUS = GS_INTERFACES_IF + "/config/admin-status"
GS_GEARBOX_CONNECTIONS = "/goldstone-gearbox:gearboxes/gearbox/connections/connection"


class ComponentNameResolver:
    """Create and parse OpenConfig component names."""

    def get_chassis(self):
        """Get name for OpenConfig component CHASSIS.

        Returns:
            str: Chassis name.
        """
        return "CHASSIS"

    def get_terminal_line_port(self, module):
        """Get name for OpenConfig component TERMINAL_LINE PORT.

        Args:
            module (dict): Goldstone goldstone-transponder:modules/module.

        Returns:
            str: Line port name.
        """
        return "line-" + module["name"]

    def get_line_transceiver(self, module):
        """Get name for OpenConfig component TRANSCEIVER for TERMINAL_LINE PORT.

        Args:
            module (dict): Goldstone goldstone-transponder:modules/module.

        Returns:
            str: Optical channel name.
        """
        return "transceiver-" + self.get_terminal_line_port(module)

    def get_optical_channel(self, module, network_interface):
        """Get name for OpenConfig component OPTICAL_CHANNEL.

        Args:
            module (dict): Goldstone goldstone-transponder:modules/module.
            network_interface (dict): Goldstone goldstone-transponder:modules/module/network-interface.

        Returns:
            str: Optical channel name.
        """
        return (
            "och-" + self.get_line_transceiver(module) + "-" + network_interface["name"]
        )

    def get_terminal_client_port(self, component):
        """Get name for OpenConfig component TERMINAL_CLIENT PORT.

        Args:
            component (dict): Goldstone goldstone-platform:components/component.

        Returns:
            str: Client port name.
        """
        return "client-" + component["name"]

    def get_client_transceiver(self, component):
        """Get name for OpenConfig component TRANSCEIVER for TERMINAL_CLIENT PORT.

        Args:
            component (dict): Goldstone goldstone-platform:components/component.

        Returns:
            str: Transceiver name.
        """
        return "transceiver-" + self.get_terminal_client_port(component)

    def get_fan(self, component):
        """Get name for OpenConfig component FAN.

        Args:
            component (dict): Goldstone goldstone-platform:components/component.

        Returns:
            str: Fan name.
        """
        return component["name"]

    def get_power_supply(self, component):
        """Get name for OpenConfig component POWER_SUPPLY.

        Args:
            component (dict): Goldstone goldstone-platform:components/component.

        Returns:
            str: Power supply name.
        """
        return component["name"]

    def parse_oc_terminal_line_port(self, name):
        """Parse OpenConfig component TERMINAL_LINE PORT name.

        Args:
            name (str): OpenConfig component name.

        Returns:
            dict: Parsed names.
                  "module": Goldstone goldstone-transponder:modules/module/name.
        """
        suffix = name.split("line-")[1]
        result = {
            "module": suffix,
        }
        return result

    def parse_oc_line_transceiver(self, name):
        """Parse OpenConfig component TRANSCEIVER for TERMINAL_LINE PORT name.

        Args:
            name (str): OpenConfig component name.

        Returns:
            dict: Parsed names.
                  "module": Goldstone goldstone-transponder:modules/module/name.
        """
        suffix = name.split("transceiver-")[1]
        return self.parse_oc_terminal_line_port(suffix)

    def parse_oc_optical_channel(self, name):
        """Parse OpenConfig component OPTICAL_CHANNEL name.

        Args:
            name (str): OpenConfig component name.

        Returns:
            dict: Parsed names.
                  "module": Goldstone goldstone-transponder:modules/module/name.
                  "network-interface": Goldstone goldstone-transponder:modules/module/network-interface/name.
        """
        suffix = name.split("och-")[1]
        tokens = suffix.split("-")
        transceiver = "-".join(tokens[:-1])
        result = self.parse_oc_line_transceiver(transceiver)
        result["network-interface"] = tokens[-1]
        return result

    def parse_oc_terminal_client_port(self, name):
        """Parse OpenConfig component TERMINAL_CLIENT PORT name.

        Args:
            name (str): OpenConfig component name.

        Returns:
            dict: Parsed names.
                  "component": Goldstone goldstone-platform:components/component/name.
        """
        suffix = name.split("client-")[1]
        result = {
            "component": suffix,
        }
        return result

    def parse_oc_client_transceiver(self, name):
        """Parse OpenConfig component TRANSCEIVER for TERMINAL_LINE PORT name.

        Args:
            name (str): OpenConfig component name.

        Returns:
            dict: Parsed names.
                  "component": Goldstone goldstone-platform:components/component/name.
        """
        suffix = name.split("transceiver-")[1]
        return self.parse_oc_terminal_client_port(suffix)

    def get_optical_port_type(self, name):
        port_type = name.split("-")[0]
        if port_type == "line":
            return "TERMINAL_LINE"
        elif port_type == "client":
            return "TERMINAL_CLIENT"


class PlatformChangeHandler(OpenConfigChangeHandler):
    """ChangeHandler base for openconfig-platform:components/component object."""

    def __init__(self, server, change):
        super().__init__(server, change)
        assert self.xpath[0][0] == "openconfig-platform"
        assert self.xpath[0][1] == "components"
        assert self.xpath[1][1] == "component"
        assert self.xpath[1][2][0][0] == "name"
        self.name = self.xpath[1][2][0][1]


class PortAdminStateHandler(PlatformChangeHandler):
    """ChangeHandler for port/optical-port/config/admin-state."""

    def _tp_admin_state(self, admin_state):
        """
        Args:
            admin-state (str): /openconfig-platform:components/component/port/optical-port/config/admin-state.
                ENABLED, DISABLED, MAINT

        Returns:
            str: /goldstone-transponder:modules/module/config/admin-status.
                unknown, down, up
        """
        if admin_state == "ENABLED":
            return "up"
        elif admin_state in ["DISABLED", "MAINT"]:
            return "down"

    def _if_admin_status(self, admin_state):
        """
        Args:
            admin-state (str): /openconfig-platform:components/component/port/optical-port/config/admin-state.
                ENABLED, DISABLED, MAINT

        Returns:
            str: Goldstone /goldstone-interface:interfaces/interface/config/admin-status.
                UP, DOWN
        """
        if admin_state == "ENABLED":
            return "UP"
        elif admin_state in ["DISABLED", "MAINT"]:
            return "DOWN"

    def _hostif(self, user):
        component_name = user["cnr"].parse_oc_terminal_client_port(self.name)[
            "component"
        ]
        interfaces = self._get(user, GS_INTERFACES_IFS, "operational")
        for interface in interfaces:
            try:
                if (
                    interface["component-connection"]["platform"]["component"]
                    == component_name
                ):
                    return interface["name"]
            except (KeyError, TypeError):
                continue

    def _netif(self, user, hostif):
        connections_ = self._get(user, GS_GEARBOX_CONNECTIONS, "operational")
        for connections in connections_:
            for connection in connections:
                try:
                    if connection["client-interface"] == hostif:
                        return connection["line-interface"]
                except (KeyError, TypeError):
                    continue
        raise NotFoundError("corresponding gearbox line-interface is not found")

    def _setup(self, user):
        self.optical_port_type = user["cnr"].get_optical_port_type(self.name)
        if self.optical_port_type == "TERMINAL_LINE":
            names = user["cnr"].parse_oc_terminal_line_port(self.name)
            self.module = names["module"]
            self.module_created = False
            self.module_xpath = GS_TRANSPONDER_MODULE.format(self.module)
            self.module_name_xpath = GS_TRANSPONDER_MODULE_NAME.format(self.module)
            self.tp_admin_state_xpath = GS_TRANSPONDER_MODULE_ADMIN_STATUS.format(
                self.module
            )
        elif self.optical_port_type == "TERMINAL_CLIENT":
            self.hostif = self._hostif(user)
            self.netif = self._netif(user, self.hostif)
            self.hostif_created = False
            self.netif_created = False
            self.hostif_xpath = GS_INTERFACES_IF.format(self.hostif)
            self.netif_xpath = GS_INTERFACES_IF.format(self.netif)
            self.hostif_name_xpath = GS_INTERFACES_IF_NAME.format(self.hostif)
            self.netif_name_xpath = GS_INTERFACES_IF_NAME.format(self.netif)
            self.hostif_admin_status_xpath = GS_INTERFACES_IF_ADMIN_STATUS.format(
                self.hostif
            )
            self.netif_admin_status_xpath = GS_INTERFACES_IF_ADMIN_STATUS.format(
                self.netif
            )

    def _get_item(self, user):
        if self.optical_port_type == "TERMINAL_LINE":
            return self._get(user, self.tp_admin_state_xpath)
        elif self.optical_port_type == "TERMINAL_CLIENT":
            hostif = self._get(user, self.hostif_admin_status_xpath)
            netif = self._get(user, self.netif_admin_status_xpath)
            if hostif is None and netif is None:
                raise NotFoundError("no admin-status values")
            return (hostif, netif)

    def _set_item(self, user, value):
        if self.optical_port_type == "TERMINAL_LINE":
            self._set(user, self.module_name_xpath, self.module)
            self._set(user, self.tp_admin_state_xpath, value)
        elif self.optical_port_type == "TERMINAL_CLIENT":
            hostif_val = value[0]
            netif_val = value[1]
            if hostif_val is not None:
                self._set(user, self.hostif_name_xpath, self.hostif)
                self._set(user, self.hostif_admin_status_xpath, hostif_val)
            else:
                # Delete value to revert.
                if self.hostif_created:
                    self._delete(user, self.hostif_xpath)
                else:
                    self._delete(user, self.hostif_admin_status_xpath)
            if netif_val is not None:
                self._set(user, self.netif_name_xpath, self.netif)
                self._set(user, self.netif_admin_status_xpath, netif_val)
            else:
                # Delete value to revert.
                if self.netif_created:
                    self._delete(user, self.netif_xpath)
                else:
                    self._delete(user, self.netif_admin_status_xpath)

    def _delete_item(self, user):
        if self.optical_port_type == "TERMINAL_LINE":
            if self.module_created:
                self._delete(user, self.module_xpath)
            else:
                self._delete(user, self.tp_admin_state_xpath)
        elif self.optical_port_type == "TERMINAL_CLIENT":
            if self.hostif_created:
                self._delete(user, self.hostif_xpath)
            else:
                self._delete(user, self.hostif_admin_status_xpath)
            if self.netif_created:
                self._delete(user, self.netif_xpath)
            else:
                self._delete(user, self.netif_admin_status_xpath)

    def _translate(self, user, value):
        if self.optical_port_type == "TERMINAL_LINE":
            return self._tp_admin_state(value)
        elif self.optical_port_type == "TERMINAL_CLIENT":
            value = self._if_admin_status(value)
            return (value, value)

    def _validate_parent(self, user):
        if self.optical_port_type == "TERMINAL_LINE":
            if self._get(user, self.module_xpath) is None:
                self.module_created = True
        elif self.optical_port_type == "TERMINAL_CLIENT":
            if self._get(user, self.hostif_xpath) is None:
                self.hostif_created = True
            if self._get(user, self.netif_xpath) is None:
                self.netif_created = True


class OpticalChannelFrequencyHandler(PlatformChangeHandler):
    """ChangeHandler for optical-channel/config/frequency."""

    def _tx_laser_freq(self, frequency):
        """
        Args:
            frequency (int): /openconfig-platform:components/component/optical-channel/config/frequency.
                uint64, MHz

        Returns:
            int: /goldstone-transponder:modules/module/network-interface/config/tx-laser-freq.
                uint64, Hz
        """
        return frequency * 1000000

    def _setup(self, user):
        names = user["cnr"].parse_oc_optical_channel(self.name)
        self.module = names["module"]
        self.netif = names["network-interface"]
        self.module_created = False
        self.netif_created = False
        self.module_xpath = GS_TRANSPONDER_MODULE.format(self.module)
        self.module_name_xpath = GS_TRANSPONDER_MODULE_NAME.format(self.module)
        self.netif_xpath = GS_TRANSPONDER_NETIF.format(self.module, self.netif)
        self.netif_name_xpath = GS_TRANSPONDER_NETIF_NAME.format(
            self.module, self.netif
        )
        self.tx_laser_freq_xpath = GS_TRANSPONDER_NETIF_TX_LASER_FREQ.format(
            self.module, self.netif
        )

    def _get_item(self, user):
        return self._get(user, self.tx_laser_freq_xpath)

    def _set_item(self, user, value):
        self._set(user, self.module_name_xpath, self.module)
        self._set(user, self.netif_name_xpath, self.netif)
        self._set(user, self.tx_laser_freq_xpath, value)

    def _delete_item(self, user):
        if self.module_created:
            self._delete(user, self.module_xpath)
        elif self.netif_created:
            self._delete(user, self.netif_xpath)
        else:
            self._delete(user, self.tx_laser_freq_xpath)

    def _translate(self, user, value):
        return self._tx_laser_freq(value)

    def _validate_parent(self, user):
        if self._get(user, self.module_xpath) is None:
            self.module_created = True
        if self._get(user, self.netif_xpath) is None:
            self.netif_created = True


class OpticalChannelTargetOutputPowerHandler(PlatformChangeHandler):
    """ChangeHandler for optical-channel/config/target-output-power."""

    def _output_power(self, target_output_power):
        """
        Args:
            target_output_power (int): /openconfig-platform:components/component/optical-channel/config/
                target-output-power.
                decimal64 fraction-digits 2, dBm

        Returns:
            int: /goldstone-transponder:modules/module/network-interface/config/output-power.
                decimal64 fraction-digits 16, dBm
        """
        return target_output_power

    def _setup(self, user):
        names = user["cnr"].parse_oc_optical_channel(self.name)
        self.module = names["module"]
        self.netif = names["network-interface"]
        self.module_created = False
        self.netif_created = False
        self.module_xpath = GS_TRANSPONDER_MODULE.format(self.module)
        self.module_name_xpath = GS_TRANSPONDER_MODULE_NAME.format(self.module)
        self.netif_xpath = GS_TRANSPONDER_NETIF.format(self.module, self.netif)
        self.netif_name_xpath = GS_TRANSPONDER_NETIF_NAME.format(
            self.module, self.netif
        )
        self.output_power_xpath = GS_TRANSPONDER_NETIF_OUTPUT_POWER.format(
            self.module, self.netif
        )

    def _get_item(self, user):
        return self._get(user, self.output_power_xpath)

    def _set_item(self, user, value):
        self._set(user, self.module_name_xpath, self.module)
        self._set(user, self.netif_name_xpath, self.netif)
        self._set(user, self.output_power_xpath, value)

    def _delete_item(self, user):
        if self.module_created:
            self._delete(user, self.module_xpath)
        elif self.netif_created:
            self._delete(user, self.netif_xpath)
        else:
            self._delete(user, self.output_power_xpath)

    def _translate(self, user, value):
        return self._output_power(value)

    def _validate_parent(self, user):
        if self._get(user, self.module_xpath) is None:
            self.module_created = True
        if self._get(user, self.netif_xpath) is None:
            self.netif_created = True


class OpticalChannelOperationalModeHandler(PlatformChangeHandler):
    """ChangeHandler for optical-channel/config/opertional-mode."""

    def _tranmission_mode(self, mode):
        """
        Args:
            mode (int): /openconfig-platform:components/component/optical-channel/config/operational-mode.
                uint16

        Returns:
            (str, str, str, str): Tuple contains
                - /goldstone-transponder:modules/module/network-interface/config/line-rate.
                    unknown, 100g, 200g, 300g, 400g
                - /goldstone-transponder:modules/module/network-interface/config/modulation-format.
                    unknown, bpsk, dp-bpsk, qpsk, dp-qpsk, 8-qam, dp-8-qam, 16-qam, dp-16-qam, 32-qam, dp-32-qam,
                    64-qam, dp-64-qam
                - /goldstone-transponder:modules/module/network-interface/config/fec-type.
                    unknown, sc-fec, cfec, ofec
                - /goldstone-transponder:modules/module/network-interface/config/client-signal-mapping-type.
                    unknown, otu4-lr, flexo-lr, zr, otuc2
        """
        try:
            line_rate = self.operational_modes[mode]["line-rate"]
            modulation_format = self.operational_modes[mode]["modulation-format"]
            fec_type = self.operational_modes[mode]["fec-type"]
            client_signal_mapping_type = self.operational_modes[mode][
                "client-signal-mapping-type"
            ]
            return (line_rate, modulation_format, fec_type, client_signal_mapping_type)
        except (KeyError, TypeError):
            return None

    def _setup(self, user):
        self.operational_modes = user["operational-modes"]
        names = user["cnr"].parse_oc_optical_channel(self.name)
        self.module = names["module"]
        self.netif = names["network-interface"]
        self.module_created = False
        self.netif_created = False
        self.module_xpath = GS_TRANSPONDER_MODULE.format(self.module)
        self.module_name_xpath = GS_TRANSPONDER_MODULE_NAME.format(self.module)
        self.netif_xpath = GS_TRANSPONDER_NETIF.format(self.module, self.netif)
        self.netif_name_xpath = GS_TRANSPONDER_NETIF_NAME.format(
            self.module, self.netif
        )
        self.line_rate_xpath = GS_TRANSPONDER_NETIF_LINE_RATE.format(
            self.module, self.netif
        )
        self.modulation_format_xpath = GS_TRANSPONDER_NETIF_MODULATION_FORMAT.format(
            self.module, self.netif
        )
        self.fec_type_xpath = GS_TRANSPONDER_NETIF_FEC_TYPE.format(
            self.module, self.netif
        )
        self.client_signal_mapping_type_xpath = (
            GS_TRANSPONDER_NETIF_CLIENT_SIGNAL_MAPPING_TYPE.format(
                self.module, self.netif
            )
        )

    def _get_item(self, user):
        network_interface = self._get(user, self.netif_xpath)
        if network_interface is not None:
            config = network_interface.get("config")
            if config is not None:
                line_rate = config.get("line-rate")
                modulation_format = config.get("modulation-format")
                fec_type = config.get("fec-type")
                client_signal_mapping_type = config.get("client-signal-mapping-type")
        else:
            line_rate = None
            modulation_format = None
            fec_type = None
            client_signal_mapping_type = None
        if (
            line_rate is None
            and modulation_format is None
            and fec_type is None
            and client_signal_mapping_type is None
        ):
            raise NotFoundError("no operational-mode values")
        return (line_rate, modulation_format, fec_type, client_signal_mapping_type)

    def _set_item(self, user, value):
        self._set(user, self.module_name_xpath, self.module)
        self._set(user, self.netif_name_xpath, self.netif)
        if value[0] is not None:
            self._set(user, self.line_rate_xpath, value[0])
        else:
            self._delete(user, self.line_rate_xpath)
        if value[1] is not None:
            self._set(user, self.modulation_format_xpath, value[1])
        else:
            self._delete(user, self.modulation_format_xpath)
        if value[2] is not None:
            self._set(user, self.fec_type_xpath, value[2])
        else:
            self._delete(user, self.fec_type_xpath)
        # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
        # if value[3] is not None:
        #     self._set(user, self.client_signal_mapping_type_xpath, value[3])
        # else:
        #     self._delete(user, self.client_signal_mapping_type_xpath)

    def _delete_item(self, user):
        if self.module_created:
            self._delete(user, self.module_xpath)
        elif self.netif_created:
            self._delete(user, self.netif_xpath)
        else:
            self._delete(user, self.line_rate_xpath)
            self._delete(user, self.modulation_format_xpath)
            self._delete(user, self.fec_type_xpath)
            # NOTE: Current implementation doesn't allow to configure client-signal-mapping-type.
            # self._delete(user, self.client_signal_mapping_type_xpath)

    def _translate(self, user, value):
        return self._tranmission_mode(value)

    def _validate_parent(self, user):
        if self._get(user, self.module_xpath) is None:
            self.module_created = True
        if self._get(user, self.netif_xpath) is None:
            self.netif_created = True


class Component:
    """Represent openconfig-platform:components/component object.

    Args:
        name (str): Component name.

    Attributes:
        name (str): Component name.
        data (dict): Operational state data of the component.
    """

    def __init__(self, name):
        self.name = name
        self.data = {
            "name": self.name,
            "state": {
                "name": self.name,
            },
        }

    def _id(self, id_):
        """
        Args:
            id_ (int): /goldstone-platform:components/component/state/id.
                uint32

        Returns:
            str: /openconfig-platform:components/component/state/id.
                string
        """
        return str(id_)

    @abstractmethod
    def translate(self):
        """Set component operational state data from Goldstone operational state data."""
        pass

    @abstractmethod
    def update_by_parent(self, parent):
        """Update component data by a parent component.

        Args:
            parent (Component): Parent component.
        """
        pass

    def set_parent(self, name):
        """Set a parent component.

        Args:
            name (str): Parent component name.
        """
        self.data["state"]["parent"] = name

    def append_subcomponent(self, name):
        """Append a subcomponent.

        Args:
            name (str): Subcomponent name.
        """
        if "subcomponents" not in self.data:
            self.data["subcomponents"] = {"subcomponent": []}
        subcomponent = {"name": name, "state": {"name": name}}
        self.data["subcomponents"]["subcomponent"].append(subcomponent)


class Chassis(Component):
    """Component for CHASSIS.

    Args:
        comp_sys (dict): goldstone-platform:components/component object (SYS) to create the component.
        comp_thermal (dict): goldstone-platform:components/component object (THERMAL) to create the component.
        system (dict): goldstone-system:system object to create the component.

    Attributes:
        comp_sys (dict): goldstone-platform:components/component object (SYS) to create the component.
        comp_thermal (dict): goldstone-platform:components/component object (THERMAL) to create the component.
        system (dict): goldstone-system:system object to create the component.
    """

    def __init__(self, name, comp_sys, comp_thermal, system):
        super().__init__(name)
        self.comp_sys = comp_sys
        self.comp_thermal = comp_thermal
        self.system = system
        self.data["state"]["type"] = "openconfig-platform-types:CHASSIS"
        self.data["state"]["oper-status"] = "openconfig-platform-types:ACTIVE"
        self.data["state"]["removable"] = False

    def _temperature(self, temperature):
        """
        Args:
            temperature (int): /goldstone-platform:components/component/thermal/state/temperature.
                int32, milli-celsius

        Returns:
            str: OpenConfig /openconfig-platform:components/component/state/temperature/instant.
                decimal64 fraction-digits 1, celsius
        """
        return round(temperature / 1000, 1)

    def translate(self):
        if self.comp_sys:
            state = self.comp_sys.get("state")
            if state is not None:
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
            sys_ = self.comp_sys.get("sys")
            if sys_ is not None:
                sys_state = sys_.get("state")
                if sys_state is not None:
                    onie_info = sys_state.get("onie-info")
                    if onie_info is not None:
                        manufacturer = onie_info.get("manufacturer")
                        if manufacturer is not None:
                            self.data["state"]["mfg-name"] = manufacturer
                        serial_number = onie_info.get("serial-number")
                        if serial_number is not None:
                            self.data["state"]["serial-no"] = serial_number
                        part_number = onie_info.get("part-number")
                        if part_number is not None:
                            self.data["state"]["part-no"] = part_number
        if self.comp_thermal:
            thermal = self.comp_thermal.get("thermal")
            if thermal is not None:
                state = thermal.get("state")
                if state is not None:
                    temperature = state.get("temperature")
                    if temperature is not None:
                        self.data["state"]["temperature"] = {
                            "instant": self._temperature(temperature)
                        }
        if self.system:
            state = self.system.get("state")
            if state is not None:
                software_version = state.get("software-version")
                if software_version is not None:
                    self.data["state"]["software-version"] = software_version


class TerminalLinePort(Component):
    """Component for TERMINAL_LINE PORT.

    Args:
        module (dict): goldstone-transponder:modules/module object to create the component.

    Attributes:
        module (dict): goldstone-transponder:modules/module object to create the component.
    """

    def __init__(self, name, module):
        super().__init__(name)
        self.module = module
        self.data["state"]["type"] = "openconfig-platform-types:PORT"
        self.data["state"]["removable"] = False
        self.data["port"] = {
            "optical-port": {
                "state": {
                    "optical-port-type": "openconfig-transport-types:TERMINAL_LINE",
                }
            }
        }

    def _id(self, id_):
        """
        Args:
            id_ (int): /goldstone-transponder:modules/module/state/id.
                uint64

        Returns:
            str: OpenConfig /openconfig-platform:components/component/state/id.
                string
        """
        return str(id_)

    def _oper_status(self, oper_status):
        """
        Args:
            oper_status (str): /goldstone-transponder:modules/module/state/oper-status.
                unknown, initialize, ready
        Returns:
            str: /openconfig-platform:components/component/state/oper-status.
                ACTIVE, INACTIVE, DISABLED
        """
        if oper_status == "ready":
            return "openconfig-platform-types:ACTIVE"
        elif oper_status == "initialize":
            return "openconfig-platform-types:INACTIVE"
        elif oper_status == "unknown":
            return "openconfig-platform-types:DISABLED"
        else:
            return "openconfig-platform-types:DISABLED"

    def _admin_state(self, admin_status):
        """
        Args:
            admin_status (str): /goldstone-transponder:modules/module/state/admin-status.
                unknown, down, up

        Returns:
            str: /openconfig-platform:components/component/port/optical-port/state/admin-state.
                ENABLED, DISABLED, MAINT
        """
        if admin_status == "up":
            return "ENABLED"
        elif admin_status in ["down", "unknown"]:
            return "DISABLED"
        else:
            return "DISABLED"

    def translate(self):
        if self.module:
            state = self.module.get("state")
            if state is not None:
                oper_status = state.get("oper-status")
                if oper_status is not None:
                    self.data["state"]["oper-status"] = self._oper_status(oper_status)
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
                location = state.get("location")
                if location is not None:
                    self.data["state"]["location"] = location
                admin_status = state.get("admin-status")
                if admin_status is not None:
                    self.data["port"]["optical-port"]["state"][
                        "admin-state"
                    ] = self._admin_state(admin_status)


class LineTransceiver(Component):
    """Component for TRANSCEIVER in TERMINAL_LINE PORT.

    Args:
        module (dict): goldstone-transponder:modules/module object to create the component.

    Attributes:
        module (dict): goldstone-transponder:modules/module object to create the component.
    """

    def __init__(self, name, module):
        super().__init__(name)
        self.module = module
        self.data["state"]["type"] = "openconfig-platform-types:TRANSCEIVER"
        self.data["state"]["removable"] = True

    def _id(self, id_):
        """
        Args:
            id_ (int): /goldstone-transponder:modules/module/state/id.
                uint64

        Returns:
            str: OpenConfig /openconfig-platform:components/component/state/id.
                string
        """
        return str(id_)

    def _temperature(self, temp):
        """
        Args:
            temp (int): /goldstone-transponder:modules/module/state/id.
                decimal64 fraction-digits 16

        Returns:
            int: /openconfig-platform:components/component/state/temperature/instant.
                decimal64 fraction-digits 1, celsius
        """
        return round(temp, 1)

    def translate(self):
        if self.module:
            state = self.module.get("state")
            if state is not None:
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
                vendor_name = state.get("vendor-name")
                if vendor_name is not None:
                    self.data["state"]["mfg-name"] = vendor_name
                firmware_version = state.get("firmware-version")
                if firmware_version is not None:
                    self.data["state"]["software-version"] = firmware_version
                vendor_serial_number = state.get("vendor-serial-number")
                if vendor_serial_number is not None:
                    self.data["state"]["serial-no"] = vendor_serial_number
                vendor_part_number = state.get("vendor-part-number")
                if vendor_part_number is not None:
                    self.data["state"]["part-no"] = vendor_part_number
                location = state.get("location")
                if location is not None:
                    self.data["state"]["location"] = location
                temp = state.get("temp")
                if temp is not None:
                    self.data["state"]["temperature"] = {
                        "instant": self._temperature(temp)
                    }

    def update_by_parent(self, parent):
        if parent:
            state = parent.data.get("state")
            if state is not None:
                oper_status = state.get("oper-status")
                if oper_status is not None:
                    self.data["state"]["oper-status"] = oper_status


class OpticalChannel(Component):
    """Component for OPTICAL_CHANNEL.

    Args:
        module (dict): goldstone-transponder:modules/module object to create the component.
        network-interface (dict): goldstone-transponder:modules/module/network-interface object to create the component.
        operational-modes (dict): Supported operational-modes.

    Attributes:
        module (dict): goldstone-transponder:modules/module object to create the component.
        network-interface (dict): goldstone-transponder:modules/module/network-interface object to create the component.
        operational-modes (dict): Supported operational-modes.
    """

    def __init__(self, name, module, network_interface, operarional_modes):
        super().__init__(name)
        self.module = module
        self.network_interface = network_interface
        self.operational_modes = operarional_modes
        self.data["state"]["type"] = "openconfig-transport-types:OPTICAL_CHANNEL"
        self.data["state"]["removable"] = False
        self.data["properties"] = {
            "property": [
                {
                    "name": "CROSS_CONNECTION",
                    "state": {"name": "CROSS_CONNECTION", "value": "PRESET"},
                },
                {"name": "latency", "state": {"name": "latency", "value": None}},
            ]
        }

    def _id(self, id_):
        """
        Args:
            id_ (int): /goldstone-transponder:modules/module/network-interface/state/id.
                uint64

        Returns:
            str: /openconfig-platform:components/component/state/id.
                string
        """
        return str(id_)

    def _location(self, index):
        """
        Args:
            index (int): /goldstone-transponder:modules/module/network-interface/state/index.
                uint32

        Returns:
            str: /openconfig-platform:components/component/state/location.
                string
        """
        return str(index)

    def _oper_status(self, oper_status):
        """
        Args:
            oper_status (str): /goldstone-transponder:modules/module/network-interface/state/oper-status.
                unknown, reset, initialize, low-power, high-power-up, tx-off, tx-turn-on, ready, tx-turn-off,
                high-power-down, fault

        Returns:
            str: /openconfig-platform:components/component/state/oper-status.
                ACTIVE, INACTIVE, DISABLED
        """
        if oper_status == "ready":
            return "openconfig-platform-types:ACTIVE"
        elif oper_status in [
            "reset",
            "initialize",
            "low-power",
            "high-power-up",
            "tx-off",
            "tx-turn-on",
            "tx-turn-off",
            "high-power-down",
            "fault",
        ]:
            return "openconfig-platform-types:INACTIVE"
        elif oper_status == "unknown":
            return "openconfig-platform-types:DISABLED"
        else:
            return "openconfig-platform-types:DISABLED"

    def _chromatic_dispersion(self, ccd):
        """
        Args:
            ccd (int): /goldstone-transponder:modules/module/network-interface/state/current-chromatic-dispersion.
                int64, ps/nm

        Returns:
            int:  optical-channel/state/chromatic-dispersion/instant.
                decimal64 fraction-digits 2, ps/nm
        """
        maximum = 92233720368547758.07
        minimum = -92233720368547758.08
        ccd = round(float(ccd), 2)
        if ccd >= maximum:
            return maximum
        elif ccd <= minimum:
            return minimum
        else:
            return ccd

    def _input_power(self, current_input_power):
        """
        Args:
            current_input_power(int): /goldstone-transponder:modules/module/network-interface/state/current-input-power.
                decimal64 fraction-digits 16, dBm

        Returns:
            int: /openconfig-platform:components/component/optical-channel/state/input-power/instant.
                decimal64 fraction-digits 2, dBm
        """
        return round(current_input_power, 2)

    def _output_power(self, current_output_power):
        """
        Args:
            current_output_power(int): /goldstone-transponder:modules/module/network-interface/state/
                current-output-power.
                decimal64 fraction-digits 16, dBm

        Returns:
            int: /openconfig-platform:components/component/optical-channel/state/output-power/instant.
                decimal64 fraction-digits 2, dBm
        """
        return round(current_output_power, 2)

    def _frequency(self, tx_laser_freq):
        """
        Args:
            tx_laser_freq(int): /goldstone-transponder:modules/module/network-interface/state/tx-laser-freq.
                uint64, Hz

        Returns:
            int: /openconfig-platform:components/component/optical-channel/state/frequency.
                uint64, MHz
        """
        return round(tx_laser_freq / 1000000)

    def _target_output_power(self, output_power):
        """
        Args:
            output_power(int): /goldstone-transponder:modules/module/network-interface/state/output-power.
                decimal64 fraction-digits 16, dBm

        Returns:
            int: /openconfig-platform:components/component/optical-channel/state/target-output-power.
                decimal64 fraction-digits 2, dBm
        """
        return round(output_power, 2)

    def _operational_mode(
        self,
        line_rate,
        modulation_format,
        fec_type,
        client_signal_mapping_type,
    ):
        """
        Args:
            line_rate (str): /goldstone-transponder:modules/module/network-interface/state/line-rate.
                unknown, 100g, 200g, 300g, 400g
            modulation_format (str): /goldstone-transponder:modules/module/network-interface/state/modulation-format.
                unknown, bpsk, dp-bpsk, qpsk, dp-qpsk, 8-qam, dp-8-qam, 16-qam, dp-16-qam, 32-qam, dp-32-qam, 64-qam,
                dp-64-qam
            fec_type (str): /goldstone-transponder:modules/module/network-interface/state/fec-type.
                unknown, sc-fec, cfec, ofec
            client_siganl_mapping_type (str): /goldstone-transponder:modules/module/network-interface/state/
                client_signal_mapping_type.
                unknown, otu4-lr, flexo-lr, zr, otuc2

        Return:
            int: /openconfig-platform:components/component/optical-channel/config/operational-mode.
                uint16
        """
        for id_, mode in self.operational_modes.items():
            if (
                line_rate == mode["line-rate"]
                and modulation_format == mode["modulation-format"]
                and fec_type == mode["fec-type"]
            ):
                if (
                    client_signal_mapping_type == mode["client-signal-mapping-type"]
                    or client_signal_mapping_type is None
                ):
                    return id_

    def translate(self):
        if self.network_interface:
            state = self.network_interface.get("state")
            if state is not None:
                oper_status = state.get("oper-status")
                if oper_status is not None:
                    self.data["state"]["oper-status"] = self._oper_status(oper_status)
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
                index = state.get("index")
                if index is not None:
                    self.data["state"]["location"] = self._location(index)
                current_chromatic_dispersion = state.get("current-chromatic-dispersion")
                current_input_power = state.get("current-input-power")
                current_output_power = state.get("current-output-power")
                tx_laser_freq = state.get("tx-laser-freq")
                output_power = state.get("output-power")
                line_rate = state.get("line-rate")
                modulation_format = state.get("modulation-format")
                fec_type = state.get("fec-type")
                client_signal_mapping_type = state.get("client-signal-mapping-type")
                if (
                    current_chromatic_dispersion is not None
                    or current_input_power is not None
                    or current_output_power is not None
                    or tx_laser_freq is not None
                    or output_power is not None
                    or line_rate is not None
                ):
                    self.data["optical-channel"] = {"state": {}}
                if current_chromatic_dispersion is not None:
                    self.data["optical-channel"]["state"]["chromatic-dispersion"] = {
                        "instant": self._chromatic_dispersion(
                            current_chromatic_dispersion
                        )
                    }
                if current_input_power is not None:
                    self.data["optical-channel"]["state"]["input-power"] = {
                        "instant": self._input_power(current_input_power)
                    }
                if current_output_power is not None:
                    self.data["optical-channel"]["state"]["output-power"] = {
                        "instant": self._output_power(current_output_power)
                    }
                if tx_laser_freq is not None:
                    self.data["optical-channel"]["state"][
                        "frequency"
                    ] = self._frequency(tx_laser_freq)
                if output_power is not None:
                    self.data["optical-channel"]["state"][
                        "target-output-power"
                    ] = self._target_output_power(output_power)
                if (
                    line_rate
                    and modulation_format
                    and fec_type
                    # NOTE: Current implementation may not return clinet-signal-mapping-type.
                    # and client_signal_mapping_type
                ):
                    self.data["optical-channel"]["state"][
                        "operational-mode"
                    ] = self._operational_mode(
                        line_rate,
                        modulation_format,
                        fec_type,
                        client_signal_mapping_type,
                    )


class TerminalClientPort(Component):
    """Component for TERMINAL_CLIENT PORT.

    Args:
        component (dict): goldstone-platform:components/component object to create the component.
        interface (dict): goldstone-interfaces:interfaces/interface object to create the component.

    Attributes:
        component (dict): goldstone-platform:components/component object to create the component.
        interface (dict): goldstone-interfaces:interfaces/interface object to create the component.
    """

    def __init__(self, name, component, interface):
        super().__init__(name)
        self.component = component
        self.interface = interface
        self.data["state"]["type"] = "openconfig-platform-types:PORT"
        self.data["state"]["removable"] = False
        self.data["port"] = {
            "optical-port": {
                "state": {
                    "optical-port-type": "openconfig-transport-types:TERMINAL_CLIENT",
                }
            }
        }

    def _oper_status(self, presence, oper_status):
        """
        Args:
            presence (str): /goldstone-platform:components/component/state/transceiver/state/presence.
                PRESENT, UNPLUGGED
            oper_status (str): /goldstone-interfaces:interfaces/interface/state/oper-status.
                UP, DOWN, DORMANT

        Returns:
            str: /openconfig-platform:components/component/state/oper-status.
                ACTIVE, INACTIVE, DISABLED
        """
        if presence == "PRESENT" and oper_status == "UP":
            return "openconfig-platform-types:ACTIVE"
        elif presence == "PRESENT" and (oper_status in ["DOWN", "DORMANT"]):
            return "openconfig-platform-types:INACTIVE"
        elif presence == "UNPLUGGED":
            return "openconfig-platform-types:DISABLED"
        else:
            return "openconfig-platform-types:DISABLED"

    def _admin_state(self, gs):
        """
        Args:
            gs (str): /goldstone-interfaces:interfaces/interface/state/admin-status.
                UP, DOWN

        Returns:
            str: /openconfig-platform:components/component/port/optical-port/config/admin-state.
                ENABLED, DISABLED, MAINT
        """
        if gs == "UP":
            return "ENABLED"
        elif gs == "DOWN":
            return "DISABLED"
        else:
            return "DISABLED"

    def translate(self):
        transceiver = None
        if self.component:
            pf_state = self.component.get("state")
            transceiver = self.component.get("transceiver")
            if pf_state is not None:
                id_ = pf_state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = pf_state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
        if self.interface:
            if_state = self.interface.get("state")
            if if_state is not None:
                admin_status = if_state.get("admin-status")
                if admin_status is not None:
                    self.data["port"]["optical-port"]["state"][
                        "admin-state"
                    ] = self._admin_state(admin_status)
                if transceiver is not None:
                    transceiver_state = transceiver.get("state")
                    if transceiver_state is not None:
                        presence = transceiver_state.get("presence")
                        oper_status = if_state.get("oper-status")
                        if presence is not None and oper_status is not None:
                            self.data["state"]["oper-status"] = self._oper_status(
                                presence, oper_status
                            )


class ClientTransceiver(Component):
    """Component for TRANSCEIVER in TERMINAL_CLIENT PORT.

    Args:
        component (dict): goldstone-platform:components/component object to create the component.
        interface (dict): goldstone-interfaces:interfaces/interface object to create the component.

    Attributes:
        component (dict): goldstone-platform:components/component object to create the component.
        interface (dict): goldstone-interfaces:interfaces/interface object to create the component.
    """

    def __init__(self, name, component, interface):
        super().__init__(name)
        self.component = component
        self.interface = interface
        self.data["state"]["type"] = "openconfig-platform-types:TRANSCEIVER"
        self.data["state"]["removable"] = True

    def translate(self):
        if self.component:
            state = self.component.get("state")
            if state is not None:
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
            transceiver = self.component.get("transceiver")
            if transceiver is not None:
                transceiver_state = transceiver.get("state")
                if transceiver_state is not None:
                    vendor = transceiver_state.get("vendor")
                    if vendor is not None:
                        self.data["state"]["mfg-name"] = vendor
                    serial = transceiver_state.get("serial")
                    if serial is not None:
                        self.data["state"]["serial-no"] = serial
                    model = transceiver_state.get("model")
                    if model is not None:
                        self.data["state"]["part-no"] = model

    def update_by_parent(self, parent):
        if parent:
            state = parent.data.get("state")
            if state is not None:
                oper_status = state.get("oper-status")
                if oper_status is not None:
                    self.data["state"]["oper-status"] = oper_status
                location = state.get("location")
                if location is not None:
                    self.data["state"]["location"] = location


class Fan(Component):
    """Component for FAN.

    Args:
        component (dict): goldstone-platform:components/component object to create the component.

    Attributes:
        component (dict): goldstone-platform:components/component object to create the component.
    """

    def __init__(self, name, component):
        super().__init__(name)
        self.component = component
        self.data["state"]["type"] = "openconfig-platform-types:FAN"

    def _oper_status(self, fan_state, status):
        """
        Args:
            fan_state (str): /goldstone-platform:components/component/fan/state/fan-state.
                PRESENT, NOT-PRESENT
            status (str): /goldstone-platform:components/component/fan/state/status.
                RUNNING, FAILED

        Returns:
            str: /openconfig-platform:components/component/state/oper-status.
                ACTIVE, INACTIVE, DISABLED
        """
        if fan_state == "PRESENT" and status == "RUNNING":
            return "openconfig-platform-types:ACTIVE"
        elif fan_state == "PRESENT" and status == "FAILED":
            return "openconfig-platform-types:INACTIVE"
        elif fan_state == "NOT-PRESENT":
            return "openconfig-platform-types:DISABLED"
        else:
            return "openconfig-platform-types:DISABLED"

    def translate(self):
        if self.component:
            state = self.component.get("state")
            if state is not None:
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
            fan = self.component.get("fan")
            if fan is not None:
                state = fan.get("state")
                if state is not None:
                    fan_state = state.get("fan-state")
                    status = state.get("status")
                    if fan_state is not None and status is not None:
                        self.data["state"]["oper-status"] = self._oper_status(
                            fan_state, status
                        )


class PowerSupply(Component):
    """Component for POWER_SUPPLY.

    Args:
        component (dict): goldstone-platform:components/component object to create the component.

    Attributes:
        component (dict): goldstone-platform:components/component object to create the component.
    """

    def __init__(self, name, component):
        super().__init__(name)
        self.component = component
        self.data["state"]["type"] = "openconfig-platform-types:POWER_SUPPLY"

    def _oper_status(self, psu_state, status):
        """
        Args:
            psu_state (str):  psu/state/psu-state.
            status (str):  psu/state/status.

        Returns:
            str: /openconfig-platform:components/component/state/oper-status.
                ACTIVE, INACTIVE, DISABLED
        """
        if psu_state == "PRESENT" and status == "RUNNING":
            return "openconfig-platform-types:ACTIVE"
        elif psu_state == "PRESENT" and status == "UNPLUGGED-OR-FAILED":
            return "openconfig-platform-types:INACTIVE"
        elif psu_state == "NOT-PRESENT":
            return "openconfig-platform-types:DISABLED"
        else:
            return "openconfig-platform-types:DISABLED"

    def _used_power(self, output_power):
        """
        Args:
            output_power (int): /goldstone-platform:components/component/psu/state/output-power.
                int32, milli-watts

        Returns:
            int:  /openconfig-platform:components/component/state/used-power.
                uint32, watts
        """
        minimum = 0
        if output_power > minimum:
            return round(output_power / 1000)
        else:
            return minimum

    def translate(self):
        if self.component:
            state = self.component.get("state")
            if state is not None:
                id_ = state.get("id")
                if id_ is not None:
                    self.data["state"]["id"] = self._id(id_)
                description = state.get("description")
                if description is not None:
                    self.data["state"]["description"] = description
            psu = self.component.get("psu")
            if psu is not None:
                state = psu.get("state")
                if state is not None:
                    psu_state = state.get("psu-state")
                    status = state.get("status")
                    if psu_state is not None and status is not None:
                        self.data["state"]["oper-status"] = self._oper_status(
                            psu_state, status
                        )
                    serial = state.get("serial")
                    if serial is not None:
                        self.data["state"]["serial-no"] = serial
                    model = state.get("model")
                    if model is not None:
                        self.data["state"]["part-no"] = model
                    output_power = state.get("output-power")
                    if output_power is not None:
                        self.data["state"]["used-power"] = self._used_power(
                            output_power
                        )


class ComponentFactory(OpenConfigObjectFactory):
    """Create OpenConfig components from Goldstone operational state data.

    A component may has references to a parent and subcomponents.

    Args:
        operational_modes (dict): Supported operational-modes.
        cnr (ComponentNameResolver): OpenConfig component name resolver.

    Attributes:
        operational_modes (dict): Supported operational-modes.
        cnr (ComponentNameResolver): OpenConfig component name resolver.
        gs (dict): Operational state data from Goldstone native/primitive models.
    """

    def __init__(self, operational_modes, cnr):
        self.operational_modes = operational_modes
        self.cnr = cnr

    def _initialize(self):
        self.gs = None

    def _get_interface(self, name):
        for interface in self.gs["interfaces"]:
            try:
                if interface["component-connection"]["platform"]["component"] == name:
                    return interface
            except (KeyError, TypeError):
                continue
        return {}

    def _get_parent_line_port(self, line_ports, line_transceiver):
        expected_parent_name = self.cnr.get_terminal_line_port(line_transceiver.module)
        for line_port in line_ports:
            if line_port.name == expected_parent_name:
                return line_port
        return None

    def _get_parent_line_transceiver(self, line_transceivers, optical_channel):
        expected_parent_name = self.cnr.get_line_transceiver(optical_channel.module)
        for line_transceiver in line_transceivers:
            if line_transceiver.name == expected_parent_name:
                return line_transceiver
        return None

    def _get_parent_client_port(self, client_ports, client_transceiver):
        expected_parent_name = self.cnr.get_terminal_client_port(
            client_transceiver.component
        )
        for client_port in client_ports:
            if client_port.name == expected_parent_name:
                return client_port
        return None

    def _create_chassis(self):
        comp_sys = None
        comp_thermal = None
        for component in self.gs["components"]:
            if not comp_sys and component["state"]["type"] == "SYS":
                comp_sys = component
            if not comp_thermal and component["state"]["type"] == "THERMAL":
                # TODO: Which THERMAL component is suitable?
                comp_thermal = component
        chassis = Chassis(
            self.cnr.get_chassis(), comp_sys, comp_thermal, self.gs["system"]
        )
        return chassis

    def _create_terminal_line_ports(self):
        line_ports = []
        for module in self.gs["modules"]:
            line_port = TerminalLinePort(
                self.cnr.get_terminal_line_port(module), module
            )
            line_ports.append(line_port)
        return line_ports

    def _create_line_transceivers(self):
        transceivers = []
        for module in self.gs["modules"]:
            transceiver = LineTransceiver(self.cnr.get_line_transceiver(module), module)
            transceivers.append(transceiver)
        return transceivers

    def _create_optical_channels(self):
        optical_channels = []
        for module in self.gs["modules"]:
            network_interfaces = module.get("network-interface")
            if network_interfaces:
                for network_interface in network_interfaces:
                    optical_channel = OpticalChannel(
                        self.cnr.get_optical_channel(module, network_interface),
                        module,
                        network_interface,
                        self.operational_modes,
                    )
                    optical_channels.append(optical_channel)
        return optical_channels

    def _create_terminal_client_ports(self):
        client_ports = []
        for component in self.gs["components"]:
            if component["state"]["type"] == "TRANSCEIVER":
                interface = self._get_interface(component["name"])
                client_port = TerminalClientPort(
                    self.cnr.get_terminal_client_port(component), component, interface
                )
                client_ports.append(client_port)
        return client_ports

    def _create_client_transceivers(self):
        transceivers = []
        for component in self.gs["components"]:
            if component["state"]["type"] == "TRANSCEIVER":
                if not component["transceiver"]["state"]["presence"] == "UNPLUGGED":
                    interface = self._get_interface(component["name"])
                    transceiver = ClientTransceiver(
                        self.cnr.get_client_transceiver(component), component, interface
                    )
                    transceivers.append(transceiver)
        return transceivers

    def _create_fans(self):
        fans = []
        for component in self.gs["components"]:
            if component["state"]["type"] == "FAN":
                fan = Fan(self.cnr.get_fan(component), component)
                fans.append(fan)
        return fans

    def _create_power_supplies(self):
        power_supplies = []
        for component in self.gs["components"]:
            if component["state"]["type"] == "PSU":
                power_supply = PowerSupply(
                    self.cnr.get_power_supply(component), component
                )
                power_supplies.append(power_supply)
        return power_supplies

    def _set_hierarchy(self, parent, child):
        child.set_parent(parent.name)
        child.update_by_parent(parent)
        parent.append_subcomponent(child.name)

    def required_data(self):
        return [
            {
                "name": "components",
                "xpath": "/goldstone-platform:components/component",
                "default": [],
            },
            {
                "name": "modules",
                "xpath": "/goldstone-transponder:modules/module",
                "default": [],
            },
            {
                "name": "interfaces",
                "xpath": "/goldstone-interfaces:interfaces/interface",
                "default": [],
            },
            {
                "name": "system",
                "xpath": "/goldstone-system:system",
                "default": {},
            },
        ]

    def create(self, gs):
        self._initialize()
        self.gs = gs
        chassis = self._create_chassis()
        line_ports = self._create_terminal_line_ports()
        line_transceivers = self._create_line_transceivers()
        optical_channels = self._create_optical_channels()
        client_ports = self._create_terminal_client_ports()
        client_transceivers = self._create_client_transceivers()
        fans = self._create_fans()
        power_supplies = self._create_power_supplies()
        components = (
            [chassis]
            + line_ports
            + line_transceivers
            + optical_channels
            + client_ports
            + client_transceivers
            + fans
            + power_supplies
        )
        for component in components:
            component.translate()
        # Component hierarchy:
        #     CASSIS
        #     +-- PORT (TERMINAL_LINE)
        #     +   +-- TRANSCEIVER (LINE)
        #     |       +-- OPTICAL_CHANNEL
        #     +-- PORT (TERMINAL_CLIENT)
        #     |   +-- TRANSCEIVER (CLIENT)
        #     +-- FAN
        #     +-- POWER_SUPPLY
        for line_port in line_ports:
            self._set_hierarchy(chassis, line_port)
        for line_transceiver in line_transceivers:
            line_port = self._get_parent_line_port(line_ports, line_transceiver)
            self._set_hierarchy(line_port, line_transceiver)
        for optical_channel in optical_channels:
            line_transceiver = self._get_parent_line_transceiver(
                line_transceivers, optical_channel
            )
            self._set_hierarchy(line_transceiver, optical_channel)
        for client_port in client_ports:
            self._set_hierarchy(chassis, client_port)
        for client_transceiver in client_transceivers:
            client_port = self._get_parent_client_port(client_ports, client_transceiver)
            self._set_hierarchy(client_port, client_transceiver)
        for fan in fans:
            self._set_hierarchy(chassis, fan)
        for power_supply in power_supplies:
            self._set_hierarchy(chassis, power_supply)
        result = []
        for component in components:
            result.append(component.data)
        return result


class PlatformServer(OpenConfigServer):
    """PlatformServer provides a service for the openconfig-platform module to central datastore.

    Args:
        operational_modes (dict): Suppoerted operational-modes.

    Attributes:
        operational_modes (dict): Suppoerted operational-modes.
        cnr (ComponentNameResolver): OpenConfig component name resolver.
    """

    def __init__(self, conn, operational_modes, reconciliation_interval=10):
        super().__init__(conn, "openconfig-platform", reconciliation_interval)
        self.handlers = {
            "components": {
                "component": {
                    "name": NoOp,
                    "config": {
                        "name": NoOp,
                    },
                    "port": {
                        "optical-port": {
                            "config": {
                                "admin-state": PortAdminStateHandler,
                            }
                        }
                    },
                    "optical-channel": {
                        "config": {
                            "frequency": OpticalChannelFrequencyHandler,
                            "target-output-power": OpticalChannelTargetOutputPowerHandler,
                            "operational-mode": OpticalChannelOperationalModeHandler,
                        }
                    },
                    # power-supply/config/enable and linecard/config/power-admin-state has a default value. Any new
                    # component config contains Changes for them.
                    "power-supply": {"config": {"enabled": NoOp}},
                    "linecard": {"config": {"power-admin-state": NoOp}},
                }
            }
        }
        self.operational_modes = operational_modes
        self.cnr = ComponentNameResolver()
        self.objects = {
            "components": {
                "component": ComponentFactory(self.operational_modes, self.cnr)
            }
        }

    async def reconcile(self):
        # TODO: implement
        pass

    def pre(self, user):
        super().pre(user)
        user["operational-modes"] = self.operational_modes
        user["cnr"] = self.cnr
