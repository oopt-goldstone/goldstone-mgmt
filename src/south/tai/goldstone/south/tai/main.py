import logging
import asyncio
import argparse
import signal
from .transponder import TransponderServer
import sysrepo
from goldstone.lib.core import start_probe

logger = logging.getLogger(__name__)


def main():
    async def _main(taish_server):
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        conn = sysrepo.SysrepoConnection()
        server = TransponderServer(conn, taish_server)

        try:
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
            await runner.cleanup()
            await server.stop()
            conn.disconnect()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-s", "--taish-server", default="127.0.0.1:50051")
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

    asyncio.run(_main(args.taish_server))


if __name__ == "__main__":
    main()
