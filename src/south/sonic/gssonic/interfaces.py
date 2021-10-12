from .core import *
from .sonic import *
import queue
import os
import json
import aioredis

logger = logging.getLogger(__name__)

REDIS_SERVICE_HOST = os.getenv("REDIS_SERVICE_HOST")
REDIS_SERVICE_PORT = os.getenv("REDIS_SERVICE_PORT")

SINGLE_LANE_INTERFACE_TYPES = ["CR", "LR", "SR", "KR"]
DOUBLE_LANE_INTERFACE_TYPES = ["CR2", "LR2", "SR2", "KR2"]
QUAD_LANE_INTERFACE_TYPES = ["CR4", "LR4", "SR4", "KR4"]
DEFAULT_INTERFACE_TYPE = "KR"


class IfChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-interfaces"
        assert xpath[0][1] == "interfaces"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        ifname = xpath[1][2][0][1]

        if ifname not in server.sonic.get_ifnames():
            raise sysrepo.SysrepoInvalArgError("Invalid Interface name")

        self.ifname = ifname

    def valid_speeds(self):
        valid_speeds = [40000, 100000]
        breakout_valid_speeds = []  # no speed change allowed for sub-interfaces
        if self.server.get_breakout_detail(self.ifname):
            return breakout_valid_speeds
        else:
            return valid_speeds


class AdminStatusHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            value = self.server.get_default("admin-status")
        logger.debug(f"set {self.ifname}'s admin-status to {value}")
        self.server.sonic.set_config_db(self.ifname, "admin-status", value)

    def revert(self, user):
        # TODO
        pass


class MTUHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            value = self.server.get_default("mtu")
        logger.debug(f"set {self.ifname}'s mtu to {value}")
        self.server.sonic.set_config_db(self.ifname, "mtu", value)


class FECHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            value = self.server.get_default("fec")
        logger.debug(f"set {self.ifname}'s fec to {value}")
        self.server.sonic.set_config_db(self.ifname, "fec", value)


class IfTypeHandler(IfChangeHandler):
    def validate(self, user):
        if self.type in ["created", "modified"]:
            self.server.validate_interface_type(self.ifname, self.change.value)

    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            try:
                v = self.server.get_breakout_detail(self.ifname)
                if not v:
                    raise KeyError
                if int(v["num-channels"]) == 4:
                    value = DEFAULT_INTERFACE_TYPE
                elif int(v["num-channels"]) == 2:
                    value = DEFAULT_INTERFACE_TYPE + "2"
                else:
                    raise sysrepo.SysrepoInvalArgError("Unsupported interface type")
            except (sysrepo.errors.SysrepoNotFoundError, KeyError):
                value = DEFAULT_INTERFACE_TYPE + "4"

        self.server.sonic.k8s.run_bcmcmd_port(self.ifname, "if=" + value)


class SpeedHandler(IfChangeHandler):
    def validate(self, user):
        if self.type in ["created", "modified"]:
            value = speed_yang_to_redis(self.change.value)
            valids = self.valid_speeds()
            if value not in valids:
                valids = [speed_redis_to_yang(v) for v in valids]
                raise sysrepo.SysrepoInvalArgError(
                    f"Invalid speed: {self.change.value}, candidates: {','.join(valids)}"
                )

    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = self.change.value
        else:
            value = "100G"
        self.server.sonic.set_config_db(self.ifname, "speed", value)
        self.server.sonic.k8s.update_bcm_portmap()


class VLANIfModeHandler(IfChangeHandler):
    def validate(self, user):
        cache = self.setup_cache(user)

        xpath = f"/goldstone-interfaces:interfaces/interface[name='{self.ifname}']"
        cache = libyang.xpath_get(cache, xpath, None)

        if self.type in ["created", "modified"]:
            config = cache["switched-vlan"]["config"]
            if config["interface-mode"] == "TRUNK" and "access-vlan" in config:
                raise sysrepo.SysrepoInvalArgError(
                    "invalid VLAN configuration. can't set TRUNK mode and access-vlan at the same time"
                )
            elif config["interface-mode"] == "ACCESS" and "trunk-vlans" in config:
                raise sysrepo.SysrepoInvalArgError(
                    "invalid VLAN configuration. can't set ACCESS mode and trunk-vlans at the same time"
                )
        else:
            if cache == None:
                return
            cache = cache.get("switched-vlan")
            if cache == None:
                return
            cache = cache.get("config")
            if cache == None:
                return
            if "access-vlan" in cache or "trunk-vlans" in cache:
                raise sysrepo.SysrepoInvalArgError(
                    "invalid VLAN configuration. must remove interface-mode, access-vlan, trunk-vlans leaves at once"
                )


