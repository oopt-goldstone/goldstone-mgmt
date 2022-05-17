"""Streaming telemetry servers."""


import logging
import asyncio
import json
from datetime import datetime, timedelta
import sysrepo
import libyang
from goldstone.lib.core import ServerBase, ChangeHandler
from .store import SubscriptionNotExistError, TelemetryNotExistError
from .path import PathParser


logger = logging.getLogger(__name__)


class ValidationFailedError(Exception):
    def __init__(self, msg):
        super().__init__()
        self.msg = msg


class Subscription:
    """Base class of subscriptions.

    It retrieves state data and sends notifications with the central datastore.

    Its behavior follows the gNMI specification. See:
        https://github.com/openconfig/reference/blob/master/rpc/gnmi/gnmi-specification.md#3515-creating-subscriptions

    Args:
        conn (SysrepoConnection): Connection with the central datastore.
        config (dict): Configuration data of the subscription.
        store (store.TelemetryStore): Datastore for telemetry data.
        update_interval (int): Telemetry data update interval in nanoseconds.
    """

    NOTIF_PATH = "goldstone-telemetry:telemetry-notify-event"

    def __init__(self, conn, config, store, update_interval):
        self._conn = conn
        self._config = config
        self._store = store
        self._update_interval = update_interval
        self._path_parser = PathParser(self._conn.ctx)
        self._id = self._config["id"]
        self._updates_only = False
        self._subscriptions = {}
        self._parse_config()
        self._validate_config()

    def _parse_config(self):
        request_config = self._config.get("config")
        if request_config is None:
            request_config = {}
        self._updates_only = request_config.get("updates-only")
        if self._updates_only is None:
            self._updates_only = False
        subscriptions = self._config.get("subscriptions")
        if subscriptions is None:
            subscriptions = {}
        subscriptions = subscriptions.get("subscription")
        if subscriptions is None:
            subscriptions = []
        for subscription in subscriptions:
            sid = subscription.get("id")
            if sid is None:
                continue
            subscription_config = subscription.get("config")
            parsed_subscription = {
                "id": subscription_config.get("id"),
                "path": subscription_config.get("path"),
                "mode": subscription_config.get("mode"),
                "sample-interval": subscription_config.get("sample-interval"),
                "suppress-redundant": subscription_config.get("suppress-redundant"),
                "heartbeat-interval": subscription_config.get("heartbeat-interval"),
            }
            self._subscriptions[sid] = parsed_subscription

    def _validate_config(self):
        for _, config in self._subscriptions.items():
            if config["path"] is None:
                msg = "path is mandatory"
                logger.error("Subscription config validation failed: %s", msg)
                raise ValidationFailedError(msg)
            if not self._path_parser.is_valid_path(config["path"]):
                msg = f"invalid path: {config['path']}"
                logger.error("Subscription config validation failed: %s", msg)
                raise ValidationFailedError(msg)

    def _get_data(self, xpath):
        data = self._conn.get_operational(xpath, strip=False)
        # NOTE: Connector returns a value None instead of raising an exception if the data was not found.
        if data is None:
            logger.info("data for path %s is not found.", xpath)
            data = {}
        return self._path_parser.parse_dict_into_leaves(data, xpath)

    def _send_notification(self, notif):
        """Send a notification.

        Args:
            notif (dict): Notification to send.
        """
        self._conn.send_notification(self.NOTIF_PATH, notif)

    def _send_sync_response(self):
        notif = {
            "type": "SYNC_RESPONSE",
            "request-id": self._id,
        }
        self._send_notification(notif)

    def _retrieve_current_data(self):
        for sid, subscription in self._subscriptions.items():
            path = subscription["path"]
            data = self._get_data(path)
            for sub_path, value in data.items():
                self._store.set((self._id, sid), sub_path, value)

    def _send_current_data(self):
        for sid, _ in self._subscriptions.items():
            ids = (self._id, sid)
            sub_paths = self._store.list(ids)
            for sub_path in sub_paths:
                data = self._store.get(ids, sub_path)
                notif = {
                    "type": "UPDATE",
                    "request-id": self._id,
                    "subscription-id": sid,
                    "path": sub_path,
                    "json-data": json.dumps(data["value"]),
                }
                self._send_notification(notif)

    async def start(self):
        """Start the subscription."""
        # Start session in __init__() because it will be used to parse and validate configuration parameters.
        self._retrieve_current_data()
        if not self._updates_only:
            self._send_current_data()
        self._send_sync_response()

    async def stop(self):
        """Stop the subscription."""
        pass

    def get_state(self):
        """Get subscription state.

        Returns:
            dict: subscription state data.
        """
        subscriptions = []
        for sid, subscription in self._subscriptions.items():
            subscriptions.append(
                {
                    "id": sid,
                    "path": subscription["path"],
                    "mode": subscription["mode"],
                    "sample-interval": subscription["sample-interval"],
                    "suppress-redundant": subscription["suppress-redundant"],
                    "heartbeat-interval": subscription["heartbeat-interval"],
                }
            )
        return {
            "id": self._config["id"],
            "mode": self._config["config"]["mode"],
            "updates-only": self._updates_only,
            "subscriptions": subscriptions,
        }


