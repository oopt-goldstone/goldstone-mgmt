import logging
import asyncio
import argparse
import signal
import itertools
import sysrepo
import json
from goldstone.lib.core import start_probe
from .interfaces import InterfaceServer
from .gearbox import GearboxServer

logger = logging.getLogger(__name__)


def main():
    async def _main(taish_server, platform_info):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = sysrepo.SysrepoConnection()

        ifserver = InterfaceServer(conn, taish_server, platform_info)
        gb = GearboxServer(conn, ifserver)
        servers = [ifserver, gb]

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
            conn.disconnect()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-s", "--taish-server", default="127.0.0.1:50051")
    parser.add_argument("platform_file", metavar="platform-file")

    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        # hpack debug log is too verbose. change it INFO level
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
    #        sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO)

    with open(args.platform_file) as f:
        platform_info = json.loads(f.read())

    asyncio.run(_main(args.taish_server, platform_info))


if __name__ == "__main__":
    main()
