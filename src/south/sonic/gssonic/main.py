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
import redis
import os
from .k8s_api import incluster_apis
from aiohttp import web
import queue

logger = logging.getLogger(__name__)

COUNTER_PORT_MAP = "COUNTERS_PORT_NAME_MAP"
COUNTER_TABLE_PREFIX = "COUNTERS:"
REDIS_SERVICE_HOST = os.getenv("REDIS_SERVICE_HOST")
REDIS_SERVICE_PORT = os.getenv("REDIS_SERVICE_PORT")

SINGLE_LANE_INTERFACE_TYPES = ["CR", "LR", "SR", "KR"]
DOUBLE_LANE_INTERFACE_TYPES = ["CR2", "LR2", "SR2", "KR2"]
QUAD_LANE_INTERFACE_TYPES = ["CR4", "LR4", "SR4", "KR4"]
DEFAULT_INTERFACE_TYPE = "KR"


def _decode(string):
    if hasattr(string, "decode"):
        return string.decode("utf-8")
    return string


# SPEED_10G => 10000
# goldstone-interfaces:SPEED_100G => 100000
def speed_yang_to_redis(yang_val):
    if not yang_val:
        return None
    yang_val = yang_val.split(":")[-1]
    yang_val = yang_val.split("_")[-1]
    return int(yang_val.split("G")[0]) * 1000


