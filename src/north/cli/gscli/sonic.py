import sys
import os

from tabulate import tabulate
import json
import sysrepo as sr
from .common import sysrepo_wrap, print_tabular

from prompt_toolkit.completion import WordCompleter


class Vlan(object):

    XPATH = "/sonic-vlan:sonic-vlan/VLAN"
    XPATHport = "/sonic-vlan:sonic-vlan/VLAN_MEMBER"

    def xpath_vlan(self, vid):
        return "{}/VLAN_LIST[name='{}']".format(self.XPATH, "Vlan" + vid)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap()
        self.tree = self.sr_op.get_data_ly("{}".format(self.XPATH), "operational")
        self.treeport = self.sr_op.get_data_ly(
            "{}".format(self.XPATHport), "operational"
        )
        try:
            self._vlan_map = json.loads(self.tree.print_mem("json"))[
                "sonic-vlan:sonic-vlan"
            ]["VLAN"]["VLAN_LIST"]
        except KeyError as error:
            pass

    def show_vlan(self, details="details"):
        self.tree = self.sr_op.get_data_ly("{}".format(self.XPATH), "running")
        self.treeport = self.sr_op.get_data_ly("{}".format(self.XPATHport), "running")
        dl1 = self.tree.print_mem("json")
        dl2 = self.treeport.print_mem("json")
        try:
            dl1 = json.loads(dl1)
            dl2 = json.loads(dl2)
        except KeyError as error:
            pass

        if dl1 == {}:
            print(tabulate([], ["VLAN ID", "Port", "Port Tagging"], tablefmt="pretty"))
        else:
            try:
                dl1 = dl1["sonic-vlan:sonic-vlan"]["VLAN"]["VLAN_LIST"]
                dl2 = dl2["sonic-vlan:sonic-vlan"]["VLAN_MEMBER"]["VLAN_MEMBER_LIST"]
            except KeyError as error:
                pass
            dln = []
            for i in range(len(dl1)):
                if "members" in dl1[i]:
                    for j in range(len(dl1[i]["members"])):
                        tg = ""
                        for k in range(len(dl2)):
                            if (
                                dl2[k]["name"] == dl1[i]["name"]
                                and dl2[k]["ifname"] == dl1[i]["members"][j]
                            ):
                                tg = dl2[k]["tagging_mode"]
                                break
                        dln.append([dl1[i]["vlanid"], dl1[i]["members"][j], tg])
                else:
                    dln.append([dl1[i]["vlanid"], "-", "-"])
            print(tabulate(dln, ["VLAN ID", "Port", "Port Tagging"], tablefmt="pretty"))
        self.session.switch_datastore("running")

    def _vlan_components(self):
        d = self._vlan_map
        return [str(v["vlanid"]) for v in d]

    def set_name(self, vlan_name):
        vid = vlan_name[4:]
        try:
            self.sr_op.set_data("{}/name".format(self.xpath_vlan(vid)), vlan_name)
        except sr.errors.SysrepoValidationFailedError as error:
            msg = str(error)
            print(msg)

    def create_vlan(self, vid):
        try:
            data_tree = self.session.get_data_ly(self.XPATH)
            vlan_map = json.loads(data_tree.print_mem("json"))["sonic-vlan:sonic-vlan"][
                "VLAN"
            ]["VLAN_LIST"]
        except sr.errors.SysrepoNotFoundError as error:
            msg = str(error)
            print(msg.split("(")[0])
            return
        except KeyError as error:
            print("key missing :{}".format(str(error)))
            return
        vlan_name = "Vlan" + vid
        if vlan_name in vlan_map:
            pass
        else:
            self.sr_op.set_data("{}/vlanid".format(self.xpath_vlan(vid)), vid)

    def delete_vlan(self, vid):
        vlan_name = "Vlan" + vid
        self.sr_op.delete_data(self.xpath_vlan(vid))

    def show(self, vid):
        xpath = self.xpath_vlan(vid)
        tree = self.sr_op.get_data(xpath)
        data = [v for v in list((tree)["sonic-vlan"]["VLAN"]["VLAN_LIST"])][0]
        if "members" in data:
            mem_delim = ","
            mem_delim = mem_delim.join(data["members"])
            data["members"] = mem_delim
        else:
            data["members"] = "-"
        print_tabular(data, "")


