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
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class sonic_defaults:
    SPEED = "100000"
    INTF_TYPE = "KR4"


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
            stdout.info(
                tabulate([], ["VLAN ID", "Port", "Port Tagging"], tablefmt="pretty")
            )
        else:
            try:
                dl1 = dl1["goldstone-vlan:vlan"].get("VLAN", {}).get("VLAN_LIST", [])
                dl2 = (
                    dl2["goldstone-vlan:vlan"]
                    .get("VLAN_MEMBER", {})
                    .get("VLAN_MEMBER_LIST", [])
                )
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
            stdout.info(
                tabulate(dln, ["VLAN ID", "Port", "Port Tagging"], tablefmt="pretty")
            )
        self.session.switch_datastore("running")

    def _vlan_components(self):
        d = self._vlan_map
        return [str(v["vlanid"]) for v in d]

    def set_name(self, name):
        vid = name[4:]
        try:
            self.sr_op.set_data("{}/name".format(self.xpath_vlan(vid)), name)
        except sr.errors.SysrepoValidationFailedError as error:
            msg = str(error)
            stderr.info(msg)

    def create(self, vid):
        name = "Vlan" + vid
        try:
            data_tree = self.session.get_data_ly(self.XPATH)
            vlan_map = json.loads(data_tree.print_mem("json"))["goldstone-vlan:vlan"][
                "VLAN"
            ]["VLAN_LIST"]
        except (sr.errors.SysrepoNotFoundError, KeyError) as error:
            logger.warning(error)
        else:
            if name in vlan_map:
                return
        self.sr_op.set_data("{}/vlanid".format(self.xpath_vlan(vid)), vid)

    def delete(self, vid):
        name = "Vlan" + vid
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
            stdout.info("vlan {}".format(data["vlanid"]))
            stdout.info("  quit")
        stdout.info("!")


