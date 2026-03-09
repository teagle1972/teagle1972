# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import time
from enum import Enum
from typing import Any, Union

import six

from arkitect.utils.context import get_client_reqid, get_reqid


class LoggerName:
    logger_name = "root"

    @classmethod
    def set(cls: Any, name: str) -> None:
        cls.logger_name = name

    @classmethod
    def get(cls: Any) -> str:
        return cls.logger_name


class LogIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        logid = getattr(record, "tags", {}).get("_reqid")
        client_reqid = getattr(record, "tags", {}).get("_client_reqid")
        if logid:
            record._logid = logid
            record._client_reqid = client_reqid
            return True
        logid = get_reqid("-")
        client_reqid = get_client_reqid("-")
        record._logid = six.ensure_text(logid)
        record._client_reqid = six.ensure_text(client_reqid)
        return True


class RpcFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        tags = getattr(record, "tags", None)
        if not tags or not isinstance(tags, dict):
            return False
        record._rpc_tags = six.ensure_text(
            " ".join(sorted(["%s:%s" % (k, v) for k, v in tags.items()]))
        )
        return True


class TimeScale(Enum):
    SECOND = 0
    MILLI_SECOND = 1
    MICRO_SECOND = 2
    NANO_SECOND = 3


class TimeDelta(object):
    """
    TimeDelta, we only store data as millisecond for the object.
    """

    __slots__ = ["_delta"]

    _k_scale_second = 1
    _k_scale_milli = 1000
    _k_scale_micro = 1000000
    _k_scale_nano = 1000000000

    _scale_map = {
        TimeScale.SECOND: _k_scale_second,
        TimeScale.MILLI_SECOND: _k_scale_milli,
        TimeScale.MICRO_SECOND: _k_scale_micro,
        TimeScale.NANO_SECOND: _k_scale_nano,
    }

    def __init__(self, delta: float, scale: TimeScale = TimeScale.SECOND) -> None:
        """
        Args:
            delta, time delta.
            scale, input delta time scale.

        """
        self._delta = delta
        if scale != TimeScale.MILLI_SECOND:
            self._delta = delta * TimeDelta._k_scale_milli / TimeDelta._scale_map[scale]

    def as_second(self) -> float:
        return self._delta / TimeDelta._k_scale_milli

    def as_micro(self) -> float:
        return self._delta * TimeDelta._k_scale_micro / TimeDelta._k_scale_milli

    def as_nano(self) -> float:
        return self._delta * TimeDelta._k_scale_nano / TimeDelta._k_scale_milli

    def __repr__(self) -> str:
        return self._delta.__repr__()

    def __add__(self, other: Union[int, float, "TimeDelta"]) -> "TimeDelta":
        if not isinstance(other, (int, float, TimeDelta)):
            return NotImplemented
        if isinstance(other, TimeDelta):
            return TimeDelta(self._delta + other._delta, scale=TimeScale.MILLI_SECOND)
        else:
            return TimeDelta(self._delta + other, scale=TimeScale.MILLI_SECOND)

    def __sub__(self, other: Union[int, float, "TimeDelta"]) -> "TimeDelta":
        if not isinstance(other, (int, float, TimeDelta)):
            return NotImplemented
        if isinstance(other, TimeDelta):
            return TimeDelta(self._delta - other._delta, scale=TimeScale.MILLI_SECOND)
        else:
            return TimeDelta(self._delta - other, scale=TimeScale.MILLI_SECOND)

    def __rsub__(self, other: Union[int, float, "TimeDelta"]) -> "TimeDelta":
        if not isinstance(other, (int, float, TimeDelta)):
            return NotImplemented
        if isinstance(other, TimeDelta):
            return TimeDelta(other._delta - self._delta, scale=TimeScale.MILLI_SECOND)
        else:
            return TimeDelta(other - self._delta, scale=TimeScale.MILLI_SECOND)

    def __truediv__(
        self, other: Union[int, float, "TimeDelta"]
    ) -> Union["TimeDelta", float]:
        if not isinstance(other, (int, float, TimeDelta)):
            return NotImplemented
        if isinstance(other, TimeDelta):
            return TimeDelta(self._delta / other._delta, scale=TimeScale.MILLI_SECOND)
        else:
            return TimeDelta(self._delta / other, scale=TimeScale.MILLI_SECOND)

    def __mul__(self, other: Union[int, float, "TimeDelta"]) -> "TimeDelta":
        if not isinstance(other, (int, float, TimeDelta)):
            return NotImplemented
        if isinstance(other, TimeDelta):
            return TimeDelta(self._delta * other._delta, scale=TimeScale.MILLI_SECOND)
        else:
            return TimeDelta(self._delta * other, scale=TimeScale.MILLI_SECOND)


class Timer(object):
    """
    A timer do record performance.
    """

    def __init__(self) -> None:
        self._time = time.perf_counter()

    def reset(self) -> "Timer":
        """
        reset base time.
        """
        self._time = time.perf_counter()
        return self

    def elapsed(self, reset: bool = True) -> float:
        """
        By default, it will reset the base time to current time.
        """
        e = TimeDelta(time.perf_counter() - self._time).as_micro()
        if reset:
            self.reset()
        return e
