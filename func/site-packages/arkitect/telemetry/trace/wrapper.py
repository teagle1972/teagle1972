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

import contextvars
import inspect
import time
from functools import wraps
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Iterable,
    Optional,
    Tuple,
    TypeVar,
)

from opentelemetry import trace

from arkitect.telemetry.trace.attributes import set_trace_attributes
from arkitect.utils import aenumerate
from arkitect.utils.context import (
    get_account_id,
    get_client_reqid,
    get_reqid,
    get_resource_id,
    get_resource_type,
)

T = TypeVar("T", covariant=True)
tracer = trace.get_tracer(__name__)
_current_span_context: contextvars.ContextVar = contextvars.ContextVar(
    "current_span_context"
)
_current_span_context_req: contextvars.ContextVar = contextvars.ContextVar(
    "current_span_context_req", default=""
)


def get_remote_func(func):  # type: ignore
    try:
        import ray

        return ray.remote(func)
    except ImportError:
        raise ModuleNotFoundError(
            "Could not import ray python package. "
            "Please install it with `pip install ray`."
        )


def _update_kwargs(args: Any, kwargs: Any, func: Callable) -> Dict[Any, Any]:
    if kwargs is None:
        kwargs = {}
    if args is None:
        return kwargs
    try:
        return {**kwargs, **dict(zip(func.__code__.co_varnames, args))}
    except Exception:
        return {"args": args}


