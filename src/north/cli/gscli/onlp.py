import sys
import os

from .base import Object, InvalidInput, Completer
import json
import libyang as ly
import sysrepo as sr

from prompt_toolkit.completion import WordCompleter

class Component(Object):
    XPATH = '/goldstone-onlp:components/component'

    def __init__(self, conn, parent, type_, name):
        if type_ not in ['fan', 'thermal', 'psu', 'led']:
            raise InvalidInput('invalid component')
        self._type = type_
        self.name = name
        self.session = conn.start_session()
        super(Component, self).__init__(parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.switch_datastore('operational')
            d = self.session.get_data("{}[name='{}']".format(self.XPATH, self.name))
            d = d['components']['component'][self.name][self._type]
            print(d)
            self.session.switch_datastore('running')

    def __str__(self):
        return '{}({})'.format(self._type, self.name)


class FanCompleter(Completer):
    def __init__(self):
        super(FanCompleter, self).__init__(lambda : ['percentage'])

class Fan(Component):

    def __init__(self, *args):
        super(Fan, self).__init__(*args)

        @self.command(FanCompleter())
        def set(args):
            if len(args) != 2:
                raise InvalidInput('usage: set <attribute> <value>[cr]')
            self.session.set_item("{}[name='{}']/fan/config/{}".format(self.XPATH, self.name, args[0]), args[1])
            self.session.apply_changes()
            # raise InvalidInput exception when value is invalid
            return self

class Platform(Object):
    XPATH = '/goldstone-onlp:components'

    def __init__(self, conn, parent):
        self.session = conn.start_session()
        super(Platform, self).__init__(parent)

        self.session.switch_datastore("operational")
        tree = self.session.get_data_ly(self.XPATH)
        self.session.switch_datastore("running")
        self._component_map = json.loads(tree.print_mem("json"))

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            self.session.switch_datastore("operational")
            tree = self.session.get_data_ly(self.XPATH)
            print(tree.print_mem("json"))
            self.session.switch_datastore("running")

        @self.command(WordCompleter(lambda : self._components('fan')))
        def fan(args):
            if len(args) != 1:
                raise InvalidInput('usage: fan <name>')
            return Fan(self.session, self, 'fan', args[0])

        @self.command(WordCompleter(lambda : self._components('thermal')))
        def thermal(args):
            if len(args) != 1:
                raise InvalidInput('usage: thermal <name>')
            return Component(self.session, self, 'thermal', args[0])

        @self.command(WordCompleter(lambda : self._components('psu')))
        def psu(args):
            if len(args) != 1:
                raise InvalidInput('usage: psu <name>')
            return Component(self.session, self, 'psu', args[0])

        @self.command(WordCompleter(lambda : self._components('led')))
        def led(args):
            if len(args) != 1:
                raise InvalidInput('usage: led <name>')
            return Component(self.session, self, 'led', args[0])

    def __str__(self):
        return 'platform'

    def _components(self, type_):
        d = self._component_map
        return [v['name'] for v in d.get('goldstone-onlp:components', {}).get('component', []) if v['state']['type'] == type_.upper()]
