import sysrepo
import libyang
import logging
import asyncio
import ctypes
import onlp.onlp
from goldstone.lib.core import ServerBase

libonlp = onlp.onlp.libonlp


class InvalidXPath(Exception):
    pass


logger = logging.getLogger(__name__)

STATUS_UNPLUGGED = 0
STATUS_ACO_PRESENT = 1 << 0
STATUS_DCO_PRESENT = 1 << 1
STATUS_QSFP28_PRESENT = 1 << 2
CFP2_STATUS_PRESENT = 1 << 3


def module_type2yang_value(v):
    v = v.replace("-", "_")
    if "GBASE" in v:
        v = v.replace("GBASE", "G_BASE")
    return "SFF_MODULE_TYPE_" + v


def get_eeprom(port):
    raw_eeprom = ctypes.POINTER(ctypes.c_ubyte)()
    libonlp.onlp_sfp_eeprom_read(port, ctypes.byref(raw_eeprom))
    eeprom = onlp.sff.sff_eeprom()
    libonlp.sff_eeprom_parse(ctypes.byref(eeprom), raw_eeprom)

    info = {}
    for field in [
        "vendor",
        "model",
        "serial",
        "media_type_name",
        "module_type_name",
        "sfp_type_name",
    ]:
        v = getattr(eeprom.info, field)
        if v:
            v = v.strip().decode("utf-8")
            info[field] = v

    return info


