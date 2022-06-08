"""gNMI server."""


import re
import logging
from concurrent import futures
import json
import time
import grpc
import random
import libyang
from .proto import gnmi_pb2_grpc, gnmi_pb2
from .repo.repo import NotFoundError, ApplyFailedError


logger = logging.getLogger(__name__)


GRPC_STATUS_CODE_OK = grpc.StatusCode.OK.value[0]
GRPC_STATUS_CODE_UNKNOWN = grpc.StatusCode.UNKNOWN.value[0]
GRPC_STATUS_CODE_INVALID_ARGUMENT = grpc.StatusCode.INVALID_ARGUMENT.value[0]
GRPC_STATUS_CODE_NOT_FOUND = grpc.StatusCode.NOT_FOUND.value[0]
GRPC_STATUS_CODE_ABORTED = grpc.StatusCode.ABORTED.value[0]
GRPC_STATUS_CODE_UNIMPLEMENTED = grpc.StatusCode.UNIMPLEMENTED.value[0]
REGEX_PTN_LIST_KEY = re.compile(r"\[.*.*\]")


class InvalidArgumentError(Exception):
    pass


def _parse_gnmi_path(gnmi_path):
    xpath = ""
    for elem in gnmi_path.elem:
        xpath += f"/{elem.name}"
        if elem.key:
            for key in sorted(elem.key):
                value = elem.key.get(key)
                xpath += f"[{key}='{value}']"
    return xpath


def _build_gnmi_path(xpath):
    gnmi_path = gnmi_pb2.Path()
    elements = list(libyang.xpath_split(xpath))
    for elem in elements:
        prefix = elem[0]
        name = elem[1]
        if prefix is not None:
            name = f"{prefix}:{name}"
        keys = {}
        for kv_peer in elem[2]:
            keys[kv_peer[0]] = kv_peer[1]
        if len(keys) > 0:
            path_elem = gnmi_pb2.PathElem(name=name, key=keys)
        else:
            path_elem = gnmi_pb2.PathElem(name=name)
        gnmi_path.elem.append(path_elem)
    return gnmi_path


class Request:
    """Base class of Request for gNMI services.

    Args:
        repo (Repository): Repository to access the datastore.
        prefix (gnmi_pb2.Path): Path prefix as gNMI Path.
        path (gnmi_pb2.Path): Path as gNMI Path.

    Attributes:
        repo (Repository): Repository to access the datastore.
        prefix (gnmi_pb2.Path): Path prefix as gNMI Path.
        path (gnmi_pb2.Path): Path as gNMI Path.
        xpath (str): Xpath in absolute path. It is made from prefix and path.
        status (gnmi_pb2.Error): Processing status of this request.
    """

    def __init__(self, repo, prefix, gnmi_path):
        self.repo = repo
        self.prefix = prefix
        self.gnmi_path = gnmi_path
        self.xpath = _parse_gnmi_path(prefix) + _parse_gnmi_path(gnmi_path)
        logger.debug("Requested xpath: %s", self.xpath)
        self.status = gnmi_pb2.Error(
            code=GRPC_STATUS_CODE_OK,
            message=None,
        )

    def exec(self):
        """Execute the request.

        Note:
            A subclass should implement this method.
        """
        pass


class GetRequest(Request):
    """Request for the gNMI Get service.

    Note:
        Add foo_result() methods to get retrieved data in other formats.

    Attributes:
        result (any): Retrieved data according to the requested path from the datastore.
        timestamp (int): Timestamp of the data. It is nanoseconds since the Unix epoch.
    """

    def exec(self):
        self.timestamp = time.time_ns()
        try:
            self.result = self.repo.get(self.xpath)
        except NotFoundError as e:
            msg = f"failed to retrieve data from datastore. {self.xpath} is not found. {e}"
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_NOT_FOUND
            self.status.message = msg
        except ValueError as e:
            msg = (
                f"failed to retrieve data from datastore. {self.xpath} is invalid. {e}"
            )
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_INVALID_ARGUMENT
            self.status.message = msg
        except Exception as e:
            msg = f"failed to retrieve data from datastore. {e}"
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_UNKNOWN
            self.status.message = msg

    def json_result(self):
        """Get retrieved data in JSON format.

        Returns:
            str: Retrieved data in JSON format.
        """
        return json.dumps(self.result)


