from .base import Command, InvalidInput
from .cli import (
    GSObject as Object,
    GlobalShowCommand,
    RunningConfigCommand,
    TechSupportCommand,
    ModelExists,
)
from .sonic import UFD
from .root import Root


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


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return UFD(self.context.root().conn).show()
        else:
            stderr.info(self.usage())


GlobalShowCommand.register_command(
    "ufd", Show, when=ModelExists("goldstone-uplink-failure-detection")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return UFD(self.context.root().conn).run_conf()
        else:
            stderr.info(self.usage())


RunningConfigCommand.register_command(
    "ufd", Run, when=ModelExists("goldstone-uplink-failure-detection")
)


class TechSupport(Command):
    def exec(self, line):
        UFD(self.context.root().conn).show()
        self.parent.xpath_list.append("/goldstone-uplink-failure-detection:ufd-groups")


TechSupportCommand.register_command(
    "ufd", TechSupport, when=ModelExists("goldstone-uplink-failure-detection")
)


class UFDCommand(Command):
    def __init__(
        self, context: Object = None, parent: Command = None, name=None, **options
    ):
        if name == None:
            name = "ufd"
        super().__init__(context, parent, name, **options)
        self.ufd = UFD(context.root().conn)

    def arguments(self):
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


Root.register_command(
    "ufd",
    UFDCommand,
    when=ModelExists("goldstone-uplink-failure-detection"),
    add_no=True,
    no_completion_on_exec=True,
)
