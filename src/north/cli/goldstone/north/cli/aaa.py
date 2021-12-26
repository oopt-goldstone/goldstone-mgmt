from .base import Command, InvalidInput
from .cli import (
    Context,
    RunningConfigCommand,
    GlobalShowCommand,
    ModelExists,
    TechSupportCommand,
)

import sysrepo as sr
from tabulate import tabulate
from .common import sysrepo_wrap, print_tabular
from natsort import natsorted
import json
import re
import logging

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class TACACS(object):
    def xpath(self, group, address):
        return "/goldstone-aaa:aaa/server-groups/server-group[name='{}']/servers/server[address='{}']".format(
            group, address
        )

    def xpath_server_group(self, group):
        return "/goldstone-aaa:aaa/server-groups/server-group[name='{}']".format(group)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.name = "TACACS+"

    def set_tacacs_server(self, ipAddress, key, port, timeout):

        xpath = self.xpath(self.name, ipAddress)
        self.sr_op.set_data(
            f"{self.xpath_server_group(self.name)}/config/name",
            self.name,
            no_apply=True,
        )
        self.sr_op.set_data(f"{xpath}/config/address", ipAddress, no_apply=True)
        self.sr_op.set_data(f"{xpath}/tacacs/config/secret-key", key, no_apply=True)
        self.sr_op.set_data(f"{xpath}/tacacs/config/port", port, no_apply=True)
        self.sr_op.set_data(f"{xpath}/config/timeout", timeout, no_apply=True)
        self.sr_op.apply()

    def set_no_tacacs(self, address):
        xpath = self.xpath("TACACS+", address)
        create_group(self.sr_op, "TACACS+")
        self.sr_op.delete_data(xpath)

    def show(self):
        xpath = self.xpath_server_group("TACACS+")
        try:
            tacacs_data = self.sr_op.get_data(xpath)
        except sr.SysrepoNotFoundError as e:
            return
        try:
            tacacs_list = list(
                tacacs_data["aaa"]["server-groups"]["server-group"]["TACACS+"][
                    "servers"
                ]["server"]
            )
        except KeyError:
            return
        rows = []
        headers = ["server", "timeout", "port", "secret-key"]
        for data in tacacs_list:
            rows.append(
                [
                    data["address"],
                    data["config"]["timeout"]
                    if "timeout" in data["config"].keys()
                    else "-",
                    data["tacacs"]["config"]["port"]
                    if "port" in data["tacacs"]["config"].keys()
                    else "-",
                    data["tacacs"]["config"]["secret-key"]
                    if "secret-key" in data["tacacs"]["config"].keys()
                    else "-",
                ]
            )

        stdout.info(tabulate(rows, headers, tablefmt="pretty"))


class AAA(object):

    xpath = "/goldstone-aaa:aaa/authentication/config/authentication-method"

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def set_aaa(self, auth_method):
        try:
            self.sr_op.get_data(self.xpath)
        except sr.SysrepoNotFoundError:
            self.sr_op.set_data(f"{self.xpath}", auth_method)
        self.sr_op.delete_data(self.xpath)
        self.sr_op.set_data(f"{self.xpath}", auth_method)

    def set_no_aaa(self):
        self.sr_op.delete_data(self.xpath)

    def show(self):
        try:
            aaa_data = self.sr_op.get_data(self.xpath)
        except sr.SysrepoNotFoundError as e:
            return
        aaa_dict = {}
        try:
            v = aaa_data["aaa"]["authentication"]["config"]["authentication-method"]
            aaa_dict["authentication-method"] = v[0]
            print_tabular(aaa_dict, "")
        except Exception as e:
            return


class System(object):
    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.aaa = AAA(conn)
        self.tacacs = TACACS(conn)

    def run_conf(self):
        server_run_conf = ["address", "timeout"]
        tacacs_run_conf = ["port", "secret-key"]
        aaa_run_conf = ["authentication"]
        stdout.info("!")

        output = []

        try:
            tacacs_tree = self.sr_op.get_data(
                "/goldstone-aaa:aaa/server-groups/server-group['TACACS+']/servers/server"
            )
            tacacs_list = list(
                tacacs_tree["aaa"]["server-groups"]["server-group"]["TACACS+"][
                    "servers"
                ]["server"]
            )
            server_address = []
            for item in tacacs_list:
                addr = item["address"]
                server_data = item.get("config")
                tacacs_data = item["tacacs"].get("config")
                dict_1 = {}
                dict_2 = {}
                for attr in server_run_conf:
                    dict_1 = {
                        attr: server_data.get(attr, None) for attr in server_run_conf
                    }
                for attr in tacacs_run_conf:
                    tacacs_dict = {
                        attr: tacacs_data.get(attr, None) for attr in tacacs_run_conf
                    }
                tacacs_dict.update(dict_1)
                for key in tacacs_dict:
                    if key == "address":
                        if tacacs_dict[key] is None:
                            pass
                        elif (tacacs_dict["port"] is None) and (
                            tacacs_dict["timeout"] is None
                        ):
                            output.append(
                                f"  tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']}"
                            )
                        elif tacacs_dict["port"] is None:
                            output.append(
                                f"  tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} timeout {tacacs_dict['timeout']}"
                            )
                        elif tacacs_dict["timeout"] is None:
                            output.append(
                                f"  tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} port {tacacs_dict['port']}"
                            )
                        else:
                            output.append(
                                f"  tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} port {tacacs_dict['port']} timeout {tacacs_dict['timeout']}"
                            )
        except Exception as e:
            pass

        try:
            aaa_data = self.sr_op.get_data("/goldstone-aaa:aaa/authentication")
            conf_data = aaa_data["aaa"]["authentication"]["config"]
            auth_method_list = conf_data.get("authentication-method")
            auth_method = auth_method_list[0]
            if auth_method is None:
                pass
            elif auth_method == "local":
                output.append(f"  aaa authentication login default local ")
            else:
                output.append(f"  aaa authentication login default group tacacs ")
        except Exception as e:
            pass

        if output:
            stdout.info("system")
            for line in output:
                stdout.info(line)
            stdout.info("  quit")
            stdout.info("!")

    def tech_support(self):
        stdout.info("AAA details")
        self.aaa.show()
        stdout.info("Tacacs server details")
        self.tacacs.show()


