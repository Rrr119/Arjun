import os

import arjun.core.config as mem
from arjun.core.utils import compatible_path, reader


def _db_dir():
    return compatible_path(
        mem.__file__.replace(compatible_path('/core/config.py'), '/db')
    )


def _load(name):
    path = os.path.join(_db_dir(), name)
    return set(reader(path, mode='lines'))


def build_tiers(words):
    """
    splits a wordlist into frequency tiers, high-frequency names first

    the bundled small/medium lists are subsets ordered by real-world
    frequency, so they are used as tier boundaries; words only present in
    the large list or a custom wordlist form the final tier. Tiers share
    no names and keep their original relative order.
    returns list of lists
    """
    words = list(dict.fromkeys(words))
    word_path = mem.var.get('wordlist', '')
    bundled = word_path.startswith(_db_dir())
    if not bundled:
        return [words] if words else []
    small = _load('small.txt')
    medium = _load('medium.txt')
    tiers = [[], [], []]
    for word in words:
        if word in small:
            tiers[0].append(word)
        elif word in medium:
            tiers[1].append(word)
        else:
            tiers[2].append(word)
    return [tier for tier in tiers if tier]


def tier_plan(words):
    """
    builds the scan plan according to the --adaptive setting
    returns list of wordlists, one per stage
    """
    if mem.var.get('adaptive'):
        return build_tiers(words)
    return [list(words)]
