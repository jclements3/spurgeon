#!/usr/bin/env python3
"""Extract individual sermons from Spurgeon's Metropolitan Tabernacle Pulpit PDFs.

Reads PDF volumes from VolOrder/, extracts text per sermon using bookmarks,
strips headers/footers, cleans up PDF artifacts, and writes one .txt file
per sermon to sermons/.
"""

import argparse
import os
import re
import sys
from pathlib import Path

from pypdf import PdfReader


# ---------------------------------------------------------------------------
# Word-rejoining dictionary
# ---------------------------------------------------------------------------

def _load_wordset():
    """Load a set of lowercase English words from the system dictionary.

    Excludes proper-noun-only entries (words that only appear capitalized
    in the dictionary, like 'Thea') to avoid false positives when rejoining
    broken words.
    """
    # First pass: collect all forms of each word
    raw_entries = {}  # lowercase -> list of original forms
    dict_path = "/usr/share/dict/words"
    try:
        with open(dict_path, "r") as f:
            for line in f:
                w = line.strip()
                if w:
                    key = w.lower()
                    if key not in raw_entries:
                        raw_entries[key] = []
                    raw_entries[key].append(w)
    except FileNotFoundError:
        pass

    # Only include words that have at least one lowercase form,
    # i.e., exclude entries that are ONLY proper nouns (capitalized-only).
    words = set()
    for key, forms in raw_entries.items():
        has_lowercase = any(f == f.lower() or f == key for f in forms
                           if f[0].islower())
        if has_lowercase:
            words.add(key)
    # Add common words that may be missing from the system dictionary,
    # including proper nouns frequently used in sermon text.
    extras = {
        "the", "that", "this", "than", "them", "then", "there", "therefore",
        "these", "those", "through", "thought", "though", "throughout",
        "gospel", "father", "mother", "brother", "sister", "attention",
        "contemplation", "writing", "loftiest", "magnify", "suffering",
        "sufferings", "scripture", "scriptures", "consequence", "condition",
        "beautiful", "wonderful", "faithful", "thankful", "gracious",
        "precious", "salvation", "congregation", "manifestation", "revelation",
        "declaration", "consolation", "imagination", "consideration",
        # Proper nouns common in sermon text (excluded by proper-noun filter)
        "christ", "jesus", "isaiah", "jeremiah", "ezekiel", "daniel",
        "matthew", "tabernacle", "jerusalem", "israel", "israelites",
        "spurgeon", "calvary", "bethlehem", "nazareth", "galilee",
        "christian", "christians", "christianity", "pharisee", "pharisees",
    }
    words.update(extras)
    return words

WORDSET = _load_wordset()

# Very short fragments (1-2 chars) that are legitimate standalone words
# and should NOT be joined with the next word.
SHORT_REAL_WORDS = {
    "a", "i", "am", "an", "as", "at", "be", "by", "do", "go", "ha", "he",
    "if", "in", "is", "it", "me", "my", "no", "of", "oh", "ok", "on", "or",
    "ox", "so", "to", "up", "us", "we",
}


# ---------------------------------------------------------------------------
# Bookmark helpers
# ---------------------------------------------------------------------------

def flatten_bookmarks(outlines, reader):
    """Recursively flatten nested PDF bookmark outlines."""
    result = []
    for item in outlines:
        if isinstance(item, list):
            result.extend(flatten_bookmarks(item, reader))
        else:
            title = item.title if hasattr(item, "title") else item.get("/Title", "")
            try:
                page_num = reader.get_destination_page_number(item)
            except Exception:
                page_num = None
            result.append((title.strip(), page_num))
    return result


# Regex to parse bookmark titles.  Handles many variants:
#   "1 - The Immutability of God."
#   "7, 8 - Christ Crucified"
#   "3O - The Power of the Holy Spirit"  (letter O for zero typo)
#   "165 The Warning Neglected."          (no dash separator)
#   "3387 \rA New Year's Benediction"     (carriage return separator)
#   "1451A - "This Year Also""            (letter suffix on number)
#   "26  - The Two Effects"               (extra spaces)
BOOKMARK_RE = re.compile(
    r"^(\d[\d\s,A-Z]*?)\s*[-–\r]\s*(.+)$"
)
# Fallback for volumes that omit the dash entirely: "165 The Warning..."
BOOKMARK_RE_NODASH = re.compile(
    r"^(\d[\d\s,A-Z]*?)\s{1,4}([A-Z\"\'].+)$"
)