class SetRequest(Request):
    """Base class for each SetRequest operation; DELETE, REPLACE and UPDATE.

    Attributes:
        val (any): Decoded value to set.
        leaves (dict): Dictionary which returns values to set with xpath of leaf.
    """

    def __init__(self, repo, prefix, gnmi_path):
        super().__init__(repo, prefix, gnmi_path)
        self.leaves = {}

    def _decode_val(self, val):
        if val.HasField("json_val"):
            return json.loads(val.json_val)
        else:
            t = val.WhichOneof("value")
            msg = f"encoding {t} is not supported."
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_UNIMPLEMENTED
            self.status.message = msg

    def _is_container(self, val):
        return isinstance(val, dict)

    def _is_container_list(self, val):
        if isinstance(val, list):
            for v in val:
                if isinstance(v, dict):
                    return True
        return False

    def _xpath_with_keys(self, container, path):
        keys_str = ""
        try:
            keys = self.repo.get_list_keys(path)
        except ValueError as e:
            msg = f"failed to parse value. {self.xpath} is invalid. {e}"
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_INVALID_ARGUMENT
            self.status.message = msg
            return
        if len(keys) == 0:
            msg = f"failed to parse value. '{path}' should not be container-list."
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_INVALID_ARGUMENT
            self.status.message = msg
            return
        for key in keys:
            val = container.get(key)
            if val is None:
                msg = f"failed to parse value. key '{key}' is required for the container-list. xpath: {path}, value: {container}."
                logger.error(msg)
                self.status.code = GRPC_STATUS_CODE_INVALID_ARGUMENT
                self.status.message = msg
                return
            keys_str = f"{keys_str}[{key}='{val}']"
        return f"{path}{keys_str}"

    def _get_leaves(self, val, path):
        if self._is_container(val):
            for k, v in val.items():
                next_path = f"{path}/{k}"
                self._get_leaves(v, next_path)
        elif self._is_container_list(val):
            for container in val:
                next_path = self._xpath_with_keys(container, path)
                # Add container instance.
                self.leaves[next_path] = None
                self._get_leaves(container, next_path)
        else:
            self.leaves[path] = val

    def _parse_val_into_leaves(self, val):
        decoded_val = self._decode_val(val)
        self.val = decoded_val
        if decoded_val is not None:
            if self._is_container(decoded_val) or self._is_container_list(decoded_val):
                self._get_leaves(decoded_val, self.xpath)
            else:
                self.leaves[self.xpath] = decoded_val


class DeleteRequest(SetRequest):
    """SetRequest for operation DELETE.

    Attributes:
        operation: Operation type of the Set service. To be specified "DELETE".
    """

    def __init__(self, repo, prefix, gnmi_path):
        super().__init__(repo, prefix, gnmi_path)
        self.operation = gnmi_pb2.UpdateResult.Operation.DELETE

    def exec(self):
        try:
            self.repo.delete(self.xpath)
        except NotFoundError:
            # Silently accept.
            logger.info(
                "%s is not found. But the DeleteRequest() for the path is accepted.",
                self.xpath,
            )
        except ValueError as e:
            msg = f"failed to delete. {self.xpath} is invalid. {e}"
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_INVALID_ARGUMENT
            self.status.message = msg
        except Exception as e:
            msg = f"failed to delete. xpath: {self.xpath}. {e}"
            logger.error(msg)
            self.status.code = GRPC_STATUS_CODE_UNKNOWN
            self.status.message = msg


class ReplaceRequest(SetRequest):
    """SetRequest for operation REPLACE.

    Attributes:
        operation: Operation type of the Set service. To be specified "REPLACE".
    """

    def __init__(self, repo, prefix, gnmi_path, val):
        super().__init__(repo, prefix, gnmi_path)
        self.operation = gnmi_pb2.UpdateResult.Operation.REPLACE
        self._parse_val_into_leaves(val)

    def exec(self, repo):
        # TODO: Delete value of not specified leaves. If default value is specified, the datastore will set the value.
        # TODO: Set value of specified leaves.
        pass


