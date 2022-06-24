import logging
import taish
import asyncio
import json
import struct
import base64
import libyang
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp
from goldstone.lib.errors import InvalArgError, LockedError, NotFoundError

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_STATUS = "down"
IGNORE_LEAVES = ["name", "enable-notify", "enable-alarm-notification"]

TAI_STATUS_NOT_SUPPORTED = -0x00000002
TAI_STATUS_ATTR_NOT_SUPPORTED_0 = -0x00050000
TAI_STATUS_ATTR_NOT_SUPPORTED_MAX = -0x0005FFFF


def is_not_supported(code):
    return code == TAI_STATUS_NOT_SUPPORTED or (
        code <= TAI_STATUS_ATTR_NOT_SUPPORTED_0
        and code >= TAI_STATUS_ATTR_NOT_SUPPORTED_MAX
    )


async def cancel_notification_task(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class TAIHandler(ChangeHandler):
    async def _init(self, user):
        xpath, module = await self.server.get_module_from_xpath(self.change.xpath)

        if module == None:
            raise InvalArgError("Invalid Transponder name")

        self.module = module
        self.xpath = xpath
        self.attr_name = None
        self.obj = None
        self.value = None
        self.original_value = None

    async def validate(self, user):
        if not self.attr_name:
            return
        try:
            meta = await self.obj.get_attribute_metadata(self.attr_name)
        except taish.TAIException as e:
            raise InvalArgError(f"unsupported attribute: {self.attr_name}")

        try:
            cap = await self.obj.get_attribute_capability(meta.attr_id)
        except taish.TAIException as e:
            if is_not_supported(e.code):
                raise InvalArgError(f"unsupported attribute: {self.attr_name}")
            raise InvalArgError(e.msg)

        logger.info(f"cap: {cap}")

        if self.type == "deleted":
            if cap.default_value == "":  # and is_deleted
                raise InvalArgError(
                    f"no default value. cannot remove the configuration"
                )
            if self.attr_name == "admin-status":
                self.value = DEFAULT_ADMIN_STATUS
            else:
                self.value = cap.default_value
        else:
            v = self.change.value
            if cap.min != "" and float(cap.min) > float(v):
                raise InvalArgError(f"minimum {k} value is {cap.min}. given {v}")

            if cap.max != "" and float(cap.max) < float(v):
                raise InvalArgError(f"maximum {k} value is {cap.max}. given {v}")

            valids = cap.supportedvalues
            if len(valids) > 0 and v not in valids:
                raise InvalArgError(f"supported values are {valids}. given {v}")

            if meta.usage == "<bool>":
                v = "true" if v else "false"

            self.value = v

    async def apply(self, user):
        if not self.attr_name:
            return
        self.original_value = await self.obj.get(self.attr_name)
        try:
            await self.obj.set(self.attr_name, self.value)
        except taish.TAIException as e:
            if is_not_supported(e.code):
                raise InvalArgError(f"unsupported attribute: {self.attr_name}")
            raise InvalArgError(e.msg)

    async def revert(self, user):
        if not self.attr_name:
            return
        logger.warning(
            f"reverting: {self.attr_name} {self.value} => {self.original_value}"
        )
        try:
            await self.obj.set(self.attr_name, self.original_value)
        except taish.TAIException as e:
            if is_not_supported(e.code):
                raise InvalArgError(f"unsupported attribute: {self.attr_name}")
            raise InvalArgError(e.msg)


class ModuleHandler(TAIHandler):
    async def _init(self, user):
        await super()._init(user)
        self.obj = self.module

        logger.info(f"obj: {self.obj}, xpath: {self.xpath}")

        if len(self.xpath) != 2 or self.xpath[1][1] in IGNORE_LEAVES:
            self.attr_name = None
        else:
            self.attr_name = self.xpath[1][1]


class InterfaceHandler(TAIHandler):
    async def _init(self, user):
        await super()._init(user)
        assert self.xpath[0][1] in ["network-interface", "host-interface"]
        assert self.xpath[0][2][0][0] == "name"
        idx = int(self.xpath[0][2][0][1])
        if self.xpath[0][1] == "network-interface":
            self.obj = self.module.get_netif(idx)
        else:
            self.obj = self.module.get_hostif(idx)

        if len(self.xpath) != 3 or self.xpath[2][1] in IGNORE_LEAVES:
            self.attr_name = None
        else:
            self.attr_name = self.xpath[2][1]

    async def validate(self, user):
        await super().validate(user)
        if self.attr_name != "line-rate":
            return

        v = self.server.rate_info.get(self.value)
        if v == None:
            raise InvalArgError(f"no platform info for line-rate: {self.value}")

        self.hostifs = v
        self.num_hostifs = int(await self.module.get("num-host-interfaces"))
        module_name = self.server.location2name(self.module.location)
        prefix = f"/goldstone-transponder:modules/module[name='{module_name}']"

        cache = self.setup_cache(user)
        for index in range(self.num_hostifs):
            must_exists = index in self.hostifs
            if not must_exists:
                xpath = prefix + f"/host-interface[name='{index}']"
                config = libyang.xpath_get(cache, xpath, None)
                if config:
                    raise InvalArgError(
                        f"host-interface({index}) has configuration that conflicts with line-rate: {self.value}"
                    )

    async def apply(self, user):
        if self.attr_name == "line-rate":
            self.created = []
            self.removed = []
            num_hostifs = int(await self.module.get("num-host-interfaces"))
            modules = self.server.modules[self.module.location]
            async with modules["lock"]:
                for index in range(self.num_hostifs):
                    must_exists = index in self.hostifs
                    try:
                        hostif = self.module.get_hostif(index)
                        if not must_exists:
                            task = modules["hostifs"][index]
                            await cancel_notification_task(task)
                            logger.debug(f"removing hostif({index})")
                            await self.server.taish.remove(hostif.oid)
                            self.removed.append(index)
                    except taish.TAIException:
                        if must_exists:
                            logger.debug(f"creating hostif({index})")
                            hostif = await self.module.create_hostif(index)
                            self.created.append(hostif)
                            task = await self.server.create_tai_notif_task(hostif)
                            modules["hostifs"][index] = task

        await super().apply(user)

    async def revert(self, user):
        await super().revert(user)

        if self.attr_name == "line-rate":

            modules = self.server.modules[self.module.location]
            async with modules["lock"]:
                for obj in self.created:
                    task = modules["hostifs"][obj.index]
                    await cancel_notification_task(task)
                    await self.server.taish.remove(obj.oid)
                for index in self.removed:
                    hostif = await self.module.create_hostif(index)
                    task = await self.server.create_tai_notif_task(hostif)
                    modules["hostifs"][index] = task


class InvalidXPath(Exception):
    pass


def attr_tai2yang(attr, meta, schema):
    if meta.usage != "<float>":
        return json.loads(attr)

    # we need special handling for float value since YANG doesn't
    # have float..
    base = schema.type()
    if base == "decimal64":
        return json.loads(attr)
    elif base == "binary":
        v = base64.b64encode(struct.pack(">f", float(attr)))
        return v.decode()

    logger.warning(f"not supported float value: {attr}")
    raise taish.TAIException()


class TransponderServer(ServerBase):
    def __init__(self, conn, taish_server, platform_info):
        super().__init__(conn, "goldstone-transponder")
        info = {}
        rate_info = {}
        for i in platform_info:
            if "component" in i and "tai" in i:
                name = i["tai"]["module"]["name"]
                if name in info:
                    raise Exception(f"duplicated platform info: module name: {name}")
                info[name] = i
            elif "transponder" in i:
                # TODO currently south-tai doesn't support per-module configuration for the netif rate and hostif mapping
                # also it doesn't support modules with multiple netif
                netif = i["transponder"]["netif"]
                assert netif["index"] == 0
                rate = netif["line-rate"]
                if rate in rate_info:
                    raise Exception(f"duplicated rate info: rate: {rate}")
                hostifs = i["transponder"]["hostifs"]
                rate_info[rate] = [v["index"] for v in hostifs]
        self.platform_info = info
        self.rate_info = rate_info
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.notif_q = asyncio.Queue()

        # modules holds asyncio tasks that subscribes to TAI notification
        # the asyncio task is created by self.create_tai_notif_task(object)
        # key: location, value: {"lock": lock for mutating TAI objects, "notif_task": notif-task for module, "netifs": {"0": <notif-task>}, "hostifs": {"0": <notif-task>, "1": <notif-task>, "2": <notif-task>..}}
        self.modules = {}

        self.is_initializing = True
        self.handlers = {
            "modules": {
                "module": {
                    "name": NoOp,
                    "config": ModuleHandler,
                    "network-interface": {
                        "name": NoOp,
                        "config": InterfaceHandler,
                    },
                    "host-interface": {
                        "name": NoOp,
                        "config": InterfaceHandler,
                    },
                    "component-connection": NoOp,
                }
            }
        }

    async def tai_cb(self, obj, attr_meta, msg):
        if isinstance(obj, taish.Module):
            type_ = "module"
        elif isinstance(obj, taish.NetIf):
            type_ = "network"
        elif isinstance(obj, taish.HostIf):
            type_ = "host"
        else:
            logger.error(f"invalid object: {obj}")
            return

        if type_ == "module":
            location = await obj.get("location")
            key = self.location2name(location)
            if not key:
                logger.warning(f"failed to get name from location: {location}")
                return
            xpath = f"/goldstone-transponder:modules/module[name='{key}']/config/enable-{attr_meta.short_name}"
        else:
            type_ = type_ + "-interface"
            m_oid = obj.obj.module_oid
            modules = await self.taish.list()

            for location, m in modules.items():
                if m.oid == m_oid:
                    module_location = location
                    break
            else:
                logger.error(f"module not found: {m_oid}")
                return

            key = self.location2name(module_location)
            if not key:
                logger.warning(
                    f"failed to get module name from location: {module_location}"
                )
                return
            index = await obj.get("index")
            xpath = f"/goldstone-transponder:modules/module[name='{key}']/{type_}[name='{index}']/config/enable-{attr_meta.short_name}"

        eventname = f"goldstone-transponder:{type_}-{attr_meta.short_name}-event"

        v = {"module-name": key}
        if type_ != "module":
            v["index"] = int(index)

        await self.notif_q.put(
            {"xpath": xpath, "eventname": eventname, "v": v, "obj": obj, "msg": msg}
        )

    async def create_tai_notif_task(self, obj):
        async def monitor(obj, attr):
            try:
                logger.info(f"monitor: {obj.oid}, attr: {attr}")
                await obj.monitor(attr, self.tai_cb)
            except asyncio.exceptions.CancelledError as e:
                while True:
                    await asyncio.sleep(0.1)
                    v = await obj.get(attr)
                    logger.debug(f"canceling monitoring {attr}, value: {v}")
                    if "(nil)" in v:
                        return
                raise e from None

        tasks = []
        for attr in ["notify", "alarm-notification"]:
            try:
                await obj.get(attr)
            except taish.TAIException:
                pass
            else:
                tasks.append(asyncio.create_task(monitor(obj, attr)))

        return asyncio.gather(*tasks)

    async def initialize_piu(self, config, location):

        name = self.location2name(location)
        if not name:
            logger.warning(f"failed to get module name from location: {location}")
            return

        assert location not in self.modules

        self.modules[location] = {"lock": asyncio.Lock()}

        async with self.modules[location]["lock"]:

            logger.info(f"initializing module({name})")

            attrs = [
                (k, v)
                for k, v in config.get("config", {}).items()
                if k not in IGNORE_LEAVES
            ]
            for a in attrs:
                if a[0] == "admin-status":
                    break
            else:
                attrs.append(("admin-status", DEFAULT_ADMIN_STATUS))

            logger.info(f"module attrs: {attrs}")
            try:
                module = await self.taish.get_module(location)
            except:
                module = await self.taish.create_module(location, attrs=attrs)
            else:
                # reconcile with the running configuration
                logger.debug(
                    f"module({location}) already exists. updating attributes.."
                )
                for k, v in attrs:
                    await module.set(k, v)

            self.modules[location]["notif_task"] = await self.create_tai_notif_task(
                module
            )

            nconfig = {
                n["name"]: n.get("config", {})
                for n in config.get("network-interface", [])
            }
            netifs = {}
            for index in range(int(await module.get("num-network-interfaces"))):
                attrs = [
                    (k, v if type(v) != bool else "true" if v else "false")
                    for k, v in nconfig.get(str(index), {}).items()
                    if k not in IGNORE_LEAVES
                ]
                logger.debug(f"module({location})/netif({index}) attrs: {attrs}")

                try:
                    netif = module.get_netif(index)
                except:
                    netif = await module.create_netif(index, attrs=attrs)
                else:
                    # reconcile with the running configuration
                    logger.debug(
                        f"module({location})/netif({index}) already exists. updating attributes.."
                    )
                    for k, v in attrs:
                        await netif.set(k, v)

                notif_task = await self.create_tai_notif_task(netif)
                netifs[index] = notif_task

            self.modules[location]["netifs"] = netifs

            num_hostifs = int(await module.get("num-host-interfaces"))

            try:
                rate = await netif.get("line-rate")
                hostifs = self.rate_info[rate]
            except taish.TAIException as e:
                logger.debug(
                    "failed to get netif line-rate. allowing all hostifs to be created"
                )
                hostifs = list(range(num_hostifs))

            hconfig = {
                n["name"]: n.get("config", {}) for n in config.get("host-interface", [])
            }
            hostif_moduless = {}

            for index in range(num_hostifs):
                attrs = [
                    (k, v if type(v) != bool else "true" if v else "false")
                    for k, v in hconfig.get(str(index), {}).items()
                    if k not in IGNORE_LEAVES
                ]
                must_exists = index in hostifs
                logger.debug(
                    f"module({location})/hostif({index}) must_exists: {must_exists}, attrs: {attrs}"
                )
                if must_exists:
                    try:
                        hostif = module.get_hostif(index)
                        logger.debug(
                            f"module({location})/hostif({index}) already exists. updating attributes.."
                        )
                        for k, v in attrs:
                            await hostif.set(k, v)
                    except taish.TAIException:
                        hostif = await module.create_hostif(index, attrs=attrs)

                    notif_task = await self.create_tai_notif_task(hostif)
                    hostif_moduless[index] = notif_task
                else:
                    try:
                        hostif = module.get_hostif(index)
                        logger.debug(
                            f"removing hostif({index}) due to the rate restriction"
                        )
                        await self.taish.remove(hostif.oid)
                    except taish.TAIException:
                        pass

            self.modules[location]["hostifs"] = hostif_moduless

    async def cleanup_piu(self, location):
        m = self.modules[location]
        async with m["lock"]:

            try:
                module = await self.taish.get_module(location)
            except taish.TAIException:
                return

            for task in m["netifs"].values():
                await cancel_notification_task(task)

            for task in m["hostifs"].values():
                await cancel_notification_task(task)

            task = m["notif_task"]
            await cancel_notification_task(task)

            for v in module.hostifs:
                logger.debug("removing hostif oid")
                await self.taish.remove(v.oid)
            for v in module.netifs:
                logger.debug("removing netif oid")
                await self.taish.remove(v.oid)
            logger.debug("removing module oid")
            await self.taish.remove(module.oid)

            logger.info(f"cleanup done for {location}")

        self.modules.pop(location)

    async def piu_notify_event_cb(self, xpath, notif_type, data, timestamp, priv):
        logger.info(f"{xpath=}, {notif_type=}, {data=}, {timestamp=}, {priv=}")
        assert "piu-notify-event" in xpath

        name = data["name"]
        location = await self.name2location(name)
        status = [v for v in data.get("status", [])]
        piu_present = "PRESENT" in status
        cfp_status = data.get("cfp2-presence", "UNPLUGGED")

        if piu_present and cfp_status == "PRESENT":
            config = self.get_running_data(
                f"/goldstone-transponder:modules/module[name='{name}']", {}
            )
            logger.debug(f"running configuration for {location}: {config}")
            try:
                await self.initialize_piu(config, location)
            except Exception as e:
                logger.error(f"failed to initialize PIU: {e}")
                if location in self.modules:
                    self.modules.pop(location)
        else:
            try:
                await self.cleanup_piu(location)
            except Exception as e:
                logger.error(f"failed to cleanup PIU: {e}")

    def location2name(self, loc):
        for info in self.platform_info.values():
            if info["tai"]["module"]["location"] == loc:
                return info["tai"]["module"]["name"]
        return None

    async def name2location(self, name, modules=None):
        if modules == None:
            modules = await self.taish.list()
        info = self.platform_info.get(name)
        if not info:
            logger.warning(f"no info in platform-info about module({name})")
            return None
        v = info["tai"]["module"]["location"]
        if v in modules:
            return v
        logger.warning(f"taish doesn't know module({v}). wrong info in platform_info?")
        return None

    def pre(self, user):
        if self.is_initializing:
            raise LockedError("initializing")

    async def start(self):
        # get hardware configuration from platform datastore ( ONLP south must be running )
        xpath = "/goldstone-platform:components/component[state/type='PIU']"
        components = self.get_operational_data(xpath, [])

        assert len(self.modules) == 0  # this must be empty

        ms = await self.taish.list()
        modules = []
        for c in components:
            location = await self.name2location(c["name"], ms)
            if location == None:
                logger.warning(f"no location found for {c['name']}")
                continue
            try:
                if (
                    "PRESENT" in c["piu"]["state"]["status"]
                    and c["piu"]["state"]["cfp2-presence"] == "PRESENT"
                ):
                    modules.append((c["name"], location))
            except KeyError:
                pass

        # TODO initializing one by one due to a taish_server bug
        # revert this change once the bug is fixed in taish_server.
        for name, location in modules:
            config = self.get_running_data(
                f"/goldstone-transponder:modules/module[name='{name}']", {}
            )
            logger.debug(f"running configuration for {location}: {config}")
            try:
                await self.initialize_piu(config, location)
            except Exception as e:
                logger.error(f"failed to initialize PIU: {e}")

        self.conn.subscribe_notification(
            "goldstone-platform",
            f"/goldstone-platform:piu-notify-event",
            self.piu_notify_event_cb,
        )

        async def ping():
            while True:
                await asyncio.sleep(5)
                try:
                    await asyncio.wait_for(self.taish.list(), timeout=2)
                except Exception as e:
                    logger.error(f"ping failed {e}")
                    return

        async def handle_notification(notification):
            xpath = notification["xpath"]
            eventname = notification["eventname"]
            v = notification["v"]
            obj = notification["obj"]
            msg = notification["msg"]

            try:
                data = self.get_running_data(xpath, include_implicit_defaults=True)
            except NotFoundError as e:
                return

            notify = libyang.xpath_get(data, xpath)
            if not notify:
                return

            keys = []

            for attr in msg.attrs:
                meta = await obj.get_attribute_metadata(attr.attr_id)
                try:
                    xpath = f"/{eventname}/goldstone-transponder:{meta.short_name}"
                    schema = self.conn.find_node(xpath)
                    data = attr_tai2yang(attr.value, meta, schema)
                    keys.append(meta.short_name)
                    if type(data) == list and len(data) == 0:
                        logger.warning(
                            f"empty leaf-list is not supported for notification"
                        )
                        continue
                    v[meta.short_name] = data
                except Error as e:
                    logger.warning(f"{xpath}: {e}")
                    continue

            if len(keys) == 0:
                logger.warning(f"nothing to notify")
                return

            v["keys"] = keys
            self.send_notification(eventname, v)

        async def notif_loop():
            while True:
                notification = await self.notif_q.get()
                await handle_notification(notification)
                self.notif_q.task_done()

        tasks = await super().start()
        self.is_initializing = False

        return tasks + [ping(), notif_loop()]

    async def stop(self):
        logger.info(f"stop server")
        await self.taish.close()
        super().stop()

    async def get_module_from_xpath(self, xpath):
        xpath = list(libyang.xpath_split(xpath))
        logger.debug(f"xpath: {xpath}")
        if (
            len(xpath) < 2
            or xpath[0][0] != "goldstone-transponder"
            or xpath[0][1] != "modules"
            or xpath[1][1] != "module"
        ):
            raise InvalidXPath()

        cond = xpath[1][2]
        if len(cond) != 1 or cond[0][0] != "name":
            # no condition
            return xpath[2:], None

        name = cond[0][1]
        n = await self.name2location(name)
        if not n:
            raise InvalidXPath()

        try:
            module = await self.taish.get_module(n)
        except Exception as e:
            logger.error(str(e))
            raise InvalidXPath()

        module.name = name

        return xpath[2:], module

    async def parse_oper_req(self, xpath):
        """
        Helper method to parse a xpath of an operational datastore pull request
        and return objects and an attribute which is requested

        :arg xpath:
            The request xpath

        :returns (module, intf, item):
            module: TAI module object which is requested
            intf: TAI network-interface or host-interface object which is requested
            item: an attribute which is requested

        :raises InvalidXPath:
            If xpath can't be handled
        :raises EmptyReturn:
            If operational datastore pull request callback doesn't need to return
            anything
        """

        if xpath == "/goldstone-transponder:*":
            return None, None, None

        xpath, module = await self.get_module_from_xpath(xpath)

        if module == None:
            if len(xpath) == 1 and xpath[0][1] == "name":
                return None, None, "name"
            return None, None, None

        if len(xpath) == 0:
            return module, None, None

        get_path = lambda l: self.conn.find_node(
            "".join("/goldstone-transponder:" + v for v in l)
        )

        if xpath[0][1] in ["network-interface", "host-interface"]:

            intf = xpath[0][1]

            if len(xpath[0][2]) == 0:
                return module, intf, "name"

            name = int(xpath[0][2][0][1])

            try:
                if intf == "network-interface":
                    obj = module.get_netif(int(name))
                else:
                    obj = module.get_hostif(int(name))
            except Exception as e:
                logger.error(str(e))
                raise InvalidXPath()

            if len(xpath) == 1:
                return module, obj, None

            if xpath[1][1] == "config":
                raise EmptyReturn()
            elif xpath[1][1] == "state":
                if len(xpath) == 2 or xpath[2][1] == "*":
                    return module, obj, None
                attr = get_path(["modules", "module", intf, "state", xpath[2][1]])
                return module, obj, attr

        elif xpath[0][1] == "config":
            raise EmptyReturn()
        elif xpath[0][1] == "state":
            if len(xpath) == 1 or xpath[1][1] == "*":
                return module, None, None
            attr = get_path(["modules", "module", "state", xpath[1][1]])
            return module, None, attr

        raise InvalidXPath()

    async def oper_cb(self, xpath, priv):
        logger.info(f"oper get callback requested xpath: {xpath}")

        async def get(obj, schema):
            attr, meta = await obj.get(schema.name(), with_metadata=True, json=True)
            return attr_tai2yang(attr, meta, schema)

        async def get_attrs(obj, schema):
            attrs = {}
            for item in schema:
                try:
                    attrs[item.name()] = await get(obj, item)
                except taish.TAIException:
                    pass
            return attrs

        try:
            module, intf, item = await self.parse_oper_req(xpath)
        except InvalidXPath:
            logger.error(f"invalid xpath: {xpath}")
            return {}
        except EmptyReturn:
            return {}

        logger.debug(
            f"result of parse_oper_req: module: {module}, intf: {intf}, item: {item}"
        )

        if item == "name":
            if module == None:
                modules = await self.taish.list()
                modules = (self.location2name(key) for key in modules.keys())
                # modules may include None. filter it with 'if name'
                modules = [
                    {"name": name, "config": {"name": name}} for name in modules if name
                ]
                return {"goldstone-transponder:modules": {"module": modules}}
            elif intf in ["network-interface", "host-interface"]:
                intfs = (
                    module.obj.netifs
                    if intf == "network-interface"
                    else module.obj.hostifs
                )
                intfs = [{"name": str(i)} for i in range(len(intfs))]
                return {
                    "goldstone-transponder:modules": {
                        "module": [{"name": module.name, intf: intfs}]
                    }
                }

        get_path = lambda l: self.conn.find_node(
            "".join("/goldstone-transponder:" + v for v in l)
        )

        module_schema = get_path(["modules", "module", "state"])
        netif_schema = get_path(["modules", "module", "network-interface", "state"])
        hostif_schema = get_path(["modules", "module", "host-interface", "state"])

        if module:
            keys = [await module.get("location")]
        else:
            # if module is None, get all modules information
            modules = await self.taish.list()
            keys = modules.keys()

        r = []
        for location in keys:
            try:
                module = await self.taish.get_module(location)
            except Exception as e:
                logger.warning(f"failed to get module location: {location}. err: {e}")
                continue

            name = self.location2name(location)
            if not name:
                logger.warning(f"failed to get name from location: {location}")
                continue

            data = {
                "name": name,
                "config": {"name": name},
            }

            p = self.platform_info.get(name)
            if p:
                v = {}
                if "component" in p:
                    v["platform"] = {"component": p["component"]["name"]}
                data["component-connection"] = v

            if intf:
                index = await intf.get("index")
                v = {"name": index, "config": {"name": index}}

                if item:
                    attr = await get(intf, item)
                    v["state"] = {item.name(): attr}
                else:
                    if isinstance(intf, taish.NetIf):
                        schema = netif_schema
                    elif isinstance(intf, taish.HostIf):
                        schema = hostif_schema

                    state = await get_attrs(intf, schema)
                    v["state"] = state

                if isinstance(intf, taish.NetIf):
                    data["network-interface"] = [v]
                elif isinstance(intf, taish.HostIf):
                    data["host-interface"] = [v]

            else:

                if item:
                    attr = await get(module, item)
                    data["state"] = {item.name(): attr}
                else:
                    data["state"] = await get_attrs(module, module_schema)

                    netif_states = [
                        await get_attrs(module.get_netif(index), netif_schema)
                        for index in range(len(module.obj.netifs))
                    ]
                    if len(netif_states):
                        data["network-interface"] = [
                            {"name": i, "config": {"name": i}, "state": s}
                            for i, s in enumerate(netif_states)
                        ]

                    hostif_states = [
                        await get_attrs(module.get_hostif(index), hostif_schema)
                        for index in range(len(module.obj.hostifs))
                    ]
                    if len(hostif_states):
                        data["host-interface"] = [
                            {"name": i, "config": {"name": i}, "state": s}
                            for i, s in enumerate(hostif_states)
                        ]

            r.append(data)

        return {"goldstone-transponder:modules": {"module": r}}
