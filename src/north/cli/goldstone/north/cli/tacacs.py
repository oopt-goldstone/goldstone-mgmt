from .base import Command, InvalidInput
from .cli import (
    GSObject as Object,
    RunningConfigCommand,
    GlobalShowCommand,
    ModelExists,
)
from .system import TACACS


class TACACSCommand(Command):
    def __init__(self, context: Object = None, parent: Command = None, name=None):
        if name == None:
            name = "tacacs-server"
        super().__init__(context, parent, name)
        self.tacacs = TACACS(context.root().conn)

    def usage(self):
        if self.parent and self.parent.name == "no":
            return "host <ipaddress>"

        return "host <ipaddress> key <string> [port <portnumber>] [timeout <seconds>]"

    def exec(self, line):
        usage = f"usage: {self.name_all()} {self.usage()}"
        if self.parent and self.parent.name == "no":
            if len(line) != 2:
                raise InvalidInput(usage)
            self.tacacs.set_no_tacacs(line[1])
        else:
            if len(line) != 4 and len(line) != 6 and len(line) != 8:
                raise InvalidInput(usage)
            if line[0] != "host" or line[2] != "key":
                raise InvalidInput(usage)

            ipAddress = line[1]
            key = line[3]
            # TODO extract these default values from the YANG model
            port = 49
            timeout = 300

            if len(line) == 6:
                if line[4] != "port" and line[4] != "timeout":
                    raise InvalidInput(usage)

                if line[4] == "port":
                    port = line[5]
                elif line[4] == "timeout":
                    timeout = line[5]

            elif len(line) == 8:
                if line[4] != "port" or line[6] != "timeout":
                    raise InvalidInput(usage)

                port = line[5]
                timeout = line[7]

            self.tacacs.set_tacacs_server(ipAddress, key, port, timeout)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return TACACS(self.context.root().conn).run_conf()
        else:
            raise InvalidInput(f"usage: {self.name_all()}")


GlobalShowCommand.register_sub_command(
    "tacacs", Show, when=ModelExists("goldstone-system")
)
