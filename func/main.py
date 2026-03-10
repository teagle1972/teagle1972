import gzip
import asyncio
import difflib
import inspect
import json
import logging
import os
import socket
import time
from pathlib import Path
import re
import struct
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, AsyncIterable, Callable, Generator

import aiohttp
import uvicorn
from arkitect.core.component.tts.model import AudioParams, ConnectionParams
from arkitect.core.component.tts import tts_client as ark_tts_client_module
from arkitect.core.component.tts.tts_client import AsyncTTSClient
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from volcenginesdkarkruntime import AsyncArk


def _patch_tts_usage_header() -> None:
    if getattr(AsyncTTSClient, "_usage_header_patch_applied", False):
        return
    original_build_header = getattr(AsyncTTSClient, "_build_http_header", None)
    if not callable(original_build_header):
        return

    usage_key = "X-Control-Require-Usage-Tokens-Return"
    usage_value = "*"

    def _patched_build_http_header(self: Any) -> dict:
        headers = original_build_header(self)
        if not isinstance(headers, dict):
            headers = dict(headers or {})
        headers[usage_key] = usage_value
        return headers

    AsyncTTSClient._build_http_header = _patched_build_http_header  # type: ignore[method-assign]
    AsyncTTSClient._usage_header_patch_applied = True  # type: ignore[attr-defined]


_patch_tts_usage_header()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")

# ASR 接入地址（WebSocket）。用于实时语音识别上行连接。
WS_URL = os.getenv("ASR_WS_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async")
# ASR 鉴权参数：应用标识与访问密钥。
ASR_APP_KEY = os.getenv("ASR_APP_KEY", "3339811743")
ASR_ACCESS_KEY = os.getenv("ASR_ACCESS_KEY", "blE2xMz0L7odR1jXt-AOiFx98tUwhs4G")
# 客户端单包音频最大字节数（bytes），过大直接拒绝，防止异常包拖垮会话。
AUDIO_CHUNK_MAX_BYTES = int(os.getenv("AUDIO_CHUNK_MAX_BYTES", str(4 * 1024 * 1024)))
# ASR 输入音频采样率（Hz），需与客户端实际采样率一致。
ASR_SAMPLE_RATE = int(os.getenv("ASR_SAMPLE_RATE", "16000"))
# ASR 识别语言，例如 zh-CN / en-US。
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE", "zh-CN")
# 结果队列等待超时（秒）：影响识别消费循环的响应粒度。
ASR_RESULT_TIMEOUT_SECONDS = float(os.getenv("ASR_RESULT_TIMEOUT_SECONDS", "0.25"))
# 静音提交阈值（秒）：连续静音达到该值后尝试提交一句。
ASR_SILENCE_COMMIT_SECONDS = float(os.getenv("ASR_SILENCE_COMMIT_SECONDS", "1.0"))
ASR_SILENCE_COMMIT_GRACE_SECONDS = float(os.getenv("ASR_SILENCE_COMMIT_GRACE_SECONDS", "0.4"))
ASR_SILENCE_NO_PUNCT_EXTRA_SECONDS = float(os.getenv("ASR_SILENCE_NO_PUNCT_EXTRA_SECONDS", "0.25"))
ASR_SILENCE_INCOMPLETE_TAIL_EXTRA_SECONDS = float(os.getenv("ASR_SILENCE_INCOMPLETE_TAIL_EXTRA_SECONDS", "0.45"))
ASR_DEFINITE_PREFER_WAIT_SECONDS = float(os.getenv("ASR_DEFINITE_PREFER_WAIT_SECONDS", "0.30"))
ASR_POST_COMMIT_EXTENSION_WINDOW_SECONDS = float(os.getenv("ASR_POST_COMMIT_EXTENSION_WINDOW_SECONDS", "3.0"))
# 单次监听硬上限（秒）：到达后强制收口（提交或丢弃），避免单轮无限等待。
ASR_MAX_LISTEN_SECONDS = float(os.getenv("ASR_MAX_LISTEN_SECONDS", "45"))
# 透传 ASR 的端点检测窗口参数（通常按 ms 理解，具体以上游 ASR 文档为准）。
ASR_END_WINDOW_SIZE = int(os.getenv("ASR_END_WINDOW_SIZE", "800"))
# 透传 ASR 的起段强制参数（通常按 ms 理解，具体以上游 ASR 文档为准）。
ASR_FORCE_TO_SPEECH_TIME = int(os.getenv("ASR_FORCE_TO_SPEECH_TIME", "1000"))
# ASR 会话空闲回收阈值（秒）：超过该时间未使用则关闭会话。
ASR_SESSION_IDLE_SECONDS = float(os.getenv("ASR_SESSION_IDLE_SECONDS", "120"))
# ASR 空闲会话清理扫描间隔（秒）：控制回收任务执行频率。
ASR_SESSION_CLEANUP_INTERVAL_SECONDS = float(os.getenv("ASR_SESSION_CLEANUP_INTERVAL_SECONDS", "15"))

# LLM 鉴权和模型配置。
ARK_API_KEY = os.getenv("ARK_API_KEY", "5b2dde3a-28c8-4e69-a447-ea1bc4cca1f1")
ARK_MODEL_ID = os.getenv("ARK_MODEL_ID", "doubao-seed-1-8-251228")
# 单轮回复 token 上限（<=0 代表不主动限制）。
ARK_MAX_TOKENS = int(os.getenv("ARK_MAX_TOKENS", "256"))
# 参与推理的历史消息条数上限（仅最近 N 条）。
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "15"))
# 禁用模型 thinking 模式，优先降低时延与输出不确定性。
NON_THINKING_EXTRA_BODY = {"thinking": {"type": "disabled"}}
# 文本切片最小长度（字符数）：达到后提前推给 TTS，平衡首包延迟与断句质量。
TTS_MIN_CHARS_PER_PUSH = int(os.getenv("TTS_MIN_CHARS_PER_PUSH", "8"))
# 意图识别模型与窗口配置。
INTENT_MODEL_ID = os.getenv("INTENT_MODEL_ID", "doubao-seed-1-6-flash-250828")
INTENT_CONTEXT_WINDOW = int(os.getenv("INTENT_CONTEXT_WINDOW", "4"))
INTENT_MAX_LABELS = int(os.getenv("INTENT_MAX_LABELS", "3"))

# TTS 接入地址与鉴权配置。
TTS_WS_URL = os.getenv("TTS_WS_URL", "wss://openspeech.bytedance.com/api/v3/tts/bidirection")
TTS_APP_KEY = os.getenv("TTS_APP_KEY", "6110098129")
TTS_ACCESS_KEY = os.getenv("TTS_ACCESS_KEY", "2Tfdn2vVFJ7_H6m7g8DNwz6Vut5z97GM")
# TTS 资源 ID（音色资源/能力版本标识）。
TTS_RESOURCE_ID = os.getenv("TTS_RESOURCE_ID", "seed-icl-2.0")
# TTS 音色 ID。
TTS_VOICE_TYPE = os.getenv("TTS_VOICE_TYPE", "S_LFqyLTCH1")
# TTS 输出采样率（Hz）与音频格式（如 pcm/mp3）。
TTS_SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "24000"))
TTS_AUDIO_FORMAT = os.getenv("TTS_AUDIO_FORMAT", "pcm")
TTS_PRICE_PER_10K_CHARS_CNY = float(os.getenv("TTS_PRICE_PER_10K_CHARS_CNY", "3.0"))
# TTS 上游 websocket keepalive 参数（秒）。<=0 表示关闭对应保活项。
TTS_WS_PING_INTERVAL = float(os.getenv("TTS_WS_PING_INTERVAL", "20"))
TTS_WS_PING_TIMEOUT = float(os.getenv("TTS_WS_PING_TIMEOUT", "90"))
# 打开后输出 websockets debug（包含 ping/pong 帧级日志，日志量较大）。
TTS_WS_TRACE = _env_bool("TTS_WS_TRACE", True)
ASR_PRICE_PER_HOUR_CNY = float(os.getenv("ASR_PRICE_PER_HOUR_CNY", "4.5"))

# 回声识别时间窗（秒）：在该窗口内更倾向判定“ASR 文本可能是 TTS 回声”。
BARGE_IN_ECHO_WINDOW_SECONDS = float(os.getenv("BARGE_IN_ECHO_WINDOW_SECONDS", "4.0"))
# 是否按实时节奏发送 TTS 音频（True 可降低堆积，False 追求吞吐）。
TTS_REALTIME_PACING = os.getenv("TTS_REALTIME_PACING", "1").strip() in ("1", "true", "True", "yes", "YES")
# 音频通道数与采样位宽（bytes）。用于计算节奏控制与分帧大小。
TTS_OUTPUT_CHANNELS = int(os.getenv("TTS_OUTPUT_CHANNELS", "1"))
TTS_SAMPLE_WIDTH_BYTES = int(os.getenv("TTS_SAMPLE_WIDTH_BYTES", "2"))
# 下发到客户端的音频帧时长（毫秒）：越小实时性越好，系统调用更频繁。
BARGE_IN_AUDIO_FRAME_MS = int(os.getenv("BARGE_IN_AUDIO_FRAME_MS", "40"))
# 最多允许“领先真实播放进度”多少秒，防止过度缓存导致打断残音。
BARGE_IN_MAX_AUDIO_AHEAD_SECONDS = float(os.getenv("BARGE_IN_MAX_AUDIO_AHEAD_SECONDS", "0.15"))
# 触发流式打断判断的最短文本长度（字符数），过短片段不触发。
BARGE_IN_MIN_CHARS = int(os.getenv("BARGE_IN_MIN_CHARS", "4"))
# 同一归一化文本在该窗口内仅允许触发一次 stream 打断，避免重复中断抖动。
BARGE_IN_STREAM_DEDUP_SECONDS = float(os.getenv("BARGE_IN_STREAM_DEDUP_SECONDS", "2.5"))
# commit 后抑制窗口（秒）：防同一句残留 stream 结果立即再次触发打断。
BARGE_IN_POST_COMMIT_SUPPRESS_SECONDS = float(os.getenv("BARGE_IN_POST_COMMIT_SUPPRESS_SECONDS", "2.5"))
# commit 后长窗口（秒）：防“同句回流”在下一轮 TTS 刚开始时再次误触发 stream 打断。
BARGE_IN_COMMIT_SAME_TEXT_SUPPRESS_SECONDS = float(
    os.getenv("BARGE_IN_COMMIT_SAME_TEXT_SUPPRESS_SECONDS", "8.0")
)
# 若 stream 文本是最近 commit 的扩展，仅当新增字符达到该阈值才允许触发打断。
BARGE_IN_EXTENSION_MIN_NEW_CHARS = int(os.getenv("BARGE_IN_EXTENSION_MIN_NEW_CHARS", "5"))
# 打断冷却（秒）：成功打断后该窗口内忽略后续打断请求，避免抖动。
# 默认置 0，允许“随时可再次打断”；可通过环境变量回调大以增强防抖。
BARGE_IN_INTERRUPT_COOLDOWN_SECONDS = float(os.getenv("BARGE_IN_INTERRUPT_COOLDOWN_SECONDS", "0.3"))
BARGE_IN_COMMIT_PREFIX_BYPASS_WINDOW_SECONDS = float(os.getenv("BARGE_IN_COMMIT_PREFIX_BYPASS_WINDOW_SECONDS", "2.0"))
# 若某轮 TTS 在该时长内即被打断，则下一次 NLP 提交将拼接本轮 user_text 与新 ASR。
SHORT_INTERRUPTED_TTS_MERGE_SECONDS = float(os.getenv("SHORT_INTERRUPTED_TTS_MERGE_SECONDS", "2.0"))
# NLP 入队去重窗口（秒）：相同归一化文本在窗口内不重复入队，避免陈旧累积文本反复触发。
NLP_STALE_WINDOW_SECONDS = float(os.getenv("NLP_STALE_WINDOW_SECONDS", "8.0"))
# 短确认词在 NLP 去重层使用更短的窗口（<=0 代表不做时间窗去重）。
NLP_SHORT_CONFIRM_STALE_WINDOW_SECONDS = float(os.getenv("NLP_SHORT_CONFIRM_STALE_WINDOW_SECONDS", "1.0"))
# 高频短确认词（归一化后）白名单：避免“好的/可以/嗯”等真实反馈被长时间窗误拦。
NLP_SHORT_CONFIRM_TEXTS = {
    w.strip()
    for w in os.getenv(
        "NLP_SHORT_CONFIRM_TEXTS",
        "好,好的,可以,行,嗯,是,是的,对,知道了,收到,明白,清楚",
    ).split(",")
    if w.strip()
}
# 单次合并提交给 NLP 的最多用户句数，避免队列积压导致多轮排队。
NLP_BATCH_MAX_ITEMS = int(os.getenv("NLP_BATCH_MAX_ITEMS", "5"))
# 单次合并提交给 NLP 的最大字符数，避免一次请求过长导致延迟抬高。
NLP_BATCH_MAX_CHARS = int(os.getenv("NLP_BATCH_MAX_CHARS", "120"))

# 单轮 LLM+TTS 总超时（秒）：兜底防卡死，不是“整段对话时长”限制。
TTS_TURN_TIMEOUT_SECONDS = float(os.getenv("TTS_TURN_TIMEOUT_SECONDS", "80"))
# 首个 TTS 音频包超时（秒）：首包未到即判该轮失败。
TTS_FIRST_AUDIO_TIMEOUT_SECONDS = float(os.getenv("TTS_FIRST_AUDIO_TIMEOUT_SECONDS", "8"))
# TTS 包间超时（秒）：首包后若长时间无新包则判该轮失败。
TTS_INTER_CHUNK_TIMEOUT_SECONDS = float(os.getenv("TTS_INTER_CHUNK_TIMEOUT_SECONDS", "4.0"))
# 取消打断时的收尾超时（秒）：避免 aclose/close 长时间阻塞导致“已打断但下一轮排队”。
TTS_CANCEL_PENDING_TASK_WAIT_SECONDS = float(os.getenv("TTS_CANCEL_PENDING_TASK_WAIT_SECONDS", "0.5"))
TTS_CANCEL_ACLOSE_TIMEOUT_SECONDS = float(os.getenv("TTS_CANCEL_ACLOSE_TIMEOUT_SECONDS", "2.5"))
TTS_CANCEL_CLIENT_CLOSE_TIMEOUT_SECONDS = float(os.getenv("TTS_CANCEL_CLIENT_CLOSE_TIMEOUT_SECONDS", "2.5"))
# 中断后等待 SessionFinished（用于拿到 usage/text_words）的超时与兜底重试配置。
TTS_SESSION_FINISH_WAIT_SECONDS = float(os.getenv("TTS_SESSION_FINISH_WAIT_SECONDS", "3.0"))
TTS_SESSION_FINISH_RETRY_WAIT_SECONDS = float(os.getenv("TTS_SESSION_FINISH_RETRY_WAIT_SECONDS", "1.5"))
TTS_SESSION_FINISH_RETRY_COUNT = max(0, int(os.getenv("TTS_SESSION_FINISH_RETRY_COUNT", "1")))
# TTS 自动重试间隔（秒，逗号分隔）。仅在“尚未播出任何音频”且出现连接类失败时触发。
_TTS_RETRY_DELAYS_RAW = os.getenv("TTS_RETRY_DELAYS_SECONDS", "0.5,1,2")
_tts_retry_delays: list[float] = []
for _part in _TTS_RETRY_DELAYS_RAW.split(","):
    _part = _part.strip()
    if not _part:
        continue
    try:
        _value = float(_part)
    except Exception:
        continue
    if _value > 0:
        _tts_retry_delays.append(_value)
TTS_RETRY_DELAYS_SECONDS = tuple(_tts_retry_delays)

# Uvicorn WebSocket 心跳间隔（秒）。<=0 表示关闭 ping。
UVICORN_WS_PING_INTERVAL = float(os.getenv("UVICORN_WS_PING_INTERVAL", "0"))
# Uvicorn WebSocket ping 超时（秒），与 ping 间隔配套使用。
UVICORN_WS_PING_TIMEOUT = float(os.getenv("UVICORN_WS_PING_TIMEOUT", "20"))
# 双通道（control/media）配对等待超时（秒）。
DUAL_CHANNEL_WAIT_SECONDS = float(os.getenv("DUAL_CHANNEL_WAIT_SECONDS", "20"))
# 双通道聚合适配器入站队列上限（条），过小易丢消息，过大占内存。
DUAL_CHANNEL_INCOMING_QUEUE_SIZE = int(os.getenv("DUAL_CHANNEL_INCOMING_QUEUE_SIZE", "2048"))

DEFAULT_CUSTOMER_PROFILE = "\n".join(
    [
        "【客户画像】",
        "催收员工号：36472051,",
        "催收员姓名：章一凯,",
        "客户姓名：雷瑞敏,",
        "客户性别：男,",
        "客户年龄：43岁,",
        "客户尊称：雷先生,",
        "客户所在城市：天津,",
        "客户地址：锦江区青年路541号15栋2单元493室,",
        "客户账户编号：L55264990,",
        "客户身份证后四位：4701,",
        "银行全称：华夏银行,",
        "贷款产品名称：微粒贷,",
        "贷款时间：9月13日,",
        "贷款金额：24173元,",
        "当前逾期天数：9天,",
        "当前逾期开始日期：1月15日,",
        "是否首逾：是,",
        "总欠款金额：23642元,",
        "本期应还款额：6655元,",
        "本金金额：6032.9元,",
        "利息金额：602.5元,",
        "罚息金额：19.6元,",
        "银行要求本期一次性结清日期：今天,",
        "银行要求本期一次性结清时间：15,",
        "最近一次还款金额：5739.6元,",
        "最近一次还款日期：12月12日,",
        "最近一次还款方式：银行卡自动扣款,",
        "最近一次延期天数：,",
        "最近一次延期是否按时到账：无历史延期,",
        "客户风险分级：低,",
        "约定还款方式：微信还款,",
        "扣款银行卡后四位：3950,",
        "对话基准日期：1月24日,",
        "对话基准日期(周单位)：星期六,",
        "对话基准时间：9点",
    ]
)

DEFAULT_WORKFLOW = "\n".join(
    [
        "【催收流程】",
        "1、开场与合规",
        "- 问候 + 确认是否方便通话",
        "- 告知银行/机构身份、姓名/工号、通话录音与用途",
        "",
        "2、核身与账户定位",
        "- 通过画像字段进行核身（常用：身份证后四位/账户号后几位）；客户确认后再进入业务",
        "",
        "3、逾期事实告知与基本口径",
        "- 告知：产品/账户、当前逾期事实、需要尽快处理的要求（金额、逾期天数等以画像为准）",
        "- 说明逾期后果（合规、克制、不夸大）：例如征信/信用记录影响、罚息/费用可能继续增加、后续管理措施升级等",
        "",
        "4、原因与态度探询（拉扯起点）",
        "- 询问未及时处理的原因、当前处理意愿与可行性",
        "- 允许客户情绪与反问；催收员要稳住节奏、澄清口径、把话题拉回“如何处理”",
        "",
        "5、推进可执行方案（核心争取）",
        "- 原则：若客户已还/正在操作，优先转入“确认已处理 + 以入账为准”收口；否则争取一次性处理（以结局目标为准）",
        "- 追问方式必须是“确认式单值”：",
        "  例：我确认一下，您是【今天】一次性处理，对吗？",
        "- 若客户仅表达“尽量/看看/到时候再说”等保留语气，即视为“意向口径”，不得判定达成承诺",
        "",
        "6、结局收口",
        "7、 结尾合规提醒",
        "",
        "要求：",
        "1、不要寒暄、不要安抚话术；信息密度高；先按N1开始主动开口。",
        "2、不要被客户三言两语打发了，要落实还款时间、金额、渠道。如客户不能还款要问清原因，并施加必要的压力",
        "3、回复内容不要太长，可以分多轮对话表述清楚。回复要言简意赅。",
        "4、是电话催收场景，对话要完全口语化",
    ]
)

DEFAULT_SYSTEM_INSTRUCTION_BASE = "\n".join(
    [
        "你是电话沟通助手，请结合用户画像和工作流程，主动发起通话并推进沟通。",
        "要口语化表达，说话要简短，不要长篇大论",
        "如需提问，每次不得超过两个问题。可以通过多轮对话把问题搞清楚，不能一股脑一次提一堆问题",
        "",
    ]
)
WORKFLOW_TASK_PLACEHOLDER = "__WORKFLOW_TASK_NOTES__"

PRE_PROMPT = "\n\n".join(
    [
        DEFAULT_SYSTEM_INSTRUCTION_BASE.strip(),
    ]
)

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", PRE_PROMPT)
START_TRIGGER = os.getenv(
    "START_TRIGGER",
    "请先输出一轮通用电话开场白：简短自我介绍、说明来电目的，并在结尾确认对方是否方便通话。",
)
START_COMMAND_COOLDOWN_SECONDS = float(os.getenv("START_COMMAND_COOLDOWN_SECONDS", "6"))
PROCESS_EXIT_DELAY_SECONDS = float(os.getenv("PROCESS_EXIT_DELAY_SECONDS", "0.2"))
VOICE_COMMAND_START = "start_dialog"
VOICE_COMMAND_END = "end_dialog"
VOICE_COMMAND_START_KEYWORDS = ("开始对话", )
VOICE_COMMAND_END_KEYWORDS = ("结束对话",)
DEFAULT_INTENT_FALLBACK_LABEL = str(os.getenv("INTENT_FALLBACK_LABEL", "") or "").strip()
WORKFLOW_DEFAULT_OTHER_INTENT_LABEL = "其他"
INTENT_SYSTEM_PROMPT = """你是电话催收场景中的“客户意图识别器（仅最后一句）”。
任务：只根据【客户最后一句话 last_customer_utterance】从给定标签库中识别最相关意图。对话上文 context_window 仅用于消歧（指代/省略/礼貌语气），不得把上文意图或承诺继承到最后一句。

硬约束：
1) 只判断 last_customer_utterance；context_window 仅参考，不得作为意图来源。
2) intents 只能从标签库中选择；不得输出库外标签。
3) 允许返回多个意图，但最多 3 个，按置信度从高到低排序。
4) 若 last_customer_utterance 不含实质业务意图（如寒暄、致谢、告别、语气词），优先规则：
   - 明确告别/结束/挂断（如“再见/拜拜/挂了/不聊了/就这样”）=> 优先 C132_主动结束对话
   - 仅“好/嗯/行/知道了/谢谢”等但不明确结束 => C199_其他无实质业务意图
   - 若同时出现，以“结束对话”优先。
5) 若无法判断：
   - 若提供 fallback_label，则 intents=[fallback_label]
   - 若无 fallback_label（或为 <none>），则 intents=[]
6) 仅输出 JSON：{"intents":["标签A",...], "reason":"..."}，不得输出任何额外文本。
"""

