import sys
import os
from tabulate import tabulate
from .sonic import Sonic
from .tai import Transponder
import json
import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES

from .base import Command, Object, InvalidInput

VER_FILE = "/etc/goldstone/loader/versions.json"


class InterfaceGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "brief": Command,
        "description": Command,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.sonic = Sonic(context.conn)
        self.port = self.sonic.port

    def exec(self, line):
        if len(line) < 1 or line[0] not in ["brief", "description"]:
            raise InvalidInput(self.usage())
        return self.port.show_interface(line[0])

    def usage(self):
        return "usage:\n" f" {self.parent.name} {self.name} (brief|description)"


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


class RunningConfigCommand(Command):
    SUBCOMMAND_DICT = {
        "transponder": Command,
        "onlp": Command,
        "vlan": Command,
        "interface": Command,
        "aaa": Command,
    }


class TransponderGroupCommand(Command):
    SUBCOMMAND_DICT = {
        "summary": Command,
    }

    def __init__(self, context, parent, name):
        super().__init__(context, parent, name)
        self.transponder = Transponder(context.conn)

    def list(self):
        module_names = self.transponder.get_modules()
        return module_names + super().list()

    def exec(self, line):
        if len(line) == 1:
            if line[0] == "summary":
                return self.transponder.show_transponder_summary()
            else:
                return self.transponder.show_transponder(line[0])
        else:
            print(self.usage())

    def usage(self):
        return (
            "usage:\n" f" {self.parent.name} {self.name} (<transponder_name>|summary)"
        )


class GlobalShowCommand(Command):
    SUBCOMMAND_DICT = {
        "interface": InterfaceGroupCommand,
        "vlan": VlanGroupCommand,
        "datastore": Command,
        "tech-support": Command,
        "logging": Command,
        "version": Command,
        "transponder": TransponderGroupCommand,
        "running-config": RunningConfigCommand,
    }

    def exec(self, line):
        if len(line) == 0:
            raise InvalidInput(self.usage())

        if line[0] == "datastore":
            self.datastore(line)

        elif line[0] == "running-config":
            self.display_run_conf(line)

        elif line[0] == "tech-support":
            self.tech_support(line)

        elif line[0] == "logging":
            self.display_log(line)

        elif line[0] == "version":
            self.get_version(line)

        else:
            raise InvalidInput(self.usage())

    def datastore(self, line):
        self.conn = self.context.conn
        self.session = self.conn.start_session()
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

        self.session.switch_datastore(ds)

        try:
            if fmt == "json":
                print(json.dumps(self.session.get_data(line[1]), indent=4))
            else:
                print(self.session.get_data(line[1]))
        except Exception as e:
            print(e)

    def display_run_conf(self, line):
        if len(line) > 1:
            module = line[1]
        else:
            module = "all"

        sonic = Sonic(self.context.conn)
        transponder = Transponder(self.context.conn)

        if module == "all":
            sonic.run_conf()
            transponder.run_conf()

        elif module == "interface":
            print("!")
            sonic.port_run_conf()

        elif module == "vlan":
            print("!")
            sonic.vlan_run_conf()

        elif module == "transponder":
            transponder.run_conf()

    def get_version(self, line):
        if os.path.isfile(VER_FILE):
            with open(VER_FILE, "r") as version_file:
                ver_data = json.loads(version_file.read())
                if "PRODUCT_ID_VERSION" in ver_data:
                    print(ver_data["PRODUCT_ID_VERSION"])
                else:
                    print("Error : Version details not found")
        else:
            print("Error : Version details not found")

    def display_log(self, line):
        print("To Be Done")

    def tech_support(self, line):
        datastore_list = ["operational", "running", "candidate", "startup"]
        xpath_list = [
            "/goldstone-vlan:vlan/VLAN/VLAN_LIST",
            "/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST",
            "/goldstone-interfaces:interfaces/interface",
            "/goldstone-tai:modules",
        ]

        sonic = Sonic(self.context.conn)
        transponder = Transponder(self.context.conn)
        sonic.tech_support()
        transponder.tech_support()
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
        args = ["running-config"]
        self.display_run_conf(args)

    def usage(self):
        return (
            "usage:\n"
            f" {self.name} interface (brief|description) \n"
            f" {self.name} vlan details \n"
            f" {self.name} transponder (<transponder_name>|summary)\n"
            f" {self.name} logging \n"
            f" {self.name} version \n"
            f" {self.name} datastore <XPATH> [running|startup|candidate|operational|] [json|]\n"
            f" {self.name} running-config [transponder|onlp|vlan|interface|aaa|]\n"
            f" {self.name} tech-support"
        )


class GSObject(Object):
    def __init__(self, parent, fuzzy_completion=False):
        super().__init__(parent, fuzzy_completion)
        self.add_command(GlobalShowCommand(self, name="show"))