def create_group(sr_op, group):
    xpath = "/goldstone-aaa:aaa/server-groups/server-group[name='{}']".format(group)
    try:
        sr_op.get_data(xpath, "running")
    except sr.SysrepoNotFoundError as e:
        sr_op.set_data(f"{xpath}/config/name", group)


class AAACommand(Command):
    def __init__(self, context: Context = None, parent: Command = None, name=None):
        if name == None:
            name = "aaa"
        super().__init__(context, parent, name)
        self.aaa = AAA(context.root().conn)

    def usage(self):
        if self.parent and self.parent.name == "no":
            return "authentication login"

        return "authentication login default [group tacacs | local]"

    def exec(self, line):
        usage = f"usage: {self.name_all()} {self.usage()}"

        if self.parent and self.parent.name == "no":
            if len(line) != 2:
                raise InvalidInput(usage)
            self.aaa.set_no_aaa()
        else:
            if len(line) not in [4, 5]:
                raise InvalidInput(usage)
            if (
                line[0] != "authentication"
                or line[1] != "login"
                or line[2] != "default"
            ):
                raise InvalidInput(usage)
            if len(line) == 4 and line[3] == "local":
                value = line[3]
            elif len(line) == 5 and line[3] == "group" and line[4] == "tacacs":
                value = line[4]
            else:
                raise InvalidInput(usage)
            self.aaa.set_aaa(value)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return AAA(self.context.root().conn).show()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


GlobalShowCommand.register_command("aaa", Show, when=ModelExists("goldstone-aaa"))


class Run(Command):
    def exec(self, line):
        if len(line) == 0:
            return System(self.context.root().conn).run_conf()
        else:
            stderr.info(self.usage())

    def usage(self):
        return "usage: {self.name_all()}"


RunningConfigCommand.register_command("system", Run, when=ModelExists("goldstone-aaa"))


class TechSupport(Command):
    def exec(self, line):
        System(self.context.root().conn).tech_support()
        self.parent.xpath_list.append("/goldstone-aaa:aaa")


TechSupportCommand.register_command(
    "system", TechSupport, when=ModelExists("goldstone-aaa")
)


class TACACSCommand(Command):
    def __init__(self, context: Context = None, parent: Command = None, name=None):
        if name == None:
            name = "tacacs-server"
        super().__init__(context, parent, name)
        self.tacacs = TACACS(context.root().conn)

    def usage(self):
        if self.parent and self.parent.name == "no":
            return "host <ipaddress>"

        return "host <ipaddress> key <string> [port <portnumber>] [timeout <seconds>]"

    def exec(self, line):
        usage = f"usage: {self.name_all()} {self.usage()}"
        if self.parent and self.parent.name == "no":
            if len(line) != 2:
                raise InvalidInput(usage)
            self.tacacs.set_no_tacacs(line[1])
        else:
            if len(line) != 4 and len(line) != 6 and len(line) != 8:
                raise InvalidInput(usage)
            if line[0] != "host" or line[2] != "key":
                raise InvalidInput(usage)

            ipAddress = line[1]
            key = line[3]
            # TODO extract these default values from the YANG model
            port = 49
            timeout = 300

            if len(line) == 6:
                if line[4] != "port" and line[4] != "timeout":
                    raise InvalidInput(usage)

                if line[4] == "port":
                    port = line[5]
                elif line[4] == "timeout":
                    timeout = line[5]

            elif len(line) == 8:
                if line[4] != "port" or line[6] != "timeout":
                    raise InvalidInput(usage)

                port = line[5]
                timeout = line[7]

            self.tacacs.set_tacacs_server(ipAddress, key, port, timeout)


class Show(Command):
    def exec(self, line):
        if len(line) == 0:
            return TACACS(self.context.root().conn).show()
        else:
            raise InvalidInput(f"usage: {self.name_all()}")


GlobalShowCommand.register_command("tacacs", Show, when=ModelExists("goldstone-system"))
