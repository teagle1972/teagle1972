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
import logging
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Awaitable, Callable

import anyio
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from arkitect.telemetry.logger import DEBUG, INFO, WARN, gen_log_id
from arkitect.utils.context import (
    get_client_reqid,
    get_reqid,
    get_start_time,
    set_client_reqid,
    set_headers,
    set_reqid,
    set_start_time,
)


@dataclass
class LogIdMiddleware:
    app: "ASGIApp"
    client_header_name: str = "x-client-request-id"
    header_name: str = "x-request-id"

    generator: Callable[[], str] = field(default=lambda: gen_log_id())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Load log ID from headers if present. Generate one otherwise.
        And put it into context.
        """
        set_start_time(time.perf_counter())
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        headers[self.header_name] = headers.get(
            "X-Faas-Request-Id", headers.get(self.header_name, self.generator())
        )
        headers[self.client_header_name] = headers.get(
            self.client_header_name.lower(), headers[self.header_name]
        )

        set_client_reqid(headers[self.client_header_name])
        set_reqid(headers[self.header_name])
        set_headers(headers)

        async def handle_outgoing_request(message: "Message") -> None:
            if message["type"] == "http.response.start" and get_reqid():
                headers = MutableHeaders(scope=message)
                headers.append(self.header_name, get_reqid())
                headers.append(self.client_header_name, get_client_reqid())

            await send(message)
            logging.debug(
                f"[{get_reqid()}] out app cost={time.perf_counter() - get_start_time()}"
            )

        await self.app(scope, receive, handle_outgoing_request)
        return


@dataclass
class ListenDisconnectionMiddleware:
    app: "ASGIApp"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Cancel the request if the client disconnected.
        """
        INFO("listen disconnection middleware called.")

        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request_received, response_sent = asyncio.Event(), asyncio.Event()

        async def _receive() -> Message:
            message = await receive()
            DEBUG(f"receive message={message}")
            if message["type"] == "http.request" and not message.get(
                "more_body", False
            ):
                request_received.set()
            return message

        async def _send(message: Message) -> None:
            DEBUG(f"send message={message}")
            if message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                response_sent.set()
            await send(message)

        async def listen_for_disconnect() -> None:
            await request_received.wait()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    if not response_sent.is_set():
                        WARN("request canceled before response finished.")
                    break

        async with anyio.create_task_group() as task_group:

            async def wrap(func: Callable[[], Awaitable[None]]) -> None:
                await func()
                task_group.cancel_scope.cancel()

            task_group.start_soon(wrap, partial(self.app, scope, _receive, _send))
            await wrap(listen_for_disconnect)

        return
