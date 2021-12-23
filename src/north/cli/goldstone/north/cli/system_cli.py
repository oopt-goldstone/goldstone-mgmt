from .cli import (
    GSObject as Object,
    RunningConfigCommand,
    GlobalShowCommand,
    GlobalClearCommand,
    ModelExists,
    TechSupportCommand,
)
from .root import Root
from .base import InvalidInput, Completer, Command
from .system import AAA, TACACS, Mgmtif, System
from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, NestedCompleter
from .common import sysrepo_wrap
import re
import logging
from tabulate import tabulate

from .tacacs import TACACSCommand
from .aaa import AAACommand

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class ManagementInterface(Object):
    def __init__(self, conn, parent, ifname):
        super().__init__(parent)
        self.session = conn.start_session()
        self.name = ifname
        self.mgmt = Mgmtif(conn)
        self.ip_cmd_list = ["address", "route"]
        self.no_dict = {"ip": {"route": None, "address": None}}
        mgmt_iflist = [
            v["name"] for v in self.mgmt.get_mgmt_interface_list("operational")
        ]
        if len(mgmt_iflist) == 0 or self.name not in mgmt_iflist:
            raise InvalidInput(f"no interface found : {ifname}")

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(args):
            if len(args) < 2:
                raise InvalidInput("usage: {}".format(self.no_usage))
            if args[0] == "ip":
                if args[1] == "address":
                    if len(args) != 3:
                        raise InvalidInput("usage: no ip address A.B.C.D/<mask>")
                    try:
                        ip_addr = args[2].split("/")[0]
                        mask = args[2].split("/")[1]
                    except IndexError as error:
                        raise InvalidInput(
                            "Entered address is not in the expected format - A.B.C.D/<mask>"
                        )
                    self.mgmt.set_ip_addr(ifname, ip_addr, mask, False)
                elif args[1] == "route":
                    if len(args) != 3:
                        raise InvalidInput("usage :no ip route <dst_prefix>")
                    dst_prefix = args[2]
                    self.mgmt.set_route(ifname, dst_prefix, False)
            else:
                raise InvalidInput(f"{self.no_usage}")

        @self.command(WordCompleter(self.ip_cmd_list))
        def ip(args):
            if len(args) < 2:
                raise InvalidInput(self.usage())
            if args[0] == "address":
                if len(args) != 2:
                    raise InvalidInput("usage: ip address A.B.C.D/<mask>")
                try:
                    ip_addr = args[1].split("/")[0]
                    mask = args[1].split("/")[1]
                except IndexError as error:
                    raise InvalidInput(
                        "Entered address is not in the expected format - A.B.C.D/<mask>"
                    )
                self.mgmt.set_ip_addr(ifname, ip_addr, mask, True)
            elif args[0] == "route":
                if len(args) != 2:
                    raise InvalidInput("usage :ip route <dst_prefix>")
                dst_prefix = args[1]
                self.mgmt.set_route(ifname, dst_prefix, True)

            else:
                raise InvalidInput(self.usage())

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                self.mgmt.show(ifname)

    def __str__(self):
        return "mgmt-if({})".format(self.name)

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        stderr.info(f'usage: no [{"|".join(no_keys)}]')

    def usage(self):
        return "usage:\n ip address A.B.C.D/<mask>\n ip route <dst_prefix>\n"


class NACM(Object):

    XPATH = "/ietf-netconf-acm:nacm"

    def __init__(self, conn, parent):
        super().__init__(parent)
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

        @self.command()
        def disable(line):
            if len(line) != 0:
                raise InvalidInput("usage: disable[cr]")
            self.sr_op.set_data(f"{self.XPATH}/enable-nacm", False)

        @self.command()
        def enable(line):
            if len(line) != 0:
                raise InvalidInput("usage: enable[cr]")
            self.sr_op.set_data(f"{self.XPATH}/enable-nacm", True)

    def __str__(self):
        return "nacm"


class Netconf(Object):

    XPATH = "/goldstone-system:system/netconf"

    def __init__(self, conn, parent):
        super().__init__(parent)
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

        @self.command()
        def shutdown(line):
            if len(line) != 0:
                raise InvalidInput("usage: shutdown[cr]")
            self.sr_op.set_data(f"{self.XPATH}/config/enabled", False)

        @self.command(WordCompleter(["shutdown"]))
        def no(line):
            if len(line) != 1 or line[0] != "shutdown":
                raise InvalidInput("usage: no shutdown")
            self.sr_op.set_data(f"{self.XPATH}/config/enabled", True)

        @self.command()
        def nacm(line):
            if len(line) != 0:
                raise InvalidInput("usage: nacm[cr]")
            return NACM(conn, self)

    def __str__(self):
        return "netconf"


