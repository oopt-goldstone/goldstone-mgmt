import logging

logger = logging.getLogger(__name__)


class PlatformServer(object):
    def __init__(self, conn):
        self.conn = conn
        self.sess = self.conn.start_session()

    def stop(self):
        self.sess.stop()

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        self.sess.switch_datastore("operational")
        data = self.sess.get_data("/goldstone-interfaces:interfaces")
        components = []

        for i in data.get("interfaces", {}).get("interface", []):
            if "parent" in i:
                continue
            port = {
                "name": i["name"],
                "config": {
                    "name": i["name"],
                },
                "state": {
                    "name": i["name"],
                    "type": "openconfig-platform-types:PORT",
                },
            }
            components.append(port)

        return {"components": {"component": components}}

    async def start(self):

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")

            self.sess.subscribe_oper_data_request(
                "openconfig-platform",
                "/openconfig-platform:components",
                self.oper_cb,
                oper_merge=True,
            )

        return []
