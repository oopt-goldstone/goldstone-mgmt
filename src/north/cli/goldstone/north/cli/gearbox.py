from .base import InvalidInput, Command
from .cli import GlobalShowCommand, ModelExists, Context
from .root import Root
import sysrepo as sr
import logging
from .common import sysrepo_wrap

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


class GearboxContext(Context):
    def __init__(self, parent: Context, name: str):
        self.name = name
        super().__init__(parent)

        self.add_command("admin-status", AdminStatusCommand, add_no=True)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                data = self.get_operational_data(
                    f"/goldstone-gearbox:gearboxes/gearbox[name='{self.name}']/state",
                    [{}],
                )[0]

                rows = []
                for k in ["admin-status", "oper-status"]:
                    rows.append((k, data.get(k, "-").lower()))
                stdout.info(tabulate(rows))

    def __str__(self):
        return f"gearbox({self.name})"


class GearboxCommand(Command):
    def arguments(self):
        return get_names(self.context.session)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <name>")
        return GearboxContext(self.context, line[0])


Root.register_command("gearbox", GearboxCommand, when=ModelExists("goldstone-gearbox"))


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
