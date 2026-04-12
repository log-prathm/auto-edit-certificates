from typing import Optional
from pathlib import Path
import fitz
from .common_helper import parse_color

def render_on_pdf(
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
    page_num: int = 0,
    auto_fit: bool = True,
) -> None:
    doc = fitz.open(str(template_path))
    try:
        if page_num < 0 or page_num >= len(doc):
            raise ValueError(f"page_num must be between 0 and {len(doc) - 1}")

        page = doc[page_num]
        rect = fitz.Rect(x, y, x + box_w, y + box_h)
        color = parse_color(color_hex)
        rgb = tuple(v / 255 for v in color)

        size = font_size
        while True:
            if font_path is None:
                result = page.insert_textbox(
                    rect,
                    name,
                    fontsize=size,
                    fontname="helv",
                    color=rgb,
                    align=1,
                    overlay=True,
                )
            else:
                result = page.insert_textbox(
                    rect,
                    name,
                    fontsize=size,
                    fontname=font_path.stem or "customfont",
                    fontfile=str(font_path),
                    color=rgb,
                    align=1,
                    overlay=True,
                )

            if not auto_fit or result >= 0 or size <= 10:
                break

            doc.close()
            doc = fitz.open(str(template_path))
            page = doc[page_num]
            size -= 1

        doc.save(str(out_path))
    finally:
        doc.close()