class StreamSubscription(Subscription):
    """Subscription for the STREAM mode."""

    HEARTBEAT_DISABLED = 0

    def __init__(self, conn, config, store, update_interval):
        self._default_sampling_interval = update_interval * 2
        super().__init__(conn, config, store, update_interval)
        self._loop_tasks = {}

    def _target_defined_mode(self, path):
        # NOTE: Select the mode by provided path.
        return "SAMPLE"

    def _parse_config(self):
        super()._parse_config()
        for _, subscription in self._subscriptions.items():
            if subscription["sample-interval"] is None:
                subscription["sample-interval"] = self._default_sampling_interval
            if subscription["suppress-redundant"] is None:
                subscription["suppress-redundant"] = False
            if subscription["heartbeat-interval"] is None:
                subscription["heartbeat-interval"] = self.HEARTBEAT_DISABLED
            if subscription["mode"] == "TARGET_DEFINED":
                subscription["mode"] = self._target_defined_mode(subscription["path"])

    def _validate_config(self):
        super()._validate_config()
        for _, config in self._subscriptions.items():
            if config["mode"] is None:
                msg = "mode is mandatory"
                logger.error("Subscription config validation failed: %s", msg)
                raise ValidationFailedError(msg)
            if (
                config["heartbeat-interval"] < self._update_interval
                and config["heartbeat-interval"] != self.HEARTBEAT_DISABLED
            ):
                msg = f"heartbeat-interval is shorter than minimum interval {self._update_interval}"
                logger.error("Subscription config validation failed: %s", msg)
                raise ValidationFailedError(msg)
            if config["mode"] == "SAMPLE":
                if config["sample-interval"] < self._update_interval:
                    msg = f"sample-interval is shorter than minimum interval {self._update_interval}"
                    logger.error("Subscription config validation failed: %s", msg)
                    raise ValidationFailedError(msg)

    async def start(self):
        await super().start()
        loops = {
            "ON_CHANGE": self._on_change_loop,
            "SAMPLE": self._sample_loop,
        }
        for _, subscription in self._subscriptions.items():
            try:
                self._loop_tasks[subscription["id"]] = asyncio.create_task(
                    loops[subscription["mode"]](subscription)
                )
            except KeyError:
                continue

    async def stop(self):
        for _, loop_task in self._loop_tasks.items():
            loop_task.cancel()
        for _, loop_task in self._loop_tasks.items():
            while True:
                if loop_task.done():
                    break
                await asyncio.sleep(0.1)
        await super().stop()

    def _should_send_notif(self, config, ids, sub_path, value):
        send_notif = True
        suppress_redundant = (
            config["suppress-redundant"] or config["mode"] == "ON_CHANGE"
        )
        hb = timedelta(microseconds=config["heartbeat-interval"] / 1000)
        if suppress_redundant:
            try:
                prev_data = self._store.get(ids, sub_path)
                hb_expired = False
                if hb > timedelta(0):
                    hb_expired = (datetime.now() - prev_data["update-time"]) > hb
                if value == prev_data["value"] and not hb_expired:
                    send_notif = False
            except TelemetryNotExistError:
                # The data node of the sub_path is created.
                pass
        return send_notif

    def _sample_and_notify(self, config):
        ids = (self._id, config["id"])
        data = self._get_data(config["path"])
        currents = set(self._store.list(ids))
        exists = set()
        # Created or updated data nodes.
        for sub_path, value in data.items():
            exists.add(sub_path)
            if self._should_send_notif(config, ids, sub_path, value):
                self._store.set(ids, sub_path, value)
                notif = {
                    "type": "UPDATE",
                    "request-id": self._id,
                    "subscription-id": config["id"],
                    "path": sub_path,
                    "json-data": json.dumps(value),
                }
                self._send_notification(notif)
        # Deleted data nodes.
        for sub_path in currents - exists:
            try:
                self._store.delete(ids, sub_path)
            except TelemetryNotExistError:
                pass
            notif = {
                "type": "DELETE",
                "request-id": self._id,
                "subscription-id": config["id"],
                "path": sub_path,
            }
            self._send_notification(notif)

    async def _on_change_loop(self, config):
        while True:
            # NOTE: We should subscribe state change notifications with the central datastore if it is possible. To do
            #   it, we need to design the archtecture and implement it into the model server daemons. Until then, we
            #   will use this polling implementation.
            await asyncio.sleep(self._update_interval / 1000 / 1000 / 1000)
            try:
                self._sample_and_notify(config)
            except Exception as e:
                logger.error(
                    "Failed to update current state and send notification. %s: %s",
                    type(e).__name__,
                    e,
                )

    async def _sample_loop(self, config):
        while True:
            await asyncio.sleep(config["sample-interval"] / 1000 / 1000 / 1000)
            try:
                self._sample_and_notify(config)
            except Exception as e:
                logger.error(
                    "Failed to update current state and send notification. %s: %s",
                    type(e).__name__,
                    e,
                )


