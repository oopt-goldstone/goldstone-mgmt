import pyroute2
import sysrepo
import logging
from pyroute2.netlink.rtnl import ndmsg

# This hardcoding has to be removed once ENV
# is added in system file for gssystem-south
MGMT_INTF_NAME = "eth0"
MAX_PREFIX_LENGTH = 32
DEFAULT_RT_TABLE = 254

logger = logging.getLogger(__name__)


class ManagementInterfaceServer:
    def __init__(self, conn):
        self.pyroute = pyroute2.IPRoute()
        self.sess = conn.start_session()

    def stop(self):
        self.sess.stop()

    async def routing_change_cb(self, event, req_id, changes, priv):
        if event != "change":
            return
        with pyroute2.NDB() as ndb:
            intf = ndb.interfaces[MGMT_INTF_NAME]
            for change in changes:
                logger.debug(f"routing change_cb:{change}")
                xpath = change.xpath
                if isinstance(change, sysrepo.ChangeCreated):
                    logger.debug("Change created")
                    if xpath.startswith(
                        "/goldstone-routing:routing/static-routes/ipv4/route[destination-prefix='"
                    ) and xpath.endswith("']"):
                        value = change.value
                        destination_prefix = value["destination-prefix"]
                        ndb.routes.create(
                            dst=destination_prefix,
                            oif=intf["index"],
                        ).commit()
                if isinstance(change, sysrepo.ChangeModified):
                    raise sysrepo.SysrepoUnsupportedError(
                        "Modification is not supported"
                    )
                if isinstance(change, sysrepo.ChangeDeleted):
                    logger.debug("Change deleted")
                    if xpath.startswith(
                        "/goldstone-routing:routing/static-routes/ipv4/route[destination-prefix='"
                    ) and xpath.endswith("']"):
                        destination_prefix = xpath.split("'")[1]
                        logger.debug(destination_prefix)
                        ndb.routes[
                            {"oif": intf["index"], "dst": destination_prefix}
                        ].remove().commit()

    async def ip_change_cb(self, event, req_id, changes, priv):
        if event != "change":
            return
        with pyroute2.NDB() as ndb:
            intf = ndb.interfaces[MGMT_INTF_NAME]
            for change in changes:
                logger.debug(f"change_cb:{change}")
                xpath = change.xpath
                if isinstance(change, sysrepo.ChangeCreated):
                    logger.debug("Change created")
                    if xpath.endswith("prefix-length"):
                        intf_name = ""
                        ip = ""
                        for node in xpath.split("/"):
                            if node.startswith("interface[name='"):
                                intf_name = node.replace("interface[name='", "")
                                intf_name = intf_name.replace("']", "")
                            elif node.startswith("address[ip='"):
                                ip = node.replace("address[ip='", "")
                                ip = ip.replace("']", "")
                        logger.debug(intf_name)
                        logger.debug(ip)
                        if intf_name != MGMT_INTF_NAME:
                            raise sysrepo.SysrepoInvalArgError(
                                "interface name is not the management interface"
                            )
                        ndb.interfaces[intf_name].add_ip(
                            ip + "/" + str(change.value)
                        ).commit()
                if isinstance(change, sysrepo.ChangeModified):
                    raise sysrepo.SysrepoUnsupportedError(
                        "Modification is not supported"
                    )
                if isinstance(change, sysrepo.ChangeDeleted):
                    logger.debug("Change delete")
                    if xpath.endswith("prefix-length"):
                        intf_name = ""
                        ip = ""
                        for node in xpath.split("/"):
                            if node.startswith("interface[name='"):
                                intf_name = node.replace("interface[name='", "")
                                intf_name = intf_name.replace("']", "")
                            elif node.startswith("address[ip='"):
                                ip = node.replace("address[ip='", "")
                                ip = ip.replace("']", "")
                        logger.debug(intf_name)
                        logger.debug(ip)
                        if intf_name != MGMT_INTF_NAME:
                            raise sysrepo.SysrepoInvalArgError(
                                "interface name is not the management interface"
                            )
                        prefix_length = (
                            ndb.interfaces[intf_name]
                            .ipaddr.summary()
                            .filter(address=ip)[0]["prefixlen"]
                        )

                        ndb.interfaces[intf_name].del_ip(
                            ip + "/" + str(prefix_length)
                        ).commit()

    def get_neighbor(self):
        intf_index = self.pyroute.link_lookup(ifname=MGMT_INTF_NAME)
        tuple_of_neighbours = self.pyroute.get_neighbours(ifindex=intf_index.pop())
        neighbour_list = []

        for neighbour in tuple_of_neighbours:
            neigh_dict = {}
            for attr in neighbour["attrs"]:
                if attr[0] == "NDA_DST":
                    neigh_dict["ip"] = attr[1]
                if attr[0] == "NDA_LLADDR":
                    neigh_dict["link-layer-address"] = attr[1]
            neighbour_list.append(neigh_dict)

        return neighbour_list

    def get_routes(self):
        with pyroute2.NDB() as ndb:
            routes = []
            destination_prefix = "0.0.0.0/0"
            next_hop_address = ""
            for route in ndb.interfaces[MGMT_INTF_NAME].routes.dump():
                if ":" not in route["dst"] and route["table"] == DEFAULT_RT_TABLE:
                    route_dic = {}
                    route_dic["next-hop"] = {}
                    if route["dst"] != "":
                        route_dic["destination-prefix"] = (
                            route["dst"] + "/" + str(route["dst_len"])
                        )
                    else:
                        route_dic["destination-prefix"] = destination_prefix
                    if route["gateway"] != None and type(route["gateway"]) != type([]):
                        route_dic["next-hop"]["outgoing-interface"] = route["gateway"]
                    if route["metrics"] != None:
                        route_dic["metric"] = soute["metrics"]
                    route_dic["flags"] = route["flags"]
                    routes.append(route_dic)
            return routes

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath:{xpath}, req_xpath:{req_xpath}")

        if req_xpath.startswith("/goldstone-mgmt-interfaces:interfaces"):
            self.sess.switch_datastore("operational")

            neighbor = self.get_neighbor()
            ifdata = self.sess.get_data(req_xpath, no_subs=True)
            if ifdata == {}:
                return ifdata

            for intf in ifdata["interfaces"]["interface"]:
                intf["goldstone-ip:ipv4"] = {"neighbor": neighbor}

            logger.debug("************DATA to be returned in oper_cb()*************")
            logger.debug(ifdata)

            return ifdata
        if req_xpath.startswith("/goldstone-routing:routes"):
            route_data = {"routes": {}}
            route_data["routes"]["route"] = self.get_routes()
            return route_data

    def clear_arp(self, xpath, input_params, event, priv):
        logger.debug(
            f"clear_arp: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        intf_index = self.pyroute.link_lookup(ifname=MGMT_INTF_NAME).pop()
        for n in self.get_neighbor():
            dst = n["ip"]
            lladdr = n["link-layer-address"]
            self.pyroute.neigh(
                "del",
                dst=dst,
                lladdr=lladdr,
                ifindex=intf_index,
            )

    def update_oper_db(self):
        logger.debug("*********inside update oper db***************")
        self.sess.switch_datastore("operational")
        xpath = (
            f"/goldstone-mgmt-interfaces:interfaces/interface[name='{MGMT_INTF_NAME}']"
        )

        with pyroute2.NDB() as ndb:
            i = ndb.interfaces[MGMT_INTF_NAME]

            for ipaddr in ndb.interfaces[MGMT_INTF_NAME].ipaddr.summary():
                ip = ipaddr["address"]
                if ":" in ip:
                    continue
                mask = ipaddr["prefixlen"]
                self.sess.set_item(
                    f"{xpath}/goldstone-ip:ipv4/address[ip='{ip}']/prefix-length",
                    mask,
                )

            self.sess.set_item(f"{xpath}/admin-status", i["state"])
            self.sess.set_item(f"{xpath}/mtu", i["mtu"])

            logger.debug("********** update oper for routing **************")

            xpath = "/goldstone-routing:routing/static-routes/ipv4/route"
            for route in ndb.interfaces[MGMT_INTF_NAME].routes.summary():
                destination_prefix = ""
                if (
                    ":" not in route["dst"]
                    and route["dst_len"] != 0
                    and route["table"] == DEFAULT_RT_TABLE
                ):
                    destination_prefix = route["dst"] + "/" + str(route["dst_len"])
                    if destination_prefix != "":
                        self.sess.set_item(
                            f"{xpath}[destination-prefix='{destination_prefix}']/destination-prefix",
                            destination_prefix,
                        )

            logger.debug("********** update oper for routing done **********")

        self.sess.apply_changes()
        logger.debug("********* update oper db done***************")

    async def start(self):
        self.update_oper_db()
        self.sess.switch_datastore("running")
        self.sess.subscribe_oper_data_request(
            "goldstone-mgmt-interfaces",
            "/goldstone-mgmt-interfaces:interfaces",
            self.oper_cb,
            oper_merge=True,
            asyncio_register=True,
        )
        self.sess.subscribe_oper_data_request(
            "goldstone-routing",
            "/goldstone-routing:routes",
            self.oper_cb,
            oper_merge=True,
            asyncio_register=True,
        )
        self.sess.subscribe_module_change(
            "goldstone-mgmt-interfaces",
            None,
            self.ip_change_cb,
            asyncio_register=True,
        )
        self.sess.subscribe_module_change(
            "goldstone-routing", None, self.routing_change_cb, asyncio_register=True
        )
        self.sess.subscribe_rpc_call(
            "/goldstone-routing:clear_arp",
            self.clear_arp,
        )

        return []
