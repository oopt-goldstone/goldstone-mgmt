#!/usr/bin/env python

import sysrepo as sr

import argparse

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer

import sys
import os
import logging
import asyncio

from .base import Object, InvalidInput, BreakLoop
from .onlp import Platform
from .tai  import Transponder

logger = logging.getLogger(__name__)

stdout = logging.getLogger('stdout')

class Root(Object):
    XPATH = '/'

    def __init__(self, sess):
        self.session = sess
        super(Root, self).__init__(None)

        @self.command()
        def platform(line):
            if len(line) != 0:
                raise InvalidInput('usage: platform[cr]')
            return Platform(self.session, self)

        @self.command()
        def transponder(line):
            if len(line) != 0:
                raise InvalidInput('usage: transponder[cr]')
            return Transponder(self.session, self)

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
            conn = sr.Connection()
            sess = sr.Session(conn)
        self.context = Root(sess)

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

async def loop_async():
    session = PromptSession()
    shell = GoldstoneShell()

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
    args = parser.parse_args()

    formatter = logging.Formatter('[%(asctime)s][%(levelname)-5s][%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    if args.verbose:
        console.setLevel(logging.DEBUG)
        log = sr.Logs()
        log.set_stderr(sr.SR_LL_DBG)

    console.setFormatter(formatter)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    shf = logging.Formatter('%(message)s')
    sh.setFormatter(shf)

    stdout.setLevel(logging.DEBUG)
    stdout.addHandler(sh)

    async def _main():
        tasks = [loop_async()]

        try:
            await asyncio.gather(*tasks)
        except BreakLoop:
            return

    asyncio.run(_main())

if __name__ == '__main__':
    main()
