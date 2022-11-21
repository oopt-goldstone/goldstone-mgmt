######################
# Defines for OcNOS
######################
BRIDGE_CUSTOMER_VLAN_TYPE = "customer"
BRIDGE_PROTOCOL_TYPE = "ieee-vlan-bridge"
INSTANCE_TYPE = "l2ni"
INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE = 1

######################
# XPATH OcNOS
######################
IPI_INTERFACE = "/ipi-interface:interfaces/interface[name='{}']"
IPI_INTERFACE_CONFIG_NAME = IPI_INTERFACE + "/config[name='{}']"
IPI_INTERFACE_CONFIG_SHUTDOWN = IPI_INTERFACE_CONFIG_NAME + "/shutdown"
IPI_INTERFACE_CONFIG_DESCRIPTION = IPI_INTERFACE_CONFIG_NAME + "/description"
IPI_INTERFACE_CONFIG_MTU = IPI_INTERFACE_CONFIG_NAME + "/mtu"
IPI_INTERFACE_ETHERNET_CONFIG = IPI_INTERFACE + "/ipi-if-ethernet:ethernet/config"
IPI_INTERFACE_ETHERNET_CONFIG_PORT_SPEED = IPI_INTERFACE_ETHERNET_CONFIG + "/port-speed"
IPI_INTERFACE_IPV4 = IPI_INTERFACE + "/ipi-if-ip:ipv4"
IPI_INTERFACE_IPV4_CONFIG = IPI_INTERFACE_IPV4 + "/config"
IPI_INTERFACE_IPV4_CONFIG_PRIMARY_ADDRESS = (
    IPI_INTERFACE_IPV4_CONFIG + "/primary-ip-addr"
)
IPI_INTERFACE_IPV4_SECONDARY_ADDRESS = (
    IPI_INTERFACE_IPV4 + "/secondary-addresses[ip-address='{}']"
)
IPI_INTERFACE_IPV4_SECONDARY_ADDRESS_CONFIG_IP_ADDRESS = (
    IPI_INTERFACE_IPV4_SECONDARY_ADDRESS + "/config/ip-address"
)
IPI_INTERFACE_CONFIG_SWITCHPORT = IPI_INTERFACE_CONFIG_NAME + "/enable-switchport"
IPI_PORT_VLAN_SWITCHED_VLAN = (
    "/ipi-port-vlan:port-vlan/switched-vlan[interface-mode='{}']"
)
IPI_PORT_VLAN_SWITCHED_VLAN_CONFIG_INTERFACE_MODE = (
    IPI_PORT_VLAN_SWITCHED_VLAN + "/config/interface-mode"
)
IPI_SWITCHED_VLAN_CONFIG = "/vlans/config/vlan-id"
IPI_PORT_VLAN_SWITCHED_VLAN_VLANS_CONFIG = (
    IPI_PORT_VLAN_SWITCHED_VLAN + IPI_SWITCHED_VLAN_CONFIG
)
IPI_INTERFACE_SWITCHED_VLAN = (
    "/ipi-interface:interfaces/interface/ipi-port-vlan:port-vlan/switched-vlan"
)
IPI_INTERFACE_SWITCHED_VLAN_CONFIG_VLAN_ID = (
    IPI_INTERFACE_SWITCHED_VLAN + "/vlans/config[vlan-id='{}']"
)
IPI_ALLOWED_VLAN_CONFIG = "/allowed-vlan/config/allowed-vlan-id"
IPI_INTERFACE_SWITCHED_VLAN_ALLOWED_VLAN_CONFIG = (
    IPI_INTERFACE_SWITCHED_VLAN + "/allowed-vlan/config"
)
IPI_PORT_VLAN_SWITCHED_VLAN_ALLOWED_VLAN_CONFIG = (
    IPI_PORT_VLAN_SWITCHED_VLAN + IPI_ALLOWED_VLAN_CONFIG
)
IPI_NETWORK_INSTANCE = "/ipi-network-instance:network-instances/network-instance[instance-name='{}'][instance-type='{}']"
IPI_NETWORK_INSTANCE_CONFIG = (
    IPI_NETWORK_INSTANCE + "/config[instance-name='{}'][instance-type='{}']"
)
IPI_BRIDGE = "/ipi-bridge:bridge"
IPI_BRIDGE_CONFIG_PROTOCOL = IPI_BRIDGE + "/config[protocol='{}']"
IPI_BRIDGE_VLAN = (
    IPI_NETWORK_INSTANCE + IPI_BRIDGE + "/ipi-vlan:vlans/vlan[vlan-id='{}']"
)
IPI_BRIDGE_VLAN_VLAN_ID = (
    IPI_NETWORK_INSTANCE + IPI_BRIDGE + "/ipi-vlan:vlans/vlan/vlan-id"
)
IPI_BRIDGE_VLAN_CONFIG = IPI_BRIDGE_VLAN + "/config/vlan-id"
IPI_BRIDGE_PORTS = IPI_BRIDGE + "/bridge-ports"
IPI_BRIDGE_PORTS_INTERFACE = IPI_BRIDGE_PORTS + "/interface[name='{}']"
IPI_BRIDGE_PORTS_INTERFACE_CONFIG_INTERFACE = (
    IPI_BRIDGE_PORTS_INTERFACE + "/config[name='{}']"
)
IPI_CUSTOMER_VLAN = "/customer-vlan"
IPI_CUSTOMER_VLAN_CONFIG_TYPE = IPI_CUSTOMER_VLAN + "/config/type"
IPI_CUSTOMER_VLAN_CONFIG_NAME = IPI_CUSTOMER_VLAN + "/config/name"
IPI_BRIDGE_VLANS_CUSTOMER_VLAN_STATE_TAGGED_INTERFACE = (
    IPI_BRIDGE_VLAN + IPI_CUSTOMER_VLAN + "/state/tagged-interface"
)

