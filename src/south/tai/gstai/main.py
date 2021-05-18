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
from aiohttp import web

# TODO improve taish library
TAI_STATUS_ITEM_ALREADY_EXISTS = -6
TAI_STATUS_FAILURE = -1


class InvalidXPath(Exception):
    pass


class NoOp(Exception):
    pass


logger = logging.getLogger(__name__)


def location2name(loc):
    return loc.split("/")[-1]


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


MODULE_DEFAULT_VALUES = {"admin-status": "up", "enable-notify": False}

NETIF_DEFAULT_VALUES = {
    "tx-dis": False,
    "output-power": 0,
    "tx-laser-freq": 193500000000000,
    "tx-fine-tune-laser-freq": 0,
    "modulation-format": "dp-16-qam",
    "differential-encoding": False,
    "pulse-shaping-tx": False,
    "pulse-shaping-rx": False,
    "pulse-shaping-tx-beta": 0,
    "pulse-shaping-rx-beta": 0,
    "voa-rx": 0,
    "loopback-type": "none",
    "prbs-type": "none",
    "ch1-freq": 191150000000000,
    "enable-notify": False,
    "enable-alarm-notification": False,
    "losi": False,
    "ber-period": 10000000,
    "hd-fec-type": "hgfec",
    "sd-fec-type": "on",
    "mld": "4-lanes",
}

HOSTIF_DEFAULT_VALUES = {
    "signal-rate": "100-gbe",
    "fec-type": "none",
    "loopback-type": "none",
    "enable-notify": False,
    "enable-alarm-notification": False,
}


