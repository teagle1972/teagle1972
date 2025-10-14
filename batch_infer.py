# -*- coding: utf-8 -*-
"""
批量推理脚本（Agent & Customer 双对话模型 + 策略模型 + 多标签分类器）

严格对齐训练体裁：
- 分类模型：<TGT>/<EOT> 体裁，不改为 JSON
- 策略模型：输入为“若干行标签历史 + 末尾 <AGENT>”（非 JSON 体裁）
- Agent对话模型：输入为“若干行 <TASK>...<EOT>（若有）+ 上下文若干行 + 末尾 <AGENT>”（非 JSON 体裁）

新增&修改要点（仅限分类器相关）：
- 分类器严格复刻“最简推理”加载方式：
  先用 BASE_MODEL_DIR 还原训练骨架（携带一致 config），再 strict=True 从 model.safetensors 加载全量权重
- 解码规则：阈值固定 tau=0.65，“严格大于”才采纳，K_max=2，允许空集（无兜底）
- Tokenizer 固定读取训练时的分词器目录，补齐 <TGT>/<EOT>/<AGENT>/<CUSTOMER> 等特殊符
- 其它（Agent/Customer/策略模型、SLOTS、落盘、截尾）完全保留
"""

# ======================== 配 置 ========================
TOKENIZER_DIR             = "/home/lilt/project/Agent/K_Distillation/bank_tokenizer_16k"
AGENT_MODEL_DIR           = "/home/lilt/project/Agent/K_Distillation/ckpt_sft_from_pure/Phase-2-Agent_LearningSlots_Prompt"
CUSTOMER_MODEL_DIR        = "/home/lilt/project/Agent/K_Distillation/ckpt_sft_from_pure/phase2_next_cust_spm_new"
OUTPUT_DIALOG_DIR         = "/home/lilt/project/Agent/K_Distillation/strategy/infer_dialogs"

# 策略模型
AGENT_STRATEGY_MODEL_DIR  = "/home/lilt/project/Agent/K_Distillation/ckpt_sft_from_pure/phase2_strategy"

# SLOTS 数据源（一次对话中固定一份）
SLOTS_VALID_PATH          = "/home/lilt/project/Agent/K_Distillation/Phase-2-Agent_LearningSlots_Prompt/.valid.jsonl"
INJECT_SLOTS_TO_AGENT_SYSTEM = True  # True: 将固定SLOTS注入 <TASK>...<EOT> 参与Agent推理

POOL_COUNT           = 10
DIALOG_WINDOW_TURNS  = 6          # 对话上下文窗口
STRATEGY_WINDOW_TURNS= 18         # 标签历史窗口
MAX_TURNS_SOFT       = 60

# 结束计数策略（'consecutive' 连续 / 'cumulative' 累计）
CLOSE_COUNT_MODE     = 'cumulative'
CLOSE_THRESHOLD_N    = 3
TRIM_AFTER_CLOSE     = True

# 采样参数
MAX_NEW_TOKENS       = 96
TEMPERATURE          = 0.8
TOP_P                = 0.9
TOP_K                = 50
REPETITION_PENALTY   = 1.05

# 最小生成长度
AGENT_MIN_NEW_TOKENS       = 8
CUSTOMER_MIN_NEW_TOKENS    = 16
STRATEGY_MIN_NEW_TOKENS    = 3
STRATEGY_MAX_NEW_TOKENS    = 8

# 控制台
STREAM_CONSOLE             = False
PRINT_AGENT_PROMPT_ONCE    = True
PRINT_STRATEGY_PROMPT_ONCE = True
SEED_FIRST_AGENT_TAGS      = False   # 默认不注入首轮种子；如需注入，置 True

# 固定第7块GPU（仅暴露7号卡）
import os as _os
_os.environ["CUDA_VISIBLE_DEVICES"] = "7"
_os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
_os.environ.setdefault("NCCL_P2P_DISABLE", "1")
_os.environ.setdefault("NCCL_IB_DISABLE", "1")
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ======================== Special Tokens ========================
AGENT = "<AGENT>"
CUSTOMER = "<CUSTOMER>"
EOT = "<EOT>"
TASK = "<TASK>"

# ======================== 策略/客户标签白名单 ========================
# —— 以“八、催收员标签”对齐（修正 A07 名称，补齐 A10/47 等）
LEGAL_A_TAGS = {
    "<A00_确认对方身份>","<A01_告知身份>","<A02_回应身份质疑>","<A03_录音合规提示>",
    "<A04_关系人身份核验>","<A05_阐明沟通目的>","<A06_信息转达及个人信息保护>","<A07_客户不便通话改约时间>",
    "<A08_逾期事实与金额核对>","<A09_账单构成解释>","<A10_回顾还款历史>",
    "<A11_询问资金来源与现金流确认>","<A12_资金用途合规与风险排查>",
    "<A13_他债确认>","<A14_他债优先级梳理>","<A15_联系方式与通知方式确认>",
    "<A16_逾期后果说明>","<A17_截止时点设定>",
    "<A19_筹款建议>","<A20_协商还款解决方案>","<A20_1_引导一次性结清方案>",
    "<A20_2_引导部分或最低还款方案>","<A20_3_引导分期方案>",
    "<A20_4_引导延期/宽限/推迟扣款方案>","<A20_5_引导只还本金方案>",
    "<A20_6_引导利息/罚息减免方案>","<A20_7_冻结利息增长承诺>",
    "<A20_8_流程暂停/扣案/撤报承诺>","<A20_9_审批与名额占位>",
    "<A29_提交电话核实小组核验>","<A30_外访说明>","<A31_安抚客户>",
    "<A32_骚扰/恐吓信息澄清>","<A33_确认客户承诺>","<A34_记录备注>",
    "<A35_协议条款异议受理>","<A36_材料清单与提交指引>","<A37_还款操作指引>",
    "<A38_沟通闭环/约定再联系>","<A39_结束通话>","<A40_通用标签>",
    "<A41_确认客户账户信息>","<A42_询问还款时间/计划>","<A43_询问逾期原因>",
    "<A44_询问还款意愿>","<A45_询问客户是否知道逾期>","<A47_成功履约说明>",
}

