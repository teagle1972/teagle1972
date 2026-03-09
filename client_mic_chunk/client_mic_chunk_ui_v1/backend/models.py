from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class UiEvent:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    ts: datetime = field(default_factory=datetime.now)

