from .k8s_api import incluster_apis
import swsssdk
import logging
import asyncio

from goldstone.lib.errors import InvalArgError, InternalError, UnsupportedError

logger = logging.getLogger(__name__)

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
    return str(string)


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
        raise InvalArgError(f"unsupported speed: {yang_val}")


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
    raise InvalArgError(f"unsupported speed: {speed}")


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

    async def init(self):
        await self.k8s.update_bcm_portmap()

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
            raise InvalArgError(f"vlan {vid} has dependencies")
        db = self.sonic_db.CONFIG_DB
        self.sonic_db.delete(db, f"VLAN|Vlan{vid}")

    def set_vlan_member(self, ifname, vid, mode):
        config = self.hgetall("CONFIG_DB", f"VLAN|Vlan{vid}")

        if not config:
            raise InvalArgError(f"vlan {vid} not found")

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
        v = _decode(
            self.sonic_db.get(
                self.sonic_db.APPL_DB, f"PORT_TABLE:{ifname}", "oper_status"
            )
        )
        return v if v != "None" else None
