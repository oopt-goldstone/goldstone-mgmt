import sys
import os
import sysrepo
from tabulate import tabulate
from .sonic import Sonic
from .tai import Transponder
from .system import System, TACACS, AAA
import json
import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES
from kubernetes.client.rest import ApiException
from kubernetes import client, config
import pydoc
import logging

from .base import Command, Object, InvalidInput

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"

stdout = logging.getLogger("stdout")

logger = logging.getLogger(__name__)


class InterfaceGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "brief": Command,
        "description": Command,
        "counters": Command,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.sonic = Sonic(context.conn)
        self.port = self.sonic.port

    def exec(self, line):
        if len(line) < 1 or line[0] not in ["brief", "description", "counters"]:
            raise InvalidInput(self.usage())
        if line[0] in ["brief", "description"]:
            if len(line) == 1:
                return self.port.show_interface(line[0])
            else:
                raise InvalidInput(self.usage())
        else:
            self.port.show_counters(line[1:])

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
        self.sonic = Sonic(context.conn)
        self.vlan = self.sonic.vlan

    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(self.usage())
        return self.vlan.show_vlan(line[0])

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name} details"


class ArpGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

    def exec(self, line):
        self.sess.switch_datastore("operational")
        xpath = "/goldstone-mgmt-interfaces:interfaces/interface"
        rows = []
        try:
            tree = self.sess.get_data(xpath)
            if_list = tree["interfaces"]["interface"]
            for intf in if_list:
                arp_list = intf["ipv4"]["neighbor"]
                for arp in arp_list:
                    row = [arp["ip"], arp["link-layer-address"], intf["name"]]
                    rows.append(row)
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            raise InvalidInput(str(error))

        headers = ["Address", "HWaddress", "Iface"]
        print(tabulate(rows, headers, tablefmt="plain"))


class IPRouteShowCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.conn = sysrepo.SysrepoConnection()
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
            print("\n".join(lines))
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
            self.SUBCOMMAND_DICT["summary"] = Command

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
            print(self.usage())

    def exec_runconf(self, line):
        self.transponder.run_conf()

    def usage(self):
        return (
            "usage:\n" f" {self.parent.name} {self.name} (<transponder_name>|summary)"
        )


class AAAGroupCommand(Command):
    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.aaa = AAA(context.conn)

    def exec(self, line):
        if len(line) == 0:
            return self.aaa.show_aaa()
        else:
            print(self.usage())

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
            print(self.usage())

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name}"


class RunningConfigCommand(Command):
    SUBCOMMAND_DICT = {
        "transponder": TransponderGroupCommand,
        "onlp": Command,
        "vlan": Command,
        "interface": Command,
        "aaa": Command,
        "mgmt-if": Command,
    }

    def exec(self, line):
        if len(line) > 0:
            module = line[0]
        else:
            module = "all"

        sonic = Sonic(self.context.conn)
        system = System(self.context.conn)

        if module == "all":
            sonic.run_conf()
            self("transponder")
            system.run_conf()

        elif module == "aaa":
            system.run_conf()

        elif module == "mgmt-if":
            print("!")
            system.mgmt_run_conf()

        elif module == "interface":
            print("!")
            sonic.port_run_conf()

        elif module == "vlan":
            print("!")
            sonic.vlan_run_conf()


class GlobalShowCommand(Command):
    SUBCOMMAND_DICT = {
        "interface": InterfaceGroupCommand,
        "vlan": VlanGroupCommand,
        "arp": ArpGroupCommand,
        "ip": IPGroupCommand,
        "datastore": Command,
        "tech-support": Command,
        "logging": Command,
        "version": Command,
        "transponder": TransponderGroupCommand,
        "running-config": RunningConfigCommand,
        "aaa": AAAGroupCommand,
        "tacacs": TACACSGroupCommand,
    }

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
                print(f'usage: show datastore <XPATH> [{"|".join(dss)}] [json|]')
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
                print(f"unsupported format: {fmt}. supported: {json}")
                return

            if ds not in dss:
                print(f"unsupported datastore: {ds}. candidates: {dss}")
                return

            sess.switch_datastore(ds)

            try:
                if fmt == "json":
                    print(json.dumps(sess.get_data(line[1]), indent=4))
                else:
                    print(sess.get_data(line[1]))
            except Exception as e:
                print(e)

    def get_version(self, line):
        conn = self.context.conn
        with conn.start_session() as sess:
            xpath = "/goldstone-system:system/state/software-version"
            sess.switch_datastore("operational")
            data = sess.get_data(xpath)
            print(data["system"]["state"]["software-version"])

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
            print("Found exception in reading the logs : {}".format(str(e)))

    def tech_support(self, line):
        datastore_list = ["operational", "running", "candidate", "startup"]
        xpath_list = [
            "/goldstone-vlan:vlan/VLAN/VLAN_LIST",
            "/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST",
            "/goldstone-interfaces:interfaces/interface",
            "/goldstone-mgmt-interfaces:interfaces/interface",
            "/goldstone-routing:routing/static-routes/ipv4/route",
            "/goldstone-tai:modules",
            "/goldstone-aaa:aaa",
        ]

        sonic = Sonic(self.context.conn)
        transponder = Transponder(self.context.conn)
        system = System(self.context.conn)
        sonic.tech_support()
        transponder.tech_support()
        system.tech_support()
        print("\nshow datastore:\n")

        with self.context.conn.start_session() as session:
            for ds in datastore_list:
                session.switch_datastore(ds)
                print("{} DB:\n".format(ds))
                for index in range(len(xpath_list)):
                    try:
                        print(f"{xpath_list[index]} : \n")
                        print(session.get_data(xpath_list[index]))
                        print("\n")
                    except Exception as e:
                        print(e)

        print("\nRunning Config:\n")
        self(["running-config"])

    def usage(self):
        return (
            "usage:\n"
            f" {self.name} interface (brief|description|counters) \n"
            f" {self.name} vlan details \n"
            f" {self.name} ip route\n"
            f" {self.name} transponder (<transponder_name>|summary)\n"
            f" {self.name} logging [sonic|tai|onlp|] [<num_lines>|]\n"
            f" {self.name} version \n"
            f" {self.name} aaa \n"
            f" {self.name} tacacs \n"
            f" {self.name} datastore <XPATH> [running|startup|candidate|operational|] [json|]\n"
            f" {self.name} running-config [transponder|onlp|vlan|interface|aaa|]\n"
            f" {self.name} tech-support"
        )


class GSObject(Object):
    def __init__(self, parent, fuzzy_completion=False):
        super().__init__(parent, fuzzy_completion)
        self.add_command(GlobalShowCommand(self, name="show"))