# ======================== 结束语识别 ========================
import re
CLOSING_PATTERNS = [
    r"(?:再见|回见|拜拜|白白|88|挂了|拜|bye|good\s*bye|see\s*you)(?:[。\.!！…～~]?|$)",
    r"(?:就这样吧?|先这样(?:吧)?|今天(?:先)?到这(?:里)?吧?)(?:[。\.!！…～~]?|$)",
    r"(?:通话结束|先不打扰|不再打扰|先不聊了)(?:[。\.!！…～~]?|$)",
    r"我(?:先|现在)?挂(?:了|断|电话)(?:[。\.!！…～~]?|$)",
    r"(?:你|您)别再打了(?:[。\.!！…～~]?|$)",
    r"(?:稍后|等会儿?|待会儿?|过会儿?)\s*(?:再)?(?:联系|说)(?:吧)?(?:[。\.!！…～~]?|$)",
    r"(?:回头|改天)\s*(?:再)?(?:联系|说)(?:吧)?(?:[。\.!！…～~]?|$)",
    r"(?:有空|方便.*)\s*(?:再)?(?:联系|回电|回拨)(?:吧)?(?:[。\.!！…～~]?|$)",
    r"(?:稍后|改天)\s*我\s*(?:再|会)?\s*回(?:电|拨|复)(?:吧)?(?:[。\.!！…～~]?|$)",
    r"(先|暂时)这样,?我有事/我先忙(?:[。\.!！…～~]?|$)",
]
CLOSING_RE = re.compile("|".join(CLOSING_PATTERNS))

# ======================== 依 赖 ========================
import os, sys, json, random, time, numpy as np
from typing import List, Tuple, Dict, Any, Optional
from threading import Thread

import torch
from transformers import (
    AutoTokenizer, AutoModelForCausalLM,
    StoppingCriteria, StoppingCriteriaList,
    TextIteratorStreamer
)

random.seed(20250913)

# ============================================================
# 纯分类器（全量参数版 Two-Path） —— 按“最简推理”方式改造
# ============================================================
from safetensors.torch import safe_open  # ★ 新增：严格加载全量 state_dict

# —— 目录与文件（与“最简推理”一致）
CLS_BASE_MODEL_DIR = "/home/lilt/project/Agent/K_Distillation/classifier/Model/classifier_lm"        # 恢复训练骨架
CLS_TOKENIZER_DIR  = "/home/lilt/project/Agent/K_Distillation/classifier/Model/cls_tokenizer_16K"    # 与训练一致
CLS_OUTPUT_DIR     = "/home/lilt/project/Agent/K_Distillation/classifier/Model/phase2_cls_multilabel" # ckpt 所在目录
CLS_CKPT_PATH      = "/home/lilt/project/Agent/K_Distillation/classifier/Model/phase2_cls_multilabel/model.safetensors"

CLS_BF16   = True
CLS_MAXLEN = 896

# —— 解码策略：严格复刻新规
CLS_DEC_TOPK  = 2       # K_max=2
CLS_TAU_FIXED = 0.65    # 阈值固定，且“严格大于”才采纳（允许空集）

# —— “七、客户标签”对齐的标签集合（保留顺序用于 id→label）
CLS_LABEL_LIST = [
    "<C00_确认本人接听>","<C01_非本人接听>","<C02_拒绝核验身份>","<C03_质疑催收身份或合法性>",
    "<C04_仅与银行/平台/法院沟通>","<C05_询问对方身份或来电目的>","<C06_知晓欠款与逾期>","<C07_不知晓欠款与逾期>",
    "<C08_身份被冒用/非本人办理贷款>","<C09_询问具体还款金额>","<C10_解释逾期原因>","<C11_咨询还款政策和方案>",
    "<C12_质疑银行政策不合理>","<C13_要求不影响信用>","<C14_表示愿意还款>","<C15_还款态度敷衍暧昧>",
    "<C16_明确拒绝还款>","<C17_表示经济困难无还款能力>","<C18_承诺部分还款>","<C19_承诺全额还款>",
    "<C20_说明款项来源>","<C21_拒绝催收联系家人/单位/居委会等>","<C22_抱怨催收骚扰>","<C23_请求停止骚扰>",
    "<C24_情绪失控/骂人/威胁/恐吓>","<C25_确认联系方式>","<C26_接受后续流程/消极配合>","<C27_更新联系方式>",
    "<C28_知晓逾期不还的后果>","<C29_请求还款路径/操作指引>","<C31_没有合适的标签>","<C32_合约争议>",
    "<C33_沟通闭环/二次确认>","<C34_结束对话>","<C35_抱怨催收话术威胁>","<C36_无家人亲友帮助>",
    "<C38_客户确认的还款时间>","<C39_多头债务>","<C40_再联系时间>","<C41_客户要求的还款时间>",
    "<C42_还款操作相关>","<C43_审核材料操作相关>","<C44_接受分期方案>","<C45_拒绝分期方案>",
    "<C46_接受延期方案>","<C47_拒绝延期方案>","<C48_接受减免方案>","<C49_拒绝减免方案>",
    "<C50_接受只还本金方案>","<C51_拒绝只还本金方案>","<C52_客户不方便接听>","<C53_客户提供发薪日>",
    "<C54_客户请求分期>","<C55_客户请求宽限延期>","<C56_客户请求减免>","<C57_询问逾期详情>",
    "<C58_回顾还款历史>","<C59_询问逾期后果>","<C60_拒绝明确还款时间>","<C61_拒绝再次联系>",
]
CLS_ID2LABEL = {i: x for i, x in enumerate(CLS_LABEL_LIST)}
C_WHITELIST = set(CLS_LABEL_LIST)

# 分类器专用标记（保持与训练一致）
CLS_TGT = "<TGT>"; CLS_EOT = "<EOT>"

import math, torch.nn as nn
from transformers import LlamaForCausalLM, LlamaTokenizer

