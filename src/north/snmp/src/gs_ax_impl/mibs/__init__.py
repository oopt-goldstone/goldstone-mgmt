import pprint
import re
import os
import logging

from swsssdk import SonicV2Connector
from swsssdk import SonicDBConfig
from swsssdk import port_util
#from swsssdk.port_util import get_index_from_str
from ax_interface.mib import MIBUpdater
from ax_interface.util import oid2tuple

logger = logging.getLogger(__name__)

COUNTERS_PORT_NAME_MAP = 'COUNTERS_PORT_NAME_MAP'
COUNTERS_QUEUE_NAME_MAP = 'COUNTERS_QUEUE_NAME_MAP'
LAG_TABLE = 'LAG_TABLE'
LAG_MEMBER_TABLE = 'LAG_MEMBER_TABLE'
LOC_CHASSIS_TABLE = 'LLDP_LOC_CHASSIS'
APPL_DB = 'APPL_DB'
ASIC_DB = 'ASIC_DB'
COUNTERS_DB = 'COUNTERS_DB'
CONFIG_DB = 'CONFIG_DB'
STATE_DB = 'STATE_DB'
SNMP_OVERLAY_DB = 'SNMP_OVERLAY_DB'

TABLE_NAME_SEPARATOR_COLON = ':'
TABLE_NAME_SEPARATOR_VBAR = '|'

SONIC_ETHERNET_RE_PATTERN = "^Ethernet(\d+_\d+$)"
"""
Ethernet-BP refers to BackPlane interfaces
in multi-asic platform.
"""
SONIC_ETHERNET_BP_RE_PATTERN = "^Ethernet-BP(\d+)$"
SONIC_VLAN_RE_PATTERN = "^Vlan(\d+)$"
SONIC_PORTCHANNEL_RE_PATTERN = "^PortChannel(\d+)$"
SONIC_MGMT_PORT_RE_PATTERN = "^eth(\d+)$"

# This is used in both rfc2737 and rfc3433
SENSOR_PART_ID_MAP = {
    "temperature":  1,
    "voltage":      2,
    "rx1power":     11,
    "rx2power":     21,
    "rx3power":     31,
    "rx4power":     41,
    "tx1bias":      12,
    "tx2bias":      22,
    "tx3bias":      32,
    "tx4bias":      42,
    "tx1power":     13,
    "tx2power":     23,
    "tx3power":     33,
    "tx4power":     43,
}

# IfIndex to OID multiplier for transceiver
IFINDEX_SUB_ID_MULTIPLIER = 1000

redis_kwargs = {'unix_socket_path': '/var/run/redis/redis.sock'}

class BaseIdx:
    ethernet_base_idx = 1
    vlan_interface_base_idx = 2000
    ethernet_bp_base_idx = 9000
    portchannel_base_idx = 1000
    mgmt_port_base_idx = 10000

def get_neigh_info(neigh_key):
    """
    split neigh_key string of the format:
    NEIGH_TABLE:device:ipv4_address
    """
    _, device, ip = neigh_key.split(':')
    return device, ip

def chassis_info_table(chassis_name):
    """
    :param: chassis_name: chassis name
    :return: chassis info entry for this chassis
    """

    return "CHASSIS_INFO" + TABLE_NAME_SEPARATOR_VBAR + chassis_name

def psu_info_table(psu_name):
    """
    :param: psu_name: psu name
    :return: psu info entry for this psu
    """

    return "PSU_INFO" + TABLE_NAME_SEPARATOR_VBAR + psu_name

def counter_table(sai_id):
    """
    :param if_name: given sai_id to cast.
    :return: COUNTERS table key.
    """
    return 'COUNTERS:oid:0x' + sai_id

def queue_table(sai_id):
    """
    :param sai_id: given sai_id to cast.
    :return: COUNTERS table key.
    """
    return 'COUNTERS:' + sai_id

def queue_key(port_index, queue_index):
    return str(port_index) + ':' + str(queue_index)

def transceiver_info_table(port_name):
    """
    :param: port_name: port name
    :return: transceiver info entry for this port
    """

    return "TRANSCEIVER_INFO" + TABLE_NAME_SEPARATOR_VBAR + port_name

