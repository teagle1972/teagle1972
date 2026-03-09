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

import asyncio
import sys
from typing import Any, Coroutine, TypeVar

_T = TypeVar("_T")


def get_event_loop(func: Coroutine[Any, Any, _T], debug: bool = False) -> _T:
    # uvloop is unsupported for windows
    if sys.platform != "win32":
        import uvloop

        return uvloop.run(func, debug=debug)
    else:
        return asyncio.run(func, debug=debug)
