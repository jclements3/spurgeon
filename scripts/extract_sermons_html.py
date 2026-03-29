#!/usr/bin/env python3
"""Extract individual sermons from Spurgeon PDF volumes as HTML fragments.

Reads PDF volumes from VolOrder/, extracts text with formatting using PyMuPDF
(fitz), strips headers/footers, preserves italic/bold/indented formatting,
and writes one .html file per sermon to sermons_html/.
"""

import argparse
import html
import os
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Import word-rejoining from extract_sermons.py
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_sermons import (
    _load_wordset,
    _rejoin_broken_words,
    _should_join_fragments,
    WORDSET,
    SHORT_REAL_WORDS,
    PROMO_MARKERS,
)

# ---------------------------------------------------------------------------
# Bookmark helpers (adapted for fitz)
# ---------------------------------------------------------------------------

# Regex to parse bookmark titles — same as extract_sermons.py
BOOKMARK_RE = re.compile(
    r"^(\d[\d\s,A-Z]*?)\s*[-–\r]\s*(.+)$"
)
BOOKMARK_RE_NODASH = re.compile(
    r"^(\d[\d\s,A-Z]*?)\s{1,4}([A-Z\"\'].+)$"
)


def parse_bookmark_title(title):
    """Return (list_of_sermon_numbers, sermon_title) or (None, None)."""
    title = title.replace("\r", " ").replace("\n", " ").strip()
    m = BOOKMARK_RE.match(title)
    if not m:
        m = BOOKMARK_RE_NODASH.match(title)
    if not m:
        return None, None
    num_part = m.group(1).replace("O", "0")
    title_part = m.group(2).strip().rstrip(".")
    nums = []
    for tok in num_part.split(","):
        tok = tok.strip()
        tok_digits = re.sub(r"[A-Za-z]+$", "", tok)
        if tok_digits.isdigit():
            nums.append(int(tok_digits))
    if not nums:
        return None, None
    return nums, title_part


def title_to_pascal(title):
    """Convert a sermon title to PascalCase for filenames."""
    t = re.sub(r"[—–-]", " ", title)
    t = re.sub(r"[^\w\s]", "", t)
    parts = [w.capitalize() for w in t.split() if w]
    return "".join(parts)


def get_sermon_bookmarks(doc):
    """Extract sermon bookmarks from a fitz Document's TOC."""
    toc = doc.get_toc()  # list of [level, title, page_num (1-based)]
    sermons = []
    for level, title, page_num in toc:
        # fitz TOC page numbers are 1-based
        nums, sermon_title = parse_bookmark_title(title)
        if nums is None:
            continue
        sermons.append((nums, sermon_title, page_num - 1))  # convert to 0-based
    return sermons


# ---------------------------------------------------------------------------
# Header/footer detection
# ---------------------------------------------------------------------------

HEADER_PATTERNS = [
    re.compile(r"Sermon\s*#\s*\d+", re.IGNORECASE),
    re.compile(r"(New Park Street Pulpit|Metropolitan Tabernacle Pulpit)", re.IGNORECASE),
    re.compile(r"Volume\s*\d+", re.IGNORECASE),
    re.compile(r"www\.spurgeongems\.org", re.IGNORECASE),
]


def is_header_line(text):
    """Check if text matches known header patterns."""
    stripped = text.strip()
    if not stripped:
        return False
    if re.match(r"^\d{1,4}\s*$", stripped):
        return True
    return sum(1 for p in HEADER_PATTERNS if p.search(stripped)) >= 1


def is_promo_line(text):
    """Check if text belongs to the trailing promo block."""
    stripped = text.strip()
    if not stripped:
        return False
    for marker in PROMO_MARKERS:
        if marker.lower() in stripped.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Metadata block patterns (same as extract_sermons.py)
# ---------------------------------------------------------------------------

