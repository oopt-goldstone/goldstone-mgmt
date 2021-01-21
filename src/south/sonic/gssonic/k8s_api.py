import datetime
import io
import re
import os
import logging
import asyncio
import json

from kubernetes_asyncio import config, client, watch
from jinja2 import Template

DEPLOYMENT_NAME = "usonic"
USONIC_CONFIGMAP_NAME = "usonic-config"
USONIC_TEMPLATE_DIR = os.getenv("USONIC_TEMPLATE_DIR")
PORT_PREFIX = "Ethernet"

logger = logging.getLogger(__name__)


class incluster_apis(object):
    def __init__(self):
        config.load_incluster_config()
        self.v1_api = client.CoreV1Api()
        self.deploy_api = client.AppsV1Api()
        self.v1_ext = client.AppsV1beta2Api()
        self.usonic_deleted = 0

    def create_usonic_config_bcm(self, interface_list):
        with open(USONIC_TEMPLATE_DIR + "/interfaces.json") as f:
            master = json.loads(f.read())

        interfaces = []
        for i, m in enumerate(master):
            name = f"{PORT_PREFIX}{i+1}_1"
            channel = 1
            speed = m["speed"] // 1000

            for c in interface_list:
                if c[0] == name and c[1] != None and c[2] != None:
                    channel = c[1]
                    speed = c[2]
                    break

            lane_num = m["lane_num"] // channel

            for ii in range(channel):
                interface = {}
                interface["port"] = m["port"] + ii * lane_num
                interface["lane"] = m["first_lane"] + ii * lane_num
                interface["speed"] = speed
                interfaces.append(interface)

        with open(USONIC_TEMPLATE_DIR + "/config.bcm.j2") as f:
            t = Template(f.read())
            return t.render(interfaces=interfaces)

    def create_usonic_port_config(self, interface_list):
        with open(USONIC_TEMPLATE_DIR + "/interfaces.json") as f:
            master = json.loads(f.read())

        interfaces = []
        for i, m in enumerate(master):
            name = f"{PORT_PREFIX}{i+1}_1"
            channel = 1
            speed = m["speed"]

            for c in interface_list:
                if c[0] == name and c[1] != None and c[2] != None:
                    channel = c[1]
                    speed = c[2] * 1000
                    break

            lane_num = m["lane_num"] // channel

            for ii in range(channel):
                name = f"{PORT_PREFIX}{i+1}_{ii+1}"
                interface = {"name": name}
                first_lane = m["first_lane"] + ii * lane_num
                interface["lanes"] = ",".join(
                    str(first_lane + idx) for idx in range(lane_num)
                )
                interface["alias"] = f"{m['alias_prefix']}-{m['index']+ii}"
                interface["speed"] = speed
                interface["index"] = m["index"] + ii * lane_num
                interfaces.append(interface)

        with open(USONIC_TEMPLATE_DIR + "/port_config.ini.j2") as f:
            t = Template(f.read())
            return t.render(interfaces=interfaces)

    async def update_usonic_config(self, interface_list):
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
        resp = await self.v1_api.read_namespaced_config_map(
            name=cm_name, namespace="default"
        )

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

        await self.v1_api.patch_namespaced_config_map(
            name=cm_name, namespace="default", body=configMap
        )

        # 4. return True when we've updated the configmap, return False if not.
        logger.info("ConfigMap {} updated".format(cm_name))
        return True

    async def restart_usonic(self):
        deployment_name = DEPLOYMENT_NAME

        deployment = await self.deploy_api.read_namespaced_deployment(
            name=deployment_name, namespace="default"
        )
        # Update annotation, to restart the deployment
        deployment.spec.template.metadata.annotations[
            "kubectl.kubernetes.io/restartedAt"
        ] = str(datetime.datetime.now())

        # Update the deployment
        await self.deploy_api.patch_namespaced_deployment(
            name=deployment_name, namespace="default", body=deployment
        )
        logger.info("Deployment updated")

    async def watch_pods(self):
        w = watch.Watch()
        async with w.stream(self.v1_api.list_pod_for_all_namespaces) as stream:
            async for event in stream:
                name = event["object"].metadata.name
                phase = event["object"].status.phase

                if ("usonic" not in name) or name == "usonic-cli":
                    continue

                logger.debug(
                    "Event: %s %s %s %s"
                    % (
                        event["type"],
                        event["object"].kind,
                        name,
                        phase,
                    )
                )

                # Events sequence will be MODIFIED, DELETED, ADDED, MODIFIED
                # We will first wait for the deployment to be DELETED and then
                # will watch for the deployment to be Running
                if self.usonic_deleted == 1 and phase == "Running":
                    logger.debug("uSONiC reached running state, exiting")
                    self.usonic_deleted = 0
                    return
                if self.usonic_deleted != 1 and event["type"] == "DELETED":
                    self.usonic_deleted = 1