######################
# TAGs OcNOS
######################
TAG_IPI_INTERFACE = "{http://www.ipinfusion.com/yang/ocnos/ipi-interface}interface"
TAG_IPI_NETWORK_INSTANCE = (
    "{http://www.ipinfusion.com/yang/ocnos/ipi-network-instance}network-instance"
)
TAG_IPI_SWITCHED_VLAN = (
    "{http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan}switched-vlan"
)
TAG_IPI_VLAN = "{http://www.ipinfusion.com/yang/ocnos/ipi-vlan}vlan"

######################
# XPATH Goldstone
######################
GOLDSTONE_INTERFACE_TOP = "/goldstone-interfaces:interfaces/interface"
GS_VLAN = "/goldstone-vlan:vlans/vlan[vlan-id='{}']"
GS_IF_MODE_CONFIG = "/goldstone-interfaces:interfaces/interface[name='{}']/gs-vlan:switched-vlan/config/interface-mode"
GS_IF_ADMIN_STATUS_CONFIG = (
    "/goldstone-interfaces:interfaces/interface[name='{}']/config/admin-status"
)
GS_IF_AUTO_NEGOTIATE_CONFIG = "/goldstone-interfaces:interfaces/interface[name='{}']/ethernet/auto-negotiate/config/enabled"
GS_TRUNK_VLANS_CONFIG = "/goldstone-interfaces:interfaces/interface[name='{}']/gs-vlan:switched-vlan/config/trunk-vlans"
GS_ACCESS_VLAN_CONFIG = "/goldstone-interfaces:interfaces/interface[name='{}']/gs-vlan:switched-vlan/config/access-vlan"

GS_IF_ETH_SPEED = (
    "/goldstone-interfaces:interfaces/interface[name='{}']/ethernet/config/speed"
)
GS_IF_IPV4 = "/goldstone-interfaces:interfaces/interface[name='{}']/ipv4/address/ip"
GS_IF_IPV4_ADDR_PREFIX_LENGTH = (
    "/goldstone-interfaces:interfaces/interface[name='{}']/ipv4/address/prefix-length"
)

######################
# Attribute mapping
######################
SPEED_MAP = {
    "SPEED_100M": "100m",
    "SPEED_1000M": "1g",
    "SPEED_2500M": "2.5g",
    "SPEED_10G": "10g",
    "SPEED_20G": "20g",
    "SPEED_25G": "25g",
    "SPEED_40G": "40g",
    "SPEED_50G": "50g",
    "SPEED_100G": "100g",
}


def insert_xml(xml, target_xml, tag):
    item = [e for e in target_xml.iter() if e.tag == tag]
    if item:
        item[0].append(xml)


def get_all_trunk_vlans_id(trunk_vlans):
    trunk_vlans_set = set(trunk_vlans.split(","))
    multi_vlans = set(v for v in trunk_vlans_set if "-" in v)
    trunk_vlans_set = trunk_vlans_set - multi_vlans
    for m in multi_vlans:
        trunk_vlans_set = trunk_vlans_set | set(
            range(int(m.split("-")[0]), int(m.split("-")[1]) + 1)
        )
    ret = sorted([int(t) for t in trunk_vlans_set])
    return ret
