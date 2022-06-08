"""Repository inmplementation for the sysrepo datastore."""


import logging
import libyang
from goldstone.lib.connector.sysrepo import (
    Connector,
    NotFoundError as ConnectorNotFound,
    Error as ConnectorError,
)
from .repo import Repository, NotFoundError, ApplyFailedError


logger = logging.getLogger(__name__)


def parse_xpath(xpath):
    """Parse xpath into a list of nodes.

    Args:
        xpath (str): Xpath to be parsed.

    Returns:
        (list of tupples): Parsed xpath as node tupples.
            node tupple: (prefix, name, list of keys)
                prefix: Namespace of the name. Typically it is a module name.
                name: Name of the node.
                list of key tupples: (key, value)
                    key: Name of the key node.
                    value: Value of the key.
    """
    return list(libyang.xpath_split(xpath))


class Sysrepo(Repository):
    """Allows to access the sysrepo datastore.

    You can use `with` statement to close and release all resources automatically on exit.

        with Sysrepo() as repo:
            repo.start()
            # something to do
        # repo.stop() will be called automatically
    """

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

    def _expect_single_result_when_path_includes_list_node(self, path):
        # If all keys defined by the data schema are specified in the provided path, return True.
        key_defined = False
        elements = parse_xpath(path)
        node = None
        for i, elem in enumerate(elements):
            prefix = elem[0]
            name = elem[1]
            if node is None:
                # Find first node.
                node = self._find_node(f"/{prefix}:{name}")
            else:
                node = self._next_node(node, name)
            if node is None:
                msg = f"node '{elem}' not found."
                raise ValueError(msg)
            elem_keys = set()
            for key in elem[2]:
                elem_keys.add(key[0])
            node_keys = set()
            for key in node.keys():
                node_keys.add(key.name())
            if len(elem_keys) > 0:
                key_defined = True
            if elem_keys != node_keys:
                return key_defined and i == len(elements) - 1 and len(elem_keys) == 0
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
            msg = f"apply failed. {e}"
            logger.error(msg)
            raise ApplyFailedError(msg) from e

    def discard(self):
        self._connector.discard_changes()

    def get_list_keys(self, path):
        elements = parse_xpath(path)
        node = None
        for elem in elements:
            prefix = elem[0]
            name = elem[1]
            if node is None:
                node = self._find_node(f"/{prefix}:{name}")
            else:
                node = self._next_node(node, name)
                if node is None:
                    msg = f"node '{elem}' not found."
                    raise ValueError(msg)
        keys = []
        for key in node.keys():
            keys.append(key.name())
        return keys

    def subscribe_notification(self, xpath, callback):
        self._connector.operational_session.subscribe_notification(xpath, callback)

    def exec_rpc(self, xpath, params):
        self._connector.operational_session.rpc(xpath, params)
