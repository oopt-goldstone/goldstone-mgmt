import unittest
import asyncio
import logging
import sysrepo
from goldstone.south.ocnos.vlan import VlanServer
from .mock_ocnos import MockOcNOS
from lxml import etree
from goldstone.lib.connector.sysrepo import Connector

logger = logging.getLogger(__name__)


class VlanMockOcNOS(MockOcNOS):
    def get(self, xpath, ds):
        if (
            xpath
            == "/ipi-network-instance:network-instances/network-instance/instance-name"
        ):
            return ["1"]


class TestVlanServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.maxDiff = None
        self.conn = Connector()

        self.conn.running_session.session.replace_config({}, "goldstone-vlan")
        self.conn.apply()

        self.ocnos = VlanMockOcNOS()
        self.server = VlanServer(self.conn, self.ocnos)

        async def event_handler(*args):
            await asyncio.sleep(10)

        self.server.event_handler = event_handler

        self.tasks = [asyncio.create_task(c) for c in await self.server.start()]

    async def asyncTearDown(self):
        self.server.stop()
        self.tasks = []
        self.ocnos.logs = []
        self.conn.stop()

    # 2. the following function is called in the second
    async def test_set_vlan_id(self):
        vlan_id = 100

        def test():
            self.conn.set(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/vlan-id",
                vlan_id,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.assertEqual(len(self.ocnos.conn.logs), 2)
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                        <network-instance>
                            <instance-name>1</instance-name>
                            <instance-type>l2ni</instance-type>
                            <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                                <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                                    <vlan>
                                        <vlan-id>{vlan_id}</vlan-id>
                                        <config>
                                            <vlan-id>{vlan_id}</vlan-id>
                                        </config>
                                        <customer-vlan>
                                            <config>
                                                <type>customer</type>
                                            </config>
                                        </customer-vlan>
                                    </vlan>
                                </vlans>
                            </bridge>
                        </network-instance>
                    </network-instances>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_vlan_id(self):
        vlan_id = 100

        def test():
            self.conn.set(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/vlan-id",
                vlan_id,
            )
            self.conn.apply()
            self.conn.delete(f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']")
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.assertEqual(len(self.ocnos.conn.logs), 3)
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
        <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
            <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                <network-instance>
                    <instance-name>1</instance-name>
                    <instance-type>l2ni</instance-type>
                    <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                        <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                            <vlan operation="delete">
                                <vlan-id>{vlan_id}</vlan-id>
                            </vlan>
                        </vlans>
                    </bridge>
                </network-instance>
            </network-instances>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_vlan_name(self):
        vlan_id = 100
        vlan_name = "vlan100"

        def test():
            self.conn.set(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/vlan-id",
                vlan_id,
            )
            self.conn.apply()
            self.conn.set(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/name",
                vlan_name,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.assertEqual(len(self.ocnos.conn.logs), 3)
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
        <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
            <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                <network-instance>
                    <instance-name>1</instance-name>
                    <instance-type>l2ni</instance-type>
                    <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                        <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                            <vlan>
                                <vlan-id>{vlan_id}</vlan-id>
                                <config>
                                    <vlan-id>{vlan_id}</vlan-id>
                                </config>
                                <customer-vlan>
                                    <config>
                                        <name>{vlan_name}</name>
                                    </config>
                                </customer-vlan>
                            </vlan>
                        </vlans>
                    </bridge>
                </network-instance>
            </network-instances>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)

        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[2],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_vlan_name(self):
        vlan_id = 100
        vlan_name = "vlan100"

        def test():
            # Create vlan-id
            self.conn.set(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/vlan-id",
                vlan_id,
            )
            self.conn.apply()
            self.conn.set(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/name",
                vlan_name,
            )
            self.conn.apply()
            # Remove vlan name
            self.conn.delete(
                f"/goldstone-vlan:vlans/vlan[vlan-id='{vlan_id}']/config/name"
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.assertEqual(len(self.ocnos.conn.logs), 4)
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
        <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
            <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                <network-instance>
                    <instance-name>1</instance-name>
                    <instance-type>l2ni</instance-type>
                    <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                        <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                            <vlan>
                                <vlan-id>{vlan_id}</vlan-id>
                                <customer-vlan>
                                    <config>
                                        <name operation="delete"/>
                                    </config>
                                </customer-vlan>
                            </vlan>
                        </vlans>
                    </bridge>
                </network-instance>
            </network-instances>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)

        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[3],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[3]).decode(),
            etree.tostring(xml).decode(),
        )


class TestVlanServerReconcile(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()

        config = {
            "vlans": {
                "vlan": [
                    {
                        "vlan-id": 100,
                        "config": {"vlan-id": 100},
                        # "config": {"vlan-id": 100, "name": "VLAN-100"},
                    },
                    {"vlan-id": 200, "config": {"vlan-id": 200, "name": "VLAN-200"}},
                ]
            }
        }

        self.conn.running_session.session.replace_config(config, "goldstone-vlan")
        self.conn.apply()

        self.ocnos = VlanMockOcNOS()
        self.server = VlanServer(self.conn, self.ocnos)

        async def event_handler(*args):
            await asyncio.sleep(10)

        self.server.event_handler = event_handler

        self.tasks = [asyncio.create_task(c) for c in await self.server.start()]

    async def asyncTearDown(self):
        self.server.stop()
        self.tasks = []
        self.ocnos.logs = []
        self.conn.stop()

    async def test_basic_reconcile(self):
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xmls = [
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                        <network-instance>
                        <instance-name>1</instance-name>
                        <instance-type>l2ni</instance-type>
                        <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                            <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                            <vlan>
                                <vlan-id>100</vlan-id>
                                <config>
                                <vlan-id>100</vlan-id>
                                </config>
                                <customer-vlan>
                                <config>
                                    <type>customer</type>
                                </config>
                                </customer-vlan>
                            </vlan>
                            </vlans>
                        </bridge>
                        </network-instance>
                    </network-instances>
                </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                        <network-instance>
                        <instance-name>1</instance-name>
                        <instance-type>l2ni</instance-type>
                        <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                            <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                            <vlan>
                                <vlan-id>200</vlan-id>
                                <config>
                                <vlan-id>200</vlan-id>
                                </config>
                                <customer-vlan>
                                <config>
                                    <type>customer</type>
                                </config>
                                </customer-vlan>
                            </vlan>
                            </vlans>
                        </bridge>
                        </network-instance>
                    </network-instances>
                </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                        <network-instance>
                        <instance-name>1</instance-name>
                        <instance-type>l2ni</instance-type>
                        <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                            <vlans xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-vlan">
                            <vlan>
                                <vlan-id>200</vlan-id>
                                <config>
                                <vlan-id>200</vlan-id>
                                </config>
                                <customer-vlan>
                                <config>
                                    <name>VLAN-200</name>
                                </config>
                                </customer-vlan>
                            </vlan>
                            </vlans>
                        </bridge>
                        </network-instance>
                    </network-instances>
                    </nc:config>""",
        ]

        self.assertEqual(len(expected_xmls), len(self.ocnos.conn.logs[1:]))

        # Must remove the first element, as it is created outside of reconcile,
        # in VlanServer initialization
        for log, expected_xml in zip(self.ocnos.conn.logs[1:], expected_xmls):
            xml = etree.fromstring(expected_xml, parser=parser)
            self.assertEqual(etree.tostring(log).decode(), etree.tostring(xml).decode())


if __name__ == "__main__":
    unittest.main()