class Port(object):

    XPATH = "/goldstone-interfaces:interfaces/interface"

    def xpath(self, ifname):
        self.path = self.XPATH
        return "{}[name='{}']".format(self.path, ifname)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def get_interface_list(self, datastore, include_implicit_values=True):
        try:
            tree = self.sr_op.get_data(
                self.XPATH, datastore, False, include_implicit_values
            )
            return natsorted(tree["interfaces"]["interface"], key=lambda x: x["name"])
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            return []

    def show_interface(self, details="description"):
        rows = []
        for intf in self.get_interface_list("operational"):
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

        stdout.info(tabulate(rows, headers, tablefmt="pretty"))

    def show_counters(self, ifname_list):
        intf_list = self.get_interface_list("operational")
        existing_ifname_list = [v["name"] for v in intf_list]

        # Raise exception if invalid interfaces are present in list
        for intf in ifname_list:
            if intf not in existing_ifname_list:
                raise InvalidInput(f"Invalid interface : {intf}")

        lines = []
        for intf in intf_list:
            if len(ifname_list) == 0 or intf["name"] in ifname_list:
                if "statistics" in intf:
                    lines.append(f"Interface  {intf['name']}")
                    statistics = intf["statistics"]
                    for key in statistics:
                        lines.append(f"  {key}: {statistics[key]}")
                    # One extra line to have readability
                    lines.append(f"\n")
                else:
                    lines.append(f"No statistics for: {intf['name']}")

        stdout.info("\n".join(lines))

    def run_conf(self):
        xpath_vlan = "/goldstone-vlan:vlan/VLAN_MEMBER"

        runn_conf_list = [
            "admin-status",
            "ipv4",
            "fec",
            "speed",
            "name",
            "breakout",
            "interface-type",
            "auto-nego",
        ]
        v_dict = {}
        interface_list = self.get_interface_list("running", False)
        if not interface_list:
            return

        ufd = self.get_ufd()
        pc = self.get_portchannel()

        for data in interface_list:
            ifname = data.get("name")
            stdout.info("interface {}".format(ifname))
            for v in runn_conf_list:
                v_dict = {v: data.get(v, None) for v in runn_conf_list}
                if v == "admin-status":
                    if v_dict["admin-status"] == "down":
                        stdout.info("  shutdown ")
                    elif v_dict["admin-status"] == None:
                        pass

                elif v == "ipv4":
                    try:
                        mtu = v_dict["ipv4"]["mtu"]
                    except:
                        mtu = None

                    if mtu:
                        stdout.info("  {} {}".format("mtu", mtu))

                elif v == "fec":
                    try:
                        fec = v_dict["fec"]
                        if fec == "none":
                            fec = None
                    except:
                        fec = None

                    if fec:
                        stdout.info("  {} {}".format("fec", fec))

                elif v == "auto-nego":
                    try:
                        auto_nego = v_dict["auto-nego"]
                    except:
                        auto_nego = None

                    if auto_nego == "yes":
                        stdout.info("  {} {}".format("auto-nego", "enable"))
                    if auto_nego == "no":
                        stdout.info("  {} {}".format("auto-nego", "disable"))

                elif v == "interface-type":
                    try:
                        intf_type = v_dict["interface-type"]
                    except:
                        intf_type = None

                    if intf_type:
                        stdout.info("  {} {}".format("interface-type", intf_type))

                elif v == "speed":
                    if (v_dict["speed"] == sonic_defaults.SPEED) or (
                        v_dict["speed"] == None
                    ):
                        pass
                    else:
                        stdout.info("  {} {}".format(v, v_dict[v]))

                elif v == "breakout":
                    if v_dict["breakout"] == None:
                        pass
                    else:
                        num_of_channels = v_dict["breakout"]["num-channels"]
                        channel_speed = v_dict["breakout"]["channel-speed"]
                        channel_speed = channel_speed.split("_")
                        channel_speed = channel_speed[1].split("B")
                        stdout.info(
                            "  {} {}X{}".format(v, num_of_channels, channel_speed[0])
                        )

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
                                stdout.info(
                                    "  switchport mode trunk vlan {}".format(
                                        str(vlanId)
                                    )
                                )
                            else:
                                stdout.info(
                                    "  switchport mode access vlan {}".format(
                                        str(vlanId)
                                    )
                                )

            if ifname in ufd:
                stdout.info(
                    "  ufd {} {}".format(ufd[ifname]["ufd-id"], ufd[ifname]["role"])
                )

            if ifname in pc:
                stdout.info("  portchannel {}".format(pc[ifname]["pc-id"]))

            stdout.info("  quit")
            stdout.info("!")
        stdout.info("!")

    def get_ufd(self):
        xpath = "/goldstone-uplink-failure-detection:ufd-groups"
        ufd = {}
        try:
            tree = self.sr_op.get_data("{}/ufd-group".format(xpath), "running")
            ufd_list = tree["ufd-groups"]["ufd-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return {}

        for data in ufd_list:
            try:
                for intf in data["config"]["uplink"]:
                    ufd[intf] = {"ufd-id": data["ufd-id"], "role": "uplink"}
            except:
                pass

            try:
                for intf in data["config"]["downlink"]:
                    ufd[intf] = {"ufd-id": data["ufd-id"], "role": "downlink"}
            except:
                pass

        return ufd

    def get_portchannel(self):
        xpath = "/goldstone-portchannel:portchannel"
        pc = {}
        try:
            tree = self.sr_op.get_data("{}/portchannel-group".format(xpath), "running")
            pc_list = tree["portchannel"]["portchannel-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return {}

        for data in pc_list:
            try:
                for intf in data["config"]["interface"]:
                    pc[intf] = {"pc-id": data["portchannel-id"]}
            except:
                pass

        return pc

    def _ifname_components(self):
        d = self._ifname_map
        return [v["name"] for v in d]

    def set_admin_status(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            set_attribute(
                self.sr_op, xpath, "interface", ifname, "admin-status", value, True
            )

        self.sr_op.apply()

    def set_fec(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            set_attribute(
                self.sr_op,
                xpath,
                "interface",
                ifname,
                "fec",
                value if value else "none",
                True,
            )
        self.sr_op.apply()

    def set_auto_nego(self, ifnames, mode):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if mode:
                set_attribute(
                    self.sr_op, xpath, "interface", ifname, "auto-nego", mode, True
                )
            else:
                self.sr_op.delete_data("{}/auto-nego".format(xpath), no_apply=True)
        self.sr_op.apply()

    def set_interface_type(self, ifnames, value, config=True):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if config:
                set_attribute(
                    self.sr_op,
                    xpath,
                    "interface",
                    ifname,
                    "interface-type",
                    value,
                    True,
                )
            else:
                self.sr_op.delete_data(f"{xpath}/interface-type", no_apply=True)
        self.sr_op.apply()

    def set_mtu(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
                set_attribute(
                    self.sr_op, xpath, "interface", ifname, "mtu", value, True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/goldstone-ip:ipv4/mtu", no_apply=True)

                # if the mtu leaf was the only node under the ipv4 container
                # remove the container
                try:
                    data = self.sr_op.get_data(f"{xpath}/goldstone-ip:ipv4")
                except sr.errors.SysrepoNotFoundError:
                    continue

                data = data.get("interfaces", {}).get("interface", {})
                data = data.get(ifname, {}).get("ipv4", None) if len(data) else None
                if not data:
                    self.sr_op.delete_data(f"{xpath}/goldstone-ip:ipv4", no_apply=True)
        self.sr_op.apply()

    def mtu_range(self):
        ctx = self.session.get_ly_ctx()
        xpath = "/goldstone-interfaces:interfaces"
        xpath += "/goldstone-interfaces:interface"
        xpath += "/goldstone-ip:ipv4"
        xpath += "/goldstone-ip:mtu"
        for node in ctx.find_path(xpath):
            return node.type().range()

    def set_speed(self, ifnames, value, config=True):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if config:
                set_attribute(
                    self.sr_op,
                    xpath,
                    "interface",
                    ifname,
                    "speed",
                    value,
                    no_apply=True,
                )
            else:
                self.sr_op.delete_data(f"{xpath}/speed", no_apply=True)
        self.sr_op.apply()

    def set_vlan_mem(self, ifnames, mode, vid, config=True, no_apply=False):
        xpath_mem_list = "/goldstone-vlan:vlan/VLAN/VLAN_LIST"
        xpath_mem_mode = "/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST"
        mode_map = {"tagged": "trunk", "untagged": "access"}

        name = "Vlan" + vid
        xpath_mem_list = xpath_mem_list + "[name='{}']".format(name)

        for ifname in ifnames:
            xpath_mem_mode = xpath_mem_mode + "[name='{}'][ifname='{}']".format(
                name, ifname
            )

            # in order to create the interface node if it doesn't exist in running DS
            try:
                self.sr_op.get_data(self.xpath(ifname), "running")

            except sr.SysrepoNotFoundError as e:
                self.sr_op.set_data(
                    f"{self.xpath(ifname)}/admin-status", "down", no_apply=True
                )

            if config:
                set_attribute(
                    self.sr_op,
                    xpath_mem_list,
                    "vlan",
                    name,
                    "members",
                    ifname,
                    no_apply=True,
                )
                set_attribute(
                    self.sr_op,
                    xpath_mem_mode,
                    "vlan",
                    name,
                    "tagging_mode",
                    "tagged" if mode == "trunk" else "untagged",
                    no_apply=True,
                )

            elif not config:
                mem_list = self.sr_op.get_leaf_data(xpath_mem_list, "members")
                if len(mem_list) == 0:
                    raise InvalidInput("No members added")
                mode_data = self.sr_op.get_leaf_data(xpath_mem_mode, "tagging_mode")
                mode_data = mode_data.pop()
                if mode == None:
                    mode = mode_map[mode_data]
                # checking whether the delete was triggered with the correct mode in the command issued
                if mode_map[mode_data] != mode:
                    raise InvalidInput(f"Incorrect mode given : {mode}")
                if ifname in mem_list:
                    self.sr_op.delete_data(f"{xpath_mem_list}/members", no_apply=True)
                    self.sr_op.delete_data(xpath_mem_mode, no_apply=True)
                    mem_list.remove(ifname)
                    # Since we dont have utiity function in sysrepo to delete one node in
                    # leaf-list , we are deleting 'members' with old data and creating again
                    # with new data.
                    for mem_intf in mem_list:
                        set_attribute(
                            self.sr_op,
                            xpath_mem_list,
                            "vlan",
                            name,
                            "members",
                            mem_intf,
                            no_apply=True,
                        )

        if not no_apply:
            self.sr_op.apply()

    def speed_to_yang_val(self, speed):
        # Considering only speeds supported in CLI
        if speed == "25G":
            return "SPEED_25GB"
        if speed == "50G":
            return "SPEED_50GB"
        if speed == "10G":
            return "SPEED_10GB"
        if speed == "20G":
            return "SPEED_20GB"

    def set_breakout(self, ifnames, number_of_channels, speed):

        if (number_of_channels == None) != (speed == None):
            raise InvalidInput(
                f"unsupported combination: {number_of_channels}, {speed}"
            )

        def remove_intf_from_all_vlans(intf):
            try:
                data = self.sr_op.get_data("/goldstone-vlan:vlan/VLAN/VLAN_LIST")
                data = data["vlan"]["VLAN"]["VLAN_LIST"]
            except (sr.errors.SysrepoNotFoundError, KeyError):
                # no VLAN configuration exists
                return

            for vlan in data:
                if intf in vlan.get("members", []):
                    self.set_vlan_mem(
                        intf, None, str(vlan["vlanid"]), config=False, no_apply=True
                    )

        is_delete = number_of_channels == None

        for ifname in ifnames:

            # TODO use the parent leaf to detect if this is a sub-interface or not
            # using "_1" is vulnerable to the interface nameing schema change
            if "_1" not in ifname:
                raise InvalidInput(
                    "Breakout cannot be configured/removed on a sub-interface"
                )

            if is_delete:
                try:
                    xpath = self.xpath(ifname)
                    data = self.sr_op.get_data(f"{xpath}/breakout", "running")
                    data = data["interfaces"]["interface"][ifname]["breakout"]
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    # If no configuration exists, no need to return error
                    continue

                stdout.info("Sub Interfaces will be deleted")

                data = self.sr_op.get_data(self.XPATH, ds="operational", no_subs=True)
                for intf in data["interfaces"]["interface"]:
                    parent = intf.get("breakout", {}).get("parent", None)
                    if ifname == parent:
                        remove_intf_from_all_vlans(intf["name"])
                        self.sr_op.delete_data(self.xpath(intf["name"]), no_apply=True)

            stdout.info("Existing configurations on parent interfaces will be flushed")
            remove_intf_from_all_vlans(ifname)
            xpath = self.xpath(ifname)
            self.sr_op.delete_data(xpath, no_apply=True)

            if is_delete:
                continue

            # Set breakout configuration
            try:
                set_attribute(
                    self.sr_op,
                    xpath,
                    "interface",
                    ifname,
                    "num-channels",
                    number_of_channels,
                    no_apply=True,
                )
                set_attribute(
                    self.sr_op,
                    xpath,
                    "interface",
                    ifname,
                    "channel-speed",
                    self.speed_to_yang_val(speed),
                    no_apply=True,
                )

            except sr.errors.SysrepoValidationFailedError as error:
                raise InvalidInput(str(error))

        self.sr_op.apply()

    def show(self, ifnames):
        for ifname in ifnames:
            if len(ifnames) > 1:
                stdout.info(f"Interface {ifname}:")
            xpath = self.xpath(ifname)
            tree = self.sr_op.get_data(xpath, "operational")
            data = [v for v in list((tree)["interfaces"]["interface"])][0]
            if "ipv4" in data:
                mtu_dict = data["ipv4"]
                data["mtu"] = mtu_dict.get("mtu", "-")
                del data["ipv4"]
            if "statistics" in data:
                del data["statistics"]
            if "breakout" in data:
                try:
                    data["breakout:num-channels"] = data["breakout"]["num-channels"]
                    data["breakout:channel-speed"] = data["breakout"]["channel-speed"]
                except:
                    data["breakout:parent"] = data["breakout"]["parent"]
                del data["breakout"]
            print_tabular(data, "")


class UFD(object):

    XPATH = "/goldstone-uplink-failure-detection:ufd-groups"

    def xpath(self, id):
        return "{}/ufd-group[ufd-id='{}']".format(self.XPATH, id)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.tree = self.sr_op.get_data_ly("{}".format(self.XPATH), "operational")

    def create(self, id):
        xpath = "/goldstone-uplink-failure-detection:ufd-groups/ufd-group[ufd-id='{}']".format(
            id
        )

        try:
            self.sr_op.get_data(xpath, "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(f"{xpath}/config/ufd-id", id)

    def delete(self, id):
        self.sr_op.delete_data(self.xpath(id))
        return

    def add_ports(self, id, ports, role):
        prefix = "/goldstone-interfaces:interfaces"
        for port in ports:
            xpath = f"{prefix}/interface[name='{port}']"
            # in order to create the interface node if it doesn't exist in running DS
            try:
                self.sr_op.get_data(xpath, "running")
            except sr.SysrepoNotFoundError as e:
                self.sr_op.set_data(f"{xpath}/admin-status", "down", no_apply=True)

            self.sr_op.set_data(f"{self.xpath(id)}/config/{role}", port, no_apply=True)
        self.sr_op.apply()

    def remove_ports(self, id, role, ports, no_apply=False):
        xpath = self.xpath(id)
        for port in ports:
            self.sr_op.delete_data(f"{xpath}/config/{role}[.='{port}']", no_apply=True)

        if not no_apply:
            self.sr_op.apply()

    def get_id(self):
        path = "/goldstone-uplink-failure-detection:ufd-groups"
        self.session.switch_datastore("operational")
        d = self.session.get_data(path, no_subs=True)
        return natsorted(
            [v["ufd-id"] for v in d.get("ufd-groups", {}).get("ufd-group", {})]
        )

    def check_ports(self, ports):
        try:
            data = self.sr_op.get_data(f"{self.XPATH}/ufd-group", "running")
            ufds = data["ufd-groups"]["ufd-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            raise InvalidInput("UFD not configured for this interface")

        for port in ports:
            found = False
            for ufd in ufds:
                try:
                    uplinks = ufd["config"]["uplink"]
                    if port in uplinks:
                        found = True
                        self.remove_ports(data["ufd-id"], "uplink", port, True)
                except KeyError:
                    pass

                try:
                    downlinks = data["config"]["downlink"]
                    if port in downlinks:
                        found = True
                        self.remove_ports(data["ufd-id"], "downlink", port, True)
                except KeyError:
                    pass

            if not found:
                self.sr_op.discard_changes()
                raise InvalidInput("ufd not configured for this interface")

        self.sr_op.apply()

    def show(self, id=None):
        try:
            self.tree = self.sr_op.get_data(
                "{}/ufd-group".format(self.XPATH), "operational"
            )
            id_list = self.tree["ufd-groups"]["ufd-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            id_list = []

        if len(id_list) == 0:
            stdout.info(
                tabulate(
                    [], ["UFD-ID", "Uplink-Ports", "Downlink-Ports"], tablefmt="pretty"
                )
            )
        else:
            data_tabulate = []
            uplink_ports = []
            downlink_ports = []
            ids = []

            if id != None:
                ids.append(id)
            else:
                for data in id_list:
                    ids.append(data["ufd-id"])

                ids = natsorted(ids)

            for id in ids:
                data = id_list[id]
                try:
                    uplink_ports.append(natsorted(list(data["config"]["uplink"])))
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    uplink_ports.append([])
                try:
                    downlink_ports.append(natsorted(list(data["config"]["downlink"])))
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    downlink_ports.append([])

            for i in range(len(ids)):

                if len(uplink_ports[i]) > 0:
                    if len(downlink_ports[i]) > 0:
                        data_tabulate.append(
                            [ids[i], uplink_ports[i][0], downlink_ports[i][0]]
                        )
                    else:
                        data_tabulate.append([ids[i], uplink_ports[i][0], "-"])
                elif len(downlink_ports[i]) > 0:
                    data_tabulate.append([ids[i], "-", downlink_ports[i][0]])
                else:
                    data_tabulate.append([ids[i], "-", "-"])

                if len(uplink_ports[i]) > len(downlink_ports[i]):
                    for j in range(1, len(uplink_ports[i])):
                        if j < len(downlink_ports[i]):
                            data_tabulate.append(
                                ["", uplink_ports[i][j], downlink_ports[i][j]]
                            )
                        else:
                            data_tabulate.append(["", uplink_ports[i][j], ""])
                else:
                    for j in range(1, len(downlink_ports[i])):
                        if j < len(uplink_ports[i]):
                            data_tabulate.append(
                                ["", uplink_ports[i][j], downlink_ports[i][j]]
                            )
                        else:
                            data_tabulate.append(["", "", downlink_ports[i][j]])

                data_tabulate.append(["", "", ""])

            stdout.info(
                tabulate(
                    data_tabulate,
                    ["UFD-ID", "Uplink Ports", "Downlink Ports"],
                    tablefmt="pretty",
                    colalign=("left",),
                )
            )

    def run_conf(self):
        try:
            self.tree = self.sr_op.get_data(
                "{}/ufd-group".format(self.XPATH), "running"
            )
            d_list = self.tree["ufd-groups"]["ufd-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return

        ids = []

        for data in d_list:
            ids.append(data["ufd-id"])

        ids = natsorted(ids)

        for id in ids:
            data = d_list[id]
            stdout.info("ufd {}".format(data["config"]["ufd-id"]))
            stdout.info("  quit")
            stdout.info("!")


class Sonic(object):
    def __init__(self, conn):
        self.port = Port(conn, self)
        self.vlan = Vlan(conn, self)
        self.ufd = UFD(conn, self)
        self.pc = Portchannel(conn, self)

    def port_run_conf(self):
        self.port.run_conf()

    def vlan_run_conf(self):
        self.vlan.run_conf()

    def ufd_run_conf(self):
        self.ufd.run_conf()

    def portchannel_run_conf(self):
        self.pc.run_conf()

    def run_conf(self):
        stdout.info("!")
        self.vlan_run_conf()
        self.port_run_conf()
        self.ufd_run_conf()
        self.portchannel_run_conf()

    def tech_support(self):
        stdout.info("\nshow vlan details:\n")
        self.vlan.show_vlan()
        stdout.info("\nshow interface description:\n")
        self.port.show_interface()
        stdout.info("\nshow ufd:\n")
        self.ufd.show()
        self.pc.show()


def set_attribute(sr_op, path, module, name, attr, value, no_apply=False):
    try:
        sr_op.get_data(path, "running")
    except sr.SysrepoNotFoundError as e:
        if module == "interface":
            sr_op.set_data(f"{path}/admin-status", "up", no_apply=no_apply)
        if attr != "tagging_mode":
            sr_op.set_data(f"{path}/name", name, no_apply=no_apply)

    if module == "interface" and attr == "mtu":
        sr_op.set_data(
            "{}/goldstone-ip:ipv4/{}".format(path, attr), value, no_apply=no_apply
        )
    elif module == "interface" and (attr == "num-channels" or attr == "channel-speed"):
        sr_op.set_data("{}/breakout/{}".format(path, attr), value, no_apply=no_apply)
    else:
        sr_op.set_data(f"{path}/{attr}", value, no_apply=no_apply)


class Portchannel(object):

    XPATH = "/goldstone-portchannel:portchannel"

    def xpath(self, id):
        return "{}/portchannel-group[portchannel-id='{}']".format(self.XPATH, id)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.tree = self.sr_op.get_data_ly("{}".format(self.XPATH), "operational")

    def create(self, id):
        try:
            self.sr_op.get_data("{}".format(self.xpath(id)), "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(
                "{}/config/portchannel-id".format(self.xpath(id)),
                id,
            )

    def delete(self, id):
        self.sr_op.delete_data(self.xpath(id))
        return

    def add_interface(self, id, intf):
        xpath_intf = f"/goldstone-interfaces:interfaces/interface[name = '{intf}']"

        # in order to create the interface node if it doesn't exist in running DS
        try:
            self.sr_op.get_data(xpath_intf, "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data("{}/admin-status".format(xpath_intf), "down")

        self.sr_op.set_data("{}/config/interface".format(self.xpath(id)), intf)

    def get_id(self):
        path = "/goldstone-portchannel:portchannel"
        self.session.switch_datastore("operational")
        d = self.session.get_data(path)
        return natsorted(
            [
                v["portchannel-id"]
                for v in d.get("portchannel-group", {}).get("portchannel", {})
            ]
        )

    def remove_interface(self, intf):
        try:
            self.tree = self.sr_op.get_data(
                "{}/portchannel-group".format(self.XPATH), "running"
            )
            id_list = self.tree["portchannel"]["portchannel-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            raise InvalidInput("portchannel not configured for this interface")

        for data in id_list:
            try:
                if intf in data["config"]["interface"]:
                    xpath = self.xpath(data["portchannel-id"])
                    self.sr_op.delete_data(f"{xpath}/config/interface[.='{intf}']")
                    return
            except KeyError:
                pass
        raise InvalidInput("portchannel not configured for this interface")

    def run_conf(self):
        try:
            self.tree = self.sr_op.get_data(
                "{}/portchannel-group".format(self.XPATH), "running"
            )
            id_list = self.tree["portchannel"]["portchannel-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return

        ids = []

        for data in id_list:
            ids.append(data["portchannel-id"])

        ids = natsorted(ids)

        for id in ids:
            data = id_list[id]
            stdout.info("portchannel {}".format(data["config"]["portchannel-id"]))
            stdout.info("  quit")
            stdout.info("!")

    def show(self, id=None):
        try:
            # Fecting from running DS since south is not implemented
            self.tree = self.sr_op.get_data(
                "{}/portchannel-group".format(self.XPATH), "running"
            )
            id_list = self.tree["portchannel"]["portchannel-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            id_list = []

        if len(id_list) == 0:
            stdout.info(
                tabulate([], ["Portchannel-ID", "Interface"], tablefmt="pretty")
            )
        else:
            data_tabulate = []
            interface = []
            ids = []

            if id != None:
                ids.append(id)
            else:
                for data in id_list:
                    ids.append(data["portchannel-id"])

                ids = natsorted(ids)

            for id in ids:
                data = id_list[id]
                try:
                    interface.append(natsorted(list(data["config"]["interface"])))
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    interface.append([])

            for i in range(len(ids)):

                if len(interface[i]) > 0:
                    data_tabulate.append([ids[i], interface[i][0]])
                else:
                    data_tabulate.append([ids[i], "-"])

                for j in range(1, len(interface[i])):
                    data_tabulate.append(["", interface[i][j]])

            stdout.info(
                tabulate(
                    data_tabulate,
                    ["Portchannel-ID", "Interface"],
                    tablefmt="pretty",
                    colalign=("left",),
                )
            )
