import base64
import struct
from natsort import natsorted
import re


def dig_dict(data, keys):
    for key in keys:
        data = data.get(key)
        if not data:
            return data
    return data


def human_ber(item):
    return "{0:.2e}".format(struct.unpack(">f", base64.b64decode(item))[0])


def object_names(session, xpath, ptn=None):
    data = session.get_operational(f"{xpath}/name", [])

    if ptn:
        try:
            ptn = re.compile(ptn)
        except re.error:
            raise InvalidInput(f"failed to compile {ptn} as a regular expression")
        f = ptn.match
    else:
        f = lambda _: True
    return natsorted(v for v in data if f(v))


def get_object_list(session, xpath, datastore):
    imp = datastore == "operational"
    objects = session.get(xpath, [], ds=datastore, include_implicit_defaults=imp)
    return natsorted(objects, key=lambda x: x["name"])