OUTPUT_ROOT = Path("/mnt/tos")
LOG_DIR = Path("/mnt/tos/logs")
LOG_FILE = LOG_DIR / f"run_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.log"
WEB_CLIENT_DIR = Path(__file__).resolve().parent / "web_client"
WEB_CLIENT_INDEX = WEB_CLIENT_DIR / "index.html"

_handlers: list[logging.Handler] = [logging.StreamHandler()]
_file_logging_enabled = False
_file_logging_error: str | None = None
try:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _handlers.insert(0, logging.FileHandler(str(LOG_FILE), encoding="utf-8"))
    _file_logging_enabled = True
except OSError as exc:
    _file_logging_error = f"{type(exc).__name__}: {exc}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=_handlers,
    force=True,
)
logger = logging.getLogger(__name__)
logger.info(
    "logging initialized host=%s pid=%s log_file=%s file_logging=%s",
    socket.gethostname(),
    os.getpid(),
    str(LOG_FILE),
    _file_logging_enabled,
)
if _file_logging_error:
    logger.warning("file logging init failed log_file=%s error=%s", str(LOG_FILE), _file_logging_error)


def _patch_tts_ws_connect() -> None:
    if getattr(AsyncTTSClient, "_ws_connect_patch_applied", False):
        return
    original_connect = getattr(ark_tts_client_module.websockets, "connect", None)
    if not callable(original_connect):
        return

    ping_interval = None if TTS_WS_PING_INTERVAL <= 0 else TTS_WS_PING_INTERVAL
    ping_timeout = None if TTS_WS_PING_TIMEOUT <= 0 else TTS_WS_PING_TIMEOUT

    def _patched_connect(*args: Any, **kwargs: Any):
        kwargs.setdefault("ping_interval", ping_interval)
        kwargs.setdefault("ping_timeout", ping_timeout)
        if TTS_WS_TRACE:
            ws_logger = logging.getLogger("websockets.client")
            ws_logger.setLevel(logging.DEBUG)
            kwargs.setdefault("logger", ws_logger)
        return original_connect(*args, **kwargs)

    ark_tts_client_module.websockets.connect = _patched_connect  # type: ignore[assignment]
    AsyncTTSClient._ws_connect_patch_applied = True  # type: ignore[attr-defined]
    logger.info(
        "tts ws connect patched ping_interval=%s ping_timeout=%s trace=%s",
        ping_interval,
        ping_timeout,
        TTS_WS_TRACE,
    )


_patch_tts_ws_connect()


def _patch_tts_receive_decode_tolerance() -> None:
    if getattr(AsyncTTSClient, "_receive_decode_tolerance_patch_applied", False):
        return
    original_parse_response = getattr(ark_tts_client_module, "parse_response", None)
    if not callable(original_parse_response):
        return

    async def _patched_receive_data(self: Any):
        if self.conn is None:
            raise ValueError("Connection is not established")
        while True:
            response = await self.conn.recv()
            try:
                return original_parse_response(response)
            except (UnicodeDecodeError, json.JSONDecodeError, gzip.BadGzipFile, ValueError) as exc:
                # Drop only this broken frame and continue consuming stream data.
                logger.warning(
                    "tts decode failed and dropped frame conn_id=%s session_id=%s err=%s",
                    getattr(self, "conn_id", None),
                    getattr(self, "session_id", None),
                    f"{exc.__class__.__name__}: {exc}",
                )
                continue

    AsyncTTSClient._receive_data = _patched_receive_data  # type: ignore[method-assign]
    AsyncTTSClient._receive_decode_tolerance_patch_applied = True  # type: ignore[attr-defined]
    logger.info("tts receive decode tolerance patch enabled")


_patch_tts_receive_decode_tolerance()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await _close_all_asr_sessions()
        if ARK_CLIENT is not None:
            await ARK_CLIENT.close()


app = FastAPI(lifespan=lifespan)
if WEB_CLIENT_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_CLIENT_DIR)), name="web")

ARK_CLIENT: AsyncArk | None = AsyncArk(api_key=ARK_API_KEY) if ARK_API_KEY else None
SESSION_HISTORY: dict[str, list[dict[str, str]]] = {}
SESSION_HISTORY_LOCK = threading.Lock()
SESSION_SYSTEM_PROMPT: dict[str, str] = {}
SESSION_SYSTEM_PROMPT_LOCK = threading.Lock()
SESSION_INTENT_LABELS: dict[str, list[str]] = {}
SESSION_INTENT_LABELS_LOCK = threading.Lock()
SESSION_INTENT_FALLBACK_LABEL: dict[str, str] = {}
SESSION_INTENT_FALLBACK_LABEL_LOCK = threading.Lock()
SESSION_WORKFLOW_STATE: dict[str, dict[str, Any]] = {}
SESSION_WORKFLOW_STATE_LOCK = threading.Lock()
DUAL_WS_SESSIONS: dict[str, dict[str, Any]] = {}
DUAL_WS_SESSIONS_LOCK = asyncio.Lock()


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", value.strip())
    return cleaned.strip("._")[:128]


def _get_obj_field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed >= 0 else default


def _extract_usage_metrics(usage_obj: Any) -> dict[str, int]:
    if usage_obj is None:
        return {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        }
    prompt_details = _get_obj_field(usage_obj, "prompt_tokens_details", {})
    completion_details = _get_obj_field(usage_obj, "completion_tokens_details", {})
    return {
        "total_tokens": _to_non_negative_int(_get_obj_field(usage_obj, "total_tokens", 0)),
        "prompt_tokens": _to_non_negative_int(_get_obj_field(usage_obj, "prompt_tokens", 0)),
        "completion_tokens": _to_non_negative_int(_get_obj_field(usage_obj, "completion_tokens", 0)),
        "cached_tokens": _to_non_negative_int(_get_obj_field(prompt_details, "cached_tokens", 0)),
        "reasoning_tokens": _to_non_negative_int(_get_obj_field(completion_details, "reasoning_tokens", 0)),
    }


def _extract_tts_usage_chars(chunk_obj: Any) -> int:
    usage_obj = _get_obj_field(chunk_obj, "usage", None)
    candidates = [usage_obj, chunk_obj]
    keys = (
        "text_words",
        "characters",
        "character_count",
        "char_count",
        "usage_chars",
        "text_characters",
        "total_characters",
        "total_chars",
        "input_characters",
        "output_characters",
        "text_length",
    )
    def _find_nested_char_count(node: Any, depth: int = 0) -> int:
        if depth > 6 or node is None:
            return 0
        if isinstance(node, dict):
            for key in keys:
                parsed = _to_non_negative_int(node.get(key), default=-1)
                if parsed >= 0:
                    return parsed
            for value in node.values():
                found = _find_nested_char_count(value, depth + 1)
                if found > 0:
                    return found
            return 0
        if isinstance(node, (list, tuple)):
            for item in node:
                found = _find_nested_char_count(item, depth + 1)
                if found > 0:
                    return found
            return 0
        return 0
    for candidate in candidates:
        if candidate is None:
            continue
        for key in keys:
            value = _get_obj_field(candidate, key, None)
            parsed = _to_non_negative_int(value, default=-1)
            if parsed >= 0:
                return parsed
        nested = _find_nested_char_count(candidate)
        if nested > 0:
            return nested
    return 0


def _normalize_model_for_pricing(model_name: str) -> str:
    compact = (model_name or "").strip().lower().replace("_", "-")
    if ("doubao-seed-1.8" in compact) or ("doubao-seed-1-8" in compact):
        return "doubao-seed-1.8"
    if ("doubao-seed-1.6-flash" in compact) or ("doubao-seed-1-6-flash" in compact):
        return "doubao-seed-1.6-flash"
    return compact


def _resolve_1_8_prices(prompt_tokens: int, completion_tokens: int) -> tuple[float, float, str]:
    # Pricing document condition for 1.8:
    # input length [0,32k] and output length [0,0.2k] / (0.2k,+inf)
    # where 0.2k tokens == 200 tokens.
    if prompt_tokens <= 32_000:
        input_price = 0.8
        output_price = 2.0 if completion_tokens <= 200 else 8.0
        condition = "input_[0,32k]_output_[0,0.2k]" if completion_tokens <= 200 else "input_[0,32k]_output_(0.2k,+inf)"
        return input_price, output_price, condition
    if prompt_tokens <= 128_000:
        return 1.2, 16.0, "input_(32k,128k]"
    return 2.4, 24.0, "input_(128k,256k]_or_above"


def _resolve_1_6_flash_prices(prompt_tokens: int) -> tuple[float, float, str]:
    if prompt_tokens <= 32_000:
        return 0.15, 1.5, "input_[0,32k]"
    if prompt_tokens <= 128_000:
        return 0.3, 3.0, "input_(32k,128k]"
    return 0.6, 6.0, "input_(128k,256k]_or_above"


def _calculate_request_cost(model_name: str, usage: dict[str, int]) -> dict[str, Any]:
    model_key = _normalize_model_for_pricing(model_name)
    prompt_tokens = max(0, int(usage.get("prompt_tokens", 0)))
    completion_tokens = max(0, int(usage.get("completion_tokens", 0)))
    total_tokens = max(0, int(usage.get("total_tokens", 0)))
    cached_tokens = max(0, int(usage.get("cached_tokens", 0)))
    reasoning_tokens = max(0, int(usage.get("reasoning_tokens", 0)))

    input_price = 0.0
    output_price = 0.0
    cache_input_price = 0.0
    cache_storage_price = 0.017
    pricing_rule = "unsupported_model"
    pricing_condition = ""
    pricing_warning = ""
    if model_key == "doubao-seed-1.8":
        input_price, output_price, pricing_condition = _resolve_1_8_prices(prompt_tokens, completion_tokens)
        cache_input_price = 0.16
        pricing_rule = "doubao-seed-1.8"
    elif model_key == "doubao-seed-1.6-flash":
        input_price, output_price, pricing_condition = _resolve_1_6_flash_prices(prompt_tokens)
        cache_input_price = 0.03
        pricing_rule = "doubao-seed-1.6-flash"

    if prompt_tokens > 256_000:
        pricing_warning = "input_tokens_exceeds_documented_range_256k_use_highest_tier_estimation"

    # Avoid double-counting cache-hit tokens in input billing.
    billable_input_tokens = max(0, prompt_tokens - cached_tokens)
    input_cost = (billable_input_tokens / 1_000_000.0) * input_price
    output_cost = (completion_tokens / 1_000_000.0) * output_price
    cache_input_cost = (cached_tokens / 1_000_000.0) * cache_input_price
    cache_storage_cost = 0.0
    total_cost = input_cost + output_cost + cache_input_cost + cache_storage_cost

    return {
        "model": model_name,
        "model_key": model_key,
        "pricing_rule": pricing_rule,
        "pricing_condition": pricing_condition,
        "pricing_warning": pricing_warning,
        "currency": "CNY",
        "usage": {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
            "billable_input_tokens": billable_input_tokens,
        },
        "price": {
            "input_per_million": input_price,
            "output_per_million": output_price,
            "cache_input_per_million": cache_input_price,
            "cache_storage_per_million_token_hour": cache_storage_price,
        },
        "cost": {
            "input": round(input_cost, 8),
            "output": round(output_cost, 8),
            "cache_input": round(cache_input_cost, 8),
            "cache_storage": round(cache_storage_cost, 8),
            "total": round(total_cost, 8),
        },
    }


def _parse_intent_labels_payload(raw_value: Any) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    candidates: list[str] = []
    if isinstance(raw_value, list):
        candidates.extend(str(item or "") for item in raw_value)
    elif isinstance(raw_value, tuple):
        candidates.extend(str(item or "") for item in raw_value)
    elif raw_value is not None:
        candidates.extend(str(raw_value).splitlines())

    marker_prefixes = (
        "intents:",
        "model:",
        "customer:",
        "assistant:",
        "客户:",
        "坐席:",
    )
    for item in candidates:
        text = str(item or "").replace("\r", "").strip()
        if not text:
            continue
        text = re.sub(r"^[\-\*\u2022]\s*", "", text)
        text = re.sub(r"^\d+\s*[\.\)、]\s*", "", text)
        text = text.rstrip(",，;；").strip()
        if not text:
            continue
        lower_text = text.lower()
        if lower_text.startswith(marker_prefixes):
            continue
        if text.startswith("[") and ("]" in text):
            continue
        if re.fullmatch(r"[-_=]{3,}", text):
            continue
        label = text
        if (not label) or (label in seen):
            continue
        labels.append(label)
        seen.add(label)
    return labels


def _normalize_intent_labels(labels: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in labels:
        label = str(item or "").strip()
        if (not label) or (label in seen):
            continue
        merged.append(label)
        seen.add(label)
    return merged


def _get_session_intent_labels(session_id: str) -> list[str]:
    with SESSION_INTENT_LABELS_LOCK:
        labels = list(SESSION_INTENT_LABELS.get(session_id, []))
    return _normalize_intent_labels(labels)


def _set_session_intent_labels(session_id: str, labels: Any) -> list[str]:
    normalized = _normalize_intent_labels(_parse_intent_labels_payload(labels))
    with SESSION_INTENT_LABELS_LOCK:
        SESSION_INTENT_LABELS[session_id] = normalized
    return normalized


def _clear_session_intent_labels(session_id: str) -> None:
    with SESSION_INTENT_LABELS_LOCK:
        SESSION_INTENT_LABELS.pop(session_id, None)


def _get_session_intent_fallback_label(session_id: str) -> str:
    with SESSION_INTENT_FALLBACK_LABEL_LOCK:
        value = str(SESSION_INTENT_FALLBACK_LABEL.get(session_id, "") or "").strip()
    if value:
        return value
    return DEFAULT_INTENT_FALLBACK_LABEL


def _set_session_intent_fallback_label(session_id: str, label: Any) -> str:
    normalized = str(label or "").strip()
    with SESSION_INTENT_FALLBACK_LABEL_LOCK:
        if normalized:
            SESSION_INTENT_FALLBACK_LABEL[session_id] = normalized
        else:
            SESSION_INTENT_FALLBACK_LABEL.pop(session_id, None)
    return normalized


def _clear_session_intent_fallback_label(session_id: str) -> None:
    with SESSION_INTENT_FALLBACK_LABEL_LOCK:
        SESSION_INTENT_FALLBACK_LABEL.pop(session_id, None)


def _normalize_workflow_edge_text(value: Any) -> str:
    current = str(value or "").strip()
    if not current:
        return ""
    return re.sub(r"\s+", "", current).casefold()


def _append_default_other_intent_label(labels: list[str]) -> list[str]:
    if not labels:
        return []
    normalized_other = _normalize_workflow_edge_text(WORKFLOW_DEFAULT_OTHER_INTENT_LABEL)
    for item in labels:
        if _normalize_workflow_edge_text(item) == normalized_other:
            return list(labels)
    merged = list(labels)
    merged.append(WORKFLOW_DEFAULT_OTHER_INTENT_LABEL)
    return merged


def _render_customer_profile_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            k = str(key or "").strip()
            v = str(item or "").strip()
            if not k:
                continue
            lines.append(f"{k}：{v}")
        return "\n".join(lines).strip()
    if isinstance(value, list):
        lines = [str(item or "").strip() for item in value if str(item or "").strip()]
        return "\n".join(lines).strip()
    return str(value or "").strip()


def _build_structured_prompt_template(
    system_instruction_text: str,
    customer_profile_text: str,
    workflow_text: str,
    use_workflow_placeholder: bool,
) -> str:
    sections: list[str] = []
    system_text = str(system_instruction_text or "").strip()
    if system_text:
        sections.append(f"【系统指令】\n{system_text}")
    profile_text = str(customer_profile_text or "").strip()
    if profile_text:
        sections.append(f"【客户画像】\n{profile_text}")
    workflow_body = WORKFLOW_TASK_PLACEHOLDER if use_workflow_placeholder else str(workflow_text or "").strip()
    if use_workflow_placeholder or workflow_body:
        sections.append(f"【下一步工作流程任务】\n{workflow_body}")
    return "\n\n".join(section for section in sections if section.strip())


def _extract_workflow_object(raw_value: Any) -> dict[str, Any] | None:
    current = raw_value
    if isinstance(current, str):
        current = _try_parse_json_object(current)
    if not isinstance(current, dict):
        return None
    nodes = current.get("nodes")
    edges = current.get("edges")
    if not isinstance(nodes, list) or (not nodes):
        return None
    if (edges is not None) and (not isinstance(edges, list)):
        return None
    return current


def _build_session_workflow_state(workflow_obj: dict[str, Any], prompt_template: str) -> dict[str, Any] | None:
    raw_nodes = workflow_obj.get("nodes")
    if not isinstance(raw_nodes, list):
        return None
    raw_edges = workflow_obj.get("edges")
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes: dict[str, dict[str, str]] = {}
    node_order: list[str] = []
    for item in raw_nodes:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or "").strip()
        if (not node_id) or (node_id in nodes):
            continue
        nodes[node_id] = {
            "id": node_id,
            "type": str(item.get("type") or "").strip().lower(),
            "task_notes": str(item.get("task_notes") or "").strip(),
        }
        node_order.append(node_id)
    if not node_order:
        return None

    edges_by_source: dict[str, list[dict[str, str]]] = {}
    for item in raw_edges:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        if (source_id not in nodes) or (target_id not in nodes):
            continue
        edge = {
            "source_id": source_id,
            "target_id": target_id,
            "text": str(item.get("text") or "").strip(),
        }
        edges_by_source.setdefault(source_id, []).append(edge)

    template = str(prompt_template or "").strip() or SYSTEM_PROMPT
    return {
        "nodes": nodes,
        "node_order": node_order,
        "edges_by_source": edges_by_source,
        "cursor_node_id": node_order[0],
        "prompt_template": template,
    }


def _resolve_workflow_runtime_view(state: dict[str, Any]) -> dict[str, Any]:
    nodes = state.get("nodes")
    node_order = state.get("node_order")
    edges_by_source = state.get("edges_by_source")
    if not isinstance(nodes, dict) or not isinstance(node_order, list) or not isinstance(edges_by_source, dict):
        return {
            "route_node_id": "",
            "content_node_id": "",
            "workflow_text": "",
            "intent_labels": [],
            "label_to_target": {},
            "intent_source_node_id": "",
        }

    cursor_node_id = str(state.get("cursor_node_id") or "").strip()
    if cursor_node_id not in nodes:
        cursor_node_id = str(node_order[0] or "").strip() if node_order else ""
    route_node_id = cursor_node_id
    content_node_id = route_node_id
    workflow_text = str(nodes.get(content_node_id, {}).get("task_notes") or "").strip()

    def _collect_labeled_edges(source_node_id: str) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        mapping: dict[str, str] = {}
        for edge in edges_by_source.get(source_node_id, []):
            label = str(edge.get("text") or "").strip()
            target_id = str(edge.get("target_id") or "").strip()
            normalized = _normalize_workflow_edge_text(label)
            if (not label) or (not target_id) or (not normalized) or (normalized in mapping):
                continue
            labels.append(label)
            mapping[normalized] = target_id
        return labels, mapping

    intent_labels: list[str] = []
    label_to_target: dict[str, str] = {}
    intent_source_node_id = route_node_id
    intent_labels, label_to_target = _collect_labeled_edges(route_node_id)

    intent_labels = _append_default_other_intent_label(intent_labels)

    return {
        "route_node_id": route_node_id,
        "content_node_id": content_node_id,
        "workflow_text": workflow_text,
        "intent_labels": intent_labels,
        "label_to_target": label_to_target,
        "intent_source_node_id": intent_source_node_id,
    }


def _get_session_workflow_runtime_snapshot(session_id: str) -> dict[str, Any] | None:
    with SESSION_WORKFLOW_STATE_LOCK:
        state = SESSION_WORKFLOW_STATE.get(session_id)
        if not isinstance(state, dict):
            return None
        _advance_workflow_cursor_by_empty_edges(state, consume_current=False)
        view = _resolve_workflow_runtime_view(state)
        cursor_node_id = str(state.get("cursor_node_id") or "").strip()
        nodes = state.get("nodes")
        edges_by_source = state.get("edges_by_source")

    total_nodes = len(nodes) if isinstance(nodes, dict) else 0
    total_edges = 0
    if isinstance(edges_by_source, dict):
        for outgoing in edges_by_source.values():
            if isinstance(outgoing, list):
                total_edges += len(outgoing)

    intent_labels = view.get("intent_labels")
    return {
        "cursor_node_id": cursor_node_id,
        "route_node_id": str(view.get("route_node_id") or "").strip(),
        "content_node_id": str(view.get("content_node_id") or "").strip(),
        "intent_source_node_id": str(view.get("intent_source_node_id") or "").strip(),
        "intent_labels": list(intent_labels) if isinstance(intent_labels, list) else [],
        "workflow_nodes": total_nodes,
        "workflow_edges": total_edges,
    }


def _render_prompt_with_workflow(prompt_template: str, workflow_text: str) -> str:
    template = str(prompt_template or "").strip() or SYSTEM_PROMPT
    current_workflow = workflow_text or ""
    if WORKFLOW_TASK_PLACEHOLDER in template:
        return template.replace(WORKFLOW_TASK_PLACEHOLDER, current_workflow)
    if DEFAULT_WORKFLOW in template:
        return template.replace(DEFAULT_WORKFLOW, current_workflow)
    marker = "【催收流程】"
    marker_index = template.find(marker)
    if marker_index >= 0:
        prefix = template[:marker_index].rstrip()
        suffix_index = template.find("\n\n【", marker_index + len(marker))
        suffix = template[suffix_index:].strip() if suffix_index >= 0 else ""
        parts: list[str] = []
        if prefix:
            parts.append(prefix)
        if current_workflow:
            parts.append(current_workflow)
        if suffix:
            parts.append(suffix)
        return "\n\n".join(parts)
    return template


def _apply_workflow_view_to_session(
    session_id: str,
    prompt_template: str,
    view: dict[str, Any],
) -> None:
    workflow_text = str(view.get("workflow_text") or "").strip()
    intent_labels = view.get("intent_labels")
    labels = list(intent_labels) if isinstance(intent_labels, list) else []
    _set_session_system_prompt(session_id, _render_prompt_with_workflow(prompt_template, workflow_text))
    _set_session_intent_labels(session_id, labels)


