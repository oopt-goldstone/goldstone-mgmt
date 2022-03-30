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

        if "cap-cache" not in user:
            user["cap-cache"] = {}

        for name in self.tai_attr_name:
            if isinstance(self.obj, taish.Module):
                t = "module"
            elif isinstance(self.obj, taish.NetIf):
                t = "netif"
            elif isinstance(self.obj, taish.HostIf):
                t = "hostif"
            else:
                raise sysrepo.SysrepoInvalArgError(
                    f"unsupported object type: {type(self.obj)}"
                )

            cap = user["cap-cache"].get(f"{t}:{name}")
            if cap == None:
                try:
                    cap = await self.obj.get_attribute_capability(name)
                except taish.TAIException as e:
                    logger.error(f"failed to get capability: {name}")
                    raise sysrepo.SysrepoInvalArgError(e.msg)
                logger.info(f"cap {name}: {cap}")
                user["cap-cache"][f"{t}:{name}"] = cap
            else:
                logger.info(f"cached cap {name}: {cap}")

            if self.type == "deleted":
                leaf = self.xpath[-1][1]
                d = self.server.get_default(leaf, self.ifname)
                if d != None:
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
        _v = []
        for i, name in enumerate(self.tai_attr_name):
            if str(self.original_value[i]) != str(self.value[i]):
                logger.debug(
                    f"applying: {name} {self.original_value[i]} => {self.value[i]}"
                )
                _v.append((name, self.value[i]))
        await self.obj.set_multiple(_v)

    async def revert(self, user):
        if not self.tai_attr_name:
            return
        _v = []
        for i, name in enumerate(self.tai_attr_name):
            if str(self.original_value[i]) != str(self.value[i]):
                logger.warning(
                    f"reverting: {self.name} {self.value[i]} => {self.original_value[i]}"
                )
                _v.append((name, self.original_value[i]))
        await self.obj.set_multiple(_v)


class AdminStatusHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.user = user
        self.tai_attr_name = "provision-mode"

    def to_tai_value(self, v, attr_name):
        if v == "UP":
            cache = self.setup_cache(self.user)
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{self.ifname}']/config"
            t = libyang.xpath_get(
                cache,
                f"{xpath}/interface-type",
                self.server.get_default("interface-type", self.ifname),
            )
            if t == "IF_ETHERNET":
                return "normal"
            elif t == "IF_OTN":
                return "serdes-only"
            else:
                raise sysrepo.SysrepoInvalArgError(f"unsupported interface-type: {t}")
        else:
            return "none"


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
        self.user = user
        self.tai_attr_name = ["provision-mode", "signal-rate"]

    def to_tai_value(self, v, attr_name):
        if attr_name == "provision-mode":
            cache = self.setup_cache(self.user)
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{self.ifname}']/config"
            a = libyang.xpath_get(
                cache,
                f"{xpath}/admin-status",
                self.server.get_default("admin-status", self.ifname),
            )
            if a == "DOWN":
                return "none"
            elif v == "IF_ETHERNET":
                return "normal"
            elif v == "IF_OTN":
                return "serdes-only"
            else:
                raise sysrepo.SysrepoInvalArgError(f"unsupported interface-type: {v}")

        elif attr_name == "signal-rate":
            if v == "IF_ETHERNET":
                return "100-gbe"
            elif v == "IF_OTN":
                return "otu4"


class PinModeHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.user = user
        self.tai_attr_name = "pin-mode"
        self._removed = []
        self._created = []

    async def validate(self, user):
        await super().validate(user)

        info = self.server.get_platform_info(self.ifname)
        if not info:
            raise sysrepo.SysrepoInvalArgError(
                f"pin-mode setting not supported. no platform info"
            )

        valids = [i["interface"]["pin-mode"] for i in info]

        if self.value[0] not in valids:
            raise sysrepo.SysrepoInvalArgError(
                f"supported values are {valids}. given {self.value[0]}"
            )

        cache = self.setup_cache(self.user)

        # conflicting interfaces must not have any configuration
        for ifname in self.server.get_conflicting_ifnames(self.ifname, self.value[0]):
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
            a = libyang.xpath_get(cache, xpath)
            if a:
                raise sysrepo.SysrepoInvalArgError(
                    f"conflicting configuration exists for {ifname}"
                )

    # remove conflicting TAI objects for a given pin-mode
    async def remove(self, ifnames=None):
        if ifnames == None:
            ifnames = self.server.get_conflicting_ifnames(self.ifname, self.value[0])

        i = []
        for ifname in ifnames:
            try:
                obj_to_remove, module = await self.server.ifname2taiobj(
                    ifname, with_module=True
                )
            except taish.TAIException:
                pass
            else:
                new_mapping = await self.server.get_new_mapping(module, ifname)
                logger.debug(f"new mapping: {new_mapping}")
                await module.set("tributary-mapping", json.dumps(new_mapping))

                logger.debug(f"removing 0x{obj_to_remove.oid:08x}")
                await self.server.taish.remove(obj_to_remove.oid)
                i.append(ifname)
        return i

    # create removed TAI objects that *were* conflicting and not any more
    # with the given pin-mode
    async def create(self, ifnames=None):
        if ifnames == None:
            # interfaces that have been removed due to the original pin-mode
            ifnames = set(
                self.server.get_conflicting_ifnames(self.ifname, self.original_value[0])
            )
            # exclude the interfaces that conflicts with the current pin-mode
            ifnames = ifnames - set(
                self.server.get_conflicting_ifnames(self.ifname, self.value[0])
            )

        cache = self.setup_cache(self.user)
        i = []
        for ifname in ifnames:
            xpath = f"/goldstone-interfaces:interfaces/interface[name='{ifname}']"
            config = libyang.xpath_get(cache, xpath, {})
            obj, module = await self.server.create_interface(ifname, config)
            logger.debug(f"created {ifname}, oid: 0x{obj.oid:08x}")
            mapping = self.server.get_default_mapping(module)
            logger.debug(f"new mapping: {mapping}")
            await module.set("tributary-mapping", mapping)
            i.append(ifname)
        return i

    def to_tai_value(self, v, attr_name):
        return v.lower()

    async def apply(self, user):
        self._removed = await self.remove()
        await super().apply(user)
        self._created = await self.create()

    async def revert(self, user):
        await self.remove(self._created)
        await super().revert(user)
        await self.create(self._removed)


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
        if v == "":
            return ""
        v = struct.unpack("IIII", base64.b64decode(v))
        return ",".join((str(i) for i in v))


class AutoNegoHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "auto-negotiation"

    async def validate(self, user):
        # netif doesn't support augo nego. only allow false config
        if isinstance(self.obj, taish.NetIf):
            if self.type == "deleted":
                return
            if self.change.value:
                raise sysrepo.SysrepoInvalArgError(
                    "line side interface doesn't support auto negotiation"
                )
            return
        return await super().validate(user)

    async def apply(self, user):
        if isinstance(self.obj, taish.NetIf):
            return
        return await super().apply(user)

    async def revert(self, user):
        if isinstance(self.obj, taish.NetIf):
            return
        return await super().revert(user)

    def to_tai_value(self, v, attr_name):
        return "true" if v else "false"


