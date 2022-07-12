import os
import logging
import re
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp

DEFAULT_TACACS_PORT = 49
DEFAULT_TACACS_TIMEOUT = 300
MAX_TACACS_SERVERS = 3

# FILE
PAM_AUTH_CONF = "/etc/pam.d/common-auth-gs"
NSS_TACPLUS_CONF = "/etc/tacplus_nss.conf"
NSS_CONF = "/etc/nsswitch.conf"
TACACS_NAME = "TACACS+"


class InvalidXPath(Exception):
    pass


logger = logging.getLogger(__name__)


class AAAHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

    def apply(self, user):
        self.setup_cache(user)
        user["update"] = True


class AAAServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-aaa")
        self.handlers = {
            "aaa": AAAHandler,
        }

    async def post(self, user):
        if not user.get("update"):
            return

        config = user.get("cache")
        await self.reconcile(config.get("aaa", {}))

    def modify_single_file(self, filename, operations):
        cmd = "sed -e {0} {1} > {1}.new; mv -f {1} {1}.old; mv -f {1}.new {1}".format(
            " -e ".join(operations), filename
        )
        os.system(cmd)

    def modify_common_auth_gs_file(self, config):
        data_key = list(config.keys())
        content = ""

        for key, value in config.items():
            content += (
                "\n"
                + "auth"
                + "\t"
                + "[success=done new_authtok_reqd=done default=ignore]"
                + "\t"
                + "pam_tacplus.so server="
                + key
                + ":"
                + str(value["port"])
                + "\t"
                + "secret="
                + value["secret-key"]
                + "\t"
                + "timeout="
                + str(value["timeout"])
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

        with open(PAM_AUTH_CONF, "w") as f:
            f.write(content)

    def modify_conf_file(self, config, auto_method):
        # Add tacplus in nsswitch.conf if TACACS+ enable
        if auto_method == "tacacs":
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
        for key, value in config.items():
            content += (
                "server="
                + key
                + ":"
                + str(value["port"])
                + ",secret="
                + value["secret-key"]
                + ",timeout="
                + str(value["timeout"])
                + "\n"
            )
        content += (
            "user_priv=15;pw_info=remote_user_su;gid=1001;group=gsmgmt;shell=/usr/local/bin/gscli"
            + "\n"
            + "user_priv=1;pw_info=remote_user;gid=100;group=gsmgmt;shell=/usr/local/bin/gscli"
            + "\n"
            + "many_to_one=y"
        )

        with open(NSS_TACPLUS_CONF, "w") as f:
            f.write(content)

    async def reconcile(self, config):
        logger.debug(f"config: {config}")
        servers = config.get("server-groups", {}).get("server-group", [])
        if servers and list(servers)[0]["name"] == TACACS_NAME:
            servers = list(servers)[0].get("servers", {}).get("server", [])
        else:
            servers = []

        auth_method = (
            config.get("authentication", {})
            .get("config", {})
            .get("authentication-method", ["local"])
        )

        config = {}
        for item in servers:
            c = {
                "timeout": item.get("config", {}).get(
                    "timeout", DEFAULT_TACACS_TIMEOUT
                ),
                "secret-key": item.get("tacacs", {})
                .get("config", {})
                .get("secret-key", ""),
                "port": item.get("tacacs", {})
                .get("config", {})
                .get("port", DEFAULT_TACACS_PORT),
            }
            key = item["config"]["address"]
            config[key] = c

        logger.debug(f"servers: {config}, auth-method: {auth_method[0]}")
        self.modify_common_auth_gs_file(config)
        self.modify_conf_file(config, auth_method[0])

    async def start(self):
        config = self.conn.get("/goldstone-aaa:aaa", {})
        await self.reconcile(config)
        return await super().start()
