import sys
import os
import sysrepo
from tabulate import tabulate
from .sonic import Port, Vlan, UFD, Portchannel
from .transponder import Transponder
from .system import System, TACACS, AAA, Mgmtif
from .platform import Component
import json
import re
import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES
from kubernetes.client.rest import ApiException
from kubernetes import client, config
import pydoc
import logging
from prompt_toolkit.completion import merge_completers
from itertools import chain

from .base import *

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"

SR_TIMEOUT_MS = 60000

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class InterfaceCounterCommand(Command):
    def list(self):
        return ["table"] + self.parent.port.interface_names()

    def exec(self, line):
        ifnames = self.parent.port.interface_names()
        table = False
        if len(line) == 1:
            if line[0] == "table":
                table = True
            else:
                try:
                    ptn = re.compile(line[0])
                except re.error:
                    raise InvalidInput(
                        f"failed to compile {line[0]} as a regular expression"
                    )
                ifnames = [i for i in ifnames if ptn.match(i)]
        elif len(line) > 1:
            for ifname in line:
                if ifname not in ifnames:
                    raise InvalidInput(f"Invalid interface {ifname}")
            ifnames = line

        self.parent.port.show_counters(ifnames, table)


class InterfaceGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "brief": Command,
        "description": Command,
        "counters": InterfaceCounterCommand,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.port = Port(context.conn)

    def exec(self, line):
        if len(line) == 1:
            return self.port.show_interface(line[0])
        else:
            raise InvalidInput(self.usage())

    def usage(self):
        return (
            "usage:\n" f" {self.parent.name} {self.name} (brief|description|counters)"
        )


class VlanGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "details": Command,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.vlan = Vlan(context.conn)

    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(self.usage())
        return self.vlan.show_vlans(line[0])

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name} details"


class UfdGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.ufd = UFD(context.conn)

    def exec(self, line):
        if len(line) == 0:
            return self.ufd.show()
        else:
            stderr.info(self.usage())

    def usage(self):
        return " >> usage:\n" f" {self.parent.name} {self.name} "


class PortchannelGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.pc = Portchannel(context.conn)

    def exec(self, line):
        if len(line) == 0:
            return self.pc.show()
        else:
            stderr.info(self.usage())

    def usage(self):
        return " >> usage:\n" f" {self.parent.name} {self.name} "


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
    SUBCOMMAND_DICT = {
        "route": IPRouteShowCommand,
    }


class TransponderGroupCommand(Command):
    def __init__(self, context, parent, name):
        self.transponder = Transponder(context.conn)
        if type(parent) == RunningConfigCommand:
            self.exec = self.exec_runconf
        elif type(parent) == GlobalShowCommand:
            self.exec = self.exec_show
            self.list = self.list_show
            self.SUBCOMMAND_DICT = {
                "summary": Command,
            }

        super().__init__(context, parent, name)

    def list_show(self):
        module_names = self.transponder.get_modules()
        return module_names + super().list()

    def exec_show(self, line):
        if len(line) == 1:
            if line[0] == "summary":
                return self.transponder.show_transponder_summary()
            else:
                return self.transponder.show_transponder(line[0])
        else:
            stderr.info(self.usage())

    def exec_runconf(self, line):
        self.transponder.run_conf()

    def usage(self):
        return (
            "usage:\n" f" {self.parent.name} {self.name} (<transponder_name>|summary)"
        )


class PlatformComponentCommand(Command):
    SUBCOMMAND_DICT = {
        "table": Command,
    }

    def exec(self, line):
        if len(line) > 1:
            raise InvalidInput(self.usage())
        format = "" if len(line) == 0 else line[0]
        return self.parent.platform_component.show_platform(self.name, format=format)

    def usage(self):
        return (
            f"usage: {self.parent.parent.name} {self.parent.name} {self.name} [table]"
        )


class PlatformGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "fan": Command,
        "psu": Command,
        "led": Command,
        "transceiver": PlatformComponentCommand,
        "thermal": Command,
        "system": Command,
        "piu": PlatformComponentCommand,
        "all": Command,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.platform_component = Component(context.conn)

    def exec(self, line):
        if len(line) != 1:
            raise InvalidInput(self.usage())
        return self.platform_component.show_platform(line[0])

    def usage(self):
        return (
            "usage:\n"
            f" {self.parent.name} {self.name} (fan|psu|led|transceiver|thermal|system|piu|all)"
        )


class AAAGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.aaa = AAA(context.conn)

    def exec(self, line):
        if len(line) == 0:
            return self.aaa.show_aaa()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name}"


class TACACSGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.tacacs = TACACS(context.conn)

    def exec(self, line):
        if len(line) == 0:
            return self.tacacs.show_tacacs()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name}"


class RunningConfigCommand(Command):
    def __init__(self, context=None, parent=None, name=None):
        super().__init__(context, parent, name)
        installed_modules = context.root().installed_modules
        if "goldstone-interfaces" in installed_modules:
            self.add_sub_command("interface", Command)

        if "goldstone-uplink-failure-detection" in installed_modules:
            self.add_sub_command("ufd", Command)

        if "goldstone-vlan" in installed_modules:
            self.add_sub_command("vlan", Command)

        if "goldstone-portchannel" in installed_modules:
            self.add_sub_command("portchannel", Command)

        if "goldstone-system" in installed_modules:
            self.add_sub_command("aaa", Command)

        if "goldstone-transponder" in installed_modules:
            self.add_sub_command("transponder", Command)

        if "goldstone-platform" in installed_modules:
            self.add_sub_command("platform", Command)

        if "goldstone-mgmt-interfaces" in installed_modules:
            self.add_sub_command("mgmt-if", Command)

    def exec(self, line):
        if len(line) > 0:
            module = line[0]
        else:
            module = "all"

        installed_modules = self.context.root().installed_modules

        system = System(self.context.conn)

        if module == "all":
            if "goldstone-vlan" in installed_modules:
                self("vlan")
            if "goldstone-uplink-failure-detection" in installed_modules:
                self("ufd")
            if "goldstone-portchannel" in installed_modules:
                self("portchannel")
            if "goldstone-interfaces" in installed_modules:
                self("interface")
            if "goldstone-transponder" in installed_modules:
                self("transponder")
            if "goldstone-system" in installed_modules:
                system.run_conf()
        elif module == "aaa":
            system.run_conf()
        elif module == "mgmt-if":
            system.mgmt_run_conf()
        elif module == "interface":
            port = Port(self.context.conn)
            port.run_conf()
        elif module == "ufd":
            ufd = UFD(self.context.conn)
            ufd.run_conf()
        elif module == "portchannel":
            portchannel = Portchannel(self.context.conn)
            portchannel.run_conf()
        elif module == "vlan":
            vlan = Vlan(self.context.conn)
            vlan.run_conf()


