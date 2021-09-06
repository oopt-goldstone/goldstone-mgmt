import sysrepo
import logging
import taish
import asyncio
import argparse
import json
import signal
from aiohttp import web


class Server(object):
    def __init__(self, taish_server):
        self.ataish = taish.AsyncClient(*taish_server.split(":"))
        self.taish = taish.Client(*taish_server.split(":"))
        self.loop = asyncio.get_event_loop()
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.notif_q = asyncio.Queue()

        routes = web.RouteTableDef()

        @routes.get("/healthz")
        async def probe(request):
            return web.Response()

        app = web.Application()
        app.add_routes(routes)

        self.runner = web.AppRunner(app)
        self.event_obj = {}

    async def stop(self):
        logger.info(f"stop server")
        for v in self.event_obj.values():
            v["event"].set()
            await v["task"]

        await self.runner.cleanup()
        self.sess.stop()
        self.conn.disconnect()
        self.ataish.close()
        self.taish.close()

    async def start(self):
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", 8080)
        await site.start()

        async def ping():
            while True:
                await asyncio.sleep(5)
                try:
                    await asyncio.wait_for(self.ataish.list(), timeout=2)
                except Exception as e:
                    logger.error(f"ping failed {e}")
                    return

        return [ping()]


def main():
    async def _main(taish_server):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server(taish_server)

        try:
            tasks = await server.start()
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
            await server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-s", "--taish-server", default="127.0.0.1:50051")

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

    asyncio.run(_main(args.taish_server))


if __name__ == "__main__":
    main()