class OnceSubscription(Subscription):
    """Subscription for the ONCE mode."""

    pass


class PollSubscription(Subscription):
    """Subscription for the POLL mode."""

    async def poll_cb(self, xpath, inputs, event, priv):
        """Callback function for a poll request.

        Args:
            xpath (str): Full data path of the request.
            inputs (dict): Input parameters.
            event (str): Event type of the callback. It is always "rpc". Don't care.
            priv (any): Private data from the request subscribing.
        """
        self._retrieve_current_data()
        self._send_current_data()
        self._send_sync_response()


class SubscribeRequestTypedHandler:
    """Base handler class for each change types of subscribe-request.

    Args:
        rid (int): Identification of the subscribe-request.
        change (sysrepo.Change): Change to apply.
    """

    def __init__(self, rid, change):
        self._id = rid
        self._change = change

    def validate(self, user):
        """Validate the change.

        Args:
            user (dict): User defined data.
        """
        pass

    async def apply(self, user):
        """Apply the change.

        Args:
            user (dict): User defined data.
        """
        pass

    async def revert(self, user):
        """Revert the change.

        Args:
            user (dict): User defined data.
        """
        pass


class SubscribeRequestCreatedHandler(SubscribeRequestTypedHandler):
    """Handler for a created subscribe-request."""

    SUBSCRIPTIONS = {
        "STREAM": StreamSubscription,
        "ONCE": OnceSubscription,
        "POLL": PollSubscription,
    }

    def __init__(self, rid, change):
        super().__init__(rid, change)
        self._config = self._change.value

    def validate(self, user):
        try:
            mode = self._config["config"]["mode"]
        except KeyError as e:
            msg = "mode should be specified"
            logger.error(msg)
            raise sysrepo.SysrepoInvalArgError(msg) from e
        try:
            self._subscription = self.SUBSCRIPTIONS[mode](
                user["conn"],
                self._config,
                user["telemetry-store"],
                user["update-interval"],
            )
        except KeyError as e:
            msg = f"invalid mode {mode}"
            logger.error(msg)
            raise sysrepo.SysrepoInvalArgError(msg) from e
        except ValidationFailedError as e:
            msg = f"invalid subscription parameter: {e.msg}"
            logger.error(msg)
            raise sysrepo.SysrepoInvalArgError(msg) from e

    async def apply(self, user):
        user["subscription-store"].add(self._id, self._subscription)
        await self._subscription.start()

    async def revert(self, user):
        await self._subscription.stop()
        user["subscription-store"].delete(self._id)


