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
from .k8s_api import incluster_apis

logger = logging.getLogger(__name__)

COUNTER_PORT_MAP = "COUNTERS_PORT_NAME_MAP"
COUNTER_TABLE_PREFIX = "COUNTERS:"


def _decode(string):
    if hasattr(string, "decode"):
        return string.decode("utf-8")
    return string


def yang_val_to_speed(yang_val):
    yang_val = yang_val.split("_")
    return yang_val[1].split("GB")[0]


def speed_to_yang_val(speed):
    # Considering only speeds supported in CLI
    if speed == b"25000":
        return "SPEED_25GB"
    elif speed == b"50000":
        return "SPEED_50GB"
    elif speed == b"10000":
        return "SPEED_10GB"
    elif speed == b"1000":
        return "SPEED_1GB"
    raise sysrepo.SysrepoInvalArgError(f"unsupported speed: {speed}")


class Server(object):
    def __init__(self):
        self.sonic_db = swsssdk.SonicV2Connector()
        # HMSET is not available in above connector, so creating new one
        self.sonic_configdb = swsssdk.ConfigDBConnector()
        self.sonic_configdb.connect()
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.is_usonic_rebooting = False
        self.k8s = incluster_apis()
        self.counter_dict = {
            "SAI_PORT_STAT_IF_IN_UCAST_PKTS": 0,
            "SAI_PORT_STAT_IF_IN_ERRORS": 0,
            "SAI_PORT_STAT_IF_IN_DISCARDS": 0,
            "SAI_PORT_STAT_IF_IN_BROADCAST_PKTS": 0,
            "SAI_PORT_STAT_IF_IN_MULTICAST_PKTS": 0,
            "SAI_PORT_STAT_IF_IN_UNKNOWN_PROTOS": 0,
            "SAI_PORT_STAT_IF_OUT_UCAST_PKTS": 0,
            "SAI_PORT_STAT_IF_OUT_ERRORS": 0,
            "SAI_PORT_STAT_IF_OUT_DISCARDS": 0,
            "SAI_PORT_STAT_IF_OUT_BROADCAST_PKTS": 0,
            "SAI_PORT_STAT_IF_OUT_MULTICAST_PKTS": 0,
            "SAI_PORT_STAT_IF_OUT_UNKNOWN_PROTOS": 0,
            "SAI_PORT_STAT_IF_IN_OCTETS": 0,
            "SAI_PORT_STAT_IF_OUT_OCTETS": 0,
        }
        self.counter_if_dict = {}

    def stop(self):
        self.sess.stop()
        self.conn.disconnect()

    def set_config_db(self, event, _hash, key, value):
        if event != "done":
            return
        return self.sonic_db.set(self.sonic_db.CONFIG_DB, _hash, key, value)

    async def restart_usonic(self):
        self.is_usonic_rebooting = True
        await self.k8s.restart_usonic()

    async def watch_pods(self):
        await self.k8s.watch_pods()

        logger.debug("uSONiC deployment ready")

        # Enable counters in SONiC
        self.enable_counters()

        # After usonic is UP , its taking approximately
        # 15 seconds to populate counter data
        logger.debug("waiting another 15 seconds for counters")
        await asyncio.sleep(15)
        # Caching base values of counters
        self.cache_counters()

        self.is_usonic_rebooting = False
        logger.info("uSONiC ready")

    async def wait_for_sr_unlock(self):
        # Since is_locked() is returning False always,
        # Waiting to take lock
        while True:
            try:
                with self.sess.lock("goldstone-interfaces"):
                    with self.sess.lock("goldstone-vlan"):
                        break
            except:
                # If taking lock fails
                await asyncio.sleep(0.1)
                continue

        # Release lock and return
        return

    async def parse_change_req(self, xpath):
        xpath = xpath.split("/")
        _hash = ""
        key = ""
        member = ""
        attr_dict = {"xpath": xpath}
        for i in range(len(xpath)):
            node = xpath[i]
            if node.find("interface") == 0:
                ifname = node.split("'")[1]
                intf_names = self.sonic_db.keys(
                    self.sonic_db.CONFIG_DB, pattern="PORT|" + ifname
                )
                if intf_names == None:
                    logger.debug(
                        "*************** Invalid Interface name ****************"
                    )
                    raise sysrepo.SysrepoInvalArgError("Invalid Interface name")
                attr_dict.update({"ifname": ifname})
                _hash = _hash + "PORT|" + ifname
                if i + 1 < len(xpath):
                    key = xpath[i + 1]
                    if key == "goldstone-ip:ipv4" and i + 2 < len(xpath):
                        key = xpath[i + 2]
                    if key == "breakout" and i + 2 < len(xpath):
                        key = xpath[i + 2]
                break
            if node.find("VLAN_LIST") == 0:
                _hash = _hash + "VLAN|" + node.split("'")[1]
                if i + 1 < len(xpath):
                    if xpath[i + 1].find("members") == 0 and xpath[i + 1] != "members":
                        key = "members@"
                        member = xpath[i + 1].split("'")[1]
                    elif xpath[i + 1] == "members":
                        key = "members@"
                    else:
                        key = xpath[i + 1]
                attr_dict.update({"member": member})
                break
            if node.find("VLAN_MEMBER_LIST") == 0:
                _hash = (
                    _hash
                    + "VLAN_MEMBER|"
                    + node.split("'")[1]
                    + "|"
                    + node.split("'")[3]
                )
                if i + 1 < len(xpath):
                    key = xpath[i + 1]
                break

        return key, _hash, attr_dict

    async def breakout_callback(self):
        self.sess.switch_datastore("running")

        await self.wait_for_sr_unlock()

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):

                await self.watch_pods()

                self.reconcile()
                self.update_oper_db()

                self.sess.switch_datastore("running")

    async def breakout_update_usonic(self, breakout_dict):

        logger.debug("Starting to Update usonic's configMap and deployment")

        interface_list = []

        self.sess.switch_datastore("running")
        # Frame interface_list with data available in sysrepo
        intf_data = self.sess.get_data("/goldstone-interfaces:interfaces")
        if "interfaces" in intf_data:
            intf_list = intf_data["interfaces"]["interface"]
            for intf in intf_list:
                ifname = intf["name"]
                # Prioirty for adding interfaces in interface_list:
                #
                # 1. Preference will be for the data received as arguments
                #    as this data will not be commited in sysrepo yet.
                # 2. Interfaces present in datastore with already configured
                #    breakout data or without breakout data
                if ifname in breakout_dict:
                    speed = None
                    breakout_data = breakout_dict[ifname]
                    if breakout_data["channel-speed"] != None:
                        speed = yang_val_to_speed(breakout_data["channel-speed"])
                    interface_list.append(
                        [ifname, breakout_data["num-channels"], speed]
                    )
                else:
                    if "breakout" in intf:
                        breakout_data = intf["breakout"]
                        speed = None
                        if breakout_data["channel-speed"] != None:
                            speed = yang_val_to_speed(breakout_data["channel-speed"])
                        interface_list.append(
                            [ifname, breakout_data["num-channels"], speed]
                        )
                    else:
                        interface_list.append([ifname, None, None])

        is_updated = await self.k8s.update_usonic_config(interface_list)

        # Restart deployment if configmap update is successful
        if is_updated:
            await self.restart_usonic()

        return is_updated

    def get_running_data(self, xpath):
        self.sess.switch_datastore("running")
        return self.sess.get_data(xpath)

    def is_breakout_port(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
        self.sess.switch_datastore("operational")
        data = self.sess.get_data(xpath, no_subs=True)
        try:
            logger.debug(f"data: {data}")
            data = data["interfaces"]["interface"][ifname]["breakout"]
            if data.get("num-channels", 1) > 1 or "parent" in data:
                return True
        except KeyError:
            return False

        return False

    def get_configured_breakout_ports(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface"
        self.sess.switch_datastore("operational")
        data = self.sess.get_data(xpath, no_subs=True)
        logger.debug(f"get_configured_breakout_ports: {ifname}, {data}")
        ports = []
        for intf in data.get("interfaces", {}).get("interface", []):
            try:
                if intf["breakout"]["parent"] == ifname:
                    name = intf["name"]
                    d = self.get_running_data(f"{xpath}[name='{name}']")
                    logger.debug(f"get_configured_breakout_ports: {name}, {d}")
                    ports.append(intf["name"])
            except (sysrepo.errors.SysrepoNotFoundError, KeyError):
                pass

        logger.debug(f"get_configured_breakout_ports: ports: {ports}")

        return ports

    async def vlan_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")
            return

        for change in changes:
            logger.debug(f"change_cb: {change}")

            key, _hash, attr_dict = await self.parse_change_req(change.xpath)
            if "member" in attr_dict:
                member = attr_dict["member"]

            logger.debug(f"key: {key}, _hash: {_hash}, attr_dict: {attr_dict}")

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug("......change created......")
                if type(change.value) != type({}) and key != "name" and key != "ifname":
                    if key == "members@":
                        try:
                            mem = _decode(
                                self.sonic_db.get(self.sonic_db.CONFIG_DB, _hash, key)
                            )
                            mem_list = mem.split(",")
                            if change.value not in mem_list:
                                mem + "," + str(change.value)
                            self.set_config_db(event, _hash, key, mem)
                        except:
                            self.set_config_db(event, _hash, key, change.value)
                    else:
                        self.set_config_db(event, _hash, key, change.value)

            if isinstance(change, sysrepo.ChangeModified):
                logger.debug("......change modified......")
                raise sysrepo.SysrepoUnsupportedError("Modification is not supported")
            if isinstance(change, sysrepo.ChangeDeleted):
                logger.debug("......change deleted......")
                if key == "members@":
                    mem = _decode(
                        self.sonic_db.get(self.sonic_db.CONFIG_DB, _hash, key)
                    )
                    if mem != None:
                        mem = mem.split(",")
                        if member in mem:
                            mem.remove(member)
                        if len(mem) >= 1:
                            value = ",".join(mem)
                            self.set_config_db(event, _hash, key, value)

                elif _hash.find("VLAN|") == 0 and key == "":
                    if event == "done":
                        self.sonic_db.delete(self.sonic_db.CONFIG_DB, _hash)

                elif _hash.find("VLAN_MEMBER|") == 0 and key == "":
                    if event == "done":
                        self.sonic_db.delete(self.sonic_db.CONFIG_DB, _hash)

    async def intf_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")
            return

        valid_speeds = [40000, 100000]
        breakout_valid_speeds = []  # no speed change allowed for sub-interfaces

        for change in changes:
            logger.debug(f"change_cb: {change}")

            key, _hash, attr_dict = await self.parse_change_req(change.xpath)
            if "ifname" in attr_dict:
                ifname = attr_dict["ifname"]

            logger.debug(f"key: {key}, _hash: {_hash}, attr_dict: {attr_dict}")

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug("......change created......")
                if type(change.value) != type({}) and key != "name" and key != "ifname":
                    if key == "description" or key == "alias":
                        self.set_config_db(event, _hash, key, change.value)
                    elif key == "admin-status":
                        self.set_config_db(event, _hash, "admin_status", change.value)
                    elif key == "speed":

                        if event == "change":
                            ifname = attr_dict["ifname"]
                            if self.is_breakout_port(ifname):
                                valids = breakout_valid_speeds
                            else:
                                valids = valid_speeds

                            if change.value not in valids:
                                logger.debug(
                                    f"invalid speed: {change.value}, candidates: {valids}"
                                )
                                raise sysrepo.SysrepoInvalArgError("Invalid speed")

                        self.set_config_db(event, _hash, "speed", change.value)

                    elif key == "forwarding" or key == "enabled":
                        logger.debug(
                            "This key:{} should not be set in redis ".format(key)
                        )
                    elif key == "num-channels" or key == "channel-speed":
                        logger.debug(
                            "This key:{} should not be set in redis ".format(key)
                        )

                        # TODO use the parent leaf to detect if this is a sub-interface or not
                        # using "_1" is vulnerable to the interface nameing schema change
                        if "_1" not in ifname:
                            raise sysrepo.SysrepoInvalArgError(
                                "breakout cannot be configured on a sub-interface"
                            )

                        paired_key = (
                            "num-channels"
                            if key == "channel-speed"
                            else "channel-speed"
                        )
                        tmp_xpath = change.xpath.replace(key, paired_key)

                        try:
                            _data = self.get_running_data(tmp_xpath)
                        except:
                            logger.debug("Both Arguments are not present yet")
                            break

                        try:
                            if_list = _data["interfaces"]["interface"]
                            for intf in if_list:
                                paired_value = intf["breakout"][paired_key]
                        except KeyError:
                            logging.error(
                                f"Failed fetching {paired_key} from get_data for breakout"
                            )
                            break

                        # We will wait for both the parameters of breakout in yang to be
                        # configured on the parent interface.
                        #
                        # Once configuration is done, we will update the configmap and
                        # deployment in breakout_update_usonic() function.
                        # After the update, we will watch asynchronosly in watch_pods()
                        # for the `usonic` deployment to be UP.
                        #
                        # Once `usonic` deployment is UP, another asynchronous call breakout_callback()
                        # will do the following:
                        # 1. Delete all the sub-interfaces created in operational datastore (during
                        #    breakout delete operation)
                        # 2. Reconciliation will be run to populate Redis DB(from running datastore)
                        #    and coresponding data in operational datastore (during breakout config,
                        #    new sub-interfaces will be added in operational datastore in this step)

                        logger.info(
                            "Both Arguments are present for breakout {} {}".format(
                                change.value, paired_value
                            )
                        )
                        breakout_dict = {
                            ifname: {key: change.value, paired_key: paired_value}
                        }

                        if event == "done":
                            is_updated = await self.breakout_update_usonic(
                                breakout_dict
                            )
                            if is_updated:
                                asyncio.create_task(self.breakout_callback())

                    else:
                        self.set_config_db(event, _hash, key, change.value)

            if isinstance(change, sysrepo.ChangeModified):
                logger.debug("......change modified......")
                if key == "description" or key == "alias":
                    self.set_config_db(event, _hash, key, change.value)
                elif key == "admin-status":
                    self.set_config_db(event, _hash, "admin_status", change.value)
                elif key == "forwarding" or key == "enabled":
                    logger.debug("This key:{} should not be set in redis ".format(key))

                elif key == "speed":

                    if event == "change":
                        if self.is_breakout_port(ifname):
                            valids = breakout_valid_speeds
                        else:
                            valids = valid_speeds

                        if change.value not in valids:
                            logger.debug("****** Invalid speed value *********")
                            raise sysrepo.SysrepoInvalArgError("Invalid speed")

                    self.set_config_db(event, _hash, "speed", change.value)

                elif key == "num-channels" or key == "channel-speed":
                    logger.debug("This key:{} should not be set in redis ".format(key))
                    raise sysrepo.SysrepoInvalArgError(
                        "Breakout config modification not supported"
                    )
                else:
                    self.set_config_db(event, _hash, key, change.value)

            if isinstance(change, sysrepo.ChangeDeleted):
                logger.debug("......change deleted......")
                if key in ["channel-speed", "num-channels"]:
                    if event == "change":
                        if len(self.get_configured_breakout_ports(ifname)):
                            raise sysrepo.SysrepoInvalArgError(
                                "Breakout can't be removed due to the dependencies"
                            )
                        continue

                    assert event == "done"

                    # change.xpath is
                    # /goldstone-interfaces:interfaces/interface[name='xxx']/breakout/channel-speed
                    # or
                    # /goldstone-interfaces:interfaces/interface[name='xxx']/breakout/num-channels
                    #
                    # set xpath to /goldstone-interfaces:interfaces/interface[name='xxx']/breakout
                    xpath = "/".join(change.xpath.split("/")[:-1])
                    try:
                        data = self.get_running_data(xpath)
                    except sysrepo.errors.SysrepoNotFoundError:
                        ch = None
                        speed = None
                    else:
                        if_list = data["interfaces"]["interface"]
                        assert len(if_list) == 1
                        intf = list(if_list)[0]
                        config = intf.get("breakout", {})
                        ch = config.get("num-channels", None)
                        speed = config.get("channel-speed", None)

                    # if both channel and speed configuration are deleted
                    # remove the breakout config from uSONiC
                    if ch != None or speed != None:
                        logger.debug(
                            "breakout config still exists: ch: {ch}, speed: {speed}"
                        )
                        continue

                    breakout_dict = {
                        ifname: {"num-channels": None, "channel-speed": None}
                    }

                    is_updated = await self.breakout_update_usonic(breakout_dict)
                    if is_updated:
                        asyncio.create_task(self.breakout_callback())

                elif "PORT|" in _hash and key == "":
                    if event == "done":
                        # since sysrepo wipes out the pushed entry in oper ds
                        # when the corresponding entry in running ds is deleted,
                        # we need to repopulate the oper ds.
                        #
                        # this behavior might change in the future
                        # https://github.com/sysrepo/sysrepo/issues/1937#issuecomment-742851607
                        self.update_oper_db()

    def get_oper_data(self, req_xpath):
        def delta_counter_value(base, present):
            return str(int(present) - int(base))

        path_prefix = "/goldstone-interfaces:interfaces/interface[name='"

        if req_xpath.endswith("oper-status"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/oper-status", "")
            key = ifname.replace("Ethernet", "PORT_TABLE:Ethernet")

            data = _decode(self.sonic_db.get(self.sonic_db.APPL_DB, key, "oper_status"))

            return data

        elif req_xpath.endswith("in-octets"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-octets", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_OCTETS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_OCTETS"], data
            )

        elif req_xpath.endswith("in-unicast-pkts"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-unicast-pkts", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )

            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_UCAST_PKTS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_UCAST_PKTS"], data
            )

        elif req_xpath.endswith("in-broadcast-pkts"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-broadcast-pkts", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )

            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB,
                        key,
                        "SAI_PORT_STAT_IF_IN_BROADCAST_PKTS",
                    )
                )
            except:
                return 0
            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_BROADCAST_PKTS"], data
            )

        elif req_xpath.endswith("in-multicast-pkts"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-multicast-pkts", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB,
                        key,
                        "SAI_PORT_STAT_IF_IN_MULTICAST_PKTS",
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_MULTICAST_PKTS"], data
            )

        elif req_xpath.endswith("in-discards"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-discards", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_DISCARDS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_DISCARDS"], data
            )

        elif req_xpath.endswith("in-errors"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-errors", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_IN_ERRORS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_ERRORS"], data
            )

        elif req_xpath.endswith("in-unknown-protos"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/in-unknown-protos", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB,
                        key,
                        "SAI_PORT_STAT_IF_IN_UNKNOWN_PROTOS",
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_IN_UNKNOWN_PROTOS"], data
            )

        elif req_xpath.endswith("out-octets"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-octets", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_OCTETS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_OUT_OCTETS"], data
            )

        elif req_xpath.endswith("out-unicast-pkts"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-unicast-pkts", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB,
                        key,
                        "SAI_PORT_STAT_IF_OUT_UCAST_PKTS",
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_OUT_UCAST_PKTS"], data
            )

        elif req_xpath.endswith("out-broadcast-pkts"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-broadcast-pkts", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB,
                        key,
                        "SAI_PORT_STAT_IF_OUT_BROADCAST_PKTS",
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_OUT_BROADCAST_PKTS"], data
            )

        elif req_xpath.endswith("out-multicast-pkts"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-multicast-pkts", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB,
                        key,
                        "SAI_PORT_STAT_IF_OUT_MULTICAST_PKTS",
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_OUT_MULTICAST_PKTS"], data
            )

        elif req_xpath.endswith("out-discards"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-discards", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_DISCARDS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_OUT_DISCARDS"], data
            )

        elif req_xpath.endswith("out-errors"):

            req_xpath = req_xpath.replace(path_prefix, "")
            ifname = req_xpath.replace("']/statistics/out-errors", "")
            if_counter_data = self.counter_if_dict[ifname]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            try:
                key = "COUNTERS:" + key

                data = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, key, "SAI_PORT_STAT_IF_OUT_ERRORS"
                    )
                )
            except:
                return 0

            return delta_counter_value(
                if_counter_data["SAI_PORT_STAT_IF_OUT_ERRORS"], data
            )

    def interface_oper_cb(self, req_xpath):
        # Changing to operational datastore to fetch data
        # for the unconfigurable params in the xpath, data will
        # be fetched from Redis and complete data will be returned.

        # Use 'no_subs=True' parameter in oper_cb to fetch data from operational
        # datastore and to avoid locking of sysrepo db
        self.sess.switch_datastore("operational")
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

        if len(path_list) <= 3:
            r = self.sess.get_data(req_xpath, no_subs=True)
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
            r = self.sess.get_data(xpath_T, no_subs=True)
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

            r = self.sess.get_data(xpath_T, no_subs=True)
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
        if self.is_usonic_rebooting:
            logger.debug("usonic is rebooting. no handling done in oper-callback")
            return

        if req_xpath.find("/goldstone-interfaces:interfaces") == 0:
            return self.interface_oper_cb(req_xpath)

    def cache_counters(self):
        self.counter_if_dict = {}
        hash_keys = self.sonic_db.keys(
            self.sonic_db.CONFIG_DB, pattern="PORT|Ethernet*"
        )
        if hash_keys != None:
            hash_keys = map(_decode, hash_keys)

            for _hash in hash_keys:
                ifname = _hash.split("|")[1]

                key = _decode(
                    self.sonic_db.get(
                        self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname
                    )
                )
                tmp_counter_dict = {}
                counter_key = COUNTER_TABLE_PREFIX + key
                for counter_name in self.counter_dict.keys():
                    counter_data = _decode(
                        self.sonic_db.get(
                            self.sonic_db.COUNTERS_DB, counter_key, counter_name
                        )
                    )
                    tmp_counter_dict[counter_name] = counter_data
                self.counter_if_dict[ifname] = tmp_counter_dict

    def enable_counters(self):
        # This is similar to "counterpoll port enable"
        value = {"FLEX_COUNTER_STATUS": "enable"}
        self.sonic_configdb.mod_entry("FLEX_COUNTER_TABLE", "PORT", value)

    def reconcile(self):
        self.sess.switch_datastore("running")
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
                            self.sonic_db.CONFIG_DB,
                            "PORT|" + name,
                            "description",
                            str(intf[key]),
                        )
                    elif key == "alias":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB,
                            "PORT|" + name,
                            "alias",
                            str(intf[key]),
                        )
                    elif key == "admin-status":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB,
                            "PORT|" + name,
                            "admin_status",
                            str(intf[key]),
                        )
                    elif key == "if-index":
                        pass
                    elif key == "breakout":
                        # Breakout configs are handled above
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
                vlan_member_list = vlan_data["vlan"]["VLAN_MEMBER"]["VLAN_MEMBER_LIST"]

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
            self.sonic_db.CONFIG_DB, pattern="PORT|Ethernet*"
        )
        if hash_keys != None:
            hash_keys = map(_decode, hash_keys)

            for _hash in hash_keys:
                ifname = _hash.split("|")[1]
                intf_data = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, _hash)
                intf_keys = [v.decode("ascii") for v in list(intf_data.keys())]

                if "admin_status" not in intf_keys:
                    self.sonic_db.set(
                        self.sonic_db.CONFIG_DB,
                        "PORT|" + ifname,
                        "admin_status",
                        "down",
                    )

    def update_oper_db(self):
        logger.debug("updating operational db")
        self.sess.switch_datastore("operational")

        # clear the intf operational ds and build it from scratch
        self.sess.delete_item("/goldstone-interfaces:interfaces")

        hash_keys = self.sonic_db.keys(
            self.sonic_db.APPL_DB, pattern="PORT_TABLE:Ethernet*"
        )
        if hash_keys != None:
            hash_keys = map(_decode, hash_keys)

            for _hash in hash_keys:
                ifname = _hash.split(":")[1]
                xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                intf_data = self.sonic_db.get_all(self.sonic_db.APPL_DB, _hash)
                logger.debug(f"key: {_hash}, value: {intf_data}")
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
            self.sonic_db.CONFIG_DB, pattern="PORT|Ethernet*"
        )
        if hash_keys != None:
            hash_keys = map(_decode, hash_keys)
            breakout_parent_dict = {}

            for _hash in hash_keys:
                ifname = _hash.split("|")[1]
                xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
                xpath_subif_breakout = f"{xpath}/breakout"

                # TODO use the parent leaf to detect if this is a sub-interface or not
                # using "_1" is vulnerable to the interface nameing schema change
                if not ifname.endswith("_1") and ifname.find("_") != -1:
                    _ifname = ifname.split("_")
                    tmp_ifname = _ifname[0] + "_1"
                    if tmp_ifname in breakout_parent_dict.keys():
                        breakout_parent_dict[tmp_ifname] = (
                            breakout_parent_dict[tmp_ifname] + 1
                        )
                    else:
                        breakout_parent_dict[tmp_ifname] = 1

                    logger.debug(
                        f"ifname: {ifname}, breakout_parent_dict: {breakout_parent_dict}"
                    )

                    self.sess.set_item(f"{xpath_subif_breakout}/parent", tmp_ifname)

                intf_data = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, _hash)
                for key in intf_data:
                    value = _decode(intf_data[key])
                    key = _decode(key)
                    if key == "mtu":
                        self.sess.set_item(f"{xpath}/goldstone-ip:ipv4/{key}", value)
                    elif (
                        key != "index"
                        and key != "phys-address"
                        and key != "admin_status"
                        and key != "alias"
                        and key != "description"
                        and key != "breakout"
                    ):
                        self.sess.set_item(f"{xpath}/{key}", value)

            for key in breakout_parent_dict:
                xpath_parent_breakout = (
                    f"/goldstone-interfaces:interfaces/interface[name='{key}']/breakout"
                )
                speed = self.sonic_db.get(
                    self.sonic_db.CONFIG_DB, "PORT|" + key, "speed"
                )
                logger.debug(f"key: {key}, speed: {speed}")
                if speed != None:
                    self.sess.set_item(
                        f"{xpath_parent_breakout}/num-channels",
                        breakout_parent_dict[key] + 1,
                    )
                    self.sess.set_item(
                        f"{xpath_parent_breakout}/channel-speed",
                        speed_to_yang_val(speed),
                    )
                else:
                    logger.warn(
                        f"Breakout interface:{key} doesnt has speed attribute in Redis"
                    )

        hash_keys = self.sonic_db.keys(self.sonic_db.CONFIG_DB, pattern="VLAN|Vlan*")

        # clear the VLAN operational ds and build it from scratch
        self.sess.delete_item("/goldstone-vlan:vlan")

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
                member_data = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, _hash)
                for key in member_data:
                    value = _decode(member_data[key])
                    key = _decode(key)
                    self.sess.set_item(f"{xpath}/{key}", value)

        try:
            self.sess.apply_changes(timeout_ms=5000, wait=True)
        except sysrepo.SysrepoTimeOutError as e:
            logger.warn(f"update oper ds timeout: {e}")
            self.sess.apply_changes(timeout_ms=5000, wait=True)

    async def start(self):

        logger.debug(
            "****************************inside start******************************"
        )
        self.sonic_db.connect(self.sonic_db.CONFIG_DB)
        self.sonic_db.connect(self.sonic_db.APPL_DB)
        self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

        logger.debug(
            "****************************reconciliation******************************"
        )

        self.sess.switch_datastore("running")

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):
                # Calling breakout_update_usonic() is mandatory before initial reconcile
                # process, as gssouth-sonic will replace the interface names properly during
                # init if they have been modified.
                breakout_dict = {}
                is_updated = await self.breakout_update_usonic(breakout_dict)
                if is_updated:
                    await self.watch_pods()
                else:
                    self.cache_counters()

                self.reconcile()
                self.update_oper_db()

                self.sess.switch_datastore("running")

                self.sess.subscribe_module_change(
                    "goldstone-interfaces",
                    None,
                    self.intf_change_cb,
                    asyncio_register=True,
                )
                self.sess.subscribe_module_change(
                    "goldstone-vlan", None, self.vlan_change_cb, asyncio_register=True
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

        return []


def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server()

        try:
            tasks = await server.start()
            tasks.append(stop_event.wait())
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
        k8s = logging.getLogger("kubernetes_asyncio.client.rest")
        k8s.setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
