import sysrepo
import logging
import asyncio
import argparse
import signal
import itertools

from .system import SystemServer
from .aaa import AAAServer
from .mgmtif import ManagementInterfaceServer
from .k8s import KubernetesServer

logger = logging.getLogger(__name__)


def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = sysrepo.SysrepoConnection()
        servers = [
            SystemServer(conn),
            AAAServer(conn),
            ManagementInterfaceServer(conn),
            KubernetesServer(conn),
        ]

        try:
            tasks = list(
                itertools.chain.from_iterable([await s.start() for s in servers])
            )
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
            for s in servers:
                s.stop()
            conn.disconnect()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        # pyroute2 debug log is too verbose. change it to INFO level
        logging.getLogger("pyroute2").setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