class SubscribeRequestModifiedHandler(SubscribeRequestTypedHandler):
    """Handler for a modified subscribe-request."""

    def __init__(self, rid, change):
        super().__init__(rid, change)
        msg = "subscription modification is not supported"
        logger.error(msg)
        raise sysrepo.SysrepoUnsupportedError(msg)


class SubscribeRequestDeletedHandler(SubscribeRequestTypedHandler):
    """Handler for a deleted subscribe-request."""

    def validate(self, user):
        try:
            self._subscription = user["subscription-store"].get(self._id)
        except SubscriptionNotExistError as e:
            msg = f"invalid id {self._id}"
            logger.error(msg)
            raise sysrepo.SysrepoInvalArgError(msg) from e

    async def apply(self, user):
        await self._subscription.stop()
        user["subscription-store"].delete(self._id)

    async def revert(self, user):
        user["subscription-store"].add(self._id, self._subscription)
        await self._subscription.start()


class SubscribeRequestChangeHandler(ChangeHandler):
    """ChangeHndler for a subscribe-request."""

    TYPES = {
        "created": SubscribeRequestCreatedHandler,
        "modified": SubscribeRequestModifiedHandler,
        "deleted": SubscribeRequestDeletedHandler,
    }

    def __init__(self, server, change):
        super().__init__(server, change)
        self.xpath = list(libyang.xpath_split(change.xpath))
        self._noop = False
        if not (
            len(self.xpath) == 2
            and self.xpath[0][0] == "goldstone-telemetry"
            and self.xpath[0][1] == "subscribe-requests"
            and self.xpath[1][1] == "subscribe-request"
            and self.xpath[1][2][0][0] == "id"
        ):
            self._noop = True
        if not self._noop:
            logger.debug("SubscribeRequestChangeHandler: %s", change)
        self._handler = self.TYPES[self.type](int(self.xpath[1][2][0][1]), self.change)

    def validate(self, user):
        if self._noop:
            return
        self._handler.validate(user)

    async def apply(self, user):
        if self._noop:
            return
        await self._handler.apply(user)

    async def revert(self, user):
        if self._noop:
            return
        await self._handler.revert(user)


