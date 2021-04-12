import logging

logger = logging.getLogger(__name__)


class InterfaceServer(object):
    def __init__(self, conn):
        self.conn = conn
        self.sess = self.conn.start_session()

    def stop(self):
        self.sess.stop()

    def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        self.sess.switch_datastore("operational")
        data = self.sess.get_data("/goldstone-interfaces:interfaces")
        interfaces = []

        for i in data.get("interfaces", {}).get("interface", []):
            intf = {
                "name": i["name"],
                "config": {
                    "name": i["name"],
                    "type": "iana-if-type:ethernetCsmacd",
                    "mtu": i["ipv4"]["mtu"],
                    "description": i["alias"],
                },
            }
            interfaces.append(intf)

        return {"interfaces": {"interface": interfaces}}

    async def start(self):

        with self.conn.start_session() as sess:
            sess.switch_datastore("running")

            self.sess.subscribe_oper_data_request(
                "openconfig-interfaces",
                "/openconfig-interfaces:interfaces",
                self.oper_cb,
                oper_merge=True,
            )

        return []
