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

import logging
from typing import Optional, Union

from pydantic import ValidationError
from volcenginesdkarkruntime._exceptions import (
    ArkAPITimeoutError,
    ArkRateLimitError,
)

from arkitect.core.errors.errorcode import ErrorCode
from arkitect.telemetry.logger import ERROR
from arkitect.utils import context

from .errorcode import ArkError


class APIException(Exception):
    def __init__(
        self,
        message: str,
        code: Union[ErrorCode, str],
        parameter: Optional[str] = None,
        http_code: Optional[int] = 500,
        error_type: Optional[str] = "InternalServerError",
    ):
        super().__init__(message)
        self.message = f"{message} Request id: {context.get_reqid()}"
        self.resource_id = context.get_resource_id()
        self.account_id = context.get_account_id() or ""
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.http_code = (
            code.http_code if isinstance(code, ErrorCode) else (http_code or 500)
        )
        self.type = (
            code.error_type
            if isinstance(code, ErrorCode)
            else (error_type or "InternalServerError")
        )
        self.parameter = parameter

    def __str__(self) -> str:
        return (
            "Detailed exception information is listed below.\n"
            + "account_id: {}\n"
            + "resource_id: {}\n"
            + "code: {}\n"
            + "message: {}"
        ).format(self.account_id, self.resource_id, self.code, self.message)

    def to_error(self) -> ArkError:
        return ArkError(
            code=self.code, message=self.message, param=self.parameter, type=self.type
        )


class InternalServiceError(APIException):
    def __init__(self, message: str):
        ERROR(f"[Internal Error]: {message}")
        super().__init__(
            message=ErrorCode.InternalServiceError.message,
            code=ErrorCode.InternalServiceError,
        )


class InvalidParameter(APIException):
    def __init__(self, parameter: str, cause: Optional[str] = None):
        message = ErrorCode.InvalidParameter.message.format(parameter=parameter)
        if cause:
            message = f"{message}.{cause}"
        super().__init__(
            message=message, code=ErrorCode.InvalidParameter, parameter=parameter
        )


class MissingParameter(APIException):
    def __init__(self, parameter: Optional[str] = None):
        message = (
            f"{ErrorCode.MissingParameter.message}:{parameter}"
            if parameter
            else str(ErrorCode.MissingParameter.message)
        )
        super().__init__(
            message=message, code=ErrorCode.MissingParameter, parameter=parameter
        )


class ResourceNotFound(APIException):
    def __init__(self, resource_type: Optional[str] = None):
        message = (
            f"{ErrorCode.ResourceNotFound.message}:{resource_type}"
            if resource_type
            else str(ErrorCode.ResourceNotFound.message)
        )
        super().__init__(
            message,
            code=ErrorCode.ResourceNotFound,
            parameter=resource_type,
        )


class RateLimitExceeded(APIException):
    def __init__(self, resource_type: str):
        message = ErrorCode.RateLimitExceeded.message.format(
            resource_type=resource_type
        )
        super().__init__(
            message,
            code=ErrorCode.RateLimitExceeded,
            parameter=resource_type,
        )


class ServerOverloaded(APIException):
    def __init__(self, service: str):
        message = ErrorCode.ServerOverloaded.message.format(service=service)
        super().__init__(
            message,
            code=ErrorCode.ServerOverloaded,
            parameter=service,
        )


class AuthenticationError(APIException):
    def __init__(self, cause: Optional[str] = None):
        message = ErrorCode.AuthenticationError.message
        if cause:
            message = f"{message} {cause}"
        super().__init__(
            message=message,
            code=ErrorCode.AuthenticationError,
        )


class AccessDenied(APIException):
    def __init__(self, cause: Optional[str] = None):
        message = ErrorCode.AccessDenied.message
        if cause:
            message = f"{message}.{cause}"
        super().__init__(
            message,
            code=ErrorCode.AccessDenied,
        )


class QuotaExceeded(APIException):
    def __init__(self, account_id: str, resource_type: str):
        message = ErrorCode.QuotaExceeded.message.format(
            account_id=account_id, resource_type=resource_type
        )
        super().__init__(message, code=ErrorCode.QuotaExceeded, parameter=resource_type)


class SensitiveContentDetected(APIException):
    def __init__(self, message: str):
        super().__init__(message, code=ErrorCode.SensitiveContentDetected)


class AccountOverdueError(APIException):
    def __init__(self, message: str):
        super().__init__(message, code=ErrorCode.AccountOverdueError)


class APITimeoutError(APIException):
    def __init__(self, message: str):
        ERROR(f"[API timeout error]: {message}")
        super().__init__(
            message=ErrorCode.APITimeoutError.message,
            code=ErrorCode.APITimeoutError,
        )


FALLBACK_EXCEPTIONS = (
    APITimeoutError,
    ArkAPITimeoutError,
    RateLimitExceeded,
    ArkRateLimitError,
)


def parse_pydantic_error(
    e: ValidationError,
) -> Union[MissingParameter, InvalidParameter]:
    try:
        err = e.errors()[-1]
        err_type, err_loc = err.get("type", ""), err.get("loc", ("",))
        if err_type == "missing":
            return MissingParameter(str(err_loc[-1]))
        else:
            return InvalidParameter(str(err_loc[-1]))
    except Exception as e:
        logging.error(f"parse pydantic error:{e}")
        return InvalidParameter("request")
