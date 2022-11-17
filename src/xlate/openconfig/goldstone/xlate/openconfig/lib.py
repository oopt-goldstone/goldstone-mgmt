"""Framework library for OpenConfig translator servers.

OpenConfig servers should be implemented by inheriting this library classes. This is for:

- Using a common mechanism to eliminate implementation redundancy.
- Hiding accidental complexities to forcus the business logic (translation rules).

The framework provides a mechanism for:

- Creating OpenConfig objects from Goldstone data.
- Configuring a device with OpenConfig device models.

The classes this framework library provides are:

- OpenConfigServer: provides a service for an OpenConfig module. e.g. "openconfig-interfaces"
      It has "OpenConfigObjectTree"s and "OpenConfigChangeHandler"s.
- OpenConfigObjectTree: creates a data tree instance that includes operational states for an OpenConfig module.
      It has "OpenConfigObjectFactory"s.
- OpenConfigObjectFactory: creates OpenConfig objects by translating Goldstone operational state data.
- OpenConfigChangeHandler: configure a device with provided OpenConfig configuration state data.

See class docstrings for detailed usage.
"""


from abc import abstractmethod
import logging
import asyncio
import libyang
from goldstone.lib.core import ChangeHandler, ServerBase
from goldstone.lib.errors import Error, InvalArgError, NotFoundError
from .cache import CacheDataNotExistError


logger = logging.getLogger(__name__)


class OpenConfigChangeHandler(ChangeHandler):
    """ChangeHandler base for OpenConfig translators.

    It provides methods to configure a device.

    It has abstract methods that will be used by template methods "validate()", "apply()", and "revert()". You should
    implement them as a part of subclass. You should implement subclasses for each configurable OpenConfig path.

    Attributes:
        xpath (list): Target xpath parsed by libyang.
        value (any): Validated Goldstone configuration value.
        original_value (any): Original Goldstone configuration value. None means "not configured yet".
    """

    def __init__(self, server, change):
        super().__init__(server, change)
        self.xpath = list(libyang.xpath_split(change.xpath))
        self.value = None
        self.original_value = None

    def _get(self, user, xpath, datastore="running"):
        sess = user["sess"][datastore]
        value = sess.get(xpath)
        return value

    def _set(self, user, xpath, value):
        sess = user["sess"]["running"]
        sess.set(xpath, value)

    def _delete(self, user, xpath):
        sess = user["sess"]["running"]
        sess.delete(xpath)

    @abstractmethod
    def _setup(self, user):
        """Setup a context of the ChangeHandler.

        Args:
            user (dict): User data.
        """
        pass

    @abstractmethod
    def _get_item(self, user):
        """Get value(s) of the target Goldstone item.

        Args:
            user (dict): User data.

        Returns:
            any: Goldstone value(s).
        """
        pass

    @abstractmethod
    def _set_item(self, user, value):
        """Set value(s) of the target Goldstone item.

        Args:
            user (dict): User data.
            value (any): Goldstone value(s) to set.
        """
        pass

    @abstractmethod
    def _delete_item(self, user):
        """Delete value(s) of the target Goldstone item.

        Args:
            user (dict): User data.
        """
        pass

    @abstractmethod
    def _translate(self, user, value):
        """Translate OpenConfig value to Goldstone value(s).

        Args:
            value (any): OpenConfig value to translate.

        Returns:
            any: Goldstone value(s).
        """
        pass

    @abstractmethod
    def _validate_parent(self, user):
        """Validate parent items and save its information.

        Notes:
            - Save "parent Goldstone items will be created?" as instance attributes.
              e.g. create interfaces/interface[name='foo'] for
                          interfaces/interface[name='foo']/config/admin-status.
            - The information may be referenced by _delete() to delete all created items.

        Args:
            user (dict): User data.
        """
        pass

    def validate(self, user):
        self._setup(user)
        try:
            self.original_value = self._get_item(user)
        except NotFoundError:
            pass
        if self.type in ["created", "modified"]:
            logger.info("Given service value: %s", self.change.value)
            self.value = self._translate(user, self.change.value)
            if self.value is None:
                raise InvalArgError(f"unsupported service value {self.change.value}")
            logger.debug("Validated Goldstone value: %s", self.value)
            self._validate_parent(user)

    def apply(self, user):
        if self.type in ["created", "modified"]:
            self._set_item(user, self.value)
        elif self.type == "deleted":
            if self.original_value:
                self._delete_item(user)

    def revert(self, user):
        # NOTE: When the change has not been applied, revert() may raise InvalArgError. The central datastore does not
        #   allow manipulating a same node multiple times in a transaction (apply()).
        if self.original_value:
            self._set_item(user, self.original_value)
        else:
            # The Goldstone configuration state had no values when a ChangeHandler was triggered, even if the change
            # type is "modified" instead of "created". When reverting, a ChangeHandler should delete all items that
            # created by itself.
            if self.type in ["created", "modified"]:
                self._delete_item(user)


