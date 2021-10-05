import logging
import sysrepo
import libyang

logger = logging.getLogger(__name__)


class InterfaceServer(object):
    def __init__(self, conn):
        self.conn = conn
        self.sess = self.conn.start_session()

    def stop(self):
        self.sess.stop()

    def get_sr_data(self, xpath, datastore, default=None):
        self.sess.switch_datastore(datastore)
        try:
            v = self.sess.get_data(xpath)
        except sysrepo.errors.SysrepoNotFoundError:
            logger.debug(
                f"xpath: {xpath}, ds: {datastore}, not found. returning {default}"
            )
            return default
        v = libyang.xpath_get(v, xpath, default)
        logger.debug(f"xpath: {xpath}, ds: {datastore}, value: {v}")
        return v

    def get_running_data(self, xpath, default=None):
        return self.get_sr_data(xpath, "running", default)

    def get_operational_data(self, xpath, default=None):
        return self.get_sr_data(xpath, "operational", default)

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        xpath = "/goldstone-interfaces:interfaces/interface"
        data = self.get_operational_data(xpath, [])
        interfaces = []

        for i in data:
            intf = {
                "name": i["name"],
                "state": {
                    "name": i["name"],
                    "type": "iana-if-type:ethernetCsmacd",
                },
            }
            for v in ["mtu", "admin-status", "oper-status", "description", "counters"]:
                value = i["state"].get(v)
                if value:
                    intf["state"][v] = value

            interfaces.append(intf)

        return {"interfaces": {"interface": interfaces}}

    def change_cb(self, event, req_id, changes, priv):
        logger.debug(f"change_cb: event: {event}, changes: {changes}")

        if event not in ["change"]:
            logger.warn(f"unsupported event: {event}")
            return

        self.sess.switch_datastore("running")

        for change in changes:
            logger.debug(f"event: {event}, type: {type(change)}, change: {change}")
            xpath = list(libyang.xpath_split(change.xpath))
            logger.debug(xpath)

            if len(xpath) < 2:
                continue

            name = xpath[1][2][0]
            assert name[0] == "name"
            name = name[1]
            prefix = f"/goldstone-interfaces:interfaces/interface[name='{name}']"

            if isinstance(change, sysrepo.ChangeCreated):
                if len(xpath) == 3 and xpath[-1][1] == "config":
                    self.sess.set_item(f"{prefix}/config/name", name)
                    enabled = change.value.get("enabled", None)
                    if enabled != None:
                        self.sess.set_item(
                            f"{prefix}/config/admin-status", "UP" if enabled else "DOWN"
                        )
            elif isinstance(change, sysrepo.ChangeModified):
                if len(xpath) == 4 and xpath[-1][1] == "enabled":
                    self.sess.set_item(
                        f"{prefix}/config/admin-status",
                        "UP" if change.value else "DOWN",
                    )
            elif isinstance(change, sysrepo.ChangeDeleted):
                if len(xpath) == 2 and xpath[-1][1] == "interface":
                    self.sess.delete_item(prefix)
                elif len(xpath) == 4 and xpath[-1][1] == "enabled":
                    self.sess.delete_item(f"{prefix}/config/admin-status")

        self.sess.apply_changes()

    async def start(self):
        self.sess.switch_datastore("running")

        self.sess.subscribe_oper_data_request(
            "openconfig-interfaces",
            "/openconfig-interfaces:interfaces",
            self.oper_cb,
            oper_merge=True,
        )

        self.sess.subscribe_module_change(
            "openconfig-interfaces",
            None,
            self.change_cb,
        )

        return []
