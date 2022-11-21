import logging
import asyncio
import argparse
import signal
import itertools
from .ocnos import OcNOSConnector
from .interfaces import InterfaceServer
from .vlan import VlanServer

import sysrepo
from goldstone.lib.util import start_probe
from goldstone.lib.connector.sysrepo import Connector

logger = logging.getLogger(__name__)


def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        sr_conn = Connector()
        ocnos_conn = OcNOSConnector(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            hostkey_verify=False,
            device_params={"name": "default"},
            look_for_keys=False,
            allow_agent=False,
            schema_dir=f"./{args.host}",
        )
        # create subscription to avoid session drop of netconfd inside OcNOS
        ocnos_conn.conn.create_subscription()

        # VLAN Server must be called first as it creates network instance by default
        # and a VLAN must exist before interface can associate to one
        vlan = VlanServer(sr_conn, ocnos_conn)
        intf = InterfaceServer(sr_conn, ocnos_conn)

        servers = [vlan, intf]

        try:
            tasks = list(
                itertools.chain.from_iterable([await s.start() for s in servers])
            )

            runner = await start_probe("/healthz", "0.0.0.0", 8080)
            tasks.append(stop_event.wait())
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug(f"DONE: {done}, PENDING: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            await runner.cleanup()
            for s in servers:
                s.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--host", type=str)
    parser.add_argument("-p", "--port", type=int, default=830)
    parser.add_argument("--username", type=str)
    parser.add_argument("--password", type=str)
    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format=fmt)
        for noisy in ["hpack"]:
            l = logging.getLogger(noisy)
            l.setLevel(logging.INFO)
            sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