class UpdateRequest(SetRequest):
    """SetRequest for operation UPDATE.

    Attributes:
        operation: Operation type of the Set service. To be specified "UPDATE".
    """

    def __init__(self, repo, prefix, gnmi_path, val):
        super().__init__(repo, prefix, gnmi_path)
        self.operation = gnmi_pb2.UpdateResult.Operation.UPDATE
        self._parse_val_into_leaves(val)

    def exec(self):
        for k in self.leaves:
            val = self.leaves.get(k)
            if not isinstance(val, list):
                val = [val]
            for v in val:
                logger.debug("Update leaf: %s = %s", k, v)
                try:
                    self.repo.set(k, v)
                except ValueError as e:
                    msg = f"failed to update. xpath: {k} or value: {v} is invalid. {e}"
                    logger.error(msg)
                    self.status.code = GRPC_STATUS_CODE_INVALID_ARGUMENT
                    self.status.message = msg
                    return
                except Exception as e:
                    msg = f"failed to update. xpath: {k}, value: {v}. {e}"
                    logger.error(msg)
                    self.status.code = GRPC_STATUS_CODE_UNKNOWN
                    self.status.message = msg
                    return


class SubscribeRequest:
    """Request for gNMI Subscribe service.

    Attributes:
        repo (Repository): Repository to access the datastore.
        rid (int): Request ID.
        subscribe (gnmi_pb2.SubscriptionList): gNMI subscribe request body.
    """

    PATH_SR = "/goldstone-telemetry:subscribe-requests/subscribe-request[id='{}']"
    PATH_POLL = "/goldstone-telemetry:poll"

    SUBSCRIBE_REQUEST_MODES = {
        gnmi_pb2.SubscriptionList.Mode.STREAM: "STREAM",
        gnmi_pb2.SubscriptionList.Mode.ONCE: "ONCE",
        gnmi_pb2.SubscriptionList.Mode.POLL: "POLL",
    }

    SUBSCRIPTION_MODES = {
        gnmi_pb2.SubscriptionMode.TARGET_DEFINED: "TARGET_DEFINED",
        gnmi_pb2.SubscriptionMode.ON_CHANGE: "ON_CHANGE",
        gnmi_pb2.SubscriptionMode.SAMPLE: "SAMPLE",
    }

    def __init__(self, repo, rid, subscribe):
        self._repo = repo
        self._rid = rid
        self._config = self._parse_config(subscribe)
        self._notifs = []

    def _parse_subscription_config(self, sid, config):
        if not config.HasField("path"):
            msg = "path should be specified."
            logger.error(msg)
            raise InvalidArgumentError(msg)
        try:
            mode = self.SUBSCRIPTION_MODES[config.mode]
        except KeyError as e:
            msg = f"mode has an invalid value {config.mode}."
            logger.error(msg)
            raise InvalidArgumentError(msg) from e
        return {
            "id": sid,
            "path": _parse_gnmi_path(config.path),
            "mode": mode,
            "sample-interval": config.sample_interval,
            "suppress-redundant": config.suppress_redundant,
            "heartbeat-interval": config.heartbeat_interval,
        }

    def _parse_config(self, config):
        try:
            mode = self.SUBSCRIBE_REQUEST_MODES[config.mode]
        except KeyError as e:
            raise InvalidArgumentError(
                f"mode has an invalid value {config.mode}."
            ) from e
        subscriptions = []
        for sid, subscription in enumerate(config.subscription):
            subscriptions.append(self._parse_subscription_config(sid, subscription))
        return {
            "id": self._rid,
            "mode": mode,
            "updates-only": config.updates_only,
            "subscriptions": subscriptions,
        }

    def exec(self):
        prefix = self.PATH_SR.format(self._rid)
        configs = {
            prefix + "/config/id": self._rid,
            prefix + "/config/mode": self._config["mode"],
            prefix + "/config/updates-only": self._config["updates-only"],
        }
        for s in self._config["subscriptions"]:
            sid = s["id"]
            sprefix = prefix + f"/subscriptions/subscription[id='{sid}']"
            configs[sprefix + "/config/id"] = sid
            configs[sprefix + "/config/path"] = s["path"]
            if self._config["mode"] == "STREAM":
                configs[sprefix + "/config/mode"] = s["mode"]
                if s["sample-interval"] > 0:
                    configs[sprefix + "/config/sample-interval"] = s["sample-interval"]
                configs[sprefix + "/config/suppress-redundant"] = s[
                    "suppress-redundant"
                ]
                if s["heartbeat-interval"] > 0:
                    configs[sprefix + "/config/heartbeat-interval"] = s[
                        "heartbeat-interval"
                    ]
        with self._repo() as repo:
            repo.start()
            for path, value in configs.items():
                try:
                    repo.set(path, value)
                except ValueError as e:
                    msg = f"failed to set {path} to the path {value}."
                    logger.error(msg)
                    raise InvalidArgumentError(msg) from e
            try:
                repo.apply()
            except ApplyFailedError as e:
                msg = f"failed to apply subscription config {self._config}. {e}."
                logger.error(msg)
                raise InvalidArgumentError(msg) from e

    def clear(self):
        with self._repo() as repo:
            repo.start()
            try:
                repo.delete(self.PATH_SR.format(self._rid))
                repo.apply()
            except NotFoundError:
                logger.info("subscription config %s to delete is not found.", self._rid)
                pass
            except ApplyFailedError as e:
                logger.error("failed to clear subscription config %s. %s", self._rid, e)
                repo.discard()

    def push_notif(self, notif):
        timestamp = time.time_ns()
        sr = None
        if notif["type"] == "SYNC_RESPONSE":
            sr = gnmi_pb2.SubscribeResponse(sync_response=True)
        elif notif["type"] == "UPDATE":
            sr = gnmi_pb2.SubscribeResponse(
                update=gnmi_pb2.Notification(
                    timestamp=timestamp,
                    update=[
                        gnmi_pb2.Update(
                            path=_build_gnmi_path(notif["path"]),
                            val=gnmi_pb2.TypedValue(
                                json_val=notif["json-data"].encode()
                            ),
                        ),
                    ],
                )
            )
        elif notif["type"] == "DELETE":
            sr = gnmi_pb2.SubscribeResponse(
                update=gnmi_pb2.Notification(
                    timestamp=timestamp,
                    delete=[
                        _build_gnmi_path(notif["path"]),
                    ],
                )
            )
        if sr is not None:
            self._notifs.insert(0, sr)

    def poll_notifs(self):
        with self._repo() as repo:
            repo.start()
            repo.exec_rpc(self.PATH_POLL, {"id": self._rid})

    def pull_notifs(self):
        while True:
            try:
                yield self._notifs.pop()
            except IndexError:
                break


