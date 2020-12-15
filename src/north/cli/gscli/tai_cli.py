from .tai import Transponder, human_freq, to_human
from .base import InvalidInput, Completer, Command
from .cli import GSObject as Object
from prompt_toolkit.completion import WordCompleter, NestedCompleter
from .common import sysrepo_wrap, print_tabular
import sysrepo as sr
import logging

logger = logging.getLogger(__name__)


class TAICommand(Command):
    def __init__(self, context, node):
        self.node = node
        super().__init__(context, name=node.name())

    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(self.usage())

        enum_values = self.list()
        if len(enum_values) and line[0] not in enum_values:
            raise InvalidInput(self.usage())

        if self.node.name() == "tx-laser-freq":
            value = human_freq(line[0])
        else:
            value = line[0]

        self.context.set(self.node, value)

    def list(self):
        if str(self.node.type()) == "boolean":
            return ["true", "false"]
        return [v[0] for v in self.node.type().all_enums() if v[0] != "unknown"]

    def usage(self):
        enum_values = self.list()
        v = f"<{self.node.type()}>"
        if len(enum_values):
            v = "[" + "|".join(enum_values) + "]"
        return f"usage: {self.node.name()} {v}"


class TAINoCommand(Command):
    def __init__(self, context, node):
        self._list = [v.name() for v in node if v.name() != "name"]
        super().__init__(context, name="no")

    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(self.usage())

        if line[0] not in self.list():
            raise InvalidInput(self.usage())

        self.context.delete(line[0])

    def list(self):
        return self._list

    def usage(self):
        return f"usage: no [{'|'.join(self.list())}]"


class TAIObject(Object):
    def __init__(self, conn, parent):
        super().__init__(parent, fuzzy_completion=True)

        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        ctx = self.session.get_ly_ctx()

        node = [n for n in ctx.find_path(self.CONFIG_XPATH)]
        assert len(node) == 1
        node = node[0]

        for v in node:
            if v.name() == "name":
                continue
            self.add_command(TAICommand(self, v))

        self.add_command(TAINoCommand(self, node))

    def set(self, node, value):
        name = node.name()
        try:
            self.sr_op.get_data(self.module_xpath(), "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(
                f"{self.module_xpath()}/config/name", self.module_name()
            )

        try:
            self.sr_op.get_data(self.xpath(), "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(f"{self.xpath()}/config/name", self.name)

        self.sr_op.set_data(f"{self.xpath()}/config/{name}", value)

    def delete(self, name):
        self.sr_op.delete_data(f"{self.xpath()}/config/{name}")


class HostIf(TAIObject):
    CONFIG_XPATH = "".join(
        f"/goldstone-tai:{v}" for v in ["modules", "module", "host-interface", "config"]
    )

    def module_xpath(self):
        return self.parent.xpath()

    def xpath(self):
        return f"{self.module_xpath()}/host-interface[name='{self.name}']"

    def module_name(self):
        return self.parent.name

    def __init__(self, conn, parent, name):
        super().__init__(conn, parent)
        self.name = name

        @self.command(parent.parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)

            xpath = self.xpath()

            try:
                data = self.sr_op.get_data(xpath, "operational")
            except sr.SysrepoNotFoundError as e:
                print("Not able to fetch data from operational database")
                return
            try:
                h = data["modules"]["module"][self.parent.name]["host-interface"][
                    self.name
                ]["state"]
                print_tabular(h, "")
            except KeyError as e:
                print(f"Error while fetching values from operational database")
                return

    def __str__(self):
        return "hostif({})".format(self.name)


class NetIf(TAIObject):
    CONFIG_XPATH = "".join(
        f"/goldstone-tai:{v}"
        for v in ["modules", "module", "network-interface", "config"]
    )

    def module_xpath(self):
        return self.parent.xpath()

    def xpath(self):
        return f"{self.module_xpath()}/network-interface[name='{self.name}']"

    def module_name(self):
        return self.parent.name

    def __init__(self, conn, parent, name):
        super().__init__(conn, parent)
        self.name = name

        @self.command(parent.parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)

            xpath = self.xpath()

            try:
                data = self.sr_op.get_data(xpath, "operational")
            except sr.SysrepoNotFoundError as e:
                print("Not able to fetch data from operational database")
                return
            try:
                h = data["modules"]["module"][self.parent.name]["network-interface"][
                    self.name
                ]["state"]
                print_tabular(to_human(h), "")
            except KeyError as e:
                print(f"Error while fetching values from operational database")
                return

    def __str__(self):
        return "netif({})".format(self.name)


class Transponder(TAIObject):
    XPATH = "/goldstone-tai:modules/module"
    CONFIG_XPATH = "".join(
        f"/goldstone-tai:{v}" for v in ["modules", "module", "config"]
    )

    def module_xpath(self):
        return f"{self.XPATH}[name='{self.name}']"

    def xpath(self):
        return self.module_xpath()

    def module_name(self):
        return self.name

    def __init__(self, conn, parent, name):
        super().__init__(conn, parent)
        self.name = name
        self.command_list = ["shutdown"]

        @self.command(WordCompleter(self.command_list))
        def no(args):
            if len(args) != 1:
                raise InvalidInput("usage: shutdown")
            if args[0] != "shutdown":
                raise InvalidInput("usage: no shutdown")
            self.set("admin-status", "up")

        @self.command(WordCompleter(self.netifs))
        def netif(args):
            if len(args) != 1:
                raise InvalidInput("usage: netif <name>")
            elif args[0] not in self.netifs():
                raise InvalidInput(f"No network interface with name {args[0]}")
            return NetIf(conn, self, args[0])

        @self.command(WordCompleter(self.hostifs))
        def hostif(args):
            if len(args) != 1:
                raise InvalidInput("usage: hostif <name>")
            elif args[0] not in self.hostifs():
                raise InvalidInput(f"No host interface with name {args[0]}")
            return HostIf(conn, self, args[0])

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            self.set("admin-status", "down")

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)

            xpath = self.xpath()

            try:
                data = self.sr_op.get_data(xpath, "operational")
            except sr.SysrepoNotFoundError as e:
                print("Not able to fetch data from operational database")
                return
            try:
                h = data["modules"]["module"][self.name]["state"]
                print_tabular(h, "")
            except KeyError as e:
                print(f"Error while fetching values from operational database")
                return

    def netifs(self):
        return self.components("network-interface")

    def hostifs(self):
        return self.components("host-interface")

    def components(self, type_):

        d = self.sr_op.get_data(
            "{}[name='{}']".format(self.XPATH, self.name),
            "operational",
            no_subs=True,
        )
        d = d.get("modules", {}).get("module", {}).get(self.name, {})
        return [v["name"] for v in d.get(type_, [])]

    def __str__(self):
        return "transponder({})".format(self.name)
