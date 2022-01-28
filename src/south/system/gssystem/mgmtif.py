import pyroute2
import sysrepo
import logging
from pyroute2.netlink.rtnl import ndmsg
import os
import re

# This hardcoding has to be removed once ENV
# is added in system file for gssystem-south
MGMT_INTF_NAMES = os.getenv("GS_MGMT_INTFS", "eth0").split(",")
MAX_PREFIX_LENGTH = 32
DEFAULT_RT_TABLE = 254
RT_PROTO_STATIC_TYPE = 4

DHCP_LEASE_DIR = os.getenv("DHCP_LEASE_DIR", "/var/lib/dhcp")
DHCP_LEASE_RE = re.compile(r"lease {(?P<lease>.*?)\n}", re.DOTALL)

logger = logging.getLogger(__name__)


def parse_dhcp_leases(data):
    leases = []
    for match in re.finditer(DHCP_LEASE_RE, data):
        lease = match.group("lease")
        lines = lease.strip().split("\n")
        if not all(l.endswith(";") for l in lines):
            raise Exception(f"unknown format: {lease}")

        lines = [l[:-1].split() for l in lines]
        lease = {}
        for line in lines:
            key = line[0]
            value = " ".join(line[1:])
            if key in lease:
                v = lease[key]
                if type(v) == list:
                    lease[key].append(value)
                else:
                    lease[key] = [v, value]
            else:
                lease[key] = value
        leases.append(lease)
    return leases


def get_latest_dhcp_ip_addr(ifname):
    fname = f"{DHCP_LEASE_DIR}/dhclient.{ifname}.leases"
    if not os.path.exists(fname):
        return None

    with open(fname) as f:
        leases = parse_dhcp_leases(f.read())
        if not leases:
            return None
        return leases[-1]


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
            # FIXME support setting nexthop
            intf = ndb.interfaces[MGMT_INTF_NAMES[0]]
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
                        try:
                            ndb.routes.create(
                                dst=destination_prefix,
                                oif=intf["index"],
                            ).commit()
                        except KeyError as error:
                            raise sysrepo.SysrepoInvalArgError(
                                f"Object exists: {str(error)}"
                            )
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
                        dst, dst_len = destination_prefix.split("/")
                        ndb.routes[
                            {"oif": intf["index"], "dst": dst, "dst_len": dst_len}
                        ].remove().commit()
                    if xpath.startswith(
                        "/goldstone-routing:routing/static-routes/ipv4/"
                    ) and xpath.endswith("route"):
                        for route in ndb.routes.dump().filter(
                            oif=intf["index"],
                            proto=RT_PROTO_STATIC_TYPE,
                            table=DEFAULT_RT_TABLE,
                        ):
                            ndb.routes[
                                {
                                    "oif": intf["index"],
                                    "table": DEFAULT_RT_TABLE,
                                    "proto": RT_PROTO_STATIC_TYPE,
                                }
                            ].remove().commit()

    async def ip_change_cb(self, event, req_id, changes, priv):

        with pyroute2.NDB() as ndb:
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
                        if intf_name not in MGMT_INTF_NAMES:
                            raise sysrepo.SysrepoInvalArgError(
                                "interface name is not the management interface"
                            )

                        try:
                            v = ndb.interfaces[intf_name].add_ip(f"{ip}/{change.value}")
                            if event == "done":
                                v.commit()
                        except KeyError as error:
                            raise sysrepo.SysrepoInvalArgError(
                                f"Object exists: {str(error)}"
                            )

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
                        if intf_name not in MGMT_INTF_NAMES:
                            raise sysrepo.SysrepoInvalArgError(
                                "interface name is not the management interface"
                            )
                        prefix_length = (
                            ndb.interfaces[intf_name]
                            .ipaddr.summary()
                            .filter(address=ip)[0]["prefixlen"]
                        )

                        v = ndb.interfaces[intf_name].del_ip(
                            ip + "/" + str(prefix_length)
                        )
                        if event == "done":
                            v.commit()

    def get_neighbor(self, ifname):
        intf_index = self.pyroute.link_lookup(ifname=ifname)
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

    def get_routes(self, ifname):
        with pyroute2.NDB() as ndb:
            routes = []
            destination_prefix = "0.0.0.0/0"
            next_hop_address = ""
            for route in ndb.interfaces[ifname].routes.dump():
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
                        route_dic["metric"] = route["metrics"]
                    route_dic["flags"] = route["flags"]
                    routes.append(route_dic)
            return routes

    async def oper_cb(self, xpath, priv):
        logger.debug(f"xpath:{xpath}")

        if xpath.startswith("/goldstone-mgmt-interfaces"):
            interfaces = []
            for ifname in MGMT_INTF_NAMES:
                interface = {"name": ifname}
                neighbor = self.get_neighbor(ifname)
                interface["goldstone-ip:ipv4"] = {"neighbor": neighbor}
                interfaces.append(interface)

            logger.debug(f"interfaces: {interfaces}")
            return {"interfaces": {"interface": interfaces}}
        elif xpath.startswith("/goldstone-routing"):
            return {"routes": {"route": self.get_routes(MGMT_INTF_NAMES[0])}}

    def clear_arp(self, xpath, input_params, event, priv):
        logger.debug(
            f"clear_arp: xpath: {xpath}, input: {input}, event: {event}, priv: {priv}"
        )
        ifname = MGMT_INTF_NAMES[0]
        intf_index = self.pyroute.link_lookup(ifname=ifname).pop()
        for n in self.get_neighbor(ifname):
            dst = n["ip"]
            self.pyroute.neigh(
                "del",
                dst=dst,
                lladdr=n.get("link-layer-address", None),
                ifindex=intf_index,
            )

    def reconcile(self):
        self.sess.switch_datastore("running")

        mgmtif_data = self.sess.get_data("/goldstone-mgmt-interfaces:interfaces")
        if "interfaces" in mgmtif_data:
            mgmtif_list = list(mgmtif_data["interfaces"]["interface"])
            logger.debug(mgmtif_list)
            with pyroute2.NDB() as ndb:
                mgmtif = mgmtif_list.pop()
                if mgmtif["name"] not in MGMT_INTF_NAMES:
                    raise sysrepo.SysrepoInvalArgError(
                        f"{mgmtif['name']} not the supported management interface"
                    )
                for key in mgmtif:
                    if key == "ipv4":
                        for ip in mgmtif["ipv4"].get("address", []):
                            try:
                                ndb.interfaces[mgmtif["name"]].add_ip(
                                    ip["ip"] + "/" + str(ip["prefix-length"])
                                ).commit()
                            except KeyError as error:
                                logger.debug(f"{str(error)} : address already present")

        route_data = self.sess.get_data("/goldstone-routing:routing")
        if "routing" in route_data:
            route_list = route_data["routing"]["static-routes"]["ipv4"]["route"]
            logger.debug(route_list)
            with pyroute2.NDB() as ndb:
                intf = ndb.interfaces[MGMT_INTF_NAMES[0]]
                for route in route_list:
                    try:
                        ndb.routes.create(
                            dst=route["destination-prefix"],
                            oif=intf["index"],
                        ).commit()
                    except KeyError as error:
                        logger.debug(f"{str(error)} : route already present")

    async def start(self):
        self.reconcile()
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
            "/goldstone-routing:clear-arp",
            self.clear_arp,
        )

        return []
