from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    import pymupdf as fitz
except ImportError:
    import fitz


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

LEADER_ALIASES = {
    "teamleaderfullname",
    "teamleader",
    "leaderfullname",
    "leadername",
    "leader",
    "name",
}

GROUP_ALIASES = {
    "groupno",
    "groupnumber",
    "group",
    "teamno",
    "teamnumber",
}


def validate_file(path_str: str | Path, label: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def clean_name(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", clean_name(value).lower())


def normalize_person_name(value: object) -> str:
    # Used only for matching a leader from leader_names.csv to sih_names.xlsx.
    return re.sub(r"\s+", " ", clean_name(value)).casefold()


def sanitize_filename(name: str, fallback: str = "recipient") -> str:
    name = clean_name(name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = name.rstrip(". ")
    return name or fallback


def unique_nonempty(names: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for name in names:
        value = clean_name(name)
        if not value:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def find_header_row(rows: list[list[object]]) -> int | None:
    for i, row in enumerate(rows):
        normalized = [normalize_header(v) for v in row]
        if any(h in LEADER_ALIASES for h in normalized):
            return i
        if any("leader" in h and "name" in h for h in normalized):
            return i
    return None


def find_leader_column(headers: list[object]) -> int | None:
    normalized = [normalize_header(h) for h in headers]

    for i, header in enumerate(normalized):
        if header in LEADER_ALIASES:
            return i

    for i, header in enumerate(normalized):
        if "leader" in header and "name" in header:
            return i

    return None


def find_member_columns(headers: list[object], leader_idx: int) -> list[int]:
    """
    Accepts:
      Member 2
      Member2
      Member 2 Full Name
      Team Member 2
      member_2_name
    """
    normalized = [normalize_header(h) for h in headers]
    found: list[tuple[int, int]] = []

    for i, header in enumerate(normalized):
        if i == leader_idx:
            continue

        if "member" not in header:
            continue

        match = re.search(r"member(\d+)", header)
        if match:
            found.append((int(match.group(1)), i))

    found.sort(key=lambda pair: pair[0])
    return [idx for _, idx in found]


def read_table(path: Path) -> tuple[list[object], list[list[object]]]:
    ext = path.suffix.lower()

    if ext == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = [list(row) for row in csv.reader(f)]

        if not rows:
            raise ValueError(f"CSV is empty: {path}")

        header_idx = find_header_row(rows)

        # If it is just a plain one-column file with no recognizable header,
        # return a synthetic header and every row as data.
        if header_idx is None:
            max_cols = max((len(r) for r in rows), default=0)
            if max_cols <= 1:
                return ["Name"], rows
            # Otherwise treat first row as header.
            header_idx = 0

        return list(rows[header_idx]), rows[header_idx + 1 :]

    if ext in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ImportError(
                "Excel input requires openpyxl.\n"
                "Install it once with:\n"
                "  pip install openpyxl"
            ) from exc

        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows = [list(row) for row in ws.iter_rows(values_only=True)]
        finally:
            wb.close()

        header_idx = find_header_row(rows)
        if header_idx is None:
            raise ValueError(
                f"Could not find a team-leader header in Excel file: {path}"
            )

        return list(rows[header_idx]), rows[header_idx + 1 :]

    if ext == ".txt":
        rows = [
            [line.strip()]
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        return ["Name"], rows

    raise ValueError(
        f"Unsupported names file type: {path.suffix}. "
        "Use .csv, .xlsx, .xlsm, or .txt."
    )


def table_has_member_columns(headers: list[object]) -> bool:
    leader_idx = find_leader_column(headers)
    if leader_idx is None:
        return False
    return len(find_member_columns(headers, leader_idx)) > 0


def rows_to_teams(
    headers: list[object],
    rows: list[list[object]],
) -> list[dict]:
    leader_idx = find_leader_column(headers)
    if leader_idx is None:
        raise ValueError("No team-leader column was found.")

    member_indices = find_member_columns(headers, leader_idx)
    if not member_indices:
        raise ValueError(
            "The roster has a team-leader column, but no Member 2 / Member 3 / "
            "etc. columns were found."
        )

    normalized_headers = [normalize_header(h) for h in headers]
    group_idx = next(
        (i for i, h in enumerate(normalized_headers) if h in GROUP_ALIASES),
        None,
    )

    teams: list[dict] = []

    for row in rows:
        padded = list(row) + [None] * max(0, len(headers) - len(row))

        leader = clean_name(padded[leader_idx])
        if not leader:
            continue

        members = [leader]
        for idx in member_indices:
            if idx < len(padded):
                member = clean_name(padded[idx])
                if member:
                    members.append(member)

        members = unique_nonempty(members)

        group = ""
        if group_idx is not None and group_idx < len(padded):
            group = clean_name(padded[group_idx])

        teams.append(
            {
                "leader": leader,
                "members": members,
                "group": group,
            }
        )

    return teams


def read_leader_selection(
    headers: list[object],
    rows: list[list[object]],
) -> list[str]:
    leader_idx = find_leader_column(headers)

    if leader_idx is None:
        leader_idx = 0

    leaders: list[str] = []
    for row in rows:
        if leader_idx >= len(row):
            continue
        value = clean_name(row[leader_idx])
        if value:
            leaders.append(value)

    return unique_nonempty(leaders)


def candidate_roster_paths(names_path: Path) -> list[Path]:
    """
    The exact old command can still use:
        --names leader_names.csv

    If that CSV contains only leaders, we automatically look for the full
    roster beside it / beside the script / in the current working directory.
    """
    directories = [
        names_path.parent,
        Path.cwd(),
        Path(__file__).resolve().parent,
    ]

    preferred_names = [
        "sih_names.xlsx",
        "SIH_names.xlsx",
        "sih-names.xlsx",
        "sih names.xlsx",
        "team_names.xlsx",
        "teams.xlsx",
    ]

    result: list[Path] = []
    seen: set[Path] = set()

    for directory in directories:
        for filename in preferred_names:
            p = (directory / filename).resolve()
            if p not in seen:
                seen.add(p)
                result.append(p)

    # Fallback: examine other Excel files in those directories.
    for directory in directories:
        if not directory.exists():
            continue
        for pattern in ("*.xlsx", "*.xlsm"):
            for p in directory.glob(pattern):
                p = p.resolve()
                if p not in seen:
                    seen.add(p)
                    result.append(p)

    return result


def discover_roster(names_path: Path) -> Path:
    checked: list[Path] = []

    for candidate in candidate_roster_paths(names_path):
        if not candidate.is_file():
            continue

        # Avoid treating the input itself as a separate roster if it has no members.
        if candidate == names_path:
            continue

        checked.append(candidate)

        try:
            headers, _ = read_table(candidate)
            if table_has_member_columns(headers):
                return candidate
        except Exception:
            # Not a usable roster; continue searching.
            continue

    checked_text = "\n".join(f"  - {p}" for p in checked) or "  (none found)"
    raise FileNotFoundError(
        "Your --names file contains only team leaders, so a full team roster is "
        "required to create member certificates.\n\n"
        "Put the uploaded Excel roster in the same project folder as:\n"
        "  sih_names.xlsx\n\n"
        "Searched usable Excel files:\n"
        f"{checked_text}"
    )


def deduplicate_roster(teams: list[dict]) -> list[dict]:
    """
    Removes exact duplicate team rows. This handles duplicate spreadsheet rows
    without generating the same six certificates twice.
    """
    result: list[dict] = []
    seen: set[tuple] = set()

    for team in teams:
        key = (
            normalize_person_name(team["leader"]),
            tuple(normalize_person_name(m) for m in team["members"]),
        )
        if key not in seen:
            seen.add(key)
            result.append(team)

    return result


def resolve_teams(names_path: Path) -> tuple[list[dict], Path]:
    """
    Two modes:

    1. --names already contains leader + Member 2..Member 6:
       use it directly.

    2. --names is leader_names.csv / TXT with leader names only:
       automatically find sih_names.xlsx and use leader_names.csv only as the
       selection list.
    """
    headers, rows = read_table(names_path)

    if table_has_member_columns(headers):
        teams = deduplicate_roster(rows_to_teams(headers, rows))
        return teams, names_path

    selected_leaders = read_leader_selection(headers, rows)
    if not selected_leaders:
        raise ValueError(f"No team leader names found in: {names_path}")

    roster_path = discover_roster(names_path)
    roster_headers, roster_rows = read_table(roster_path)
    roster_teams = deduplicate_roster(
        rows_to_teams(roster_headers, roster_rows)
    )

    by_leader: dict[str, list[dict]] = {}
    for team in roster_teams:
        key = normalize_person_name(team["leader"])
        by_leader.setdefault(key, []).append(team)

    selected_teams: list[dict] = []
    missing: list[str] = []

    for leader in selected_leaders:
        key = normalize_person_name(leader)
        matches = by_leader.get(key, [])

        if not matches:
            missing.append(leader)
            continue

        # If duplicate rows have the same leader but different members, use the
        # first row and explicitly warn. Exact duplicate rows were removed above.
        if len(matches) > 1:
            print(
                f"Warning: multiple different roster rows found for leader "
                f"'{leader}'. Using the first matching row."
            )

        selected_teams.append(matches[0])

    if missing:
        missing_text = "\n".join(f"  - {name}" for name in missing)
        raise ValueError(
            "These leaders from the --names file were not found in "
            f"{roster_path.name}:\n{missing_text}\n\n"
            "Check spelling/spacing in leader_names.csv."
        )

    return selected_teams, roster_path


def find_font(explicit_font: str | None) -> Path:
    if explicit_font:
        font = validate_file(explicit_font, "Font file")
        if font.suffix.lower() not in {".ttf", ".otf"}:
            raise ValueError("Font must be a .ttf or .otf file.")
        return font

    candidates = [
        Path.cwd() / "Cinzel-SemiBold.ttf",
        Path.cwd() / "static" / "Cinzel-SemiBold.ttf",
        Path.cwd() / "fonts" / "Cinzel-SemiBold.ttf",
        Path(__file__).resolve().parent / "Cinzel-SemiBold.ttf",
        Path(__file__).resolve().parent / "static" / "Cinzel-SemiBold.ttf",
        Path(__file__).resolve().parent / "fonts" / "Cinzel-SemiBold.ttf",
    ]

    for p in candidates:
        if p.is_file():
            return p.resolve()

    font_dirs: list[Path] = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    ]

    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        font_dirs.append(
            Path(localappdata) / "Microsoft" / "Windows" / "Fonts"
        )

    for folder in font_dirs:
        if not folder.exists():
            continue
        for p in folder.glob("*"):
            if not p.is_file() or p.suffix.lower() not in {".ttf", ".otf"}:
                continue
            normalized = re.sub(r"[^a-z0-9]", "", p.stem.lower())
            if "cinzel" in normalized and "semibold" in normalized:
                return p.resolve()

    raise FileNotFoundError(
        "Cinzel SemiBold was not found.\n"
        'Pass it explicitly with --font "static\\Cinzel-SemiBold.ttf"'
    )


def parse_hex_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("Color must be in #RRGGBB format.")
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise ValueError("Color must be in #RRGGBB format.") from exc


def auto_box_horizontal(canvas_w: float) -> tuple[float, float]:
    box_w = canvas_w * 0.80
    x = (canvas_w - box_w) / 2
    return x, box_w


def auto_box_vertical(canvas_h: float) -> tuple[float, float]:
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
        name,
        font_path,
        font_size,
        box_w,
        box_h,
        auto_fit,
    )

    bbox = draw.textbbox((0, 0), name, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    text_x = x + (box_w - text_w) / 2 - bbox[0]
    text_y = y + (box_h - text_h) / 2 - bbox[1]

    draw.text((text_x, text_y), name, font=font, fill=rgb)

    out_path.parent.mkdir(parents=True, exist_ok=True)
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
            name,
            font,
            font_size,
            box_w,
            box_h,
            auto_fit,
        )

        font_alias = "certfont"
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
                "because --no-auto-fit was used."
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path), garbage=4, deflate=True)
    finally:
        doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate SIH certificate PDFs, grouped by team leader."
        )
    )

    parser.add_argument("--template", required=True)
    parser.add_argument("--names", required=True)
    parser.add_argument("--names-column", default=None)  # legacy compatibility
    parser.add_argument("--outdir", required=True)

    parser.add_argument("--x", type=float, default=None)
    parser.add_argument("--box-w", type=float, default=None)
    parser.add_argument("--y", type=float, default=None)
    parser.add_argument("--box-h", type=float, default=None)

    parser.add_argument("--font", default=None)
    parser.add_argument("--font-size", type=int, default=40)
    parser.add_argument("--color", default="#000000")
    parser.add_argument("--page-num", type=int, default=0)
    parser.add_argument("--no-auto-fit", action="store_true")
    parser.add_argument("--suffix", default="")

    args = parser.parse_args()

    template = validate_file(args.template, "Template file")
    names_path = validate_file(args.names, "Names file")
    font_path = find_font(args.font)

    teams, roster_source = resolve_teams(names_path)

    # Exact requested structure:
    # <outdir>\sih_certificates\<TEAM LEADER>\<PERSON>.pdf
    output_root = (
        Path(args.outdir).expanduser().resolve()
        / "sih_certificates"
    )
    output_root.mkdir(parents=True, exist_ok=True)

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
            "Provide both --x and --box-w, or omit both."
        )

    if args.y is None and args.box_h is None:
        y, box_h = auto_box_vertical(canvas_h)
    elif args.y is not None and args.box_h is not None:
        y, box_h = args.y, args.box_h
    else:
        raise ValueError(
            "Provide both --y and --box-h, or omit both."
        )

    total_people = sum(len(team["members"]) for team in teams)

    print(f"Selection file : {names_path}")
    print(f"Roster source  : {roster_source}")
    print(f"Template       : {template}")
    print(f"Font           : {font_path}")
    print(f"Teams          : {len(teams)}")
    print(f"Certificates   : {total_people}")
    print(f"Output         : {output_root}")
    print(
        f"Name box       : x={x:.2f}, y={y:.2f}, "
        f"w={box_w:.2f}, h={box_h:.2f}"
    )
    print()

    created = 0

    for team_index, team in enumerate(teams, start=1):
        leader = team["leader"]
        members = team["members"]

        team_dir = output_root / sanitize_filename(
            leader,
            fallback=f"team_{team_index}",
        )
        team_dir.mkdir(parents=True, exist_ok=True)

        print(
            f"[Team {team_index}/{len(teams)}] {leader} "
            f"({len(members)} people)"
        )

        for member in members:
            filename = sanitize_filename(
                member,
                fallback=f"member_{created + 1}",
            )
            out_path = team_dir / f"{filename}{args.suffix}.pdf"

            if is_image:
                render_image_template_to_pdf(
                    template_path=template,
                    out_path=out_path,
                    name=member,
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
                    name=member,
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

            created += 1
            print(f"    + {out_path.name}")

    print()
    print(f"Done. Created {created} certificate PDF(s).")
    print(output_root)


if __name__ == "__main__":
    main()