def _advance_workflow_cursor_by_empty_edges(state: dict[str, Any], *, consume_current: bool) -> None:
    nodes = state.get("nodes")
    node_order = state.get("node_order")
    edges_by_source = state.get("edges_by_source")
    if not isinstance(nodes, dict) or not isinstance(node_order, list) or not isinstance(edges_by_source, dict):
        return

    current = str(state.get("cursor_node_id") or "").strip()
    if current not in nodes:
        current = str(node_order[0] or "").strip() if node_order else ""
    if current not in nodes:
        return

    seen: set[str] = set()
    consumed_task_node = False
    while current and (current in nodes) and (current not in seen):
        seen.add(current)
        outgoing = list(edges_by_source.get(current, []))
        labeled_edges = [
            edge for edge in outgoing if _normalize_workflow_edge_text(edge.get("text"))
        ]
        if labeled_edges:
            break
        has_task_notes = bool(str(nodes.get(current, {}).get("task_notes") or "").strip())
        empty_edges = [edge for edge in outgoing if not str(edge.get("text") or "").strip()]
        if has_task_notes:
            if (not consume_current) or consumed_task_node:
                break
            if len(empty_edges) != 1:
                break
            next_node_id = str(empty_edges[0].get("target_id") or "").strip()
            if (not next_node_id) or (next_node_id not in nodes):
                break
            # consume_current=True 表示当前任务节点已完成一轮任务执行，
            # 可沿唯一空边推进到下一节点（包括 decision），后续再在新节点做判断。
            consumed_task_node = True
            current = next_node_id
            continue
        if len(empty_edges) != 1:
            break
        next_node_id = str(empty_edges[0].get("target_id") or "").strip()
        if (not next_node_id) or (next_node_id not in nodes):
            break
        current = next_node_id
    state["cursor_node_id"] = current


def _refresh_session_workflow_view(session_id: str, *, consume_current: bool = False) -> bool:
    prompt_template = ""
    view: dict[str, Any] | None = None
    with SESSION_WORKFLOW_STATE_LOCK:
        state = SESSION_WORKFLOW_STATE.get(session_id)
        if not isinstance(state, dict):
            return False
        _advance_workflow_cursor_by_empty_edges(state, consume_current=consume_current)
        prompt_template = str(state.get("prompt_template") or "")
        view = _resolve_workflow_runtime_view(state)
    if view is None:
        return False
    _apply_workflow_view_to_session(
        session_id=session_id,
        prompt_template=prompt_template,
        view=view,
    )
    return True


def _has_session_workflow_state(session_id: str) -> bool:
    with SESSION_WORKFLOW_STATE_LOCK:
        return session_id in SESSION_WORKFLOW_STATE


def _clear_session_workflow_state(session_id: str) -> None:
    with SESSION_WORKFLOW_STATE_LOCK:
        SESSION_WORKFLOW_STATE.pop(session_id, None)


def _set_session_workflow_state(
    session_id: str,
    workflow_payload: Any,
    prompt_template: str,
) -> tuple[bool, str]:
    workflow_obj = _extract_workflow_object(workflow_payload)
    if workflow_obj is None:
        return False, "invalid_workflow_json"
    state = _build_session_workflow_state(workflow_obj, prompt_template=prompt_template)
    if state is None:
        return False, "invalid_workflow_graph"
    _advance_workflow_cursor_by_empty_edges(state, consume_current=False)
    view = _resolve_workflow_runtime_view(state)
    with SESSION_WORKFLOW_STATE_LOCK:
        SESSION_WORKFLOW_STATE[session_id] = state
    _apply_workflow_view_to_session(
        session_id=session_id,
        prompt_template=str(state.get("prompt_template") or ""),
        view=view,
    )
    return True, ""


def _advance_session_workflow_by_intents(session_id: str, intents: list[str]) -> tuple[bool, str, str]:
    matched_label = ""
    jump_node_id = ""
    next_prompt_template = ""
    next_view: dict[str, Any] | None = None
    normalized_default_other = _normalize_workflow_edge_text(WORKFLOW_DEFAULT_OTHER_INTENT_LABEL)
    with SESSION_WORKFLOW_STATE_LOCK:
        state = SESSION_WORKFLOW_STATE.get(session_id)
        if not isinstance(state, dict):
            return False, "", ""
        _advance_workflow_cursor_by_empty_edges(state, consume_current=False)
        current_view = _resolve_workflow_runtime_view(state)
        label_to_target = current_view.get("label_to_target")
        if not isinstance(label_to_target, dict) or (not label_to_target):
            return False, "", ""
        target_node_id = ""
        for item in intents:
            label = str(item or "").strip()
            normalized = _normalize_workflow_edge_text(label)
            if not normalized:
                continue
            if normalized == normalized_default_other:
                # "其他" 为默认保留标签：命中时停留当前节点，不触发跳转。
                continue
            target_candidate = str(label_to_target.get(normalized) or "").strip()
            if not target_candidate:
                continue
            matched_label = label
            target_node_id = target_candidate
            break
        if not target_node_id:
            return False, "", ""
        jump_node_id = target_node_id
        state["cursor_node_id"] = target_node_id
        _advance_workflow_cursor_by_empty_edges(state, consume_current=False)
        next_prompt_template = str(state.get("prompt_template") or "")
        next_view = _resolve_workflow_runtime_view(state)
    if next_view is None:
        return False, "", ""
    _apply_workflow_view_to_session(
        session_id=session_id,
        prompt_template=next_prompt_template,
        view=next_view,
    )
    return True, matched_label, jump_node_id


def _gzip_compress(data: bytes) -> bytes:
    return gzip.compress(data)


def _gzip_decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


def _new_auth_headers() -> dict[str, str]:
    return {
        "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Access-Key": ASR_ACCESS_KEY,
        "X-Api-App-Key": ASR_APP_KEY,
    }


