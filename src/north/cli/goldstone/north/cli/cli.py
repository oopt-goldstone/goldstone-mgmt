import json
import sysrepo as sr
from sysrepo.session import DATASTORE_VALUES
from kubernetes.client.rest import ApiException
from kubernetes import client, config
import pydoc
import logging
from prompt_toolkit.completion import merge_completers

from .base import *

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"

SR_TIMEOUT_MS = 60000

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class RunningConfigCommand(Command):
    REGISTERED_SUBCOMMANDS = {}

    def exec(self, line):
        if len(line) > 0:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

        for cmd in self.list():
            self(cmd)

    def usage(self):
        return f"[ {' | '.join(self.list())} ]"


class TechSupportCommand(Command):
    REGISTERED_SUBCOMMANDS = {}

    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")

        self.xpath_list = []

        for cmd in self.list():
            self(cmd)

        stdout.info("\nshow datastore:\n")

        with self.context.conn.start_session() as session:
            for ds in ["running", "operational", "startup"]:
                session.switch_datastore(ds)
                stdout.info("{} DB:\n".format(ds))
                for xpath in self.xpath_list:
                    try:
                        stdout.info(f"{xpath} : \n")
                        stdout.info(session.get_data(xpath))
                        stdout.info("\n")
                    except Exception as e:
                        stderr.info(e)

        stdout.info("\nshow running-config:\n")
        self.parent(["running-config"])


class GlobalShowCommand(Command):
    SUBCOMMAND_DICT = {
        "datastore": Command,
        "tech-support": TechSupportCommand,
        "logging": Command,
        "running-config": RunningConfigCommand,
    }
    REGISTERED_SUBCOMMANDS = {}

    def exec(self, line):
        if len(line) == 0:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

        if line[0] == "datastore":
            self.datastore(line)

        elif line[0] == "logging":
            self.display_log(line)

        else:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

    def datastore(self, line):
        conn = self.context.conn
        with conn.start_session() as sess:
            dss = list(DATASTORE_VALUES.keys())
            fmt = "default"
            if len(line) < 2:
                stderr.info(f'usage: show datastore <XPATH> [{"|".join(dss)}] [json|]')
                return

            if len(line) == 2:
                ds = "running"
            else:
                ds = line[2]

            if len(line) == 4:
                fmt = line[3]
            elif len(line) == 3 and line[2] == "json":
                ds = "running"
                fmt = line[2]

            if fmt == "default" or fmt == "json":
                pass
            else:
                stderr.info(f"unsupported format: {fmt}. supported: {json}")
                return

            if ds not in dss:
                stderr.info(f"unsupported datastore: {ds}. candidates: {dss}")
                return

            sess.switch_datastore(ds)

            if ds == "operational":
                defaults = True
            else:
                defaults = False

            try:
                data = sess.get_data(
                    line[1],
                    include_implicit_defaults=defaults,
                    timeout_ms=SR_TIMEOUT_MS,
                )
            except Exception as e:
                stderr.info(e)
                return

            if fmt == "json":
                stdout.info(json.dumps(data), indent=4)
            else:
                stdout.info(data)

    def display_log(self, line):
        log_filter = ["sonic", "tai", "onlp"]
        module_name = "gs-mgmt-"
        line_count = 0
        if len(line) >= 2:
            if line[1].isdigit() and len(line) == 2:
                line_count = int(line[1])
            elif line[1] in log_filter:
                module_name = module_name + line[1]
                if len(line) == 3 and line[2].isdigit():
                    line_count = int(line[2])
                elif len(line) == 2:
                    line_count = 0
                else:
                    raise InvalidInput("The argument <num_lines> must be a number")
            else:
                raise InvalidInput(
                    f"usage: {self.name_all()} logging [sonic|tai|onlp] [<num_lines>]"
                )
        else:
            line_count = 0
            module_name = "gs-mgmt-"

        try:
            config.load_kube_config(KUBECONFIG)
        except config.config_exception.ConfigException as error:
            config.load_incluster_config()

        try:
            api_instance = client.CoreV1Api()
            pod_info = api_instance.list_pod_for_all_namespaces(watch=False)
            log = ""
            for pod_name in pod_info.items:
                if pod_name.metadata.name.startswith(module_name):
                    log = log + ("----------------------------------\n")
                    log = log + (f"{pod_name.metadata.name}\n")
                    log = log + ("----------------------------------\n")
                    try:
                        if line_count > 0:
                            api_response = api_instance.read_namespaced_pod_log(
                                name=pod_name.metadata.name,
                                namespace="default",
                                tail_lines=line_count,
                            )
                        else:
                            api_response = api_instance.read_namespaced_pod_log(
                                name=pod_name.metadata.name, namespace="default"
                            )

                        log = log + api_response
                    except ApiException as e:
                        log = (
                            log
                            + f"Exception occured while fetching log for {pod_name.metadata.name}\n"
                        )
                        continue

            log = log + ("\n")
            pydoc.pager(log)

        except ApiException as e:
            stderr.info("Found exception in reading the logs : {}".format(str(e)))

    def usage(self):
        return f"[ {' | '.join(self.list())} ]"


