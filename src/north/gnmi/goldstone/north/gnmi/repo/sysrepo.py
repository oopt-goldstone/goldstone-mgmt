"""Repository inmplementation for the sysrepo datastore."""


import logging
import re
from goldstone.lib.connector.sysrepo import (
    Connector,
    NotFound as ConnectorNotFound,
    Error as ConnectorError,
)
from .repo import Repository, NotFoundError, ApplyFailedError


logger = logging.getLogger(__name__)


class Sysrepo(Repository):
    """Allows to access the sysrepo datastore.

    You can use `with` statement to close and release all resources automatically on exit.

        with Sysrepo() as repo:
            repo.start()
            # something to do
        # repo.stop() will be called automatically
    """

    FIND_KEYS_PATTERN = re.compile(r"\[(.*)\]")

    def __init__(self):
        self._connector = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def start(self):
        self._connector = Connector()

    def stop(self):
        self._connector.stop()

    def _find_node(self, path):
        return self._connector.find_node(path)

    def _next_node(self, node, target_name):
        for c in node.children():
            if c.name() == target_name:
                return c

    def _find_keys(self, target):
        statements = self.FIND_KEYS_PATTERN.findall(target)
        keys = set()
        for s in statements:
            key = s.split("=")[0].split(":")[-1]
            keys.add(key)
        return keys

    def _expect_single_result_when_path_includes_list_node(self, path):
        # If all keys defined by the data schema are specified in the provided path, return True.
        key_defined = False
        elements = path.split("/")[1:]
        node = None
        for i, elem in enumerate(elements):
            name = elem.split("[")[0]
            if node is None:
                # Find first node.
                node = self._find_node(f"/{name}")
            else:
                name = name.split(":")[-1]
                node = self._next_node(node, name)
            if node is None:
                msg = f"node '{elem}' not found."
                raise ValueError(msg)
            elem_keys = self._find_keys(elem)
            if len(elem_keys) > 0:
                key_defined = True
            node_keys = set()
            for key in node.keys():
                node_keys.add(key.name())
            if elem_keys != node_keys:
                if key_defined and i == len(elements) - 1 and len(elem_keys) == 0:
                    return True
                else:
                    return False
        return key_defined

    def get(self, xpath, strip=True):
        try:
            one = self._expect_single_result_when_path_includes_list_node(xpath)
            logger.debug("one: %s", one)
            # Goldstone xlate/south daemons enable the datastore layering.
            # When you get data from the operational datastore, you may get data from the running datastore too.
            # It means that you can get operational state and configuration state at same time.
            r = self._connector.get(xpath, strip=strip, one=one, ds="operational")
        except ConnectorNotFound as e:
            logger.error("%s not found. %s", xpath, e)
            raise NotFoundError(xpath) from e
        except ConnectorError as e:
            msg = f"failed to get. {xpath}: invalid xpath. {e}"
            logger.debug(msg)
            raise ValueError(msg) from e
        logger.debug("result: %s", r)
        if r is None:
            raise NotFoundError(xpath)
        return r

    def set(self, xpath, data):
        try:
            self._connector.set(xpath, data)
        except ConnectorError as e:
            msg = f"failed to set. xpath: {xpath}, value: {data}. {e}"
            logger.debug(msg)
            raise ValueError(msg) from e

    def delete(self, xpath):
        try:
            self._connector.delete(xpath)
        except ConnectorNotFound as e:
            logger.error("%s not found. %s", xpath, e)
            raise NotFoundError(xpath) from e
        except ConnectorError as e:
            msg = f"failed to delete. xpath: {xpath}. {e}"
            logger.debug(msg)
            raise ValueError(msg) from e

    def apply(self):
        try:
            self._connector.apply()
        except ConnectorError as e:
            # TODO: can split into detailed exceptions?
            logger.error("apply failed. %s", e)
            raise ApplyFailedError() from e

    def discard(self):
        self._connector.discard_changes()

    def get_list_keys(self, path):
        elements = path.split("/")[1:]
        node = None
        for elem in elements:
            name = elem.split("[")[0]
            if node is None:
                node = self._find_node(f"/{name}")
            else:
                name = name.split(":")[-1]
                node = self._next_node(node, name)
                if node is None:
                    msg = f"node '{elem}' not found."
                    raise ValueError(msg)
        keys = []
        for key in node.keys():
            keys.append(key.name())
        return keys
