"""翻译提示词构造与语言（中/英/法/韩/日/西/葡）识别。"""
from __future__ import annotations

import re

LANGUAGES = ["中文", "英文", "法文", "韩文", "日文", "西班牙文", "葡萄牙文"]
LANG_EN = {
    "中文": "Chinese",
    "英文": "English",
    "法文": "French",
    "韩文": "Korean",
    "日文": "Japanese",
    "西班牙文": "Spanish",
    "葡萄牙文": "Portuguese",
}
SOURCE_OPTIONS = ["自动检测"] + LANGUAGES
TONES = ["正式商务", "自然口语", "忠实直译"]
TONE_HINTS = {
    "正式商务": "Use a formal, professional business register.",
    "自然口语": "Use a natural, conversational tone.",
    "忠实直译": "Translate faithfully and literally, preserving the original structure.",
}

_HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def detect_language(text: str) -> str:
    """按字符脚本粗略判断语言（拉丁语系用变音符号启发式）。"""
    t = text or ""
    if _HANGUL.search(t):
        return "韩文"
    if _KANA.search(t):
        return "日文"
    if _CJK.search(t):
        return "中文"
    low = t.lower()
    if any(ch in low for ch in "ñ¿¡"):
        return "西班牙文"
    if any(ch in low for ch in "ãõ"):
        return "葡萄牙文"
    if any(ch in low for ch in "çœàâèêëîïôùûü"):
        return "法文"
    return "英文"


def _en(name: str) -> str:
    return LANG_EN.get(name, "English")


def build_messages(text: str, src: str, tgt: str, tone: str) -> list[dict]:
    if src == "自动检测":
        src = detect_language(text)
    if src == tgt:
        tgt = "中文" if src != "中文" else "英文"
    src_en, tgt_en = _en(src), _en(tgt)
    system = (
        f"You are a professional translator. Translate the user's {src_en} text into {tgt_en}. "
        "Preserve the meaning, tone, numbers and formatting. Output ONLY the translation, "
        "without explanations, notes or surrounding quotes."
    )
    hint = TONE_HINTS.get(tone, "")
    if hint:
        system = system + " " + hint
    user = f"Translate the following {src_en} text into {tgt_en}:\n\n{text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
