from .base import InvalidInput
from .common import sysrepo_wrap, print_tabular
import sysrepo as sr
import libyang as ly
import logging
from tabulate import tabulate
from natsort import natsorted
import re
import base64
import struct


logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

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
        if key.endswith("-ber"):
            d[key] = human_ber(d[key])
        elif "freq" in key:
            d[key] = human_freq(d[key])
        elif type(d[key]) == bool:
            d[key] = "true" if d[key] else "false"
        elif not runconf and key.endswith("power"):
            d[key] = f"{d[key]:.2f} dBm"
        elif type(d[key]) == ly.keyed_list.KeyedList:
            d[key] = ", ".join(d[key])

    return d


class Transponder(object):
    XPATH = "/goldstone-transponder:modules/module"

    def xpath(self, transponder_name):
        return "{}[name='{}']".format(self.XPATH, transponder_name)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def show_transponder(self, name):
        if name not in self.get_modules():
            stderr.info(
                f"Enter the correct transponder name. {name} is not a valid transponder name"
            )
            return
        xpath = self.xpath(name)
        try:
            v = self.sr_op.get_data(xpath, "operational")
        except (sr.SysrepoNotFoundError, sr.SysrepoCallbackFailedError) as e:
            stderr.info(e)
            return

        try:
            data = v["modules"]["module"][name]

            # module info
            print_tabular(data["state"])

            for netif in range(data["state"]["num-network-interfaces"]):
                d = data["network-interface"][str(netif)]["state"]
                print_tabular(to_human(d), f"Network Interface {netif}")

            for hostif in range(data["state"]["num-host-interfaces"]):
                d = data["host-interface"][str(hostif)]["state"]
                print_tabular(to_human(d), f"Host Interface {hostif}")

        except KeyError as e:
            stderr.info(f"Error while fetching values from operational database: {e}")
            return

    def show_transponder_summary(self):
        attrs = [
            "vendor-name",
            "vendor-part-number",
            "vendor-serial-number",
            "admin-status",
            "oper-status",
        ]
        rows = []
        for module in self.get_modules():
            prefix = self.xpath(module)
            data = [module]
            for attr in attrs:
                xpath = f"{prefix}/state/{attr}"
                try:
                    v = self.sr_op.get_data(xpath, "operational")
                    v = ly.xpath_get(v, xpath, "N/A")
                except (sr.SysrepoNotFoundError, sr.SysrepoCallbackFailedError):
                    v = "N/A"
                data.append(v)
            rows.append(data)

        # insert "transponder" for the header use
        attrs.insert(0, "transponder")

        stdout.info(tabulate(rows, attrs, tablefmt="pretty", colalign="left"))

    def run_conf(self):
        transponder_conf_blacklist = ["name"]
        netif_conf_blacklist = ["name"]
        hostif_conf_blacklist = ["name"]

        try:
            tree = self.sr_op.get_data(self.XPATH)
        except sr.errors.SysrepoNotFoundError as e:
            stdout.info("!")
            return

        modules = list(tree.get("modules", {}).get("module", []))
        if len(modules) == 0:
            stdout.info("!")
            return

        for module in modules:
            stdout.info("transponder {}".format(module.get("name")))

            m = to_human(module.get("config", {}))
            for k, v in m.items():
                if k in transponder_conf_blacklist:
                    continue
                stdout.info(f"  {k} {v}")

            for netif in module.get("network-interface", []):
                stdout.info(f"  netif {netif['name']}")
                n = to_human(netif.get("config", {}), runconf=True)
                for k, v in n.items():
                    if k in netif_conf_blacklist:
                        continue
                    stdout.info(f"    {k} {v}")
                stdout.info("    quit")

            for hostif in module.get("host-interface", []):
                stdout.info(f"  hostif {hostif['name']}")
                h = to_human(hostif.get("config", {}), runconf=True)
                for k, v in h.items():
                    if k in hostif_conf_blacklist:
                        continue
                    stdout.info(f"    {k} {v}")
                stdout.info("    quit")

            stdout.info("  quit")

        stdout.info("!")

    def tech_support(self):
        stdout.info("\nshow transponder details:\n")
        modules = self.get_modules()
        for module in modules:
            self.show_transponder(module)

    def get_modules(self):
        path = "/goldstone-transponder:modules/module/name"
        d = self.sr_op.get_data(path, "operational")
        return natsorted(v["name"] for v in d["modules"]["module"])
