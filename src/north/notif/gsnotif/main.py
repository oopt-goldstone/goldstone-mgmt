import libyang
import logging
import asyncio
import argparse
import json
import signal
import struct
import base64
import os
from aiohttp import web
from libyang import SNode

from goldstone.lib.util import start_probe
from goldstone.lib.connector.sysrepo import Connector

logger = logging.getLogger(__name__)


class Server(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.conn = Connector()
        self.sess = self.conn.new_session()

        routes = web.RouteTableDef()

    async def stop(self):
        logger.info(f"stop server")
        self.sess.stop()

    async def monitor_notif(self):
        while True:
            await asyncio.sleep(1)

    def notification_cb(self, notification):
        logger.info(f"{notification=}")

    async def start(self):

        logger.info("**********Inside Start**********")

        self.sess.subscribe_notifications(self.notification_cb)

        return [self.monitor_notif()]


def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server()

        try:
            runner = None
            tasks = await server.start()
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
            await server.stop()
            conn.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    fmt = "%(levelname)s %(module)s %(funcName)s l.%(lineno)d | %(message)s"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        hpack = logging.getLogger("hpack")
        hpack.setLevel(logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
