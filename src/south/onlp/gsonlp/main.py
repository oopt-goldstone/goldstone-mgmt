import sysrepo
import logging
import asyncio
import argparse
import signal
import ctypes
import onlp.onlp
from pathlib import Path

libonlp = onlp.onlp.libonlp

logger = logging.getLogger(__name__)

STATUS_UNPLUGGED      = 0
STATUS_ACO_PRESENT    = (1 << 0)
STATUS_DCO_PRESENT    = (1 << 1)
STATUS_QSFP_PRESENT   = (1 << 2)
CFP2_STATUS_UNPLUGGED = (1 << 3)
CFP2_STATUS_PRESENT   = (1 << 4)

class Server(object):

    def __init__(self):
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.onlp_oids_dict = {
                               onlp.onlp.ONLP_OID_TYPE.SYS : [],
                               onlp.onlp.ONLP_OID_TYPE.THERMAL : [],
                               onlp.onlp.ONLP_OID_TYPE.FAN : [],
                               onlp.onlp.ONLP_OID_TYPE.PSU : [],
                               onlp.onlp.ONLP_OID_TYPE.LED : [],
                               #Module here is PIU
                               onlp.onlp.ONLP_OID_TYPE.MODULE : []
                              }
        #This list would be indexed by piuId
        self.onlp_piu_status = []

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
    async def monitor_piu(self):
        while True:
            self.sess.switch_datastore('operational')

            for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
                # TODO we set the PIU name as /dev/piu?. This is because libtai-aco.so expects
                # the module location to be the device file of the module.
                # However, this device file name might be awkward for network operators.
                # We may want to think about having more friendly alias for these names.
                piuId = oid & 0xFFFFFF

                name = f'/dev/piu{piuId}'

                xpath = f"/goldstone-onlp:components/component[name='{name}']"

                sts = ctypes.c_uint()
                libonlp.onlp_module_status_get(oid, ctypes.byref(sts))

                status_change = self.onlp_piu_status[piuId-1] ^ sts.value

                #continue if there is no change in status
                if status_change == 0:
                    continue

                self.onlp_piu_status[piuId-1] = sts.value
                self.sess.delete_item(f"{xpath}/piu/state/status")

                if sts.value != STATUS_UNPLUGGED:
                    self.sess.set_item(f"{xpath}/piu/state/status", "PRESENT")
                    if status_change & STATUS_ACO_PRESENT:
                        self.sess.set_item(f"{xpath}/piu/state/piu-type", "ACO")
                    elif status_change & STATUS_DCO_PRESENT:
                        self.sess.set_item(f"{xpath}/piu/state/piu-type", "DCO")
                    elif status_change & STATUS_QSFP_PRESENT:
                        self.sess.set_item(f"{xpath}/piu/state/piu-type", "QSFP")
                    else:
                        self.sess.set_item(f"{xpath}/piu/state/piu-type", "UNKNOWN")
                else:
                    self.sess.set_item(f"{xpath}/piu/state/status", "UNPLUGGED")
                    self.sess.delete_item(f"{xpath}/piu/state/piu-type")

            self.sess.apply_changes()
            await asyncio.sleep(1)

    def oid_iter_cb(self):
        def _v(oid, cookie):
            try:
                type = (oid >> 24)
                logger.debug(f"OID: {hex(oid)}, Type: {type}")
                self.onlp_oids_dict[type].append(oid)
                return onlp.onlp.ONLP_STATUS.OK
            except:
                logger.debug("exception found!!")
                return onlp.onlp.ONLP_STATUS.E_GENERIC
        return onlp.onlp.onlp_oid_iterate_f(_v)

    def initialise_devices(self):
        self.sess.switch_datastore('operational')

        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
            piuId = oid & 0xFFFFFF
            name = f'/dev/piu{piuId}'

            xpath = f"/goldstone-onlp:components/component[name='{name}']"
            self.sess.set_item(f"{xpath}/config/name", 'piu' + str(piuId))
            self.sess.set_item(f"{xpath}/state/type", "PIU")
            self.sess.set_item(f"{xpath}/piu/state/status", "UNPLUGGED")

            self.onlp_piu_status.append(0)

        self.sess.apply_changes()
        #Extend here for other devices[FAN,PSU,LED etc]


    async def start(self):
        # passing None to the 2nd argument is important to enable layering the running datastore
        # as the bottom layer of the operational datastore
        self.sess.subscribe_module_change('goldstone-onlp', None, self.change_cb, asyncio_register=True)

        # passing oper_merge=True is important to enable pull/push information layering
        self.sess.subscribe_oper_data_request('goldstone-onlp', '/goldstone-onlp:components/component', self.oper_cb, oper_merge=True, asyncio_register=True)

        # Read all the OID's , which would be used as handles to invoke ONLP API's
        self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.SYS].append(onlp.onlp.ONLP_OID_SYS)
        #loop through the SYS OID and get all the peripheral devices OIDs
        libonlp.onlp_oid_iterate(onlp.onlp.ONLP_OID_SYS, 0, self.oid_iter_cb(), None)
        logger.debug(f"System OID Dictionary: {self.onlp_oids_dict}")

        self.initialise_devices()

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
            tasks.append(stop_event.wait())
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
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
