import sysrepo
import libyang
import logging
import taish
import asyncio
import argparse
import json
import signal
import struct
import base64
import re

class InvalidXPath(Exception):
    pass

class NoOp(Exception):
    pass

logger = logging.getLogger(__name__)

class Server(object):

    def __init__(self, taish_server):
        self.taish = taish.AsyncClient(*taish_server.split(':'))
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

    def stop(self):
        self.sess.stop()
        self.conn.disconnect()
        self.taish.close()

    async def parse_change_req(self, xpath, value):
        """
        Helper method to parse changes and return a TAI object and a dict of
        attributes to be set

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
        # TODO to support event 'change', we need to get the supported attributes of TAI library first
        if event != 'done':
            return
        for change in changes:
            logger.debug(f'change_cb: {change}')
            if any(isinstance(change, cls) for cls in [sysrepo.ChangeCreated, sysrepo.ChangeModified]):
                obj, items = await self.parse_change_req(change.xpath, change.value)

                if obj and items:
                    for k, v in items.items():
                        # check if we can get metadata of this attribute
                        # before doing actual setting
                        try:
                            meta = await obj.get_attribute_metadata(k)
                        except taish.TAIException:
                            continue
                        await obj.set(k, v)


    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.info(f'oper get callback requested xpath: {req_xpath}')

        async def get(obj, item):
            attr, meta = await obj.get(item.name(), with_metadata=True, json=True)
            if meta.usage != '<float>':
                return json.loads(attr)

            # we need special handling for float value since YANG doesn't
            # have float..
            base = item.type().basename()
            if base == 'decimal64':
                return json.loads(attr)
            elif base == 'binary':
                v = base64.b64encode(struct.pack('>f', float(attr)))
                return v.decode()

            logger.warn(f'not supported float value: {attr}')
            raise taish.TAIException()

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
                module = await self.taish.get_module(location)
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
            return {}

        return r

    async def start(self):

        self.sess.switch_datastore('operational')
        modules = await self.taish.list()
        for key, m in modules.items():
            xpath = f"/goldstone-tai:modules/module[name='{key}']"
            self.sess.set_item(f"{xpath}/config/name", key)

            for i in range(len(m.netifs)):
                self.sess.set_item(f"{xpath}/network-interface[name='{i}']/config/name", i)

            for i in range(len(m.hostifs)):
                self.sess.set_item(f"{xpath}/host-interface[name='{i}']/config/name", i)
        self.sess.apply_changes()

        self.sess.switch_datastore('running')
        self.sess.subscribe_module_change('goldstone-tai', None, self.change_cb, asyncio_register=True)
        self.sess.subscribe_oper_data_request('goldstone-tai', '/goldstone-tai:modules/module', self.oper_cb, oper_merge=True, asyncio_register=True)

def main():
    async def _main(taish_server):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server(taish_server)
        try:
            await asyncio.gather(server.start(), stop_event.wait())
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-s', '--taish-server', default='127.0.0.1:50051')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        hpack = logging.getLogger('hpack')
        hpack.setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main(args.taish_server))

if __name__ == '__main__':
    main()
