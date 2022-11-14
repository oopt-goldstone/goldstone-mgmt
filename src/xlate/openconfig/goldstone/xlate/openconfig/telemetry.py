"""OpenConfig translator for openconfig-telemetry.

Target OpenConfig object is dynamic-subscription
("openconfig-telemetry:telemetry-system/subscriptions/dynamic-subscriptions/dynamic-subscription") for now. You can add
persistent-subscriptions and related objects.

OpenConfig dynamic-subscription is represented as the DynamicSubscription class.
"""


from .lib import OpenConfigObjectFactory, OpenConfigServer


class DynamicSubscription:
    """Represents /openconfig-telemetry:telemetry-system/subscriptions/dynamic-subscriptions/dynamic-sybscription
    object.

    Args:
        subscribe_request (dict): /goldstone-telemetry:subscribe-requests/subscribe-request
        subscription (dict): /goldstone-telemetry:subscribe-requests/subscribe-request/subscriptions/subscription

    Attributes:
        subscribe_request (dict): /goldstone-telemetry:subscribe-requests/subscribe-request
        subscription (dict): /goldstone-telemetry:subscribe-requests/subscribe-request/subscriptions/subscription
        data (dict): Operational state data
    """

    def __init__(self, subscribe_request, subscription):
        self.subscribe_request = subscribe_request
        self.subscription = subscription
        self.data = {
            "state": {
                "protocol": "openconfig-telemetry-types:STREAM_GRPC",
                "encoding": "openconfig-telemetry-types:ENC_JSON_IETF",
            },
            "sensor-paths": {
                "sensor-path": [],
            },
        }

    def _id(self, srid, sid):
        """
        Args:
            srid (int): /goldstone-telemetry:subscribe-requests/subscribe-request/id
                uint32
            sid (int): /goldstone-telemetry:subscribe-requests/subscribe-request/subscriptions/sunscription/id
                uint32

        Returns:
            uint64: /openconfig-telemetry:telemetry-system/subscriptions/dynamic-subscriptions/dynamic-subscription/id
                uint64
        """
        return (srid << 32) + sid

    def translate(self):
        """Set dynamic-subscription operational state data from Goldstone operational state data."""
        id_ = self._id(self.subscribe_request["id"], self.subscription["id"])
        self.data["id"] = id_
        self.data["state"]["id"] = id_
        path = self.subscription["state"]["path"]
        sensor_path = {
            "path": path,
            "state": {
                "path": path,
            },
        }
        self.data["sensor-paths"]["sensor-path"].append(sensor_path)
        sample_interval = self.subscription["state"].get("sample-interval")
        if sample_interval is not None:
            self.data["state"]["sample-interval"] = sample_interval
        heartbeat_interval = self.subscription["state"].get("heartbeat-interval")
        if heartbeat_interval is not None:
            self.data["state"]["heartbeat-interval"] = heartbeat_interval
        suppress_redundant = self.subscription["state"].get("suppress-redundant")
        if suppress_redundant is not None:
            self.data["state"]["suppress-redundant"] = suppress_redundant


class DynamicSubscriptionFactory(OpenConfigObjectFactory):
    """Create OpenConfig dynamic-subscriptions from Goldstone operational state data.

    Attributes:
        gs (dict): Operational state data from Goldstone native/primitive models.
    """

    def required_data(self):
        return [
            {
                "name": "subscribe-requests",
                "xpath": "/goldstone-telemetry:subscribe-requests/subscribe-request",
                "default": [],
            },
        ]

    def create(self, gs):
        result = []
        for subscribe_request in gs["subscribe-requests"]:
            sr_state = subscribe_request.get("state")
            subscriptions = None
            sr_subscriptions = subscribe_request.get("subscriptions")
            if sr_subscriptions is not None:
                subscriptions = sr_subscriptions.get("subscription")
            if subscriptions is None:
                subscriptions = []
            for subscription in subscriptions:
                ds = DynamicSubscription(sr_state, subscription)
                ds.translate()
                result.append(ds.data)
        return result


class TelemetryServer(OpenConfigServer):
    """TelemetryServer provides a service for the openconfig-telemetry module to central datastore.

    The server provides operational state information of subscriptions.
    """

    def __init__(self, conn, reconciliation_interval=10):
        super().__init__(conn, "openconfig-telemetry", reconciliation_interval)
        self.handlers = {"telemetry-system": {}}
        self.objects = {
            "telemetry-system": {
                "subscriptions": {
                    "dynamic-subscriptions": {
                        "dynamic-subscription": DynamicSubscriptionFactory()
                    }
                }
            }
        }
