import asyncio
import logging

import libyang
import sysrepo
from goldstone.lib.core import *
from .lib import OpenROADMServer

logger = logging.getLogger(__name__)

OPENROADM_VERSION = "10.0"

GS_PLATFORM_COMPONENTS_COMPONENT = "/goldstone-platform:components/component"
GS_TRANSPONDER_MODULE = "/goldstone-transponder:modules/module[name='{}']"
GS_TRANSPONDER_MODULE_NAME = GS_TRANSPONDER_MODULE + "/config/name"
GS_TRANSPONDER_NETIF = GS_TRANSPONDER_MODULE + "/network-interface[name='{}']"
GS_TRANSPONDER_NETIF_NAME = GS_TRANSPONDER_NETIF + "/config/name"
GS_TRANSPONDER_NETIF_TX_LASER_FREQ = GS_TRANSPONDER_NETIF + "/config/tx-laser-freq"
GS_TRANSPONDER_NETIF_OUTPUT_POWER = GS_TRANSPONDER_NETIF + "/config/output-power"
GS_TRANSPONDER_NETIF_LINE_RATE = GS_TRANSPONDER_NETIF + "/config/line-rate"
GS_TRANSPONDER_NETIF_MODULATION_FORMAT = (
    GS_TRANSPONDER_NETIF + "/config/modulation-format"
)
GS_TRANSPONDER_NETIF_FEC_TYPE = GS_TRANSPONDER_NETIF + "/config/fec-type"
GS_TRANSPONDER_NETIF_LOOPBACK_TYPE = GS_TRANSPONDER_NETIF + "/config/loopback-type"
GS_TRANSPONDER_HOSTIF = GS_TRANSPONDER_MODULE + "/host-interface[name='{}']"
GS_TRANSPONDER_HOSTIF_NAME = GS_TRANSPONDER_HOSTIF + "/config/name"
GS_TRANSPONDER_HOSTIF_SIGNAL_RATE = GS_TRANSPONDER_HOSTIF + "/config/signal-rate"
GS_TRANSPONDER_HOSTIF_FEC_TYPE = GS_TRANSPONDER_HOSTIF + "/config/fec-type"


class ShelfChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "org-openroadm-device"
        assert xpath[0][1] == "org-openroadm-device"
        assert xpath[1][1] == "shelves"
        assert xpath[1][2][0][0] == "shelf-name"
        self.xpath = xpath
        self.shelfname = xpath[1][2][0][1]

    def _get_components_by_type(self, type):
        ret = []
        for component in self.server.components:
            if component["state"]["type"] == type:
                ret.append(component)
        return ret


class ShelfNameHandler(ShelfChangeHandler):
    def validate(self, user):
        logger.info(
            f"ShelfNameHandler:validate: type:{self.type}, change:{self.change}"
        )
        if self.type in ["created", "modified"]:
            # Only allow for provisioning of 'SYS' shelf
            sys_components = self._get_components_by_type("SYS")
            valid_names = [comp.get("name") for comp in sys_components]
            if self.shelfname not in valid_names:
                raise sysrepo.errors.SysrepoInvalArgError("invalid shelf-name")


class CircuitPackChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "org-openroadm-device"
        assert xpath[0][1] == "org-openroadm-device"
        assert xpath[1][1] == "circuit-packs"
        assert xpath[1][2][0][0] == "circuit-pack-name"
        self.xpath = xpath
        self.circuit_pack_name = xpath[1][2][0][1]

    def _get_component_by_name(self, name):
        for component in self.server.components:
            if component["name"] == name:
                return component
        return None


class CircuitPackNameHandler(CircuitPackChangeHandler):
    def validate(self, user):
        logger.info(
            f"CircuitPackChangeHandler:validate: type:{self.type}, change:{self.change}"
        )
        if self.type in ["created", "modified"]:
            # Only allow for provisioning of circuit-packs matching primitive model components
            if not self._get_component_by_name(self.circuit_pack_name):
                raise sysrepo.errors.SysrepoInvalArgError("invalid circuit-pack-name")


class PortNameHandler(CircuitPackChangeHandler):
    def validate(self, user):
        logger.info(f"PortNameHandler:validate: type:{self.type}, change:{self.change}")
        if self.type in ["created", "modified"]:
            # Only allow ports for transceivers and PIUs
            comp = self._get_component_by_name(self.circuit_pack_name)
            if not comp:
                raise sysrepo.errors.SysrepoInvalArgError("invalid circuit-pack")
            comp_type = comp.get("state", {}).get("type")
            if comp_type not in ["TRANSCEIVER", "PIU"]:
                raise sysrepo.errors.SysrepoInvalArgError(
                    "port provisioning only allowed on TRANSCEIVER, PIU"
                )

            # Only allow provisioning of "1" port-name
            if self.change.value != "1":
                raise sysrepo.errors.SysrepoInvalArgError("invalid port-name")


class IfChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "org-openroadm-device"
        assert xpath[0][1] == "org-openroadm-device"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        self.ifname = xpath[1][2][0][1]
        self.attr_name = None

    async def validate(self, user):
        logger.info(f"IfChangeHandler:validate: type:{self.type}, change:{self.change}")
        cache = self.setup_cache(user)
        # find OpenROADM supporting circuit-pack
        xpath = f"/org-openroadm-device:org-openroadm-device/interface[name='{self.ifname}']/supporting-circuit-pack-name"
        self.or_cpname = libyang.xpath_get(cache, xpath)
        if not self.or_cpname and self.type == "deleted":
            self.or_cpname = self.server.otsi_sup_cpname[self.ifname]

    async def validate_modules(self, user):
        """Validate and save primitive goldstone-transponder module and network interface name."""
        # find/validate goldstone-transponder module
        module_data = self.server.get_operational_data(
            GS_TRANSPONDER_MODULE.format(self.or_cpname)
        )

        if module_data == None:
            raise sysrepo.errors.SysrepoInvalArgError("missing goldstone module")

        # validate module name
        gsoper_name = libyang.xpath_get(module_data, "name")
        if gsoper_name[0] == None:
            raise sysrepo.errors.SysrepoInvalArgError("missing goldstone module name")

        # validate network-interface name
        gsoper_niname = libyang.xpath_get(module_data, "network-interface/config/name")
        if gsoper_niname[0] == None:
            raise sysrepo.errors.SysrepoInvalArgError(
                "missing goldstone module network interface name"
            )

        self.module_data = module_data
        # only supporting single name entries for now
        self.gsoper_name = gsoper_name[0]
        self.gsoper_niname = gsoper_niname[0][0]


