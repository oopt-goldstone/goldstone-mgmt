import sys
import os
import re

from .base import InvalidInput, Command
from .cli import (
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    GlobalClearCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
from .common import sysrepo_wrap, print_tabular
import libyang as ly
import sysrepo as sr
from tabulate import tabulate

from prompt_toolkit.document import Document
from prompt_toolkit.completion import (
    WordCompleter,
    Completion,
    NestedCompleter,
    FuzzyWordCompleter,
)

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


XPATH = "/goldstone-interfaces:interfaces/interface"


def get_session(cmd):
    return cmd.context.root().conn.start_session()


def ifxpath(ifname):
    return f"{XPATH}[name='{ifname}']"


def interface_names(session, ptn=None):
    sr_op = sysrepo_wrap(session)
    try:
        data = sr_op.get_data(f"{XPATH}/name", "operational")
    except sr.SysrepoNotFoundError:
        raise InvalidInput("no interface found")
    if ptn:
        try:
            ptn = re.compile(ptn)
        except re.error:
            raise InvalidInput(f"failed to compile {ptn} as a regular expression")
        f = ptn.match
    else:
        f = lambda _: True
    return natsorted(v["name"] for v in data["interfaces"]["interface"] if f(v["name"]))


def get_interface_list(session, datastore):
    sr_op = sysrepo_wrap(session)
    try:
        imp = datastore == "operational"
        tree = sr_op.get_data(XPATH, datastore, include_implicit_values=imp)
    except sr.SysrepoError as e:
        if datastore == "operational":
            raise InvalidInput(e.details[0][1] if e.details else str(e))
        else:
            return []
    interfaces = tree["interfaces"]["interface"]
    return natsorted(interfaces, key=lambda x: x["name"])


def show_interface(session, details="description"):
    rows = []
    interfaces = get_interface_list(session, "operational")
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


def show_counters(session, ifnames, table):
    rows = []
    sr_op = sysrepo_wrap(session)
    interfaces = get_interface_list(session, "operational")
    for ifname in ifnames:
        if len(ifnames) > 1:
            if not table:
                stdout.info(f"Interface {ifname}:")

        xpath = f"{XPATH}[name='{ifname}']/state/counters"
        data = sr_op.get_data(xpath, "operational")
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


def run_conf(session):
    interface_list = get_interface_list(session, "running")
    if not interface_list:
        return

    ufd = get_ufd(session)
    pc = get_portchannel(session)

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

        otn = data.get("otn")
        if otn:
            mfi = otn.get("config", {}).get("mfi-type")
            if mfi:
                stdout.info(f"  interface-type otn {mfi.lower()}")

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


def get_ufd(session):
    sr_op = sysrepo_wrap(session)
    xpath = "/goldstone-uplink-failure-detection:ufd-groups"
    ufd = {}
    try:
        tree = sr_op.get_data("{}/ufd-group".format(xpath), "running")
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


def get_portchannel(session):
    sr_op = sysrepo_wrap(session)
    xpath = "/goldstone-portchannel:portchannel"
    pc = {}
    try:
        tree = sr_op.get_data("{}/portchannel-group".format(xpath), "running")
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


def set_admin_status(session, ifnames, value):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(f"{xpath}/config/admin-status", value, no_apply=True)
        else:
            sr_op.delete_data(f"{xpath}/config/admin-status", no_apply=True)

    sr_op.apply()


def set_fec(session, ifnames, value):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(f"{xpath}/ethernet/config/fec", value, no_apply=True)
        else:
            sr_op.delete_data(f"{xpath}/ethernet/config/fec", no_apply=True)
    sr_op.apply()


def set_auto_nego(session, ifnames, mode):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if mode:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(
                f"{xpath}/ethernet/auto-negotiate/config/enabled",
                mode,
                no_apply=True,
            )
        else:
            sr_op.delete_data(
                f"{xpath}/ethernet/auto-negotiate/config/enabled", no_apply=True
            )
    sr_op.apply()


def set_auto_nego_adv_speed(session, ifnames, speeds):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        sr_op.delete_data(
            f"{xpath}/ethernet/auto-negotiate/config/advertised-speeds",
            no_apply=True,
        )
        if speeds:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            for speed in speeds.split(","):
                sr_op.set_data(
                    f"{xpath}/ethernet/auto-negotiate/config/advertised-speeds",
                    speed_human_to_yang(speed),
                    no_apply=True,
                )

    sr_op.apply()


def set_interface_type(session, ifnames, value):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(
                f"{xpath}/config/interface-type", "IF_ETHERNET", no_apply=True
            )
            sr_op.set_data(
                f"{xpath}/ethernet/config/interface-type", value, no_apply=True
            )
            sr_op.delete_data(f"{xpath}/otn", no_apply=True)
        else:
            sr_op.delete_data(f"{xpath}/ethernet/config/interface-type", no_apply=True)
            sr_op.delete_data(f"{xpath}/config/interface-type", no_apply=True)
    sr_op.apply()


def set_otn_interface_type(session, ifnames, value):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(f"{xpath}/config/interface-type", "IF_OTN", no_apply=True)
            sr_op.set_data(f"{xpath}/otn/config/mfi-type", value.upper(), no_apply=True)
            sr_op.delete_data(f"{xpath}/ethernet/config/interface-type", no_apply=True)
        else:
            sr_op.delete_data(f"{xpath}/otn", no_apply=True)
            sr_op.delete_data(f"{xpath}/config/interface-type", no_apply=True)
    sr_op.apply()


def set_mtu(session, ifnames, value):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(f"{xpath}/ethernet/config/mtu", value, no_apply=True)
        else:
            sr_op.delete_data(f"{xpath}/ethernet/config/mtu", no_apply=True)
    sr_op.apply()


def mtu_range(session):
    ctx = session.get_ly_ctx()
    xpath = "/goldstone-interfaces:interfaces"
    xpath += "/goldstone-interfaces:interface"
    xpath += "/goldstone-interfaces:ethernet"
    xpath += "/goldstone-interfaces:config"
    xpath += "/goldstone-interfaces:mtu"
    for node in ctx.find_path(xpath):
        return node.type().range()


def valid_speeds(session):
    ctx = session.get_ly_ctx()
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


def set_speed(session, ifnames, speed):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if speed:
            speed = speed_human_to_yang(speed)
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(f"{xpath}/ethernet/config/speed", speed, no_apply=True)
        else:
            sr_op.delete_data(f"{xpath}/ethernet/config/speed", no_apply=True)
    sr_op.apply()


def set_breakout(session, ifnames, numch, speed):
    sr_op = sysrepo_wrap(session)
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
                xpath = ifxpath(ifname)
                xpath = f"{xpath}/ethernet/breakout/config"
                data = sr_op.get_data(xpath, "running")
                ly.xpath_get(data, xpath)
            except (sr.errors.SysrepoNotFoundError, KeyError):
                # If no configuration exists, no need to return error
                continue

            stdout.info("Sub Interfaces will be deleted")

            data = sr_op.get_data(XPATH, ds="operational")
            data = ly.xpath_get(data, XPATH)

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

            stdout.info("Existing configurations on parent interfaces will be flushed")
            for i in interfaces:
                sr_op.delete_data(ifxpath(i), no_apply=True)

        else:
            stdout.info("Existing configurations on parent interfaces will be flushed")
            xpath = ifxpath(ifname)
            sr_op.delete_data(xpath, no_apply=True)
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)
            sr_op.set_data(
                f"{xpath}/ethernet/breakout/config/num-channels",
                numch,
                no_apply=True,
            )
            sr_op.set_data(
                f"{xpath}/ethernet/breakout/config/channel-speed",
                speed_human_to_yang(speed),
                no_apply=True,
            )

    sr_op.apply()


