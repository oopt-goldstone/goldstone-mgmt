import sys
import os

from .base import InvalidInput, Completer
from .cli import GSObject as Object
import libyang as ly
import sysrepo as sr

from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, NestedCompleter
from .sonic import Sonic


class Interface_CLI(Object):
    def close(self):
        self.session.stop()

    def __init__(self, conn, parent, ifname):
        self.session = conn.start_session()
        self.ifname = ifname
        super(Interface_CLI, self).__init__(parent)
        self.sonic = Sonic(conn)
        self.no_dict = {"shutdown": None, "speed": None, "mtu": None}

        @self.command(NestedCompleter.from_nested_dict(self.no_dict))
        def no(args):
            if len(args) < 1:
                raise InvalidInput("usage: no shutdown")
            if args[0] == "shutdown":
                self.sonic.port.set_admin_status(self.ifname, "up")
            elif args[0] == "speed":
                self.sonic.port.set_speed(self.ifname, "100000")
            elif args[0] == "mtu":
                self.sonic.port.set_mtu(self.ifname, 9100)
            else:
                self.no_usage()

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            self.sonic.port.set_admin_status(self.ifname, "down")

        @self.command()
        def speed(args):
            if len(args) != 1:
                raise InvalidInput(
                    "usage: speed 1000|10000|25000|40000|50000|100000|400000"
                )
            speed = args[0]
            if speed.isdigit():
                self.sonic.port.set_speed(self.ifname, speed)
            else:
                raise InvalidInput("Argument must be numbers and not letters")

        @self.command()
        def mtu(args):
            if len(args) != 1:
                raise InvalidInput("usage: mtu <range 1312..9216>")
            if args[0].isdigit():
                mtu = int(args[0])
                self.sonic.port.set_mtu(self.ifname, mtu)
            else:
                raise InvalidInput("Argument must be numbers and not letters")

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            # raise InvalidInput ('usage: show')
            self.sonic.port.show(self.ifname)

    def no_usage(self):
        no_keys = list(self.no_dict.keys())
        print(f'usage: no [{"|".join(no_keys)}]')

    def __str__(self):
        return "interface({})".format(self.ifname)