def parse_bookmark_title(title):
    """Return (list_of_sermon_numbers, sermon_title) or (None, None) if not a sermon."""
    # Clean up control characters
    title = title.replace("\r", " ").replace("\n", " ").strip()

    m = BOOKMARK_RE.match(title)
    if not m:
        m = BOOKMARK_RE_NODASH.match(title)
    if not m:
        return None, None

    num_part = m.group(1).replace("O", "0")  # fix letter-O typos
    title_part = m.group(2).strip().rstrip(".")

    # Parse potentially comma-separated numbers like "7, 8" or "39, 40"
    # Also handle letter suffixes like "1451A" -> 1451
    nums = []
    for tok in num_part.split(","):
        tok = tok.strip()
        # Strip trailing letter suffix (A, B, etc.)
        tok_digits = re.sub(r"[A-Za-z]+$", "", tok)
        if tok_digits.isdigit():
            nums.append(int(tok_digits))
    if not nums:
        return None, None
    return nums, title_part


def title_to_pascal(title):
    """Convert a sermon title to PascalCase for filenames.

    Keeps only alphanumeric characters, drops punctuation, capitalizes each word.
    """
    # Replace hyphens/dashes with spaces so hyphenated words become separate
    t = re.sub(r"[—–-]", " ", title)
    # Keep only word characters and spaces
    t = re.sub(r"[^\w\s]", "", t)
    # Split on whitespace and capitalize
    parts = [w.capitalize() for w in t.split() if w]
    return "".join(parts)


# ---------------------------------------------------------------------------
# Page text cleaning
# ---------------------------------------------------------------------------

# Patterns that appear in the first two header lines
HEADER_PATTERNS = [
    re.compile(r"Sermon\s*#\s*\d+", re.IGNORECASE),
    re.compile(r"(New Park Street Pulpit|Metropolitan Tabernacle Pulpit)", re.IGNORECASE),
    re.compile(r"Volume\s*\d+", re.IGNORECASE),
    re.compile(r"www\.spurgeongems\.org", re.IGNORECASE),
]

# Promo block at end of last page
PROMO_MARKERS = [
    "Adapted from The C. H. Spurgeon Collection",
    "PRAY THE HOLY SPIRIT",
    "www.spurgeongems.org",
    "C. H. Spurgeon sermons in Modern English",
    "Spanish translations",
    "By the grace of God",
    "WILL USE THIS SERMON",
    "TO BRING MANY TO A SAVING KNOWLEDGE",
]


def is_header_line(line):
    """Check if a line matches known header patterns."""
    stripped = line.strip()
    if not stripped:
        return False
    # A line that is just a page number (1-4 digits, possibly with spaces)
    if re.match(r"^\d{1,4}\s*$", stripped):
        return True
    # Lines matching header patterns
    matches = sum(1 for p in HEADER_PATTERNS if p.search(stripped))
    return matches >= 1


def is_promo_line(line):
    """Check if a line belongs to the trailing promo block."""
    stripped = line.strip()
    if not stripped:
        return False  # blank lines between promo lines handled by context
    for marker in PROMO_MARKERS:
        if marker.lower() in stripped.lower():
            return True
    return False


def strip_headers(lines):
    """Remove header lines from the top of a page's text.

    The pattern is: 2 header lines, then 0-2 page-number-only lines.
    """
    idx = 0
    # Strip up to 2 header lines
    headers_found = 0
    while idx < len(lines) and headers_found < 2:
        if not lines[idx].strip():
            idx += 1
            continue
        if is_header_line(lines[idx]):
            idx += 1
            headers_found += 1
        else:
            break

    # Strip duplicated page number lines that follow headers
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        if re.match(r"^\d{1,4}\s*$", stripped):
            idx += 1
        else:
            break

    return lines[idx:]


