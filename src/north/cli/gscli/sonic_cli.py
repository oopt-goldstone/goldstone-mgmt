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
from . import sonic

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

        self.port = sonic.Port(conn)
        self.ufd = sonic.UFD(conn)
        self.portchannel = sonic.Portchannel(conn)
        self.vlan = sonic.Vlan(conn)

        ifnames = [i for i in self.port.interface_names() if ptn.match(i)]

        if len(ifnames) == 0:
            raise InvalidInput(f"no interface found: {ifname}")
        elif len(ifnames) > 1:
            stdout.info(f"Selected interfaces: {ifnames}")

            @self.command()
            def selected(args):
                if len(args) != 0:
                    raise InvalidInput("usage: selected[cr]")
                stdout.info(", ".join(ifnames))

        self.switchprt_dict = {
            "mode": {
                "trunk": {"vlan": WordCompleter(self.vlan.get_vids)},
                "access": {"vlan": WordCompleter(self.vlan.get_vids)},
            }
        }

        self.ufd_dict = {}

        for id in self.ufd.get_id():
            self.ufd_dict[id] = {"uplink": None, "downlink": None}

        self.no_dict = {
            "shutdown": None,
            "speed": None,
            "mtu": None,
            "switchport": self.switchprt_dict,
            "breakout": None,
            "interface-type": None,
            "auto-negotiate": {"advertise": None},
            "fec": None,
            "ufd": None,
            "portchannel": None,
            "admin-status": None,
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
        self.tagging_mode_list = ["trunk", "access"]

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(args):
            if len(args) < 1:
                raise InvalidInput("usage: {}".format(self.no_usage()))
            if args[0] == "shutdown":
                self.port.set_admin_status(ifnames, "UP")
            elif args[0] == "admin-status":
                self.port.set_admin_status(ifnames, None)
            elif args[0] == "speed":
                self.port.set_speed(ifnames, None)
            elif args[0] == "interface-type":
                self.port.set_interface_type(ifnames, None)
            elif args[0] == "auto-negotiate":
                if len(args) == 2:
                    if args[1] != "advertise":
                        raise InvalidInput("usage: {}".format(self.no_usage()))
                    self.port.set_auto_nego_adv_speed(ifnames, None)
                else:
                    self.port.set_auto_nego(ifnames, None)
            elif args[0] == "ufd":
                self.ufd.check_ports(ifnames)
            elif args[0] == "mtu":
                self.port.set_mtu(ifnames, None)
            elif args[0] == "switchport" and len(args) == 5:
                if args[1] != "mode" and args[2] not in self.tagging_mode_list:
                    raise InvalidInput(
                        "usage : no switchport mode trunk|access vlan <vid>"
                    )
                if args[3] != "vlan":
                    raise InvalidInput(
                        "usage : no switchport mode trunk|access vlan <vid>"
                    )
                self.port.set_vlan_mem(ifnames, args[2], args[4], config=False)

            elif args[0] == "breakout":
                self.port.set_breakout(ifnames, None, None)
            elif args[0] == "fec" and len(args) == 1:
                self.port.set_fec(ifnames, None)
            elif args[0] == "portchannel":
                self.portchannel.remove_interfaces(ifnames)
            else:
                self.no_usage()

        @self.command(WordCompleter(self.fec_list))
        def fec(args):
            if len(args) != 1 or args[0] not in ["fc", "rs"]:
                raise InvalidInput("usages: fec <fc|rs>")
            self.port.set_fec(ifnames, args[0].upper())

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            self.port.set_admin_status(ifnames, "DOWN")

        admin_status_list = ["up", "down"]

        @self.command(WordCompleter(admin_status_list), name="admin-status")
        def admin_status(args):
            if len(args) != 1 or args[0] not in admin_status_list:
                raise InvalidInput(
                    f"usage: admin_status [{'|'.join(admin_status_list)}]"
                )
            self.port.set_admin_status(ifnames, args[0].upper())

        speeds = self.port.valid_speeds()

        @self.command(WordCompleter(speeds))
        def speed(args):
            if len(args) != 1:
                raise InvalidInput(f"usage: speed [{'|'.join(speeds)}]")
            speed = args[0]
            self.port.set_speed(ifnames, speed)

        @self.command()
        def mtu(args):
            if len(args) != 1:
                range_ = port.mtu_range()
                range_ = f" <range {range_}>" if range_ else ""
                raise InvalidInput(f"usage: mtu{range_}")
            if args[0].isdigit():
                mtu = int(args[0])
                self.port.set_mtu(ifnames, mtu)
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

            self.port.set_vlan_mem(ifnames, args[1], args[3])

        @self.command(WordCompleter(self.interface_type_list), name="interface-type")
        def interface_type(args):
            valid_args = self.interface_type_list
            invalid_input_str = (
                f'usage: interface-type [{"|".join(self.interface_type_list)}]'
            )
            if len(args) != 1:
                raise InvalidInput(invalid_input_str)
            if args[0] not in valid_args:
                raise InvalidInput(invalid_input_str)
            self.port.set_interface_type(ifnames, args[0])

        auto_nego_dict = {
            "enable": None,
            "disable": None,
            "advertise": WordCompleter(speeds),
        }

        @self.command(
            NestedCompleter.from_nested_dict(auto_nego_dict), name="auto-negotiate"
        )
        def auto_nego(args):
            invalid_input_str = (
                f'usage: auto-negotiate [{"|".join(auto_nego_dict.keys())}]'
            )
            if len(args) < 1 or args[0] not in auto_nego_dict.keys():
                raise InvalidInput(invalid_input_str)

            if args[0] in ["enable", "disable"]:
                if len(args) != 1:
                    raise InvalidInput(invalid_input_str)
                self.port.set_auto_nego(ifnames, args[0] == "enable")
            elif args[0] == "advertise":
                if len(args) != 2:
                    raise InvalidInput(invalid_input_str)
                self.port.set_auto_nego_adv_speed(ifnames, args[1])

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

            self.port.set_breakout(ifnames, input_values[0], input_values[1])

        @self.command(NestedCompleter.from_nested_dict(self.ufd_dict))
        def ufd(args):
            if len(args) != 2 or (args[1] != "uplink" and args[1] != "downlink"):
                raise InvalidInput("usage: ufd <ufdid> <uplink|downlink>")

            self.ufd.add_ports(args[0], ifnames, args[1])

        @self.command(WordCompleter(self.portchannel.get_id))
        def portchannel(args):
            if len(args) != 1:
                raise InvalidInput("usage: portchannel <portchannel_id>")
            self.portchannel.add_interfaces(args[0], ifnames)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.port.show(ifnames)

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        stderr.info(f'usage: no [{"|".join(no_keys)}]')

    def __str__(self):
        return "interface({})".format(self.name)
