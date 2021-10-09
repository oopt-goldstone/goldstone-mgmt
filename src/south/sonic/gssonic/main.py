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

REDIS_SERVICE_HOST = os.getenv("REDIS_SERVICE_HOST")
REDIS_SERVICE_PORT = os.getenv("REDIS_SERVICE_PORT")

SINGLE_LANE_INTERFACE_TYPES = ["CR", "LR", "SR", "KR"]
DOUBLE_LANE_INTERFACE_TYPES = ["CR2", "LR2", "SR2", "KR2"]
QUAD_LANE_INTERFACE_TYPES = ["CR4", "LR4", "SR4", "KR4"]
DEFAULT_INTERFACE_TYPE = "KR"

COUNTER_PORT_MAP = "COUNTERS_PORT_NAME_MAP"
COUNTER_TABLE_PREFIX = "COUNTERS:"
SAI_COUNTER_TO_YANG_MAP = {
    "SAI_PORT_STAT_IF_IN_UCAST_PKTS": "in-unicast-pkts",
    "SAI_PORT_STAT_IF_IN_ERRORS": "in-errors",
    "SAI_PORT_STAT_IF_IN_DISCARDS": "in-discards",
    "SAI_PORT_STAT_IF_IN_BROADCAST_PKTS": "in-broadcast-pkts",
    "SAI_PORT_STAT_IF_IN_MULTICAST_PKTS": "in-multicast-pkts",
    "SAI_PORT_STAT_IF_IN_UNKNOWN_PROTOS": "in-unknown-protos",
    "SAI_PORT_STAT_IF_OUT_UCAST_PKTS": "out-unicast-pkts",
    "SAI_PORT_STAT_IF_OUT_ERRORS": "out-errors",
    "SAI_PORT_STAT_IF_OUT_DISCARDS": "out-discards",
    "SAI_PORT_STAT_IF_OUT_BROADCAST_PKTS": "out-broadcast-pkts",
    "SAI_PORT_STAT_IF_OUT_MULTICAST_PKTS": "out-multicast-pkts",
    "SAI_PORT_STAT_IF_IN_OCTETS": "in-octets",
    "SAI_PORT_STAT_IF_OUT_OCTETS": "out-octets",
}


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
    if "G" in yang_val:
        return int(yang_val.split("G")[0]) * 1000
    elif "M" in yang_val:
        return int(yang_val.split("M")[0])
    else:
        raise sysrepo.SysrepoInvalArgError(f"unsupported speed: {yang_val}")


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
    elif speed == "5000":
        return "SPEED_5000M"
    elif speed == "2500":
        return "SPEED_2500M"
    elif speed == "1000":
        return "SPEED_1000M"
    elif speed == "100":
        return "SPEED_100M"
    raise sysrepo.SysrepoInvalArgError(f"unsupported speed: {speed}")


def speed_bcm_to_yang(speed):
    return f"SPEED_{speed[:-1]}"


