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


def breakout_yang_to_human(breakout):
    numch = breakout["num-channels"]
    speed = breakout["channel-speed"]
    speed = speed_yang_to_human(speed)
    return f"{numch}X{speed}"


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

    def get_interface_list(self, datastore):
        try:
            imp = datastore == "operational"
            tree = self.sr_op.get_data(
                self.XPATH, datastore, include_implicit_values=imp
            )
        except sr.SysrepoError as e:
            if datastore == "operational":
                raise InvalidInput(e.details[0][1] if e.details else str(e))
            else:
                return []
        interfaces = tree["interfaces"]["interface"]
        return natsorted(interfaces, key=lambda x: x["name"])

    def show_interface(self, details="description"):
        rows = []
        interfaces = self.get_interface_list("operational")
        for intf in interfaces:
            state = intf.get("state", {})
            row = [
                intf["name"],
                state.get("oper-status", "-").lower(),
                state.get("admin-status", "-").lower(),
                state.get("alias", "-"),
            ]
            if details == "description":
                state = intf.get("ethernet", {}).get("state", {})
                speed = state.get("speed", "-")
                if speed != "-":
                    speed = speed_yang_to_human(speed)
                mtu = state.get("mtu", "-")
                row += [speed, mtu]

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
            if data == None:
                stdout.info(f"no counter info for Interface {ifname}")
                continue

            if table:
                rows.append((ifname, data))
            else:
                for d in data:
                    stdout.info(f"  {d}: {data[d]}")

        if table and len(rows) > 0:
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
        interface_list = self.get_interface_list("running")
        if not interface_list:
            return

        ufd = self.get_ufd()
        pc = self.get_portchannel()

        for data in interface_list:
            ifname = data.get("name")
            stdout.info("interface {}".format(ifname))

            config = data.get("config")
            if config:
                for key, value in config.items():
                    if key == "admin-status":
                        if value == "DOWN":
                            stdout.info("  admin-status down")
                        elif value == "UP":
                            stdout.info("  admin-status up")

            ethernet = data.get("ethernet")
            if ethernet:
                config = ethernet.get("config", {})
                for key in ["fec", "interface-type", "speed", "mtu"]:
                    if key in config and config.get(key):
                        value = config.get(key)
                        if key == "fec":
                            value = value.lower()
                        elif key == "speed":
                            value = speed_yang_to_human(value)
                        stdout.info(f"  {key} {value}")

                if "auto-negotiate" in ethernet:
                    config = ethernet["auto-negotiate"].get("config", {})
                    v = config.get("enabled")
                    if v != None:
                        value = "enable" if v else "disable"
                        stdout.info(f"  auto-negotiate {value}")

                    v = config.get("advertised-speeds")
                    if v:
                        v = ",".join(speed_yang_to_human(s) for s in v)
                        stdout.info(f"  auto-negotiate advatise {v}")

                if "breakout" in ethernet:
                    config = ethernet["breakout"].get("config", {})
                    breakout = breakout_yang_to_human(config)
                    stdout.info(f"  breakout {breakout}")

            vlan = data.get("switched-vlan")
            if vlan:
                config = vlan.get("config", {})
                mode = config.get("interface-mode", "").lower()
                if mode == "access":
                    vids = [config["access-vlan"]]
                elif mode == "trunk":
                    vids = config.get("trunk-vlans", [])
                else:
                    continue  # print error?

                for vid in vids:
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
        except (sr.errors.SysrepoError, KeyError):
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
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/config/admin-status", value, no_apply=True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/config/admin-status", no_apply=True)

        self.sr_op.apply()

    def set_fec(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/ethernet/config/fec", value, no_apply=True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/ethernet/config/fec", no_apply=True)
        self.sr_op.apply()

    def set_auto_nego(self, ifnames, mode):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if mode:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/ethernet/auto-negotiate/config/enabled",
                    mode,
                    no_apply=True,
                )
            else:
                self.sr_op.delete_data(
                    f"{xpath}/ethernet/auto-negotiate/config/enabled", no_apply=True
                )
        self.sr_op.apply()

    def set_auto_nego_adv_speed(self, ifnames, speeds):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            self.sr_op.delete_data(
                f"{xpath}/ethernet/auto-negotiate/config/advertised-speeds",
                no_apply=True,
            )
            if speeds:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                for speed in speeds.split(","):
                    self.sr_op.set_data(
                        f"{xpath}/ethernet/auto-negotiate/config/advertised-speeds",
                        speed_human_to_yang(speed),
                        no_apply=True,
                    )

        self.sr_op.apply()

    def set_interface_type(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/ethernet/config/interface-type", value, no_apply=True
                )
            else:
                self.sr_op.delete_data(
                    f"{xpath}/ethernet/config/interface-type", no_apply=True
                )
        self.sr_op.apply()

    def set_mtu(self, ifnames, value):
        for ifname in ifnames:
            xpath = self.xpath(ifname)
            if value:
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/ethernet/config/mtu", value, no_apply=True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/ethernet/config/mtu", no_apply=True)
        self.sr_op.apply()

    def mtu_range(self):
        ctx = self.session.get_ly_ctx()
        xpath = "/goldstone-interfaces:interfaces"
        xpath += "/goldstone-interfaces:interface"
        xpath += "/goldstone-interfaces:ethernet"
        xpath += "/goldstone-interfaces:config"
        xpath += "/goldstone-interfaces:mtu"
        for node in ctx.find_path(xpath):
            return node.type().range()

    def valid_speeds(self):
        ctx = self.session.get_ly_ctx()
        xpath = "/goldstone-interfaces:interfaces"
        xpath += "/goldstone-interfaces:interface"
        xpath += "/goldstone-interfaces:ethernet"
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
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/ethernet/config/speed", speed, no_apply=True
                )
            else:
                self.sr_op.delete_data(f"{xpath}/ethernet/config/speed", no_apply=True)
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

    def set_breakout(self, ifnames, numch, speed):

        if (numch == None) != (speed == None):
            raise InvalidInput(f"unsupported combination: {numch}, {speed}")

        is_delete = numch == None

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
                    xpath = f"{xpath}/ethernet/breakout/config"
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
                        intf.get("ethernet", {})
                        .get("breakout", {})
                        .get("state", {})
                        .get("parent")
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
                self.sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
                self.sr_op.set_data(
                    f"{xpath}/ethernet/breakout/config/num-channels",
                    numch,
                    no_apply=True,
                )
                self.sr_op.set_data(
                    f"{xpath}/ethernet/breakout/config/channel-speed",
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

            if "ethernet" in data:
                ethernet = data["ethernet"]

                if "state" in ethernet:
                    state = ethernet["state"]
                    if "speed" in state:
                        data["speed"] = speed_yang_to_human(state["speed"])
                    if "fec" in state:
                        data["fec"] = state["fec"].lower()
                    if "mtu" in state:
                        data["mtu"] = state["mtu"]
                    if "interface-type" in state:
                        data["interface-type"] = state["interface-type"]

                if "breakout" in ethernet:
                    state = ethernet["breakout"].get("state", {})
                    if "num-channels" in state:
                        data["breakout"] = breakout_yang_to_human(state)
                    elif "parent" in state:
                        data["parent"] = state["parent"]

                if "auto-negotiate" in ethernet:
                    autonego = ethernet["auto-negotiate"].get("state")
                    if autonego:
                        v = "enabled" if autonego["enabled"] else "disabled"
                        data["auto-negotiate"] = v
                        v = autonego.get("advertised-speeds")
                        if v:
                            v = ",".join(speed_yang_to_human(e) for e in v)
                            data["advertised-speeds"] = v

                if "switched-vlan" in ethernet:
                    state = ethernet["switched-vlan"]["state"]
                    data["vlan-mode"] = state["interface-mode"].lower()
                    if data["vlan-mode"] == "trunk":
                        data["trunk-vlans"] = ", ".join(state["trunk-vlans"])
                    elif data["vlan-mode"] == "access":
                        data["access-vlan"] = state["access-vlan"]

                if "pcs" in ethernet:
                    state = ethernet["pcs"].get("state", {})
                    for field in ["pcs-status", "serdes-status"]:
                        if field in state:
                            data[field] = ", ".join(state[field])

                del data["ethernet"]

            for key in ["admin-status", "oper-status"]:
                if key in data:
                    data[key] = data[key].lower()

            print_tabular(data, "")
