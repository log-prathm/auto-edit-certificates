from __future__ import annotations
import argparse
from pathlib import Path

from PIL import Image
import fitz  # PyMuPDF

from helper_function.handle_pdf import render_on_pdf
from helper_function.handle_img import render_on_image

from helper_function.common_helper import validate_file
from helper_function.common_helper import resolve_font
from helper_function.common_helper import load_names
from helper_function.common_helper import sanitize_filename
from helper_function.common_helper import auto_box_horizontal
from helper_function.common_helper import auto_box_vertical



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