def speed_redis_to_yang(speed):
    # Considering only speeds supported in CLI
    speed = _decode(speed)
    if speed == "25000":
        return "SPEED_25G"
    elif speed == "20000":
        return "SPEED_20G"
    elif speed == "50000":
        return "SPEED_50G"
    elif speed == "100000":
        return "SPEED_100G"
    elif speed == "40000":
        return "SPEED_40G"
    elif speed == "10000":
        return "SPEED_10G"
    elif speed == "1000":
        return "SPEED_1G"
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
        self.task_queue = queue.Queue()
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
        self.notif_if = {}
        self.mtu_default = self.get_default_from_yang("mtu")
        self.speed_default = "100000"

        routes = web.RouteTableDef()

        @routes.get("/healthz")
        async def probe(request):
            return web.Response()

        app = web.Application()
        app.add_routes(routes)

        self.runner = web.AppRunner(app)

    async def stop(self):
        await self.runner.cleanup()
        self.redis_thread.stop()
        self.sess.stop()
        self.conn.disconnect()

    def get_default_from_yang(self, key):
        ctx = self.sess.get_ly_ctx()
        xpath = "/goldstone-interfaces:interfaces"
        xpath += "/goldstone-interfaces:interface"
        if key == "mtu":
            xpath += "/goldstone-ip:ipv4"
            xpath += "/goldstone-ip:mtu"
        for node in ctx.find_path(xpath):
            return node.default()

    def get_config_db_keys(self, pattern):
        keys = self.sonic_db.keys(self.sonic_db.CONFIG_DB, pattern=pattern)
        return map(_decode, keys) if keys else []

    def set_config_db(self, event, _hash, key, value):
        if event != "done":
            return
        if key == "speed":
            value = speed_yang_to_redis(value)
        if type(value) == str:
            value = value.lower()
        key = key.replace("-", "_")
        return self.sonic_db.set(self.sonic_db.CONFIG_DB, _hash, key, str(value))

    def restart_usonic(self):
        self.is_usonic_rebooting = True
        self.k8s.restart_usonic()

    async def watch_pods(self):
        await self.k8s.watch_pods()

        logger.debug("uSONiC deployment ready")

        # Enable counters in SONiC
        self.enable_counters()
        # Caching base values of counters
        self.cache_counters()

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

    def parse_vlan_change_req(self, xpath):
        xpath = xpath.split("/")
        _hash = ""
        key = ""
        member = ""
        attr_dict = {"xpath": xpath}
        for i in range(len(xpath)):
            node = xpath[i]
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

    def parse_intf_change_req(self, xpath):
        xpath = list(libyang.xpath_split(xpath))
        _hash = ""
        key = ""
        member = ""
        attr_dict = {"xpath": xpath}
        assert xpath[0][0] == "goldstone-interfaces"
        assert xpath[0][1] == "interfaces"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        ifname = xpath[1][2][0][1]

        intf_names = self.sonic_db.keys(
            self.sonic_db.CONFIG_DB, pattern="PORT|" + ifname
        )
        if intf_names == None:
            logger.debug("*************** Invalid Interface name ****************")
            raise sysrepo.SysrepoInvalArgError("Invalid Interface name")

        _hash = _hash + "PORT|" + ifname
        attr_dict.update({"ifname": ifname})

        if len(xpath) >= 4:
            if xpath[2][1] == "config":
                key = xpath[-1][1]
            elif xpath[2][1] == "ipv4":
                key = xpath[3][1]
            elif xpath[2][1] == "auto-negotiate":
                key = "auto-negotiate"

        return key, _hash, attr_dict

    async def breakout_callback(self):
        self.sess.switch_datastore("running")

        await self.wait_for_sr_unlock()

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):

                await self.watch_pods()

                await self.reconcile()

                self.is_usonic_rebooting = False

                self.sess.switch_datastore("running")

    def breakout_update_usonic(self):

        logger.debug("Starting to Update usonic's configMap and deployment")

        intfs = {}

        xpath = "/goldstone-interfaces:interfaces/interface"
        data = self.get_running_data(xpath, [])

        for i in data:
            name = i["name"]
            b = i.get("config", {}).get("breakout", {})
            numch = b.get("num-channels", None)
            speed = speed_yang_to_redis(b.get("channel-speed", None))
            intfs[name] = (numch, speed)

        is_updated = self.k8s.update_usonic_config(intfs)

        # Restart deployment if configmap update is successful
        if is_updated:
            self.restart_usonic()

        return is_updated

    def get_sr_data(self, xpath, datastore, default=None):
        self.sess.switch_datastore(datastore)
        try:
            v = self.sess.get_data(xpath)
        except sysrepo.errors.SysrepoNotFoundError:
            logger.debug(
                f"xpath: {xpath}, ds: {datastore}, not found. returning {default}"
            )
            return default
        v = libyang.xpath_get(v, xpath, default)
        logger.debug(f"xpath: {xpath}, ds: {datastore}, value: {v}")
        return v

    def get_running_data(self, xpath, default=None):
        return self.get_sr_data(xpath, "running", default)

    def get_operational_data(self, xpath, default=None):
        return self.get_sr_data(xpath, "operational", default)

    def get_breakout_detail(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/state/breakout"
        data = self.get_operational_data(xpath)
        if not data:
            return None

        logger.debug(f"data: {data}")
        if data.get("num-channels", 1) > 1:
            return {
                "num-channels": data["num-channels"],
                "channel-speed": data["channel-speed"],
            }

        if "parent" in data:
            return self.get_breakout_detail(data["parent"])

        return None

    def get_redis_all(self, db, key):
        db = getattr(self.sonic_db, db)
        data = self.sonic_db.get_all(db, key)
        return {_decode(k): _decode(v) for k, v in data.items()}

    def validate_interface_type(self, ifname, iftype):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
        err = sysrepo.SysrepoInvalArgError("Unsupported interface type")

        try:
            self.get_running_data(xpath)
            detail = self.get_breakout_detail(ifname)
            if not detail:
                raise KeyError

            numch = int(detail["num-channels"])
        except (KeyError, sysrepo.SysrepoNotFoundError):
            numch = 1

        if numch == 4:
            if detail["channel-speed"].endswith("10GB") and iftype == "SR":
                raise err
            elif iftype not in SINGLE_LANE_INTERFACE_TYPES:
                raise err
        elif numch == 2:
            if iftype not in DOUBLE_LANE_INTERFACE_TYPES:
                raise err
        elif numch == 1:
            if iftype not in QUAD_LANE_INTERFACE_TYPES:
                raise err
        else:
            raise err

    def get_ufd_configured_ports(self, ifname):
        ufd_list = self.get_ufd()
        breakout_ports = []
        for ufd_data in ufd_list:
            try:
                uplink_port = list(ufd_data["config"]["uplink"])
                if uplink_port[0].find(ifname[:-1]) == 0:
                    breakout_ports.append(uplink_port[0])
            except:
                pass

            try:
                downlink_ports = ufd_data["config"]["downlink"]
                for port in downlink_ports:
                    if port.find(ifname[:-1]) == 0:
                        breakout_ports.append(port)
            except:
                pass

        if len(breakout_ports) > 0:
            return breakout_ports

        return []

    def get_configured_breakout_ports(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface"
        self.sess.switch_datastore("operational")
        data = self.get_operational_data(xpath, default=[])
        ports = []
        for intf in data:
            if intf["state"].get("breakout", {}).get("parent", None) == ifname:
                name = intf["name"]
                d = self.get_running_data(f"{xpath}[name='{name}']/config")
                if d and len(d) > 1:
                    ports.append(intf["name"])

        logger.debug(f"parent: {ifname}, breakouts: {ports}")
        return ports

    def vlan_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn(f"unsupported event: {event}")
            return

        for change in changes:

            key, _hash, attr_dict = self.parse_vlan_change_req(change.xpath)
            if "member" in attr_dict:
                member = attr_dict["member"]

            logger.debug(f"key: {key}, _hash: {_hash}, attr_dict: {attr_dict}")

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug(f"change created: {change}")
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
                logger.debug(f"change modified: {change}")
                raise sysrepo.SysrepoUnsupportedError("Modification is not supported")
            if isinstance(change, sysrepo.ChangeDeleted):
                logger.debug(f"change deleted: {change}")
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

    def intf_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")
            return

        if self.is_usonic_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

        valid_speeds = [40000, 100000]
        breakout_valid_speeds = []  # no speed change allowed for sub-interfaces

        update_usonic = False
        intfs_need_adv_speed_config = (
            set()
        )  # put ifname of the interfaces that need adv speed config

        for change in changes:
            logger.debug(f"change_cb: {change}")

            key, _hash, attr_dict = self.parse_intf_change_req(change.xpath)
            if "ifname" in attr_dict:
                ifname = attr_dict["ifname"]

            logger.debug(f"key: {key}, _hash: {_hash}, attr_dict: {attr_dict}")

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug("......change created......")
                if key in ["admin-status", "fec", "description", "alias", "mtu"]:
                    self.set_config_db(event, _hash, key, change.value)
                elif key == "interface-type":
                    iftype = change.value
                    if event == "change":
                        self.validate_interface_type(ifname, iftype)
                    elif event == "done":
                        self.k8s.run_bcmcmd_port(ifname, "if=" + iftype)
                elif key == "auto-negotiate":
                    if event == "change":
                        if attr_dict["xpath"][-1][1] == "advertised-speeds":
                            value = speed_yang_to_redis(change.value)
                            if self.get_breakout_detail(ifname):
                                valids = breakout_valid_speeds
                            else:
                                valids = valid_speeds
                            if value not in valids:
                                valids = [speed_redis_to_yang(v) for v in valids]
                                raise sysrepo.SysrepoInvalArgError(
                                    f"Invalid speed: {change.value}, candidates: {valids}"
                                )

                    if event == "done":
                        if attr_dict["xpath"][-1][1] == "enabled":
                            self.k8s.run_bcmcmd_port(
                                ifname, "an=" + ("yes" if change.value else "no")
                            )
                        elif attr_dict["xpath"][-1][1] == "advertised-speeds":
                            intfs_need_adv_speed_config.add(ifname)

                elif key == "speed":

                    if event == "change":
                        # 'goldstone-interfaces:SPEED_100GB' to 1000000
                        value = speed_yang_to_redis(change.value)
                        ifname = attr_dict["ifname"]
                        if self.get_breakout_detail(ifname):
                            valids = breakout_valid_speeds
                        else:
                            valids = valid_speeds
                        if value not in valids:
                            raise sysrepo.SysrepoInvalArgError(
                                f"Invalid speed: {change.value}, candidates: {valids}"
                            )
                    elif event == "done":
                        self.set_config_db(event, _hash, key, change.value)
                        self.k8s.update_bcm_portmap()

                elif key == "num-channels" or key == "channel-speed":
                    # using "_1" is vulnerable to the interface nameing schema change
                    if "_1" not in ifname:
                        raise sysrepo.SysrepoInvalArgError(
                            "breakout cannot be configured on a sub-interface"
                        )

                    ufd_list = self.get_ufd()
                    if self.is_ufd_port(ifname, ufd_list):
                        raise sysrepo.SysrepoInvalArgError(
                            "Breakout cannot be configured on the interface that is part of UFD"
                        )

                    paired_key = (
                        "num-channels" if key == "channel-speed" else "channel-speed"
                    )
                    paired_xpath = change.xpath.replace(key, paired_key)

                    try:
                        paired_value = self.get_running_data(paired_xpath)
                    except:
                        logger.debug("Both Arguments are not present yet")
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
                        update_usonic = True
                else:
                    logger.warn(f"unhandled change: {change}")

            if isinstance(change, sysrepo.ChangeModified):
                logger.debug("......change modified......")
                if key == "name":
                    raise sysrepo.SysrepoInvalArgError("Can't change interface name")
                elif key in ["admin-status", "fec", "description", "alias", "mtu"]:
                    self.set_config_db(event, _hash, key, change.value)
                elif key == "interface-type":
                    iftype = change.value
                    if event == "change":
                        self.validate_interface_type(ifname, iftype)
                    elif event == "done":
                        self.k8s.run_bcmcmd_port(ifname, "if=" + iftype)
                elif key == "auto-negotiate":
                    if event == "change":
                        if attr_dict["xpath"][-1][1] == "advertised-speeds":
                            value = speed_yang_to_redis(change.value)
                            if self.get_breakout_detail(ifname):
                                valids = breakout_valid_speeds
                            else:
                                valids = valid_speeds
                            if value not in valids:
                                raise sysrepo.SysrepoInvalArgError(
                                    f"Invalid speed: {change.value}, candidates: {valids}"
                                )

                    if event == "done":
                        if attr_dict["xpath"][-1][1] == "enabled":
                            self.k8s.run_bcmcmd_port(
                                ifname, "an=" + ("yes" if change.value else "no")
                            )
                        elif attr_dict["xpath"][-1][1] == "advertised-speeds":
                            intfs_need_adv_speed_config.add(ifname)

                elif key == "speed":

                    if event == "change":
                        if self.get_breakout_detail(ifname):
                            valids = breakout_valid_speeds
                        else:
                            valids = valid_speeds

                        # 'goldstone-interfaces:SPEED_100GB' to 1000000
                        value = speed_yang_to_redis(change.value)

                        if value not in valids:
                            logger.debug("****** Invalid speed value *********")
                            raise sysrepo.SysrepoInvalArgError(
                                f"Invalid speed: {change.value}, candidates: {valids}"
                            )
                    elif event == "done":
                        self.set_config_db(event, _hash, key, change.value)
                        self.k8s.update_bcm_portmap()

                elif key == "num-channels" or key == "channel-speed":
                    raise sysrepo.SysrepoInvalArgError(
                        "Breakout config modification not supported"
                    )
                else:
                    logger.warn(f"unhandled change: {change}")

            if isinstance(change, sysrepo.ChangeDeleted):
                logger.debug("......change deleted......")
                if key in ["channel-speed", "num-channels"]:

                    if event == "change":
                        breakouts = self.get_configured_breakout_ports(ifname)
                        # check if these breakouts are going to be deleted in this change
                        for breakout in breakouts:
                            xpath = f"/goldstone-interfaces:interfaces/interface[name='{breakout}']"
                            for c in changes:
                                logger.debug(f"{c}, {xpath}")
                                if (
                                    isinstance(c, sysrepo.ChangeDeleted)
                                    and c.xpath == xpath
                                ):
                                    break
                            else:
                                raise sysrepo.SysrepoInvalArgError(
                                    "Breakout can't be removed due to the dependencies"
                                )

                        if len(self.get_ufd_configured_ports(ifname)):
                            raise sysrepo.SysrepoInvalArgError(
                                "Breakout can't be removed due to the dependencies"
                            )
                        continue

                    assert event == "done"

                    # change.xpath is
                    # /goldstone-interfaces:interfaces/interface[name='xxx']/config/breakout/channel-speed
                    # or
                    # /goldstone-interfaces:interfaces/interface[name='xxx']/config/breakout/num-channels
                    #
                    # set xpath to /goldstone-interfaces:interfaces/interface[name='xxx']/config/breakout
                    xpath = "/".join(change.xpath.split("/")[:-1])
                    v = self.get_running_data(xpath)
                    if v:
                        ch = v.get("num-channels", None)
                        speed = v.get("channel-speed", None)
                    else:
                        ch = speed = None

                    # if both channel and speed configuration are deleted
                    # remove the breakout config from uSONiC
                    if ch != None or speed != None:
                        logger.debug(
                            f"breakout config still exists: ch: {ch}, speed: {speed}"
                        )
                        continue

                    update_usonic = True

                elif key in ["mtu", "speed", "fec", "admin-status"]:

                    if event == "done":
                        if key == "speed":
                            # TODO remove hardcoded value
                            value = "100G"
                        elif key in ["fec", "admin-status", "mtu"]:
                            value = self.get_default_from_yang(key).lower()

                        logger.debug(f"adding default value {value} of {key} to redis")
                        self.set_config_db("done", "PORT|" + ifname, key, value)

                        if key == "speed":
                            self.k8s.update_bcm_portmap()

                elif key == "interface-type":
                    if event == "done":
                        try:
                            breakout_details = self.get_breakout_detail(ifname)
                            logger.debug(f"Breakout Details :: {breakout_details}")
                            if not breakout_details:
                                raise KeyError
                            if int(breakout_details["num-channels"]) == 4:
                                self.k8s.run_bcmcmd_port(
                                    ifname, "if=" + DEFAULT_INTERFACE_TYPE
                                )
                            elif int(breakout_details["num-channels"]) == 2:
                                self.k8s.run_bcmcmd_port(
                                    ifname, "if=" + DEFAULT_INTERFACE_TYPE + "2"
                                )
                            else:
                                raise sysrepo.SysrepoInvalArgError(
                                    "Unsupported interface type"
                                )
                        except (sysrepo.errors.SysrepoNotFoundError, KeyError):
                            self.k8s.run_bcmcmd_port(
                                ifname, "if=" + DEFAULT_INTERFACE_TYPE + "4"
                            )
                elif key == "auto-negotiate":
                    if event == "done":
                        if attr_dict["xpath"][-1][1] == "enabled":
                            self.k8s.run_bcmcmd_port(ifname, "an=no")
                        elif attr_dict["xpath"][-1][1] == "advertised-speeds":
                            intfs_need_adv_speed_config.add(ifname)
                else:
                    logger.warn(f"unhandled change: {change}")

        for ifname in intfs_need_adv_speed_config:
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/auto-negotiate/config/advertised-speeds"
            config = self.get_running_data(xpath)
            if config:
                speeds = ",".join(v.replace("SPEED_", "").lower() for v in config)
                logger.debug(f"speeds: {speeds}")
            else:
                speeds = ""
            self.k8s.run_bcmcmd_port(ifname, f"adv={speeds}")

        if update_usonic:
            logger.info("creating breakout task")
            updated = self.breakout_update_usonic()
            if updated:
                self.task_queue.put(self.breakout_callback())

    def get_counter(self, ifname, counter):
        if ifname not in self.counter_if_dict:
            return 0
        base = self.counter_if_dict[ifname].get(counter, 0)
        key = _decode(
            self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
        )
        try:
            key = "COUNTERS:" + key
            present = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, key, counter)
            )
        except:
            return 0
        if base and present:
            return int(present) - int(base)
        return 0

    def get_interface_state_data(self, xpath):
        def delta_counter_value(base, present):
            if base and present:
                return int(present) - int(base)
            else:
                return 0

        xpath = list(libyang.xpath_split(xpath))

        assert xpath[0][0] == "goldstone-interfaces"
        assert xpath[0][1] == "interfaces"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        ifname = xpath[1][2][0][1]

        leaf = xpath[-1][1]

        if leaf == "oper-status":
            return _decode(
                self.sonic_db.get(
                    self.sonic_db.APPL_DB, f"PORT_TABLE:{ifname}", "oper_status"
                )
            )
        elif leaf == "in-octets":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_OCTETS")
        elif leaf == "in-unicast-pkts":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_UCAST_PKTS")
        elif leaf == "in-broadcast-pkts":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_BROADCAST_PKTS")
        elif leaf == "in-multicast-pkts":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_MULTICAST_PKTS")
        elif leaf == "in-discards":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_DISCARDS")
        elif leaf == "in-errors":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_ERRORS")
        elif leaf == "in-unknown-protos":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_IN_UNKNOWN_PROTOS")
        elif leaf == "out-octets":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_OUT_OCTETS")
        elif leaf == "out-unicast-pkts":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_OUT_UCAST_PKTS")
        elif leaf == "out-broadcast-pkts":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_OUT_BROADCAST_PKTS")
        elif leaf == "out-multicast-pkts":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_OUT_MULTICAST_PKTS")
        elif leaf == "out-discards":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_OUT_DISCARDS")
        elif leaf == "out-errors":
            return self.get_counter(ifname, "SAI_PORT_STAT_IF_OUT_ERRORS")

    def is_downlink_port(self, ifname):
        ufd_list = self.get_ufd()
        for data in ufd_list:
            try:
                if ifname in data["config"]["downlink"]:
                    return True, list(data["config"]["uplink"])
            except:
                pass

        return False, None

    def interface_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        if self.is_usonic_rebooting:
            # FIXME sysrepo bug. oper cb can't raise exception
            # see https://github.com/sysrepo/sysrepo/issues/2524
            # or https://github.com/sysrepo/sysrepo/issues/2448
            # raise sysrepo.SysrepoCallbackFailedError("uSONiC is rebooting")
            return {}

        # Changing to operational datastore to fetch data
        # for the unconfigurable params in the xpath, data will
        # be fetched from Redis and complete data will be returned.
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

        req_xpath = list(libyang.xpath_split(req_xpath))
        if (
            len(req_xpath) == 3
            and req_xpath[1][1] == "interface"
            and req_xpath[2][1] == "name"
        ):
            interfaces = [
                {"name": key.split("|")[1]}
                for key in self.get_config_db_keys("PORT|Ethernet*")
            ]
            return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

        interfaces = {}
        parent_dict = {}
        for key in self.get_config_db_keys("PORT|Ethernet*"):
            name = key.split("|")[1]
            config = self.get_redis_all("CONFIG_DB", key)
            logger.debug(f"config db entry: key: {key}, value: {config}")

            interface = {
                "name": name,
                "config": {"name": name},
                "state": {"name": name},
            }

            # TODO use the parent leaf to detect if this is a sub-interface or not
            # using "_1" is vulnerable to the interface nameing schema change
            if not name.endswith("_1") and name.find("_") != -1:
                _name = name.split("_")
                parent = _name[0] + "_1"
                if parent in parent_dict:
                    parent_dict[parent] += 1
                else:
                    parent_dict[parent] = 1

                logger.debug(f"parent: {parent}, parent_dict: {parent_dict}")
                interface["state"]["breakout"] = {"parent": parent}

            interfaces[name] = interface

        for key, value in parent_dict.items():
            v = self.get_redis_all("APPL_DB", f"PORT_TABLE:{key}")

            if "speed" in v:
                speed = speed_redis_to_yang(v["speed"])
                logger.debug(f"key: {key}, speed: {speed}")
                interfaces[key]["state"] = {
                    "breakout": {"num-channels": value + 1, "channel-speed": speed}
                }
            else:
                logger.warn(
                    f"Breakout interface:{key} doesnt has speed attribute in Redis"
                )

        interfaces = list(interfaces.values())

        prefix = "/goldstone-interfaces:interfaces"

        bcminfo = self.k8s.bcm_ports_info(list(i["name"] for i in interfaces))

        for intf in interfaces:
            ifname = intf["name"]

            xpath = f"{prefix}/interface[name='{ifname}']"
            intf["state"]["oper-status"] = self.get_oper_status(ifname)

            config = self.get_redis_all("APPL_DB", f"PORT_TABLE:{ifname}")
            for key, value in config.items():
                if key in ["alias", "lanes"]:
                    intf["state"][key] = value
                elif key in ["speed"]:
                    intf["state"][key] = speed_redis_to_yang(value)
                elif key in ["mtu"]:
                    intf["ipv4"] = {key: value}
                elif key in ["admin_status", "fec"]:
                    intf["state"][key.replace("_", "-")] = value.upper()

            xpath = f"{xpath}/counters"
            intf["state"]["counters"] = {}
            for sl in statistic_leaves:
                sl_value = self.get_interface_state_data(xpath + "/" + sl)
                if sl_value != None:
                    intf["state"]["counters"][sl] = sl_value

            info = bcminfo.get(ifname, {})
            logger.debug(f"bcminfo: {info}")

            iftype = info.get("iftype")
            if iftype:
                intf["state"]["interface-type"] = iftype

            auto_nego = info.get("auto-nego")
            if auto_nego:
                intf["auto-negotiate"] = {"state": {"enabled": True}}
                v = auto_nego.get("local", {}).get("fd")
                if v:
                    intf["auto-negotiate"]["state"]["advertised-speeds"] = [
                        f"SPEED_{e[:-1]}" for e in v
                    ]
            else:
                intf["auto-negotiate"] = {"state": {"enabled": False}}

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

    def portchannel_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        if self.is_usonic_rebooting:
            logger.debug("usonic is rebooting. no handling done in oper-callback")
            return

        self.sess.switch_datastore("running")
        r = self.sess.get_data(req_xpath)
        if r == {}:
            return r

        keys = self.sonic_db.keys(
            self.sonic_db.APPL_DB, pattern="LAG_TABLE:PortChannel*"
        )
        keys = keys if keys else []
        oper_dict = {}

        for key in keys:
            _hash = _decode(key)
            pc_id = _hash.split(":")[1]
            oper_status = _decode(
                self.sonic_db.get(self.sonic_db.APPL_DB, key, "oper_status")
            )
            if oper_status != None:
                oper_dict[pc_id] = oper_status

        for data in r["portchannel"]["portchannel-group"]:
            if oper_dict[data["portchannel-id"]] != None:
                data["config"]["oper-status"] = oper_dict[data["portchannel-id"]]

        return r

    def cache_counters(self):
        self.counter_if_dict = {}
        for key in self.get_config_db_keys("PORT|Ethernet*"):
            ifname = key.split("|")[1]

            key = _decode(
                self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
            )
            if not key:
                continue
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

    def clear_counters(self, xpath, input_params, event, priv):
        logger.debug(
            f"clear_counters: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        self.cache_counters()

    async def reconcile(self):
        self.sess.switch_datastore("running")
        intf_list = self.get_running_data(
            "/goldstone-interfaces:interfaces/interface", []
        )
        for intf in intf_list:
            config = intf.pop("config", {})
            intf.update(config)
            name = intf.pop("name")
            ipv4 = intf.pop("ipv4", {})
            intf.update(ipv4)

            logger.debug(f"interface config: {intf}")

            for key in intf:
                _hash = "PORT|" + name
                if key == "auto-negotiate":
                    self.k8s.run_bcmcmd_port(
                        name, "an=" + ("yes" if intf[key] else "no")
                    )
                elif key == "interface-type":
                    self.k8s.run_bcmcmd_port(name, "if=" + intf[key])
                elif key in [
                    "admin-status",
                    "fec",
                    "description",
                    "alias",
                    "mtu",
                    "speed",
                ]:
                    self.set_config_db("done", _hash, key, intf[key])
                elif key in ["if-index", "breakout"]:
                    pass
                else:
                    logger.warn(f"unhandled configuration: {key}, {intf[key]}")

        vlan_data = self.sess.get_data("/goldstone-vlan:vlan")
        if "vlan" in vlan_data:
            logger.debug(f"vlan config: {vlan_data}")
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

        portchannel_data = self.sess.get_data("/goldstone-portchannel:portchannel")
        if "portchannel" in portchannel_data:
            if "portchannel-group" in portchannel_data["portchannel"]:
                for port_channel in portchannel_data["portchannel"][
                    "portchannel-group"
                ]:
                    key = port_channel["portchannel-id"]
                    try:
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB,
                            "PORTCHANNEL|" + key,
                            "admin_status",
                            port_channel["config"]["admin-status"],
                        )
                    except KeyError:
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB,
                            "PORTCHANNEL|" + key,
                            "admin_status",
                            "up",
                        )
                    try:
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB,
                            "PORTCHANNEL|" + key,
                            "mtu",
                            port_channel["config"]["goldstone-ip:ipv4"]["mtu"],
                        )
                    except KeyError:
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB,
                            "PORTCHANNEL|" + key,
                            "mtu",
                            self.mtu_default,
                        )
                    try:
                        for intf in port_channel["config"]["interface"]:
                            self.sonic_db.set(
                                self.sonic_db.CONFIG_DB,
                                "PORTCHANNEL_MEMBER|" + key + "|" + intf,
                                "NULL",
                                "NULL",
                            )
                    except KeyError:
                        logger.debug("interfaces not configured")

        for key in self.get_config_db_keys("PORT|Ethernet*"):
            intf_keys = self.get_redis_all("CONFIG_DB", key).keys()

            if "admin_status" not in intf_keys:
                self.sonic_db.set(
                    self.sonic_db.CONFIG_DB,
                    key,
                    "admin_status",
                    "down",
                )

            if "mtu" not in intf_keys:
                self.sonic_db.set(
                    self.sonic_db.CONFIG_DB,
                    key,
                    "mtu",
                    str(self.mtu_default),
                )

    def is_ufd_port(self, port, ufd_list):

        for ufd_id in ufd_list:
            try:
                if port in ufd_id.get("config", {}).get("uplink"):
                    return True
            except:
                pass
            try:
                if port in ufd_id.get("config", {}).get("downlink"):
                    return True
            except:
                pass

        return False

    def get_ufd(self):
        xpath = "/goldstone-uplink-failure-detection:ufd-groups"
        self.sess.switch_datastore("operational")
        d = self.sess.get_data(xpath)
        ufd_list = [v for v in d.get("ufd-groups", {}).get("ufd-group", {})]
        return ufd_list

    def parse_ufd_req(self, xpath):
        ufd_id = xpath.split("'")
        if len(ufd_id) > 1:
            ufd_id = ufd_id[1]
        xpath = xpath.split("/")
        attribute = ""
        for i in range(len(xpath)):
            node = xpath[i]
            if node.find("uplink") == 0:
                attribute = "uplink"
                break
            if node.find("downlink") == 0:
                attribute = "downlink"
                break

        return ufd_id, attribute

    def ufd_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")

        if event == "change":
            for change in changes:

                logger.debug(f"event: {event}; change_cb:{change}")
                ufd_list = self.get_ufd()
                ufd_id, attribute = self.parse_ufd_req(change.xpath)
                if isinstance(change, sysrepo.ChangeCreated):
                    if attribute == "uplink":
                        for data in ufd_list:
                            if data["ufd-id"] == ufd_id:
                                ufd_data = data
                                break
                        try:
                            uplink_port = ufd_data["config"]["uplink"]
                            raise sysrepo.SysrepoValidationFailedError(
                                "Uplink Already configured"
                            )

                        except KeyError:
                            if self.is_ufd_port(change.value, ufd_list):
                                raise sysrepo.SysrepoInvalArgError(
                                    f"{change.value}:Port Already configured"
                                )
                            else:
                                pass
                    elif attribute == "downlink":
                        if self.is_ufd_port(change.value, ufd_list):
                            raise sysrepo.SysrepoInvalArgError(
                                f"{change.value}:Port Already configured"
                            )
                        else:
                            pass

        elif event == "done":
            for change in changes:
                logger.debug(f"event: {event}; change_cb:{change}")
                ufd_id, attribute = self.parse_ufd_req(change.xpath)

                if len(attribute) > 0:
                    if isinstance(change, sysrepo.ChangeCreated):
                        if attribute == "uplink":
                            # check if the port is part of ufd already
                            # if so return error
                            # if uplink port's oper_status is down in redis
                            # config admin status of downlink ports to down in redis
                            ufd_list = self.get_ufd()
                            _hash = "PORT_TABLE:" + change.value

                            oper_status = _decode(
                                self.sonic_db.get(
                                    self.sonic_db.APPL_DB, _hash, "oper_status"
                                )
                            )
                            if oper_status == "down":
                                for data in ufd_list:
                                    if data["ufd-id"] == ufd_id:
                                        break

                                try:
                                    downlink_ports = data["config"]["downlink"]
                                    for port in downlink_ports:
                                        _hash = "PORT|" + port
                                        self.set_config_db(
                                            event, _hash, "admin_status", "down"
                                        )
                                except:
                                    pass

                        elif attribute == "downlink":
                            # check if the port is part of ufd already
                            # if so return error

                            # if uplink is already configured
                            # anf if uplink operstatus is down in redis
                            # config admin status of downlink ports to down in redis
                            ufd_list = self.get_ufd()
                            for data in ufd_list:
                                if data["ufd-id"] == ufd_id:
                                    break
                            else:
                                logger.warn(
                                    f"failed to find configuration for UFD {ufd_id}"
                                )
                                continue

                            if not "uplink" in data.get("config", {}):
                                logger.debug(f"uplink not configured for UFD {ufd_id}")
                                continue

                            uplink_port = list(data["config"]["uplink"])
                            _hash = "PORT_TABLE:" + uplink_port[0]
                            oper_status = _decode(
                                self.sonic_db.get(
                                    self.sonic_db.APPL_DB, _hash, "oper_status"
                                )
                            )
                            if oper_status == "down":
                                _hash = "PORT|" + change.value
                                self.set_config_db(
                                    "done", _hash, "admin_status", "down"
                                )

                    if isinstance(change, sysrepo.ChangeDeleted):
                        if attribute == "uplink":
                            # configure downlink ports admin status in redis as per sysrepo running db values
                            ufd_list = self.get_ufd()
                            for data in ufd_list:
                                if data["ufd-id"] == ufd_id:
                                    break
                            try:
                                downlink_ports = data["config"]["downlink"]
                                self.sess.switch_datastore("running")
                                for port in downlink_ports:
                                    try:
                                        xpath = f"/goldstone-interfaces:interfaces/interface[name ='{port}']/config/admin-status"
                                        admin_status = self.get_running_data(xpath)
                                        if admin_status:
                                            _hash = "PORT|" + port
                                            self.set_config_db(
                                                "done",
                                                _hash,
                                                "admin_status",
                                                admin_status.lower(),
                                            )
                                    except KeyError:
                                        pass
                            except:
                                pass

                        if attribute == "downlink":
                            # configure downlink ports admin status in redis as per sysrepo running db values
                            try:
                                port = str(change).split("'")[3]
                                xpath = f"/goldstone-interfaces:interfaces/interface[name='{port}']/config/admin-status"
                                admin_status = self.get_running_data(xpath)
                                if admin_status:
                                    _hash = "PORT|" + port
                                    self.set_config_db(
                                        "done",
                                        _hash,
                                        "admin_status",
                                        admin_status.lower(),
                                    )
                            except KeyError:
                                pass

    def get_portchannel(self):
        xpath = "/goldstone-portchannel:portchannel"
        self.sess.switch_datastore("operational")
        d = self.sess.get_data(xpath)
        portchannel_list = [
            v for v in d.get("portchannel", {}).get("portchannel-group", {})
        ]
        return portchannel_list

    def is_portchannel_intf(self, intf):
        portchannel_list = self.get_portchannel()
        for portchannel_id in portchannel_list:
            try:
                if intf in portchannel_id.get("config", {}).get("interface"):
                    return True
            except:
                pass
        return False

    def parse_portchannel_req(self, xpath):
        portchannel_id = xpath.split("'")
        if len(portchannel_id) > 1:
            portchannel_id = portchannel_id[1]
        xpath = xpath.split("/")
        attr = ""
        _mem_hash = None
        for i in range(len(xpath)):
            node = xpath[i]
            if node.find("interface") == 0:
                attr = "interface"
                ifname = node.split("'")
                if len(ifname) > 1:
                    ifname = ifname[1]
                    _mem_hash = "PORTCHANNEL_MEMBER|" + portchannel_id + "|" + ifname
                break
            elif node.find("admin-status") == 0:
                attr = "admin-status"
                break
            elif node.find("mtu") == 0:
                attr = "mtu"
                break
        if attr == "":
            attr = xpath[-1]
        _hash = "PORTCHANNEL|" + portchannel_id
        return portchannel_id, attr, _hash, _mem_hash

    def portchannel_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn(f"unsupported event: {event}")
            return

        if event == "change":
            for change in changes:
                logger.debug(f"event: {event}; change_cb: {change}")
                portchannel_id, attr, _hash, _mem_hash = self.parse_portchannel_req(
                    change.xpath
                )
                if isinstance(change, sysrepo.ChangeCreated):
                    if attr == "interface":
                        if self.is_portchannel_intf(change.value):
                            raise sysrepo.SysrepoInvalArgError(
                                f"{change.value}:Interface is already part of LAG"
                            )
                        else:
                            pass
        elif event == "done":
            for change in changes:
                logger.debug(f"event: {event}; change_cb: {change}")
                portchannel_id, attr, _hash, _mem_hash = self.parse_portchannel_req(
                    change.xpath
                )
                if isinstance(change, sysrepo.ChangeCreated) or isinstance(
                    change, sysrepo.ChangeModified
                ):
                    logger.debug("change created/modified")
                    if attr == "config":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB, _hash, "mtu", self.mtu_default
                        )
                    if attr == "admin-status":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB, _hash, "admin_status", change.value
                        )
                    if attr == "mtu":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB, _hash, "mtu", change.value
                        )
                    if attr == "interface":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB, _mem_hash, "NULL", "NULL"
                        )
                if isinstance(change, sysrepo.ChangeDeleted):
                    logger.debug(f"{change.xpath}")
                    logger.debug("change deleted")
                    if attr == "mtu":
                        self.sonic_db.set(
                            self.sonic_db.CONFIG_DB, _hash, "mtu", self.mtu_default
                        )
                    if attr == "interface":
                        self.sonic_db.delete(self.sonic_db.CONFIG_DB, _mem_hash)
                    if attr == "config":
                        self.sonic_db.delete(self.sonic_db.CONFIG_DB, _hash)

    def get_oper_status(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/state/oper-status"
        oper_status = self.get_interface_state_data(xpath)
        downlink_port, uplink_port = self.is_downlink_port(ifname)

        if downlink_port:
            _hash = "PORT_TABLE:" + uplink_port[0]
            uplink_oper_status = _decode(
                self.sonic_db.get(self.sonic_db.APPL_DB, _hash, "oper_status")
            )

            if uplink_oper_status == "down":
                return "DORMANT"

        if oper_status != None:
            return oper_status.upper()

    def event_handler(self, msg):
        try:
            key = _decode(msg["channel"])
            key = key.replace("__keyspace@0__:", "")
            name = key.replace("PORT_TABLE:", "")
            oper_status = _decode(
                self.sonic_db.get(self.sonic_db.APPL_DB, key, "oper_status")
            )

            curr_oper_status = self.notif_if.get(name, "unknown")

            if curr_oper_status == oper_status:
                return

            eventname = "goldstone-interfaces:interface-link-state-notify-event"
            notif = {
                eventname: {
                    "if-name": name,
                    "oper-status": self.get_oper_status(name),
                }
            }

            with self.conn.start_session() as sess:
                ly_ctx = sess.get_ly_ctx()
                n = json.dumps(notif)
                logger.info(f"Notification: {n}")
                dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
                sess.notification_send_ly(dnode)
                self.notif_if[name] = oper_status

        except Exception as exp:
            logger.error(exp)
            pass

    async def handle_tasks(self):
        while True:
            await asyncio.sleep(1)
            try:
                task = self.task_queue.get(False)
                await task
                self.task_queue.task_done()
            except queue.Empty:
                pass

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
                is_updated = self.breakout_update_usonic()
                if is_updated:
                    await self.watch_pods()
                else:
                    self.cache_counters()

                await self.reconcile()

                self.is_usonic_rebooting = False

                self.sess.switch_datastore("running")

                self.sess.subscribe_module_change(
                    "goldstone-interfaces",
                    None,
                    self.intf_change_cb,
                )
                self.sess.subscribe_module_change(
                    "goldstone-vlan", None, self.vlan_change_cb
                )
                self.sess.subscribe_module_change(
                    "goldstone-uplink-failure-detection", None, self.ufd_change_cb
                )
                self.sess.subscribe_module_change(
                    "goldstone-portchannel", None, self.portchannel_change_cb
                )
                logger.debug(
                    "**************************after subscribe module change****************************"
                )

                self.sess.subscribe_oper_data_request(
                    "goldstone-interfaces",
                    "/goldstone-interfaces:interfaces",
                    self.interface_oper_cb,
                )
                self.sess.subscribe_oper_data_request(
                    "goldstone-portchannel",
                    "/goldstone-portchannel:portchannel",
                    self.portchannel_oper_cb,
                    oper_merge=True,
                )
                self.sess.subscribe_rpc_call(
                    "/goldstone-interfaces:clear-counters",
                    self.clear_counters,
                )

                cache = redis.Redis(REDIS_SERVICE_HOST, REDIS_SERVICE_PORT)
                pubsub = cache.pubsub()
                pubsub.psubscribe(
                    **{"__keyspace@0__:PORT_TABLE:Ethernet*": self.event_handler}
                )
                self.redis_thread = pubsub.run_in_thread(sleep_time=2)

        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()

        return [self.handle_tasks()]


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
            await server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        for noisy in [
            "hpack",
            "kubernetes.client.rest",
            "kubernetes_asyncio.client.rest",
        ]:
            l = logging.getLogger(noisy)
            l.setLevel(logging.INFO)
    #        sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
