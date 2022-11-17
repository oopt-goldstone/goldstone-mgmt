"""OpenConfig translator for openconfig-terminal-device.

Target OpenConfig objects are logical-channel ("openconfig-terminal-device:terminal-device/logical-channels/channel")
and operational-mode ("openconfig-terminal-device:terminal-device/operational-modes/mode").

OpenConfig logical-channel is represented as the LogicalChannel class. OpenConfig logical-channel has various types
(based on "openconfig-transport-types:TRIBUTARY_PROTOCOL_TYPE") and they implemented as subclasses of the
LogicalChannel. e.g. LogicalChannel100GE for "PROT_100GE".

OpenConfig operational-mode is represented as just a python dict because of it is simple and has no subtypes.

Currently, we only support one type of device with gearboxes. So, it is probably too early to generalize/specialize
LogicalChannelFactory.
"""


from abc import abstractmethod
import logging
import struct
import base64
from .lib import OpenConfigObjectFactory, OpenConfigServer, OpenConfigObjectTree
from .platform import ComponentFactory, ComponentNameResolver


logger = logging.getLogger(__name__)


class LogicalChannel:
    """LogicalChannel represents openconfig-terminal-device:logical-channels/channel object.

    Args:
        index (int): Logical-channel index.

    Attributes:
        index (int): Logical-channel index.
        data (dict): Operational state date of the logical-channel.
    """

    def __init__(self, index):
        self.index = index
        self.data = {
            "index": self.index,
            "state": {
                "index": self.index,
                "description": "",
                "admin-state": "ENABLED",
            },
            "logical-channel-assignments": {"assignment": []},
        }

    def _get_rate_from_class(self, rate_class):
        return float(
            rate_class.replace("openconfig-transport-types:TRIB_RATE_", "").replace(
                "G", ""
            )
        )

    @abstractmethod
    def translate(self):
        """Set logical-channel operational state data from Goldstone operational state data."""
        pass

    def append_logical_channel_assignment(self, next_logical_channel):
        """Append logical-channel assignment in the logical-channel operational state data.

        Args:
            next_logical_channel (LogicalChannel): Logical-channel to assign.
        """
        index = len(self.data["logical-channel-assignments"]["assignment"])
        self_rate = self._get_rate_from_class(self.data["state"]["rate-class"])
        next_rate = self._get_rate_from_class(
            next_logical_channel.data["state"]["rate-class"]
        )
        if self_rate < next_rate:
            allocation = self_rate
        else:
            allocation = next_rate
        assignment = {
            "index": index,
            "state": {
                "index": index,
                "assignment-type": "LOGICAL_CHANNEL",
                "logical-channel": next_logical_channel.data["index"],
                "mapping": "openconfig-transport-types:GMP",
                "allocation": allocation,
                "tributary-slot-index": 0,
            },
        }
        self.data["logical-channel-assignments"]["assignment"].append(assignment)


class LogicalChannelClientSignal(LogicalChannel):
    """LogicalChannel for client signals.

    Args:
        ingress (str): Ingress transceiver name.

    Attributes:
        ingress (str): Ingress transceiver name.
    """

    def __init__(self, index, ingress):
        super().__init__(index)
        self.ingress = ingress
        self.data["ingress"] = {
            "state": {
                "transceiver": ingress,
            }
        }


class LogicalChannelClientSignalEthernet(LogicalChannelClientSignal):
    """LogicalChannel for Ethernet client signals."""

    def __init__(self, index, ingress):
        super().__init__(index, ingress)
        self.data["state"][
            "logical-channel-type"
        ] = "openconfig-transport-types:PROT_ETHERNET"

    def translate(self):
        # NOTE: No data sources exist.
        # self.data["ethernet"] = {
        #     "state": {
        #         "in-crc-errors": None,
        #         "out-crc-errors": None,
        #         "in-block-errors": None,
        #         "out-block-errors": None,
        #         "in-pcs-bip-errors": None,
        #         "out-pcs-bip-errors": None,
        #         "in-pcs-errored-seconds": None,
        #         "in-pcs-severely-errored-seconds": None,
        #         "in-pcs-unavailable-seconds": None,
        #     }
        # }
        pass


