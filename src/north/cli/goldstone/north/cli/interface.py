from .base import InvalidInput
from .cli import (
    Command,
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    GlobalClearCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
from tabulate import tabulate
from natsort import natsorted
import re
import logging
import base64
import struct


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


def static_macsec_key_to_yang(key):
    v = line[0].split(",")
    if len(v) != 4:
        return None

    try:
        v = [int(i, 0) for i in v]
    except ValueError:
        return None

    key = struct.pack("IIII", *v)
    return base64.b64encode(key).decode()


def static_macsec_key_to_human(key):
    key = struct.unpack("IIII", base64.b64decode(key))
    key = ",".join(f"0x{i:08x}" for i in key)
    return key


def breakout_yang_to_human(breakout):
    numch = breakout["num-channels"]
    speed = breakout["channel-speed"]
    speed = speed_yang_to_human(speed)
    return f"{numch}X{speed}"


XPATH = "/goldstone-interfaces:interfaces/interface"


def ifxpath(ifname):
    return f"{XPATH}[name='{ifname}']"


def interface_names(session, ptn=None):
    data = session.get_operational(f"{XPATH}/name", [])

    if ptn:
        try:
            ptn = re.compile(ptn)
        except re.error:
            raise InvalidInput(f"failed to compile {ptn} as a regular expression")
        f = ptn.match
    else:
        f = lambda _: True
    return natsorted(v for v in data if f(v))


def get_interface_list(session, datastore):
    imp = datastore == "operational"
    interfaces = session.get(XPATH, [], ds=datastore, include_implicit_defaults=imp)
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
    for ifname in ifnames:
        if len(ifnames) > 1:
            if not table:
                stdout.info(f"Interface {ifname}:")

        xpath = f"{XPATH}[name='{ifname}']/state/counters"
        data = session.get_operational(xpath, one=True)
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
            if "static-macsec" in ethernet:
                config = ethernet["static-macsec"].get("config", {})
                key = config.get("key")
                if key:
                    key = static_macsec_key_to_human(key)
                    stdout.info(f"  static-macsec-key {key}")

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
    xpath = "/goldstone-uplink-failure-detection:ufd-groups"
    ufd = {}
    ufd_list = session.get(f"{xpath}/ufd-group")
    if ufd_list == None:
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
    xpath = "/goldstone-portchannel:portchannel"
    pc = {}
    pc_list = session.get(f"{xpath}/portchannel-group")
    if pc_list == None:
        return {}

    for data in pc_list:
        try:
            for intf in data["config"]["interface"]:
                pc[intf] = {"pc-id": data["portchannel-id"]}
        except:
            pass

    return pc


def _set(session, ifnames, attr, value):
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            session.set(f"{xpath}/config/name", ifname)
            session.set(f"{xpath}/{attr}", value)
        else:
            session.delete(f"{xpath}/{attr}")
    session.apply()


def set_admin_status(session, ifnames, value):
    return _set(session, ifnames, "config/admin-status", value)


def set_fec(session, ifnames, value):
    return _set(session, ifnames, "ethernet/config/fec", value)


def set_mtu(session, ifnames, value):
    return _set(session, ifnames, "ethernet/config/mtu", value)


def set_speed(session, ifnames, speed):
    return _set(
        session,
        ifnames,
        "ethernet/config/speed",
        speed_human_to_yang(speed) if speed else None,
    )


def set_auto_nego(session, ifnames, value):
    return _set(session, ifnames, "ethernet/auto-negotiate/config/enabled", value)


def set_auto_nego_adv_speed(session, ifnames, speeds):
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        session.delete(
            f"{xpath}/ethernet/auto-negotiate/config/advertised-speeds",
        )
        if speeds:
            session.set(f"{xpath}/config/name", ifname)
            for speed in speeds.split(","):
                session.set(
                    f"{xpath}/ethernet/auto-negotiate/config/advertised-speeds",
                    speed_human_to_yang(speed),
                )
    session.apply()


def set_interface_type(session, ifnames, value):
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            session.set(f"{xpath}/config/name", ifname)
            session.set(f"{xpath}/config/interface-type", "IF_ETHERNET")
            session.set(f"{xpath}/ethernet/config/interface-type", value)
            session.delete(f"{xpath}/otn")
        else:
            session.delete(f"{xpath}/ethernet/config/interface-type")
            session.delete(f"{xpath}/config/interface-type")
    session.apply()


def set_otn_interface_type(session, ifnames, value):
    for ifname in ifnames:
        xpath = ifxpath(ifname)
        if value:
            session.set(f"{xpath}/config/name", ifname)
            session.set(f"{xpath}/config/interface-type", "IF_OTN")
            session.set(f"{xpath}/otn/config/mfi-type", value.upper())
            session.delete(f"{xpath}/ethernet/config/interface-type")
        else:
            session.delete(f"{xpath}/otn")
            session.delete(f"{xpath}/config/interface-type")
    session.apply()


def mtu_range(session):
    xpath = "/goldstone-interfaces:interfaces"
    xpath += "/goldstone-interfaces:interface"
    xpath += "/goldstone-interfaces:ethernet"
    xpath += "/goldstone-interfaces:config"
    xpath += "/goldstone-interfaces:mtu"
    return session.find_node(xpath).range()


def valid_speeds(session):
    xpath = "/goldstone-interfaces:interfaces"
    xpath += "/goldstone-interfaces:interface"
    xpath += "/goldstone-interfaces:ethernet"
    xpath += "/goldstone-interfaces:config"
    xpath += "/goldstone-interfaces:speed"
    node = session.find_node(xpath)
    # SPEED_10G => 10G
    v = [e[0].replace("SPEED_", "") for e in node.enums()]
    return v[1:]  # remove SPEED_UNKNOWN


def valid_eth_if_type(session):
    xpath = "/goldstone-interfaces:interfaces"
    xpath += "/goldstone-interfaces:interface"
    xpath += "/goldstone-interfaces:ethernet"
    xpath += "/goldstone-interfaces:config"
    xpath += "/goldstone-interfaces:interface-type"
    return (e[0] for e in session.find_node(xpath).enums())


def set_breakout(session, ifnames, numch, speed):
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
            xpath = ifxpath(ifname)
            xpath = f"{xpath}/ethernet/breakout/config"
            data = session.get(xpath)
            if data == None:
                # If no configuration exists, no need to return error
                continue

            stdout.info("Sub Interfaces will be deleted")

            data = session.get_operational(XPATH, [])

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
                session.delete(ifxpath(i))

        else:
            stdout.info("Existing configurations on parent interfaces will be flushed")
            xpath = ifxpath(ifname)
            session.delete(xpath)
            session.set(f"{xpath}/config/name", ifname)
            session.set(
                f"{xpath}/ethernet/breakout/config/num-channels",
                numch,
            )
            session.set(
                f"{xpath}/ethernet/breakout/config/channel-speed",
                speed_human_to_yang(speed),
            )

    session.apply()


def show(session, ifnames):
    for ifname in ifnames:
        if len(ifnames) > 1:
            stdout.info(f"Interface {ifname}:")
        xpath = ifxpath(ifname)
        data = session.get_operational(xpath, one=True)
        if data == None:
            if len(ifnames) > 1:
                stdout.info("interface not found")
                continue
            else:
                raise InvalidInput("interface not found")

        logger.debug(f"data: {data}")

        rows = []

        def add_to_rows(field, v, f=lambda v: v):
            if v == None:
                return
            v = v.get(field)
            if v == None:
                return
            v = f(v)
            rows.append((field, v))
            return v

        config = data.get("config")
        state = data.get("state")
        add_to_rows("name", config)
        add_to_rows("admin-status", state, lambda v: v.lower())
        add_to_rows("oper-status", state, lambda v: v.lower())
        add_to_rows("alias", state)
        add_to_rows("lanes", state)
        #        add_to_rows("interface-type", config, lambda v: v.lower().replace("if_", ""))

        ethernet = data.get("ethernet", {})
        state = ethernet.get("state")
        add_to_rows("speed", state, speed_yang_to_human)
        add_to_rows("fec", state, lambda v: v.lower())
        add_to_rows("mtu", state)
        add_to_rows("interface-type", state)

        breakout = ethernet.get("breakout", {})
        state = breakout.get("state")
        add_to_rows("breakout", state, breakout_yang_to_human)
        add_to_rows("parent", state)

        autonego = ethernet.get("auto-negotiate", {})
        state = autonego.get("state")
        add_to_rows("auto-negotiate", state, lambda v: "enabled" if v else "disabled")
        add_to_rows(
            "advertised-speeds",
            state,
            lambda v: ",".join(speed_yang_to_human(e) for e in v),
        )

        vlan = ethernet.get("switched-vlan", {})
        state = vlan.get("state")
        v = add_to_rows("vlan-mode", state, lambda v: v.lower())
        if v == "trunk":
            add_to_rows("trunk-vlans", state, lambda v: ", ".join(v))
        elif v == "access":
            add_to_rows("access-vlan", state)

        pcs = ethernet.get("pcs", {})
        state = pcs.get("state")
        add_to_rows("pcs-status", state, lambda v: ", ".join(v))
        add_to_rows("serdes-status", state, lambda v: ", ".join(v))

        otn = data.get("otn", {})
        state = otn.get("state")
        add_to_rows("mfi-type", state, lambda v: v.lower())
        state = data.get("state")
        add_to_rows("is-connected", state, lambda v: "true" if v else "false")

        macsec = ethernet.get("static-macsec", {})
        state = macsec.get("state", {})
        key = state.get("key")
        if key:
            rows.append(("static-macsec-key", static_macsec_key_to_human(key)))

        stdout.info(tabulate(rows))


class ShutdownCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")

        admin_status = "UP" if self.parent.name == "no" else "DOWN"
        set_admin_status(self.conn, self.context.ifnames, admin_status)


class AdminStatusCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["up", "down"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_admin_status(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_admin_status(self.conn, self.context.ifnames, line[0].upper())


class FECCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["none", "fc", "rs"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_fec(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_fec(self.conn, self.context.ifnames, line[0].upper())


class SpeedCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return valid_speeds(self.conn)

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_speed(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_speed(self.conn, self.context.ifnames, line[0])


class InterfaceTypeOTNCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["otl", "foic"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_otn_interface_type(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_otn_interface_type(self.conn, self.context.ifnames, line[0])


class InterfaceTypeCommand(Command):
    COMMAND_DICT = {"otn": InterfaceTypeOTNCommand}

    def arguments(self):
        if self.root.name != "no":
            return valid_eth_if_type(self.conn)

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_interface_type(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_interface_type(self.conn, self.context.ifnames, line[0])


class MTUCommand(Command):
    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_mtu(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                range_ = mtu_range(self.conn)
                range_ = f" <range {range_}>" if range_ else ""
                raise InvalidInput(f"usage: mtu{range_}")
            if line[0].isdigit():
                mtu = int(line[0])
                set_mtu(self.conn, self.context.ifnames, mtu)
            else:
                raise InvalidInput("Argument must be numbers and not letters")


class AutoNegoAdvertiseCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return valid_speeds(self.conn)

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_auto_nego_adv_speed(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_auto_nego_adv_speed(self.conn, self.context.ifnames, line[0])


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
            set_auto_nego(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_auto_nego(self.conn, self.context.ifnames, line[0] == "enable")


class BreakoutCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["2X50G", "2X20G", "4X25G", "4X10G"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_breakout(self.conn, self.context.ifnames, None, None)
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
                self.conn,
                self.context.ifnames,
                input_values[0],
                input_values[1],
            )


class StaticMACSECCommand(Command):
    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            for name in self.context.ifnames:
                self.conn.delete(
                    f"{ifxpath(name)}/ethernet/goldstone-static-macsec:static-macsec"
                )
            self.conn.apply()
        else:
            if len(line) != 1:
                raise InvalidInput(self.usage())

            key = static_macsec_key_to_yang(line[0])
            if not key:
                raise InvalidInput(self.usage())

            attr = "ethernet/goldstone-static-macsec:static-macsec/config/key"
            _set(self.conn, self.context.ifnames, attr, key)

    def usage(self):
        return f"usage: {self.name_all()} <static-macsec-key> (<uint32>,<uint32>,<uint32>,<uint32>)"


class InterfaceContext(Context):
    REGISTERED_COMMANDS = {}

    def __init__(self, parent, ifname):
        super().__init__(parent)
        self.name = ifname
        ifnames = interface_names(self.conn, ifname)

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

        if ModelExists("goldstone-static-macsec")(self):
            self.add_command("static-macsec-key", StaticMACSECCommand, add_no=True)

        @self.command(parent.get_completer("show"), name="show")
        def show_(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                show(self.conn, ifnames)

    def __str__(self):
        return "interface({})".format(self.name)


class InterfaceMACSECCounterCommand(Command):
    def arguments(self):
        return [
            n
            for n in interface_names(self.conn)
            if self.conn.get(
                f"{ifxpath(n)}/ethernet/goldstone-static-macsec:static-macsec/config/key"
            )
        ]

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <interface name>")
        xpath = f"{ifxpath(line[0])}/ethernet/goldstone-static-macsec:static-macsec/state/counters"
        data = self.conn.get_operational(xpath, one=True)
        if not data:
            raise InvalidInput(f"no static-macsec stats for {line[0]}")

        stdout.info("Ingress SA:")
        stdout.info(tabulate([(k, v) for k, v in data["ingress"]["sa"].items()]))
        stdout.info("Ingress SecY:")
        stdout.info(tabulate([(k, v) for k, v in data["ingress"]["secy"].items()]))
        stdout.info("Ingress Channel:")
        stdout.info(tabulate([(k, v) for k, v in data["ingress"]["channel"].items()]))

        stdout.info("Egress SA:")
        stdout.info(tabulate([(k, v) for k, v in data["egress"]["sa"].items()]))
        stdout.info("Egress SecY:")
        stdout.info(tabulate([(k, v) for k, v in data["egress"]["secy"].items()]))
        stdout.info("Egress Channel:")
        stdout.info(tabulate([(k, v) for k, v in data["egress"]["channel"].items()]))


class InterfaceCounterCommand(Command):
    def __init__(self, context, parent, name, **options):
        super().__init__(context, parent, name, **options)

        if ModelExists("goldstone-static-macsec")(self):
            self.add_command("static-macsec", InterfaceMACSECCounterCommand)

    def arguments(self):
        return ["table"] + interface_names(self.conn)

    def exec(self, line):
        table = False
        ptn = None
        if len(line) == 1 and line[0] != "table":
            ptn = line[0]
        ifnames = interface_names(self.conn, ptn)

        if len(ifnames) == 0:
            raise InvalidInput("no interface found")

        if len(line) == 1 and line[0] == "table":
            table = True
        elif len(line) > 1:
            for ifname in line:
                if ifname not in ifnames:
                    raise InvalidInput(f"Invalid interface {ifname}")
            ifnames = line

        show_counters(self.conn, ifnames, table)


class Show(Command):
    COMMAND_DICT = {
        "brief": Command,
        "description": Command,
        "counters": InterfaceCounterCommand,
    }

    def exec(self, line):
        if len(line) == 1:
            return show_interface(self.conn, line[0])
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
        if len(line) == 1 and line[0] == "counters":
            self.conn.rpc("/goldstone-interfaces:clear-counters", {})
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
            return run_conf(self.conn)
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "interface", Run, when=ModelExists("goldstone-interfaces")
)


class TechSupport(Command):
    def exec(self, line):
        show_interface(self.conn)
        self.parent.xpath_list.append("/goldstone-interfaces:interfaces")


TechSupportCommand.register_command(
    "interfaces", TechSupport, when=ModelExists("goldstone-interfaces")
)


class InterfaceCommand(Command):
    def arguments(self):
        return interface_names(self.conn)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <ifname>")
        if self.root.name == "no":
            for name in interface_names(self.conn, line[0]):
                self.conn.delete(ifxpath(name))
            self.conn.apply()
        else:
            return InterfaceContext(self.context, line[0])


Root.register_command(
    "interface",
    InterfaceCommand,
    when=ModelExists("goldstone-interfaces"),
    add_no=True,
    no_completion_on_exec=True,
)
