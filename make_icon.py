"""生成应用图标 `翻译助手.ico`（需要 Pillow）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "翻译助手.ico"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
]


def load_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def build() -> None:
    from PIL import Image, ImageDraw

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = 8
    draw.rounded_rectangle(
        [pad, pad, size - 1 - pad, size - 1 - pad],
        radius=56,
        fill=(217, 164, 65, 255),
    )
    # 内圈高光，增加质感
    draw.rounded_rectangle(
        [pad + 10, pad + 10, size - 1 - pad - 10, size - 1 - pad - 10],
        radius=46,
        outline=(255, 236, 200, 90),
        width=3,
    )

    font = load_font(150)
    glyph = "译"
    bbox = draw.textbbox((0, 0), glyph, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1] - 6),
        glyph,
        font=font,
        fill=(26, 18, 4, 255),
    )

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(OUTPUT, format="ICO", sizes=sizes)
    print(f"已生成图标：{OUTPUT}")


if __name__ == "__main__":
    build()
