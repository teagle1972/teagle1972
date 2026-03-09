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

import random
from datetime import datetime

time_fmt = "%Y%m%d%H%M%S"


def gen_log_id() -> str:
    """
    Generates a unique log ID.

    This function creates a log ID by combining
    the current date and time with a random number.
    The date and time are formatted as YYYYMMDDHHMMSS,
    and the random number is a 20-digit hexadecimal number.
    """
    return datetime.now().strftime(time_fmt) + format(
        random.randint(0, 2**64 - 1), "020X"
    )
