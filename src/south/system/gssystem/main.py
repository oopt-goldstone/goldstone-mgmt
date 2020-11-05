import sysrepo
import libyang
import logging
import asyncio
import argparse
import signal
import re

logger = logging.getLogger(__name__)
DEFAULT_TACACS_PORT = 49
DEFAULT_TACACS_TIMEOUT = 300
MAX_TACACS_SERVERS = 3


class InvalidXPath(Exception):
    pass


class Server:
    def __init__(self):
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.data = {}

    def stop(self):
        self.sess.stop()
        self.conn.disconnect()

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
                        self.data[item["config"]["address"]]["timeout"] = item["config"][
                            "timeout"
                        ]
                    else:
                        self.data[item["config"]["address"]]["timeout"] = DEFAULT_TACACS_TIMEOUT

                    if item["tacacs"]["config"]["secret-key"]:
                        self.data[item["config"]["address"]]["secret-key"] = item["tacacs"][
                            "config"
                        ]["secret-key"]
                    else:
                        self.data[item["config"]["address"]]["secret-key"] = ""

                    if item["tacacs"]["config"]["port"]:
                        self.data[item["config"]["address"]]["port"] = item["tacacs"][
                            "config"
                        ]["port"]
                    else:
                        self.data[item["config"]["address"]]["port"] = DEFAULT_TACACS_PORT

            logger.debug(f"configured data: {self.data}")

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
            print("PAMD To Be Integrated")
            """
            fileLocation = open("/etc/pam.d/common-auth", "a+")
            data_key = list(self.data.keys())
            for address in data_key:
                content = '\n'+"auth"+'\t'+pam_tacplus_so_path+'\t'+"server="+ip+'\t'+"secret=test123"+'\n'+'auth'+'\t'+"[success=1 default=ignore]"+"\t"+"pam_unix.so"+"\t"+"nullok_secure"+"\t"+"try_first_pass"+'\n'+'account'+'\t'+pam_tacplus_so_path+'\t'+'server='+ip+'\t'+"secret=test123"+'\t'+"service=shell"+"\t"+"profile=ssh"+'\n'+"session"+'\t'+pam_tacplus_so_path+'\t'+'server='+ip+'\t'+"secret=test123"+'\t'+"server="+ip+'\t'+"secret=test123"+'\t'+"service=shell"+'\t'+'protocol=ssh'+"\n"
            fileLocation.write(content)
            fileLocation.close()
            """

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
                        else:
                            logger.error("Reached MAX TACACS SERVER count")
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
        return None

    def config_aaa_auth(self, xpath, value):
        prefix = "/goldstone-aaa:aaa/authentication/config/authentication-method"
        if not xpath == prefix:
            raise InvalidXPath()
        if value == "tacacs":
            print("PAMD To Be Integrated")
            """
            fileLocation = open("/etc/pam.d/common-auth", "a+")
            data_key = list(self.data.keys())
            for address in data_key:
                content = '\n'+"auth"+'\t'+pam_tacplus_so_path+'\t'+"server="+ip+'\t'+"secret=test123"+'\n'+'auth'+'\t'+"[success=1 default=ignore]"+"\t"+"pam_unix.so"+"\t"+"nullok_secure"+"\t"+"try_first_pass"+'\n'+'account'+'\t'+pam_tacplus_so_path+'\t'+'server='+ip+'\t'+"secret=test123"+'\t'+"service=shell"+"\t"+"profile=ssh"+'\n'+"session"+'\t'+pam_tacplus_so_path+'\t'+'server='+ip+'\t'+"secret=test123"+'\t'+"server="+ip+'\t'+"secret=test123"+'\t'+"service=shell"+'\t'+'protocol=ssh'+"\n"
            fileLocation.write(content)
            fileLocation.close()
            """

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
            config_aaa_auth(xpath)

    async def change_cb(self, event, req_id, changes, priv):
        if event != "change":
            return
        for change in changes:
            logger.debug(f"change_cb:{change}")
            if any(
                isinstance(change, cls)
                for cls in [sysrepo.ChangeCreated, sysrepo.ChangeModified]
            ):
                print(change.xpath, change.value)
                await self.parse_change_req(change.xpath, change.value, "false")
            elif any(isinstance(change, cls) for cls in [sysrepo.ChangeDeleted]):
                await self.parse_change_req(change.xpath, "ignore", "true")

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        print(xpath)
        req_xpath = "/goldstone-aaa:aaa/server-groups/server-group[name='TACACS+']/servers/server"
        print(req_xpath)
        # await self.get_change_req(req_xpath)

    async def start(self):
        try:
            self.sess.switch_datastore("running")
            self.sess.subscribe_module_change(
                "goldstone-aaa", None, self.change_cb, asyncio_register=True
            )
            self.store_data(
                "/goldstone-aaa:aaa/server-groups/server-group[name='TACACS+']/servers/server"
            )
            # self.sess.switch_datastore ('operational')
            self.sess.subscribe_oper_data_request(
                "goldstone-aaa",
                "/goldstone-aaa:aaa",
                self.oper_cb,
                oper_merge=True,
                asyncio_register=True,
            )
        except Exception as e:
            logger.error(f"error:{str(e)}")
            return {}


def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server()

        try:
            await asyncio.gather(server.start(), stop_event.wait())
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
