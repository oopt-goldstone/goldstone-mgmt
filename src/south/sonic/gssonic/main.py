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


def yang_val_to_speed(yang_val):
    if not yang_val:
        return None
    yang_val = yang_val.split(":")[-1]
    yang_val = yang_val.split("_")
    return int(yang_val[1].split("GB")[0])


def speed_to_yang_val(speed):
    # Considering only speeds supported in CLI
    speed = _decode(speed)
    if speed == "25000":
        return "SPEED_25GB"
    elif speed == "20000":
        return "SPEED_20GB"
    elif speed == "50000":
        return "SPEED_50GB"
    elif speed == "100000":
        return "SPEED_100GB"
    elif speed == "40000":
        return "SPEED_40GB"
    elif speed == "10000":
        return "SPEED_10GB"
    elif speed == "1000":
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
        return self.sonic_db.set(self.sonic_db.CONFIG_DB, _hash, key, value)

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

        return key, _hash, attr_dict

    async def breakout_callback(self):
        self.sess.switch_datastore("running")

        await self.wait_for_sr_unlock()

        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):

                await self.watch_pods()

                await self.reconcile()
                self.update_oper_ds()

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
            speed = yang_val_to_speed(b.get("channel-speed", None))
            intfs[name] = (numch, speed)

        is_updated = self.k8s.update_usonic_config(intfs)

        # Restart deployment if configmap update is successful
        if is_updated:
            self.restart_usonic()

        return is_updated

    def get_sr_data(self, xpath, datastore, default=None, no_subs=False):
        self.sess.switch_datastore(datastore)
        try:
            v = self.sess.get_data(xpath, no_subs=no_subs)
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

    def get_operational_data(self, xpath, default=None, no_subs=False):
        return self.get_sr_data(xpath, "operational", default, no_subs)

    def get_breakout_detail(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/breakout"
        data = self.get_operational_data(xpath, no_subs=True)
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

        update_oper_ds = False
        update_usonic = False

        for change in changes:
            logger.debug(f"change_cb: {change}")

            key, _hash, attr_dict = self.parse_intf_change_req(change.xpath)
            if "ifname" in attr_dict:
                ifname = attr_dict["ifname"]

            logger.debug(f"key: {key}, _hash: {_hash}, attr_dict: {attr_dict}")

            if isinstance(change, sysrepo.ChangeCreated):
                logger.debug("......change created......")
                if type(change.value) != type({}) and key != "name" and key != "ifname":
                    if key == "description" or key == "alias":
                        self.set_config_db(event, _hash, key, change.value)

                    elif key == "admin-status":
                        self.set_config_db(
                            event, _hash, "admin_status", change.value.lower()
                        )

                    elif key == "interface-type":
                        iftype = change.value
                        if event == "change":
                            self.validate_interface_type(ifname, iftype)
                        elif event == "done":
                            self.k8s.run_bcmcmd_usonic(key, ifname, iftype)
                    elif key == "auto-negotiate":
                        # if event == "change":
                        #   Validation with respect to Port Breakout to be done
                        if event == "done":
                            self.k8s.run_bcmcmd_usonic(key, ifname, change.value)

                    elif key == "speed":

                        # 'goldstone-interfaces:SPEED_100GB' to 1000000
                        value = yang_val_to_speed(change.value) * 1000

                        if event == "change":
                            ifname = attr_dict["ifname"]
                            if self.get_breakout_detail(ifname):
                                valids = breakout_valid_speeds
                            else:
                                valids = valid_speeds
                            if value not in valids:
                                raise sysrepo.SysrepoInvalArgError(
                                    f"Invalid speed: {change.value}, candidates: {valids}"
                                )

                        self.set_config_db(event, _hash, "speed", value)

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

                        ufd_list = self.get_ufd()
                        if self.is_ufd_port(ifname, ufd_list):
                            raise sysrepo.SysrepoInvalArgError(
                                "Breakout cannot be configured on the interface that is part of UFD"
                            )

                        paired_key = (
                            "num-channels"
                            if key == "channel-speed"
                            else "channel-speed"
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
                        self.set_config_db(event, _hash, key, change.value)

            if isinstance(change, sysrepo.ChangeModified):
                logger.debug("......change modified......")
                if key == "description" or key == "alias":
                    self.set_config_db(event, _hash, key, change.value)
                elif key == "admin-status":
                    self.set_config_db(
                        event, _hash, "admin_status", change.value.lower()
                    )
                elif key == "interface-type":
                    iftype = change.value

                    if event == "change":
                        self.validate_interface_type(ifname, iftype)
                    elif event == "done":
                        self.k8s.run_bcmcmd_usonic(key, ifname, iftype)

                elif key == "auto-negotiate":
                    # if event == "change":
                    #   Validation with respect to Port Breakout to be done
                    if event == "done":
                        status_bcm = self.k8s.run_bcmcmd_usonic(
                            key, ifname, change.value
                        )
                elif key == "forwarding" or key == "enabled":
                    logger.debug("This key:{} should not be set in redis ".format(key))

                elif key == "speed":

                    # 'goldstone-interfaces:SPEED_100GB' to 1000000
                    value = yang_val_to_speed(change.value.split(":")[-1]) * 1000

                    if event == "change":
                        if self.get_breakout_detail(ifname):
                            valids = breakout_valid_speeds
                        else:
                            valids = valid_speeds

                        if value not in valids:
                            logger.debug("****** Invalid speed value *********")
                            raise sysrepo.SysrepoInvalArgError(
                                f"Invalid speed: {change.value}, candidates: {valids}"
                            )

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
                        breakouts = self.get_configured_breakout_ports(ifname)
                        # check if these breakouts are going to be deleted in this change
                        for breakout in breakouts:
                            xpath = f"/goldstone-interfaces:interfaces/interface[name='{breakout}']"
                            for c in changes:
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

                elif key in ["mtu", "speed"]:

                    if event == "done":
                        if key == "mtu":
                            value = self.mtu_default
                        elif key == "speed":
                            value = self.speed_default

                        logger.debug(f"adding default value of {key} to redis")
                        self.pack_defaults_to_redis(ifname=ifname, leaf_node=key)
                        update_oper_ds = True

                elif key == "interface-type":
                    if event == "change":
                        pass
                    if event == "done":
                        try:
                            breakout_details = self.get_breakout_detail(ifname)
                            logger.debug(f"Breakout Details :: {breakout_details}")
                            if not breakout_details:
                                raise KeyError
                            if int(breakout_details["num-channels"]) == 4:
                                status_bcm = self.k8s.run_bcmcmd_usonic(
                                    key, ifname, default_intf_type
                                )
                            elif int(breakout_details["num-channels"]) == 2:
                                status_bcm = self.k8s.run_bcmcmd_usonic(
                                    key, ifname, default_intf_type + "2"
                                )
                            else:
                                raise sysrepo.SysrepoInvalArgError(
                                    "Unsupported interface type"
                                )
                        except (sysrepo.errors.SysrepoNotFoundError, KeyError):
                            status_bcm = self.k8s.run_bcmcmd_usonic(
                                key, ifname, default_intf_type + "4"
                            )

                elif "PORT|" in _hash and key == "":
                    if event == "done":
                        # since sysrepo wipes out the pushed entry in oper ds
                        # when the corresponding entry in running ds is deleted,
                        # we need to repopulate the oper ds.
                        #
                        # this behavior might change in the future
                        # https://github.com/sysrepo/sysrepo/issues/1937#issuecomment-742851607
                        update_oper_ds = True

        if update_oper_ds:
            self.update_oper_ds()

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

    def interface_oper_cb(self, req_xpath):
        # Changing to operational datastore to fetch data
        # for the unconfigurable params in the xpath, data will
        # be fetched from Redis and complete data will be returned.

        # Use 'no_subs=True' parameter in oper_cb to fetch data from operational
        # datastore and to avoid locking of sysrepo db
        self.sess.switch_datastore("operational")
        r = {}
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

        self.sess.switch_datastore("operational")
        req_xpath = "/".join(req_xpath.split("/")[:3])
        try:
            interfaces = self.sess.get_data(req_xpath, no_subs=True)
        except Exception as e:
            logger.error(f"failed to get pushd oper data: xpath: {req_xpath}, err: {e}")
            return

        if not interfaces:
            return {}

        interfaces = interfaces.get("interfaces", {}).get("interface", [])
        prefix = "/goldstone-interfaces:interfaces"

        for intf in interfaces:
            ifname = intf["name"]
            if not "state" in intf:
                intf["state"] = {}

            xpath = f"{prefix}/interface[name='{ifname}']"
            intf["state"]["oper-status"] = self.get_oper_status(ifname)

            config = self.get_redis_all("APPL_DB", f"PORT_TABLE:{ifname}")
            for key, value in config.items():
                if key in ["alias", "lanes"]:
                    intf["state"][key] = value
                elif key in ["speed"]:
                    intf["state"][key] = speed_to_yang_val(value)
                elif key in ["mtu"]:
                    intf["ipv4"] = {key: value}
                elif key in ["admin_status"]:
                    intf["state"]["admin-status"] = value.upper()

            xpath = f"{xpath}/counters"
            intf["state"]["counters"] = {}
            for sl in statistic_leaves:
                sl_value = self.get_interface_state_data(xpath + "/" + sl)
                if sl_value != None:
                    intf["state"]["counters"][sl] = sl_value

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}

    def portchannel_oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug("***********inside portchannel oper callback***********")
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

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(
            "****************************inside oper-callback******************************"
        )
        if self.is_usonic_rebooting:
            logger.debug("usonic is rebooting. no handling done in oper-callback")
            return

        if req_xpath.startswith("/goldstone-interfaces:interfaces"):
            return self.interface_oper_cb(req_xpath)

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

    def pack_defaults_to_redis(self, ifname, leaf_node):
        if leaf_node == "mtu":
            self.sonic_db.set(
                self.sonic_db.CONFIG_DB,
                "PORT|" + ifname,
                "mtu",
                str(self.mtu_default),
            )
        elif leaf_node == "speed" and not self.get_breakout_detail(ifname):
            self.sonic_db.set(
                self.sonic_db.CONFIG_DB,
                "PORT|" + ifname,
                "speed",
                self.speed_default,
            )

    async def reconcile(self):
        self.sess.switch_datastore("running")
        intf_list = self.get_running_data(
            "/goldstone-interfaces:interfaces/interface", []
        )
        for intf in intf_list:
            config = intf.pop("config", {})
            intf.update(config)
            name = intf.pop("name")
            logger.debug(f"interface config: {intf}")

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
                elif key == "auto-negotiate" or key == "interface-type":
                    logger.debug("Reconcile for bcmcmd")
                    status_bcm = self.k8s.run_bcmcmd_usonic(key, name, intf[key])
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
                        str(intf[key].lower()),
                    )
                elif key == "speed":
                    self.sonic_db.set(
                        self.sonic_db.CONFIG_DB,
                        "PORT|" + name,
                        "speed",
                        str(yang_val_to_speed(intf[key]) * 1000),
                    )
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
            ifname = key.split("|")[1]
            intf_data = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, key)
            intf_keys = [v.decode("ascii") for v in list(intf_data.keys())]

            if "admin_status" not in intf_keys:
                self.sonic_db.set(
                    self.sonic_db.CONFIG_DB,
                    "PORT|" + ifname,
                    "admin_status",
                    "down",
                )

            if "mtu" not in intf_keys:
                self.sonic_db.set(
                    self.sonic_db.CONFIG_DB,
                    "PORT|" + ifname,
                    "mtu",
                    str(self.mtu_default),
                )

    def clean_oper_ds(self, sess):

        try:
            v = sess.get_data("/goldstone-vlan:*", no_subs=True)
            logger.debug(f"VLAN oper ds before delete: {v}")
            # clear the vlan operational ds and build it from scratch
            sess.delete_item("/goldstone-vlan:vlan")
        except Exception as e:
            logger.debug(f"failed to clear vlan oper ds: {e}")

        try:
            v = sess.get_data("/goldstone-interfaces:*", no_subs=True)
            logger.debug(f"interface oper ds before delete: {v}")
            # clear the intf operational ds and build it from scratch
            sess.delete_item("/goldstone-interfaces:interfaces")
        except Exception as e:
            logger.debug(f"failed to clear interface oper ds: {e}")

    def update_vlan_oper_ds(self, sess):
        logger.debug("updating vlan operational ds")

    #
    #        keys = self.sonic_db.keys(self.sonic_db.CONFIG_DB, pattern="VLAN|Vlan*")
    #        keys = keys if keys else []
    #
    #        for key in keys:
    #            _hash = _decode(key)
    #            name = _hash.split("|")[1]
    #            xpath = f"/goldstone-vlan:vlan/VLAN/VLAN_LIST[name='{name}']"
    #            vlanDATA = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, _hash)
    #            for key in vlanDATA:
    #                logger.debug(f"vlan config: {vlanDATA}")
    #                value = _decode(vlanDATA[key])
    #                key = _decode(key)
    #                if key == "members@":
    #                    member_list = value.split(",")
    #                    for member in member_list:
    #                        sess.set_item(f"{xpath}/members", member)
    #                else:
    #                    sess.set_item(f"{xpath}/{key}", value)
    #
    #        keys = self.sonic_db.keys(
    #            self.sonic_db.CONFIG_DB, pattern="VLAN_MEMBER|Vlan*|Ethernet*"
    #        )
    #        keys = keys if keys else []
    #
    #        for key in keys:
    #            _hash = _decode(key)
    #            name, ifname = _hash.split("|")[1:]
    #            xpath = f"/goldstone-vlan:vlan/VLAN_MEMBER/VLAN_MEMBER_LIST[name='{name}'][ifname='{ifname}']"
    #            member_data = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, _hash)
    #            for key in member_data:
    #                value = _decode(member_data[key])
    #                key = _decode(key)
    #                sess.set_item(f"{xpath}/{key}", value)

    def update_interface_oper_ds(self, sess):
        logger.debug("updating interface operational ds")

        prefix = "/goldstone-interfaces:interfaces"

        keys = self.sonic_db.keys(self.sonic_db.APPL_DB, pattern="PORT_TABLE:Ethernet*")
        keys = keys if keys else []

        for key in keys:
            _hash = _decode(key)
            name = _hash.split(":")[1]
            xpath = f"{prefix}/interface[name='{name}']"
            sess.set_item(f"{xpath}/config/name", name)
            sess.set_item(f"{xpath}/state/name", name)

        parent_dict = {}
        for key in self.get_config_db_keys("PORT|Ethernet*"):
            name = key.split("|")[1]
            intf_data = self.sonic_db.get_all(self.sonic_db.CONFIG_DB, key)
            logger.debug(f"config db entry: key: {key}, value: {intf_data}")

            xpath = f"{prefix}/interface[name='{name}']"
            xpath_subif_breakout = f"{xpath}/state/breakout"

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

                sess.set_item(f"{xpath_subif_breakout}/parent", parent)

        for key, value in parent_dict.items():
            xpath = f"{prefix}/interface[name='{key}']/config/breakout"
            v = self.get_redis_all("APPL_DB", f"PORT_TABLE:{key}")

            if "speed" in v:
                speed = speed_to_yang_val(v["speed"])
                logger.debug(f"key: {key}, speed: {speed}")
                sess.set_item(f"{xpath}/num-channels", value + 1)
                sess.set_item(f"{xpath}/channel-speed", speed)
            else:
                logger.warn(
                    f"Breakout interface:{key} doesnt has speed attribute in Redis"
                )

    def update_oper_ds(self):
        self.sess.switch_datastore("operational")

        self.clean_oper_ds(self.sess)
        self.update_vlan_oper_ds(self.sess)
        self.update_interface_oper_ds(self.sess)

        self.sess.apply_changes(wait=True)

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
        d = self.sess.get_data(xpath, no_subs=True)
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
                            try:
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
                            except:
                                pass

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
        d = self.sess.get_data(xpath, no_subs=True)
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
                self.update_oper_ds()
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
                    self.oper_cb,
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
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
        rest = logging.getLogger("rest")
        rest.setLevel(logging.INFO)
        k8s = logging.getLogger("kubernetes_asyncio.client.rest")
        k8s.setLevel(logging.INFO)
    #        sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