_no_re = re.compile(r"^\s*NO\.\s*\d+", re.IGNORECASE)
_sermon_delivery_re = re.compile(r"^\s*A\s+SERMON", re.IGNORECASE)
_by_re = re.compile(
    r"^\s*(BY\s+(THE\s+REV\.\s+)?C\.?\s*H\.?\s*SPURGEON|DELIVERED\s+BY|BY\s+C\.\s*H)",
    re.IGNORECASE,
)
_at_re = re.compile(
    r"^\s*AT\s+(THE\s+)?(METROPOLITAN\s+TABERNACLE|NEW\s+PARK\s+STREET|EXETER\s+HALL|SURREY)",
    re.IGNORECASE,
)
_date_continuation_re = re.compile(
    r"^\s*ON\s+(SUNDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|LORD)",
    re.IGNORECASE,
)
_intended_re = re.compile(r"^\s*INTENDED\s+FOR\s+READING", re.IGNORECASE)


def _is_allcaps_title(s):
    """Check if line is an ALL-CAPS title (not a scripture verse)."""
    stripped = s.strip()
    if not stripped:
        return False
    alpha = [c for c in stripped if c.isalpha()]
    if len(alpha) < 3:
        return False
    upper_count = sum(1 for c in alpha if c.isupper())
    return upper_count / len(alpha) > 0.8


def is_metadata_line(text):
    """Check if text is part of the sermon header metadata."""
    stripped = text.strip()
    if not stripped:
        return True
    if _no_re.match(stripped):
        return True
    if _sermon_delivery_re.match(stripped):
        return True
    if _by_re.match(stripped):
        return True
    if _at_re.match(stripped):
        return True
    if _date_continuation_re.match(stripped):
        return True
    if _intended_re.match(stripped):
        return True
    if _is_allcaps_title(stripped):
        return True
    return False


# ---------------------------------------------------------------------------
# ALL CAPS fix (from txt_to_ssml.py)
# ---------------------------------------------------------------------------

_KEEP_UPPER = {
    "LORD", "GOD", "JEHOVAH", "CHRIST", "JESUS", "HOLY", "KING",
    "AMEN", "HALLELUJAH", "SELAH", "I", "II", "III", "IV", "V",
}


def fix_allcaps_leading(text):
    """Fix ALL CAPS leading words: 'IT has been' -> 'It has been'."""
    # Fix paragraph-leading ALL CAPS words
    text = re.sub(
        r'(?m)^([A-Z]{2,})(\s)',
        lambda m: m.group(1).capitalize() + m.group(2),
        text,
    )

    # Fix mid-sentence ALL CAPS words (preserve intentional ones)
    def _fix_caps_word(m):
        word = m.group(1)
        if word in _KEEP_UPPER or len(word) <= 1:
            return m.group(0)
        return word.capitalize() + m.group(2)

    text = re.sub(r'\b([A-Z]{2,})\b(\s)', _fix_caps_word, text)
    return text


# ---------------------------------------------------------------------------
# Span/line processing
# ---------------------------------------------------------------------------

class FormattedSpan:
    """A text span with formatting info."""
    __slots__ = ('text', 'italic', 'bold', 'size', 'x0', 'font')

    def __init__(self, text, italic=False, bold=False, size=14.0, x0=0.0, font=''):
        self.text = text
        self.italic = italic
        self.bold = bold
        self.size = size
        self.x0 = x0
        self.font = font


class FormattedLine:
    """A line of text with its spans and position."""
    __slots__ = ('spans', 'x0', 'y0', 'y1')

    def __init__(self, spans, x0, y0, y1):
        self.spans = spans
        self.x0 = x0
        self.y0 = y0
        self.y1 = y1

    @property
    def text(self):
        return ''.join(s.text for s in self.spans)


