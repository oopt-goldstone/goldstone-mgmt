"""Tests for datastores."""

import unittest
import datetime
from goldstone.lib.connector.sysrepo import Connector
from goldstone.system.telemetry.store import (
    InMemoryTelemetryStore,
    TelemetryNotExistError,
    InMemorySubscriptionStore,
    SubscriptionExistError,
    SubscriptionNotExistError,
)
from goldstone.system.telemetry.telemetry import Subscription


class TestInMemoryTelemetryStore(unittest.TestCase):
    """Tests for InMemoryTelemetryStore."""

    def test_set(self):
        ts = InMemoryTelemetryStore()
        ids = (1, 1)
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
        value = "UP"
        # Create an entry.
        self.assertFalse(path in ts.list(ids))
        before = datetime.datetime.now()
        ts.set(ids, path, value)
        after = datetime.datetime.now()
        self.assertTrue(path in ts.list(ids))
        stored_telemetry = ts.get(ids, path)
        self.assertEqual(stored_telemetry["value"], value)
        self.assertTrue(before <= stored_telemetry["update-time"] <= after)
        # Update an entry.
        new_value = "DOWN"
        self.assertTrue(path in ts.list(ids))
        before = datetime.datetime.now()
        ts.set(ids, path, new_value)
        after = datetime.datetime.now()
        self.assertTrue(path in ts.list(ids))
        stored_telemetry = ts.get(ids, path)
        self.assertEqual(stored_telemetry["value"], new_value)
        self.assertTrue(before <= stored_telemetry["update-time"] <= after)

    def test_delete(self):
        ts = InMemoryTelemetryStore()
        ids = (1, 1)
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
        value = "UP"
        ts.set(ids, path, value)
        self.assertTrue(path in ts.list(ids))
        ts.delete(ids, path)
        self.assertFalse(path in ts.list(ids))

    def test_delete_not_exist(self):
        ts = InMemoryTelemetryStore()
        ids = (1, 1)
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
        self.assertFalse(path in ts.list(ids))
        with self.assertRaises(TelemetryNotExistError):
            ts.delete(ids, path)

    def test_get(self):
        ts = InMemoryTelemetryStore()
        ids = (1, 1)
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
        value = "UP"
        ts.set(ids, path, value)
        self.assertTrue(path in ts.list(ids))
        stored_telemetry = ts.get(ids, path)
        self.assertEqual(stored_telemetry["value"], value)

    def test_get_not_exist(self):
        ts = InMemoryTelemetryStore()
        ids = (1, 1)
        path = "/goldstone-interfaces:interfaces/interface[name='Interface1/0/1']/config/admin-status"
        self.assertFalse(path in ts.list(ids))
        with self.assertRaises(TelemetryNotExistError):
            ts.get(ids, path)


class TestInMemorySubscriptionStore(unittest.TestCase):
    """Tests for InMemorySubscriptionStore."""

    def test_add(self):
        conn = Connector()
        ss = InMemorySubscriptionStore()
        ts = InMemoryTelemetryStore()
        id_1 = 1
        subscription = Subscription(conn, {"id": id_1}, ts, 5)
        ss.add(id_1, subscription)
        self.assertTrue(id_1 in ss.list())
        stored_subscription = ss.get(id_1)
        self.assertEqual(stored_subscription, subscription)

    def test_add_exist(self):
        conn = Connector()
        ss = InMemorySubscriptionStore()
        ts = InMemoryTelemetryStore()
        id_1 = 1
        subscription = Subscription(conn, {"id": id_1}, ts, 5)
        ss.add(id_1, subscription)
        with self.assertRaises(SubscriptionExistError):
            ss.add(id_1, subscription)

    def test_delete(self):
        conn = Connector()
        ss = InMemorySubscriptionStore()
        ts = InMemoryTelemetryStore()
        id_1 = 1
        subscription = Subscription(conn, {"id": id_1}, ts, 5)
        ss.add(id_1, subscription)
        self.assertTrue(id_1 in ss.list())
        ss.delete(id_1)
        self.assertFalse(id_1 in ss.list())

    def test_delete_not_exist(self):
        ss = InMemorySubscriptionStore()
        with self.assertRaises(SubscriptionNotExistError):
            ss.delete(1)

    def test_get(self):
        conn = Connector()
        ss = InMemorySubscriptionStore()
        ts = InMemoryTelemetryStore()
        id_1 = 1
        subscription_1 = Subscription(conn, {"id": id_1}, ts, 5)
        ss.add(id_1, subscription_1)
        id_2 = 2
        subscription_2 = Subscription(conn, {"id": id_2}, ts, 5)
        ss.add(id_2, subscription_2)
        stored_subscription_1 = ss.get(id_1)
        stored_subscription_2 = ss.get(id_2)
        self.assertEqual(stored_subscription_1, subscription_1)
        self.assertEqual(stored_subscription_2, subscription_2)

    def test_get_not_exist(self):
        conn = Connector()
        ss = InMemorySubscriptionStore()
        ts = InMemoryTelemetryStore()
        id_1 = 1
        subscription_1 = Subscription(conn, {"id": id_1}, ts, 5)
        ss.add(id_1, subscription_1)
        with self.assertRaises(SubscriptionNotExistError):
            ss.delete(2)

    def test_list(self):
        conn = Connector()
        ss = InMemorySubscriptionStore()
        ts = InMemoryTelemetryStore()
        self.assertEqual(ss.list(), [])
        id_1 = 1
        subscription = Subscription(conn, {"id": id_1}, ts, 5)
        ss.add(id_1, subscription)
        self.assertEqual(ss.list(), [id_1])
        id_2 = 2
        subscription = Subscription(conn, {"id": id_2}, ts, 5)
        ss.add(id_2, subscription)
        self.assertEqual(ss.list(), [id_1, id_2])


if __name__ == "__main__":
    unittest.main()
