import sysrepo
import logging
import taish
import asyncio
import json
import struct
import base64
import libyang
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_STATUS = "down"
IGNORE_LEAVES = ["name", "enable-notify", "enable-alarm-notification"]


class TAIHandler(ChangeHandler):
    async def _init(self, user):
        xpath, module = await self.server.get_module_from_xpath(self.change.xpath)

        if module == None:
            raise sysrepo.SysrepoInvalArgError("Invalid Transponder name")

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
            cap = await self.obj.get_attribute_capability(self.attr_name)
        except taish.TAIException as e:
            raise sysrepo.SysrepoInvalArgError(e.msg)

        logger.info(f"cap: {cap}")

        if self.type == "deleted":
            if cap.default_value == "":  # and is_deleted
                raise sysrepo.SysrepoInvalArgError(
                    f"no default value. cannot remove the configuration"
                )
            if self.attr_name == "admin-status":
                self.value = DEFAULT_ADMIN_STATUS
            else:
                self.value = cap.default_value
        else:
            v = self.change.value
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

            meta = await self.obj.get_attribute_metadata(self.attr_name)
            if meta.usage == "<bool>":
                v = "true" if v else "false"

            self.value = v

    async def apply(self, user):
        if not self.attr_name:
            return
        self.original_value = await self.obj.get(self.attr_name)
        await self.obj.set(self.attr_name, self.value)

    async def revert(self, user):
        logger.warning(
            f"reverting: {self.attr_name} {self.value} => {self.original_value}"
        )
        await self.obj.set(self.attr_name, self.original_value)


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


class InvalidXPath(Exception):
    pass


