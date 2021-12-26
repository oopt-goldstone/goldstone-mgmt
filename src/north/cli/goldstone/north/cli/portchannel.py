from .base import Command, InvalidInput
from .cli import (
    Context,
    GlobalShowCommand,
    RunningConfigCommand,
    TechSupportCommand,
    ModelExists,
)
from .root import Root
from .common import sysrepo_wrap, print_tabular
from tabulate import tabulate
from natsort import natsorted
from prompt_toolkit.completion import (
    FuzzyWordCompleter,
)
import sysrepo as sr

from .interface import InterfaceContext

import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

XPATH = "/goldstone-portchannel:portchannel"


def get_session(cmd):
    return cmd.context.root().conn.start_session()


def pcxpath(id):
    return f"{XPATH}/portchannel-group[portchannel-id='{id}']"


def create(session, id):
    sr_op = sysrepo_wrap(session)
    sr_op.set_data(f"{pcxpath(id)}/config/portchannel-id", id)


def delete(session, id):
    sr_op = sysrepo_wrap(session)
    sr_op.delete_data(pcxpath(id))


def get_list(session, ds, include_implicit_values=True):
    sr_op = sysrepo_wrap(session)
    try:
        tree = sr_op.get_data(XPATH, ds, include_implicit_values)
        return natsorted(
            tree["portchannel"]["portchannel-group"],
            key=lambda x: x["portchannel-id"],
        )
    except (KeyError, sr.errors.SysrepoNotFoundError) as error:
        return []


def add_interfaces(session, id, ifnames):
    sr_op = sysrepo_wrap(session)
    prefix = "/goldstone-interfaces:interfaces"
    for ifname in ifnames:
        xpath = f"{prefix}/interface[name='{ifname}']"
        # in order to create the interface node if it doesn't exist in running DS
        try:
            sr_op.get_data(xpath, "running")
        except sr.SysrepoNotFoundError as e:
            sr_op.set_data(f"{xpath}/config/name", ifname, no_apply=True)

        sr_op.set_data(f"{pcxpath(id)}/config/interface", ifname, no_apply=True)
    sr_op.apply()


def set_admin_status(session, id, value):
    sr_op = sysrepo_wrap(session)
    if value:
        sr_op.set_data(f"{pcxpath(id)}/config/admin-status", value)
    else:
        sr_op.delete_data(f"{pcxpath(id)}/config/admin-status")


def get_id(session):
    return [v["portchannel-id"] for v in get_list(session, "operational")]


def remove_interfaces(session, ifnames):
    sr_op = sysrepo_wrap(session)
    groups = get_list(session, "running")
    if len(groups) == 0:
        raise InvalidInput("portchannel not configured for this interface")

    for ifname in ifnames:
        for data in groups:
            try:
                if ifname in data["config"]["interface"]:
                    xpath = pcxpath(data["portchannel-id"])
                    sr_op.delete_data(
                        f"{xpath}/config/interface[.='{ifname}']", no_apply=True
                    )
                    break
            except KeyError:
                pass
        else:
            sr_op.discard_changes()
            raise InvalidInput(f"portchannel not configured for {ifname}")

    sr_op.apply()


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
    sr_op = sysrepo_wrap(session)
    try:
        tree = sr_op.get_data(XPATH, "operational")
        id_list = tree["portchannel"]["portchannel-group"]
    except (sr.SysrepoNotFoundError, KeyError):
        id_list = []
    except sr.SysrepoCallbackFailedError as e:
        raise InvalidInput(e.details[0][1] if e.details else str(e))

    if len(id_list) == 0:
        stdout.info(
            tabulate(
                [],
                ["Portchannel-ID", "oper-status", "admin-status", "Interface"],
                tablefmt="pretty",
            )
        )
    else:
        data_tabulate = []
        interface = []
        ids = []
        adm_st = []
        op_st = []

        if id != None:
            ids.append(id)
        else:
            for data in id_list:
                ids.append(data["portchannel-id"])

            ids = natsorted(ids)

        for id in ids:
            data = id_list[id]
            adm_st.append(data["state"]["admin-status"].lower())
            try:
                interface.append(natsorted(list(data["state"]["interface"])))
            except (sr.errors.SysrepoNotFoundError, KeyError):
                interface.append([])
            try:
                op_st.append(data["state"]["oper-status"].lower())
            except (sr.errors.SysrepoNotFoundError, KeyError):
                op_st.append("-")

        for i in range(len(ids)):

            if len(interface[i]) > 0:
                data_tabulate.append([ids[i], op_st[i], adm_st[i], interface[i][0]])
            else:
                data_tabulate.append([ids[i], op_st[i], adm_st[i], "-"])

            for j in range(1, len(interface[i])):
                data_tabulate.append(["", "", "", interface[i][j]])

            if i != len(ids) - 1:
                data_tabulate.append(["", "", "", ""])

        stdout.info(
            tabulate(
                data_tabulate,
                ["Portchannel-ID", "oper-status", "admin-status", "Interface"],
                tablefmt="pretty",
                colalign=("left",),
            )
        )


class PortchannelContext(Context):
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

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            set_admin_status(session, id, "DOWN")

        @self.command(FuzzyWordCompleter(["shutdown", "admin-status"]))
        def no(args):
            if len(args) != 1:
                raise InvalidInput(f"usage: no [shutdown|admin-status]")
            if args[0] == "shutdown":
                set_admin_status(session, id, "UP")
            elif args[0] == "admin-status":
                set_admin_status(session, id, None)
            else:
                raise InvalidInput(f"usage: no [shutdown|admin-status]")

        admin_status_list = ["up", "down"]

        @self.command(FuzzyWordCompleter(admin_status_list), name="admin-status")
        def admin_status(args):
            if len(args) != 1 or args[0] not in admin_status_list:
                raise InvalidInput(
                    f"usage: admin_status [{'|'.join(admin_status_list)}]"
                )
            set_admin_status(session, id, args[0].upper())

    def __str__(self):
        return "portchannel({})".format(self.id)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return show(get_session(self))
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
            return run_conf(get_session(self))
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "portchannel", Run, when=ModelExists("goldstone-portchannel")
)


class TechSupport(Command):
    def exec(self, line):
        show(get_session(self))
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
        return get_id(get_session(self))

    def usage(self):
        return "<portchannel-id>"

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")
        if self.parent and self.parent.name == "no":
            delete(get_session(self), line[0])
        else:
            return PortchannelContext(self.context, line[0])


Root.register_command(
    "portchannel",
    PortchannelCommand,
    when=ModelExists("goldstone-portchannel"),
    add_no=True,
    no_completion_on_exec=True,
)


class InterfacePortchannelCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            get_id(get_session(self))
        return []

    def exec(self, line):
        if self.root.name == "no":
            remove_interfaces(get_session(self), self.context.ifnames)
        else:
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <portchannel_id>")
            add_interfaces(get_session(self), line[0], self.context.ifnames)


InterfaceContext.register_command(
    "portchannel",
    InterfacePortchannelCommand,
    when=ModelExists("goldstone-portchannel"),
    add_no=True,
)
