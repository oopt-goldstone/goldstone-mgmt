from .base import InvalidInput
from .cli import (
    Command,
    Context,
    GlobalShowCommand,
    ModelExists,
)
from .root import Root
from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter
from .aaa import AAACommand, TACACSCommand

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class NACM(Context):
    XPATH = "/ietf-netconf-acm:nacm"

    def __init__(self, conn, parent):
        super().__init__(parent)

        @self.command()
        def disable(line):
            if len(line) != 0:
                raise InvalidInput("usage: disable[cr]")
            self.conn.set(f"{self.XPATH}/enable-nacm", False)
            self.conn.apply()

        @self.command()
        def enable(line):
            if len(line) != 0:
                raise InvalidInput("usage: enable[cr]")
            self.conn.set(f"{self.XPATH}/enable-nacm", True)
            self.conn.apply()

    def __str__(self):
        return "nacm"


class Netconf(Context):
    XPATH = "/goldstone-system:system/netconf"

    def __init__(self, conn, parent):
        super().__init__(parent)

        @self.command()
        def shutdown(line):
            if len(line) != 0:
                raise InvalidInput("usage: shutdown[cr]")
            self.conn.set(f"{self.XPATH}/config/enabled", False)
            self.conn.apply()

        @self.command(WordCompleter(["shutdown"]))
        def no(line):
            if len(line) != 1 or line[0] != "shutdown":
                raise InvalidInput("usage: no shutdown")
            self.conn.set(f"{self.XPATH}/config/enabled", True)
            self.conn.apply()

        @self.command()
        def nacm(line):
            if len(line) != 0:
                raise InvalidInput("usage: nacm[cr]")
            return NACM(conn, self)

    def __str__(self):
        return "netconf"


class SystemContext(Context):
    def __init__(self, parent):
        super().__init__(parent)

        @self.command(name="netconf")
        def netconf(line):
            if len(line) != 0:
                raise InvalidInput("usage: netconf[cr]")
            return Netconf(self.conn, self)

        @self.command()
        def reboot(line):
            stdout.info(self.conn.rpc("/goldstone-system:reboot", {}))

        @self.command()
        def shutdown(line):
            stdout.info(self.conn.rpc("/goldstone-system:shutdown", {}))

        self.add_command("tacacs", TACACSCommand, add_no=True)
        self.add_command("aaa", AAACommand, add_no=True)

    def __str__(self):
        return "system"


class Version(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())

        xpath = "/goldstone-system:system/state/software-version"
        version = self.conn.get_operational(xpath)
        if version == None:
            raise InvalidInput("failed to get software-version")
        stdout.info(version)

    def usage(self):
        return "usage: {self.name_all()}"


GlobalShowCommand.register_command(
    "version", Version, when=ModelExists("goldstone-system")
)


class SystemCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput("usage: system")
        return SystemContext(self.context)


Root.register_command("system", SystemCommand, when=ModelExists("goldstone-system"))
