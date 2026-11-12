"""翻译提示词构造与语言方向判断。"""
from __future__ import annotations

import re

DIRECTIONS = ["中 → 英", "英 → 中", "自动检测"]
TONES = ["正式商务", "自然口语", "忠实直译"]

TONE_HINTS = {
    "正式商务": "Use a formal, professional business register.",
    "自然口语": "Use a natural, conversational tone.",
    "忠实直译": "Translate faithfully and literally, preserving the original structure.",
}

_CJK = re.compile(r"[\u4e00-\u9fff]")


def detect_direction(text: str) -> str:
    """含中文则视为中译英，否则英译中。"""
    return "中 → 英" if _CJK.search(text or "") else "英 → 中"


def _langs(direction: str) -> tuple[str, str]:
    if direction == "英 → 中":
        return "English", "Chinese"
    return "Chinese", "English"


def build_messages(text: str, direction: str, tone: str) -> list[dict]:
    if direction == "自动检测":
        direction = detect_direction(text)
    src, tgt = _langs(direction)
    system = (
        f"You are a professional translator. Translate the user's {src} text into {tgt}. "
        "Preserve the meaning, tone, numbers and formatting. Output ONLY the translation, "
        "without explanations, notes or surrounding quotes."
    )
    hint = TONE_HINTS.get(tone, "")
    if hint:
        system = system + " " + hint
    user = f"Translate the following {src} text into {tgt}:\n\n{text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