class TelemetryServer(ServerBase):
    """goldstone-terlemetry server.

    The server manages telemetry subscriptions requested via goldstone-telemetry.

    Args:
        subscription_store (store.SubscriptionStore): Datastore for managed subscriptions.
        telemetry_store (store.TelemetryStore): Datastore for telemetry data.
        update_interval (int): Telemetry data update interval in seconds.
    """

    DEFAULT_UPDATE_INTERVAL = 5

    def __init__(
        self,
        conn,
        subscription_store,
        telemetry_store,
        update_interval=DEFAULT_UPDATE_INTERVAL,
    ):
        super().__init__(conn, "goldstone-telemetry")
        self._subscription_store = subscription_store
        self._telemetry_store = telemetry_store
        self._update_interval = update_interval * 1000 * 1000 * 1000
        self.handlers = {
            "subscribe-requests": {"subscribe-request": SubscribeRequestChangeHandler}
        }

    async def start(self):
        """Start a service."""
        tasks = await super().start()
        # NOTE: The sysrepo v1 doesn't support subscriptions to specific "data" instances. It supports subscriptions to
        #   "schema" nodes. So, we should share a subscription to the RPC "/poll" for all POLL mode subscribe requests.
        #   The sysrepo v2 supports subscriptions to specific "data" instances. Then, we can subscribe an action for a
        #   data instance of a subscribe request like "/subscribe-requests/subscribe-request[id='{request-id}']/poll".
        #   See also:
        #   - https://github.com/sysrepo/sysrepo/issues/1255
        #   - https://github.com/sysrepo/sysrepo/issues/1438
        xpath = "/goldstone-telemetry:poll"
        self.conn.subscribe_rpc_call(xpath, self.poll_cb)
        return tasks

    async def stop(self):
        """Stop a service."""
        for rid in self._subscription_store.list():
            await self._subscription_store.get(rid).stop()
        super().stop()

    def pre(self, user):
        """Pre action for changes."""
        user["conn"] = self.conn.conn
        user["subscription-store"] = self._subscription_store
        user["telemetry-store"] = self._telemetry_store
        user["update-interval"] = self._update_interval

    async def poll_cb(self, xpath, inputs, event, priv):
        """Callback function for a poll request.

        Args:
            xpath (str): Full data path of the request.
            inputs (dict): Input parameters.
            event (str): Event type of the callback. It is always "rpc". Don't care.
            priv (any): Private data from the request subscribing.
        """
        logger.info(
            "poll_cb - xpath: %s, inputs: %s, event: %s",
            xpath,
            inputs,
            event,
        )
        rid = inputs["id"]
        logger.info("Poll request for %s.", rid)
        subscription = self._subscription_store.get(rid)
        await subscription.poll_cb(xpath, inputs, event, priv)

    async def oper_cb(self, xpath, priv):
        """Callback function for a operational state request.

        Args:
            xpath (str): Full data path of the request.
            priv (any): Private data from the request subscribing.
        """
        subscribe_requests = []
        for rid in self._subscription_store.list():
            subscription = self._subscription_store.get(rid)
            data = subscription.get_state()
            subscribe_request = {
                "id": data["id"],
                "state": {
                    "id": data["id"],
                    "mode": data["mode"],
                },
            }
            if data["updates-only"] is not None:
                subscribe_request["state"]["updates-only"] = data["updates-only"]
            internal_subscriptions = []
            for internal_subscription_data in data["subscriptions"]:
                internal_subscription = {
                    "id": internal_subscription_data["id"],
                    "state": {
                        "id": internal_subscription_data["id"],
                        "path": internal_subscription_data["path"],
                    },
                }
                if internal_subscription_data["mode"] is not None:
                    internal_subscription["state"]["mode"] = internal_subscription_data[
                        "mode"
                    ]
                if internal_subscription_data["sample-interval"] is not None:
                    internal_subscription["state"][
                        "sample-interval"
                    ] = internal_subscription_data["sample-interval"]
                if internal_subscription_data["suppress-redundant"] is not None:
                    internal_subscription["state"][
                        "suppress-redundant"
                    ] = internal_subscription_data["suppress-redundant"]
                if internal_subscription_data["heartbeat-interval"] is not None:
                    internal_subscription["state"][
                        "heartbeat-interval"
                    ] = internal_subscription_data["heartbeat-interval"]
                internal_subscriptions.append(internal_subscription)
            if len(internal_subscriptions) > 0:
                subscribe_request["subscriptions"] = {
                    "subscription": internal_subscriptions
                }
            subscribe_requests.append(subscribe_request)
        return {
            "subscribe-requests": {
                "subscribe-request": subscribe_requests,
            }
        }