def _build_full_request(seq: int, audio_format: str) -> bytes:
    header = bytearray()
    header.append((0b0001 << 4) | 1)
    header.append((0b0001 << 4) | 0b0001)
    header.append((0b0001 << 4) | 0b0001)
    header.extend(bytes([0x00]))

    payload = {
        "user": {"uid": "func_uid"},
        "audio": {
            "format": audio_format,
            "codec": "raw",
            "rate": ASR_SAMPLE_RATE,
            "bits": 16,
            "channel": 1,
            "language": ASR_LANGUAGE,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "enable_lid": False,
            "show_utterances": True,
            "enable_nonstream": False,
            "result_type": "single",
            "end_window_size": ASR_END_WINDOW_SIZE,
            "force_to_speech_time": ASR_FORCE_TO_SPEECH_TIME,
        },
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    compressed = _gzip_compress(payload_bytes)

    req = bytearray()
    req.extend(bytes(header))
    req.extend(struct.pack(">i", seq))
    req.extend(struct.pack(">I", len(compressed)))
    req.extend(compressed)
    return bytes(req)


def _build_audio_request(seq: int, segment: bytes, is_last: bool) -> bytes:
    header = bytearray()
    header.append((0b0001 << 4) | 1)
    header.append((0b0010 << 4) | (0b0011 if is_last else 0b0001))
    header.append((0b0001 << 4) | 0b0001)
    header.extend(bytes([0x00]))

    actual_seq = -seq if is_last else seq
    compressed_segment = _gzip_compress(segment)

    req = bytearray()
    req.extend(bytes(header))
    req.extend(struct.pack(">i", actual_seq))
    req.extend(struct.pack(">I", len(compressed_segment)))
    req.extend(compressed_segment)
    return bytes(req)


def _parse_response(msg: bytes) -> dict[str, Any]:
    header_size = msg[0] & 0x0F
    message_type = msg[1] >> 4
    flags = msg[1] & 0x0F
    serialization = msg[2] >> 4
    compression = msg[2] & 0x0F
    payload = msg[header_size * 4 :]

    is_last = bool(flags & 0x02)
    code = 0

    if flags & 0x01:
        payload = payload[4:]
    if flags & 0x04:
        payload = payload[4:]

    if message_type == 0b1001:
        payload = payload[4:]
    elif message_type == 0b1111:
        code = struct.unpack(">i", payload[:4])[0]
        payload = payload[8:]

    payload_msg: Any = None
    if payload:
        if compression == 0b0001:
            payload = _gzip_decompress(payload)
        if serialization == 0b0001:
            payload_msg = json.loads(payload.decode("utf-8"))

    return {"code": code, "is_last": is_last, "payload_msg": payload_msg}


def _extract_text(payload_msg: Any) -> str:
    if payload_msg is None:
        return ""

    obj = payload_msg
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        obj = obj["result"]

    if isinstance(obj, dict) and isinstance(obj.get("utterances"), list):
        texts = []
        for u in obj["utterances"]:
            if isinstance(u, dict):
                t = u.get("text") or u.get("sentence")
                if isinstance(t, str) and t.strip():
                    texts.append(t.strip())
        if texts:
            return " ".join(texts)

    if isinstance(obj, dict):
        for k in ("text", "transcript", "sentence"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    if isinstance(payload_msg, str):
        return payload_msg.strip()
    return ""


def _extract_asr_definite(payload_msg: Any) -> bool:
    obj = payload_msg
    if isinstance(obj, dict):
        obj = obj.get("result", obj)
    if isinstance(obj, list):
        obj = obj[-1] if obj else {}
    if not isinstance(obj, dict):
        return False
    utterances = obj.get("utterances")
    if not isinstance(utterances, list):
        return False
    for item in reversed(utterances):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or item.get("sentence") or "").strip()
        if not text:
            continue
        if "definite" in item:
            return bool(item.get("definite"))
        additions = item.get("additions")
        if isinstance(additions, dict) and "definite" in additions:
            return bool(additions.get("definite"))
        break
    return False


def _has_terminal_punctuation(text: str) -> bool:
    current = (text or "").strip()
    return current.endswith(("\u3002", "\uff01", "\uff1f", "!", "?", ".", ";", "\uff1b", "~"))


def _looks_incomplete_tail(text: str) -> bool:
    current = (text or "").strip()
    if not current:
        return False
    if _has_terminal_punctuation(current):
        return False
    tail = current[-8:]
    if re.search(r"(然后|所以|因为|但是|就是|那个|这个|我现在|你现在|等一下|稍等|还有|而且|今天我|明天我)$", tail):
        return True
    if re.search(r"(能不能|是不是|对不对|行不行|可不可以|怎么|为什么|多少|几点)$", tail):
        return True
    if re.search(r"[的地得了呢吗啊呀吧嘛]$", current):
        return True
    return False


def _get_asr_silence_commit_threshold_seconds(text: str) -> float:
    current = (text or "").strip()
    base = max(0.0, ASR_SILENCE_COMMIT_SECONDS)
    if not current:
        return base
    compact = _normalize_compact_text(current)
    if _is_voice_command_text(current):
        return base
    if _is_short_confirmation_compact(compact):
        return max(base, 0.75)
    if not _has_terminal_punctuation(current):
        base += max(0.0, ASR_SILENCE_NO_PUNCT_EXTRA_SECONDS)
    if _looks_incomplete_tail(current):
        base += max(0.0, ASR_SILENCE_INCOMPLETE_TAIL_EXTRA_SECONDS)
    return base


def _normalize_compact_text(text: str) -> str:
    number_map = str.maketrans(
        {
            "零": "0",
            "〇": "0",
            "一": "1",
            "二": "2",
            "两": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
        }
    )
    return (
        (text or "")
        .translate(number_map)
        .replace(" ", "")
        .replace("\uff0c", "")
        .replace("\u3002", "")
        .replace("\uff01", "")
        .replace("\uff1f", "")
        .replace(",", "")
        .replace(".", "")
        .replace("!", "")
        .replace("?", "")
        .strip()
    )


def _is_compact_prefix_extension(base_compact: str, newer_compact: str) -> bool:
    base = (base_compact or "").strip()
    newer = (newer_compact or "").strip()
    if not base or not newer:
        return False
    if newer == base:
        return False
    if len(newer) <= len(base):
        return False
    return newer.startswith(base)


def _merge_user_text_for_nlp(previous_text: str, current_text: str) -> str:
    previous = (previous_text or "").strip()
    current = (current_text or "").strip()
    if not previous:
        return current
    if not current:
        return previous

    previous_compact = _normalize_compact_text(previous)
    current_compact = _normalize_compact_text(current)
    if previous_compact and current_compact:
        if previous_compact == current_compact:
            return current
        if _is_compact_prefix_extension(previous_compact, current_compact):
            return current
        if _is_compact_prefix_extension(current_compact, previous_compact):
            return previous

    left = previous.rstrip(" \t\r\n\uff0c\u3002\uff01\uff1f,.;!?")
    right = current.lstrip(" \t\r\n\uff0c\u3002\uff01\uff1f,.;!?")
    if not left:
        return right
    if not right:
        return left
    return f"{left}。{right}"


def _is_short_confirmation_compact(compact_text: str) -> bool:
    compact = (compact_text or "").strip()
    if not compact:
        return False
    return compact in NLP_SHORT_CONFIRM_TEXTS


def _get_nlp_stale_window_seconds(compact_text: str) -> float:
    if _is_short_confirmation_compact(compact_text):
        return max(0.0, NLP_SHORT_CONFIRM_STALE_WINDOW_SECONDS)
    return max(0.0, NLP_STALE_WINDOW_SECONDS)


def _get_nlp_stale_drop_reason(
    current_compact: str,
    last_compact: str,
    *,
    delta_seconds: float,
    stale_window_seconds: float,
) -> str:
    current = (current_compact or "").strip()
    previous = (last_compact or "").strip()
    if (not current) or (not previous):
        return ""
    if stale_window_seconds <= 0 or delta_seconds < 0 or delta_seconds > stale_window_seconds:
        return ""
    if current == previous:
        return "exact"
    # Structured values (numbers/ids) are usually high-signal; avoid aggressive near-duplicate suppression.
    if _is_structured_user_value(current) or _is_structured_user_value(previous):
        return ""
    # Prefix variants like "对，资金周转不开，开" vs "对，资金周转不开" should be deduped in a short window.
    if _is_compact_prefix_extension(previous, current) or _is_compact_prefix_extension(current, previous):
        if min(len(current), len(previous)) >= 4 and abs(len(current) - len(previous)) <= 3:
            return "prefix_variant"
    if min(len(current), len(previous)) >= 6 and abs(len(current) - len(previous)) <= 3:
        ratio = difflib.SequenceMatcher(None, current, previous).ratio()
        if ratio >= 0.92:
            return "similar_variant"
    return ""


def _is_structured_user_value(text: str) -> bool:
    current = _normalize_compact_text(text)
    if not current:
        return False
    if re.fullmatch(r"\d{3,18}", current):
        return True
    if re.fullmatch(r"[A-Za-z0-9]{3,24}", current):
        return True
    return False


def _normalize_with_index_map(text: str) -> tuple[str, list[int]]:
    number_map = {
        "零": "0",
        "〇": "0",
        "一": "1",
        "二": "2",
        "两": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
    }
    normalized_chars: list[str] = []
    raw_indexes: list[int] = []
    for idx, ch in enumerate(text or ""):
        if ch in (" ", "\t", "\r", "\n", "\uff0c", "\u3002", "\uff01", "\uff1f", ",", ".", "!", "?", ";", "\uff1b"):
            continue
        normalized_chars.append(number_map.get(ch, ch))
        raw_indexes.append(idx)
    return "".join(normalized_chars), raw_indexes


def _is_likely_tts_echo(
    asr_text: str,
    recent_ai_text: str,
    recent_ai_ts: float,
    *,
    is_definite: bool = False,
    allow_stale_recent: bool = False,
) -> bool:
    current_compact = _normalize_compact_text(asr_text)
    recent_compact = _normalize_compact_text(recent_ai_text)
    if not current_compact or not recent_compact:
        return False
    if len(current_compact) < max(3, BARGE_IN_MIN_CHARS):
        return False
    if recent_ai_ts <= 0:
        return False

    now = time.monotonic()
    elapsed = max(0.0, now - float(recent_ai_ts))
    stale_window = max(0.6, BARGE_IN_ECHO_WINDOW_SECONDS)
    if allow_stale_recent:
        stale_window *= 1.5
    if elapsed > stale_window:
        return False

    if current_compact in recent_compact:
        return True
    if (
        len(recent_compact) >= 6
        and recent_compact in current_compact
        and len(current_compact) <= len(recent_compact) + 8
    ):
        return True
    if _is_compact_prefix_extension(current_compact, recent_compact):
        return True
    if _is_compact_prefix_extension(recent_compact, current_compact):
        return True

    ratio = difflib.SequenceMatcher(None, current_compact, recent_compact).ratio()
    if ratio >= 0.76:
        return True

    return False
def _strip_ai_echo_prefix(asr_text: str, recent_ai_text: str) -> str:
    current_raw = (asr_text or "").strip()
    recent_raw = (recent_ai_text or "").strip()
    if not current_raw or not recent_raw:
        return current_raw

    current_norm, current_index_map = _normalize_with_index_map(current_raw)
    recent_norm, _ = _normalize_with_index_map(recent_raw)
    if not current_norm or not recent_norm:
        return current_raw

    max_overlap = min(len(current_norm), len(recent_norm))
    overlap = 0
    min_overlap = 6
    for k in range(max_overlap, min_overlap - 1, -1):
        if current_norm.startswith(recent_norm[-k:]):
            overlap = k
            break
    if overlap <= 0:
        return current_raw

    cut_raw_pos = current_index_map[overlap - 1] + 1
    stripped = current_raw[cut_raw_pos:].lstrip(" \t\r\n\uff0c\u3002\uff01\uff1f,.;!?")
    return stripped


def _dump_nlp_submit_payload(payload: dict[str, Any]) -> None:
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    logger.info("***** NLP提交开始 ******")
    logger.info("%s", text)
    logger.info("***** NLP提交结束 ******")


def _match_voice_command(text: str) -> str | None:
    compact = _normalize_compact_text(text)
    if not compact:
        return None
    if any(keyword in compact for keyword in VOICE_COMMAND_END_KEYWORDS):
        return VOICE_COMMAND_END
    if any(keyword in compact for keyword in VOICE_COMMAND_START_KEYWORDS):
        return VOICE_COMMAND_START
    return None


def _is_voice_command_text(text: str) -> bool:
    return _match_voice_command(text) is not None


def _is_interrupt_command_text(text: str) -> bool:
    compact = _normalize_compact_text(text)
    if not compact:
        return False
    return any(keyword in compact for keyword in ( "暂停播报", "停止播报"))


def _is_normal_user_text(text: str) -> bool:
    current = (text or "").strip()
    if not current:
        return False
    if _is_voice_command_text(current):
        return False
    cleaned = _normalize_compact_text(current)
    return len(cleaned) >= 2


def _is_barge_in_stream_text(text: str) -> bool:
    current = (text or "").strip()
    if not current:
        return False
    if _is_voice_command_text(current):
        return False
    cleaned = _normalize_compact_text(current)
    if not cleaned:
        return False
    return len(cleaned) >= BARGE_IN_MIN_CHARS


async def _terminate_process_after_delay(reason: str, delay_seconds: float = PROCESS_EXIT_DELAY_SECONDS) -> None:
    logger.warning(
        "process termination disabled for web server mode reason=%s delay_seconds=%s",
        reason,
        delay_seconds,
    )
    await asyncio.sleep(max(0.0, delay_seconds))


class ASRStreamingSession:
    def __init__(
        self,
        session_id: str,
        audio_format: str,
        on_audio_sent: Callable[[int], None] | None = None,
    ):
        self.session_id = session_id
        self.audio_format = audio_format
        self.on_audio_sent = on_audio_sent
        self.seq = 2
        self.http_session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.recv_task: Any = None
        self.sender_task: Any = None
        self.commit_task: Any = None
        self.nlp_task: Any = None
        self.connect_lock = asyncio.Lock()
        self.send_lock = asyncio.Lock()
        self.audio_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self.event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self.stream_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self.nlp_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self.last_partial_text = ""
        self.last_definite_text = ""
        self.last_submit_text = ""
        self.last_submit_compact = ""
        self.last_submit_at = 0.0
        self.silence_grace_deadline_at = 0.0
        self.silence_grace_text = ""
        self.silence_grace_compact = ""
        self.current_seen_definite = False
        self.current_seen_definite = False
        self.last_committed_text = ""
        self.best_text = ""
        self.started_at = 0.0
        self.last_update_at = 0.0
        self.last_commit_update_at: float = 0.0
        self.last_commit_started_at: float = 0.0
        self.last_touch = time.monotonic()

    def touch(self) -> None:
        self.last_touch = time.monotonic()

    def idle_seconds(self, now: float | None = None) -> float:
        current = now if now is not None else time.monotonic()
        return current - self.last_touch

    async def ensure_connected(self, audio_format: str) -> None:
        if self.ws is not None and not self.ws.closed:
            return
        if not ASR_APP_KEY or not ASR_ACCESS_KEY:
            raise HTTPException(status_code=500, detail="missing ASR_APP_KEY/ASR_ACCESS_KEY")

        async with self.connect_lock:
            if self.ws is not None and not self.ws.closed:
                return

            self.audio_format = audio_format
            if self.http_session is not None:
                try:
                    await self.http_session.close()
                except Exception:
                    pass

            timeout = aiohttp.ClientTimeout(total=None)
            self.http_session = aiohttp.ClientSession(timeout=timeout)
            self.ws = await self.http_session.ws_connect(WS_URL, headers=_new_auth_headers())
            await self.ws.send_bytes(_build_full_request(seq=1, audio_format=audio_format))
            ack = await self.ws.receive(timeout=5)
            if ack.type not in (aiohttp.WSMsgType.BINARY, aiohttp.WSMsgType.TEXT):
                raise HTTPException(status_code=502, detail=f"unexpected ASR ack type: {ack.type}")
            self.seq = 2
            self.recv_task = asyncio.create_task(self._recv_loop())
            self.touch()

    def _ensure_background_tasks_started(self) -> None:
        if self.sender_task is None or self.sender_task.done():
            self.sender_task = asyncio.create_task(self._sender_loop())
        if self.commit_task is None or self.commit_task.done():
            self.commit_task = asyncio.create_task(self._commit_loop())
        if self.nlp_task is None or self.nlp_task.done():
            self.nlp_task = asyncio.create_task(self._nlp_loop())

    def enqueue_chunk(self, audio_bytes: bytes, audio_format: str, chunk_index: int) -> None:
        self._ensure_background_tasks_started()
        item = {
            "audio_bytes": audio_bytes,
            "audio_format": audio_format,
            "chunk_index": chunk_index,
            "enqueued_at": time.monotonic(),
        }
        try:
            self.audio_queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                _ = self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self.audio_queue.put_nowait(item)
            except asyncio.QueueFull:
                pass
        self.touch()

    async def send_chunk(self, audio_bytes: bytes, audio_format: str) -> None:
        async with self.send_lock:
            await self.ensure_connected(audio_format=audio_format)
            if self.ws is None or self.ws.closed:
                raise HTTPException(status_code=502, detail="asr ws is closed")

            packet = _build_audio_request(seq=self.seq, segment=audio_bytes, is_last=False)
            self.seq += 1
            await self.ws.send_bytes(packet)
            if self.on_audio_sent is not None and audio_bytes:
                try:
                    self.on_audio_sent(len(audio_bytes))
                except Exception:
                    pass
            self.touch()

    async def _sender_loop(self) -> None:
        try:
            while True:
                item = await self.audio_queue.get()
                audio_bytes = item.get("audio_bytes") or b""
                audio_format = str(item.get("audio_format") or self.audio_format)
                chunk_index = item.get("chunk_index")
                if not audio_bytes:
                    continue
                try:
                    await self.send_chunk(audio_bytes=audio_bytes, audio_format=audio_format)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "failed to send chunk to asr session_id=%s chunk_index=%s",
                        self.session_id,
                        chunk_index,
                    )
        except asyncio.CancelledError:
            pass

    async def _recv_loop(self) -> None:
        ws = self.ws
        if ws is None:
            return
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.BINARY:
                    parsed = _parse_response(msg.data)
                    if parsed["code"] != 0:
                        logger.warning("asr server code=%s session=%s", parsed["code"], self.session_id)
                        continue
                    payload = parsed.get("payload_msg")
                    text = _extract_text(payload).strip()
                    if not text:
                        continue
                    is_definite = _extract_asr_definite(payload)
                    self.last_partial_text = text
                    if is_definite:
                        self.last_definite_text = text
                    logger.info("ASR realtime: %s", text)
                    logger.info(
                        "asr stream session_id=%s text=%s definite=%s",
                        self.session_id,
                        text,
                        is_definite,
                    )
                    event = {"text": text, "is_definite": is_definite, "ts": time.monotonic()}
                    try:
                        self.event_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        try:
                            _ = self.event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            self.event_queue.put_nowait(event)
                        except asyncio.QueueFull:
                            pass
                    try:
                        self.stream_event_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        try:
                            _ = self.stream_event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            self.stream_event_queue.put_nowait(event)
                        except asyncio.QueueFull:
                            pass
                    continue

                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    break
                if msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning("asr ws error session=%s err=%s", self.session_id, ws.exception())
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("asr recv loop failed session=%s", self.session_id)
        finally:
            if self.ws is ws:
                self.ws = None

    def _merge_event_batch(self, events: list[dict[str, Any]], queue_name: str) -> dict[str, Any] | None:
        if not events:
            return None
        merged = dict(events[0])
        prefix_merged = 0
        for event in events[1:]:
            candidate = dict(event)
            merged_text = str(merged.get("text") or "").strip()
            candidate_text = str(candidate.get("text") or "").strip()
            merged_compact = _normalize_compact_text(merged_text)
            candidate_compact = _normalize_compact_text(candidate_text)
            is_prefix_related = bool(
                merged_compact
                and candidate_compact
                and (
                    merged_compact.startswith(candidate_compact)
                    or candidate_compact.startswith(merged_compact)
                )
            )
            if is_prefix_related:
                prefix_merged += 1
                if len(candidate_compact) >= len(merged_compact):
                    merged = candidate
                # definite 只要任一分段确认即可保留，便于更快提交。
                merged["is_definite"] = bool(merged.get("is_definite")) or bool(candidate.get("is_definite"))
                try:
                    merged["ts"] = max(float(merged.get("ts") or 0.0), float(candidate.get("ts") or 0.0))
                except Exception:
                    pass
                continue
            # 非前缀关系时默认取更新的一条，避免错误拼接造成“假句子”。
            merged = candidate
        if len(events) > 1:
            logger.info(
                "asr %s drain merge session_id=%s drained=%s prefix_merged=%s final=%s",
                queue_name,
                self.session_id,
                len(events),
                prefix_merged,
                str(merged.get("text") or "").strip(),
            )
        return merged

    async def pop_latest_event(self, timeout_seconds: float) -> dict[str, Any] | None:
        events: list[dict[str, Any]] = []
        try:
            first = await asyncio.wait_for(self.event_queue.get(), timeout=timeout_seconds)
            events.append(first)
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

        while True:
            try:
                events.append(self.event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return self._merge_event_batch(events, "event")

    async def pop_latest_stream_event(self, timeout_seconds: float) -> dict[str, Any] | None:
        events: list[dict[str, Any]] = []
        try:
            first = await asyncio.wait_for(self.stream_event_queue.get(), timeout=timeout_seconds)
            events.append(first)
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

        while True:
            try:
                events.append(self.stream_event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return self._merge_event_batch(events, "stream_event")

    async def claim_definite_text(self, timeout_seconds: float) -> str:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            now = time.monotonic()
            committed = self._commit_by_time(now)
            if committed:
                return committed

            remaining = deadline - now
            if remaining <= 0:
                return ""

            event = await self.pop_latest_event(timeout_seconds=remaining)
            if event is None:
                continue
            committed = self._consume_event(event)
            if committed:
                return committed

    async def _commit_loop(self) -> None:
        try:
            while True:
                committed = await self.claim_definite_text(timeout_seconds=ASR_RESULT_TIMEOUT_SECONDS)
                if committed:
                    self.last_committed_text = committed
                    self._enqueue_nlp_text(committed)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("asr commit loop failed session=%s", self.session_id)

    def _enqueue_nlp_text(self, text: str) -> None:
        item = {"text": (text or "").strip(), "ts": time.monotonic()}
        if not item["text"]:
            return
        try:
            self.nlp_queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass
        try:
            _ = self.nlp_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self.nlp_queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def _nlp_loop(self) -> None:
        try:
            while True:
                item = await self.nlp_queue.get()
                user_text = str(item.get("text") or "").strip()
                if not user_text:
                    continue
                command = _match_voice_command(user_text)
                if command == VOICE_COMMAND_END:
                    logger.info("received end command in nlp loop session_id=%s text=%s", self.session_id, user_text)
                    break
                if command == VOICE_COMMAND_START:
                    reply = await _generate_next_script(
                        session_id=self.session_id,
                        user_text=user_text,
                        transient_system_prompt=START_TRIGGER,
                    )
                    if reply:
                        logger.info("NLP start script session_id=%s text=%s", self.session_id, reply)
                    continue
                reply = await _generate_next_script(session_id=self.session_id, user_text=user_text)
                if reply:
                    logger.info("NLP next script session_id=%s text=%s", self.session_id, reply)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("nlp loop failed session=%s", self.session_id)

    def _reset_commit_state(self) -> None:
        self.best_text = ""
        self.started_at = 0.0
        self.last_update_at = 0.0
        self.silence_grace_deadline_at = 0.0
        self.silence_grace_text = ""
        self.silence_grace_compact = ""

    def _commit_text(self, text: str) -> str:
        committed = (text or "").strip()
        committed_compact = _normalize_compact_text(committed)
        prev_text = self.last_submit_text
        prev_compact = self.last_submit_compact
        prev_ts = float(self.last_submit_at or 0.0)
        now_ts = time.monotonic()
        self.last_commit_update_at = self.last_update_at  # 在 reset 前保存，供外部读取 ASR 静音等待耗时
        self.last_commit_started_at = self.started_at    # 在 reset 前保存，供外部计算 ASR 识别耗时
        self._reset_commit_state()
        if not committed:
            return ""
        if committed == prev_text:
            logger.info(
                "drop asr commit duplicate exact session_id=%s text=%s",
                self.session_id,
                committed,
            )
            return ""
        if committed_compact and committed_compact == prev_compact:
            logger.info(
                "drop asr commit duplicate compact session_id=%s text=%s compact=%s",
                self.session_id,
                committed,
                committed_compact,
            )
            return ""
        if (
            committed_compact
            and prev_compact
            and _is_compact_prefix_extension(prev_compact, committed_compact)
            and (now_ts - prev_ts) <= ASR_POST_COMMIT_EXTENSION_WINDOW_SECONDS
        ):
            logger.info(
                "asr commit prefix-extension correction session_id=%s prev=%s new=%s delta_ms=%.1f",
                self.session_id,
                prev_text,
                committed,
                (now_ts - prev_ts) * 1000.0,
            )
        self.last_submit_text = committed
        self.last_submit_compact = committed_compact
        self.last_submit_at = now_ts
        logger.info("***** %s *******", committed)
        return committed

    def _consume_event(self, event: dict[str, Any]) -> str:
        now = time.monotonic()
        raw_text = str(event.get("text") or "").strip()
        is_definite = bool(event.get("is_definite"))
        event_ts = float(event.get("ts") or now)

        if not raw_text:
            return ""
        if self.started_at <= 0:
            self.started_at = now
            self.last_update_at = now
        if event_ts < self.started_at - 0.05:
            return ""

        incoming_compact = _normalize_compact_text(raw_text)
        if self.silence_grace_deadline_at > 0 and self.silence_grace_compact:
            if _is_compact_prefix_extension(self.silence_grace_compact, incoming_compact):
                logger.info(
                    "asr silence grace extend session_id=%s old=%s new=%s",
                    self.session_id,
                    self.silence_grace_text,
                    raw_text,
                )
                self.silence_grace_deadline_at = 0.0
                self.silence_grace_text = ""
                self.silence_grace_compact = ""

        best_compact = _normalize_compact_text(self.best_text)
        progressed = False
        if len(raw_text) >= len(self.best_text):
            self.best_text = raw_text
            progressed = True
        elif incoming_compact and best_compact and _is_compact_prefix_extension(best_compact, incoming_compact):
            self.best_text = raw_text
            progressed = True
        if progressed:
            self.last_update_at = now
            if self.silence_grace_deadline_at > 0:
                self.silence_grace_deadline_at = 0.0
                self.silence_grace_text = ""
                self.silence_grace_compact = ""

        logger.info("asr stream session_id=%s text=%s definite=%s", self.session_id, raw_text, is_definite)
        if is_definite:
            self.current_seen_definite = True
        if is_definite and self.best_text:
            logger.info("asr definite commit session_id=%s text=%s", self.session_id, self.best_text)
            return self._commit_text(self.best_text)
        return ""

    def _commit_by_time(self, now: float) -> str:
        if self.started_at <= 0:
            return ""

        elapsed = now - self.started_at
        if elapsed >= ASR_MAX_LISTEN_SECONDS:
            if self.best_text:
                logger.info("asr max listen commit session_id=%s text=%s", self.session_id, self.best_text)
                return self._commit_text(self.best_text)
            logger.info("asr max listen reset empty session_id=%s text=%s", self.session_id, self.best_text)
            self._reset_commit_state()
            return ""

        if not self.best_text:
            return ""

        if self.silence_grace_deadline_at > 0:
            if now < self.silence_grace_deadline_at:
                return ""
            if self.best_text:
                logger.info("asr silence grace commit session_id=%s text=%s", self.session_id, self.best_text)
                return self._commit_text(self.best_text)
            logger.info("asr silence grace reset empty session_id=%s text=%s", self.session_id, self.best_text)
            self._reset_commit_state()
            return ""

        silence = now - self.last_update_at
        silence_threshold = _get_asr_silence_commit_threshold_seconds(self.best_text)
        if silence < silence_threshold:
            return ""

        if (
            (not self.current_seen_definite)
            and (not _is_voice_command_text(self.best_text))
            and (not _has_terminal_punctuation(self.best_text))
            and len((self.best_text or "").strip()) >= 4
            and silence < (silence_threshold + max(0.0, ASR_DEFINITE_PREFER_WAIT_SECONDS))
        ):
            return ""

        if ASR_SILENCE_COMMIT_GRACE_SECONDS > 0:
            self.silence_grace_deadline_at = now + ASR_SILENCE_COMMIT_GRACE_SECONDS
            self.silence_grace_text = self.best_text
            self.silence_grace_compact = _normalize_compact_text(self.best_text)
            logger.info(
                "asr silence grace armed session_id=%s text=%s grace_ms=%.1f",
                self.session_id,
                self.best_text,
                ASR_SILENCE_COMMIT_GRACE_SECONDS * 1000.0,
            )
            return ""

        logger.info("asr silence commit session_id=%s text=%s", self.session_id, self.best_text)
        return self._commit_text(self.best_text)

    async def close(self) -> None:
        if self.nlp_task is not None:
            self.nlp_task.cancel()
            try:
                await self.nlp_task
            except Exception:
                pass
            self.nlp_task = None
        if self.sender_task is not None:
            self.sender_task.cancel()
            try:
                await self.sender_task
            except Exception:
                pass
            self.sender_task = None
        if self.commit_task is not None:
            self.commit_task.cancel()
            try:
                await self.commit_task
            except Exception:
                pass
            self.commit_task = None
        if self.recv_task is not None:
            self.recv_task.cancel()
            try:
                await self.recv_task
            except Exception:
                pass
            self.recv_task = None
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
        if self.http_session is not None:
            try:
                await self.http_session.close()
            except Exception:
                pass
            self.http_session = None


ASR_SESSIONS: dict[str, ASRStreamingSession] = {}
ASR_SESSIONS_LOCK = threading.Lock()
_LAST_ASR_CLEANUP_AT = 0.0


def _get_or_create_asr_session(session_id: str, audio_format: str) -> ASRStreamingSession:
    with ASR_SESSIONS_LOCK:
        session = ASR_SESSIONS.get(session_id)
        if session is None:
            session = ASRStreamingSession(session_id=session_id, audio_format=audio_format)
            ASR_SESSIONS[session_id] = session
        return session


async def _cleanup_idle_asr_sessions(force: bool = False) -> None:
    global _LAST_ASR_CLEANUP_AT
    now = time.monotonic()
    if (not force) and (now - _LAST_ASR_CLEANUP_AT) < ASR_SESSION_CLEANUP_INTERVAL_SECONDS:
        return
    _LAST_ASR_CLEANUP_AT = now

    stale_items: list[tuple[str, ASRStreamingSession]] = []
    with ASR_SESSIONS_LOCK:
        for sid, sess in list(ASR_SESSIONS.items()):
            if sess.idle_seconds(now) >= ASR_SESSION_IDLE_SECONDS:
                stale_items.append((sid, sess))
                del ASR_SESSIONS[sid]

    for sid, sess in stale_items:
        await sess.close()
        logger.info("asr session closed for idle timeout session_id=%s", sid)


async def _close_all_asr_sessions() -> None:
    sessions: list[ASRStreamingSession] = []
    with ASR_SESSIONS_LOCK:
        for _, sess in ASR_SESSIONS.items():
            sessions.append(sess)
        ASR_SESSIONS.clear()
    for sess in sessions:
        await sess.close()


def _put_latest_queue_item(queue: asyncio.Queue[Any], item: Any) -> None:
    if not item:
        return
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        # Keep FIFO semantics for dialogue integrity: do not evict old items.
        logger.warning("queue is full, drop newest item: %s", str(item)[:200])


def _pop_tts_segments(buffer: str) -> tuple[list[str], str]:
    segments: list[str] = []
    start = 0
    for idx, ch in enumerate(buffer):
        if ch in ("\u3002", "\uff01", "\uff1f", "\uff1b", "!", "?", ";", "\n"):
            seg = buffer[start : idx + 1].strip()
            if seg:
                segments.append(seg)
            start = idx + 1
    return segments, buffer[start:]


def _trim_to_complete_sentence(text: str) -> str:
    current = (text or "").strip()
    if not current:
        return ""
    last_cut = -1
    for idx, ch in enumerate(current):
        if ch in ("\u3002", "\uff01", "\uff1f", "\uff1b", "!", "?", ";", "\n"):
            last_cut = idx
    if last_cut >= 0:
        return current[: last_cut + 1].strip()
    return ""


def _iter_audio_frames(audio: bytes, frame_bytes: int) -> Generator[bytes, None, None]:
    if not audio:
        return
    if frame_bytes <= 0 or len(audio) <= frame_bytes:
        yield audio
        return
    for offset in range(0, len(audio), frame_bytes):
        frame = audio[offset : offset + frame_bytes]
        if frame:
            yield frame


def _get_session_system_prompt(session_id: str) -> str:
    with SESSION_SYSTEM_PROMPT_LOCK:
        prompt = str(SESSION_SYSTEM_PROMPT.get(session_id, "") or "").strip()
    return prompt or SYSTEM_PROMPT


def _set_session_system_prompt(session_id: str, prompt: str) -> None:
    normalized = (prompt or "").strip()
    with SESSION_SYSTEM_PROMPT_LOCK:
        if normalized:
            SESSION_SYSTEM_PROMPT[session_id] = normalized
        else:
            SESSION_SYSTEM_PROMPT.pop(session_id, None)


def _clear_session_system_prompt(session_id: str) -> None:
    with SESSION_SYSTEM_PROMPT_LOCK:
        SESSION_SYSTEM_PROMPT.pop(session_id, None)


def _build_messages(
    session_id: str,
    user_text: str,
    transient_system_prompt: str | None = None,
) -> list[dict[str, str]]:
    with SESSION_HISTORY_LOCK:
        history = list(SESSION_HISTORY.get(session_id, []))
    messages = [{"role": "system", "content": _get_session_system_prompt(session_id)}]
    if transient_system_prompt:
        messages.append({"role": "system", "content": transient_system_prompt})
    messages.extend(history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": user_text})
    return messages


def _format_nlp_prompt_messages(messages: list[dict[str, str]], max_chars: int = 6000) -> str:
    parts: list[str] = []
    for item in messages:
        role = str(item.get("role") or "").strip() or "unknown"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        compact = " ".join(content.replace("\r", " ").replace("\n", " ").split())
        if not compact:
            continue
        parts.append(f"{role}: {compact}")
    if not parts:
        return ""
    text = " || ".join(parts)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + " ...[truncated]"


def _build_intent_context_lines(session_id: str, window_size: int) -> list[str]:
    with SESSION_HISTORY_LOCK:
        history = list(SESSION_HISTORY.get(session_id, []))
    recent = history[-max(0, window_size) :] if window_size > 0 else []
    lines: list[str] = []
    for item in recent:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        speaker = "客户" if role == "user" else "催收员"
        lines.append(f"{speaker}: {content}")
    return lines


def _try_parse_json_object(text: str) -> Any:
    current = (text or "").strip()
    if not current:
        return None
    try:
        return json.loads(current)
    except Exception:
        pass
    if "```" in current:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", current, flags=re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except Exception:
                pass
    start = current.find("{")
    end = current.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(current[start : end + 1])
        except Exception:
            pass
    return None


def _build_intent_label_index(label_library: list[str]) -> tuple[list[str], set[str], dict[str, str]]:
    normalized = _normalize_intent_labels(_parse_intent_labels_payload(label_library))
    label_set = set(normalized)
    code_map = {label.casefold(): label for label in normalized}
    return normalized, label_set, code_map


def _normalize_intent_label(
    value: Any,
    label_library: list[str],
    label_set: set[str],
    label_code_map: dict[str, str],
) -> str:
    raw = str(value or "").strip().strip("[]\"'")
    if not raw:
        return ""
    if raw in label_set:
        return raw
    mapped = label_code_map.get(raw.casefold())
    if mapped:
        return mapped
    for label in label_library:
        if raw.startswith(label) or label in raw:
            return label
    return ""


def _extract_intent_labels(raw_output: str, label_library: list[str]) -> list[str]:
    current_library, label_set, label_code_map = _build_intent_label_index(label_library)
    candidates: list[Any] = []
    parsed = _try_parse_json_object(raw_output)
    if isinstance(parsed, dict):
        value = parsed.get("intents")
        if isinstance(value, list):
            candidates.extend(value)
        elif value is not None:
            candidates.append(value)
    elif isinstance(parsed, list):
        candidates.extend(parsed)

    if not candidates:
        for label in current_library:
            if label and (label in (raw_output or "")):
                candidates.append(label)

    labels: list[str] = []
    seen: set[str] = set()
    max_labels = max(1, INTENT_MAX_LABELS)
    for item in candidates:
        normalized = _normalize_intent_label(
            item,
            label_library=current_library,
            label_set=label_set,
            label_code_map=label_code_map,
        )
        if not normalized or normalized in seen:
            continue
        labels.append(normalized)
        seen.add(normalized)
        if len(labels) >= max_labels:
            break
    return labels


async def _classify_customer_intents(
    session_id: str,
    user_text: str,
    on_usage: Callable[[str, dict[str, int]], None] | None = None,
) -> tuple[list[str], str, str]:
    if ARK_CLIENT is None:
        raise HTTPException(status_code=500, detail="missing ARK_API_KEY")

    label_library = _get_session_intent_labels(session_id=session_id)
    fallback_label = _get_session_intent_fallback_label(session_id=session_id)
    effective_library = list(label_library)
    if fallback_label and fallback_label not in effective_library:
        effective_library.append(fallback_label)
    if not effective_library:
        return [], "no_intent_labels_configured", ""

    last_customer_utterance = (user_text or "").strip()
    if not last_customer_utterance:
        if fallback_label:
            return [fallback_label], "empty_last_customer_utterance", ""
        return [], "empty_last_customer_utterance", ""

    context_lines = _build_intent_context_lines(
        session_id=session_id,
        window_size=max(0, INTENT_CONTEXT_WINDOW),
    )
    label_set_json = json.dumps(effective_library, ensure_ascii=False)
    context_window_text = "\n".join(context_lines) if context_lines else "<empty>"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "输入格式：\n"
                f"label_set: {label_set_json}\n"
                f"fallback_label: {fallback_label or '<none>'}\n"
                f"context_window (最近{max(0, INTENT_CONTEXT_WINDOW)}条历史，仅供消歧):\n{context_window_text}\n"
                f"last_customer_utterance: {last_customer_utterance}\n\n"
                '请输出 JSON，例如 {"intents":["标签A"],"reason":"..."}'
            ),
        },
    ]
    intent_prompt_text = _format_nlp_prompt_messages(messages=messages)
    kwargs: dict[str, Any] = {
        "model": INTENT_MODEL_ID,
        "messages": messages,
        "extra_body": NON_THINKING_EXTRA_BODY,
    }
    if ARK_MAX_TOKENS > 0:
        kwargs["max_tokens"] = max(96, min(ARK_MAX_TOKENS, 256))

    response = await ARK_CLIENT.chat.completions.create(**kwargs)
    if on_usage is not None:
        try:
            response_usage = _extract_usage_metrics(getattr(response, "usage", None))
            if response_usage["total_tokens"] > 0:
                on_usage(INTENT_MODEL_ID, response_usage)
        except Exception:
            pass
    content = ""
    try:
        choices = getattr(response, "choices", None) or []
        if choices:
            message = getattr(choices[0], "message", None)
            content = str(getattr(message, "content", "") or "").strip()
    except Exception:
        content = ""
    labels = _extract_intent_labels(content, label_library=effective_library)
    if not labels:
        if fallback_label:
            labels = [fallback_label]
        else:
            labels = []
    return labels[: max(1, min(INTENT_MAX_LABELS, len(effective_library)))], content, intent_prompt_text