class GlobalShowCommand(Command):
    SUBCOMMAND_DICT = {
        "datastore": Command,
        "tech-support": Command,
        "logging": Command,
        "running-config": RunningConfigCommand,
    }

    def __init__(self, context=None, parent=None, name=None):
        super().__init__(context, parent, name)
        installed_modules = context.root().installed_modules
        if "goldstone-interfaces" in installed_modules:
            self.add_sub_command("interface", InterfaceGroupCommand)

        if "goldstone-uplink-failure-detection" in installed_modules:
            self.add_sub_command("ufd", UfdGroupCommand)

        if "goldstone-vlan" in installed_modules:
            self.add_sub_command("vlan", VlanGroupCommand)

        if "goldstone-portchannel" in installed_modules:
            self.add_sub_command("portchannel", PortchannelGroupCommand)

        if "goldstone-system" in installed_modules:
            self.add_sub_command("version", Command)
            self.add_sub_command("aaa", AAAGroupCommand)
            self.add_sub_command("tacacs", TACACSGroupCommand)

        if "goldstone-transponder" in installed_modules:
            self.add_sub_command("transponder", TransponderGroupCommand)

        if "goldstone-platform" in installed_modules:
            self.add_sub_command("chassis-hardware", PlatformGroupCommand)

        if "goldstone-mgmt-interfaces" in installed_modules:
            self.add_sub_command("ip", IPGroupCommand)
            self.add_sub_command("arp", ArpGroupCommand)

    def exec(self, line):
        if len(line) == 0:
            raise InvalidInput(self.usage())

        if line[0] == "datastore":
            self.datastore(line)

        elif line[0] == "tech-support":
            self.tech_support(line)

        elif line[0] == "logging":
            self.display_log(line)

        elif line[0] == "version":
            self.get_version(line)

        else:
            raise InvalidInput(self.usage())

    def datastore(self, line):
        conn = self.context.conn
        with conn.start_session() as sess:
            dss = list(DATASTORE_VALUES.keys())
            fmt = "default"
            if len(line) < 2:
                stderr.info(f'usage: show datastore <XPATH> [{"|".join(dss)}] [json|]')
                return

            if len(line) == 2:
                ds = "running"
            else:
                ds = line[2]

            if len(line) == 4:
                fmt = line[3]
            elif len(line) == 3 and line[2] == "json":
                ds = "running"
                fmt = line[2]

            if fmt == "default" or fmt == "json":
                pass
            else:
                stderr.info(f"unsupported format: {fmt}. supported: {json}")
                return

            if ds not in dss:
                stderr.info(f"unsupported datastore: {ds}. candidates: {dss}")
                return

            sess.switch_datastore(ds)

            if ds == "operational":
                defaults = True
            else:
                defaults = False

            try:
                data = sess.get_data(
                    line[1],
                    include_implicit_defaults=defaults,
                    timeout_ms=SR_TIMEOUT_MS,
                )
            except Exception as e:
                stderr.info(e)
                return

            if fmt == "json":
                stdout.info(json.dumps(data), indent=4)
            else:
                stdout.info(data)

    def get_version(self, line):
        conn = self.context.conn
        with conn.start_session() as sess:
            xpath = "/goldstone-system:system/state/software-version"
            sess.switch_datastore("operational")
            data = sess.get_data(xpath)
            stdout.info(data["system"]["state"]["software-version"])

    def display_log(self, line):
        log_filter = ["sonic", "tai", "onlp"]
        module_name = "gs-mgmt-"
        line_count = 0
        if len(line) >= 2:
            if line[1].isdigit() and len(line) == 2:
                line_count = int(line[1])
            elif line[1] in log_filter:
                module_name = module_name + line[1]
                if len(line) == 3 and line[2].isdigit():
                    line_count = int(line[2])
                elif len(line) == 2:
                    line_count = 0
                else:
                    raise InvalidInput("The argument <num_lines> must be a number")
            else:
                raise InvalidInput(
                    f" {self.name} logging [sonic|tai|onlp|] [<num_lines>|]"
                )
        else:
            line_count = 0
            module_name = "gs-mgmt-"

        try:
            config.load_kube_config(KUBECONFIG)
        except config.config_exception.ConfigException as error:
            config.load_incluster_config()

        try:
            api_instance = client.CoreV1Api()
            pod_info = api_instance.list_pod_for_all_namespaces(watch=False)
            log = ""
            for pod_name in pod_info.items:
                if pod_name.metadata.name.startswith(module_name):
                    log = log + ("----------------------------------\n")
                    log = log + (f"{pod_name.metadata.name}\n")
                    log = log + ("----------------------------------\n")
                    try:
                        if line_count > 0:
                            api_response = api_instance.read_namespaced_pod_log(
                                name=pod_name.metadata.name,
                                namespace="default",
                                tail_lines=line_count,
                            )
                        else:
                            api_response = api_instance.read_namespaced_pod_log(
                                name=pod_name.metadata.name, namespace="default"
                            )

                        log = log + api_response
                    except ApiException as e:
                        log = (
                            log
                            + f"Exception occured while fetching log for {pod_name.metadata.name}\n"
                        )
                        continue

            log = log + ("\n")
            pydoc.pager(log)

        except ApiException as e:
            stderr.info("Found exception in reading the logs : {}".format(str(e)))

    def tech_support(self, line):
        datastore_list = ["operational", "running", "candidate", "startup"]
        installed_modules = self.context.root().installed_modules

        xpath_list = []

        if "goldstone-interfaces" in installed_modules:
            stdout.info("\nshow interface description:\n")
            port = Port(self.context.conn)
            try:
                port.show_interface()
            except InvalidInput as e:
                stderr.info(e)

            xpath_list.append("/goldstone-interfaces:interfaces/interface")

        if "goldstone-uplink-failure-detection" in installed_modules:
            stdout.info("\nshow ufd:\n")
            ufd = UFD(self.context.conn)
            try:
                ufd.show()
            except InvalidInput as e:
                stderr.info(e)

            xpath_list.append(
                "/goldstone-uplink-failure-detection:ufd-groups/ufd-group"
            )

        if "goldstone-vlan" in installed_modules:
            stdout.info("\nshow vlan details:\n")
            vlan = Vlan(self.context.conn)
            try:
                vlan.show_vlans()
            except InvalidInput as e:
                stderr.info(e)

            xpath_list.append("/goldstone-vlan:vlan/vlans")

        if "goldstone-portchannel" in installed_modules:
            stdout.info("\nshow portchannel:\n")
            portchannel = Portchannel(self.context.conn)
            try:
                portchannel.show()
            except InvalidInput as e:
                stderr.info(e)

            xpath_list.append("/goldstone-portchannel:portchannel")

        if "goldstone-system" in installed_modules:
            system = System(self.context.conn)
            system.tech_support()

            xpath_list.append("/goldstone-aaa:aaa")

        if "goldstone-transponder" in installed_modules:
            transponder = Transponder(self.context.conn)
            transponder.tech_support()

            xpath_list.append("/goldstone-transponder:modules")

        if "goldstone-platform" in installed_modules:
            component = Component(self.context.conn)
            component.tech_support()

            xpath_list.append("/goldstone-platform:components")

        if "goldstone-mgmt-interfaces" in installed_modules:
            xpath_list.append("/goldstone-mgmt-interfaces:interfaces/interface")
            xpath_list.append("/goldstone-routing:routing/static-routes/ipv4/route")

        stdout.info("\nshow datastore:\n")

        with self.context.conn.start_session() as session:
            for ds in datastore_list:
                session.switch_datastore(ds)
                stdout.info("{} DB:\n".format(ds))
                for index in range(len(xpath_list)):
                    try:
                        stdout.info(f"{xpath_list[index]} : \n")
                        stdout.info(session.get_data(xpath_list[index]))
                        stdout.info("\n")
                    except Exception as e:
                        stderr.info(e)

        stdout.info("\nRunning Config:\n")
        self(["running-config"])

    def usage(self):
        return (
            "usage:\n"
            f" {self.name_all()} interface (brief|description|counters) \n"
            f" {self.name_all()} vlan details \n"
            f" {self.name_all()} ip route\n"
            f" {self.name_all()} transponder (<transponder_name>|summary)\n"
            f" {self.name_all()} chassis-hardware (fan|psu|led|transceiver|thermal|system|all)\n"
            f" {self.name_all()} ufd \n"
            f" {self.name_all()} portchannel \n"
            f" {self.name_all()} logging [sonic|tai|onlp|] [<num_lines>|]\n"
            f" {self.name_all()} version \n"
            f" {self.name_all()} aaa \n"
            f" {self.name_all()} tacacs \n"
            f" {self.name_all()} datastore <XPATH> [running|startup|candidate|operational|] [json|]\n"
            f" {self.name_all()} running-config [transponder|platform|vlan|interface|aaa|ufd|portchannel]\n"
            f" {self.name_all()} tech-support"
        )


