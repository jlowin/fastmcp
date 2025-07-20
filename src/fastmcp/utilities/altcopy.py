import json
from copy import copy as copyBuiltin


def copy(x):
    """Shallow copy operation on arbitrary Python objects."""
    return copyBuiltin(x)


def deepcopy(x, memo=None, _nil=[]):
    """Deep copy operation on arbitrary Python objects.
    function signature is the same as Python builtin copy.deepcopy() for compatibility.
    replacing deepcopy implementation from builtin copy.deepcopy into json.dumps+loads to get faster.
    """
    return json.loads(json.dumps(x, ensure_ascii=False))
