import dbus
from kubernetes_asyncio import config, client
import asyncio
import os
import logging
import os.path
import pyroute2

KUBECONFIG = os.getenv("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")
K8S_SERVICE = os.getenv("K8S_SERVICE", "k3s.service")
SERVICE_CIDR = os.getenv("SERVICE_CIDR", "10.43.0.0/16")
K8S_INTF_NAME = os.getenv("K8S_INTF_NAME", "cni0")

logger = logging.getLogger(__name__)


class KubernetesServer:
    def __init__(self, conn):
        self.sess = conn.start_session()

    def stop(self):
        self.sess.stop()

    def restart_k8s(self):
        logger.info(f"restarting k8s")
        bus = dbus.SystemBus()
        systemd = bus.get_object(
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1"
        )
        manager = dbus.Interface(systemd, "org.freedesktop.systemd1.Manager")
        manager.ReloadOrRestartUnit(K8S_SERVICE, "fail")

    async def ping(self):
        await config.load_kube_config(KUBECONFIG)

        async with client.ApiClient() as api:
            v = client.VersionApi(api)

            try:
                await v.get_code()
            except Exception as e:
                logger.error(f"failed to access k8s: {e}")
                return False

        return True

    async def monitor(self):

        while not os.path.exists(KUBECONFIG):
            logger.warn(f"{KUBECONFIG} doesn't exist. sleep 10sec")
            await asyncio.sleep(10)

        while True:

            # TODO wait longer for initial bootup
            # get uptime and decide what to do
            if await self.ping():
                await asyncio.sleep(5)
            else:
                self.restart_k8s()

                while True:
                    if await self.ping():
                        break
                    await asyncio.sleep(5)

            with pyroute2.NDB() as ndb:
                try:
                    intf = ndb.interfaces[K8S_INTF_NAME]
                    ndb.routes.create(dst=SERVICE_CIDR,oif=intf["index"]).commit()
                except Exception as error:
                    logger.debug(f"{str(error)}")


    async def start(self):

        return [self.monitor()]
