import sysrepo
import logging
import taish
import asyncio
import argparse
import json
import signal
import struct
import base64
import re
import libyang
import traceback
from goldstone.lib.core import ServerBase, ChangeHandler, NoOp

logger = logging.getLogger(__name__)

# TODO improve taish library
TAI_STATUS_ITEM_ALREADY_EXISTS = -6
TAI_STATUS_FAILURE = -1

DEFAULT_ADMIN_STATUS = "down"
IGNORE_LEAVES = ["name", "enable-notify", "enable-alarm-notification"]


class TAIHandler(ChangeHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        xpath, module = self.server.get_module_from_xpath(change.xpath)

        if module == None:
            raise sysrepo.SysrepoInvalArgError("Invalid Transponder name")

        self.module = module
        self.xpath = xpath
        self.attr_name = None
        self.obj = None
        self.value = None
        self.original_value = None

    def validate(self, user):
        if not self.attr_name:
            return
        try:
            cap = self.obj.get_attribute_capability(self.attr_name)
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

            meta = self.obj.get_attribute_metadata(self.attr_name)
            if meta.usage == "<bool>":
                v = "true" if v else "false"

            self.value = v

    def apply(self, user):
        if not self.attr_name:
            return
        self.original_value = self.obj.get(self.attr_name)
        self.obj.set(self.attr_name, self.value)

    def revert(self, user):
        logger.warn(
            f"reverting: {self.attr_name} {self.value} => {self.original_value}"
        )
        self.obj.set(self.attr_name, self.original_value)


class ModuleHandler(TAIHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
        self.obj = self.module

        logger.info(f"obj: {self.obj}, xpath: {self.xpath}")

        if len(self.xpath) != 2 or self.xpath[1][1] in IGNORE_LEAVES:
            self.attr_name = None
        else:
            self.attr_name = self.xpath[1][1]


class InterfaceHandler(TAIHandler):
    def __init__(self, server, change):
        super().__init__(server, change)
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


class EmptyReturn(Exception):
    pass


def location2name(loc):
    if loc.isdigit():
        return f"piu{loc}"  # 1 => piu1
    return loc.split("/")[-1]  # /dev/piu1 => piu1


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
    def __init__(self, conn, taish_server):
        super().__init__(conn, "goldstone-transponder")
        self.ataish = taish.AsyncClient(*taish_server.split(":"))
        self.taish = taish.Client(*taish_server.split(":"))
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
            key = location2name(location)
            xpath = f"/goldstone-transponder:modules/module[name='{key}']/config/enable-{attr_meta.short_name}"
        else:
            type_ = type_ + "-interface"
            m_oid = obj.obj.module_oid
            modules = await self.ataish.list()

            for location, m in modules.items():
                if m.oid == m_oid:
                    module_location = location
                    break
            else:
                logger.error(f"module not found: {m_oid}")
                return

            key = location2name(module_location)
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
            module = await self.ataish.get_module(location)
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

        name = location2name(location)

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
            module = await self.ataish.get_module(location)
        except:
            module = await self.ataish.create_module(location, attrs=attrs)
        else:
            # reconcile with the sysrepo configuration
            logger.debug(f"module({location}) already exists. updating attributes..")
            for k, v in attrs:
                await module.set(k, v)

        nconfig = {
            n["name"]: n.get("config", {}) for n in config.get("network-interface", [])
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
        self.event_obj[location] = {"event": event, "task": task}

    async def cleanup_piu(self, location):
        self.event_obj[location]["event"].set()
        await self.event_obj[location]["task"]

        m = await self.ataish.get_module(location)
        for v in m.obj.hostifs:
            logger.debug("removing hostif oid")
            await self.ataish.remove(v.oid)
        for v in m.obj.netifs:
            logger.debug("removing netif oid")
            await self.ataish.remove(v.oid)
        logger.debug("removing module oid")
        await self.ataish.remove(m.oid)

    async def notification_cb(self, notif_name, value, timestamp, priv):
        logger.info(value.print_dict())
        data = value.print_dict()
        assert "piu-notify-event" in data

        data = data["piu-notify-event"]
        name = data["name"]
        location = self.name2location(name)
        status = [v for v in data.get("status", [])]
        piu_present = "PRESENT" in status
        cfp_status = data.get("cfp2-presence", "UNPLUGGED")

        if piu_present and cfp_status == "PRESENT":
            self.sess.switch_datastore("running")
            config = self.get_running_data(
                f"/goldstone-transponder:modules/module[name='{name}']", {}
            )
            logger.debug(f"running configuration for {location}: {config}")
            try:
                await self.initialize_piu(config, location)
            except Exception as e:
                logger.info(f"failed to initialize PIU: {e}")
        else:
            try:
                await self.cleanup_piu(location)
            except Exception as e:
                logger.info(f"failed to cleanup PIU: {e}")

    def name2location(self, name, modules=None):
        if modules == None:
            modules = self.taish.list()
        v = f"/dev/{name}"
        if v in modules:
            return v  # piu1 => /dev/piu1
        v = name.replace("piu", "")
        if v in modules:
            return v  # piu1 => 1
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

        ms = self.taish.list()
        try:
            modules = list(
                filter(
                    None,
                    (
                        self.name2location(c["name"], ms)
                        for c in components
                        if c["piu"]["state"]["status"] == ["PRESENT"]
                    ),
                )
            )
        except KeyError:
            modules = []

        self.sess.switch_datastore("running")
        config = self.sess.get_data("/goldstone-transponder:*")
        config = {m["name"]: m for m in config.get("modules", {}).get("module", [])}
        logger.debug(f"sysrepo running configuration: {config}")

        # TODO initializing one by one due to a taish_server bug
        # revert this change once the bug is fixed in taish_server.
        for m in modules:
            await self.initialize_piu(config, m)

        self.sess.subscribe_notification_tree(
            "goldstone-platform",
            f"/goldstone-platform:piu-notify-event",
            0,
            0,
            self.notification_cb,
            asyncio_register=True,
        )

        async def ping():
            while True:
                await asyncio.sleep(5)
                try:
                    await asyncio.wait_for(self.ataish.list(), timeout=2)
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
            v["event"].set()
            await v["task"]

        self.ataish.close()
        self.taish.close()
        super().stop()

    def get_module_from_xpath(self, xpath):
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

        try:
            module = self.taish.get_module(self.name2location(name))
        except Exception as e:
            logger.error(str(e))
            raise InvalidXPath()

        module.name = name

        return xpath[2:], module

    def parse_oper_req(self, xpath):
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

        xpath, module = self.get_module_from_xpath(xpath)

        if module == None:
            if len(xpath) == 1 and xpath[0][1] == "name":
                return None, None, "name"
            raise InvalidXPath()

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

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.info(f"oper get callback requested xpath: {req_xpath}")

        def get(obj, schema):
            attr, meta = obj.get(schema.name(), with_metadata=True, json=True)
            return attr_tai2yang(attr, meta, schema)

        def get_attrs(obj, schema):
            attrs = {}
            for item in schema:
                try:
                    attrs[item.name()] = get(obj, item)
                except taish.TAIException:
                    pass
            return attrs

        try:
            module, intf, item = self.parse_oper_req(req_xpath)
        except InvalidXPath:
            logger.error(f"invalid xpath: {req_xpath}")
            return {}
        except EmptryReturn:
            return {}

        logger.debug(
            f"result of parse_oper_req: module: {module}, intf: {intf}, item: {item}"
        )

        r = {"goldstone-transponder:modules": {"module": []}}

        if item == "name":
            if module == None:
                modules = await self.ataish.list()
                modules = (location2name(key) for key in modules.keys())
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

        try:
            ly_ctx = self.sess.get_ly_ctx()
            get_path = lambda l: list(
                ly_ctx.find_path("".join("/goldstone-transponder:" + v for v in l))
            )[0]

            module_schema = get_path(["modules", "module", "state"])
            netif_schema = get_path(["modules", "module", "network-interface", "state"])
            hostif_schema = get_path(["modules", "module", "host-interface", "state"])

            if module:
                keys = [module.get("location")]
            else:
                # if module is None, get all modules information
                modules = self.taish.list()
                keys = modules.keys()

            for location in keys:
                try:
                    module = self.taish.get_module(location)
                except Exception as e:
                    logger.warning(
                        f"failed to get module location: {location}. err: {e}"
                    )
                    continue

                name = location2name(location)
                v = {
                    "name": name,
                    "config": {"name": name},
                }

                if intf:
                    index = intf.get("index")
                    vv = {"name": index, "config": {"name": index}}

                    if item:
                        attr = get(intf, item)
                        vv["state"] = {item.name(): attr}
                    else:
                        if isinstance(intf, taish.NetIf):
                            schema = netif_schema
                        elif isinstance(intf, taish.HostIf):
                            schema = hostif_schema

                        state = get_attrs(intf, schema)
                        vv["state"] = state

                    if isinstance(intf, taish.NetIf):
                        v["network-interface"] = [vv]
                    elif isinstance(intf, taish.HostIf):
                        v["host-interface"] = [vv]

                else:

                    if item:
                        attr = get(module, item)
                        v["state"] = {item.name(): attr}
                    else:
                        v["state"] = get_attrs(module, module_schema)

                        netif_states = [
                            get_attrs(module.get_netif(index), netif_schema)
                            for index in range(len(module.obj.netifs))
                        ]
                        if len(netif_states):
                            v["network-interface"] = [
                                {"name": i, "config": {"name": i}, "state": s}
                                for i, s in enumerate(netif_states)
                            ]

                        hostif_states = [
                            get_attrs(module.get_hostif(index), hostif_schema)
                            for index in range(len(module.obj.hostifs))
                        ]
                        if len(hostif_states):
                            v["host-interface"] = [
                                {"name": i, "config": {"name": i}, "state": s}
                                for i, s in enumerate(hostif_states)
                            ]

                r["goldstone-transponder:modules"]["module"].append(v)

        except Exception as e:
            logger.error(f"oper get callback failed: {str(e)}")
            traceback.print_exc()
            return {}

        return r
