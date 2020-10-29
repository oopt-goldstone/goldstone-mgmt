import sysrepo
import logging
import asyncio
import argparse
import signal
import onlp.onlp
from pathlib import Path

libonlp = onlp.onlp.libonlp

logger = logging.getLogger(__name__)

class Server(object):

    def __init__(self):
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()

    def stop(self):
        logger.info(f'stop server')
        self.sess.stop()
        self.conn.disconnect()

    async def change_cb(self, event, req_id, changes, priv):
        logger.info(f"change_cb: {event}, {req_id}, {changes}")
        return

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.info(f'oper get callback requested xpath: {req_xpath}')
        return {}

    # monitor_piu() monitor PIU status periodically and change the operational data store
    # accordingly.
    # TODO currently the detection logic is implemented in monitor_piu(). It is better to delegated this to libonlp.so
    async def monitor_piu(self):
        while True:
            self.sess.switch_datastore('operational')

            pius = Path('/sys/class/piu')

            for piu in pius.iterdir():
                # TODO we set the PIU name as /dev/piu?. This is because libtai-aco.so expects
                # the module location to be the device file of the module.
                # However, this device file name might be awkward for network operators.
                # We may want to think about having more friendly alias for these names.
                name = f'/dev/{piu.name}' 

                xpath = f"/goldstone-onlp:components/component[name='{name}']"
                self.sess.set_item(f"{xpath}/config/name", piu.name)
                self.sess.set_item(f"{xpath}/state/type", "PIU")

                with (piu / 'piu_type').open() as f:
                    piu_type = f.read().strip()
                    logger.info(f'{name} | type: {piu_type}')
                    if piu_type:
                        self.sess.set_item(f"{xpath}/piu/state/status", "PRESENT")
                    else:
                        self.sess.set_item(f"{xpath}/piu/state/status", "UNPLUGGED")

            self.sess.apply_changes()
            await asyncio.sleep(1)

    async def start(self):
        # passing None to the 2nd argument is important to enable layering the running datastore
        # as the bottom layer of the operational datastore
        self.sess.subscribe_module_change('goldstone-onlp', None, self.change_cb, asyncio_register=True)

        # passing oper_merge=True is important to enable pull/push information layering
        self.sess.subscribe_oper_data_request('goldstone-onlp', '/goldstone-onlp:components/component', self.oper_cb, oper_merge=True, asyncio_register=True)

        return [self.monitor_piu()]

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
