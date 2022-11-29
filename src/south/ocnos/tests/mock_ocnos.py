import logging
from lxml import etree
from ncclient.xml_ import *
import xmltodict
import re
import libyang

logger = logging.getLogger(__name__)

namespaces = {
    "cml-data-types": "http://www.ipinfusion.com/yang/ocnos/cml-data-types",
    "ipi-if-types": "http://www.ipinfusion.com/yang/ocnos/ipi-if-types",
    "feature-list": "http://ipinfusion.com/ns/feature-list",
    "ipi-network-instance-types": "http://www.ipinfusion.com/yang/ocnos/ipi-network-instance-types",
    "ipi-network-instance": "http://www.ipinfusion.com/yang/ocnos/ipi-network-instance",
    "ipi-vrf": "http://www.ipinfusion.com/yang/ocnos/ipi-vrf",
    "ipi-interface": "http://www.ipinfusion.com/yang/ocnos/ipi-interface",
    "ipi-if-ethernet": "http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet",
    "ipi-if-ip": "http://www.ipinfusion.com/yang/ocnos/ipi-if-ip",
    "ipi-vlan-types": "http://www.ipinfusion.com/yang/ocnos/ipi-vlan-types",
    "ipi-bridge-types": "http://www.ipinfusion.com/yang/ocnos/ipi-bridge-types",
    "ipi-port-vlan": "http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan",
    "ipi-port-vlan-types": "http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan-types",
    "ipi-bridge": "http://www.ipinfusion.com/yang/ocnos/ipi-bridge",
    "ipi-qos-types": "http://www.ipinfusion.com/yang/ocnos/ipi-qos-types",
    "ipi-qos": "http://www.ipinfusion.com/yang/ocnos/ipi-qos",
    "ietf-inet-types": "urn:ietf:params:xml:ns:yang:ietf-inet-types",
    "ipi-vlan": "http://www.ipinfusion.com/yang/ocnos/ipi-vlan",
    "ietf-yang-types": "urn:ietf:params:xml:ns:yang:ietf-yang-types",
    "ipi-vxlan-types": "http://www.ipinfusion.com/yang/ocnos/ipi-vxlan-types",
    "ipi-vxlan": "http://www.ipinfusion.com/yang/ocnos/ipi-vxlan",
    "ipi-if-extended": "http://www.ipinfusion.com/yang/ocnos/ipi-if-extended",
}


class XmlData(object):
    def __init__(self, **kwargs):
        self.data = []


class MockConnection(object):
    def __init__(self):
        self.logs = []

    def edit_config(self, config):
        self.logs.append((config))

    def commit(self):
        pass


class MockOcNOS(object):
    def __init__(self, **kwargs):
        self.conn = MockConnection()

    def apply(self):
        pass

    def stop(self):
        pass

    def xpath2xml(self, xpath, value=None, delete_oper=False):
        xpath = list(libyang.xpath_split(xpath))
        if len(xpath) == 0:
            return None
        node = xpath[0][1]
        model = xpath[0][0]

        v = namespaces.get(model)
        if v:
            root = new_ele_ns(node, v)
        else:
            root = new_ele(node)

        cur = root
        for i, e in enumerate(xpath[1:]):
            if e[0]:
                v = namespaces.get(e[0])
                cur = sub_ele_ns(cur, e[1], v)
            else:
                cur = sub_ele(cur, e[1])
            for cond in e[2]:
                ccur = cur
                for cc in cond[0].split("/"):
                    ccur = sub_ele(ccur, cc)
                ccur.text = cond[1]

        if value and not delete_oper:
            cur.text = str(value)
        elif not value and delete_oper:
            cur.set("{urn:ietf:params:xml:ns:netconf:base:1.0}operation", "delete")
        elif value and delete_oper:
            cur.text = str(value)
            cur.set("{urn:ietf:params:xml:ns:netconf:base:1.0}operation", "delete")
        elif not value and not delete_oper:
            pass

        root_str = etree.tostring(root).decode()
        root_str = re.sub("ns\d+:", "", root_str)
        root_str = re.sub(":ns\d+", "", root_str)
        root_str = re.sub("nc:", "", root_str)
        root = etree.fromstring(root_str)

        logger.debug(f"xpath: {xpath}, value: {value} xml: {root_str}")
        return root