class TwoPathMultiLabel(nn.Module):
    def __init__(self, base_causal_lm: LlamaForCausalLM, tokenizer: LlamaTokenizer, num_labels: int):
        super().__init__()
        self.backbone = base_causal_lm.model
        self.hidden = self.backbone.config.hidden_size
        self.tokenizer = tokenizer
        self.num_labels = num_labels
        self.tgt_fuse = nn.Sequential(nn.Linear(self.hidden*2, self.hidden), nn.SiLU())
        self.ctx_query = nn.Parameter(torch.randn(self.hidden))
        self.ctx_norm = nn.LayerNorm(self.hidden)
        self.gate = nn.Linear(self.hidden*2, 2)
        self.classifier = nn.Linear(self.hidden, num_labels)
        self.id_TGT = tokenizer.convert_tokens_to_ids(CLS_TGT)
        self.id_EOT = tokenizer.convert_tokens_to_ids(CLS_EOT)
        self.id_AGENT = tokenizer.convert_tokens_to_ids("<AGENT>")
        self.id_CUSTOMER = tokenizer.convert_tokens_to_ids("<CUSTOMER>")

    @staticmethod
    def _mean_pool(h, mask):
        denom = mask.sum().clamp_min(1).unsqueeze(-1)
        return (h * mask.unsqueeze(-1)).sum(dim=0) / denom

    def _extract_spans(self, token_ids):
        L = len(token_ids)
        try:
            tgt_idx = token_ids.index(self.id_TGT)
        except ValueError:
            eots = [i for i,t in enumerate(token_ids) if t==self.id_EOT]
            tgt_eot_idx = eots[-1] if eots else L-1
            return (max(0,tgt_eot_idx-16), max(0,tgt_eot_idx-1)), [], tgt_eot_idx
        try:
            tgt_eot_idx = token_ids.index(self.id_EOT, tgt_idx+1)
        except ValueError:
            tgt_eot_idx = L-1
        tgt_span = (min(L-1,tgt_idx+1), max(tgt_idx+1, tgt_eot_idx-1))
        ctx_spans, cur_start, i = [], None, 0
        while i < tgt_idx:
            tok = token_ids[i]
            if tok in (self.id_AGENT,self.id_CUSTOMER): cur_start = i+1
            if tok == self.id_EOT and cur_start is not None:
                if i-1 >= cur_start: ctx_spans.append((cur_start, i-1))
                cur_start = None
            i+=1
        return tgt_span, ctx_spans, tgt_eot_idx

    def forward(self, input_ids=None, attention_mask=None):
        out = self.backbone(input_ids=input_ids, attention_mask=attention_mask, return_dict=True)
        H = out.last_hidden_state
        B, L, D = H.shape
        logits_list=[]
        for b in range(B):
            ids_b = input_ids[b].tolist()
            attn_b = attention_mask[b].bool()
            hb = H[b]
            (s,e), ctx_spans, tgt_eot_idx = self._extract_spans(ids_b)
            s = max(0,min(s,L-1)); e = max(0,min(e,L-1))
            if e < s: s,e = max(0,tgt_eot_idx-8), max(0,tgt_eot_idx-1)
            # target
            span_mask = torch.zeros(L, dtype=torch.float32, device=H.device); span_mask[s:e+1]=1.0
            span_mask = span_mask * attn_b.float()
            h_span = self._mean_pool(hb, span_mask)
            h_eot  = hb[max(0,min(tgt_eot_idx,L-1))]
            h_tgt  = self.tgt_fuse(torch.cat([h_span, h_eot], dim=-1))
            # context
            ctx_turns=[]
            for (cs,ce) in ctx_spans:
                cs=max(0,min(cs,L-1)); ce=max(0,min(ce,L-1))
                if ce<cs: continue
                m=torch.zeros(L, dtype=torch.float32, device=H.device); m[cs:ce+1]=1.0
                m = m * attn_b.float()
                ctx_turns.append(self._mean_pool(hb, m))
            if len(ctx_turns)==0:
                h_ctx = torch.zeros(D, dtype=hb.dtype, device=hb.device)
            else:
                Ct = self.ctx_norm(torch.stack(ctx_turns, dim=0))
                att = torch.matmul(Ct, self.ctx_query) / math.sqrt(D)
                alpha_ctx = torch.softmax(att, dim=0)
                h_ctx = torch.sum(alpha_ctx.unsqueeze(-1)*Ct, dim=0)
            alpha = torch.softmax(self.gate(torch.cat([h_tgt,h_ctx], dim=-1)), dim=-1)
            h_star= alpha[0]*h_tgt + alpha[1]*h_ctx
            logits_list.append(self.classifier(h_star).unsqueeze(0))
        return torch.cat(logits_list, dim=0)

# ===== 分类器 Tokenizer（固定用训练目录，补齐特殊符） =====
def cls_build_tokenizer() -> LlamaTokenizer:
    tok = LlamaTokenizer.from_pretrained(CLS_TOKENIZER_DIR, use_fast=False)
    if "<pad>" in tok.get_vocab():
        tok.pad_token = "<pad>"
    else:
        tok.add_special_tokens({"pad_token":"<pad>"})

    specials_to_add = []
    for s in [CLS_TGT, CLS_EOT, "<AGENT>", "<CUSTOMER>"]:
        if tok.convert_tokens_to_ids(s) == tok.unk_token_id:
            specials_to_add.append(s)
    if specials_to_add:
        tok.add_special_tokens({"additional_special_tokens": specials_to_add})
    return tok

# ===== <TGT> 注入与输入构造（与训练/最简推理一致） =====
def _inject_tgt_marker(role_prefixed_text: str) -> str:
    t = role_prefixed_text or ""
    if CLS_TGT in t:
        return t
    if t.startswith("<CUSTOMER>"):
        return t.replace("<CUSTOMER>", "<CUSTOMER>"+CLS_TGT, 1)
    if t.startswith("<AGENT>"):
        return t.replace("<AGENT>", "<AGENT>"+CLS_TGT, 1)
    return CLS_TGT + t

def cls_build_input(history_window: List[str], role: str, utter_with_eot: str) -> str:
    ctx = "\n".join(history_window) if history_window else ""
    sep = ("\n" if ctx else "")
    tgt = _inject_tgt_marker(f"{role}{utter_with_eot}")
    return ctx + sep + tgt

