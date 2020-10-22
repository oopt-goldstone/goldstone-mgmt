import sysrepo
import logging
import asyncio
import argparse
import signal
import onlp.onlp

libonlp = onlp.onlp_init()

logger = logging.getLogger(__name__)

class Server(object):

    def __init__(self):
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

    def stop(self):
        logger.info(f'stop server')
        self.sess.stop()
        self.conn.disconnect()

    async def start(self):
        libonlp.onlp_platform_dump(libonlp.aim_pvs_stdout, (onlp.onlp.ONLP_OID_DUMP.RECURSE | onlp.onlp.ONLP_OID_DUMP.EVEN_IF_ABSENT))

        return []

def main():
    async def _main():
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)

        server = Server()

        try:
            tasks = await server.start()
            [ asyncio.create_task(t) for t in tasks ]
            await stop_event.wait()
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main())

if __name__ == '__main__':
    main()
