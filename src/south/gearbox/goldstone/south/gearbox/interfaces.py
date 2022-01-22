from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
import libyang
import taish
import asyncio
import sysrepo
import logging
import json
import base64
import struct

logger = logging.getLogger(__name__)


class IfChangeHandler(ChangeHandler):
    async def _init(self, user):
        xpath = self.change.xpath

        xpath = list(libyang.xpath_split(xpath))
        assert xpath[0][0] == "goldstone-interfaces"
        assert xpath[0][1] == "interfaces"
        assert xpath[1][1] == "interface"
        assert xpath[1][2][0][0] == "name"
        self.xpath = xpath
        ifname = xpath[1][2][0][1]

        self.obj = await self.server.ifname2taiobj(ifname)
        if self.obj == None:
            raise sysrepo.SysrepoInvalArgError("Invalid Interface name")

        self.ifname = ifname
        self.tai_attr_name = None

    async def validate(self, user):
        if not self.tai_attr_name:
            return

        if type(self.tai_attr_name) != list:
            self.tai_attr_name = [self.tai_attr_name]

        self.value = []

        for name in self.tai_attr_name:
            try:
                cap = await self.obj.get_attribute_capability(name)
            except taish.TAIException as e:
                raise sysrepo.SysrepoInvalArgError(e.msg)

            logger.info(f"cap: {cap}")

            if self.type == "deleted":
                leaf = self.xpath[-1][1]
                d = self.server.get_default(leaf)
                if d:
                    self.value.append(self.to_tai_value(d, name))
                elif cap.default_value == "":  # and is_deleted
                    raise sysrepo.SysrepoInvalArgError(
                        f"no default value. cannot remove the configuration"
                    )
                else:
                    self.value.append(cap.default_value)
            else:
                v = self.to_tai_value(self.change.value, name)
                if cap.min != "" and float(cap.min) > float(v):
                    raise sysrepo.SysrepoInvalArgError(
                        f"minimum {k} value is {cap.min}. given {v}"
                    )

                if cap.max != "" and float(cap.max) < float(v):
                    raise sysrepo.SysrepoInvalArgError(
                        f"maximum {k} value is {cap.max}. given {v}"
                    )

                valids = cap.supportedvalues
                if len(valids) > 0 and v not in valids:
                    raise sysrepo.SysrepoInvalArgError(
                        f"supported values are {valids}. given {v}"
                    )

                self.value.append(v)

    async def apply(self, user):
        if not self.tai_attr_name:
            return
        self.original_value = await self.obj.get_multiple(self.tai_attr_name)
        logger.debug(
            f"applying: {self.tai_attr_name} {self.original_value} => {self.value}"
        )
        await self.obj.set_multiple(list(zip(self.tai_attr_name, self.value)))

    async def revert(self, user):
        if not self.tai_attr_name:
            return
        logger.warning(
            f"reverting: {self.tai_attr_name} {self.value} => {self.original_value}"
        )
        await self.obj.set_multiple(list(zip(self.tai_attr_name, self.original_value)))


class AdminStatusHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "tx-dis"

    def to_tai_value(self, v, attr_name):
        return "false" if v == "UP" else "true"


class FECHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "fec-type"

    def to_tai_value(self, v, attr_name):
        return v.lower()


class MTUHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = ["mtu", "mru"]

    def to_tai_value(self, v, attr_name):
        return v


class InterfaceTypeHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = ["provision-mode", "signal-rate"]

    def to_tai_value(self, v, attr_name):
        if attr_name == "provision-mode":
            if v == "IF_ETHERNET":
                return "normal"
            elif v == "IF_OTN":
                return "serdes-only"
        elif attr_name == "signal-rate":
            if v == "IF_ETHERNET":
                return "100-gbe"
            elif v == "IF_OTN":
                return "otu4"


class MFITypeHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "otn-mfi-type"

    def to_tai_value(self, v, attr_name):
        return v.lower()


class MACSECStaticKeyHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "macsec-static-key"

    def to_tai_value(self, v, attr_name):
        v = struct.unpack("IIII", base64.b64decode(v))
        return ",".join((str(i) for i in v))


class AutoNegoHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "auto-negotiation"

    def to_tai_value(self, v, attr_name):
        return "true" if v else "false"


def pcs_status2oper_status(pcs):
    status = "DOWN"
    if (
        "ready" in pcs
        and ("rx-remote-fault" not in pcs)
        and ("rx-local-fault" not in pcs)
    ):
        status = "UP"
    return status


def parse_counters(attrs):
    counters = {}
    mac_rx = [int(v) for v in attrs[0].split(",")]
    mac_tx = [int(v) for v in attrs[1].split(",")]
    phy_rx = [int(v) for v in attrs[2].split(",")]

    counters["in-octets"] = mac_rx[0]
    counters["in-unicast-pkts"] = mac_rx[14]
    counters["in-broadcast-pkts"] = mac_rx[12]
    counters["in-multicast-pkts"] = mac_rx[13]
    # counters["in-discards"]
    counters["in-errors"] = mac_rx[4]

    counters["out-octets"] = mac_tx[0]
    counters["out-unicast-pkts"] = mac_rx[5]
    counters["out-broadcast-pkts"] = mac_rx[7]
    counters["out-multicast-pkts"] = mac_rx[6]
    # counters["out-discards"]
    counters["out-errors"] = mac_rx[4]

    return counters


def parse_macsec_counters(attrs):
    counters = {
        "ingress": {"sa": {}, "secy": {}, "channel": {}},
        "egress": {"sa": {}, "secy": {}, "channel": {}},
    }
    ingress_sa = [int(v) for v in attrs[0].split(",")]
    counters["ingress"]["sa"]["packets-unchecked"] = ingress_sa[0]
    counters["ingress"]["sa"]["packets-delayed"] = ingress_sa[1]
    counters["ingress"]["sa"]["packets-late"] = ingress_sa[2]
    counters["ingress"]["sa"]["packets-ok"] = ingress_sa[3]
    counters["ingress"]["sa"]["packets-invalid"] = ingress_sa[4]
    counters["ingress"]["sa"]["packets-not-valid"] = ingress_sa[5]
    counters["ingress"]["sa"]["packets-not-using-sa"] = ingress_sa[6]
    counters["ingress"]["sa"]["packets-unused-sa"] = ingress_sa[7]
    counters["ingress"]["sa"]["octets-decrypted"] = ingress_sa[8]
    counters["ingress"]["sa"]["octets-validated"] = ingress_sa[9]

    egress_sa = [int(v) for v in attrs[1].split(",")]
    counters["egress"]["sa"]["packets-entrypted-protected"] = egress_sa[0]
    counters["egress"]["sa"]["packets-too-long"] = egress_sa[1]
    counters["egress"]["sa"]["packets-sa-not-in-use"] = egress_sa[2]
    counters["egress"]["sa"]["octets-encrypted-protected"] = egress_sa[3]

    ingress_secy = [int(v) for v in attrs[2].split(",")]
    counters["ingress"]["secy"]["unicast-packets-uncontrolled"] = ingress_secy[0]
    counters["ingress"]["secy"]["multicast-packets-uncontrolled"] = ingress_secy[1]
    counters["ingress"]["secy"]["broadcast-packets-uncontrolled"] = ingress_secy[2]
    counters["ingress"]["secy"]["rx-drop-packets-uncontrolled"] = ingress_secy[3]
    counters["ingress"]["secy"]["rx-error-packets-uncontrolled"] = ingress_secy[4]
    counters["ingress"]["secy"]["unicast-packets-controlled"] = ingress_secy[5]
    counters["ingress"]["secy"]["multicast-packets-controlled"] = ingress_secy[6]
    counters["ingress"]["secy"]["broadcast-packets-controlled"] = ingress_secy[7]
    counters["ingress"]["secy"]["rx-drop-packets-controlled"] = ingress_secy[8]
    counters["ingress"]["secy"]["rx-error-packets-controlled"] = ingress_secy[9]
    counters["ingress"]["secy"]["total-bytes-uncontrolled"] = ingress_secy[10]
    counters["ingress"]["secy"]["total-bytes-controlled"] = ingress_secy[11]
    counters["ingress"]["secy"]["packets-transform-error"] = ingress_secy[12]
    counters["ingress"]["secy"]["control-packets"] = ingress_secy[13]
    counters["ingress"]["secy"]["untagged-packets"] = ingress_secy[14]
    counters["ingress"]["secy"]["no-tag-packets"] = ingress_secy[15]
    counters["ingress"]["secy"]["bad-tag-packets"] = ingress_secy[16]
    counters["ingress"]["secy"]["no-sci-match-packets"] = ingress_secy[17]
    counters["ingress"]["secy"]["unknown-sci-match-packets"] = ingress_secy[18]
    counters["ingress"]["secy"]["tagged-control-packets"] = ingress_secy[19]

    egress_secy = [int(v) for v in attrs[3].split(",")]
    counters["egress"]["secy"]["unicast-packets-uncontrolled"] = egress_secy[0]
    counters["egress"]["secy"]["multicast-packets-uncontrolled"] = egress_secy[1]
    counters["egress"]["secy"]["broadcast-packets-uncontrolled"] = egress_secy[2]
    counters["egress"]["secy"]["rx-drop-packets-uncontrolled"] = egress_secy[3]
    counters["egress"]["secy"]["rx-error-packets-uncontrolled"] = egress_secy[4]
    counters["egress"]["secy"]["unicast-packets-controlled"] = egress_secy[5]
    counters["egress"]["secy"]["multicast-packets-controlled"] = egress_secy[6]
    counters["egress"]["secy"]["broadcast-packets-controlled"] = egress_secy[7]
    counters["egress"]["secy"]["rx-drop-packets-controlled"] = egress_secy[8]
    counters["egress"]["secy"]["rx-error-packets-controlled"] = egress_secy[9]
    counters["egress"]["secy"]["total-bytes-uncontrolled"] = egress_secy[10]
    counters["egress"]["secy"]["total-bytes-controlled"] = egress_secy[11]
    counters["egress"]["secy"]["packets-transform-error"] = egress_secy[12]
    counters["egress"]["secy"]["control-packets"] = egress_secy[13]
    counters["egress"]["secy"]["untagged-packets"] = egress_secy[14]

    ingress_channel = [int(v) for v in attrs[4].split(",")]
    counters["ingress"]["channel"]["multiple-rule-match"] = ingress_channel[0]
    counters["ingress"]["channel"]["header-parser-drop"] = ingress_channel[1]
    counters["ingress"]["channel"]["rule-mismatch"] = ingress_channel[2]
    counters["ingress"]["channel"]["control-packet-match"] = ingress_channel[3]
    counters["ingress"]["channel"]["data-packet-match"] = ingress_channel[4]
    counters["ingress"]["channel"]["dropped-packets"] = ingress_channel[5]
    counters["ingress"]["channel"]["in-error-packets"] = ingress_channel[6]

    egress_channel = [int(v) for v in attrs[5].split(",")]
    counters["egress"]["channel"]["multiple-rule-match"] = egress_channel[0]
    counters["egress"]["channel"]["header-parser-drop"] = egress_channel[1]
    counters["egress"]["channel"]["rule-mismatch"] = egress_channel[2]
    counters["egress"]["channel"]["control-packet-match"] = egress_channel[3]
    counters["egress"]["channel"]["data-packet-match"] = egress_channel[4]
    counters["egress"]["channel"]["dropped-packets"] = egress_channel[5]
    counters["egress"]["channel"]["in-error-packets"] = egress_channel[6]

    return counters