def _append_history(session_id: str, user_text: str, assistant_reply: str) -> None:
    user_text = (user_text or "").strip()
    assistant_reply = (assistant_reply or "").strip()
    if not user_text and not assistant_reply:
        return
    with SESSION_HISTORY_LOCK:
        history = SESSION_HISTORY.setdefault(session_id, [])
        if user_text:
            history.append({"role": "user", "content": user_text})
        if assistant_reply:
            history.append({"role": "assistant", "content": assistant_reply})
        if len(history) > MAX_HISTORY_MESSAGES * 2:
            SESSION_HISTORY[session_id] = history[-MAX_HISTORY_MESSAGES * 2 :]


def _new_tts_client() -> AsyncTTSClient:
    params = ConnectionParams(
        speaker=TTS_VOICE_TYPE,
        audio_params=AudioParams(format=TTS_AUDIO_FORMAT, sample_rate=TTS_SAMPLE_RATE),
    )
    return AsyncTTSClient(
        access_key=TTS_ACCESS_KEY,
        app_key=TTS_APP_KEY,
        connection_params=params,
        api_resource_id=TTS_RESOURCE_ID,
        base_url=TTS_WS_URL,
    )


async def _generate_next_script(
    session_id: str,
    user_text: str,
    transient_system_prompt: str | None = None,
) -> str:
    messages = _build_messages(
        session_id=session_id,
        user_text=user_text,
        transient_system_prompt=transient_system_prompt,
    )
    reply_parts: list[str] = []
    nlp_started_at = time.monotonic()
    first_token_logged = False
    try:
        async for token_text in _iter_llm_tokens(messages=messages):
            if not first_token_logged:
                first_token_logged = True
                first_token_latency_ms = (time.monotonic() - nlp_started_at) * 1000.0
                logger.info(
                    "NLP first token latency session_id=%s latency_ms=%.1f",
                    session_id,
                    first_token_latency_ms,
                )
            reply_parts.append(token_text)
            logger.info("NLP token session_id=%s token=%s", session_id, token_text)
    except Exception:
        logger.exception("failed to generate nlp reply session_id=%s", session_id)
    assistant_reply = "".join(reply_parts).strip()
    _append_history(session_id=session_id, user_text=user_text, assistant_reply=assistant_reply)
    return assistant_reply


async def _iter_llm_tokens(
    messages: list[dict[str, str]],
    cancel_event: asyncio.Event | None = None,
    on_usage: Callable[[str, dict[str, int]], None] | None = None,
) -> AsyncGenerator[str, None]:
    if ARK_CLIENT is None:
        raise HTTPException(status_code=500, detail="missing ARK_API_KEY")

    kwargs: dict[str, Any] = {
        "model": ARK_MODEL_ID,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "extra_body": NON_THINKING_EXTRA_BODY,
    }
    if ARK_MAX_TOKENS > 0:
        kwargs["max_tokens"] = ARK_MAX_TOKENS
    _dump_nlp_submit_payload(kwargs)

    try:
        stream = await ARK_CLIENT.chat.completions.create(**kwargs)
    except Exception as exc:
        if "stream_options" in str(exc):
            kwargs.pop("stream_options", None)
            stream = await ARK_CLIENT.chat.completions.create(**kwargs)
        else:
            raise

    async def _force_close_stream() -> bool:
        closed = False
        close_fn = getattr(stream, "close", None)
        if callable(close_fn):
            try:
                result = close_fn()
                if inspect.isawaitable(result):
                    await result
                closed = True
            except Exception:
                pass
        response_obj = getattr(stream, "response", None)
        if response_obj is not None:
            response_close = getattr(response_obj, "close", None)
            if callable(response_close):
                try:
                    response_result = response_close()
                    if inspect.isawaitable(response_result):
                        await response_result
                    closed = True
                except Exception:
                    pass
        return closed

    cancel_watcher_task: asyncio.Task[Any] | None = None
    if cancel_event is not None:
        async def _cancel_watcher() -> None:
            await cancel_event.wait()
            if await _force_close_stream():
                logger.info("llm stream closed by cancel_event")
        cancel_watcher_task = asyncio.create_task(_cancel_watcher())

    try:
        async for chunk in stream:
            if cancel_event is not None and cancel_event.is_set():
                break
            choices = getattr(chunk, "choices", None)
            if on_usage is not None:
                try:
                    usage_obj = getattr(chunk, "usage", None)
                    if usage_obj is not None and (not choices):
                        usage_metrics = _extract_usage_metrics(usage_obj)
                        if usage_metrics["total_tokens"] > 0:
                            on_usage(ARK_MODEL_ID, usage_metrics)
                except Exception:
                    pass
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            text = getattr(delta, "content", None) or ""
            if not text:
                continue
            yield text
    except Exception as exc:
        if cancel_event is not None and cancel_event.is_set():
            logger.info("llm stream stop after cancel_event err=%s", exc.__class__.__name__)
            return
        exc_name = exc.__class__.__name__
        if exc_name in ("ReadError", "StreamClosed", "RemoteProtocolError"):
            logger.warning("llm stream read closed err=%s", exc_name)
            return
        raise
    finally:
        if cancel_watcher_task is not None:
            cancel_watcher_task.cancel()
            try:
                await cancel_watcher_task
            except Exception:
                pass


async def _iter_llm_segments(
    messages: list[dict[str, str]],
    reply_parts: list[str],
    cancel_event: asyncio.Event | None = None,
    on_token: Callable[[str], None] | None = None,
    on_usage: Callable[[str, dict[str, int]], None] | None = None,
    on_segment: Callable[[str], Any] | None = None,
) -> AsyncGenerator[str, None]:
    tts_buffer = ""
    async for text in _iter_llm_tokens(messages=messages, cancel_event=cancel_event, on_usage=on_usage):
        if cancel_event is not None and cancel_event.is_set():
            break
        if on_token is not None:
            try:
                on_token(text)
            except Exception:
                pass
        reply_parts.append(text)
        tts_buffer += text

        segments, tts_buffer = _pop_tts_segments(tts_buffer)
        for seg in segments:
            if on_segment is not None:
                try:
                    maybe_result = on_segment(seg)
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                except Exception:
                    pass
            yield seg
        if len(tts_buffer.strip()) >= TTS_MIN_CHARS_PER_PUSH:
            seg = tts_buffer.strip()
            tts_buffer = ""
            if seg:
                if on_segment is not None:
                    try:
                        maybe_result = on_segment(seg)
                        if inspect.isawaitable(maybe_result):
                            await maybe_result
                    except Exception:
                        pass
                yield seg

    tail = tts_buffer.strip()
    if tail and (cancel_event is None or not cancel_event.is_set()):
        if on_segment is not None:
            try:
                maybe_result = on_segment(tail)
                if inspect.isawaitable(maybe_result):
                    await maybe_result
            except Exception:
                pass
        yield tail


async def _empty_audio_stream() -> AsyncGenerator[bytes, None]:
    if False:
        yield b""


async def _stream_tts_audio(
    messages: list[dict[str, str]],
    session_id: str,
    reply_parts_out: list[str] | None = None,
    cancel_event: asyncio.Event | None = None,
    on_token: Callable[[str], None] | None = None,
    on_usage: Callable[[str, dict[str, int]], None] | None = None,
    on_segment: Callable[[str], Any] | None = None,
    on_tts_usage: Callable[[int], None] | None = None,
) -> AsyncGenerator[bytes, None]:
    if not TTS_APP_KEY or not TTS_ACCESS_KEY:
        raise HTTPException(status_code=500, detail="missing TTS_APP_KEY/TTS_ACCESS_KEY")

    # Use the caller-provided list directly so tokens are visible outside even if this
    # generator is closed early via aclose() before its post-loop finalizer runs.
    reply_parts: list[str] = reply_parts_out if reply_parts_out is not None else []
    total_audio_bytes = 0
    interrupted = False
    canceled_by_user = False
    timed_out = False
    retry_index = 0
    retry_reason = ""
    tts_usage_seen_total = 0
    tts_started_at = time.monotonic()
    while True:
        tts_client = _new_tts_client()
        tts_iter: AsyncIterable[Any] | None = None
        tts_iter_obj: Any = None
        pending_chunk_task: asyncio.Task[Any] | None = None
        should_retry = False
        attempt_reason = ""
        try:
            if retry_index > 0 and total_audio_bytes <= 0:
                reply_parts.clear()
            text_segments = _iter_llm_segments(
                messages=messages,
                reply_parts=reply_parts,
                cancel_event=cancel_event,
                on_token=on_token,
                on_usage=on_usage,
                on_segment=on_segment,
            )
            tts_iter = tts_client.tts(text_segments, stream=True, include_transcript=False)
            tts_iter_obj = tts_iter.__aiter__()
            while True:
                if (time.monotonic() - tts_started_at) >= TTS_TURN_TIMEOUT_SECONDS:
                    interrupted = True
                    timed_out = True
                    logger.warning(
                        "tts turn timeout session_id=%s timeout_s=%.1f",
                        session_id,
                        TTS_TURN_TIMEOUT_SECONDS,
                    )
                    break
                if cancel_event is not None and cancel_event.is_set():
                    interrupted = True
                    canceled_by_user = True
                    break
                timeout_seconds = (
                    TTS_FIRST_AUDIO_TIMEOUT_SECONDS if total_audio_bytes <= 0 else TTS_INTER_CHUNK_TIMEOUT_SECONDS
                )
                if pending_chunk_task is None:
                    pending_chunk_task = asyncio.create_task(tts_iter_obj.__anext__())
                try:
                    done, _ = await asyncio.wait({pending_chunk_task}, timeout=timeout_seconds)
                    if not done:
                        if cancel_event is not None and cancel_event.is_set():
                            interrupted = True
                            canceled_by_user = True
                            break
                        logger.warning(
                            "tts chunk timeout session_id=%s first_chunk=%s timeout_s=%.1f",
                            session_id,
                            total_audio_bytes <= 0,
                            timeout_seconds,
                        )
                        if total_audio_bytes <= 0:
                            timed_out = True
                            should_retry = retry_index < len(TTS_RETRY_DELAYS_SECONDS)
                            attempt_reason = "first_chunk_timeout"
                            break
                        interrupted = True
                        timed_out = True
                        break
                    chunk = pending_chunk_task.result()
                    pending_chunk_task = None
                except StopAsyncIteration:
                    pending_chunk_task = None
                    break
                except Exception as exc:
                    pending_chunk_task = None
                    if cancel_event is not None and cancel_event.is_set():
                        interrupted = True
                        canceled_by_user = True
                        break
                    err_text = str(exc)
                    recoverable = (
                        ("Connection is not established" in err_text)
                        or ("timed out during opening handshake" in err_text)
                        or ("opening handshake" in err_text and "timeout" in err_text.lower())
                    )
                    if recoverable:
                        logger.warning("tts connection error session_id=%s err=%s", session_id, err_text)
                        timed_out = True
                        should_retry = total_audio_bytes <= 0 and retry_index < len(TTS_RETRY_DELAYS_SECONDS)
                        attempt_reason = "connection_error"
                        if should_retry:
                            break
                        interrupted = True
                        break
                    raise
                if on_tts_usage is not None:
                    try:
                        raw_chars = _extract_tts_usage_chars(chunk)
                        if raw_chars > 0:
                            if raw_chars >= tts_usage_seen_total:
                                delta_chars = raw_chars - tts_usage_seen_total
                                tts_usage_seen_total = raw_chars
                            else:
                                delta_chars = raw_chars
                            if delta_chars > 0:
                                on_tts_usage(delta_chars)
                    except Exception:
                        pass
                audio = chunk.audio or b""
                if audio:
                    total_audio_bytes += len(audio)
                    yield audio
        except asyncio.CancelledError:
            interrupted = True
            canceled_by_user = True
        except Exception:
            logger.exception("failed to stream TTS audio")
            interrupted = True
            timed_out = True
            should_retry = total_audio_bytes <= 0 and retry_index < len(TTS_RETRY_DELAYS_SECONDS)
            attempt_reason = "unexpected_error"
        finally:
            # We prioritize interruption handoff latency over final TTS usage collection.
            # Do not block on session_finished after interruption; close immediately.
            if interrupted and tts_iter_obj is not None:
                logger.info("skip tts session_finished wait after interrupt session_id=%s", session_id)

            if pending_chunk_task is not None and not pending_chunk_task.done():
                pending_chunk_task.cancel()
                try:
                    await asyncio.wait_for(
                        pending_chunk_task,
                        timeout=max(0.01, TTS_CANCEL_PENDING_TASK_WAIT_SECONDS),
                    )
                except asyncio.TimeoutError:
                    logger.info(
                        "tts pending chunk cancel timeout session_id=%s timeout_s=%.3f",
                        session_id,
                        max(0.01, TTS_CANCEL_PENDING_TASK_WAIT_SECONDS),
                    )
                except BaseException:
                    pass

            if tts_iter_obj is not None:
                close_fn = getattr(tts_iter_obj, "aclose", None)
                if callable(close_fn):
                    try:
                        close_result = close_fn()
                        if inspect.isawaitable(close_result):
                            await asyncio.wait_for(
                                close_result,
                                timeout=max(0.01, TTS_CANCEL_ACLOSE_TIMEOUT_SECONDS),
                            )
                    except asyncio.TimeoutError:
                        logger.info(
                            "tts iterator aclose timeout session_id=%s timeout_s=%.3f",
                            session_id,
                            max(0.01, TTS_CANCEL_ACLOSE_TIMEOUT_SECONDS),
                        )
                    except BaseException:
                        pass
            close_client_fn = getattr(tts_client, "close", None)
            if callable(close_client_fn):
                try:
                    close_client_result = close_client_fn()
                    if inspect.isawaitable(close_client_result):
                        await asyncio.wait_for(
                            close_client_result,
                            timeout=max(0.01, TTS_CANCEL_CLIENT_CLOSE_TIMEOUT_SECONDS),
                        )
                except asyncio.TimeoutError:
                    logger.info(
                        "tts client close timeout session_id=%s timeout_s=%.3f",
                        session_id,
                        max(0.01, TTS_CANCEL_CLIENT_CLOSE_TIMEOUT_SECONDS),
                    )
                except BaseException:
                    pass

        if interrupted or canceled_by_user:
            break
        if not should_retry:
            break
        delay_seconds = TTS_RETRY_DELAYS_SECONDS[retry_index]
        retry_index += 1
        retry_reason = attempt_reason or "unknown"
        logger.warning(
            "tts retry scheduled session_id=%s attempt=%s delay_s=%.2f reason=%s",
            session_id,
            retry_index,
            delay_seconds,
            retry_reason,
        )
        await asyncio.sleep(delay_seconds)

    try:
        # reply_parts is already reply_parts_out (same object), so no copy needed.
        # _append_history is handled by run_tts_turn after the generator loop to
        # guarantee it runs even when this generator is closed early via aclose().
        assistant_reply = "".join(reply_parts).strip()
        if timed_out:
            logger.info(
                "tts turn ended by timeout session_id=%s assistant_chars=%s audio_bytes=%s",
                session_id,
                len(assistant_reply),
                total_audio_bytes,
            )
            if retry_reason:
                logger.info(
                    "tts turn timeout reason session_id=%s reason=%s retries=%s",
                    session_id,
                    retry_reason,
                    retry_index,
                )
        if assistant_reply:
            logger.info("NLP reply session_id=%s text=%s", session_id, assistant_reply)
        logger.info(
            "session_id=%s assistant_chars=%s tts_audio_bytes=%s",
            session_id,
            len(assistant_reply),
            total_audio_bytes,
        )
    except Exception:
        logger.exception("failed to finalize tts turn session_id=%s", session_id)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/debug/whoami")
async def debug_whoami(request: Request) -> dict[str, Any]:
    probe = {
        "ok": True,
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "revision": os.getenv("K_REVISION", ""),
        "pod_name": os.getenv("HOSTNAME", ""),
        "function_name": os.getenv("FUNCTION_NAME", ""),
        "function_id": os.getenv("FUNCTION_ID", ""),
        "client": request.client.host if request.client else "",
        "log_dir": str(LOG_DIR),
        "log_file": str(LOG_FILE),
        "ts": time.time(),
    }
    logger.info(
        "debug whoami probe host=%s pid=%s client=%s revision=%s log_file=%s",
        probe["host"],
        probe["pid"],
        probe["client"],
        probe["revision"],
        probe["log_file"],
    )
    return probe


@app.get("/")
async def web_client_index() -> Any:
    if WEB_CLIENT_INDEX.exists():
        return FileResponse(str(WEB_CLIENT_INDEX))
    return {"ok": False, "message": "web client not found", "hint": "put index.html under ./web_client"}


class _SplitChannelWebSocketAdapter:
    def __init__(
        self,
        *,
        session_id: str,
        audio_format: str,
        control_ws: WebSocket,
        media_ws: WebSocket,
    ) -> None:
        self.query_params = {"session_id": session_id, "format": audio_format}
        self._control_ws = control_ws
        self._media_ws = media_ws
        self._control_send_lock = asyncio.Lock()
        self._media_send_lock = asyncio.Lock()
        self._close_lock = asyncio.Lock()
        self._incoming_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=max(32, DUAL_CHANNEL_INCOMING_QUEUE_SIZE)
        )
        self._pump_tasks: list[asyncio.Task[Any]] = []
        self._pumps_started = False
        self._closed = False

    async def accept(self) -> None:
        if self._pumps_started:
            return
        self._pumps_started = True
        self._pump_tasks = [
            asyncio.create_task(self._pump_control_loop()),
            asyncio.create_task(self._pump_media_loop()),
        ]

    async def send_json(self, payload: dict[str, Any]) -> None:
        await self.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_text(self, text: str) -> None:
        async with self._control_send_lock:
            await self._control_ws.send_text(text)

    async def send_bytes(self, payload: bytes) -> None:
        async with self._media_send_lock:
            await self._media_ws.send_bytes(payload)

    async def receive(self) -> dict[str, Any]:
        return await self._incoming_queue.get()

    def _enqueue_message(self, message: dict[str, Any]) -> None:
        if not message:
            return
        try:
            self._incoming_queue.put_nowait(message)
            return
        except asyncio.QueueFull:
            pass
        try:
            _ = self._incoming_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            self._incoming_queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    async def _pump_control_loop(self) -> None:
        try:
            while not self._closed:
                message = await self._control_ws.receive()
                msg_type = message.get("type")
                if msg_type == "websocket.disconnect":
                    self._enqueue_message({"type": "websocket.disconnect"})
                    break
                text_data = message.get("text")
                if text_data is not None:
                    self._enqueue_message({"type": "websocket.receive", "text": text_data})
        except Exception:
            self._enqueue_message({"type": "websocket.disconnect"})

    async def _pump_media_loop(self) -> None:
        try:
            while not self._closed:
                message = await self._media_ws.receive()
                msg_type = message.get("type")
                if msg_type == "websocket.disconnect":
                    self._enqueue_message({"type": "websocket.disconnect"})
                    break
                audio_bytes = message.get("bytes")
                if audio_bytes is not None:
                    self._enqueue_message({"type": "websocket.receive", "bytes": audio_bytes})
                    continue
                text_data = message.get("text")
                if text_data is not None:
                    self._enqueue_message({"type": "websocket.receive", "text": text_data})
        except Exception:
            self._enqueue_message({"type": "websocket.disconnect"})

    async def close(self, code: int = 1000) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            for task in self._pump_tasks:
                if task.done():
                    continue
                task.cancel()
            for task in self._pump_tasks:
                try:
                    await task
                except Exception:
                    pass
            try:
                await self._control_ws.close(code=code)
            except Exception:
                pass
            try:
                await self._media_ws.close(code=code)
            except Exception:
                pass


async def _attach_dual_ws_channel(
    *,
    safe_session: str,
    raw_session_id: str,
    channel: str,
    websocket: WebSocket,
    audio_format: str,
) -> tuple[dict[str, Any] | None, str | None]:
    ws_key = "control_ws" if channel == "control" else "media_ws"
    async with DUAL_WS_SESSIONS_LOCK:
        state = DUAL_WS_SESSIONS.get(safe_session)
        if state is None:
            state = {
                "safe_session": safe_session,
                "raw_session_id": raw_session_id,
                "audio_format": audio_format,
                "control_ws": None,
                "media_ws": None,
                "ready_event": asyncio.Event(),
                "done_event": asyncio.Event(),
                "runner_task": None,
            }
            DUAL_WS_SESSIONS[safe_session] = state
        elif state.get(ws_key) is not None and state.get(ws_key) is not websocket:
            return None, f"duplicate {channel} channel for session_id={safe_session}"
        else:
            if channel == "media":
                state["audio_format"] = audio_format or state.get("audio_format") or "pcm"
            if raw_session_id:
                state["raw_session_id"] = raw_session_id
        state[ws_key] = websocket
        if state.get("control_ws") is not None and state.get("media_ws") is not None:
            state["ready_event"].set()
        return state, None


async def _detach_dual_ws_channel(*, safe_session: str, channel: str, websocket: WebSocket) -> None:
    ws_key = "control_ws" if channel == "control" else "media_ws"
    async with DUAL_WS_SESSIONS_LOCK:
        state = DUAL_WS_SESSIONS.get(safe_session)
        if state is None:
            return
        if state.get(ws_key) is websocket:
            state[ws_key] = None
        runner_task = state.get("runner_task")
        if (
            state.get("control_ws") is None
            and state.get("media_ws") is None
            and (runner_task is None or runner_task.done())
        ):
            DUAL_WS_SESSIONS.pop(safe_session, None)


