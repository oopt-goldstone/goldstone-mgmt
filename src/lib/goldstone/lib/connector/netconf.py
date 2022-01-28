from .base import (
    Connector as BaseConnector,
    Session as BaseSession,
    Node,
    Error,
)

import libyang
import logging
import urllib.parse
from functools import cache
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


logger = logging.getLogger(__name__)


def str2bool(d, key):
    v = d.get(key)
    if v == "false":
        d[key] = False
    elif v == "true":
        d[key] = True


def get_schema(conn, model, cache_dir=None):
    cache_file = Path(f"{cache_dir}/schema/{model}.yang") if cache_dir else None
    if cache_file and cache_file.exists():
        with cache_file.open() as f:
            return f.read()

    schema = conn.get_schema(identifier=model)
    schema = schema._data
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w") as f:
            f.write(schema)
    return schema


def jsonxsl_xformer(models, cache_dir=None):
    cache_file = Path(f"{cache_dir}/xsl/goldstone-json.xsl") if cache_dir else None
    if cache_file and cache_file.exists():
        with cache_file.open() as f:
            xslt = f.read()
    else:
        repos = repository.FileRepository()

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

        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with cache_file.open("w") as f:
                f.write(xslt)

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
        cache_dir = kwargs.pop("cache_dir", None)
        str2bool(kwargs, "hostkey_verify")
        self._connect_args = kwargs
        self.sess = self.new_session()
        self.conn = self.sess.netconf_conn
        self._models = {}
        xform_models = []

        for cap in self.conn.server_capabilities:
            t = urllib.parse.urlparse(cap)
            q = [v.split("=") for v in t.query.split("&") if v]
            q = {q[0]: q[1] for q in q}
            m = q.get("module")
            if not m:
                continue

            if t.scheme == "http":
                ns = cap.split("?")[0]
            elif t.scheme == "urn":
                ns = f"urn:{t.path}"
            else:
                raise Error(f"unsupported scheme: {t.scheme}")
            self._models[m] = {"query": q, "ns": ns}

            schema = get_schema(self.conn, m, cache_dir)

            xform_models.append((m + ".yang", schema))
            self._models[m]["schema"] = schema

        ctx = libyang.Context()
        failed = []
        for k, m in self._models.items():
            schema = m.get("schema")
            if schema:
                try:
                    mm = ctx.parse_module_str(schema)
                except libyang.util.LibyangError as e:
                    # depends on the order loading may fail due to dependency
                    failed.append(m)

        # try loading the failed module again
        for f in failed:
            mm = ctx.parse_module_str(f["schema"])

        self.ctx = ctx

        f = jsonxsl_xformer(xform_models, cache_dir)
        self.xform = lambda v: json.loads(str(f(v)))

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
            root = new_ele_ns(node, v["ns"])
        else:
            root = new_ele(node)

        cur = root
        for i, e in enumerate(xpath[1:]):
            cur = sub_ele(cur, e[1])
            for cond in e[2]:
                ccur = cur
                for cc in cond[0].split("/"):
                    ccur = sub_ele(ccur, cc)
                ccur.text = cond[1]

        if value:
            cur.text = value
        else:
            cur.set("{urn:ietf:params:xml:ns:netconf:base:1.0}operation", "delete")

        logger.debug(
            f"xpath: {xpath}, value: {value} xml: {etree.tostring(root).decode()}"
        )

        return root

    def get_ns_from_xpath(self, xpath):
        return {
            elem[0]: self._models.get(elem[0])["ns"]
            for elem in libyang.xpath_split(xpath)
            if elem[0]  # elem[0] == prefix
        }

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
        logger.debug(f"{xpath=}, {ds=}, {nss=}")

        if ds == "operational":
            v = self.conn.get(filter=("xpath", (nss, xpath)))
        elif ds == "running":
            v = self.conn.get_config(source=ds, filter=("xpath", (nss, xpath)))
        else:
            super().get(xpath, default, include_implicit_defaults, strip, one, ds)

        logger.debug(f"data_xml: {v.data_xml}")

        data = self.xform(etree.fromstring(v.data_xml.encode()))

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
