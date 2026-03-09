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

import os
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    Optional,
    Tuple,
    Type,
    Union,
)

from pydantic import ValidationError
from volcenginesdkarkruntime._exceptions import ArkAPIError

from arkitect.core.client import Client
from arkitect.core.errors import (
    APIException,
    InternalServiceError,
    MissingParameter,
    parse_pydantic_error,
)
from arkitect.core.runtime import (
    Context,
    Request,
    Response,
)
from arkitect.launcher.runner import get_endpoint_config, get_runner
from arkitect.telemetry.trace import TraceConfig

from .common import parse_request, parse_response
from .initializer import initialize

StreamingResponse = AsyncIterator[str]
JsonResponse = Dict[str, Any]


class Environment(str, Enum):
    VEFAAS = "VeFaaS"
    LOCAL = "Local"


def _get_parameters(
    environment: Environment, *args: Any, **kwargs: Any
) -> Tuple[Union[Dict[str, Any], Request], Any]:
    if environment == Environment.LOCAL:
        if len(args) == 0:
            raise MissingParameter("request")
        return args[0], Context()
    else:
        if len(args) == 2:
            return args[0], args[1]
        if len(kwargs) == 2:
            event, context = kwargs.get("event", ""), kwargs.get("context", "")
            assert event and context, "No valid faas input"

            return event, context

        raise TypeError("No valid faas input")


def parse_function_request(
    environment: Environment,
    parameters: Union[Dict[str, Any], Request],
    endpoint_path: str,
    func: Callable,
) -> Request:
    # load request class type by signature
    endpoint_config = get_endpoint_config(
        endpoint_path=endpoint_path, runnable_func=func
    )
    request_cls = endpoint_config.get(endpoint_path, Request)

    if environment == Environment.LOCAL:
        # load args as it looks
        request: Request = (
            request_cls.model_validate(parameters)
            if isinstance(parameters, dict)
            else parameters
        )
    else:
        # transform the input args for vefaas deployment
        request = parse_request(
            event=parameters,
            request_cls=request_cls,
        )
    return request


def parse_function_response(
    environment: Environment,
    *,
    response: Optional[Response] = None,
    exception: Optional[APIException] = None,
) -> Union[Response, JsonResponse]:
    if environment == Environment.LOCAL:
        if exception:
            # error should be directly raised
            raise exception
        elif response:
            # response should be directly returned
            return response
    else:
        if exception:
            # error should return with http code
            return parse_response(
                status_code=exception.http_code,
                content=Response(error=exception.to_error()).model_dump_json(
                    exclude_none=True
                ),
            )
        elif response:
            # response should return with serialization
            return parse_response(
                status_code=200,
                content=response.model_dump_json(exclude_none=True),
            )
    return Response()


def bot_wrapper(
    endpoint_path: str = "/api/v3/bots/chat/completions",
    clients: Optional[Dict[str, Tuple[Type[Client], Any]]] = None,
    trace_on: bool = True,
    trace_config: Optional[TraceConfig] = None,
) -> Any:
    """
    This bot_wrapper is for launching vefaas function,
    to initialize the environment and translate request/response.
    Args:
        endpoint_path: The api path of the procode service for client to request
            e.g. https://{host}/api/v3/bots/chat/completions
        clients: The clients for the procode service,
                 each key stands for client name,
                 each value stands for the client initialize params.
            e.g. {
                "ark": (
                    AsyncArk,
                    {
                        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                        "max_retries": 3,
                    },
            )}
        trace_on: The option stands for using tracing, ref: https://opentelemetry.io/docs/
        if turn on, with @task decorator represents tracing
        the duration & input/output of the decorated function.
        trace_config: Detailed trace config for tracing
    """

    def wrapper(
        func: Callable,
    ) -> Callable[
        [Tuple[Any, ...], Dict[str, Any]],
        Union[
            Coroutine[Any, Any, Union[JsonResponse, StreamingResponse, Response]],
            JsonResponse,
        ],
    ]:
        def run_bot(
            *args: Any, **kwargs: Any
        ) -> Union[
            Coroutine[Any, Any, Union[JsonResponse, StreamingResponse, Response]],
            JsonResponse,
        ]:
            environment: Environment = Environment.VEFAAS
            if os.getenv("IS_LOCAL") is not None:
                environment = Environment.LOCAL

            # decode environment-related parameters
            parameters, context = _get_parameters(environment, *args, **kwargs)

            # initialize environment
            initialize(context, clients, trace_on, trace_config)

            # get runner for handler(handle sse & error code)
            runner = get_runner(func)
            try:
                # encode request
                request = parse_function_request(
                    environment, parameters, endpoint_path, func
                )
            except Exception as e:
                if isinstance(e, APIException):
                    runtime_exception: APIException = e
                elif isinstance(e, ValidationError):
                    runtime_exception = parse_pydantic_error(e)
                else:
                    runtime_exception = InternalServiceError(str(e))

                return parse_response(
                    status_code=runtime_exception.http_code,
                    content=Response(
                        error=runtime_exception.to_error()
                    ).model_dump_json(exclude_none=True),
                )

            async def entry() -> Union[JsonResponse, StreamingResponse, Response]:
                try:
                    # run function
                    if request.stream:
                        return runner.astream(request)
                    else:
                        response = await runner.arun(request)

                        return parse_function_response(environment, response=response)
                except Exception as e:
                    if isinstance(e, APIException):
                        runtime_exception: APIException = e
                    elif isinstance(e, ArkAPIError):
                        runtime_exception = APIException(
                            http_code=e.status_code
                            if hasattr(e, "status_code")
                            else 500,
                            code=e.code,
                            message=e.message,
                            parameter=e.param,
                            error_type=e.type,
                        )
                    elif isinstance(e, ValidationError):
                        runtime_exception = parse_pydantic_error(e)
                    else:
                        runtime_exception = InternalServiceError(str(e))

                    return parse_function_response(
                        environment, exception=runtime_exception
                    )

            return entry()

        return run_bot

    return wrapper
