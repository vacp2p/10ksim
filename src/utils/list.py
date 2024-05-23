# Python Import
from itertools import chain
from typing import List


def order_by_groups(list_to_order: List) -> List:
    # TODO: change this to a more generic function
    def get_default_format_id(val):
        return int(val.split('-')[1].split('_')[0])

    nodes = []
    bootstrap = []
    midstrap = []
    others = []
    for item in list_to_order:
        if item.startswith('nodes'):
            nodes.append(item)
        elif item.startswith('bootstrap'):
            bootstrap.append(item)
        elif item.startswith('midstrap'):
            midstrap.append(item)
        else:
            others.append(item)
    nodes.sort(key=get_default_format_id)
    bootstrap.sort(key=get_default_format_id)
    midstrap.sort(key=get_default_format_id)

    return list(chain(others, bootstrap, midstrap, nodes))