class LogicalChannel100GE(LogicalChannelClientSignalEthernet):
    """LogicalChannel for 100G Ethernet client signal."""

    def __init__(self, index, ingress):
        super().__init__(index, ingress)
        self.data["state"]["rate-class"] = "openconfig-transport-types:TRIB_RATE_100G"
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_100GE"


class LogicalChannel200GE(LogicalChannelClientSignalEthernet):
    """LogicalChannel for 200G Ethernet client signal."""

    def __init__(self, index, ingress):
        super().__init__(index, ingress)
        self.data["state"]["rate-class"] = "openconfig-transport-types:TRIB_RATE_200G"
        # NOTE: OpenConfig does not have a definition for 200GE. (No "PROT_200GE")
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_200GE"


class LogicalChannel400GE(LogicalChannelClientSignalEthernet):
    """LogicalChannel for 400G Ethernet client signal."""

    def __init__(self, index, ingress):
        super().__init__(index, ingress)
        self.data["state"]["rate-class"] = "openconfig-transport-types:TRIB_RATE_400G"
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_400GE"


class LogicalChannelODU(LogicalChannel):
    """LogicalChannel for ODUs.

    This is for both of ODU LO (Lower Order) and ODU HO (Higher Order) protocols. When you need different behavior for
    them, you should split this class into LogicalChannelODULO and LogicalChannelODUHO.
    """

    def __init__(self, index):
        super().__init__(index)
        self.data["state"][
            "logical-channel-type"
        ] = "openconfig-transport-types:PROT_OTN"


class LogicalChannelODU4(LogicalChannelODU):
    """LogicalChannel for ODU4."""

    def __init__(self, index):
        super().__init__(index)
        self.data["state"]["rate-class"] = "openconfig-transport-types:TRIB_RATE_100G"
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_ODU4"


class LogicalChannelODUFlexCBR(LogicalChannelODU):
    """LogicalChannel for ODU flex (CBR).

    Args:
        rate (int): Signal rate in Gbps. e.g. 200 for 200Gbps.

    Attributes:
        rate (int): Signal rate in Gbps.
    """

    def __init__(self, index, rate):
        super().__init__(index)
        self.rate = rate
        if self.rate == 200:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_200G"
        elif self.rate == 400:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_400G"
        else:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_200G"
        self.data["state"][
            "trib-protocol"
        ] = "openconfig-transport-types:PROT_ODUFLEX_CBR"


class LogicalChannelODUCN(LogicalChannelODU):
    """LogicalChannel for ODUCn.

    Args:
        n (int): "n" of ODUCn. e.g. 2 for ODUC2.

    Attributes:
        n (int): "n" of ODUCn.
    """

    def __init__(self, index, n):
        super().__init__(index)
        self.n = n
        if n == 1:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_100G"
        elif n == 2:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_200G"
        elif n == 3:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_300G"
        elif n == 4:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_400G"
        else:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_100G"
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_ODUCN"


