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
import struct
from typing import Optional

from pydantic import BaseModel

from arkitect.core.component.tts.constants import (
    DEFAULT_SPEAKER,
    FULL_CLIENT,
    HEADER_SIZE,
    JSON,
    NAMESPACE,
    NO_COMPRESSION,
    PROTOCAL_VERSION,
    WITH_EVENT,
)


class AudioParams(BaseModel):
    format: str = "mp3"
    sample_rate: int = 24000


class ConnectionParams(BaseModel):
    audio_params: AudioParams
    speaker: str = DEFAULT_SPEAKER


class ResponseEvent(BaseModel):
    event: Optional[int] = None
    audio_only: bool = False
    session_finished: bool = False
    session_id: Optional[str] = None
    connection_id: Optional[str] = None
    payload_msg: dict = {}
    payload_size: int = 0

    audio: bytes = b""


def _write_message(
    event: Optional[int],
    payload: str,
    connection_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bytes:
    event_bytes = struct.pack(">I", event)
    frame = event_bytes
    if connection_id is not None:
        connection_id_len = struct.pack(">I", len(connection_id))
        frame += connection_id_len + connection_id.encode("utf-8")
    if session_id is not None:
        session_id_len = struct.pack(">I", len(session_id))
        frame += session_id_len + session_id.encode("utf-8")
    payload_bytes = payload.encode("utf-8")
    payload_len_bytes = struct.pack(">I", len(payload_bytes))
    frame += payload_len_bytes + payload_bytes
    return frame


# Message Class
class Message:
    def __init__(
        self,
        message_type: int = FULL_CLIENT,
        type_flag: int = WITH_EVENT,
        session_id: Optional[str] = None,
        event: Optional[int] = None,
        connection_id: Optional[str] = None,
    ):
        self.type_and_flag_bits = message_type << 4 | type_flag
        self.msg_type = None
        self.event: Optional[int] = event
        self.session_id: Optional[str] = session_id
        self.connection_id: Optional[str] = connection_id
        self.sequence = None
        self.error_code = None
        self.payload: Optional[dict] = None

    def type_flag(self) -> int:
        return self.type_and_flag_bits & 0b00001111

    def write_start_connection(self) -> bytes:
        return self._write_header() + _write_message(event=self.event, payload="{}")

    def write_start_tts_session(self) -> bytes:
        return self._write_header() + _write_message(
            event=self.event,
            connection_id=self.connection_id,
            payload=json.dumps(self.payload),
        )

    def write_text_request(self) -> bytes:
        return self._write_header() + _write_message(
            event=self.event,
            session_id=self.session_id,
            payload=json.dumps(self.payload),
        )

    def write_finish_session(self) -> bytes:
        return self._write_header() + _write_message(
            event=self.event,
            session_id=self.session_id,
            payload=json.dumps(self.payload),
        )

    def write_finish_connection(self) -> bytes:
        return self._write_header() + _write_message(
            event=self.event,
            connection_id=self.connection_id,
            payload=json.dumps(self.payload),
        )

    def _write_header(self) -> bytes:
        header = bytearray(
            [
                PROTOCAL_VERSION << 4 | HEADER_SIZE,
                self.type_and_flag_bits,
                JSON << 4 | NO_COMPRESSION,
            ]
        )
        padding_size = HEADER_SIZE * 4 - len(header)
        if padding_size > 0:
            header.extend([0] * padding_size)
        return header


class TextRequest(BaseModel):
    text: str
    finished: bool


class TTSRequest(BaseModel):
    event: int
    namespace: str = NAMESPACE
    req_params: dict