async def _run_dual_ws_session(state: dict[str, Any]) -> None:
    safe_session = str(state.get("safe_session") or "")
    raw_session_id = str(state.get("raw_session_id") or safe_session)
    audio_format = str(state.get("audio_format") or "pcm")
    control_ws = state.get("control_ws")
    media_ws = state.get("media_ws")
    adapter: _SplitChannelWebSocketAdapter | None = None
    try:
        if not isinstance(control_ws, WebSocket) or not isinstance(media_ws, WebSocket):
            return
        logger.info("dual ws session start session_id=%s format=%s", safe_session, audio_format)
        adapter = _SplitChannelWebSocketAdapter(
            session_id=raw_session_id,
            audio_format=audio_format,
            control_ws=control_ws,
            media_ws=media_ws,
        )
        await _run_realtime_audio_session(adapter)
    except Exception:
        logger.exception("dual ws session failed session_id=%s", safe_session)
    finally:
        if adapter is not None:
            try:
                await adapter.close()
            except Exception:
                pass
        state["done_event"].set()
        async with DUAL_WS_SESSIONS_LOCK:
            existing = DUAL_WS_SESSIONS.get(safe_session)
            if existing is state:
                DUAL_WS_SESSIONS.pop(safe_session, None)
        logger.info("dual ws session closed session_id=%s", safe_session)