class Server(object):
    """
    The TAI south server implementation.

    The TAI south server is responsible for reconciling hardware configuration, sysrepo running configuration and TAI configuration.

    The main YANG model to interact is 'goldstone-tai'.
    The TAI south server doesn't modify the running configuration of goldstone-tai.
    The running configuration is always given by user and it might be empty if a user doesn't give any configuration.
    When the user doesn't give any configuration for the TAI module, TAI south server creates the module with the default configuration.
    To disable the module, the user needs to explicitly set the module admin-status to 'down'

    1. start-up process

    In the beginning of the start-up process, the TAI south server gets the hardware configuration from the ONLP operational configuration.
    In order to get this information, the ONLP south server must be always running.
    If ONLP south server is not running, TAI south server fails to get the hardware configuraion and exit. The restarting of the server is k8s's responsibility.

    After getting the hardware configuration, the TAI south server checks if taish-server has created all the TAI objects corresponds to the hardware.
    If not, it will create the TAI objects.

    When creating the TAI objects, the TAI south server uses sysrepo TAI running configuration if any. If the user doesn't give any configuration, TAI library's default values will be used.
    If taish-server has already created TAI objects, the TAI south server checks if those TAI objects have the same configuration as the sysrepo running configuration.
    This reconcilation process only runs in the start-up process.
    Since the configuration between taish-server and sysrepo running configuration will become inconsistent, it is not recommended to change the TAI configuration directly by the taish command
    when the TAI south server is running.

    2. operational datastore

    The sysrepo TAI operational datastore is represented to the north daemons by layering three layers.

    The bottom layer is running datastore. The second layer is the operational information which is **pushed** to the datastore.
    The top layer is the operational information which is **pulled** from the taish-server.

    To enable layering the running datastore, we need to subscribe to the whole goldstone-tai. For this reason, we are passing
    'None' to the 2nd argument of subscribe_module_change().

    To enable layering the push and pull information, oper_merge=True option is passed to subscribe_oper_data_request().

    The TAI south server doesn't modify the running datastore as mentioned earlier.
    Basic information such as created modules, netifs and hostifs' name will be **pushed** in the start-up process.

    The pull information is collected in Server::oper_cb().
    This operation takes time since it actually invokes hardware access to get the latest information.
    To mitigate the time as much as possible, we don't want to retrieve unnecessary information.

    For example, if the north daemon is requesting the current modulation formation by the XPATH
    "/goldstone-tai:modules/module[name='/dev/piu1']/network-interface[name='0']/state/modulation-format",
    we don't need to retrieve other attributes of the netif or the attributes of the parent module.

    Even if we return unnecessary information, sysrepo drops them before returning to the caller based on the
    requested XPATH.

    In Server::oper_cb(), Server::parse_oper_req() is called to limit the call to taish-server by examining the
    requested XPATH.
    """

    def __init__(self, taish_server):
        self.taish = taish.AsyncClient(*taish_server.split(":"))
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

        routes = web.RouteTableDef()

        @routes.get("/healthz")
        async def probe(request):
            return web.Response()

        app = web.Application()
        app.add_routes(routes)

        self.runner = web.AppRunner(app)

    async def stop(self):
        logger.info(f"stop server")
        await self.runner.cleanup()
        self.sess.stop()
        self.conn.disconnect()
        self.taish.close()

    def get_default_value(self, obj, attr):
        try:
            if obj == "network-interface":
                return NETIF_DEFAULT_VALUES[attr]
            elif obj == "host-interface":
                return HOSTIF_DEFAULT_VALUES[attr]
            elif obj == "module":
                return MODULE_DEFAULT_VALUES[attr]
        except KeyError:
            pass
        logger.warning(f"no default value for {obj} {attr}")
        return None

    async def _get_module_from_xpath(self, xpath):
        prefix = "/goldstone-tai:modules"
        if not xpath.startswith(prefix):
            raise InvalidXPath()
        xpath = xpath[len(prefix) :]
        if xpath == "" or xpath == "/module":
            return xpath, None

        m = re.search(r"/module\[name\=\'(?P<name>.+?)\'\]", xpath)
        if not m:
            raise InvalidXPath()
        name = m.group("name")

        try:
            self.sess.switch_datastore("operational")
            d = self.sess.get_data(
                f"/goldstone-tai:modules/module[name='{name}']/state/location",
                no_subs=True,
            )
            location = d["modules"]["module"][name]["state"]["location"]
            module = await self.taish.get_module(location)
        except Exception as e:
            logger.error(str(e))
            raise InvalidXPath()

        return xpath[m.end() :], module

    async def parse_change_req(self, xpath, value):
        """
        Helper method to parse sysrepo ChangeCreated, ChangeModified and ChangeDeleted.
        This returns a TAI object and a dict of attributes to be set

        :arg xpath:
            The xpath for the change
        :arg value:
            The value of the change. None if the xpath leaf needs is deleted

        :returns:
            TAI object and a dict of attributes to be set
        :raises InvalidXPath:
            If xpath can't be handled
        """

        xpath, module = await self._get_module_from_xpath(xpath)

        if xpath.startswith("/config/"):
            xpath = xpath[len("/config/") :]
            if value == None:
                value = self.get_default_value("module", xpath)
                if value == None:
                    return None, None

            return module, {xpath: value}
        elif any((i in xpath) for i in ["/network-interface", "/host-interface"]):
            intf = (
                "network-interface"
                if "/network-interface" in xpath
                else "host-interface"
            )
            m = re.search(r"/{}\[name\=\'(?P<name>.+?)\'\]".format(intf), xpath)
            if not m:
                raise InvalidXPATH()
            name = m.group("name")

            try:
                if intf == "network-interface":
                    obj = module.get_netif(int(name))
                else:
                    obj = module.get_hostif(int(name))
            except Exception as e:
                logger.error(str(e))
                raise InvalidXPath()

            xpath = xpath[m.end() :]
            if xpath.startswith("/config/"):
                xpath = xpath[len("/config/") :]

                if value == None:
                    value = self.get_default_value(intf, xpath)
                    if value == None:
                        return None, None

                return obj, {xpath: value}

        return None, None

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
        :raises NoOp:
            If operational datastore pull request callback doesn't need to return
            anything
        """

        if xpath == "/goldstone-tai:*":
            return None, None, None

        xpath, module = await self._get_module_from_xpath(xpath)

        if xpath == "":
            return module, None, None

        ly_ctx = self.sess.get_ly_ctx()
        get_path = lambda l: list(
            ly_ctx.find_path("".join("/goldstone-tai:" + v for v in l))
        )[0]

        if any((i in xpath) for i in ["/network-interface", "/host-interface"]):
            intf = (
                "network-interface"
                if "/network-interface" in xpath
                else "host-interface"
            )

            m = re.search(r"/{}\[name\=\'(?P<name>.+?)\'\]".format(intf), xpath)
            if not m:
                raise InvalidXPATH()
            name = m.group("name")

            try:
                if intf == "network-interface":
                    obj = module.get_netif(int(name))
                else:
                    obj = module.get_hostif(int(name))
            except Exception as e:
                logger.error(str(e))
                raise InvalidXPath()

            xpath = xpath[m.end() :]

            if xpath == "":
                return module, obj, None

            if "/config" in xpath:
                raise NoOp()
            elif "/state" in xpath:
                xpath = xpath[len("/state") :]
                if xpath == "" or xpath == "/*":
                    return module, obj, None
                elif not xpath.startswith("/"):
                    raise InvalidXPath()

                attr = get_path(["modules", "module", intf, "state", xpath[1:]])
                return module, obj, attr

        elif "/config" in xpath:
            raise NoOp()
        elif "/state" in xpath:
            xpath = xpath[len("/state") :]
            if xpath == "" or xpath == "/*":
                return module, None, None
            elif not xpath.startswith("/"):
                raise InvalidXPath()

            attr = get_path(["modules", "module", "state", xpath[1:]])
            return module, None, attr

        raise InvalidXPath()

    async def change_cb(self, event, req_id, changes, priv):
        if event == "done":
            # TODO can be smarter. detect when the container is removed
            if any(isinstance(change, sysrepo.ChangeDeleted) for change in changes):
                await self.update_operds()
            return

        if event != "change":
            return

        for change in changes:
            logger.debug(f"change_cb: {change}")

            if any(
                isinstance(change, cls)
                for cls in [
                    sysrepo.ChangeCreated,
                    sysrepo.ChangeModified,
                    sysrepo.ChangeDeleted,
                ]
            ):
                is_deleted = isinstance(change, sysrepo.ChangeDeleted)
                value = None if is_deleted else change.value
                obj, items = await self.parse_change_req(change.xpath, value)

                if obj and items:
                    for k, v in items.items():
                        # check if we can get metadata of this attribute
                        # before doing actual setting
                        try:
                            meta = await obj.get_attribute_metadata(k)
                            if meta.usage == "<bool>":
                                v = "true" if v else "false"
                        except taish.TAIException:
                            continue

                        try:
                            await obj.set(k, v)
                        except taish.TAIException as e:
                            raise sysrepo.SysrepoUnsupportedError(str(e))

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.info(f"oper get callback requested xpath: {req_xpath}")

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
            module, intf, item = await self.parse_oper_req(req_xpath)
        except InvalidXPath:
            logger.error(f"invalid xpath: {req_xpath}")
            return {}
        except NoOp:
            return {}

        logger.debug(
            f"result of parse_oper_req: module: {module}, intf: {intf}, item: {item}"
        )

        r = {"goldstone-tai:modules": {"module": []}}

        try:
            ly_ctx = self.sess.get_ly_ctx()
            get_path = lambda l: list(
                ly_ctx.find_path("".join("/goldstone-tai:" + v for v in l))
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

            for location in keys:
                try:
                    module = await self.taish.get_module(location)
                except Exception as e:
                    logger.warning(
                        f"failed to get module location: {location}. err: {e}"
                    )
                    continue

                v = {
                    "name": location2name(location),
                    "config": {"name": location2name(location)},
                }

                if intf:
                    index = await intf.get("index")
                    vv = {"name": index, "config": {"name": index}}

                    if item:
                        attr = await get(intf, item)
                        vv["state"] = {item.name(): attr}
                    else:
                        if isinstance(intf, taish.NetIf):
                            schema = netif_schema
                        elif isinstance(intf, taish.HostIf):
                            schema = hostif_schema

                        state = await get_attrs(intf, schema)
                        vv["state"] = state

                    if isinstance(intf, taish.NetIf):
                        v["network-interface"] = [vv]
                    elif isinstance(intf, taish.HostIf):
                        v["host-interface"] = [vv]

                else:

                    if item:
                        attr = await get(module, item)
                        v["state"] = {item.name(): attr}
                    else:
                        v["state"] = await get_attrs(module, module_schema)

                        netif_states = [
                            await get_attrs(module.get_netif(index), netif_schema)
                            for index in range(len(module.obj.netifs))
                        ]
                        if len(netif_states):
                            v["network-interface"] = [
                                {"name": i, "config": {"name": i}, "state": s}
                                for i, s in enumerate(netif_states)
                            ]

                        hostif_states = [
                            await get_attrs(module.get_hostif(index), hostif_schema)
                            for index in range(len(module.obj.hostifs))
                        ]
                        if len(hostif_states):
                            v["host-interface"] = [
                                {"name": i, "config": {"name": i}, "state": s}
                                for i, s in enumerate(hostif_states)
                            ]

                r["goldstone-tai:modules"]["module"].append(v)

        except Exception as e:
            logger.error(f"oper get callback failed: {str(e)}")
            traceback.print_exc()
            return {}

        return r

    async def tai_cb(self, obj, attr_meta, msg):
        self.sess.switch_datastore("running")
        ly_ctx = self.sess.get_ly_ctx()

        objname = None
        if isinstance(obj, taish.NetIf):
            objname = "network-interface"
        elif isinstance(obj, taish.HostIf):
            objname = "host-interface"
        elif isinstance(obj, taish.Module):
            objname = "module"

        if not objname:
            logger.error(f"invalid object: {obj}")
            return

        eventname = f"goldstone-tai:{objname}-{attr_meta.short_name}-event"

        v = {}

        for attr in msg.attrs:
            meta = await obj.get_attribute_metadata(attr.attr_id)
            try:
                xpath = f"/{eventname}/goldstone-tai:{meta.short_name}"
                schema = list(ly_ctx.find_path(xpath))[0]
                data = attr_tai2yang(attr.value, meta, schema)
                if type(data) == list and len(data) == 0:
                    logger.warning(f"empty leaf-list is not supported for notification")
                    continue
                v[meta.short_name] = data
            except libyang.util.LibyangError as e:
                logger.warning(f"{xpath}: {e}")
                continue

        if len(v) == 0:
            logger.warning(f"nothing to notify")
            return

        notif = {eventname: v}

        # FIXME adding '/' at the prefix or giving wrong module causes Segmentation fault
        # needs a fix in sysrepo
        n = json.dumps(notif)
        dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
        self.sess.notification_send_ly(dnode)

    async def update_operds(self, return_notifiers=False):

        logger.info("updating operds")

        with self.conn.start_session() as sess:

            sess.switch_datastore("operational")

            modules = await self.taish.list()
            notifiers = []
            for location, m in modules.items():
                try:
                    module = await self.taish.get_module(location)
                except Exception as e:
                    logger.warning(
                        f"failed to get module location: {location}. err: {e}"
                    )
                    continue

                key = location2name(location)

                xpath = f"/goldstone-tai:modules/module[name='{key}']"
                sess.set_item(f"{xpath}/config/name", key)
                sess.set_item(f"{xpath}/state/location", location)

                for i in range(len(m.netifs)):
                    sess.set_item(
                        f"{xpath}/network-interface[name='{i}']/config/name", i
                    )
                    if return_notifiers:
                        n = module.get_netif(i)
                        notifiers.append(
                            n.monitor("alarm-notification", self.tai_cb, json=True)
                        )

                for i in range(len(m.hostifs)):
                    sess.set_item(f"{xpath}/host-interface[name='{i}']/config/name", i)
                    if return_notifiers:
                        h = module.get_hostif(i)
                        notifiers.append(
                            h.monitor("alarm-notification", self.tai_cb, json=True)
                        )

            sess.apply_changes()

        if return_notifiers:
            return notifiers

    async def start(self):
        # get hardware configuration from ONLP datastore ( ONLP south must be running )
        # TODO hot-plugin is not implemented for now
        # this can be implemented by subscribing to ONLP operational datastore
        # and create/remove TAI modules according to hardware configuration changes
        self.sess.switch_datastore("operational")
        d = self.sess.get_data("/goldstone-onlp:components/component", no_subs=True)
        modules = [
            {"name": c["name"], "location": c["name"]}
            for c in d["components"]["component"]
            if c["state"]["type"] == "PIU"
            and c["piu"]["state"]["status"] == ["PRESENT"]
        ]
        self.sess.switch_datastore("running")

        with self.sess.lock("goldstone-tai"):

            config = self.sess.get_data("/goldstone-tai:*")
            config = {m["name"]: m for m in config.get("modules", {}).get("module", [])}
            logger.debug(f"sysrepo running configuration: {config}")

            for module in modules:
                key = module["location"]
                mconfig = config.get(key, {})
                # 'name' is not a valid TAI attribute. we need to exclude it
                # we might want to invent a cleaner way by using an annotation in the YANG model
                attrs = [
                    (k, v) for k, v in mconfig.get("config", {}).items() if k != "name"
                ]
                try:
                    module = await self.taish.create_module(key, attrs=attrs)
                except taish.TAIException as e:
                    if e.code != TAI_STATUS_ITEM_ALREADY_EXISTS:
                        if e.code == TAI_STATUS_FAILURE:
                            logger.debug(f"Failed to intialize module {key}")
                            continue
                        raise e
                    module = await self.taish.get_module(key)
                    # reconcile with the sysrepo configuration
                    logger.debug(f"module({key}) already exists. updating attributes..")
                    for k, v in attrs:
                        await module.set(k, v)

                nconfig = {
                    n["name"]: n.get("config", {})
                    for n in mconfig.get("network-interface", [])
                }
                for index in range(int(await module.get("num-network-interfaces"))):
                    attrs = [
                        (k, v)
                        for k, v in nconfig.get(str(index), {}).items()
                        if k != "name"
                    ]
                    try:
                        netif = await module.create_netif(index)
                        for k, v in attrs:
                            try:
                                meta = await netif.get_attribute_metadata(k)
                                if meta.usage == "<bool>":
                                    v = "true" if v else "false"
                            except taish.TAIException:
                                continue
                            await netif.set(k, v)

                    except taish.TAIException as e:
                        if e.code != TAI_STATUS_ITEM_ALREADY_EXISTS:
                            raise e
                        netif = module.get_netif(index)
                        # reconcile with the sysrepo configuration
                        logger.debug(
                            f"module({key})/netif({index}) already exists. updating attributes.."
                        )
                        for k, v in attrs:
                            try:
                                meta = await netif.get_attribute_metadata(k)
                                if meta.usage == "<bool>":
                                    v = "true" if v else "false"
                            except taish.TAIException:
                                continue
                            ret = await netif.set(k, v)
                            logger.debug(
                                f"module({key})/netif({index}) {k}:{v}, ret: {ret}"
                            )

                hconfig = {
                    n["name"]: n.get("config", {})
                    for n in mconfig.get("host-interface", [])
                }
                for index in range(int(await module.get("num-host-interfaces"))):
                    attrs = [
                        (k, v)
                        for k, v in hconfig.get(str(index), {}).items()
                        if k != "name"
                    ]
                    try:
                        hostif = await module.create_hostif(index, attrs=attrs)
                    except taish.TAIException as e:
                        if e.code != TAI_STATUS_ITEM_ALREADY_EXISTS:
                            raise e
                        hostif = module.get_hostif(index)
                        # reconcile with the sysrepo configuration
                        logger.debug(
                            f"module({key})/hostif({index}) already exists. updating attributes.."
                        )
                        for k, v in attrs:
                            await hostif.set(k, v)

            notifiers = await self.update_operds(return_notifiers=True)

            self.sess.switch_datastore("running")

            # passing None to the 2nd argument is important to enable layering the running datastore
            # as the bottom layer of the operational datastore
            self.sess.subscribe_module_change(
                "goldstone-tai", None, self.change_cb, asyncio_register=True
            )

            # passing oper_merge=True is important to enable pull/push information layering
            self.sess.subscribe_oper_data_request(
                "goldstone-tai",
                "/goldstone-tai:modules/module",
                self.oper_cb,
                oper_merge=True,
                asyncio_register=True,
            )

        async def catch_exception(coroutine):
            try:
                return await coroutine
            except BaseException as e:
                logger.error(e)

        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()

        return [catch_exception(n) for n in notifiers]


def main():
    async def _main(taish_server):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server(taish_server)

        try:
            tasks = await server.start()
            tasks.append(stop_event.wait())
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-s", "--taish-server", default="127.0.0.1:50051")

    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        # hpack debug log is too verbose. change it INFO level
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
        sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main(args.taish_server))


if __name__ == "__main__":
    main()
