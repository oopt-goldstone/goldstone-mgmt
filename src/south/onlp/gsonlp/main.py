import sysrepo
import logging
import asyncio
import argparse
import signal
import ctypes
import onlp.onlp
import json
import re
from pathlib import Path

libonlp = onlp.onlp.libonlp


class InvalidXPath(Exception):
    pass


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
        self.transceiver_presence = []
        self.components = {}

    def stop(self):
        logger.info(f"stop server")
        self.sess.stop()
        self.conn.disconnect()

    async def parse_oper_req(self, xpath):
        if xpath == "/goldstone-platform:*":
            return None
        prefix = "/goldstone-platform:components"
        if not xpath.startswith(prefix):
            raise InvalidXPath()
        xpath = xpath[len(prefix) :]
        if xpath == "" or xpath == "/component":
            return None
        c = re.search(r"/component\[state/type\=\'(?P<item>.+?)\'\]", xpath)
        item = c.group("item")
        return item

    def get_thermal_info(self):
        thermal = onlp.onlp.onlp_thermal_info()
        threshold = onlp.onlp.onlp_thermal_info_thresholds()
        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.THERMAL]:
            libonlp.onlp_thermal_info_get(oid, ctypes.byref(thermal))
            thermal_id = oid & 0xFFFFF
            name = f"THERMAL SENSOR{thermal_id}"
            if thermal.status & onlp.onlp.ONLP_THERMAL_STATUS.PRESENT:
                status = "PRESENT"
            else:
                status = "FAILED"
                r = {
                    "name": name,
                    "config": {"name": name},
                    "state": {
                        "type": "THERMAL",
                        "description": str(thermal.hdr.description, "utf-8"),
                    },
                    "thermal": {"state": {"status": [status]}},
                }
                self.components["goldstone-platform:components"]["component"].append(r)
                continue
            threshold = thermal.thresholds

            if thermal.caps & onlp.onlp.ONLP_THERMAL_CAPS.GET_TEMPERATURE:
                temperature = thermal.mcelcius
            else:
                temperature = 0xFFFF

            if thermal.caps & onlp.onlp.ONLP_THERMAL_CAPS.GET_WARNING_THRESHOLD:
                threshold_warning = threshold.warning
            else:
                threshold_warning = 0xFFFF

            if thermal.caps & onlp.onlp.ONLP_THERMAL_CAPS.GET_ERROR_THRESHOLD:
                threshold_error = threshold.error
            else:
                threshold_error = 0xFFFF

            if thermal.caps & onlp.onlp.ONLP_THERMAL_CAPS.GET_SHUTDOWN_THRESHOLD:
                threshold_shutdown = threshold.shutdown
            else:
                threshold_shutdown = 0xFFFF

            r = {
                "name": name,
                "config": {"name": name},
                "state": {
                    "type": "THERMAL",
                    "description": str(thermal.hdr.description, "utf-8"),
                },
                "thermal": {
                    "state": {
                        "status": [status],
                        "temperature": temperature,
                        "thresholds": {
                            "warning": threshold_warning,
                            "error": threshold_error,
                            "shutdown": threshold_shutdown,
                        },
                    }
                },
            }
            self.components["goldstone-platform:components"]["component"].append(r)

    def get_fan_info(self):
        fan = onlp.onlp.onlp_fan_info()
        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.FAN]:
            libonlp.onlp_fan_info_get(oid, ctypes.byref(fan))
            fan_id = oid & 0xFFFFFF
            name = f"FAN{fan_id}"
            fan_state = fan.status & onlp.onlp.ONLP_FAN_STATUS.PRESENT
            fan_status = fan.status & 3
            if fan_state:
                state = "PRESENT"
                if fan_status == 1:
                    status = "RUNNING"
                elif fan_status == 3:
                    status = "FAILED"

            else:
                state = "NOT-PRESENT"
                r = {
                    "name": name,
                    "config": {"name": name},
                    "state": {
                        "type": "FAN",
                        "description": str(fan.hdr.description, "utf-8"),
                    },
                    "fan": {"state": {"fan-state": state}},
                }

                self.components["goldstone-platform:components"]["component"].append(r)
                continue

            if fan.status & onlp.onlp.ONLP_FAN_STATUS.B2F:
                direction = "B2F"
            else:
                direction = "F2B"

            if fan.caps & onlp.onlp.ONLP_FAN_CAPS.GET_RPM:
                rpm = fan.rpm
            else:
                rpm = 0xFFFF

            if fan.caps & onlp.onlp.ONLP_FAN_CAPS.GET_PERCENTAGE:
                percentage = fan.percentage
            else:
                percentage = 0xFFFF

            r = {
                "name": name,
                "config": {"name": name},
                "state": {
                    "type": "FAN",
                    "description": str(fan.hdr.description, "utf-8"),
                },
                "fan": {
                    "state": {
                        "rpm": rpm,
                        "percentage": percentage,
                        "direction": direction,
                        "fan-state": state,
                        "status": status,
                    }
                },
            }

            self.components["goldstone-platform:components"]["component"].append(r)

    def get_psu_info(self):
        psu = onlp.onlp.onlp_psu_info()
        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.PSU]:
            libonlp.onlp_psu_info_get(oid, ctypes.byref(psu))
            psu_id = oid & 0xFFFFFF
            name = f"PSU{psu_id}"
            model = str(psu.model, "utf-8")
            serial = str(psu.serial, "utf-8")

            if psu.caps & onlp.onlp.ONLP_PSU_CAPS.IIN:
                in_curr = psu.miin
            else:
                in_curr = 0xFFFF

            if psu.caps & onlp.onlp.ONLP_PSU_CAPS.IOUT:
                out_curr = psu.miout
            else:
                out_curr = 0xFFFF

            if psu.caps & onlp.onlp.ONLP_PSU_CAPS.PIN:
                in_power = psu.mpin
            else:
                in_power = 0xFFFF

            if psu.caps & onlp.onlp.ONLP_PSU_CAPS.POUT:
                out_power = psu.mpout
            else:
                out_power = 0xFFFF

            if psu.caps & onlp.onlp.ONLP_PSU_CAPS.VIN:
                in_volt = psu.mvin
            else:
                in_volt = 0xFFFF

            if psu.caps & onlp.onlp.ONLP_PSU_CAPS.VOUT:
                out_volt = psu.mvout
            else:
                out_volt = 0xFFFF

            status_present = psu.status & onlp.onlp.ONLP_PSU_STATUS.PRESENT
            status_psu = psu.status ^ onlp.onlp.ONLP_PSU_STATUS.PRESENT
            if status_present:
                state = "PRESENT"
                if status_psu == 0:
                    status = "RUNNING"
                else:
                    status = "UNPLUGGED-OR-FAILED"
                r = {
                    "name": name,
                    "config": {"name": name},
                    "state": {
                        "type": "PSU",
                        "description": str(psu.hdr.description, "utf-8"),
                    },
                    "psu": {
                        "state": {
                            "psu-state": state,
                            "status": status,
                            "model": model,
                            "serial": serial,
                            "input-voltage": in_volt,
                            "output-voltage": out_volt,
                            "input-current": in_curr,
                            "output-current": out_curr,
                            "input-power": in_power,
                            "output-power": out_power,
                        }
                    },
                }
            else:
                state = "NOT-PRESENT"
                r = {
                    "name": name,
                    "config": {"name": name},
                    "state": {
                        "type": "PSU",
                        "description": str(psu.hdr.description, "utf-8"),
                    },
                    "psu": {"state": {"psu-state": state}},
                }
            self.components["goldstone-platform:components"]["component"].append(r)

    def get_led_info(self):
        led = onlp.onlp.onlp_led_info()
        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.LED]:
            libonlp.onlp_led_info_get(oid, ctypes.byref(led))
            led_id = oid & 0xFFFFFF
            name = f"LED{led_id}"
            if led.status & onlp.onlp.ONLP_LED_STATUS.PRESENT:
                status = "PRESENT"
            else:
                status = "FAILED"
                r = {
                    "name": name,
                    "config": {"name": name},
                    "state": {
                        "type": "LED",
                        "description": str(led.hdr.description, "utf-8"),
                    },
                    "led": {"state": {"status": [status]}},
                }

            mode = "OFF"
            if led.mode == onlp.onlp.ONLP_LED_MODE.OFF:
                mode = "OFF"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.ON:
                mode = "ON"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.RED:
                mode = "RED"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.RED_BLINKING:
                mode = "RED_BLINKING"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.ORANGE:
                mode = "ORANGE"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.ORANGE_BLINKING:
                mode = "ORANGE_BLINKING"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.YELLOW:
                mode = "YELLOW"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.YELLOW_BLINKING:
                mode = "YELLOW_BLINKING"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.GREEN:
                mode = "GREEN"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.GREEN_BLINKING:
                mode = "GREEN_BLINKING"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.BLUE:
                mode = "BLUE"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.BLUE_BLINKING:
                mode = "BLUE_BLINKING"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.PURPLE:
                mode = "PURPLE"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.PURPLE_BLINKING:
                mode = "PURPLE_BLINKING"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.AUTO:
                mode = "AUTO"
            elif led.mode == onlp.onlp.ONLP_LED_MODE.AUTO_BLINKING:
                mode = "AUTO_BLINKING"

            r = {
                "name": name,
                "config": {"name": name},
                "state": {
                    "type": "LED",
                    "description": str(led.hdr.description, "utf-8"),
                },
                "led": {"state": {"mode": mode, "status": [status]}},
            }

            self.components["goldstone-platform:components"]["component"].append(r)

    def get_onie_fields_from_schema(self):
        xpath = ["components", "component", "sys", "state", "onie-info"]
        xpath = "".join(f"/goldstone-platform:{v}" for v in xpath)
        ctx = self.sess.get_ly_ctx()
        o = list(ctx.find_path(xpath)).pop()
        return [child.name() for child in o.children()]

    def get_sys_info(self):
        sys = onlp.onlp.onlp_sys_info()
        libonlp.onlp_sys_info_get(ctypes.byref(sys))
        onie = {}
        for field in self.get_onie_fields_from_schema():
            value = getattr(sys.onie_info, field.replace("-", "_"), None)
            if type(value) == bytes:
                onie[field] = value.decode("utf-8")
            elif field == "mac" and value:
                onie[field] = ":".join(f"{v:02x}" for v in value)
            elif value:
                onie[field] = int(value)

        r = {
            "name": "SYS",
            "config": {"name": "SYS"},
            "state": {"type": "SYS", "description": "System Information"},
            "sys": {
                "state": {
                    "onie-info": onie,
                }
            },
        }
        self.components["goldstone-platform:components"]["component"].append(r)

    async def change_cb(self, event, req_id, changes, priv):
        logger.info(f"change_cb: {event}, {req_id}, {changes}")
        return

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        self.components = {"goldstone-platform:components": {"component": []}}
        logger.debug(f"oper_cb: {xpath}, {req_xpath}")
        item = await self.parse_oper_req(req_xpath)
        if item == None:
            self.get_thermal_info()
            self.get_fan_info()
            self.get_psu_info()
            self.get_led_info()
            self.get_sys_info()
        elif item == "THERMAL":
            self.get_thermal_info()
        elif item == "FAN":
            self.get_fan_info()
        elif item == "PSU":
            self.get_psu_info()
        elif item == "LED":
            self.get_led_info()
        elif item == "SYS":
            self.get_sys_info()
        elif item == "PIU" or "TRANSCEIVER":
            pass
        return self.components

    def send_notifcation(self, notif):
        ly_ctx = self.sess.get_ly_ctx()
        if len(notif) == 0:
            logger.warning(f"nothing to notify")
        else:
            n = json.dumps(notif)
            logger.info(f"Notification: {n}")
            dnode = ly_ctx.parse_data_mem(n, fmt="json", notification=True)
            self.sess.notification_send_ly(dnode)

    # monitor_piu() monitor PIU status periodically and change the operational data store
    # accordingly.
    def monitor_piu(self):
        self.sess.switch_datastore("operational")

        eventname = "goldstone-platform:piu-notify-event"

        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
            # TODO we set the PIU name as /dev/piu?. This is because libtai-aco.so expects
            # the module location to be the device file of the module.
            # However, this device file name might be awkward for network operators.
            # We may want to think about having more friendly alias for these names.
            piuId = oid & 0xFFFFFF

            name = f"/dev/piu{piuId}"

            xpath = f"/goldstone-platform:components/component[name='{name}']"

            sts = ctypes.c_uint()
            libonlp.onlp_module_status_get(oid, ctypes.byref(sts))

            status_change = self.onlp_piu_status[piuId - 1] ^ sts.value
            piu_sts_change = status_change & (
                STATUS_ACO_PRESENT | STATUS_DCO_PRESENT | STATUS_QSFP_PRESENT
            )
            cfp_sts_change = status_change & (
                CFP2_STATUS_UNPLUGGED | CFP2_STATUS_PRESENT
            )

            # continue if there is no change in status
            if status_change == 0:
                continue

            self.onlp_piu_status[piuId - 1] = sts.value

            piu_type = "UNKNOWN"
            cfp2_presence = "UNPLUGGED"

            if sts.value == STATUS_UNPLUGGED:
                piu_presence = "UNPLUGGED"
                notif = {eventname: {"name": name, "status": ["UNPLUGGED"]}}
            else:
                piu_presence = "PRESENT"
                if sts.value & STATUS_ACO_PRESENT:
                    piu_type = "ACO"
                elif sts.value & STATUS_DCO_PRESENT:
                    piu_type = "DCO"
                elif sts.value & STATUS_QSFP_PRESENT:
                    piu_type = "QSFP"
                else:
                    piu_type = "UNKNOWN"
                if sts.value & CFP2_STATUS_PRESENT:
                    cfp2_presence = "PRESENT"
                else:
                    cfp2_presence = "UNPLUGGED"
                notif = {
                    eventname: {
                        "name": name,
                        "status": ["PRESENT"],
                        "piu-type": piu_type,
                        "cfp2-presence": cfp2_presence,
                    }
                }
            self.send_notifcation(notif)

            if piu_sts_change != 0:
                self.sess.delete_item(f"{xpath}/piu/state/status")
                if piu_presence == "PRESENT":
                    self.sess.set_item(f"{xpath}/piu/state/piu-type", piu_type)
                    self.sess.set_item(
                        f"{xpath}/piu/state/cfp2-presence", cfp2_presence
                    )
                else:
                    self.sess.delete_item(f"{xpath}/piu/state/piu-type")
                    self.sess.delete_item(f"{xpath}/piu/state/cfp2-presence")

                self.sess.set_item(f"{xpath}/piu/state/status", piu_presence)

            if cfp_sts_change != 0 and sts.value != STATUS_UNPLUGGED:
                self.sess.set_item(f"{xpath}/piu/state/cfp2-presence", cfp2_presence)

        self.sess.apply_changes()

    # monitor_transceiver() monitor transceiver presence periodically and
    # change the operational data store accordingly.
    def monitor_transceiver(self):
        self.sess.switch_datastore("operational")
        eventname = "goldstone-platform:transceiver-notify-event"
        eeprom = ctypes.POINTER(ctypes.c_ubyte)()

        for i in range(len(self.transceiver_presence)):
            port = i + 1
            name = f"sfp{port}"
            xpath = f"/goldstone-platform:components/component[name='{name}']"

            presence = libonlp.onlp_sfp_is_present(port)

            if not (presence ^ self.transceiver_presence[i]):
                continue

            self.transceiver_presence[i] = presence

            self.sess.set_item(f"{xpath}/config/name", "sfp" + str(port))
            self.sess.set_item(f"{xpath}/state/type", "TRANSCEIVER")

            if presence:
                presence = "PRESENT"
                libonlp.onlp_sfp_eeprom_read(port, ctypes.byref(eeprom))
                sffEeprom = onlp.sff.sff_eeprom()
                libonlp.sff_eeprom_parse(ctypes.byref(sffEeprom), eeprom)
                vendor = sffEeprom.info.vendor.strip()
                model = sffEeprom.info.model.strip()
                serial_number = sffEeprom.info.serial.strip()
                if isinstance(vendor, bytes):
                    vendor = str(vendor, "utf-8")
                if isinstance(model, bytes):
                    model = str(model, "utf-8")
                if isinstance(serial_number, bytes):
                    serial_number = str(serial_number, "utf-8")
                self.sess.set_item(f"{xpath}/transceiver/state/vendor", vendor)
                self.sess.set_item(f"{xpath}/transceiver/state/model", model)
                self.sess.set_item(f"{xpath}/transceiver/state/serial", serial_number)
            else:
                presence = "UNPLUGGED"

            self.sess.set_item(f"{xpath}/transceiver/state/presence", presence)
            notif = {eventname: {"name": name, "presence": presence}}
            self.send_notifcation(notif)

    async def monitor_devices(self):
        while True:
            # Monitor change in PIU status
            self.monitor_piu()
            # Monitor change in QSFP presence
            self.monitor_transceiver()

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

            xpath = f"/goldstone-platform:components/component[name='{name}']"
            self.sess.set_item(f"{xpath}/config/name", "piu" + str(piuId))
            self.sess.set_item(f"{xpath}/state/type", "PIU")
            self.sess.set_item(f"{xpath}/piu/state/status", "UNPLUGGED")

            self.onlp_piu_status.append(0)

        self.sess.apply_changes()

    def initialise_component_transceiver(self):
        self.sess.switch_datastore("operational")

        # Component : SFP
        libonlp.onlp_sfp_init()

        bitmap = onlp.onlp.aim_bitmap256()
        libonlp.onlp_sfp_bitmap_t_init(ctypes.byref(bitmap))
        libonlp.onlp_sfp_bitmap_get(ctypes.byref(bitmap))

        total_ports = 0
        for port in range(1, 256):
            if onlp.onlp.aim_bitmap_get(bitmap.hdr, port):
                name = f"sfp{port}"
                xpath = f"/goldstone-platform:components/component[name='{name}']"

                self.sess.set_item(f"{xpath}/config/name", "sfp" + str(port))
                self.sess.set_item(f"{xpath}/state/type", "TRANSCEIVER")
                self.sess.set_item(f"{xpath}/transceiver/state/presence", "UNPLUGGED")

                self.transceiver_presence.append(0)
                total_ports += 1

        self.sess.apply_changes()
        logger.debug(f"Total ports supported: {total_ports}")

    def initialise_component_devices(self):
        # Read all the OID's , which would be used as handles to invoke ONLP API's
        self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.SYS].append(onlp.onlp.ONLP_OID_SYS)
        # loop through the SYS OID and get all the peripheral devices OIDs
        libonlp.onlp_oid_iterate(onlp.onlp.ONLP_OID_SYS, 0, self.oid_iter_cb(), None)
        logger.debug(f"System OID Dictionary: {self.onlp_oids_dict}")

        self.initialise_component_piu()

        self.initialise_component_transceiver()

        # Extend here for other devices[FAN,PSU,LED etc]

    async def start(self):
        # passing None to the 2nd argument is important to enable layering the running datastore
        # as the bottom layer of the operational datastore
        self.sess.switch_datastore("running")
        self.sess.subscribe_module_change(
            "goldstone-platform", None, self.change_cb, asyncio_register=True
        )

        # passing oper_merge=True is important to enable pull/push information layering
        self.sess.subscribe_oper_data_request(
            "goldstone-platform",
            "/goldstone-platform:components/component",
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
