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

#TODO improve taish library
TAI_STATUS_ITEM_ALREADY_EXISTS = -6

class InvalidXPath(Exception):
    pass

class NoOp(Exception):
    pass

logger = logging.getLogger(__name__)

def attr_tai2yang(attr, meta, schema):
    if meta.usage != '<float>':
        return json.loads(attr)

    # we need special handling for float value since YANG doesn't
    # have float..
    base = schema.type().basename()
    if base == 'decimal64':
        return json.loads(attr)
    elif base == 'binary':
        v = base64.b64encode(struct.pack('>f', float(attr)))
        return v.decode()

    logger.warning(f'not supported float value: {attr}')
    raise taish.TAIException()

NETIF_DEFAULT_VALUES = {"modulation-format": "dp-16-qam",
                        "output-power": 1,
                        "voa-rx": 0,
                        "tx-laser-freq": 193500000000000,
                        "tx-dis": False,
                        "differential-encoding": False
                        }
HOSTIF_DEFAULT_VALUES = {"fec-type": "none"}

class Server(object):
    """
    The TAI south server implementation.

    THe TAI south server is responsible for reconciling hardware configuration, sysrepo running configuration and TAI configuration.

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
        self.taish = taish.AsyncClient(*taish_server.split(':'))
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

    def stop(self):
        logger.info(f'stop server')
        self.sess.stop()
        self.conn.disconnect()
        self.taish.close()

    def get_default_value(self, intf, attr):
        try:
            if intf == "network-interface":
                return NETIF_DEFAULT_VALUES[attr]
            elif intf == "host-interface":
                return HOSTIF_DEFAULT_VALUES[attr]
        except KeyError:
            raise sysrepo.SysrepoInvalArgError(f"no default value for {intf} {attr}")
        raise sysrepo.SysrepoInvalArgError(f"no default value for {intf} {attr}")

    async def parse_change_req(self, xpath, value, is_change_deleted):
        """
        Helper method to parse sysrepo ChangeCreated, ChangeModified and ChangeDeleted.
        This returns a TAI object and a dict of attributes to be set

        :arg xpath:
            The xpath for the change
        :arg value:
            The value of the change

        :returns:
            TAI object and a dict of attributes to be set
        :raises InvalidXPath:
            If xpath can't be handled
        """
        prefix = '/goldstone-tai:modules'
        if not xpath.startswith(prefix):
            raise InvalidXPath()
        xpath = xpath[len(prefix):]
        if xpath == '' or xpath == '/module':
            raise InvalidXPath()

        m = re.search(r"/module\[name\=\'(?P<name>.+?)\'\]", xpath)
        if not m:
            raise InvalidXPath()
        name = m.group('name')

        try:
            module = await self.taish.get_module(name)
        except Exception as e:
            logger.error(str(e))
            raise InvalidXPath()

        xpath = xpath[m.end():]

        if xpath.startswith('/config/'):
            xpath = xpath[len('/config/'):]
            return module, {xpath: value}
        elif any((i in xpath) for i in ['/network-interface', '/host-interface']):
            intf = 'network-interface' if '/network-interface' in xpath else 'host-interface'
            m = re.search(r"/{}\[name\=\'(?P<name>.+?)\'\]".format(intf), xpath)
            if not m:
                raise InvalidXPATH()
            name = m.group('name')

            try:
                if intf == 'network-interface':
                    obj = module.get_netif(int(name))
                else:
                    obj = module.get_hostif(int(name))
            except Exception as e:
                logger.error(str(e))
                raise InvalidXPath()

            xpath = xpath[m.end():]
            if xpath.startswith('/config/'):
                xpath = xpath[len('/config/'):]

                if is_change_deleted:
                    value = self.get_default_value(intf, xpath)
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

        if xpath == '/goldstone-tai:*':
            return None, None, None

        prefix = '/goldstone-tai:modules'
        if not xpath.startswith(prefix):
            raise InvalidXPath()
        xpath = xpath[len(prefix):]
        if xpath == '' or xpath == '/module':
            return None, None, None

        m = re.search(r"/module\[name\=\'(?P<name>.+?)\'\]", xpath)
        if not m:
            raise InvalidXPath()
        name = m.group('name')

        try:
            module = await self.taish.get_module(name)
        except Exception as e:
            logger.error(str(e))
            raise InvalidXPath()

        xpath = xpath[m.end():]

        if xpath == '':
            return module, None, None

        ly_ctx = self.sess.get_ly_ctx()
        get_path = lambda l : list(ly_ctx.find_path(''.join('/goldstone-tai:' + v for v in l)))[0]

        if any((i in xpath) for i in ['/network-interface', '/host-interface']):
            intf = 'network-interface' if '/network-interface' in xpath else 'host-interface'

            m = re.search(r"/{}\[name\=\'(?P<name>.+?)\'\]".format(intf), xpath)
            if not m:
                raise InvalidXPATH()
            name = m.group('name')

            try:
                if intf == 'network-interface':
                    obj = module.get_netif(int(name))
                else:
                    obj = module.get_hostif(int(name))
            except Exception as e:
                logger.error(str(e))
                raise InvalidXPath()

            xpath = xpath[m.end():]

            if xpath == '':
                return module, obj, None

            if '/config' in xpath:
                raise NoOp()
            elif '/state' in xpath:
                xpath = xpath[len('/state'):]
                if xpath == '' or xpath == '/*':
                    return module, obj, None
                elif not xpath.startswith('/'):
                    raise InvalidXPath()

                attr = get_path(['modules', 'module', intf, 'state', xpath[1:]])
                return module, obj, attr

        elif '/config' in xpath:
            raise NoOp()
        elif '/state' in xpath:
            xpath = xpath[len('/state'):]
            if xpath == '' or xpath == '/*':
                return module, None, None
            elif not xpath.startswith('/'):
                raise InvalidXPath()

            attr = get_path(['modules', 'module', 'state', xpath[1:]])
            return module, None, attr

        raise InvalidXPath()

    async def change_cb(self, event, req_id, changes, priv):
        if event != 'change':
            return
        for change in changes:
            logger.debug(f'change_cb: {change}')

            if any(isinstance(change, cls) for cls in [sysrepo.ChangeCreated, sysrepo.ChangeModified, sysrepo.ChangeDeleted]):
                is_deleted = isinstance(change, sysrepo.ChangeDeleted)
                value = "" if is_deleted else change.value
                obj, items = await self.parse_change_req(change.xpath, value, is_deleted)

                if obj and items:
                    for k, v in items.items():
                        # check if we can get metadata of this attribute
                        # before doing actual setting
                        try:
                            meta = await obj.get_attribute_metadata(k)
                            if meta.usage == '<bool>':
                                v = 'true' if v else 'false'
                        except taish.TAIException:
                            continue

                        try:
                            await obj.set(k, v)
                        except taish.TAIException as e:
                            raise sysrepo.SysrepoUnsupportedError(str(e))

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.info(f'oper get callback requested xpath: {req_xpath}')

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
            logger.error(f'invalid xpath: {req_xpath}')
            return {}
        except NoOp:
            return {}

        logger.debug(f'result of parse_oper_req: module: {module}, intf: {intf}, item: {item}')

        r = {'goldstone-tai:modules': {'module': []}}

        try:
            ly_ctx = self.sess.get_ly_ctx()
            get_path = lambda l : list(ly_ctx.find_path(''.join('/goldstone-tai:' + v for v in l)))[0]

            module_schema = get_path(['modules', 'module', 'state'])
            netif_schema = get_path(['modules', 'module', 'network-interface', 'state'])
            hostif_schema = get_path(['modules', 'module', 'host-interface', 'state'])

            if module:
                keys = [await module.get('location')]
            else:
                # if module is None, get all modules information
                modules = await self.taish.list()
                keys = modules.keys()

            for location in keys:
                try:
                    module = await self.taish.get_module(location)
                except Exception as e:
                    logger.warning(f'failed to get module location: {location}. err: {e}')
                    continue

                v = {'name': location, 'config': {'name': location}}

                if intf:
                    index = await intf.get('index')
                    vv = {'name': index, 'config': {'name': index}}

                    if item:
                        attr = await get(intf, item)
                        vv['state'] = {item.name(): attr}
                    else:
                        if isinstance(intf, taish.NetIf):
                            schema = netif_schema
                        elif isinstance(intf, taish.HostIf):
                            schema = hostif_schema

                        state = await get_attrs(intf, schema)
                        vv['state'] = state

                    if isinstance(intf, taish.NetIf):
                        v['network-interface'] = [vv]
                    elif isinstance(intf, taish.HostIf):
                        v['host-interface'] = [vv]

                else:

                    if item:
                        attr = await get(module, item)
                        v['state'] = {item.name(): attr}
                    else:
                        v['state'] = await get_attrs(module, module_schema)

                        netif_states = [ await get_attrs(module.get_netif(index), netif_schema) for index in range(len(module.obj.netifs)) ]
                        if len(netif_states):
                            v['network-interface'] = [{'name': i, 'config': {'name': i}, 'state': s} for i, s in enumerate(netif_states)]

                        hostif_states = [ await get_attrs(module.get_hostif(index), hostif_schema) for index in range(len(module.obj.hostifs)) ]
                        if len(hostif_states):
                            v['host-interface'] = [{'name': i, 'config': {'name': i}, 'state': s} for i, s in enumerate(hostif_states)]

                r['goldstone-tai:modules']['module'].append(v)

        except Exception as e:
            logger.error(f'oper get callback failed: {str(e)}')
            traceback.print_exc()
            return {}

        return r

    async def tai_cb(self, obj, attr_meta, msg):
        self.sess.switch_datastore('running')
        ly_ctx = self.sess.get_ly_ctx()

        objname = None
        if isinstance(obj, taish.NetIf):
            objname = 'network-interface'
        elif isinstance(obj, taish.HostIf):
            objname = 'host-interface'
        elif isinstance(obj, taish.Module):
            objname = 'module'

        if not objname:
            logger.error(f'invalid object: {obj}')
            return

        eventname = f'goldstone-tai:{objname}-{attr_meta.short_name}-event'

        v = {}

        for attr in msg.attrs:
            meta = await obj.get_attribute_metadata(attr.attr_id)
            try:
                xpath = f'/{eventname}/goldstone-tai:{meta.short_name}'
                schema = list(ly_ctx.find_path(xpath))[0]
                data = attr_tai2yang(attr.value, meta, schema)
                if type(data) == list and len(data) == 0:
                    logger.warning(f'empty leaf-list is not supported for notification')
                    continue
                v[meta.short_name] = data
            except libyang.util.LibyangError as e:
                logger.warning(f'{xpath}: {e}')
                continue

        if len(v) == 0:
            logger.warning(f'nothing to notify')
            return

        notif = {eventname: v}

        # FIXME adding '/' at the prefix or giving wrong module causes Segmentation fault
        # needs a fix in sysrepo
        n = json.dumps(notif)
        dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
        self.sess.notification_send_ly(dnode)


    async def start(self):
        # get hardware configuration from ONLP datastore ( ONLP south must be running )
        # TODO check if the module is present by a status flag
        # we are abusing the description field to embed TAI module information.
        # the description must be in JSON format
        # TODO hot-plugin is not implemented for now
        # this can be implemented by subscribing to ONLP operational datastore
        # and create/remove TAI modules according to hardware configuration changes
        self.sess.switch_datastore('operational')
        d = self.sess.get_data('/goldstone-onlp:components/component')
        modules = [{'name': c['name'], 'location': json.loads(c['state']['description'])['location']} for c in d['components']['component'] if c['state']['type'] == 'MODULE']

        self.sess.switch_datastore('running')

        with self.sess.lock('goldstone-tai'):

            config = self.sess.get_data('/goldstone-tai:*')
            config = { m['name']: m for m in config.get('modules', {}).get('module', []) }
            logger.debug(f'sysrepo running configuration: {config}')

            for module in modules:
                key = module['location']
                mconfig = config.get(key, {})
                # 'name' is not a valid TAI attribute. we need to exclude it
                # we might want to invent a cleaner way by using an annotation in the YANG model
                attrs = [(k, v) for k, v in mconfig.get('config', {}).items() if k != 'name']
                try:
                    module = await self.taish.create_module(key, attrs=attrs)
                except taish.TAIException as e:
                    if e.code != TAI_STATUS_ITEM_ALREADY_EXISTS:
                        raise e
                    module = await self.taish.get_module(key)
                    # reconcile with the sysrepo configuration
                    logger.debug(f'module({key}) already exists. updating attributes..')
                    for k, v in attrs:
                        await module.set(k, v)

                nconfig = {n['name']: n.get('config', {}) for n in mconfig.get('network-interface', [])}
                for index in range(int(await module.get('num-network-interfaces'))):
                    attrs = [(k, v) for k, v in nconfig.get(str(index), {}).items() if k != 'name']
                    try:
                        netif = await module.create_netif(index)
                        for k, v in attrs:
                            await netif.set(k, v)

                    except taish.TAIException as e:
                        if e.code != TAI_STATUS_ITEM_ALREADY_EXISTS:
                            raise e
                        netif = module.get_netif(index)
                        # reconcile with the sysrepo configuration
                        logger.debug(f'module({key})/netif({index}) already exists. updating attributes..')
                        for k, v in attrs:
                            await netif.set(k, v)

                hconfig = {n['name']: n.get('config', {}) for n in mconfig.get('host-interface', [])}
                for index in range(int(await module.get('num-host-interfaces'))):
                    attrs = [(k, v) for k, v in hconfig.get(str(index), {}).items() if k != 'name']
                    try:
                        hostif = await module.create_hostif(index, attrs=attrs)
                    except taish.TAIException as e:
                        if e.code != TAI_STATUS_ITEM_ALREADY_EXISTS:
                            raise e
                        hostif = module.get_hostif(index)
                        # reconcile with the sysrepo configuration
                        logger.debug(f'module({key})/netif({index}) already exists. updating attributes..')
                        for k, v in attrs:
                            await hostif.set(k, v)

            self.sess.switch_datastore('operational')

            modules = await self.taish.list()
            notifiers = []
            for key, m in modules.items():
                try:
                    module = await self.taish.get_module(key)
                except Exception as e:
                    logger.warning(f'failed to get module location: {key}. err: {e}')
                    continue

                xpath = f"/goldstone-tai:modules/module[name='{key}']"
                self.sess.set_item(f"{xpath}/config/name", key)

                notifiers.append(module.monitor('notify', self.tai_cb, json=True))

                for i in range(len(m.netifs)):
                    self.sess.set_item(f"{xpath}/network-interface[name='{i}']/config/name", i)
                    n = module.get_netif(i)
                    notifiers.append(n.monitor('alarm-notification', self.tai_cb, json=True))

                for i in range(len(m.hostifs)):
                    self.sess.set_item(f"{xpath}/host-interface[name='{i}']/config/name", i)
                    h = module.get_hostif(i)
                    notifiers.append(h.monitor('alarm-notification', self.tai_cb, json=True))

            self.sess.apply_changes()

            self.sess.switch_datastore('running')

            # passing None to the 2nd argument is important to enable layering the running datastore
            # as the bottom layer of the operational datastore
            self.sess.subscribe_module_change('goldstone-tai', None, self.change_cb, asyncio_register=True)

            # passing oper_merge=True is important to enable pull/push information layering
            self.sess.subscribe_oper_data_request('goldstone-tai', '/goldstone-tai:modules/module', self.oper_cb, oper_merge=True, asyncio_register=True)

        async def catch_exception(coroutine):
            try:
                return await coroutine
            except BaseException as e:
                logger.error(e)

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
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-s', '--taish-server', default='127.0.0.1:50051')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        # hpack debug log is too verbose. change it INFO level
        hpack = logging.getLogger('hpack')
        hpack.setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main(args.taish_server))

if __name__ == '__main__':
    main()