def extract_page_lines(page, skip_headers=True, is_last_page=False):
    """Extract formatted lines from a PDF page.

    Returns a list of FormattedLine objects, skipping headers/footers.
    """
    d = page.get_text("dict")
    page_height = d.get("height", 792)
    lines = []

    for block in d["blocks"]:
        if block["type"] != 0:  # text block only
            continue

        for line_data in block["lines"]:
            bbox = line_data["bbox"]
            y0 = bbox[1]
            y1 = bbox[3]

            spans = []
            for span in line_data["spans"]:
                text = span["text"]
                if not text:
                    continue
                size = span["size"]
                flags = span["flags"]
                italic = bool(flags & 2)
                bold = bool(flags & 16)
                font = span.get("font", "")
                spans.append(FormattedSpan(
                    text=text, italic=italic, bold=bold,
                    size=size, x0=span["bbox"][0], font=font
                ))

            if spans:
                lines.append(FormattedLine(
                    spans=spans, x0=bbox[0], y0=y0, y1=y1
                ))

    if not lines:
        return []

    # Filter out header/footer lines (size <= 10pt, or in top/bottom margin)
    filtered = []
    for line in lines:
        line_text = line.text.strip()
        if not line_text:
            continue

        # Skip lines where all spans are <= ~10pt (headers/footers)
        # Use 10.5 threshold to account for slight font size variations
        max_size = max(s.size for s in line.spans if s.text.strip())
        if max_size <= 10.5:
            continue

        # Skip lines in the bottom margin area (footers)
        if line.y0 > page_height - 80:
            # Check if it looks like a footer
            if max_size <= 12 and (is_header_line(line_text) or
                                    is_promo_line(line_text) or
                                    re.match(r'^\d{1,4}\s*$', line_text)):
                continue

        filtered.append(line)

    if skip_headers:
        # Strip top header lines (first lines that match header patterns)
        result = []
        headers_skipped = 0
        for line in filtered:
            if headers_skipped < 3 and is_header_line(line.text.strip()):
                headers_skipped += 1
                continue
            result.append(line)
        filtered = result

    if is_last_page:
        # Strip promo block from end
        while filtered and is_promo_line(filtered[-1].text):
            filtered.pop()
        # Strip trailing blank-like lines
        while filtered and not filtered[-1].text.strip():
            filtered.pop()

    return filtered


# ---------------------------------------------------------------------------
# Paragraph assembly
# ---------------------------------------------------------------------------

def compute_normal_margin(all_lines):
    """Find the most common left x-position (the normal margin)."""
    from collections import Counter
    x_counts = Counter()
    for line in all_lines:
        # Round to nearest integer for grouping
        x_counts[round(line.x0)] += 1
    if not x_counts:
        return 54.0
    return x_counts.most_common(1)[0][0]


