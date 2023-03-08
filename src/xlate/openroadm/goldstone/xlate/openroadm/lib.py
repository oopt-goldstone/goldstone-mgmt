import logging
import asyncio
import libyang
from goldstone.lib.core import ServerBase
from goldstone.lib.errors import Error, CallbackFailedError


logger = logging.getLogger(__name__)


class OpenROADMServer(ServerBase):
    """Server base for OpenROADM translators.
    You can provide an OpenROADM service for "module" by implementing attributes "handlers" and "objects" as a
    subclass.
    If you want to provide user attributes to OpenROAMD's handlers, you should override pre() and set items to
    "user".
    Args:
        conn (Connector): Connection to the central datastore.
        module (str): YANG module name of the service. e.g. "org-openroadm-interfaces"
        reconciliation_interval (int): Interval seconds between executions of the reconcile task.
    Attributes:
        conn (Connector): Connection to the central datastore.
        reconciliation_interval (int): Interval seconds between executions of the reconcile task.
    """

    def __init__(self, conn, module, reconciliation_interval=10):
        super().__init__(conn, module)
        self.reconciliation_interval = reconciliation_interval
        self.reconcile_task = None
        self.handlers = {}
        self.objects = {}

    async def reconcile(self):
        """Reconcile between OpenROADM configuration state and Goldstone configuration state."""
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
        """Setup function before execution of handlers for OpenROADM
        Args:
            user (dict): Context attributes to provide to OpenROADM's handlers.
        """
        sess_running = self.conn.conn.new_session("running")
        sess_operational = self.conn.conn.new_session("operational")
        user["sess"] = {"running": sess_running, "operational": sess_operational}

    async def post(self, user):
        """Teardown function after execution of handlers for OpenROADM
        If a OpenROADM's handler failed, this will not be called.
        Args:
            user (dict): Context attributes to provide to OpenROADM's handlers.
        """
        try:
            user["sess"]["running"].apply()
            user["sess"]["running"].stop()
            user["sess"]["operational"].stop()
        except Error as e:
            # Just for logging.
            logger.error("Failed to apply changes. %s", e)
            raise e

    def _translate_circuit_pack_name(self, or_port_map, circuit_pack_name):
        """get goldstone piu name and hostif name according to pin-mode of interface.

        Args:
            or_port_map (dict): port mapping information for translating openroadm model
            circuit_pack_name (str): circuit-pack-name to be translated

        Returns:
            gs_piu, gs_port (tuple): goldstone's piu name and hostif name correspond to given circuit-pack-name.

        Examples:

            >>> self._translate_circuit_pack_name({'port3': {'PAM4': ('Interface1/1/3', 'piu1', '2'), 'NRZ': ('Interface1/1/3', 'piu1', '1')})
            ('piu1', '2')  // port3 corresponds to ('piu1', '2') when Interface1/1/3 is set to PAM4.

        """
        if_info = or_port_map.get(circuit_pack_name, None)
        if if_info == None:
            logger.warning(f"no port mapping info for circuit-pack {circuit_pack_name}")
            return None, None

        for k, v in if_info.items():
            try:
                [pin_mode] = self.get_operational_data(
                    f"/goldstone-interfaces:interfaces/interface[name='{v[0]}']/state/pin-mode"
                )
            except CallbackFailedError:  # when the interface (v[0]) does not exist
                continue
            if k == pin_mode:
                return v[1], v[2]
        return None, None
