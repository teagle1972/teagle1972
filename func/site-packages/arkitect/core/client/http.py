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

from typing import Type

import fastapi
from httpx import Timeout
from pydantic import ValidationError
from volcenginesdkarkruntime import AsyncArk

from arkitect.core.errors import InvalidParameter, parse_pydantic_error
from arkitect.core.runtime import RequestType

from .base import get_client_pool


def default_ark_client() -> AsyncArk:
    """
    Retrieves or creates an instance of the AsyncArk client.

    This function attempts to fetch an existing client from the client pool.
    If no client is found, it creates a new instance of the AsyncArk client
    with a specified timeout configuration.

    Returns:
        AsyncArk: An instance of the AsyncArk client.
    """
    client_pool = get_client_pool()
    client: AsyncArk = client_pool.get_client("ark")  # type: ignore
    if not client:
        client = AsyncArk(timeout=Timeout(connect=1.0, timeout=60.0))
    return client


async def load_request(
    http_request: fastapi.Request,
    req_cls: Type[RequestType],
) -> RequestType:
    """
    Loads and validates a request from a FastAPI HTTP request.
    """
    if "content-type" not in http_request.headers:
        raise InvalidParameter("Invalid request: missing content-type")
    content_type, body = (
        http_request.headers.get("content-type", ""),
        await http_request.body(),
    )
    media_type = content_type.split(";")[0].strip()
    try:
        if media_type == "application/json":
            return req_cls.model_validate_json(body)
    except ValidationError as e:
        raise parse_pydantic_error(e)
    raise InvalidParameter(f"Invalid request: invalid content-type={content_type}")
