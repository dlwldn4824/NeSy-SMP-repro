"""Render Markdown reports to PDF (Korean font + Mermaid via Kroki)."""
from __future__ import annotations

import base64
import re
import zlib
from pathlib import Path

import markdown
import requests
from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
FONT_B = Path(r"C:\Windows\Fonts\malgunbd.ttf")


def strip_md_inline(s: str) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = s.replace("\u2248", "~").replace("\u2192", "->").replace("\u2190", "<-")
    s = s.replace("\U0001f534", "[!]").replace("🔴", "[!]")
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    return s


def kroki_png(diagram: str) -> bytes | None:
    # Prefer POST (avoids huge URL limits)
    try:
        r = requests.post(
            "https://kroki.io/mermaid/png",
            data=diagram.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=90,
        )
        if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n":
            return r.content
        print(f"  kroki status={r.status_code} body={r.text[:120]}")
    except Exception as e:
        print(f"  kroki err={e}")
    return None


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        if not FONT.exists():
            raise FileNotFoundError(FONT)
        self.add_font("malgun", "", str(FONT))
        if FONT_B.exists():
            self.add_font("malgun", "B", str(FONT_B))
        self.set_font("malgun", size=11)

    def footer(self):
        self.set_y(-12)
        self.set_font("malgun", size=8)
        self.cell(0, 8, f"{self.page_no()}", align="C")


def md_to_pdf(md_path: Path, pdf_path: Path, asset_dir: Path) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    raw = md_path.read_text(encoding="utf-8")

    # Extract mermaid blocks and replace with placeholders
    mermaid_blocks = []

    def _repl(m):
        i = len(mermaid_blocks)
        mermaid_blocks.append(m.group(1).strip())
        return f"\n\n[[MERMAID:{i}]]\n\n"

    body = re.sub(r"```mermaid\n(.*?)```", _repl, raw, flags=re.S)

    # Render mermaid images
    img_paths = []
    for i, diag in enumerate(mermaid_blocks):
        png = kroki_png(diag)
        out = asset_dir / f"mmd_{i}.png"
        if png:
            out.write_bytes(png)
            img_paths.append(out)
            print(f"  mermaid {i}: ok ({len(png)} bytes)")
        else:
            img_paths.append(None)
            print(f"  mermaid {i}: FAILED")

    pdf = ReportPDF()
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    lines = body.splitlines()
    i = 0
    in_code = False
    in_quote = False
    table_buf: list[str] = []

    def flush_table():
        nonlocal table_buf
        if len(table_buf) < 2:
            table_buf = []
            return
        rows = []
        for row in table_buf:
            if re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$", row):
                continue
            cells = [strip_md_inline(c.strip()) for c in row.strip().strip("|").split("|")]
            rows.append(cells)
        if not rows:
            table_buf = []
            return
        ncol = max(len(r) for r in rows)
        for r in rows:
            while len(r) < ncol:
                r.append("")
        col_w = usable / ncol
        pdf.set_font("malgun", size=8)
        for ri, r in enumerate(rows):
            # estimate height
            max_h = 6
            for cell in r:
                # rough wrap count
                max_h = max(max_h, 5 + 4 * max(1, len(cell) // max(1, int(col_w / 2))))
            max_h = min(max_h, 28)
            y0 = pdf.get_y()
            if y0 + max_h > pdf.h - 15:
                pdf.add_page()
                y0 = pdf.get_y()
            x0 = pdf.l_margin
            for ci, cell in enumerate(r):
                pdf.set_xy(x0 + ci * col_w, y0)
                style = "B" if ri == 0 else ""
                pdf.set_font("malgun", style=style, size=8)
                pdf.multi_cell(col_w, 4, cell, border=1, max_line_height=4)
            pdf.set_y(y0 + max_h)
        pdf.ln(2)
        pdf.set_font("malgun", size=11)
        table_buf = []

    while i < len(lines):
        line = lines[i]
        # mermaid placeholder
        m = re.match(r"\[\[MERMAID:(\d+)\]\]", line.strip())
        if m:
            flush_table()
            idx = int(m.group(1))
            img = img_paths[idx] if idx < len(img_paths) else None
            if img and img.exists():
                # scale to page width
                if pdf.get_y() > pdf.h - 80:
                    pdf.add_page()
                pdf.image(str(img), w=min(usable, 180))
                pdf.ln(4)
            else:
                pdf.set_font("malgun", size=9)
                pdf.multi_cell(usable, 5, f"[다이어그램 렌더 실패: mermaid #{idx}]")
                pdf.set_font("malgun", size=11)
            i += 1
            continue

        if line.strip().startswith("|"):
            table_buf.append(line)
            i += 1
            # peek
            if i >= len(lines) or not lines[i].strip().startswith("|"):
                flush_table()
            continue
        else:
            flush_table()

        if line.strip().startswith("```"):
            in_code = not in_code
            i += 1
            continue

        if in_code:
            pdf.set_font("Courier", size=8)
            # fpdf may not have courier korean - use malgun small
            pdf.set_font("malgun", size=8)
            pdf.multi_cell(usable, 4, line[:200])
            pdf.set_font("malgun", size=11)
            i += 1
            continue

        if line.startswith("# "):
            pdf.set_font("malgun", "B", 16)
            pdf.ln(3)
            pdf.multi_cell(usable, 8, strip_md_inline(line[2:]))
            pdf.set_font("malgun", size=11)
            pdf.ln(2)
        elif line.startswith("## "):
            pdf.set_font("malgun", "B", 13)
            pdf.ln(2)
            pdf.multi_cell(usable, 7, strip_md_inline(line[3:]))
            pdf.set_font("malgun", size=11)
            pdf.ln(1)
        elif line.startswith("### "):
            pdf.set_font("malgun", "B", 11)
            pdf.multi_cell(usable, 6, strip_md_inline(line[4:]))
            pdf.set_font("malgun", size=11)
        elif line.startswith("> "):
            pdf.set_font("malgun", size=10)
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(usable - 3, 5, strip_md_inline(line[2:]))
            pdf.set_font("malgun", size=11)
        elif line.strip().startswith("- ") or line.strip().startswith("* "):
            pdf.multi_cell(usable, 5, "• " + strip_md_inline(line.strip()[2:]))
        elif line.strip() == "":
            pdf.ln(2)
        elif line.strip() == "---":
            pdf.ln(1)
        else:
            pdf.multi_cell(usable, 5, strip_md_inline(line))
        i += 1

    flush_table()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    print(f"wrote {pdf_path} pages={pdf.page_no()}")


if __name__ == "__main__":
    jobs = [
        (
            ROOT / "docs" / "NeSy-SMP_REPRO_REPORT.md",
            ROOT / "docs" / "NeSy-SMP_REPRO_REPORT.pdf",
            ROOT / "docs" / "_assets",
        ),
        (
            ROOT / "local_docs" / "NeSy-SMP_STUDY_GUIDE.md",
            ROOT / "local_docs" / "NeSy-SMP_STUDY_GUIDE.pdf",
            ROOT / "local_docs" / "_assets",
        ),
    ]
    for md, pdf, assets in jobs:
        print("===", md.name)
        md_to_pdf(md, pdf, assets)