class OpenConfigObjectFactory:
    """Factory base for OpenConfig translators.

    It creates OpenConfig objects from Goldstone operational state data. The source Goldstone data are provided by its
    user. A created object may have references to another created object.

    It is an abstract class. You should implement a subclass for each OpenConfig object type. You should also implement
    a subclass for each device type (and/or a set of supported Goldstone native/primitive models). Because a subclass
    hides knowledge of object creation and association rules from its user. The knowledge includes what kind of
    Goldstone data are used and how to use them.
    """

    @abstractmethod
    def required_data(self):
        """Return a list of required data to create OpenConfig objects.

        Returns:
            list: List of required data dictionaries.
                Attributes in a dictionary.
                    "name": Name of the data.
                        It will be used as a key of the dictionary "gs" the argument of the create().
                    "xpath": Path to get the data.
                    "default": Default value if the data is not found.
        """
        pass

    @abstractmethod
    def create(self, gs):
        """Create OpenConfig objects from Goldstone data.

        Args:
            gs (dict): Data from Goldstone native/primitive models.

        Returns:
            list: List of dictionalies. Each dictionaly represents an OpenConfig object.
        """
        pass


class OpenConfigObjectTree:
    """Data tree factory base for OpenConfig modules.

    It creates an operational state data tree of an OpenConfig module. It has "OpenConfigObjectFactory"s related to the
    module. You should implement the "self.objects" attribute in your subclass.

    Attributes:
        objects (dict): OpenConfigObjectFactory instances for an OpenConfig module.
            A dictionary key represents a data node.
    """

    def __init__(self):
        self.objects = {}

    def _create_tree(self, gs, subtree):
        result = {}
        for k, v in subtree.items():
            if isinstance(v, dict):
                result[k] = self._create_tree(gs, v)
            elif isinstance(v, OpenConfigObjectFactory):
                result[k] = v.create(gs)
        return result

    def _get_factories(self, subtree):
        result = []
        for _, v in subtree.items():
            if isinstance(v, dict):
                result += self._get_factories(v)
            elif isinstance(v, OpenConfigObjectFactory):
                result.append(v)
        return result

    def required_data(self):
        """Return a list of required data to create OpenConfig objects.

        Returns:
            list: List of required data dictionaries. See OpenConfigObjectFactory.required_data().
        """
        required_data = []
        factories = self._get_factories(self.objects)
        for factory in factories:
            for data in factory.required_data():
                if not data in required_data:
                    required_data.append(data)
        return required_data

    def create(self, gs):
        """Create an operational state data tree of an OpenConfig module.

        Args:
            gs (dict): Data from Goldstone native/primitive models.

        Returns:
            dict: Operational state data tree of an Openconfig module.
        """
        return self._create_tree(gs, self.objects)


