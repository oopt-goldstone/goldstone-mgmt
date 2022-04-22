from .base import InvalidInput
from .cli import GlobalShowCommand, ModelExists, Context, RunningConfigCommand, Command
from .root import Root
import logging
from prompt_toolkit.completion import Completion, Completer

from tabulate import tabulate
from natsort import natsorted

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

XPATH = "/goldstone-dpll:dplls/dpll"


def dpll_xpath(name):
    return f"{XPATH}[name='{name}']"


class ModeCommand(Command):
    def arguments(self):
        if self.root.name != "no":
            return ["automatic", "freerun"]

    def exec(self, line):
        name = self.context.name
        xpath = dpll_xpath(name)
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            self.conn.delete(f"{xpath}/config/mode")
        else:
            if len(line) != 1:
                raise InvalidInput(
                    f"usage: {self.name_all()} [{'|'.join(self.list())}]"
                )
            self.conn.set(f"{xpath}/config/name", name)
            self.conn.set(f"{xpath}/config/mode", line[0])
        self.conn.apply()


class DPLLContext(Context):
    def __init__(self, parent: Context, name: str):
        self.name = name
        super().__init__(parent)
        self.add_command("mode", ModeCommand, add_no=True)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                data = self.conn.get_operational(
                    dpll_xpath(self.name),
                    {},
                    one=True,
                )

                rows = []
                state = data.get("state", {})
                for k in ["mode", "state"]:
                    v = state.get(k, "-")
                    if type(v) == bool:
                        v = "true" if v else "false"
                    rows.append((k, v.lower()))
                stdout.info(tabulate(rows))

    def __str__(self):
        return f"dpll({self.name})"


class DPLLCommand(Command):
    def arguments(self):
        return natsorted(v for v in self.conn.get_operational(XPATH + "/name", []))

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <name>")

        if self.root.name == "no":
            xpath = dpll_xpath(line[0])
            self.conn.delete(xpath)
            self.conn.apply()
        else:
            return DPLLContext(self.context, line[0])


Root.register_command(
    "dpll", DPLLCommand, when=ModelExists("goldstone-dpll"), add_no=True
)


class Show(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")
        data = self.conn.get_operational(XPATH, [])
        rows = []
        for d in data:
            state = d.get("state", {})
            rows.append((d["name"], state.get("mode", "-"), state.get("state", "-")))

        stdout.info(tabulate(rows, ["name", "mode", "state"], tablefmt="pretty"))


GlobalShowCommand.register_command("dpll", Show, when=ModelExists("goldstone-dpll"))


class Run(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")
        data = self.conn.get(XPATH, [])
        for d in data:
            stdout.info(f"dpll {d['name']}")
            config = d.get("config")
            if config:
                for key, value in config.items():
                    if key == "mode":
                        stdout.info(f"  mode {value.lower()}")

            stdout.info(f"  quit")


RunningConfigCommand.register_command("dpll", Run, when=ModelExists("goldstone-dpll"))