class PlatformServer(ServerBase):
    def __init__(self, conn):
        super().__init__(conn, "goldstone-platform")
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

    async def start(self):
        self.initialise_component_devices()
        tasks = await super().start()

        return tasks + [self.monitor_devices()]

    def parse_oper_req(self, xpath):
        if xpath == "/goldstone-platform:*":
            return None

        xpath = list(libyang.xpath_split(xpath))
        if (
            len(xpath) < 2
            or xpath[0][0] != "goldstone-platform"
            or xpath[0][1] != "components"
            or xpath[1][1] != "component"
        ):
            return None
        if len(xpath[1][2]) > 0 and xpath[1][2][0][0] == "state/type":
            return xpath[1][2][0][1]

    # monitor_piu() monitor PIU status periodically and change the operational data store
    # accordingly.
    def monitor_piu(self):
        self.sess.switch_datastore("operational")

        eventname = "goldstone-platform:piu-notify-event"

        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
            piuId = oid & 0xFFFFFF
            name = f"piu{piuId}"

            xpath = f"/goldstone-platform:components/component[name='{name}']"

            sts = ctypes.c_uint()
            libonlp.onlp_module_status_get(oid, ctypes.byref(sts))

            status_change = self.onlp_piu_status[piuId - 1] ^ sts.value
            piu_sts_change = status_change & (
                STATUS_ACO_PRESENT | STATUS_DCO_PRESENT | STATUS_QSFP28_PRESENT
            )
            cfp_sts_change = status_change & CFP2_STATUS_PRESENT

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
                elif sts.value & STATUS_QSFP28_PRESENT:
                    piu_type = "QSFP28"
                else:
                    piu_type = "UNKNOWN"
                if sts.value & CFP2_STATUS_PRESENT:
                    cfp2_presence = "PRESENT"
                else:
                    cfp2_presence = "UNPLUGGED"
                notif = {
                    "name": name,
                    "status": ["PRESENT"],
                    "piu-type": piu_type,
                    "cfp2-presence": cfp2_presence,
                }
            self.send_notification(eventname, notif)

    # monitor_transceiver() monitor transceiver presence periodically and
    # change the operational data store accordingly.
    def monitor_transceiver(self):
        eventname = "goldstone-platform:transceiver-notify-event"
        for i in range(len(self.transceiver_presence)):
            port = i + 1
            name = f"port{port}"
            presence = libonlp.onlp_sfp_is_present(port)
            if not (presence ^ self.transceiver_presence[i]):
                continue

            self.transceiver_presence[i] = presence
            notif = {
                "name": name,
                "presence": "PRESENT" if presence else "UNPLUGGED",
            }
            self.send_notification(eventname, notif)

    async def monitor_devices(self):
        while True:
            # Monitor change in PIU status
            self.monitor_piu()
            # Monitor change in QSFP28 presence
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
        # Component : PIU
        v = len(self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE])
        self.onlp_piu_status = [0 for _ in range(v)]

    def initialise_component_transceiver(self):
        # Component : SFP
        libonlp.onlp_sfp_init()

        bitmap = onlp.onlp.aim_bitmap256()
        libonlp.onlp_sfp_bitmap_t_init(ctypes.byref(bitmap))
        libonlp.onlp_sfp_bitmap_get(ctypes.byref(bitmap))

        total_ports = 0
        for port in range(1, 256):
            if onlp.onlp.aim_bitmap_get(bitmap.hdr, port):
                total_ports += 1
        self.transceiver_presence = [0 for _ in range(total_ports)]

    def initialise_component_devices(self):
        # Read all the OID's , which would be used as handles to invoke ONLP API's
        self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.SYS].append(onlp.onlp.ONLP_OID_SYS)
        # loop through the SYS OID and get all the peripheral devices OIDs
        libonlp.onlp_oid_iterate(onlp.onlp.ONLP_OID_SYS, 0, self.oid_iter_cb(), None)
        logger.debug(f"System OID Dictionary: {self.onlp_oids_dict}")

        self.initialise_component_piu()

        self.initialise_component_transceiver()

        # Extend here for other devices[FAN,PSU,LED etc]

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

    def get_piu_info(self):
        for oid in self.onlp_oids_dict[onlp.onlp.ONLP_OID_TYPE.MODULE]:
            piuId = oid & 0xFFFFFF
            name = f"piu{piuId}"
            r = {
                "name": name,
                "config": {"name": name},
                "state": {"type": "PIU"},
                "piu": {"state": {}},
            }

            sts = ctypes.c_uint()
            libonlp.onlp_module_status_get(oid, ctypes.byref(sts))

            piu_type = "UNKNOWN"
            cfp2_presence = "UNPLUGGED"

            if sts.value == STATUS_UNPLUGGED:
                piu_presence = "UNPLUGGED"
            else:
                piu_presence = "PRESENT"
                if sts.value & STATUS_ACO_PRESENT:
                    piu_type = "ACO"
                elif sts.value & STATUS_DCO_PRESENT:
                    piu_type = "DCO"
                elif sts.value & STATUS_QSFP28_PRESENT:
                    piu_type = "QSFP28"

                if sts.value & CFP2_STATUS_PRESENT:
                    cfp2_presence = "PRESENT"
                else:
                    cfp2_presence = "UNPLUGGED"

            r["piu"]["state"]["status"] = [piu_presence]
            r["piu"]["state"]["piu-type"] = piu_type
            r["piu"]["state"]["cfp2-presence"] = cfp2_presence
            self.components["goldstone-platform:components"]["component"].append(r)

    def get_transceiver_info(self):
        for i in range(len(self.transceiver_presence)):
            port = i + 1
            name = f"port{port}"
            r = {
                "name": name,
                "config": {"name": name},
                "state": {"type": "TRANSCEIVER"},
                "transceiver": {"state": {}},
            }

            presence = libonlp.onlp_sfp_is_present(port)

            if presence:
                presence = "PRESENT"
                eeprom = get_eeprom(port)
                logger.debug(f"port{port} eeprom: {eeprom}")
                if "vendor" in eeprom:
                    r["transceiver"]["state"]["vendor"] = eeprom["vendor"]
                if "model" in eeprom:
                    r["transceiver"]["state"]["model"] = eeprom["model"]
                if "serial" in eeprom:
                    r["transceiver"]["state"]["serial"] = eeprom["serial"]
                if "sfp_type_name" in eeprom:
                    r["transceiver"]["state"]["form-factor"] = eeprom["sfp_type_name"]
                if "module_type_name" in eeprom:
                    t = module_type2yang_value(eeprom["module_type_name"])
                    r["transceiver"]["state"]["sff-module-type"] = t
            else:
                presence = "UNPLUGGED"

            r["transceiver"]["state"]["presence"] = presence
            self.components["goldstone-platform:components"]["component"].append(r)

    async def oper_cb(self, sess, xpath, req_xpath, parent, priv):
        self.components = {"goldstone-platform:components": {"component": []}}
        logger.debug(f"oper_cb: {xpath}, {req_xpath}")
        item = self.parse_oper_req(req_xpath)
        logger.debug(f"parse_oper_req: item: {item}")
        if item == None:
            self.get_thermal_info()
            self.get_fan_info()
            self.get_psu_info()
            self.get_led_info()
            self.get_sys_info()
            self.get_piu_info()
            self.get_transceiver_info()
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
        elif item == "PIU":
            self.get_piu_info()
        elif item == "TRANSCEIVER":
            self.get_transceiver_info()
        logger.info(f"components: {self.components}")
        return self.components
