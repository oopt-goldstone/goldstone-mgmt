"""
SNMP subagent entrypoint.
"""

import asyncio
import functools
import os
import signal
import argparse
import logging

import ax_interface
from .mibs.ietf import rfc1213

DEFAULT_UPDATE_FREQUENCY = 5

logger = logging.getLogger(__name__)


class GoldstoneMIB(
    rfc1213.InterfacesMIB,
    rfc1213.SystemMIB,
):
    """
    If Goldstone was to create custom MIBEntries, they may be specified here.
    """


def main():
    async def _main(host, update_freq):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        agent = ax_interface.Agent(GoldstoneMIB, update_freq, loop, host)

        # start the agent, wait for it to come back.
        logger.info("Starting agent with PID: {}".format(os.getpid()))

        try:
            asyncio.create_task(agent.run_in_event_loop())
            await stop_event.wait()
        finally:
            await agent.shutdown()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--update-frequency", default=DEFAULT_UPDATE_FREQUENCY, type=int
    )
    parser.add_argument("--host", default="tcp:localhost:3161")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main(args.host, args.update_frequency))


if __name__ == "__main__":
    main()
