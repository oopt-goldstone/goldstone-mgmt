from .cli import (
    Command,
    Context,
    RunningConfigCommand,
    GlobalShowCommand,
    GlobalClearCommand,
    ModelExists,
    TechSupportCommand,
)
from .root import Root
from .base import InvalidInput
from tabulate import tabulate
from natsort import natsorted
from prompt_toolkit.completion import WordCompleter, NestedCompleter

import logging


logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


XPATH_MGMT = "/goldstone-mgmt-interfaces:interfaces/interface"


def xpath_mgmt(ifname):
    return f"{XPATH_MGMT}[name='{ifname}']"


def get_mgmt_interface_list(session, datastore):
    tree = session.get(XPATH_MGMT, ds=datastore)
    return natsorted(tree, key=lambda x: x["name"])


def set_ip_addr(session, ifname, ip_addr, mask, config=True):
    xpath = xpath_mgmt(ifname)
    if config:
        session.set(f"{xpath}/admin-status", "up")
        xpath += "/goldstone-ip:ipv4"
        session.set(f"{xpath}/address[ip='{ip_addr}']/prefix-length", mask)
    else:
        xpath += "/goldstone-ip:ipv4"
        session.delete(f"{xpath}/address[ip='{ip_addr}']")
    session.apply()


def set_route(session, ifname, dst_prefix, config=True):
    xpath = "/goldstone-routing:routing/static-routes/ipv4/route"

    if config:
        session.set(f"{xpath_mgmt(ifname)}/admin-status", "up")
        session.set(
            f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix",
            dst_prefix,
        )
    else:
        session.delete(f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix")
    session.apply()


def clear_route(session):
    session.delete("/goldstone-routing:routing/static-routes/ipv4/route")
    session.apply()


def show(session, ifname):
    stdout.info(session.get_operational(xpath_mgmt(ifname), one=True))


def run_conf(session):
    conf = session.get("/goldstone-mgmt-interfaces:interfaces/interface", [])

    n = 0

    for c in conf:
        stdout.info(f"mgmt-if {c['name']}")
        if "admin-status" in c:
            n += 1
            stdout.info(f"  admin-status {c['admin-status']}")

        for addr in c.get("ipv4", {}).get("address", []):
            n += 1
            stdout.info(f"  ip address {addr['ip']}/{addr['prefix-length']}")

    conf = session.get("/goldstone-routing:routing/static-routes/ipv4/route", [])

    for c in conf:
        r = c["destination-prefix"]
        n += 1
        stdout.info(f"  ip route {r}")

    return n


class ManagementInterface(Context):
    def __init__(self, parent, ifname):
        super().__init__(parent)
        self.name = ifname
        self.ip_cmd_list = ["address", "route"]
        self.no_dict = {"ip": {"route": None, "address": None}}
        mgmt_iflist = [
            v["name"] for v in get_mgmt_interface_list(self.conn, "operational")
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
                    set_ip_addr(self.conn, ifname, ip_addr, mask, False)
                elif args[1] == "route":
                    if len(args) != 3:
                        raise InvalidInput("usage :no ip route <dst_prefix>")
                    dst_prefix = args[2]
                    set_route(self.conn, ifname, dst_prefix, False)
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
                set_ip_addr(self.conn, ifname, ip_addr, mask, True)
            elif args[0] == "route":
                if len(args) != 2:
                    raise InvalidInput("usage :ip route <dst_prefix>")
                dst_prefix = args[1]
                set_route(self.conn, ifname, dst_prefix, True)

            else:
                raise InvalidInput(self.usage())

        @self.command(parent.get_completer("show"), name="show")
        def show_(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                show(self.conn, ifname)

    def __str__(self):
        return f"mgmt-if({self.name})"

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        stderr.info(f'usage: no [{"|".join(no_keys)}]')

    def usage(self):
        return "usage:\n ip address A.B.C.D/<mask>\n ip route <dst_prefix>\n"


class ArpGroupCommand(Command):
    def exec(self, line):
        xpath = "/goldstone-mgmt-interfaces:interfaces/interface"
        rows = []
        try:
            for intf in self.conn.get_operational(xpath, []):
                if "neighbor" in intf["ipv4"]:
                    arp_list = intf["ipv4"]["neighbor"]
                    for arp in arp_list:
                        if "link-layer-address" not in arp:
                            arp["link-layer-address"] = "(incomplete)"
                        row = [arp["ip"], arp["link-layer-address"], intf["name"]]
                        rows.append(row)
        except KeyError as error:
            raise InvalidInput(str(error))

        headers = ["Address", "HWaddress", "Iface"]
        stdout.info(tabulate(rows, headers, tablefmt="plain"))


class IPRouteShowCommand(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())

        xpath = "/goldstone-routing:routes/route"
        for route in self.conn.get_operational(xpath, []):
            line = f"{route['destination-prefix']} "
            if "next-hop" in route and "outgoing-interface" in route["next-hop"]:
                line = line + "via " + str(route["next-hop"]["outgoing-interface"])
            else:
                line = line + "is directly connected"
            stdout.info(line)

    def usage(self):
        return f"usage: {self.name_all()}"


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
            return clear_route(self.conn)
        else:
            raise InvalidInput(self.usage())

    def usage(self):
        return "usage:\n" f" {self.name_all()} (route)"


class ClearArpGroupCommand(Command):
    def exec(self, line):
        stdout.info(self.conn.rpc("/goldstone-routing:clear-arp", {}))


GlobalShowCommand.register_command(
    "ip", IPGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)

GlobalShowCommand.register_command(
    "arp", ArpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)

GlobalClearCommand.register_command(
    "ip", ClearIpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)

GlobalClearCommand.register_command(
    "arp", ClearArpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)


class Run(Command):
    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(self.usage())
        self.parent.num_lines = run_conf(self.conn)

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
    def arguments(self):
        return (v["name"] for v in get_mgmt_interface_list(self.conn, "operational"))

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(f"usage: {self.name_all()} <ifname>")
        return ManagementInterface(self.context, line[0])


Root.register_command(
    "mgmt-if",
    MgmtIfCommand,
    when=ModelExists("goldstone-mgmt-interfaces"),
    hidden=True,
    no_completion_on_exec=True,
)
