import sys
import os
import re
import logging

from .base import InvalidInput, Command
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


class ShutdownCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")

        port = self.context.port
        if self.root.name == "no":
            port.set_admin_status(self.context.ifnames, "UP")
        else:
            port.set_admin_status(self.context.ifnames, "DOWN")


class AdminStatusCommand(Command):
    def list(self):
        if self.root.name != "no":
            return ["up", "down"]
        return []

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_admin_status(self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            port.set_admin_status(self.context.ifnames, line[0].upper())


class FECCommand(Command):
    def list(self):
        if self.root.name != "no":
            return ["none", "fc", "rs"]
        return []

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_fec(self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            port.set_fec(self.context.ifnames, line[0].upper())


class SpeedCommand(Command):
    def list(self):
        if self.root.name != "no":
            return self.context.port.valid_speeds()
        return []

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_speed(self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            port.set_speed(self.context.ifnames, line[0])


class InterfaceTypeCommand(Command):
    def list(self):
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
        return []

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_interface_type(self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            port.set_interface_type(self.context.ifnames, line[0])


class MTUCommand(Command):
    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_mtu(self.context.ifnames, None)
        else:
            if len(line) != 1:
                range_ = port.mtu_range()
                range_ = f" <range {range_}>" if range_ else ""
                raise InvalidInput(f"usage: mtu{range_}")
            if line[0].isdigit():
                mtu = int(line[0])
                port.set_mtu(self.context.ifnames, mtu)
            else:
                raise InvalidInput("Argument must be numbers and not letters")


class AutoNegoAdvertiseCommand(Command):
    def list(self):
        if self.root.name != "no":
            return self.context.port.valid_speeds()
        return []

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_auto_nego_adv_speed(self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            port.set_auto_nego_adv_speed(self.context.ifnames, line[0])


class AutoNegoCommand(Command):
    SUBCOMMAND_DICT = {
        "enable": Command,
        "disable": Command,
        "advertise": AutoNegoAdvertiseCommand,
    }

    def list(self):
        if self.root.name != "no":
            return ["enable", "disable"]
        return []

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_auto_nego(self.context.ifnames, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            port.set_auto_nego(self.context.ifnames, line[0] == "enable")


class SwitchportModeVLANCommand(Command):
    def list(self):
        return self.context.vlan.get_vids()


class SwitchportModeAccessCommand(Command):
    SUBCOMMAND_DICT = {"vlan": SwitchportModeVLANCommand}


class SwitchportModeTrunkCommand(Command):
    SUBCOMMAND_DICT = {"vlan": SwitchportModeVLANCommand}


class SwitchportModeCommand(Command):
    SUBCOMMAND_DICT = {
        "access": SwitchportModeAccessCommand,
        "trunk": SwitchportModeTrunkCommand,
    }

    def exec(self, line):
        port = self.context.port
        if (
            len(line) < 3
            or (line[1] not in self.SUBCOMMAND_DICT)
            or (line[2] != "vlan")
        ):
            raise InvalidInput(f"usage : {self.name_all()} [trunk|access] vlan <vid>")

        port.set_vlan_mem(
            self.context.ifnames, line[1], line[3], config=self.root.name != "no"
        )


class SwitchportCommand(Command):
    SUBCOMMAND_DICT = {"mode": SwitchportModeCommand}


class UFDLinkCommand(Command):
    SUBCOMMAND_DICT = {"uplink": Command, "downlink": Command}


class UFDCommand(Command):
    def __init__(self, context: Object = None, parent: Command = None, name=None):
        super().__init__(context, parent, name)
        if self.root.name != "no":
            for id in self.context.ufd.get_id():
                self.add_sub_command(str(id), UFDLinkCommand)

    def exec(self, line):
        ufd = self.context.ufd
        if self.root.name == "no":
            ufd.check_ports(self.context.ifnames)
        else:
            if len(line) != 2 or (line[1] != "uplink" and line[1] != "downlink"):
                raise InvalidInput(
                    f"usage: {self.name_all()} <ufdid> <uplink|downlink>"
                )
            ufd.add_ports(line[0], self.context.ifnames, line[1])


class BreakoutCommand(Command):
    def list(self):
        if self.root.name != "no":
            return ["2X50G", "2X20G", "4X25G", "4X10G"]

    def exec(self, line):
        port = self.context.port
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            port.set_breakout(self.context.ifnames, None, None)
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
            port.set_breakout(self.context.ifnames, input_values[0], input_values[1])


class PortchannelCommand(Command):
    def list(self):
        if self.root.name != "no":
            self.context.portchannel.get_id()
        return []

    def exec(self, line):
        portchannel = self.context.portchannel
        if self.root.name == "no":
            portchannel.remove_interfaces(self.context.ifnames)
        else:
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <portchannel_id>")
            portchannel.add_interfaces(line[0], ifnames)


class InterfaceObject(Object):
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

        self.ifnames = ifnames

        self.add_command(ShutdownCommand(self), name="shutdown")
        self.no.add_sub_command("shutdown", ShutdownCommand)

        self.add_command(AdminStatusCommand(self), name="admin-status")
        self.no.add_sub_command("admin-status", AdminStatusCommand)

        self.add_command(FECCommand(self), name="fec")
        self.no.add_sub_command("fec", FECCommand)

        self.add_command(SpeedCommand(self), name="speed")
        self.no.add_sub_command("speed", SpeedCommand)

        self.add_command(InterfaceTypeCommand(self), name="interface-type")
        self.no.add_sub_command("interface-type", InterfaceTypeCommand)

        self.add_command(MTUCommand(self), name="mtu")
        self.no.add_sub_command("mtu", MTUCommand)

        self.add_command(AutoNegoCommand(self), name="auto-negotiate")
        self.no.add_sub_command("auto-negotiate", AutoNegoCommand)

        self.add_command(BreakoutCommand(self), name="breakout")
        self.no.add_sub_command("breakout", BreakoutCommand)

        if "goldstone-vlan" in self.parent.installed_modules:
            self.vlan = sonic.Vlan(conn)
            self.add_command(SwitchportCommand(self), name="switchport")
            self.no.add_sub_command("switchport", SwitchportCommand)

        if "goldstone-uplink-failure-detection" in self.parent.installed_modules:
            self.ufd = sonic.UFD(conn)
            self.add_command(UFDCommand(self), name="ufd")
            self.no.add_sub_command("ufd", UFDCommand)

        if "goldstone-portchannel" in self.parent.installed_modules:
            self.portchannel = sonic.Portchannel(conn)
            self.add_command(PortchannelCommand(self), name="portchannel")
            self.no.add_sub_command("portchannel", PortchannelCommand)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.port.show(ifnames)

    def __str__(self):
        return "interface({})".format(self.name)
