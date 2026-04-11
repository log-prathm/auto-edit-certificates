from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-add names to certificate templates.")
    parser.add_argument("--template", required=True, help="Path to template (.png/.jpg/.jpeg/.pdf)")
    parser.add_argument("--names", required=True, help="CSV file or TXT file with names")
    parser.add_argument("--names-column", default=None, help="CSV column name containing names")
    parser.add_argument("--outdir", required=True, help="Output folder")

    # Horizontal can be auto-centered if omitted.
    parser.add_argument("--x", type=float, default=None, help="Top-left x of name box")
    parser.add_argument("--box-w", type=float, default=None, help="Width of name box")

    # Vertical can be manually controlled if provided.
    parser.add_argument("--y", type=float, default=None, help="Top-left y of name box")
    parser.add_argument("--box-h", type=float, default=None, help="Height of name box")

    parser.add_argument("--font", default=None, help="Path to a .ttf/.otf font file")
    parser.add_argument("--font-size", type=int, default=40, help="Starting font size")
    parser.add_argument("--color", default="#000000", help="Text color in hex")
    parser.add_argument("--page-num", type=int, default=0, help="PDF page number (0-based)")
    parser.add_argument("--no-auto-fit", action="store_true", help="Disable automatic font shrinking")
    parser.add_argument("--suffix", default="_certificate", help="Output filename suffix")

    args = parser.parse_args()

    template = validate_file(args.template, "Template file")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    font_path = resolve_font(args.font)
    names = load_names(args.names, args.names_column)
    if not names:
        raise ValueError("No names found in input file.")

    ext = template.suffix.lower()
    is_pdf = ext == ".pdf"
    is_image = ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

    if not is_pdf and not is_image:
        raise ValueError(f"Unsupported template type: {ext}")

    # Horizontal: if both x and box-w are omitted, auto-center.
    # Vertical: if both y and box-h are omitted, auto-center.
    # Mixed partial input is allowed.
    for i, name in enumerate(names, start=1):
        safe_name = sanitize_filename(name, fallback=f"recipient_{i}")
        out_path = outdir / f"{safe_name}{args.suffix}{ext}"

        if is_image:
            with Image.open(template) as img:
                canvas_w, canvas_h = img.size

            if args.x is None and args.box_w is None:
                x, box_w = auto_box_horizontal(canvas_w)
            elif args.x is not None and args.box_w is not None:
                x, box_w = args.x, args.box_w
            else:
                raise ValueError("Provide both --x and --box-w, or omit both for auto horizontal placement.")

            if args.y is None and args.box_h is None:
                y, box_h = auto_box_vertical(canvas_h)
            elif args.y is not None and args.box_h is not None:
                y, box_h = args.y, args.box_h
            else:
                raise ValueError("Provide both --y and --box-h, or omit both for auto vertical placement.")

            render_on_image(
                template_path=template,
                out_path=out_path,
                name=name,
                x=float(x),
                y=float(y),
                box_w=float(box_w),
                box_h=float(box_h),
                font_path=font_path,
                font_size=args.font_size,
                color_hex=args.color,
                auto_fit=not args.no_auto_fit,
            )

        else:
            doc = fitz.open(str(template))
            try:
                page = doc[args.page_num]
                canvas_w = page.rect.width
                canvas_h = page.rect.height
            finally:
                doc.close()

            if args.x is None and args.box_w is None:
                x, box_w = auto_box_horizontal(canvas_w)
            elif args.x is not None and args.box_w is not None:
                x, box_w = args.x, args.box_w
            else:
                raise ValueError("Provide both --x and --box-w, or omit both for auto horizontal placement.")

            if args.y is None and args.box_h is None:
                y, box_h = auto_box_vertical(canvas_h)
            elif args.y is not None and args.box_h is not None:
                y, box_h = args.y, args.box_h
            else:
                raise ValueError("Provide both --y and --box-h, or omit both for auto vertical placement.")

            render_on_pdf(
                template_path=template,
                out_path=out_path,
                name=name,
                x=float(x),
                y=float(y),
                box_w=float(box_w),
                box_h=float(box_h),
                font_path=font_path,
                font_size=args.font_size,
                color_hex=args.color,
                page_num=args.page_num,
                auto_fit=not args.no_auto_fit,
            )

    print(f"Done. Created {len(names)} certificates in: {outdir.resolve()}")


if __name__ == "__main__":
    main()