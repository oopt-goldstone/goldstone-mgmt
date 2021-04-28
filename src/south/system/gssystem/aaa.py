import os
import logging
import sysrepo
import re

DEFAULT_TACACS_PORT = 49
DEFAULT_TACACS_TIMEOUT = 300
MAX_TACACS_SERVERS = 3

# FILE
PAM_AUTH_CONF = "/etc/pam.d/common-auth-gs"
NSS_TACPLUS_CONF = "/etc/tacplus_nss.conf"
NSS_CONF = "/etc/nsswitch.conf"


class InvalidXPath(Exception):
    pass


logger = logging.getLogger(__name__)


class AAAServer:
    def __init__(self, conn):
        self.sess = conn.start_session()
        self.auth_default = {
            "login": "local",
        }
        self.auth = {}
        self.data = {}

    def stop(self):
        self.sess.stop()

    def modify_single_file(self, filename, operations=None):
        if operations:
            cmd = (
                "sed -e {0} {1} > {1}.new; mv -f {1} {1}.old; mv -f {1}.new {1}".format(
                    " -e ".join(operations), filename
                )
            )
            os.system(cmd)

    def store_data(self, xpath):
        xpath = "/goldstone-aaa:aaa/server-groups/server-group[name='TACACS+']/servers/server"
        try:
            items = self.sess.get_data(xpath)
        except sysrepo.SysrepoNotFoundError as e:
            logger.debug("Not able to fetch data from database")
            return
        try:
            items = list((items["aaa"]["server-groups"]["server-group"]))
            items = list(items[0]["servers"]["server"])
            for item in items:
                if item["config"]["address"]:
                    self.data[item["config"]["address"]] = {}
                    if item["config"]["timeout"]:
                        self.data[item["config"]["address"]]["timeout"] = item[
                            "config"
                        ]["timeout"]
                    else:
                        self.data[item["config"]["address"]][
                            "timeout"
                        ] = DEFAULT_TACACS_TIMEOUT

                    if item["tacacs"]["config"]["secret-key"]:
                        self.data[item["config"]["address"]]["secret-key"] = item[
                            "tacacs"
                        ]["config"]["secret-key"]
                    else:
                        self.data[item["config"]["address"]]["secret-key"] = ""

                    if item["tacacs"]["config"]["port"]:
                        self.data[item["config"]["address"]]["port"] = item["tacacs"][
                            "config"
                        ]["port"]
                    else:
                        self.data[item["config"]["address"]][
                            "port"
                        ] = DEFAULT_TACACS_PORT

            logger.debug(f"configured data: {self.data}")
            self.modify_common_auth_gs_file()

        except KeyError as e:
            logger.debug("Not able to fetch configured data")
            return

        xpath = "/goldstone-aaa:aaa/authentication/config/authentication-method"

        try:
            auth_method = self.sess.get_data(xpath)
        except sysrepo.SysrepoNotFoundError as e:
            logger.debug("Not able to fetch data from database")
            return

        if auth_method == "tacacs":
            self.auth["login"] = auth_method
            self.auth["failthrough"] = True

            self.modify_conf_file()

    def config_tacacs(self, xpath, value, delete):
        prefix = (
            "/goldstone-aaa:aaa/server-groups/server-group[name='TACACS+']/servers/"
        )

        if not xpath.startswith(prefix):
            raise InvalidXPath()

        xpath = xpath[len(prefix) :]
        if xpath == "" or xpath == "/server":
            return None

        s = re.search(
            r"server\[address\=\'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\'\]", xpath
        )
        if not s:
            raise InvalidXPath()

        address = re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", xpath)
        address = address.group()
        xpath = xpath[s.end() :]

        if xpath == "" or xpath == "/address":
            return None

        if xpath.startswith("/config"):
            xpath = xpath[len("/config") :]
            if xpath == "":
                return None

            if xpath == "/address":
                if delete == "true":
                    if address in self.data:
                        del self.data[address]
                else:
                    if not address in self.data:
                        if len(self.data) < MAX_TACACS_SERVERS:
                            self.data[address] = {}
                            self.data[address]["port"] = DEFAULT_TACACS_PORT
                            self.data[address]["timeout"] = DEFAULT_TACACS_TIMEOUT
                            self.data[address]["secret-key"] = ""
                        else:
                            logger.error("Reached MAX TACACS SERVER count")
                            raise sysrepo.SysrepoInvalArgError(
                                "Maximum TACACS Server count reached"
                            )
                            return
            elif xpath == "/timeout":
                if delete == "true":
                    if address in self.data:
                        self.data[address]["timeout"] = DEFAULT_TACACS_TIMEOUT
                else:
                    if address in self.data:
                        self.data[address]["timeout"] = value
            else:
                raise InvalidXPath()
        elif xpath.startswith("/tacacs"):
            xpath = xpath[len("/tacacs") :]
            if xpath == "":
                return None
            if xpath.startswith("/config"):
                xpath = xpath[len("/config") :]
                if xpath == "":
                    return None

                if xpath == "/port":
                    if delete == "true":
                        if address in self.data:
                            self.data[address]["port"] = DEFAULT_TACACS_PORT
                    else:
                        if address in self.data:
                            self.data[address]["port"] = value
                elif xpath == "/secret-key":
                    if delete == "true":
                        if address in self.data:
                            self.data[address]["secret-key"] = ""
                    else:
                        if address in self.data:
                            self.data[address]["secret-key"] = value
                else:
                    raise InvalidXPath()
            else:
                raise InvalidXPath()
        else:
            raise InvalidXPath()
        logger.debug(f"configured data: {self.data}")
        self.modify_common_auth_gs_file()
        return None

    def config_aaa_auth(self, xpath, value):
        prefix = "/goldstone-aaa:aaa/authentication/config/authentication-method"
        if xpath.startswith(prefix):
            self.auth["login"] = value
            self.auth["failthrough"] = True

            self.modify_conf_file()

    def modify_common_auth_gs_file(self):
        auth = self.auth_default.copy()
        auth.update(self.auth)

        data_key = list(self.data.keys())

        with open(PAM_AUTH_CONF, "w") as f:
            content = ""
            for ip in data_key:
                content += (
                    "\n"
                    + "auth"
                    + "\t"
                    + "[success=done new_authtok_reqd=done default=ignore]"
                    + "\t"
                    + "pam_tacplus.so server="
                    + ip
                    + ":"
                    + str(self.data[ip]["port"])
                    + "\t"
                    + "secret="
                    + self.data[ip]["secret-key"]
                    + "\t"
                    + "timeout="
                    + str(self.data[ip]["timeout"])
                    + "\t"
                    + "try_first_pass"
                )
            content += (
                "\n"
                + "auth"
                + "\t"
                + "[success=1 default=ignore]"
                + "\t"
                + "pam_unix.so nullok try_first_pass"
                + "\n"
                + "auth    requisite                       pam_deny.so"
                + "\n"
                + "auth    required                        pam_permit.so"
            )

            f.write(content)

    def modify_conf_file(self):
        auth = self.auth_default.copy()
        auth.update(self.auth)

        data_key = list(self.data.keys())

        # Add tacplus in nsswitch.conf if TACACS+ enable
        if "tacacs" in auth["login"]:
            # Modify common-auth include file in /etc/pam.d/login and sshd
            if os.path.isfile(PAM_AUTH_CONF):
                self.modify_single_file(
                    "/etc/pam.d/sshd", ["'/^@include/s/common-auth$/common-auth-gs/'"]
                )

            # Add tacplus in nsswitch.conf if TACACS+ enable
            if os.path.isfile(NSS_CONF):
                self.modify_single_file(
                    NSS_CONF,
                    [
                        "'/tacplus/b'",
                        "'/^passwd/s/compat/tacplus &/'",
                        "'/^passwd/s/files/tacplus &/'",
                    ],
                )
        else:
            self.modify_single_file(
                "/etc/pam.d/sshd", ["'/^@include/s/common-auth-gs$/common-auth/'"]
            )
            if os.path.isfile(NSS_CONF):
                self.modify_single_file(NSS_CONF, ["'/^passwd/s/tacplus //g'"])

        # Set tacacs+ server in nss-tacplus conf
        content = "debug=on" + "\n"
        with open(NSS_TACPLUS_CONF, "w") as f:
            for ip in data_key:
                content += (
                    "server="
                    + ip
                    + ":"
                    + str(self.data[ip]["port"])
                    + ",secret="
                    + self.data[ip]["secret-key"]
                    + ",timeout="
                    + str(self.data[ip]["timeout"])
                    + "\n"
                )
            content += (
                "user_priv=15;pw_info=remote_user_su;gid=1001;group=admin;shell=/usr/local/bin/gscli"
                + "\n"
                + "user_priv=1;pw_info=remote_user;gid=100;group=users;shell=/usr/local/bin/gscli"
                + "\n"
                + "many_to_one=y"
            )
            f.write(content)

    async def parse_change_req(self, xpath, value, delete):
        tacacs_xpath = "/goldstone-aaa:aaa/server-groups/server-group[name='TACACS+']/servers/server"
        aaa_auth_xpath = "/goldstone-aaa:aaa/authentication"

        if xpath.startswith(tacacs_xpath):
            try:
                self.config_tacacs(xpath, value, delete)
            except InvalidXPath:
                logger.error(f"invalid xpath: {xpath}")
                return
        elif xpath.startswith(aaa_auth_xpath):
            self.config_aaa_auth(xpath, value)

    async def change_cb(self, event, req_id, changes, priv):
        if event != "change":
            return
        for change in changes:
            logger.debug(f"change_cb:{change}")
            if any(
                isinstance(change, cls)
                for cls in [sysrepo.ChangeCreated, sysrepo.ChangeModified]
            ):
                await self.parse_change_req(change.xpath, change.value, "false")
            elif any(isinstance(change, cls) for cls in [sysrepo.ChangeDeleted]):
                await self.parse_change_req(change.xpath, "ignore", "true")

    async def start(self):

        self.sess.switch_datastore("running")
        self.sess.subscribe_module_change(
            "goldstone-aaa", None, self.change_cb, asyncio_register=True
        )
        self.store_data(
            "/goldstone-aaa:aaa/server-groups/server-group[name='TACACS+']/servers/server"
        )
        return []