def strip_promo_block(lines):
    """Remove the trailing promo/ad block from the last page."""
    # Walk backwards to find where the promo starts
    # Once we hit the first promo line going backwards, keep removing until
    # we find real content.
    end = len(lines)
    # First, trim trailing blank lines
    while end > 0 and not lines[end - 1].strip():
        end -= 1

    # Walk backwards removing promo lines and blanks between them
    while end > 0:
        stripped = lines[end - 1].strip()
        if not stripped or is_promo_line(lines[end - 1]):
            end -= 1
        else:
            break

    return lines[:end]


# ---------------------------------------------------------------------------
# Text cleanup for PDF extraction artifacts
# ---------------------------------------------------------------------------

def _rejoin_broken_words(line):
    """Fix mid-word spaces caused by PDF column extraction.

    Scans for patterns like 'ther efore', 'th ought', 'contemplat ion'
    where a word was split with a space inserted.  Uses a dictionary
    to verify that joining produces a real word and that the left
    fragment is NOT a common standalone word (or if it is, that the
    right fragment is NOT a standalone word and the combined IS).
    """
    # Tokenize the line preserving whitespace structure.
    # Split into tokens of (word, trailing_whitespace) pairs.
    # We'll process adjacent word pairs and decide whether to join.
    #
    # We use a simple approach: split on single spaces and try to
    # rejoin adjacent lowercase fragments.

    # Split into "tokens" preserving all spacing.
    # re.split with a capturing group alternates: [word, sep, word, sep, ...]
    tokens = re.split(r'( +)', line)
    # tokens at even indices are word segments, odd indices are spaces.

    if len(tokens) < 3:
        return line

    # Work on even-indexed (word) tokens, checking if adjacent pairs
    # separated by a single space should be joined.
    # Build a new token list.
    result = []
    i = 0
    while i < len(tokens):
        if i % 2 == 0:
            # This is a word token.  Check if it should be joined with
            # the next word token (at i+2) across a single-space separator (i+1).
            if (
                i + 2 < len(tokens)
                and tokens[i + 1] == ' '  # exactly one space
                and tokens[i]
                and tokens[i + 2]
                and tokens[i][-1].islower()
                and tokens[i + 2][0].islower()
            ):
                if _should_join_fragments(tokens[i], tokens[i + 2]):
                    # Join: merge current word + next word, skip the space.
                    # Preserve any trailing punctuation on the right token.
                    tokens[i + 2] = tokens[i] + tokens[i + 2]
                    # Don't append current token or space; advance to i+2
                    i += 2
                    continue

        result.append(tokens[i])
        i += 1

    return ''.join(result)


def _should_join_fragments(left, right):
    """Decide whether two space-separated fragments should be joined.

    Returns True if they look like a broken word, False if they look
    like legitimate separate words.
    """
    # Extract the alphabetic core of each fragment, ignoring leading/
    # trailing punctuation on the right side (e.g., "her." -> "her").
    # If left contains non-alpha characters (apostrophes, hyphens, etc.)
    # it's likely a real word with punctuation, not a broken fragment.
    # e.g., "God's" + "elect" should NOT be joined.
    if not left.isalpha():
        return False

    # Right may have trailing punctuation (period, comma, semicolon, etc.)
    right_alpha = right.rstrip(".,;:!?\"')]}—–-")
    if not right_alpha or not right_alpha.isalpha():
        return False

    left_lower = left.lower()
    right_lower = right_alpha.lower()
    combined_lower = (left + right_alpha).lower()

    # Case 1: Left fragment is NOT a real word
    if left_lower not in WORDSET:
        # If combined IS a real word, join
        if combined_lower in WORDSET:
            return True
        return False

    # Case 2: Left IS a real word, right IS a real word
    if right_lower in WORDSET:
        # Both fragments are real words.  Usually these are legitimate
        # two-word sequences.  But PDF breaks can produce things like
        # "Fat her" (Father), "go spel" (gospel) where both halves
        # happen to be words.  Join if:
        #   - combined is also a word, AND
        #   - at least one fragment is very short (<=3 chars), suggesting
        #     it's a fragment rather than a real word in context
        if combined_lower in WORDSET and (len(left_lower) <= 3 or len(right_lower) <= 3):
            return True
        return False

    # Case 3: Left IS a real word, right is NOT a real word
    # This handles cases like "Fat her" (Fat=word, her=word -> Case 2 says no)
    # and "go spel" (go=word, spel=not a word)
    # If combined is a real word, join
    if combined_lower in WORDSET:
        return True

    return False


