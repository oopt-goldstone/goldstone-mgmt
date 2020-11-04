import datetime
import io
import re
import logging
import asyncio

from .constants import INTERFACE_MAP
from .constants import CONFIG_BCM_CONTSTANTS1, CONFIG_BCM_CONTSTANTS2

from kubernetes import config, client, watch

DEPLOYMENT_NAME = "usonic"
USONIC_CONFIGMAP_NAME = "usonic-config"

logger = logging.getLogger(__name__)


class incluster_apis(object):
    def __init__(self):
        config.load_incluster_config()
        self.v1_api = client.CoreV1Api()
        self.deploy_api = client.AppsV1Api()
        self.v1_ext = client.AppsV1beta2Api()
        self.usonic_deleted = 0

    def get_portmap_number_from_lane(self, lane):
        if lane <= 29:
            return lane
        if lane >= 33 and lane <= 61:
            return lane + 1
        if lane == 69:
            return 68
        if lane == 65:
            return 72
        if lane == 77:
            return 76
        if lane == 73:
            return 80
        if lane >= 81 and lane <= 93:
            return lane + 3
        if lane >= 97 and lane <= 125:
            return lane + 5

    def create_usonic_config_bcm(self, interface_list):
        # config_bcm is divided in 3 parts
        # 1. Configurations present above portmap configs are stored
        #    in CONFIG_BCM_CONTSTANTS1
        # 2. Create port_map from inteface_map
        # 3. Configurations present below portmap configs are stored
        #    in CONFIG_BCM_CONTSTANTS2
        config_bcm = CONFIG_BCM_CONTSTANTS1
        pattern = "portmap_{}={}:{}\n"

        for interface in INTERFACE_MAP:

            line = ""
            lane_num = INTERFACE_MAP[interface][0]
            port_num = self.get_portmap_number_from_lane(lane_num)
            speed = "100"

            # Loop through interface_list if this interface exists and get the
            # breakout configuration
            breakout_config = []
            for intf in interface_list:
                if intf[0] == interface:
                    breakout_config = intf
                    break

            if len(breakout_config) == 0 or (
                breakout_config[1] == None and breakout_config[2] == None
            ):
                # If interface is not present in received interface list
                # OR interface doesnt have breakout configurations
                line = pattern.format(str(port_num), str(lane_num), speed)
            else:
                # Interface with num-channels and channel-speed
                if breakout_config[1] != None and breakout_config[2] != None:
                    speed = str(breakout_config[2])
                    if breakout_config[1] == 2:
                        # Parent Interface
                        line = pattern.format(str(port_num), str(lane_num), speed)

                        # Sub-if
                        tmp_port_num = port_num + 2
                        tmp_lane_num = lane_num + 2
                        line = line + pattern.format(
                            str(tmp_port_num), str(tmp_lane_num), speed
                        )
                    elif breakout_config[1] == 4:
                        # Parent Interface
                        line = pattern.format(str(port_num), str(lane_num), speed)

                        # Sub-interfaces
                        for i in range(1, 3 + 1):
                            tmp_port_num = port_num + i
                            tmp_lane_num = lane_num + i
                            line = line + pattern.format(
                                str(tmp_port_num), str(tmp_lane_num), speed
                            )

            config_bcm = config_bcm + line

        config_bcm = config_bcm + CONFIG_BCM_CONTSTANTS2

        return config_bcm

    def create_usonic_port_config(self, interface_list):
        port_config = ""
        header = "# name      lanes            alias         index speed\n"
        pattern = "{} {} {} {} {}\n"

        port_config = header
        # inteface_map is standard map of interfaces with values
        # required to build port_config.ini and config.bcm
        for interface in INTERFACE_MAP:

            line = ""
            lane_num = INTERFACE_MAP[interface][0]
            alias = INTERFACE_MAP[interface][1]
            index = INTERFACE_MAP[interface][2]
            speed = "100000"

            # Loop through interface_list if this interface exists and get the
            # breakout configuration
            breakout_config = []
            for intf in interface_list:
                if intf[0] == interface:
                    breakout_config = intf
                    break

            if len(breakout_config) == 0 or (
                breakout_config[1] == None and breakout_config[2] == None
            ):
                # If interface is not present in received interface list
                # OR interface doesnt have breakout configurations
                lanes = (
                    str(lane_num)
                    + ","
                    + str(lane_num + 1)
                    + ","
                    + str(lane_num + 2)
                    + ","
                    + str(lane_num + 3)
                )
                # Adding line according to header
                line = pattern.format(interface, lanes, alias, str(index), speed)
            else:
                # Interface with num-channels and channel-speed
                if breakout_config[1] != None and breakout_config[2] != None:
                    common_ifname = interface.split("/")
                    common_alias = alias.split("/")

                    # Channel speed
                    speed = str(int(breakout_config[2]) * 1000)
                    # Number of channels
                    if breakout_config[1] == 2:
                        # Parent Interface
                        lanes = str(lane_num) + "," + str(lane_num + 1)
                        line = pattern.format(
                            interface, lanes, alias, str(index), speed
                        )

                        # Sub-if
                        index = index + 2
                        lanes = str(lane_num + 2) + "," + str(lane_num + 3)
                        line = line + pattern.format(
                            common_ifname[0] + "/2",
                            lanes,
                            common_alias[0] + "/2",
                            str(index),
                            speed,
                        )
                    elif breakout_config[1] == 4:
                        # Parent Interface
                        line = pattern.format(
                            interface, str(lane_num), alias, str(index), speed
                        )

                        # Sub-interfaces
                        for i in range(1, 3 + 1):
                            tmp_index = index + i
                            lanes = str(lane_num + i)
                            tmp_ifname = common_ifname[0] + "/" + str(i + 1)
                            tmp_alias = common_alias[0] + "/" + str(i + 1)
                            line = line + pattern.format(
                                tmp_ifname, lanes, tmp_alias, str(tmp_index), speed
                            )
            port_config = port_config + line

        return port_config

    def update_usonic_config(self, interface_list):
        cm_name = USONIC_CONFIGMAP_NAME

        logger.debug("configmap update: {} {} ".format(cm_name, interface_list))

        # 1. create complete port_config.ini and config.bcm from the interface_list argument
        #    without using the existing config_map data
        #    Using string.Template (https://docs.python.org/3/library/string.html#template-strings) or Jinja2
        #    might make the code easier to read.
        config_bcm = self.create_usonic_config_bcm(interface_list)
        port_config = self.create_usonic_port_config(interface_list)

        logger.debug(f"port_config.ini file after creating:\n {port_config}")

        logger.debug(f"config.bcm file after creating :\n {config_bcm}")

        # 2. get the config_map using k8s API if it already exists
        resp = self.v1_api.read_namespaced_config_map(name=cm_name, namespace="default")

        configMap = resp
        running_port_config = ""
        running_config_bcm = ""
        try:
            running_port_config = configMap.data["port_config.ini"]
        except:
            logger.error("port_config.ini is not present")
            return False

        try:
            running_config_bcm = configMap.data["config.bcm"]
        except:
            logger.error("config.bcm is not present")
            return False

        logger.debug(f"Running port_config.ini :\n {port_config}")

        logger.debug(f"Running config.bcm :\n {config_bcm}")

        # 3. if the generated port_config.ini / config.bcm is different from what exists in k8s API, update it
        if (running_port_config == port_config) and (running_config_bcm == config_bcm):
            logger.debug(f"No changes in port_config.ini and config.bcm")
            return False

        configMap.data["port_config.ini"] = port_config

        configMap.data["config.bcm"] = config_bcm

        resp = self.v1_api.patch_namespaced_config_map(
            name=cm_name, namespace="default", body=configMap
        )

        # 4. return True when we've updated the configmap, return False if not.
        logger.info("ConfigMap {} updated".format(cm_name))
        return True

    def restart_usonic(self):
        deployment_name = DEPLOYMENT_NAME

        deployment = self.deploy_api.read_namespaced_deployment(
            name=deployment_name, namespace="default"
        )
        # Update annotation, to restart the deployment
        deployment.spec.template.metadata.annotations[
            "kubectl.kubernetes.io/restartedAt"
        ] = str(datetime.datetime.now())

        # Update the deployment
        api_response = self.deploy_api.patch_namespaced_deployment(
            name=deployment_name, namespace="default", body=deployment
        )
        logger.info("Deployment updated")

    async def watch_pods(self):
        w = watch.Watch()
        for event in w.stream(self.v1_api.list_pod_for_all_namespaces):
            if (event["object"].metadata.name).find("usonic") != -1 and event[
                "object"
            ].metadata.name != "usonic-cli":
                logger.debug(
                    "Event: %s %s %s %s"
                    % (
                        event["type"],
                        event["object"].kind,
                        event["object"].metadata.name,
                        event["object"].status.phase,
                    )
                )
                # Events sequence will be MODIFIED, DELETED, ADDED, MODIFIED
                # We will first wait for the deployment to be DELETED and then
                # will watch for the deployment to be Running
                if (
                    self.usonic_deleted == 1
                    and event["object"].status.phase == "Running"
                ):
                    logger.debug("Usonic reached running state, exiting")
                    return
                if self.usonic_deleted != 1 and event["type"] == "DELETED":
                    self.usonic_deleted = 1
            await asyncio.sleep(0)