class LogicalChannelOTU(LogicalChannel):
    """LogicalChannel for OTU.

    Args:
        optical_channel (str): Optical-channel (openconfig-platform:components/component) name to assign.
        netif (dict): Network interface (goldstone-transponder:modules/module/netowrk-interface) associated with the
            optical-channel.


    Attributes:
        optical_channel (str): Optical-channel (openconfig-platform:components/component) name to assign.
        netif (dict): Network interface (goldstone-transponder:modules/module/netowrk-interface) associated with the
            optical-channel.
    """

    def __init__(self, index, optical_channel, netif):
        super().__init__(index)
        self.optical_channel = optical_channel
        self.netif = netif
        self.data["state"][
            "logical-channel-type"
        ] = "openconfig-transport-types:PROT_OTN"
        self.data["otn"] = {
            "state": {
                "tributary-slot-granularity": "openconfig-transport-types:TRIB_SLOT_5G",
            }
        }

    def _pre_fec_ber_instant(self, current_pre_fec_ber):
        """
        Args:
            current_pre_fec_ber (str): /goldstone-transponder:modules/module/network-interface/state/current-pre-fec-ber
                base64-encoded 64-bit double precision IEEE 754
        Returns:
            str: /openconfig-terminal-device:terminal-device/logical-channels/channel/otn/state/pre-fec-ber/instant
                decimal64 fraction-digits 18, bit-errors-per-second
                libyang failed with "Invalid value" error when the value is represented in scientific notation.
                e.g. fail:    0.00003 (3e-05)
                     success: 0.123456789012345678
                So we should return the value in formated string without scientific notation instead of float.
        """
        maximum = 9.223372036854775807
        minimum = -9.223372036854775808
        ber = round(struct.unpack(">f", base64.b64decode(current_pre_fec_ber))[0], 18)
        if ber >= maximum:
            ber = maximum
        elif ber <= minimum:
            ber = minimum
        return format(ber, ".18f")

    def _pre_fec_ber_interval(self, current_ber_period):
        """
        Args:
            current_ber_period (int): /goldstone-transponder:modules/module/network-interface/state/current-ber-period
                uint32, microseconds
        Returns:
            int: /openconfig-terminal-device:terminal-device/logical-channels/channel/otn/state/pre-fec-ber/interval
                uint64, nanoseconds
        """
        return current_ber_period * 1000

    def _get_rate_from_line(self, line_rate):
        return float(line_rate.replace("g", ""))

    def _append_optical_channel_assignment(self, optical_channel, netif):
        index = len(self.data["logical-channel-assignments"]["assignment"])
        self_rate = self._get_rate_from_class(self.data["state"]["rate-class"])
        next_rate = self._get_rate_from_line(netif["state"]["line-rate"])
        if self_rate < next_rate:
            allocation = self_rate
        else:
            allocation = next_rate
        assignment = {
            "index": index,
            "state": {
                "index": index,
                "assignment-type": "OPTICAL_CHANNEL",
                "optical-channel": optical_channel["name"],
                "mapping": "openconfig-transport-types:GMP",
                "allocation": allocation,
                "tributary-slot-index": 0,
            },
        }
        self.data["logical-channel-assignments"]["assignment"].append(assignment)

    def _assign_optical_channels(self):
        self._append_optical_channel_assignment(self.optical_channel, self.netif)

    def translate(self):
        self._assign_optical_channels()
        netif_state = self.netif.get("state")
        if netif_state is not None:
            current_pre_fec_ber = netif_state.get("current-pre-fec-ber")
            current_ber_period = netif_state.get("current-ber-period")
            if current_pre_fec_ber is not None or current_ber_period is not None:
                self.data["otn"]["state"]["pre-fec-ber"] = {}
            if current_pre_fec_ber is not None:
                self.data["otn"]["state"]["pre-fec-ber"][
                    "instant"
                ] = self._pre_fec_ber_instant(current_pre_fec_ber)
            if current_ber_period is not None:
                self.data["otn"]["state"]["pre-fec-ber"][
                    "interval"
                ] = self._pre_fec_ber_interval(current_ber_period)
        # NOTE: No data sources exist.
        # self.data["otn"]["state"]["errored-seconds"] = None
        # self.data["otn"]["state"]["severely-errored-seconds"] = None
        # self.data["otn"]["state"]["unavailable-seconds"] = None
        # self.data["otn"]["state"]["background-block-errors"] = None
        # self.data["otn"]["state"]["fec-uncorrectable-blocks"] = None
        # self.data["otn"]["state"]["fec-uncorrectable-words"] = None
        # self.data["otn"]["state"]["fec-corrected-bits"] = None
        # self.data["otn"]["state"]["pre-fec-ber"]["avg"] = None
        # self.data["otn"]["state"]["q-value"]["avg"] = None
        # self.data["otn"]["state"]["q-value"]["instant"] = None
        # self.data["otn"]["state"]["q-value"]["interval"] = None
        # self.data["otn"]["state"]["esnr"]["avg"] = None
        # /goldstone-transponder:modules/module/network-interface/state/current-snr may be optical SNR instead of
        # electrical SNR.
        # self.data["otn"]["state"]["esnr"]["instant"] = None