class AccessVLANHandler(IfChangeHandler):
    def apply(self, user):
        for key in self.server.sonic.get_keys(f"VLAN_MEMBER|*|{self.ifname}"):
            v = self.server.sonic.hgetall("CONFIG_DB", key)
            if v.get("tagging_mode") == "untagged":
                vid = int(key.split("|")[1].replace("Vlan", ""))
                self.server.sonic.remove_vlan_member(self.ifname, vid)

        if self.type in ["created", "modified"]:
            self.server.sonic.set_vlan_member(
                self.ifname, self.change.value, "untagged"
            )


class TrunkVLANsHandler(IfChangeHandler):
    def apply(self, user):
        if self.type == "created":
            self.server.sonic.set_vlan_member(self.ifname, self.change.value, "tagged")
        elif self.type == "modified":
            logger.warn("trunk-vlans leaf-list should not trigger modified event.")
        else:
            vid = int(self.xpath[-1][2][0][1])
            v = self.server.sonic.hgetall(
                "CONFIG_DB", f"VLAN_MEMBER|Vlan{vid}|{self.ifname}"
            )
            if v.get("tagging_mode") == "tagged":
                self.server.sonic.remove_vlan_member(self.ifname, vid)


class AutoNegotiateHandler(IfChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            value = "yes" if self.change.value else "no"
        else:
            value = "no"  # default

        self.server.sonic.k8s.run_bcmcmd_port(self.ifname, "an=" + value)


class AutoNegotiateAdvertisedSpeedsHandler(IfChangeHandler):
    def validate(self, user):
        if self.type in ["created", "modified"]:
            value = speed_yang_to_redis(self.change.value)
            valids = self.valid_speeds()
            if value not in valids:
                valids = [speed_redis_to_yang(v) for v in valids]
                raise sysrepo.SysrepoInvalArgError(
                    f"Invalid speed: {change.value}, candidates: {','.join(valids)}"
                )

    def apply(self, user):
        self.setup_cache(user)
        v = user.get("needs_adv_speed_config", set())
        v.add(self.ifname)
        user["needs_adv_speed_config"] = v


class BreakoutHandler(IfChangeHandler):
    def validate(self, user):
        cache = self.setup_cache(user)

        if self.type in ["created", "modified"]:

            if "_1" not in self.ifname:
                raise sysrepo.SysrepoInvalArgError(
                    "breakout cannot be configured on a sub-interface"
                )

            if self.server.is_ufd_port(self.ifname):
                raise sysrepo.SysrepoInvalArgError(
                    "Breakout cannot be configured on the interface that is part of UFD"
                )

            xpath = f"/goldstone-interfaces:interfaces/interface[name='{self.ifname}']"
            cache = libyang.xpath_get(cache, xpath, None)
            config = cache["ethernet"]["breakout"]["config"]
            if "num-channels" not in config or "channel-speed" not in config:
                raise sysrepo.SysrepoInvalArgError(
                    "both num-channels and channel-speed must be set at once"
                )

    def apply(self, user):
        user["update-sonic"] = True


class InterfaceServer(ServerBase):
    def __init__(self, conn, sonic, servers):
        super().__init__(conn, "goldstone-interfaces")
        self.conn = conn
        self.task_queue = queue.Queue()
        self.sonic = sonic
        self.servers = servers
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "admin-status": AdminStatusHandler,
                        "name": NoOp,
                        "description": NoOp,
                    },
                    "ethernet": {
                        "config": {
                            "mtu": MTUHandler,
                            "fec": FECHandler,
                            "interface-type": IfTypeHandler,
                            "speed": SpeedHandler,
                        },
                        "breakout": {
                            "config": BreakoutHandler,
                        },
                        "auto-negotiate": {
                            "config": {
                                "enabled": AutoNegotiateHandler,
                                "advertised-speeds": AutoNegotiateAdvertisedSpeedsHandler,
                            },
                        },
                    },
                    "switched-vlan": {
                        "config": {
                            "interface-mode": VLANIfModeHandler,
                            "access-vlan": AccessVLANHandler,
                            "trunk-vlans": TrunkVLANsHandler,
                        }
                    },
                }
            }
        }

    def breakout_update_usonic(self, config):

        logger.debug("Starting to Update usonic's configMap and deployment")

        intfs = {}

        for i in config.get("interfaces", {}).get("interface", []):
            name = i["name"]
            b = i.get("ethernet", {}).get("breakout", {}).get("config", {})
            numch = b.get("num-channels", None)
            speed = speed_yang_to_redis(b.get("channel-speed", None))
            intfs[name] = (numch, speed)

        is_updated = self.sonic.k8s.update_usonic_config(intfs)

        # Restart deployment if configmap update is successful
        if is_updated:
            self.sonic.restart()

        return is_updated

    def pre(self, user):
        if self.sonic.is_rebooting:
            raise sysrepo.SysrepoLockedError("uSONiC is rebooting")

    def post(self, user):
        logger.info(f"post: {user}")
        if user.get("update-sonic"):
            self.sonic.is_rebooting = True
            self.task_queue.put(self.reconcile())
            return  # usonic will reboot. no need to proceed

        for ifname in user.get("needs_adv_speed_config", []):
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/advertised-speeds"
            config = libyang.xpath_get(user["cache"], xpath)
            if config:
                speeds = ",".join(v.replace("SPEED_", "").lower() for v in config)
                logger.debug(f"speeds: {speeds}")
            else:
                speeds = ""
            self.sonic.k8s.run_bcmcmd_port(ifname, f"adv={speeds}")

    async def reconcile(self):
        self.sess.switch_datastore("running")
        with self.sess.lock("goldstone-interfaces"):
            with self.sess.lock("goldstone-vlan"):
                await self._reconcile()

    async def _reconcile(self):
        config = self.get_running_data(self.top, default={}, strip=False)
        is_updated = self.breakout_update_usonic(config)
        if is_updated:
            await self.sonic.wait()
        else:
            self.sonic.cache_counters()
        self.sonic.is_rebooting = False

        prefix = "/goldstone-interfaces:interfaces/interface"
        for ifname in self.sonic.get_ifnames():
            xpath = f"{prefix}[name='{ifname}']"
            data = self.get_running_data(xpath, {})
            config = data.get("config", {})

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

        for server in self.servers:
            await server.reconcile()

    def get_default(self, key):
        ctx = self.sess.get_ly_ctx()
        keys = ["interfaces", "interface", "config", key]
        xpath = "".join(f"/goldstone-interfaces:{v}" for v in keys)

        try:
            for node in ctx.find_path(xpath):
                return node.default()
        except libyang.util.LibyangError:
            keys = ["interfaces", "interface", "ethernet", "config", key]
            xpath = "".join(f"/goldstone-interfaces:{v}" for v in keys)
            for node in ctx.find_path(xpath):
                return node.default()

    async def handle_tasks(self):
        while True:
            await asyncio.sleep(1)
            try:
                task = self.task_queue.get(False)
                await task
                self.task_queue.task_done()
            except queue.Empty:
                pass

    async def event_handler(self):

        redis = aioredis.from_url(f"redis://{REDIS_SERVICE_HOST}:{REDIS_SERVICE_PORT}")
        psub = redis.pubsub()
        await psub.psubscribe("__keyspace@0__:PORT_TABLE:Ethernet*")

        async for msg in psub.listen():
            if msg.get("pattern") == None:
                continue

            ifname = msg["channel"].decode().split(":")[-1]
            oper_status = self.sonic.get_oper_status(ifname)
            curr_oper_status = self.sonic.notif_if.get(ifname, "unknown")

            if oper_status == None or curr_oper_status == oper_status:
                continue

            eventname = "goldstone-interfaces:interface-link-state-notify-event"
            notif = {
                eventname: {
                    "if-name": ifname,
                    "oper-status": self.get_oper_status(ifname),
                }
            }

            ly_ctx = self.sess.get_ly_ctx()
            n = json.dumps(notif)
            logger.info(f"notification: {n}")
            dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
            self.sess.notification_send_ly(dnode)
            self.sonic.notif_if[ifname] = oper_status

    def clear_counters(self, xpath, input_params, event, priv):
        logger.debug(
            f"clear_counters: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        self.sonic.cache_counters()

    def stop(self):
        super().stop()

    async def start(self):
        await self.reconcile()
        tasks = await super().start()
        tasks.append(self.handle_tasks())
        tasks.append(self.event_handler())

        self.sess.subscribe_rpc_call(
            "/goldstone-interfaces:clear-counters",
            self.clear_counters,
        )

        return tasks

    def get_breakout_detail(self, ifname):
        xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/breakout/state"
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

    def get_ufd(self):
        xpath = "/goldstone-uplink-failure-detection:ufd-groups/ufd-group"
        return self.get_operational_data(xpath, [])

    def is_ufd_port(self, ifname, ufd_list=None):
        if ufd_list == None:
            ufd_list = self.get_ufd()

        for ufd_id in ufd_list:
            if port in ufd_id.get("config", {}).get("uplink", []):
                return True
            if port in ufd_id.get("config", {}).get("downlink", []):
                return True
        return False

    def is_downlink_port(self, ifname):
        ufd_list = self.get_ufd()
        for data in ufd_list:
            try:
                if ifname in data["config"]["downlink"]:
                    return True, list(data["config"]["uplink"])
            except:
                pass

        return False, None

    def get_oper_status(self, ifname):
        oper_status = self.sonic.get_oper_status(ifname)
        downlink_port, uplink_port = self.is_downlink_port(ifname)

        if downlink_port and uplink_port:
            uplink_oper_status = self.sonic.get_oper_status(uplink_port[0])
            if uplink_oper_status == "down":
                return "DORMANT"

        if oper_status != None:
            return oper_status.upper()

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
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

        interfaces = []
        for name in ifnames:
            interface = {
                "name": name,
                "config": {"name": name},
                "state": {"name": name},
                "ethernet": {"state": {}, "breakout": {"state": {}}},
            }

            # FIXME using "_1" is vulnerable to the interface nameing schema change
            if not name.endswith("_1") and name.find("_") != -1:
                _name = name.split("_")
                parent = _name[0] + "_1"
                interface["ethernet"]["breakout"]["state"] = {"parent": parent}
            else:
                config = self.get_running_data(
                    f"/goldstone-interfaces:interfaces/interface[name='{name}']/ethernet/breakout/config"
                )
                if config:
                    interface["ethernet"]["breakout"]["state"] = config

            interfaces.append(interface)

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
                    elif key == "speed":
                        intf["ethernet"]["state"][key] = speed_redis_to_yang(value)
                    elif key == "admin_status":
                        intf["state"]["admin-status"] = value.upper()
                    elif key in ["fec", "mtu"]:
                        intf["ethernet"]["state"][key] = value.upper()

                info = bcminfo.get(ifname, {})
                logger.debug(f"bcminfo: {info}")

                iftype = info.get("iftype")
                if iftype:
                    intf["ethernet"]["state"]["interface-type"] = iftype

                auto_nego = info.get("auto-nego")
                if auto_nego:
                    intf["ethernet"]["auto-negotiate"] = {"state": {"enabled": True}}
                    v = auto_nego.get("local", {}).get("fd")
                    if v:
                        intf["ethernet"]["auto-negotiate"]["state"][
                            "advertised-speeds"
                        ] = [speed_bcm_to_yang(e) for e in v]
                else:
                    intf["ethernet"]["auto-negotiate"] = {"state": {"enabled": False}}

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}
