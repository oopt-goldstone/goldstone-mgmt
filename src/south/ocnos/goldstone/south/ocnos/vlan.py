from goldstone.lib.core import *
import sysrepo
import ncclient
from ncclient.xml_ import *
import libyang
import re
from lxml import etree
from .util import *

logger = logging.getLogger(__name__)


class VlanChangeHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath = change.xpath

        xpath_list = list(libyang.xpath_split(xpath))

        assert xpath_list[0][0] == "goldstone-vlan"
        assert xpath_list[0][1] == "vlans"
        assert xpath_list[1][1] == "vlan"
        assert xpath_list[1][2][0][0] == "vlan-id"
        self.vlan_id = xpath_list[1][2][0][1]
        logger.debug(f"VLAN-ID: {self.vlan_id}")


class VlanIdHandler(VlanChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            try:
                self.set_vlan_id(self.vlan_id)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for set vlan-id: {e.message}"
                )
            logger.debug(f"set {self.vlan_id} vlan-id")
        else:
            try:
                self.unset_vlan_id(self.vlan_id)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for unset vlan-id: {e.message}"
                )
            logger.debug(f"unset {self.vlan_id} vlan-id")

    def set_vlan_id(self, value):
        xpath_bridge_vlan = IPI_BRIDGE_VLAN_CONFIG.format(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, value
        )
        xpath_customer_vlan = IPI_CUSTOMER_VLAN_CONFIG_TYPE
        xml_bridge_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_bridge_vlan, value=value
        )
        xml_customer_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_customer_vlan, value=BRIDGE_CUSTOMER_VLAN_TYPE
        )

        insert_xml(xml_customer_vlan, xml_bridge_vlan, TAG_IPI_VLAN)

        config = new_ele("config")
        config.append(xml_bridge_vlan)
        logger.debug(
            f"Sending xml for vlan id configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def unset_vlan_id(self, value):
        xpath_bridge_vlan = IPI_BRIDGE_VLAN.format(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, value
        )
        xml_bridge_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_bridge_vlan, delete_oper=True
        )

        config = new_ele("config")
        config.append(xml_bridge_vlan)
        logger.debug(
            f"Sending xml for delete vlan id configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def validate(self, user):
        if self.type != "deleted":
            return

        used_access_vids = self.server.ocnos_conn.get(
            IPI_INTERFACE_SWITCHED_VLAN_CONFIG_VLAN_ID.format(self.vlan_id),
            ds="running",
        )
        used_access_vids = [] if used_access_vids is None else used_access_vids
        if len(used_access_vids) > 0:
            raise sysrepo.SysrepoInvalArgError(
                f"Cannot delete vlan {self.vlan_id} since it is in use"
            )

        used_trunk_vids = self.server.ocnos_conn.get(
            IPI_INTERFACE_SWITCHED_VLAN_ALLOWED_VLAN_CONFIG, ds="running"
        )
        if used_trunk_vids:
            used_trunk_vids = (
                used_trunk_vids if type(used_trunk_vids) == list else [used_trunk_vids]
            )
        else:
            used_trunk_vids = []
        for e in used_trunk_vids:
            trunk_vids = get_all_trunk_vlans_id(e["allowed-vlan-id"])
            if int(self.vlan_id) in trunk_vids:
                raise sysrepo.SysrepoInvalArgError(
                    f"Cannot delete vlan {self.vlan_id} since it is in use"
                )


class VlanNameHandler(VlanChangeHandler):
    def apply(self, user):
        if self.type in ["created", "modified"]:
            try:
                value = self.change.value
                self.set_vlan_name(value)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for set vlan name: {e.message}"
                )
            logger.debug(f"set {self.vlan_id} vlan-id with name {value}")
        else:
            try:
                self.unset_vlan_name(user)
            except ncclient.operations.RPCError as e:
                self.server.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Edit-config failed in OcNOS for unset vlan name: {e.message}"
                )
            logger.debug(f"unset {self.vlan_id} vlan-id name")

    def set_vlan_name(self, value):
        xpath_bridge_vlan = IPI_BRIDGE_VLAN_CONFIG.format(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, self.vlan_id
        )
        xpath_customer_vlan = IPI_CUSTOMER_VLAN_CONFIG_NAME
        xml_bridge_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_bridge_vlan, value=self.vlan_id
        )
        xml_customer_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_customer_vlan, value=value
        )

        insert_xml(xml_customer_vlan, xml_bridge_vlan, TAG_IPI_VLAN)

        config = new_ele("config")
        config.append(xml_bridge_vlan)
        logger.debug(
            f"Sending xml for vlan id configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)

    def unset_vlan_name(self, user):
        cache = self.setup_cache(user)

        # Check vlan-id is present on candidate-config before removing the vlans's name.
        # It's necessary because the sysrepo try to remove the vlan-name also, when the
        # vlan-id is being removed. If vlan-id is not present it is not necessary
        # to send the name removal to the OcNOS.
        xpath_list = list(libyang.xpath_split(self.change.xpath))
        assert xpath_list[1][1] == "vlan"
        vlan_id = xpath_list[1][2][0][1]
        xpath_gs_vlan = GS_VLAN.format(vlan_id)
        if not libyang.xpath_get(cache, xpath_gs_vlan, None):
            return

        xpath_bridge_vlan = IPI_BRIDGE_VLAN.format(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, self.vlan_id
        )
        xpath_customer_vlan = IPI_CUSTOMER_VLAN_CONFIG_NAME
        xml_bridge_vlan = self.server.ocnos_conn.xpath2xml(xpath_bridge_vlan)
        xml_customer_vlan = self.server.ocnos_conn.xpath2xml(
            xpath_customer_vlan, delete_oper=True
        )

        insert_xml(xml_customer_vlan, xml_bridge_vlan, TAG_IPI_VLAN)

        config = new_ele("config")
        config.append(xml_bridge_vlan)
        logger.debug(
            f"Sending xml for vlan id configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        return self.server.ocnos_conn.conn.edit_config(config)


class VlanServer(ServerBase):
    def __init__(self, sr_conn, ocnos_conn):
        super().__init__(sr_conn, "goldstone-vlan")
        self.sr_conn = sr_conn
        self.ocnos_conn = ocnos_conn

        # Create default network-instance
        self._create_default_network_instance(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE
        )

        # TODO: other handlers should be implemented in future.
        self.handlers = {
            "vlans": {
                "vlan": {
                    "vlan-id": NoOp,
                    "config": {"vlan-id": VlanIdHandler, "name": VlanNameHandler},
                }
            }
        }

    async def start(self):
        await self.reconcile()
        tasks = await super().start()

        return tasks

    def stop(self):
        # Remove default network-instance
        self._delete_default_network_instance(
            INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE
        )

        super().stop()

    async def post(self, user):
        try:
            self.ocnos_conn.apply()
        except ncclient.operations.RPCError as e:
            self.ocnos_conn.discard_changes()
            raise sysrepo.SysrepoInternalError(
                f"Commit failed in OcNOS due: {e.message}"
            )

    def reconcile_edit_config(self, msg, config):
        xml = new_ele("config")
        xml.append(config)
        logger.debug(
            f"Sending xml for {msg} configuration: {etree.tostring(xml,pretty_print=True).decode()}"
        )
        self.ocnos_conn.conn.edit_config(xml)

    async def reconcile(self):
        data = self.get_running_data("/goldstone-vlan:vlans/vlan", [])

        for d in data:
            config = d.get("config")
            vlan_id = d.get("vlan-id")
            xpath_bridge_vlan = IPI_BRIDGE_VLAN_CONFIG.format(
                INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, vlan_id
            )
            xpath_customer_vlan = IPI_CUSTOMER_VLAN_CONFIG_TYPE
            xml_bridge_vlan = self.ocnos_conn.xpath2xml(xpath_bridge_vlan, vlan_id)
            xml_customer_vlan = self.ocnos_conn.xpath2xml(
                xpath_customer_vlan, value=BRIDGE_CUSTOMER_VLAN_TYPE
            )

            insert_xml(xml_customer_vlan, xml_bridge_vlan, TAG_IPI_VLAN)
            self.reconcile_edit_config("vlan id", xml_bridge_vlan)
            vlan_name = config.get("name")
            if vlan_name:
                xpath_bridge_vlan = IPI_BRIDGE_VLAN_CONFIG.format(
                    INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, vlan_id
                )
                xpath_customer_vlan = IPI_CUSTOMER_VLAN_CONFIG_NAME
                xml_bridge_vlan = self.ocnos_conn.xpath2xml(xpath_bridge_vlan, vlan_id)
                xml_customer_vlan = self.ocnos_conn.xpath2xml(
                    xpath_customer_vlan, vlan_name
                )
                insert_xml(xml_customer_vlan, xml_bridge_vlan, TAG_IPI_VLAN)
                self.reconcile_edit_config("vlan name", xml_bridge_vlan)

            # commit all configs
            try:
                self.ocnos_conn.apply()
            except ncclient.operations.RPCError as e:
                self.ocnos_conn.discard_changes()
                raise sysrepo.SysrepoInternalError(
                    f"Reconcile Commit failed in OcNOS due: {e.message}"
                )
        logger.debug(f"Reconcile finished for vlan")

    async def oper_cb(self, xpath, priv):
        logger.info(f"oper_cb xpath: {xpath}")
        req_xpath = list(libyang.xpath_split(xpath))

        vlan_ids = self.ocnos_conn.get(
            IPI_BRIDGE_VLAN_VLAN_ID.format(
                INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE
            ),
            ds="operational",
        )
        if not vlan_ids:
            return

        vlan_ids = (
            vlan_ids["bridge"]["vlans"]["vlan"]
            if type(vlan_ids["bridge"]["vlans"]["vlan"]) == list
            else [vlan_ids["bridge"]["vlans"]["vlan"]]
        )
        if (
            len(req_xpath) == 3
            and req_xpath[1][1] == "vlan"
            and req_xpath[2][1] == "vlan-id"
        ):
            return {"goldstone-vlan:vlans": {"vlan": vlan_ids}}

        vids = [id["vlan-id"] for id in vlan_ids]
        vlans = []
        for vlan_id in vids:
            members = []
            vlan_data = self.ocnos_conn.get(
                IPI_BRIDGE_VLAN.format(
                    INSTANCE_NAME_FOR_IEEE_VLAN_BRIDGE, INSTANCE_TYPE, vlan_id
                ),
                ds="operational",
            )

            if (
                "tagged-interface"
                in vlan_data["bridge"]["vlans"]["vlan"]["customer-vlan"]["state"]
            ):
                members = vlan_data["bridge"]["vlans"]["vlan"]["customer-vlan"][
                    "state"
                ]["tagged-interface"]

                # When there is only one interface on tagged-interface, OcNOS sends it as a string instead list
                # OcNOS returns the interfaces with like this eth1(t)/eth1(u) to indicate tagged and untagged.
                if type(members) == str:
                    members = [re.sub("([(u,t)])", "", members)]
                elif type(members) == list:
                    members = [re.sub("([(u,t)])", "", m) for m in members]

            vlan_name = None
            if "name" in vlan_data["bridge"]["vlans"]["vlan"]["customer-vlan"]["state"]:
                vlan_name = vlan_data["bridge"]["vlans"]["vlan"]["customer-vlan"][
                    "state"
                ]["name"]

            vlan = {
                "vlan-id": vlan_id,
                "state": {"vlan-id": vlan_id, "name": vlan_name},
                "members": {"member": members},
            }
            vlans.append(vlan)
        return {"goldstone-vlan:vlans": {"vlan": vlans}}

    def _create_default_network_instance(self, name, type):
        xpath_ni = IPI_NETWORK_INSTANCE_CONFIG.format(name, type, name, type)
        xpath_bridge = IPI_BRIDGE_CONFIG_PROTOCOL.format(BRIDGE_PROTOCOL_TYPE)
        xml_ni = self.ocnos_conn.xpath2xml(xpath_ni)
        xml_bridge = self.ocnos_conn.xpath2xml(xpath_bridge)

        insert_xml(xml_bridge, xml_ni, TAG_IPI_NETWORK_INSTANCE)

        config = new_ele("config")
        config.append(xml_ni)
        logger.debug(
            f"Sending xml to create network-instance default configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        self.ocnos_conn.conn.edit_config(config)
        self.ocnos_conn.conn.commit()

    def _delete_default_network_instance(self, name, type):
        xpath_ni = IPI_NETWORK_INSTANCE.format(name, type)
        xml_ni = self.ocnos_conn.xpath2xml(xpath_ni, delete_oper=True)

        config = new_ele("config")
        config.append(xml_ni)
        logger.debug(
            f"Sending xml to remove network-instance default configuration: {etree.tostring(config,pretty_print=True).decode()}"
        )
        self.ocnos_conn.conn.edit_config(config)
        self.ocnos_conn.conn.commit()
