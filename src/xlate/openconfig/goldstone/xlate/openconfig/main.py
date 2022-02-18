"""main() function for OpenConfig translators."""

import logging
import asyncio
import argparse
import signal
import itertools
import json
from goldstone.lib.util import start_probe, call
from goldstone.lib.connector.sysrepo import Connector
from .interfaces import InterfaceServer
from .platform import PlatformServer
from .terminal_device import TerminalDeviceServer


logger = logging.getLogger(__name__)


def load_operational_modes(operational_modes_file):
    try:
        with open(operational_modes_file, "r", encoding="utf-8") as f:
            operational_modes = json.loads(f.read())
    except json.decoder.JSONDecodeError as e:
        logger.error("Invalid configuration file %s.", operational_modes_file)
        raise e
    except FileNotFoundError as e:
        logger.error("Configuration file %s is not found.", operational_modes_file)
        raise e
    parsed_operational_modes = {}
    for mode in operational_modes:
        try:
            parsed_operational_modes[int(mode["openconfig"]["mode-id"])] = {
                "vendor-id": mode["openconfig"]["vendor-id"],
                "description": mode["description"],
                "line-rate": mode["line-rate"],
                "modulation-format": mode["modulation-format"],
                "fec-type": mode["fec-type"],
                "client-signal-mapping-type": mode["client-signal-mapping-type"],
            }
        except (KeyError, TypeError):
            pass
    return parsed_operational_modes


def main():
    async def _main(operational_modes):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = Connector()
        ifserver = InterfaceServer(conn)
        pfserver = PlatformServer(conn, operational_modes)
        tdserver = TerminalDeviceServer(conn, operational_modes)
        servers = [ifserver, pfserver, tdserver]

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
            if runner:
                await runner.cleanup()
            for s in servers:
                await call(s.stop)
            conn.disconnect()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable detailed output"
    )
    parser.add_argument(
        "operational_modes_file",
        metavar="operational-modes-file",
        help="path to operational-modes config file",
    )
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

    operational_modes = load_operational_modes(args.operational_modes_file)

    asyncio.run(_main(operational_modes))


if __name__ == "__main__":
    main()
