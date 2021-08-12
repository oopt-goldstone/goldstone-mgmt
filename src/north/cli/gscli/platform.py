import sys
import os
from .base import InvalidInput
import libyang as ly
import sysrepo as sr
from .common import sysrepo_wrap
from tabulate import tabulate
import logging

from natsort import natsorted

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


def to_human(d):
    for key, val in d.items():
        if val == 0xFFFF:
            continue
        if "temperature" in key:
            d[key] = f"{d[key]/1000}°C"
        elif key.endswith("power"):
            d[key] = f"{d[key]/1000:.2f} W"
        elif key.endswith("voltage"):
            d[key] = f"{d[key]/1000:.2f} V"
        elif key.endswith("current"):
            d[key] = f"{d[key]/1000:.2f} A"
        elif "thresholds" in key:
            for p, q in d[key].items():
                if q == 0xFFFF:
                    continue
                else:
                    d[key][p] = f"{q/1000:.2f}°C"

    return d


class Component(object):
    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.component = {}
        self.XPATH = "/goldstone-platform:components"

    def get_state_attr(self, details, component):
        table = []
        try:
            data = component[details]["state"]
            data = to_human(data)
            if details != "piu" and details != "transceiver":
                desc = component["state"]["description"]
                table.append(["description", desc])
            for k, v in data.items():
                subnode = data[k]
                if isinstance(subnode, dict):
                    table.append([k])
                    for p, q in subnode.items():
                        if q == 0xFFFF:
                            q = "-"
                        table.append([p, q])
                elif isinstance(subnode, list):
                    for p in subnode:
                        if p == 0xFFFF:
                            p = "-"
                        table.append([k, p])
                else:
                    if v == 0xFFFF:
                        v = "-"
                    table.append([k, v])
        except (sr.errors.SysrepoNotFoundError, KeyError) as error:
            stderr.info(error)
        return table

    def show_platform(self, option="all", format=""):

        if option == "all":
            types = ["fan", "psu", "led", "piu", "transceiver", "thermal", "sys"]
            for type_ in types:
                stdout.info("\n")
                t = type_.upper()
                stdout.info("-------------------------------")
                stdout.info(f"{t} INFORMATION")
                stdout.info("-------------------------------")
                components = self.get_components(type_)
                for component in components:
                    table = self.get_state_attr(type_, component)
                    stdout.info(component["name"])
                    stdout.info(tabulate(table))
            stdout.info("Note: Values with the symbol '-' are unsupported")
        elif option == "transceiver" and format == "table":
            header = [
                "name",
                "presence",
                "model",
                "serial number",
                "form factor",
                "SFF type",
            ]
            rows = []
            for c in self.get_components("transceiver"):
                s = c.get("transceiver", {}).get("state", {})
                rows.append(
                    [
                        c["name"],
                        s.get("presence", "-").lower(),
                        s.get("model", "-"),
                        s.get("serial", "-"),
                        s.get("form-factor", "-"),
                        s.get("sff-module-type", "-"),
                    ]
                )
            stdout.info(tabulate(rows, header))
        elif option == "piu" and format == "table":
            header = ["name", "status", "PIU type", "CFP2 presence"]
            rows = []
            for c in self.get_components("piu"):
                s = c.get("piu", {}).get("state", {})
                rows.append(
                    [
                        c["name"],
                        "|".join(list(s.get("status", ["-"]))).lower(),
                        s.get("piu-type", "-"),
                        s.get("cfp2-presence", "-").lower(),
                    ]
                )
            stdout.info(tabulate(rows, header))
        elif option == "system":
            components = self.get_components("sys")
            for component in components:
                table = self.get_state_attr("sys", component)
                stdout.info(component["name"])
                stdout.info(tabulate(table))
        else:
            components = self.get_components(option)
            for component in components:
                table = self.get_state_attr(option, component)
                stdout.info(component["name"])
                stdout.info(tabulate(table))
            stdout.info("Note: Values with the symbol '-' are unsupported")

    def get_components(self, type_):
        c = self.sr_op.get_data(
            f"{self.XPATH}/component[state/type='{type_.upper()}']", "operational"
        )
        c = c.get("components", {}).get("component", [])
        return natsorted(c, key=lambda v: v["name"])

    def tech_support(self):
        stdout.info("\n Show platform details")
        self.show_platform()
