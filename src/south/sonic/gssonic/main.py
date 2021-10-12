import sysrepo
import logging
import asyncio
import argparse
import signal
from aiohttp import web
import itertools
from .sonic import SONiC
from .interfaces import InterfaceServer
from .vlan import VLANServer
from .portchannel import PortChannelServer
from .ufd import UFDServer

logger = logging.getLogger(__name__)


async def start_probe(route, host, port):
    routes = web.RouteTableDef()

    @routes.get(route)
    async def probe(request):
        return web.Response()

    app = web.Application()
    app.add_routes(routes)

    runner = web.AppRunner(app)

    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    return runner


def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = sysrepo.SysrepoConnection()
        sonic = SONiC()

        vlan = VLANServer(conn, sonic)
        pc = PortChannelServer(conn, sonic)
        ufd = UFDServer(conn, sonic)
        intf = InterfaceServer(conn, sonic, [vlan, pc, ufd])
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
            conn.disconnect()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
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
    #        sysrepo.configure_logging(py_logging=True)
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
