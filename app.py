"""译心 · LocalTranslate — 本地多语言翻译助手（Streamlit）。

架构：本界面通过 HTTP 调用本机的 llama.cpp `llama-server`，
模型为 Hy-MT2-7B Q4_K_M。全部离线，数据不出机。

支持中文与英/法/韩/日/西/葡双向互译。
引擎按需启停：首次翻译时加载，翻译完成/空闲后自动关闭以释放 CPU 与内存。
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assets import settings as user_settings
from assets.engine import engine
from assets.llm_client import LlamaServerClient
from assets.translator import LANGUAGES, LANG_EN, SOURCE_OPTIONS, TONES, build_messages

PALETTES = {
    "dark": {
        "bg": "#0f1115", "panel": "#15181e", "panel2": "#191c23",
        "line": "#2a2f39", "text": "#ece7dd", "muted": "#8a909c",
        "gold": "#d9a441", "mint": "#6ee7c8",
        "alert_bg": "#16202e", "alert_text": "#cfe3ff",
    },
    "light": {
        "bg": "#f4f1ea", "panel": "#ffffff", "panel2": "#faf8f3",
        "line": "#e0dacd", "text": "#1f2933", "muted": "#4b5563",
        "gold": "#b3821f", "mint": "#0f9d76",
        "alert_bg": "#e8f0fe", "alert_text": "#1f2933",
    },
}

MODEL_LABEL = "Hy-MT2-7B · Q4_K_M"
RELEASE_OPTIONS = ["立即", "30 秒", "1 分钟", "3 分钟", "不释放"]
RELEASE_SECONDS = {"立即": 0, "30 秒": 30, "1 分钟": 60, "3 分钟": 180, "不释放": 0}

st.set_page_config(
    page_title="译心 · 本地翻译助手",
    page_icon=str(ROOT / "翻译助手.ico") if (ROOT / "翻译助手.ico").exists() else "🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- 样式
def inject_style(theme: str) -> None:
    palette = PALETTES.get(theme, PALETTES["dark"])
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    order = ["bg", "panel", "panel2", "line", "text", "muted", "gold", "mint"]
    vars_css = ":root{" + "".join(f"--lt-{k}: {palette[k]};" for k in order) + "}"
    vars_css = vars_css[:-1] + (
        f"--lt-alert-bg: {palette['alert_bg']};"
        f"--lt-alert-text: {palette['alert_text']};"
        "}"
    )
    st.markdown(f"<style>{css}\n{vars_css}</style>", unsafe_allow_html=True)


# --------------------------------------------------------------------------- 状态
def persist_settings() -> None:
    user_settings.save(
        {
            "src_lang": st.session_state.get("src_lang", "中文"),
            "tgt_lang": st.session_state.get("tgt_lang", "英文"),
            "tone": st.session_state.get("tone", TONES[0]),
            "theme": st.session_state.get("theme", "dark"),
            "release": st.session_state.get("release", "30 秒"),
        }
    )


def on_theme_toggle() -> None:
    st.session_state["theme"] = "dark" if st.session_state.get("dark_toggle") else "light"
    persist_settings()


def init_state() -> None:
    if st.session_state.get("_lt_ready"):
        return
    saved = user_settings.load()
    src_lang = saved["src_lang"] if saved.get("src_lang") in SOURCE_OPTIONS else "中文"
    tgt_lang = saved["tgt_lang"] if saved.get("tgt_lang") in LANGUAGES else "英文"
    tone = saved["tone"] if saved["tone"] in TONES else TONES[0]
    theme = saved["theme"] if saved["theme"] in ("dark", "light") else "dark"
    release = saved["release"] if saved.get("release") in RELEASE_OPTIONS else "30 秒"
    st.session_state["src_lang"] = src_lang
    st.session_state["tgt_lang"] = tgt_lang
    st.session_state["tone"] = tone
    st.session_state["theme"] = theme
    st.session_state["release"] = release
    st.session_state["dark_toggle"] = theme == "dark"
    st.session_state.setdefault("result", "")
    st.session_state.setdefault("src_text", "")
    st.session_state.setdefault("_last_rate", None)
    st.session_state["_lt_ready"] = True


def apply_pending_actions() -> None:
    if st.session_state.pop("_swap_pending", False):
        old_src = st.session_state.get("src_text", "")
        st.session_state["src_text"] = st.session_state.get("result", "")
        st.session_state["result"] = old_src
        src = st.session_state.get("src_lang", "中文")
        tgt = st.session_state.get("tgt_lang", "英文")
        if src == "自动检测":
            st.session_state["src_lang"] = tgt
            st.session_state["tgt_lang"] = "中文"
        else:
            st.session_state["src_lang"] = tgt
            st.session_state["tgt_lang"] = src
        persist_settings()
    if st.session_state.pop("_clear_pending", False):
        st.session_state["src_text"] = ""
        st.session_state["result"] = ""


# --------------------------------------------------------------------------- 渲染
def render_output(text: str, caret: bool = False) -> str:
    escaped = html.escape(text or "")
    caret_html = '<span class="lt-caret">▌</span>' if caret else ""
    if not escaped and not caret:
        escaped = '<span class="lt-empty">译文将显示在这里…</span>'
    return f'<div class="lt-output">{escaped}{caret_html}</div>'


def header_html(healthy: bool) -> str:
    dot = "#6ee7c8" if healthy else "#d9a441"
    state = "引擎运行中 · 空闲自动释放" if healthy else "引擎待启动 · 首次翻译自动加载"
    return f"""
    <div class="lt-header">
      <div class="lt-brand">
        <div class="lt-logo">译</div>
        <div>
          <div class="lt-name">译心</div>
          <div class="lt-sub">LocalTranslate · 本地多语言翻译</div>
        </div>
      </div>
      <div class="lt-status">
        <span class="lt-status-dot" style="background:{dot};box-shadow:0 0 8px {dot}"></span>
        {state} · {MODEL_LABEL} · {engine.backend_label()}
      </div>
    </div>
    """


def footer_html(rate: float | None, healthy: bool) -> str:
    speed = (
        f'<span class="lt-speed">{rate:.1f} tok/s</span>'
        if rate is not None
        else '<span class="lt-muted">— tok/s</span>'
    )
    engine_state = (
        '<span class="lt-ok">● 引擎运行中</span>'
        if healthy
        else '<span class="lt-muted">○ 引擎已释放内存</span>'
    )
    return (
        '<div class="lt-foot">'
        f"{engine_state}"
        f"<span>{MODEL_LABEL}</span><span>{engine.backend_label()}</span>{speed}"
        "<span>100% 本地 · 数据不出机</span>"
        "</div>"
    )


def clipboard_button(text: str) -> None:
    if not text:
        return
    payload = json.dumps(text)
    doc = f"""
    <button id="ltcp" type="button">复制译文</button>
    <script>
    const txt = {payload};
    const btn = document.getElementById('ltcp');
    btn.onclick = async () => {{
      try {{
        await navigator.clipboard.writeText(txt);
        btn.textContent = '已复制 ✓';
        setTimeout(() => btn.textContent = '复制译文', 1500);
      }} catch (e) {{
        btn.textContent = '复制失败';
      }}
    }};
    </script>
    <style>
      html, body {{ margin:0; padding:0; }}
      #ltcp {{ width:100%; padding:9px 12px; background:#191c23; color:#ece7dd;
               border:1px solid #2a2f39; border-radius:8px; font-size:13px; cursor:pointer;
               font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif; }}
      #ltcp:hover {{ border-color:#d9a441; }}
    </style>
    """
    components.html(doc, height=46)


# --------------------------------------------------------------------------- 初始化
init_state()
apply_pending_actions()
inject_style(st.session_state["theme"])

engine.idle_timeout = RELEASE_SECONDS.get(st.session_state.get("release", "30 秒"), 30)
client = LlamaServerClient(engine.url)
healthy = engine.health()

# --------------------------------------------------------------------------- 侧边栏
with st.sidebar:
    st.markdown(
        '<div class="lt-sub" style="letter-spacing:1.5px;margin-bottom:16px;">翻译设置</div>',
        unsafe_allow_html=True,
    )
    st.selectbox("源语言", SOURCE_OPTIONS, key="src_lang", on_change=persist_settings)
    st.selectbox("目标语言", LANGUAGES, key="tgt_lang", on_change=persist_settings)
    st.selectbox("语气", TONES, key="tone", on_change=persist_settings)
    st.selectbox(
        "翻译后释放引擎",
        RELEASE_OPTIONS,
        key="release",
        on_change=persist_settings,
        help="引擎会占用约 5 GB 内存。选「立即」表示每次翻译结束就关掉引擎。",
    )
    st.text_input("模型", value=MODEL_LABEL, disabled=True, key="model_display")
    st.toggle("暗色主题", key="dark_toggle", on_change=on_theme_toggle)
    st.caption("引擎：" + ("运行中" if healthy else "已释放 / 待启动"))
    if st.button("立即释放引擎内存", key="release_now", use_container_width=True):
        engine.stop()
        st.rerun()
    st.markdown(
        '<div class="lt-sidefoot">离线运行 · 数据不出机<br>无需联网 · 无需安装</div>',
        unsafe_allow_html=True,
    )
    with st.expander("关于 / 部署说明"):
        st.markdown(
            "本工具依赖本目录下的 `llama-server.exe` 与 "
            "`models/Hy-MT2-7B-Q4_K_M.gguf`。\n\n"
            "支持中文与英/法/韩/日/西/葡互译。引擎按需启动：首次翻译自动加载（约 6 秒），"
            "之后按「翻译后释放引擎」设置自动关闭，释放内存。"
        )

# --------------------------------------------------------------------------- 主区
st.markdown(header_html(healthy), unsafe_allow_html=True)

if not healthy:
    st.info(
        "引擎当前未运行（按需启动）。点击「立即翻译」会自动加载模型（约 6 秒），"
        "完成后按设置自动释放内存。"
    )

col_left, col_right = st.columns(2, gap="large")

with col_left:
    left_head = st.empty()
    src = st.text_area(
        "原文",
        key="src_text",
        height=280,
        label_visibility="collapsed",
        placeholder="在此粘贴中文、英文或其他语言文本，点击「立即翻译」…",
    )
    left_head.markdown(
        f'<div class="lt-colhead"><span>原文</span><span>{len(src)} 字</span></div>',
        unsafe_allow_html=True,
    )

with col_right:
    tgt_display = LANG_EN.get(st.session_state.get("tgt_lang", "英文"), "English")
    st.markdown(
        f'<div class="lt-colhead"><span>译文</span><span>{tgt_display}</span></div>',
        unsafe_allow_html=True,
    )
    out_ph = st.empty()

if st.session_state.get("result"):
    out_ph.markdown(render_output(st.session_state["result"]), unsafe_allow_html=True)

action_cols = st.columns([1.3, 0.9, 0.8, 1.1, 1.1])
with action_cols[0]:
    do_translate = st.button("立即翻译", type="primary", use_container_width=True)
with action_cols[1]:
    do_swap = st.button("交换 ⇄", use_container_width=True)
with action_cols[2]:
    do_clear = st.button("清空", use_container_width=True)
with action_cols[3]:
    st.download_button(
        "导出 .txt",
        data=st.session_state.get("result", "") or "",
        file_name="translation.txt",
        mime="text/plain",
        use_container_width=True,
        disabled=not st.session_state.get("result"),
    )
with action_cols[4]:
    clipboard_button(st.session_state.get("result", ""))

footer_ph = st.empty()
footer_ph.markdown(
    footer_html(st.session_state.get("_last_rate"), healthy), unsafe_allow_html=True
)

if do_swap:
    st.session_state["_swap_pending"] = True
    st.rerun()
if do_clear:
    st.session_state["_clear_pending"] = True
    st.rerun()

if do_translate:
    text = (st.session_state.get("src_text") or "").strip()
    if not text:
        out_ph.markdown(render_output("请先输入要翻译的内容。"), unsafe_allow_html=True)
    else:
        src_lang = st.session_state.get("src_lang", "中文")
        tgt_lang = st.session_state.get("tgt_lang", "英文")
        if src_lang != "自动检测" and src_lang == tgt_lang:
            tgt_lang = "中文" if src_lang != "中文" else "英文"
            st.session_state["tgt_lang"] = tgt_lang
        ok = False
        err_msg = ""
        with st.spinner("正在启动翻译引擎（首次约 6 秒）…"):
            try:
                ok = engine.ensure_running()
            except Exception as exc:  # noqa: BLE001
                err_msg = str(exc)
        if not ok:
            out_ph.markdown(
                render_output(
                    f"翻译引擎启动失败：{err_msg or '请查看 logs/llama-server.log'}"
                ),
                unsafe_allow_html=True,
            )
        else:
            messages = build_messages(
                text, src_lang, tgt_lang, st.session_state.get("tone", TONES[0])
            )
            buf: list[str] = []
            first_at: float | None = None
            chunks = 0
            last_paint = 0.0
            out_ph.markdown(render_output("", caret=True), unsafe_allow_html=True)
            try:
                for piece in client.stream_chat(messages):
                    engine.touch()
                    if first_at is None:
                        first_at = time.perf_counter()
                    buf.append(piece)
                    chunks += 1
                    now = time.perf_counter()
                    if now - last_paint > 0.06:
                        out_ph.markdown(
                            render_output("".join(buf), caret=True), unsafe_allow_html=True
                        )
                        if first_at:
                            footer_ph.markdown(
                                footer_html(chunks / max(now - first_at, 1e-6), True),
                                unsafe_allow_html=True,
                            )
                        last_paint = now
                full = "".join(buf)
                final_rate = None
                if first_at:
                    final_rate = chunks / max(time.perf_counter() - first_at, 1e-6)
                st.session_state["result"] = full
                st.session_state["_last_rate"] = final_rate
                out_ph.markdown(render_output(full), unsafe_allow_html=True)
                engine.touch()
                if st.session_state.get("release") == "立即":
                    engine.stop()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                out_ph.markdown(render_output(f"翻译失败：{exc}"), unsafe_allow_html=True)