class OpenConfigServer(ServerBase):
    """Server base for OpenConfig translators.

    You can provide an OpenConfig service for "module" by implementing attributes "handlers" and "objects" as a
    subclass.

    A subclass should not aware that which Goldstone data are required and how to use them. The knowledge should be a
    part of "OpenConfigObjectFactory"s and "OpenConfigChangeHandler"s. A subclass has one or multiple
    "OpenConfigObjectFactory"s to create operational state for the service. A subclass has one or multiple
    "OpenConfigChangeHandler"s to apply configuration state change to device's actual configuration.

    If you want to provide user attributes to "OpenConfigChangeHandler"s, you should override pre() and set items to
    "user".

    Args:
        conn (Connector): Connection to the central datastore.
        module (str): YANG module name of the service. e.g. "openconfig-interfaces"
        cache (Cache): Cache datastore instance to store operational state data of OpenConfig modules.
            If it is None, OpenConfigServer does not use cached data.
        reconciliation_interval (int): Interval seconds between executions of the reconcile task.

    Attributes:
        conn (Connector): Connection to the central datastore.
        reconciliation_interval (int): Interval seconds between executions of the reconcile task.
        reconcile_task (Task): Reconcile task instance.
        handlers (dict): "OpenConfigChangeHandler"s for each configurable OpenConfig path.
            e.g.
            {
                "interfaces": {
                    "interface": {
                        "config": {
                            "enabled": EnabledHandler # => EnableHandler for /interfaces/interface/config/enabled
                        }
                    }
                }
            }
    """

    def __init__(self, conn, module, cache, reconciliation_interval=10):
        super().__init__(conn, module)
        self.module = module
        self.reconciliation_interval = reconciliation_interval
        self.reconcile_task = None
        self.handlers = {}
        self._cache = cache
        self._object_tree = None

    async def reconcile(self):
        """Reconcile between OpenConfig configuration state and Goldstone configuration state."""
        pass

    async def reconcile_loop(self):
        """Reconcile task coroutine."""
        while True:
            await asyncio.sleep(self.reconciliation_interval)
            await self.reconcile()

    async def start(self):
        """Start a service."""
        tasks = await super().start()
        if self.reconciliation_interval > 0:
            self.reconcile_task = self.reconcile_loop()
            tasks.append(self.reconcile_task)
        return tasks

    async def stop(self):
        """Stop a service."""
        super().stop()

    def pre(self, user):
        """Setup function before execution of "OpenConfigChangeHandler"s.

        Args:
            user (dict): Context attributes to provide to "OpenConfigChangeHandler"s.
        """
        sess_running = self.conn.conn.new_session("running")
        sess_operational = self.conn.conn.new_session("operational")
        user["sess"] = {
            "running": sess_running,
            "operational": sess_operational,
        }

    async def post(self, user):
        """Teardown function after execution of "OpenConfigChangeHandler"s.

        If a OpenConfigChangeHandler failed, this will not be called.

        Args:
            user (dict): Context attributes to provide to OpenConfigChangeHandlers.
        """
        try:
            user["sess"]["running"].apply()
            user["sess"]["running"].stop()
            user["sess"]["operational"].stop()
        except Error as e:
            # Just for logging.
            logger.error("Failed to apply changes. %s", e)
            raise e

    def _get_gs(self, required_data):
        gs = {}
        for d in required_data:
            data = self.get_operational_data(d["xpath"], d["default"])
            gs[d["name"]] = data
        return gs

    async def oper_cb(self, xpath, priv):
        """Callback function to get operational state of the service.

        Returns:
            dict: Operational states in a tree form.
                e.g.
                {"interfaces": {"interface": [
                    {"name": "Ethernet1/0/1", "state": {"oper-status": "UP"}},
                    {"name": "Ethernet1/0/2", "state": {"oper-status": "DOWN"}},
                ]}}
        """
        if self._cache is None:
            try:
                required_data = self._object_tree.required_data()
                gs = self._get_gs(required_data)
                result = self._object_tree.create(gs)
            except Exception as e:
                logger.error(
                    "Failed to create operational state data for %s by an error: %s",
                    self.module,
                    e,
                )
                raise e
        else:
            try:
                result = self._cache.get(self.module)
            except CacheDataNotExistError as e:
                logger.error(
                    "The operational state data for %s was not cached in the cache datastore. %s",
                    self.module,
                    e,
                )
                raise e
            except Exception as e:
                logger.error(
                    "Failed to get operational state data for %s from the cache datastore by an error: %s",
                    self.module,
                    e,
                )
                raise e
        return result