def compute_normal_line_spacing(all_lines):
    """Compute the median line spacing."""
    spacings = []
    for i in range(1, len(all_lines)):
        gap = all_lines[i].y0 - all_lines[i - 1].y0
        if 0 < gap < 30:  # reasonable line spacing range
            spacings.append(gap)
    if not spacings:
        return 16.0
    spacings.sort()
    return spacings[len(spacings) // 2]


def spans_to_html(spans):
    """Convert a list of FormattedSpan objects to an HTML string."""
    parts = []
    for span in spans:
        text = html.escape(span.text)
        if not text.strip():
            parts.append(text)
            continue
        if span.italic and span.bold:
            parts.append(f"<strong><em>{text}</em></strong>")
        elif span.italic:
            parts.append(f"<em>{text}</em>")
        elif span.bold:
            parts.append(f"<strong>{text}</strong>")
        else:
            parts.append(text)
    return ''.join(parts)


def merge_adjacent_tags(html_text):
    """Merge adjacent identical tags: </em><em>, </strong><strong>."""
    html_text = re.sub(r'</em>\s*<em>', '', html_text)
    html_text = re.sub(r'</strong>\s*<strong>', '', html_text)
    html_text = re.sub(r'</em></strong>\s*<strong><em>', '', html_text)
    return html_text


def rejoin_hyphenated_html(html_text):
    """Rejoin hyphenated words split across lines in HTML.

    Handles letter-hyphen + whitespace + letter (line break with space preserved).
    """
    html_text = re.sub(
        r'([a-z])-\s+([a-z])',
        r'\1\2',
        html_text,
    )
    return html_text


def _join_lines_spans(lines):
    """Join multiple lines' spans into a single span list, handling hyphenation.

    When the last span of a line ends with a lowercase letter + hyphen
    and the first span of the next line starts with a lowercase letter,
    the hyphen is removed and no space is inserted (dehyphenation).
    Otherwise a space is inserted between lines.
    """
    all_spans = []
    for i, line_spans in enumerate(lines):
        if i > 0 and all_spans and line_spans:
            # Check for line-break hyphenation
            last_text = all_spans[-1].text.rstrip()
            first_text = line_spans[0].text.lstrip()
            if (last_text and first_text
                    and len(last_text) >= 2
                    and last_text[-1] == '-'
                    and last_text[-2].islower()
                    and first_text[0].islower()):
                # Dehyphenate: remove trailing hyphen from last span
                all_spans[-1] = FormattedSpan(
                    text=all_spans[-1].text.rstrip()[:-1],
                    italic=all_spans[-1].italic,
                    bold=all_spans[-1].bold,
                    size=all_spans[-1].size,
                    x0=all_spans[-1].x0,
                    font=all_spans[-1].font,
                )
            else:
                all_spans.append(FormattedSpan(' ', italic=False, bold=False))
        all_spans.extend(line_spans)
    return all_spans


class Paragraph:
    """Accumulates lines into a paragraph with formatting."""

    def __init__(self, kind='body'):
        self.lines = []  # list of list of FormattedSpan
        self.kind = kind  # 'body', 'verse', 'blockquote', 'scripture'

    def add_line(self, spans):
        self.lines.append(spans)

    def to_html(self):
        if not self.lines:
            return ''

        if self.kind == 'scripture':
            all_spans = _join_lines_spans(self.lines)
            raw = spans_to_html(all_spans)
            raw = merge_adjacent_tags(raw)
            raw = rejoin_hyphenated_html(raw)
            raw = _apply_text_fixes(raw)
            return f'<h2>{raw.strip()}</h2>'

        if self.kind == 'verse':
            # Poetry/hymn — each line separated by <br>
            parts = []
            for line_spans in self.lines:
                raw = spans_to_html(line_spans)
                raw = merge_adjacent_tags(raw)
                raw = _apply_text_fixes(raw)
                parts.append(raw.strip())
            inner = '<br>\n'.join(parts)
            return f'<div class="verse">{inner}</div>'

        if self.kind == 'blockquote':
            all_spans = _join_lines_spans(self.lines)
            raw = spans_to_html(all_spans)
            raw = merge_adjacent_tags(raw)
            raw = rejoin_hyphenated_html(raw)
            raw = _apply_text_fixes(raw)
            return f'<blockquote>{raw.strip()}</blockquote>'

        # Normal body paragraph
        all_spans = _join_lines_spans(self.lines)
        raw = spans_to_html(all_spans)
        raw = merge_adjacent_tags(raw)
        raw = rejoin_hyphenated_html(raw)
        raw = _apply_text_fixes(raw)
        return f'<p>{raw.strip()}</p>'


def _apply_text_fixes(html_text):
    """Apply text cleanup: broken word rejoining, ALL CAPS fix."""
    # We need to operate on text content, not tags.
    # Strategy: extract text segments, fix them, reassemble.

    # Split into tags and text segments
    parts = re.split(r'(<[^>]+>)', html_text)
    result = []
    for part in parts:
        if part.startswith('<'):
            result.append(part)
        else:
            # Apply text fixes to non-tag content
            fixed = _rejoin_broken_words(part)
            fixed = fix_allcaps_leading(fixed)
            result.append(fixed)
    return ''.join(result)


# ---------------------------------------------------------------------------
# Main sermon extraction
# ---------------------------------------------------------------------------

def extract_sermon_html(doc, start_page, end_page):
    """Extract a single sermon's pages and produce HTML."""
    all_lines = []

    for pg_idx in range(start_page, end_page):
        if pg_idx >= len(doc):
            break
        page = doc[pg_idx]
        is_last = (pg_idx == end_page - 1)
        lines = extract_page_lines(page, skip_headers=True, is_last_page=is_last)
        all_lines.extend(lines)

    if not all_lines:
        return ''

    # Compute layout metrics
    normal_margin = compute_normal_margin(all_lines)
    normal_spacing = compute_normal_line_spacing(all_lines)
    indent_threshold = normal_margin + 20  # lines indented > 20pt from margin

    # Detect the high-indent threshold for verse/poetry (often at ~198pt)
    verse_threshold = normal_margin + 100

    # Phase 1: Skip the metadata title block
    # The metadata block consists of: ALL CAPS title, NO. NNNN, A SERMON...,
    # BY C. H. SPURGEON, AT THE METROPOLITAN TABERNACLE, etc.
    # It ends when we hit a scripture quote or body text.
    body_start = 0
    scripture_lines = []
    found_metadata = False

    for i, line in enumerate(all_lines):
        text = line.text.strip()
        if not text:
            continue

        # Check if this is a scripture quote line (starts with quote char)
        if text and text[0] in ('"', '\u201c', '\u201d', "'", '\u2018', '\u2019', '\u201e'):
            found_metadata = True
            # Collect scripture quote lines (typically 12-13pt, italic+bold,
            # indented from normal margin). Stop when we hit 14pt body text.
            j = i
            while j < len(all_lines):
                stext = all_lines[j].text.strip()
                if not stext:
                    j += 1
                    continue
                max_sz = max(s.size for s in all_lines[j].spans if s.text.strip())
                # Body text is ~14pt (often 13.98) — stop here
                if max_sz >= 13.5:
                    break
                # Scripture/reference lines (12-13pt, indented)
                scripture_lines.append(all_lines[j])
                j += 1
            body_start = j
            break

        # Check if we've moved past the metadata into body text
        if not is_metadata_line(text):
            # Check if it has body text characteristics (14pt, normal margin)
            max_sz = max(s.size for s in line.spans if s.text.strip())
            if max_sz >= 13.5 and round(line.x0) <= normal_margin + 20:
                body_start = i
                break

        found_metadata = True

    if not found_metadata:
        body_start = 0

    # Skip blank-ish lines after metadata
    while body_start < len(all_lines):
        text = all_lines[body_start].text.strip()
        if text:
            break
        body_start += 1

    body_lines = all_lines[body_start:]

    # Phase 2: Group lines into paragraphs
    paragraphs = []

    # Build scripture paragraph if we found one
    if scripture_lines:
        p = Paragraph('scripture')
        for line in scripture_lines:
            p.add_line(line.spans)
        paragraphs.append(p)

    if not body_lines:
        return _paragraphs_to_html(paragraphs)

    current_para = None
    prev_line = None

    for line in body_lines:
        text = line.text.strip()
        if not text:
            continue

        # Determine line type based on x-position
        x0 = round(line.x0)
        is_indented = x0 >= verse_threshold

        # Detect verse: indented lines with smaller font (often 12pt), or
        # short lines that are clearly poetry
        max_sz = max(s.size for s in line.spans if s.text.strip())
        is_verse_line = is_indented and max_sz <= 13

        # Check for paragraph break: significant y-gap from previous line
        is_new_para = False
        if prev_line is not None:
            y_gap = line.y0 - prev_line.y1
            if y_gap > normal_spacing * 1.5:
                # Large positive gap within same page = paragraph break
                is_new_para = True
            elif y_gap < -50:
                # Cross-page jump. Only treat as paragraph break if this line
                # has a first-line indent (new paragraph) or is verse/indented.
                # Lines starting at normal margin are likely continuations.
                if x0 > normal_margin + 10 or is_indented:
                    is_new_para = True
                # Otherwise: continuation of previous paragraph across page

        # Also treat a shift from verse back to body (or vice versa) as a break
        if current_para is not None:
            if is_verse_line and current_para.kind != 'verse':
                is_new_para = True
            elif not is_verse_line and current_para.kind == 'verse':
                is_new_para = True

        # Also: first-line indent (x0 slightly > margin, like 72 vs 54)
        # indicates a new paragraph when previous line was at normal margin
        is_first_line_indent = (
            indent_threshold > x0 > normal_margin + 10
            and not is_verse_line
            and max_sz >= 13.5
        )
        if is_first_line_indent and current_para is not None and current_para.kind == 'body':
            is_new_para = True

        if is_new_para or current_para is None:
            if current_para is not None:
                paragraphs.append(current_para)
            if is_verse_line:
                current_para = Paragraph('verse')
            elif is_indented:
                current_para = Paragraph('blockquote')
            else:
                current_para = Paragraph('body')

        current_para.add_line(line.spans)
        prev_line = line

    if current_para is not None:
        paragraphs.append(current_para)

    return _paragraphs_to_html(paragraphs)


def _paragraphs_to_html(paragraphs):
    """Convert list of Paragraph objects to HTML string."""
    parts = []
    for p in paragraphs:
        h = p.to_html()
        if h:
            parts.append(h)
    return '\n'.join(parts) + '\n'


# ---------------------------------------------------------------------------
# Volume processing
# ---------------------------------------------------------------------------

def extract_volume(pdf_path, vol_num, output_dir):
    """Extract all sermons from a single volume PDF as HTML."""
    doc = fitz.open(pdf_path)
    sermons = get_sermon_bookmarks(doc)

    if not sermons:
        print(f"  WARNING: No sermon bookmarks found in volume {vol_num}")
        return 0

    total_pages = len(doc)
    count = 0

    for i, (nums, sermon_title, start_page) in enumerate(sermons):
        # Determine page range
        if i + 1 < len(sermons):
            end_page = sermons[i + 1][2]
        else:
            end_page = total_pages

        # Extract HTML
        body_html = extract_sermon_html(doc, start_page, end_page)

        # Build output for each sermon number
        pascal_title = title_to_pascal(sermon_title)
        for num in nums:
            filename = f"{num:04d}_{pascal_title}.html"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(body_html)

            count += 1

    doc.close()
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract sermons from Spurgeon PDF volumes as HTML fragments."
    )
    parser.add_argument(
        "-v", "--volume",
        type=int,
        default=None,
        help="Process only this volume number (1-63). Default: all volumes.",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Directory containing PDF volumes (default: VolOrder/).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for output .html files (default: sermons_html/).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    input_dir = Path(args.input_dir) if args.input_dir else repo_root / "VolOrder"
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "sermons_html"

    if not input_dir.is_dir():
        print(f"ERROR: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.volume is not None:
        volumes = [args.volume]
    else:
        volumes = list(range(1, 64))

    total_sermons = 0
    for vol in volumes:
        pdf_name = f"chsbm{vol:02d}.pdf"
        pdf_path = input_dir / pdf_name
        if not pdf_path.is_file():
            print(f"WARNING: {pdf_name} not found, skipping.")
            continue

        print(f"Processing volume {vol:2d} ({pdf_name})...", end=" ", flush=True)
        try:
            count = extract_volume(str(pdf_path), vol, str(output_dir))
            print(f"{count} sermons extracted.")
            total_sermons += count
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nDone. {total_sermons} sermon files written to {output_dir}/")


if __name__ == "__main__":
    main()
