import sys
import os
import re
import logging

from .base import InvalidInput, Command
from .cli import (
    GSObject as Object,
    GlobalShowCommand,
    RunningConfigCommand,
    GlobalClearCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
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
    def arguments(self):
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
    def arguments(self):
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
    def arguments(self):
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
    def arguments(self):
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


class UFDLinkCommand(Command):
    COMMAND_DICT = {"uplink": Command, "downlink": Command}


class UFDCommand(Command):
    def __init__(self, context: Object = None, parent: Command = None, name=None):
        super().__init__(context, parent, name)
        if self.root.name != "no":
            for id in self.context.ufd.get_id():
                self.add_command(str(id), UFDLinkCommand)

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
    def arguments(self):
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


class InterfaceObject(Object):
    REGISTERED_COMMANDS = {}

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

        self.add_command("shutdown", ShutdownCommand, add_no=True)
        self.add_command("admin-status", AdminStatusCommand, add_no=True)
        self.add_command("fec", FECCommand, add_no=True)
        self.add_command("speed", SpeedCommand, add_no=True)
        self.add_command("interface-type", InterfaceTypeCommand, add_no=True)
        self.add_command("mtu", MTUCommand, add_no=True)
        self.add_command("auto-negotiate", AutoNegoCommand, add_no=True)
        self.add_command("breakout", BreakoutCommand, add_no=True)

        if "goldstone-uplink-failure-detection" in self.parent.installed_modules:
            self.ufd = sonic.UFD(conn)
            self.add_command("ufd", UFDCommand, add_no=True)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.port.show(ifnames)

    def __str__(self):
        return "interface({})".format(self.name)


class InterfaceCounterCommand(Command):
    def arguments(self):
        return ["table"] + self.parent.port.interface_names()

    def exec(self, line):
        ifnames = self.parent.port.interface_names()
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

        self.parent.port.show_counters(ifnames, table)


class InterfaceGroupCommand(Command):
    COMMAND_DICT = {
        "brief": Command,
        "description": Command,
        "counters": InterfaceCounterCommand,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.port = sonic.Port(context.conn)

    def exec(self, line):
        if len(line) == 1:
            return self.port.show_interface(line[0])
        else:
            raise InvalidInput(self.usage())

    def usage(self):
        return (
            "usage:\n" f" {self.parent.name} {self.name} (brief|description|counters)"
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


GlobalShowCommand.register_command(
    "interface", InterfaceGroupCommand, when=ModelExists("goldstone-interfaces")
)

GlobalClearCommand.register_command(
    "interface", ClearInterfaceGroupCommand, when=ModelExists("goldstone-interfaces")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return sonic.Port(self.context.root().conn).run_conf()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "interface", Run, when=ModelExists("goldstone-interfaces")
)


class TechSupport(Command):
    def exec(self, line):
        sonic.Port(self.context.root().conn).show_interface()
        self.parent.xpath_list.append("/goldstone-interfaces:interfaces")


TechSupportCommand.register_command(
    "interfaces", TechSupport, when=ModelExists("goldstone-interfaces")
)


class InterfaceCommand(Command):
    def __init__(self, context, parent, name, **options):
        super().__init__(context, parent, name, **options)
        self.port = sonic.Port(context.conn)

    def arguments(self):
        return self.port.interface_names()

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput("usage: interface <ifname>")
        return InterfaceObject(self.context.root().conn, self.context, line[0])


Root.register_command(
    "interface",
    InterfaceCommand,
    when=ModelExists("goldstone-interfaces"),
    no_completion_on_exec=True,
)
