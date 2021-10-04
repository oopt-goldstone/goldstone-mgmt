import sys
import os

from tabulate import tabulate
import json
import sysrepo as sr
import libyang as ly
from .common import sysrepo_wrap, print_tabular

from prompt_toolkit.completion import WordCompleter
from .base import InvalidInput

from natsort import natsorted

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


def speed_human_to_yang(speed):
    # Considering only speeds supported in CLI
    return f"SPEED_{speed}"


def speed_yang_to_human(speed):
    # Considering only speeds supported in CLI
    speed = speed.split(":")[-1]
    return speed.replace("SPEED_", "")


class Vlan(object):

    XPATH = "/goldstone-vlan:vlan/VLAN"
    XPATHport = "/goldstone-vlan:vlan/VLAN_MEMBER"

    def xpath_vlan(self, vid):
        return "{}/VLAN_LIST[name='{}']".format(self.XPATH, "Vlan" + vid)

    def xpath_mem(self, vid):
        return "{}/VLAN_MEMBER_LIST[name='{}']".format(self.XPATHport, "Vlan" + vid)

    def __init__(self, conn):
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

    def get_vid(self):
        try:
            d = self.sr_op.get_data(f"{self.XPATH}/VLAN_LIST", "operational")
            d = d["vlan"]["VLAN"]["VLAN_LIST"]
            return [str(v["vlanid"]) for v in d]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            return []

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

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def interface_names(self):
        try:
            data = self.sr_op.get_data(f"{self.XPATH}/name", "operational")
        except sr.SysrepoNotFoundError:
            raise InvalidInput("no interface found")
        return natsorted(v["name"] for v in data["interfaces"]["interface"])

    def get_interface_list(
        self, datastore, include_implicit_values=True, no_subs=False
    ):
        try:
            tree = self.sr_op.get_data(
                self.XPATH, datastore, no_subs, include_implicit_values
            )
            return natsorted(tree["interfaces"]["interface"], key=lambda x: x["name"])
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            return []

    def show_interface(self, details="description"):
        rows = []
        interfaces = self.get_interface_list("operational")
        if len(interfaces) == 0:
            # FIXME workaround for sysrepo bug
            # Because oper cb can't raise any Exception,
            # treat len(interfaces) == 0 as an error
            raise InvalidInput("no interface found")

        for intf in interfaces:
            state = intf.get("state", {})
            row = [
                intf["name"],
                state.get("oper-status", "-").lower(),
                state.get("admin-status", "-").lower(),
                state.get("alias", "-"),
            ]
            if details == "description":
                speed = state.get("speed", "-")
                if speed != "-":
                    speed = speed_yang_to_human(speed)
                row += [speed, intf.get("mtu", "-")]

            rows.append(row)

        if details == "brief":
            headers = ["name", "oper-status", "admin-status", "alias"]
        elif details == "description":
            headers = ["name", "oper-status", "admin-status", "alias", "speed", "mtu"]
        else:
            raise InvalidInput(f"unsupported format: {details}")

        stdout.info(tabulate(rows, headers, tablefmt="pretty"))

    def show_counters(self, ifnames, table):
        rows = []
        for ifname in ifnames:
            if len(ifnames) > 1:
                if not table:
                    stdout.info(f"Interface {ifname}:")

            xpath = f"{self.XPATH}[name='{ifname}']/state/counters"
            data = self.sr_op.get_data(xpath, "operational")
            data = ly.xpath_get(data, xpath)
            if table:
                rows.append((ifname, data))
            else:
                for d in data:
                    stdout.info(f"  {d}: {data[d]}")

        if table:
            keys = rows[0][1].keys()
            rows_ = []
            for row in rows:
                r = [row[0]]
                for key in keys:
                    r.append(row[1][key])
                rows_.append(r)

            headers = [""] + ["\n".join(k.split("-")) for k in keys]

            stdout.info(tabulate(rows_, headers))

    def run_conf(self):
        xpath_vlan = "/goldstone-vlan:vlan/VLAN_MEMBER"

        interface_list = self.get_interface_list("running", False)
        if not interface_list:
            return

        ufd = self.get_ufd()
        pc = self.get_portchannel()

        for data in interface_list:
            ifname = data.get("name")
            config = data.get("config", {})

            an = data.get("auto-negotiate", {})
            config["auto-negotiate"] = an

            stdout.info("interface {}".format(ifname))
            for key, value in config.items():
                if key == "admin-status":
                    if value == "DOWN":
                        stdout.info("  admin-status down")
                    elif value == "UP":
                        stdout.info("  admin-status up")

                elif key in ["fec", "interface-type", "speed", "mtu"]:
                    if value:
                        stdout.info(f"  {key} {value}")

                elif key == "auto-negotiate":
                    try:
                        v = value["config"]["enabled"]
                        if v:
                            stdout.info("  auto-negotiate enable")
                        else:
                            stdout.info("  auto-negotiate disable")
                        v = value["config"]["advertised-speeds"]
                        if v:
                            v = ",".join(speed_yang_to_human(s) for s in v)
                            stdout.info(f"  auto-negotiate advatise {v}")
                    except KeyError:
                        pass

                elif key == "breakout":
                    if value:
                        num_of_channels = value["num-channels"]
                        channel_speed = value["channel-speed"]
                        channel_speed = channel_speed.split("_")
                        channel_speed = channel_speed[1].split("B")
                        stdout.info(
                            "  {} {}X{}".format(key, num_of_channels, channel_speed[0])
                        )
                elif key == "name":
                    try:
                        vlan_tree = self.sr_op.get_data_ly(xpath_vlan, "running")
                        vlan_memlist = json.loads(vlan_tree.print_mem("json"))
                        vlan_memlist = vlan_memlist["goldstone-vlan:vlan"][
                            "VLAN_MEMBER"
                        ]["VLAN_MEMBER_LIST"]
                    except (sr.errors.SysrepoNotFoundError, KeyError):
                        # No vlan configrations is a valid case
                        continue

                    for vlan in vlan_memlist:
                        if vlan["ifname"] != value:
                            continue
                        vid = vlan["name"].split("Vlan", 1)[1]
                        mode = "trunk" if vlan["tagging_mode"] == "tagged" else "access"
                        stdout.info(f"  switchport mode {mode} vlan {vid}")

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
            if value:
                set_attribute(
                    self.sr_op, xpath, "interface", ifname, "admin-status", value, True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/config/admin-status", no_apply=True)

        self.sr_op.apply()

    def set_fec(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
                set_attribute(
                    self.sr_op,
                    xpath,
                    "interface",
                    ifname,
                    "fec",
                    value,
                    True,
                )
            else:
                self.sr_op.delete_data(f"{xpath}/config/fec", no_apply=True)
        self.sr_op.apply()

    def set_auto_nego(self, ifnames, mode):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if mode == None:
                self.sr_op.delete_data(
                    f"{xpath}/auto-negotiate/config/enabled", no_apply=True
                )
            else:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(f"{xpath}/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/auto-negotiate/config/enabled", mode, no_apply=True
                )
        self.sr_op.apply()

    def set_auto_nego_adv_speed(self, ifnames, speeds):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            self.sr_op.delete_data(
                f"{xpath}/auto-negotiate/config/advertised-speeds", no_apply=True
            )
            if speeds:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(f"{xpath}/name", ifname, no_apply=True)
                for speed in speeds.split(","):
                    self.sr_op.set_data(
                        f"{xpath}/auto-negotiate/config/advertised-speeds",
                        speed_human_to_yang(speed),
                        no_apply=True,
                    )

        self.sr_op.apply()

    def set_interface_type(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
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
                self.sr_op.delete_data(f"{xpath}/config/interface-type", no_apply=True)
        self.sr_op.apply()

    def set_mtu(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
                set_attribute(
                    self.sr_op, xpath, "interface", ifname, "mtu", value, True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/config/mtu", no_apply=True)
        self.sr_op.apply()

    def mtu_range(self):
        ctx = self.session.get_ly_ctx()
        xpath = "/goldstone-interfaces:interfaces"
        xpath += "/goldstone-interfaces:interface"
        xpath += "/goldstone-interfaces:config"
        xpath += "/goldstone-interfaces:mtu"
        for node in ctx.find_path(xpath):
            return node.type().range()

    def valid_speeds(self):
        ctx = self.session.get_ly_ctx()
        xpath = "/goldstone-interfaces:interfaces"
        xpath += "/goldstone-interfaces:interface"
        xpath += "/goldstone-interfaces:config"
        xpath += "/goldstone-interfaces:speed"
        leaf = list(ctx.find_path(xpath))[0]
        # SPEED_10G => 10G
        v = [e[0].replace("SPEED_", "") for e in leaf.type().enums()]
        v = v[1:]  # remove SPEED_UNKNOWN
        return v

    def set_speed(self, ifnames, speed):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if speed:
                speed = speed_human_to_yang(speed)
                set_attribute(
                    self.sr_op,
                    xpath,
                    "interface",
                    ifname,
                    "speed",
                    speed,
                    no_apply=True,
                )
            else:
                self.sr_op.delete_data(f"{xpath}/config/speed", no_apply=True)
        self.sr_op.apply()

    def set_vlan_mem(self, ifnames, mode, vid, config=True, no_apply=False):
        xpath_mem_list = "/goldstone-vlan:vlan/VLAN/VLAN_LIST"
        xpath_mem_mode_prefix = "/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST"
        mode_map = {"tagged": "trunk", "untagged": "access"}

        name = "Vlan" + vid
        xpath_mem_list = xpath_mem_list + "[name='{}']".format(name)

        if config:
            for ifname in ifnames:

                # in order to create the interface node if it doesn't exist in running DS
                try:
                    self.sr_op.get_data(self.xpath(ifname), "running")

                except sr.SysrepoNotFoundError as e:
                    self.sr_op.set_data(
                        f"{self.xpath(ifname)}/config/name", ifname, no_apply=True
                    )

                set_attribute(
                    self.sr_op,
                    xpath_mem_list,
                    "vlan",
                    name,
                    "members",
                    ifname,
                    no_apply=True,
                )

                xpath_mem_mode = (
                    f"{xpath_mem_mode_prefix}[name='{name}'][ifname='{ifname}']"
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

        else:
            mem_list = self.sr_op.get_leaf_data(xpath_mem_list, "members")
            if len(mem_list) == 0:
                raise InvalidInput("No members added")
            self.sr_op.delete_data(f"{xpath_mem_list}/members", no_apply=True)

            for ifname in ifnames:
                if ifname in mem_list:
                    xpath_mem_mode = (
                        f"{xpath_mem_mode_prefix}[name='{name}'][ifname='{ifname}']"
                    )
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

    def set_breakout(self, ifnames, number_of_channels, speed):

        if (number_of_channels == None) != (speed == None):
            raise InvalidInput(
                f"unsupported combination: {number_of_channels}, {speed}"
            )

        def remove_interfaces_from_vlans(interfaces):
            try:
                data = self.sr_op.get_data("/goldstone-vlan:vlan/VLAN/VLAN_LIST")
                data = data["vlan"]["VLAN"]["VLAN_LIST"]
            except (sr.errors.SysrepoNotFoundError, KeyError):
                # no VLAN configuration exists
                return

            for vlan in data:
                intfs = [m for m in vlan.get("members", []) if m in interfaces]
                if intfs:
                    self.set_vlan_mem(
                        intfs, None, str(vlan["vlanid"]), config=False, no_apply=True
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
                    xpath = f"{xpath}/config/breakout"
                    data = self.sr_op.get_data(xpath, "running")
                    ly.xpath_get(data, xpath)
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    # If no configuration exists, no need to return error
                    continue

                stdout.info("Sub Interfaces will be deleted")

                data = self.sr_op.get_data(self.XPATH, ds="operational")
                data = ly.xpath_get(data, self.XPATH)

                interfaces = [ifname]
                for intf in data:
                    parent = (
                        intf.get("state", {}).get("breakout", {}).get("parent", None)
                    )
                    if ifname == parent:
                        interfaces.append(intf["name"])

                stdout.info(
                    "Existing configurations on parent interfaces will be flushed"
                )
                remove_interfaces_from_vlans(interfaces)
                for i in interfaces:
                    self.sr_op.delete_data(self.xpath(i), no_apply=True)

            else:
                stdout.info(
                    "Existing configurations on parent interfaces will be flushed"
                )
                remove_interfaces_from_vlans([ifname])
                xpath = self.xpath(ifname)
                self.sr_op.delete_data(xpath, no_apply=True)

                # Set breakout configuration
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
                    speed_human_to_yang(speed),
                    no_apply=True,
                )

        self.sr_op.apply()

    def show(self, ifnames):
        for ifname in ifnames:
            if len(ifnames) > 1:
                stdout.info(f"Interface {ifname}:")
            xpath = self.xpath(ifname)
            try:
                tree = self.sr_op.get_data(xpath, "operational")
            except sr.SysrepoNotFoundError:
                if len(ifnames) > 1:
                    stdout.info("interface not found")
                    continue
                else:
                    raise InvalidInput("interface not found")
            data = ly.xpath_get(tree, xpath)

            if "config" in data:
                data.update(data["config"])
                del data["config"]

            if "state" in data:
                data.update(data["state"])
                del data["state"]

            if "counters" in data:
                del data["counters"]
            if "breakout" in data:
                try:
                    data["breakout:num-channels"] = data["breakout"]["num-channels"]
                    data["breakout:channel-speed"] = data["breakout"]["channel-speed"]
                except:
                    data["breakout:parent"] = data["breakout"]["parent"]
                del data["breakout"]

            autonego = data.get("auto-negotiate", {}).get("state")
            if autonego:
                v = "enabled" if autonego["enabled"] else "disabled"
                data["auto-negotiate"] = v
                v = autonego.get("advertised-speeds")
                if v:
                    v = ",".join(speed_yang_to_human(e) for e in v)
                    data["advertised-speeds"] = v
            else:
                del data["auto-negotiate"]

            if "speed" in data:
                data["speed"] = speed_yang_to_human(data["speed"])

            for key in ["admin-status", "oper-status", "fec"]:
                if key in data:
                    data[key] = data[key].lower()

            print_tabular(data, "")


class UFD(object):

    XPATH = "/goldstone-uplink-failure-detection:ufd-groups"

    def xpath(self, id):
        return "{}/ufd-group[ufd-id='{}']".format(self.XPATH, id)

    def __init__(self, conn):
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
                self.sr_op.set_data(f"{xpath}/config/name", port, no_apply=True)

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
        d = self.session.get_data(path)
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
                config = ufd["config"]
                for role in ["uplink", "downlink"]:
                    links = config.get(role, [])
                    if port in links:
                        found = True
                        self.remove_ports(ufd["ufd-id"], role, [port], True)

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

                if i != len(ids) - 1:
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


def set_attribute(sr_op, path, module, name, attr, value, no_apply=False):
    try:
        sr_op.get_data(path, "running")
    except sr.SysrepoNotFoundError as e:
        if module == "interface":
            sr_op.set_data(f"{path}/config/name", name, no_apply=no_apply)
        if attr != "tagging_mode":
            sr_op.set_data(f"{path}/name", name, no_apply=no_apply)

    if module == "interface":
        if attr == "num-channels" or attr == "channel-speed":
            xpath = f"{path}/config/breakout/{attr}"
        else:
            xpath = f"{path}/config/{attr}"
    else:
        xpath = f"{path}/{attr}"
    sr_op.set_data(xpath, value, no_apply=no_apply)


class Portchannel(object):

    XPATH = "/goldstone-portchannel:portchannel"

    def xpath(self, id):
        return "{}/portchannel-group[portchannel-id='{}']".format(self.XPATH, id)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

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

    def get_list(self, ds, include_implicit_values=True):
        try:
            tree = self.sr_op.get_data(self.XPATH, ds, False, include_implicit_values)
            return natsorted(
                tree["portchannel"]["portchannel-group"],
                key=lambda x: x["portchannel-id"],
            )
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            return []

    def add_interfaces(self, id, ifnames):
        prefix = "/goldstone-interfaces:interfaces"
        for ifname in ifnames:
            xpath = f"{prefix}/interface[name='{ifname}']"
            # in order to create the interface node if it doesn't exist in running DS
            try:
                self.sr_op.get_data(xpath, "running")
            except sr.SysrepoNotFoundError as e:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)

            self.sr_op.set_data(
                f"{self.xpath(id)}/config/interface", ifname, no_apply=True
            )
        self.sr_op.apply()

    def set_admin_status(self, id, value):
        if value:
            self.sr_op.set_data(f"{self.xpath(id)}/config/admin-status", value)
        else:
            self.sr_op.delete_data(f"{self.xpath(id)}/config/admin-status")

    def get_id(self):
        return [v["portchannel-id"] for v in self.get_list("operational")]

    def remove_interfaces(self, ifnames):
        groups = self.get_list("running")
        if len(groups) == 0:
            raise InvalidInput("portchannel not configured for this interface")

        for ifname in ifnames:
            for data in groups:
                try:
                    if ifname in data["config"]["interface"]:
                        xpath = self.xpath(data["portchannel-id"])
                        self.sr_op.delete_data(
                            f"{xpath}/config/interface[.='{ifname}']", no_apply=True
                        )
                        break
                except KeyError:
                    pass
            else:
                self.sr_op.discard_changes()
                raise InvalidInput(f"portchannel not configured for {ifname}")

        self.sr_op.apply()

    def run_conf(self):
        for data in self.get_list("running", False):
            stdout.info("portchannel {}".format(data["config"]["portchannel-id"]))
            config = data.get("config", {})
            for key, value in config.items():
                if key == "admin-status":
                    stdout.info(f"  {key} {value.lower()}")
            stdout.info("  quit")
            stdout.info("!")

    def show(self, id=None):
        try:
            tree = self.sr_op.get_data(self.XPATH, "operational")
            id_list = tree["portchannel"]["portchannel-group"]
        except (sr.errors.SysrepoNotFoundError, KeyError):
            id_list = []

        if len(id_list) == 0:
            stdout.info(
                tabulate(
                    [],
                    ["Portchannel-ID", "oper-status", "admin-status", "Interface"],
                    tablefmt="pretty",
                )
            )
        else:
            data_tabulate = []
            interface = []
            ids = []
            adm_st = []
            op_st = []

            if id != None:
                ids.append(id)
            else:
                for data in id_list:
                    ids.append(data["portchannel-id"])

                ids = natsorted(ids)

            for id in ids:
                data = id_list[id]
                adm_st.append(data["state"]["admin-status"].lower())
                try:
                    interface.append(natsorted(list(data["config"]["interface"])))
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    interface.append([])
                try:
                    op_st.append(data["state"]["oper-status"].lower())
                except (sr.errors.SysrepoNotFoundError, KeyError):
                    op_st.append("-")

            for i in range(len(ids)):

                if len(interface[i]) > 0:
                    data_tabulate.append([ids[i], op_st[i], adm_st[i], interface[i][0]])
                else:
                    data_tabulate.append([ids[i], op_st[i], adm_st[i], "-"])

                for j in range(1, len(interface[i])):
                    data_tabulate.append(["", "", "", interface[i][j]])

                if i != len(ids) - 1:
                    data_tabulate.append(["", "", "", ""])

            stdout.info(
                tabulate(
                    data_tabulate,
                    ["Portchannel-ID", "oper-status", "admin-status", "Interface"],
                    tablefmt="pretty",
                    colalign=("left",),
                )
            )