def transceiver_dom_table(port_name):
    """
    :param: port_name: port name
    :return: transceiver dom entry for this port
    """

    return "TRANSCEIVER_DOM_SENSOR" + TABLE_NAME_SEPARATOR_VBAR + port_name

def lldp_entry_table(if_name):
    """
    :param if_name: given interface to cast.
    :return: LLDP_ENTRY_TABLE key.
    """
    return 'LLDP_ENTRY_TABLE:' + if_name


def if_entry_table(if_name):
    """
    :param if_name: given interface to cast.
    :return: PORT_TABLE key.
    """
    return 'PORT_TABLE:' + if_name


def lag_entry_table(lag_name):
    """
    :param lag_name: given lag to cast.
    :return: LAG_TABLE key.
    """
    return 'LAG_TABLE:' + lag_name


def mgmt_if_entry_table(if_name):
    """
    :param if_name: given interface to cast
    :return: MGMT_PORT_TABLE key
    """

    return 'MGMT_PORT|' + if_name


def mgmt_if_entry_table_state_db(if_name):
    """
    :param if_name: given interface to cast
    :return: MGMT_PORT_TABLE key
    """

    return 'MGMT_PORT_TABLE|' + if_name

def get_sai_id_key(namespace, sai_id):
    """
    inputs:
    namespace - string
    sai id - bytes
    Return type:
    bytes
    Return value: namespace:sai id or sai id
    """
    if namespace != '':
        return namespace + ':' + sai_id
    else:
        return sai_id

def split_sai_id_key(sai_id_key):
    """
    Input - bytes
    Return namespace string and sai id in byte string.
    """
    result = sai_id_key.split(':')
    if len(result) == 1:
        return '', sai_id_key
    else:
        return result[0], result[1]

def config(**kwargs):
    global redis_kwargs
    redis_kwargs = {k:v for (k,v) in kwargs.items() if k in ['unix_socket_path', 'host', 'port']}
    redis_kwargs['decode_responses'] = True

def init_db():
    """
    Connects to DB
    :return: db_conn
    """
    SonicDBConfig.load_sonic_global_db_config()
    # SyncD database connector. THIS MUST BE INITIALIZED ON A PER-THREAD BASIS.
    # Redis PubSub objects (such as those within swsssdk) are NOT thread-safe.
    db_conn = SonicV2Connector(**redis_kwargs)

    return db_conn

def init_mgmt_interface_tables(db_conn):
    """
    Initializes interface maps for mgmt ports
    :param db_conn: db connector
    :return: tuple of mgmt name to oid map and mgmt name to alias map
    """

    db_conn.connect(CONFIG_DB)
    db_conn.connect(STATE_DB)

    mgmt_ports_keys = db_conn.keys(CONFIG_DB, mgmt_if_entry_table('*'))

    if not mgmt_ports_keys:
        logger.debug('No managment ports found in {}'.format(mgmt_if_entry_table('')))
        return {}, {}

    mgmt_ports = [key.split(mgmt_if_entry_table(''))[-1] for key in mgmt_ports_keys]
    oid_name_map = {get_index_from_str(mgmt_name): mgmt_name for mgmt_name in mgmt_ports}
    logger.debug('Managment port map:\n' + pprint.pformat(oid_name_map, indent=2))

    if_alias_map = dict()

    for if_name in oid_name_map.values():
        if_entry = db_conn.get_all(CONFIG_DB, mgmt_if_entry_table(if_name), blocking=True)
        if_alias_map[if_name] = if_entry.get('alias', if_name)

    logger.debug("Management alias map:\n" + pprint.pformat(if_alias_map, indent=2))

    return oid_name_map, if_alias_map