# ===== 使用 BASE_MODEL_DIR 还原骨架 + 严格加载全量权重 =====
def cls_build_model(tokenizer: LlamaTokenizer) -> TwoPathMultiLabel:
    bf16_ok = (torch.cuda.is_available() and getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    dtype = torch.bfloat16 if bf16_ok else (torch.float16 if torch.cuda.is_available() else torch.float32)

    base = LlamaForCausalLM.from_pretrained(
        CLS_BASE_MODEL_DIR,
        torch_dtype=dtype,
        low_cpu_mem_usage=True
    )
    base.resize_token_embeddings(len(tokenizer))
    base.config.pad_token_id = tokenizer.pad_token_id
    base.config.eos_token_id = tokenizer.eos_token_id
    base.config.bos_token_id = tokenizer.bos_token_id

    model = TwoPathMultiLabel(base, tokenizer, num_labels=len(CLS_LABEL_LIST))

    print(f"[CLS][LOAD] loading full weights: {CLS_CKPT_PATH}")
    with safe_open(CLS_CKPT_PATH, framework="pt", device="cpu") as f:
        state = {k: f.get_tensor(k) for k in f.keys()}
    any_key = next(iter(state.keys()))
    print(f"[CLS][LOAD] tensors={len(state)} | sample_key='{any_key}' | hidden={model.backbone.config.hidden_size}")
    model.load_state_dict(state, strict=True)
    print("[CLS][LOAD] OK (strict=True)")
    return model

# ===== 解码：严格 “> tau” + K_max=2，允许空集 =====
def cls_decode(probs: np.ndarray, tau: float, topk: int = CLS_DEC_TOPK) -> np.ndarray:
    if probs.ndim == 1:
        probs = probs[None, :]
    B, C = probs.shape
    out = np.zeros((B, C), dtype=np.int64)
    for b in range(B):
        above = np.where(probs[b] > tau)[0].tolist()  # ★ 严格大于
        if above:
            above = sorted(above, key=lambda i: probs[b, i], reverse=True)[:topk]
            out[b, above] = 1
        # else: 空集（不兜底）
    return out

# ===== τ：固定 0.65（不再读取 tau.json） =====
def cls_load_tau(default_tau: float = CLS_TAU_FIXED) -> float:
    return float(CLS_TAU_FIXED)

# ======================== 文本工具 ========================
def _fw_to_hw(s):
    return ''.join((' ' if ord(ch)==0x3000 else chr(ord(ch)-0xFEE0) if 0xFF01<=ord(ch)<=0xFF5E else ch) for ch in (s or ""))

def normalize_text(s: str) -> str:
    s=_fw_to_hw((s or "").strip())
    s=(s.replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'")
        .replace("—", "-").replace("–", "-").replace("…", "..."))
    s=re.sub(r"\s+"," ", s).strip()
    return s

def slice_dialog_by_turns(history: List[str], k: int) -> List[str]:
    if not k or k <= 0:
        return history
    return history[-k:] if len(history) > k else history

def ensure_single_eot(text: str) -> str:
    t = (text or "").strip()
    while t.endswith(EOT + EOT):
        t = t[:-len(EOT)]
    if not t.endswith(EOT):
        t = t + EOT
    return t

def strip_role_prefix(x: str) -> str:
    if x.startswith(AGENT): return x[len(AGENT):]
    if x.startswith(CUSTOMER): return x[len(CUSTOMER):]
    return x

def strip_trailing_eots(x: str) -> str:
    t = (x or "").rstrip()
    while t.endswith(EOT):
        t = t[:-len(EOT)]
        t = t.rstrip()
    return t

def make_labeled_line(role_tok: str, label_tokens: List[str], utter_with_eot: str) -> str:
    """
    落盘行：标签在前、话术在后、行末单一<EOT>；若标签为空则保留一个空格分隔
    """
    utter = strip_role_prefix(utter_with_eot)
    utter = strip_trailing_eots(utter)
    labels = "".join(label_tokens)
    if labels:
        line = f"{role_tok}{labels} {utter}{EOT}"
    else:
        line = f"{role_tok} {utter}{EOT}"
    return line.strip()

# ======================== Prompt 构造 ========================
def decode_keep_business(ids, tok):
    """不跳过 special，再手工去掉 BOS/EOS/PAD（保留 <AGENT>/<CUSTOMER>/<EOT>）"""
    txt = tok.decode(ids, skip_special_tokens=False)
    for s in [tok.bos_token, tok.eos_token, tok.pad_token]:
        if s:
            txt = txt.replace(s, "")
    return txt.strip()

def build_strategy_prompt_text(label_history: List[str], k: int) -> str:
    """
    策略模型（非 JSON 体裁）：
    最近 k 条标签历史（每行以 <EOT> 结尾），末尾追加 '<AGENT>'
    """
    ctx = slice_dialog_by_turns(label_history, k)
    parts: List[str] = []
    for ln in ctx:
        ln = (ln or "").strip()
        if not ln:
            continue
        if not ln.endswith(EOT):
            ln = ln + EOT
        parts.append(ln)
    parts.append(AGENT)
    return "".join(parts)

def build_agent_prompt_text(history_clean: List[str],
                            system_blocks: List[str],
                            k_ctx: int,
                            slots_blocks: Optional[List[str]] = None) -> str:
    """
    Agent 对话模型（非 JSON 体裁）：
    先写 slots_blocks（若有，每个都是 '<TASK>...<EOT>'），
    再写 system_blocks（'<TASK>...<EOT>'），
    再写最近 k_ctx 条对话（带 <EOT>），最后写 '<AGENT>'。
    """
    parts = []
    # 1) SLOTS 固定指令
    for s in (slots_blocks or []):
        s = (s or "").strip()
        if not s:
            continue
        if not s.endswith(EOT):
            s = s + EOT
        parts.append(s)
    # 2) 任务块（策略标签）
    for s in (system_blocks or []):
        s = (s or "").strip()
        if not s:
            continue
        if not s.endswith(EOT):
            s = s + EOT
        parts.append(s)
    # 3) 对话上下文
    for ln in slice_dialog_by_turns(history_clean, k_ctx):
        ln = (ln or "").strip()
        if not ln:
            continue
        if not ln.endswith(EOT):
            ln = ln + EOT
        parts.append(ln)
    parts.append(AGENT)
    return "\n".join(parts).strip()

# ======================== 生成 utils ========================
class KeywordsStopper(StoppingCriteria):
    def __init__(self, ids_list):
        self.ids_list = [torch.tensor(x, dtype=torch.long) for x in ids_list]
    def __call__(self, input_ids, scores, **kwargs):
        seq = input_ids[0]
        for kw in self.ids_list:
            L = kw.numel()
            if L <= seq.numel() and torch.equal(seq[-L:], kw.to(seq.device)):
                return True
        return False

def build_agent_gen_kwargs(tok):
    stop_ids = [
        tok.encode(EOT, add_special_tokens=False),
        tok.encode(CUSTOMER, add_special_tokens=False),
    ]
    return dict(
        max_new_tokens=MAX_NEW_TOKENS,
        min_new_tokens=AGENT_MIN_NEW_TOKENS,
        do_sample=True,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        top_k=TOP_K,
        repetition_penalty=REPETITION_PENALTY,
        pad_token_id=tok.pad_token_id,
        stopping_criteria=StoppingCriteriaList([KeywordsStopper(stop_ids)]),
    )

def build_customer_gen_kwargs(tok):
    stop_ids = [
        tok.encode(EOT, add_special_tokens=False),
        tok.encode(AGENT, add_special_tokens=False),
    ]
    return dict(
        max_new_tokens=MAX_NEW_TOKENS,
        min_new_tokens=CUSTOMER_MIN_NEW_TOKENS,
        do_sample=True,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        top_k=TOP_K,
        repetition_penalty=REPETITION_PENALTY,
        pad_token_id=tok.pad_token_id,
        stopping_criteria=StoppingCriteriaList([KeywordsStopper(stop_ids)]),
    )

# ===== 策略模型：评测脚本同款“确定性解码 + <EOT> 停词” =====
def build_strategy_gen_kwargs(tok):
    stop_ids = [ tok.encode(EOT, add_special_tokens=False) ]
    return dict(
        max_new_tokens=STRATEGY_MAX_NEW_TOKENS,
        min_new_tokens=STRATEGY_MIN_NEW_TOKENS,
        do_sample=False,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        repetition_penalty=1.0,
        pad_token_id=tok.pad_token_id,
        stopping_criteria=StoppingCriteriaList([KeywordsStopper(stop_ids)]),
        return_dict_in_generate=True,
        output_scores=True,
    )

def generate_once(model, tok, prompt: str, gen_kwargs: dict, stream: bool = False) -> str:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.eval(); model.to(device)
    inps = tok(prompt, add_special_tokens=False, return_tensors="pt")
    inps = {k: v.to(device) for k, v in inps.items()}
    if not stream:
        with torch.no_grad():
            if device == "cuda":
                with torch.autocast(device_type="cuda",
                                    dtype=(torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)):
                    out = model.generate(**inps, **gen_kwargs)
            else:
                out = model.generate(**inps, **gen_kwargs)
        if isinstance(out, torch.Tensor):
            gen_ids = out[0][inps["input_ids"].shape[1]:]
        else:
            gen_ids = out.sequences[0][inps["input_ids"].shape[1]:]
        text = tok.decode(gen_ids, skip_special_tokens=True)
        return text.strip()
    streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
    gkw = dict(**gen_kwargs, streamer=streamer); gkw.update(inps)
    def _gen():
        with torch.no_grad():
            if device == "cuda":
                with torch.autocast(device_type="cuda",
                                    dtype=(torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)):
                    model.generate(**gkw)
            else:
                model.generate(**gkw)
    th = Thread(target=_gen, daemon=True); th.start()
    buf = ""; printed = 0
    for chunk in streamer:
        buf += chunk
        if STREAM_CONSOLE:
            inc = buf[printed:]
            if inc:
                print(inc, end="", flush=True)
                printed = len(buf)
    th.join()
    return buf.strip()

def generate_strategy_once(model, tok, prompt: str, gen_kwargs: dict) -> str:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.eval(); model.to(device)
    inps = tok(prompt, add_special_tokens=False, return_tensors="pt")
    inps = {k: v.to(device) for k, v in inps.items()}
    with torch.no_grad():
        if device == "cuda":
            autocast_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            with torch.autocast(device_type="cuda", dtype=autocast_dtype):
                out = model.generate(**inps, **gen_kwargs)
        else:
            out = model.generate(**inps, **gen_kwargs)
    sequences = out.sequences if hasattr(out, "sequences") else out
    gen_ids = sequences[0][inps["input_ids"].shape[1]:]
    return decode_keep_business(gen_ids, tok)

# ======================== 结束截尾工具 ========================
def _strip_tag(x: str) -> str:
    if x.startswith(AGENT): return x[len(AGENT):]
    if x.startswith(CUSTOMER): return x[len(CUSTOMER):]
    return x

def find_nth_consecutive_close_index(history: List[str], n: int) -> Optional[int]:
    streak = 0
    for i, turn in enumerate(history):
        content = _strip_tag(turn)
        if CLOSING_RE.search(content):
            streak += 1
            if streak >= n: return i
        else:
            streak = 0
    return None

def find_nth_cumulative_close_index(history: List[str], n: int) -> Optional[int]:
    total = 0
    for i, turn in enumerate(history):
        content = _strip_tag(turn)
        if CLOSING_RE.search(content):
            total += 1
            if total >= n: return i
    return None

def trim_history_after_close(history: List[str], n: int, mode: str) -> List[str]:
    if mode == 'consecutive':
        idx = find_nth_consecutive_close_index(history, n)
    else:
        idx = find_nth_cumulative_close_index(history, n)
    if idx is None: return history
    return history[: idx + 1]

# ======================== 落 盘 ========================
def save_dialog_to_path(system_text: str,
                        slots_lines: List[str],
                        history_with_tags: List[str],
                        out_path: str) -> str:
    """
    按顺序输出：
    【任务指令】
    【SLOTS】（固定）
    <空行>
    历史对话（标签在前）
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines = []
    sys_txt = (system_text or "").strip()
    lines.append("【任务指令】")
    lines.append(sys_txt if sys_txt else "（空）")
    lines.append("")
    lines.append("【SLOTS】")
    if slots_lines:
        for s in slots_lines:
            s = (s or "").strip()
            if not s.endswith(EOT):
                s = s + EOT
            lines.append(s)
    else:
        lines.append("<SLOT_空><EOT>")
    lines.append("")
    for t in history_with_tags:
        lines.append((t or "").strip())
    content = "\n".join(lines).rstrip() + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path

# ======================== 标签解析与校验 ========================
_A_TAG_RE = re.compile(r"<A\d[^>]*>")  # 与评测一致，不做修复

def parse_strategy_tags(generated: str, max_tags: int = 4) -> List[str]:
    if not generated:
        return []
    tags = _A_TAG_RE.findall(generated)
    seen = set(); uniq = []
    for t in tags:
        if t not in seen:
            seen.add(t); uniq.append(t)
            if len(uniq) >= max_tags: break
    return uniq

def validate_strategy_tags_or_retry(agent_strategy, tok, prompt, gk, first_tags: List[str]) -> List[str]:
    """
    不做修复。若空或含非法标签，则重试一次；仍不通过则退出。
    """
    def _gen_once_and_parse():
        raw = generate_strategy_once(agent_strategy, tok, prompt, gk)
        print("[STRATEGY][RAW]:", (raw if len(raw) <= 300 else raw[:300]+"…"), flush=True)
        tags = parse_strategy_tags(raw, max_tags=4)
        print("[STRATEGY][PARSED]:", tags, flush=True)
        return tags

    tags = first_tags
    if not tags or not all(t in LEGAL_A_TAGS for t in tags):
        if not tags:
            print("[STRATEGY] Empty tags on 1st try → retry once.", flush=True)
        else:
            print("[STRATEGY] Tags contain illegal items → retry once.", flush=True)
        tags = _gen_once_and_parse()
        if not tags or not all(t in LEGAL_A_TAGS for t in tags):
            print("[STRATEGY][FATAL] Still empty/illegal on retry:", tags, flush=True)
            sys.exit(1)
        print("[STRATEGY] Accepted on retry:", tags, flush=True)
    else:
        print("[STRATEGY] Parsed on 1st try:", tags, flush=True)

    return tags

def validate_customer_tags_or_retry(cls_model, cls_tok, device, cls_input_builder_fn, history_window, cust_text, tau) -> List[str]:
    """
    客户标签白名单校验：若含非法标签→重跑一次分类；仍非法则终止。
    新规：允许空集（不强行兜底）。
    """
    def classify_once() -> List[str]:
        enc = cls_tok(cls_input_builder_fn(history_window, CUSTOMER, cust_text),
                      add_special_tokens=False, truncation=True, max_length=CLS_MAXLEN, return_tensors="pt")
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            logits = cls_model(**enc)
            # TwoPath.forward 返回 Tensor；为兼容，做一次分支
            probs  = torch.sigmoid(logits if isinstance(logits, torch.Tensor) else logits["logits"]).float().cpu().numpy()[0]
        biny = cls_decode(probs, tau, CLS_DEC_TOPK)[0]
        labs = [CLS_ID2LABEL[i] for i in np.where(biny==1)[0]]
        return labs

    labs_c = classify_once()
    # 白名单检查（允许空集）
    if labs_c and not all(t in C_WHITELIST for t in labs_c):
        print(f"[WARN] Customer tags not in whitelist (1st try): {labs_c}", flush=True)
        labs_c = classify_once()
        if labs_c and not all(t in C_WHITELIST for t in labs_c):
            print(f"[ERROR] Customer tags still invalid after retry: {labs_c}", flush=True)
            sys.exit(1)
        if labs_c:
            print(f"[INFO] Customer tags accepted on retry: {labs_c}", flush=True)
    return labs_c

# ======================== SLOTS 读取与采样 ========================
_SLOT_LINE_RE = re.compile(r"<[^>]+>.*?<EOT>")

def _ensure_slot_line(s: str) -> str:
    s = (s or "").strip()
    if not s: return ""
    return s if s.endswith(EOT) else (s + EOT)

def load_slots_pool(path: str) -> List[List[str]]:
    """
    返回形如 [[slot_line1, slot_line2, ...], ...]
    解析优先级：
      1) JSON字段: 'slots' or 'SLOTS' 为 list[str]
      2) 若是 dict，则转为 '<KEY>VAL<EOT>' 体裁
      3) 文本抓取: 匹配 '<...>...<EOT>' 片段
    """
    pool: List[List[str]] = []
    if not os.path.isfile(path):
        print(f"[SLOTS][WARN] file not found: {path}")
        return pool
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = (ln or "").strip()
            if not ln: continue
            slots_lines: List[str] = []
            rec = None
            try:
                rec = json.loads(ln)
            except Exception:
                rec = None
            # 1) 直接 list[str]
            if isinstance(rec, dict):
                if isinstance(rec.get("slots"), list) and all(isinstance(x, str) for x in rec["slots"]):
                    slots_lines = [_ensure_slot_line(x) for x in rec["slots"] if x and isinstance(x, str)]
                elif isinstance(rec.get("SLOTS"), list) and all(isinstance(x, str) for x in rec["SLOTS"]):
                    slots_lines = [_ensure_slot_line(x) for x in rec["SLOTS"] if x and isinstance(x, str)]
                elif isinstance(rec.get("slots"), dict):
                    for k, v in rec["slots"].items():
                        k = str(k).strip(); v = str(v).strip()
                        if k:
                            slots_lines.append(_ensure_slot_line(f"<{k}>{v}"))
                elif isinstance(rec.get("SLOTS"), dict):
                    for k, v in rec["SLOTS"].items():
                        k = str(k).strip(); v = str(v).strip()
                        if k:
                            slots_lines.append(_ensure_slot_line(f"<{k}>{v}"))
                else:
                    # 扫描 dict 字段中可能的 '<...>...<EOT>' 片段
                    joined = " ".join([str(v) for v in rec.values() if isinstance(v, (str, list, dict))])
                    slots_lines += [m.group(0) for m in _SLOT_LINE_RE.finditer(joined)]
            else:
                # 不是JSON就从整行抓片段
                slots_lines = [m.group(0) for m in _SLOT_LINE_RE.finditer(ln)]

            slots_lines = [x for x in slots_lines if x.strip()]
            if slots_lines:
                pool.append(slots_lines)
    print(f"[SLOTS] loaded {len(pool)} candidate records from {path}")
    return pool

def sample_slots(pool: List[List[str]]) -> List[str]:
    if not pool:
        # 兜底，避免流程中断
        return ["<FIELD_样本占位>无<EOT>"]
    rec = random.choice(pool)
    # 也可随机子集，这里保留整份以“固定SLOTS”的语义
    return [ _ensure_slot_line(x) for x in rec if x and isinstance(x, str) ]

# ======================== 主流程：单条对话生成 ========================
def run_one_dialog(agent, customer, agent_strategy, tok, row: Dict[str, Any], idx: int, out_path: str,
                   cls_model, cls_tok, cls_tau: float, device: str) -> Optional[str]:
    if os.path.exists(out_path):
        print(f"[SKIP] 样本 {idx+1}: 目标文件已存在 → {out_path}")
        return out_path

    # 顶部 system 文本仅用于落盘展示（无实际含义）
    sys_text = (row.get("system") or "")

    # —— 本次对话固定 SLOTS（已在 main 中写入 row["slots_lines"]）
    slots_lines: List[str] = row.get("slots_lines") or []
    # 预构造 “固定 SLOTS” 对 Agent 的系统注入
    slots_tasks: List[str] = []
    if INJECT_SLOTS_TO_AGENT_SYSTEM and slots_lines:
        for s in slots_lines:
            s = (s or "").strip()
            if not s:
                continue
            # 保持 '<TASK>...<EOT>' 体裁
            if s.endswith(EOT):
                slots_tasks.append(f"{TASK}{s}")
            else:
                slots_tasks.append(f"{TASK}{s}{EOT}")

    history_clean: List[str] = []
    history_with_tags: List[str] = []
    label_history: List[str] = []

    # 开场（模板化，Agent 先发言；不带任何标签）
    opening_variants = [
        "您好，这里是银行委托的贷后服务团队，请问是您本人接听吗?",
        "您好，我们是银行委托的客户服务中心，请问现在方便沟通吗?",
        "您好，这里是银行委托的风险管理中心，请问是您本人吗?",
        "您好，我们受托就您的账户情况进行合规回访，请问是您接听吗?",
        "您好，这里是银行委托的账户管理团队，方便确认一下，是您本人吗?",
    ]
    import random as _rnd
    opening = ensure_single_eot(_rnd.choice(opening_variants))

    # 历史（clean：原始行；with_tags：标签在前）
    history_clean.append(f"{AGENT}{opening}")
    history_with_tags.append(make_labeled_line(AGENT, [], opening))

    printed_agent_prompt_once = False
    printed_strategy_prompt_once = False
    turn = 1

    close_streak = 1 if CLOSING_RE.search(opening) else 0
    close_total  = 1 if CLOSING_RE.search(opening) else 0

    print(f"\n=== 样本 {idx+1} / 目标 {POOL_COUNT} | 对话开始 ===")

    agent_gk    = build_agent_gen_kwargs(tok)
    cust_gk     = build_customer_gen_kwargs(tok)
    strategy_gk = build_strategy_gen_kwargs(tok)   # 评测模式：确定性解码

    # 是否注入首轮 A 标签种子
    if SEED_FIRST_AGENT_TAGS:
        seed_tags = ["<A00_确认对方身份>"]
        label_history.append(f"{AGENT}{''.join(seed_tags)}{EOT}")
        print("[SEED] Inject agent seed A-tags into label_history:", seed_tags, flush=True)

    while True:
        # ========== 客户回合 ==========
        prompt_c = "\n".join(slice_dialog_by_turns(history_clean, DIALOG_WINDOW_TURNS) + [CUSTOMER])
        if STREAM_CONSOLE: print(f"[{idx+1}-C] {CUSTOMER}", end="", flush=True)
        cust_text = generate_once(customer, tok, prompt_c, cust_gk, stream=STREAM_CONSOLE)
        cust_text = ensure_single_eot(cust_text)
        if STREAM_CONSOLE and cust_text: print(cust_text)

        history_clean.append(f"{CUSTOMER}{cust_text}")

        # 分类：客户意图标签 + 白名单校验（可能重试一次）
        labs_c = validate_customer_tags_or_retry(
            cls_model, cls_tok, device, cls_build_input,
            slice_dialog_by_turns(history_clean[:-1], DIALOG_WINDOW_TURNS),
            cust_text, cls_tau
        )
        print("[CLS][CUSTOMER-TAGS]:", labs_c, flush=True)

        # 标签历史（仅标签，不含话术）
        if labs_c:
            label_history.append(f"{CUSTOMER}{''.join(labs_c)}{EOT}")
        else:
            label_history.append(f"{CUSTOMER}{EOT}")

        # 落盘：客户行（标签在前）
        history_with_tags.append(make_labeled_line(CUSTOMER, labs_c, cust_text))

        # 结束检测
        if CLOSING_RE.search(cust_text):
            close_streak += 1; close_total += 1
        else:
            close_streak = 0

        if (CLOSE_COUNT_MODE == 'consecutive' and close_streak >= CLOSE_THRESHOLD_N) or \
           (CLOSE_COUNT_MODE == 'cumulative'  and close_total  >= CLOSE_THRESHOLD_N):
            break
        if turn >= MAX_TURNS_SOFT:
            print(f"[INFO] 样本 {idx+1}: 达到安全上限 {MAX_TURNS_SOFT} 句,结束。")
            break

        # ========== 策略决策（非 JSON 体裁）==========
        strategy_prompt = build_strategy_prompt_text(label_history, STRATEGY_WINDOW_TURNS)
        if PRINT_STRATEGY_PROMPT_ONCE and not printed_strategy_prompt_once:
            print("\n----- [策略模型输入 | 仅打印一次] -----")
            print(strategy_prompt if len(strategy_prompt) <= 1200 else "..." + strategy_prompt[-1200:])
            print("--------------------------------------\n")
            printed_strategy_prompt_once = True

        strategy_out_struct = generate_strategy_once(agent_strategy, tok, strategy_prompt, strategy_gk)
        print("[STRATEGY][OUT-1st]:", (strategy_out_struct if len(strategy_out_struct) <= 300 else strategy_out_struct[:300]+"…"), flush=True)

        a_tags_1st = parse_strategy_tags(strategy_out_struct, max_tags=4)
        a_tags = validate_strategy_tags_or_retry(agent_strategy, tok, strategy_prompt, strategy_gk, a_tags_1st)

        if a_tags:
            label_history.append(f"{AGENT}{''.join(a_tags)}{EOT}")

        # ========== Agent 回合（把固定 SLOTS 作为系统块注入）==========
        system_blocks = [f"{TASK}{t}{EOT}" for t in a_tags] if a_tags else []
        agent_prompt_text = build_agent_prompt_text(
            history_clean=history_clean,
            system_blocks=system_blocks,
            k_ctx=DIALOG_WINDOW_TURNS,
            slots_blocks=slots_tasks   # 关键：每一轮Agent都带着同一份SLOTS
        )

        if PRINT_AGENT_PROMPT_ONCE and not printed_agent_prompt_once:
            print("\n----- [Agent模型输入 | 仅打印一次] -----")
            print(agent_prompt_text if len(agent_prompt_text) <= 1200 else "..." + agent_prompt_text[-1200:])
            print("---------------------------------------\n")
            printed_agent_prompt_once = True

        if STREAM_CONSOLE: print(f"[{idx+1}-A] {AGENT}", end="", flush=True)
        agent_text = generate_once(agent, tok, agent_prompt_text, agent_gk, stream=STREAM_CONSOLE)
        agent_text = ensure_single_eot(agent_text)

        # 历史：原始与标签版
        history_clean.append(f"{AGENT}{agent_text}")
        history_with_tags.append(make_labeled_line(AGENT, a_tags, agent_text))

        if CLOSING_RE.search(agent_text):
            close_streak += 1; close_total += 1
        else:
            close_streak = 0

        if (CLOSE_COUNT_MODE == 'consecutive' and close_streak >= CLOSE_THRESHOLD_N) or \
           (CLOSE_COUNT_MODE == 'cumulative'  and close_total  >= CLOSE_THRESHOLD_N):
            break
        if turn >= MAX_TURNS_SOFT:
            print(f"[INFO] 样本 {idx+1}: 达到安全上限 {MAX_TURNS_SOFT} 句,结束。")
            break

        turn += 2

    # 截尾对齐
    if TRIM_AFTER_CLOSE:
        trimmed_clean = trim_history_after_close(history_clean, CLOSE_THRESHOLD_N, CLOSE_COUNT_MODE)
        keep_n = len(trimmed_clean)
        history_with_tags = history_with_tags[:keep_n]

    # 落盘（含 SLOTS）
    try:
        path = save_dialog_to_path(sys_text, slots_lines, history_with_tags, out_path)
        print(f"[SAVE] 样本 {idx+1} 已保存：{path}")
        return path
    except Exception as e:
        print(f"[SAVE-ERROR] 样本 {idx+1} 保存失败：{e}")
        return None

# ======================== 数据源 ========================
def load_pool_rows(need_count: int, slots_pool: List[List[str]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _ in range(max(0, need_count)):
        rows.append({
            # 可放置额外meta/system等字段
            "system": "",
            "slots_lines": sample_slots(slots_pool)  # 固定本条对话的 SLOTS
        })
    return rows

# ======================== 主 过 程 ========================
def main():
    # 读取 SLOTS 池
    slots_pool = load_slots_pool(SLOTS_VALID_PATH)

    rows = load_pool_rows(POOL_COUNT, slots_pool)
    if not rows:
        print(f"[ERROR] 无可用样本（POOL_COUNT={POOL_COUNT})")
        return

    to_process = []
    for i in range(len(rows)):
        out_path = os.path.join(OUTPUT_DIALOG_DIR, f"{i+1}.txt")
        if os.path.exists(out_path):
            print(f"[SKIP] 预检：样本 {i+1} 目标已存在 → {out_path}")
        else:
            to_process.append((i, out_path))
    if not to_process:
        print(f"[INFO] 所有前 {len(rows)} 个目标文件均已存在,退出。目录：{OUTPUT_DIALOG_DIR}")
        return

    # GPU/精度
    print("[CUDA] available =", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("[CUDA] visible_count =", torch.cuda.device_count())
        print("[CUDA] current_device =", torch.cuda.current_device())
        print("[CUDA] name =", torch.cuda.get_device_name(0))
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")

    # 分词器/三模型加载（统一 tokenizer）
    tok = AutoTokenizer.from_pretrained(TOKENIZER_DIR, use_fast=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    dtype = (torch.bfloat16 if (torch.cuda.is_available() and torch.cuda.is_bf16_supported())
             else (torch.float16 if torch.cuda.is_available() else torch.float32))
    agent = AutoModelForCausalLM.from_pretrained(AGENT_MODEL_DIR, torch_dtype=dtype, low_cpu_mem_usage=True)
    customer = AutoModelForCausalLM.from_pretrained(CUSTOMER_MODEL_DIR, torch_dtype=dtype, low_cpu_mem_usage=True)
    agent_strategy = AutoModelForCausalLM.from_pretrained(AGENT_STRATEGY_MODEL_DIR, torch_dtype=dtype, low_cpu_mem_usage=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    agent.to(device); customer.to(device); agent_strategy.to(device)

    # 分类器加载（严格复刻“最简推理”）
    cls_tok   = cls_build_tokenizer()
    cls_model = cls_build_model(cls_tok).to(device)
    cls_model.eval()
    cls_tau   = cls_load_tau()
    print(f"[CLS] tau={cls_tau:.2f} | dec_topk={CLS_DEC_TOPK} | rule='strict > tau' | allow_empty=True")

    print(f"[INFO] 本次按顺序处理 {len(rows)} 条样本，其中需要生成 {len(to_process)} 条。")

    ok = 0
    for i, out_path in to_process:
        row = rows[i]
        path = run_one_dialog(agent, customer, agent_strategy, tok, row, i, out_path, cls_model, cls_tok, cls_tau, device)
        if path:
            ok += 1
    print(f"\n[DONE] 目标={len(to_process)},成功={ok},输出目录：{OUTPUT_DIALOG_DIR}")

if __name__ == "__main__":
    main()
