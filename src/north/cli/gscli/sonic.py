import sys
import os

from .base import Object, InvalidInput, Completer
from pyang import repository, context
import json
import sysrepo as sr

from prompt_toolkit.completion import WordCompleter

TIMEOUT_MS = 10000


class vlan_list(Object):
    XPATH = '/sonic-vlan:sonic-vlan/VLAN/VLAN_LIST'

    def xpath_vlan_list(self):
        return "{}[name='{}']".format(self.XPATH, 'Vlan' + self.vlan_name)

    def __init__(self, session, parent, *args):
        self.session = session
        self.vlan_name = args[0]
        self._get_hook = {}
        self._set_hook = {}
        self.session.switch_datastore('operational')
        self.vlan_tree = self.session.get_data("{}".format(self.xpath_vlan_list()))
        self._set_map = {"members":"string"}
        try:
            self._map = list(self.vlan_tree['sonic-vlan']['VLAN']['VLAN_LIST'])[0]

        except KeyError as error:
            print("Vlan list configurations are empty")

        self.session.switch_datastore('running')
        super(vlan_list, self).__init__(parent)
       
 
        @self.command(WordCompleter(self._components()))
        def get(args):
            if len(args) != 1:
                raise InvalidInput('usage: get <parameter_name>')
            self.session.switch_datastore('operational')
            try:
                items = self.session.get_items("{}/{}".format(self.xpath_vlan_list(), args[0]))
                for item in items:
                    if args[0] in self._get_hook:
                        print(self._get_hook[args[0]](item))
                    else:
                        print(item.value)
            except sr.errors.SysrepoCallbackFailedError as e:
                print(e)
            self.session.switch_datastore('running')



        @self.command(WordCompleter(self._set_components()))
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <parameter_name> <value>')
            if args[0] in self._set_hook:
                v = self._set_hook[args[0]](args[1])
            else:
                v = args[1]
            if (args[0] == 'vlanid' or args[0] =='name'):
                raise InvalidInput('Cannot change the property')
            else:
                self.session.set_item('{}/{}'.format(self.xpath_vlan_list(), args[0]), v)
                self.session.apply_changes()



    def _components(self):
        d = self._map
        return [v for v in d]

    def _set_components(self):
        d = self._set_map
        return [v for v in d]

    def __str__(self):
        return 'vlan({})'.format(self.vlan_name)




class Ifname(Object):
    XPATH = '/sonic-port:sonic-port/PORT/PORT_LIST'

    def xpath(self):
        return "{}[ifname='{}']".format(self.XPATH, self.ifname)

    def __init__(self, session, parent, *args):
        self.session = session
        self.ifname = args[0]
        self._get_hook = {}
        self._set_hook = {}
        self.session.switch_datastore('operational')
        self.iftree = self.session.get_data(self.xpath())
        self._set_map = {"alias":"string", "speed":"integer" , "mtu":"integer", "admin_status":"up/down" }
        try:
            self._map = list((self.iftree)['sonic-port']['PORT']['PORT_LIST'])[0]
        except KeyError as error:
            print("sonic-port interfaces  are not configured")
        self.session.switch_datastore('running')
        super(Ifname, self).__init__(parent)


        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            print (json.dumps(self.iftree))

        @self.command(WordCompleter(self._components()))
        def get(args):
            if len(args) != 1:
                raise InvalidInput('usage: get <parameter_name>')
            self.session.switch_datastore('operational')
            try:
                items = self.session.get_items("{}/{}".format(self.xpath(), args[0]))
                for item in items:
                    if args[0] in self._get_hook:
                        print(self._get_hook[args[0]](item))
                    else:
                        print(item.value)
            except sr.errors.SysrepoCallbackFailedError as e:
                print(e)
            self.session.switch_datastore('running')

        @self.command(WordCompleter(self._set_components()))
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <parameter_name> <value>')
            if args[0] in self._set_hook:
                v = self._set_hook[args[0]](args[1])
            else:
                v = args[1]
            try:
                self.session.set_item('{}/{}'.format(self.xpath(), args[0]), v)
                self.session.apply_changes()
            except sr.errors.SysrepoCallbackFailedError as e:
                print(e)


    def _ifnames(self):
        d = self._ifname_map
        return [v['ifname'] for v in d.get('sonic-port:sonic-port/PORT/PORT_LIST', {}).get('ifname', {})]

    def __str__(self):
        return 'ifname({})'.format(self.ifname)

    def _components(self):
        d = self._map
        return [v for v in d]

    def _set_components(self):
        d = self._set_map
        return [v for v in d]



