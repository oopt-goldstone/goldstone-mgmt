from .base import Command, InvalidInput
from .cli import (
    GSObject as Object,
    GlobalShowCommand,
    RunningConfigCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
from .sonic import Portchannel
from prompt_toolkit.completion import (
    FuzzyWordCompleter,
)


class PortchannelObject(Object):
    def __init__(self, pc, parent, id):
        self.id = id
        super().__init__(parent)
        pc.create(self.id)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            pc.show(self.id)

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            pc.set_admin_status(id, "DOWN")

        @self.command(FuzzyWordCompleter(["shutdown", "admin-status"]))
        def no(args):
            if len(args) != 1:
                raise InvalidInput(f"usage: no [shutdown|admin-status]")
            if args[0] == "shutdown":
                pc.set_admin_status(id, "UP")
            elif args[0] == "admin-status":
                pc.set_admin_status(id, None)
            else:
                raise InvalidInput(f"usage: no [shutdown|admin-status]")

        admin_status_list = ["up", "down"]

        @self.command(FuzzyWordCompleter(admin_status_list), name="admin-status")
        def admin_status(args):
            if len(args) != 1 or args[0] not in admin_status_list:
                raise InvalidInput(
                    f"usage: admin_status [{'|'.join(admin_status_list)}]"
                )
            pc.set_admin_status(id, args[0].upper())

    def __str__(self):
        return "portchannel({})".format(self.id)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return Portchannel(self.context.root().conn).show()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


GlobalShowCommand.register_command(
    "portchannel", Show, when=ModelExists("goldstone-portchannel")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return Portchannel(self.context.root().conn).run_conf()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "portchannel", Run, when=ModelExists("goldstone-portchannel")
)


class TechSupport(Command):
    def exec(self, line):
        Portchannel(self.context.root().conn).show()
        self.parent.xpath_list.append("/goldstone-portchannel:portchannel")


TechSupportCommand.register_command(
    "portchannel", TechSupport, when=ModelExists("goldstone-portchannel")
)


class PortchannelCommand(Command):
    def __init__(
        self, context: Object = None, parent: Command = None, name=None, **options
    ):
        if name == None:
            name = "portchannel"
        super().__init__(context, parent, name, **options)
        self.pc = Portchannel(context.root().conn)

    def arguments(self):
        return self.pc.get_id()

    def usage(self):
        return "<portchannel-id>"

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        if self.parent and self.parent.name == "no":
            self.pc.delete(line[0])
        else:
            return PortchannelObject(self.pc, self.context, line[0])


Root.register_command(
    "portchannel",
    PortchannelCommand,
    when=ModelExists("goldstone-portchannel"),
    add_no=True,
    no_completion_on_exec=True,
)
