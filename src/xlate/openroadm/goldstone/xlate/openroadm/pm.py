import asyncio
import base64
import logging
import struct

import libyang
from goldstone.lib.core import *
from .lib import OpenROADMServer

logger = logging.getLogger(__name__)


class PMServer(OpenROADMServer):
    def __init__(self, conn, reconciliation_interval=10):
        super().__init__(conn, "org-openroadm-pm", reconciliation_interval)

    def _oper_current_pm_list(self, transponder_data, device_data):
        """Fetches and maps operational data for current-pm-list container.

        Args:
            transponder_data (Dict): operational data from goldstone-transponder primitive model.
            device_data (Dict): operational data from openroadm-device model.

        Returns:
            A dictionary containing the list representing the operational OpenROADM PM current-pm-list container.
        """

        def find_otsi(module_name, device_data):
            """Finds corresponding otsi interface for goldstone-transponder module in OpenROADM hierarchy."""
            intfs = libyang.xpath_get(device_data, f"/org-openroadm-device/interface")
            for i in intfs:
                if (
                    i.get("type") == "org-openroadm-interfaces:otsi"
                    and i.get("supporting-circuit-pack-name") == module_name
                ):
                    name = i.get("name")
                    return f"/org-openroadm-device:org-openroadm-device/interface[name='{name}']"
            return None

        def find_port(module_name, device_data):
            """Finds corresponding port for goldstone-transponder module in OpenROADM hierarchy."""
            otsi = find_otsi(module_name, device_data)
            otsi_name = libyang.xpath_get(device_data, f"{otsi}/name")
            cp_name = libyang.xpath_get(
                device_data,
                f"/org-openroadm-device/interface[name='{otsi_name}']/supporting-circuit-pack-name",
            )
            port_name = libyang.xpath_get(
                device_data,
                f"/org-openroadm-device/interface[name='{otsi_name}']/supporting-port",
            )
            return f"/org-openroadm-device:org-openroadm-device/circuit-packs[circuit-pack-name='{cp_name}']/ports[port-name='{port_name}']"

        current_pm_list = []

        # fetch PIU PMs
        for module in transponder_data:
            name = module.get("name")

            intf_resource_inst = find_otsi(name, device_data)
            port_resource_inst = find_port(name, device_data)

            # fetch pm values from goldstone-transponder
            if len(module.get("network-interface")) > 1:
                logger.warning(
                    "only supports module with one network interface, using the first one"
                )
            state = next(iter(module.get("network-interface"))).get("state", {})
            current_output_power = state.get("current-output-power")
            current_input_power = state.get("current-input-power")
            current_pre_fec_ber = state.get("current-pre-fec-ber")

            # add pms to current-pm-list
            if current_output_power != None and port_resource_inst != None:
                pm = {
                    "pm-resource-instance": port_resource_inst,
                    "pm-resource-type": "port",
                    "pm-resource-type-extension": "",
                    "current-pm": [
                        {
                            "type": "opticalPowerOutput",
                            "extension": "",
                            "location": "nearEnd",
                            "direction": "tx",
                            "measurement": [
                                {
                                    "granularity": "notApplicable",
                                    "pmParameterValue": current_output_power,
                                }
                            ],
                        }
                    ],
                }
                current_pm_list.append(pm)

            if current_input_power != None and port_resource_inst != None:
                pm = {
                    "pm-resource-instance": port_resource_inst,
                    "pm-resource-type": "port",
                    "pm-resource-type-extension": "",
                    "current-pm": [
                        {
                            "type": "opticalPowerInput",
                            "extension": "",
                            "location": "nearEnd",
                            "direction": "rx",
                            "measurement": [
                                {
                                    "granularity": "notApplicable",
                                    "pmParameterValue": current_input_power,
                                }
                            ],
                        }
                    ],
                }
                current_pm_list.append(pm)

            if current_pre_fec_ber != None and intf_resource_inst != None:
                ber = round(
                    struct.unpack(">f", base64.b64decode(current_pre_fec_ber))[0], 17
                )
                ber = format(ber, ".17f")
                pm = {
                    "pm-resource-instance": intf_resource_inst,
                    "pm-resource-type": "interface",
                    "pm-resource-type-extension": "",
                    "current-pm": [
                        {
                            "type": "preFECbitErrorRate",
                            "extension": "",
                            "location": "nearEnd",
                            "direction": "rx",
                            "measurement": [
                                {
                                    "granularity": "notApplicable",
                                    "pmParameterValue": ber,
                                }
                            ],
                        }
                    ],
                }
                current_pm_list.append(pm)
        return {"current-pm-entry": current_pm_list}

    def oper_cb(self, xpath, priv):
        logger.debug(f"oper_cb: {xpath}")
        transponder_data = self.get_operational_data(
            "/goldstone-transponder:modules/module", []
        )
        device_data = self.get_running_data(
            "/org-openroadm-device:org-openroadm-device", strip=False
        )

        return {
            "current-pm-list": self._oper_current_pm_list(transponder_data, device_data)
        }
