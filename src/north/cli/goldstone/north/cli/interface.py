from .base import InvalidInput
from .cli import (
    Command,
    ConfigCommand,
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    GlobalClearCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
from .util import dig_dict

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
    v = key.split(",")
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


def show_detail_counters(session, ifnames):
    for ifname in ifnames:
        if len(ifnames) > 1:
            stdout.info(f"Interface {ifname}:")

        xpath = f"{ifxpath(ifname)}/ethernet/state/counters"
        data = session.get_operational(xpath, one=True)
        if not data:
            msg = f"no Ethernet counters for {ifname}"
            if len(ifnames) == 1:
                raise InvalidInput(msg)
            else:
                stderr.info(msg)
                continu

        stdout.info("Rx:")
        stdout.info(
            tabulate(
                [
                    (k[3:], data.get(k, "-"))  # remove 'rx-' prefix
                    for k in [
                        "rx-octets-all",
                        "rx-octets-good",
                        "rx-pkts-all",
                        "rx-pkts-good",
                        "rx-pkts-err",
                        "rx-pkts-long",
                        "rx-pkts-crc-err",
                        "rx-pkts-all-crc-err",
                        "rx-pkts-jabber",
                        "rx-pkts-stomped",
                        "rx-pkts-vlan",
                        "rx-pkts-mac-ctrl",
                        "rx-pkts-broadcast",
                        "rx-pkts-multicast",
                        "rx-pkts-unicast",
                        "rx-pkts-0-63-b",
                        "rx-pkts-64-b",
                        "rx-pkts-65-127-b",
                        "rx-pkts-128-255-b",
                        "rx-pkts-256-511-b",
                        "rx-pkts-512-1023-b",
                        "rx-pkts-1024-1518-b",
                        "rx-pkts-1519-2047-b",
                        "rx-pkts-2048-4095-b",
                        "rx-pkts-4096-8191-b",
                        "rx-pkts-8192-max-b",
                        "rx-err-blk",
                        "rx-valid-err-blk",
                        "rx-unknown-err-blk",
                        "rx-inv-err-blk",
                        "rx-pkts-pause",
                        "rx-pkts-pause-pfc0",
                        "rx-pkts-pfc1",
                        "rx-pkts-pfc2",
                        "rx-pkts-pfc3",
                        "rx-pkts-pfc4",
                        "rx-pkts-pfc5",
                        "rx-pkts-pfc6",
                        "rx-pkts-pfc7",
                        "rx-pkts-link-pause",
                    ]
                ]
            )
        )

        stdout.info("Tx:")
        stdout.info(
            tabulate(
                [
                    (k[3:], data.get(k, "-"))  # remove 'tx-' prefix
                    for k in [
                        "tx-octets-all",
                        "tx-octets-good",
                        "tx-pkts-all",
                        "tx-pkts-good",
                        "tx-pkts-err",
                        "tx-pkts-unicast",
                        "tx-pkts-multicast",
                        "tx-pkts-broadcast",
                        "tx-pkts-pause",
                        "tx-pkts-pause-pfc0",
                        "tx-pkts-pfc1",
                        "tx-pkts-pfc2",
                        "tx-pkts-pfc3",
                        "tx-pkts-pfc4",
                        "tx-pkts-pfc5",
                        "tx-pkts-pfc6",
                        "tx-pkts-pfc7",
                        "tx-pkts-vlan",
                        "tx-pkts-0-63-b",
                        "tx-pkts-64-b",
                        "tx-pkts-65-127-b",
                        "tx-pkts-128-255-b",
                        "tx-pkts-256-511-b",
                        "tx-pkts-512-1023-b",
                        "tx-pkts-1024-1518-b",
                        "tx-pkts-1519-2047-b",
                        "tx-pkts-2048-4095-b",
                        "tx-pkts-4096-8191-b",
                        "tx-pkts-8192-max-b",
                        "tx-pkts-drained",
                        "tx-pkts-jabbered",
                        "tx-pkts-padded",
                        "tx-pkts-trunc",
                    ]
                ]
            )
        )


def show_pcs_counters(session, ifnames):
    for ifname in ifnames:
        if len(ifnames) > 1:
            stdout.info(f"Interface {ifname}:")

        xpath = f"{ifxpath(ifname)}/ethernet/pcs/state/counters"
        data = session.get_operational(xpath, one=True)
        if not data:
            msg = f"no PCS counters for {ifname}"
            if len(ifnames) == 1:
                raise InvalidInput(msg)
            else:
                stderr.info(msg)
                continu

        stdout.info(
            tabulate(
                [
                    (k, data.get(k, "-"))
                    for k in [
                        "bip-error",
                        "virtual-lane-loss",
                        "serdes-lane-fec-symbol-error",
                        "corrected-fec-error",
                        "uncorrected-fec-error",
                        "fec-symbol-error",
                        "fc-fec-corrected-error",
                        "fc-fec-uncorrected-error",
                        "sync-header-error",
                        "hiber",
                        "test-pattern-error",
                        "loss-of-block-lock",
                        "ber-elapsed-sec",
                        "ber-elapsed-usec",
                    ]
                ]
            )
        )


def show_macsec_counters(session, ifnames):
    for ifname in ifnames:
        if len(ifnames) > 1:
            stdout.info(f"Interface {ifname}:")

        xpath = f"{ifxpath(ifname)}/ethernet/goldstone-static-macsec:static-macsec/state/counters"
        data = session.get_operational(xpath, one=True)
        if not data:
            msg = f"no static-macsec stats for {ifname}"
            if len(ifnames) == 1:
                raise InvalidInput(msg)
            else:
                stderr.info(msg)
                continue

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


def set_pin_mode(session, ifnames, value):
    return _set(session, ifnames, "config/pin-mode", value)


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


def valid_tx_timing_mode(session):
    xpath = "/goldstone-interfaces:interfaces"
    xpath += "/goldstone-interfaces:interface"
    xpath += "/goldstone-interfaces:ethernet"
    xpath += "/goldstone-synce:synce"
    xpath += "/goldstone-synce:config"
    xpath += "/goldstone-synce:tx-timing-mode"
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

        def add_to_rows(field, v, f=lambda v: v, alt_field=None):
            if v == None:
                return
            v = v.get(field)
            if v == None:
                return
            v = f(v)
            rows.append((alt_field if alt_field else field, v))
            return v

        config = data.get("config")
        state = data.get("state")
        add_to_rows("name", config)
        add_to_rows("admin-status", state, lambda v: v.lower())
        add_to_rows("oper-status", state, lambda v: v.lower())
        add_to_rows("pin-mode", state, lambda v: v.lower())
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
        add_to_rows(
            "enabled", state, lambda v: "enabled" if v else "disabled", "auto-negotiate"
        )
        add_to_rows(
            "advertised-speeds",
            state,
            lambda v: ", ".join(speed_yang_to_human(e) for e in v),
        )
        add_to_rows(
            "status", state, lambda v: ", ".join(e for e in v), "auto-negotiate status"
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

        synce = ethernet.get("synce", {})
        state = synce.get("state", {})
        add_to_rows("tx-timing-mode", state)
        add_to_rows("current-tx-timing-mode", state)

        stdout.info(tabulate(rows))


class ShutdownCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")

        admin_status = "UP" if self.parent.name == "no" else "DOWN"
        set_admin_status(self.conn, self.context.ifnames, admin_status)


def eth_config(data, key):
    return dig_dict(data, ["ethernet", "config", key])


class AdminStatusCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        config = data.get("config")
        if not config:
            return
        v = config.get("admin-status")
        if v == "DOWN":
            return "admin-status down"
        elif v == "UP":
            return "admin-status up"


class PinModeCommand(ConfigCommand):
    def arguments(self):
        if self.root.name != "no":
            return ["pam4", "nrz"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_pin_mode(self.conn, self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_pin_mode(self.conn, self.context.ifnames, line[0].upper())

    @staticmethod
    def to_command(conn, data):
        config = data.get("config")
        if not config:
            return
        v = config.get("pin-mode")
        if v == "PAM4":
            return "pin-mode pam4"
        elif v == "NRZ":
            return "pin-mode nrz"


class FECCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        fec = eth_config(data, "fec")
        if fec:
            return f"fec {fec.lower()}"


class SpeedCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        speed = eth_config(data, "speed")
        if speed:
            return f"speed {speed_yang_to_human(speed)}"


class InterfaceTypeOTNCommand(ConfigCommand):
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


class InterfaceTypeCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        otn = data.get("otn")
        if otn:
            mfi = otn.get("config", {}).get("mfi-type")
            if mfi:
                return f"interface-type otn {mfi.lower()}"

        iftype = eth_config(data, "interface-type")
        if iftype:
            return f"interface-type {iftype}"


class MTUCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        mtu = eth_config(data, "mtu")
        if mtu:
            return f"mtu {mtu}"


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


class AutoNegoCommand(ConfigCommand):
    COMMAND_DICT = {
        "advertise": AutoNegoAdvertiseCommand,
    }

    def arguments(self):
        if self.root.name != "no":
            return ["enable", "disable"]

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

    @staticmethod
    def to_command(conn, data):
        config = dig_dict(data, ["ethernet", "auto-negotiate", "config"])
        if not config:
            return None
        v = config.get("enabled")
        lines = []
        if v:
            value = "enable" if v else "disable"
            lines.append(f"auto-negotiate {value}")

        v = config.get("advertised-speeds")
        if v:
            v = ",".join(speed_yang_to_human(s) for s in v)
            lines.append(f"auto-negotiate advatise {v}")

        return lines


class BreakoutCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        config = dig_dict(data, ["ethernet", "breakout", "config"])
        if not config:
            return None
        return "breakout " + breakout_yang_to_human(config)


class StaticMACSECCommand(ConfigCommand):
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

    @staticmethod
    def to_command(conn, data):
        key = dig_dict(data, ["ethernet", "static-macsec", "config", "key"])
        if key:
            key = static_macsec_key_to_human(key)
            return f"static-macsec-key {key}"


class TXTimingModeCommand(ConfigCommand):
    def arguments(self):
        if self.root.name != "no":
            return valid_tx_timing_mode(self.conn)

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            for name in self.context.ifnames:
                self.conn.delete(
                    f"{ifxpath(name)}/ethernet/goldstone-synce:synce/config/tx-timing-mode"
                )
            self.conn.apply()
        else:
            if len(line) != 1:
                raise InvalidInput(self.usage())

            attr = "ethernet/goldstone-synce:synce/config/tx-timing-mode"
            _set(self.conn, self.context.ifnames, attr, line[0])

    def usage(self):
        return f"usage: {self.name_all()} [{'|'.join(self.list())}]"

    @staticmethod
    def to_command(conn, data):
        mode = dig_dict(data, ["ethernet", "synce", "config", "tx-timing-mode"])
        if mode:
            return f"tx-timing-mode {mode}"


class InterfaceDetailCounterCommand(Command):
    def arguments(self):
        if self.parent.parent.name == "interface":
            return interface_names(self.conn)

    def exec(self, line):
        if self.parent.parent.name == "interface":
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <interface name>")
            ifnames = [line[0]]
        else:
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            ifnames = self.context.ifnames

        show_detail_counters(self.conn, ifnames)


class InterfacePCSCounterCommand(Command):
    def arguments(self):
        if self.parent.parent.name == "interface":
            return interface_names(self.conn)

    def exec(self, line):
        if self.parent.parent.name == "interface":
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <interface name>")
            ifnames = [line[0]]
        else:
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            ifnames = self.context.ifnames

        show_pcs_counters(self.conn, ifnames)


class InterfaceMACSECCounterCommand(Command):
    def arguments(self):
        if self.parent.parent.name == "interface":
            return [
                n
                for n in interface_names(self.conn)
                if self.conn.get(
                    f"{ifxpath(n)}/ethernet/goldstone-static-macsec:static-macsec/config/key"
                )
            ]

    def exec(self, line):
        if self.parent.parent.name == "interface":
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <interface name>")
            ifnames = [line[0]]
        else:
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            ifnames = self.context.ifnames

        show_macsec_counters(self.conn, ifnames)


class InterfaceCounterCommand(Command):
    def __init__(self, context, parent, name, **options):
        super().__init__(context, parent, name, **options)

        self.add_command("pcs", InterfacePCSCounterCommand)
        self.add_command("detail", InterfaceDetailCounterCommand)

        if ModelExists("goldstone-static-macsec")(self):
            self.add_command("static-macsec", InterfaceMACSECCounterCommand)

    def arguments(self):
        if self.parent.name == "interface":
            return ["table"] + interface_names(self.conn)
        else:
            return ["table"]

    def exec(self, line):
        table = False
        ptn = None

        if self.parent.name == "interface":
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
        else:
            if (len(line) == 1 and line[0] != "table") or len(line) > 1:
                raise InvalidInput("usage: {self.name_all()} [table]")

            if len(line) == 1:
                table = line[0] == "table"

            ifnames = self.context.ifnames

        show_counters(self.conn, ifnames, table)


class InterfaceShowCommand(Command):
    COMMAND_DICT = {"counters": InterfaceCounterCommand}

    def exec(self, line):
        if len(line) != 0:
            return self.context.root().exec(f"show {' '.join(line)}")
        else:
            show(self.conn, self.context.ifnames)


class InterfaceContext(Context):
    REGISTERED_COMMANDS = {}

    def __init__(self, parent, ifname):
        super().__init__(parent)
        self.name = ifname

        if ifname:  # ifname == None when running config
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
        self.add_command("pin-mode", PinModeCommand, add_no=True)
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

        if ModelExists("goldstone-synce")(self):
            self.add_command("tx-timing-mode", TXTimingModeCommand, add_no=True)

        self.add_command(
            "show",
            InterfaceShowCommand,
            additional_completer=parent.get_completer("show"),
        )

    def __str__(self):
        return "interface({})".format(self.name)

    def run_conf(self):
        interface_list = get_interface_list(self.conn, "running")
        if not interface_list:
            return

        for data in interface_list:
            ifname = data.get("name")
            stdout.info(f"interface {ifname}")

            registered = []

            def gen(cmd):
                if isinstance(cmd, type) and issubclass(cmd, ConfigCommand):
                    lines = cmd.to_command(self.conn, data)
                    if not lines:
                        return

                    if type(lines) == str:
                        lines = [lines]

                    for line in lines:
                        stdout.info("  " + line)

            for k, (cmd, options) in self._command.subcommand_dict.items():
                if "registered" in options:
                    registered.append(cmd)
                    continue
                gen(cmd)

            for cmd in registered:
                gen(cmd)

            stdout.info("  quit")
            stdout.info("!")

        stdout.info("!")


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
            return InterfaceContext(self.context, None).run_conf()
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