class LogicalChannelOTU4(LogicalChannelOTU):
    """LogicalChannel for OTU4."""

    def __init__(self, index, optical_channel, netif):
        super().__init__(index, optical_channel, netif)
        self.data["state"]["rate-class"] = "openconfig-transport-types:TRIB_RATE_100G"
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_OTU4"


class LogicalChannelOTUCN(LogicalChannelOTU):
    """LogicalChannel for OTUCn.

    Args:
        n (int): "n" of OTUCn. For example, 2 for OTUC2.

    Attributes:
        n (int): "n" of OTUCn.
    """

    def __init__(self, index, optical_channel, netif, n):
        super().__init__(index, optical_channel, netif)
        self.n = n
        if n == 1:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_100G"
        elif n == 2:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_200G"
        elif n == 3:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_300G"
        elif n == 4:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_400G"
        else:
            self.data["state"][
                "rate-class"
            ] = "openconfig-transport-types:TRIB_RATE_100G"
        self.data["state"]["trib-protocol"] = "openconfig-transport-types:PROT_OTUCN"


class LogicalChannelFactory(OpenConfigObjectFactory):
    """Create OpenConfig logical-channels from Goldstone operational state data.

    A logical-channel has one or multiple references to next logical channel(s) or optical-channel component(s) as
    logical-channel-assignments. A logical-channel for client signal also has a reference to a client transceiver
    component as an ingress.

    Args:
        cnr (ComponentNameResolver): OpenConfig component name resolver.
        cf (ComponentFactory): Create OpenConfig components from Goldstone operational state data.
            Getting openconfig-platform operational state data from the central datastore may take few seconds. Use
            ComponentFactory to reduce the time.

    Attributes:
        cnr (ComponentNameResolver): OpenConfig component name resolver.
        cf (ComponentFactory): Create OpenConfig components from Goldstone operational state data.
        gs (dict): Operational state data from Goldstone native/primitive models.
        oc (dict): Operational state data form OpenConfig models.
    """

    DEFAULT_SIGNAL_RATE = "100-gbe"
    DEFAULT_LINE_RATE = "100g"
    DEFAULT_CLIENT_SIGNAL_MAPPING_TYPE = "flexo-lr"

    def __init__(self, cnr, cf):
        self.cnr = cnr
        self.cf = cf
        self._index = 0

    def _initialize(self):
        self._index = 0
        self.gs = None
        self.oc = None

    def _get_oc_component(self, name):
        for component in self.oc["components"]:
            if component["name"] == name:
                return component

    def _get_gb_clientif_name(self, component_name):
        for interface in self.gs["interfaces"]:
            try:
                if (
                    interface["component-connection"]["platform"]["component"]
                    == component_name
                ):
                    return interface["name"]
            except (KeyError, TypeError):
                continue

    def _get_gb_lineif_names(self, hostif_name):
        lineifs = []
        for gearbox in self.gs["gearboxes"]:
            try:
                for connection in gearbox["connections"]["connection"]:
                    if connection["client-interface"] == hostif_name:
                        lineifs.append(connection["line-interface"])
            except (KeyError, TypeError):
                continue
        return lineifs

    def _get_tp_netif_name(self, tp_module_name, tp_hostif_name):
        module = self.gs["modules"][tp_module_name]
        # TODO: Search goldstone-transponder:modules/module/state/tributary-mapping by tp_hostif_name.
        return list(module["network-interface"])[0]["name"]

    def _get_tp(self, gb_lineif_name):
        interface = self.gs["interfaces"][gb_lineif_name]
        try:
            module = interface["component-connection"]["transponder"]["module"]
            hostif = interface["component-connection"]["transponder"]["host-interface"]
            netif = self._get_tp_netif_name(module, hostif)
            return {
                "tp-module": module,
                "tp-hostif": hostif,
                "tp-netif": netif,
            }
        except (KeyError, TypeError):
            return {}

    def _create_client_side_mapping(self):
        """Get internal connectivity mapping information based on clinet ports.

        Returns:
            dict: Mapping information. Example;
                  {
                      "client-port1": {
                          "transceiver": "transceiver-client-port1",
                          "component": "port1",
                          "gb-clientif": "Ethernet1/0/1",
                          "gb-lineifs": {
                              "Ethernet1/1/1": {
                                  "tp-module": "piu1",
                                  "tp-hostif": "1",
                                  "tp-netif": "1",
                              },
                              "Ethernet2/1/1": {..}
                          }
                      },
                      "client-port2": {..}
                  }
        """
        mapping = {}
        for component in self.oc["components"]:
            try:
                if (
                    component["state"]["type"] == "openconfig-platform-types:PORT"
                    and component["port"]["optical-port"]["state"]["optical-port-type"]
                    == "openconfig-transport-types:TERMINAL_CLIENT"
                ):
                    gs_component_name = self.cnr.parse_oc_terminal_client_port(
                        component["name"]
                    )["component"]
                    gb_clientif_name = self._get_gb_clientif_name(gs_component_name)
                    gb_lineif_names = self._get_gb_lineif_names(gb_clientif_name)
                    gb_lineifs = {}
                    for gb_lineif_name in gb_lineif_names:
                        gb_lineifs[gb_lineif_name] = self._get_tp(gb_lineif_name)
                    mapping[component["name"]] = {
                        "transceiver": component["subcomponents"]["subcomponent"][0][
                            "name"
                        ],
                        "component": gs_component_name,
                        "gb-clientif": gb_clientif_name,
                        "gb-lineifs": gb_lineifs,
                    }
            except (KeyError, TypeError):
                continue
        return mapping

    def _create_line_side_mapping(self):
        """Get internal connectivity mapping information based on optical channels.

        Returns:
            dict: Mapping information. Example;
                  {
                      "och-line-piu1-1": {
                          "tp-module": "piu1",
                          "tp-netif": "1",
                      },
                      "och-line-piu2-1": {..}
                  }
        """
        mapping = {}
        for component in self.oc["components"]:
            if (
                component["state"]["type"]
                == "openconfig-transport-types:OPTICAL_CHANNEL"
            ):
                names = self.cnr.parse_oc_optical_channel(component["name"])
                mapping[component["name"]] = {
                    "tp-module": names["module"],
                    "tp-netif": names["network-interface"],
                }
        return mapping

    def _get_index(self):
        # TODO: Improve persistency.
        index = self._index
        self._index += 1
        return index

    def _create_client_side_logical_channels(self, mapping):
        logical_channels = {}
        for name, data in mapping.items():
            # NOTE: Only support 1:1 gerabox connection for now.
            assert len(data["gb-lineifs"]) == 1
            gb_lineif_name = list(data["gb-lineifs"].keys())[0]
            try:
                tp_module = self.gs["modules"][
                    data["gb-lineifs"][gb_lineif_name]["tp-module"]
                ]
                tp_hostif = tp_module["host-interface"][
                    data["gb-lineifs"][gb_lineif_name]["tp-hostif"]
                ]
                signal_rate = tp_hostif["state"]["signal-rate"]
            except (KeyError, TypeError):
                signal_rate = self.DEFAULT_SIGNAL_RATE
            try:
                tp_module = self.gs["modules"][
                    data["gb-lineifs"][gb_lineif_name]["tp-module"]
                ]
                tp_netif = tp_module["network-interface"][
                    data["gb-lineifs"][gb_lineif_name]["tp-netif"]
                ]
                client_signal_mapping_type = tp_netif["state"][
                    "client-signal-mapping-type"
                ]
            except (KeyError, TypeError):
                client_signal_mapping_type = self.DEFAULT_CLIENT_SIGNAL_MAPPING_TYPE
            logical_channels[name] = []
            ingress_transceiver = data["transceiver"]
            if signal_rate == "100-gbe" and client_signal_mapping_type == "otu4-lr":
                logical_channels[name].append(
                    LogicalChannel100GE(self._get_index(), ingress_transceiver)
                )
                logical_channels[name].append(LogicalChannelODU4(self._get_index()))
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            elif signal_rate == "100-gbe" and client_signal_mapping_type == "flexo-lr":
                logical_channels[name].append(
                    LogicalChannel100GE(self._get_index(), ingress_transceiver)
                )
                logical_channels[name].append(LogicalChannelODU4(self._get_index()))
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            elif signal_rate == "200-gbe" and client_signal_mapping_type == "flexo-lr":
                logical_channels[name].append(
                    LogicalChannel200GE(self._get_index(), ingress_transceiver)
                )
                logical_channels[name].append(
                    LogicalChannelODUFlexCBR(self._get_index(), 200)
                )
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            elif signal_rate == "400-gbe" and client_signal_mapping_type == "flexo-lr":
                logical_channels[name].append(
                    LogicalChannel400GE(self._get_index(), ingress_transceiver)
                )
                logical_channels[name].append(
                    LogicalChannelODUFlexCBR(self._get_index(), 400)
                )
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            else:
                logger.warning(
                    "Unsupported combination of signal-rate: %s, client-signal-mapping-type: %s will be ignored.",
                    signal_rate,
                    client_signal_mapping_type,
                )
                continue
            for logical_channel in logical_channels[name]:
                logical_channel.translate()
        return logical_channels

    def _create_line_side_logical_channels(self, mapping):
        logical_channels = {}
        for name, data in mapping.items():
            tp_module = self.gs["modules"][data["tp-module"]]
            tp_netif = tp_module["network-interface"][data["tp-netif"]]
            optical_channel = self._get_oc_component(name)
            try:
                line_rate = tp_netif["state"]["line-rate"]
            except (KeyError, TypeError):
                line_rate = self.DEFAULT_LINE_RATE
            try:
                client_signal_mapping_type = tp_netif["state"][
                    "client-signal-mapping-type"
                ]
            except (KeyError, TypeError):
                client_signal_mapping_type = self.DEFAULT_CLIENT_SIGNAL_MAPPING_TYPE
            logical_channels[name] = []
            if line_rate == "100g" and client_signal_mapping_type == "otu4-lr":
                logical_channels[name].append(LogicalChannelODU4(self._get_index()))
                logical_channels[name].append(
                    LogicalChannelOTU4(self._get_index(), optical_channel, tp_netif)
                )
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            elif line_rate == "100g" and client_signal_mapping_type == "flexo-lr":
                logical_channels[name].append(LogicalChannelODUCN(self._get_index(), 1))
                logical_channels[name].append(
                    LogicalChannelOTUCN(self._get_index(), optical_channel, tp_netif, 1)
                )
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            elif line_rate == "200g" and client_signal_mapping_type == "flexo-lr":
                logical_channels[name].append(LogicalChannelODUCN(self._get_index(), 2))
                logical_channels[name].append(
                    LogicalChannelOTUCN(self._get_index(), optical_channel, tp_netif, 2)
                )
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            elif line_rate == "400g" and client_signal_mapping_type == "flexo-lr":
                logical_channels[name].append(LogicalChannelODUCN(self._get_index(), 4))
                logical_channels[name].append(
                    LogicalChannelOTUCN(self._get_index(), optical_channel, tp_netif, 4)
                )
                logical_channels[name][0].append_logical_channel_assignment(
                    logical_channels[name][1]
                )
            else:
                logger.warning(
                    "Unsupported combination of line-rate: %s, client-signal-mapping-type: %s will be ignored.",
                    line_rate,
                    client_signal_mapping_type,
                )
                continue
            for logical_channel in logical_channels[name]:
                logical_channel.translate()
        return logical_channels

    def _connect_client_and_line(
        self, mapping, client_logical_channels, line_logical_channels
    ):
        for client_port in mapping:
            if (
                client_port not in client_logical_channels.keys()
                or len(client_logical_channels[client_port]) < 1
            ):
                # No client side logical channels for the client port.
                continue
            for tp in mapping[client_port]["gb-lineifs"].values():
                try:
                    tp_module = self.gs["modules"][tp["tp-module"]]
                    tp_netif = tp_module["network-interface"][tp["tp-netif"]]
                except (KeyError, TypeError):
                    # The gearbox line interface does not connect to a transponder.
                    continue
                optical_channel = self.cnr.get_optical_channel(tp_module, tp_netif)
                if (
                    optical_channel not in line_logical_channels.keys()
                    or len(line_logical_channels[optical_channel]) < 1
                ):
                    # No line side logical channels for the optical-channel.
                    continue
                client_logical_channels[client_port][
                    -1
                ].append_logical_channel_assignment(
                    line_logical_channels[optical_channel][0]
                )

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
                "name": "gearboxes",
                "xpath": "/goldstone-gearbox:gearboxes/gearbox",
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
        self.oc = {"components": self.cf.create(self.gs)}
        client_mapping = self._create_client_side_mapping()
        line_mapping = self._create_line_side_mapping()
        client_logical_channels = self._create_client_side_logical_channels(
            client_mapping
        )
        line_logical_channels = self._create_line_side_logical_channels(line_mapping)
        # Logical channel assignment structure:
        #     [Client side]
        #     ingress transceiver component
        #               |
        #     logical channel for client signal
        #               |
        #     logical channel for ODU LO
        #               |
        #     logical channel for ODU HO
        #               |
        #     logical channel for OTU
        #               |
        #     optical channel component
        #     [Line side]
        self._connect_client_and_line(
            client_mapping, client_logical_channels, line_logical_channels
        )
        logical_channels = []
        for part_logical_channels in list(client_logical_channels.values()) + list(
            line_logical_channels.values()
        ):
            for logical_channel in part_logical_channels:
                logical_channels.append(logical_channel.data)
        return logical_channels


