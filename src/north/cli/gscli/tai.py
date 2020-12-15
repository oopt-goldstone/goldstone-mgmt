import re
import base64
import struct
import sysrepo as sr
from tabulate import tabulate
from .common import sysrepo_wrap, print_tabular
from .base import InvalidInput

_FREQ_RE = re.compile(r".+[kmgt]?hz$")


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
            multiplier = 1
            if item[-1] == "t":
                multiplier = 1e12
            elif item[-1] == "g":
                multiplier = 1e9
            elif item[-1] == "m":
                multiplier = 1e6
            elif item[-1] == "k":
                multiplier = 1e3
            return str(round(float(item[:-1]) * multiplier))
    else:
        return "{0:.2f}THz".format(int(item) / 1e12)


def human_ber(item):
    return "{0:.2e}".format(struct.unpack(">f", base64.b64decode(item))[0])


def to_human(d, runconf=False):
    for key in d:
        if key.endswith("ber"):
            d[key] = human_ber(d[key])
        elif "freq" in key:
            d[key] = human_freq(d[key])
        elif type(d[key]) == bool:
            d[key] = "true" if d[key] else "false"
        elif not runconf and key.endswith("power"):
            d[key] = f"{d[key]}dBm"

    return d


class Transponder(object):
    XPATH = "/goldstone-tai:modules/module"

    def xpath(self, transponder_name):
        return "{}[name='{}']".format(self.XPATH, transponder_name)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def show_transponder(self, transponder_name):
        if transponder_name not in self.get_modules():
            print(
                f"Enter the correct transponder name, {transponder_name} is not a valid transponder name"
            )
            return
        xpath = self.xpath(transponder_name)
        try:
            v = self.sr_op.get_data(xpath, "operational")
        except sr.SysrepoNotFoundError as e:
            print(e)
            return
        except sr.errors.SysrepoCallbackFailedError as e:
            print(e)
            return
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
                upd_net_interface = to_human(net_interface)
                print_tabular(upd_net_interface, f"Network Interface {netif}")
            for hostif in range(get_hostif_num):
                host_interface = v["modules"]["module"][transponder_name][
                    "host-interface"
                ][f"{hostif}"]["state"]
                print_tabular(host_interface, f"Host Interface {hostif}")
        except KeyError as e:
            print(f"Error while fetching values from operational database")
            return

    def show_transponder_summary(self):
        path = "/goldstone-tai:modules"
        d = self.sr_op.get_data(path, "operational", no_subs=True)
        modules = []
        for v in d.get("modules", {}).get("module", {}):
            modules.append(v["name"])
        state_data = []
        try:
            attrs = [
                "location",
                "vendor-name",
                "vendor-part-number",
                "vendor-serial-number",
                "admin-status",
                "oper-status",
            ]
            rows = []
            for module in modules:
                xpath = self.xpath(module)
                data = []
                for attr in attrs:
                    try:
                        v = self.sr_op.get_data(f"{xpath}/state/{attr}", "operational")
                        data.append(v["modules"]["module"][module]["state"][attr])
                    except (sr.SysrepoNotFoundError, KeyError) as e:
                        data.append("N/A")
                rows.append(data)

            # change "location" to "transponder" for the header use
            attrs[0] = "transponder"

            print(tabulate(rows, attrs, tablefmt="pretty", colalign="left"))
        except Exception as e:
            print(e)

    def run_conf(self):
        transponder_run_conf_list = ["admin-status"]
        netif_run_conf_list = [
            "output-power",
            "modulation-format",
            "tx-laser-freq",
            "voa-rx",
            "tx-dis",
            "differential-encoding",
        ]
        hostif_run_conf_list = ["fec-type"]

        try:
            tree = self.sr_op.get_data(self.XPATH)
        except sr.errors.SysrepoNotFoundError as e:
            print("!")
            return

        modules = list(tree.get("modules", {}).get("module", []))
        if len(modules) == 0:
            print("!")
            return

        for module in modules:
            print("transponder {}".format(module.get("name")))

            m = to_human(module.get("config", {}))
            for attr in transponder_run_conf_list:
                value = m.get(attr, None)
                if value:
                    if attr == "admin-status":
                        v = "shutdown" if value == "down" else "no shutdown"
                        print(f" {v}")
                    else:
                        print(f" {attr} {value}")

            for netif in module.get("network-interface", []):
                print(f" netif {netif['name']}")
                n = to_human(netif.get("config", {}), runconf=True)
                for attr in netif_run_conf_list:
                    value = n.get(attr, None)
                    if value:
                        print(f" {attr} {value}")
                print(" quit")

            for hostif in module.get("host-interface", []):
                print(f" hostif {hostif['name']}")
                n = to_human(hostif.get("config", {}), runconf=True)
                for attr in hostif_run_conf_list:
                    value = n.get(attr, None)
                    if value:
                        print(f" {attr} {value}")
                print(" quit")

            print("quit")

        print("!")

    def tech_support(self):
        print("\nshow transponder details:\n")
        modules = self.get_modules()
        for module in modules:
            self.show_transponder(module)

    def get_modules(self):
        path = "/goldstone-tai:modules"
        module_data = self.sr_op.get_data(path, "operational", no_subs=True)
        return [v["name"] for v in module_data.get("modules", {}).get("module", {})]
