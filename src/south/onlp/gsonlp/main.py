import sysrepo
import logging
import asyncio
import argparse
import signal
import ctypes
import onlp.onlp
import json
from pathlib import Path

libonlp = onlp.onlp.libonlp

logger = logging.getLogger(__name__)

STATUS_UNPLUGGED = 0
STATUS_ACO_PRESENT = 1 << 0
STATUS_DCO_PRESENT = 1 << 1
STATUS_QSFP_PRESENT = 1 << 2
CFP2_STATUS_UNPLUGGED = 1 << 3
CFP2_STATUS_PRESENT = 1 << 4


class Server(object):
    def __init__(self):
        self.conn = sysrepo.SysrepoConnection()
        self.sess = self.conn.start_session()
        self.onlp_oids_dict = {
            onlp.onlp.ONLP_OID_TYPE.SYS: [],
            onlp.onlp.ONLP_OID_TYPE.THERMAL: [],
            onlp.onlp.ONLP_OID_TYPE.FAN: [],
            onlp.onlp.ONLP_OID_TYPE.PSU: [],
            onlp.onlp.ONLP_OID_TYPE.LED: [],
            # Module here is PIU
            onlp.onlp.ONLP_OID_TYPE.MODULE: [],
        }
        # This list would be indexed by piuId
        self.onlp_piu_status = []
        # This list would be indexed by port
        self.onlp_sfp_presence = []

    def stop(self):
        logger.info(f"stop server")
        self.sess.stop()
        self.conn.disconnect()

    async def change_cb(self, event, req_id, changes, priv):
        logger.info(f"change_cb: {event}, {req_id}, {changes}")
        return

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        logger.info(f"oper get callback requested xpath: {req_xpath}")
        return {}

    def send_notifcation(self, notif):
        ly_ctx = self.sess.get_ly_ctx()
        if len(notif) == 0:
            logger.warning(f"nothing to notify")
        else:
            n = json.dumps(notif)
            dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
            self.sess.notification_send_ly(dnode)

    # monitor_piu() monitor PIU status periodically and change the operational data store
    # accordingly.
    def monitor_piu(self):
        self.sess.switch_datastore("operational")

        eventname = "goldstone-onlp:piu-notify-event"

        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
            # TODO we set the PIU name as /dev/piu?. This is because libtai-aco.so expects
            # the module location to be the device file of the module.
            # However, this device file name might be awkward for network operators.
            # We may want to think about having more friendly alias for these names.
            piuId = oid & 0xFFFFFF

            name = f"/dev/piu{piuId}"

            xpath = f"/goldstone-onlp:components/component[name='{name}']"

            sts = ctypes.c_uint()
            libonlp.onlp_module_status_get(oid, ctypes.byref(sts))

            status_change = self.onlp_piu_status[piuId - 1] ^ sts.value

            # continue if there is no change in status
            if status_change == 0:
                continue

            self.onlp_piu_status[piuId - 1] = sts.value
            self.sess.delete_item(f"{xpath}/piu/state/status")

            if sts.value != STATUS_UNPLUGGED:
                self.sess.set_item(f"{xpath}/piu/state/status", "PRESENT")
                if status_change & STATUS_ACO_PRESENT:
                    piu_type = "ACO"
                elif status_change & STATUS_DCO_PRESENT:
                    piu_type = "DCO"
                elif status_change & STATUS_QSFP_PRESENT:
                    piu_type = "QSFP"
                else:
                    piu_type = "UNKNOWN"

                self.sess.set_item(f"{xpath}/piu/state/piu-type", piu_type)

                if status_change & CFP2_STATUS_PRESENT:
                    cfp2_status = "PRESENT"
                    self.sess.set_item(f"{xpath}/piu/state/cfp2-presence", "PRESENT")
                elif status_change & CFP2_STATUS_UNPLUGGED:
                    cfp2_status = "UNPLUGGED"
                    self.sess.set_item(f"{xpath}/piu/state/cfp2-presence", "UNPLUGGED")

                notif = {
                    eventname: {
                        "name": name,
                        "status": ["PRESENT"],
                        "piu-type": piu_type,
                        "cfp2-presence": cfp2_status,
                    }
                }

            else:
                self.sess.set_item(f"{xpath}/piu/state/status", "UNPLUGGED")
                self.sess.delete_item(f"{xpath}/piu/state/piu-type")
                notif = {eventname: {"name": name, "status": ["UNPLUGGED"]}}

            self.send_notifcation(notif)
        self.sess.apply_changes()

    # monitor_sfp() monitor SFP presence periodically and change the operational data store
    # accordingly.
    def monitor_sfp(self):
        self.sess.switch_datastore("operational")
        eventname = "goldstone-onlp:sfp-notify-event"

        for i in range(len(self.onlp_sfp_presence)):
            port = i + 1
            name = f"sfp{port}"
            xpath = f"/goldstone-onlp:components/component[name='{name}']"

            self.sess.set_item(f"{xpath}/config/name", "sfp" + str(port))
            self.sess.set_item(f"{xpath}/state/type", "SFP")

            presence = libonlp.onlp_sfp_is_present(port)

            if not (presence ^ self.onlp_sfp_presence[i]):
                continue

            if presence:
                sfp_presence = "PRESENT"
            else:
                sfp_presence = "UNPLUGGED"

            self.sess.set_item(f"{xpath}/sfp/state/presence", sfp_presence)
            notif = {eventname: {"name": name, "presence": sfp_presence}}
            self.send_notifcation(notif)
            self.onlp_sfp_presence[i] = presence

    async def monitor_devices(self):
        while True:
            # Monitor change in PIU status
            self.monitor_piu()
            # Monitor change in QSFP presence
            self.monitor_sfp()

            await asyncio.sleep(1)

    def oid_iter_cb(self):
        def _v(oid, cookie):
            try:
                type = oid >> 24
                logger.debug(f"OID: {hex(oid)}, Type: {type}")
                self.onlp_oids_dict[type].append(oid)
                return onlp.onlp.ONLP_STATUS.OK
            except:
                logger.debug("exception found!!")
                return onlp.onlp.ONLP_STATUS.E_GENERIC

        return onlp.onlp.onlp_oid_iterate_f(_v)

    def initialise_component_piu(self):
        self.sess.switch_datastore("operational")

        # Component : PIU
        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
            piuId = oid & 0xFFFFFF
            name = f"/dev/piu{piuId}"

            xpath = f"/goldstone-onlp:components/component[name='{name}']"
            self.sess.set_item(f"{xpath}/config/name", "piu" + str(piuId))
            self.sess.set_item(f"{xpath}/state/type", "PIU")
            self.sess.set_item(f"{xpath}/piu/state/status", "UNPLUGGED")

            self.onlp_piu_status.append(0)

        self.sess.apply_changes()

    def initialise_component_sfp(self):
        self.sess.switch_datastore("operational")

        # Component : SFP
        libonlp.onlp_sfp_init()

        bitmap = onlp.onlp.aim_bitmap256()
        libonlp.onlp_sfp_bitmap_t_init(ctypes.byref(bitmap))
        libonlp.onlp_sfp_bitmap_get(ctypes.byref(bitmap))

        total_sfp_ports = 0
        for port in range(1, 256):
            if onlp.onlp.aim_bitmap_get(bitmap.hdr, port):
                name = f"sfp{port}"
                xpath = f"/goldstone-onlp:components/component[name='{name}']"

                self.sess.set_item(f"{xpath}/config/name", "sfp" + str(port))
                self.sess.set_item(f"{xpath}/state/type", "SFP")
                self.sess.set_item(f"{xpath}/sfp/state/presence", "UNPLUGGED")

                self.onlp_sfp_presence.append(0)
                total_sfp_ports += 1

        self.sess.apply_changes()
        logger.debug(f"Total SFP ports supported: {total_sfp_ports}")

    def initialise_component_devices(self):
        # Read all the OID's , which would be used as handles to invoke ONLP API's
        self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.SYS].append(onlp.onlp.ONLP_OID_SYS)
        # loop through the SYS OID and get all the peripheral devices OIDs
        libonlp.onlp_oid_iterate(onlp.onlp.ONLP_OID_SYS, 0, self.oid_iter_cb(), None)
        logger.debug(f"System OID Dictionary: {self.onlp_oids_dict}")

        self.initialise_component_piu()

        self.initialise_component_sfp()

        # Extend here for other devices[FAN,PSU,LED etc]

    async def start(self):
        # passing None to the 2nd argument is important to enable layering the running datastore
        # as the bottom layer of the operational datastore
        self.sess.subscribe_module_change(
            "goldstone-onlp", None, self.change_cb, asyncio_register=True
        )

        # passing oper_merge=True is important to enable pull/push information layering
        self.sess.subscribe_oper_data_request(
            "goldstone-onlp",
            "/goldstone-onlp:components/component",
            self.oper_cb,
            oper_merge=True,
            asyncio_register=True,
        )

        self.initialise_component_devices()

        return [self.monitor_devices()]


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
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            logger.debug(f"done: {done}, pending: {pending}")
            for task in done:
                e = task.exception()
                if e:
                    raise e
        finally:
            server.stop()

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
