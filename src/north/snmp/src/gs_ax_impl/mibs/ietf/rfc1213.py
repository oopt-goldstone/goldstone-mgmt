from goldstone.lib.connector.sysrepo import Connector as SysrepoConnector
from goldstone.lib.connector import Error

from enum import unique, Enum
from bisect import bisect_right
from natsort import natsorted

from ... import mibs

from ax_interface.mib import (
    MIBMeta,
    ValueType,
    MIBUpdater,
    MIBEntry,
    SubtreeMIBEntry,
)

from ax_interface.encodings import ObjectIdentifier

sysrepo_conn = SysrepoConnector()


@unique
class IfTypes(int, Enum):
    """IANA ifTypes"""

    ethernetCsmacd = 6
    ieee8023adLag = 161


class SystemUpdater(MIBUpdater):
    def __init__(self):
        self.range = [(i,) for i in range(1, 10)]
        self.update_counter = 0
        self.reinit_rate = 0

    def reinit_data(self):
        return

    def update_data(self):
        return

    def get_next(self, sub_id):
        """
        :param sub_id: The 1-based sub-identifier query.
        :return: the next sub id.
        """
        right = bisect_right(self.range, sub_id)
        if right == len(self.range):
            return None
        return self.range[right]

    def system_desc(self):
        version = "Init"
        sysDescription = "Goldstone Version"

        xpath = "/goldstone-system:system/state/software-version"
        try:
            version = sysrepo_conn.get(xpath)
        except Error as e:
            mibs.logger.warning(f"sysDesc Exception: {e}")

        return f"{sysDescription} {version}"

    def sys_objectid(self):
        # return "OID: iso.3.6.1.4.1.8072.3.2.10"
        return ObjectIdentifier.null_oid()

    def get_uptime(self):
        # return '(8301) 0:01:23.01'
        return 0

    def get_contact(self):
        return "GoldstoneRoot"

    def get_name(self):
        return "GoldstoneSNMP"

    def get_location(self):
        return "unknown"

    def get_services(self):
        return 4

    def get_oids(self, sub_id):
        """
        :param sub_id: The 1-based sub-identifier query.
        :return: the 0-based interface ID.
        """
        oid_map = [
            (1, 3, 6, 1, 6, 3, 11, 3, 1, 1),
            (1, 3, 6, 1, 6, 3, 15, 2, 1, 1),
            (1, 3, 6, 1, 6, 3, 10, 3, 1, 1),
            (1, 3, 6, 1, 6, 3, 1),
            (1, 3, 6, 1, 6, 3, 16, 2, 2, 1),
            (1, 3, 6, 1, 2, 1, 49),
            (1, 3, 6, 1, 2, 1, 4),
            (1, 3, 6, 1, 2, 1, 50),
            (1, 3, 6, 1, 6, 3, 13, 3, 1, 3),
            (1, 3, 6, 1, 2, 1, 92),
        ]
        mibs.logger.warning("SubId in get_oids '{}'.".format(sub_id))
        if sub_id:
            return oid_map[sub_id % 10]
        else:
            return oid_map[0]

    def get_descriptions(self, sub_id):
        desc_map = [
            "The MIB for Message Processing and Dispatching.",
            "The management information definitions for the SNMP User-based Security Model.",
            "The SNMP Management Architecture MIB.",
            "The MIB module for SNMPv2 entities",
            "View-based Access Control Model for SNMP.",
            "The MIB module for managing TCP implementations",
            "The MIB module for managing IP and ICMP implementations",
            "The MIB module for managing UDP implementations",
            "The MIB modules for managing SNMP Notification, plus filtering.",
            "The MIB module for logging SNMP Notifications.",
        ]

        if sub_id:
            return desc_map[sub_id % 10]


class SystemMIB(metaclass=MIBMeta, prefix=".1.3.6.1.2.1.1.1"):
    """
    'interfaces' https://tools.ietf.org/html/rfc1213#section-3.4
    """

    sys_updater = SystemUpdater()

    sysDescr = MIBEntry("0", ValueType.OCTET_STRING, sys_updater.system_desc)


