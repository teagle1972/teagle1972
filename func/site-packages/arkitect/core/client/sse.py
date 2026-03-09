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

from typing import AsyncIterator

from aiohttp import StreamReader


class AsyncSSEDecoder(object):
    """
    A class for decoding SSE response from a StreamReader.
    """

    def __init__(self, source: StreamReader) -> None:
        self.source = source

    async def _read(self) -> AsyncIterator[bytes]:
        data = b""
        async for chunk in self.source:
            for line in chunk.splitlines(True):
                data += line
                if data.endswith((b"\r\r", b"\n\n", b"\r\n\r\n")):
                    yield data
                    data = b""
        if data:
            yield data

    async def next(self) -> AsyncIterator[bytes]:
        """
        Decodes the next event from the SSE stream.
        """
        async for chunk in self._read():
            for line in chunk.splitlines():
                # skip comment
                if line.startswith(b":"):
                    continue

                if b":" in line:
                    field, value = line.split(b":", 1)
                else:
                    field, value = line, b""

                if field == b"data" and len(value) > 0:
                    yield value
