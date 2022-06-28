from .base import InvalidInput

from goldstone.lib.errors import Error

from .cli import (
    Command,
    Context,
    Run,
    RunningConfigCommand,
    GlobalShowCommand,
    ModelExists,
    TechSupportCommand,
    ShowCommand,
    ConfigCommand,
)

from .root import Root
from .util import dig_dict, human_ber, object_names

from prompt_toolkit.completion import WordCompleter

import logging
from tabulate import tabulate
from natsort import natsorted
import re

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")

_FREQ_RE = re.compile(r".+[kmgt]?hz$")

XPATH = "/goldstone-transponder:modules/module"


def modulexpath(name):
    return f"{XPATH}[name='{name}']"


def module_names(session, ptn=None):
    return object_names(session, XPATH, ptn)


# Function to print data from show command with tabulate library
def print_tabular(h, table_title=""):
    if table_title != "":
        stdout.info(f"\n{table_title}")

    table = []
    skip_attrs = ["index", "location"]
    for k, v in h.items():
        if k in skip_attrs:
            continue
        table.append([k, v])

    stdout.info(tabulate(table))


def human_freq(item):
    if type(item) == str:
        try:
            int(item)
            return item
        except ValueError:
            item = item.lower()
            if not _FREQ_RE.match(item):
                raise InvalidInput("invalid frequency input. (e.g 193.50THz)")
            item = item[:-2]
            multiplier = 1
            if item[-1] == "t":
                multiplier = 1e12
            elif item[-1] == "g":
                multiplier = 1e9
            elif item[-1] == "m":
                multiplier = 1e6
            elif item[-1] == "k":
                multiplier = 1e3
            return str(round(float(item[:-1]) * multiplier))
    else:
        return "{0:.2f}THz".format(int(item) / 1e12)


def to_human(d, runconf=False):
    for key in d:
        if key.endswith("-ber"):
            d[key] = human_ber(d[key])
        elif "freq" in key:
            d[key] = human_freq(d[key])
        elif type(d[key]) == bool:
            d[key] = "true" if d[key] else "false"
        elif not runconf and key.endswith("power"):
            d[key] = f"{float(d[key]):.2f} dBm"
        elif isinstance(d[key], list):
            d[key] = ", ".join(d[key])

    return d


def show_transponder(session, name):
    xpath = modulexpath(name)
    data = session.get_operational(xpath, one=True)
    if data == None:
        stderr.info(f"no operational info found for {name}")
        return

    # module info
    print_tabular(data["state"])

    for netif in natsorted(data.get("network-interface", []), key=lambda v: v["name"]):
        print_tabular(to_human(netif["state"]), f"Network Interface {netif['name']}")

    for hostif in natsorted(data.get("host-interface", []), key=lambda v: v["name"]):
        print_tabular(to_human(hostif["state"]), f"Host Interface {hostif['name']}")


def show_transponder_summary(session):
    attrs = [
        "vendor-name",
        "vendor-part-number",
        "vendor-serial-number",
        "admin-status",
        "oper-status",
    ]
    rows = []
    for module in module_names(session):
        prefix = modulexpath(module)
        data = [module]
        for attr in attrs:
            xpath = f"{prefix}/state/{attr}"
            try:
                v = session.get_operational(xpath, "N/A", one=True)
            except Error:
                v = "N/A"
            data.append(v)
        rows.append(data)

    if len(rows) == 0:
        stderr.info(f"no operational info found for transponders")
        return

    # insert "transponder" for the header use
    attrs.insert(0, "transponder")

    stdout.info(tabulate(rows, attrs, tablefmt="pretty", colalign="left"))


class SetCommand(ConfigCommand):
    def exec(self, line):
        node = self.options["node"]
        if self.root.name == "no":
            self.context.delete(node)
        else:
            if len(line) != 1:
                raise InvalidInput(self.usage())

            enum_values = self.arguments()
            if len(enum_values) and line[0] not in enum_values:
                raise InvalidInput(self.usage())

            if node.name() == "tx-laser-freq":
                value = human_freq(line[0])
            else:
                value = line[0]

            self.context.set(node, value)

    def arguments(self):
        if self.root.name == "no":
            return
        node = self.options["node"]
        if node.type() == "boolean":
            return ["true", "false"]
        return [v for v in node.enums() if v != "unknown"]

    def usage(self):
        enum_values = self.arguments()
        node = self.options["node"]
        if len(enum_values):
            v = "[" + "|".join(enum_values) + "]"
        else:
            v = f"<{node.type()}>"
        return f"usage: {node.name()} {v}"

    @classmethod
    def to_command(cls, conn, data, **options):
        node = options["node"]
        data = dig_dict(data, ["config", node.name()])
        if data:
            if node.type() == "boolean":
                v = "true" if data else "false"
            elif "freq" in node.name():
                v = human_freq(data)
            elif type(data) == str:
                v = data.lower()
            else:
                v = data
            return f"{node.name()} {v}"