def get_index_from_str(if_name):
    """
    OIDs are 1-based, interfaces are 0-based, return the 1-based index
    Ethernet N = N + 1
    Vlan N = N + 2000
    Ethernet_BP N = N + 9000
    PortChannel N = N + 1000
    eth N = N + 10000
    """
    patterns = {
        SONIC_ETHERNET_RE_PATTERN: BaseIdx.ethernet_base_idx,
        SONIC_ETHERNET_BP_RE_PATTERN: BaseIdx.ethernet_bp_base_idx,
        SONIC_VLAN_RE_PATTERN: BaseIdx.vlan_interface_base_idx,
        SONIC_PORTCHANNEL_RE_PATTERN: BaseIdx.portchannel_base_idx,
        SONIC_MGMT_PORT_RE_PATTERN: BaseIdx.mgmt_port_base_idx
    }

    for pattern, baseidx in patterns.items():
        match = re.match(pattern, if_name)
        if match:
            return int(match.group(1).split('_')[0]) + baseidx

def init_sync_d_interface_tables(db_conn):
    """
    Initializes interface maps for SyncD-connected MIB(s).
    :return: tuple(if_name_map, if_id_map, oid_map, if_alias_map)
    """
    if_id_map = {}
    if_name_map = {}

    # { if_name (SONiC) -> sai_id }
    # ex: { "Ethernet76" : "1000000000023" }
    if_name_map_util, if_id_map_util = port_util.get_interface_oid_map(db_conn)
    for if_name, sai_id in if_name_map_util.items():
        if_name_str = if_name
        if (re.match(SONIC_ETHERNET_RE_PATTERN, if_name_str) or \
                re.match(SONIC_ETHERNET_BP_RE_PATTERN, if_name_str)):
            if_name_map[if_name] = sai_id
        logger.debug(f"index: {get_index_from_str(if_name)}")
    # As sai_id is not unique in multi-asic platform, concatenate it with
    # namespace to get a unique key. Assuming that ':' is not present in namespace
    # string or in sai id.
    # sai_id_key = namespace : sai_id
    for sai_id, if_name in if_id_map_util.items():
        if (re.match(SONIC_ETHERNET_RE_PATTERN, if_name) or \
                re.match(SONIC_ETHERNET_BP_RE_PATTERN, if_name)):
            if_id_map[get_sai_id_key(db_conn.namespace, sai_id)] = if_name
    logger.debug("Port name map:\n" + pprint.pformat(if_name_map, indent=2))
    logger.debug("Interface name map:\n" + pprint.pformat(if_id_map, indent=2))

    # { OID -> if_name (SONiC) }
    oid_name_map = {get_index_from_str(if_name): if_name for if_name in if_name_map
                    # only map the interface if it's a style understood to be a SONiC interface.
                    if get_index_from_str(if_name) is not None}

    logger.debug("OID name map:\n" + pprint.pformat(oid_name_map, indent=2))

    # SyncD consistency checks.
    if not oid_name_map:
        # In the event no interface exists that follows the SONiC pattern, no OIDs are able to be registered.
        # A RuntimeError here will prevent the 'main' module from loading. (This is desirable.)
        message = "No interfaces found matching pattern '{}'. SyncD database is incoherent." \
            .format(SONIC_ETHERNET_RE_PATTERN)
        logger.error(message)
        raise RuntimeError(message)
    elif len(if_id_map) < len(if_name_map) or len(oid_name_map) < len(if_name_map):
        # a length mismatch indicates a bad interface name
        logger.warning("SyncD database contains incoherent interface names. Interfaces must match pattern '{}'"
                       .format(SONIC_ETHERNET_RE_PATTERN))
        logger.warning("Port name map:\n" + pprint.pformat(if_name_map, indent=2))


    if_alias_map = dict()

    for if_name in if_name_map:
        if_entry = db_conn.get_all(APPL_DB, if_entry_table(if_name), blocking=True)
        if_alias_map[if_name] = if_entry.get('alias', if_name)

    logger.debug("Chassis name map:\n" + pprint.pformat(if_alias_map, indent=2))

    return if_name_map, if_alias_map, if_id_map, oid_name_map

