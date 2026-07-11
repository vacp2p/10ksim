def flatten(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from flatten(value)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            yield from flatten(value)
    else:
        yield obj