class Vlan(Object):

    XPATH = '/sonic-vlan:sonic-vlan/VLAN'


    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.session.switch_datastore('operational')
        self.tree = self.session.get_data("{}".format(self.XPATH), 0, TIMEOUT_MS)
        try:
            self._vlan_map = list(self.tree['sonic-vlan']['VLAN']['VLAN_LIST'])
        except KeyError as error:
            print("No VLAN configurations created")
        self.session.switch_datastore('running')
        super(Vlan, self).__init__(parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            print (json.dumps(self.tree))
        
        @self.command(WordCompleter(lambda : self._vlan_components()))
        def vlan(args):
            if len(args) != 1:
               raise InvalidInput('usage: vlan <vlan_id>')
            return vlan_list(self.session, self, args[0])

    def _vlan_components(self):
        d = self._vlan_map
        return [str(v['vlanid']) for v in d]
    
    def __str__(self):
        return 'vlan'




class Interface(Object):

    XPATH = '/sonic-interface:sonic-interface/INTERFACE'


    def xpath_iplist(self):
        return "{}/INTERFACE_IPADDR_LIST".format(self.XPATH)

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        super(Interface, self).__init__(parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.switch_datastore('operational')
            try:
                tree = self.session.get_data_ly(self.xpath_iplist())
                print (tree.print_mem("json"))
            except sr.errors.SysrepoNotFoundError as e:
                print(e)
            except KeyError as error:
                print("Sonic-interface ip addr list not configured")
            self.session.switch_datastore('running')
        

        @self.command()
        def get(args):
            if len(args) != 1:
                raise InvalidInput('usage: get <portname> <ip_prefix>')
            self.session.switch_datastore('operational')
            try:
                items = self.session.get_items("{}=[portname= '{}'],[ipprefix='{}']".format(self.xpath_iplist(), args[0]))
                for item in items:
                    if args[0] in self._get_hook:
                        print(self._get_hook[args[0]](item))
                    else:
                        print(item.value)
            except sr.errors.SysrepoCallbackFailedError as e:
                print(e)
            self.session.switch_datastore('running')

        @self.command()
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <parameter_name> <value>')
            if args[0] in self._set_hook:
                v = self._set_hook[args[0]](args[1])
            else:
                v = args[1]
            self.session.set_item("{}=[ipprefix='{}']".format(self.xpath_iplist(), args[0], v))
            self.session.apply_changes()

    def __str__(self):
        return 'interface'





class Port(Object):

    XPATH = '/sonic-port:sonic-port/PORT/PORT_LIST'

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        self.session.switch_datastore('operational')
        try:
            self.tree = self.session.get_data(self.XPATH)
            self._ifname_map = list(self.tree['sonic-port']['PORT']['PORT_LIST'])
        except KeyError as error:
            print("Port list is not configured")
        except sr.errors.SysrepoNotFoundError as error:
            print("sonic-mgmt is down")
        self.session.switch_datastore('running')
        super(Port, self).__init__(parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            print (json.dumps(self.tree))

        @self.command(WordCompleter(lambda : self._ifname_components()))
        def ifname(args):
            if len(args) != 1:
                raise InvalidInput('usage: ifname <interface_name>')
            return Ifname(self.session, self, args[0])

    def __str__(self):
        return 'port'

    def _ifname_components(self):
        d = self._ifname_map
        return [v['ifname'] for v in d]



class Sonic(Object):
    XPATH = '/sonic-port:sonic-port/PORT/PORT_LIST'

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        super(Sonic, self).__init__(parent)

        @self.command()
        def interface(args):
            if len(args) != 0:
               raise InvalidInput('usage: interface[cr] ')
            return Interface(conn, self)


        @self.command()
        def port(args):
            if len(args) != 0:
               raise InvalidInput('usage: port[cr] ')
            return Port(conn, self)


        @self.command()
        def vlan(args):
            if len(args) != 0:
               raise InvalidInput('usage: vlan[cr] ')
            return Vlan(conn, self)

    def __str__(self):
        return 'sonic'

