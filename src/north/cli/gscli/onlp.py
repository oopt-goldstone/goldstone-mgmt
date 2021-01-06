import sys
import os
from .base import InvalidInput
import libyang as ly
import sysrepo as sr
from .common import sysrepo_wrap
from tabulate import tabulate


class Component(object):
    def __init__(self, conn):
        self.session = conn.start_session()
        self.sr_op = sysrepo_wrap(self.session)
        self.component = {}
        self.XPATH = "/goldstone-onlp:components"

    def get_state_attr(self, details, component):
        table = []
        try:
            data = self.component["components"]["component"][component][details][
                "state"
            ]
            if details != "piu" and details != "sfp":
                desc = self.component["components"]["component"][component]["state"][
                    "description"
                ]
                table.append(["description", desc])
            for k, v in data.items():
                subnode = data[k]
                if isinstance(subnode, dict):
                    table.append([k])
                    for p, q in subnode.items():
                        table.append([p, q])
                elif isinstance(subnode, list):
                    for p in subnode:
                        table.append([k, p])
                else:
                    table.append([k, v])
        except (sr.errors.SysrepoNotFoundError, KeyError) as error:
            print(error)
        return table

    def show_onlp(self, option="all"):

        self.component = self.sr_op.get_data(self.XPATH, "operational")
        if option == "all":
            types = ["fan", "psu", "led", "piu", "sfp", "thermal", "sys"]
            components = self.get_components(option)
            for type_ in types:
                print("\n")
                t = type_.upper()
                print("-------------------------------")
                print(f"{t} INFORMATION")
                print("-------------------------------")
                components = self.get_components(type_)
                for component in components:
                    table = self.get_state_attr(type_, component)
                    print(component)
                    print(tabulate(table))

        elif option == "transceiver":
            components = self.get_components("piu")
            components.sort()
            for component in components:
                table = self.get_state_attr("piu", component)
                print(component)
                print(tabulate(table))
            components = self.get_components("sfp")
            components.sort()
            for component in components:
                table = self.get_state_attr("sfp", component)
                print(component)
                print(tabulate(table))
        elif option == "system":
            components = self.get_components("sys")
            components.sort()
            for component in components:
                table = self.get_state_attr("sys", component)
                print(component)
                print(tabulate(table))

        else:
            components = self.get_components(option)
            components.sort()
            for component in components:
                table = self.get_state_attr(option, component)
                print(component)
                print(tabulate(table))

    def get_components(self, type_):
        if type_ != "all":
            return [
                v["name"]
                for v in self.component.get("components", {}).get("component", [])
                if v["state"]["type"] == type_.upper()
            ]
        else:
            return [
                v for v in self.component.get("components", {}).get("component", [])
            ]

    def tech_support(self):
        print("\n Show Onlp details")
        self.show_onlp()
