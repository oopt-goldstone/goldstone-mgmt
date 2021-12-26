import sysrepo as sr
from .cli import (
    Context,
    RunningConfigCommand,
    GlobalShowCommand,
    GlobalClearCommand,
    ModelExists,
    TechSupportCommand,
)
from .root import Root
from .base import InvalidInput, Command
from .common import sysrepo_wrap
from tabulate import tabulate
from natsort import natsorted
from prompt_toolkit.completion import WordCompleter, NestedCompleter

import logging


logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


XPATH_MGMT = "/goldstone-mgmt-interfaces:interfaces/interface"


def get_session(cmd):
    return cmd.context.root().conn.start_session()


def xpath_mgmt(ifname):
    return f"{XPATH_MGMT}[name='{ifname}']"


def get_mgmt_interface_list(session, datastore):
    sr_op = sysrepo_wrap(session)
    try:
        tree = sr_op.get_data(XPATH_MGMT, datastore)
        return natsorted(tree["interfaces"]["interface"], key=lambda x: x["name"])
    except (KeyError, sr.SysrepoNotFoundError) as error:
        return []


def set_ip_addr(session, ifname, ip_addr, mask, config=True):
    sr_op = sysrepo_wrap(session)
    xpath = xpath_mgmt(ifname)
    if config:
        sr_op.set_data(f"{xpath}/admin-status", "up")
        xpath += "/goldstone-ip:ipv4"
        sr_op.set_data(f"{xpath}/address[ip='{ip_addr}']/prefix-length", mask)
    else:
        xpath += "/goldstone-ip:ipv4"
        sr_op.delete_data(f"{xpath}/address[ip='{ip_addr}']")


def set_route(session, ifname, dst_prefix, config=True):
    sr_op = sysrepo_wrap(session)
    xpath = "/goldstone-routing:routing/static-routes/ipv4/route"

    if config:
        sr_op.set_data(f"{xpath_mgmt(ifname)}/admin-status", "up")
        sr_op.set_data(
            f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix",
            dst_prefix,
        )
    else:
        sr_op.delete_data(
            f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix"
        )


def clear_route(session):
    sr_op = sysrepo_wrap(session)
    sr_op.delete_data("/goldstone-routing:routing/static-routes/ipv4/route")


def show(session, ifname):
    sr_op = sysrepo_wrap(session)
    stdout.info(sr_op.get_data(xpath_mgmt(ifname), "operational"))


def run_conf(session):
    sr_op = sysrepo_wrap(session)
    mgmt_dict = {}
    try:
        mgmt_data = sr_op.get_data(
            "/goldstone-mgmt-interfaces:interfaces/interface/goldstone-ip:ipv4/address"
        )
    except sr.SysrepoNotFoundError as e:
        pass

    try:
        mgmt_intf_dict = sr_op.get_data(
            "/goldstone-mgmt-interfaces:interfaces/interface"
        )
        mgmt_intf = list(mgmt_intf_dict["interfaces"]["interface"])[0]
        stdout.info(f"interface {mgmt_intf['name']}")
    except (sr.SysrepoNotFoundError, KeyError) as e:
        return

    try:
        run_conf_data = list(mgmt_data["interfaces"]["interface"])[0]
        run_conf_list = run_conf_data["ipv4"]["address"]
        for item in run_conf_list:
            ip_addr = item["ip"]
            ip_addr += "/" + str(item["prefix-length"])
            mgmt_dict.update({"ip_addr": ip_addr})
            stdout.info(f"  ip address {mgmt_dict['ip_addr']}")
    except Exception as e:
        pass
    try:
        route_data = sr_op.get_data(
            "/goldstone-routing:routing/static-routes/ipv4/route"
        )
    except sr.SysrepoNotFoundError as e:
        stdout.info("!")
        return
    try:
        route_conf_list = list(route_data["routing"]["static-routes"]["ipv4"]["route"])
        for route in route_conf_list:
            dst_addr = route["destination-prefix"]
            mgmt_dict.update({"dst_addr": dst_addr})
            stdout.info(f"  ip route {mgmt_dict['dst_addr']}")
    except Exception as e:
        stdout.info("!")
        return
    stdout.info("!")


class ManagementInterface(Context):
    def __init__(self, parent, ifname):
        super().__init__(parent)
        session = parent.root().conn.start_session()
        self.name = ifname
        self.ip_cmd_list = ["address", "route"]
        self.no_dict = {"ip": {"route": None, "address": None}}
        mgmt_iflist = [
            v["name"] for v in get_mgmt_interface_list(session, "operational")
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
                    set_ip_addr(session, ifname, ip_addr, mask, False)
                elif args[1] == "route":
                    if len(args) != 3:
                        raise InvalidInput("usage :no ip route <dst_prefix>")
                    dst_prefix = args[2]
                    set_route(session, ifname, dst_prefix, False)
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
                set_ip_addr(session, ifname, ip_addr, mask, True)
            elif args[0] == "route":
                if len(args) != 2:
                    raise InvalidInput("usage :ip route <dst_prefix>")
                dst_prefix = args[1]
                set_route(session, ifname, dst_prefix, True)

            else:
                raise InvalidInput(self.usage())

        @self.command(parent.get_completer("show"), name="show")
        def show_(args):
            if len(args) != 0:
                parent.exec(f"show {' '.join(args)}")
            else:
                show(session, ifname)

    def __str__(self):
        return f"mgmt-if({self.name})"

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        stderr.info(f'usage: no [{"|".join(no_keys)}]')

    def usage(self):
        return "usage:\n ip address A.B.C.D/<mask>\n ip route <dst_prefix>\n"


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
        except (KeyError, sr.SysrepoNotFoundError) as error:
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
        except (KeyError, sr.SysrepoNotFoundError) as error:
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
            return clear_route(get_session(self))
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

GlobalClearCommand.register_command(
    "ip", ClearIpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
)

GlobalClearCommand.register_command(
    "arp", ClearArpGroupCommand, when=ModelExists("goldstone-mgmt-interfaces")
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
        return (
            v["name"] for v in get_mgmt_interface_list(get_session(self), "operational")
        )

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