def init_sync_d_lag_tables(db_conn):
    """
    Helper method. Connects to and initializes LAG interface maps for SyncD-connected MIB(s).
    :param db_conn: database connector
    :return: tuple(lag_name_if_name_map, if_name_lag_name_map, oid_lag_name_map)
    """
    # { lag_name (SONiC) -> [ lag_members (if_name) ] }
    # ex: { "PortChannel0" : [ "Ethernet0", "Ethernet4" ] }
    lag_name_if_name_map = {}
    # { if_name (SONiC) -> lag_name }
    # ex: { "Ethernet0" : "PortChannel0" }
    if_name_lag_name_map = {}
    # { OID -> lag_name (SONiC) }
    oid_lag_name_map = {}

    db_conn.connect(APPL_DB)

    lag_entries = db_conn.keys(APPL_DB, "LAG_TABLE:*")

    if not lag_entries:
        return lag_name_if_name_map, if_name_lag_name_map, oid_lag_name_map

    for lag_entry in lag_entries:
        lag_name = lag_entry[len("LAG_TABLE:"):]
        lag_members = db_conn.keys(APPL_DB, "LAG_MEMBER_TABLE:%s:*" % lag_name)
        # TODO: db_conn.keys() should really return [] instead of None
        if lag_members is None:
            lag_members = []

        def member_name_str(val, lag_name):
            return val[len("LAG_MEMBER_TABLE:%s:" % lag_name):]

        lag_member_names = [member_name_str(m, lag_name) for m in lag_members]
        lag_name_if_name_map[lag_name] = lag_member_names
        for lag_member_name in lag_member_names:
            if_name_lag_name_map[lag_member_name] = lag_name

    for if_name in lag_name_if_name_map.keys():
        idx = get_index_from_str(if_name)
        if idx:
            oid_lag_name_map[idx] = if_name

    return lag_name_if_name_map, if_name_lag_name_map, oid_lag_name_map

def init_sync_d_queue_tables(db_conn):
    """
    Initializes queue maps for SyncD-connected MIB(s).
    :return: tuple(port_queues_map, queue_stat_map)
    """

    # { Port name : Queue index (SONiC) -> sai_id }
    # ex: { "Ethernet0:2" : "1000000000023" }
    queue_name_map = db_conn.get_all(COUNTERS_DB, COUNTERS_QUEUE_NAME_MAP, blocking=True)
    logger.debug("Queue name map:\n" + pprint.pformat(queue_name_map, indent=2))

    # Parse the queue_name_map and create the following maps:
    # port_queues_map -> {"port_index : queue_index" : sai_oid}
    # queue_stat_map -> {"port_index : queue stat table name" : {counter name : value}} 
    # port_queue_list_map -> {port_index: [sorted queue list]}
    port_queues_map = {}
    queue_stat_map = {}
    port_queue_list_map = {}

    for queue_name, sai_id in queue_name_map.items():
        port_name, queue_index = queue_name.split(':')
        queue_index = ''.join(i for i in queue_index if i.isdigit())
        port_index = get_index_from_str(port_name)
        key = queue_key(port_index, queue_index)
        port_queues_map[key] = sai_id

        queue_stat_name = queue_table(sai_id)
        queue_stat = db_conn.get_all(COUNTERS_DB, queue_stat_name, blocking=False)
        if queue_stat is not None:
            queue_stat_key = queue_key(port_index, queue_stat_name)
            queue_stat_map[queue_stat_key] = queue_stat

        if not port_queue_list_map.get(int(port_index)):
            port_queue_list_map[int(port_index)] = [int(queue_index)]
        else:
            port_queue_list_map[int(port_index)].append(int(queue_index))

    # SyncD consistency checks.
    if not port_queues_map:
        # In the event no queue exists that follows the SONiC pattern, no OIDs are able to be registered.
        # A RuntimeError here will prevent the 'main' module from loading. (This is desirable.)
        logger.error("No queues found in the Counter DB. SyncD database is incoherent.")
        raise RuntimeError('The port_queues_map is not defined')
    elif not queue_stat_map:
        logger.error("No queue stat counters found in the Counter DB. SyncD database is incoherent.")
        raise RuntimeError('The queue_stat_map is not defined')

    for queues in port_queue_list_map.values():
        queues.sort()

    return port_queues_map, queue_stat_map, port_queue_list_map

