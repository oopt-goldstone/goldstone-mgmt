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

from .interface import InterfaceContext

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


XPATH = "/goldstone-uplink-failure-detection:ufd-groups"


def xpath(id):
    return f"{XPATH}/ufd-group[ufd-id='{id}']"


def create(session, id):
    session.set(f"{xpath(id)}/config/ufd-id", id)
    session.apply()


def delete(session, id):
    session.delete(xpath(id))
    session.apply()


def add_ports(session, id, ports, role):
    prefix = "/goldstone-interfaces:interfaces"
    for port in ports:
        x = f"{prefix}/interface[name='{port}']"
        # in order to create the interface node if it doesn't exist in running DS
        session.set(f"{x}/config/name", port)
        session.set(f"{xpath(id)}/config/{role}", port)
    session.apply()


def get_id(session):
    xpath = f"{XPATH}/ufd-group/ufd-id"
    return natsorted(session.get_operational(xpath, []))


def check_ports(session, ports):
    ufds = session.get(f"{XPATH}/ufd-group", [])

    for port in ports:
        found = False
        for ufd in ufds:
            config = ufd["config"]
            for role in ["uplink", "downlink"]:
                links = config.get(role, [])
                if port in links:
                    found = True
                    xpath = xpath(id)
                    session.delete(f"{xpath}/config/{role}[.='{port}']")

        if not found:
            session.discard_changes()
            raise InvalidInput("ufd not configured for this interface")

    session.apply()


def show(session, id=None):
    id_list = session.get_operational(f"{XPATH}/ufd-group", [])

    if len(id_list) == 0:
        stdout.info(
            tabulate(
                [], ["UFD-ID", "Uplink-Ports", "Downlink-Ports"], tablefmt="pretty"
            )
        )
    else:
        data_tabulate = []
        uplink_ports = []
        downlink_ports = []
        ids = get_id(session)

        for id in ids:
            data = id_list[id]
            try:
                uplink_ports.append(natsorted(list(data["config"]["uplink"])))
            except KeyError:
                uplink_ports.append([])
            try:
                downlink_ports.append(natsorted(list(data["config"]["downlink"])))
            except KeyError:
                downlink_ports.append([])

        for i in range(len(ids)):

            if len(uplink_ports[i]) > 0:
                if len(downlink_ports[i]) > 0:
                    data_tabulate.append(
                        [ids[i], uplink_ports[i][0], downlink_ports[i][0]]
                    )
                else:
                    data_tabulate.append([ids[i], uplink_ports[i][0], "-"])
            elif len(downlink_ports[i]) > 0:
                data_tabulate.append([ids[i], "-", downlink_ports[i][0]])
            else:
                data_tabulate.append([ids[i], "-", "-"])

            if len(uplink_ports[i]) > len(downlink_ports[i]):
                for j in range(1, len(uplink_ports[i])):
                    if j < len(downlink_ports[i]):
                        data_tabulate.append(
                            ["", uplink_ports[i][j], downlink_ports[i][j]]
                        )
                    else:
                        data_tabulate.append(["", uplink_ports[i][j], ""])
            else:
                for j in range(1, len(downlink_ports[i])):
                    if j < len(uplink_ports[i]):
                        data_tabulate.append(
                            ["", uplink_ports[i][j], downlink_ports[i][j]]
                        )
                    else:
                        data_tabulate.append(["", "", downlink_ports[i][j]])

            if i != len(ids) - 1:
                data_tabulate.append(["", "", ""])

        stdout.info(
            tabulate(
                data_tabulate,
                ["UFD-ID", "Uplink Ports", "Downlink Ports"],
                tablefmt="pretty",
                colalign=("left",),
            )
        )


def run_conf(session):
    d_list = session.get(f"{XPATH}/ufd-group")
    for id in get_id(session):
        data = d_list[id]
        stdout.info("ufd {}".format(data["config"]["ufd-id"]))
        stdout.info("  quit")
        stdout.info("!")


class UFDContext(Context):
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

    def __str__(self):
        return "ufd({})".format(self.id)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return show(self.conn)
        else:
            stderr.info(self.usage())


GlobalShowCommand.register_command(
    "ufd", Show, when=ModelExists("goldstone-uplink-failure-detection")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return run_conf(self.conn)
        else:
            stderr.info(self.usage())


RunningConfigCommand.register_command(
    "ufd", Run, when=ModelExists("goldstone-uplink-failure-detection")
)


class TechSupport(Command):
    def exec(self, line):
        show(self.conn)
        self.parent.xpath_list.append("/goldstone-uplink-failure-detection:ufd-groups")


TechSupportCommand.register_command(
    "ufd", TechSupport, when=ModelExists("goldstone-uplink-failure-detection")
)


class UFDCommand(Command):
    def arguments(self):
        return get_id(self.conn)

    def usage(self):
        return "<ufd-id>"

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        if self.root.name == "no":
            delete(self.conn, line[0])
        else:
            return UFDContext(self.context, line[0])


Root.register_command(
    "ufd",
    UFDCommand,
    when=ModelExists("goldstone-uplink-failure-detection"),
    add_no=True,
    no_completion_on_exec=True,
)


class UFDLinkCommand(Command):
    COMMAND_DICT = {"uplink": Command, "downlink": Command}


def get_ufd(conn, ifname):
    xpath = "/goldstone-uplink-failure-detection:ufd-groups"
    ufd = []

    for data in conn.get(f"{xpath}/ufd-group", []):
        for kind in ["uplink", "downlink"]:
            for intf in data.get("config", {}).get(kind, []):
                if intf == ifname:
                    ufd.append((data["ufd-id"], kind))

    return ufd


class InterfaceUFDCommand(ConfigCommand):
    def __init__(
        self, context: Context = None, parent: Command = None, name=None, **options
    ):
        super().__init__(context, parent, name, **options)
        if self.root.name != "no":
            for id in get_id(self.conn):
                self.add_command(str(id), UFDLinkCommand)

    def exec(self, line):
        if self.root.name == "no":
            check_ports(self.conn, self.context.ifnames)
        else:
            if len(line) != 2 or (line[1] != "uplink" and line[1] != "downlink"):
                raise InvalidInput(
                    f"usage: {self.name_all()} <ufdid> <uplink|downlink>"
                )
            add_ports(self.conn, line[0], self.context.ifnames, line[1])

    @classmethod
    def to_command(cls, conn, data):
        ifname = data.get("name")
        return [f"ufd {v[0]} {v[1]}" for v in get_ufd(conn, ifname)]


InterfaceContext.register_command(
    "ufd",
    InterfaceUFDCommand,
    when=ModelExists("goldstone-uplink-failure-detection"),
    add_no=True,
)
