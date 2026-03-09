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

import inspect
from inspect import Signature
from typing import Any, AsyncIterable, Callable, Dict, Tuple, Type

from volcenginesdkarkruntime import AsyncArk

from arkitect.core.client import Client
from arkitect.core.component.llm import (
    ArkChatRequest,
)
from arkitect.core.runtime import (
    AsyncRunner,
    ChatAsyncRunner,
    CustomAsyncRunner,
    Request,
    RequestType,
    ResponseType,
)
from arkitect.telemetry.trace import task


@task()
def get_runner(
    runnable_func: Callable[[RequestType], AsyncIterable[ResponseType]],
) -> AsyncRunner:
    signature = inspect.signature(runnable_func)
    request_cls: Type[RequestType] = get_request_cls(signature)
    response_cls: Type[ResponseType] = get_response_cls(signature)

    if issubclass(request_cls, ArkChatRequest):
        return ChatAsyncRunner(runnable_func)  # type: ignore
    else:
        return CustomAsyncRunner(response_cls, runnable_func)


@task()
def get_endpoint_config(
    endpoint_path: str,
    runnable_func: Callable[[RequestType], AsyncIterable[ResponseType]],
) -> Dict[str, Type[RequestType]]:
    signature = inspect.signature(runnable_func)
    return {endpoint_path: get_request_cls(signature)}


@task()
def get_request_cls(signature: Signature) -> Type[RequestType]:
    parameters = signature.parameters.values()

    for param in parameters:
        annotation = param.annotation
        assert issubclass(annotation, Request), TypeError(
            "function request should be subclass of request"
        )
        return annotation

    raise Exception("should not reach here")


@task()
def get_response_cls(signature: Signature) -> Type[ResponseType]:
    return_cls = signature.return_annotation
    assert hasattr(return_cls, "__origin__") and issubclass(
        return_cls.__origin__, AsyncIterable
    ), TypeError("function response should be AsyncIterable")
    assert return_cls.__args__ and len(return_cls.__args__) == 1, TypeError(
        "function should return one value"
    )

    # skip response class check
    response_cls = return_cls.__args__[0]
    return response_cls


def get_default_client_configs() -> Dict[str, Tuple[Type[Client], Any]]:
    return {
        "chat": (
            AsyncArk,
            {
                "region": "cn-beijing",
                "ak": "xxx",
                "sk": "xxx",
                "api_key": "xxx",
            },
        ),
    }
