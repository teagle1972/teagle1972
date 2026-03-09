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

"errors"

from enum import Enum
from typing import Optional

from pydantic import BaseModel

__all__ = ["ErrorCode"]


class ReprEnum(Enum):
    """
    Only changes the repr(), leaving str() and format() to the mixed-in type.
    """


class StrEnum(str, ReprEnum):
    """
    Enum where members are also (and must be) strings
    """

    def __new__(cls, *values: str) -> "StrEnum":
        "values must already be of type `str`"
        if len(values) > 3:
            raise TypeError("too many arguments for str(): %r" % (values,))
        if len(values) == 1:
            # it must be a string
            if not isinstance(values[0], str):
                raise TypeError("%r is not a string" % (values[0],))
        if len(values) >= 2:
            # check that encoding argument is a string
            if not isinstance(values[1], str):
                raise TypeError("encoding must be a string, not %r" % (values[1],))
        if len(values) == 3:
            # check that errors argument is a string
            if not isinstance(values[2], str):
                raise TypeError("errors must be a string, not %r" % (values[2]))
        value = str(*values)
        member = str.__new__(cls, value)
        member._value_ = value
        return member

    def _generate_next_value_(self, start, count, last_values) -> str:  # type: ignore
        """
        Return the lower-cased version of the member name.
        """
        return self.lower()


class ErrorCode(StrEnum):
    http_code: int
    message: str
    error_type: str

    def __new__(
        cls,
        code: str,
        http_code: int,
        message: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> "ErrorCode":
        error_code = str.__new__(cls, code)
        error_code._value_ = code
        error_code.http_code = http_code  # type: ignore
        error_code.message = message or ""  # type: ignore
        error_code.error_type = error_type or ""  # type: ignore
        return error_code

    MissingParameter = (
        "MissingParameter",
        400,
        "The request failed because it is missing required parameters",
        "BadRequest",
    )
    InvalidParameter = (
        "InvalidParameter",
        400,
        "A parameter specified in the request is not valid: {parameter}",
        "BadRequest",
    )
    ResourceNotFound = (
        "ResourceNotFound",
        404,
        "The specified resource is not found",
        "NotFound",
    )
    RateLimitExceeded = (
        "RateLimitExceeded",
        429,
        "The Requests Per Minute(RPM) limit of the associated {resource_type} for your "
        "account has been exceeded.",
        "TooManyRequests",
    )
    ServerOverloaded = (
        "ServerOverloaded",
        429,
        "The service: {service} is currently unable to handle "
        "additional requests due to server overload.",
        "TooManyRequests",
    )

    SensitiveContentDetected = (
        "SensitiveContentDetected",
        400,
        "The request failed because the input text may contain sensitive information.",
        "BadRequest",
    )

    AuthenticationError = (
        "AuthenticationError",
        401,
        "The API key in the request is missing or invalid.",
        "Unauthorized",
    )

    AccessDenied = (
        "AccessDenied",
        403,
        "The request failed because you do not have access to the requested resource.",
        "Forbidden",
    )

    AccountOverdueError = (
        "AccountOverdueError",
        403,
        "The request failed because your account has an overdue balance.",
        "Forbidden",
    )
    QuotaExceeded = (
        "QuotaExceeded",
        429,
        "Your account {account_id} has exhausted its free trial "
        "quota for {resource_type}.",
        "TooManyRequests",
    )

    InternalServiceError = (
        "InternalServiceError",
        500,
        "The service encountered an unexpected internal error.",
        "InternalServerError",
    )

    Unknown = ("Unknown", 500, "Unknown error")

    ModelLoadingError = (
        "ModelLoadingError",
        429,
        "The request cannot be processed at this time because "
        "the model is currently being loaded",
        "TooManyRequests",
    )

    APITimeoutError = (
        "APITimeoutError",
        500,
        "Request timed out",
        "InternalServerError",
    )


class Error(BaseModel):
    code: str
    code_n: Optional[int] = None
    message: str


class ArkError(BaseModel):
    code: str
    message: str
    param: Optional[str] = None
    type: Optional[str] = None
