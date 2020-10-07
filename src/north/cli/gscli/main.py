#!/usr/bin/env python

import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES

import argparse

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer, WordCompleter, NestedCompleter
from prompt_toolkit import patch_stdout

import sys
import os
import subprocess
import logging
import asyncio
import json

from .base import Object, InvalidInput, BreakLoop
from .onlp import Platform
from .tai  import Transponder
from .sonic  import Sonic
from .config import Interface
from .common import sonic_wrap

logger = logging.getLogger(__name__)

stdout = logging.getLogger('stdout')

class Root(Object):
    XPATH = '/'

    def __init__(self, conn):
        self.session = conn.start_session()

        # TODO consider getting notification xpaths from each commands' classmethod
        self.session.subscribe_notification_tree("goldstone-tai", "/goldstone-tai:*", 0, 0, self.notification_cb)

        super(Root, self).__init__(None)

        self.cli_op = sonic_wrap(conn, self)
        #TODO:add timer for inactive user
        self.show_dict = {
                    'interface' : {
                        'brief' : None,
                        'description' : None
                        },
                    'vlan' : {'description'},
                    'date' : None,
                    'datastore' : None
                }

        @self.command()
        def save(line):
            if len(line) != 1:
                raise InvalidInput('usage: save <module name>')
            self.session.switch_datastore('startup')

            try:
                self.session.copy_config('running', line[0])
            except sr.SysrepoError as e:
                print(e)

        @self.command()
        def ping(line):
            try:
                png=' '.join(['ping'] + line)
                subprocess.call(png,shell=True)
            except KeyboardInterrupt:
                print("")
            except :
                print("Unexpected error:",sys.exc_info()[0])

        @self.command()
        def traceroute(line) :
            try:
                png=' '.join(['traceroute'] + line)
                subprocess.call(png,shell=True)
            except :
                print("Unexpected error:",sys.exc_info()[0])

        @self.command()
        def hostname(line) :
            try:
                png=' '.join(['hostname'] + line)
                subprocess.call(png,shell=True)
            except :
                print("Unexpected error:",sys.exc_info()[0])


        @self.command()
        def platform(line):
            if len(line) != 0:
                raise InvalidInput('usage: platform[cr]')
            return Platform(conn, self)

        @self.command()
        def transponder(line):
            if len(line) != 0:
                raise InvalidInput('usage: transponder[cr]')
            return Transponder(conn, self)

        @self.command(WordCompleter(lambda : self.get_ifnames()))
        def interface(line):
            if len(line) != 1:
               raise InvalidInput('usage: interface <ifname>')
            return Interface(conn, self, line[0])



        @self.command(NestedCompleter.from_nested_dict(self.show_dict))
        def show(args):
            if len(args) == 0:
               raise InvalidInput('usage:\n'
                                  ' show interface (brief| description) \n'
                                  ' show vlan (brief) \n'
                                  ' show date \n'
                                  ' show datastore <XPATH> [running|startup|candidate|operational])')

            #datastore command
            if (args[0] == 'datastore') :
                self.datastore(args)

            #date command
            if (args[0] == 'date') :
                self.date(args)

            else:
               self.cli_op.display(args)

    def get_ifnames(self):
        self.path = '/sonic-port:sonic-port/PORT/PORT_LIST'
        self.data_tree = self.session.get_data_ly(self.path)
        self.map = json.loads(self.data_tree.print_mem("json"))['sonic-port:sonic-port']['PORT']['PORT_LIST']
        return [v['ifname'] for v in self.map]

    def date(self, line) :
        subprocess.call("date",shell=True)

    def datastore(self, line):
        dss = list(DATASTORE_VALUES.keys())
        print (line)
        if len(line) < 1:
            raise InvalidInput(f'usage: show datastore <XPATH> [{"|".join(dss)}]')

        if len(line) == 2:
            ds = 'running'
        else:
            ds = line[2]

        if ds not in dss:
            raise InvalidInput(f'unsupported datastore: {ds}. candidates: {dss}')

        self.session.switch_datastore(ds)

        try:
            print(self.session.get_data(line[1]))
        except Exception as e:
            print(e)



    def notification_cb(self, a, b, c, d):
        print(b.print_dict())

    def __str__(self):
        return ''


class GoldstoneShellCompleter(Completer):
    def __init__(self, context):
        self.context = context

    def get_completions(self, document, complete_event):
        return self.context.completion(document, complete_event)


class GoldstoneShell(object):
    def __init__(self, sess=None, default_prompt='> ', prefix=''):
        if sess == None:
            conn = sr.SysrepoConnection()
            sess = conn.start_session()
        self.context = Root(conn)

        self.completer = GoldstoneShellCompleter(self.context)
        self.default_input = ''
        self.default_prompt = default_prompt
        self.prefix = prefix

        #TODO subscribe to global error message bus

    def prompt(self):
        c = self.context
        l = [str(c)]
        while c.parent:
            l.insert(0, str(c.parent))
            c = c.parent
        return self.prefix + ('/'.join(l)[1:] if len(l) > 1 else '') + self.default_prompt

    async def exec(self, cmd: list, no_fail=True):
        ret = await self.context.exec_async(cmd, no_fail=no_fail)
        if ret:
            self.context = ret
            self.completer.context = ret
        self.default_input = ''

    def bindings(self):
        b = KeyBindings()

        @b.add('?')
        def _(event):
            buf = event.current_buffer
            original_text = buf.text
            help_msg = event.app.shell.context.help(buf.text)
            buf.insert_text('?')
            buf.insert_line_below(copy_margin=False)
            buf.insert_text(help_msg)
            event.app.exit('')
            event.app.shell.default_input = original_text

#        @b.add(' ')
#        def _(event):
#            buf = event.current_buffer
#            if len(buf.text.strip()) > 0 and len(buf.text) == buf.cursor_position:
#                candidates = list(event.app.shell.context.completion(buf.document))
#                if len(candidates) == 1:
#                    c = candidates[0]
#                    buf.insert_text(c.text[-c.start_position:])
#                buf.cancel_completion()
#            buf.insert_text(' ')

        return b

async def loop_async(shell):
    session = PromptSession()

    with patch_stdout.patch_stdout():
        while True:
            c = shell.completer
            p = shell.prompt()
            b = shell.bindings()
            session.app.shell = shell
            line = await session.prompt_async(p, completer=c, key_bindings=b, default=shell.default_input)
            if len(line) > 0:
                await shell.exec(line)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-c', '--command-string')
    parser.add_argument('-k', '--keep-open', action='store_true')
    parser.add_argument('-x', '--stdin', action='store_true')
    args = parser.parse_args()

    formatter = logging.Formatter('[%(asctime)s][%(levelname)-5s][%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    if args.verbose:
        console.setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger('sysrepo').setLevel(logging.DEBUG)

    console.setFormatter(formatter)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    shf = logging.Formatter('%(message)s')
    sh.setFormatter(shf)

    stdout.setLevel(logging.DEBUG)
    stdout.addHandler(sh)

    shell = GoldstoneShell()

    async def _main():

        if args.stdin or args.command_string:
            stream = sys.stdin if args.stdin else args.command_string.split(';')
            for line in stream:
                try:
                    await shell.exec(line, no_fail=False)
                except InvalidInput as e:
                    stdout.info('failed to execute: {}'.format(line))
                    stdout.info(e)
                    sys.exit(1)
            if not args.keep_open:
                return

        tasks = [loop_async(shell)]

        try:
            await asyncio.gather(*tasks)
        except BreakLoop:
            return

    asyncio.run(_main())

if __name__ == '__main__':
    main()