class TxPwrHandler(IfChangeHandler):
    async def validate(self, user):
        logger.info(f"TxPwrHandler:validate: type:{self.type}, change:{self.change}")
        await super().validate(user)
        await super().validate_modules(user)

        # Store original output-power for revert
        orig_output_power = libyang.xpath_get(
            self.module_data, "network-interface/config/output-power"
        )
        self.orig_output_power = orig_output_power

    def apply(self, user):
        logger.info(f"TxPwrHandler:apply: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]

        # Note that any set operations performed from here are only allowed to use goldstone derived information
        if self.type in ["created", "modified"]:
            # There are other required leafs that have to be created
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                f"{self.gsoper_niname}",
            )
            sess.set(
                GS_TRANSPONDER_NETIF_OUTPUT_POWER.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.change.value,
            )

        else:
            # delete processing
            sess.delete(
                GS_TRANSPONDER_NETIF_OUTPUT_POWER.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )

    def revert(self, user):
        logger.warning(f"TxPwrHandler:revert: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]
        if self.orig_output_power != None:
            sess.set(
                GS_TRANSPONDER_NETIF_OUTPUT_POWER.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.orig_output_power,
            )

        else:
            # no output power was set originally, so cleanup output power leaf
            sess.delete(
                GS_TRANSPONDER_NETIF_OUTPUT_POWER.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )


class OpticalOperationalModeHandler(IfChangeHandler):
    async def validate(self, user):
        logger.info(
            f"OpticalOperationalMode:validate: type:{self.type}, change:{self.change}"
        )
        await super().validate(user)
        await super().validate_modules(user)

        # save original values for revert
        self.orig_values = {
            "line-rate": libyang.xpath_get(
                self.module_data, "network-interface/config/line-rate"
            ),
            "modulation-format": libyang.xpath_get(
                self.module_data, "network-interface/config/modulation-format"
            ),
            "fec-type": libyang.xpath_get(
                self.module_data, "network-interface/config/fec-type"
            ),
        }

        # check json file for provisioned mode
        if self.type in ["created", "modified"]:
            for mode in self.server.operational_modes:
                if mode.get("openroadm", {}).get("profile-name") == self.change.value:
                    self.mode = mode
                    return
            raise sysrepo.errors.SysrepoInvalArgError(
                "invalid optical operational mode: profile not found"
            )

    def apply(self, user):
        logger.info(
            f"OpticalOperationalMode:apply: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        line_rate_xpath = GS_TRANSPONDER_NETIF_LINE_RATE.format(
            self.gsoper_name, self.gsoper_niname
        )
        mod_format_xpath = GS_TRANSPONDER_NETIF_MODULATION_FORMAT.format(
            self.gsoper_name, self.gsoper_niname
        )
        fec_type_xpath = GS_TRANSPONDER_NETIF_FEC_TYPE.format(
            self.gsoper_name, self.gsoper_niname
        )

        if self.type in ["created", "modified"]:
            # other required leaves
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                self.gsoper_niname,
            )

            # set values from json-defined mode
            sess.set(line_rate_xpath, self.mode.get("line-rate"))
            sess.set(mod_format_xpath, self.mode.get("modulation-format"))
            sess.set(fec_type_xpath, self.mode.get("fec-type"))
        else:
            sess.delete(line_rate_xpath)
            sess.delete(mod_format_xpath)
            sess.delete(fec_type_xpath)

    def revert(self, user):
        logger.warning(
            f"OpticalOperationalMode:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        for leaf in self.orig_values:
            if self.orig_values.get(leaf) != None:
                sess.set(
                    GS_TRANSPONDER_NETIF.format(self.gsoper_name, self.gsoper_niname)
                    + "/config/{leaf}",
                    self.orig_values.get(leaf),
                )
            else:
                sess.delete(
                    GS_TRANSPONDER_NETIF.format(self.gsoper_name, self.gsoper_niname)
                    + "/config/{leaf}"
                )


class OtsiRateHandler(IfChangeHandler):
    OTSIRATE_PREFIX = "org-openroadm-common-optical-channel-types:"
    OR_TO_GS = {
        OTSIRATE_PREFIX + "R100G-otsi": "100g",
        OTSIRATE_PREFIX + "R200G-otsi": "200g",
        OTSIRATE_PREFIX + "R300G-otsi": "300g",
        OTSIRATE_PREFIX + "R400G-otsi": "400g",
    }
    GS_TO_OR = dict((v, k) for k, v in OR_TO_GS.items() if v != "unknown")

    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM otsi-rate and Goldstone line-rate values.

        Args:
            or_val (str): OpenROADM otsi-rate value to convert, None if conversion type
            gs_val (str): Goldstone line-rate value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return (
            OtsiRateHandler.OR_TO_GS.get(or_val)
            if or_val != None
            else OtsiRateHandler.GS_TO_OR.get(gs_val)
        )

    async def validate(self, user):
        logger.info(f"OtsiRateHandler:validate: type:{self.type}, change:{self.change}")
        await super().validate(user)
        await super().validate_modules(user)

        # check if supported/translatable
        if self.type in ["created", "modified"]:
            self.new_rate = OtsiRateHandler.translate(or_val=self.change.value)
            if self.new_rate == None:
                raise sysrepo.errors.SysrepoInvalArgError(
                    "invalid otsi-rate: not supported"
                )

        # store original line-rate for revert
        self.orig_linerate = libyang.xpath_get(
            self.module_data, "network-interface/config/line-rate"
        )

    def apply(self, user):
        logger.info(f"OtsiRateHandler:apply: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]

        if self.type in ["created", "modified"]:
            # other required leaves
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                self.gsoper_niname,
            )

            # set line-rate
            sess.set(
                GS_TRANSPONDER_NETIF_LINE_RATE.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.new_rate,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_LINE_RATE.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )

    def revert(self, user):
        logger.warning(
            f"OtsiRateHandler:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        if self.orig_linerate:
            sess.set(
                GS_TRANSPONDER_NETIF_LINE_RATE.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.orig_linerate,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_LINE_RATE.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )


class ModulationFormatHandler(IfChangeHandler):
    OR_TO_GS = {
        "bpsk": "bpsk",
        "dc-dp-bpsk": "dp-bpsk",
        "qpsk": "qpsk",
        "dp-qpsk": "dp-qpsk",
        "qam16": "16-qam",
        "dp-qam16": "dp-16-qam",
        "dc-dp-qam16": "unknown",
        "qam8": "8-qam",
        "dp-qam8": "dp-8-qam",
        "dc-dp-qam16": "unknown",
    }
    GS_TO_OR = dict((v, k) for k, v in OR_TO_GS.items() if v != "unknown")

    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM modulation-format and Goldstone modulation-format values.

        Args:
            or_val (str): OpenROADM modulation-format value to convert, None if conversion type
            gs_val (str): Goldstone modulation-format value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return (
            ModulationFormatHandler.OR_TO_GS.get(or_val)
            if or_val != None
            else ModulationFormatHandler.GS_TO_OR.get(gs_val)
        )

    async def validate(self, user):
        logger.info(
            f"ModulationFormatHandler:validate: type:{self.type}, change:{self.change}"
        )
        await super().validate(user)
        await super().validate_modules(user)

        # check if supported/translatable
        if self.type in ["created", "modified"]:
            self.new_format = ModulationFormatHandler.translate(
                or_val=self.change.value
            )
            if self.new_format == None:
                raise sysrepo.errors.SysrepoInvalArgError(
                    "invalid modulation-format: not supported"
                )

        # store original modulation-format for revert
        self.orig_modulationformat = libyang.xpath_get(
            self.module_data, "network-interface/config/modulation-format"
        )

    def apply(self, user):
        logger.info(
            f"ModulationFormatHandler:apply: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]

        if self.type in ["created", "modified"]:
            # other required leaves
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                self.gsoper_niname,
            )

            # set modulation-format
            sess.set(
                GS_TRANSPONDER_NETIF_MODULATION_FORMAT.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.new_format,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_MODULATION_FORMAT.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )

    def revert(self, user):
        logger.warning(
            f"ModulationFormatHandler:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        if self.orig_modulationformat:
            sess.set(
                GS_TRANSPONDER_NETIF_MODULATION_FORMAT.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.orig_modulationformat,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_MODULATION_FORMAT.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )


class FecHandler(IfChangeHandler):
    FEC_PREFIX = "org-openroadm-common-types:"
    OR_TO_GS = {
        FEC_PREFIX + "off-fec": "unknown",
        FEC_PREFIX + "off": "none",
        FEC_PREFIX + "scfec": "sc-fec",
        FEC_PREFIX + "rsfec": "unknown",
        FEC_PREFIX + "ofec": "ofec",
        FEC_PREFIX + "efec": "unknown",
        FEC_PREFIX + "ufec": "unknown",
        FEC_PREFIX + "sdfec": "unknown",
        FEC_PREFIX + "sdfeca1": "unknown",
        FEC_PREFIX + "sdfecb1": "unknown",
        FEC_PREFIX + "baser": "unknown",
    }
    GS_TO_OR = dict((v, k) for k, v in OR_TO_GS.items() if v != "unknown")

    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM fec and Goldstone fec-type values.

        Args:
            or_val (str): OpenROADM fec value to convert, None if conversion type
            gs_val (str): Goldstone fec-type value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return (
            FecHandler.OR_TO_GS.get(or_val)
            if or_val != None
            else FecHandler.GS_TO_OR.get(gs_val)
        )

    async def validate(self, user):
        logger.info(f"FecHandler:validate: type:{self.type}, change:{self.change}")
        await super().validate(user)
        await super().validate_modules(user)

        # check if supported/translatable
        if self.type in ["created", "modified"]:
            self.new_fec = FecHandler.translate(or_val=self.change.value)
            if self.new_fec == None:
                raise sysrepo.errors.SysrepoInvalArgError("invalid fec: not supported")

        # store original fec-type for revert
        self.orig_fec = libyang.xpath_get(
            self.module_data, "network-interface/config/fec-type"
        )

    def apply(self, user):
        logger.info(f"FecHandler:apply: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]
        module_xpath = (
            f"/goldstone-transponder:modules/module[name='{self.gsoper_name}']"
        )
        ni_xpath = module_xpath + f"/network-interface[name='{self.gsoper_niname}']"

        if self.type in ["created", "modified"]:
            # other required leaves
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                self.gsoper_niname,
            )

            # set fec-type
            sess.set(
                GS_TRANSPONDER_NETIF_FEC_TYPE.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.new_fec,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_FEC_TYPE.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )

    def revert(self, user):
        logger.warning(f"FecHandler:revert: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]
        if self.orig_fec:
            sess.set(
                GS_TRANSPONDER_NETIF_FEC_TYPE.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.orig_fec,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_FEC_TYPE.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )


class FrequencyHandler(IfChangeHandler):
    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM frequency values and Goldstone tx-laser-freq.

        Args:
            or_val (float): OpenROADM frequency value to convert, None if conversion type
            gs_val (int): Goldstone tx-laser-freq value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return int(or_val * 1e12) if or_val != None else round(gs_val / 1e12, 8)

    async def validate(self, user):
        logger.info(
            f"FrequencyHandler:validate: type:{self.type}, change:{self.change}"
        )
        await super().validate(user)
        await super().validate_modules(user)

        # store original frequency for revert
        self.orig_frequency = libyang.xpath_get(
            self.module_data, "network-interface/config/tx-laser-freq"
        )

    def apply(self, user):
        logger.info(f"FrequencyHandler:apply: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]

        if self.type in ["created", "modified"]:
            # other required leaves
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                self.gsoper_niname,
            )

            # set frequency (convert from THz to Hz)
            sess.set(
                GS_TRANSPONDER_NETIF_TX_LASER_FREQ.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                FrequencyHandler.translate(or_val=self.change.value),
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_TX_LASER_FREQ.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )

    def revert(self, user):
        logger.warning(
            f"FrequencyHandler:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        if self.orig_frequency:
            sess.set(
                GS_TRANSPONDER_NETIF_TX_LASER_FREQ.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.orig_frequency,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_TX_LASER_FREQ.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )


class EthSpdHandler(IfChangeHandler):
    GS_TO_OR = {
        "unknown": 0,
        "100-gbe": 100000,
        "200-gbe": 200000,
        "400-gbe": 400000,
        "otu4": 100000,
    }
    OR_TO_GS = dict((v, k) for k, v in GS_TO_OR.items())
    OR_TO_GS[100000] = "100-gbe"

    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM speed and Goldstone signal-rate values.

        Args:
            or_val (int): OpenROADM speed value to convert, None if conversion type
            gs_val (str): Goldstone signal-rate value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return (
            EthSpdHandler.OR_TO_GS.get(or_val)
            if or_val != None
            else EthSpdHandler.GS_TO_OR.get(gs_val)
        )

    async def validate(self, user):
        logger.info(f"EthSpdHandler:validate: type:{self.type}, change:{self.change}")
        await super().validate(user)

        gs_piu, gs_port = self.server._translate_circuit_pack_name(
            self.server.or_port_map, self.or_cpname
        )
        module_data = self.server.get_operational_data(
            GS_TRANSPONDER_HOSTIF.format(gs_piu, gs_port)
        )
        if module_data == None:
            raise sysrepo.errors.SysrepoInvalArgError("missing goldstone module")

        gsoper_hiname = libyang.xpath_get(module_data, "name")
        if gsoper_hiname[0] == None:
            raise sysrepo.errors.SysrepoInvalArgError(
                "missing goldstone host interface name"
            )

        # check that the incoming speed value is sane (for changes)
        new_speed = "unknown"
        if self.type in ["created", "modified"]:
            new_speed = EthSpdHandler.translate(or_val=self.change.value)
            if new_speed == None:
                raise sysrepo.errors.SysrepoInvalArgError("invalid ethernet speed")

        # Last is to store the existing speed to handle revert cases
        orig_speed = libyang.xpath_get(module_data, "config/signal-rate")

        self.gsoper_hiname = gsoper_hiname[0]
        self.gs_piu = gs_piu
        self.new_speed = new_speed
        if orig_speed:
            self.orig_speed = orig_speed[0]
        else:
            self.orig_speed = None

    def apply(self, user):
        logger.info(f"\n\nEthSpdHandler:apply: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]

        if self.type in ["created", "modified"]:
            sess.set(GS_TRANSPONDER_MODULE_NAME.format(self.gs_piu), self.gs_piu)
            sess.set(
                GS_TRANSPONDER_HOSTIF_NAME.format(self.gs_piu, self.gsoper_hiname),
                self.gsoper_hiname,
            )
            sess.set(
                GS_TRANSPONDER_HOSTIF_SIGNAL_RATE.format(
                    self.gs_piu, self.gsoper_hiname
                ),
                self.new_speed,
            )
        else:
            # delete processing
            sess.delete(
                GS_TRANSPONDER_HOSTIF_SIGNAL_RATE.format(
                    self.gs_piu, self.gsoper_hiname
                )
            )

    def revert(self, user):
        logger.warning(
            f"\n\nEthSpdHandler:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        if self.orig_speed != None:
            sess.set(
                GS_TRANSPONDER_HOSTIF_SIGNAL_RATE.format(
                    self.gs_piu, self.gsoper_hiname
                ),
                self.orig_speed,
            )
        else:
            # no eth speed was set originally, so cleanup the host interface leaf
            sess.delete(
                GS_TRANSPONDER_HOSTIF_NAME.format(self.gs_piu, self.gsoper_hiname)
            )


class OtuMaintLoopbackTypeHandler(IfChangeHandler):
    OR_TO_GS = {"fac": "shallow", "fac2": "deep"}
    GS_TO_OR = dict((v, k) for k, v in OR_TO_GS.items())

    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM type and Goldstone loopback-type values.

        Args:
            or_val (str): OpenROADM type value to convert, None if conversion type
            gs_val (str): Goldstone loopback-type value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return (
            OtuMaintLoopbackTypeHandler.OR_TO_GS.get(or_val)
            if or_val != None
            else OtuMaintLoopbackTypeHandler.GS_TO_OR.get(gs_val)
        )

    async def validate(self, user):
        logger.info(
            f"OtuMaintLoopbackTypeHandler:validate: type:{self.type}, change:{self.change}"
        )
        await super().validate(user)
        await super().validate_modules(user)
        cache = self.setup_cache(user)

        # check and store enabled leaf
        xpath = f"/org-openroadm-device:org-openroadm-device/interface[name='{self.ifname}']/otu/maint-loopback/enabled"
        self.enabled = libyang.xpath_get(cache, xpath)

        # check if OR value is translatable
        self.new_type = "unknown"
        if self.type in ["created", "modified"]:
            self.new_type = OtuMaintLoopbackTypeHandler.translate(
                or_val=self.change.value
            )
            if self.new_type == None:
                raise sysrepo.errors.SysrepoInvalArgError("invalid loopback type")

        # store original primitive value
        self.orig_loopback_type = libyang.xpath_get(
            self.module_data, "network-interface/config/loopback-type"
        )

    async def apply(self, user):
        logger.info(
            f"OtuMaintLoopbackTypeHandler:apply: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]

        if self.type in ["created", "modified"]:
            # other required leaves
            sess.set(
                GS_TRANSPONDER_MODULE_NAME.format(self.gsoper_name), self.gsoper_name
            )
            sess.set(
                GS_TRANSPONDER_NETIF_NAME.format(self.gsoper_name, self.gsoper_niname),
                self.gsoper_niname,
            )

            # set loopback-type
            if self.enabled:
                sess.set(
                    GS_TRANSPONDER_NETIF_LOOPBACK_TYPE.format(
                        self.gsoper_name, self.gsoper_niname
                    ),
                    self.new_type,
                )
            else:
                sess.set(
                    GS_TRANSPONDER_NETIF_LOOPBACK_TYPE.format(
                        self.gsoper_name, self.gsoper_niname
                    ),
                    "none",
                )
        else:
            if self.enabled:
                sess.delete(
                    GS_TRANSPONDER_NETIF_LOOPBACK_TYPE.format(
                        self.gsoper_name, self.gsoper_niname
                    )
                )
            else:
                sess.set(
                    GS_TRANSPONDER_NETIF_LOOPBACK_TYPE.format(
                        self.gsoper_name, self.gsoper_niname
                    ),
                    "none",
                )

    def revert(self, user):
        logger.warning(
            f"OtuMaintLoopbackTypeHandler:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        if self.orig_loopback_type:
            sess.set(
                GS_TRANSPONDER_NETIF_LOOPBACK_TYPE.format(
                    self.gsoper_name, self.gsoper_niname
                ),
                self.orig_loopback_type,
            )
        else:
            sess.delete(
                GS_TRANSPONDER_NETIF_LOOPBACK_TYPE.format(
                    self.gsoper_name, self.gsoper_niname
                )
            )


class EthFecHandler(IfChangeHandler):
    OR_TO_GS = {
        "org-openroadm-common-types:off": "none",
        "org-openroadm-common-types:rsfec": "rs",
        "org-openroadm-common-types:baser": "fc",
    }
    GS_TO_OR = dict((v, k) for k, v in OR_TO_GS.items())

    def translate(or_val=None, gs_val=None):
        """Translate between OpenROADM fec and Goldstone fec-type values.

        Args:
            or_val (str): OpenROADM fec value to convert, None if conversion type
            gs_val (str): Goldstone fec-type value to convert, None if conversion type

        Returns:
            Converted value.
        """
        assert not (or_val != None and gs_val != None)
        if or_val == None and gs_val == None:
            return None
        return (
            EthFecHandler.OR_TO_GS.get(or_val)
            if or_val != None
            else EthFecHandler.GS_TO_OR.get(gs_val)
        )

    async def validate(self, user):
        logger.info(f"EthFecHandler:validate: type:{self.type}, change:{self.change}")
        await super().validate(user)

        gs_piu, gs_port = self.server._translate_circuit_pack_name(
            self.server.or_port_map, self.or_cpname
        )
        module_data = self.server.get_operational_data(
            GS_TRANSPONDER_HOSTIF.format(gs_piu, gs_port)
        )
        if module_data == None:
            raise sysrepo.errors.SysrepoInvalArgError("missing goldstone module")

        gsoper_hiname = libyang.xpath_get(module_data, "name")
        if gsoper_hiname[0] == None:
            raise sysrepo.errors.SysrepoInvalArgError(
                "missing goldstone host interface name"
            )

        # check that the incoming fec value is sane (for changes)
        self.new_fec = "unknown"
        if self.type in ["created", "modified"]:
            self.new_fec = EthFecHandler.translate(or_val=self.change.value)
            if self.new_fec == None:
                raise sysrepo.errors.SysrepoInvalArgError("invalid ethernet fec")

        # Last is to store the existing fec to handle revert cases
        orig_fec = libyang.xpath_get(module_data, "config/fec-type")

        self.gsoper_hiname = gsoper_hiname[0]
        self.gs_piu = gs_piu
        if orig_fec:
            self.orig_fec = orig_fec[0]
        else:
            self.orig_fec = None

    def apply(self, user):
        logger.info(f"\n\nEthSpdHandler:apply: type:{self.type}, change:{self.change}")
        sess = user["sess"]["running"]
        if self.type in ["created", "modified"]:
            sess.set(GS_TRANSPONDER_MODULE_NAME.format(self.gs_piu), self.gs_piu)
            sess.set(
                GS_TRANSPONDER_HOSTIF_NAME.format(self.gs_piu, self.gsoper_hiname),
                self.gsoper_hiname,
            )
            sess.set(
                GS_TRANSPONDER_HOSTIF_FEC_TYPE.format(self.gs_piu, self.gsoper_hiname),
                self.new_fec,
            )
        else:
            # delete processing
            sess.delete(
                GS_TRANSPONDER_HOSTIF_FEC_TYPE.format(self.gs_piu, self.gsoper_hiname)
            )

    def revert(self, user):
        logger.warning(
            f"\n\nEthSpdHandler:revert: type:{self.type}, change:{self.change}"
        )
        sess = user["sess"]["running"]
        if self.orig_fec != None:
            sess.set(
                GS_TRANSPONDER_HOSTIF_FEC_TYPE.format(self.gs_piu, self.gsoper_hiname),
                self.orig_fec,
            )
        else:
            # no eth fec was set originally, so cleanup the host interface leaf
            sess.delete(
                GS_TRANSPONDER_HOSTIF_NAME.format(self.gs_piu, self.gsoper_hiname)
            )


class DeviceServer(OpenROADMServer):
    def __init__(
        self, conn, operational_modes, platform_info, reconciliation_interval=10
    ):
        super().__init__(conn, "org-openroadm-device", reconciliation_interval)
        self.handlers = {
            "org-openroadm-device": {
                "info": {
                    "node-id": NoOp,
                    "node-number": NoOp,
                    "node-type": NoOp,
                    "clli": NoOp,
                    "template": NoOp,
                    "lifecycle-state": NoOp,
                    "geoLocation": {"latitude": NoOp, "longitude": NoOp},
                },
                "shelves": {
                    "shelf-name": ShelfNameHandler,
                    "shelf-type": NoOp,
                    "rack": NoOp,
                    "shelf-position": NoOp,
                    "lifecycle-state": NoOp,
                    "administrative-state": NoOp,
                    "equipment-state": NoOp,
                    "user-description": NoOp,
                    "due-date": NoOp,
                },
                "circuit-packs": {
                    "circuit-pack-name": NoOp,
                    "circuit-pack-type": NoOp,
                    "circuit-pack-product-code": NoOp,
                    "third-party-pluggable": NoOp,
                    "circuit-pack-name": CircuitPackNameHandler,
                    "lifecycle-state": NoOp,
                    "administrative-state": NoOp,
                    "equipment-state": NoOp,
                    "circuit-pack-mode": NoOp,
                    "shelf": NoOp,
                    "slot": NoOp,
                    "subSlot": NoOp,
                    "user-description": NoOp,
                    "due-date": NoOp,
                    "parent-circuit-pack": {
                        "circuit-pack-name": NoOp,
                        "cp-slot-name": NoOp,
                    },
                    "ports": {
                        "port-name": PortNameHandler,
                        "port-type": NoOp,
                        "port-qual": NoOp,
                        "user-description": NoOp,
                        "lifecycle-state": NoOp,
                        "administrative-state": NoOp,
                    },
                    "parent-circuit-pack": {
                        "circuit-pack-name": NoOp,
                        "cp-slot-name": NoOp,
                    },
                },
                "interface": {
                    "name": NoOp,
                    "description": NoOp,
                    "type": NoOp,
                    "lifecycle-state": NoOp,
                    "administrative-state": NoOp,
                    "circuit-id": NoOp,
                    "supporting-circuit-pack-name": NoOp,
                    "supporting-port": NoOp,
                    "supporting-interface-list": NoOp,
                    "otsi": {
                        "provision-mode": NoOp,
                        "otsi-rate": OtsiRateHandler,
                        "frequency": FrequencyHandler,
                        "modulation-format": ModulationFormatHandler,
                        "transmit-power": TxPwrHandler,
                        "fec": FecHandler,
                        "optical-operational-mode": OpticalOperationalModeHandler,
                        "flexo": NoOp,
                        "foic-type": NoOp,
                        "iid": NoOp,
                    },
                    "otu": {
                        "rate": NoOp,
                        "otucn-n-rate": NoOp,
                        "tim-act-enabled": NoOp,
                        "tim-detect-mode": NoOp,
                        "degm-intervals": NoOp,
                        "degthr-percentage": NoOp,
                        "maint-loopback": {
                            "enabled": NoOp,  # handled by YANG restriction, will trigger change to 'type'
                            "type": OtuMaintLoopbackTypeHandler,
                        },
                    },
                    "odu": {
                        "rate": NoOp,
                        "oducn-n-rate": NoOp,
                        "tim-act-enabled": NoOp,
                        "tim-detect-mode": NoOp,
                        "degm-intervals": NoOp,
                        "degthr-percentage": NoOp,
                        "odu-function": NoOp,
                        "monitoring-mode": NoOp,
                        "maint-testsignal": NoOp,
                        "parent-odu-allocation": {
                            "trib-port-number": NoOp,
                            "opucn-trib-slots": NoOp,
                        },
                        "tx-sapi": NoOp,
                        "opu": {"payload-type": NoOp, "exp-payload-type": NoOp},
                    },
                    "ethernet": {
                        "speed": EthSpdHandler,
                        "fec": EthFecHandler,
                        "egress-consequent-action": NoOp,
                        "duplex": NoOp,
                        "auto-negotiation": NoOp,
                        "maint-testsignal": {"enabled": NoOp},
                        "maint-loopback": {"type": NoOp, "enabled": NoOp},
                    },
                    "otsi-group": {"group-rate": NoOp, "group-id": NoOp},
                },
                "odu-connection": {
                    "connection-name": NoOp,
                    "direction": NoOp,
                    "source": {"src-if": NoOp},
                    "destination": {"dst-if": NoOp},
                },
            }
        }

        or_port_map = {}
        for i in platform_info:
            if "openroadm" in i:
                assert "name" in i["openroadm"]
                or_port_name = i["openroadm"]["name"]
                pin_mode = i["interface"]["pin-mode"].upper()
                ifname = i["interface"]["name"]
                m = i["tai"]["module"]["name"]
                hi = i["tai"]["hostif"]["name"]
                or_port_map.setdefault(or_port_name, {})
                or_port_map[or_port_name] |= {pin_mode: (ifname, m, hi)}
        if not or_port_map:
            raise Exception(
                "port mapping information between openroadm and goldstone models is required for translation."
            )
        self.or_port_map = or_port_map
        self.operational_modes = operational_modes
        self.otsi_sup_cpname = {}
        self.components = self.get_operational_data(GS_PLATFORM_COMPONENTS_COMPONENT)
        module = self.conn.conn.get_module("org-openroadm-device")
        revisions = module.revisions()
        assert (next(revisions).description()) == f"Version {OPENROADM_VERSION}"

    def pre(self, user):
        super().pre(user)
        user["operational-modes"] = self.operational_modes

    def _oper_info(self, data):
        """Fetches and maps operational data for info container.

        Args:
            data (Dict): operational data from goldstone-platform primitive model.

        Returns:
            A dictionary representing the operational OpenROADM Device info container.
        """
        info = {"openroadm-version": OPENROADM_VERSION}

        # find and map 'SYS' component
        sys_comp = next(
            (comp for comp in data if comp.get("state", {}).get("type") == "SYS"), {}
        )
        onie_info = sys_comp.get("sys", {}).get("state", {}).get("onie-info", {})
        info["vendor"] = onie_info.get("vendor")
        info["model"] = onie_info.get("part-number")
        info["serial-id"] = onie_info.get("serial-number")

        return info

    def _oper_shelves(self, data):
        """Fetches and maps operational data for shelves container.

        Args:
            data (Dict): operational data from goldstone-platform primitive model.

        Returns:
            A list representing the operational OpenROADM Device shelves container.
        """
        shelves = []

        # find and map 'SYS' component
        sys_comp = next(
            (comp for comp in data if comp.get("state", {}).get("type") == "SYS"), {}
        )
        onie_info = sys_comp.get("sys", {}).get("state", {}).get("onie-info", {})
        sys_shelf = {
            "shelf-name": sys_comp.get("name"),
            "vendor": onie_info.get("vendor"),
            "model": onie_info.get("part-number"),
            "serial-id": onie_info.get("serial-number"),
            "operational-state": "inService",
            "is-physical": True,
            "is-passive": False,
            "faceplate-label": "none",
        }
        shelves.append(sys_shelf)

        return shelves

    def _oper_circuit_packs(self, data):
        """Fetches and maps operational data for circuit-packs container.
        Args:
            data (Dict): operational data from goldstone-platform primitive model.
        Returns:
            A list representing the operational OpenROADM Device circuit-packs container.
        """
        circuit_packs = []

        # map SYS circuit-pack
        sys_comp = next(
            (comp for comp in data if comp.get("state", {}).get("type") == "SYS"), {}
        )
        onie_info = sys_comp.get("sys", {}).get("state", {}).get("onie-info", {})
        base_pack = {
            "circuit-pack-name": sys_comp.get("name"),
            "vendor": onie_info.get("vendor"),
            "model": onie_info.get("part-number"),
            "serial-id": onie_info.get("serial-number"),
            "operational-state": "inService",
            "is-pluggable-optics": False,
            "is-physical": True,
            "is-passive": False,
            "faceplate-label": "none",
        }
        circuit_packs.append(base_pack)

        # map PSU circuit-packs
        psu_info = [comp for comp in data if comp.get("state", {}).get("type") == "PSU"]
        for psu_comp in psu_info:
            psu_pack = {
                "circuit-pack-name": psu_comp.get("name"),
                "model": psu_comp.get("psu", {}).get("state", {}).get("model"),
                "serial-id": psu_comp.get("psu", {}).get("state", {}).get("serial"),
            }
            circuit_packs.append(psu_pack)

        # map TRANSCEIVER circuit-packs
        transceiver_comps = [
            comp for comp in data if comp.get("state", {}).get("type") == "TRANSCEIVER"
        ]
        for t_comp in transceiver_comps:
            t_state = t_comp.get("transceiver", {}).get("state", {})
            pack = {
                "circuit-pack-name": t_comp.get("name"),
                "vendor": t_state.get("vendor"),
                "model": t_state.get("model"),
                "serial-id": t_state.get("serial"),
                "operational-state": "inService"
                if t_state.get("presence") == "PRESENT"
                else "outOfService",
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            circuit_packs.append(pack)

        # map PIU circuit-packs
        oper_enums = {
            "unknown": "degraded",
            "initialize": "outOfService",
            "ready": "inService",
        }
        piu_comps = [
            comp for comp in data if comp.get("state", {}).get("type") == "PIU"
        ]
        for piu_comp in piu_comps:
            name = piu_comp.get("name")
            modules = self.get_operational_data(
                f"/goldstone-transponder:modules/module[name='{name}']"
            )
            if not modules:
                continue
            module = modules[0]

            # Process the PIU info
            state_info = module.get("state", {})
            piu_pack = {
                "circuit-pack-name": module.get("name"),
                "vendor": state_info.get("vendor-name"),
                "model": state_info.get("vendor-part-number"),
                "serial-id": state_info.get("vendor-serial-number"),
                "is-pluggable-optics": True,
                "is-physical": True,
                "is-passive": False,
                "faceplate-label": "none",
            }
            val = oper_enums.get(state_info.get("oper-status"))
            if val:
                piu_pack["operational-state"] = val
            circuit_packs.append(piu_pack)

        # add static port info to user-provisioned circuit-packs
        circuit_packs_xpath = "/org-openroadm-device:org-openroadm-device/circuit-packs"
        running_cps = self.get_running_data(circuit_packs_xpath, [])
        existing_cps = set([cp["circuit-pack-name"] for cp in circuit_packs])

        for cp in running_cps:
            cp_name = cp["circuit-pack-name"]
            if cp_name not in existing_cps:
                continue
            ports = cp.get("ports", [])

            for running_port in ports:
                # find the corresponding operational circuit-pack and port
                oper_pack = next(
                    (
                        pack
                        for pack in circuit_packs
                        if pack["circuit-pack-name"] == cp_name
                    )
                )
                new_port = {"port-name": running_port["port-name"]}
                if "ports" not in oper_pack:
                    oper_pack["ports"] = []
                oper_pack["ports"].append(new_port)
                oper_port = new_port

                oper_port["port-direction"] = "bidirectional"
                oper_port["is-physical"] = True
                oper_port["faceplate-label"] = "none"
                oper_port["operational-state"] = "inService"

        return circuit_packs

    def _oper_interfaces(self):
        """Fetches and maps operational data for interface container.

        Returns:
            A list representing the operational OpenROADM Device interface container.
        """

        def isOdu(intf, running_intf):
            logger.debug(f"isOdu: name:{intf.get('name')}, type:{intf.get('type')}")
            if intf.get("type") == "org-openroadm-interfaces:otnOdu":
                sup_intf_name = next(
                    iter(intf.get("supporting-interface-list", [None]))
                )
                if sup_intf_name:
                    sup_intf = next(
                        (
                            intf
                            for intf in running_intf
                            if intf.get("name") == sup_intf_name
                        ),
                        None,
                    )
                    logger.debug(
                        f"isOdu: name:{intf.get('name')}, sup_intf_type:{sup_intf.get('type')}"
                    )
                    if sup_intf and sup_intf.get("type") in [
                        "org-openroadm-interfaces:otnOdu",
                        "org-openroadm-interfaces:ethernetCsmacd",
                    ]:
                        return True
            return False

        interfaces = []

        running_intfs = self.get_running_data(
            "/org-openroadm-device:org-openroadm-device/interface", []
        )
        for orif in running_intfs:
            name = orif.get("supporting-circuit-pack-name")
            if not name:
                continue

            # For handling interfaces, there are multiple types.
            # Check for the specific ones of interest, and handle accordingly
            if orif.get("type") == "org-openroadm-interfaces:otsi":
                modules = self.get_operational_data(
                    f"/goldstone-transponder:modules/module[name='{name}']"
                )
                if not modules:
                    continue
                assert len(modules) == 1
                module = modules[0]

                # store the supporting-circuit-pack-name for each otsi interface
                self.otsi_sup_cpname[orif["name"]] = name

                netifs = module.get("network-interface")
                if not netifs:
                    continue

                if len(netifs) > 0:
                    logger.warning(
                        "only supports module with one network interface, using the first one"
                    )
                netif = next(iter(netifs))

                config = netif.get("config")
                if not config:
                    continue
                val = {"name": orif["name"]}
                interfaces.append(val)

            elif orif.get("type") == "org-openroadm-interfaces:ethernetCsmacd":
                gs_piu, _ = self._translate_circuit_pack_name(self.or_port_map, name)
                modules = self.get_operational_data(
                    f"/goldstone-transponder:modules/module[name='{gs_piu}']"
                )
                if not modules:
                    continue
                assert len(modules) == 1
                module = modules[0]

                hostif = module.get("host-interface")
                if not hostif:
                    continue

                state = next(iter(hostif)).get("state")
                if not state:
                    continue

                val = {"name": orif["name"]}
                speed = EthSpdHandler.translate(gs_val=state.get("signal-rate"))
                val["org-openroadm-ethernet-interfaces:ethernet"] = {
                    "curr-speed": speed
                }
                interfaces.append(val)

        # Add static data to ODU interfaces
        odu_intfs = [intf for intf in running_intfs if isOdu(intf, running_intfs)]
        for intf in odu_intfs:
            oper_intf = {
                "name": intf.get("name"),
                "odu": {"no-oam-function": None, "no-maint-testsignal-function": None},
            }
            interfaces.append(oper_intf)
            logger.debug(
                f"_oper_interfaces: name:{intf.get('name')}, ODU static data added."
            )
        return interfaces

    def _oper_optical_profiles(self):
        """Fetches and maps operational data for optical-operational-mode-profile container.

        Returns:
            A list representing the operational OpenROADM Device optical-operational-mode-profile container.
        """

        optical_operational_mode_profile = []
        for mode in self.operational_modes:
            my_profile_name = mode.get("openroadm", {}).get("profile-name")
            if my_profile_name != None:
                logger.debug(f"_oper_optical_profiles: profile-name:{my_profile_name}")
                bookend_profile = {"profile-name": my_profile_name}
                optical_operational_mode_profile.append(bookend_profile)
        return optical_operational_mode_profile

    def oper_cb(self, xpath, priv):
        logger.debug(f"oper_cb: {xpath}")
        xpath = "/goldstone-platform:components/component"
        data = self.get_operational_data(xpath, [])
        return {
            "org-openroadm-device": {
                "info": self._oper_info(data),
                "shelves": self._oper_shelves(data),
                "circuit-packs": self._oper_circuit_packs(data),
                "interface": self._oper_interfaces(),
                "optical-operational-mode-profile": self._oper_optical_profiles(),
            }
        }
