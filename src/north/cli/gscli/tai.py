import re
import base64
import struct
import sysrepo as sr
from tabulate import tabulate
from .common import sysrepo_wrap, print_tabular
from .base import InvalidInput


class HostIf(object):
    def xpath(self, transponder_name, hostif_id):
        return (
            "/goldstone-tai:modules/module[name='{}']/host-interface[name='{}']".format(
                transponder_name, hostif_id
            )
        )

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.type = "host-interface"

    def set_fec_type(self, transponder_name, hostif_id, value):
        set_attribute(
            self.sr_op, self.type, transponder_name, hostif_id, "fec-type", value
        )

    def no(self, transponder_name, hostif_id, attr):
        xpath = self.xpath(transponder_name, hostif_id)
        self.sr_op.delete_data(f"{xpath}/config/{attr}")

    def show(self, transponder_name, hostif_id):
        xpath = self.xpath(transponder_name, hostif_id)
        try:
            b = self.sr_op.get_data(xpath, "operational")
        except sr.SysrepoNotFoundError as e:
            print("Not able to fetch data from operational database")
            return
        try:
            h = b["modules"]["module"][transponder_name]["host-interface"][hostif_id][
                "state"
            ]
            print_tabular(h, "")
        except KeyError as e:
            print(f"Error while fetching values from operational database")
            return


class NetIf(object):
    def xpath(self, transponder_name, netif_id):
        return "/goldstone-tai:modules/module[name='{}']/network-interface[name='{}']".format(
            transponder_name, netif_id
        )

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.type = "network-interface"

    def set_output_power(self, transponder_name, netif_id, value):
        set_attribute(
            self.sr_op, self.type, transponder_name, netif_id, "output-power", value
        )

    def set_modulation_format(self, transponder_name, netif_id, value):
        set_attribute(
            self.sr_op,
            self.type,
            transponder_name,
            netif_id,
            "modulation-format",
            value,
        )

    def set_tx_laser_freq(self, transponder_name, netif_id, value):
        freq_hz = human_freq(value)
        set_attribute(
            self.sr_op, self.type, transponder_name, netif_id, "tx-laser-freq", freq_hz
        )

    def set_tx_dis(self, transponder_name, netif_id, value):
        set_attribute(
            self.sr_op, self.type, transponder_name, netif_id, "tx-dis", value
        )

    def set_differential_encoding(self, transponder_name, netif_id, value):
        set_attribute(
            self.sr_op,
            self.type,
            transponder_name,
            netif_id,
            "differential-encoding",
            value,
        )

    def set_voa_rx(self, transponder_name, netif_id, value):
        set_attribute(
            self.sr_op, self.type, transponder_name, netif_id, "voa-rx", value
        )

    # no command will delete the configuration data from the running database
    def set_no_command(self, transponder_name, netif_id, attr):
        xpath = self.xpath(transponder_name, netif_id)
        self.sr_op.delete_data(f"{xpath}/config/{attr}")

    def show(self, transponder_name, netif_id):
        xpath = self.xpath(transponder_name, netif_id)
        try:
            a = self.sr_op.get_data(xpath, "operational")
        except sr.SysrepoNotFoundError as e:
            print(f"Error while fetching values from operational database")
            return
        try:
            n = a["modules"]["module"][transponder_name]["network-interface"][netif_id][
                "state"
            ]
            upd_netif = ber_decode(n)
            print_tabular(upd_netif, "")
        except KeyError as e:
            print(f"Error while fetching values from operational database")
            return


