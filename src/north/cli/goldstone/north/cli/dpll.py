from .base import InvalidInput
from .cli import (
    GlobalShowCommand,
    ModelExists,
    Context,
    Run,
    RunningConfigCommand,
    ConfigCommand,
    Command,
)
from .root import Root
from .util import dig_dict
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


class ModeCommand(ConfigCommand):
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

    @classmethod
    def to_command(cls, conn, data, **options):
        config = dig_dict(data, ["config", "mode"])
        if not config:
            return None
        return f"mode {config}"


class PhaseSlopeLimitCommand(ConfigCommand):
    def arguments(self):
        if self.root.name != "no":
            return ["unlimitted"]

    def exec(self, line):
        name = self.context.name
        xpath = dpll_xpath(name)
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            self.conn.delete(f"{xpath}/config/phase-slope-limit")
        else:
            if len(line) != 1:
                raise InvalidInput(f'usage: {self.name_all()} ["unlimitted"|<value>]')

            if "unlimitted".startswith(line[0]):
                line[0] = "unlimitted"

            self.conn.set(f"{xpath}/config/name", name)
            self.conn.set(f"{xpath}/config/phase-slope-limit", line[0])
        self.conn.apply()

    @classmethod
    def to_command(cls, conn, data, **options):
        config = dig_dict(data, ["config", "phase-slope-limit"])
        if not config:
            return None
        return f"phase-slope-limit {config}"


class LoopBandwidthCommand(ConfigCommand):
    def exec(self, line):
        name = self.context.name
        xpath = dpll_xpath(name)
        if self.root.name == "no":
            if len(line) != 0:
                raise InvalidInput(f"usage: {self.name_all()}")
            self.conn.delete(f"{xpath}/config/loop-bandwidth")
        else:
            if len(line) != 1:
                raise InvalidInput(f"usage: {self.name_all()} <value>")

            self.conn.set(f"{xpath}/config/name", name)
            self.conn.set(f"{xpath}/config/loop-bandwidth", line[0])
        self.conn.apply()

    @classmethod
    def to_command(cls, conn, data, **options):
        config = dig_dict(data, ["config", "loop-bandwidth"])
        if not config:
            return None
        return f"loop-bandwidth {config}"


class PriorityCommand(ConfigCommand):
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

    @classmethod
    def to_command(cls, conn, data, **options):
        config = dig_dict(data, ["config", "priority"])
        if not config:
            return None
        return f"priority {config}"


class InputRefContext(Context):
    OBJECT_NAME = "input-reference"

    def __init__(self, parent: Context, name: str = None):
        super().__init__(parent, name)
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

    def xpath(self):
        dpll = dpll_xpath(self.parent.name)
        return f"{dpll}/input-references/input-reference"


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
    OBJECT_NAME = "dpll"
    SUB_CONTEXTS = [InputRefContext]

    def __init__(self, parent: Context, name: str = None):
        super().__init__(parent, name=name)
        self.add_command("mode", ModeCommand, add_no=True)
        self.add_command(
            "phase-slope-limit",
            PhaseSlopeLimitCommand,
            add_no=True,
            no_completion_on_exec=True,  # this command can take "unlimitted" and numeric value as an argument
        )
        self.add_command("loop-bandwidth", LoopBandwidthCommand, add_no=True)
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
            for k in [
                "mode",
                "phase-slope-limit",
                "loop-bandwidth",
                "state",
                "selected-reference",
            ]:
                v = state.get(k, "-")
                if k == "phase-slope-limit":
                    if type(v) == int:
                        v = f"{v}ns/s"
                elif k == "loop-bandwidth":
                    v = f"{v}Hz"
                elif type(v) == bool:
                    v = "true" if v else "false"
                elif type(v) == str:
                    v = v.lower()

                rows.append((k, v))
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

    def xpath(self):
        return XPATH


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


RunningConfigCommand.register_command(
    "dpll", Run, when=ModelExists("goldstone-dpll"), ctx=DPLLContext
)