class ClearIpGroupCommand(Command):
    SUBCOMMAND_DICT = {
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


class ClearInterfaceGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "counters": Command,
    }

    def exec(self, line):
        conn = self.context.root().conn
        with conn.start_session() as sess:
            if len(line) < 1 or line[0] not in ["counters"]:
                raise InvalidInput(self.usage())
            if len(line) == 1:
                if line[0] == "counters":
                    sess.rpc_send("/goldstone-interfaces:clear-counters", {})
                    stdout.info("Interface counters are cleared.\n")
            else:
                raise InvalidInput(self.usage())

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name} (counters)"


def remove_switched_vlan_configuration(sess):
    for vlan in sess.get_items(
        "/goldstone-interfaces:interfaces/interface/goldstone-vlan:switched-vlan"
    ):
        sess.delete_item(vlan.xpath)
    sess.apply_changes()


class ClearDatastoreGroupCommand(Command):
    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(
                f"usage: {self.parent.name} {self.name} [ <module name> | all ] [ running | startup ]"
            )

        ds = line[1] if len(line) == 2 else "running"

        root = self.context.root()

        try:
            with root.conn.start_session() as sess:
                sess.switch_datastore(ds)

                if line[0] == "all":
                    ctx = root.conn.get_ly_ctx()
                    modules = [m.name() for m in ctx if "goldstone" in m.name()]
                    # the interface model has dependencies to other models (e.g. vlan, ufd )
                    # we need to the clear interface model lastly
                    # the vlan model has dependency to switched-vlan configuration
                    # we need to clear the switched-vlan configuration first
                    # TODO invent cleaner way when we have more dependency among models
                    remove_switched_vlan_configuration(sess)
                    modules.remove("goldstone-interfaces")
                    modules.append("goldstone-interfaces")
                else:
                    modules = [line[0]]

                for m in modules:
                    stdout.info(f"clearing module {m}")
                    sess.replace_config({}, m)

                sess.apply_changes()

        except sr.SysrepoError as e:
            raise CLIException(f"failed to clear: {e}")

    def get(self, arg):
        elected = self.complete_subcommand(arg)
        if elected == None:
            return None
        return Choice(["running", "startup"], self.context, self, elected)

    def list(self):
        ctx = self.context.root().conn.get_ly_ctx()
        cmds = [m.name() for m in ctx if "goldstone" in m.name()]
        cmds.append("all")
        return cmds


