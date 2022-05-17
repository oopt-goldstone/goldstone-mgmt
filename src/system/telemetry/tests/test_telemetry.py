"""Tests for subscription stores."""


import unittest
import asyncio
import logging
import time
import sysrepo
from multiprocessing import Process, Queue
from goldstone.lib.core import ServerBase, NoOp
from goldstone.lib.connector.sysrepo import Connector
from goldstone.system.telemetry.store import (
    InMemorySubscriptionStore,
    InMemoryTelemetryStore,
)
from goldstone.system.telemetry.telemetry import TelemetryServer


class MockGSServer(ServerBase):
    """MockGSServer is mock handler server for Goldstone primitive models.

    Attributes:
        oper_data (dict): Data for oper_cb() to return. You can set this to configure mock's behavior.
    """

    def __init__(self, conn, module):
        super().__init__(conn, module)
        self.oper_data = {}
        self.handlers = {"interfaces": NoOp}

    def oper_cb(self, xpath, priv):
        return self.oper_data


class MockGSInterfaceServer(MockGSServer):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-interfaces")


MOCK_SERVERS = {
    "goldstone-interfaces": MockGSInterfaceServer,
}


def run_mock_server(q, mock_modules):
    """Run mock servers.

    A TestCase can communicate with MockServers by using a Queue.
        Stop MockServers: {"type": "stop"}
        Set operational state data of a MockServer: {"type": "set", "server": "<SERVER NAME>", "data": "<DATA TO SET>"}

    Args:
        q (Queue): Queue to communicate between a TestCase and MockServers.
        mock_modules (list of str): Names of modules to mock. Keys in MOCK_SERVERS.
    """
    conn = Connector()
    servers = {}
    for mock_module in mock_modules:
        servers[mock_module] = MOCK_SERVERS[mock_module](conn)

    async def _main():
        tasks = []
        for server in servers.items():
            tasks += await server[1].start()

        async def evloop():
            while True:
                await asyncio.sleep(0.01)
                try:
                    msg = q.get(False)
                except:
                    pass
                else:
                    if msg["type"] == "stop":
                        return
                    elif msg["type"] == "set-oper-data":
                        servers[msg["server"]].oper_data = msg["data"]

        tasks.append(evloop())
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t) for t in tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    asyncio.run(_main())


def config_subscription(sess, params):
    sess.switch_datastore("running")
    rid = params["id"]
    sess.set_item(
        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/config/id",
        rid,
    )
    if params["mode"] is not None:
        sess.set_item(
            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/config/mode",
            params["mode"],
        )
    if params["updates-only"] is not None:
        sess.set_item(
            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/config/updates-only",
            params["updates-only"],
        )
    for subscription in params["subscriptions"]:
        sid = subscription["id"]
        sess.set_item(
            f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
            f"/subscription[id='{sid}']/config/id",
            sid,
        )
        if subscription["path"] is not None:
            sess.set_item(
                f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                f"/subscription[id='{sid}']/config/path",
                subscription["path"],
            )
        if subscription["mode"] is not None:
            sess.set_item(
                f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                f"/subscription[id='{sid}']/config/mode",
                subscription["mode"],
            )
        if subscription["sample-interval"] is not None:
            sess.set_item(
                f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                f"/subscription[id='{sid}']/config/sample-interval",
                subscription["sample-interval"],
            )
        if subscription["suppress-redundant"] is not None:
            sess.set_item(
                f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                f"/subscription[id='{sid}']/config/suppress-redundant",
                subscription["suppress-redundant"],
            )
        if subscription["heartbeat-interval"] is not None:
            sess.set_item(
                f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                f"/subscription[id='{sid}']/config/heartbeat-interval",
                subscription["heartbeat-interval"],
            )
    sess.apply_changes()


