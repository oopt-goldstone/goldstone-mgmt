from .base import Command, InvalidInput
from .cli import GSObject as Object
from .system import AAA


class AAACommand(Command):
    def __init__(self, context: Object = None, parent: Command = None, name=None):
        if name == None:
            name = "aaa"
        super().__init__(context, parent, name)
        self.aaa = AAA(context.root().conn)

    def usage(self):
        if self.parent and self.parent.name == "no":
            return "authentication login"

        return "authentication login default [group tacacs | local]"

    def exec(self, line):
        usage = f"usage: {self.name_all()} {self.usage()}"

        if self.parent and self.parent.name == "no":
            if len(line) != 2:
                raise InvalidInput(usage)
            self.aaa.set_no_aaa()
        else:
            if len(line) not in [4, 5]:
                raise InvalidInput(usage)
            if (
                line[0] != "authentication"
                or line[1] != "login"
                or line[2] != "default"
            ):
                raise InvalidInput(usage)
            if len(line) == 4 and line[3] == "local":
                value = line[3]
            elif len(line) == 5 and line[3] == "group" and line[4] == "tacacs":
                value = line[4]
            else:
                raise InvalidInput(usage)
            self.aaa.set_aaa(value)