class ShowCommand(Command):
    def __init__(self, context=None, parent=None, name=None, additional_completer=None):
        if name == None:
            name = "show"
        c = context.root().get_completer("show")
        if additional_completer:
            c = merge_completers([c, additional_completer])
        super().__init__(context, parent, name, c)


class GlobalClearCommand(Command):
    SUBCOMMAND_DICT = {
        "arp": ClearArpGroupCommand,
        "ip": ClearIpGroupCommand,
        "interface": ClearInterfaceGroupCommand,
        "datastore": ClearDatastoreGroupCommand,
    }


class NoCommand(Command):
    def exec(self, line):
        raise InvalidInput(self.usage())

    def usage(self):
        n = self.name_all()
        l = []
        for k, cls in chain(self.SUBCOMMAND_DICT.items(), self.subcommand_dict.items()):
            v = cls(self.context, self)
            l.append(f"  {n} {k} {v.usage()}")

        return "usage:\n" + "\n".join(l)

    # hide no command if no sub-command is registerd
    def hidden(self):
        return (
            len(list(chain(self.SUBCOMMAND_DICT.items(), self.subcommand_dict.items())))
            == 0
        )


class GSObject(Object):
    def __init__(self, parent, fuzzy_completion=False):
        super().__init__(parent, fuzzy_completion)
        self.add_command(GlobalShowCommand(self, name="show"))
        self.add_command(GlobalClearCommand(self, name="clear"))
        self.no = NoCommand(self, name="no")
        self.add_command(self.no)