class SONiC(object):
    def __init__(self):
        self.sonic_db = swsssdk.SonicV2Connector()
        # HMSET is not available in above connector, so creating new one
        self.sonic_configdb = swsssdk.ConfigDBConnector()
        self.sonic_configdb.connect()
        self.k8s = incluster_apis()
        self.is_rebooting = False
        self.counter_if_dict = {}
        self.notif_if = {}

        self.sonic_db.connect(self.sonic_db.CONFIG_DB)
        self.sonic_db.connect(self.sonic_db.APPL_DB)
        self.sonic_db.connect(self.sonic_db.COUNTERS_DB)

    def restart(self):
        self.is_rebooting = True
        self.k8s.restart_usonic()

    def enable_counters(self):
        # This is similar to "counterpoll port enable"
        value = {"FLEX_COUNTER_STATUS": "enable"}
        self.sonic_configdb.mod_entry("FLEX_COUNTER_TABLE", "PORT", value)

    def cache_counters(self):
        self.enable_counters()
        for k, v in self.hgetall("COUNTERS_DB", COUNTER_PORT_MAP).items():
            d = self.hgetall("COUNTERS_DB", f"COUNTERS:{v}")
            if not d:
                return False
            self.counter_if_dict[k] = d
        return True

    def get_counters(self, ifname):
        if ifname not in self.counter_if_dict:
            return {}

        oid = _decode(
            self.sonic_db.get(self.sonic_db.COUNTERS_DB, COUNTER_PORT_MAP, ifname)
        )
        data = self.hgetall("COUNTERS_DB", f"COUNTERS:{oid}")
        ret = {}
        for k, v in data.items():
            if k not in SAI_COUNTER_TO_YANG_MAP:
                logger.debug(f"skip: {k}")
                continue
            if k in self.counter_if_dict[ifname]:
                ret[SAI_COUNTER_TO_YANG_MAP[k]] = int(v) - int(
                    self.counter_if_dict[ifname][k]
                )
        return ret

    async def wait(self):
        await self.k8s.watch_pods()

        logger.debug("uSONiC deployment ready")

        # Caching base values of counters
        while True:
            if self.cache_counters():
                break
            logger.debug("counters not ready. waiting..")
            await asyncio.sleep(1)

        logger.info("uSONiC ready")

    def hgetall(self, db, key):
        db = getattr(self.sonic_db, db)
        data = self.sonic_db.get_all(db, key)
        if not data:
            return {}
        return {_decode(k): _decode(v) for k, v in data.items()}

    def get_keys(self, pattern, db="CONFIG_DB"):
        db = getattr(self.sonic_db, db)
        keys = self.sonic_db.keys(db, pattern=pattern)
        return map(_decode, keys) if keys else []

    def get_ifnames(self):
        return (n.split("|")[1] for n in self.get_keys("PORT|Ethernet*"))

    def get_vids(self):
        return (
            int(n.split("|")[1].replace("Vlan", ""))
            for n in self.get_keys("VLAN|Vlan*")
        )

    def create_vlan(self, vid):
        db = self.sonic_db.CONFIG_DB
        self.sonic_db.set(db, f"VLAN|Vlan{vid}", "vlanid", vid)

    def get_vlan_members(self, vid):
        members = self.get_keys(f"VLAN_MEMBER|Vlan{vid}|*")
        return [m.split("|")[-1] for m in members]

    def remove_vlan(self, vid):
        if len(self.get_vlan_members(vid)) > 0:
            raise sysrepo.SysrepoInvalArgError(f"vlan {vid} has dependencies")
        db = self.sonic_db.CONFIG_DB
        self.sonic_db.delete(db, f"VLAN|Vlan{vid}")

    def set_vlan_member(self, ifname, vid, mode):
        config = self.hgetall("CONFIG_DB", f"VLAN|Vlan{vid}")

        if not config:
            raise sysrepo.SysrepoInvalArgError(f"vlan {vid} not found")

        if "members@" in config:
            ifs = set(config["members@"].split(","))
            ifs.add(ifname)
            ifs = ",".join(ifs)
        else:
            ifs = ifname

        db = self.sonic_db.CONFIG_DB
        self.sonic_db.set(db, f"VLAN|Vlan{vid}", "vlanid", vid)
        self.sonic_db.set(db, f"VLAN|Vlan{vid}", "members@", ifs)
        self.sonic_db.set(
            db, f"VLAN_MEMBER|Vlan{vid}|{ifname}", "tagging_mode", mode.lower()
        )

    def remove_vlan_member(self, ifname, vid):
        config = self.hgetall("CONFIG_DB", f"VLAN|Vlan{vid}")

        if "members@" not in config:
            return

        ifs = set(config["members@"].split(","))
        ifs.remove(ifname)
        ifs = ",".join(ifs)
        db = self.sonic_db.CONFIG_DB

        self.sonic_db.set(db, f"VLAN|Vlan{vid}", "members@", ifs)
        self.sonic_db.delete(db, f"VLAN_MEMBER|Vlan{vid}|{ifname}")

    def set_config_db(self, name, key, value, table="PORT"):
        if key == "speed":
            value = speed_yang_to_redis(value)
        if type(value) == str and value != "NULL":
            value = value.lower()
        key = key.replace("-", "_")
        return self.sonic_db.set(
            self.sonic_db.CONFIG_DB, f"{table}|{name}", key, str(value)
        )

    def get_oper_status(self, ifname):
        return _decode(
            self.sonic_db.get(
                self.sonic_db.APPL_DB, f"PORT_TABLE:{ifname}", "oper_status"
            )
        )