def task(
    distributed: bool = False,
    watch_io: bool = True,
    trace_all: bool = True,
    custom_attributes: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Decorator that wraps a function with tracing and exception handling.

    Args:
        distributed : Whether the function is distributed.
        watch_io : Whether to watch input and output.
        trace_all : Whether to trace all iterations.
        custom_attributes : Custom attributes to add to the trace.
    """

    def task_wrapper(func):  # type: ignore
        async def async_exec(*args: Any, **kwargs: Any) -> Any:
            _init_trace_context()

            parent_ctx = _current_span_context.get(None)
            with tracer.start_as_current_span(
                name=func.__qualname__, context=parent_ctx
            ) as span:
                _current_span_context.set(trace.set_span_in_context(span))

                input = _update_kwargs(args, kwargs, func)
                try:
                    result = await (get_remote_func(func) if distributed else func)(
                        *args, **kwargs
                    )
                    set_trace_attributes(
                        span,
                        status_code=trace.StatusCode.OK,
                        input=input if watch_io else "",
                        output=result if watch_io else "",
                        resource_type=get_resource_type(),
                        resource_id=get_resource_id(),
                        request_id=get_reqid(),
                        client_request_id=get_client_reqid(),
                        account_id=get_account_id(),
                        custom_attributes=custom_attributes,
                    )

                    _current_span_context.set(parent_ctx)
                    return result
                except Exception as e:
                    handle_exception(span, e, input)
                    raise e

        def sync_exec(*args: Any, **kwargs: Any) -> Any:
            _init_trace_context()

            parent_ctx = _current_span_context.get(None)
            with tracer.start_as_current_span(
                name=func.__qualname__, context=parent_ctx
            ) as span:
                _current_span_context.set(trace.set_span_in_context(span))

                input = _update_kwargs(args, kwargs, func)
                try:
                    result = func(*args, **kwargs)
                    set_trace_attributes(
                        span,
                        status_code=trace.StatusCode.OK,
                        input=input if watch_io else "",
                        output=result if watch_io else "",
                        resource_type=get_resource_type(),
                        resource_id=get_resource_id(),
                        request_id=get_reqid(),
                        client_request_id=get_client_reqid(),
                        account_id=get_account_id(),
                        custom_attributes=custom_attributes,
                    )

                    _current_span_context.set(parent_ctx)
                    return result
                except Exception as e:
                    handle_exception(span, e, input)
                    raise e

        @wraps(func)
        async def async_iter_task(*args: Any, **kwargs: Any) -> AsyncGenerator[T, None]:
            _init_trace_context()

            root_parent_ctx, root_span = _get_span_with_context(
                func.__qualname__ + ".root"
            )
            last_resp = None
            input = _update_kwargs(args, kwargs, func)

            async def iter_entry() -> AsyncGenerator[T, None]:
                parent_ctx = _current_span_context.get()
                span = tracer.start_span(
                    name=func.__qualname__ + ".first_iter",
                    start_time=time.time_ns(),
                    context=parent_ctx,
                )

                try:
                    async for i, resp in aenumerate(func(*args, **kwargs)):  # type: ignore
                        if i == 0 or trace_all:
                            set_trace_attributes(
                                span,
                                status_code=trace.StatusCode.OK,
                                input=input if (watch_io and i == 0) else "",
                                output=resp if watch_io else "",
                                resource_type=get_resource_type(),
                                resource_id=get_resource_id(),
                                request_id=get_reqid(),
                                client_request_id=get_client_reqid(),
                                account_id=get_account_id(),
                                merge_output=True,
                                custom_attributes=custom_attributes,
                            )
                            if i == 0:
                                span.end(end_time=time.time_ns())
                            else:
                                _return_span_with_context(parent_ctx, span)
                        yield resp

                        if trace_all:
                            parent_ctx, span = _get_span_with_context(func.__qualname__)

                except Exception as e:
                    if not trace_all:
                        span = tracer.start_span(
                            name=func.__qualname__, start_time=time.time_ns()
                        )
                    handle_exception(span, e, input)
                    raise e
                finally:
                    _return_span_with_context(parent_ctx, span)

            try:
                async for resp in iter_entry():
                    last_resp = resp
                    yield resp

            except Exception as e:
                raise e

            finally:
                set_trace_attributes(
                    root_span,
                    status_code=trace.StatusCode.OK,
                    input=input if watch_io else "",
                    output=last_resp if watch_io else "",
                    resource_type=get_resource_type(),
                    resource_id=get_resource_id(),
                    request_id=get_reqid(),
                    client_request_id=get_client_reqid(),
                    account_id=get_account_id(),
                    merge_output=True,
                    custom_attributes=custom_attributes,
                )
                _return_span_with_context(root_parent_ctx, root_span)

        @wraps(func)
        def iter_task(*args: Any, **kwargs: Any) -> Iterable[T]:
            _init_trace_context()

            root_parent_ctx, root_span = _get_span_with_context(
                func.__qualname__ + ".root"
            )
            last_resp = None
            input = _update_kwargs(args, kwargs, func)

            def iter_entry() -> Iterable[T]:
                parent_ctx = _current_span_context.get()
                span = tracer.start_span(
                    name=func.__qualname__ + ".first_iter",
                    start_time=time.time_ns(),
                    context=parent_ctx,
                )

                try:
                    for i, resp in enumerate(func(*args, **kwargs)):
                        if i == 0 or trace_all:
                            set_trace_attributes(
                                span,
                                status_code=trace.StatusCode.OK,
                                input=input if (watch_io and i == 0) else "",
                                output=resp if watch_io else "",
                                resource_type=get_resource_type(),
                                resource_id=get_resource_id(),
                                request_id=get_reqid(),
                                client_request_id=get_client_reqid(),
                                account_id=get_account_id(),
                                merge_output=True,
                                custom_attributes=custom_attributes,
                            )
                            if i == 0:
                                span.end(end_time=time.time_ns())
                            else:
                                _return_span_with_context(parent_ctx, span)

                        yield resp
                        if trace_all:
                            parent_ctx, span = _get_span_with_context(func.__qualname__)

                except Exception as e:
                    if not trace_all:
                        span = tracer.start_span(
                            name=func.__qualname__, start_time=time.time_ns()
                        )
                    handle_exception(span, e, input)
                    raise e
                finally:
                    set_trace_attributes(
                        span,
                        status_code=trace.StatusCode.OK,
                        input=input if watch_io else "",
                        output=last_resp if watch_io else "",
                        resource_type=get_resource_type(),
                        resource_id=get_resource_id(),
                        request_id=get_reqid(),
                        client_request_id=get_client_reqid(),
                        account_id=get_account_id(),
                        merge_output=True,
                        custom_attributes=custom_attributes,
                    )
                    _return_span_with_context(parent_ctx, span)

            try:
                for resp in iter_entry():
                    last_resp = resp
                    yield resp
            except Exception as e:
                raise e
            finally:
                _return_span_with_context(root_parent_ctx, root_span)

        if inspect.isasyncgenfunction(func):
            return async_iter_task
        elif inspect.isgeneratorfunction(func):
            return iter_task
        elif inspect.iscoroutinefunction(func) or distributed:
            return async_exec
        else:
            return sync_exec

    return task_wrapper


def handle_exception(span: trace.Span, exception: Exception, args: Any) -> None:
    set_trace_attributes(
        span,
        status_code=trace.StatusCode.ERROR,
        input=args,
        output="",
        resource_type=get_resource_type(),
        resource_id=get_resource_id(),
        request_id=get_reqid(),
        account_id=get_account_id(),
        client_request_id=get_client_reqid(),
    )
    span.record_exception(exception)


def _init_trace_context() -> None:
    context_req = _current_span_context_req.get("")
    if context_req != get_reqid():
        _current_span_context.set(None)
        _current_span_context_req.set(get_reqid())


def _get_span_with_context(name: str) -> Tuple[Any, Any]:
    parent_ctx = _current_span_context.get()
    span = tracer.start_span(
        name=name,
        start_time=time.time_ns(),
        context=parent_ctx,
    )
    _current_span_context.set(trace.set_span_in_context(span))

    return parent_ctx, span


def _return_span_with_context(parent_ctx: Any, span: Any) -> None:
    _current_span_context.set(parent_ctx)
    span.end(end_time=time.time_ns())