class OperationalModeFactory(OpenConfigObjectFactory):
    """Create OpenConfig operational-modes from provided operational modes.

    Args:
        operational_modes (dict): Operational modes as server configuration.

    Attributes:
        operational_modes (dict): Operational modes as server configuration.
    """

    def __init__(self, operatinal_modes):
        self.operational_modes = operatinal_modes

    def _initialize(self):
        pass

    def required_data(self):
        return []

    def create(self, gs):
        self._initialize()
        operational_modes = []
        for mode_id in self.operational_modes:
            try:
                mode = {
                    "mode-id": mode_id,
                    "state": {
                        "mode-id": mode_id,
                        "description": self.operational_modes[mode_id]["description"],
                        "vendor-id": self.operational_modes[mode_id]["vendor-id"],
                    },
                }
                operational_modes.append(mode)
            except (KeyError, TypeError):
                logger.warning(
                    "Invalid operational-mode: %s. Ignore.",
                    self.operational_modes[mode_id],
                )
        return operational_modes


class TerminalDeviceObjectTree(OpenConfigObjectTree):
    """OpenConfigObjectTree for the openconfig-terminal-device module.

    It creates an operational state data tree of the openconfig-terminal-device module.

    Args:
        operational_modes (dict): Supported operational-modes.
    """

    def __init__(self, operational_modes):
        super().__init__()
        cnr = ComponentNameResolver()
        self.objects = {
            "terminal-device": {
                "logical-channels": {
                    "channel": LogicalChannelFactory(
                        cnr,
                        ComponentFactory(operational_modes, cnr),
                    )
                },
                "operational-modes": {
                    "mode": OperationalModeFactory(operational_modes)
                },
            }
        }


class TerminalDeviceServer(OpenConfigServer):
    """TerminalDeviceServer provides a service for the openconfig-terminal-device module to central datastore.

    Args:
        operational_modes (dict): Suppoerted operational-modes.

    Attributes:
        operational_modes (dict): Suppoerted operational-modes.
    """

    def __init__(self, conn, cache, operational_modes, reconciliation_interval=10):
        super().__init__(
            conn, "openconfig-terminal-device", cache, reconciliation_interval
        )
        self.handlers = {"terminal-device": {}}
        self.operational_modes = operational_modes
        self._object_tree = TerminalDeviceObjectTree(self.operational_modes)

    async def reconcile(self):
        pass

    def pre(self, user):
        super().pre(user)
        user["operational-modes"] = self.operational_modes