def remove_switched_vlan_configuration(sess):
    for vlan in sess.get_items(
        "/goldstone-interfaces:interfaces/interface/goldstone-vlan:switched-vlan"
    ):
        sess.delete_item(vlan.xpath)
    sess.apply_changes()


class ClearDatastoreGroupCommand(Command):
    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(
                f"usage: {self.name_all()} [ <module name> | all ] [ running | startup ]"
            )

        ds = line[1] if len(line) == 2 else "running"

        root = self.context.root()

        try:
            with root.conn.start_session() as sess:
                sess.switch_datastore(ds)

                if line[0] == "all":
                    ctx = root.conn.get_ly_ctx()
                    modules = [m.name() for m in ctx if "goldstone" in m.name()]
                    # the interface model has dependencies to other models (e.g. vlan, ufd )
                    # we need to the clear interface model lastly
                    # the vlan model has dependency to switched-vlan configuration
                    # we need to clear the switched-vlan configuration first
                    # TODO invent cleaner way when we have more dependency among models
                    remove_switched_vlan_configuration(sess)
                    modules.remove("goldstone-interfaces")
                    modules.append("goldstone-interfaces")
                else:
                    modules = [line[0]]

                for m in modules:
                    stdout.info(f"clearing module {m}")
                    sess.replace_config({}, m)

                sess.apply_changes()

        except sr.SysrepoError as e:
            raise CLIException(f"failed to clear: {e}")

    def get(self, arg):
        elected = self.complete_subcommand(arg)
        if elected == None:
            return None
        return Choice(["running", "startup"], self.context, self, elected)

    def list(self):
        ctx = self.context.root().conn.get_ly_ctx()
        cmds = [m.name() for m in ctx if "goldstone" in m.name()]
        cmds.append("all")
        return cmds


class ShowCommand(Command):
    def __init__(self, context=None, parent=None, name=None, additional_completer=None):
        if name == None:
            name = "show"
        c = context.root().get_completer("show")
        if additional_completer:
            c = merge_completers([c, additional_completer])
        super().__init__(context, parent, name, c)


class GlobalClearCommand(Command):
    SUBCOMMAND_DICT = {
        "datastore": ClearDatastoreGroupCommand,
    }
    REGISTERED_SUBCOMMANDS = {}


class NoCommand(Command):
    def exec(self, line):
        raise InvalidInput(self.usage())

    # hide no command if no sub-command is registerd
    def hidden(self):
        return len(list(self.list_subcommands())) == 0

    def usage(self):
        n = self.name_all()
        l = []
        for k, cls in self.list_subcommands():
            v = cls(self.context, self, name=k)
            l.append(f"  {n} {k} {v.usage()}")

        return "usage:\n" + "\n".join(l)


def ModelExists(model):
    def f(cmd):
        return model in cmd.context.root().installed_modules

    return f


class GSObject(Object):
    def __init__(self, parent, fuzzy_completion=False):
        super().__init__(parent, fuzzy_completion)
        self.add_command(GlobalShowCommand(self, name="show"))
        self.add_command(GlobalClearCommand(self, name="clear"))
        self.no = NoCommand(self, name="no")
        self.add_command(self.no)