class TestTelemetryServer(unittest.IsolatedAsyncioTestCase):
    """Tests for TelemetryServer."""

    MOCK_WAIT = 1
    NOTIFICATION_WAIT = 0.1

    async def asyncSetUp(self):
        logging.basicConfig(level=logging.CRITICAL)
        # NOTE: Enable for debugging.
        # logging.basicConfig(level=logging.DEBUG)
        # self.maxDiff = None
        self.conn = Connector()

        self.conn.delete_all("goldstone-telemetry")
        self.conn.apply()

        self.received_notif = {}
        self.ss = InMemorySubscriptionStore()
        self.ts = InMemoryTelemetryStore()
        self.server = TelemetryServer(self.conn, self.ss, self.ts)
        self.q = Queue()
        mock_modules = ["goldstone-interfaces"]
        self.process = Process(target=run_mock_server, args=(self.q, mock_modules))
        self.process.start()

        self.tasks = await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()
        self.tasks = []
        self.conn.stop()
        self.q.put({"type": "stop"})
        self.process.join()
        self.clear_received_notif()

    async def run_test(self, test):
        """Run a test as a thread.

        Args:
            test (func): Test to run.
        """
        self.tasks.append(asyncio.to_thread(test))
        tasks = [
            t if isinstance(t, asyncio.Task) else asyncio.create_task(t)
            for t in self.tasks
        ]

        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            e = task.exception()
            if e:
                raise e

    def set_mock_oper_data(self, server, data):
        """Set operational state data to the mock server.

        Args:
            server (str): Target mock server name. A key in MOCK_SERVERS.
            data (dict): Operational state data that the server returns.
        """
        self.q.put({"type": "set-oper-data", "server": server, "data": data})

    def notif_callback(self, xpath, notif_type, notif, ts, priv):
        if "path" in notif.keys():
            self.received_notif[notif["path"]] = notif
        else:
            self.received_notif["sync-response"] = notif

    def clear_received_notif(self):
        self.received_notif = {}

    async def test_empty(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected = {}
                    self.assertEqual(data, expected)

        await self.run_test(test)

    async def test_basic_op_stream_sample_subscription(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": False,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": True,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected = {
                        "subscribe-requests": {
                            "subscribe-request": [
                                {
                                    "id": params["id"],
                                    "config": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "state": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "subscriptions": {
                                        "subscription": [
                                            {
                                                "id": s["id"],
                                                "config": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                    "mode": s["mode"],
                                                    "sample-interval": s[
                                                        "sample-interval"
                                                    ],
                                                    "suppress-redundant": s[
                                                        "suppress-redundant"
                                                    ],
                                                    "heartbeat-interval": s[
                                                        "heartbeat-interval"
                                                    ],
                                                },
                                                "state": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                    "mode": s["mode"],
                                                    "sample-interval": s[
                                                        "sample-interval"
                                                    ],
                                                    "suppress-redundant": s[
                                                        "suppress-redundant"
                                                    ],
                                                    "heartbeat-interval": s[
                                                        "heartbeat-interval"
                                                    ],
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                    self.assertEqual(data, expected)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Update the target data.
                    sess.switch_datastore("running")
                    sess.set_item(path, "DOWN")
                    sess.apply_changes()

                    # Wait sample interval.
                    time.sleep(s["sample-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"DOWN"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

                    # Modify a subscription.
                    sess.switch_datastore("running")
                    new_path = path_prefix + "/config/interface-type"
                    rid = params["id"]
                    sid = s["id"]
                    sess.set_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                        f"/subscription[id='{sid}']/config/path",
                        new_path,
                    )
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        sess.apply_changes()
                    sess.discard_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    self.assertEqual(data, expected)

                    # Delete a subscription.
                    sess.switch_datastore("running")
                    sess.delete_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']"
                    )
                    sess.apply_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected_after_delete = {}
                    self.assertEqual(data, expected_after_delete)

        await self.run_test(test)

    async def test_basic_op_stream_on_change_subscription(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": False,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "ON_CHANGE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": 20 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected = {
                        "subscribe-requests": {
                            "subscribe-request": [
                                {
                                    "id": params["id"],
                                    "config": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "state": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "subscriptions": {
                                        "subscription": [
                                            {
                                                "id": s["id"],
                                                "config": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                    "mode": s["mode"],
                                                    "heartbeat-interval": s[
                                                        "heartbeat-interval"
                                                    ],
                                                },
                                                "state": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                    "mode": s["mode"],
                                                    "sample-interval": 10
                                                    * 1000
                                                    * 1000
                                                    * 1000,
                                                    "suppress-redundant": False,
                                                    "heartbeat-interval": s[
                                                        "heartbeat-interval"
                                                    ],
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                    self.assertEqual(data, expected)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Update the target data.
                    sess.switch_datastore("running")
                    sess.set_item(path, "DOWN")
                    sess.apply_changes()

                    # Wait default update interval.
                    time.sleep(5)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"DOWN"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

                    # Modify a subscription.
                    sess.switch_datastore("running")
                    new_path = path_prefix + "/config/interface-type"
                    rid = params["id"]
                    sid = s["id"]
                    sess.set_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                        f"/subscription[id='{sid}']/config/path",
                        new_path,
                    )
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        sess.apply_changes()
                    sess.discard_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    self.assertEqual(data, expected)

                    # Delete a subscription.
                    sess.switch_datastore("running")
                    sess.delete_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']"
                    )
                    sess.apply_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected_after_delete = {}
                    self.assertEqual(data, expected_after_delete)

        await self.run_test(test)

    async def test_basic_op_poll_subscription(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "POLL",
                        "updates-only": False,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected = {
                        "subscribe-requests": {
                            "subscribe-request": [
                                {
                                    "id": params["id"],
                                    "config": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "state": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "subscriptions": {
                                        "subscription": [
                                            {
                                                "id": s["id"],
                                                "config": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                },
                                                "state": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                    self.assertEqual(data, expected)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Update the target data.
                    sess.switch_datastore("running")
                    sess.set_item(path, "DOWN")
                    sess.apply_changes()

                    # Send a poll request.
                    sess.rpc_send("/goldstone-telemetry:poll", {"id": params["id"]})

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"DOWN"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

                    # Modify a subscription.
                    sess.switch_datastore("running")
                    new_path = path_prefix + "/config/interface-type"
                    rid = params["id"]
                    sid = s["id"]
                    sess.set_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                        f"/subscription[id='{sid}']/config/path",
                        new_path,
                    )
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        sess.apply_changes()
                    sess.discard_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    self.assertEqual(data, expected)

                    # Delete a subscription.
                    sess.switch_datastore("running")
                    sess.delete_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']"
                    )
                    sess.apply_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected_after_delete = {}
                    self.assertEqual(data, expected_after_delete)

        await self.run_test(test)

    async def test_basic_op_once_subscription(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": False,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected = {
                        "subscribe-requests": {
                            "subscribe-request": [
                                {
                                    "id": params["id"],
                                    "config": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "state": {
                                        "id": params["id"],
                                        "mode": params["mode"],
                                        "updates-only": params["updates-only"],
                                    },
                                    "subscriptions": {
                                        "subscription": [
                                            {
                                                "id": s["id"],
                                                "config": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                },
                                                "state": {
                                                    "id": s["id"],
                                                    "path": s["path"],
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                    self.assertEqual(data, expected)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

                    # Modify a subscription.
                    sess.switch_datastore("running")
                    new_path = path_prefix + "/config/interface-type"
                    rid = params["id"]
                    sid = s["id"]
                    sess.set_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']/subscriptions"
                        f"/subscription[id='{sid}']/config/path",
                        new_path,
                    )
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        sess.apply_changes()
                    sess.discard_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    self.assertEqual(data, expected)

                    # Delete a subscription.
                    sess.switch_datastore("running")
                    sess.delete_item(
                        f"/goldstone-telemetry:subscribe-requests/subscribe-request[id='{rid}']"
                    )
                    sess.apply_changes()
                    sess.switch_datastore("operational")
                    data = sess.get_data("/goldstone-telemetry:subscribe-requests")
                    expected_after_delete = {}
                    self.assertEqual(data, expected_after_delete)

        await self.run_test(test)

    async def test_config_subscription_ok(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": True,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    config_subscription(sess, params)

        await self.run_test(test)

    async def test_config_subscription_error_no_mode(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
                    params = {
                        "id": 1,
                        "mode": None,
                        "updates-only": None,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        config_subscription(sess, params)

        await self.run_test(test)

    async def test_config_subscription_error_no_subscription_path(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": None,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": None,
                                "mode": "SAMPLE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        config_subscription(sess, params)

        await self.run_test(test)

    async def test_config_subscription_error_invalid_path(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    path = (
                        "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config"
                        "/unknown-leaf-node-to-fail"
                    )
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": None,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        config_subscription(sess, params)

        await self.run_test(test)

    async def test_config_subscription_error_no_stream_mode(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": None,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        config_subscription(sess, params)

        await self.run_test(test)

    async def test_config_subscription_error_short_sample_interval(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": None,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 4 * 1000 * 1000 * 1000,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        config_subscription(sess, params)

        await self.run_test(test)

    async def test_config_subscription_error_short_heartbeat_interval(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": None,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": 4 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    with self.assertRaises(sysrepo.SysrepoCallbackFailedError):
                        config_subscription(sess, params)

        await self.run_test(test)

    async def test_subscribe_container(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config"
                    path_name = path + "/name"
                    path_admin_status = path + "/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_name, "Interface1/0/1")
                    sess.set_item(path_admin_status, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": False,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        path_name: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_name,
                            "json-data": '"Interface1/0/1"',
                        },
                        path_admin_status: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_admin_status,
                            "json-data": '"UP"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_subscribe_container_list(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path = "/goldstone-interfaces:interfaces/interface"
                    path_1 = path + "[name='Interface1/0/1']"
                    path_name_1 = path_1 + "/name"
                    path_config_name_1 = path_1 + "/config/name"
                    path_config_admin_status_1 = path_1 + "/config/admin-status"
                    path_2 = path + "[name='Interface1/0/2']"
                    path_name_2 = path_2 + "/name"
                    path_config_name_2 = path_2 + "/config/name"
                    path_config_admin_status_2 = path_2 + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_config_name_1, "Interface1/0/1")
                    sess.set_item(path_config_admin_status_1, "UP")
                    sess.set_item(path_config_name_2, "Interface1/0/2")
                    sess.set_item(path_config_admin_status_2, "DOWN")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": False,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        path_name_1: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_name_1,
                            "json-data": '"Interface1/0/1"',
                        },
                        path_config_name_1: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_config_name_1,
                            "json-data": '"Interface1/0/1"',
                        },
                        path_config_admin_status_1: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_config_admin_status_1,
                            "json-data": '"UP"',
                        },
                        path_name_2: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_name_2,
                            "json-data": '"Interface1/0/2"',
                        },
                        path_config_name_2: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_config_name_2,
                            "json-data": '"Interface1/0/2"',
                        },
                        path_config_admin_status_2: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": path_config_admin_status_2,
                            "json-data": '"DOWN"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_stream_updates_only(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": True,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Update the target data.
                    sess.switch_datastore("running")
                    sess.set_item(path, "DOWN")
                    sess.apply_changes()

                    # Wait sample interval.
                    time.sleep(s["sample-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"DOWN"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_poll_updates_only(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "POLL",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Update the target data.
                    sess.switch_datastore("running")
                    sess.set_item(path, "DOWN")
                    sess.apply_changes()

                    # Send a poll request.
                    sess.rpc_send("/goldstone-telemetry:poll", {"id": params["id"]})

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"DOWN"',
                        },
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_once_updates_only(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "ONCE",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": None,
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": None,
                            }
                        ],
                    }
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_stream_sample_not_suppress_redundant(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": False,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Wait sample interval.
                    time.sleep(s["sample-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_stream_sample_suppress_redundant(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": True,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Wait sample interval.
                    time.sleep(s["sample-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {}
                    self.assertEqual(len(self.received_notif), len(expected_notifs))

        await self.run_test(test)

    async def test_stream_sample_suppress_redundant_but_heartbeat_expired(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": True,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Wait heartbeat interval.
                    time.sleep(s["heartbeat-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_stream_on_change_not_changed(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "ON_CHANGE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Wait default update interval.
                    time.sleep(5)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {}
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_stream_on_change_not_changed_but_heartbeat_expired(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    # Set initial data.
                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "ON_CHANGE",
                                "sample-interval": None,
                                "suppress-redundant": None,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Wait heartbeat interval.
                    time.sleep(s["heartbeat-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)

    async def test_notification_types(self):
        def test():
            time.sleep(self.MOCK_WAIT)
            with sysrepo.SysrepoConnection() as conn:
                with conn.start_session() as sess:
                    # Subscribe notification.
                    sess.subscribe_notification(
                        "goldstone-telemetry",
                        "/goldstone-telemetry:telemetry-notify-event",
                        self.notif_callback,
                        asyncio_register=False,
                    )

                    path_prefix = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']"
                    path = path_prefix + "/config/admin-status"

                    # Add a subscription.
                    params = {
                        "id": 1,
                        "mode": "STREAM",
                        "updates-only": True,
                        "subscriptions": [
                            {
                                "id": 1,
                                "path": path,
                                "mode": "SAMPLE",
                                "sample-interval": 5 * 1000 * 1000 * 1000,
                                "suppress-redundant": True,
                                "heartbeat-interval": 10 * 1000 * 1000 * 1000,
                            }
                        ],
                    }
                    s = params["subscriptions"][0]
                    config_subscription(sess, params)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        "sync-response": {
                            "type": "SYNC_RESPONSE",
                            "request-id": params["id"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Create the target data.
                    sess.switch_datastore("running")
                    sess.set_item(path_prefix + "/config/name", "Interface1/0/1")
                    sess.set_item(path, "UP")
                    sess.apply_changes()

                    # Wait sample interval.
                    time.sleep(s["sample-interval"] / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "UPDATE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                            "json-data": '"UP"',
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)
                    self.clear_received_notif()

                    # Delete the target data.
                    sess.switch_datastore("running")
                    sess.delete_item(path_prefix)
                    sess.apply_changes()

                    # Wait sample interval.
                    time.sleep(s["sample-interval"] * 2 / 1000 / 1000 / 1000)

                    # Receive notifications.
                    time.sleep(self.NOTIFICATION_WAIT)
                    expected_notifs = {
                        s["path"]: {
                            "type": "DELETE",
                            "request-id": params["id"],
                            "subscription-id": s["id"],
                            "path": s["path"],
                        },
                    }
                    self.assertEqual(self.received_notif, expected_notifs)

        await self.run_test(test)


if __name__ == "__main__":
    unittest.main()