class InterfacesUpdater(MIBUpdater):
    def __init__(self):
        super().__init__()
        self.interfaces = []

    def reinit_data(self):
        xpath = "/goldstone-interfaces:interfaces/interface"
        self.interfaces = []
        try:
            names = sysrepo_conn.get_operational(xpath + "/name")
            ifs = []
            for name in names:
                ifs.append(sysrepo_conn.get_operational(xpath + f"[name='{name}']"))
            self.interfaces = natsorted(ifs, key=lambda v: v["name"])
        except Error as e:
            mibs.logger.warning(f"reinit_data Exception: {e}")

    def update_data(self):
        self.reinit_data()

    def get_next(self, sub_id):
        if sub_id == ():
            return (1,)
        if sub_id[0] < len(self.interfaces):
            return (sub_id[0] + 1,)
        return ()

    def get_if_number(self):
        return len(self.interfaces)

    def if_index(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        return sub_id[0]

    def interface_description(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        interface = self.interfaces[sub_id[0] - 1]
        return interface["name"]

    def get_if_type(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        interface = self.interfaces[sub_id[0] - 1]
        if interface.get("ethernet", {}).get("state"):
            return IfTypes.ethernetCsmacd

    def get_mtu(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        i = self.interfaces[sub_id[0] - 1]
        return int(i.get("ethernet", {}).get("state", {}).get("mtu", 0))

    def get_speed_bps(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        i = self.interfaces[sub_id[0] - 1]
        speed = i.get("ethernet", {}).get("state", {}).get("speed")
        if speed:
            speed = speed.split("_")[-1]
            if "G" in speed:
                return int(speed.split("G")[0]) * 1000
            elif "M" in speed:
                return int(speed.split("M")[0])

    def _to_snmp_status(self, value):
        status_map = {
            "up": 1,
            "down": 2,
            "testing": 3,
            "unknown": 4,
            "dormant": 5,
            "notPresent": 6,
            "lowerLayerDown": 7,
        }
        return status_map.get(value.lower(), 4)

    def get_admin_status(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        i = self.interfaces[sub_id[0] - 1]
        return self._to_snmp_status(i.get("state", {}).get("admin-status"))

    def get_oper_status(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        i = self.interfaces[sub_id[0] - 1]
        return self._to_snmp_status(i.get("state", {}).get("oper-status"))

    def get_phys_address(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        return ""

    def get_last_change(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        return 0

    def get_counters(self, sub_id, field):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        i = self.interfaces[sub_id[0] - 1]
        return i.get("state", {}).get("counters", {}).get("in-octets", 0)

    def get_in_octets(self, sub_id):
        return self.get_counters(sub_id, "in-octets")

    def get_in_ucast(self, sub_id):
        return self.get_counters(sub_id, "in-unicast-pkts")

    def get_in_n_ucast(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        return self.get_counters(sub_id, "in-multicast-pkts") + self.get_counters(
            sub_id, "in-broadcast-pkts"
        )

    def get_in_discards(self, sub_id):
        return self.get_counters(sub_id, "in-discards")

    def get_in_errors(self, sub_id):
        return self.get_counters(sub_id, "in-errors")

    def get_in_unknown(self, sub_id):
        return self.get_counters(sub_id, "in-unknown-protos")

    def get_out_octets(self, sub_id):
        return self.get_counters(sub_id, "out-octets")

    def get_out_ucast(self, sub_id):
        return self.get_counters(sub_id, "out-unicast-pkts")

    def get_out_n_ucast(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        return self.get_counters(sub_id, "out-multicast-pkts") + self.get_counters(
            sub_id, "out-broadcast-pkts"
        )

    def get_out_discards(self, sub_id):
        return self.get_counters(sub_id, "out-discards")

    def get_out_errors(self, sub_id):
        return self.get_counters(sub_id, "out-errors")

    def get_out_unknown(self, sub_id):
        return self.get_counters(sub_id, "out-unknown-protos")

    def get_out_qlen(self, sub_id):
        return self.get_counters(sub_id, "out-q-len")

    def get_specific(self, sub_id):
        if sub_id == () or sub_id[0] > len(self.interfaces):
            return None
        return ObjectIdentifier.null_oid()


class InterfacesMIB(metaclass=MIBMeta, prefix=".1.3.6.1.2.1.2"):
    """
    'interfaces' https://tools.ietf.org/html/rfc1213#section-3.5
    """

    if_updater = InterfacesUpdater()

    # (subtree, value_type, callable_, *args, handler=None)
    ifNumber = MIBEntry("1", ValueType.INTEGER, if_updater.get_if_number)

    # ifTable ::= { interfaces 2 }
    # ifEntry ::= { ifTable 1 }

    ifIndex = SubtreeMIBEntry(
        "2.1.1", if_updater, ValueType.INTEGER, if_updater.if_index
    )

    ifDescr = SubtreeMIBEntry(
        "2.1.2", if_updater, ValueType.OCTET_STRING, if_updater.interface_description
    )

    ifType = SubtreeMIBEntry(
        "2.1.3", if_updater, ValueType.INTEGER, if_updater.get_if_type
    )

    ifMtu = SubtreeMIBEntry("2.1.4", if_updater, ValueType.INTEGER, if_updater.get_mtu)

    ifSpeed = SubtreeMIBEntry(
        "2.1.5", if_updater, ValueType.GAUGE_32, if_updater.get_speed_bps
    )

    ifPhysAddress = SubtreeMIBEntry(
        "2.1.6", if_updater, ValueType.OCTET_STRING, if_updater.get_phys_address
    )

    ifAdminStatus = SubtreeMIBEntry(
        "2.1.7", if_updater, ValueType.INTEGER, if_updater.get_admin_status
    )

    ifOperStatus = SubtreeMIBEntry(
        "2.1.8", if_updater, ValueType.INTEGER, if_updater.get_oper_status
    )

    ifLastChange = SubtreeMIBEntry(
        "2.1.9", if_updater, ValueType.TIME_TICKS, if_updater.get_last_change
    )

    ifInOctets = SubtreeMIBEntry(
        "2.1.10",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_in_octets,
    )

    ifInUcastPkts = SubtreeMIBEntry(
        "2.1.11",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_in_ucast,
    )

    ifInNUcastPkts = SubtreeMIBEntry(
        "2.1.12",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_in_n_ucast,
    )

    ifInDiscards = SubtreeMIBEntry(
        "2.1.13",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_in_discards,
    )

    ifInErrors = SubtreeMIBEntry(
        "2.1.14",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_in_errors,
    )

    ifInUnknownProtos = SubtreeMIBEntry(
        "2.1.15",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_in_unknown,
    )

    ifOutOctets = SubtreeMIBEntry(
        "2.1.16",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_out_octets,
    )

    ifOutUcastPkts = SubtreeMIBEntry(
        "2.1.17",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_out_ucast,
    )

    ifOutNUcastPkts = SubtreeMIBEntry(
        "2.1.18", if_updater, ValueType.COUNTER_32, if_updater.get_out_n_ucast
    )

    ifOutDiscards = SubtreeMIBEntry(
        "2.1.19", if_updater, ValueType.COUNTER_32, if_updater.get_out_discards
    )

    ifOutErrors = SubtreeMIBEntry(
        "2.1.20",
        if_updater,
        ValueType.COUNTER_32,
        if_updater.get_out_errors,
    )

    ifOutQLen = SubtreeMIBEntry(
        "2.1.21",
        if_updater,
        ValueType.GAUGE_32,
        if_updater.get_out_qlen,
    )

    ifSpecific = SubtreeMIBEntry(
        "2.1.22", if_updater, ValueType.OBJECT_IDENTIFIER, if_updater.get_specific
    )
