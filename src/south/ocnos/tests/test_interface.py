import unittest
import asyncio
import logging
import sysrepo
from goldstone.south.ocnos.interfaces import InterfaceServer
from .mock_ocnos import MockOcNOS
from lxml import etree
import libyang
from goldstone.lib.connector.sysrepo import Connector
from goldstone.lib.server_connector.sysrepo import Change
from goldstone.south.ocnos.interfaces import IfChangeHandler

logger = logging.getLogger(__name__)


class InterfaceMockOcNOS(MockOcNOS):
    def get(self, xpath, ds):
        # return the list of mock interfaces (assume only one interface for simplicity)
        if xpath == "/ipi-interface:interfaces/interface/name":
            return ["xe1"]
        # return the state of each mock interface (assume only one interface for simplicity)
        elif xpath == "/ipi-interface:interfaces/interface[name='xe1']":
            return {
                "state": {
                    "admin-status": "UP",
                    "name": "xe1",
                    "description": "DESC XE1",
                    "oper-status": "DOWN",
                    "counters": {
                        "last-clear": "Never",
                        "out-errors": 0,
                        "out-discards": 0,
                        "out-pkts": 950,
                        "out-octets": 0,
                        "in-errors": 0,
                        "in-errors": 0,
                        "in-discards": 0,
                        "in-multicast-pkts": 0,
                        "in-pkts": 950,
                        "in-octets": 305286275470760,
                        "extended-counters": {
                            "out-window-errors": 0,
                            "out-heartbeat-errors": 0,
                            "out-fifo-errors": 0,
                            "out-carrier-errors": 0,
                        },
                    },
                },
                "ethernet": {"state": {"mtu": "4000", "port-speed": "100g"}},
                "port-vlan": {
                    "switched-vlan": {
                        "interface-mode": "trunk",
                        "state": {"interface-mode": "trunk"},
                        "allowed-vlan": {"state": {"allowed-vlan-id": "100,200,300"}},
                    }
                },
            }


class TestInterfaceServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()
        self.ocnos = InterfaceMockOcNOS()
        self.server = InterfaceServer(self.conn, self.ocnos)
        self.maxDiff = None
        self.conn.delete_all("goldstone-interfaces")
        self.conn.delete_all("goldstone-vlan")
        self.conn.apply()
        self.sess = {
            "running": self.conn.new_session("running"),
            "operational": self.conn.new_session("operational"),
        }

        async def event_handler(*args):
            await asyncio.sleep(10)

        self.server.event_handler = event_handler

        self.tasks = [asyncio.create_task(c) for c in await self.server.start()]

    async def asyncTearDown(self):
        self.server.stop()
        self.tasks = []
        self.ocnos.conn.logs = []
        self.sess["running"].discard_changes()
        self.sess["running"].stop()
        self.sess["operational"].stop()
        self.conn.discard_changes()
        self.conn.stop()

    async def test_set_admin_status_up(self):
        ifname = "xe1"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status",
                "UP",
            )
            self.conn.apply()
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status",
                "DOWN",
            )
            self.conn.apply()
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status",
                "UP",
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # At first config, UP, it should not generate any xml config as it sends delete
        # to default value in OcNOS, the config will fail. Configure down, then UP to check
        # UP value.
        self.assertEqual(len(self.ocnos.conn.logs), 2)

        parser = etree.XMLParser(remove_blank_text=True)
        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <shutdown/>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>
                """

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[0]).decode(),
            etree.tostring(xml).decode(),
        )

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <shutdown operation="delete"/>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>
                """

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_admin_status(self):
        ifname = "xe1"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status",
                "UP",
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status"
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.assertEqual(len(self.ocnos.conn.logs), 1)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <shutdown/>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[0]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_admin_status_down(self):
        ifname = "xe1"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/admin-status",
                "DOWN",
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        self.assertEqual(len(self.ocnos.conn.logs), 1)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <shutdown/>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[0]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_description(self):
        ifname = "xe1"
        desc = "XE1 DESC"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/description",
                desc,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 2)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <description>{desc}</description>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[0]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_description(self):
        ifname = "xe1"
        desc = "XE1 DESC"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/description",
                desc,
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/description"
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 3)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <description operation="delete"/>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_mtu(self):
        ifname = "xe1"
        mtu = 5000

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/mtu",
                mtu,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 2)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <mtu>{mtu}</mtu>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_mtu(self):
        ifname = "xe1"
        mtu = 5000

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/mtu",
                mtu,
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/mtu"
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 3)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <config>
                            <name>{ifname}</name>
                            <mtu operation="delete"/>
                        </config>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_speed(self):
        ifname = "xe1"
        speed = "SPEED_1000M"
        speed_ocnos = "1g"
        autoneg = False

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/speed",
                speed,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                autoneg,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 2)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed>{speed_ocnos}</port-speed>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_speed(self):
        ifname = "xe1"
        speed = "SPEED_1000M"
        autoneg = False

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/speed",
                speed,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                autoneg,
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/speed"
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 3)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed operation="delete"/>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_edit_speed_to_autoneg(self):
        ifname = "xe1"
        speed = "SPEED_1000M"
        speed_ocnos = "1g"
        speed_autoneg_ocnos = "auto"
        autoneg = True

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.apply()
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/config/speed",
                speed,
            )
            self.conn.apply()
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                autoneg,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 3)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed>{speed_ocnos}</port-speed>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed>{speed_autoneg_ocnos}</port-speed>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_autonegotiate_true(self):
        ifname = "xe1"
        speed_ocnos = "auto"
        autoneg = True

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                autoneg,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 2)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed>{speed_ocnos}</port-speed>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_autonegotiate(self):
        ifname = "xe1"
        autoneg = True

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                autoneg,
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled"
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 3)

        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed operation="delete"/>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_autonegotiate_false(self):
        ifname = "xe1"
        speed_ocnos = "auto"
        autoneg = False

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                True,
            )
            self.conn.apply()

            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/auto-negotiate/config/enabled",
                autoneg,
            )
            self.conn.apply()

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))
        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

        # The sysrepo always sends by default the admin-state false within, when configuring a interface from scratch,
        # as it is the case in the tests
        self.assertEqual(len(self.ocnos.conn.logs), 3)
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed>{speed_ocnos}</port-speed>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

        expected_xml = f"""
                <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                    <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                        <interface>
                        <name>{ifname}</name>
                        <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                            <config>
                            <port-speed operation="delete"/>
                            </config>
                        </ethernet>
                        </interface>
                    </interfaces>
                </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    #######################
    # SWITCHED-VLAN TESTS
    #######################

    async def test_set_interface_mode(self):
        if_mode_gs = "ACCESS"
        if_mode_ocnos = "access"
        ifname = "xe1"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode",
                if_mode_gs,
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
                <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                    <interface>
                    <name>{ifname}</name>
                    <config>
                        <name>{ifname}</name>
                        <enable-switchport/>
                    </config>
                    <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                        <switched-vlan>
                        <interface-mode>{if_mode_ocnos}</interface-mode>
                        <config>
                            <interface-mode>{if_mode_ocnos}</interface-mode>
                        </config>
                        </switched-vlan>
                    </port-vlan>
                    </interface>
                </interfaces>
                <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                    <network-instance>
                    <instance-name>1</instance-name>
                    <instance-type>l2ni</instance-type>
                    <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                        <bridge-ports>
                        <interface>
                            <name>{ifname}</name>
                            <config>
                            <name>{ifname}</name>
                            </config>
                        </interface>
                        </bridge-ports>
                    </bridge>
                    </network-instance>
                </network-instances>
            </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)

        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[1],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[1]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_interface_mode(self):
        if_mode_gs = "ACCESS"
        if_mode_ocnos = "access"
        ifname = "xe1"

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode",
                if_mode_gs,
            )
            self.conn.apply()
            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode"
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
                <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                    <interface>
                        <name>{ifname}</name>
                            <config>
                                <name>{ifname}</name>
                                <enable-switchport operation="delete"/>
                            </config>
                        <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                            <switched-vlan operation="delete">
                                <interface-mode>{if_mode_ocnos}</interface-mode>
                            </switched-vlan>
                        </port-vlan>
                    </interface>
                </interfaces>
                <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                    <network-instance>
                    <instance-name>1</instance-name>
                    <instance-type>l2ni</instance-type>
                    <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                        <bridge-ports>
                        <interface operation="delete">
                            <name>{ifname}</name>
                        </interface>
                        </bridge-ports>
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

    async def test_set_access_vlan(self):
        if_mode_gs = "ACCESS"
        if_mode_ocnos = "access"
        ifname = "xe1"
        vlan_id = 100

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode",
                if_mode_gs,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/access-vlan",
                vlan_id,
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
            <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                <interface>
                    <name>{ifname}</name>
                    <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                        <switched-vlan>
                            <interface-mode>{if_mode_ocnos}</interface-mode>
                            <config>
                                <interface-mode>{if_mode_ocnos}</interface-mode>
                            </config>
                            <vlans>
                                <config>
                                    <vlan-id>{vlan_id}</vlan-id>
                                </config>
                            </vlans>
                        </switched-vlan>
                    </port-vlan>
                </interface>
            </interfaces>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)

        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[2],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_access_vlan(self):
        if_mode_gs = "ACCESS"
        if_mode_ocnos = "access"
        ifname = "xe1"
        vlan_id = 100

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode",
                if_mode_gs,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/access-vlan",
                vlan_id,
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/access-vlan"
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
            <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                <interface>
                <name>{ifname}</name>
                <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                    <switched-vlan>
                    <interface-mode>{if_mode_ocnos}</interface-mode>
                    <vlans>
                        <config>
                        <vlan-id operation="delete"/>
                        </config>
                    </vlans>
                    </switched-vlan>
                </port-vlan>
                </interface>
            </interfaces>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)

        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[3],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[3]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_set_trunk_vlan(self):
        if_mode_gs = "TRUNK"
        if_mode_ocnos = "trunk"
        ifname = "xe1"
        tvlan_1 = 100
        tvlan_2 = 200

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode",
                if_mode_gs,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/trunk-vlans",
                tvlan_1,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/trunk-vlans",
                tvlan_2,
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
            <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                <interface>
                <name>{ifname}</name>
                <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                    <switched-vlan>
                        <interface-mode>{if_mode_ocnos}</interface-mode>
                        <config>
                            <interface-mode>{if_mode_ocnos}</interface-mode>
                        </config>
                        <allowed-vlan>
                            <config>
                                <allowed-vlan-id>{tvlan_1}</allowed-vlan-id>
                            </config>
                        </allowed-vlan>
                    </switched-vlan>
                </port-vlan>
                </interface>
            </interfaces>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[2],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[2]).decode(),
            etree.tostring(xml).decode(),
        )

        expected_xml = f"""
        <nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
            <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                <interface>
                <name>{ifname}</name>
                <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                    <switched-vlan>
                        <interface-mode>{if_mode_ocnos}</interface-mode>
                        <config>
                            <interface-mode>{if_mode_ocnos}</interface-mode>
                        </config>
                        <allowed-vlan>
                            <config>
                                <allowed-vlan-id>{tvlan_2}</allowed-vlan-id>
                            </config>
                        </allowed-vlan>
                    </switched-vlan>
                </port-vlan>
                </interface>
            </interfaces>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[3],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[3]).decode(),
            etree.tostring(xml).decode(),
        )

    async def test_unset_trunk_vlan(self):
        if_mode_gs = "TRUNK"
        if_mode_ocnos = "trunk"
        ifname = "xe1"
        tvlan_1 = 100

        def test():
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/config/name",
                ifname,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/interface-mode",
                if_mode_gs,
            )
            self.conn.set(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/trunk-vlans",
                tvlan_1,
            )
            self.conn.apply()

            self.conn.delete(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/goldstone-vlan:switched-vlan/config/trunk-vlans"
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
            <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                <interface>
                <name>{ifname}</name>
                <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                    <switched-vlan>
                        <interface-mode>{if_mode_ocnos}</interface-mode>
                        <allowed-vlan>
                            <config>
                                <allowed-vlan-id operation="delete">{tvlan_1}</allowed-vlan-id>
                            </config>
                        </allowed-vlan>
                    </switched-vlan>
                </port-vlan>
                </interface>
            </interfaces>
        </nc:config>"""

        xml = etree.fromstring(expected_xml, parser=parser)
        logger.debug(
            f"XML: {etree.tostring(self.ocnos.conn.logs[3],pretty_print=True).decode()}"
        )
        self.assertEqual(
            etree.tostring(self.ocnos.conn.logs[3]).decode(),
            etree.tostring(xml).decode(),
        )

    #######################
    # GET TESTS
    #######################

    async def test_get_specific_interface(self):
        def test():
            data = self.conn.get_operational(
                "/goldstone-interfaces:interfaces/interface/name"
            )
            expected = ["xe1"]
            self.assertEqual(data, expected)

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    async def test_get_interfaces(self):
        def test():
            data = self.conn.get_operational("/goldstone-interfaces:interfaces")

            expected = {
                "interface": [
                    {
                        "name": "xe1",
                        "config": {"name": "xe1"},
                        "state": {
                            "name": "xe1",
                            "admin-status": "UP",
                            "oper-status": "DOWN",
                            "description": "DESC XE1",
                            "counters": {
                                "out-errors": 0,
                                "out-discards": 0,
                                "out-octets": 0,
                                "in-errors": 0,
                                "in-discards": 0,
                                "in-multicast-pkts": 0,
                                "in-octets": 305286275470760,
                            },
                        },
                        "ethernet": {
                            "state": {"speed": "SPEED_100G"},
                            "auto-negotiate": {"state": {"enabled": False}},
                        },
                        "switched-vlan": {
                            "state": {
                                "interface-mode": "TRUNK",
                                "trunk-vlans": [100, 200, 300],
                            }
                        },
                    }
                ]
            }
            self.assertEqual(data, expected)

        self.tasks.append(asyncio.create_task(asyncio.to_thread(test)))

        done, _ = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e


class TestInterfaceServerReconcile(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.conn = Connector()
        self.ocnos = InterfaceMockOcNOS()
        self.server = InterfaceServer(self.conn, self.ocnos)
        self.maxDiff = None
        config = {
            "interfaces": {
                "interface": [
                    {
                        "name": "xe1",
                        "config": {
                            "name": "xe1",
                            "admin-status": "UP",
                            "description": "DESC XE1",
                        },
                        "ethernet": {
                            "config": {"mtu": 5000, "speed": "SPEED_1000M"},
                            "auto-negotiate": {"config": {"enabled": False}},
                        },
                        "switched-vlan": {
                            "config": {"interface-mode": "ACCESS", "access-vlan": "100"}
                        },
                    },
                    {
                        "name": "xe2",
                        "config": {
                            "name": "xe2",
                            "admin-status": "DOWN",
                            "description": "DESC XE2",
                        },
                        "ethernet": {
                            "config": {"mtu": 3000},
                            "auto-negotiate": {"config": {"enabled": True}},
                        },
                        "switched-vlan": {
                            "config": {
                                "interface-mode": "TRUNK",
                                "trunk-vlans": ["200", "300"],
                            }
                        },
                    },
                ]
            }
        }

        self.conn.running_session.session.replace_config(config, "goldstone-interfaces")
        self.conn.apply()

        async def event_handler(*args):
            await asyncio.sleep(10)

        self.server.event_handler = event_handler

        self.tasks = [asyncio.create_task(c) for c in await self.server.start()]

    async def asyncTearDown(self):
        self.server.stop()
        self.tasks = []
        self.ocnos.conn.logs = []
        self.conn.stop()

    async def test_basic_reconcile(self):
        parser = etree.XMLParser(remove_blank_text=True)

        expected_xmls = [
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe1</name>
                            <config>
                                <name>xe1</name>
                                <description>DESC XE1</description>
                            </config>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe1</name>
                            <config>
                                <name>xe1</name>
                                <mtu>5000</mtu>
                            </config>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe1</name>
                            <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                                <config>
                                <port-speed>1g</port-speed>
                                </config>
                            </ethernet>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe1</name>
                            <config>
                                <name>xe1</name>
                                <enable-switchport/>
                            </config>
                            <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                                <switched-vlan>
                                <interface-mode>access</interface-mode>
                                <config>
                                    <interface-mode>access</interface-mode>
                                </config>
                                </switched-vlan>
                            </port-vlan>
                            </interface>
                        </interfaces>
                        <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                            <network-instance>
                            <instance-name>1</instance-name>
                            <instance-type>l2ni</instance-type>
                            <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                                <bridge-ports>
                                <interface>
                                    <name>xe1</name>
                                    <config>
                                    <name>xe1</name>
                                    </config>
                                </interface>
                                </bridge-ports>
                            </bridge>
                            </network-instance>
                        </network-instances>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe1</name>
                            <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                                <switched-vlan>
                                <interface-mode>access</interface-mode>
                                <config>
                                    <interface-mode>access</interface-mode>
                                </config>
                                <vlans>
                                    <config>
                                    <vlan-id>100</vlan-id>
                                    </config>
                                </vlans>
                                </switched-vlan>
                            </port-vlan>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe2</name>
                            <config>
                                <name>xe2</name>
                                <shutdown/>
                            </config>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe2</name>
                            <config>
                                <name>xe2</name>
                                <description>DESC XE2</description>
                            </config>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe2</name>
                                <config>
                                    <name>xe2</name>
                                    <mtu>3000</mtu>
                                </config>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe2</name>
                            <ethernet xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-if-ethernet">
                                <config>
                                <port-speed>auto</port-speed>
                                </config>
                            </ethernet>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                            <name>xe2</name>
                            <config>
                                <name>xe2</name>
                                <enable-switchport/>
                            </config>
                            <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                                <switched-vlan>
                                <interface-mode>trunk</interface-mode>
                                <config>
                                    <interface-mode>trunk</interface-mode>
                                </config>
                                </switched-vlan>
                            </port-vlan>
                            </interface>
                        </interfaces>
                        <network-instances xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-network-instance">
                            <network-instance>
                            <instance-name>1</instance-name>
                            <instance-type>l2ni</instance-type>
                            <bridge xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-bridge">
                                <bridge-ports>
                                <interface>
                                    <name>xe2</name>
                                    <config>
                                    <name>xe2</name>
                                    </config>
                                </interface>
                                </bridge-ports>
                            </bridge>
                            </network-instance>
                        </network-instances>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                                <name>xe2</name>
                                <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                                    <switched-vlan>
                                    <interface-mode>trunk</interface-mode>
                                    <config>
                                            <interface-mode>trunk</interface-mode>
                                    </config>
                                    <allowed-vlan>
                                        <config>
                                        <allowed-vlan-id>200</allowed-vlan-id>
                                        </config>
                                    </allowed-vlan>
                                    </switched-vlan>
                                </port-vlan>
                            </interface>
                        </interfaces>
                    </nc:config>""",
            """<nc:config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
                        <interfaces xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-interface">
                            <interface>
                                <name>xe2</name>
                                    <port-vlan xmlns="http://www.ipinfusion.com/yang/ocnos/ipi-port-vlan">
                                        <switched-vlan>
                                        <interface-mode>trunk</interface-mode>
                                        <config>
                                            <interface-mode>trunk</interface-mode>
                                        </config>
                                        <allowed-vlan>
                                            <config>
                                            <allowed-vlan-id>300</allowed-vlan-id>
                                            </config>
                                        </allowed-vlan>
                                        </switched-vlan>
                                    </port-vlan>
                            </interface>
                        </interfaces>
                    </nc:config>""",
        ]

        self.assertEqual(len(expected_xmls), len(self.ocnos.conn.logs))

        for log, expected_xml in zip(self.ocnos.conn.logs, expected_xmls):
            xml = etree.fromstring(expected_xml, parser=parser)
            self.assertEqual(etree.tostring(log).decode(), etree.tostring(xml).decode())


if __name__ == "__main__":
    unittest.main()
