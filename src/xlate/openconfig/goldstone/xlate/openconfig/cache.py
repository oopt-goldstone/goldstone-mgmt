"""Cache datastore for OpenConfig translators."""


from abc import abstractmethod
import logging


logger = logging.getLogger(__name__)


class CacheDataNotExistError(Exception):
    pass


class Cache:
    """Base for cache datastore.

    It is an abstract class. You should implement a subclass for each datastore type.
    """

    @abstractmethod
    def get(self, module):
        """Get operational state data of a module from the cache datastore.

        Args:
            module (str): Module name.

        Returns:
            dict: Operational state data of a module.

        Raises:
            CacheDataNotExistError: Data for the module does not exist in the cache datastore.
        """
        pass

    @abstractmethod
    def set(self, module, data):
        """Set operational state data of an OpenConfig model to the cache datastore.

        Args:
            module (str): Module name.
            data (dict): Operational state data of a model.
        """
        pass


class InMemoryCache(Cache):
    """In-memory cache datastore.

    Attribute:
        _data (dict): Operational state data for modules. A key is a module name.
    """

    def __init__(self):
        self._data = {}

    def get(self, module):
        try:
            return self._data[module]
        except KeyError as e:
            logger.error("%s is not cached.", module)
            raise CacheDataNotExistError(
                f"Cache data for {module} does not exist in the cache datastore"
            ) from e

    def set(self, module, data):
        self._data[module] = data
