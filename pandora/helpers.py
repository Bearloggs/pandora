#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

from datetime import timedelta
from enum import Enum, unique, auto
from functools import lru_cache
from typing import Dict, List, Optional, Union, Any

import yaml

from .default import get_homedir
from .role import Role


@unique
class Status(Enum):
    WAITING = auto()
    RUNNING = auto()
    OKAY = auto()
    WARN = auto()
    ALERT = auto()
    ERROR = auto()
    DEACTIVATE = auto()
    DELETED = auto()


@unique
class TypeObservable(Enum):
    DOMAIN = auto()
    IPV4 = auto()
    IPV6 = auto()
    EMAIL = auto()
    IBAN = auto()


@lru_cache(64)
def allowlist_default() -> List[str]:
    with (get_homedir() / 'config' / 'allowlist.yml').open() as config_file:
        config = yaml.safe_load(config_file.read())
    return config['allowlist']


@lru_cache(64)
def roles_from_config() -> Dict[str, Role]:
    with (get_homedir() / 'config' / 'roles.yml').open() as config_file:
        config = yaml.safe_load(config_file.read())
    to_return = {}
    for r in config['roles']:
        actions = {key[4:]: value for key, value in r.items() if key.startswith('can_')}
        role = Role(name=r['name'], description=r['description'], actions=actions)
        to_return[r['name']] = role
    return to_return


@lru_cache(64)
def workers() -> Dict[str, Any]:
    with (get_homedir() / 'config' / 'workers.yml').open() as config_file:
        config = yaml.safe_load(config_file.read())
    return config['workers']


def make_bool(value: Optional[Union[bool, int, str]]) -> bool:
    if value in [True, 1, '1']:
        return True
    return False


def make_bool_for_redis(value: Optional[bool]) -> int:
    if value is True:
        return 1
    return 0


def expire_in_sec(time: Optional[Union[str, int]]) -> Optional[int]:
    """
    Try to parse time value and return the amount of seconds.
    :param time: time value to parse
    :return: seconds until expire
    """
    if time is None:
        return None
    match = re.fullmatch(r'(\d+)([smhd]?)', str(time))
    assert match is not None, f"impossible to parse cache '{time}'"
    if not match.group(2) or match.group(2) == 's':
        return int(timedelta(seconds=int(match.group(1))).total_seconds())
    elif match.group(2) == 'm':
        return int(timedelta(minutes=int(match.group(1))).total_seconds())
    elif match.group(2) == 'h':
        return int(timedelta(hours=int(match.group(1))).total_seconds())
    elif match.group(2) == 'd':
        return int(timedelta(days=int(match.group(1))).total_seconds())
    return None