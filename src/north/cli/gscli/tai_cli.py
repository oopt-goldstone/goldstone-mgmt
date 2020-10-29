from .tai import Transponder
from .base import InvalidInput, Completer
from .cli import GSObject as Object
from prompt_toolkit.completion import WordCompleter, NestedCompleter


class HostIf_CLI(Object):
    def __init__(self, transponder, conn, hostif_id):
        self.session = conn.start_session()
        self.tai = Transponder(conn)
        self.tai_hostif = self.tai.hostif
        super(HostIf_CLI, self).__init__(transponder)
        self.transponder_name = transponder.transponder_name
        self.hostif_id = hostif_id
        self.fec_alg = ["fc", "rs"]
        self.command_list = ["fec-type"]

        @self.command(WordCompleter(self.fec_alg), name="fec-type")
        def fec_type(args):
            if len(args) != 1:
                raise InvalidInput("usage: fec-type <alg>")
            self.tai_hostif.set_fec_type(self.transponder_name, self.hostif_id, args[0])

        @self.command(WordCompleter(self.command_list))
        def no(args):
            if len(args) != 1:
                raise InvalidInput("usage: no fec-type")
            if args[0] != "fec-type":
                raise InvalidInput("usage: no fec-type")
            self.tai_hostif.no(self.transponder_name, self.hostif_id, args[0])

        @self.command(transponder.parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return transponder.show(args)
            self.tai_hostif.show(self.transponder_name, self.hostif_id)

    def __str__(self):
        return "hostif({})".format(self.hostif_id)


class NetIf_CLI(Object):
    def __init__(self, transponder, conn, netif_id):
        self.session = conn.start_session()
        self.tai = Transponder(conn)
        self.tai_netif = self.tai.netif
        self.transponder_name = transponder.transponder_name
        self.netif_id = netif_id
        super(NetIf_CLI, self).__init__(transponder)
        self.mod_format = [
            "bpsk",
            "dp-bpsk",
            "qpsk",
            "dp-qpsk",
            "8-qam",
            "dp-8-qam",
            "16-qam",
            "dp-16-qam",
            "32-qam",
            "dp-32-qam",
            "64-qam",
            "dp-64-qam",
        ]
        self.command_list = [
            "tx-dis",
            "modulation-format",
            "output-power",
            "tx-laser-freq",
            "voa-rx",
            "differential-encoding",
        ]

        @self.command(name="output-power")
        def output_power(args):
            if len(args) != 1:
                raise InvalidInput("usage: output-power <value_in_db>")
            self.tai_netif.set_output_power(
                self.transponder_name, self.netif_id, args[0]
            )

        @self.command(WordCompleter(self.mod_format), name="modulation-format")
        def modulation_format(args):
            if len(args) != 1:
                raise InvalidInput("usage: modulation-format <type>")
            self.tai_netif.set_modulation_format(
                self.transponder_name, self.netif_id, args[0]
            )

        @self.command(name="tx-laser-freq")
        def tx_laser_freq(args):
            if len(args) != 1:
                raise InvalidInput("usage: tx-laser-freq <Hz>")
            self.tai_netif.set_tx_laser_freq(
                self.transponder_name, self.netif_id, args[0]
            )

        @self.command(name="tx-dis")
        def tx_dis(args):
            if len(args) != 0:
                raise InvalidInput("usage: tx-dis")
            self.tai_netif.set_tx_dis(self.transponder_name, self.netif_id, "true")

        @self.command(name="differential-encoding")
        def differential_encoding(args):
            if len(args) != 0:
                raise InvalidInput("usage: differential-encoding")
            self.tai_netif.set_differential_encoding(
                self.transponder_name, self.netif_id, "true"
            )

        @self.command(name="voa-rx")
        def voa_rx(args):
            if len(args) != 1:
                raise InvalidInput("usage: voa-rx <value>")
            self.tai_netif.set_voa_rx(self.transponder_name, self.netif_id, args[0])

        @self.command(WordCompleter(self.command_list))
        def no(args):
            if len(args) != 1:
                raise InvalidInput("usage: no <operation>")
            if args[0] in self.command_list:
                self.tai_netif.set_no_command(
                    self.transponder_name, self.netif_id, args[0]
                )
            else:
                self.no_usage()

        @self.command(transponder.parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                # raise InvalidInput ('usage: show')
                return transponder.show(args)
            self.tai_netif.show(self.transponder_name, self.netif_id)

    def no_usage(self):
        print(f'usage: no [{"|".join(self.command_list)}]')

    def __str__(self):
        return "netif({})".format(self.netif_id)


class Transponder_CLI(Object):
    def __init__(self, conn, parent, transponder_name):
        self.session = conn.start_session()
        self.tai_transponder = Transponder(conn)
        self.transponder_name = transponder_name
        super(Transponder_CLI, self).__init__(parent)
        self.command_list = ["shutdown"]

        @self.command(WordCompleter(self.command_list))
        def no(args):
            if len(args) != 1:
                raise InvalidInput("usage: shutdown")
            if args[0] != "shutdown":
                raise InvalidInput("usage: no shutdown")
            self.tai_transponder.set_admin_status(self.transponder_name, "up")

        @self.command(
            WordCompleter(
                lambda: self.tai_transponder._components(
                    self.transponder_name, "network-interface"
                )
            )
        )
        def netif(args):
            if len(args) != 1:
                raise InvalidInput("usage: netif <name>")
            elif args[0] in self.tai_transponder._components(
                self.transponder_name, "network-interface"
            ):
                return NetIf_CLI(self, conn, args[0])
            else:
                print(f"There is no network interface with id {args[0]}")
                return

        @self.command(
            WordCompleter(
                lambda: self.tai_transponder._components(
                    self.transponder_name, "host-interface"
                )
            )
        )
        def hostif(args):
            if len(args) != 1:
                raise InvalidInput("usage: hostif <name>")
            elif args[0] in self.tai_transponder._components(
                self.transponder_name, "host-interface"
            ):
                return HostIf_CLI(self, conn, args[0])
            else:
                print(f"There is no host interface with id {args[0]}")
                return

        @self.command()
        def shutdown(args):
            if len(args) != 0:
                raise InvalidInput("usage: shutdown")
            self.tai_transponder.set_admin_status(self.transponder_name, "down")

        @self.command(parent.get_completer("show"))
        def show(args):
            if len(args) != 0:
                return parent.show(args)
            self.tai_transponder.show_transponder(self.transponder_name)

    def __str__(self):
        return "transponder({})".format(self.transponder_name)
