import argparse
import asyncio
import itertools
import json
import logging
import signal

from goldstone.lib.connector.sysrepo import Connector
from .device import DeviceServer
from .pm import PMServer

logger = logging.getLogger(__name__)


# TODO consider making this function common as utility.
def load_configuration_file(configuration_file):
    try:
        with open(configuration_file, "r") as f:
            return json.loads(f.read())
    except json.decoder.JSONDecodeError as e:
        logger.error("Invalid configuration file %s.", configuration_file)
        raise e
    except FileNotFoundError as e:
        logger.error("Configuration file %s is not found.", configuration_file)
        raise e


def main():
    async def _main(operational_modes, platform_info):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = Connector()
        servers = [DeviceServer(conn, operational_modes, platform_info), PMServer(conn)]

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
            conn.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "operational_modes_file",
        metavar="operational-modes-file",
        help="path to operational-modes config file",
    )
    parser.add_argument(
        "platform_file", metavar="platform_file", help="path to platform file"
    )
    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    operational_modes = load_configuration_file(args.operational_modes_file)
    platform_info = load_configuration_file(args.platform_file)

    asyncio.run(_main(operational_modes, platform_info))


if __name__ == "__main__":
    main()