def get_device_metadata(db_conn):
    """
    :param db_conn: Sonic DB connector
    :return: device metadata
    """

    DEVICE_METADATA = "DEVICE_METADATA|localhost"
    db_conn.connect(db_conn.STATE_DB)

    device_metadata = db_conn.get_all(db_conn.STATE_DB, DEVICE_METADATA)
    return device_metadata

def get_transceiver_sub_id(ifindex):
    """
    Returns sub OID for transceiver. Sub OID is calculated as folows:
    +------------+------------+
    |Interface   |Index       |
    +------------+------------+
    |Ethernet[X] |X * 1000    |
    +------------+------------+
    ()
    :param ifindex: interface index
    :return: sub OID of a port calculated as sub OID = {{index}} * 1000
    """

    return (ifindex * IFINDEX_SUB_ID_MULTIPLIER, )

def get_transceiver_sensor_sub_id(ifindex, sensor):
    """
    Returns sub OID for transceiver sensor. Sub OID is calculated as folows:
    +-------------------------------------+------------------------------+
    |Sensor                               |Index                         |
    +-------------------------------------+------------------------------+
    |RX Power for Ethernet[X]/[LANEID]    |X * 1000 + LANEID * 10 + 1    |
    |TX Bias for Ethernet[X]/[LANEID]     |X * 1000 + LANEID * 10 + 2    |
    |Temperature for Ethernet[X]          |X * 1000 + 1                  |
    |Voltage for Ethernet[X]/[LANEID]     |X * 1000 + 2                  |
    +-------------------------------------+------------------------------+
    ()
    :param ifindex: interface index
    :param sensor: sensor key
    :return: sub OID = {{index}} * 1000 + {{lane}} * 10 + sensor id
    """

    transceiver_oid, = get_transceiver_sub_id(ifindex)
    return (transceiver_oid + SENSOR_PART_ID_MAP[sensor], )

def get_redis_pubsub(db_conn, db_name, pattern):
    redis_client = db_conn.get_redis_client(db_name)
    db = db_conn.get_dbid(db_name)
    pubsub = redis_client.pubsub()
    pubsub.psubscribe("__keyspace@{}__:{}".format(db, pattern))
    return pubsub

class RedisOidTreeUpdater(MIBUpdater):
    def __init__(self, prefix_str):
        super().__init__()

        self.db_conn = Namespace.init_namespace_dbs() 
        if prefix_str.startswith('.'):
            prefix_str = prefix_str[1:]
        self.prefix_str = prefix_str

    def get_next(self, sub_id):
        """
        :param sub_id: The 1-based sub-identifier query.
        :return: the next sub id.
        """
        raise NotImplementedError

    def reinit_data(self):
        """
        Subclass update loopback information
        """
        pass

    def update_data(self):
        """
        Update redis (caches config)
        Pulls the table references for each interface.
        """
        self.oid_list = []
        self.oid_map = {}

        keys = Namespace.dbs_keys(self.db_conn, SNMP_OVERLAY_DB, self.prefix_str + '*')
        # TODO: fix db_conn.keys to return empty list instead of None if there is no match
        if keys is None:
            keys = []

        for key in keys:
            oid = oid2tuple(key, dot_prefix=False)
            self.oid_list.append(oid)
            value = Namespace.dbs_get_all(self.db_conn, SNMP_OVERLAY_DB, key)
            if value['type'] in ['COUNTER_32', 'COUNTER_64']:
                self.oid_map[oid] = int(value['data'])
            else:
                raise ValueError("Invalid value type")

        self.oid_list.sort()

    def get_oidvalue(self, oid):
        if oid not in self.oid_map:
            return None
        return self.oid_map[oid]

