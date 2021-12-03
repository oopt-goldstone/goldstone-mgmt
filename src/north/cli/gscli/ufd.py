from .base import Command, InvalidInput
from .cli import GSObject as Object
from .sonic import UFD


class UFDObject(Object):
    def __init__(self, ufd, parent, id):
        self.id = id
        super().__init__(parent)
        ufd.create(self.id)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            ufd.show(self.id)

    def __str__(self):
        return "ufd({})".format(self.id)


class UFDCommand(Command):
    def __init__(self, context: Object = None, parent: Command = None, name=None):
        if name == None:
            name = "ufd"
        super().__init__(context, parent, name)
        self.ufd = UFD(context.root().conn)

    def list(self):
        return self.ufd.get_id()

    def usage(self):
        return "<ufd-id>"

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        if self.parent and self.parent.name == "no":
            self.ufd.delete(line[0])
        else:
            return UFDObject(self.ufd, self.context, line[0])
