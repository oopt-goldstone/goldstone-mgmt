from .base import (
    Connector as BaseConnector,
    Session as BaseSession,
    Error,
)

import libyang
import logging
import threading
from pathlib import Path

from ncclient import manager
from ncclient.xml_ import *
from lxml import etree

from pyang import repository
from pyang import context
from pyang.plugins.jsonxsl import JsonXslPlugin
from pyang import syntax
import io
import json

from xml.dom.minidom import parseString


logger = logging.getLogger(__name__)


def str2bool(d, key):
    v = d.get(key)
    if v == "false":
        d[key] = False
    elif v == "true":
        d[key] = True


def get_schema(conn, schema_dir, model, revision=None):
    revision_str = "@" + revision if revision else ""
    schema_file = (
        Path(f"{schema_dir}/schema/{model}{revision_str}.yang") if schema_dir else None
    )
    if schema_file.exists():
        with schema_file.open() as f:
            return f.read()

    schema = conn.get_schema(identifier=model, version=revision)
    schema = schema._data
    schema_file.parent.mkdir(parents=True, exist_ok=True)
    with schema_file.open("w") as f:
        f.write(schema)
    return schema


def jsonxsl_xformer(models, schema_dir):
    schema_file = Path(f"{schema_dir}/xsl/goldstone-json.xsl")
    if schema_file.exists():
        with schema_file.open() as f:
            xslt = f.read()
    else:
        repos = repository.FileRepository(schema_dir)

        ctx = context.Context(repos)

        jsonxsl = JsonXslPlugin()
        jsonxsl.setup_fmt(ctx)

        modules = []

        for filename, text in models:
            m = syntax.re_filename.search(filename)
            name, rev, in_format = m.groups()
            module = ctx.add_module(
                filename,
                text,
                in_format,
                name,
                rev,
                expect_failure_error=False,
                primary_module=True,
            )
            modules.append(module)

        ctx.validate()

        buf = io.StringIO()
        jsonxsl.emit(ctx, modules, buf)
        xslt = buf.getvalue()

        schema_file.parent.mkdir(parents=True, exist_ok=True)
        with schema_file.open("w") as f:
            f.write(parseString(xslt).toprettyxml())

    # no idea why we need this, but without this, it failes to resolv URL
    # there might be a better and cleaner way
    class FileResolver(etree.Resolver):
        def resolve(self, url, pubid, context):
            return self.resolve_filename("/" + url, context)

    parser = etree.XMLParser()
    parser.resolvers.add(FileResolver())

    return etree.XSLT(etree.parse(io.BytesIO(xslt.encode()), parser))


class Session(BaseSession):
    def __init__(self, conn, ds):
        self.conn = conn
        self.ds = ds
        self.netconf_conn = manager.connect(**self.conn._connect_args)
        assert self.netconf_conn != None
        self._thread = None

    def delete_all(self, model):
        if self.ds != "running":
            super().delete_all(model)
        return self.conn.delete_all(model)

    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        return self.conn.get(xpath, default, include_implicit_defaults, strip, one, ds)

    def get_operational(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
    ):
        return self.get(
            xpath, default, include_implicit_defaults, strip, one, ds="operational"
        )

    def apply(self):
        if self.ds != "running":
            super().delete_all(model)
        return self.conn.apply()

    def stop(self):
        self.netconf_conn.close_session()
        if self._thread != None:
            self._stop = True
            self._thread.join()
            self._thread = None

    def _loop(self, callback):
        while True:
            v = self.netconf_conn.take_notification(block=False, timeout=0.5)
            if v == None:
                if self._stop:
                    return
                else:
                    continue

            try:
                data = self.conn.xform(etree.fromstring(v.notification_xml))
            except etree.XSLTApplyError:
                logger.debug(f"failed to xform notification: {v.notification_xml}")
                continue
            callback(data)

    def subscribe_notifications(self, callback):
        if self._thread != None:
            raise Error("notification already subscribed")

        self.netconf_conn.create_subscription()
        self._thread = threading.Thread(target=self._loop, args=(callback,))

        self._stop = False
        self._thread.start()


