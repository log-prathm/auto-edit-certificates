from pathlib import Path
from .common_helper import parse_color
from PIL import Image, ImageDraw, ImageFont
from .common_helper import fit_font_size_pil
from typing import Optional


def render_on_image(
    template_path: Path,
    out_path: Path,
    name: str,
    x: float,
    y: float,
    box_w: float,
    box_h: float,
    font_path: Optional[Path],
    font_size: int,
    color_hex: str,
    auto_fit: bool = True,
) -> None:
    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    color = parse_color(color_hex)

    if font_path is not None:
        if auto_fit:
            font = fit_font_size_pil(draw, name, font_path, font_size, box_w, box_h)
        else:
            font = ImageFont.truetype(str(font_path), size=font_size)
    else:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), name, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    tx = x + (box_w - text_w) / 2
    ty = y + (box_h - text_h) / 2

    draw.text((tx, ty), name, fill=color, font=font)

    if out_path.suffix.lower() in {".jpg", ".jpeg"}:
        img = img.convert("RGB")

    img.save(out_path)
