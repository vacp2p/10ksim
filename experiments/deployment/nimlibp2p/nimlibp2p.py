#!/usr/bin/env python3


import itertools
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import humanfriendly
from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field
from ruamel import yaml

from kube_utils import (
    cleanup_resources,
    get_cleanup_resources,
    get_future_time,
    helm_build_from_params,
    kubectl_apply,
    maybe_dir,
    poll_namespace_has_objects,
    str_to_timedelta,
    timedelta_until,
    wait_for_cleanup,
    wait_for_no_objs_in_namespace,
    wait_for_rollout,
    wait_for_time,
)

logger = logging.getLogger(__name__)

class Builder(BaseModel):
    pass
