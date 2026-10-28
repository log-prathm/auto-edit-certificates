from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def validate_file(path_str: str, label: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def sanitize_filename(name: str, fallback: str = "recipient") -> str:
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name or fallback


def load_names(path_str: str, column: str | None = None) -> list[str]:
    path = validate_file(path_str, "Names file")

    if path.suffix.lower() == ".txt":
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("CSV has no header row.")

            selected = column or reader.fieldnames[0]
            if selected not in reader.fieldnames:
                raise ValueError(
                    f"CSV column '{selected}' not found. "
                    f"Available columns: {reader.fieldnames}"
                )

            return [
                row[selected].strip()
                for row in reader
                if row.get(selected) and row[selected].strip()
            ]

    raise ValueError("Names file must be .txt or .csv")


def find_cinzel_semibold(explicit_font: str | None) -> Path:
    if explicit_font:
        font = validate_file(explicit_font, "Font file")
        if font.suffix.lower() not in {".ttf", ".otf"}:
            raise ValueError("Font must be a .ttf or .otf file.")
        return font

    candidates: list[Path] = []

    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates.append(windir / "Fonts")

    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        candidates.append(Path(localappdata) / "Microsoft" / "Windows" / "Fonts")

    exact_names = [
        "Cinzel-SemiBold.ttf",
        "Cinzel SemiBold.ttf",
        "Cinzel-SemiBold.otf",
        "Cinzel SemiBold.otf",
    ]

    for folder in candidates:
        if not folder.exists():
            continue

        for filename in exact_names:
            p = folder / filename
            if p.is_file():
                return p

        for p in folder.glob("*"):
            if not p.is_file() or p.suffix.lower() not in {".ttf", ".otf"}:
                continue
            normalized = re.sub(r"[^a-z0-9]", "", p.stem.lower())
            if "cinzel" in normalized and "semibold" in normalized:
                return p

    raise FileNotFoundError(
        "Cinzel SemiBold was not found in Windows Fonts.\n"
        "Install Cinzel SemiBold, or pass it explicitly with:\n"
        '  --font "C:\\path\\to\\Cinzel-SemiBold.ttf"'
    )


def parse_hex_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("Color must be in #RRGGBB format.")
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as e:
        raise ValueError("Color must be in #RRGGBB format.") from e


def auto_box_horizontal(canvas_w: float) -> tuple[float, float]:
    # Centered box occupying 80% of the certificate width.
    box_w = canvas_w * 0.80
    x = (canvas_w - box_w) / 2
    return x, box_w


def auto_box_vertical(canvas_h: float) -> tuple[float, float]:
    # Default name region around the vertical middle.
    box_h = canvas_h * 0.14
    y = (canvas_h - box_h) / 2
    return y, box_h


def fit_font_size_pil(
    name: str,
    font_path: Path,
    start_size: int,
    box_w: float,
    box_h: float,
    auto_fit: bool,
) -> tuple[ImageFont.FreeTypeFont, int]:
    size = max(1, int(start_size))

    while True:
        font = ImageFont.truetype(str(font_path), size=size)
        bbox = font.getbbox(name)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        if not auto_fit or (text_w <= box_w and text_h <= box_h) or size <= 6:
            return font, size

        size -= 1


def render_image_template_to_pdf(
    template_path: Path,
    out_path: Path,
    name: str,
    x: float,
    y: float,
    box_w: float,
    box_h: float,
    font_path: Path,
    font_size: int,
    color_hex: str,
    auto_fit: bool,
) -> None:
    rgb = parse_hex_color(color_hex)

    with Image.open(template_path) as original:
        image = original.convert("RGB")

    draw = ImageDraw.Draw(image)
    font, _ = fit_font_size_pil(
        name, font_path, font_size, box_w, box_h, auto_fit
    )

    bbox = draw.textbbox((0, 0), name, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    text_x = x + (box_w - text_w) / 2 - bbox[0]
    text_y = y + (box_h - text_h) / 2 - bbox[1]

    draw.text((text_x, text_y), name, font=font, fill=rgb)

    # Pillow writes a proper one-page PDF.
    image.save(out_path, "PDF", resolution=300.0)


def fit_pdf_font_size(
    name: str,
    font: fitz.Font,
    start_size: int,
    box_w: float,
    box_h: float,
    auto_fit: bool,
) -> int:
    size = max(1, int(start_size))

    while True:
        text_w = font.text_length(name, fontsize=size)
        # Approximate text height using font ascender/descender.
        text_h = (font.ascender - font.descender) * size

        if not auto_fit or (text_w <= box_w and text_h <= box_h) or size <= 6:
            return size

        size -= 1


def render_pdf_template_to_pdf(
    template_path: Path,
    out_path: Path,
    name: str,
    x: float,
    y: float,
    box_w: float,
    box_h: float,
    font_path: Path,
    font_size: int,
    color_hex: str,
    page_num: int,
    auto_fit: bool,
) -> None:
    rgb255 = parse_hex_color(color_hex)
    rgb = tuple(c / 255.0 for c in rgb255)

    doc = fitz.open(str(template_path))
    try:
        if page_num < 0 or page_num >= len(doc):
            raise IndexError(
                f"PDF page {page_num} does not exist. "
                f"Template has {len(doc)} page(s)."
            )

        page = doc[page_num]

        font = fitz.Font(fontfile=str(font_path))
        fitted_size = fit_pdf_font_size(
            name, font, font_size, box_w, box_h, auto_fit
        )

        font_alias = "cinzel_semibold"
        page.insert_font(fontname=font_alias, fontfile=str(font_path))

        rect = fitz.Rect(x, y, x + box_w, y + box_h)

        result = page.insert_textbox(
            rect,
            name,
            fontsize=fitted_size,
            fontname=font_alias,
            color=rgb,
            align=fitz.TEXT_ALIGN_CENTER,
            overlay=True,
        )

        if result < 0 and not auto_fit:
            print(
                f"Warning: '{name}' may not fit in the selected box "
                f"because --no-auto-fit was used."
            )

        doc.save(str(out_path), garbage=4, deflate=True)
    finally:
        doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-add recipient names to a certificate and output one PDF per person."
    )

    parser.add_argument(
        "--template",
        required=True,
        help="Certificate template: .pdf, .png, .jpg, .jpeg, .bmp, or .webp",
    )
    parser.add_argument(
        "--names",
        required=True,
        help="TXT file (one name per line) or CSV file",
    )
    parser.add_argument(
        "--names-column",
        default=None,
        help="CSV column containing recipient names. Defaults to first column.",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Folder where generated PDFs will be saved",
    )

    parser.add_argument("--x", type=float, default=None, help="Name box left X")
    parser.add_argument("--y", type=float, default=None, help="Name box top Y")
    parser.add_argument("--box-w", type=float, default=None, help="Name box width")
    parser.add_argument("--box-h", type=float, default=None, help="Name box height")

    parser.add_argument(
        "--font",
        default=None,
        help="Optional path to Cinzel SemiBold .ttf/.otf. "
             "If omitted, Windows Fonts is searched automatically.",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=40,
        help="Starting font size. Default: 40",
    )
    parser.add_argument(
        "--color",
        default="#000000",
        help="Text color in #RRGGBB format. Default: #000000",
    )
    parser.add_argument(
        "--page-num",
        type=int,
        default=0,
        help="PDF template page number, 0-based. Default: 0",
    )
    parser.add_argument(
        "--no-auto-fit",
        action="store_true",
        help="Disable automatic font shrinking",
    )
    parser.add_argument(
        "--suffix",
        default="_certificate",
        help='Filename suffix. Default: "_certificate"',
    )

    args = parser.parse_args()

    template = validate_file(args.template, "Template file")
    names = load_names(args.names, args.names_column)

    if not names:
        raise ValueError("No names found in the input file.")

    font_path = find_cinzel_semibold(args.font)

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    ext = template.suffix.lower()
    is_pdf = ext == ".pdf"
    is_image = ext in IMAGE_EXTS

    if not is_pdf and not is_image:
        raise ValueError(f"Unsupported template type: {ext}")

    if is_image:
        with Image.open(template) as img:
            canvas_w, canvas_h = img.size
    else:
        doc = fitz.open(str(template))
        try:
            if args.page_num < 0 or args.page_num >= len(doc):
                raise IndexError(
                    f"PDF page {args.page_num} does not exist. "
                    f"Template has {len(doc)} page(s)."
                )
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
        raise ValueError(
            "Provide both --x and --box-w, or omit both for automatic horizontal placement."
        )

    if args.y is None and args.box_h is None:
        y, box_h = auto_box_vertical(canvas_h)
    elif args.y is not None and args.box_h is not None:
        y, box_h = args.y, args.box_h
    else:
        raise ValueError(
            "Provide both --y and --box-h, or omit both for automatic vertical placement."
        )

    print(f"Template : {template}")
    print(f"Font     : {font_path}")
    print(f"Recipients: {len(names)}")
    print(f"Output   : {outdir}")
    print(f"Name box : x={x:.2f}, y={y:.2f}, w={box_w:.2f}, h={box_h:.2f}")
    print()

    for i, name in enumerate(names, start=1):
        safe_name = sanitize_filename(name, fallback=f"recipient_{i}")
        out_path = outdir / f"{safe_name}{args.suffix}.pdf"

        if is_image:
            render_image_template_to_pdf(
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
            render_pdf_template_to_pdf(
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

        print(f"[{i}/{len(names)}] {out_path.name}")

    print(f"\nDone. Created {len(names)} PDF certificate(s) in:")
    print(outdir)


if __name__ == "__main__":
    main()
