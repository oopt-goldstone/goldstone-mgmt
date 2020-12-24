import math
from enum import unique, Enum
from bisect import bisect_right

from sonic_ax_impl import mibs
from sonic_ax_impl.mibs import Namespace
from ax_interface import MIBMeta, ValueType, MIBUpdater, MIBEntry, SubtreeMIBEntry
from ax_interface.encodings import ObjectIdentifier

# Maps SNMP queue stat counters to SAI counters and type
CounterMap = {
    # Unicast send packets
    ('SAI_QUEUE_STAT_PACKETS', 'SAI_QUEUE_TYPE_UNICAST'): 1,
    # Unicast send bytes
    ('SAI_QUEUE_STAT_BYTES', 'SAI_QUEUE_TYPE_UNICAST'): 2,
    # Multicast send packets
    ('SAI_QUEUE_STAT_PACKETS','SAI_QUEUE_TYPE_MULTICAST'): 3,
    # Multicast send bytes
    ('SAI_QUEUE_STAT_BYTES','SAI_QUEUE_TYPE_MULTICAST'): 4,
    # Unicast dropped packets
    ('SAI_QUEUE_STAT_DROPPED_PACKETS','SAI_QUEUE_TYPE_UNICAST'): 5,
    # Unicast dropped bytes
    ('SAI_QUEUE_STAT_DROPPED_BYTES','SAI_QUEUE_TYPE_UNICAST'): 6,
    # Multicast dropped packets
    ('SAI_QUEUE_STAT_DROPPED_PACKETS','SAI_QUEUE_TYPE_MULTICAST'): 7,
    # Multicast dropped bytes
    ('SAI_QUEUE_STAT_DROPPED_BYTES', 'SAI_QUEUE_TYPE_MULTICAST'): 8
}


class DirectionTypes(int, Enum):
    """
    Queue direction types
    """
    INGRESS = 1
    EGRESS = 2


