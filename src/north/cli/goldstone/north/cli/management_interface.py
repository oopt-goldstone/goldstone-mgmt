from .cli import (
    Command,
    Run,
    RunningConfigCommand,
    ModelExists,
    TechSupportCommand,
)
from .root import Root
from .base import InvalidInput
from .interface import interface_names, InterfaceContext

import logging


logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class ManagementInterface(InterfaceContext):
    OBJECT_NAME = "management-interface"
    MODEL = "goldstone-mgmt-interfaces"


RunningConfigCommand.register_command(
    "management-interface",
    Run,
    when=ModelExists("goldstone-mgmt-interfaces"),
    ctx=ManagementInterface,
)


class TechSupport(Command):
    def exec(self, line):
        self.parent.xpath_list.append("/goldstone-mgmt-interfaces:interfaces")


TechSupportCommand.register_command(
    "management-interface", TechSupport, when=ModelExists("goldstone-mgmt-interfaces")
)


class MgmtIfCommand(Command):
    def arguments(self):
        return interface_names(self.conn, model="goldstone-mgmt-interfaces")

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <ifname>")
        return ManagementInterface(self.context, line[0])


Root.register_command(
    "management-interface",
    MgmtIfCommand,
    when=ModelExists("goldstone-mgmt-interfaces"),
    no_completion_on_exec=True,
)