class Server(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.sonic = SONiC()
        self.task_queue = queue.Queue()

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

    def get_default(self, key):
        ctx = self.sess.get_ly_ctx()
        keys = ["interfaces", "interface", "config", key]
        xpath = "".join(f"/goldstone-interfaces:{v}" for v in keys)

        for node in ctx.find_path(xpath):
            return node.default()

    def restart_usonic(self):
        return self.sonic.restart()

    async def wait_sonic(self):
        await self.sonic.wait()

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
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-vlan"
        assert xpath[0][1] == "vlans"
        assert xpath[1][1] == "vlan"
        assert xpath[1][2][0][0] == "vlan-id"
        vid = xpath[1][2][0][1]

        key = None
        if len(xpath) >= 4:
            if xpath[2][1] == "config":
                key = xpath[-1][1]

        return xpath, vid, key

    def parse_intf_change_req(self, xpath):
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-interfaces"
        assert xpath[0][1] == "interfaces"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        ifname = xpath[1][2][0][1]

        if ifname not in self.sonic.get_ifnames():
            raise sysrepo.SysrepoInvalArgError("Invalid Interface name")

        key = None
        if len(xpath) >= 4:
            if xpath[2][1] == "config":
                key = xpath[-1][1]
            elif xpath[2][1] == "auto-negotiate":
                key = "auto-negotiate"
            elif xpath[2][1] == "switched-vlan":
                key = "switched-vlan"

        return xpath, ifname, key

    async def breakout_callback(self):
        self.sess.switch_datastore("running")

        await self.wait_for_sr_unlock()

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):
                await self.wait_sonic()

                await self.reconcile()

                self.sonic.is_rebooting = False

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

        is_updated = self.sonic.k8s.update_usonic_config(intfs)

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

        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

        for change in changes:
            logger.debug(f"event: {event}, type: {type(change)}, change: {change}")

            xpath, vid, key = self.parse_vlan_change_req(change.xpath)

            logger.debug(f"xpath: {xpath}, vid: {vid}, key: {key}")

            if isinstance(change, sysrepo.ChangeCreated):
                if key == "vlan-id":
                    if event == "done":
                        self.sonic.create_vlan(vid)
            elif isinstance(change, sysrepo.ChangeDeleted):
                if key == "vlan-id":
                    if event == "change":
                        if len(self.sonic.get_vlan_members(vid)) > 0:
                            raise sysrepo.SysrepoInvalArgError(
                                f"vlan {vid} has dependencies"
                            )
                        config = self.sonic.hgetall("CONFIG_DB", f"VLAN|Vlan{vid}")
                        if not config:
                            raise sysrepo.SysrepoInvalArgError(f"vlan {vid} not found")
                    elif event == "done":
                        self.sonic.remove_vlan(vid)

    def intf_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")
            return

        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

        valid_speeds = [40000, 100000]
        breakout_valid_speeds = []  # no speed change allowed for sub-interfaces

        update_usonic = False
        intfs_need_adv_speed_config = (
            set()
        )  # put ifname of the interfaces that need adv speed config

        for change in changes:
            logger.debug(f"event: {event}, type: {type(change)}, change: {change}")

            xpath, ifname, key = self.parse_intf_change_req(change.xpath)

            logger.debug(f"xpath: {xpath}, ifname: {ifname}, key: {key}")

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug("......change created......")
                if key in ["admin-status", "fec", "description", "alias", "mtu"]:
                    if event == "done":
                        self.sonic.set_config_db(ifname, key, change.value)
                elif key == "interface-type":
                    iftype = change.value
                    if event == "change":
                        self.validate_interface_type(ifname, iftype)
                    elif event == "done":
                        self.sonic.k8s.run_bcmcmd_port(ifname, "if=" + iftype)
                elif key == "auto-negotiate":
                    if event == "change":
                        if xpath[-1][1] == "advertised-speeds":
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
                        if xpath[-1][1] == "enabled":
                            self.sonic.k8s.run_bcmcmd_port(
                                ifname, "an=" + ("yes" if change.value else "no")
                            )
                        elif xpath[-1][1] == "advertised-speeds":
                            intfs_need_adv_speed_config.add(ifname)
                        self.sonic.k8s.update_bcm_portmap()
                elif key == "switched-vlan":
                    prefix = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config"
                    if event == "change":
                        if xpath[-1][1] == "interface-mode":
                            mode = change.value
                            if mode == "TRUNK":
                                xpath = prefix + "/trunk-vlans"
                                vids = self.get_running_data(xpath, [])
                                for vid in vids:
                                    self.sonic.set_vlan_member(ifname, vid, "tagged")
                            elif mode == "ACCESS":
                                xpath = prefix + "/access-vlan"
                                vid = self.get_running_data(xpath)
                                if vid:
                                    self.sonic.set_vlan_member(ifname, vid, "untagged")
                        elif xpath[-1][1] == "trunk-vlans":
                            self.sonic.set_vlan_member(ifname, change.value, "tagged")
                        elif xpath[-1][1] == "access-vlan":
                            self.sonic.set_vlan_member(ifname, change.value, "untagged")

                elif key == "speed":

                    if event == "change":
                        # 'goldstone-interfaces:SPEED_100GB' to 1000000
                        value = speed_yang_to_redis(change.value)
                        if self.get_breakout_detail(ifname):
                            valids = breakout_valid_speeds
                        else:
                            valids = valid_speeds
                        if value not in valids:
                            raise sysrepo.SysrepoInvalArgError(
                                f"Invalid speed: {change.value}, candidates: {valids}"
                            )
                    elif event == "done":
                        self.sonic.set_config_db(ifname, key, change.value)
                        self.sonic.k8s.update_bcm_portmap()

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
                    # After the update, we will watch asynchronosly in wait_sonic()
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
                    if event == "done":
                        self.sonic.set_config_db(ifname, key, change.value)
                elif key == "interface-type":
                    iftype = change.value
                    if event == "change":
                        self.validate_interface_type(ifname, iftype)
                    elif event == "done":
                        self.sonic.k8s.run_bcmcmd_port(ifname, "if=" + iftype)
                elif key == "auto-negotiate":
                    if event == "change":
                        if xpath[-1][1] == "advertised-speeds":
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
                        if xpath[-1][1] == "enabled":
                            self.sonic.k8s.run_bcmcmd_port(
                                ifname, "an=" + ("yes" if change.value else "no")
                            )
                        elif xpath[-1][1] == "advertised-speeds":
                            intfs_need_adv_speed_config.add(ifname)

                elif key == "switched-vlan":
                    prefix = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config"
                    if event == "change":
                        if xpath[-1][1] == "interface-mode":
                            mode = change.value
                            if mode == "TRUNK":
                                xpath = prefix + "/trunk-vlans"
                                vids = self.get_running_data(xpath, [])
                                for vid in vids:
                                    self.sonic.set_vlan_member(ifname, vid, "tagged")
                            elif mode == "ACCESS":
                                xpath = prefix + "/access-vlan"
                                vid = self.get_running_data(xpath)
                                if vid:
                                    self.sonic.set_vlan_member(ifname, vid, "untagged")
                        elif xpath[-1][1] == "trunk-vlans":
                            logger.warn(
                                "trunk-vlans leaf-list should not trigger modified event.."
                            )
                            self.sonic.set_vlan_member(ifname, change.value, "tagged")
                        elif xpath[-1][1] == "access-vlan":
                            for key in self.sonic.get_keys(f"VLAN_MEMBER|*|{ifname}"):
                                v = self.sonic.hgetall("CONFIG_DB", key)
                                if v.get("tagging_mode") == "untagged":
                                    vid = int(key.split("|")[1].replace("Vlan", ""))
                                    self.sonic.remove_vlan_member(ifname, vid)
                            self.sonic.set_vlan_member(ifname, change.value, "untagged")

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
                        self.sonic.set_config_db(ifname, key, change.value)
                        self.sonic.k8s.update_bcm_portmap()

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

                    if key == "speed":
                        # TODO remove hardcoded value
                        value = "100G"
                    elif key in ["fec", "admin-status", "mtu"]:
                        value = self.get_default(key)

                    if event == "done":
                        logger.debug(f"adding default value {value} of {key} to redis")
                        self.sonic.set_config_db(ifname, key, value)

                    if event == "done" and key == "speed":
                        self.sonic.k8s.update_bcm_portmap()

                elif key == "interface-type":
                    if event == "done":
                        try:
                            breakout_details = self.get_breakout_detail(ifname)
                            logger.debug(f"Breakout Details :: {breakout_details}")
                            if not breakout_details:
                                raise KeyError
                            if int(breakout_details["num-channels"]) == 4:
                                self.sonic.k8s.run_bcmcmd_port(
                                    ifname, "if=" + DEFAULT_INTERFACE_TYPE
                                )
                            elif int(breakout_details["num-channels"]) == 2:
                                self.sonic.k8s.run_bcmcmd_port(
                                    ifname, "if=" + DEFAULT_INTERFACE_TYPE + "2"
                                )
                            else:
                                raise sysrepo.SysrepoInvalArgError(
                                    "Unsupported interface type"
                                )
                        except (sysrepo.errors.SysrepoNotFoundError, KeyError):
                            self.sonic.k8s.run_bcmcmd_port(
                                ifname, "if=" + DEFAULT_INTERFACE_TYPE + "4"
                            )
                elif key == "auto-negotiate":
                    if event == "done":
                        if xpath[-1][1] == "enabled":
                            self.sonic.k8s.run_bcmcmd_port(ifname, "an=no")
                        elif xpath[-1][1] == "advertised-speeds":
                            intfs_need_adv_speed_config.add(ifname)
                elif key == "switched-vlan":
                    if event == "done":
                        if xpath[-1][1] == "trunk-vlans":
                            vid = int(xpath[-1][2][0][1])
                            v = self.sonic.hgetall(
                                "CONFIG_DB", f"VLAN_MEMBER|Vlan{vid}|{ifname}"
                            )
                            if v.get("tagging_mode") == "tagged":
                                self.sonic.remove_vlan_member(ifname, vid)
                        elif xpath[-1][1] == "access-vlan":
                            for key in self.sonic.get_keys(f"VLAN_MEMBER|*|{ifname}"):
                                v = self.sonic.hgetall("CONFIG_DB", key)
                                if v.get("tagging_mode") == "untagged":
                                    vid = int(key.split("|")[1].replace("Vlan", ""))
                                    self.sonic.remove_vlan_member(ifname, vid)

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
            self.sonic.k8s.run_bcmcmd_port(ifname, f"adv={speeds}")

        if update_usonic:
            logger.info("creating breakout task")
            updated = self.breakout_update_usonic()
            if updated:
                self.task_queue.put(self.breakout_callback())

    def is_downlink_port(self, ifname):
        ufd_list = self.get_ufd()
        for data in ufd_list:
            try:
                if ifname in data["config"]["downlink"]:
                    return True, list(data["config"]["uplink"])
            except:
                pass

        return False, None

    def vlan_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")

        if self.sonic.is_rebooting:
            return {}

        vlans = [
            {"vlan-id": vid, "config": {"vlan-id": vid}, "state": {"vlan-id": vid}}
            for vid in self.sonic.get_vids()
        ]

        for vlan in vlans:
            members = self.sonic.get_vlan_members(vlan["vlan-id"])
            if members:
                vlan["members"] = {"member": members}

        return {"goldstone-vlan:vlans": {"vlan": vlans}}

    def interface_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        if self.sonic.is_rebooting:
            # FIXME sysrepo bug. oper cb can't raise exception
            # see https://github.com/sysrepo/sysrepo/issues/2524
            # or https://github.com/sysrepo/sysrepo/issues/2448
            # raise sysrepo.SysrepoCallbackFailedError("uSONiC is rebooting")
            return {}

        counter_only = "counters" in req_xpath

        req_xpath = list(libyang.xpath_split(req_xpath))
        ifnames = self.sonic.get_ifnames()

        if (
            len(req_xpath) == 3
            and req_xpath[1][1] == "interface"
            and req_xpath[2][1] == "name"
        ):
            interfaces = [{"name": name} for name in ifnames]
            return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

        if (
            len(req_xpath) > 1
            and req_xpath[1][1] == "interface"
            and len(req_xpath[1][2]) == 1
        ):
            cond = req_xpath[1][2][0]
            assert cond[0] == "name"
            if cond[1] not in ifnames:
                return None
            ifnames = [cond[1]]

        interfaces = {}
        parent_dict = {}
        for name in ifnames:
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
                interface["state"]["breakout"] = {"parent": parent}

            interfaces[name] = interface

        for key, value in parent_dict.items():
            v = self.sonic.hgetall("APPL_DB", f"PORT_TABLE:{key}")

            if "speed" in v:
                speed = speed_redis_to_yang(v["speed"])
                logger.debug(f"key: {key}, speed: {speed}")
                if key not in interfaces:
                    interfaces[key] = {"name": name, "config": {"name": name}}
                interfaces[key]["state"] = {
                    "breakout": {"num-channels": value + 1, "channel-speed": speed}
                }
            else:
                logger.warn(
                    f"Breakout interface:{key} doesnt has speed attribute in Redis"
                )

        interfaces = list(interfaces.values())

        if not counter_only:
            bcminfo = self.sonic.k8s.bcm_ports_info(list(i["name"] for i in interfaces))

        for intf in interfaces:
            ifname = intf["name"]
            intf["state"]["counters"] = self.sonic.get_counters(ifname)

            if not counter_only:

                intf["state"]["oper-status"] = self.get_oper_status(ifname)

                config = self.sonic.hgetall("APPL_DB", f"PORT_TABLE:{ifname}")
                for key, value in config.items():
                    if key in ["alias", "lanes"]:
                        intf["state"][key] = value
                    elif key in ["speed"]:
                        intf["state"][key] = speed_redis_to_yang(value)
                    elif key in ["admin_status", "fec", "mtu"]:
                        intf["state"][key.replace("_", "-")] = value.upper()

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
                            speed_bcm_to_yang(e) for e in v
                        ]
                else:
                    intf["auto-negotiate"] = {"state": {"enabled": False}}

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

    def portchannel_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        if self.sonic.is_rebooting:
            logger.debug("usonic is rebooting. no handling done in oper-callback")
            return

        keys = self.sonic.get_keys("LAG_TABLE:PortChannel*", "APPL_DB")

        r = []

        for key in keys:
            name = key.split(":")[1]
            state = self.sonic.hgetall("APPL_DB", key)
            state = {k.replace("_", "-"): v.upper() for k, v in state.items()}
            r.append({"portchannel-id": name, "state": state})

        logger.debug(f"portchannel: {r}")

        return {"goldstone-portchannel:portchannel": {"portchannel-group": r}}

    def clear_counters(self, xpath, input_params, event, priv):
        logger.debug(
            f"clear_counters: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        self.sonic.cache_counters()

    async def reconcile(self):
        self.sess.switch_datastore("running")

        vlans = self.get_running_data("/goldstone-vlan:vlans/vlan", [])

        for vlan in vlans:
            self.sonic.create_vlan(vlan["vlan-id"])

        prefix = "/goldstone-interfaces:interfaces/interface"
        for ifname in self.sonic.get_ifnames():
            xpath = f"{prefix}[name='{ifname}']"
            data = self.get_running_data(xpath, {})
            config = data.get("config", {})

            vlan_config = data.get("switched-vlan", {}).get("config", {})

            logger.debug(f"{ifname} interface config: {config}")

            # default setting
            for key in ["admin-status", "mtu"]:
                if key not in config:
                    config[key] = self.get_default(key)

            for key in config:
                if key == "interface-type":
                    self.sonic.k8s.run_bcmcmd_port(ifname, "if=" + config[key])
                elif key in [
                    "admin-status",
                    "fec",
                    "description",
                    "alias",
                    "mtu",
                    "speed",
                ]:
                    self.sonic.set_config_db(ifname, key, config[key])
                elif key in ["name"]:
                    pass
                else:
                    logger.warn(f"unhandled configuration: {key}, {config[key]}")

            if vlan_config:
                mode = vlan_config.get("interface-mode")
                if mode == "TRUNK":
                    for vid in vlan_config.get("trunk-vlans", []):
                        self.sonic.set_vlan_member(ifname, vid, "tagged")
                elif mode == "ACCESS":
                    vid = vlan_config.get("access-vlan")
                    if vid:
                        self.sonic.set_vlan_member(ifname, vid, "untagged")

        pc_list = self.get_running_data(
            "/goldstone-portchannel:portchannel/portchannel-group", []
        )
        for pc in pc_list:
            pid = pc["portchannel-id"]
            for leaf in ["admin-status", "mtu"]:
                default = self.get_default(leaf)
                value = pc["config"].get(leaf, default)
                self.sonic.set_config_db(pid, leaf, value, "PORTCHANNEL")
            for intf in pc["config"].get("interface", []):
                self.sonic.set_config_db(
                    pid + "|" + intf, "NULL", "NULL", "PORTCHANNEL_MEMBER"
                )
            else:
                logger.debug(f"no interface configured on {pid}")

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
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-uplink-failure-detection"
        assert xpath[0][1] == "ufd-groups"
        assert xpath[1][1] == "ufd-group"
        assert xpath[1][2][0][0] == "ufd-id"
        uid = xpath[1][2][0][1]

        key = None
        if len(xpath) >= 4:
            if xpath[2][1] == "config":
                key = xpath[-1][1]

        return xpath, uid, key

    def ufd_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn("unsupported event: {event}")

        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

        for change in changes:

            logger.debug(f"event: {event}, type: {type(change)}, change: {change}")

            xpath, uid, key = self.parse_ufd_req(change.xpath)
            ufd_list = self.get_ufd()

            logger.debug(f"xpath: {xpath}, uid: {uid}, key: {key}")

            if event == "change":
                if isinstance(change, sysrepo.ChangeCreated):
                    if key == "uplink":
                        for data in ufd_list:
                            if data["ufd-id"] == uid:
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
                    elif key == "downlink":
                        if self.is_ufd_port(change.value, ufd_list):
                            raise sysrepo.SysrepoInvalArgError(
                                f"{change.value}:Port Already configured"
                            )
                        else:
                            pass

            elif event == "done":
                if isinstance(change, sysrepo.ChangeCreated):
                    if key == "uplink":
                        # check if the port is part of ufd already
                        # if so return error
                        # if uplink port's oper_status is down in redis
                        # config admin status of downlink ports to down in redis
                        if self.sonic.get_oper_status(change.value) == "down":
                            for data in ufd_list:
                                if data["ufd-id"] == uid:
                                    break

                            try:
                                downlink_ports = data["config"]["downlink"]
                                for port in downlink_ports:
                                    self.sonic.set_config_db(
                                        port, "admin_status", "down"
                                    )
                            except:
                                pass

                    elif key == "downlink":
                        # check if the port is part of ufd already
                        # if so return error

                        # if uplink is already configured
                        # anf if uplink operstatus is down in redis
                        # config admin status of downlink ports to down in redis
                        ufd_list = self.get_ufd()
                        for data in ufd_list:
                            if data["ufd-id"] == uid:
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
                        if self.sonic.get_oper_status(uplink_port[0]) == "down":
                            self.sonic.set_config_db(
                                change.value, "admin-status", "down"
                            )

                if isinstance(change, sysrepo.ChangeDeleted):
                    if key == "uplink":
                        # configure downlink ports admin status in redis as per sysrepo running db values
                        for data in ufd_list:
                            if data["ufd-id"] == uid:
                                break
                        try:
                            downlink_ports = data["config"]["downlink"]
                            self.sess.switch_datastore("running")
                            for port in downlink_ports:
                                try:
                                    xpath = f"/goldstone-interfaces:interfaces/interface[name ='{port}']/config/admin-status"
                                    admin_status = self.get_running_data(xpath)
                                    if admin_status:
                                        self.sonic.set_config_db(
                                            port, "admin-status", admin_status.lower()
                                        )
                                except KeyError:
                                    pass
                        except:
                            pass

                    if key == "downlink":
                        # configure downlink ports admin status in redis as per sysrepo running db values
                        try:
                            port = str(change).split("'")[3]
                            xpath = f"/goldstone-interfaces:interfaces/interface[name='{port}']/config/admin-status"
                            admin_status = self.get_running_data(xpath)
                            if admin_status:
                                self.sonic.set_config_db(
                                    port,
                                    "admin-status",
                                    admin_status.lower(),
                                )
                        except KeyError:
                            pass

    def get_portchannel(self):
        xpath = "/goldstone-portchannel:portchannel/portchannel-group"
        return self.get_operational_data(xpath)

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
        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-portchannel"
        assert xpath[0][1] == "portchannel"
        assert xpath[1][1] == "portchannel-group"
        assert xpath[1][2][0][0] == "portchannel-id"
        pid = xpath[1][2][0][1]

        key = None
        if len(xpath) >= 3:
            if xpath[2][1] == "config":
                key = xpath[-1][1]

        return xpath, pid, key

    def portchannel_change_cb(self, event, req_id, changes, priv):
        logger.debug(f"event: {event}, changes: {changes}")

        if event not in ["change", "done"]:
            logger.warn(f"unsupported event: {event}")
            return

        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

        for change in changes:
            logger.debug(f"event: {event}, type: {type(change)}, change: {change}")

            xpath, pid, key = self.parse_portchannel_req(change.xpath)

            logger.debug(f"xpath: {xpath}, pid: {pid}, key: {key}")

            if event == "change":
                if isinstance(change, sysrepo.ChangeCreated):
                    if key == "interface":
                        if self.is_portchannel_intf(change.value):
                            raise sysrepo.SysrepoInvalArgError(
                                f"{change.value}:Interface is already part of LAG"
                            )
                        else:
                            pass
            elif event == "done":
                logger.debug(f"event: {event}; change_cb: {change}")

                if type(change) in [sysrepo.ChangeCreated, sysrepo.ChangeModified]:
                    if key == "config":
                        self.sonic.set_config_db(
                            pid, "mtu", self.get_default("mtu"), "PORTCHANNEL"
                        )
                    elif key in ["admin-status", "mtu"]:
                        self.sonic.set_config_db(pid, key, change.value, "PORTCHANNEL")
                    elif key == "interface":
                        ifname = xpath[-1][2][0][1]
                        self.sonic.sonic_db.set(
                            self.sonic.sonic_db.CONFIG_DB,
                            f"PORTCHANNEL_MEMBER|{pid}|{ifname}",
                            "NULL",
                            "NULL",
                        )
                elif type(change) == sysrepo.ChangeDeleted:
                    if key == "mtu":
                        self.sonic.set_config_db(
                            pid, "mtu", self.get_default("mtu"), "PORTCHANNEL"
                        )
                    elif key == "interface":
                        ifname = xpath[-1][2][0][1]
                        self.sonic.sonic_db.delete(
                            self.sonic.sonic_db.CONFIG_DB,
                            f"PORTCHANNEL_MEMBER|{pid}|{ifname}",
                        )
                    elif key == "config":
                        self.sonic.sonic_db.delete(
                            self.sonic.sonic_db.CONFIG_DB, f"PORTCHANNEL|{pid}"
                        )

    def get_oper_status(self, ifname):
        oper_status = self.sonic.get_oper_status(ifname)
        downlink_port, uplink_port = self.is_downlink_port(ifname)

        if downlink_port:
            _hash = "PORT_TABLE:" + uplink_port[0]
            uplink_oper_status = _decode(
                self.sonic.sonic_db.get(
                    self.sonic.sonic_db.APPL_DB, _hash, "oper_status"
                )
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
                self.sonic.sonic_db.get(self.sonic.sonic_db.APPL_DB, key, "oper_status")
            )

            curr_oper_status = self.sonic.notif_if.get(name, "unknown")

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
                self.sonic.notif_if[name] = oper_status

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

        self.sess.switch_datastore("running")

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):
                # Calling breakout_update_usonic() is mandatory before initial reconcile
                # process, as gssouth-sonic will replace the interface names properly during
                # init if they have been modified.
                is_updated = self.breakout_update_usonic()
                if is_updated:
                    await self.wait_sonic()
                else:
                    self.sonic.cache_counters()

                await self.reconcile()

                self.sonic.is_rebooting = False

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
                    "goldstone-vlan",
                    "/goldstone-vlan:vlans",
                    self.vlan_oper_cb,
                    oper_merge=True,
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
