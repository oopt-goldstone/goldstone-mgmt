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

class Mgmtif(object):

    XPATH_MGMT = "/goldstone-mgmt-interfaces:interfaces/interface"

    def xpath_mgmt(self, ifname):
        self.name = ifname
        self.path = self.XPATH_MGMT
        return "{}[name='{}']".format(self.path, ifname)

    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)

    def get_mgmt_interface_list(self, datastore):
        try:
            tree = self.sr_op.get_data(self.XPATH_MGMT, datastore)
            return natsorted(tree["interfaces"]["interface"], key=lambda x: x["name"])
        except (KeyError, sr.errors.SysrepoNotFoundError) as error:
            return []

    def set_ip_addr(self, ifname, ip_addr, mask, config=True):
        xpath = self.xpath_mgmt(ifname)
        try:
            self.sr_op.get_data(xpath, "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(f"{xpath}/admin-status", "up")
        xpath += "/goldstone-ip:ipv4"
        self.sr_op.set_data(f"{xpath}/address[ip='{ip_addr}']/prefix-length", mask)
        if config == False:
            self.sr_op.delete_data(f"{xpath}/address[ip='{ip_addr}']")

    def set_route(self, ifname, dst_prefix, config=True):
        xpath = "/goldstone-routing:routing/static-routes/ipv4/route"
        try:
            self.sr_op.get_data(xpath, "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(
                f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix",
                dst_prefix,
            )
        try:
            self.sr_op.get_data(self.xpath_mgmt(ifname), "running")
        except sr.SysrepoNotFoundError as e:
            self.sr_op.set_data(f"{self.xpath_mgmt(ifname)}/admin-status", "up")
        self.sr_op.set_data(
            f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix",
            dst_prefix,
        )
        if config == False:
            self.sr_op.delete_data(
                f"{xpath}[destination-prefix='{dst_prefix}']/destination-prefix"
            )

    def clear_route(self):
        xpath = "/goldstone-routing:routing/static-routes/ipv4/route"
        try:
            self.sr_op.get_data(xpath, "running")
        except sr.SysrepoNotFoundError as e:
            # No configured routes are present to be cleared
            # Need not raise any error in this case
            return

        self.sr_op.delete_data(f"{xpath}")

    def show(self, ifname):
        stdout.info(self.sr_op.get_data(self.xpath_mgmt(ifname), "operational"))

    def run_conf(self):
        mgmt_dict = {}
        try:
            mgmt_data = self.sr_op.get_data(
                "/goldstone-mgmt-interfaces:interfaces/interface/goldstone-ip:ipv4/address"
            )
        except sr.SysrepoNotFoundError as e:
            pass

        try:
            mgmt_intf_dict = self.sr_op.get_data(
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
            route_data = self.sr_op.get_data(
                "/goldstone-routing:routing/static-routes/ipv4/route"
            )
        except sr.SysrepoNotFoundError as e:
            stdout.info("!")
            return
        try:
            route_conf_list = list(
                route_data["routing"]["static-routes"]["ipv4"]["route"]
            )
            for route in route_conf_list:
                dst_addr = route["destination-prefix"]
                mgmt_dict.update({"dst_addr": dst_addr})
                stdout.info(f"  ip route {mgmt_dict['dst_addr']}")
        except Exception as e:
            stdout.info("!")
            return
        stdout.info("!")


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
        self.mgmt = Mgmtif(conn)

    def mgmt_run_conf(self):
        self.mgmt.run_conf()

    def run_conf(self):
        server_run_conf = ["address", "timeout"]
        tacacs_run_conf = ["port", "secret-key"]
        aaa_run_conf = ["authentication"]
        stdout.info("!")

        self.mgmt_run_conf()

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
                            stdout.info(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']}"
                            )
                        elif tacacs_dict["port"] is None:
                            stdout.info(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} timeout {tacacs_dict['timeout']}"
                            )
                        elif tacacs_dict["timeout"] is None:
                            stdout.info(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} port {tacacs_dict['port']}"
                            )
                        else:
                            stdout.info(
                                f" tacacs-server host {tacacs_dict['address']} key {tacacs_dict['secret-key']} port {tacacs_dict['port']} timeout {tacacs_dict['timeout']}"
                            )
        except Exception as e:
            return
        stdout.info("exit")
        try:
            aaa_data = self.sr_op.get_data("/goldstone-aaa:aaa/authentication")
        except sr.SysrepoNotFoundError as e:
            stderr.info(e)
        try:
            conf_data = aaa_data["aaa"]["authentication"]["config"]
            auth_method_list = conf_data.get("authentication-method")
            auth_method = auth_method_list[0]
            if auth_method is None:
                pass
            elif auth_method == "local":
                stdout.info(f" aaa authentication login default local ")
            else:
                stdout.info(f" aaa authentication login default group tacacs ")
        except Exception as e:
            return
        stdout.info("exit")
        stdout.info("!")

    def tech_support(self):
        stdout.info("AAA details")
        self.aaa.show_aaa()
        stdout.info("Tacacs server details")
        self.tacacs.show_tacacs()


def create_group(sr_op, group):
    xpath = "/goldstone-aaa:aaa/server-groups/server-group[name='{}']".format(group)
    try:
        sr_op.get_data(xpath, "running")
    except sr.SysrepoNotFoundError as e:
        sr_op.set_data(f"{xpath}/config/name", group)
