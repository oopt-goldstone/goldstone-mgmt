"""Cache data updater for OpenConfig translators."""

import asyncio
import logging
from .interfaces import InterfacesObjectTree
from .platform import PlatformObjectTree
from .terminal_device import TerminalDeviceObjectTree
from goldstone.lib.errors import Error as ConnectorError
from goldstone.lib.connector.sysrepo import Connector


logger = logging.getLogger(__name__)


DEFAULT_UPDATE_INTERVAL = 5


class CacheUpdater:
    """Cache data updater for OpenConfig translators.

    Args:
        cache (Cache): Cache datastore instance to use.
        operational_modes (dict): Supported operational-modes.
        update_interval (int): Interval seconds between executions of the update task.
    """

    def __init__(
        self, cache, operational_modes, update_interval=DEFAULT_UPDATE_INTERVAL
    ):
        self._cache = cache
        self._operational_modes = operational_modes
        self._update_interval = update_interval
        self._connector = Connector()
        self._required_data = []
        self._object_trees = {
            "openconfig-interfaces": InterfacesObjectTree(),
            "openconfig-platform": PlatformObjectTree(self._operational_modes),
            "openconfig-terminal-device": TerminalDeviceObjectTree(
                self._operational_modes
            ),
        }
        for _, object_tree in self._object_trees.items():
            for data in object_tree.required_data():
                if not data in self._required_data:
                    self._required_data.append(data)

    def _get_gs(self):
        """Get operational state data of Goldstone primitive models from the central datastore.

        Returns:
            dict: Operational state data of Goldstone primitive models.
        """
        gs = {}
        for d in self._required_data:
            try:
                gs[d["name"]] = self._connector.get_operational(
                    d["xpath"], d["default"]
                )
            except ConnectorError as e:
                logger.error("Failed to get source data from %s. %s", d["name"], e)
        return gs

    async def _update(self):
        """Update cache datastore."""
        gs = self._get_gs()
        for module, object_tree in self._object_trees.items():
            try:
                self._cache.set(module, object_tree.create(gs))
            except Exception as e:
                logger.error("Failed to update cache data for %s. %s", module, e)

    async def _update_loop(self):
        """Update task coroutine."""
        while True:
            await asyncio.sleep(self._update_interval)
            await self._update()

    async def start(self):
        """Start a service.

        Returns:
            list: List of coroutine objects.
        """
        return [self._update_loop()]

    async def stop(self):
        """Stop a service."""
        pass
