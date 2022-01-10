from .base import InvalidInput, Command
from .cli import GlobalShowCommand, ModelExists, Context, RunningConfigCommand
from .root import Root
import sysrepo as sr
import logging
from .common import sysrepo_wrap
from prompt_toolkit.completion import Completion, Completer, FuzzyWordCompleter

from tabulate import tabulate
from natsort import natsorted

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

XPATH = "/goldstone-gearbox:gearboxes/gearbox"


def get_names(session):
    sr_op = sysrepo_wrap(session)
    try:
        d = sr_op.get_data(XPATH, "operational")
        d = d.get("gearboxes", {}).get("gearbox", {})
        return natsorted(v["name"] for v in d)
    except sr.SysrepoNotFoundError:
        return []


def gbxpath(name):
    return f"{XPATH}[name='{name}']"


def set_admin_status(session, name, value):
    sr_op = sysrepo_wrap(session)

    xpath = gbxpath(name)
    if value:
        sr_op.set_data(f"{xpath}/config/name", name, no_apply=True)
        sr_op.set_data(f"{xpath}/config/admin-status", value, no_apply=True)
    else:
        sr_op.delete_data(f"{xpath}/config/admin-status", no_apply=True)

    sr_op.apply()


def set_enable_flexible_connection(session, name, value):
    sr_op = sysrepo_wrap(session)

    xpath = gbxpath(name)
    if value:
        sr_op.set_data(f"{xpath}/config/name", name, no_apply=True)
        sr_op.set_data(
            f"{xpath}/config/enable-flexible-connection", value, no_apply=True
        )
    else:
        sr_op.delete_data(f"{xpath}/config/enable-flexible-connection", no_apply=True)

    sr_op.apply()


class AdminStatusCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["up", "down"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_admin_status(self.context.session, self.context.name, None)
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_admin_status(self.context.session, self.context.name, line[0].upper())


class ConnectionCompleter(Completer):
    def __init__(self, command):
        self.command = command

    def get_completions(self, document, complete_event=None):
        t = document.text.split()
        is_space_trailing = bool(len(document.text)) and (document.text[-1] == " ")
        if len(t) == 0 or (len(t) == 1 and not is_space_trailing):
            for c in self.command.client_interfaces():
                if c.startswith(document.text):
                    yield Completion(c, start_position=-len(document.text))
        elif (len(t) == 1 and is_space_trailing) or (
            len(t) == 2 and not is_space_trailing
        ):
            text = document.text[len(t[0]) :].lstrip()
            for c in self.command.line_interfaces(t[0]):
                if c.startswith(text):
                    yield Completion(c, start_position=-len(text))


class ConnectionCommand(Command):
    # this command takes two positional arguments client-interface and line-interface
    def __init__(self, context, parent, name, **options):
        options["additional_completer"] = ConnectionCompleter(self)
        super().__init__(context, parent, name, **options)

    def _parse(self, elems, is_space_trailing, info, fuzzy, nest=0):
        # return all candidates
        if len(elems) == 0:
            info.append(self.client_interfaces())
            return

        # do client-interface completion and return
        # no perfect match needed because we're still completing elems[0]
        if len(elems) == 1 and not is_space_trailing:
            try:
                elected = self.complete_subcommand(
                    elems[0],
                    fuzzy,
                    find_perfect_match=False,
                    l=self.client_interfaces(),
                )
            except InvalidInput as e:
                info.append(e)
            else:
                info.append(elected)
            return

        # now (len(elems) == 1 and is_space_trailing) or len(elems) > 1
        # first complete elems[0]. find perfect match
        try:
            elected = self.complete_subcommand(
                elems[0],
                fuzzy,
                find_perfect_match=True,
                l=self.client_interfaces(),
            )
        except InvalidInput as e:
            info.append(e)
            return
        else:
            info.append(elected)
            # if len(elems) == 1 return all candidates and return
            if len(elems) == 1:
                info.append(self.line_interfaces(elected))
                return

        # now len(elems) > 1 and elems[0] is completed (=elected)
        try:
            elected = self.complete_subcommand(
                elems[1],
                fuzzy,
                find_perfect_match=is_space_trailing,
                l=self.line_interfaces(elected),
            )
        except InvalidInput as e:
            info.append(e)
        else:
            info.append(elected)

        # this command doesn't take arguments more than 2.
        # append an empty list to indicate this
        if len(elems) > 2 or is_space_trailing:
            info.append([])

    def exec(self, line):
        if len(line) != 2:
            raise InvalidInput(
                f"usage: {self.name_all()} <client interface> <line interface>"
            )

        client = self.complete_subcommand(
            line[0],
            True,
            find_perfect_match=True,
            l=self.client_interfaces(),
        )

        line = self.complete_subcommand(
            line[1],
            True,
            find_perfect_match=True,
            l=self.line_interfaces(client),
        )

        sr_op = sysrepo_wrap(self.context.session)

        name = self.context.name
        xpath = gbxpath(name)
        if self.root.name != "no":
            sr_op.set_data(f"{xpath}/config/name", name, no_apply=True)
            sr_op.set_data(
                f"/goldstone-interfaces:interfaces/interface[name='{client}']/config/name",
                client,
                no_apply=True,
            )
            sr_op.set_data(
                f"/goldstone-interfaces:interfaces/interface[name='{line}']/config/name",
                line,
                no_apply=True,
            )
            xpath = f"{xpath}/connections/connection[client-interface='{client}'][line-interface='{line}']"
            sr_op.set_data(
                f"{xpath}/config/client-interface",
                client,
                no_apply=True,
            )
            sr_op.set_data(
                f"{xpath}/config/line-interface",
                line,
                no_apply=True,
            )
        else:
            xpath = f"{xpath}/connections/connection[client-interface='{client}'][line-interface='{line}']"
            sr_op.delete_data(xpath, no_apply=True)

        sr_op.apply()

    def _interfaces(self, kind):
        name = self.context.name
        xpath = (
            "/goldstone-interfaces:interfaces"
            f"/interface[state/goldstone-gearbox:associated-gearbox='{name}']"
            "/goldstone-component-connection:component-connection"
        )
        v = self.context.get_operational_data(xpath, {}, strip=False)
        interfaces = v.get("interfaces", {}).get("interface", [])
        return (
            i["name"] for i in interfaces if kind in i.get("component-connection", {})
        )

    def client_interfaces(self):
        return self._interfaces("platform")

    def line_interfaces(self, client):
        return self._interfaces("transponder")


class EnableFlexibleConnectionCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["true", "false"]

    def exec(self, line):
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            set_enable_flexible_connection(
                self.context.session, self.context.name, None
            )
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            set_enable_flexible_connection(
                self.context.session, self.context.name, line[0] == "true"
            )


class GearboxContext(Context):
    def __init__(self, parent: Context, name: str):
        self.name = name
        super().__init__(parent)

        self.add_command("admin-status", AdminStatusCommand, add_no=True)
        self.add_command(
            "enable-flexible-connection", EnableFlexibleConnectionCommand, add_no=True
        )
        self.add_command("connection", ConnectionCommand, add_no=True)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                data = self.get_operational_data(
                    f"/goldstone-gearbox:gearboxes/gearbox[name='{self.name}']",
                    [{}],
                )[0]

                rows = []
                state = data.get("state", {})
                for k in ["admin-status", "oper-status", "enable-flexible-connection"]:
                    v = state.get(k, "-")
                    if type(v) == bool:
                        v = "true" if v else "false"
                    rows.append((k, v.lower()))

                stdout.info(tabulate(rows))

                stdout.info("")

                connections = []

                for c in natsorted(
                    data.get("connections", {}).get("connection", []),
                    key=lambda v: v["client-interface"],
                ):
                    connections.append(
                        (c["client-interface"], "<---->", c["line-interface"])
                    )

                stdout.info(tabulate(connections, ["client", "", "line"]))

    def __str__(self):
        return f"gearbox({self.name})"


class GearboxCommand(Command):
    def arguments(self):
        return get_names(self.context.session)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <name>")

        if self.root.name == "no":
            xpath = gbxpath(line[0])
            sr_op = sysrepo_wrap(self.context.session)
            sr_op.delete_data(xpath)
        else:
            return GearboxContext(self.context, line[0])


Root.register_command(
    "gearbox", GearboxCommand, when=ModelExists("goldstone-gearbox"), add_no=True
)


class Show(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")
        data = self.context.get_operational_data(
            "/goldstone-gearbox:gearboxes/gearbox", []
        )
        rows = []
        for d in data:
            state = d.get("state", {})
            rows.append(
                (
                    d["name"],
                    state.get("oper-status", "-").lower(),
                    state.get("admin-status", "-").lower(),
                )
            )
        stdout.info(
            tabulate(rows, ["name", "oper-status", "admin-status"], tablefmt="pretty")
        )


GlobalShowCommand.register_command(
    "gearbox", Show, when=ModelExists("goldstone-gearbox")
)


class Run(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")
        data = self.context.get_running_data("/goldstone-gearbox:gearboxes/gearbox", [])
        for d in data:
            stdout.info(f"gearbox {d['name']}")
            config = d.get("config")
            if config:
                for key, value in config.items():
                    if key == "admin-status":
                        stdout.info(f"  admin-status {value.lower()}")
                    elif key == "enable-flexible-connection":
                        stdout.info(
                            f"  enable-flexible-connection {'true' if value else 'false'}"
                        )
            connections = d.get("connections", {}).get("connection", [])

            for conn in connections:
                stdout.info(
                    f"  connection {conn['client-interface']} {conn['line-interface']}"
                )
                stdout.info(f"    quit")
            stdout.info(f"  quit")


RunningConfigCommand.register_command(
    "gearbox", Run, when=ModelExists("goldstone-gearbox")
)