import sys
import os

from .base import Object, InvalidInput, Completer
from pyang import repository, context
import json
import libyang as ly
import sysrepo as sr
import base64
import struct

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, NestedCompleter
from .common import sonic_wrap


class Interface(Object):
    XPATH = "/"

    def close(self):
        self.session.stop()

    def xpath(self):
        self.path = "/sonic-port:sonic-port/PORT/PORT_LIST"
        return "{}[ifname='{}']".format(self.path, self.ifname)

    def __init__(self, conn, parent, ifname):
        self.session = conn.start_session()
        self.ifname = ifname
        super(Interface, self).__init__(parent)
        self.cli_op = sonic_wrap(conn, self)
        self.no_dict = {"shutdown": None}

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(args):
            if len(args) < 1:
                raise InvalidInput("usage: no shutdown")
            xpath = self.xpath()
            self.cli_op.set_admin_status(xpath, "up")

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            xpath = self.xpath()
            self.cli_op.set_admin_status(xpath, "down")

    def __str__(self):
        return "interface({})".format(self.ifname)
