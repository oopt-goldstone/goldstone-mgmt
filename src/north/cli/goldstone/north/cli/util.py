import base64
import struct


def dig_dict(data, keys):
    for key in keys:
        data = data.get(key)
        if not data:
            return data
    return data


def human_ber(item):
    return "{0:.2e}".format(struct.unpack(">f", base64.b64decode(item))[0])
