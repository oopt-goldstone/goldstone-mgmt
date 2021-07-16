import sys
import os
import re
import logging

from .base import InvalidInput, Completer
from .cli import GSObject as Object
import libyang as ly
import sysrepo as sr

from prompt_toolkit.document import Document
from prompt_toolkit.completion import (
    WordCompleter,
    Completion,
    NestedCompleter,
    FuzzyWordCompleter,
)
from .sonic import Sonic, sonic_defaults
from natsort import natsorted

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class Interface(Object):
    def __init__(self, conn, parent, ifname):
        super().__init__(parent)
        self.conn = conn
        self.session = conn.start_session()
        self.name = ifname
        try:
            ptn = re.compile(ifname)
        except re.error:
            raise InvalidInput(f"failed to compile {ifname} as a regular expression")
        self.sonic = Sonic(conn)
        iflist = [v["name"] for v in self.sonic.port.get_interface_list("operational")]

        self.ifnames = [i for i in iflist if ptn.match(i)]

        if len(self.ifnames) == 0:
            raise InvalidInput(f"no interface found: {ifname}")
        elif len(self.ifnames) > 1:
            stdout.info(f"Selected interfaces: {self.ifnames}")

            @self.command()
            def selected(args):
                if len(args) != 0:
                    raise InvalidInput("usage: selected[cr]")
                stdout.info(", ".join(self.ifnames))

        self.switchprt_dict = {
            "mode": {
                "trunk": {"vlan": WordCompleter(lambda: parent.get_vid())},
                "access": {"vlan": WordCompleter(lambda: parent.get_vid())},
            }
        }

        self.ufd_dict = {}

        for id in self.sonic.ufd.get_id():
            self.ufd_dict[id] = {"uplink": None, "downlink": None}

        self.no_dict = {
            "shutdown": None,
            "speed": None,
            "mtu": None,
            "switchport": self.switchprt_dict,
            "breakout": None,
            "interface-type": None,
            "auto-nego": None,
            "fec": None,
            "ufd": None,
            "portchannel": None,
        }
        self.fec_list = ["fc", "rs"]
        self.breakout_list = ["2X50G", "2X20G", "4X25G", "4X10G"]
        self.interface_type_list = [
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
        self.auto_nego_list = ["enable", "disable"]
        self.tagging_mode_list = ["trunk", "access"]

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(args):
            if len(args) < 1:
                raise InvalidInput("usage: {}".format(self.no_usage))
            if args[0] == "shutdown":
                for ifname in self.ifnames:
                    self.sonic.port.set_admin_status(ifname, "up")
            elif args[0] == "speed":
                for ifname in self.ifnames:
                    self.sonic.port.set_speed(
                        ifname, sonic_defaults.SPEED, config=False
                    )
            elif args[0] == "interface-type":
                for ifname in self.ifnames:
                    self.sonic.port.set_interface_type(
                        ifname, sonic_defaults.INTF_TYPE, config=False
                    )
            elif args[0] == "auto-nego":
                for ifname in self.ifnames:
                    self.sonic.port.set_auto_nego(ifname, "no", config=False)
            elif args[0] == "ufd":
                self.sonic.ufd.check_port(self.name)
            elif args[0] == "mtu":
                for ifname in self.ifnames:
                    self.sonic.port.set_mtu(ifname, None)
            elif args[0] == "switchport" and len(args) == 5:
                if args[1] != "mode" and args[2] not in self.tagging_mode_list:
                    raise InvalidInput(
                        "usage : no switchport mode trunk|access vlan <vid>"
                    )
                if args[3] != "vlan":
                    raise InvalidInput(
                        "usage : no switchport mode trunk|access vlan <vid>"
                    )
                if args[4].isdigit():
                    if args[4] in parent.get_vid():
                        for ifname in self.ifnames:
                            self.sonic.port.set_vlan_mem(
                                ifname, args[2], args[4], config=False
                            )
                    else:
                        raise InvalidInput("Entered vid does not exist")
                else:
                    raise InvalidInput("Entered <vid> must be numbers and not letters")
            elif args[0] == "breakout":
                for ifname in self.ifnames:
                    self.sonic.port.set_breakout(ifname, None, None)
            elif args[0] == "fec" and len(args) == 1:
                for ifname in self.ifnames:
                    self.sonic.port.set_fec(ifname, None)

            elif args[0] == "portchannel":
                self.sonic.pc.remove_interface(self.name)

            else:
                self.no_usage()

        @self.command(WordCompleter(self.fec_list))
        def fec(args):
            if len(args) != 1 or args[0] not in ["fc", "rs"]:
                raise InvalidInput("usages: fec <fc|rs>")
            for ifname in self.ifnames:
                self.sonic.port.set_fec(ifname, args[0])

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            for ifname in self.ifnames:
                self.sonic.port.set_admin_status(ifname, "down")

        @self.command()
        def speed(args):
            if len(args) != 1:
                raise InvalidInput("usage: speed 40000|100000")
            speed = args[0]
            if speed.isdigit():
                for ifname in self.ifnames:
                    self.sonic.port.set_speed(ifname, speed)
            else:
                raise InvalidInput("Argument must be numbers and not letters")

        @self.command()
        def mtu(args):
            if len(args) != 1:
                range_ = self.sonic.port.mtu_range()
                range_ = f" <range {range_}>" if range_ else ""
                raise InvalidInput(f"usage: mtu{range_}")
            if args[0].isdigit():
                mtu = int(args[0])
                for ifname in self.ifnames:
                    self.sonic.port.set_mtu(ifname, mtu)
            else:
                raise InvalidInput("Argument must be numbers and not letters")

        @self.command(NestedCompleter.from_nested_dict(self.switchprt_dict))
        def switchport(args):
            if len(args) != 4:
                raise InvalidInput("usage: switchport mode (trunk|access) vlan <vid>")

            if args[0] != "mode" or args[1] not in self.tagging_mode_list:
                raise InvalidInput("usage: switchport mode (trunk|access) vlan <vid>")

            if args[2] != "vlan":
                raise InvalidInput("usage: switchport mode (trunk|access) vlan <vid>")

            if not args[3].isdigit():
                raise InvalidInput("argument vid must be numbers and not letters")

            if args[3] not in parent.get_vid():
                raise InvalidInput("Entered vid does not exist")

            for ifname in self.ifnames:
                self.sonic.port.set_vlan_mem(ifname, args[1], args[3])

        @self.command(WordCompleter(self.interface_type_list))
        def interface_type(args):
            valid_args = self.interface_type_list
            invalid_input_str = (
                f'usage: interface-type [{"|".join(self.interface_type_list)}]'
            )
            if len(args) != 1:
                raise InvalidInput(invalid_input_str)
            if args[0] not in valid_args:
                raise InvalidInput(invalid_input_str)
            for ifname in self.ifnames:
                self.sonic.port.set_interface_type(ifname, args[0])

        @self.command(WordCompleter(self.auto_nego_list))
        def auto_nego(args):
            invalid_input_str = f'usage: auto_nego [{"|".join(self.auto_nego_list)}]'
            if len(args) != 1 or args[0] not in self.auto_nego_list:
                raise InvalidInput(invalid_input_str)
            else:
                for ifname in self.ifnames:
                    if args[0] == "enable":
                        self.sonic.port.set_auto_nego(ifname, "yes")
                    if args[0] == "disable":
                        self.sonic.port.set_auto_nego(ifname, "no")

        @self.command(WordCompleter(self.breakout_list))
        def breakout(args):
            valid_speed = ["50G", "20G", "10G", "25G"]
            invalid_input_str = f'usage: breakout [{"|".join(self.breakout_list)}]'
            if len(args) != 1:
                raise InvalidInput(invalid_input_str)
            try:
                # Split values '2X50G', '2X20G', '4X25G', '4X10G' and validate
                input_values = args[0].split("X")
                if len(input_values) != 2 and (
                    input_values[0] != "2" or input_values[0] != "4"
                ):
                    raise InvalidInput(invalid_input_str)
                if input_values[1] not in valid_speed:
                    raise InvalidInput(invalid_input_str)
            except:
                raise InvalidInput(invalid_input_str)

            for ifname in self.ifnames:
                self.sonic.port.set_breakout(ifname, input_values[0], input_values[1])

        @self.command(NestedCompleter.from_nested_dict(self.ufd_dict))
        def ufd(args):
            if len(args) != 2 or (args[1] != "uplink" and args[1] != "downlink"):
                raise InvalidInput("usage: ufd <ufdid> <uplink|downlink>")

            for ifname in self.ifnames:
                self.sonic.ufd.add_port(args[0], ifname, args[1])

        @self.command()
        def portchannel(args):
            if len(args) != 1:
                raise InvalidInput("usage: portchannel <portchannel_id>")
            for ifname in self.ifnames:
                self.sonic.pc.add_interface(args[0], ifname)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            for ifname in self.ifnames:
                if len(self.ifnames) > 1:
                    stdout.info(f"Interface {ifname}:")
                self.sonic.port.show(ifname)

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        stderr.info(f'usage: no [{"|".join(no_keys)}]')

    def __str__(self):
        return "interface({})".format(self.name)


class Vlan(Object):
    def __init__(self, conn, parent, vid):
        self.vid = vid
        super().__init__(parent)
        self.sonic = Sonic(conn)
        self.sonic.vlan.create(self.vid)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.sonic.vlan.show(self.vid)

    def __str__(self):
        return "vlan({})".format(self.vid)


class Ufd(Object):
    def __init__(self, conn, parent, id):
        self.id = id
        super().__init__(parent)
        self.sonic = Sonic(conn)
        self.sonic.ufd.create(self.id)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.sonic.ufd.show(self.id)

    def __str__(self):
        return "ufd({})".format(self.id)


class Portchannel(Object):
    def __init__(self, conn, parent, id):
        self.id = id
        super().__init__(parent)
        self.sonic = Sonic(conn)
        self.sonic.pc.create(self.id)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.sonic.pc.show(self.id)

    def __str__(self):
        return "portchannel({})".format(self.id)
