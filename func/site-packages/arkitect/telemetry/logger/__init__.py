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
from typing import Any

from .common import LoggerName, Timer
from .logid import gen_log_id

__all__ = ["DEBUG", "INFO", "WARN", "ERROR", "Timer", "gen_log_id"]


def DEBUG(msg: str, *args: Any, **kwargs: Any) -> None:
    logging.getLogger(LoggerName.get()).debug(msg, stacklevel=2, *args, **kwargs)


def INFO(msg: str, *args: Any, **kwargs: Any) -> None:
    logging.getLogger(LoggerName.get()).info(msg, stacklevel=2, *args, **kwargs)


def WARN(msg: str, *args: Any, **kwargs: Any) -> None:
    logging.getLogger(LoggerName.get()).warn(msg, stacklevel=2, *args, **kwargs)


def ERROR(msg: str, *args: Any, **kwargs: Any) -> None:
    logging.getLogger(LoggerName.get()).error(msg, stacklevel=2, *args, **kwargs)
