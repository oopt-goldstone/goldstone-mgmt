from kubernetes.client.rest import ApiException
from kubernetes import client, config
import pydoc
import logging
from prompt_toolkit.completion import merge_completers

from .base import Command as BaseCommand, Context as BaseContext, InvalidInput

KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"

logger = logging.getLogger(__name__)
stdout = logging.getLogger("stdout")
stderr = logging.getLogger("stderr")


class Command(BaseCommand):
    @property
    def conn(self):
        return self.context.conn


class RunningConfigCommand(Command):
    REGISTERED_COMMANDS = {}

    def exec(self, line):
        if len(line) > 0:
            raise InvalidInput(f"usage: {self.name_all()} {self.usage()}")

        for cmd in self.list():
            self(cmd)

    def usage(self):
        return f"[ {' | '.join(self.list())} ]"


class TechSupportCommand(Command):
    REGISTERED_COMMANDS = {}

    def exec(self, line):
        if len(line) != 0:
            raise InvalidInput(f"usage: {self.name_all()}")

        self.xpath_list = []

        for cmd in self.list():
            self(cmd)

        stdout.info("\nshow datastore:\n")

        for ds in ["running", "operational", "startup"]:
            stdout.info("{} DB:\n".format(ds))
            for xpath in self.xpath_list:
                try:
                    stdout.info(f"{xpath} : \n")
                    stdout.info(self.conn.get(xpath, ds=ds))
                    stdout.info("\n")
                except Exception as e:
                    stderr.info(e)

        stdout.info("\nshow running-config:\n")
        self.parent(["running-config"])


class GlobalShowCommand(Command):
    COMMAND_DICT = {
        "datastore": Command,
        "tech-support": TechSupportCommand,
        "logging": Command,
        "running-config": RunningConfigCommand,
    }
    REGISTERED_COMMANDS = {}

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
        dss = ["running", "operational", "startup"]
        if len(line) < 2:
            stderr.info(f'usage: show datastore <XPATH> [{"|".join(dss)}]')
            return

        if len(line) == 2:
            ds = "running"
        else:
            ds = line[2]

        if ds not in dss:
            stderr.info(f"unsupported datastore: {ds}. candidates: {dss}")
            return

        stdout.info(self.conn.get(line[1], "", ds=ds, strip=False))

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
    for vlan in sess.get(
        "/goldstone-interfaces:interfaces/interface/goldstone-vlan:switched-vlan", []
    ):
        sess.delete(vlan.xpath)
    sess.apply()


class ClearDatastoreGroupCommand(Command):
    def exec(self, line):
        if len(line) < 1:
            raise InvalidInput(
                f"usage: {self.name_all()} [ <module name> | all ] [ running | startup ]"
            )

        ds = line[1] if len(line) == 2 else "running"

        sess = self.conn.new_session(ds)

        if line[0] == "all":
            models = [m for m in self.conn.models if "goldstone" in m]
            # the interface model has dependencies to other models (e.g. vlan, ufd )
            # we need to the clear interface model lastly
            # the vlan model has dependency to switched-vlan configuration
            # we need to clear the switched-vlan configuration first
            # TODO invent cleaner way when we have more dependency among models
            if "goldstone-vlan" in models:
                remove_switched_vlan_configuration(sess)
            models.remove("goldstone-interfaces")
            models.append("goldstone-interfaces")
        else:
            models = [line[0]]

        for m in models:
            stdout.info(f"clearing module {m}")
            sess.delete_all(m)

        sess.apply()

    def get(self, arg):
        elected = self.complete_subcommand(arg)
        if elected == None:
            return None
        return Choice(["running", "startup"], self.context, self, elected)

    def arguments(self):
        cmds = [m for m in self.conn.models if "goldstone" in m]
        cmds.append("all")
        return cmds


class ShowCommand(Command):
    def __init__(self, context=None, parent=None, name=None, additional_completer=None):
        if name == None:
            name = "show"
        c = context.root().get_completer("show")
        if additional_completer:
            c = merge_completers([c, additional_completer])
        super().__init__(context, parent, name, additional_completer=c)


class GlobalClearCommand(Command):
    COMMAND_DICT = {
        "datastore": ClearDatastoreGroupCommand,
    }
    REGISTERED_COMMANDS = {}


class NoCommand(Command):
    def exec(self, line):
        raise InvalidInput(self.usage())

    def usage(self):
        n = self.name_all()
        l = []
        for k, (cls, options) in self.list_subcommands():
            if not options.get("hidden"):
                v = cls(self.context, self, name=k)
                l.append(f"  {n} {k} {v.usage()}")

        return "usage:\n" + "\n".join(l)


def ModelExists(model):
    def f(ctx):
        if isinstance(ctx, Command):
            ctx = ctx.context
        return model in ctx.conn.models

    return f


class Context(BaseContext):
    def __init__(self, parent, fuzzy_completion=None):
        self.conn = parent.root().conn if parent != None else self.conn
        super().__init__(parent, fuzzy_completion)
        self.add_command("show", GlobalShowCommand)
        self.add_command("clear", GlobalClearCommand)

        for k, (cls, options) in list(self.list_subcommands()):
            if options.get("add_no"):
                self.add_no_command(k, cls, **options)

    def add_command(self, name, cmd, **options):
        super().add_command(name, cmd, **options)
        if options.get("add_no"):
            self.add_no_command(name, cmd, **options)

    def add_no_command(self, name, cmd, **options):
        no = getattr(self, "no", None)
        if not no:
            self.no = NoCommand(self, None, name="no")
            self.add_command("no", self.no)
        self.no.add_command(name, cmd, **options)