class Transponder(object):
    XPATH = "/goldstone-tai:modules/module"

    def xpath(self, transponder_name):
        return "{}[name='{}']".format(self.XPATH, transponder_name)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.hostif = HostIf(conn)
        self.netif = NetIf(conn)
        self.type = "module"

    def set_admin_status(self, transponder_name, value):
        set_attribute(
            self.sr_op, self.type, transponder_name, "Unknown", "admin-status", value
        )

    def show_transponder(self, transponder_name):
        if transponder_name not in self.get_modules():
            print(
                f"Enter the correct transponder name, {transponder_name} is not a valid transponder name"
            )
            return
        self.xpath = "{}[name='{}']".format(self.XPATH, transponder_name)
        try:
            v = self.sr_op.get_data(self.xpath, "operational")
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
                upd_net_interface = ber_decode(net_interface)
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
            tree = self.sr_op.get_data("{}".format(self.XPATH))
        except sr.errors.SysrepoNotFoundError as e:
            print(e)
            return
        t_dict = {}
        n_dict = {}
        h_dict = {}
        try:
            data_list = list((tree)["modules"]["module"])
        except Exception as e:
            print(f"No key named {e} found in the running database")
            return
        print("!")
        for data in data_list:
            module_data = data.get("config")
            print("transponder {}".format(data.get("name")))
            for attr in transponder_run_conf_list:
                t_dict = {
                    attr: module_data.get(attr, None)
                    for attr in transponder_run_conf_list
                }
                if attr == "admin-status":
                    if t_dict["admin-status"] is None:
                        pass
                    elif t_dict["admin-status"] == "down":
                        print(" shutdown ")
                    else:
                        print(" no shutdown ")
            try:
                netif_data = data["network-interface"]
            except KeyError as e:
                print(f"No key named {e} found in the running database")
                return
            for netif in netif_data:
                print("\nnetif {}\n".format(netif.get("name")))
                net_interface = netif.get("config")
                for attr in netif_run_conf_list:
                    n_dict = {
                        attr: net_interface.get(attr, None)
                        for attr in netif_run_conf_list
                    }
                for key in n_dict:
                    if (key == "tx-dis") or (key == "differential-encoding"):
                        if n_dict[key] == True:
                            print(f" {key} ")
                        elif n_dict[key] == False:
                            print(f" no {key} ")
                        else:
                            pass
                    else:
                        if n_dict[key] is None:
                            pass
                        else:
                            print(" {} {}".format(key, n_dict[key]))
            try:
                hostif_data = data["host-interface"]
            except KeyError as e:
                print(f"No key named {e} found in the running database")
                return
            for hostif in hostif_data:
                print("\nhostif {} \n".format(hostif.get("name")))
                host_interface = hostif.get("config")
                for attr in hostif_run_conf_list:
                    h_dict = {
                        attr: host_interface.get(attr, None)
                        for attr in hostif_run_conf_list
                    }
                    if attr == "fec-type":
                        if h_dict["fec-type"] is None:
                            pass
                        else:
                            print(" {} {}".format(attr, h_dict[attr]))
            print("quit")
        print("!")

    def tech_support(self):
        print("\nshow transponder details:\n")
        modules = self.get_modules()
        for module in modules:
            self.show_transponder(module)

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
        module_data = self.sr_op.get_data(path, "operational", no_subs=True)
        return [v["name"] for v in module_data.get("modules", {}).get("module", {})]


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


def ber_decode(netif_dict):
    upd_dict = netif_dict
    for key in upd_dict:
        if key[-3:] == "ber":
            upd_dict[key] = human_ber(upd_dict[key])
    return upd_dict


def human_ber(item):
    return "{0:.2e}".format(struct.unpack(">f", base64.b64decode(item))[0])


_FREQ_RE = re.compile(r".+[kmgt]?hz$")


def set_attribute(sr_op, type, trans_name, intf_id, attr, value):
    trans_xpath = "/goldstone-tai:modules/module[name='{}']".format(trans_name)
    try:
        sr_op.get_data(trans_xpath, "running")
    except sr.SysrepoNotFoundError as e:
        sr_op.set_data(f"{trans_xpath}/config/name", trans_name)

    if type == "network-interface" or type == "host-interface":
        xpath = "{}/{}[name='{}']".format(trans_xpath, type, intf_id)

        try:
            sr_op.get_data(xpath, "running")
        except sr.SysrepoNotFoundError as e:
            sr_op.set_data(f"{xpath}/config/name", intf_id)
        sr_op.set_data(f"{xpath}/config/{attr}", value)
    elif type == "module":
        sr_op.set_data(f"{trans_xpath}/config/{attr}", value)
