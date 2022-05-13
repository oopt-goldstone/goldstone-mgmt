"""gNMI server."""


import logging
from concurrent import futures
import json
import time
import grpc
from .proto import gnmi_pb2_grpc, gnmi_pb2
from .repo.repo import NotFoundError, ApplyFailedError


logger = logging.getLogger(__name__)

GRPC_STATUS_CODE_OK = grpc.StatusCode.OK.value[0]
GRPC_STATUS_CODE_UNKNOWN = grpc.StatusCode.UNKNOWN.value[0]
GRPC_STATUS_CODE_INVALID_ARGUMENT = grpc.StatusCode.INVALID_ARGUMENT.value[0]
GRPC_STATUS_CODE_NOT_FOUND = grpc.StatusCode.NOT_FOUND.value[0]
GRPC_STATUS_CODE_ABORTED = grpc.StatusCode.ABORTED.value[0]
GRPC_STATUS_CODE_UNIMPLEMENTED = grpc.StatusCode.UNIMPLEMENTED.value[0]


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
        self.xpath = self._parse_xpath(prefix) + self._parse_xpath(gnmi_path)
        logger.debug("Requested xpath: %s", self.xpath)
        self.status = gnmi_pb2.Error(
            code=GRPC_STATUS_CODE_OK,
            message=None,
        )

    def _parse_xpath(self, path):
        xpath = ""
        for elem in path.elem:
            xpath += f"/{elem.name}"
            if elem.key:
                for key in sorted(elem.key):
                    value = elem.key.get(key)
                    xpath += f"[{key}='{value}']"
        return xpath

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


class gNMIServicer(gnmi_pb2_grpc.gNMIServicer):
    """gNMIServicer provides an implementation of the methods of the gNMI service.

    Args:
        repo (Repository): Datastore instance where requested data are get, set or delete.
        supported_models (dict): List of yang models supported by the gNMI server.
    """

    SUPPORTED_ENCODINGS = [gnmi_pb2.Encoding.JSON]

    def __init__(self, repo, supported_models):
        super().__init__()
        self.repo = repo
        self.supported_models = supported_models

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

    # TODO: Implement Subscribe().


def serve(
    repo,
    max_workers=10,
    secure_port=50051,
    insecure_port=None,
    supported_models_file=None,
):
    """Run a gNMI server.

    Args:
        repo (Repository): Datastore instance where requested data will be retrieved.
        max_workers (int): The number of threads to execute calls asynchronously.
        secure_port (int): gNMI server listens this port number for secure connections.
        insecure_port (int): gNMI server listens this port number for insecure connections.
            If it is None, the gNMI server does not accept insecure connection.
        supported_models_file (str): Path to JSON file which is listed yang models supported by the gNMI server.
    """
    logger.info(
        "gNMI server serves as: max_workers=%d, secure_port=%d, insecure_port=%d, supported_models_file=%s",
        max_workers,
        secure_port,
        insecure_port,
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
    # TODO: Add credentials and enable a secure connection.
    # server.add_secure_port("[::]:{}"".format(secure_port), credentials)
    if insecure_port is not None:
        server.add_insecure_port(f"[::]:{insecure_port}")
    server.start()
    server.wait_for_termination()