class ShutdownCommand(Command):
    def exec(self, line):
        if self.root.name == "no":
            self.context.set("admin-status", "up")
        else:
            if len(line) != 0:
                raise InvalidInput(self.usage())
            self.context.set("admin-status", "down")

    def usage(self):
        return f"usage: shutdown"


class TransponderShowCommand(ShowCommand):
    COMMAND_DICT = {
        "details": Command,
    }
    SKIP_ATTRS = ["index", "location"]

    def exec(self, line):
        ctx = self.context
        if len(line) != 0:
            if line[0] == "details":
                return self.show(detail=True)
            ctx.root().exec(f"show {' '.join(line)}")
            return ctx

        self.show()

    def show(self, detail=False):
        ctx = self.context
        for obj in self.context.objs:
            if len(self.context.objs) > 1:
                stdout.info(f"{self.context.OBJECT_NAME}({obj}):")

            xpath = ctx.xpath(obj) + "/state"
            data = self.conn.get_operational(xpath, one=True)
            if data == None:
                raise InvalidInput("Not able to fetch data from operational database")

            data = to_human(data)

            table = []
            for k, v in data.items():
                if k in self.SKIP_ATTRS:
                    continue
                if not detail and k in self.context.DETAILED_ATTRS:
                    continue
                table.append([k, v])

            stdout.info(tabulate(table))


class TransponderBaseContext(Context):
    DETAILED_ATTRS = []

    def __init__(self, parent, name):
        super().__init__(parent, name, fuzzy_completion=True)
        node = self.conn.find_node(self.CONFIG_XPATH)

        for v in node.children():
            if v.name() == "name":
                continue
            self.add_command(v.name(), SetCommand, add_no=True, node=v)

            # special handling for "shutdown", backward compatibility
            if v.name() == "admin-status":
                self.add_command("shutdown", ShutdownCommand, add_no=True)

        self.add_command("show", TransponderShowCommand(self))

    def set(self, node, value):
        if type(node) == str:
            name = node
        else:
            name = node.name()

        self.conn.set(f"{self.module_xpath()}/config/name", self.module_name())

        for obj in self.objs:
            self.conn.set(f"{self.xpath(obj)}/config/name", obj)
            self.conn.set(f"{self.xpath(obj)}/config/{name}", value)

        self.conn.apply()

    def delete(self, node):
        name = node.name()

        for obj in self.objs:
            self.conn.delete(f"{self.xpath(obj)}/config/{name}")
        self.conn.apply()

    def components(self, type_, ptn=None):
        xpath = f"{self.module_xpath()}/{type_}/name"
        data = self.conn.get_operational(xpath, [], one=True)

        if ptn:
            try:
                ptn = re.compile(ptn)
            except re.error:
                raise InvalidInput(f"failed to compile {ptn} as a regular expression")
            f = ptn.match
        else:
            f = lambda _: True
        return natsorted(v for v in data if f(v))


class InterfaceContext(TransponderBaseContext):
    def module_xpath(self):
        return self.parent.module_xpath()

    def xpath(self, name=None):
        v = f"{self.module_xpath()}/{self.OBJECT_TYPE}"
        if name != None:
            v += f"[name='{name}']"
        return v

    def module_name(self):
        return self.parent.name

    def __init__(self, parent, name=None):
        super().__init__(parent, name)

        if name == None:  # running config context
            return

        objs = self.components(self.OBJECT_TYPE, name)
        if len(objs) == 0:
            raise InvalidInput(f"No {self.OBJECT_NAME} with name {name}")
        elif len(objs) > 1 or objs[0] != name:
            stdout.info(f"Selected interfaces: {objs}")

            @self.command()
            def selected(args):
                if len(args) != 0:
                    raise InvalidInput("usage: selected[cr]")
                stdout.info(", ".join(objs))

        self.objs = objs