def attr_tai2yang(attr, meta, schema):
    if meta.usage != "<float>":
        return json.loads(attr)

    # we need special handling for float value since YANG doesn't
    # have float..
    base = schema.type().basename()
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
        for i in platform_info:
            if "component" in i and "tai" in i:
                name = i["tai"]["module"]["name"]
                info[name] = i
        self.platform_info = info
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.notif_q = asyncio.Queue()
        self.event_obj = {}
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
            index = await obj.get("index")
            xpath = f"/goldstone-transponder:modules/module[name='{key}']/{type_}[name='{index}']/config/enable-{attr_meta.short_name}"

        eventname = f"goldstone-transponder:{type_}-{attr_meta.short_name}-event"

        v = {"module-name": key}
        if type_ != "module":
            v["index"] = int(index)

        await self.notif_q.put(
            {"xpath": xpath, "eventname": eventname, "v": v, "obj": obj, "msg": msg}
        )

    async def get_tai_notification_tasks(self, location):
        tasks = []
        finalizers = []

        async def finalizer(obj, attr):
            while True:
                await asyncio.sleep(0.1)
                v = await obj.get(attr)
                logger.debug(v)
                if "(nil)" in v:
                    return

        def add(obj, attr):
            tasks.append(obj.monitor(attr, self.tai_cb, json=True))
            finalizers.append(finalizer(obj, attr))

        try:
            module = await self.taish.get_module(location)
        except Exception as e:
            logger.warning(f"failed to get module location: {location}. err: {e}")
            return

        for attr in ["notify"]:
            try:
                await module.get(attr)
            except taish.TAIException:
                logger.warning(
                    f"monitoring {attr} is not supported for module({location})"
                )
            else:
                add(module, attr)

        for i in range(int(await module.get("num-network-interfaces"))):
            n = module.get_netif(i)
            for attr in ["notify", "alarm-notification"]:
                try:
                    await n.get(attr)
                except taish.TAIException:
                    logger.warning(f"monitoring {attr} is not supported for netif({i})")
                else:
                    add(n, attr)

        for i in range(int(await module.get("num-host-interfaces"))):
            h = module.get_hostif(i)
            for attr in ["notify", "alarm-notification"]:
                try:
                    await h.get(attr)
                except taish.TAIException:
                    logger.warning(
                        f"monitoring {attr} is not supported for hostif({i})"
                    )
                else:
                    add(h, attr)

        return tasks, finalizers

    async def initialize_piu(self, config, location):

        name = self.location2name(location)

        if location not in self.event_obj:
            # this happens if south-onlp is not running when south-tai starts
            # allow this situtation for now. might need reconsideration
            logger.warning(
                f"registering module({name}). somehow failed to do this during initialization"
            )
            self.event_obj[location] = {"lock": asyncio.Lock()}

        async with self.event_obj[location]["lock"]:

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
                # reconcile with the sysrepo configuration
                logger.debug(
                    f"module({location}) already exists. updating attributes.."
                )
                for k, v in attrs:
                    await module.set(k, v)

            nconfig = {
                n["name"]: n.get("config", {})
                for n in config.get("network-interface", [])
            }
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
                    # reconcile with the sysrepo configuration
                    logger.debug(
                        f"module({location})/netif({index}) already exists. updating attributes.."
                    )
                    for k, v in attrs:
                        await netif.set(k, v)

            hconfig = {
                n["name"]: n.get("config", {}) for n in config.get("host-interface", [])
            }
            for index in range(int(await module.get("num-host-interfaces"))):
                attrs = [
                    (k, v if type(v) != bool else "true" if v else "false")
                    for k, v in hconfig.get(str(index), {}).items()
                    if k not in IGNORE_LEAVES
                ]
                logger.debug(f"module({location})/hostif({index}) attrs: {attrs}")
                try:
                    hostif = module.get_hostif(index)
                except:
                    hostif = await module.create_hostif(index, attrs=attrs)
                else:
                    # reconcile with the sysrepo configuration
                    logger.debug(
                        f"module({location})/hostif({index}) already exists. updating attributes.."
                    )
                    for k, v in attrs:
                        await hostif.set(k, v)

            tasks, finalizers = await self.get_tai_notification_tasks(location)
            event = asyncio.Event()
            tasks.append(event.wait())
            task = asyncio.create_task(self.notif_handler(tasks, finalizers))
            self.event_obj[location]["event"] = event
            self.event_obj[location]["task"] = task

    async def cleanup_piu(self, location):
        async with self.event_obj[location]["lock"]:
            self.event_obj[location]["event"].set()
            await self.event_obj[location]["task"]

            m = await self.taish.get_module(location)
            for v in m.obj.hostifs:
                logger.debug("removing hostif oid")
                await self.taish.remove(v.oid)
            for v in m.obj.netifs:
                logger.debug("removing netif oid")
                await self.taish.remove(v.oid)
            logger.debug("removing module oid")
            await self.taish.remove(m.oid)

            logger.info(f"cleanup done for {location}")

    async def notification_cb(self, xpath, notif_type, data, timestamp, priv):
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

    async def notif_handler(self, tasks, finalizers):
        tasks = [asyncio.create_task(t) for t in tasks]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        logger.debug(f"done: {done}, pending: {pending}")
        for task in pending:
            task.cancel()
        logger.debug("waiting for finalizer tasks")
        finalizers = [asyncio.create_task(f) for f in finalizers]
        done, pending = await asyncio.wait(
            finalizers, return_when=asyncio.ALL_COMPLETED, timeout=5
        )
        if len(pending) > 0:
            logger.warning(
                f"finalizer not all tasks finished: done: {done}, pending: {pending}"
            )
        else:
            logger.debug("finalizer done")

    def pre(self, user):
        if self.is_initializing:
            raise sysrepo.SysrepoLockedError("initializing")

    async def start(self):
        # get hardware configuration from platform datastore ( ONLP south must be running )
        xpath = "/goldstone-platform:components/component[state/type='PIU']"
        components = self.get_operational_data(xpath, [])

        assert len(self.event_obj) == 0  # this must be empty

        ms = await self.taish.list()
        modules = []
        for c in components:
            location = await self.name2location(c["name"], ms)
            if location == None:
                logger.warning(f"no location found for {c['name']}")
                continue
            self.event_obj[location] = {"lock": asyncio.Lock()}
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
            await self.initialize_piu(config, location)

        self.sess.subscribe_notification(
            "goldstone-platform",
            f"/goldstone-platform:piu-notify-event",
            self.notification_cb,
            asyncio_register=True,
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

            self.sess.switch_datastore("running")
            ly_ctx = self.sess.get_ly_ctx()

            try:
                data = self.sess.get_data(xpath, include_implicit_defaults=True)
            except sysrepo.errors.SysrepoNotFoundError as e:
                return

            notify = libyang.xpath_get(data, xpath)
            if not notify:
                return

            keys = []

            for attr in msg.attrs:
                meta = await obj.get_attribute_metadata(attr.attr_id)
                try:
                    xpath = f"/{eventname}/goldstone-transponder:{meta.short_name}"
                    schema = list(ly_ctx.find_path(xpath))[0]
                    data = attr_tai2yang(attr.value, meta, schema)
                    keys.append(meta.short_name)
                    if type(data) == list and len(data) == 0:
                        logger.warning(
                            f"empty leaf-list is not supported for notification"
                        )
                        continue
                    v[meta.short_name] = data
                except libyang.util.LibyangError as e:
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
        for v in self.event_obj.values():
            if "event" in v:
                v["event"].set()
                await v["task"]

        self.taish.close()
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
        :raises EmptryReturn:
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

        ly_ctx = self.sess.get_ly_ctx()
        get_path = lambda l: list(
            ly_ctx.find_path("".join("/goldstone-transponder:" + v for v in l))
        )[0]

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
                raise EmptryReturn()
            elif xpath[1][1] == "state":
                if len(xpath) == 2 or xpath[2][1] == "*":
                    return module, obj, None
                attr = get_path(["modules", "module", intf, "state", xpath[2][1]])
                return module, obj, attr

        elif xpath[0][1] == "config":
            raise EmptryReturn()
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
        except EmptryReturn:
            return {}

        logger.debug(
            f"result of parse_oper_req: module: {module}, intf: {intf}, item: {item}"
        )

        if item == "name":
            if module == None:
                modules = await self.taish.list()
                modules = (self.location2name(key) for key in modules.keys())
                modules = [{"name": name, "config": {"name": name}} for name in modules]
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

        ly_ctx = self.sess.get_ly_ctx()
        get_path = lambda l: list(
            ly_ctx.find_path("".join("/goldstone-transponder:" + v for v in l))
        )[0]

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
