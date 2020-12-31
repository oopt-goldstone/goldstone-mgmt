import sys
import os
import re

from .base import InvalidInput, Completer
from .cli import GSObject as Object
import libyang as ly
import sysrepo as sr

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, NestedCompleter
from .sonic import Sonic, sonic_defaults


class Interface_CLI(Object):
    def __init__(self, conn, parent, ifname):
        super().__init__(parent)
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
            print(f"Selected interfaces: {self.ifnames}")

            @self.command()
            def selected(args):
                if len(args) != 0:
                    raise InvalidInput("usage: selected[cr]")
                print(", ".join(self.ifnames))

        self.switchprt_dict = {
            "mode": {
                "trunk": {"vlan": WordCompleter(lambda: parent.get_vid())},
                "access": {"vlan": WordCompleter(lambda: parent.get_vid())},
            }
        }
        self.no_dict = {
            "shutdown": None,
            "speed": None,
            "mtu": None,
            "switchport": self.switchprt_dict,
            "breakout": None,
        }
        self.breakout_list = ["2X50G", "4X25G", "4X10G"]

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
            elif args[0] == "mtu":
                for ifname in self.ifnames:
                    self.sonic.port.set_mtu(ifname, None)
            elif args[0] == "switchport" and len(args) == 5:
                if args[4].isdigit():
                    if args[4] in parent.get_vid():
                        for ifname in self.ifnames:
                            self.sonic.port.set_vlan_mem(
                                ifname, args[1], args[4], no=True
                            )
                    else:
                        print("Entered vid does not exist")
                else:
                    print("argument vid must be numbers and not letters")
            elif args[0] == "breakout":
                for ifname in self.ifnames:
                    self.sonic.port.set_breakout(ifname, None, None)
            else:
                self.no_usage()

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

            if not args[3].isdigit():
                raise InvalidInput("argument vid must be numbers and not letters")

            if args[3] not in parent.get_vid():
                raise InvalidInput("Entered vid does not exist")

            for ifname in self.ifnames:
                self.sonic.port.set_vlan_mem(ifname, args[1], args[3])

        @self.command(WordCompleter(self.breakout_list))
        def breakout(args):
            valid_speed = ["50G", "10G", "25G"]
            invalid_input_str = f'usage: breakout [{"|".join(self.breakout_list)}]'
            if len(args) != 1:
                raise InvalidInput(invalid_input_str)
            try:
                # Split values '2X50G', '4X25G', '4X10G' and validate
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

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            for ifname in self.ifnames:
                if len(self.ifnames) > 1:
                    print(f"Interface {ifname}:")
                self.sonic.port.show(ifname)

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        print(f'usage: no [{"|".join(no_keys)}]')

    def __str__(self):
        return "interface({})".format(self.name)


class Vlan_CLI(Object):
    def __init__(self, conn, parent, vid):
        self.vid = vid
        super().__init__(parent)
        self.sonic = Sonic(conn)
        self.sonic.vlan.create_vlan(self.vid)

        @self.command()
        def name(args):
            if len(args) != 1:
                raise InvalidInput("usage: name <vlan_name>")
            vlan_name = args[0]
            self.sonic.vlan.set_name(vlan_name)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.sonic.vlan.show(self.vid)

    def __str__(self):
        return "vlan({})".format(self.vid)