class InterfaceServer(ServerBase):
    def __init__(self, conn, taish_server, platform_info):
        super().__init__(conn, "goldstone-interfaces")
        info = {}
        for i in platform_info:
            if "interface" in i:
                ifname = f"Interface{i['interface']['suffix']}"
                info[ifname] = i
        self.platform_info = info
        self.conn = conn
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.notif_q = asyncio.Queue()
        self.is_initializing = True
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "admin-status": AdminStatusHandler,
                        "name": NoOp,
                        "description": NoOp,
                        "interface-type": InterfaceTypeHandler,
                    },
                    "ethernet": {
                        "config": {
                            "fec": FECHandler,
                            "mtu": MTUHandler,
                        },
                        "auto-negotiate": {
                            "config": {
                                "enabled": AutoNegoHandler,
                            }
                        },
                        "static-macsec": {
                            "config": {
                                "key": MACSECStaticKeyHandler,
                            }
                        },
                    },
                    "otn": {
                        "config": {
                            "mfi-type": MFITypeHandler,
                        }
                    },
                }
            }
        }

    def get_default(self, key):
        ctx = self.sess.get_ly_ctx()
        keys = [
            ["interfaces", "interface", "config", key],
            ["interfaces", "interface", "ethernet", "config", key],
            ["interfaces", "interface", "otn", "config", key],
            [
                "interfaces",
                "interface",
                "ethernet",
                "auto-negotiate",
                "config",
                key,
            ],
        ]

        for k in keys:
            xpath = "".join(f"/goldstone-interfaces:{v}" for v in k)
            try:
                for node in ctx.find_path(xpath):
                    if node.type().name() == "boolean":
                        return node.default() == "true"
                    return node.default()
            except libyang.util.LibyangError:
                pass

        raise None

    async def reconcile(self):
        prefix = "/goldstone-interfaces:interfaces/interface"
        for ifname, obj, module in await self.get_ifname_list():
            xpath = f"{prefix}[name='{ifname}']"
            config = self.get_running_data(
                xpath, default={}, include_implicit_defaults=True
            )
            iftype = config.get("config", {}).get(
                "interface-type", self.get_default("interface-type")
            )
            if iftype == "IF_OTN":
                mfi = (
                    config.get("otn", {})
                    .get("config", {})
                    .get("mfi-type", self.get_default("mfi-type"))
                )
                await obj.set_multiple(
                    [
                        ("provision-mode", "serdes-only"),
                        ("signal-rate", "otu4"),
                        ("otn-mfi-type", mfi.lower()),
                    ]
                )
            elif iftype == "IF_ETHERNET":
                await obj.set_multiple(
                    [("provision-mode", "normal"), ("signal-rate", "100-gbe")]
                )

            admin_status = config.get("config", {}).get(
                "admin-status", self.get_default("admin-status")
            )
            value = "false" if admin_status == "UP" else "true"
            await obj.set("tx-dis", value)

            fec = config.get("ethernet", {}).get("config", {}).get("fec")
            if fec == None:
                fec = self.get_default("fec")
            await obj.set("fec-type", fec.lower())

            mtu = config.get("ethernet", {}).get("config", {}).get("mtu")
            if mtu == None:
                mtu = int(self.get_default("mtu"))
            await obj.set("mtu", mtu)
            await obj.set("mru", mtu)

            if isinstance(obj, taish.NetIf):
                key = (
                    config.get("ethernet", {})
                    .get("static-macsec", {})
                    .get("config", {})
                    .get("key")
                )
                if key:
                    key = struct.unpack("IIII", base64.b64decode(key))
                    key = ",".join((str(i) for i in key))
                else:
                    key = ""

                await obj.set("macsec-static-key", key)

            elif isinstance(obj, taish.HostIf):
                anlt = (
                    config.get("ethernet", {})
                    .get("auto-negotiate", {})
                    .get("config", {})
                    .get("enabled", self.get_default("enabled"))
                )
                await obj.set("auto-negotiation", "true" if anlt else "false")

    async def tai_cb(self, obj, attr_meta, msg):
        m_oid = obj.obj.module_oid
        modules = await self.list_modules()

        for location, m in modules.items():
            if m.oid == m_oid:
                loc = location
                break
        else:
            logger.error(f"module not found: {m_oid}")
            return

        ifname = await self.taiobj2ifname(
            loc, 1 if isinstance(obj, taish.NetIf) else 0, obj
        )
        if not ifname:
            return

        await self.notif_q.put({"ifname": ifname, "msg": msg, "obj": obj})

    async def taiobj2ifname(self, loc, type_, obj):
        index = int(await obj.get("index"))
        return f"Interface{loc}/{type_}/{index+1}"

    async def notification_tasks(self):
        async def task(obj, attr):
            try:
                await obj.monitor(attr, self.tai_cb, json=True)
            except asyncio.exceptions.CancelledError as e:
                while True:
                    await asyncio.sleep(0.1)
                    v = await obj.get(attr)
                    logger.debug(v)
                    if "(nil)" in v:
                        return
                raise e

        return [
            task(obj, "alarm-notification")
            for ifname, obj, module in await self.get_ifname_list()
        ]

    async def start(self):
        async def ping():
            while True:
                await asyncio.sleep(5)
                try:
                    await asyncio.wait_for(self.list_modules(), timeout=2)
                except Exception as e:
                    logger.error(f"ping failed {e}")
                    return

        async def handle_notification(notification):
            logger.info(notification)
            ifname = notification["ifname"]
            msg = notification["msg"]
            obj = notification["obj"]
            eventname = "goldstone-interfaces:interface-link-state-notify-event"

            for attr in msg.attrs:
                meta = await obj.get_attribute_metadata(attr.attr_id)
                if meta.short_name != "pcs-status":
                    continue
                status = pcs_status2oper_status(json.loads(attr.value))
                notif = {"if-name": ifname, "oper-status": status}
                self.send_notification(eventname, notif)

        async def notif_loop():
            while True:
                notification = await self.notif_q.get()
                await handle_notification(notification)
                self.notif_q.task_done()

        tasks = await super().start()
        self.is_initializing = False

        return tasks + [ping(), notif_loop()] + await self.notification_tasks()

    async def stop(self):
        logger.info(f"stop server")
        self.taish.close()
        super().stop()

    def pre(self, user):
        if self.is_initializing:
            raise sysrepo.SysrepoLockedError("initializing")

    async def list_modules(self):
        modules = await self.taish.list()
        return {k: v for k, v in modules.items() if k not in self.taish._ignored_module}

    async def get_ifname_list(self, gearbox=None):
        modules = await self.list_modules()

        interfaces = []
        for loc, module in modules.items():
            if gearbox and gearbox != loc:
                continue
            for hostif in module.hostifs:
                interfaces.append(
                    (f"Interface{loc}/0/{hostif.index+1}", hostif, module)
                )
            for netif in module.netifs:
                interfaces.append((f"Interface{loc}/1/{netif.index+1}", netif, module))

        return interfaces

    async def ifname2taiobj(self, ifname, with_module=False):
        v = [int(v) for v in ifname.replace("Interface", "").split("/")]
        m = await self.taish.get_module(str(v[0]))
        obj = None
        if v[1] == 0:  # hostif
            obj = m.get_hostif(v[2] - 1)
        elif v[1] == 1:  # netif
            obj = m.get_netif(v[2] - 1)

        if with_module:
            return (obj, m)
        else:
            return obj

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.debug(f"xpath: {xpath}, req_xpath: {req_xpath}")
        xpath = list(libyang.xpath_split(req_xpath))
        logger.debug(f"xpath: {xpath}")

        counter_only = "counters" in req_xpath

        if len(xpath) < 2 or len(xpath[1][2]) < 1:
            ifnames = await self.get_ifname_list()
        else:
            if xpath[1][2][0][0] == "name":
                name = xpath[1][2][0][1]
                obj, module = await self.ifname2taiobj(name, with_module=True)
                ifnames = [(name, obj, module)]
            elif xpath[1][2][0][0] == "state/goldstone-gearbox:associated-gearbox":
                ifnames = await self.get_ifname_list(xpath[1][2][0][1])
            else:
                logger.warn(f"invalid request: {xpath}")
                return

        interfaces = []
        for ifname, obj, module in ifnames:
            i = {
                "name": ifname,
                "config": {"name": ifname},
                "state": {"associated-gearbox": module.obj.location},
            }

            if len(xpath) == 3 and xpath[2][1] == "name":
                interfaces.append(i)
                continue

            p = self.platform_info.get(ifname)
            if p:
                v = {}
                if "component" in p:
                    v["platform"] = {"component": p["component"]["name"]}
                if "tai" in p:
                    t = {
                        "module": p["tai"]["module"]["name"],
                        "host-interface": p["tai"]["hostif"]["name"],
                    }
                    v["transponder"] = t
                i["component-connection"] = v

            if len(xpath) == 3 and xpath[2][1] == "component-connection":
                interfaces.append(i)
                continue

            if (await module.get("admin-status")) != "up":
                i["state"]["admin-status"] = "DOWN"
                i["state"]["oper-status"] = "DOWN"
                interfaces.append(i)
                continue

            counters = {}
            try:
                attrs = await obj.get_multiple(
                    ["pmon-enet-mac-rx", "pmon-enet-mac-tx", "pmon-enet-phy-rx"]
                )
                i["state"]["counters"] = parse_counters(attrs)
            except taish.TAIException as e:
                logger.warning(f"failed to get counter info: {e}")

            if counter_only:
                interfaces.append(i)
                continue

            try:
                i["state"]["admin-status"] = (
                    "DOWN" if await obj.get("tx-dis") == "true" else "UP"
                )
            except taish.TAIException:
                pass

            signal_rate = await obj.get("signal-rate")
            connected = await obj.get("connected-interface")
            i["state"]["is-connected"] = connected != "oid:0x0"
            if signal_rate == "otu4":
                i["state"]["oper-status"] = (
                    "UP"
                    if connected != "oid:0x0" and i["state"]["admin-status"] == "UP"
                    else "DOWN"
                )
                state = {}
                try:
                    state["mfi-type"] = (await obj.get("otn-mfi-type")).upper()
                except taish.TAIException:
                    pass
                i["otn"] = {"state": state}
            else:
                state = {}
                try:
                    state["fec"] = (await obj.get("fec-type")).upper()
                except taish.TAIException:
                    pass

                try:
                    state["mtu"] = int(await obj.get("mtu"))
                except taish.TAIException:
                    pass

                state["speed"] = (
                    "SPEED_100G" if signal_rate == "100-gbe" else "SPEED_UNKNOWN"
                )

                i["ethernet"] = {"state": state}

                if isinstance(obj, taish.NetIf):
                    try:
                        attrs = await obj.get_multiple(
                            [
                                "macsec-static-key",
                                "macsec-ingress-sa-stats",
                                "macsec-egress-sa-stats",
                                "macsec-ingress-secy-stats",
                                "macsec-egress-secy-stats",
                                "macsec-ingress-channel-stats",
                                "macsec-egress-channel-stats",
                            ]
                        )
                        key = attrs[0]
                        key = [int(v) for v in key.split(",")]
                        key = struct.pack("IIII", *key)
                        key = base64.b64encode(key).decode()
                        counters = parse_macsec_counters(attrs[1:])
                        i["ethernet"]["static-macsec"] = {
                            "state": {
                                "key": key,
                                "counters": counters,
                            }
                        }
                    except taish.TAIException as e:
                        logger.warning(f"failed to get MACSEC info: {e}")
                elif isinstance(obj, taish.HostIf):
                    enabled = await obj.get("auto-negotiation")
                    anlt = {"enabled": enabled == "true"}
                    try:
                        status = json.loads(await obj.get("anlt-defect", json=True))
                        anlt["status"] = status
                    except taish.TAIException as e:
                        pass

                    i["ethernet"]["auto-negotiate"] = {"state": anlt}

                try:
                    pcs = json.loads(await obj.get("pcs-status", json=True))
                    serdes = json.loads(await obj.get("serdes-status", json=True))
                    i["state"]["oper-status"] = pcs_status2oper_status(pcs)
                    state = {"pcs-status": pcs, "serdes-status": serdes}
                    i["ethernet"]["pcs"] = {"state": state}
                except taish.TAIException:
                    pass

            interfaces.append(i)

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}
