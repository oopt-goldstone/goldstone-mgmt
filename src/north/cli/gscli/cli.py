import sys
import os
from tabulate import tabulate
from .sonic import Sonic
from .tai import Transponder
import json
import libyang as ly
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES

class show_wrap(object):
    XPATH = '/'
    def __init__(self):
        conn = sr.SysrepoConnection()
        self.session = conn.start_session()
        self.sonic = Sonic(conn)
        self.vlan = self.sonic.vlan
        self.port = self.sonic.port
        self.transponder = Transponder (conn)
    
    def display (self, line):
        if (len(line) < 2):
            print(self.disp_usage())
            return 
        module = line[0]
        detail_level = line[1]

        if (module == 'transponder'):
            if (detail_level == "summary"):
                return (self.transponder.show_transponder_summary())
            else:
                return (self.transponder.show_transponder(line[1]))
 
        elif (module == 'vlan' and detail_level == 'details'):
            return (self.vlan.show_vlan(detail_level))
        elif (module == 'interface' and (detail_level == 'brief' or detail_level == 'description')):
            return (self.port.show_interface(detail_level))
        else:
            if (module == 'interface'):
                print('usage: show interface (brief|description)')
            elif (module == 'vlan'):
                print('usage: show vlan details')
            return 
    
    def module_dict(self):
        module_names = self.transponder.get_modules()
        module_dict = dict.fromkeys(module_names,None)
        module_dict["summary"] = None
        return module_dict

    def datastore(self, line):
        dss = list(DATASTORE_VALUES.keys())
        fmt = 'default'
        if len(line) < 2:
            print(f'usage: show datastore <XPATH> [{"|".join(dss)}] [json|]')
            return

        if len(line) == 2:
            ds = 'running'
        else:
            ds = line[2]

        if (len(line) == 4):
            fmt = line[3]
        elif (len(line) == 3 and line[2] == 'json'):
            ds = 'running'
            fmt = line[2]
        
        if (fmt == 'default' or fmt == 'json'):
            pass
        else:
            print(f'unsupported format: {fmt}. supported: {json}')
            return

        if ds not in dss:
            print(f'unsupported datastore: {ds}. candidates: {dss}')
            return

        self.session.switch_datastore(ds)

        try:
            if (fmt == 'json'):
                print(json.dumps(self.session.get_data(line[1]), indent = 4))
            else:
                print(self.session.get_data(line[1]))
        except Exception as e:
            print(e)


    def disp_usage(self):
        return ('usage:\n'
                ' show interface (brief|description) \n'
                ' show vlan details \n'
                ' show transponder (<transponder_name>|summary)\n')

    
    def display_run_conf(self, line):
        if (len(line) > 1):
            module = line[1]
        else:
            module = 'all'

        if (module == 'all'):
            self.sonic.run_conf()
        
        elif (module == 'interface'):
            self.sonic.port_run_conf()
        
        elif (module == 'vlan'):
            self.sonic.vlan_run_conf()
    
    
    
    def get_version(self, line):
        print('To Be Done')
   

    def display_log(self, line):
        print('To Be Done')

    
    
    def tech_support(self, line):
        datastore_list = ['operational', 'running', 'candidate', 'startup']
        xpath_list = ['/sonic-vlan:sonic-vlan/VLAN/VLAN_LIST',
                     '/sonic-port:sonic-port/PORT/PORT_LIST'
                     ] 
     
        self.sonic.tech_support() 
        print('\nshow datastore:\n')

        for ds in datastore_list:
            self.session.switch_datastore(ds)
            print('{} DB:\n'.format(ds))
            for index in range(len(xpath_list)):
                try:
                    print(self.session.get_data(xpath_list[index]))
                    print('\n')
                except Exception as e:
                    print(e)
        print('\nRunning Config:\n')
        args = ['running-config']
        self.display_run_conf(args)

