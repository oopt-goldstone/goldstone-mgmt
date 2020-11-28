from .cli import GSObject as Object
from .base import InvalidInput, Completer
from .system import AAA, TACACS
from prompt_toolkit.document import Document
from prompt_toolkit.completion import WordCompleter, Completion, NestedCompleter


class AAA_CLI(Object):
    def __init__(self, conn):
        self.session = conn.start_session()
        self.aaa_sys = AAA(conn)

    def aaa(self, args):
        usage = "usage: aaa authentication login default (group tacacs| local)"

        if len(args) != 4 and len(args) != 5:
            raise InvalidInput(usage)
        if args[0] != "authentication" or args[1] != "login" or args[2] != "default":
            raise InvalidInput(usage)
        if len(args) == 4 and args[3] == "local":
            value = args[3]
        elif len(args) == 5 and args[3] == "group" and args[4] == "tacacs":
            value = args[4]
        else:
            raise InvalidInput(usage)
        self.aaa_sys.set_aaa(value)


class TACACS_CLI(Object):
    def __init__(self, conn):
        self.session = conn.start_session()
        self.tacacs = TACACS(conn)

    def tacacs_server(self, args):
        usage = "usage: tacacs-server host (ipaddress) key (string) [port (portnumber)] [timeout (seconds)]"

        if len(args) != 4 and len(args) != 6 and len(args) != 8:
            raise InvalidInput(usage)
        if args[0] != "host" or args[2] != "key":
            raise InvalidInput(usage)

        ipAddress = args[1]
        key = args[3]
        # TODO extract these default values from the YANG model
        port = 49
        timeout = 300

        if len(args) == 6:
            if args[4] != "port" and args[4] != "timeout":
                raise InvalidInput(usage)

            if args[4] == "port":
                port = args[5]
            elif args[4] == "timeout":
                timeout = args[5]

        elif len(args) == 8:
            if args[4] != "port" or args[6] != "timeout":
                raise InvalidInput(usage)

            port = args[5]
            timeout = args[7]

        self.tacacs.set_tacacs_server(ipAddress, key, port, timeout)
