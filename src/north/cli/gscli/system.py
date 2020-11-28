import sysrepo as sr
from tabulate import tabulate
from .common import sysrepo_wrap, print_tabular
import json
import re


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

    def set_tacacs_server(self, ipAddress, key, port, timeout):
        xpath = self.xpath("TACACS+", ipAddress)
        create_group(self.sr_op, "TACACS+")
        self.sr_op.set_data(f"{xpath}/config/address", ipAddress)
        self.sr_op.set_data(f"{xpath}/tacacs/config/secret-key", key)
        self.sr_op.set_data(f"{xpath}/tacacs/config/port", port)
        self.sr_op.set_data(f"{xpath}/config/timeout", timeout)

    def set_no_tacacs(self, address):
        xpath = self.xpath("TACACS+", address)
        create_group(self.sr_op, "TACACS+")
        self.sr_op.delete_data(xpath)

    def show_tacacs(self):
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

        print(tabulate(rows, headers, tablefmt="pretty"))


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

    def show_aaa(self):
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
        print("!")
        try:
            tacacs_tree = self.sr_op.get_data(
                "/goldstone-aaa:aaa/server-groups/server-group['TACACS+']/servers/server"
            )
        except sr.SysrepoNotFoundError as e:
            return
        try:
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
                            print(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']}"
                            )
                        elif tacacs_dict["port"] is None:
                            print(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} timeout {tacacs_dict['timeout']}"
                            )
                        elif tacacs_dict["timeout"] is None:
                            print(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} port {tacacs_dict['port']}"
                            )
                        else:
                            print(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} port {tacacs_dict['port']} timeout {tacacs_dict['timeout']}"
                            )
        except Exception as e:
            return
        print("exit")
        try:
            aaa_data = self.sr_op.get_data("/goldstone-aaa:aaa/authentication")
        except sr.SysrepoNotFoundError as e:
            print(e)
        try:
            conf_data = aaa_data["aaa"]["authentication"]["config"]
            auth_method_list = conf_data.get("authentication-method")
            auth_method = auth_method_list[0]
            if auth_method is None:
                pass
            elif auth_method == "local":
                print(f" aaa authentication login default local ")
            else:
                print(f" aaa authentication login default group tacacs ")
        except Exception as e:
            return
        print("exit")
        print("!")

    def tech_support(self):
        print("AAA details")
        self.aaa.show_aaa()
        print("Tacacs server details")
        self.tacacs.show_tacacs()


def create_group(sr_op, group):
    xpath = "/goldstone-aaa:aaa/server-groups/server-group[name='{}']".format(group)
    try:
        sr_op.get_data(xpath, "running")
    except sr.SysrepoNotFoundError as e:
        sr_op.set_data(f"{xpath}/config/name", group)