class gNMIServicer(gnmi_pb2_grpc.gNMIServicer):
    """gNMIServicer provides an implementation of the methods of the gNMI service.

    Args:
        repo (Repository): Datastore instance where requested data are get, set or delete.
        supported_models (dict): List of yang models supported by the gNMI server.
    """

    SUPPORTED_ENCODINGS = [gnmi_pb2.Encoding.JSON]
    NOTIFICATION_PULL_INTERVAL = 0.01

    def __init__(self, repo, supported_models):
        super().__init__()
        self.repo = repo
        self.supported_models = supported_models
        self._subscribe_requests = {}
        self._subscribe_repo = self.repo()
        self._subscribe_repo.start()
        self._subscribe_repo.subscribe_notification(
            "/goldstone-telemetry:telemetry-notify-event", self._notification_cb
        )

    def Capabilities(self, request, context):
        return gnmi_pb2.CapabilityResponse(
            supported_models=[
                gnmi_pb2.ModelData(
                    name=m.get("name"),
                    organization=m.get("organization"),
                    version=m.get("version"),
                )
                for m in self.supported_models.get("supported_models")
            ],
            supported_encodings=self.SUPPORTED_ENCODINGS,
            gNMI_version="0.6.0",
        )

    def _get_status_code(self, code):
        for sc in grpc.StatusCode:
            if sc.value[0] == code:
                return sc
        return grpc.StatusCode.UNKNOWN

    def _verify_encoding(self, encoding):
        if encoding is not None and encoding not in self.SUPPORTED_ENCODINGS:
            msg = f"unsupported encoding type '{gnmi_pb2.Encoding.Name(encoding)}' is specified in Get."
            logger.error(msg)
            return gnmi_pb2.Error(
                code=GRPC_STATUS_CODE_UNIMPLEMENTED,
                message=msg,
            )

    def _collect_get_requests(self, request, repo):
        requests = []
        for path in request.path:
            gr = GetRequest(repo, request.prefix, path)
            requests.append(gr)
        return requests

    def _exec_get_requests(self, requests):
        for r in requests:
            r.exec()
            if r.status.code != GRPC_STATUS_CODE_OK:
                return r.status

    def Get(self, request, context):
        error = self._verify_encoding(request.encoding)
        if error is None:
            with self.repo() as repo:
                repo.start()
                requests = self._collect_get_requests(request, repo)
                error = self._exec_get_requests(requests)
        if error is not None:
            status_code = self._get_status_code(error.code)
            details = error.message
            context.set_code(status_code)
            context.set_details(details)
            logger.debug("gRPC StatusCode: %s, details: %s", status_code, details)
            return gnmi_pb2.GetResponse(error=error)
        notifications = []
        for r in requests:
            tv = gnmi_pb2.TypedValue()
            tv.json_val = r.json_result().encode()
            # tv.json_ietf_val = r.json_result().encode()
            u = gnmi_pb2.Update(
                path=r.gnmi_path,
                val=tv,
            )
            updates = [u]
            n = gnmi_pb2.Notification(
                timestamp=r.timestamp,
                prefix=request.prefix,
                update=updates,
            )
            notifications.append(n)
        return gnmi_pb2.GetResponse(notification=notifications)

    def _collect_set_requests(self, request, repo):
        prefix = request.prefix
        delete_requests = []
        replace_requests = []
        update_requests = []
        error_requests = []
        error = None
        for r in request.delete:
            dr = DeleteRequest(repo, prefix, r)
            delete_requests.append(dr)
        for r in request.replace:
            rr = ReplaceRequest(repo, prefix, r.path, r.val)
            replace_requests.append(rr)
        for r in request.update:
            ur = UpdateRequest(repo, prefix, r.path, r.val)
            update_requests.append(ur)
        requests = delete_requests + replace_requests + update_requests
        for r in requests:
            if r.status.code != GRPC_STATUS_CODE_OK:
                error_requests.append(r)
                if error is None:
                    error = gnmi_pb2.Error(
                        code=GRPC_STATUS_CODE_ABORTED,
                        message=r.status.message,
                    )
                else:
                    error.message = error.message + " " + r.status.message
        return requests, error_requests, error

    def _exec_set_requests(self, requests):
        error_requests = []
        error = None
        for r in requests:
            r.exec()
            if r.status.code != GRPC_STATUS_CODE_OK:
                error_requests.append(r)
                error = gnmi_pb2.Error(
                    code=GRPC_STATUS_CODE_ABORTED,
                    message=r.status.message,
                )
                break
        return error_requests, error

    def _set_status_code_aborted(self, requests, error_requests):
        for r in requests:
            if r in error_requests:
                continue
            r.status.code = GRPC_STATUS_CODE_ABORTED

    def _apply_set_requests(self, repo):
        try:
            repo.apply()
        except ApplyFailedError as e:
            # TODO: Update r.status to describe it was failed.
            #       But how to know which request(s) was failed?
            msg = f"failed to apply changes. {e}, {type(e)}"
            logger.error(msg)
            return gnmi_pb2.Error(
                code=GRPC_STATUS_CODE_ABORTED,
                message=msg,
            )

    def Set(self, request, context):
        with self.repo() as repo:
            repo.start()
            requests, error_requests, error = self._collect_set_requests(request, repo)
            if error is None:
                error_requests, error = self._exec_set_requests(requests)
            if error is None:
                error = self._apply_set_requests(repo)
            if error is not None:
                self._set_status_code_aborted(requests, error_requests)
                logger.error("Set() discards all changes.")
                repo.discard()
        timestamp = time.time_ns()
        results = []
        for r in requests:
            ur = gnmi_pb2.UpdateResult(
                timestamp=timestamp,
                path=r.gnmi_path,
                message=r.status,
                op=r.operation,
            )
            results.append(ur)
        if error is not None:
            status_code = self._get_status_code(error.code)
            details = error.message
            context.set_code(status_code)
            context.set_details(details)
            logger.debug("gRPC StatusCode: %s, details: %s", status_code, details)
            logger.debug(
                "SetRequest StatusCode: %s", self._get_status_code(error.code).name
            )
            for r in requests:
                logger.debug(
                    "%s, StatusCode: %s",
                    gnmi_pb2.UpdateResult.Operation.Name(r.operation),
                    self._get_status_code(r.status.code).name,
                )
        return gnmi_pb2.SetResponse(
            prefix=request.prefix,
            response=results,
            message=error,
            timestamp=timestamp,
        )

    def _notification_cb(self, xpath, notif_type, value, timestamp, priv):
        rid = value["request-id"]
        try:
            sr = self._subscribe_requests[rid]
        except KeyError:
            logger.error(
                "Subscribe request %s related to the notification is not found.", rid
            )
            return
        sr.push_notif(value)

    def _generate_subscribe_request_id(self):
        while True:
            rid = random.randint(0, 0xFFFFFFFF)
            if rid not in self._subscribe_requests.keys():
                return rid

    def _notify_current_states(self, sr):
        sync_response = False
        while True:
            for notification in sr.pull_notifs():
                yield notification
                if notification.sync_response:
                    sync_response = True
            if sync_response:
                break
            time.sleep(self.NOTIFICATION_PULL_INTERVAL)

    def _notify_updated_states(self, sr, context):
        while True:
            if not context.is_active():
                break
            for notification in sr.pull_notifs():
                yield notification
            time.sleep(self.NOTIFICATION_PULL_INTERVAL)

    def Subscribe(self, request_iterator, context):
        def set_error(code, msg):
            logger.error(msg)
            context.set_code(code)
            context.set_details(msg)
            return gnmi_pb2.Error(code=code, message=msg)

        # Create a subscription.
        req = next(request_iterator)
        mode = req.subscribe.mode
        rid = self._generate_subscribe_request_id()
        error = None
        try:
            sr = SubscribeRequest(self.repo, rid, req.subscribe)
            self._subscribe_requests[rid] = sr
            sr.exec()
        except InvalidArgumentError as e:
            error = set_error(
                GRPC_STATUS_CODE_INVALID_ARGUMENT,
                f"request has invalid argument(s). {e}",
            )
        except Exception as e:
            error = set_error(
                GRPC_STATUS_CODE_UNKNOWN, f"an unknown error has occurred. {e}"
            )
        if error is not None:
            try:
                self._subscribe_requests[rid].clear()
                del self._subscribe_requests[rid]
            except KeyError:
                pass
            return gnmi_pb2.SubscribeResponse(error=error)

        # Generate notifications.
        try:
            for notification in self._notify_current_states(sr):
                yield notification
            if mode == gnmi_pb2.SubscriptionList.Mode.POLL:
                for req in request_iterator:
                    if not req.HasField("poll"):
                        error = set_error(
                            GRPC_STATUS_CODE_INVALID_ARGUMENT,
                            "the request is not a 'poll' request.",
                        )
                        break
                    sr.poll_notifs()
                    for notification in self._notify_current_states(sr):
                        yield notification
            elif mode == gnmi_pb2.SubscriptionList.Mode.STREAM:
                for notification in self._notify_updated_states(sr, context):
                    yield notification
        except Exception as e:
            error = set_error(
                GRPC_STATUS_CODE_UNKNOWN, f"an unknown error has occurred. {e}"
            )
        finally:
            self._subscribe_requests[rid].clear()
            del self._subscribe_requests[rid]
        if error is None:
            return gnmi_pb2.SubscribeResponse()
        else:
            return gnmi_pb2.SubscribeResponse(error=error)


