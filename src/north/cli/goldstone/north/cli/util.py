def dig_dict(data, keys):
    for key in keys:
        data = data.get(key)
        if not data:
            return data
    return data
