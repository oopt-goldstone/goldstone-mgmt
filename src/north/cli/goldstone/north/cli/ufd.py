from .base import Command, InvalidInput
from .cli import (
    GSObject as Object,
    GlobalShowCommand,
    RunningConfigCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
from .common import sysrepo_wrap, print_tabular
from tabulate import tabulate
from natsort import natsorted
import sysrepo as sr

from .interface import InterfaceObject

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


XPATH = "/goldstone-uplink-failure-detection:ufd-groups"


def get_session(cmd):
    return cmd.context.root().conn.start_session()


def xpath(id):
    return f"{XPATH}/ufd-group[ufd-id='{id}']"


def create(session, id):
    sr_op = sysrepo_wrap(session)
    sr_op.set_data(f"{xpath(id)}/config/ufd-id", id)


def delete(session, id):
    sr_op = sysrepo_wrap(session)
    sr_op.delete_data(xpath(id))


def add_ports(session, id, ports, role):
    sr_op = sysrepo_wrap(session)
    prefix = "/goldstone-interfaces:interfaces"
    for port in ports:
        x = f"{prefix}/interface[name='{port}']"
        # in order to create the interface node if it doesn't exist in running DS
        sr_op.set_data(f"{x}/config/name", port, no_apply=True)
        sr_op.set_data(f"{xpath(id)}/config/{role}", port, no_apply=True)
    sr_op.apply()


def remove_ports(session, id, role, ports, no_apply=False):
    sr_op = sysrepo_wrap(session)
    xpath = xpath(id)
    for port in ports:
        sr_op.delete_data(f"{xpath}/config/{role}[.='{port}']", no_apply=True)

    if not no_apply:
        sr_op.apply()


def get_id(session):
    sr_op = sysrepo_wrap(session)
    path = "/goldstone-uplink-failure-detection:ufd-groups"
    try:
        d = sr_op.get_data(XPATH, "operational")
        d = d.get("ufd-groups", {}).get("ufd-group", {})
        return natsorted(v["ufd-id"] for v in d)
    except (sr.errors.SysrepoNotFoundError, KeyError):
        return []


def check_ports(session, ports):
    sr_op = sysrepo_wrap(session)
    try:
        data = sr_op.get_data(f"{XPATH}/ufd-group", "running")
        ufds = data["ufd-groups"]["ufd-group"]
    except (sr.errors.SysrepoNotFoundError, KeyError):
        raise InvalidInput("UFD not configured for this interface")

    for port in ports:
        found = False
        for ufd in ufds:
            config = ufd["config"]
            for role in ["uplink", "downlink"]:
                links = config.get(role, [])
                if port in links:
                    found = True
                    remove_ports(session, ufd["ufd-id"], role, [port], True)

        if not found:
            sr_op.discard_changes()
            raise InvalidInput("ufd not configured for this interface")

    sr_op.apply()


def show(session, id=None):
    sr_op = sysrepo_wrap(session)
    try:
        tree = sr_op.get_data(f"{XPATH}/ufd-group", "operational")
        id_list = tree["ufd-groups"]["ufd-group"]
    except (sr.SysrepoNotFoundError, KeyError):
        id_list = []
    except sr.SysrepoCallbackFailedError as e:
        raise InvalidInput(e.details[0][1] if e.details else str(e))

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
        ids = []

        if id != None:
            ids.append(id)
        else:
            for data in id_list:
                ids.append(data["ufd-id"])

            ids = natsorted(ids)

        for id in ids:
            data = id_list[id]
            try:
                uplink_ports.append(natsorted(list(data["config"]["uplink"])))
            except (sr.errors.SysrepoNotFoundError, KeyError):
                uplink_ports.append([])
            try:
                downlink_ports.append(natsorted(list(data["config"]["downlink"])))
            except (sr.errors.SysrepoNotFoundError, KeyError):
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
    sr_op = sysrepo_wrap(session)
    try:
        tree = sr_op.get_data(f"{XPATH}/ufd-group", "running")
        d_list = tree["ufd-groups"]["ufd-group"]
    except (sr.errors.SysrepoNotFoundError, KeyError):
        return

    ids = []

    for data in d_list:
        ids.append(data["ufd-id"])

    ids = natsorted(ids)

    for id in ids:
        data = d_list[id]
        stdout.info("ufd {}".format(data["config"]["ufd-id"]))
        stdout.info("  quit")
        stdout.info("!")


class UFDObject(Object):
    def __init__(self, parent, id):
        self.id = id
        super().__init__(parent)
        session = self.root().conn.start_session()
        create(session, self.id)

        @self.command(parent.get_completer("show"), name="show")
        def show_(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                show(session, self.id)

    def __str__(self):
        return "ufd({})".format(self.id)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return show(get_session(self))
        else:
            stderr.info(self.usage())


GlobalShowCommand.register_command(
    "ufd", Show, when=ModelExists("goldstone-uplink-failure-detection")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return run_conf(get_session(self))
        else:
            stderr.info(self.usage())


RunningConfigCommand.register_command(
    "ufd", Run, when=ModelExists("goldstone-uplink-failure-detection")
)


class TechSupport(Command):
    def exec(self, line):
        show(get_session(self))
        self.parent.xpath_list.append("/goldstone-uplink-failure-detection:ufd-groups")


TechSupportCommand.register_command(
    "ufd", TechSupport, when=ModelExists("goldstone-uplink-failure-detection")
)


class UFDCommand(Command):
    def arguments(self):
        return get_id(get_session(self))

    def usage(self):
        return "<ufd-id>"

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        if self.parent and self.parent.name == "no":
            delete(get_session(self), line[0])
        else:
            return UFDObject(self.context, line[0])


Root.register_command(
    "ufd",
    UFDCommand,
    when=ModelExists("goldstone-uplink-failure-detection"),
    add_no=True,
    no_completion_on_exec=True,
)


class UFDLinkCommand(Command):
    COMMAND_DICT = {"uplink": Command, "downlink": Command}


class InterfaceUFDCommand(Command):
    def __init__(
        self, context: Object = None, parent: Command = None, name=None, **options
    ):
        super().__init__(context, parent, name, **options)
        if self.root.name != "no":
            for id in get_id(get_session(self)):
                self.add_command(str(id), UFDLinkCommand)

    def exec(self, line):
        if self.root.name == "no":
            check_ports(get_session(self), self.context.ifnames)
        else:
            if len(line) != 2 or (line[1] != "uplink" and line[1] != "downlink"):
                raise InvalidInput(
                    f"usage: {self.name_all()} <ufdid> <uplink|downlink>"
                )
            add_ports(get_session(self), line[0], self.context.ifnames, line[1])


InterfaceObject.register_command(
    "ufd",
    InterfaceUFDCommand,
    when=ModelExists("goldstone-uplink-failure-detection"),
    add_no=True,
)
