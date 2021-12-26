from .cli import (
    Context,
    GlobalShowCommand,
    ModelExists,
)
from .root import Root
from .base import InvalidInput, Command
from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter
from .common import sysrepo_wrap
from .aaa import AAACommand, TACACSCommand
import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class NACM(Context):

    XPATH = "/ietf-netconf-acm:nacm"

    def __init__(self, conn, parent):
        super().__init__(parent)
        self.sr_op = sysrepo_wrap(self.session)

        @self.command()
        def disable(line):
            if len(line) != 0:
                raise InvalidInput("usage: disable[cr]")
            self.sr_op.set_data(f"{self.XPATH}/enable-nacm", False)

        @self.command()
        def enable(line):
            if len(line) != 0:
                raise InvalidInput("usage: enable[cr]")
            self.sr_op.set_data(f"{self.XPATH}/enable-nacm", True)

    def __str__(self):
        return "nacm"


class Netconf(Context):

    XPATH = "/goldstone-system:system/netconf"

    def __init__(self, conn, parent):
        super().__init__(parent)
        self.sr_op = sysrepo_wrap(self.session)

        @self.command()
        def shutdown(line):
            if len(line) != 0:
                raise InvalidInput("usage: shutdown[cr]")
            self.sr_op.set_data(f"{self.XPATH}/config/enabled", False)

        @self.command(WordCompleter(["shutdown"]))
        def no(line):
            if len(line) != 1 or line[0] != "shutdown":
                raise InvalidInput("usage: no shutdown")
            self.sr_op.set_data(f"{self.XPATH}/config/enabled", True)

        @self.command()
        def nacm(line):
            if len(line) != 0:
                raise InvalidInput("usage: nacm[cr]")
            return NACM(conn, self)

    def __str__(self):
        return "netconf"


class SystemContext(Context):
    def __init__(self, conn, parent):
        super().__init__(parent)

        @self.command(name="netconf")
        def netconf(line):
            if len(line) != 0:
                raise InvalidInput("usage: netconf[cr]")
            return Netconf(conn, self)

        @self.command()
        def reboot(line):
            session = conn.start_session()
            stdout.info(session.rpc_send("/goldstone-system:reboot", {}))

        @self.command()
        def shutdown(line):
            session = conn.start_session()
            stdout.info(session.rpc_send("/goldstone-system:shutdown", {}))

        c = TACACSCommand(self)
        self.add_command(c.name, c, add_no=True)

        c = AAACommand(self)
        self.add_command(c.name, c, add_no=True)

    def __str__(self):
        return "system"


class Version(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())

        conn = self.context.root().conn
        with conn.start_session() as sess:
            xpath = "/goldstone-system:system/state/software-version"
            sess.switch_datastore("operational")
            data = sess.get_data(xpath)
            stdout.info(data["system"]["state"]["software-version"])

    def usage(self):
        return "usage: {self.name_all()}"


GlobalShowCommand.register_command(
    "version", Version, when=ModelExists("goldstone-system")
)


class SystemCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput("usage: system")
        return SystemContext(self.context.root().conn, self.context)


Root.register_command("system", SystemCommand, when=ModelExists("goldstone-system"))
