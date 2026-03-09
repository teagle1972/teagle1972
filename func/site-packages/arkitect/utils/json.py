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

import json
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterable,
    Generator,
)

from pydantic import BaseModel


def dump_json_str(obj: Any) -> str:
    """
    Converts an object to a JSON string.
    """
    return json.dumps(dump_json(obj), ensure_ascii=False, default=lambda x: str(x))


def dump_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: dump_json(v) for k, v in obj.items()}
    elif isinstance(obj, (tuple, list)):
        return [dump_json(v) for v in obj]
    elif isinstance(obj, BaseModel):
        return obj.model_dump(exclude_unset=True, exclude_none=True)
    elif isinstance(obj, (AsyncGenerator, Generator, AsyncIterable)):
        return str(obj)
    else:
        return obj


_MAX_DEPTH = 10


def dump_json_str_truncate(obj: Any, string_length_limit: int) -> str:
    """
    Only for trace
    Truncate all strings to prevent excessively
    long input/output (e.g., base64 images)
    """
    return json.dumps(
        dump_json_truncate(obj, string_length_limit),
        ensure_ascii=False,
        default=lambda x: str(x),
    )


def dump_json_truncate(obj: Any, string_length_limit: int, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:  # for safety
        return "max recursion depth exceeded"
    if isinstance(obj, dict):
        result_dict = {}
        for k, v in obj.items():
            value = dump_json_truncate(v, string_length_limit, depth + 1)
            if value is not None:
                result_dict[k] = value
        return result_dict
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, (AsyncGenerator, Generator, AsyncIterable)):
        return str(obj)
    elif isinstance(obj, (list, tuple)):
        return [
            dump_json_truncate(item, string_length_limit, depth + 1) for item in obj
        ]
    elif isinstance(obj, str):
        return obj[:string_length_limit]
    elif isinstance(obj, BaseModel) and hasattr(obj, "__dict__"):
        result_dict = {}
        for k, v in obj.__dict__.items():
            value = dump_json_truncate(v, string_length_limit, depth + 1)
            if value is not None:
                result_dict[k] = value
        return result_dict
    else:
        return obj
