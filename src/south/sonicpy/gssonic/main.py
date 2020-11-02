import sysrepo
import libyang
import logging
import asyncio
import argparse
import json
import signal
import struct
import base64
import swsssdk
import re

logger = logging.getLogger(__name__)


def _decode(string):
    if type(string) != type(b""):
        return string
    return string.decode("ascii")


class Server(object):
    def __init__(self):
        self.sonic_db = swsssdk.SonicV2Connector()
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

    def stop(self):
        self.sess.stop()
        self.conn.disconnect()

    async def change_cb(self, event, req_id, changes, priv):
        logger.debug("Entering change callback")
        if event != "change":
            logger.debug(
                "***********************Inside Change cb event not done************************"
            )
            return "Hello"
        for change in changes:
            logger.debug(
                "****************************inside change cb************************************************"
            )

            xpath = (change.xpath).split("/")
            _hash = ""
            hash_appl = ""
            key = ""
            member = ""
            for i in range(len(xpath)):
                node = xpath[i]
                if node.find("interface") == 0:
                    _hash = _hash + "PORT|" + node[16:-2]
                    hash_appl = hash_appl + "PORT_TABLE:" + node[16:-2]
                    if i + 1 < len(xpath):
                        key = xpath[i + 1]
                        if key == "goldstone-ip:ipv4" and i + 2 < len(xpath):
                            key = xpath[i + 2]
                    break
                if node.find("VLAN_LIST") == 0:
                    _hash = _hash + "VLAN|" + node[16:-2]
                    if i + 1 < len(xpath):
                        if (
                            xpath[i + 1].find("members") == 0
                            and xpath[i + 1] != "members"
                        ):
                            key = "members@"
                            member = xpath[i + 1][11:-2]
                        elif xpath[i + 1] == "members":
                            key = "members@"
                        else:
                            key = xpath[i + 1]
                    break
                if node.find("VLAN_MEMBER_LIST") == 0:
                    _hash = _hash + "VLAN_MEMBER|" + node[23:-2]
                    _hash = _hash.replace("'][ifname='", "|")
                    if i + 1 < len(xpath):
                        key = xpath[i + 1]

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug("......change created......")
                if type(change.value) != type({}) and key != "name" and key != "ifname":
                    if key == "description" or key == "alias":
                        self.sonic_db.set(
                            self.sonic_db.APPL_DB, hash_appl, key, change.value
                        )
                    elif key == "admin-status":
                        self.sonic_db.set(
                            self.sonic_db.APPL_DB,
                            hash_appl,
                            "admin_status",
                            change.value,
                        )
                    elif key == "members@":
                        try:
                            mem = _decode(
                                self.sonic_db.get(self.sonic_db.CONFIG_DB, _hash, key)
                            )
                            mem_list = mem.split(",")
                            if change.value not in mem_list:
                                mem + "," + str(change.value)
                            self.sonic_db.set(self.sonic_db.CONFIG_DB, _hash, key, mem)
                        except:
                            self.sonic_db.set(
                                self.sonic_db.CONFIG_DB, _hash, key, str(change.value)
                            )
                    else:
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB, _hash, key, str(change.value)
                        )

            if isinstance(change, sysrepo.ChangeModified):
                logger.debug("......change modified......")
                if key == "description" or key == "alias":
                    self.sonic_db.set(
                        self.sonic_db.APPL_DB, hash_appl, key, str(change.value)
                    )
                elif key == "admin-status":
                    self.sonic_db.set(
                        self.sonic_db.APPL_DB,
                        hash_appl,
                        "admin_status",
                        str(change.value),
                    )
                else:
                    self.sonic_db.set(
                        self.sonic_db.CONFIG_DB, _hash, key, str(change.value)
                    )

            if isinstance(change, sysrepo.ChangeDeleted):
                logger.debug("......change deleted......")
                if key == "members@":
                    mem = _decode(
                        self.sonic_db.get(self.sonic_db.CONFIG_DB, _hash, key)
                    )
                    if mem != None:
                        mem = mem.split(",")
                        mem.remove(member)
                        value = ",".join(mem)
                        self.sonic_db.set(self.sonic_db.CONFIG_DB, _hash, key, value)
                elif _hash.find("VLAN|") == 0 and key == "":
                    self.sonic_db.delete(self.sonic_db.CONFIG_DB, _hash)

                elif _hash.find("VLAN_MEMBER|") == 0 and key == "":
                    self.sonic_db.delete(self.sonic_db.CONFIG_DB, _hash)

    def get_oper_data(self, req_xpath):
        path_prefix = "/goldstone-interfaces:interfaces/interface[name='"

        if req_xpath.endswith("oper-status"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/oper-status", "")
            key = ifname.replace("Ethernet", "PORT_TABLE:Ethernet")

            self.sonic_db.connect(self.sonic_db.APPL_DB)
            data = _decode(self.sonic_db.get(self.sonic_db.APPL_DB, key, "oper_status"))

            return data

        elif req_xpath.endswith("in-octets"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-octets", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_OCTETS"
                )
            )
            return data

        elif req_xpath.endswith("in-unicast-pkts"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-unicast-pkts", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_UCAST_PKTS"
                )
            )
            return data

        elif req_xpath.endswith("in-broadcast-pkts"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-broadcast-pkts", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_BROADCAST_PKTS"
                )
            )
            return data

        elif req_xpath.endswith("in-multicast-pkts"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-multicast-pkts", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_MULTICAST_PKTS"
                )
            )
            return data

        elif req_xpath.endswith("in-discards"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-discards", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_DISCARDS"
                )
            )
            return data

        elif req_xpath.endswith("in-errors"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-errors", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_ERRORS"
                )
            )
            return data

        elif req_xpath.endswith("in-unknown-protos"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-unknown-protos", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_UNKNOWN_PROTOS"
                )
            )
            return data

        elif req_xpath.endswith("out-octets"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-octets", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_OCTETS"
                )
            )
            return data

        elif req_xpath.endswith("out-unicast-pkts"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-unicast-pkts", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_UCAST_PKTS"
                )
            )
            return data

        elif req_xpath.endswith("out-broadcast-pkts"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-broadcast-pkts", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB,
                    key,
                    "SAI_PORT_STAT_IF_OUT_BROADCAST_PKTS",
                )
            )
            return data

        elif req_xpath.endswith("out-multicast-pkts"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-multicast-pkts", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB,
                    key,
                    "SAI_PORT_STAT_IF_OUT_MULTICAST_PKTS",
                )
            )
            return data

        elif req_xpath.endswith("out-discards"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-discards", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_DISCARDS"
                )
            )
            return data

        elif req_xpath.endswith("out-errors"):
            self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-errors", "")

            key = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, "COUNTERS_PORT_NAME_MAP", ifname
                )
            )
            key = "COUNTERS:" + key

            data = _decode(
                self.sonic_db.get(
                    self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_ERRORS"
                )
            )
            return data

    def interface_oper_cb(self, req_xpath):
        # Changing to operational datastore to fetch data
        # for the unconfigurable params in the xpath, data will
        # be fetched from Redis and complete data will be returned.
        #
        # WARNING: If we enable below line, sysrepo gets locked and it will not be released
        # self.sess.switch_datastore("operational")
        r = {}
        path_list = req_xpath.split("/")
        statistic_leaves = [
            "in-octets",
            "in-unicast-pkts",
            "in-broadcast-pkts",
            "in-multicast-pkts",
            "in-discards",
            "in-errors",
            "in-unknown-protos",
            "out-octets",
            "out-unicast-pkts",
            "out-broadcast-pkts",
            "out-multicast-pkts",
            "out-discards",
            "out-errors",
        ]

        try:
            _data = self.sess.get_data(req_xpath)
        except:
            logger.info("Unable for fetch data in oper_cb")
            return r

        if len(path_list) <= 3:
            r = self.sess.get_data(req_xpath)
            if r == {}:
                return r
            else:
                for intf in r["interfaces"]["interface"]:
                    ifname = intf["name"]
                    xpath = (
                        f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                    )
                    oper_status = self.get_oper_data(xpath + "/oper-status")
                    if oper_status != None:
                        intf["oper-status"] = oper_status
                    xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/statistics"
                    intf["statistics"] = {}
                    for sl in statistic_leaves:
                        sl_value = self.get_oper_data(xpath + "/" + sl)
                        if sl_value != None:
                            intf["statistics"][sl] = sl_value
            return r
        elif req_xpath[-10:] == "statistics":
            xpath_T = req_xpath.replace("/statistics", "")
            r = self.sess.get_data(xpath_T)
            if r == {}:
                return r
            else:
                for intf in r["interfaces"]["interface"]:
                    ifname = intf["name"]
                    intf["statistics"] = {}
                    xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/statistics"
                    for sl in statistic_leaves:
                        sl_value = self.get_oper_data(xpath + "/" + sl)
                        if sl_value != None:
                            intf["statistics"][sl] = sl_value
                return r

        elif (
            path_list[len(path_list) - 1] in statistic_leaves
            or path_list[len(path_list) - 1] == "oper-status"
        ):
            xpath_T = req_xpath.replace(
                "/statistics/" + path_list[len(path_list) - 1], ""
            )
            xpath_T = xpath_T.replace("/oper-status", "")

            r = self.sess.get_data(xpath_T)
            if r == {}:
                return r
            else:
                for intf in r["interfaces"]["interface"]:
                    ifname = intf["name"]
                    if path_list[len(path_list) - 1] == "oper-status":
                        value = self.get_oper_data(req_xpath)
                        if value != None:
                            intf["oper-status"] = value
                    else:
                        intf["statistics"] = {}
                        value = self.get_oper_data(req_xpath)
                        if value != None:
                            intf["statistics"][path_list[len(path_list) - 1]] = value
                return r
        return r

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(
            "****************************inside oper-callback******************************"
        )
        if req_xpath.find("/goldstone-interfaces:interfaces") == 0:
            return self.interface_oper_cb(req_xpath)

    async def start(self):
        logger.debug(
            "****************************inside start******************************"
        )
        self.sonic_db.connect(self.sonic_db.CONFIG_DB)
        self.sonic_db.connect(self.sonic_db.APPL_DB)

        logger.debug(
            "****************************reconciliation******************************"
        )

        self.sess.switch_datastore("running")

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):

                intf_data = self.sess.get_data("/goldstone-interfaces:interfaces")
                if "interfaces" in intf_data:
                    intf_list = intf_data["interfaces"]["interface"]
                    for intf in intf_list:
                        name = intf.pop("name")
                        for key in intf:
                            if key == "ipv4":
                                if "mtu" in intf[key]:
                                    self.sonic_db.set(
                                        self.sonic_db.CONFIG_DB,
                                        "PORT|" + name,
                                        "mtu",
                                        str(intf[key]["mtu"]),
                                    )
                            elif key == "description":
                                self.sonic_db.set(
                                    self.sonic_db.APPL_DB,
                                    "PORT_TABLE:" + name,
                                    "description",
                                    str(intf[key]),
                                )
                            elif key == "alias":
                                self.sonic_db.set(
                                    self.sonic_db.APPL_DB,
                                    "PORT_TABLE:" + name,
                                    "alias",
                                    str(intf[key]),
                                )
                            elif key == "admin-status":
                                self.sonic_db.set(
                                    self.sonic_db.APPL_DB,
                                    "PORT_TABLE:" + name,
                                    "admin_status",
                                    str(intf[key]),
                                )
                            elif key == "if-index":
                                pass
                            else:
                                self.sonic_db.set(
                                    self.sonic_db.CONFIG_DB,
                                    "PORT|" + name,
                                    key,
                                    str(intf[key]),
                                )

                vlan_data = self.sess.get_data("/goldstone-vlan:vlan")
                if "vlan" in vlan_data:
                    if "VLAN" in vlan_data["vlan"]:
                        vlan_list = vlan_data["vlan"]["VLAN"]["VLAN_LIST"]

                        for vlan in vlan_list:
                            name = vlan.pop("name")
                            for key in vlan:
                                if key == "members":
                                    self.sonic_db.set(
                                        self.sonic_db.CONFIG_DB,
                                        "VLAN|" + name,
                                        "members@",
                                        ",".join(vlan[key]),
                                    )
                                else:
                                    self.sonic_db.set(
                                        self.sonic_db.CONFIG_DB,
                                        "VLAN|" + name,
                                        key,
                                        str(vlan[key]),
                                    )

                    if "VLAN_MEMBER" in vlan_data["vlan"]:
                        vlan_member_list = vlan_data["vlan"]["VLAN_MEMBER"][
                            "VLAN_MEMBER_LIST"
                        ]

                        for vlan_member in vlan_member_list:
                            self.sonic_db.set(
                                self.sonic_db.CONFIG_DB,
                                "VLAN_MEMBER|"
                                + vlan_member["name"]
                                + "|"
                                + vlan_member["ifname"],
                                "tagging_mode",
                                vlan_member["tagging_mode"],
                            )

                hash_keys = self.sonic_db.keys(
                    self.sonic_db.APPL_DB, pattern="PORT_TABLE:Ethernet*"
                )
                if hash_keys != None:
                    hash_keys = map(_decode, hash_keys)

                    for _hash in hash_keys:
                        ifname = _hash.split(":")[1]
                        intf_data = self.sonic_db.get_all(self.sonic_db.APPL_DB, _hash)
                        intf_keys = [v.decode("ascii") for v in list(intf_data.keys())]

                        if "admin_status" not in intf_keys:
                            self.sonic_db.set(
                                self.sonic_db.APPL_DB,
                                "PORT_TABLE:" + ifname,
                                "admin_status",
                                "down",
                            )

                self.sess.switch_datastore("operational")

                hash_keys = self.sonic_db.keys(
                    self.sonic_db.CONFIG_DB, pattern="PORT|Ethernet*"
                )
                if hash_keys != None:
                    hash_keys = map(_decode, hash_keys)

                    for _hash in hash_keys:
                        ifname = _hash.split("|")[1]
                        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                        intf_data = self.sonic_db.get_all(
                            self.sonic_db.CONFIG_DB, _hash
                        )
                        for key in intf_data:
                            value = _decode(intf_data[key])
                            key = _decode(key)
                            if key == "mtu":
                                self.sess.set_item(
                                    f"{xpath}/goldstone-ip:ipv4/{key}", value
                                )
                            elif (
                                key != "index"
                                and key != "phys-address"
                                and key != "admin-status"
                                and key != "alias"
                                and key != "description"
                            ):
                                self.sess.set_item(f"{xpath}/{key}", value)

                hash_keys = self.sonic_db.keys(
                    self.sonic_db.APPL_DB, pattern="PORT_TABLE:Ethernet*"
                )
                if hash_keys != None:
                    hash_keys = map(_decode, hash_keys)

                    for _hash in hash_keys:
                        ifname = _hash.split(":")[1]
                        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                        intf_data = self.sonic_db.get_all(self.sonic_db.APPL_DB, _hash)
                        for key in intf_data:
                            value = _decode(intf_data[key])
                            key = _decode(key)
                            if key == "alias" or key == "description":
                                self.sess.set_item(f"{xpath}/{key}", value)
                            elif key == "admin_status":
                                if value == None:
                                    value = "down"
                                self.sess.set_item(f"{xpath}/admin-status", value)

                hash_keys = self.sonic_db.keys(
                    self.sonic_db.CONFIG_DB, pattern="VLAN|Vlan*"
                )

                if hash_keys != None:
                    hash_keys = map(_decode, hash_keys)

                    for _hash in hash_keys:
                        name = _hash.split("|")[1]
                        xpath = f"/goldstone-vlan:vlan/VLAN/VLAN_LIST[name='{name}']"
                        vlanDATA = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, _hash)
                        for key in vlanDATA:
                            value = _decode(vlanDATA[key])
                            key = _decode(key)
                            if key == "members@":
                                member_list = value.split(",")
                                for member in member_list:
                                    self.sess.set_item(f"{xpath}/members", member)
                            else:
                                self.sess.set_item(f"{xpath}/{key}", value)

                hash_keys = self.sonic_db.keys(
                    self.sonic_db.CONFIG_DB, pattern="VLAN_MEMBER|Vlan*|Ethernet*"
                )

                if hash_keys != None:
                    hash_keys = map(_decode, hash_keys)

                    for _hash in hash_keys:
                        name, ifname = _hash.split("|")[1:]
                        xpath = f"/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST[name='{name}'][ifname='{ifname}']"
                        member_data = self.sonic_db.get_all(
                            self.sonic_db.CONFIG_DB, _hash
                        )
                        for key in member_data:
                            value = _decode(member_data[key])
                            key = _decode(key)
                            self.sess.set_item(f"{xpath}/{key}", value)

                self.sess.apply_changes()
                self.sess.switch_datastore("running")

                self.sess.subscribe_module_change(
                    "goldstone-interfaces", None, self.change_cb, asyncio_register=True
                )
                self.sess.subscribe_module_change(
                    "goldstone-vlan", None, self.change_cb, asyncio_register=True
                )
                logger.debug(
                    "**************************after subscribe module change****************************"
                )

                self.sess.subscribe_oper_data_request(
                    "goldstone-interfaces",
                    "/goldstone-interfaces:interfaces",
                    self.oper_cb,
                    oper_merge=True,
                    asyncio_register=True,
                )


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
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