class SystemObject(Object):
    def __init__(self, conn, parent):
        super().__init__(parent)

        @self.command(name="netconf")
        def netconf(line):
            if len(line) != 0:
                raise InvalidInput("usage: netconf[cr]")
            return Netconf(conn, self)

        @self.command()
        def reboot(line):
            session = conn.start_session()
            stdout.info(session.rpc_send("/goldstone-system:reboot", {}))

        @self.command()
        def shutdown(line):
            session = conn.start_session()
            stdout.info(session.rpc_send("/goldstone-system:shutdown", {}))

        c = TACACSCommand(self)
        self.add_command(c.name, c, add_no=True)

        c = AAACommand(self)
        self.add_command(c.name, c, add_no=True)

    def __str__(self):
        return "system"


class ArpGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.conn = context.root().conn
        self.sess = self.conn.start_session()

    def exec(self, line):
        self.sess.switch_datastore("operational")
        xpath = "/goldstone-mgmt-interfaces:interfaces/interface"
        rows = []
        try:
            tree = self.sess.get_data(xpath)
            if_list = tree["interfaces"]["interface"]
            for intf in if_list:
                if "neighbor" in intf["ipv4"]:
                    arp_list = intf["ipv4"]["neighbor"]
                    for arp in arp_list:
                        if "link-layer-address" not in arp:
                            arp["link-layer-address"] = "(incomplete)"
                        row = [arp["ip"], arp["link-layer-address"], intf["name"]]
                        rows.append(row)
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            raise InvalidInput(str(error))

        headers = ["Address", "HWaddress", "Iface"]
        stdout.info(tabulate(rows, headers, tablefmt="plain"))


class IPRouteShowCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.conn = context.root().conn
        self.sess = self.conn.start_session()

    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())

        self.sess.switch_datastore("operational")
        xpath = "/goldstone-routing:routes"
        lines = []
        try:
            tree = self.sess.get_data(xpath)
            tree = tree["routes"]["route"]
            for route in tree:
                line = ""
                line = line + route["destination-prefix"] + " "
                if "next-hop" in route and "outgoing-interface" in route["next-hop"]:
                    line = line + "via " + str(route["next-hop"]["outgoing-interface"])
                else:
                    line = line + "is directly connected"
                lines.append(line)
            stdout.info("\n".join(lines))
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            raise InvalidInput(str(error))

    def usage(self):
        return "usage:\n" f" {self.parent.parent.name} {self.parent.name} {self.name}"


class IPGroupCommand(Command):
    COMMAND_DICT = {
        "route": IPRouteShowCommand,
    }


class ClearIpGroupCommand(Command):
    COMMAND_DICT = {
        "route": Command,
    }

    def exec(self, line):
        if len(line) < 1 or line[0] not in ["route"]:
            raise InvalidInput(self.usage())

        if len(line) == 1:
            mgmtif = Mgmtif(self.context.root().conn)
            return mgmtif.clear_route()
        else:
            raise InvalidInput(self.usage())

    def usage(self):
        return "usage:\n" f" {self.name_all()} (route)"


class ClearArpGroupCommand(Command):
    def exec(self, line):
        conn = self.context.root().conn
        with conn.start_session() as sess:
            stdout.info(sess.rpc_send("/goldstone-routing:clear-arp", {}))


GlobalShowCommand.register_command(
    "ip", IPGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)

GlobalShowCommand.register_command(
    "arp", ArpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)


class Version(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())

        conn = self.context.root().conn
        with conn.start_session() as sess:
            xpath = "/goldstone-system:system/state/software-version"
            sess.switch_datastore("operational")
            data = sess.get_data(xpath)
            stdout.info(data["system"]["state"]["software-version"])

    def usage(self):
        return "usage: {self.name_all()}"


GlobalShowCommand.register_command(
    "version", Version, when=ModelExists("goldstone-system")
)

GlobalClearCommand.register_command(
    "ip", ClearIpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)

GlobalClearCommand.register_command(
    "arp", ClearArpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return System(self.context.root().conn).mgmt_run_conf()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command(
    "mgmt-if", Run, when=ModelExists("goldstone-mgmt-interfaces")
)


class TechSupport(Command):
    def exec(self, line):
        self.parent.xpath_list.append("/goldstone-mgmt-interfaces:interfaces")
        self.parent.xpath_list.append("/goldstone-routing:routing")


TechSupportCommand.register_command(
    "mgmt-if", TechSupport, when=ModelExists("goldstone-mgmt-interfaces")
)


class MgmtIfCommand(Command):
    def __init__(self, context, parent, name, **options):
        super().__init__(context, parent, name, **options)
        self.mgmt = Mgmtif(context.conn)

    def arguments(self):
        return (v["name"] for v in self.mgmt.get_mgmt_interface_list("operational"))

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <ifname>")
        return ManagementInterface(self.context.root().conn, self.context, line[0])


Root.register_command(
    "mgmt-if",
    MgmtIfCommand,
    when=ModelExists("goldstone-mgmt-interfaces"),
    hidden=True,
    no_completion_on_exec=True,
)


class SystemCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput("usage: system")
        return SystemObject(self.context.root().conn, self.context)


Root.register_command("system", SystemCommand, when=ModelExists("goldstone-system"))
