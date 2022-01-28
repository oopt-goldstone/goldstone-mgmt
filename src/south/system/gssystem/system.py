import dbus
import logging
import json
import sysrepo
import os

VERSION_FILE = os.getenv(
    "GOLDSTONE_VERSION_FILE", "/etc/goldstone/loader/versions.json"
)

logger = logging.getLogger(__name__)


class SystemServer:
    def __init__(self, conn):
        self.sess = conn.start_session()

    def stop(self):
        self.sess.stop()

    async def oper_cb(self, xpath, priv):
        try:
            with open(VERSION_FILE, "r") as f:
                d = json.loads(f.read())
                return {
                    "goldstone-system:system": {
                        "state": {"software-version": d["PRODUCT_ID_VERSION"]}
                    }
                }
        except (FileNotFoundError, KeyError) as e:
            logger.error(f"failed to get version info: {e}")
            raise sysrepo.SysrepoInternalError("version details not found")

    def reboot(self, xpath, input_params, event, priv):
        logger.debug(
            f"reboot: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        bus = dbus.SystemBus()
        logind = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
        manager = dbus.Interface(logind, "org.freedesktop.login1.Manager")
        manager.Reboot(False)

    def shutdown(self, xpath, input_params, event, priv):
        logger.debug(
            f"shutdown: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        bus = dbus.SystemBus()
        logind = bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1")
        manager = dbus.Interface(logind, "org.freedesktop.login1.Manager")
        manager.PowerOff(False)

    async def change_cb(self, event, req_id, changes, priv):
        if event != "done":
            return
        for change in changes:
            logger.info(change, change.xpath)

    async def start(self):
        self.sess.switch_datastore("running")

        self.sess.subscribe_oper_data_request(
            "goldstone-system",
            "/goldstone-system:system",
            self.oper_cb,
            oper_merge=True,
            asyncio_register=True,
        )

        self.sess.subscribe_module_change(
            "goldstone-system",
            None,
            self.change_cb,
            asyncio_register=True,
        )

        self.sess.subscribe_rpc_call(
            "/goldstone-system:reboot",
            self.reboot,
        )

        self.sess.subscribe_rpc_call(
            "/goldstone-system:shutdown",
            self.shutdown,
        )

        return []