async def _run_realtime_audio_session(websocket: Any) -> None:
    session_id = websocket.query_params.get("session_id", "").strip()
    audio_format = websocket.query_params.get("format", "pcm").lower().strip() or "pcm"
    if not session_id:
        session_id = f"ws_{uuid.uuid4().hex[:12]}"
    safe_session = _safe_segment(session_id)

    await websocket.accept()
    if not safe_session:
        await websocket.send_json({"event": "error", "message": "invalid session_id"})
        await websocket.close(code=1008)
        return

    # Preserve all committed user turns in order for NLP context continuity.
    commit_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=0)
    stop_event = asyncio.Event()
    # In split-channel mode, control(text) and media(bytes) should not share one lock,
    # otherwise control events (like tts_latency) can be delayed behind media sends.
    ws_text_send_lock = asyncio.Lock()
    ws_audio_send_lock = ws_text_send_lock
    if isinstance(websocket, _SplitChannelWebSocketAdapter):
        ws_audio_send_lock = asyncio.Lock()
    state: dict[str, Any] = {
        "last_start_at": 0.0,
        "tts_busy": False,
        "tts_interrupted": False,
        "tts_audio_started": False,
        "turn_task": None,
        "turn_cancel_event": None,
        "recent_ai_text": "",
        "recent_ai_ts": 0.0,
        "tts_live_text": "",
        "tts_live_ts": 0.0,
        "last_commit_ts": 0.0,
        "last_commit_compact": "",
        "stream_interrupt_suppress_until": 0.0,
        "interrupt_cooldown_until": 0.0,
        "last_stream_interrupt_ts": 0.0,
        "last_stream_interrupt_compact": "",
        "last_nlp_commit_ts": 0.0,
        "last_nlp_commit_compact": "",
        "pending_merge_user_text": "",
        "billing_active": False,
        "billing_started_at": 0.0,
        "billing_ended_at": 0.0,
        "billing_start_source": "",
        "billing_start_text": "",
        "billing_summary_emitted": False,
        "billing_totals": {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "llm_cost": 0.0,
            "tts_characters": 0,
            "tts_cost": 0.0,
            "asr_audio_bytes": 0,
            "asr_audio_seconds": 0.0,
            "asr_cost": 0.0,
            "total_cost": 0.0,
        },
        "billing_models": {},
    }
    asr_session = ASRStreamingSession(
        session_id=safe_session,
        audio_format=audio_format,
        on_audio_sent=lambda size: _accumulate_asr_audio_bytes(int(size)),
    )

    def _reset_billing_accumulator() -> None:
        state["billing_totals"] = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "llm_cost": 0.0,
            "tts_characters": 0,
            "tts_cost": 0.0,
            "asr_audio_bytes": 0,
            "asr_audio_seconds": 0.0,
            "asr_cost": 0.0,
            "total_cost": 0.0,
        }
        state["billing_models"] = {}

    def _start_billing(*, source: str, trigger_text: str = "") -> bool:
        if bool(state.get("billing_active")):
            return False
        _reset_billing_accumulator()
        state["billing_active"] = True
        state["billing_summary_emitted"] = False
        state["billing_started_at"] = time.time()
        state["billing_ended_at"] = 0.0
        state["billing_start_source"] = source
        state["billing_start_text"] = trigger_text
        return True

    def _accumulate_model_usage(model_name: str, usage: dict[str, int]) -> None:
        if not bool(state.get("billing_active")):
            return
        usage_metrics = _extract_usage_metrics(usage)
        if usage_metrics["total_tokens"] <= 0:
            return
        cost_detail = _calculate_request_cost(model_name, usage_metrics)
        model_key = str(cost_detail.get("model_key") or _normalize_model_for_pricing(model_name))
        model_buckets = state.get("billing_models")
        if not isinstance(model_buckets, dict):
            model_buckets = {}
            state["billing_models"] = model_buckets
        bucket = model_buckets.get(model_key)
        if not isinstance(bucket, dict):
            bucket = {
                "model": model_name,
                "model_key": model_key,
                "pricing_rule": cost_detail.get("pricing_rule", ""),
                "pricing_condition": cost_detail.get("pricing_condition", ""),
                "pricing_warning": cost_detail.get("pricing_warning", ""),
                "calls": 0,
                "usage": {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                },
                "cost": {
                    "input": 0.0,
                    "output": 0.0,
                    "cache_input": 0.0,
                    "cache_storage": 0.0,
                    "total": 0.0,
                },
                "price": cost_detail.get("price", {}),
            }
            model_buckets[model_key] = bucket
        if (not str(bucket.get("pricing_condition", "")).strip()) and str(cost_detail.get("pricing_condition", "")).strip():
            bucket["pricing_condition"] = str(cost_detail.get("pricing_condition", "")).strip()
        if str(cost_detail.get("pricing_warning", "")).strip():
            bucket["pricing_warning"] = str(cost_detail.get("pricing_warning", "")).strip()
        bucket["calls"] = int(bucket.get("calls", 0)) + 1
        bucket_usage = bucket.get("usage", {})
        bucket_cost = bucket.get("cost", {})
        for token_key in ("total_tokens", "prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens"):
            bucket_usage[token_key] = int(bucket_usage.get(token_key, 0)) + int(usage_metrics.get(token_key, 0))
        for cost_key in ("input", "output", "cache_input", "cache_storage", "total"):
            bucket_cost[cost_key] = round(
                float(bucket_cost.get(cost_key, 0.0)) + float(cost_detail.get("cost", {}).get(cost_key, 0.0)),
                8,
            )
        totals = state.get("billing_totals", {})
        for token_key in ("total_tokens", "prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens"):
            totals[token_key] = int(totals.get(token_key, 0)) + int(usage_metrics.get(token_key, 0))
        totals["llm_cost"] = round(float(totals.get("llm_cost", 0.0)) + float(cost_detail.get("cost", {}).get("total", 0.0)), 8)
        totals["total_cost"] = round(
            float(totals.get("llm_cost", 0.0))
            + float(totals.get("tts_cost", 0.0))
            + float(totals.get("asr_cost", 0.0)),
            8,
        )
        state["billing_totals"] = totals

    def _accumulate_asr_audio_bytes(audio_bytes: int) -> None:
        if (not bool(state.get("billing_active"))) or audio_bytes <= 0:
            return
        totals = state.get("billing_totals", {})
        prev_bytes = int(totals.get("asr_audio_bytes", 0))
        merged_bytes = max(0, prev_bytes + int(audio_bytes))
        bytes_per_second = max(1.0, float(ASR_SAMPLE_RATE * 2))
        asr_audio_seconds = merged_bytes / bytes_per_second
        asr_cost = (asr_audio_seconds / 3600.0) * ASR_PRICE_PER_HOUR_CNY
        totals["asr_audio_bytes"] = merged_bytes
        totals["asr_audio_seconds"] = round(asr_audio_seconds, 6)
        totals["asr_cost"] = round(asr_cost, 8)
        llm_cost = float(totals.get("llm_cost", 0.0))
        tts_cost = float(totals.get("tts_cost", 0.0))
        totals["total_cost"] = round(llm_cost + tts_cost + float(totals["asr_cost"]), 8)
        state["billing_totals"] = totals

    def _accumulate_tts_usage_characters(characters: int) -> None:
        if (not bool(state.get("billing_active"))) or characters <= 0:
            return
        totals = state.get("billing_totals", {})
        merged_chars = int(totals.get("tts_characters", 0)) + int(characters)
        tts_cost = (merged_chars / 10000.0) * TTS_PRICE_PER_10K_CHARS_CNY
        totals["tts_characters"] = merged_chars
        totals["tts_cost"] = round(tts_cost, 8)
        llm_cost = float(totals.get("llm_cost", 0.0))
        asr_cost = float(totals.get("asr_cost", 0.0))
        totals["total_cost"] = round(llm_cost + float(totals["tts_cost"]) + asr_cost, 8)
        state["billing_totals"] = totals

    def _build_billing_result_payload(*, source: str, reason: str, trigger_text: str = "") -> dict[str, Any]:
        started_at = float(state.get("billing_started_at") or 0.0)
        ended_at = time.time()
        if started_at <= 0:
            started_at = ended_at
        duration_seconds = max(0.0, ended_at - started_at)
        totals = state.get("billing_totals", {})
        models_raw = state.get("billing_models", {})
        model_items: list[dict[str, Any]] = []
        if isinstance(models_raw, dict):
            for _, item in models_raw.items():
                if isinstance(item, dict):
                    model_items.append(item)
        model_items.sort(key=lambda x: str(x.get("model_key", "")))

        def _make_empty_model_item(model_key: str, model_name: str) -> dict[str, Any]:
            cache_input_price = 0.16 if model_key == "doubao-seed-1.8" else 0.03
            return {
                "model": model_name,
                "model_key": model_key,
                "pricing_rule": model_key,
                "calls": 0,
                "usage": {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                },
                "cost": {
                    "input": 0.0,
                    "output": 0.0,
                    "cache_input": 0.0,
                    "cache_storage": 0.0,
                    "total": 0.0,
                },
                "price": {
                    "input_per_million": 0.0,
                    "output_per_million": 0.0,
                    "cache_input_per_million": cache_input_price,
                    "cache_storage_per_million_token_hour": 0.017,
                },
            }

        model_by_key: dict[str, dict[str, Any]] = {
            str(item.get("model_key", "") or ""): item for item in model_items if isinstance(item, dict)
        }
        if "doubao-seed-1.6-flash" not in model_by_key:
            model_by_key["doubao-seed-1.6-flash"] = _make_empty_model_item(
                "doubao-seed-1.6-flash",
                "doubao-seed-1.6-flash",
            )
        if "doubao-seed-1.8" not in model_by_key:
            model_by_key["doubao-seed-1.8"] = _make_empty_model_item(
                "doubao-seed-1.8",
                "doubao-seed-1.8",
            )
        model_items = [
            model_by_key["doubao-seed-1.6-flash"],
            model_by_key["doubao-seed-1.8"],
        ] + [
            item
            for key, item in model_by_key.items()
            if key not in {"doubao-seed-1.6-flash", "doubao-seed-1.8"}
        ]
        return {
            "event": "billing_result",
            "session_id": safe_session,
            "currency": "CNY",
            "started": bool(state.get("billing_active", False)),
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": round(duration_seconds, 3),
            "start_source": str(state.get("billing_start_source") or ""),
            "start_text": str(state.get("billing_start_text") or ""),
            "end_source": source,
            "end_reason": reason,
            "trigger_text": trigger_text,
            "usage": {
                "total_tokens": int(totals.get("total_tokens", 0)),
                "prompt_tokens": int(totals.get("prompt_tokens", 0)),
                "completion_tokens": int(totals.get("completion_tokens", 0)),
                "cached_tokens": int(totals.get("cached_tokens", 0)),
                "reasoning_tokens": int(totals.get("reasoning_tokens", 0)),
            },
            "cost": {
                "llm_total": round(float(totals.get("llm_cost", 0.0)), 8),
                "tts_total": round(float(totals.get("tts_cost", 0.0)), 8),
                "asr_total": round(float(totals.get("asr_cost", 0.0)), 8),
                "total": round(float(totals.get("total_cost", 0.0)), 8),
            },
            "tts": {
                "usage": {
                    "characters": int(totals.get("tts_characters", 0)),
                },
                "price": {
                    "per_10k_characters": TTS_PRICE_PER_10K_CHARS_CNY,
                },
                "cost": {
                    "total": round(float(totals.get("tts_cost", 0.0)), 8),
                },
            },
            "asr": {
                "usage": {
                    "audio_bytes": int(totals.get("asr_audio_bytes", 0)),
                    "audio_seconds": round(float(totals.get("asr_audio_seconds", 0.0)), 6),
                    "audio_hours": round(float(totals.get("asr_audio_seconds", 0.0)) / 3600.0, 8),
                },
                "price": {
                    "per_hour": ASR_PRICE_PER_HOUR_CNY,
                },
                "cost": {
                    "total": round(float(totals.get("asr_cost", 0.0)), 8),
                },
            },
            "models": model_items,
            "model_costs": {
                "doubao-seed-1.6-flash": {
                    "cost_total": round(float(model_by_key["doubao-seed-1.6-flash"].get("cost", {}).get("total", 0.0)), 8),
                    "total_tokens": int(model_by_key["doubao-seed-1.6-flash"].get("usage", {}).get("total_tokens", 0)),
                    "prompt_tokens": int(model_by_key["doubao-seed-1.6-flash"].get("usage", {}).get("prompt_tokens", 0)),
                    "completion_tokens": int(model_by_key["doubao-seed-1.6-flash"].get("usage", {}).get("completion_tokens", 0)),
                },
                "doubao-seed-1.8": {
                    "cost_total": round(float(model_by_key["doubao-seed-1.8"].get("cost", {}).get("total", 0.0)), 8),
                    "total_tokens": int(model_by_key["doubao-seed-1.8"].get("usage", {}).get("total_tokens", 0)),
                    "prompt_tokens": int(model_by_key["doubao-seed-1.8"].get("usage", {}).get("prompt_tokens", 0)),
                    "completion_tokens": int(model_by_key["doubao-seed-1.8"].get("usage", {}).get("completion_tokens", 0)),
                },
            },
            "pricing": {
                "note": "LLM 按 doubao-seed-1.8 与 doubao-seed-1.6-flash 文档估算；TTS 按 3元/万字符（按提交到TTS的文本字符数估算）；ASR按实际传输PCM时长折算4.5元/小时。",
            },
        }

    async def _emit_billing_result(*, source: str, reason: str, trigger_text: str = "") -> None:
        if bool(state.get("billing_summary_emitted")):
            return
        payload = _build_billing_result_payload(source=source, reason=reason, trigger_text=trigger_text)
        await send_json_event(payload)
        state["billing_summary_emitted"] = True
        state["billing_active"] = False
        state["billing_ended_at"] = float(payload.get("ended_at", time.time()))

    async def send_json_event(payload: dict[str, Any]) -> None:
        async with ws_text_send_lock:
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_audio_frame(audio: bytes) -> None:
        if not audio:
            return
        async with ws_audio_send_lock:
            await websocket.send_bytes(audio)

    async def emit_workflow_progress(
        *,
        trigger: str,
        intents: list[str] | None = None,
        matched_label: str = "",
        jump_node_id: str = "",
        from_node_id: str = "",
        advanced: bool | None = None,
        reason: str = "",
    ) -> None:
        snapshot = _get_session_workflow_runtime_snapshot(safe_session)
        if not isinstance(snapshot, dict):
            return
        payload: dict[str, Any] = {
            "event": "workflow_progress",
            "session_id": safe_session,
            "trigger": trigger,
            **snapshot,
        }
        if intents is not None:
            payload["intents"] = [str(item).strip() for item in intents if str(item).strip()]
        if matched_label:
            payload["matched_label"] = matched_label
        if jump_node_id:
            payload["jump_node_id"] = jump_node_id
        if from_node_id:
            payload["from_node_id"] = from_node_id
        if advanced is not None:
            payload["advanced"] = bool(advanced)
        if reason:
            payload["reason"] = reason
        await send_json_event(payload)

    async def interrupt_current_tts(trigger: str, text: str, *, bypass_cooldown: bool = False, bypass_reason: str = "") -> bool:
        if not bool(state.get("tts_busy")):
            return False
        if bool(state.get("tts_interrupted")):
            return False
        now = time.monotonic()
        cooldown_until = float(state.get("interrupt_cooldown_until") or 0.0)
        if now < cooldown_until and (not bypass_cooldown):
            logger.info(
                "tts interrupt ignored by cooldown session_id=%s trigger=%s remain_ms=%.1f",
                safe_session,
                trigger,
                (cooldown_until - now) * 1000.0,
            )
            return False
        if now < cooldown_until and bypass_cooldown:
            logger.info(
                "tts interrupt bypass cooldown session_id=%s trigger=%s remain_ms=%.1f reason=%s",
                safe_session,
                trigger,
                (cooldown_until - now) * 1000.0,
                bypass_reason or "prefix_extend",
            )
        state["interrupt_cooldown_until"] = now + BARGE_IN_INTERRUPT_COOLDOWN_SECONDS
        state["tts_interrupted"] = True
        logger.info("tts interrupt triggered session_id=%s trigger=%s text=%s", safe_session, trigger, text)
        turn_cancel_event = state.get("turn_cancel_event")
        if isinstance(turn_cancel_event, asyncio.Event):
            turn_cancel_event.set()
        # Hard-cancel the active turn task to minimize barge-in interruption latency.
        # Keep cancel_event as well so stream-level cleanup paths can observe the stop intent.
        turn_task = state.get("turn_task")
        if isinstance(turn_task, asyncio.Task) and (not turn_task.done()):
            turn_task.cancel()
            logger.info(
                "tts turn task cancel requested session_id=%s trigger=%s",
                safe_session,
                trigger,
            )
        await send_json_event(
            {
                "event": "tts_interrupted",
                "session_id": safe_session,
                "trigger": trigger,
                "text": text,
                "action": "stop_and_clear_playback",
            }
        )
        return True

    def drop_pending_user_text_items() -> int:
        dropped = 0
        reserved: list[dict[str, Any]] = []
        while True:
            try:
                candidate = commit_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            kind = str(candidate.get("kind") or "user_text")
            if kind == "user_text":
                dropped += 1
                continue
            reserved.append(candidate)
        for candidate in reserved:
            try:
                commit_queue.put_nowait(candidate)
            except asyncio.QueueFull:
                break
        return dropped

    async def recv_audio_loop() -> None:
        while not stop_event.is_set():
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            audio_bytes = message.get("bytes")
            if audio_bytes is not None:
                if len(audio_bytes) > AUDIO_CHUNK_MAX_BYTES:
                    await send_json_event(
                        {
                            "event": "error",
                            "message": f"chunk too large, max={AUDIO_CHUNK_MAX_BYTES} bytes",
                        }
                    )
                    continue
                await asr_session.send_chunk(audio_bytes=audio_bytes, audio_format=audio_format)
                continue

            text_data = message.get("text")
            if not text_data:
                continue
            try:
                payload = json.loads(text_data)
            except Exception:
                payload = {"event": str(text_data).strip().lower()}
            event = str(payload.get("event", "")).strip().lower() if isinstance(payload, dict) else ""
            if event == "client_event" and isinstance(payload, dict):
                # Backward/forward compatibility:
                # some clients send {"event":"client_event","command":"start_dialog|end_dialog"}.
                mapped = str(payload.get("command", "")).strip().lower()
                if mapped:
                    event = mapped
            if event in ("stop", "close", "disconnect"):
                break
            if event in ("ping", "heartbeat"):
                await send_json_event({"event": "pong", "session_id": safe_session})
                continue
            if event in ("set_system_prompt", "update_system_prompt", "set_prompt_context"):
                prompt_text = ""
                effective_prompt_template = ""
                structured_prompt_template = ""
                has_prompt_context = False
                prompt_context_payload: dict[str, Any] | None = None
                has_intent_field = False
                intent_payload: Any = None
                has_fallback_field = False
                fallback_payload: Any = None
                has_workflow_field = False
                workflow_payload: Any = None
                if isinstance(payload, dict):
                    prompt_text = str(
                        payload.get("prompt_template")
                        or payload.get("promptTemplate")
                        or payload.get("system_prompt")
                        or payload.get("prompt")
                        or payload.get("text")
                        or ""
                    ).strip()
                    if prompt_text:
                        logger.info(
                            "client prompt_template received session_id=%s chars=%s content=%s",
                            safe_session,
                            len(prompt_text),
                            prompt_text,
                        )
                    for key in ("intent_labels", "intent_label_library", "labels"):
                        if key in payload:
                            has_intent_field = True
                            intent_payload = payload.get(key)
                            break
                    for key in ("fallback_label", "intent_fallback_label"):
                        if key in payload:
                            has_fallback_field = True
                            fallback_payload = payload.get(key)
                            break
                    if "workflow_json" in payload:
                        has_workflow_field = True
                        workflow_payload = payload.get("workflow_json")
                    maybe_prompt_context = payload.get("prompt_context")
                    if isinstance(maybe_prompt_context, dict):
                        has_prompt_context = True
                        prompt_context_payload = maybe_prompt_context
                        context_system_instruction = str(
                            maybe_prompt_context.get("system_instruction")
                            or maybe_prompt_context.get("system_instruction_text")
                            or maybe_prompt_context.get("instruction")
                            or ""
                        ).strip()
                        context_customer_profile = _render_customer_profile_text(
                            maybe_prompt_context.get("customer_profile")
                            if ("customer_profile" in maybe_prompt_context)
                            else maybe_prompt_context.get("customer_profile_text")
                        )
                        context_workflow_text = str(maybe_prompt_context.get("workflow_text") or "").strip()
                        context_prompt_template = str(
                            maybe_prompt_context.get("prompt_template")
                            or maybe_prompt_context.get("promptTemplate")
                            or maybe_prompt_context.get("system_prompt")
                            or maybe_prompt_context.get("prompt")
                            or ""
                        ).strip()
                        if context_prompt_template:
                            prompt_text = context_prompt_template
                        if (not has_intent_field):
                            for key in ("intent_labels", "intent_label_library", "labels"):
                                if key in maybe_prompt_context:
                                    has_intent_field = True
                                    intent_payload = maybe_prompt_context.get(key)
                                    break
                        if (not has_fallback_field):
                            for key in ("fallback_label", "intent_fallback_label"):
                                if key in maybe_prompt_context:
                                    has_fallback_field = True
                                    fallback_payload = maybe_prompt_context.get(key)
                                    break
                        if "workflow_json" in maybe_prompt_context:
                            has_workflow_field = True
                            workflow_payload = maybe_prompt_context.get("workflow_json")
                        structured_prompt_template = _build_structured_prompt_template(
                            system_instruction_text=context_system_instruction,
                            customer_profile_text=context_customer_profile,
                            workflow_text=context_workflow_text,
                            use_workflow_placeholder=has_workflow_field,
                        )
                        logger.info(
                            "client prompt_context received session_id=%s keys=%s workflow_json=%s",
                            safe_session,
                            ",".join(sorted(maybe_prompt_context.keys())),
                            has_workflow_field,
                        )
                        if structured_prompt_template:
                            logger.info(
                                "client prompt_context template session_id=%s chars=%s content=%s",
                                safe_session,
                                len(structured_prompt_template),
                                structured_prompt_template,
                            )
                effective_prompt_template = (
                    structured_prompt_template if has_prompt_context else prompt_text
                ) or prompt_text
                if (not effective_prompt_template) and (not has_intent_field) and (not has_fallback_field) and (not has_workflow_field):
                    await send_json_event(
                        {
                            "event": "command",
                            "session_id": safe_session,
                            "command": "set_system_prompt",
                            "action": "ignored_empty",
                        }
                    )
                    continue
                if effective_prompt_template and (not has_workflow_field):
                    _set_session_system_prompt(safe_session, effective_prompt_template)
                labels_count = 0
                if has_intent_field:
                    labels_count = len(_set_session_intent_labels(safe_session, intent_payload))
                else:
                    labels_count = len(_get_session_intent_labels(safe_session))
                if has_fallback_field:
                    fallback_value = _set_session_intent_fallback_label(safe_session, fallback_payload)
                else:
                    fallback_value = _get_session_intent_fallback_label(safe_session)
                workflow_applied = False
                workflow_error = ""
                workflow_nodes = 0
                workflow_edges = 0
                workflow_chars = 0
                if has_workflow_field:
                    workflow_chars = len(str(workflow_payload or ""))
                    workflow_obj = _extract_workflow_object(workflow_payload)
                    if isinstance(workflow_obj, dict):
                        raw_nodes = workflow_obj.get("nodes")
                        raw_edges = workflow_obj.get("edges")
                        if isinstance(raw_nodes, list):
                            workflow_nodes = len(raw_nodes)
                        if isinstance(raw_edges, list):
                            workflow_edges = len(raw_edges)
                    logger.info(
                        "workflow_json received session_id=%s chars=%s nodes=%s edges=%s",
                        safe_session,
                        workflow_chars,
                        workflow_nodes,
                        workflow_edges,
                    )
                    prompt_template = effective_prompt_template or _get_session_system_prompt(safe_session)
                    workflow_applied, workflow_error = _set_session_workflow_state(
                        session_id=safe_session,
                        workflow_payload=workflow_payload,
                        prompt_template=prompt_template,
                    )
                    if workflow_applied:
                        labels_count = len(_get_session_intent_labels(safe_session))
                    elif prompt_template:
                        _set_session_system_prompt(safe_session, prompt_template)
                logger.info(
                    "session prompt context updated session_id=%s system_chars=%s intent_labels=%s fallback_label=%s workflow_applied=%s workflow_error=%s workflow_nodes=%s workflow_edges=%s",
                    safe_session,
                    len(effective_prompt_template),
                    labels_count,
                    fallback_value,
                    workflow_applied,
                    workflow_error,
                    workflow_nodes,
                    workflow_edges,
                )
                command_payload = {
                    "event": "command",
                    "session_id": safe_session,
                    "command": "set_system_prompt",
                    "action": "updated",
                    "system_chars": len(effective_prompt_template),
                    "intent_labels": labels_count,
                    "fallback_label": fallback_value,
                }
                if has_workflow_field:
                    command_payload["workflow_applied"] = workflow_applied
                    command_payload["workflow_error"] = workflow_error
                    command_payload["workflow_nodes"] = workflow_nodes
                    command_payload["workflow_edges"] = workflow_edges
                await send_json_event(command_payload)
                if has_workflow_field and workflow_applied:
                    await emit_workflow_progress(
                        trigger="workflow_loaded",
                        advanced=False,
                        reason="workflow_applied",
                    )
                continue
            if event == "clear_system_prompt":
                _clear_session_system_prompt(safe_session)
                _clear_session_intent_labels(safe_session)
                _clear_session_intent_fallback_label(safe_session)
                _clear_session_workflow_state(safe_session)
                await send_json_event(
                    {
                        "event": "command",
                        "session_id": safe_session,
                        "command": "clear_system_prompt",
                        "action": "cleared",
                    }
                )
                continue
            if event == VOICE_COMMAND_START:
                billing_started = _start_billing(source="client_event", trigger_text=VOICE_COMMAND_START_KEYWORDS[0])
                if billing_started:
                    await send_json_event(
                        {
                            "event": "billing_started",
                            "session_id": safe_session,
                            "source": "client_event",
                            "trigger_text": VOICE_COMMAND_START_KEYWORDS[0],
                            "started_at": float(state.get("billing_started_at") or time.time()),
                        }
                    )
                if bool(state.get("tts_busy")):
                    await send_json_event(
                        {
                            "event": "command",
                            "session_id": safe_session,
                            "command": VOICE_COMMAND_START,
                            "action": "ignored_busy",
                        }
                    )
                    continue
                now = time.monotonic()
                if (now - float(state["last_start_at"])) < START_COMMAND_COOLDOWN_SECONDS:
                    await send_json_event(
                        {
                            "event": "command",
                            "session_id": safe_session,
                            "command": VOICE_COMMAND_START,
                            "action": "ignored_cooldown",
                        }
                    )
                    continue
                state["last_start_at"] = now
                _put_latest_queue_item(
                    commit_queue,
                    {
                        "kind": VOICE_COMMAND_START,
                        "text": VOICE_COMMAND_START_KEYWORDS[0],
                    },
                )
                continue
            if event == VOICE_COMMAND_END:
                await _emit_billing_result(
                    source="client_event",
                    reason="voice_command_end_dialog",
                    trigger_text=VOICE_COMMAND_END_KEYWORDS[0],
                )
                terminate_trace_id = uuid.uuid4().hex[:12]
                await send_json_event(
                    {
                        "event": "command",
                        "session_id": safe_session,
                        "command": VOICE_COMMAND_END,
                        "action": "terminate_session",
                        "terminate_source": "client_event",
                        "terminate_by": "client",
                        "terminate_reason": "voice_command_end_dialog",
                        "terminate_trace_id": terminate_trace_id,
                        "server_ts": time.time(),
                    }
                )
                stop_event.set()
                break

    async def asr_commit_loop() -> None:
        while not stop_event.is_set():
            committed = await asr_session.claim_definite_text(timeout_seconds=ASR_RESULT_TIMEOUT_SECONDS)
            if not committed:
                continue
            structured_value = _is_structured_user_value(committed)
            recent_ai_text = str(state.get("tts_live_text") or state.get("recent_ai_text") or "")
            recent_ai_ts = float(state.get("tts_live_ts") or state.get("recent_ai_ts") or 0.0)
            busy = bool(state.get("tts_busy"))
            if busy:
                stripped = _strip_ai_echo_prefix(committed, recent_ai_text)
                if stripped != committed:
                    logger.info(
                        "strip ai echo prefix session_id=%s before=%s after=%s",
                        safe_session,
                        committed,
                        stripped,
                    )
                    committed = stripped
                if not committed:
                    logger.info("drop empty committed after strip session_id=%s", safe_session)
                    continue
                structured_value = _is_structured_user_value(committed)
            command = _match_voice_command(committed)

            if _is_interrupt_command_text(committed):
                # Interrupt commands ("暂停播报/停止播报") are shown to client but not submitted to NLP.
                if not command:
                    await send_json_event({"event": "asr_commit", "text": committed, "session_id": safe_session, "nlp_submitted": False})
                await interrupt_current_tts(trigger="interrupt_command", text=committed)
                continue

            # "开始对话/结束对话" are control commands and should not be shown
            # as normal dialogue records on the client.

            if command == VOICE_COMMAND_END:
                await _emit_billing_result(
                    source="asr_commit",
                    reason="voice_command_end_dialog",
                    trigger_text=committed,
                )
                terminate_trace_id = uuid.uuid4().hex[:12]
                await send_json_event(
                    {
                        "event": "command",
                        "session_id": safe_session,
                        "command": VOICE_COMMAND_END,
                        "action": "terminate_session",
                        "terminate_source": "asr_commit",
                        "terminate_by": "asr",
                        "terminate_reason": "voice_command_end_dialog",
                        "trigger_text": committed,
                        "terminate_trace_id": terminate_trace_id,
                        "server_ts": time.time(),
                    }
                )
                stop_event.set()
                break

            if command == VOICE_COMMAND_START:
                billing_started = _start_billing(source="asr_commit", trigger_text=committed)
                if billing_started:
                    await send_json_event(
                        {
                            "event": "billing_started",
                            "session_id": safe_session,
                            "source": "asr_commit",
                            "trigger_text": committed,
                            "started_at": float(state.get("billing_started_at") or time.time()),
                        }
                    )
                if bool(state.get("tts_busy")):
                    await send_json_event(
                        {
                            "event": "command",
                            "session_id": safe_session,
                            "command": VOICE_COMMAND_START,
                            "action": "ignored_busy",
                        }
                    )
                    continue
                now = time.monotonic()
                if (now - float(state["last_start_at"])) < START_COMMAND_COOLDOWN_SECONDS:
                    await send_json_event(
                        {
                            "event": "command",
                            "session_id": safe_session,
                            "command": VOICE_COMMAND_START,
                            "action": "ignored_cooldown",
                        }
                    )
                    continue
                state["last_start_at"] = now
                _put_latest_queue_item(
                    commit_queue,
                    {
                        "kind": VOICE_COMMAND_START,
                        "text": committed,
                        "enqueue_ts": time.monotonic(),
                        "asr_last_update_at": asr_session.last_commit_update_at,
                    },
                )
                continue

            committed_compact = _normalize_compact_text(committed)
            now_ts = time.monotonic()
            nlp_stale_window = _get_nlp_stale_window_seconds(committed_compact)
            if committed_compact and nlp_stale_window > 0:
                last_nlp_compact = str(state.get("last_nlp_commit_compact") or "")
                last_nlp_ts = float(state.get("last_nlp_commit_ts") or 0.0)
                delta_nlp_seconds = now_ts - last_nlp_ts
                stale_reason = _get_nlp_stale_drop_reason(
                    committed_compact,
                    last_nlp_compact,
                    delta_seconds=delta_nlp_seconds,
                    stale_window_seconds=nlp_stale_window,
                )
                if stale_reason:
                    logger.info(
                        "drop stale nlp commit session_id=%s text=%s reason=%s compact=%s last_compact=%s delta_ms=%.1f window_ms=%.1f short_confirm=%s",
                        safe_session,
                        committed,
                        stale_reason,
                        committed_compact,
                        last_nlp_compact,
                        delta_nlp_seconds * 1000.0,
                        nlp_stale_window * 1000.0,
                        _is_short_confirmation_compact(committed_compact),
                    )
                    await send_json_event({"event": "asr_commit", "text": committed, "session_id": safe_session, "nlp_submitted": False})
                    continue

            if bool(state.get("tts_busy")) and _is_normal_user_text(committed):
                audio_started = bool(state.get("tts_audio_started"))
                bypass_cooldown = (not audio_started)
                last_commit_compact = str(state.get("last_commit_compact") or "")
                last_commit_ts = float(state.get("last_commit_ts") or 0.0)
                now_for_interrupt = time.monotonic()
                if (
                    committed_compact
                    and last_commit_compact
                    and _is_compact_prefix_extension(last_commit_compact, committed_compact)
                    and (now_for_interrupt - last_commit_ts) <= BARGE_IN_COMMIT_PREFIX_BYPASS_WINDOW_SECONDS
                ):
                    bypass_cooldown = True
                    logger.info(
                        "barge_in_commit prefix-extend bypass armed session_id=%s prev=%s new=%s delta_ms=%.1f",
                        safe_session,
                        last_commit_compact,
                        committed_compact,
                        (now_for_interrupt - last_commit_ts) * 1000.0,
                    )
                await interrupt_current_tts(
                    trigger="barge_in_commit",
                    text=committed,
                    bypass_cooldown=bypass_cooldown,
                    bypass_reason="pre_audio" if (not audio_started) else ("same_prefix_extension" if bypass_cooldown else ""),
                )

            if bool(state.get("tts_busy")) and _is_normal_user_text(committed):
                dropped = drop_pending_user_text_items()
                if dropped > 0:
                    logger.info(
                        "drop stale pending user_text while busy session_id=%s dropped=%s keep_latest=%s",
                        safe_session,
                        dropped,
                        committed,
                    )

            _asr_started = asr_session.last_commit_started_at
            _asr_last_update = asr_session.last_commit_update_at
            _asr_recognition_ms = round((_asr_last_update - _asr_started) * 1000.0, 1) if _asr_started > 0 and _asr_last_update > _asr_started else None
            _asr_silence_ms = round((now_ts - _asr_last_update) * 1000.0, 1) if _asr_last_update > 0 else None
            logger.info(
                "asr_commit latency session_id=%s asr_recognition_ms=%s asr_silence_wait_ms=%s text=%s",
                safe_session, _asr_recognition_ms, _asr_silence_ms, committed,
            )
            await send_json_event({
                "event": "asr_commit",
                "text": committed,
                "session_id": safe_session,
                "nlp_submitted": True,
                "asr_silence_wait_ms": _asr_silence_ms,
            })
            _put_latest_queue_item(
                commit_queue,
                {
                    "kind": "user_text",
                    "text": committed,
                    "enqueue_ts": now_ts,
                    "asr_last_update_at": _asr_last_update,
                    "asr_started_at": _asr_started,
                },
            )
            if committed_compact:
                state["last_nlp_commit_compact"] = committed_compact
                state["last_nlp_commit_ts"] = now_ts
            # Avoid stale stream ASR events from the same utterance instantly interrupting
            # the next turn before it can start.
            state["last_commit_ts"] = now_ts
            state["last_commit_compact"] = committed_compact
            state["stream_interrupt_suppress_until"] = (
                float(state["last_commit_ts"]) + BARGE_IN_POST_COMMIT_SUPPRESS_SECONDS
            )

    async def asr_stream_interrupt_loop() -> None:
        while not stop_event.is_set():
            event = await asr_session.pop_latest_stream_event(timeout_seconds=ASR_RESULT_TIMEOUT_SECONDS)
            if event is None:
                continue
            text = str(event.get("text") or "").strip()
            is_definite = bool(event.get("is_definite"))
            event_ts = float(event.get("ts") or time.monotonic())
            if not text:
                continue
            current_compact = _normalize_compact_text(text)
            if not bool(state.get("tts_busy")):
                continue
            if bool(state.get("tts_interrupted")):
                continue
            suppress_until = float(state.get("stream_interrupt_suppress_until") or 0.0)
            if event_ts <= suppress_until:
                committed_compact = str(state.get("last_commit_compact") or "")
                if (
                    committed_compact
                    and current_compact
                    and (
                        current_compact in committed_compact
                        or committed_compact in current_compact
                    )
                ):
                    logger.info(
                        "skip stale stream barge-in session_id=%s text=%s event_ts=%.3f suppress_until=%.3f",
                        safe_session,
                        text,
                        event_ts,
                        suppress_until,
                    )
                    continue
            last_commit_compact = str(state.get("last_commit_compact") or "")
            last_commit_ts = float(state.get("last_commit_ts") or 0.0)
            allow_extension_barge_in = False
            if last_commit_compact and current_compact:
                if current_compact == last_commit_compact:
                    logger.info(
                        "skip exact same-text stream barge-in session_id=%s text=%s compact=%s",
                        safe_session,
                        text,
                        current_compact,
                    )
                    continue
                if current_compact.startswith(last_commit_compact):
                    extension_len = len(current_compact) - len(last_commit_compact)
                    if extension_len < max(1, BARGE_IN_EXTENSION_MIN_NEW_CHARS):
                        logger.info(
                            "skip short extension stream barge-in session_id=%s text=%s commit_compact=%s extension_len=%s min_new_chars=%s",
                            safe_session,
                            text,
                            last_commit_compact,
                            extension_len,
                            BARGE_IN_EXTENSION_MIN_NEW_CHARS,
                        )
                        continue
                    allow_extension_barge_in = True
                    logger.info(
                        "allow extension stream barge-in session_id=%s text=%s commit_compact=%s extension_len=%s min_new_chars=%s",
                        safe_session,
                        text,
                        last_commit_compact,
                        extension_len,
                        BARGE_IN_EXTENSION_MIN_NEW_CHARS,
                    )
            if (
                last_commit_compact
                and current_compact
                and (
                    current_compact in last_commit_compact
                    or last_commit_compact in current_compact
                )
            ):
                if not allow_extension_barge_in:
                    delta_from_commit = event_ts - last_commit_ts
                    if 0.0 <= delta_from_commit <= BARGE_IN_COMMIT_SAME_TEXT_SUPPRESS_SECONDS:
                        logger.info(
                            "skip same-text stream barge-in session_id=%s text=%s compact=%s commit_compact=%s delta_ms=%.1f window_ms=%.1f",
                            safe_session,
                            text,
                            current_compact,
                            last_commit_compact,
                            delta_from_commit * 1000.0,
                            BARGE_IN_COMMIT_SAME_TEXT_SUPPRESS_SECONDS * 1000.0,
                        )
                        continue
            if _is_likely_tts_echo(
                asr_text=text,
                recent_ai_text=str(state.get("tts_live_text") or ""),
                recent_ai_ts=float(state.get("tts_live_ts") or 0.0),
                is_definite=is_definite,
                allow_stale_recent=True,
            ):
                continue
            if current_compact and BARGE_IN_STREAM_DEDUP_SECONDS > 0:
                last_interrupt_compact = str(state.get("last_stream_interrupt_compact") or "")
                last_interrupt_ts = float(state.get("last_stream_interrupt_ts") or 0.0)
                if (
                    last_interrupt_compact == current_compact
                    and (event_ts - last_interrupt_ts) <= BARGE_IN_STREAM_DEDUP_SECONDS
                ):
                    logger.info(
                        "skip duplicate stream interrupt session_id=%s text=%s compact=%s last_compact=%s delta_ms=%.1f",
                        safe_session,
                        text,
                        current_compact,
                        last_interrupt_compact,
                        (event_ts - last_interrupt_ts) * 1000.0,
                    )
                    continue
            if _is_interrupt_command_text(text):
                logger.info("barge-in stream command detected session_id=%s text=%s", safe_session, text)
                interrupted = await interrupt_current_tts(trigger="interrupt_stream", text=text)
                if interrupted and current_compact:
                    state["last_stream_interrupt_compact"] = current_compact
                    state["last_stream_interrupt_ts"] = event_ts
                continue
            if _is_barge_in_stream_text(text):
                logger.info("barge-in stream detected session_id=%s text=%s", safe_session, text)
                interrupted = await interrupt_current_tts(trigger="barge_in_stream", text=text)
                if interrupted and current_compact:
                    state["last_stream_interrupt_compact"] = current_compact
                    state["last_stream_interrupt_ts"] = event_ts

    async def tts_stream_loop() -> None:
        async def run_tts_turn(
            kind: str,
            user_text: str,
            turn_cancel_event: asyncio.Event,
            enqueue_ts: float | None = None,
            asr_last_update_at: float | None = None,
            asr_started_at: float | None = None,
        ) -> None:
            state["tts_live_text"] = ""
            state["tts_live_ts"] = 0.0
            state["tts_audio_started"] = False
            turn_started_at = time.monotonic()
            first_token_at: float | None = None
            first_audio_at: float | None = None
            first_send_at: float | None = None
            queue_wait_ms = -1.0
            if isinstance(enqueue_ts, (int, float)):
                queue_wait_ms = (turn_started_at - float(enqueue_ts)) * 1000.0
            asr_silence_wait_ms: float | None = None
            if isinstance(asr_last_update_at, float) and asr_last_update_at > 0 and isinstance(enqueue_ts, (int, float)):
                asr_silence_wait_ms = (float(enqueue_ts) - asr_last_update_at) * 1000.0
            asr_recognition_ms: float | None = None
            if isinstance(asr_started_at, (int, float)) and asr_started_at > 0 and isinstance(asr_last_update_at, (int, float)) and asr_last_update_at > asr_started_at:
                asr_recognition_ms = (float(asr_last_update_at) - float(asr_started_at)) * 1000.0

            def _on_llm_token(token: str) -> None:
                nonlocal first_token_at
                if not token:
                    return
                if first_token_at is None:
                    first_token_at = time.monotonic()
                    logger.info(
                        "ws turn first token latency session_id=%s mode=%s latency_ms=%.1f",
                        safe_session,
                        kind,
                        (first_token_at - turn_started_at) * 1000.0,
                    )
                merged = str(state.get("tts_live_text") or "") + token
                if len(merged) > 300:
                    merged = merged[-300:]
                state["tts_live_text"] = merged
                state["tts_live_ts"] = time.monotonic()

            transient_system_prompt = START_TRIGGER if kind == VOICE_COMMAND_START else None
            workflow_enabled = _has_session_workflow_state(safe_session)
            if kind == "user_text" and user_text.strip() and workflow_enabled:
                before_snapshot = _get_session_workflow_runtime_snapshot(safe_session) or {}
                from_node_id = str(before_snapshot.get("cursor_node_id") or "").strip()
                current_intent_labels = _get_session_intent_labels(safe_session)
                if current_intent_labels:
                    try:
                        intents, raw_output, intent_prompt_text = await _classify_customer_intents(
                            session_id=safe_session,
                            user_text=user_text,
                            on_usage=_accumulate_model_usage,
                        )
                        if intent_prompt_text:
                            await send_json_event(
                                {
                                    "event": "intent_prompt",
                                    "session_id": safe_session,
                                    "text": user_text,
                                    "prompt": intent_prompt_text,
                                    "model": INTENT_MODEL_ID,
                                }
                            )
                        workflow_advanced, matched_label, jump_node_id = _advance_session_workflow_by_intents(
                            session_id=safe_session,
                            intents=intents,
                        )
                        await send_json_event(
                            {
                                "event": "intent_result",
                                "session_id": safe_session,
                                "text": user_text,
                                "intents": intents,
                                "model": INTENT_MODEL_ID,
                                "context_window": max(0, INTENT_CONTEXT_WINDOW),
                            }
                        )
                        await emit_workflow_progress(
                            trigger="intent_result",
                            intents=intents,
                            matched_label=matched_label,
                            jump_node_id=jump_node_id,
                            from_node_id=from_node_id,
                            advanced=workflow_advanced,
                        )
                        logger.info(
                            "intent result session_id=%s text=%s intents=%s workflow_advanced=%s matched_label=%s jump_node_id=%s raw=%s",
                            safe_session,
                            user_text,
                            intents,
                            workflow_advanced,
                            matched_label,
                            jump_node_id,
                            raw_output,
                        )
                    except Exception:
                        logger.exception(
                            "intent classify failed session_id=%s text=%s",
                            safe_session,
                            user_text,
                        )
                        try:
                            fallback_label = _get_session_intent_fallback_label(safe_session)
                            fallback_intents = [fallback_label] if fallback_label else []
                            await send_json_event(
                                {
                                    "event": "intent_result",
                                    "session_id": safe_session,
                                    "text": user_text,
                                    "intents": fallback_intents,
                                    "model": INTENT_MODEL_ID,
                                    "context_window": max(0, INTENT_CONTEXT_WINDOW),
                                }
                            )
                            await emit_workflow_progress(
                                trigger="intent_result",
                                intents=fallback_intents,
                                from_node_id=from_node_id,
                                advanced=False,
                                reason="intent_classify_failed",
                            )
                        except Exception:
                            pass
                else:
                    logger.info(
                        "intent classify skipped session_id=%s text=%s reason=no_labeled_outgoing_edges",
                        safe_session,
                        user_text,
                    )
                    try:
                        await send_json_event(
                            {
                                "event": "intent_result",
                                "session_id": safe_session,
                                "text": user_text,
                                "intents": [],
                                "model": INTENT_MODEL_ID,
                                "context_window": max(0, INTENT_CONTEXT_WINDOW),
                                "skipped": True,
                                "reason": "no_labeled_outgoing_edges",
                            }
                        )
                        await emit_workflow_progress(
                            trigger="intent_result",
                            intents=[],
                            from_node_id=from_node_id,
                            advanced=False,
                            reason="no_labeled_outgoing_edges",
                        )
                    except Exception:
                        pass

            messages = _build_messages(
                session_id=safe_session,
                user_text=user_text,
                transient_system_prompt=transient_system_prompt,
            )
            if kind == "user_text" and user_text.strip() and (not workflow_enabled):
                async def _emit_intent_result() -> None:
                    try:
                        intents, raw_output, intent_prompt_text = await _classify_customer_intents(
                            session_id=safe_session,
                            user_text=user_text,
                            on_usage=_accumulate_model_usage,
                        )
                        if intent_prompt_text:
                            await send_json_event(
                                {
                                    "event": "intent_prompt",
                                    "session_id": safe_session,
                                    "text": user_text,
                                    "prompt": intent_prompt_text,
                                    "model": INTENT_MODEL_ID,
                                }
                            )
                        await send_json_event(
                            {
                                "event": "intent_result",
                                "session_id": safe_session,
                                "text": user_text,
                                "intents": intents,
                                "model": INTENT_MODEL_ID,
                                "context_window": max(0, INTENT_CONTEXT_WINDOW),
                            }
                        )
                        logger.info(
                            "intent result session_id=%s text=%s intents=%s raw=%s",
                            safe_session,
                            user_text,
                            intents,
                            raw_output,
                        )
                    except Exception:
                        logger.exception(
                            "intent classify failed session_id=%s text=%s",
                            safe_session,
                            user_text,
                        )
                        try:
                            fallback_label = _get_session_intent_fallback_label(safe_session)
                            fallback_intents = [fallback_label] if fallback_label else []
                            await send_json_event(
                                {
                                    "event": "intent_result",
                                    "session_id": safe_session,
                                    "text": user_text,
                                    "intents": fallback_intents,
                                    "model": INTENT_MODEL_ID,
                                    "context_window": max(0, INTENT_CONTEXT_WINDOW),
                                }
                            )
                        except Exception:
                            pass

                asyncio.create_task(_emit_intent_result())
            prompt_text = _format_nlp_prompt_messages(messages)
            await send_json_event(
                {
                    "event": "nlp_prompt",
                    "session_id": safe_session,
                    "mode": kind,
                    "text": prompt_text,
                    "message_count": len(messages),
                }
            )
            await send_json_event(
                {
                    "event": "tts_start",
                    "session_id": safe_session,
                    "text": "",
                    "mode": kind,
                }
            )
            total_audio_bytes = 0
            llm_reply_parts: list[str] = []
            interrupted = False
            send_started_at = time.monotonic()
            bytes_per_second = max(1, TTS_SAMPLE_RATE * TTS_OUTPUT_CHANNELS * TTS_SAMPLE_WIDTH_BYTES)
            bytes_per_sample = max(1, TTS_OUTPUT_CHANNELS * TTS_SAMPLE_WIDTH_BYTES)
            frame_ms = max(5, BARGE_IN_AUDIO_FRAME_MS)
            frame_bytes = max(bytes_per_sample, int(bytes_per_second * (frame_ms / 1000.0)))
            frame_bytes = max(bytes_per_sample, (frame_bytes // bytes_per_sample) * bytes_per_sample)
            max_audio_ahead_seconds = max(0.0, BARGE_IN_MAX_AUDIO_AHEAD_SECONDS)

            segment_seq = 0
            tts_chars_before = int((state.get("billing_totals", {}) or {}).get("tts_characters", 0))

            async def _on_llm_segment(segment: str) -> None:
                nonlocal segment_seq
                raw_segment = segment or ""
                # TTS billing fallback: count submitted characters directly (official rule: each code point counts as 1).
                _accumulate_tts_usage_characters(len(raw_segment))
                current = raw_segment.strip()
                if not current:
                    return
                segment_seq += 1
                logger.info("NLP segment session_id=%s mode=%s text=%s", safe_session, kind, current)
                await send_json_event(
                    {
                        "event": "tts_segment",
                        "session_id": safe_session,
                        "mode": kind,
                        "seq": segment_seq,
                        "text": current,
                    }
                )

            audio_stream = _stream_tts_audio(
                messages=messages,
                session_id=safe_session,
                reply_parts_out=llm_reply_parts,
                cancel_event=turn_cancel_event,
                on_token=_on_llm_token,
                on_usage=_accumulate_model_usage,
                on_segment=_on_llm_segment,
            )
            try:
                async for audio_chunk in audio_stream:
                    if stop_event.is_set() or turn_cancel_event.is_set():
                        interrupted = True
                        break
                    for frame in _iter_audio_frames(audio_chunk, frame_bytes):
                        if stop_event.is_set() or turn_cancel_event.is_set():
                            interrupted = True
                            break
                        if TTS_REALTIME_PACING:
                            while True:
                                actual_elapsed = max(0.0, time.monotonic() - send_started_at)
                                ahead_after_send = (
                                    (total_audio_bytes + len(frame)) / float(bytes_per_second)
                                ) - actual_elapsed
                                if ahead_after_send <= max_audio_ahead_seconds:
                                    break
                                await asyncio.sleep(min(0.02, ahead_after_send - max_audio_ahead_seconds))
                                if stop_event.is_set() or turn_cancel_event.is_set():
                                    interrupted = True
                                    break
                            if interrupted:
                                break
                        await send_audio_frame(frame)
                        total_audio_bytes += len(frame)
                        if total_audio_bytes > 0:
                            state["tts_audio_started"] = True
                        if first_audio_at is None and total_audio_bytes > 0:
                            first_audio_at = time.monotonic()
                            logger.info(
                                "ws turn first audio latency session_id=%s mode=%s latency_ms=%.1f",
                                safe_session,
                                kind,
                                (first_audio_at - turn_started_at) * 1000.0,
                            )
                            await send_json_event({
                                "event": "tts_latency",
                                "session_id": safe_session,
                                "latency": {
                                    "queue_wait_ms": round(queue_wait_ms, 1) if queue_wait_ms >= 0 else None,
                                    "nlp_first_token_ms": round((first_token_at - turn_started_at) * 1000.0, 1) if first_token_at else None,
                                    "tts_first_audio_ms": round((first_audio_at - first_token_at) * 1000.0, 1) if first_token_at else None,
                                },
                            })
                        if first_send_at is None and total_audio_bytes > 0:
                            first_send_at = time.monotonic()
                    if interrupted:
                        break
            except asyncio.CancelledError:
                interrupted = True
            except Exception:
                logger.exception("ws tts turn failed session_id=%s", safe_session)

            if turn_cancel_event.is_set():
                interrupted = True
            assistant_text = "".join(llm_reply_parts).strip()
            # Always save history here — the _stream_tts_audio generator may have been
            # closed early via aclose() (barge-in race), in which case its finalizer
            # never runs and _append_history would be skipped without this call.
            history_user_text = "" if _match_voice_command(user_text) == VOICE_COMMAND_START else user_text
            _append_history(session_id=safe_session, user_text=history_user_text, assistant_reply=assistant_text)
            if assistant_text:
                state["recent_ai_text"] = assistant_text
                state["recent_ai_ts"] = time.monotonic()
            if assistant_text and not interrupted:
                await send_json_event(
                    {
                        "event": "assistant_text",
                        "session_id": safe_session,
                        "text": assistant_text,
                        "mode": kind,
                    }
                )

            latency_report: dict[str, Any] = {
                "asr_silence_wait_ms": round(asr_silence_wait_ms, 1) if asr_silence_wait_ms is not None else None,
                "queue_wait_ms": round(queue_wait_ms, 1) if queue_wait_ms >= 0 else None,
                "nlp_first_token_ms": round((first_token_at - turn_started_at) * 1000.0, 1) if first_token_at else None,
                "tts_first_audio_ms": round((first_audio_at - first_token_at) * 1000.0, 1) if (first_token_at and first_audio_at) else None,
                "first_send_ms": round((first_send_at - first_audio_at) * 1000.0, 1) if (first_send_at and first_audio_at) else None,
                "backend_total_ms": round((first_send_at - turn_started_at) * 1000.0, 1) if first_send_at else None,
            }
            logger.info(
                "ws turn latency session_id=%s mode=%s %s",
                safe_session,
                kind,
                latency_report,
            )
            await send_json_event(
                {
                    "event": "tts_end",
                    "session_id": safe_session,
                    "audio_bytes": total_audio_bytes,
                    "mode": kind,
                    "interrupted": interrupted,
                    "latency": latency_report,
                }
            )
            if first_token_at is not None and first_audio_at is not None:
                logger.info(
                    "ws turn token_to_audio latency session_id=%s mode=%s latency_ms=%.1f",
                    safe_session,
                    kind,
                    (first_audio_at - first_token_at) * 1000.0,
                )
            logger.info(
                "ws turn done session_id=%s mode=%s queue_wait_ms=%.1f total_ms=%.1f interrupted=%s assistant_chars=%s audio_bytes=%s",
                safe_session,
                kind,
                queue_wait_ms,
                (time.monotonic() - turn_started_at) * 1000.0,
                interrupted,
                len(assistant_text),
                total_audio_bytes,
            )
            tts_chars_after = int((state.get("billing_totals", {}) or {}).get("tts_characters", 0))
            if total_audio_bytes > 0 and tts_chars_after <= tts_chars_before:
                logger.warning(
                    "tts usage missing session_id=%s mode=%s audio_bytes=%s chars_before=%s chars_after=%s",
                    safe_session,
                    kind,
                    total_audio_bytes,
                    tts_chars_before,
                    tts_chars_after,
                )
            played_seconds = total_audio_bytes / float(max(1, bytes_per_second))
            if kind == "user_text":
                if interrupted and total_audio_bytes > 0 and played_seconds <= SHORT_INTERRUPTED_TTS_MERGE_SECONDS:
                    previous_pending = str(state.get("pending_merge_user_text") or "")
                    merged_pending = _merge_user_text_for_nlp(previous_pending, user_text)
                    state["pending_merge_user_text"] = merged_pending
                    logger.info(
                        "queue short-interrupted user_text for next nlp session_id=%s played_s=%.3f threshold_s=%.3f text=%s",
                        safe_session,
                        played_seconds,
                        SHORT_INTERRUPTED_TTS_MERGE_SECONDS,
                        merged_pending,
                    )
                else:
                    if interrupted:
                        logger.info(
                            "clear pending merge because interrupted turn exceeded threshold session_id=%s played_s=%.3f threshold_s=%.3f",
                            safe_session,
                            played_seconds,
                            SHORT_INTERRUPTED_TTS_MERGE_SECONDS,
                        )
                    state["pending_merge_user_text"] = ""
            if workflow_enabled:
                try:
                    before_snapshot = _get_session_workflow_runtime_snapshot(safe_session) or {}
                    _refresh_session_workflow_view(
                        safe_session,
                        consume_current=(not interrupted),
                    )
                    after_snapshot = _get_session_workflow_runtime_snapshot(safe_session) or {}
                    advanced = (
                        str(before_snapshot.get("cursor_node_id") or "").strip()
                        != str(after_snapshot.get("cursor_node_id") or "").strip()
                    )
                    await emit_workflow_progress(
                        trigger="turn_complete",
                        advanced=advanced,
                        reason="tts_turn_end",
                    )
                except Exception:
                    logger.exception("workflow view refresh failed session_id=%s", safe_session)
            state["tts_live_text"] = ""
            state["tts_live_ts"] = 0.0
            state["tts_audio_started"] = False

        pending_item: dict[str, Any] | None = None
        while not stop_event.is_set():
            if pending_item is not None:
                item = pending_item
                pending_item = None
            else:
                try:
                    item = await asyncio.wait_for(commit_queue.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue
            kind = str(item.get("kind") or "user_text")
            user_text = str(item.get("text") or "").strip()
            enqueue_ts = item.get("enqueue_ts")
            asr_last_update_at = item.get("asr_last_update_at")
            asr_started_at = item.get("asr_started_at")
            if not user_text:
                continue

            if kind == "user_text":
                max_batch_items = max(1, NLP_BATCH_MAX_ITEMS)
                max_batch_chars = max(1, NLP_BATCH_MAX_CHARS)
                batch_texts: list[str] = [user_text]
                batch_chars = len(user_text)

                while len(batch_texts) < max_batch_items and batch_chars < max_batch_chars:
                    try:
                        next_item = commit_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    next_kind = str(next_item.get("kind") or "user_text")
                    next_text = str(next_item.get("text") or "").strip()
                    if not next_text:
                        continue
                    if next_kind != "user_text":
                        pending_item = next_item
                        break
                    estimated_chars = batch_chars + 1 + len(next_text)
                    if estimated_chars > max_batch_chars:
                        pending_item = next_item
                        break
                    batch_texts.append(next_text)
                    batch_chars = estimated_chars

                if len(batch_texts) > 1:
                    merged_parts = [seg.strip().rstrip("。.!！？?；;") for seg in batch_texts if seg.strip()]
                    user_text = "。".join(part for part in merged_parts if part)
                    if user_text and not user_text.endswith(("。", "！", "？", "!", "?", "；", ";")):
                        user_text += "。"
                    logger.info(
                        "nlp batch merged session_id=%s items=%s chars=%s text=%s",
                        safe_session,
                        len(batch_texts),
                        len(user_text),
                        user_text,
                    )

            if not user_text:
                continue
            if kind == "user_text":
                pending_merge_text = str(state.get("pending_merge_user_text") or "").strip()
                if pending_merge_text:
                    merged_user_text = _merge_user_text_for_nlp(pending_merge_text, user_text)
                    logger.info(
                        "merge short-interrupted text into next nlp submit session_id=%s previous=%s current=%s merged=%s",
                        safe_session,
                        pending_merge_text,
                        user_text,
                        merged_user_text,
                    )
                    user_text = merged_user_text
                    state["pending_merge_user_text"] = ""

            state["tts_busy"] = True
            state["tts_interrupted"] = False
            state["tts_audio_started"] = False
            # Reset cross-turn interrupt gates so a newly started TTS turn can be interrupted immediately.
            state["interrupt_cooldown_until"] = 0.0
            state["last_stream_interrupt_ts"] = 0.0
            state["last_stream_interrupt_compact"] = ""
            turn_cancel_event = asyncio.Event()
            state["turn_cancel_event"] = turn_cancel_event
            turn_task = asyncio.create_task(
                run_tts_turn(
                    kind=kind,
                    user_text=user_text,
                    turn_cancel_event=turn_cancel_event,
                    enqueue_ts=float(enqueue_ts) if isinstance(enqueue_ts, (int, float)) else None,
                    asr_last_update_at=float(asr_last_update_at) if isinstance(asr_last_update_at, (int, float)) else None,
                    asr_started_at=float(asr_started_at) if isinstance(asr_started_at, (int, float)) else None,
                )
            )
            state["turn_task"] = turn_task
            try:
                await turn_task
            except asyncio.CancelledError:
                pass
            finally:
                if state.get("turn_task") is turn_task:
                    state["turn_task"] = None
                if state.get("turn_cancel_event") is turn_cancel_event:
                    state["turn_cancel_event"] = None
                state["tts_busy"] = False

    await send_json_event(
        {
            "event": "ready",
            "session_id": safe_session,
            "asr_sample_rate": ASR_SAMPLE_RATE,
            "tts_sample_rate": TTS_SAMPLE_RATE,
            "tts_format": TTS_AUDIO_FORMAT,
        }
    )

    recv_task = asyncio.create_task(recv_audio_loop())
    commit_task = asyncio.create_task(asr_commit_loop())
    stream_interrupt_task = asyncio.create_task(asr_stream_interrupt_loop())
    tts_task = asyncio.create_task(tts_stream_loop())
    tasks = [recv_task, commit_task, stream_interrupt_task, tts_task]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for done_task in done:
            try:
                await done_task
            except WebSocketDisconnect:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("ws realtime task failed session_id=%s", safe_session)
        stop_event.set()
        for pending_task in pending:
            pending_task.cancel()
        for pending_task in pending:
            try:
                await pending_task
            except Exception:
                pass
    finally:
        stop_event.set()
        for task in tasks:
            if task.done():
                continue
            task.cancel()
            try:
                await task
            except Exception:
                pass
        if bool(state.get("billing_active")) and (not bool(state.get("billing_summary_emitted"))):
            try:
                await _emit_billing_result(
                    source="session_closed",
                    reason="connection_closed_before_end_command",
                    trigger_text="",
                )
            except Exception:
                logger.exception("failed to emit billing result on session close session_id=%s", safe_session)
        _clear_session_system_prompt(safe_session)
        _clear_session_intent_labels(safe_session)
        _clear_session_intent_fallback_label(safe_session)
        _clear_session_workflow_state(safe_session)
        await asr_session.close()
        try:
            await websocket.close()
        except Exception:
            pass


async def _ws_realtime_dual_channel_entry(websocket: WebSocket, channel: str) -> None:
    session_id = websocket.query_params.get("session_id", "").strip()
    audio_format = websocket.query_params.get("format", "pcm").lower().strip() or "pcm"
    if not session_id:
        session_id = f"ws_{uuid.uuid4().hex[:12]}"
    safe_session = _safe_segment(session_id)

    await websocket.accept()
    if not safe_session:
        if channel == "control":
            await websocket.send_text(json.dumps({"event": "error", "message": "invalid session_id"}, ensure_ascii=False))
        await websocket.close(code=1008)
        return

    state, err = await _attach_dual_ws_channel(
        safe_session=safe_session,
        raw_session_id=session_id,
        channel=channel,
        websocket=websocket,
        audio_format=audio_format,
    )
    if err:
        if channel == "control":
            await websocket.send_text(json.dumps({"event": "error", "message": err}, ensure_ascii=False))
        await websocket.close(code=1008)
        return
    if state is None:
        await websocket.close(code=1011)
        return

    try:
        ready_event = state["ready_event"]
        done_event = state["done_event"]
        if not ready_event.is_set():
            if channel == "control":
                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "waiting_peer",
                            "session_id": safe_session,
                            "channel": channel,
                            "message": "waiting for media/control channel",
                        },
                        ensure_ascii=False,
                    )
                )
            await asyncio.wait_for(ready_event.wait(), timeout=DUAL_CHANNEL_WAIT_SECONDS)

        async with DUAL_WS_SESSIONS_LOCK:
            current = DUAL_WS_SESSIONS.get(safe_session)
            if (
                current is state
                and current.get("control_ws") is not None
                and current.get("media_ws") is not None
            ):
                runner_task = current.get("runner_task")
                if runner_task is None or runner_task.done():
                    current["runner_task"] = asyncio.create_task(_run_dual_ws_session(current))
        await done_event.wait()
    except asyncio.TimeoutError:
        if channel == "control":
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "error",
                        "session_id": safe_session,
                        "message": f"dual channel timeout: missing peer for {DUAL_CHANNEL_WAIT_SECONDS:.1f}s",
                    },
                    ensure_ascii=False,
                )
            )
    except WebSocketDisconnect:
        pass
    finally:
        await _detach_dual_ws_channel(safe_session=safe_session, channel=channel, websocket=websocket)
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/realtime/control")
async def ws_realtime_control(websocket: WebSocket) -> None:
    await _ws_realtime_dual_channel_entry(websocket, "control")


