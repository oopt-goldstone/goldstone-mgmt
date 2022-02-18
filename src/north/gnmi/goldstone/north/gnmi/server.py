"""gNMI server."""


import logging
from concurrent import futures
import json
import time
import grpc
from .proto import gnmi_pb2_grpc, gnmi_pb2
from .repo.repo import NotFoundError, ApplyFailedError


logger = logging.getLogger(__name__)


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
    """

    def __init__(self, repo, prefix, gnmi_path):
        self.repo = repo
        self.prefix = prefix
        self.gnmi_path = gnmi_path
        self.xpath = self._parse_xpath(prefix) + self._parse_xpath(gnmi_path)
        logger.debug("Requested xpath: %s", self.xpath)

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
        self.result = self.repo.get(self.xpath)
        self.timestamp = time.time_ns()

    def json_result(self):
        """Get retrieved data in JSON format.

        Returns:
            str: Retrieved data in JSON format.
        """
        return json.dumps(self.result)


class SetRequest(Request):
    """Base class for each SetRequest operation; DELETE, REPLACE and UPDATE.

    Attributes:
        status (gnmi_pb2.Error): Include status code and message as a result of the execution.
        val (any): Decoded value to set.
        leaves (dict): Dictionary which returns values to set with xpath of leaf.
    """

    def __init__(self, repo, prefix, gnmi_path):
        super().__init__(repo, prefix, gnmi_path)
        self.leaves = {}
        self.status = gnmi_pb2.Error(
            code=grpc.StatusCode.OK.value[0],
            message=None,
        )

    def _decode_val(self, val):
        if val.HasField("json_val"):
            return json.loads(val.json_val)
        else:
            t = val.WhichOneof("value")
            msg = f"encoding {t} is not supported."
            logger.error(msg)
            self.status.code = grpc.StatusCode.UNIMPLEMENTED.value[0]
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
        keys = self.repo.get_list_keys(path)
        for key in keys:
            val = container[key]
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
            logger.debug("xpath:%s, val:%s", path, val)
            self.leaves[path] = val

    def _parse_val_into_leaves(self, val):
        decoded_val = self._decode_val(val)
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
            logger.debug(
                "%s is not found. But the DeleteRequest() for the path is accepted.",
                self.xpath,
            )
        except Exception as e:
            logger.error("Failed to delete %s. %s", self.xpath, e)
            self.status.code = grpc.StatusCode.UNKNOWN.value[0]
            self.status.message = f"{self.xpath}, {e}"


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
                except Exception as e:
                    logger.error("Failed to update xpath: %s, value: %s. %s", k, v, e)
                    self.status.code = grpc.StatusCode.UNKNOWN.value[0]
                    self.status.message = f"{self.xpath}, {e}"
                    return


class gNMIServicer(gnmi_pb2_grpc.gNMIServicer):
    """gNMIServicer provides an implementation of the methods of the gNMI service.

    Args:
        repo (Repository): Datastore instance where requested data are get, set or delete.
        supported_models (dict): List of yang models supported by the gNMI server.
    """

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
            supported_encodings=[gnmi_pb2.Encoding.JSON],
            gNMI_version="0.6.0",
        )

    def _get_status_code(self, code):
        for sc in grpc.StatusCode:
            if sc.value[0] == code:
                return sc
        return grpc.StatusCode.UNKNOWN

    def _collect_get_requests(self, request, repo):
        requests = []
        for path in request.path:
            gr = GetRequest(repo, request.prefix, path)
            requests.append(gr)
        return requests

    def _exec_get_request(self, requests):
        for r in requests:
            try:
                r.exec()
            except NotFoundError as e:
                logger.error(
                    "Failed to retrieve data from datastore for Get(%s). %s",
                    r.xpath,
                    e,
                )
                return gnmi_pb2.GetResponse(
                    error=gnmi_pb2.Error(
                        code=grpc.StatusCode.NOT_FOUND.value[0],
                        message=f"XPath: {r.xpath}, {e}",
                    )
                )
            except Exception as e:
                logger.error(
                    "Failed to retrieve data from datastore for Get(%s). %s",
                    r.xpath,
                    e,
                )
                return gnmi_pb2.GetResponse(
                    error=gnmi_pb2.Error(
                        code=grpc.StatusCode.UNKNOWN.value[0],
                        message=f"XPath: {r.xpath}, {e}",
                    )
                )

    def Get(self, request, context):
        error_response = None
        requests = []
        with self.repo() as repo:
            repo.start()
            requests = self._collect_get_requests(request, repo)
            error_response = self._exec_get_request(requests)
        if error_response is not None:
            status_code = self._get_status_code(error_response.error.code)
            details = error_response.error.message
            context.set_code(status_code)
            context.set_details(details)
            logger.debug("gRPC StatusCode: %s, details: %s", status_code, details)
            return error_response
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
        for r in request.delete:
            dr = DeleteRequest(repo, prefix, r)
            delete_requests.append(dr)
        for r in request.replace:
            rr = ReplaceRequest(repo, prefix, r.path, r.val)
            replace_requests.append(rr)
        for r in request.update:
            ur = UpdateRequest(repo, prefix, r.path, r.val)
            update_requests.append(ur)
        return delete_requests, replace_requests, update_requests

    def _exec_set_requests(self, requests, status):
        for r in requests:
            r.exec()
            if (
                r.status.code is not grpc.StatusCode.OK.value[0]
                and status.code is grpc.StatusCode.OK.value[0]
            ):
                status.MergeFrom(r.status)

    def _apply_set_requests(self, repo, status):
        if status.code == grpc.StatusCode.OK.value[0]:
            try:
                repo.apply()
            except ApplyFailedError as e:
                logger.error("Failed to apply changes for Set(). %s", e)
                repo.discard()
                status.MergeFrom(
                    gnmi_pb2.Error(
                        code=grpc.StatusCode.INTERNAL.value[0],
                        message=f"{e}",
                    )
                )
                # TODO: Update r.status to describe it was failed.
                #       But how to know which request(s) was failed?
        else:
            logger.error("Set() discards all changes.")
            repo.discard()

    def Set(self, request, context):
        with self.repo() as repo:
            repo.start()
            deletes, replaces, updates = self._collect_set_requests(request, repo)
            status = gnmi_pb2.Error(
                code=grpc.StatusCode.OK.value[0],
                message=None,
            )
            self._exec_set_requests(deletes, status)
            self._exec_set_requests(replaces, status)
            self._exec_set_requests(updates, status)
            self._apply_set_requests(repo, status)

        timestamp = time.time_ns()
        requests = deletes + replaces + updates
        results = []
        for r in requests:
            ur = gnmi_pb2.UpdateResult(
                timestamp=timestamp,
                path=r.gnmi_path,
                message=r.status,
                op=r.operation,
            )
            results.append(ur)
        response = gnmi_pb2.SetResponse(
            prefix=request.prefix,
            response=results,
            message=status,
            timestamp=timestamp,
        )
        status_code = self._get_status_code(status.code)
        details = status.message
        context.set_code(status_code)
        context.set_details(details)
        logger.debug("gRPC StatusCode: %s, details: %s", status_code, details)
        return response

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