class TXTimingModeHandler(IfChangeHandler):
    async def _init(self, user):
        await super()._init(user)
        self.tai_attr_name = "tx-timing-mode"

    def to_tai_value(self, v, attr_name):
        return v


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
    counters["out-unicast-pkts"] = mac_tx[5]
    counters["out-broadcast-pkts"] = mac_tx[7]
    counters["out-multicast-pkts"] = mac_tx[6]
    counters["out-discards"] = mac_tx[29]  # tx_pkts_drained
    counters["out-errors"] = mac_tx[4]

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
                assert "name" in i["interface"]
                assert "pin-mode" in i["interface"]
                if i["interface"]["name"] not in info:
                    info[i["interface"]["name"]] = []
                info[i["interface"]["name"]].append(i)

        self._platform_info = info
        self.conn = conn
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.notif_q = asyncio.Queue()
        self.notif_task_q = asyncio.Queue()
        self.is_initializing = True
        self.oidmap = {}  # key: oid, value: obj
        self.handlers = {
            "interfaces": {
                "interface": {
                    "name": NoOp,
                    "config": {
                        "admin-status": AdminStatusHandler,
                        "name": NoOp,
                        "description": NoOp,
                        "interface-type": InterfaceTypeHandler,
                        "pin-mode": PinModeHandler,
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
                        "synce": {
                            "config": {
                                "tx-timing-mode": TXTimingModeHandler,
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

    def get_default(self, key, ifname):
        # static-macsec/config/key
        if key == "key":
            return ""
        elif key == "pin-mode":
            info = self.get_platform_info(ifname)
            if not info:
                return None

            if len(info) == 1:
                return info[0]["interface"]["pin-mode"].upper()

            for i in info:
                if i["interface"]["default"]:
                    return i["interface"]["pin-mode"].upper()

            return None

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

        return None

    async def reconcile_interface(self, ifname, obj, config):
        iftype = config.get("config", {}).get(
            "interface-type", self.get_default("interface-type", ifname)
        )
        admin_status = config.get("config", {}).get(
            "admin-status", self.get_default("admin-status", ifname)
        )

        if iftype == "IF_OTN":
            mfi = (
                config.get("otn", {})
                .get("config", {})
                .get("mfi-type", self.get_default("mfi-type", ifname))
            )
            mode = "serdes-only" if admin_status == "UP" else "none"
            attrs = [
                ("provision-mode", mode),
                ("signal-rate", "otu4"),
                ("otn-mfi-type", mfi.lower()),
            ]
        elif iftype == "IF_ETHERNET":
            mode = "normal" if admin_status == "UP" else "none"
            attrs = [("provision-mode", mode), ("signal-rate", "100-gbe")]

        pin_mode = await self.get_pin_mode(ifname)
        if pin_mode:
            attrs.append(("pin-mode", pin_mode.lower()))
        else:
            logger.warning(f"no pin-mode configuration for {ifname}")

        await obj.set_multiple(attrs)

        fec = config.get("ethernet", {}).get("config", {}).get("fec")
        if fec == None:
            fec = self.get_default("fec", ifname)
        await obj.set("fec-type", fec.lower())

        mtu = config.get("ethernet", {}).get("config", {}).get("mtu")
        if mtu == None:
            mtu = int(self.get_default("mtu", ifname))
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
                .get("enabled", self.get_default("enabled", ifname))
            )
            await obj.set("auto-negotiation", "true" if anlt else "false")

    async def reconcile(self):
        prefix = "/goldstone-interfaces:interfaces/interface"

        for ifname, obj, _ in await self.get_ifname_list():
            xpath = f"{prefix}[name='{ifname}']"
            config = self.get_running_data(
                xpath, default={}, include_implicit_defaults=True
            )
            await self.reconcile_interface(ifname, obj, config)

    async def tai_cb(self, obj, attr_meta, msg):
        logger.info(f"{obj}, {obj.obj}")
        m_oid = obj.obj.module_oid
        modules = await self.list_modules()

        for location, m in modules.items():
            if m.oid == m_oid:
                loc = location
                break
        else:
            logger.error(f"module not found: {m_oid}")
            return

        ifname = await self.taiobj2ifname(loc, obj)
        if not ifname:
            return

        await self.notif_q.put({"ifname": ifname, "msg": msg, "obj": obj})

    async def taiobj2ifname(self, loc, obj):
        index = int(await obj.get("index"))
        type_ = 1 if isinstance(obj, taish.NetIf) else 0
        return f"Interface{loc}/{type_}/{index+1}"

    async def notification_task(self):
        async def monitor(obj, attr):
            try:
                await obj.monitor(attr, self.tai_cb)
            except asyncio.exceptions.CancelledError as e:
                while True:
                    await asyncio.sleep(0.1)
                    v = await obj.get(attr)
                    logger.debug(v)
                    if "(nil)" in v:
                        return
                raise e

        tasks = [
            asyncio.create_task(monitor(obj, "alarm-notification"), name=ifname)
            for ifname, obj, _ in await self.get_ifname_list()
        ]

        tasks.append(asyncio.create_task(self.notif_task_q.get(), name="create-task"))

        while True:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            pending = list(pending)

            for d in done:
                name = d.get_name()
                if name == "create-task":
                    ifname, obj = d.result()
                    logger.info(f"creating alarm notification task for {ifname}")
                    task = asyncio.create_task(
                        monitor(obj.obj, "alarm-notification"), name=ifname
                    )
                    pending.append(task)
                    pending.append(
                        asyncio.create_task(self.notif_task_q.get(), name="create-task")
                    )
                else:
                    logger.info(
                        f"alarm notification task for {name} ended. exception: {d.exception()}"
                    )

            if not pending:
                return

            tasks = pending

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
                if meta.short_name != "oper-status":
                    continue
                notif = {"if-name": ifname, "oper-status": attr.value.upper()}
                self.send_notification(eventname, notif)

        async def notif_loop():
            while True:
                notification = await self.notif_q.get()
                await handle_notification(notification)
                self.notif_q.task_done()

        tasks = await super().start()
        self.is_initializing = False

        return tasks + [ping(), notif_loop(), self.notification_task()]

    async def stop(self):
        logger.info(f"stop server")
        await self.taish.close()
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

        index = v[2] - 1
        if v[1] == 0:  # hostif
            obj = m.get_hostif(index)
        elif v[1] == 1:  # netif
            obj = m.get_netif(index)

        if with_module:
            return (obj, m)
        else:
            return obj

    async def create_interface(self, ifname, config):
        v = [int(v) for v in ifname.replace("Interface", "").split("/")]
        m = await self.taish.get_module(str(v[0]))

        index = v[2] - 1
        if v[1] == 0:  # hostif
            obj = await m.create_hostif(index)
        elif v[1] == 1:  # netif
            obj = await m.create_netif(index)

        await self.reconcile_interface(ifname, obj, config)

        await self.notif_task_q.put((ifname, obj))

        self.oidmap[obj.oid] = obj

        return obj, m

    def get_platform_info(self, ifname, pin_mode=None):
        info = self._platform_info.get(ifname)
        if not info:
            logger.warning(f"no platform info found for {ifname}")
            return None

        if pin_mode == None:
            return info

        if len(info) == 1:
            return info[0]

        for i in info:
            if i["interface"]["pin-mode"] == pin_mode:
                return i

        logger.error(f"no platform info found for {ifname}")

    def get_conflicting_ifnames(self, ifname, pin_mode):
        info = self.get_platform_info(ifname, pin_mode)
        if not info:
            return []
        return info["interface"].get("conflicts-with", [])

    async def get_pin_mode(self, ifname):
        prefix = "/goldstone-interfaces:interfaces/interface"
        pin_mode = self.get_running_data(f"{prefix}[name='{ifname}']/config/pin-mode")
        if pin_mode:
            return pin_mode

        return self.get_default("pin-mode", ifname)

    async def oper_cb_intf(self, xpath, counter_only, ifname, obj, module):
        i = {
            "name": ifname,
            "config": {"name": ifname},
            "state": {"associated-gearbox": module.obj.location},
        }

        if len(xpath) == 3 and xpath[2][1] == "name":
            return i

        obj = await self.ifname2taiobj(ifname)
        pm = await obj.get("pin-mode")
        p = self.get_platform_info(ifname, pm)
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
            return i

        if (await module.get("admin-status")) != "up":
            i["state"]["admin-status"] = "DOWN"
            i["state"]["oper-status"] = "DOWN"
            return i

        counters = {}
        try:
            attrs = await obj.get_multiple(
                ["pmon-enet-mac-rx", "pmon-enet-mac-tx", "pmon-enet-phy-rx"]
            )
            i["state"]["counters"] = parse_counters(attrs)
        except taish.TAIException as e:
            logger.warning(f"failed to get counter info: {e}")

        if counter_only:
            return i

        (
            prov_mode,
            signal_rate,
            connected,
            mfi_type,
            fec_type,
            mtu,
            tx_timing_mode,
            current_tx_timing_mode,
            oper_status,
            pin_mode,
        ) = await obj.get_multiple(
            [
                "provision-mode",
                "signal-rate",
                "connected-interface",
                "otn-mfi-type",
                "fec-type",
                "mtu",
                "tx-timing-mode",
                "current-tx-timing-mode",
                "oper-status",
                "pin-mode",
            ]
        )

        i["state"]["admin-status"] = "DOWN" if prov_mode == "none" else "UP"
        i["state"]["oper-status"] = oper_status.upper()
        i["state"]["is-connected"] = connected != "oid:0x0"
        i["state"]["pin-mode"] = pin_mode.upper()

        if signal_rate == "otu4":
            i["state"]["oper-status"] = (
                "UP"
                if connected != "oid:0x0" and i["state"]["admin-status"] == "UP"
                else "DOWN"
            )
            i["otn"] = {"state": {"mfi-type": mfi_type.upper()}}
            return i

        i["ethernet"] = {
            "state": {
                "fec": fec_type.upper(),
                "mtu": int(mtu),
                "speed": "SPEED_100G" if signal_rate == "100-gbe" else "SPEED_UNKNOWN",
            },
            "synce": {
                "state": {
                    "tx-timing-mode": tx_timing_mode,
                    "current-tx-timing-mode": current_tx_timing_mode,
                }
            },
        }

        if isinstance(obj, taish.NetIf):
            # check if static MACSEC is configured
            key = self.get_running_data(
                f"/goldstone-interfaces:interfaces/interface[name='{ifname}']/ethernet/goldstone-static-macsec:static-macsec/config/key"
            )
            if key:
                state = {"key": key}
                try:
                    attrs = await obj.get_multiple(
                        [
                            "macsec-ingress-sa-stats",
                            "macsec-egress-sa-stats",
                            "macsec-ingress-secy-stats",
                            "macsec-egress-secy-stats",
                            "macsec-ingress-channel-stats",
                            "macsec-egress-channel-stats",
                        ]
                    )
                    counters = parse_macsec_counters(attrs)
                    state["counters"] = counters
                except taish.TAIException as e:
                    logger.warning(f"failed to get MACSEC counters: {e}")

                i["ethernet"]["static-macsec"] = {"state": state}

        elif isinstance(obj, taish.HostIf):
            enabled = await obj.get("auto-negotiation")
            anlt = {"enabled": enabled == "true"}
            if enabled == "true":
                try:
                    status = json.loads(await obj.get("anlt-defect", json=True))
                    anlt["status"] = status
                except taish.TAIException as e:
                    logger.warning(f"failed to get Autonego defect info: {e}")

            i["ethernet"]["auto-negotiate"] = {"state": anlt}

        try:
            attrs = [
                json.loads(v)
                for v in await obj.get_multiple(
                    ["pcs-status", "serdes-status"], json=True
                )
            ]
            pcs = attrs[0]
            serdes = attrs[1]
            state = {"pcs-status": pcs, "serdes-status": serdes}
            i["ethernet"]["pcs"] = {"state": state}
        except taish.TAIException as e:
            logger.warning(f"failed to get PCS/SERDES status: {e}")
            i["state"]["oper-status"] = "DOWN"

        return i

    def get_default_mapping(self, module):
        _m = {}
        mapping = []
        for netif in module.netifs:
            _m[netif.index] = netif

        for hostif in module.hostifs:
            if hostif.index in _m:
                netif = _m[hostif.index]
                mapping.append({f"oid:0x{netif.oid:08x}": [f"oid:0x{hostif.oid:08x}"]})

        return json.dumps(mapping)

    async def oid2ifname(self, module, oid):
        if type(oid) == str:
            oid = int(oid.replace("oid:", ""), 0)
        obj = self.oidmap.get(oid)
        if not obj:
            return None
        v = await self.taiobj2ifname(module.obj.location, obj)
        return v

    async def get_new_mapping(self, module, ifname_to_exclude):
        new_mapping = []
        for v in json.loads(await module.get("tributary-mapping", json=True)):
            if len(v) != 1:
                logger.warning(f"invalid tributary-mapping item: {v}")
                continue
            for netif, hostif in v.items():
                if len(hostif) != 1:
                    logger.warning(f"invalid tributary-mapping item: {v}")
                    continue
                hostif = hostif[0]

            obj = self.oidmap.get(int(netif.replace("oid:", ""), 0))
            if not obj:
                logger.warning(f"not found {netif}")
                continue
            netif = await self.taiobj2ifname(module.obj.location, obj)

            obj = self.oidmap.get(int(hostif.replace("oid:", ""), 0))
            if not obj:
                logger.warning(f"not found {hostif}")
                continue
            hostif = await self.taiobj2ifname(module.obj.location, obj)

            if ifname_to_exclude == netif or ifname_to_exclude == hostif:
                logger.debug(f"removing entry {v} from the tributary-mapping attribute")
                continue
            new_mapping.append(v)
        return new_mapping

    async def oper_cb(self, xpath, priv):
        counter_only = "counters" in xpath and "static-macsec" not in xpath
        xpath = list(libyang.xpath_split(xpath))

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

        tasks = [
            self.oper_cb_intf(xpath, counter_only, ifname, obj, module)
            for ifname, obj, module in ifnames
        ]

        interfaces = await asyncio.gather(*tasks)

        return {"goldstone-interfaces:interfaces": {"interface": interfaces}}