class QueueStatUpdater(MIBUpdater):
    """
    Class to update the info from Counter DB and to handle the SNMP request
    """
    def __init__(self):
        """
        init the updater
        """
        super().__init__()
        self.db_conn = Namespace.init_namespace_dbs()
        self.lag_name_if_name_map = {}
        self.if_name_lag_name_map = {}
        self.oid_lag_name_map = {}
        self.queue_type_map = {}

        self.if_name_map = {}
        self.if_alias_map = {}
        self.if_id_map = {}
        self.oid_name_map = {}

        self.port_queues_map = {}
        self.queue_stat_map = {}
        self.port_queue_list_map = {}

        self.mib_oid_to_queue_map = {}
        self.mib_oid_list = []

        self.queue_type_map = {}
        self.port_index_namespace = {}
        self.namespace_db_map = Namespace.get_namespace_db_map(self.db_conn)

    def reinit_data(self):
        """
        Subclass update interface information
        """
        self.if_name_map, \
        self.if_alias_map, \
        self.if_id_map, \
        self.oid_name_map = Namespace.get_sync_d_from_all_namespace(mibs.init_sync_d_interface_tables, self.db_conn)

        for sai_id_key in self.if_id_map:
            namespace, sai_id = mibs.split_sai_id_key(sai_id_key)
            if_idx = mibs.get_index_from_str(self.if_id_map[sai_id_key])
            self.port_index_namespace[if_idx] = namespace

        self.port_queues_map, self.queue_stat_map, self.port_queue_list_map = \
            Namespace.get_sync_d_from_all_namespace(mibs.init_sync_d_queue_tables, self.db_conn)

        for db_conn in Namespace.get_non_host_dbs(self.db_conn):
            self.queue_type_map[db_conn.namespace] = db_conn.get_all(mibs.COUNTERS_DB, "COUNTERS_QUEUE_TYPE_MAP", blocking=False)
 
    def update_data(self):
        """
        Update redis (caches config)
        Pulls the table references for each queue.
        """
        for queue_key, sai_id in self.port_queues_map.items():
            queue_stat_name = mibs.queue_table(sai_id)
            port_index, _ = queue_key.split(':')
            queue_stat_idx = mibs.queue_key(port_index, queue_stat_name)
            namespace = self.port_index_namespace[int(port_index)]
            queue_stat = self.namespace_db_map[namespace].get_all( \
                    mibs.COUNTERS_DB, queue_stat_name, blocking=False)
            if queue_stat is not None:
                self.queue_stat_map[queue_stat_idx] = queue_stat
            else:
                del self.queue_stat_map[queue_stat_idx]

        self.update_stats()

    def update_stats(self):
        """
        Update statistics.
        1. Get and sort port list to keep the order in MIB
        2. Prepare OID and get a statistic for each queue of each port
        3. Get and sort LAG ports list to keep the order in MIB
        4. Prepare OID for LAG and prepare a statistic for each queue of each LAG port
        """
        # Clear previous data
        self.mib_oid_to_queue_map = {}
        self.mib_oid_list = []

        # Sort the ports to keep the OID order in the MIB
        if_range = list(self.oid_name_map.keys())
        # Update queue counters for port
        for if_index in if_range:
            if if_index not in self.port_queue_list_map:
                # Port does not has a queues, continue..
                continue
            if_queues = self.port_queue_list_map[if_index]
            namespace = self.port_index_namespace[if_index]

            # The first half of queue id is for ucast, and second half is for mcast
            # To simulate vendor OID, we wrap queues by half distance
            pq_count = math.ceil((max(if_queues) + 1) / 2)

            for queue in if_queues:
                # Get queue type and statistics
                queue_sai_oid = self.port_queues_map[mibs.queue_key(if_index, queue)]
                queue_stat_table_name = mibs.queue_table(queue_sai_oid)
                queue_stat_key = mibs.queue_key(if_index, queue_stat_table_name)
                queue_type = self.queue_type_map[namespace].get(queue_sai_oid)
                queue_stat = self.queue_stat_map.get(queue_stat_key, {})

                # Add supported counters to MIBs list and store counters values
                for (counter, counter_type), counter_mib_id in CounterMap.items():
                    # Only egress queues are supported
                    mib_oid = (if_index, int(DirectionTypes.EGRESS), (queue % pq_count) + 1, counter_mib_id)

                    counter_value = 0
                    if queue_type == counter_type:
                        counter_value = int(queue_stat.get(counter, 0))

                        if mib_oid in self.mib_oid_to_queue_map:
                            continue
                        self.mib_oid_list.append(mib_oid)
                        self.mib_oid_to_queue_map[mib_oid] = counter_value

        self.mib_oid_list.sort()

    def get_next(self, sub_id):
        """
        :param sub_id: The 1-based sub-identifier query.
        :return: the next sub id.
        """

        right = bisect_right(self.mib_oid_list, sub_id)
        if right >= len(self.mib_oid_list):
            return None

        return self.mib_oid_list[right]

    def handle_stat_request(self, sub_id):
        """
        :param sub_id: The 1-based sub-identifier query.
        :return: the counter for the respective sub_id/table.
        """
        # if_index, if_direction, queue_index and counter id should be passed

        if sub_id in self.mib_oid_to_queue_map:
            return self.mib_oid_to_queue_map[sub_id] & 0xffffffffffffffff
        else:
            return None

class csqIfQosGroupStatsTable(metaclass=MIBMeta, prefix='.1.3.6.1.4.1.9.9.580.1.5.5'):
    """
    'csqIfQosGroupStatsTable' http://oidref.com/1.3.6.1.4.1.9.9.580.1.5.5
    """

    queue_updater = QueueStatUpdater()

    # csqIfQosGroupStatsTable = '1.3.6.1.4.1.9.9.580.1.5.5'
    # csqIfQosGroupStatsEntry = '1.3.6.1.4.1.9.9.580.1.5.5.1.4'

    queue_stat_request = \
        SubtreeMIBEntry('1.4', queue_updater, ValueType.COUNTER_64, queue_updater.handle_stat_request)
