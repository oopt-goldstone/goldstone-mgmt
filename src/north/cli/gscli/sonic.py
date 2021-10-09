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

    XPATH = "/goldstone-vlan:vlans/vlan"

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def get_interface_mode(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode"
        mode = self.sr_op.get_data(xpath)
        return ly.xpath_get(mode, xpath).lower()

    def show_vlans(self, details="details"):

        try:
            data = self.sr_op.get_data(self.XPATH, "operational")
        except sr.SysrepoNotFoundError:
            stderr.info("no vlan configured")
            return

        data = ly.xpath_get(data, self.XPATH)
        rows = []
        for v in data:
            vid = v.get("vlan-id", "-")
            name = v["state"].get("name", "-")
            members = natsorted(v.get("members", {}).get("member", []))
            modes = []
            for ifname in members:
                modes.append(self.get_interface_mode(ifname))

            members = "\n".join(members) if len(members) > 0 else "-"
            modes = "\n".join(modes) if len(modes) > 0 else "-"

            rows.append((vid, name, members, modes))

        rows = natsorted(rows, lambda v: v[0])
        stdout.info(tabulate(rows, ["vid", "name", "members", "mode"]))

    def set_name(self, vid, name):
        self.sr_op.set_data(f"{self.xpath(vid)}/config/name", name)

    def xpath(self, vid):
        return f"{self.XPATH}[vlan-id='{vid}']"

    def create(self, vid):
        self.sr_op.set_data(f"{self.xpath(vid)}/config/vlan-id", vid)

    def delete(self, vid):
        if vid not in self.get_vids():
            raise InvalidInput(f"vlan {vid} not found")
        self.sr_op.delete_data(self.xpath(vid))

    def get_vids(self):
        xpath = f"{self.XPATH}/vlan-id"
        try:
            data = self.sr_op.get_data(xpath)
        except sr.SysrepoNotFoundError:
            return []
        data = ly.xpath_get(data, self.XPATH)
        return [str(v["vlan-id"]) for v in data]

    def show(self, vid):
        xpath = self.xpath(vid)
        v = self.sr_op.get_data(xpath, "operational")
        v = ly.xpath_get(v, xpath)
        rows = [("vid", v.get("vlan-id", "-"))]
        rows.append(("name", v["state"].get("name", "-")))
        members = natsorted(v.get("members", {}).get("member", []))
        members = "\n".join(f"{m} {self.get_interface_mode(m)}" for m in members)
        rows.append(("members", members))
        stdout.info(tabulate(rows))

    def run_conf(self):
        for vid in self.get_vids():
            stdout.info(f"vlan {vid}")
            stdout.info(f"  quit")
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
        interface_list = self.get_interface_list("running", False)
        if not interface_list:
            return

        ufd = self.get_ufd()
        pc = self.get_portchannel()

        for data in interface_list:
            ifname = data.get("name")
            config = data.get("config", {})

            an = data.get("auto-negotiate")
            if an:
                config["auto-negotiate"] = an

            vlan = data.get("switched-vlan")
            if vlan:
                config["switched-vlan"] = vlan

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
                elif key == "switched-vlan":
                    try:
                        mode = value["config"]["interface-mode"].lower()
                        if mode == "access":
                            vids = [value["config"]["access-vlan"]]
                        elif mode == "trunk":
                            vids = value["config"]["trunk-vlans"]
                        else:
                            continue  # print error?

                        for vid in vids:
                            stdout.info(f"  switchport mode {mode} vlan {vid}")
                    except KeyError:
                        pass

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

        for ifname in ifnames:
            xpath = self.xpath(ifname) + "/config"
            self.sr_op.set_data(f"{xpath}/name", ifname, no_apply=True)
            xpath = self.xpath(ifname) + "/goldstone-vlan:switched-vlan/config"

            if config:
                self.sr_op.set_data(
                    f"{xpath}/interface-mode", mode.upper(), no_apply=True
                )
                if mode == "access":
                    self.sr_op.set_data(f"{xpath}/access-vlan", vid, no_apply=True)
                else:
                    self.sr_op.set_data(f"{xpath}/trunk-vlans", vid, no_apply=True)
            else:
                if mode == "access":
                    self.sr_op.delete_data(f"{xpath}/access-vlan", no_apply=True)
                else:
                    self.sr_op.delete_data(
                        f"{xpath}/trunk-vlans[.='{vid}']", no_apply=True
                    )

        if not no_apply:
            self.sr_op.apply()

    def set_breakout(self, ifnames, number_of_channels, speed):

        if (number_of_channels == None) != (speed == None):
            raise InvalidInput(
                f"unsupported combination: {number_of_channels}, {speed}"
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
                for i in interfaces:
                    self.sr_op.delete_data(self.xpath(i), no_apply=True)

            else:
                stdout.info(
                    "Existing configurations on parent interfaces will be flushed"
                )
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

            if "auto-negotiate" in data:
                autonego = data["auto-negotiate"].get("state")
                if autonego:
                    v = "enabled" if autonego["enabled"] else "disabled"
                    data["auto-negotiate"] = v
                    v = autonego.get("advertised-speeds")
                    if v:
                        v = ",".join(speed_yang_to_human(e) for e in v)
                        data["advertised-speeds"] = v
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
