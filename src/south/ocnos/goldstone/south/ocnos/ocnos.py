import logging
from goldstone.lib.connector.netconf import (
    Session,
    Connector as NETCONFConnector,
    str2bool,
    get_schema,
)
from goldstone.lib.errors import Error
from pathlib import Path
from lxml import etree
from ncclient.xml_ import *
import xmltodict
import libyang
import pkgutil
import re

logger = logging.getLogger(__name__)


class OcNOSConnector(NETCONFConnector):
    def __init__(self, **kwargs):
        if "host" not in kwargs:
            raise Error("missing host option")
        schema_dir = kwargs.pop("schema_dir", None)
        if schema_dir == None:
            raise Error("missing schema_dir option")
        str2bool(kwargs, "hostkey_verify")
        self._connect_args = kwargs
        self.sess = self.new_session()
        self.conn = self.sess.netconf_conn
        self._models = {}
        # TODO: it is important to make sure the schema dir exists before
        # creating the libyang context. Otherwise, libyang won't
        # search for the schemas in the directory.

        logger.info("getting schemas...")

        schema_names = [
            "cml-data-types",
            "ipi-if-types",
            "feature-list",
            "ipi-network-instance-types",
            "ipi-network-instance",
            "ipi-vrf",
            "ipi-interface",
            "ipi-if-ethernet",
            "ipi-if-ip",
            "ipi-vlan-types",
            "ipi-bridge-types",
            "ipi-port-vlan",
            "ipi-port-vlan-types",
            "ipi-bridge",
            "ipi-qos-types",
            "ipi-qos",
            "ietf-inet-types",
            "ipi-vlan",
            "ietf-yang-types",
            "ipi-vxlan-types",
            "ipi-vxlan",
            "ipi-if-extended",
        ]

        schemas = []
        for sn in schema_names:
            # The "feature-list" is loaded from local file which includes limited feature.
            # This is because libyang cannot parse original one due to storing limitation.
            if sn == "feature-list":
                schema = pkgutil.get_data("data", "feature-list.yang").decode()
                continue
            schema = get_schema(self.conn, schema_dir, sn, revision=None)
            schemas.append(schema)
        data = dict(zip(schema_names, schemas))

        for sn, schema in data.items():
            m = {}
            m["name"] = sn
            if sn not in self._models:
                self._models[sn] = []
            m["import-only"] = False
            m["filename"] = f"{sn}.yang"
            m["namespace"] = f"http://www.ipinfusion.com/yang/ocnos/{sn}"
            m["schema"] = schema
            self._models[m["name"]].append(m)
        # TODO: load schema to use its info

    def stop(self):
        self.sess.stop()

    # Overwritten xpath2xml function for ocnos.
    def xpath2xml(self, xpath, value=None, delete_oper=False):
        xpath = list(libyang.xpath_split(xpath))
        if len(xpath) == 0:
            return None
        node = xpath[0][1]
        model = xpath[0][0]
        v = self._models.get(model)
        if v:
            root = new_ele_ns(node, v[0]["namespace"])
        else:
            root = new_ele(node)

        cur = root
        for i, e in enumerate(xpath[1:]):
            if e[0]:
                v = self._models.get(e[0])
                cur = sub_ele_ns(cur, e[1], v[0]["namespace"])
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

        # FIXME: consider better way to do following strip.
        # TODO: investigate how ncclient inserts ns/nc char.
        root_str = etree.tostring(root).decode()
        root_str = re.sub("ns\d+:", "", root_str)
        root_str = re.sub(":ns\d+", "", root_str)
        root_str = re.sub("nc:", "", root_str)
        root = etree.fromstring(root_str)

        logger.info(f"xpath: {xpath}, value: {value} xml: {root_str}")

        return root

    # TODO: when xform is given, use it to xlate XML to Python dict.
    # Otherwise, use libyang to do the parsing
    def _get(self, xpath, nss, ds):
        options = {}
        xml = self.xpath2xml(xpath)
        # subtree/xml is used as filter, not xpath.
        if ds == "operational":
            v = self.conn.get(filter=("subtree", xml))
            options["get"] = True
        elif ds == "running":
            v = self.conn.get_config(source=ds, filter=("subtree", xml))
            options["getconfig"] = True
        else:
            raise Error(f"not supported ds: {ds}")

        logger.info(f"data_xml: {v}")
        data = xmltodict.parse(str(v)).get("rpc-reply").get("data")
        # TODO: parse data using schema info.
        return data