def clean_text(text):
    """Clean up common PDF text extraction artifacts."""
    lines = text.split("\n")

    # Rejoin hyphenated words split across lines.
    # Only join when the hyphen looks like a line-break hyphenation
    # (lowercase letter before hyphen, lowercase letter starting next line).
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            i + 1 < len(lines)
            and line.rstrip().endswith("-")
            and len(line.rstrip()) >= 2
            and line.rstrip()[-2].islower()
            and lines[i + 1].lstrip()
            and lines[i + 1].lstrip()[0].islower()
        ):
            # Remove the trailing hyphen and join with next line
            dehyphenated = line.rstrip()[:-1]
            next_line = lines[i + 1]
            result.append(dehyphenated + next_line.lstrip())
            i += 2
        else:
            result.append(line)
            i += 1

    # Fix mid-word spaces from PDF column extraction
    cleaned = [_rejoin_broken_words(line) for line in result]

    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# First-page title block handling
# ---------------------------------------------------------------------------

def strip_title_block(lines):
    """Remove the sermon header metadata block from the first page.

    The header block typically looks like:
        THE IMMUTABILITY OF GOD
        NO. 1

        A SERMON DELIVERED ON SABBATH MORNING, JANUARY 7, 1855,
        BY THE REV. C. H. SPURGEON,
        AT NEW PARK STREET CHAPEL, SOUTHWARK.

        "I am the Lord, I change not; ..."
        Malachi 3:6.

    We strip everything from the ALL-CAPS title through the delivery
    metadata (A SERMON..., BY..., AT...).  We KEEP the scripture
    quotation and everything after it.

    The title and sermon number are already written as the first two
    lines of the output file by the caller, so this info is not lost.
    """
    if not lines:
        return lines

    # Strategy: scan forward looking for the end of the metadata block.
    # The metadata block contains:
    #   - ALL CAPS title line(s)
    #   - "NO. NNNN" line
    #   - blank lines
    #   - "A SERMON DELIVERED ON..." / "A SERMON PUBLISHED ON..." etc.
    #   - "BY ..." line
    #   - "AT THE METROPOLITAN TABERNACLE..." line
    #   - blank lines
    # After that comes the scripture verse (starts with " or various quote chars)
    # or the body text.

    # Patterns that identify header/metadata lines
    no_re = re.compile(r"^\s*NO\.\s*\d+", re.IGNORECASE)
    sermon_delivery_re = re.compile(
        r"^\s*A\s+SERMON", re.IGNORECASE
    )
    by_re = re.compile(
        r"^\s*(BY\s+(THE\s+REV\.\s+)?C\.?\s*H\.?\s*SPURGEON|DELIVERED\s+BY|BY\s+C\.\s*H)",
        re.IGNORECASE,
    )
    at_re = re.compile(
        r"^\s*AT\s+(THE\s+)?(METROPOLITAN\s+TABERNACLE|NEW\s+PARK\s+STREET|EXETER\s+HALL|SURREY)",
        re.IGNORECASE,
    )
    # Date/location continuation lines (e.g., "ON THURSDAY EVENING, AUGUST 19, 1876.")
    date_continuation_re = re.compile(
        r"^\s*ON\s+(SUNDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|LORD)",
        re.IGNORECASE,
    )
    # Intended for reading line
    intended_re = re.compile(
        r"^\s*INTENDED\s+FOR\s+READING",
        re.IGNORECASE,
    )

    def is_allcaps_title(s):
        """Check if line is an ALL-CAPS title (not a scripture verse)."""
        stripped = s.strip()
        if not stripped:
            return False
        # Must have at least some alpha chars
        alpha = [c for c in stripped if c.isalpha()]
        if len(alpha) < 3:
            return False
        # Check if mostly uppercase (allow punctuation, numbers)
        upper_count = sum(1 for c in alpha if c.isupper())
        return upper_count / len(alpha) > 0.8

    def is_metadata_line(s):
        """Check if a line is part of the sermon header metadata."""
        stripped = s.strip()
        if not stripped:
            return True  # blank lines within the block
        if no_re.match(stripped):
            return True
        if sermon_delivery_re.match(stripped):
            return True
        if by_re.match(stripped):
            return True
        if at_re.match(stripped):
            return True
        if date_continuation_re.match(stripped):
            return True
        if intended_re.match(stripped):
            return True
        # ALL CAPS lines in the header (title, location, etc.)
        if is_allcaps_title(stripped):
            return True
        return False

    # Scan forward through metadata lines
    idx = 0
    # We require at least one recognizable metadata line to strip anything
    found_metadata = False

    while idx < len(lines):
        stripped = lines[idx].strip()

        # Stop at scripture quote (starts with quote character)
        if stripped and stripped[0] in ('"', '\u201c', '\u201d', "'", '\u2018', '\u2019'):
            found_metadata = True
            break

        # Stop if we hit a line that looks like body text (starts lowercase,
        # or is a long mixed-case line that isn't metadata)
        if stripped and not is_metadata_line(lines[idx]):
            break

        if stripped:
            found_metadata = True
        idx += 1

    if not found_metadata:
        return lines

    # Skip any remaining blank lines between metadata and body
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    return lines[idx:]


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_volume(pdf_path, vol_num, output_dir):
    """Extract all sermons from a single volume PDF."""
    reader = PdfReader(pdf_path)
    bookmarks = flatten_bookmarks(reader.outline, reader)

    # Filter to sermon bookmarks only
    sermons = []
    for title, page_num in bookmarks:
        if page_num is None:
            continue
        nums, sermon_title = parse_bookmark_title(title)
        if nums is None:
            continue
        sermons.append((nums, sermon_title, page_num))

    if not sermons:
        print(f"  WARNING: No sermon bookmarks found in volume {vol_num}")
        return 0

    total_pages = len(reader.pages)
    count = 0

    for i, (nums, sermon_title, start_page) in enumerate(sermons):
        # Determine page range
        if i + 1 < len(sermons):
            end_page = sermons[i + 1][2]  # exclusive
        else:
            end_page = total_pages  # last sermon goes to end of PDF

        # Extract text from all pages in range
        page_texts = []
        for pg in range(start_page, end_page):
            raw = reader.pages[pg].extract_text()
            if not raw:
                continue
            lines = raw.split("\n")

            # Strip headers (all pages)
            lines = strip_headers(lines)

            # Strip promo block (last page of sermon only)
            if pg == end_page - 1:
                lines = strip_promo_block(lines)

            page_texts.append("\n".join(lines))

        body = "\n".join(page_texts)

        # Strip the sermon header metadata block (title, NO., delivery info)
        body_lines = body.split("\n")
        body_lines = strip_title_block(body_lines)
        body = "\n".join(body_lines)

        body = clean_text(body)

        # Build output for each sermon number
        pascal_title = title_to_pascal(sermon_title)
        for num in nums:
            filename = f"{num:04d}_{pascal_title}.txt"
            filepath = os.path.join(output_dir, filename)

            content = f"{sermon_title}\n{num}\n\n{body}\n"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            count += 1

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Extract sermons from Spurgeon PDF volumes."
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
        help="Directory containing PDF volumes (default: VolOrder/ relative to repo root).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for output .txt files (default: sermons/ relative to repo root).",
    )
    args = parser.parse_args()

    # Resolve paths relative to the repo root (parent of scripts/)
    repo_root = Path(__file__).resolve().parent.parent
    input_dir = Path(args.input_dir) if args.input_dir else repo_root / "VolOrder"
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "sermons"

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

    print(f"\nDone. {total_sermons} sermon files written to {output_dir}/")


if __name__ == "__main__":
    main()