class Port(object):

    XPATH = "/sonic-port:sonic-port/PORT/PORT_LIST"

    def xpath(self, ifname):
        self.path = self.XPATH
        return "{}[ifname='{}']".format(self.path, ifname)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap()
        self._ifname_map = []
        try:
            self.tree = self.sr_op.get_data(self.XPATH, "operational")
            self._ifname_map = list(self.tree["sonic-port"]["PORT"]["PORT_LIST"])
        except KeyError as error:
            print("Port list is not configured")
        except sr.errors.SysrepoNotFoundError as error:
            print("sonic-mgmt is down")

    def show_interface(self, details="description"):
        # TODO:switch to operational when sonic_south is fixed
        try:
            self.tree = self.sr_op.get_data(self.XPATH)
            self._ifname_map = list(self.tree["sonic-port"]["PORT"]["PORT_LIST"])
        except KeyError as error:
            print("Port list is not configured")
        except sr.errors.SysrepoNotFoundError as error:
            print("sonic-mgmt is down")
        rows = []
        if details == "brief":
            headers = ["ifname", "oper_status", "admin_status", "alias"]
            for data in self._ifname_map:
                rows.append(
                    [
                        data["ifname"],
                        data["oper_status"] if "oper_status" in data.keys() else "-",
                        data["admin_status"] if "admin_status" in data.keys() else "-",
                        data["alias"],
                    ]
                )
            print(tabulate(rows, headers, tablefmt="pretty"))
        elif details == "description":
            headers = ["ifname", "oper_status", "admin_status", "alias", "speed", "mtu"]
            for data in self._ifname_map:
                rows.append(
                    [
                        data["ifname"],
                        data["oper_status"] if "oper_status" in data.keys() else "-",
                        data["admin_status"] if "admin_status" in data.keys() else "-",
                        data["alias"],
                        data["speed"] if "speed" in data.keys() else "-",
                        data["mtu"] if "mtu" in data.keys() else "-",
                    ]
                )
            print(tabulate(rows, headers, tablefmt="pretty"))

    def run_conf(self):
        runn_conf_list = ["admin_status", "mtu", "speed"]
        tree = self.sr_op.get_data("{}".format(self.XPATH))
        v_dict = {}
        d_list = list((tree)["sonic-port"]["PORT"]["PORT_LIST"])
        print("!")
        for data in d_list:
            print("interface {}".format(data.get("ifname")))
            for v in runn_conf_list:
                v_dict = {v: data.get(v, None) for v in runn_conf_list}
                if v == "admin_status":
                    if v_dict["admin_status"] == "down":
                        print("  shutdown ")
                    elif v_dict["admin_status"] == None:
                        pass

                elif v == "mtu":
                    if (v_dict["mtu"] == 9100) or (v_dict["mtu"] == None):
                        pass
                    else:
                        print("  {} {}".format(v, v_dict[v]))

                elif v == "speed":
                    if (v_dict["speed"] == 100000) or (v_dict["speed"] == None):
                        pass
                    else:
                        print("  {} {}".format(v, v_dict[v]))

            print("  quit")
        print("!")

    def _ifname_components(self):
        d = self._ifname_map
        return [v["ifname"] for v in d]

    def set_admin_status(self, ifname, value):
        xpath = self.xpath(ifname)
        self.sr_op.set_data("{}/{}".format(xpath, "admin_status"), value)

    def set_mtu(self, ifname, value):
        xpath = self.xpath(ifname)
        self.sr_op.set_data("{}/{}".format(xpath, "mtu"), value)

    def set_speed(self, ifname, value):
        xpath = self.xpath(ifname)
        self.sr_op.set_data("{}/{}".format(xpath, "speed"), value)

    def show(self, ifname):
        xpath = self.xpath(ifname)
        tree = self.sr_op.get_data(xpath)
        data = [v for v in list((tree)["sonic-port"]["PORT"]["PORT_LIST"])][0]
        print_tabular(data, "")


class Sonic(object):
    def __init__(self, conn):
        self.session = conn.start_session()
        self.port = Port(conn, self)
        self.vlan = Vlan(conn, self)

    def port_run_conf(self):
        self.port.run_conf()

    def vlan_run_conf(self):
        print("To Be Implemented")
        pass

    def run_conf(self):
        self.port_run_conf()

    def tech_support(self):
        print("\nshow vlan details:\n")
        self.vlan.show_vlan()
        print("\nshow interface description:\n")
        self.port.show_interface()
