import sys
import os

from .base import Object, InvalidInput, Completer
from pyang import repository, context
import json
import yang as ly
import sysrepo as sr
import base64
import struct

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, FuzzyCompleter

TIMEOUT_MS = 10000

class Sonic(Object):
    XPATH = '/sonic-port:sonic-port/PORT/PORT_LIST'

    def __init__(self, session, parent):
        self.session = session
        super(Sonic, self).__init__(parent)

        @self.command()
        def show(args):
            if len(args) != 0:
                raise InvalidInput('usage: show[cr]')
            tree = self.session.get_subtree(self.XPATH)
            data = json.loads(tree.print_mem(ly.LYD_JSON, 0))
            print(data)

    def __str__(self):
        return 'sonic'
