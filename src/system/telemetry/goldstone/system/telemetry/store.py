"""Datastore implementations."""


from abc import abstractmethod
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class TelemetryNotExistError(Exception):
    pass


class TelemetryStore:
    """Base class for telemetry datastore.

    Users should depend on this interface instead of subclass implementations.
    """

    @abstractmethod
    def set(self, ids, path, value):
        """Set a telemetry data.

        If the telemetry data entry does not exist, it creates an entry.

        Args:
            ids (tupple of int): Identifier of the subscription
                0: Outer ID. Request ID.
                1: Inner ID. Subscription ID.
            path (str): Identifier of the telemetry data. Path to a leaf node.
            value (any): The telemetry data to set.
        """
        pass

    @abstractmethod
    def delete(self, ids, path):
        """Delete a telemetry data.

        Args:
            ids (tupple of int): Identifier of the subscription
                0: Outer ID. Request ID.
                1: Inner ID. Subscription ID.
            path (str): Identifier of the telemetry data. Path to a leaf node.

        Raises:
            TelemetryNotExistError: The telemetry data is not found.
        """
        pass

    @abstractmethod
    def get(self, ids, path):
        """Get a telemetry data.

        Args:
            ids (tupple of int): Identifier of the subscription
                0: Outer ID. Request ID.
                1: Inner ID. Subscription ID.
            path (str): Identifier of the telemetry data. Path to a leaf node.

        Returns:
            dict: The telemetry data of the path.
                "value" (any): The telemetry data.
                "update-time" (datetime): Last update time.

        Raises:
            TelemetryNotExistError: The telemetry data is not found.
        """
        pass

    @abstractmethod
    def list(self, ids):
        """Get a telemetry data.

        Args:
            ids (tupple of int): Identifier of the subscription
                0: Outer ID. Request ID.
                1: Inner ID. Subscription ID.

        Returns:
            list of str: Identifiers of telemetry data. Paths to leaf nodes.
        """
        pass


class InMemoryTelemetryStore(TelemetryStore):
    """A telemetry datastore implementation using volatile memory.

    If you want to keep telemetry data after rebooting your application, you should not use this."""

    def __init__(self):
        self._data = {}

    def set(self, ids, path, value):
        outer_id, inner_id = ids
        if outer_id not in self._data.keys():
            self._data[outer_id] = {}
        if inner_id not in self._data[outer_id].keys():
            self._data[outer_id][inner_id] = {}
        data = {
            "value": value,
            "update-time": datetime.now(),
        }
        self._data[outer_id][inner_id][path] = data

    def delete(self, ids, path):
        outer_id, inner_id = ids
        try:
            del self._data[outer_id][inner_id][path]
            if len(self._data[outer_id][inner_id]) <= 0:
                del self._data[outer_id][inner_id]
            if len(self._data[outer_id]) <= 0:
                del self._data[outer_id]
        except KeyError as e:
            raise TelemetryNotExistError() from e

    def get(self, ids, path):
        outer_id, inner_id = ids
        try:
            return self._data[outer_id][inner_id][path]
        except KeyError as e:
            raise TelemetryNotExistError() from e

    def list(self, ids):
        outer_id, inner_id = ids
        outer = self._data.get(outer_id)
        if outer is None:
            return []
        inner = outer.get(inner_id)
        if inner is None:
            return []
        return inner.keys()


class SubscriptionExistError(Exception):
    pass


class SubscriptionNotExistError(Exception):
    pass


class SubscriptionStore:
    """Base class for subscription datastore.

    Users should depend on this interface instead of subclass implementations.
    """

    @abstractmethod
    def add(self, id_, subscription):
        """Add a subscription.

        Args:
            id_ (int): Identifier of the subscription to add.
            subscription (Subscription): A subscription to add.

        Raises:
            SubscriptionExistError: The subscription has been added.
        """
        pass

    @abstractmethod
    def delete(self, id_):
        """Delete a subscription.

        Args:
            id_ (int): Identifier of the subscription to delete.

        Raises:
            SubscriptionNotExistError: The subscription is not found.
        """
        pass

    @abstractmethod
    def get(self, id_):
        """Get a subscription.

        Args:
            id_ (int): Identifier of the subscription to get.

        Returns:
            Subscription: The subscription.

        Raises:
            SubscriptionNotExistError: The subscription is not found.
        """
        pass

    @abstractmethod
    def list(self):
        """Get a list of subscription identifiers.

        Returns:
            list of str: The list of subscription identifiers.
        """
        pass


class InMemorySubscriptionStore(SubscriptionStore):
    """A subscription datastore implementation using volatile memory.

    If you want to keep subscriptions after rebooting your application, you should not use this."""

    def __init__(self):
        self._subscriptions = {}

    def add(self, id_, subscription):
        if id_ in self._subscriptions.keys():
            raise SubscriptionExistError()
        self._subscriptions[id_] = subscription

    def delete(self, id_):
        try:
            del self._subscriptions[id_]
        except KeyError as e:
            raise SubscriptionNotExistError() from e

    def get(self, id_):
        try:
            return self._subscriptions[id_]
        except KeyError as e:
            raise SubscriptionNotExistError() from e

    def list(self):
        return list(self._subscriptions.keys())