def serve(
    repo,
    max_workers=10,
    secure_port=51051,
    insecure_port=None,
    private_key_file=None,
    certificate_chain_file=None,
    supported_models_file=None,
):
    """Run a gNMI server.

    Args:
        repo (Repository): Datastore instance where requested data will be retrieved.
        max_workers (int): The number of threads to execute calls asynchronously.
        secure_port (int): gNMI server listens this port number for secure connections.
        insecure_port (int): gNMI server listens this port number for insecure connections.
            If it is None, the gNMI server does not accept insecure connection.
        private_key_file (str): Path to a PEM-encoded private key file.
        certificate_chain_file (str): Path to a PEM-encoded certificate chain file.
        supported_models_file (str): Path to a JSON file which is listed yang models supported by the gNMI server.
    """
    logger.info(
        "gNMI server serves as: max_workers=%d, secure_port=%d, insecure_port=%s,"
        " private_key_file=%s, certificate_chain_file=%s, supported_models_file=%s",
        max_workers,
        secure_port,
        insecure_port,
        private_key_file,
        certificate_chain_file,
        supported_models_file,
    )

    with open(supported_models_file, "r") as f:
        try:
            supported_models = json.loads(f.read())
        except json.JSONDecodeError as e:
            logger.error("%s is not JSON format.: %s", supported_models_file, e)
            exit()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    gnmi_pb2_grpc.add_gNMIServicer_to_server(
        gNMIServicer(repo, supported_models), server
    )
    port = None
    if private_key_file is not None and certificate_chain_file is not None:
        with open(private_key_file, "rb") as f:
            private_key = f.read()
        with open(certificate_chain_file, "rb") as f:
            certificate_chain = f.read()
        credentials = grpc.ssl_server_credentials(((private_key, certificate_chain),))
        port = server.add_secure_port(f"[::]:{secure_port}", credentials)
    if insecure_port is not None:
        port = server.add_insecure_port(f"[::]:{insecure_port}")
    if port is None:
        logger.error("No ports to listen.")
        exit()
    server.start()
    server.wait_for_termination()
