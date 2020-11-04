import sys
import os

from tabulate import tabulate
import json
import sysrepo as sr
from .common import sysrepo_wrap, print_tabular

from prompt_toolkit.completion import WordCompleter
from .base import InvalidInput

from natsort import natsorted

import logging

logger = logging.getLogger(__name__)


class Vlan(object):

    XPATH = "/goldstone-vlan:vlan/VLAN"
    XPATHport = "/goldstone-vlan:vlan/VLAN_MEMBER"

    def xpath_vlan(self, vid):
        return "{}/VLAN_LIST[name='{}']".format(self.XPATH, "Vlan" + vid)

    def xpath_mem(self, vid):
        return "{}/VLAN_MEMBER_LIST[name='{}']".format(self.XPATHport, "Vlan" + vid)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.tree = self.sr_op.get_data_ly("{}".format(self.XPATH), "operational")
        self.treeport = self.sr_op.get_data_ly(
            "{}".format(self.XPATHport), "operational"
        )
        try:
            self._vlan_map = json.loads(self.tree.print_mem("json"))[
                "goldstone-vlan:vlan"
            ]["VLAN"]["VLAN_LIST"]
        except KeyError as error:
            pass

    def show_vlan(self, details="details"):
        self.tree = self.sr_op.get_data_ly("{}".format(self.XPATH), "operational")
        self.treeport = self.sr_op.get_data_ly(
            "{}".format(self.XPATHport), "operational"
        )
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
                dl1 = dl1["goldstone-vlan:vlan"]["VLAN"]["VLAN_LIST"]
                dl2 = dl2["goldstone-vlan:vlan"]["VLAN_MEMBER"]["VLAN_MEMBER_LIST"]
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
        vlan_name = "Vlan" + vid
        try:
            data_tree = self.session.get_data_ly(self.XPATH)
            vlan_map = json.loads(data_tree.print_mem("json"))["goldstone-vlan:vlan"][
                "VLAN"
            ]["VLAN_LIST"]
        except (sr.errors.SysrepoNotFoundError, KeyError) as error:
            logger.warning(error)
        else:
            if vlan_name in vlan_map:
                return
        self.sr_op.set_data("{}/vlanid".format(self.xpath_vlan(vid)), vid)

    def delete_vlan(self, vid):
        vlan_name = "Vlan" + vid
        try:
            mem_dict = self.sr_op.get_data("{}/members".format(self.xpath_vlan(vid)))
            mem_dict = list(mem_dict["vlan"]["VLAN"]["VLAN_LIST"])[0]
            mem_list = mem_dict["members"]
        except sr.errors.SysrepoNotFoundError as error:
            self.sr_op.delete_data(self.xpath_vlan(vid))
            return
        for member in mem_list:
            self.sr_op.delete_data(
                "{}[ifname='{}']".format(self.xpath_mem(vid), member)
            )

        self.sr_op.delete_data("{}/{}".format(self.xpath_vlan(vid), "members"))
        self.sr_op.delete_data(self.xpath_vlan(vid))

    def show(self, vid):
        xpath = self.xpath_vlan(vid)
        tree = self.sr_op.get_data(xpath, "operational")
        data = [v for v in list((tree)["vlan"]["VLAN"]["VLAN_LIST"])][0]
        if "members" in data:
            mem_delim = ","
            mem_delim = mem_delim.join(data["members"])
            data["members"] = mem_delim
        else:
            data["members"] = "-"
        print_tabular(data, "")

    def run_conf(self):
        try:
            self.tree = self.sr_op.get_data(
                "{}/VLAN_LIST".format(self.XPATH), "running"
            )
            d_list = self.tree["vlan"]["VLAN"]["VLAN_LIST"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return
        for data in d_list:
            print("vlan {}".format(data["vlanid"]))
            print("  quit")
        print("!")


class Port(object):

    XPATH = "/goldstone-interfaces:interfaces/interface"

    def xpath(self, ifname):
        self.path = self.XPATH
        return "{}[name='{}']".format(self.path, ifname)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def get_interface_list(self):
        try:
            tree = self.sr_op.get_data(self.XPATH, "operational")
            return natsorted(tree["interfaces"]["interface"], key=lambda x: x["name"])
        except KeyError as error:
            logger.warning("interface list is not configured")
        except sr.errors.SysrepoNotFoundError as error:
            logger.warning("sonic-mgmt is down")
        return []

    def show_interface(self, details="description"):
        rows = []
        for intf in self.get_interface_list():
            row = [
                intf["name"],
                intf.get("oper-status", "-"),
                intf.get("admin-status", "-"),
                intf.get("alias", "-"),
            ]
            if details == "description":
                row += [intf.get("speed", "-"), intf.get("ipv4", {}).get("mtu", "-")]

            rows.append(row)

        if details == "brief":
            headers = ["name", "oper-status", "admin-status", "alias"]
        elif details == "description":
            headers = ["name", "oper-status", "admin-status", "alias", "speed", "mtu"]
        else:
            raise InvalidInput(f"unsupported format: {details}")

        print(tabulate(rows, headers, tablefmt="pretty"))

    def run_conf(self):
        xpath_vlan = "/goldstone-vlan:vlan/VLAN_MEMBER"

        runn_conf_list = ["admin-status", "mtu", "speed", "name"]
        v_dict = {}

        interface_list = self.get_interface_list()
        if not interface_list:
            return

        for data in interface_list:
            print("interface {}".format(data.get("name")))
            for v in runn_conf_list:
                v_dict = {v: data.get(v, None) for v in runn_conf_list}
                if v == "admin-status":
                    if v_dict["admin-status"] == "down":
                        print("  shutdown ")
                    elif v_dict["admin-status"] == None:
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

                elif v == "name":
                    try:
                        vlan_tree = self.sr_op.get_data_ly(
                            "{}".format(xpath_vlan), "running"
                        )
                        vlan_memlist = json.loads(vlan_tree.print_mem("json"))
                        vlan_memlist = vlan_memlist["goldstone-vlan:vlan"][
                            "VLAN_MEMBER"
                        ]["VLAN_MEMBER_LIST"]
                    except (sr.errors.SysrepoNotFoundError, KeyError):
                        # No vlan configrations is a valid case
                        continue

                    for vlan in range(len(vlan_memlist)):
                        if vlan_memlist[vlan]["ifname"] == v_dict["name"]:
                            vlanId = (vlan_memlist[vlan]["name"]).split("Vlan", 1)[1]
                            if vlan_memlist[vlan]["tagging_mode"] == "tagged":
                                print(
                                    "  switchport mode trunk vlan {}".format(
                                        str(vlanId)
                                    )
                                )
                            else:
                                print(
                                    "  switchport mode access vlan {}".format(
                                        str(vlanId)
                                    )
                                )

            print("  quit")
        print("!")

    def _ifname_components(self):
        d = self._ifname_map
        return [v["name"] for v in d]

    def set_admin_status(self, ifname, value):
        xpath = self.xpath(ifname)
        set_attribute(self.sr_op, xpath, "interface", ifname, "admin-status", value)

    def set_mtu(self, ifname, value):
        xpath = self.xpath(ifname)
        set_attribute(self.sr_op, xpath, "interface", ifname, "mtu", value)

    def set_speed(self, ifname, value):
        xpath = self.xpath(ifname)
        set_attribute(self.sr_op, xpath, "interface", ifname, "speed", value)

    def set_vlan_mem(self, ifname, mode, vid, no=False):
        xpath_mem_list = "/goldstone-vlan:vlan/VLAN/VLAN_LIST"
        xpath_mem_mode = "/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST"

        xpath_mem_list = xpath_mem_list + "[name='{}']".format("Vlan" + vid)
        xpath_mem_mode = xpath_mem_mode + "[name='{}'][ifname='{}']".format(
            "Vlan" + vid, ifname
        )
        vlan_name = "Vlan" + vid

        # in order to create the interface node if it doesn't exist in running DS
        try:
            self.sr_op.get_data(self.xpath(ifname), "running")

        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data("{}/admin-status".format(self.xpath(ifname)), "down")

        if no == False:
            set_attribute(
                self.sr_op, xpath_mem_list, "vlan", vlan_name, "members", ifname
            )
        else:
            mem_list = self.sr_op.get_leaf_data(xpath_mem_list, "members")
            if ifname in mem_list:
                self.sr_op.delete_data("{}/{}".format(xpath_mem_list, "members"))
                self.sr_op.delete_data("{}".format(xpath_mem_mode))
                mem_list.remove(ifname)
                # Since we dont have utiity function in sysrepo to delete one node in
                # leaf-list , we are deleting 'members' with old data and creating again
                # with new data.
                if len(mem_list) > 1:
                    set_attribute(
                        self.sr_op,
                        xpath_mem_list,
                        "vlan",
                        vlan_name,
                        "members",
                        mem_list,
                    )

        if mode == "trunk":
            set_attribute(
                self.sr_op, xpath_mem_mode, "vlan", vlan_name, "tagging_mode", "tagged"
            )
        elif mode == "access":
            set_attribute(
                self.sr_op,
                xpath_mem_mode,
                "vlan",
                vlan_name,
                "tagging_mode",
                "untagged",
            )

    def show(self, ifname):
        xpath = self.xpath(ifname)
        tree = self.sr_op.get_data(xpath, "operational")
        data = [v for v in list((tree)["interfaces"]["interface"])][0]
        if "ipv4" in data:
            mtu_dict = data["ipv4"]
            data["mtu"] = mtu_dict["mtu"]
            del data["ipv4"]
        if "statistics" in data:
            del data["statistics"]
        print_tabular(data, "")


class Sonic(object):
    def __init__(self, conn):
        self.port = Port(conn, self)
        self.vlan = Vlan(conn, self)

    def port_run_conf(self):
        self.port.run_conf()

    def vlan_run_conf(self):
        self.vlan.run_conf()

    def run_conf(self):
        print("!")
        self.vlan_run_conf()
        self.port_run_conf()

    def tech_support(self):
        print("\nshow vlan details:\n")
        self.vlan.show_vlan()
        print("\nshow interface description:\n")
        self.port.show_interface()


def set_attribute(sr_op, path, module, name, attr, value):
    try:
        sr_op.get_data(path, "running")
    except sr.SysrepoNotFoundError as e:
        if module == "interface":
            sr_op.set_data(f"{path}/admin-status", "up")
        if attr != "tagging_mode":
            sr_op.set_data(f"{path}/name", name)

    if module == "interface" and attr == "mtu":
        sr_op.set_data("{}/goldstone-ip:ipv4/{}".format(path, attr), value)
    else:
        sr_op.set_data(f"{path}/{attr}", value)