class Connector(BaseConnector):
    def __init__(self, **kwargs):
        if "host" not in kwargs:
            raise Error("missing host option")
        schema_dir = kwargs.pop("schema_dir", None)
        if schema_dir == None:
            raise Error("missing schema_dir option")
        str2bool(kwargs, "hostkey_verify")
        self._connect_args = kwargs
        self.sess = self.new_session()
        self.conn = self.sess.netconf_conn
        self._models = {}
        # it is important to make sure the schema dir exists before
        # creating the libyang context. Otherwise, libyang won't
        # search for the schemas in the directory.
        Path(schema_dir).mkdir(parents=True, exist_ok=True)
        self.ctx = libyang.Context(schema_dir)

        data = self._get_remote_modules(schema_dir)

        logger.info("getting schemas...")

        for m in data["module"]:
            if m["name"] not in self._models:
                self._models[m["name"]] = []
            m["import-only"] = False
            m["filename"] = f"{m['name']}@{m['revision']}.yang"
            logger.debug(f"getting schema {m['filename']} ..")
            m["schema"] = get_schema(self.conn, schema_dir, m["name"], m["revision"])
            self._models[m["name"]].append(m)

        for m in data["import-only-module"]:
            if m["name"] not in self._models:
                self._models[m["name"]] = []
            m["import-only"] = True
            m["filename"] = f"{m['name']}@{m['revision']}.yang"
            logger.debug(f"getting schema {m['filename']} ..")
            m["schema"] = get_schema(self.conn, schema_dir, m["name"], m["revision"])
            self._models[m["name"]].append(m)

        logger.info("parsing schemas...")

        for k, ms in self._models.items():
            logger.debug(f"parsing {k} ..")
            for m in ms:
                if not m["import-only"]:
                    schema = m["schema"]
                    self.ctx.parse_module_str(schema)

        for m in self.ctx:
            logger.info(
                f"loaded module: {m}, revisions: {', '.join(str(r) for r in m.revisions())}"
            )

    def _get_remote_modules(self, schema_dir):
        schema = get_schema(self.conn, schema_dir, "ietf-yang-library", None)
        # we can't use libyang to parse the XML data of yang-library since
        # libyang handles yang-library information differently
        # use jsonxsl to do the parsing
        xformer = jsonxsl_xformer([("ietf-yang-library.yang", schema)], schema_dir)

        def xform(data):
            data = etree.fromstring(data.data_xml.encode())
            return json.loads(str(xformer(data)))

        data = self._get(
            "/ietf-yang-library:yang-library/*",
            {
                "ietf-yang-library": "urn:ietf:params:xml:ns:yang:ietf-yang-library",
            },
            "operational",
            xform,
        )
        if not data:
            raise Error("failed to get ietf-yang-library:yang-library")
        sets = list(data["ietf-yang-library:yang-library"]["module-set"])
        assert len(sets) > 0
        module_set = sets[0]
        if len(sets) > 1:
            logger.warning(
                f"more than 1 module-set. using the first one: {module_set['name']}"
            )
        return module_set

    def new_session(self, ds="running"):
        return Session(self, ds)

    @property
    def type(self):
        return "netconf"

    def xpath2xml(self, xpath, value=None):
        xpath = list(libyang.xpath_split(xpath))
        if len(xpath) == 0:
            return None
        node = xpath[0][1]
        model = xpath[0][0]
        v = self._models.get(model)
        if v:
            root = new_ele_ns(node, v[0]["namespace"])
        else:
            root = new_ele(node)

        cur = root
        for i, e in enumerate(xpath[1:]):
            if e[0]:
                v = self._models.get(e[0])
                cur = sub_ele_ns(cur, e[1], v[0]["namespace"])
            else:
                cur = sub_ele(cur, e[1])
            for cond in e[2]:
                ccur = cur
                for cc in cond[0].split("/"):
                    ccur = sub_ele(ccur, cc)
                ccur.text = cond[1]

        if value:
            cur.text = str(value)
        else:
            cur.set("{urn:ietf:params:xml:ns:netconf:base:1.0}operation", "delete")

        logger.debug(
            f"xpath: {xpath}, value: {value} xml: {etree.tostring(root).decode()}"
        )

        return root

    def get_ns_from_xpath(self, xpath):
        try:
            return {
                elem[0]: self._models.get(elem[0])[0]["namespace"]
                for elem in libyang.xpath_split(xpath)
                if elem[0]  # elem[0] == prefix
            }
        except TypeError:  # elem[0] not exist in self._modules
            return None

    @property
    def models(self):
        return self._models.keys()

    def set(self, xpath, value):
        v = self.xpath2xml(xpath, value)
        config = new_ele("config")
        config.append(v)
        logger.debug(f"xml: {etree.tostring(config).decode()}")
        return self.conn.edit_config(config)

    def delete(self, xpath):
        return self.set(xpath, None)

    def delete_all(self, model):
        m = self.ctx.get_module(model)
        for n in m:
            if n.keyword() in ["container", "leaf", "leaf-list", "list"]:
                self.delete(f"/{model}:{n.name()}")

    def apply(self):
        return self.conn.commit()

    def discard_changes(self):
        self.conn.discard_changes()

    # when xform is given, use it to xlate XML to Python dict.
    # Otherwise, use libyang to do the parsing
    def _get(self, xpath, nss, ds, xform=None):
        logger.debug(f"{xpath=}, {ds=}, {nss=}")
        options = {}
        if ds == "operational":
            v = self.conn.get(filter=("xpath", (nss, xpath)))
            options["get"] = True
        elif ds == "running":
            v = self.conn.get_config(source=ds, filter=("xpath", (nss, xpath)))
            options["getconfig"] = True
        else:
            raise Error(f"not supported ds: {ds}")

        logger.debug(f"data_xml: {v.data_xml}")
        if xform:
            data = xform(v)
        else:
            if not len(v.data):
                return None
            data = self.ctx.parse_data_mem(
                etree.tostring(v.data[0]), fmt="xml", **options
            ).print_dict()
        return data

    def get(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
        ds="running",
    ):
        nss = self.get_ns_from_xpath(xpath)
        if nss == None:
            return default
        if ds in ["running", "operational"]:
            data = self._get(xpath, nss, ds)
        else:
            return super().get(
                xpath, default, include_implicit_defaults, strip, one, ds
            )

        if data == None:
            return default

        assert len(data.keys()) < 2
        if len(data.keys()) == 1:
            key = list(data.keys())[0]
            data[key.split(":")[-1]] = data[key]

        if not strip:
            return data

        data = libyang.xpath_get(
            data, xpath, default=default, filter=ds == "operational"
        )
        if data and one:
            if len(data) == 1:
                data = data[0]
            elif len(data) > 1:
                raise Error(f"{xpath} matches more than one item: {data}")

        logger.debug(f"xpath: {xpath}, ds: {ds}, value: {data}")
        return data

    def get_operational(
        self,
        xpath,
        default=None,
        include_implicit_defaults=False,
        strip=True,
        one=False,
    ):
        return self.get(
            xpath, default, include_implicit_defaults, strip, one, ds="operational"
        )
