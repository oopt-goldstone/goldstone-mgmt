### The TAI south server implementation.

The TAI south server is responsible for reconciling hardware configuration, sysrepo running configuration and TAI configuration.

The main YANG model to interact is 'goldstone-transponder'.
The TAI south server doesn't modify the running configuration of goldstone-transponder.
The running configuration is always given by user and it might be empty if a user doesn't give any configuration.
When the user doesn't give any configuration for the TAI module, TAI south server creates the module with the default configuration.
To disable the module, the user needs to explicitly set the module admin-status to 'down'

1. start-up process

In the beginning of the start-up process, the TAI south server gets the hardware configuration from the Platform operational configuration.
In order to get this information, the ONLP south server must be always running.
If ONLP south server is not running, TAI south server fails to get the hardware configuraion and exit. The restarting of the server is k8s's responsibility.

After getting the hardware configuration, the TAI south server checks if taish-server has created all the TAI objects corresponds to the hardware.
If not, it will create the TAI objects.

When creating the TAI objects, the TAI south server uses sysrepo TAI running configuration if any. If the user doesn't give any configuration, TAI library's default values will be used.
If taish-server has already created TAI objects, the TAI south server checks if those TAI objects have the same configuration as the sysrepo running configuration.
This reconcilation process only runs in the start-up process.
Since the configuration between taish-server and sysrepo running configuration will become inconsistent, it is not recommended to change the TAI configuration directly by the taish command
when the TAI south server is running.

2. operational datastore

The sysrepo TAI operational datastore is represented to the north daemons by layering two layers.

The bottom layer is running datastore. The top layer is the operational information which is **pulled** from the taish-server.
We stopped using the **push** mechanism to the operational datastore due to sysrepo's bug and trickey behavior.

To enable layering the running datastore, we need to subscribe to the whole goldstone-transponder. For this reason, we are passing
'None' to the 2nd argument of subscribe_module_change().

To enable layering, oper_merge=True option is passed to subscribe_oper_data_request().

The TAI south server doesn't modify the running datastore as mentioned earlier.
Basic information such as created modules, netifs and hostifs' name will be **pushed** in the start-up process.

The pull information is collected in TransponderServer::oper_cb().
This operation takes time since it actually invokes hardware access to get the latest information.
To mitigate the time as much as possible, we don't want to retrieve unnecessary information.

For example, if the north daemon is requesting the current modulation formation by the XPATH
"/goldstone-transponder:modules/module[name='/dev/piu1']/network-interface[name='0']/state/modulation-format",
we don't need to retrieve other attributes of the netif or the attributes of the parent module.

Even if we return unnecessary information, sysrepo drops them before returning to the caller based on the
requested XPATH.

In TransponderServer::oper_cb(), TransponderServer::parse_oper_req() is called to limit the call to taish-server by examining the
requested XPATH.