@app.websocket("/ws/realtime/media")
async def ws_realtime_media(websocket: WebSocket) -> None:
    await _ws_realtime_dual_channel_entry(websocket, "media")


@app.post("/api/v3/audio/chunks")
async def upload_audio_chunk(request: Request) -> Any:
    session_id = request.query_params.get("session_id", "")
    chunk_index_text = request.query_params.get("chunk_index", "")
    audio_format = request.query_params.get("format", "pcm").lower().strip() or "pcm"

    if not session_id:
        raise HTTPException(status_code=400, detail="missing query parameter: session_id")

    safe_session = _safe_segment(session_id)
    if not safe_session:
        raise HTTPException(status_code=400, detail="invalid session_id")

    try:
        chunk_index = int(chunk_index_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="chunk_index must be an integer") from exc
    if chunk_index < 0:
        raise HTTPException(status_code=400, detail="chunk_index must be >= 0")

    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="empty request body")
    if len(audio_bytes) > AUDIO_CHUNK_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"chunk too large, max={AUDIO_CHUNK_MAX_BYTES} bytes")

    await _cleanup_idle_asr_sessions(force=False)
    asr_session = _get_or_create_asr_session(session_id=safe_session, audio_format=audio_format)
    asr_session.enqueue_chunk(audio_bytes=audio_bytes, audio_format=audio_format, chunk_index=chunk_index)

    return {
        "ok": True,
        "received": True,
        "session_id": safe_session,
        "chunk_index": chunk_index,
        "size": len(audio_bytes),
    }


if __name__ == "__main__":
    port = int(os.getenv("_FAAS_RUNTIME_PORT", "8080"))
    ws_ping_interval = None if UVICORN_WS_PING_INTERVAL <= 0 else UVICORN_WS_PING_INTERVAL
    ws_ping_timeout = None if ws_ping_interval is None else UVICORN_WS_PING_TIMEOUT
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        access_log=False,
        ws_ping_interval=ws_ping_interval,
        ws_ping_timeout=ws_ping_timeout,
    )
