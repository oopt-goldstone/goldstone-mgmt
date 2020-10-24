import sys
import os
import re
from tabulate import tabulate


import sysrepo as sr
import base64
import struct

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, FuzzyCompleter
from .common import sysrepo_wrap, print_tabular

from libyang.schema import iter_children
from _libyang import lib
import libyang


class HostIf(object):
    def xpath(self, transponder_name, hostif_id):
        return (
            "/goldstone-tai:modules/module[name='{}']/host-interface[name='{}']".format(
                transponder_name, hostif_id
            )
        )

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap()

    def set_fec_type(self, transponder_name, hostif_id, value):
        xpath = self.xpath(transponder_name, hostif_id)
        self.sr_op.set_data("{}/{}".format(xpath, "config/fec-type"), value)

    def no(self, transponder_name, hostif_id, attr):
        xpath = self.xpath(transponder_name, hostif_id)
        self.sr_op.delete_data("{}/{}".format(xpath, "config/{attr}"))

    def show(self, transponder_name, hostif_id):
        xpath = self.xpath(transponder_name, hostif_id)
        try:
            b = self.sr_op.get_data(xpath, "operational")
        except sr.SysrepoNotFoundError as e:
            print(e)
        try:
            h = b["modules"]["module"][transponder_name]["host-interface"][hostif_id][
                "state"
            ]
            print_tabular(h, "")
        except Exception as e:
            print(e)


class NetIf(object):
    def xpath(self, transponder_name, netif_id):
        return "/goldstone-tai:modules/module[name='{}']/network-interface[name='{}']".format(
            transponder_name, netif_id
        )

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap()

    def set_output_power(self, transponder_name, netif_id, value):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.set_data("{}/{}".format(xpath, "config/output-power"), value)

    def set_modulation_format(self, transponder_name, netif_id, value):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.set_data("{}/{}".format(xpath, "config/modulation-format"), value)

    def set_tx_laser_freq(self, transponder_name, netif_id, value):
        xpath = self.xpath(transponder_name, netif_id)
        freq_hz = human_freq(value)
        self.sr_op.set_data("{}/{}".format(xpath, "config/tx-laser-freq"), freq_hz)

    def set_tx_dis(self, transponder_name, netif_id, value):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.set_data("{}/{}".format(xpath, "config/tx-dis"), value)

    def set_differential_encoding(self, transponder_name, netif_id, value):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.set_data(
            "{}/{}".format(xpath, "config/differential-encoding"), value
        )

    def set_voa_rx(self, transponder_name, netif_id, value):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.set_data("{}/{}".format(xpath, "config/voa-rx"), value)

    # no command will delete the configuration data from the running database
    def set_no_command(self, transponder_name, netif_id, attr):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.delete_data("{}/{}".format(xpath, f"config/{attr}"), attr)

    def show(self, transponder_name, netif_id):
        xpath = self.xpath(transponder_name, netif_id)
        try:
            a = self.sr_op.get_data(xpath, "operational")
        except sr.SysrepoNotFoundError as e:
            print(e)
        try:
            n = a["modules"]["module"][transponder_name]["network-interface"][netif_id][
                "state"
            ]
            print_tabular(n, "")
        except Exception as e:
            print(e)


class Transponder(object):
    XPATH = "/goldstone-tai:modules/module"

    def xpath(self, transponder_name):
        return "{}[name='{}']".format(self.XPATH, transponder_name)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap()
        self.hostif = HostIf(conn)
        self.netif = NetIf(conn)

    def set_admin_status(self, transponder_name, value):
        xpath = self.xpath(transponder_name)
        self.sr_op.set_data(f"{xpath}/config/admin-status", value)

    def show_transponder(self, transponder_name):
        self.xpath = "{}[name='{}']".format(self.XPATH, transponder_name)
        try:
            v = self.sr_op.get_data(self.xpath, "operational")
        except sr.SysrepoNotFoundError as e:
            print(e)
        try:
            mod = v["modules"]["module"][transponder_name]["state"]
            print_tabular(mod, "")
            get_netif_num = v["modules"]["module"][transponder_name]["state"][
                "num-network-interfaces"
            ]
            get_hostif_num = v["modules"]["module"][transponder_name]["state"][
                "num-host-interfaces"
            ]
            for netif in range(get_netif_num):
                net_interface = v["modules"]["module"][transponder_name][
                    "network-interface"
                ][f"{netif}"]["state"]
                print_tabular(net_interface, f"Network Interface {netif}")
            for hostif in range(get_hostif_num):
                host_interface = v["modules"]["module"][transponder_name][
                    "host-interface"
                ][f"{hostif}"]["state"]
                print_tabular(host_interface, f"Host Interface {hostif}")
        except Exception as e:
            print(e)

    def show_transponder_summary(self):
        path = "/goldstone-tai:modules"
        d = self.sr_op.get_data(path, "operational", no_subs=True)
        modules = []
        for v in d.get("modules", {}).get("module", {}):
            modules.append(v["name"])
        state_data = []
        try:
            for module in modules:
                data_path = "{}[name='{}']".format(self.XPATH, module)
                mod_data = self.sr_op.get_data(f"{data_path}/state", "operational")
                state_data.append(mod_data["modules"]["module"][module]["state"])
            headers = [
                "transponder",
                "vendor-name",
                "vendor-part-name",
                "vendor-serial-number",
                "admin-status",
                "oper-status",
            ]
            rows = []
            for data in state_data:
                rows.append(
                    [
                        data["location"] if "location" in data.keys() else "N/A",
                        data["vendor-name"] if "vendor-name" in data.keys() else "N/A",
                        data["vendor-part-name"]
                        if "vendor-part-name" in data.keys()
                        else "N/A",
                        data["vendor-serial-number"]
                        if "vendor-serial-number" in data.keys()
                        else "N/A",
                        data["admin-status"]
                        if "admin-status" in data.keys()
                        else "N/A",
                        data["oper-status"] if "oper-status" in data.keys() else "N/A",
                    ]
                )
            print(tabulate(rows, headers, tablefmt="pretty", colalign="left"))
        except Exception as e:
            print(e)

    def _components(self, transponder_name, type_):

        d = self.sr_op.get_data(
            "{}[name='{}']".format(self.XPATH, transponder_name),
            "operational",
            no_subs=True,
        )
        d = d.get("modules", {}).get("module", {}).get(transponder_name, {})
        return [v["name"] for v in d.get(type_, [])]

    def get_modules(self):
        path = "/goldstone-tai:modules"
        d = self.sr_op.get_data(path, "operational", no_subs=True)
        return [v["name"] for v in d.get("modules", {}).get("module", {})]


def human_freq(item):
    if type(item) == str:
        try:
            int(item)
            return item
        except ValueError:
            item = item.lower()
            if not _FREQ_RE.match(item):
                raise InvalidInput("invalid frequency input. (e.g 193.50THz)")
            item = item[:-2]
            v = 1
            if item[-1] == "t":
                v = 1e12
            elif item[-1] == "g":
                v = 1e9
            elif item[-1] == "m":
                v = 1e6
            elif item[-1] == "k":
                v = 1e3
            return str(round(float(item[:-1]) * v))
    else:
        return "{0:.2f}THz".format(int(item) / 1e12)


def human_ber(item):
    return "{0:.2e}".format(struct.unpack(">f", base64.b64decode(item))[0])
