from .base import InvalidInput
from .cli import (
    Command,
    ConfigCommand,
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root

from tabulate import tabulate
from natsort import natsorted
from prompt_toolkit.completion import (
    FuzzyWordCompleter,
)
from .interface import InterfaceContext

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

XPATH = "/goldstone-portchannel:portchannel"


def pcxpath(id):
    return f"{XPATH}/portchannel-group[portchannel-id='{id}']"


def create(session, id):
    session.set(f"{pcxpath(id)}/config/portchannel-id", id)
    session.apply()


def delete(session, id):
    session.delete(pcxpath(id))
    session.apply()


def get_list(session, ds, include_implicit_defaults=True):
    l = session.get(
        XPATH + "/portchannel-group",
        [],
        ds=ds,
        include_implicit_defaults=include_implicit_defaults,
    )
    return natsorted(
        l,
        key=lambda x: x["portchannel-id"],
    )


def add_interfaces(session, id, ifnames):
    prefix = "/goldstone-interfaces:interfaces"
    for ifname in ifnames:
        xpath = f"{prefix}/interface[name='{ifname}']"
        # in order to create the interface node if it doesn't exist in running DS
        session.set(f"{xpath}/config/name", ifname)
        session.set(f"{pcxpath(id)}/config/interface", ifname)
    session.apply()


def set_admin_status(session, id, value):
    if value:
        session.set(f"{pcxpath(id)}/config/admin-status", value)
    else:
        session.delete(f"{pcxpath(id)}/config/admin-status")
    session.apply()


def get_id(session):
    return [v["portchannel-id"] for v in get_list(session, "operational")]


def remove_interfaces(session, ifnames):
    groups = get_list(session, "running")
    if len(groups) == 0:
        raise InvalidInput("portchannel not configured for this interface")

    for ifname in ifnames:
        for data in groups:
            try:
                if ifname in data["config"]["interface"]:
                    xpath = pcxpath(data["portchannel-id"])
                    session.delete(f"{xpath}/config/interface[.='{ifname}']")
                    break
            except KeyError:
                pass
        else:
            session.discard_changes()
            raise InvalidInput(f"portchannel not configured for {ifname}")

    session.apply()


def run_conf(session):
    for data in get_list(session, "running", False):
        stdout.info("portchannel {}".format(data["config"]["portchannel-id"]))
        config = data.get("config", {})
        for key, value in config.items():
            if key == "admin-status":
                stdout.info(f"  {key} {value.lower()}")
        stdout.info("  quit")
        stdout.info("!")


def show(session, id=None):

    if id != None:
        items = session.get_operational(pcxpath(id))
    else:
        items = get_list(session, "operational")

    rows = []
    for item in items:
        rows.append(
            [
                item["portchannel-id"],
                item["state"]["oper-status"].lower(),
                item["state"]["admin-status"].lower(),
                ", ".join(natsorted(list(item["state"].get("interface", [])))),
            ]
        )

    stdout.info(
        tabulate(
            rows,
            ["Portchannel ID", "oper-status", "admin-status", "Interfaces"],
        )
    )


class PortchannelContext(Context):
    def __init__(self, parent, id):
        self.id = id
        super().__init__(parent)
        create(self.conn, self.id)

        @self.command(parent.get_completer("show"), name="show")
        def show_(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                show(self.conn, self.id)

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            set_admin_status(self.conn, id, "DOWN")

        @self.command(FuzzyWordCompleter(["shutdown", "admin-status"]))
        def no(args):
            if len(args) != 1:
                raise InvalidInput(f"usage: no [shutdown|admin-status]")
            if args[0] == "shutdown":
                set_admin_status(self.conn, id, "UP")
            elif args[0] == "admin-status":
                set_admin_status(self.conn, id, None)
            else:
                raise InvalidInput(f"usage: no [shutdown|admin-status]")

        admin_status_list = ["up", "down"]

        @self.command(FuzzyWordCompleter(admin_status_list), name="admin-status")
        def admin_status(args):
            if len(args) != 1 or args[0] not in admin_status_list:
                raise InvalidInput(
                    f"usage: admin_status [{'|'.join(admin_status_list)}]"
                )
            set_admin_status(self.conn, id, args[0].upper())

    def __str__(self):
        return "portchannel({})".format(self.id)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return show(self.conn)
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
            return run_conf(self.conn)
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "portchannel", Run, when=ModelExists("goldstone-portchannel")
)


class TechSupport(Command):
    def exec(self, line):
        show(self.conn)
        self.parent.xpath_list.append("/goldstone-portchannel:portchannel")


TechSupportCommand.register_command(
    "portchannel", TechSupport, when=ModelExists("goldstone-portchannel")
)


class PortchannelCommand(Command):
    def __init__(
        self, context: Context = None, parent: Command = None, name=None, **options
    ):
        if name == None:
            name = "portchannel"
        super().__init__(context, parent, name, **options)

    def arguments(self):
        return get_id(self.conn)

    def usage(self):
        return "<portchannel-id>"

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        if self.root.name == "no":
            delete(self.conn, line[0])
        else:
            return PortchannelContext(self.context, line[0])


Root.register_command(
    "portchannel",
    PortchannelCommand,
    when=ModelExists("goldstone-portchannel"),
    add_no=True,
    no_completion_on_exec=True,
)


def get_portchannel(conn, ifname):
    xpath = "/goldstone-portchannel:portchannel"
    pc = []
    for data in conn.get(f"{xpath}/portchannel-group", []):
        for intf in data.get("config", {}).get("interface", []):
            if intf == ifname:
                pc.append(data["portchannel-id"])
    return pc


class InterfacePortchannelCommand(ConfigCommand):
    def arguments(self):
        if self.root.name != "no":
            return get_id(self.conn)
        return []

    def exec(self, line):
        if self.root.name == "no":
            remove_interfaces(self.conn, self.context.ifnames)
        else:
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <portchannel_id>")
            add_interfaces(self.conn, line[0], self.context.ifnames)

    @classmethod
    def to_command(cls, conn, data):
        ifname = data.get("name")
        return [f"portchannel {v}" for v in get_portchannel(conn, ifname)]


InterfaceContext.register_command(
    "portchannel",
    InterfacePortchannelCommand,
    when=ModelExists("goldstone-portchannel"),
    add_no=True,
)