class Namespace:
    @staticmethod
    def init_namespace_dbs():
        db_conn = []
        SonicDBConfig.load_sonic_global_db_config()
        for namespace in SonicDBConfig.get_ns_list():
            db = SonicV2Connector(use_unix_socket_path=True, namespace=namespace, decode_responses=True)
            db_conn.append(db)

        Namespace.connect_namespace_dbs(db_conn)
        return db_conn

    @staticmethod
    def get_namespace_db_map(dbs):
        """
        Return a map of namespace:db_conn
        """
        db_map = {}
        for db_conn in dbs:
            db_map[db_conn.namespace] = db_conn
        return db_map

    @staticmethod
    def connect_namespace_dbs(dbs):
        list_of_dbs = [APPL_DB, COUNTERS_DB, CONFIG_DB, STATE_DB, ASIC_DB, SNMP_OVERLAY_DB]
        for db_name in list_of_dbs:
            Namespace.connect_all_dbs(dbs, db_name)

    @staticmethod
    def connect_all_dbs(dbs, db_name):
        for db_conn in dbs:
            db_conn.connect(db_name)

    @staticmethod
    def dbs_keys(dbs, db_name, pattern='*'):
        """
        db keys function execute on global and all namespace DBs.
        """
        result_keys=[]
        for db_conn in dbs:
            keys = db_conn.keys(db_name, pattern)
            if keys is not None:
                result_keys.extend(keys)
        return result_keys

    @staticmethod
    def dbs_keys_namespace(dbs, db_name, pattern='*'):
        """
        dbs_keys_namespace function execute on global
        and all namespace DBs. Provides a map of keys
        and namespace(db index).
        """
        result_keys = {}
        for db_index in range(len(dbs)):
            keys = dbs[db_index].keys(db_name, pattern)
            if keys is not None:
                keys_ns = dict.fromkeys(keys, db_index)
                result_keys.update(keys_ns)
        return result_keys

    @staticmethod
    def dbs_get_all(dbs, db_name, _hash, *args, **kwargs):
        """
        db get_all function executed on global and all namespace DBs.
        """
        result = {}
        # If there are multiple namespaces, _hash might not be 
        # present in all namespace, ignore if not present in a
        # specfic namespace.
        if len(dbs) > 1:
            tmp_kwargs = kwargs.copy()
            tmp_kwargs['blocking'] = False
        else:
            tmp_kwargs = kwargs
        for db_conn in dbs:
            ns_result = db_conn.get_all(db_name, _hash, *args, **tmp_kwargs)
            if ns_result is not None:
                result.update(ns_result)
        return result

    @staticmethod
    def get_non_host_dbs(dbs):
        """
        From the list of all dbs, return the list of dbs
        which will have interface related tables.
        For single namespace db, return the single db.
        For multiple namespace dbs, return all dbs except the
        host namespace db which is the first db in the list.
        """
        if len(dbs) == 1:
            return dbs
        else:
            return dbs[1:]

    @staticmethod
    def get_sync_d_from_all_namespace(per_namespace_func, dbs):
        # return merged tuple of dictionaries retrieved from per
        # namespace functions.
        result_map = {}
        # list of return values
        result_list = []
        for db_conn in Namespace.get_non_host_dbs(dbs):
            ns_tuple = per_namespace_func(db_conn)
            for idx in range(len(ns_tuple)):
                if idx not in result_map:
                    result_map[idx] = ns_tuple[idx]
                else:
                    result_map[idx].update(ns_tuple[idx])
        for idx, ns_tuple_dict in result_map.items():
            result_list.append(ns_tuple_dict)
        return result_list

    @staticmethod
    def dbs_get_bridge_port_map(dbs, db_name):
        """
        get_bridge_port_map from all namespace DBs
        """
        if_br_oid_map = {}
        for db_conn in Namespace.get_non_host_dbs(dbs):
            if_br_oid_map_ns = port_util.get_bridge_port_map(db_conn)
            if_br_oid_map.update(if_br_oid_map_ns)
        return if_br_oid_map

    @staticmethod
    def dbs_get_vlan_id_from_bvid(dbs, bvid):
        for db_conn in Namespace.get_non_host_dbs(dbs):
            db_conn.connect('ASIC_DB')
            vlan_obj = db_conn.keys('ASIC_DB', "ASIC_STATE:SAI_OBJECT_TYPE_VLAN:" + bvid)
            if vlan_obj is not None:
                return port_util.get_vlan_id_from_bvid(db_conn, bvid)
