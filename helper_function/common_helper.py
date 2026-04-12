from pathlib import Path
import csv
from typing import Optional
from PIL import ImageDraw, ImageFont
def parse_color(color: str) -> tuple[int, int, int]:
    color = color.strip()
    if color.startswith("#"):
        color = color[1:]
    if len(color) != 6:
        raise ValueError("Color must be in hex format like #000000")
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as e:
        raise ValueError("Invalid hex color value.") from e


def validate_file(path: str | Path, label: str) -> Path:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"{label} not found: {p.resolve()}")
    return p


def load_names(path: str, column: str | None = None) -> list[str]:
    p = validate_file(path, "Names file")

    if p.suffix.lower() == ".csv":
        with p.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("CSV has no header row.")
            if column is None:
                column = reader.fieldnames[0]

            names: list[str] = []
            for row in reader:
                value = (row.get(column) or "").strip()
                if value:
                    names.append(value)
            return names

    with p.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def sanitize_filename(name: str, fallback: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    safe = "_".join(safe.split())
    return safe or fallback


def resolve_font(font_path: Optional[str]) -> Optional[Path]:
    if not font_path:
        return None
    p = Path(font_path)
    if not p.is_file():
        raise FileNotFoundError(f"Font file not found: {p.resolve()}")
    return p


def fit_font_size_pil(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_size: int,
    box_w: float,
    box_h: float,
    min_size: int = 10,
) -> ImageFont.FreeTypeFont:
    size = max_size
    while size >= min_size:
        font = ImageFont.truetype(str(font_path), size=size)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        if text_w <= box_w and text_h <= box_h:
            return font
        size -= 1
    return ImageFont.truetype(str(font_path), size=min_size)


def auto_box_horizontal(canvas_w: float) -> tuple[float, float]:
    box_w = canvas_w * 0.90
    x = (canvas_w - box_w) / 2
    return x, box_w


def auto_box_vertical(canvas_h: float) -> tuple[float, float]:
    box_h = canvas_h * 0.18
    y = (canvas_h - box_h) / 2
    return y, box_h


