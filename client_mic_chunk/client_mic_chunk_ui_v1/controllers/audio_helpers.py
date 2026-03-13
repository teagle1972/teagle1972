from __future__ import annotations


def normalize_aec_profile(raw: str | None) -> str:
    profile = str(raw or "asr_first").strip().lower()
    if profile not in {"asr_first", "aggressive"}:
        return "asr_first"
    return profile


def get_profile_tuning_defaults(
    profile: str,
    *,
    specs: tuple[dict[str, object], ...],
    asr_first_overrides: dict[str, str],
    aggressive_overrides: dict[str, str],
) -> dict[str, str]:
    normalized = normalize_aec_profile(profile)
    values = {str(spec["key"]): str(spec["default"]) for spec in specs}
    if normalized == "aggressive":
        values.update(aggressive_overrides)
    else:
        values.update(asr_first_overrides)
    return values


def format_numeric_for_option(value: float, value_type: str) -> str:
    if value_type == "int":
        return str(int(value))
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text or "0"


def remove_command_option(tokens: list[str], flag: str) -> None:
    i = 0
    while i < len(tokens):
        token = str(tokens[i] or "")
        if token == flag:
            del tokens[i]
            if i < len(tokens):
                nxt = str(tokens[i] or "")
                if nxt and (not nxt.startswith("--")):
                    del tokens[i]
            continue
        if token.startswith(f"{flag}="):
            del tokens[i]
            continue
        i += 1


def read_command_option(tokens: list[str], flag: str) -> str:
    for idx, token in enumerate(tokens):
        token_text = str(token or "").strip()
        if token_text == flag:
            if idx + 1 >= len(tokens):
                return ""
            value = str(tokens[idx + 1] or "").strip()
            if value.startswith("--"):
                return ""
            return value
        if token_text.startswith(f"{flag}="):
            return token_text.split("=", 1)[1].strip()
    return ""

