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


def dpll_input_ref_xpath(dpll, name):
    return f"{dpll_xpath(dpll)}/input-references/input-reference[name='{name}']"


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


class PriorityCommand(Command):
    def exec(self, line):
        dpll = self.context.parent.name
        name = self.context.name
        dxpath = dpll_xpath(dpll)
        xpath = dpll_input_ref_xpath(dpll, name)

        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            self.conn.delete(f"{xpath}/config/priority")
        else:
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <priority>")
            self.conn.set(f"{dxpath}/config/name", dpll)
            self.conn.set(f"{xpath}/config/name", name)
            self.conn.set(f"{xpath}/config/priority", line[0])
        self.conn.apply()


class InputRefContext(Context):
    def __init__(self, parent: Context, name: str):
        self.name = name
        super().__init__(parent)
        self.add_command("priority", PriorityCommand, add_no=True)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
                return

            data = self.conn.get_operational(
                dpll_input_ref_xpath(self.parent.name, self.name),
                {},
                one=True,
            )

            rows = []
            state = data.get("state", {})
            for k in ["priority", "alarm"]:
                v = state.get(k, "-")
                if isinstance(v, list):
                    v = "|".join(v)
                rows.append((k, v))
            stdout.info(tabulate(rows))

    def __str__(self):
        return f"input-reference({self.name})"


class InputRefCommand(Command):
    def arguments(self):
        data = self.conn.get_operational(
            f"/goldstone-dpll:dplls/dpll[name='{self.context.name}']",
            {},
            one=True,
        )
        clocks = data.get("input-references", {}).get("input-reference", [])
        return natsorted([c["name"] for c in clocks])

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <name>")

        if self.root.name != "no":
            return InputRefContext(self.context, line[0])
        else:
            xpath = dpll_input_ref_xpath(self.context.name, line[0])
            self.conn.delete(xpath)
            self.conn.apply()


class DPLLContext(Context):
    def __init__(self, parent: Context, name: str):
        self.name = name
        super().__init__(parent)
        self.add_command("mode", ModeCommand, add_no=True)
        self.add_command("input-reference", InputRefCommand, add_no=True)

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
                return

            data = self.conn.get_operational(
                dpll_xpath(self.name),
                {},
                one=True,
            )

            rows = []
            state = data.get("state", {})
            for k in ["mode", "state", "selected-reference"]:
                v = state.get(k, "-")
                if type(v) == bool:
                    v = "true" if v else "false"
                rows.append((k, v.lower()))
            stdout.info(tabulate(rows))
            stdout.info("")
            stdout.info("Input reference information:")

            cc_info = {}  # key: input-reference name, value: (gearbox info, clock info)
            if "goldstone-gearbox" in self.conn.models:
                gbs = self.conn.get_operational(
                    "/goldstone-gearbox:gearboxes/gearbox", []
                )
                for gb in gbs:
                    clks = gb.get("synce-reference-clocks", {}).get(
                        "synce-reference-clock", []
                    )
                    for clk in clks:
                        cc = clk["state"].get("component-connection", {})
                        if cc.get("dpll") == self.name and cc.get("input-reference"):
                            cc_info[cc.get("input-reference")] = (gb, clk)

            refs = []
            for c in natsorted(
                data.get("input-references", {}).get("input-reference", []),
                key=lambda v: v["name"],
            ):
                s = c["state"]
                connected_to = "-"
                cc = cc_info.get(c.get("name"))
                if cc:
                    gb = cc[0]["name"]
                    clk = cc[1]["name"]
                    connected_c = f"gearbox({gb})/synce-reference-clock({clk})"
                    connected_if = cc[1]["state"].get("reference-interface", "-")

                ref = [
                    c["name"],
                    s.get("priority", "-"),
                    connected_if,
                    connected_c,
                    "|".join(s.get("alarm", "")),
                ]
                refs.append(ref)

            stdout.info(
                tabulate(
                    refs,
                    [
                        "name",
                        "prio",
                        "connected-interface",
                        "connected-component",
                        "alarm",
                    ],
                )
            )

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
