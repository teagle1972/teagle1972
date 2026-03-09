(function () {
  const $ = (id) => document.getElementById(id);

  const ui = {
    serverBase: $("serverBase"),
    sessionId: $("sessionId"),
    statusLine: $("statusLine"),
    systemPrompt: $("systemPrompt"),
    asrBox: $("asrBox"),
    ttsBox: $("ttsBox"),
    intentBox: $("intentBox"),
    logBox: $("logBox"),
    btnConnect: $("btnConnect"),
    btnDisconnect: $("btnDisconnect"),
    btnMicStart: $("btnMicStart"),
    btnMicStop: $("btnMicStop"),
    btnStartDialog: $("btnStartDialog"),
    btnEndDialog: $("btnEndDialog"),
    btnSetPrompt: $("btnSetPrompt"),
    btnClearPrompt: $("btnClearPrompt"),
  };

  const state = {
    controlWs: null,
    mediaWs: null,
    controlOpen: false,
    mediaOpen: false,
    micOn: false,
    mediaStream: null,
    captureCtx: null,
    captureSource: null,
    captureProcessor: null,
    captureSilentGain: null,
    playbackCtx: null,
    ttsSampleRate: 24000,
    ttsFormat: "pcm",
    nextPlayTime: 0,
    heartbeatTimer: null,
    asrPartial: "",
  };

  const DEFAULT_CUSTOMER_PROFILE = [
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
  ].join("\n");

  const DEFAULT_WORKFLOW = [
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
  ].join("\n");

  const DEFAULT_SYSTEM_INSTRUCTION_BASE = [
    "你是电话沟通助手，请结合用户画像和工作流程，主动发起通话并推进沟通。",
    "请先输出一轮电话开场白，包含自我介绍、来电目的，并确认对方是否方便通话。",
    "",
    "【ASR识别结果】",
  ].join("\n");

  function buildDefaultSystemPrompt() {
    return [
      DEFAULT_SYSTEM_INSTRUCTION_BASE.trim(),
      DEFAULT_CUSTOMER_PROFILE.trim(),
      DEFAULT_WORKFLOW.trim(),
    ].join("\n\n");
  }

  function nowText() {
    const d = new Date();
    return d.toLocaleTimeString();
  }

  function genSessionId() {
    return "ws_" + Math.random().toString(16).slice(2, 10);
  }

  function appendConsole(el, line, maxLines) {
    const text = (el.textContent || "") + line + "\n";
    const lines = text.split("\n");
    if (lines.length > maxLines) {
      el.textContent = lines.slice(lines.length - maxLines).join("\n");
    } else {
      el.textContent = text;
    }
    el.scrollTop = el.scrollHeight;
  }

  function log(line) {
    appendConsole(ui.logBox, `[${nowText()}] ${line}`, 500);
  }

  function setStatus(text) {
    ui.statusLine.textContent = `状态: ${text}`;
  }

  function normalizeWsBase(raw) {
    const v = (raw || "").trim();
    if (!v) {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${location.host}`;
    }
    if (v.startsWith("ws://") || v.startsWith("wss://")) {
      return v.replace(/\/$/, "");
    }
    if (v.startsWith("http://") || v.startsWith("https://")) {
      return v.replace(/^http/i, "ws").replace(/\/$/, "");
    }
    return `ws://${v.replace(/\/$/, "")}`;
  }

  function currentSessionId() {
    const sid = (ui.sessionId.value || "").trim();
    return sid || genSessionId();
  }

  function buildWsUrl(path) {
    const sid = currentSessionId();
    ui.sessionId.value = sid;
    const base = normalizeWsBase(ui.serverBase.value);
    const qs = `session_id=${encodeURIComponent(sid)}&format=pcm`;
    return `${base}${path}?${qs}`;
  }

  function sendControl(payload) {
    if (!state.controlWs || state.controlWs.readyState !== WebSocket.OPEN) {
      log("control 通道未连接");
      return;
    }
    state.controlWs.send(JSON.stringify(payload));
  }

  function applySessionPromptFromTextarea(silent) {
    const text = (ui.systemPrompt.value || "").trim();
    if (!text) {
      if (!silent) {
        log("提示词为空，未下发");
      }
      return;
    }
    sendControl({ event: "set_system_prompt", system_prompt: text });
    if (!silent) {
      log(`已下发系统提示词，chars=${text.length}`);
    }
  }

  function ensurePlaybackContext() {
    if (!state.playbackCtx) {
      state.playbackCtx = new AudioContext();
      state.nextPlayTime = state.playbackCtx.currentTime;
    }
    return state.playbackCtx;
  }

  function playPcmChunk(arrayBuffer) {
    if (!(arrayBuffer instanceof ArrayBuffer)) {
      return;
    }
    if (state.ttsFormat !== "pcm") {
      log(`暂不支持音频格式: ${state.ttsFormat}`);
      return;
    }
    const pcm16 = new Int16Array(arrayBuffer);
    if (!pcm16.length) {
      return;
    }
    const ctx = ensurePlaybackContext();
    const sampleRate = Number(state.ttsSampleRate) || 24000;

    const floatData = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i += 1) {
      floatData[i] = Math.max(-1, Math.min(1, pcm16[i] / 32768));
    }

    const buffer = ctx.createBuffer(1, floatData.length, sampleRate);
    buffer.copyToChannel(floatData, 0);

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);

    const now = ctx.currentTime;
    if (!state.nextPlayTime || state.nextPlayTime < now) {
      state.nextPlayTime = now + 0.02;
    }
    src.start(state.nextPlayTime);
    state.nextPlayTime += buffer.duration;
  }

  function downsampleTo16kPCM(float32Data, sourceRate) {
    const targetRate = 16000;
    if (!float32Data || !float32Data.length) {
      return null;
    }

    let outLength = float32Data.length;
    let ratio = 1;
    if (sourceRate > targetRate) {
      ratio = sourceRate / targetRate;
      outLength = Math.max(1, Math.round(float32Data.length / ratio));
    }

    const out = new Int16Array(outLength);
    let pos = 0;
    let idx = 0;
    while (idx < outLength) {
      const nextPos = Math.min(float32Data.length, Math.round((idx + 1) * ratio));
      let sum = 0;
      let count = 0;
      for (let i = pos; i < nextPos; i += 1) {
        sum += float32Data[i];
        count += 1;
      }
      const sample = count > 0 ? sum / count : float32Data[Math.min(float32Data.length - 1, pos)];
      const clamped = Math.max(-1, Math.min(1, sample));
      out[idx] = clamped < 0 ? clamped * 32768 : clamped * 32767;
      pos = nextPos;
      idx += 1;
    }

    return out.buffer;
  }

  function resetAsrPartial() {
    state.asrPartial = "";
  }

  function renderAsrPartial() {
    if (!state.asrPartial) {
      return;
    }
    appendConsole(ui.asrBox, `[partial] ${state.asrPartial}`, 300);
  }

  function handleControlEvent(payload) {
    const event = String(payload.event || "message");

    if (event === "ready") {
      state.ttsSampleRate = Number(payload.tts_sample_rate || 24000);
      state.ttsFormat = String(payload.tts_format || "pcm");
      log(`会话就绪 session=${payload.session_id} tts=${state.ttsSampleRate}/${state.ttsFormat}`);
      return;
    }

    if (event === "waiting_peer") {
      log(`等待对端通道: ${payload.message || "waiting"}`);
      return;
    }

    if (event === "asr_partial") {
      state.asrPartial = String(payload.text || "");
      renderAsrPartial();
      return;
    }

    if (event === "asr_commit") {
      resetAsrPartial();
      const text = String(payload.text || "");
      const command = payload.command ? ` | command=${payload.command}` : "";
      appendConsole(ui.asrBox, `[commit] ${text}${command}`, 300);
      return;
    }

    if (event === "nlp_prompt") {
      appendConsole(ui.ttsBox, `[nlp_prompt] ${payload.mode || "-"}: ${payload.text || ""}`, 400);
      return;
    }

    if (event === "tts_start") {
      appendConsole(ui.ttsBox, `[tts_start] ${payload.text || ""}`, 400);
      return;
    }

    if (event === "tts_segment") {
      appendConsole(ui.ttsBox, `[tts_segment#${payload.seq || 0}] ${payload.text || ""}`, 400);
      return;
    }

    if (event === "assistant_text") {
      appendConsole(ui.ttsBox, `[assistant] ${payload.text || ""}`, 400);
      return;
    }

    if (event === "tts_interrupted") {
      if (state.playbackCtx) {
        state.nextPlayTime = state.playbackCtx.currentTime;
      }
      appendConsole(ui.ttsBox, `[tts_interrupted] trigger=${payload.trigger || ""} text=${payload.text || ""}`, 400);
      return;
    }

    if (event === "tts_end") {
      appendConsole(ui.ttsBox, `[tts_end] bytes=${payload.audio_bytes || 0} interrupted=${!!payload.interrupted}`, 400);
      return;
    }

    if (event === "intent_result") {
      const intents = Array.isArray(payload.intents) ? payload.intents.join(", ") : String(payload.intents || "");
      appendConsole(ui.intentBox, `[intent] text=${payload.text || ""} | intents=${intents}`, 300);
      return;
    }

    if (event === "command") {
      log(`command=${payload.command || ""} action=${payload.action || ""}`);
      return;
    }

    if (event === "error") {
      log(`ERROR: ${payload.message || "unknown"}`);
      return;
    }

    if (event === "pong") {
      return;
    }

    log(`event=${event} payload=${JSON.stringify(payload)}`);
  }

  function handleControlMessage(rawText) {
    try {
      const payload = JSON.parse(rawText);
      handleControlEvent(payload);
    } catch (err) {
      log(`control raw: ${rawText}`);
    }
  }

  async function connectWs() {
    if (state.controlOpen || state.mediaOpen) {
      log("已有连接，请先断开");
      return;
    }

    const controlUrl = buildWsUrl("/ws/realtime/control");
    const mediaUrl = buildWsUrl("/ws/realtime/media");

    setStatus("连接中");
    log(`control => ${controlUrl}`);
    log(`media => ${mediaUrl}`);

    state.controlWs = new WebSocket(controlUrl);
    state.mediaWs = new WebSocket(mediaUrl);
    state.mediaWs.binaryType = "arraybuffer";

    state.controlWs.onopen = function () {
      state.controlOpen = true;
      setStatus(`control已连接 / session=${ui.sessionId.value}`);
      log("control connected");
      applySessionPromptFromTextarea(true);
    };
    state.controlWs.onclose = function () {
      state.controlOpen = false;
      setStatus("control已断开");
      log("control closed");
      stopMic();
    };
    state.controlWs.onerror = function () {
      log("control error");
    };
    state.controlWs.onmessage = function (ev) {
      if (typeof ev.data === "string") {
        handleControlMessage(ev.data);
      }
    };

    state.mediaWs.onopen = function () {
      state.mediaOpen = true;
      log("media connected");
    };
    state.mediaWs.onclose = function () {
      state.mediaOpen = false;
      log("media closed");
      stopMic();
    };
    state.mediaWs.onerror = function () {
      log("media error");
    };
    state.mediaWs.onmessage = function (ev) {
      if (typeof ev.data === "string") {
        handleControlMessage(ev.data);
        return;
      }
      if (ev.data instanceof ArrayBuffer) {
        playPcmChunk(ev.data);
        return;
      }
      if (ev.data instanceof Blob) {
        ev.data.arrayBuffer().then(playPcmChunk).catch(() => {});
      }
    };

    if (state.heartbeatTimer) {
      clearInterval(state.heartbeatTimer);
    }
    state.heartbeatTimer = setInterval(function () {
      if (state.controlWs && state.controlWs.readyState === WebSocket.OPEN) {
        sendControl({ event: "ping" });
      }
    }, 10000);
  }

  function disconnectWs() {
    if (state.heartbeatTimer) {
      clearInterval(state.heartbeatTimer);
      state.heartbeatTimer = null;
    }
    stopMic();
    if (state.controlWs) {
      try { state.controlWs.close(); } catch (_) {}
    }
    if (state.mediaWs) {
      try { state.mediaWs.close(); } catch (_) {}
    }
    state.controlWs = null;
    state.mediaWs = null;
    state.controlOpen = false;
    state.mediaOpen = false;
    setStatus("未连接");
  }

  async function startMic() {
    if (state.micOn) {
      return;
    }
    if (!state.mediaWs || state.mediaWs.readyState !== WebSocket.OPEN) {
      log("media 通道未连接，无法开麦");
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      log("当前浏览器不支持 getUserMedia");
      return;
    }

    try {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.captureCtx = new AudioContext();
      state.captureSource = state.captureCtx.createMediaStreamSource(state.mediaStream);
      state.captureProcessor = state.captureCtx.createScriptProcessor(4096, 1, 1);
      state.captureSilentGain = state.captureCtx.createGain();
      state.captureSilentGain.gain.value = 0;

      state.captureProcessor.onaudioprocess = function (ev) {
        if (!state.micOn) {
          return;
        }
        if (!state.mediaWs || state.mediaWs.readyState !== WebSocket.OPEN) {
          return;
        }
        const input = ev.inputBuffer.getChannelData(0);
        const buf = downsampleTo16kPCM(input, state.captureCtx.sampleRate);
        if (buf && buf.byteLength > 0) {
          state.mediaWs.send(buf);
        }
      };

      state.captureSource.connect(state.captureProcessor);
      state.captureProcessor.connect(state.captureSilentGain);
      state.captureSilentGain.connect(state.captureCtx.destination);

      state.micOn = true;
      log(`mic started, capture_rate=${state.captureCtx.sampleRate}`);
    } catch (err) {
      log(`开麦失败: ${err && err.message ? err.message : err}`);
      stopMic();
    }
  }

  function stopMic() {
    state.micOn = false;

    if (state.captureProcessor) {
      try { state.captureProcessor.disconnect(); } catch (_) {}
      state.captureProcessor.onaudioprocess = null;
      state.captureProcessor = null;
    }
    if (state.captureSource) {
      try { state.captureSource.disconnect(); } catch (_) {}
      state.captureSource = null;
    }
    if (state.captureSilentGain) {
      try { state.captureSilentGain.disconnect(); } catch (_) {}
      state.captureSilentGain = null;
    }
    if (state.mediaStream) {
      try {
        state.mediaStream.getTracks().forEach((t) => t.stop());
      } catch (_) {}
      state.mediaStream = null;
    }
    if (state.captureCtx) {
      state.captureCtx.close().catch(() => {});
      state.captureCtx = null;
    }

    log("mic stopped");
  }

  function bindEvents() {
    ui.btnConnect.addEventListener("click", connectWs);
    ui.btnDisconnect.addEventListener("click", disconnectWs);
    ui.btnMicStart.addEventListener("click", startMic);
    ui.btnMicStop.addEventListener("click", stopMic);

    ui.btnStartDialog.addEventListener("click", function () {
      sendControl({ event: "start_dialog" });
    });

    ui.btnEndDialog.addEventListener("click", function () {
      sendControl({ event: "end_dialog" });
    });

    ui.btnSetPrompt.addEventListener("click", function () {
      applySessionPromptFromTextarea(false);
    });

    ui.btnClearPrompt.addEventListener("click", function () {
      sendControl({ event: "clear_system_prompt" });
    });

    window.addEventListener("beforeunload", function () {
      disconnectWs();
    });
  }

  function init() {
    ui.sessionId.value = genSessionId();
    ui.systemPrompt.value = buildDefaultSystemPrompt();
    setStatus("未连接");
    bindEvents();
    log("页面已加载。提示：远程浏览器采麦通常需要 HTTPS。")
  }

  init();
})();