class HostInterfaceContext(InterfaceContext):
    OBJECT_TYPE = "host-interface"
    OBJECT_NAME = "hostif"
    CONFIG_XPATH = "".join(
        f"/goldstone-transponder:{v}"
        for v in ["modules", "module", OBJECT_TYPE, "config"]
    )


class NetworkInterfaceContext(InterfaceContext):
    OBJECT_TYPE = "network-interface"
    OBJECT_NAME = "netif"
    CONFIG_XPATH = "".join(
        f"/goldstone-transponder:{v}"
        for v in ["modules", "module", OBJECT_TYPE, "config"]
    )
    DETAILED_ATTRS = [
        "pulse-shaping-tx",
        "pulse-shaping-rx",
        "pulse-shaping-tx-beta",
        "pulse-shaping-rx-beta",
        "losi",
        "laser-grid-support",
        "disable-constellation",
        "custom-trb100-rx-power-low-warning-threshold",
        "custom-trb100-rx-power-low-alarm-threshold",
        "custom-trb100-rx-los",
        "ber-period",
        "current-ber-period",
    ]


class InterfaceCommand(Command):
    def arguments(self):
        return self.context.components(self.OBJECT_TYPE)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <name>")
        if self.root.name == "no":
            names = self.context.components(self.OBJECT_TYPE, line[0])
            for name in names:
                xpath = (
                    f"{self.context.module_xpath()}/{self.OBJECT_TYPE}[name='{name}']"
                )
                self.conn.delete(xpath)
            self.conn.apply()
        else:
            return self.OBJECT_CONTEXT(self.context, line[0])


class HostInterfaceCommand(InterfaceCommand):
    OBJECT_TYPE = "host-interface"
    OBJECT_CONTEXT = HostInterfaceContext


class NetworkInterfaceCommand(InterfaceCommand):
    OBJECT_TYPE = "network-interface"
    OBJECT_CONTEXT = NetworkInterfaceContext


class TransponderContext(TransponderBaseContext):
    OBJECT_TYPE = "module"
    OBJECT_NAME = "transponder"
    XPATH = "/goldstone-transponder:modules/module"
    CONFIG_XPATH = "".join(
        f"/goldstone-transponder:{v}" for v in ["modules", "module", "config"]
    )
    SUB_CONTEXTS = [NetworkInterfaceContext, HostInterfaceContext]

    def module_xpath(self):
        return f"{self.XPATH}[name='{self.name}']"

    def xpath(self, name=None):
        if name == None:
            return self.XPATH
        return self.module_xpath()

    def module_name(self):
        return self.name

    def __init__(self, parent, name=None):
        super().__init__(parent, name)

        if name == None:  # running config context
            return

        self.objs = [name]

        self.add_command(
            "netif", NetworkInterfaceCommand, add_no=True, no_completion_on_exec=True
        )
        self.add_command(
            "hostif", HostInterfaceCommand, add_no=True, no_completion_on_exec=True
        )


class Show(Command):
    def arguments(self):
        return ["summary"] + module_names(self.conn)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(self.usage())

        if line[0] == "summary":
            return show_transponder_summary(self.conn)
        else:
            return show_transponder(self.conn, line[0])

    def usage(self):
        return f"usage: {self.name_all()} {{ summary | <transponder_name> }}"


GlobalShowCommand.register_command(
    "transponder", Show, when=ModelExists("goldstone-transponder")
)


RunningConfigCommand.register_command(
    "transponder",
    Run,
    when=ModelExists("goldstone-transponder"),
    ctx=TransponderContext,
)


class TechSupport(Command):
    def exec(self, line):
        stdout.info("\nshow transponder details:\n")
        modules = module_names(self.conn)
        for module in modules:
            stdout.info(f"Transponder {module}")
            show_transponder(self.conn, module)
        self.parent.xpath_list.append("/goldstone-transponder:modules")


TechSupportCommand.register_command(
    "transponder", TechSupport, when=ModelExists("goldstone-transponder")
)


class TransponderCommand(Command):
    def arguments(self):
        return module_names(self.conn)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <name>")
        if self.root.name == "no":
            for name in module_names(self.conn, line[0]):
                self.conn.delete(modulexpath(name))
            self.conn.apply()
        else:
            return TransponderContext(self.context, line[0])


Root.register_command(
    "transponder",
    TransponderCommand,
    when=ModelExists("goldstone-transponder"),
    add_no=True,
)