def show(session, ifnames):
    sr_op = sysrepo_wrap(session)
    for ifname in ifnames:
        if len(ifnames) > 1:
            stdout.info(f"Interface {ifname}:")
        xpath = ifxpath(ifname)
        try:
            tree = sr_op.get_data(xpath, "operational")
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


class ShutdownCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")

        admin_status = "UP" if self.parent.name == "no" else "DOWN"
        set_admin_status(get_session(self), self.context.ifnames, admin_status)


class AdminStatusCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["up", "down"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_admin_status(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_admin_status(get_session(self), self.context.ifnames, line[0].upper())


class FECCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["none", "fc", "rs"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_fec(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_fec(get_session(self), self.context.ifnames, line[0].upper())


class SpeedCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return valid_speeds(get_session(self))

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_speed(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_speed(get_session(self), self.context.ifnames, line[0])


class InterfaceTypeOTNCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["otl", "foic"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_otn_interface_type(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_otn_interface_type(get_session(self), self.context.ifnames, line[0])


class InterfaceTypeCommand(Command):
    COMMAND_DICT = {"otn": InterfaceTypeOTNCommand}

    def arguments(self):
        if self.root.name != "no":
            return [
                "SR",
                "SR2",
                "SR4",
                "CR",
                "CR2",
                "CR4",
                "LR",
                "LR2",
                "LR4",
                "KR",
                "KR2",
                "KR4",
            ]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_interface_type(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_interface_type(get_session(self), self.context.ifnames, line[0])


class MTUCommand(Command):
    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_mtu(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                range_ = mtu_range(get_session(self))
                range_ = f" <range {range_}>" if range_ else ""
                raise InvalidInput(f"usage: mtu{range_}")
            if line[0].isdigit():
                mtu = int(line[0])
                set_mtu(get_session(self), self.context.ifnames, mtu)
            else:
                raise InvalidInput("Argument must be numbers and not letters")


class AutoNegoAdvertiseCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return valid_speeds(get_session(self))

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_auto_nego_adv_speed(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_auto_nego_adv_speed(get_session(self), self.context.ifnames, line[0])


class AutoNegoCommand(Command):
    COMMAND_DICT = {
        "enable": Command,
        "disable": Command,
        "advertise": AutoNegoAdvertiseCommand,
    }

    def arguments(self):
        if self.root.name != "no":
            return ["enable", "disable", "advertise"]
        return ["advertise"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_auto_nego(get_session(self), self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_auto_nego(get_session(self), self.context.ifnames, line[0] == "enable")


class BreakoutCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["2X50G", "2X20G", "4X25G", "4X10G"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_breakout(get_session(self), self.context.ifnames, None, None)
        else:
            valid_speed = ["50G", "20G", "10G", "25G"]
            usage = f'usage: {self.name_all()} [{"|".join(self.list())}]'
            if len(line) != 1:
                raise InvalidInput(usage)
            try:
                # Split values '2X50G', '2X20G', '4X25G', '4X10G' and validate
                input_values = line[0].split("X")
                if len(input_values) != 2 and (
                    input_values[0] != "2" or input_values[0] != "4"
                ):
                    raise InvalidInput(usage)
                if input_values[1] not in valid_speed:
                    raise InvalidInput(usage)
            except:
                raise InvalidInput(usage)
            set_breakout(
                get_session(self),
                self.context.ifnames,
                input_values[0],
                input_values[1],
            )


class InterfaceContext(Context):
    REGISTERED_COMMANDS = {}

    def __init__(self, parent, ifname):
        super().__init__(parent)
        self.session = self.root().conn.start_session()
        self.name = ifname
        ifnames = interface_names(self.session, ifname)

        if len(ifnames) == 0:
            raise InvalidInput(f"no interface found: {ifname}")
        elif len(ifnames) > 1:
            stdout.info(f"Selected interfaces: {ifnames}")

            @self.command()
            def selected(args):
                if len(args) != 0:
                    raise InvalidInput("usage: selected[cr]")
                stdout.info(", ".join(ifnames))

        self.ifnames = ifnames

        self.add_command("shutdown", ShutdownCommand, add_no=True)
        self.add_command("admin-status", AdminStatusCommand, add_no=True)
        self.add_command("fec", FECCommand, add_no=True)
        self.add_command(
            "speed",
            SpeedCommand,
            add_no=True,
            fuzzy=False,
        )
        self.add_command("interface-type", InterfaceTypeCommand, add_no=True)
        self.add_command("mtu", MTUCommand, add_no=True)
        self.add_command("auto-negotiate", AutoNegoCommand, add_no=True)
        self.add_command("breakout", BreakoutCommand, add_no=True)

        @self.command(parent.get_completer("show"), name="show")
        def show_(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                show(self.session, ifnames)

    def __str__(self):
        return "interface({})".format(self.name)


class InterfaceCounterCommand(Command):
    def arguments(self):
        return ["table"] + interface_names(get_session(self))

    def exec(self, line):
        ifnames = interface_names(get_session(self))
        table = False
        if len(line) == 1:
            if line[0] == "table":
                table = True
            else:
                try:
                    ptn = re.compile(line[0])
                except re.error:
                    raise InvalidInput(
                        f"failed to compile {line[0]} as a regular expression"
                    )
                ifnames = [i for i in ifnames if ptn.match(i)]
        elif len(line) > 1:
            for ifname in line:
                if ifname not in ifnames:
                    raise InvalidInput(f"Invalid interface {ifname}")
            ifnames = line

        show_counters(get_session(self), ifnames, table)


class Show(Command):
    COMMAND_DICT = {
        "brief": Command,
        "description": Command,
        "counters": InterfaceCounterCommand,
    }

    def __init__(self, context, parent, name, **options):
        super().__init__(context, parent, name, **options)

    def exec(self, line):
        if len(line) == 1:
            return show_interface(get_session(self), line[0])
        else:
            raise InvalidInput(self.usage())

    def usage(self):
        return (
            "usage:\n" f" {self.parent.name} {self.name} (brief|description|counters)"
        )


GlobalShowCommand.register_command(
    "interface", Show, when=ModelExists("goldstone-interfaces")
)


class ClearInterfaceGroupCommand(Command):
    COMMAND_DICT = {
        "counters": Command,
    }

    def exec(self, line):
        conn = self.context.root().conn
        with conn.start_session() as sess:
            if len(line) < 1 or line[0] not in ["counters"]:
                raise InvalidInput(self.usage())
            if len(line) == 1:
                if line[0] == "counters":
                    sess.rpc_send("/goldstone-interfaces:clear-counters", {})
                    stdout.info("Interface counters are cleared.\n")
            else:
                raise InvalidInput(self.usage())

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name} (counters)"


GlobalClearCommand.register_command(
    "interface", ClearInterfaceGroupCommand, when=ModelExists("goldstone-interfaces")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return run_conf(get_session(self))
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "interface", Run, when=ModelExists("goldstone-interfaces")
)


class TechSupport(Command):
    def exec(self, line):
        show_interface(get_session(self))
        self.parent.xpath_list.append("/goldstone-interfaces:interfaces")


TechSupportCommand.register_command(
    "interfaces", TechSupport, when=ModelExists("goldstone-interfaces")
)


class InterfaceCommand(Command):
    def arguments(self):
        return interface_names(get_session(self))

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <ifname>")
        if self.root.name == "no":
            sess = get_session(self)
            sr_op = sysrepo_wrap(sess)
            for name in interface_names(sess, line[0]):
                sr_op.delete_data(ifxpath(name), no_apply=True)
            sr_op.apply()
        else:
            return InterfaceContext(self.context, line[0])


Root.register_command(
    "interface",
    InterfaceCommand,
    when=ModelExists("goldstone-interfaces"),
    add_no=True,
    no_completion_on_exec=True,
)
