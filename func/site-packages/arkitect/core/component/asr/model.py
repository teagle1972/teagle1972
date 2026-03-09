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

from typing import List, Optional

from pydantic import BaseModel


class ASRClientConnectRequest(BaseModel):
    pass


class ASRUser(BaseModel):
    uid: Optional[str] = None
    did: Optional[str] = None
    platform: Optional[str] = None
    sdk_version: Optional[str] = None
    app_version: Optional[str] = None


class ASRAudio(BaseModel):
    format: str
    codec: str
    sample_rate: Optional[int] = None
    channel: Optional[int] = None


class ASRCorpus(BaseModel):
    boosting_table_id: Optional[str] = None
    context: Optional[str] = None


class ASRRequest(BaseModel):
    model_name: str
    enable_itn: Optional[bool] = None
    enable_ddc: Optional[bool] = None
    enable_punc: Optional[bool] = None
    corpus: Optional[ASRCorpus] = None


class ASRFullClientRequest(BaseModel):
    user: Optional[ASRUser] = None
    audio: ASRAudio
    request: ASRRequest


class ASRAudioOnlyRequest(BaseModel):
    last_package: bool
    seq: int
    audio: bytes


class ASRAudioInfoRsp(BaseModel):
    duration: Optional[int] = None


class Word(BaseModel):
    blank_duration: Optional[int] = None
    end_time: int
    start_time: int
    text: str


class Utterance(BaseModel):
    definite: bool
    end_time: int
    start_time: int
    text: str
    words: List[Word] = []


class ASRResult(BaseModel):
    text: Optional[str] = ""
    utterances: List[Utterance] = []


class ASRFullServerResponse(BaseModel):
    sequence: Optional[int] = None
    last_package: bool = False
    result: Optional[ASRResult] = None
    audio: Optional[ASRAudioInfoRsp] = None


class ASRServerError(BaseModel):
    code: int
    msg: str

    def __str__(self) -> str:
        return self.msg
