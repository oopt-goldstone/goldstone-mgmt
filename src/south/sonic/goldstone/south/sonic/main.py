import logging
import asyncio
import argparse
import signal
import itertools
import json
from .interfaces import InterfaceServer
from .vlan import VLANServer
from .portchannel import PortChannelServer
from .ufd import UFDServer
from .sonic import SONiC

from goldstone.lib.util import start_probe
from goldstone.lib.connector.sysrepo import Connector


logger = logging.getLogger(__name__)


def main():
    async def _main(platform_info):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = Connector()
        sonic = SONiC()

        await sonic.init()

        vlan = VLANServer(conn, sonic)
        pc = PortChannelServer(conn, sonic)
        ufd = UFDServer(conn, sonic)
        intf = InterfaceServer(conn, sonic, [vlan, pc, ufd], platform_info)
        servers = [intf, vlan, pc, ufd]

        try:
            tasks = list(
                itertools.chain.from_iterable([await s.start() for s in servers])
            )

            runner = await start_probe("/healthz", "0.0.0.0", 8080)
            tasks.append(stop_event.wait())
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            await runner.cleanup()
            for s in servers:
                s.stop()
            conn.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("platform_file", metavar="platform-file")
    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        for noisy in [
            "hpack",
            "kubernetes.client.rest",
            "kubernetes_asyncio.client.rest",
        ]:
            l = logging.getLogger(noisy)
            l.setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    with open(args.platform_file) as f:
        platform_info = json.loads(f.read())

    asyncio.run(_main(platform_info))


if __name__ == "__main__":
    main()
