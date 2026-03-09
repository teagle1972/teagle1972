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

import gzip
import json
from typing import Union

from arkitect.core.component.tts.constants import (
    GZIP,
    INT_SIZE,
    JSON,
    NO_SERIALIZATION,
    WITH_EVENT,
    EventConnectionFailed,
    EventConnectionFinished,
    EventConnectionStarted,
    EventFinishConnection,
    EventSessionFinished,
    EventStartConnection,
)
from arkitect.core.component.tts.model import ResponseEvent


def contain_event(flags: int) -> bool:
    return flags == WITH_EVENT


def parse_response(res: Union[str, bytes]) -> ResponseEvent:
    """
    protocol_version(4 bits), header_size(4 bits),
    message_type(4 bits), message_type_specific_flags(4 bits)
    serialization_method(4 bits) message_compression(4 bits)
    reserved （8bits) reserved(8bits)
    header_extensions header extension(size = 8 * 4 * (header_size - 1) )
    payload same as http body
    """
    if isinstance(res, str):
        res = res.encode("utf-8")
    header_size = res[0] & 0x0F
    message_type_specific_flags = res[1] & 0x0F
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0F
    ptr = header_size * 4
    result = ResponseEvent()
    if contain_event(message_type_specific_flags):
        event = int.from_bytes(res[ptr : ptr + INT_SIZE], "big", signed=True)
        ptr += 4
        result.event = event
        if event == EventSessionFinished:
            result.session_finished = True
        if event not in [
            EventStartConnection,
            EventFinishConnection,
            EventConnectionStarted,
            EventConnectionFailed,
            EventConnectionFinished,
        ]:
            session_id_len = int.from_bytes(
                res[ptr : ptr + INT_SIZE], "big", signed=False
            )
            ptr += 4
            session_id = res[ptr : ptr + session_id_len]
            ptr += session_id_len
            result.session_id = session_id.decode("utf-8")
        if event in [
            EventConnectionStarted,
            EventConnectionFailed,
            EventConnectionFinished,
        ]:
            connection_id_len = int.from_bytes(
                res[ptr : ptr + INT_SIZE], "big", signed=False
            )
            ptr += 4
            connection_id = res[ptr : ptr + connection_id_len]
            ptr += connection_id_len
            result.connection_id = connection_id.decode("utf-8")
    payload_size = int.from_bytes(res[ptr : ptr + INT_SIZE], "big", signed=True)
    payload = res[ptr + INT_SIZE :]
    payload_msg = payload

    if message_compression == GZIP:
        payload_msg = gzip.decompress(payload_msg)
    if serialization_method == JSON:
        result.payload_msg = json.loads(payload_msg)
    elif serialization_method == NO_SERIALIZATION:
        result.audio_only = True
        result.audio = payload_msg
    result.payload_size = payload_size
    return result
