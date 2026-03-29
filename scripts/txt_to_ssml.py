#!/usr/bin/env python3
"""Convert plain text sermon files to SSML optimized for ElevenLabs TTS (Daniel voice).

Transformations applied in order:
  1. XML-escape special characters
  2. Scripture reference expansion to <sub> tags
  3. Biblical name pronunciation via <phoneme> tags
  4. Sentence/paragraph structuring with <s>, <p>, <break> tags
  5. Title and sermon number formatting
"""

import argparse
import os
import re
import sys


# ---------------------------------------------------------------------------
# A. Scripture Reference Expansion
# ---------------------------------------------------------------------------

BOOK_ABBREVIATIONS = {
    # Old Testament
    "Gen.": "Genesis",
    "Ex.": "Exodus",
    "Exod.": "Exodus",
    "Lev.": "Leviticus",
    "Num.": "Numbers",
    "Deut.": "Deuteronomy",
    "Josh.": "Joshua",
    "Judg.": "Judges",
    "Ruth": "Ruth",
    "1 Sam.": "First Samuel",
    "2 Sam.": "Second Samuel",
    "1 Kin.": "First Kings",
    "2 Kin.": "Second Kings",
    "1 Kings": "First Kings",
    "2 Kings": "Second Kings",
    "1 Chron.": "First Chronicles",
    "2 Chron.": "Second Chronicles",
    "Ezra": "Ezra",
    "Neh.": "Nehemiah",
    "Est.": "Esther",
    "Esth.": "Esther",
    "Job": "Job",
    "Ps.": "Psalms",
    "Psa.": "Psalms",
    "Psalm": "Psalm",
    "Prov.": "Proverbs",
    "Eccl.": "Ecclesiastes",
    "Eccles.": "Ecclesiastes",
    "Song": "Song of Solomon",
    "Sol.": "Song of Solomon",
    "Isa.": "Isaiah",
    "Jer.": "Jeremiah",
    "Lam.": "Lamentations",
    "Ezek.": "Ezekiel",
    "Dan.": "Daniel",
    "Hos.": "Hosea",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obad.": "Obadiah",
    "Jon.": "Jonah",
    "Jonah": "Jonah",
    "Mic.": "Micah",
    "Nah.": "Nahum",
    "Hab.": "Habakkuk",
    "Zeph.": "Zephaniah",
    "Hag.": "Haggai",
    "Zech.": "Zechariah",
    "Mal.": "Malachi",
    # New Testament
    "Matt.": "Matthew",
    "Mark": "Mark",
    "Luke": "Luke",
    "John": "John",
    "Acts": "Acts",
    "Rom.": "Romans",
    "1 Cor.": "First Corinthians",
    "2 Cor.": "Second Corinthians",
    "Gal.": "Galatians",
    "Eph.": "Ephesians",
    "Phil.": "Philippians",
    "Col.": "Colossians",
    "1 Thess.": "First Thessalonians",
    "2 Thess.": "Second Thessalonians",
    "1 Tim.": "First Timothy",
    "2 Tim.": "Second Timothy",
    "Tit.": "Titus",
    "Titus": "Titus",
    "Philem.": "Philemon",
    "Heb.": "Hebrews",
    "Jas.": "James",
    "James": "James",
    "1 Pet.": "First Peter",
    "2 Pet.": "Second Peter",
    "1 John": "First John",
    "2 John": "Second John",
    "3 John": "Third John",
    "Jude": "Jude",
    "Rev.": "Revelation",
    # Full names (unabbreviated) that might appear
    "Genesis": "Genesis",
    "Exodus": "Exodus",
    "Leviticus": "Leviticus",
    "Numbers": "Numbers",
    "Deuteronomy": "Deuteronomy",
    "Joshua": "Joshua",
    "Judges": "Judges",
    "Nehemiah": "Nehemiah",
    "Esther": "Esther",
    "Proverbs": "Proverbs",
    "Ecclesiastes": "Ecclesiastes",
    "Isaiah": "Isaiah",
    "Jeremiah": "Jeremiah",
    "Lamentations": "Lamentations",
    "Ezekiel": "Ezekiel",
    "Daniel": "Daniel",
    "Hosea": "Hosea",
    "Obadiah": "Obadiah",
    "Micah": "Micah",
    "Nahum": "Nahum",
    "Habakkuk": "Habakkuk",
    "Zephaniah": "Zephaniah",
    "Haggai": "Haggai",
    "Zechariah": "Zechariah",
    "Malachi": "Malachi",
    "Matthew": "Matthew",
    "Romans": "Romans",
    "Galatians": "Galatians",
    "Ephesians": "Ephesians",
    "Philippians": "Philippians",
    "Colossians": "Colossians",
    "Hebrews": "Hebrews",
    "Revelation": "Revelation",
}

# Build regex pattern for book names, longest first to avoid partial matches
_book_names_sorted = sorted(BOOK_ABBREVIATIONS.keys(), key=len, reverse=True)
_book_pattern = "|".join(re.escape(b) for b in _book_names_sorted)

# Full scripture reference pattern:
#   Book  chapter:verse(-verse)(, verse(-verse))*
#   or Book chapter (chapter-only)
# Optional leading "v.", "vs.", "vv." handled separately
_SCRIPTURE_RE = re.compile(
    r"(?<!\w)"                          # not preceded by word char
    r"((?:[123]\s)?"                    # optional numbered book prefix
    r"(?:" + _book_pattern + r"))"      # book name
    r"\s+"                              # space
    r"(\d+)"                            # chapter number
    r"(?:"                              # optional verse part
    r":(\d+)"                           # colon + first verse
    r"(?:\s*[-\u2013]\s*(\d+))?"        # optional dash + end verse
    r"((?:\s*,\s*\d+(?:\s*[-\u2013]\s*\d+)?)*)"  # optional additional verses
    r")?"
    r"(?!\w)"                           # not followed by word char
)

# Verse-prefix references: "v. 5", "vs. 3-4", "vv. 1, 3, 5"
_VERSE_PREFIX_RE = re.compile(
    r"\b(vv?s?\.)\s*"
    r"(\d+)"
    r"(?:\s*[-\u2013]\s*(\d+))?"
    r"((?:\s*,\s*\d+(?:\s*[-\u2013]\s*\d+)?)*)"
)


def _format_verse_part(start, end, extra):
    """Build the spoken verse portion of a scripture reference."""
    parts = []
    if end:
        parts.append(f"verses {start} through {end}")
    else:
        parts.append(f"verse {start}")

    if extra:
        # Parse additional verse groups like ", 29" or ", 3-5"
        for m in re.finditer(r"(\d+)(?:\s*[-\u2013]\s*(\d+))?", extra):
            v1, v2 = m.group(1), m.group(2)
            if v2:
                parts.append(f"{v1} through {v2}")
            else:
                parts.append(v1)
        # Rebuild as a combined string
        if len(parts) > 1:
            combined = parts[0]
            # If the first part was "verse X", upgrade to "verses X"
            combined = combined.replace("verse ", "verses ", 1)
            combined += ", " + ", ".join(parts[1:])
            return combined

    return parts[0]


def _scripture_replace(match):
    """Replace a scripture reference match with a <sub> tag."""
    original = match.group(0)
    book_raw = match.group(1)
    chapter = match.group(2)
    verse_start = match.group(3)
    verse_end = match.group(4)
    extra_verses = match.group(5) if match.lastindex >= 5 else ""

    book_full = BOOK_ABBREVIATIONS.get(book_raw.strip())
    if not book_full:
        return original

    if verse_start:
        verse_spoken = _format_verse_part(verse_start, verse_end, extra_verses)
        alias = f"{book_full} chapter {chapter}, {verse_spoken}"
    else:
        alias = f"{book_full} chapter {chapter}"

    return f'<sub alias="{alias}">{original}</sub>'


def expand_scripture_references(text):
    """Expand abbreviated and full scripture references to SSML <sub> tags."""
    text = _SCRIPTURE_RE.sub(_scripture_replace, text)
    return text


# ---------------------------------------------------------------------------
# B. Biblical Name Pronunciations
# ---------------------------------------------------------------------------

# (ipa_string, case_sensitive)
BIBLICAL_PRONUNCIATIONS = {
    "Job": ("dʒoʊb", True),
    "Naomi": ("neɪˈoʊ.mi", False),
    "Habakkuk": ("həˈbæk.ək", False),
    "Nahum": ("ˈneɪ.həm", False),
    "Malachi": ("ˈmæl.ə.kaɪ", False),
    "Nehemiah": ("ˌniː.əˈmaɪ.ə", False),
    "Deuteronomy": ("ˌdjuː.təˈrɒn.ə.mi", False),
    "Ecclesiastes": ("ɪˌkliː.ziˈæs.tiːz", False),
    "Laodicea": ("ˌleɪ.ɒd.ɪˈsiː.ə", False),
    "Gethsemane": ("ɡɛθˈsɛm.ə.ni", False),
    "Calvary": ("ˈkæl.və.ri", False),
    "Pharisee": ("ˈfær.ɪ.siː", False),
    "Pharisees": ("ˈfær.ɪ.siːz", False),
    "Sadducees": ("ˈsæd.juː.siːz", False),
    "Hezekiah": ("ˌhɛz.ɪˈkaɪ.ə", False),
    "Josiah": ("dʒoʊˈsaɪ.ə", False),
    "Elijah": ("ɪˈlaɪ.dʒə", False),
    "Elisha": ("ɪˈlaɪ.ʃə", False),
    "Isaiah": ("aɪˈzeɪ.ə", False),
    "Jeremiah": ("ˌdʒɛr.ɪˈmaɪ.ə", False),
    "Ezekiel": ("ɪˈziː.ki.əl", False),
    "Obadiah": ("ˌoʊ.bəˈdaɪ.ə", False),
    "Zephaniah": ("ˌzɛf.əˈnaɪ.ə", False),
    "Zechariah": ("ˌzɛk.əˈraɪ.ə", False),
    "Haggai": ("ˈhæɡ.aɪ", False),
    "Micah": ("ˈmaɪ.kə", False),
    "Hosea": ("hoʊˈzeɪ.ə", False),
    "Levi": ("ˈliː.vaɪ", False),
    "Levite": ("ˈliː.vaɪt", False),
    "Levites": ("ˈliː.vaɪts", False),
    "Leviticus": ("lɪˈvɪt.ɪ.kəs", False),
    "Sinai": ("ˈsaɪ.naɪ", False),
    "Horeb": ("ˈhɔː.rɛb", False),
    "Canaan": ("ˈkeɪ.nən", False),
    "Canaanite": ("ˈkeɪ.nə.naɪt", False),
    "Bethlehem": ("ˈbɛθ.lɪ.hɛm", False),
    "Nazareth": ("ˈnæz.ə.rɛθ", False),
    "Galilee": ("ˈɡæl.ɪ.liː", False),
    "Capernaum": ("kəˈpɜːr.neɪ.əm", False),
    "Corinth": ("ˈkɒr.ɪnθ", False),
    "Corinthians": ("kɒˈrɪn.θi.ənz", False),
    "Ephesus": ("ˈɛf.ɪ.səs", False),
    "Ephesians": ("ɪˈfiː.ʒənz", False),
    "Galatians": ("ɡəˈleɪ.ʃənz", False),
    "Philippians": ("fɪˈlɪp.i.ənz", False),
    "Colossians": ("kəˈlɒʃ.ənz", False),
    "Thessalonians": ("ˌθɛs.əˈloʊ.ni.ənz", False),
    "Philemon": ("fɪˈliː.mən", False),
    "Titus": ("ˈtaɪ.təs", False),
    "Hebrews": ("ˈhiː.bruːz", False),
    "Nicodemus": ("ˌnɪk.əˈdiː.məs", False),
    "Lazarus": ("ˈlæz.ə.rəs", False),
    "Barabbas": ("bəˈræb.əs", False),
    "Pontius": ("ˈpɒn.ʃəs", False),
    "Pilate": ("ˈpaɪ.lət", False),
    "Pharaoh": ("ˈfɛr.oʊ", False),
    "Moses": ("ˈmoʊ.zɪz", False),
    "Aaron": ("ˈɛr.ən", False),
    "Abraham": ("ˈeɪ.brə.hæm", False),
    "Isaac": ("ˈaɪ.zək", False),
    "Jacob": ("ˈdʒeɪ.kəb", False),
    "Esau": ("ˈiː.sɔː", False),
    "Boaz": ("ˈboʊ.æz", False),
    "Rahab": ("ˈreɪ.hæb", False),
    "Samson": ("ˈsæm.sən", False),
    "Delilah": ("dɪˈlaɪ.lə", False),
    "Goliath": ("ɡəˈlaɪ.əθ", False),
    "Absalom": ("ˈæb.sə.ləm", False),
    "Bathsheba": ("bæθˈʃiː.bə", False),
    "Melchizedek": ("mɛlˈkɪz.ɪ.dɛk", False),
    "Nebuchadnezzar": ("ˌnɛb.jʊ.kədˈnɛz.ər", False),
    "Belshazzar": ("bɛlˈʃæz.ər", False),
    "Cyrus": ("ˈsaɪ.rəs", False),
    "Mordecai": ("ˈmɔːr.dɪ.kaɪ", False),
    "Esther": ("ˈɛs.tər", False),
    "Jehoshaphat": ("dʒɪˈhɒʃ.ə.fæt", False),
    "Rehoboam": ("ˌriː.əˈboʊ.əm", False),
    "Jeroboam": ("ˌdʒɛr.əˈboʊ.əm", False),
    "Manasseh": ("məˈnæs.ə", False),
    "Ananias": ("ˌæn.əˈnaɪ.əs", False),
    "Sapphira": ("səˈfaɪ.rə", False),
    "Barnabas": ("ˈbɑːr.nə.bəs", False),
    "Apollos": ("əˈpɒl.oʊs", False),
    "Aquila": ("ˈæk.wɪ.lə", False),
    "Priscilla": ("prɪˈsɪl.ə", False),
    "Gamaliel": ("ɡəˈmeɪ.li.əl", False),
    "Beelzebub": ("biˈɛl.zɪ.bʌb", False),
    "Armageddon": ("ˌɑːr.məˈɡɛd.ən", False),
    "Maranatha": ("ˌmær.əˈnæθ.ə", False),
    "Hallelujah": ("ˌhæl.ɪˈluː.jə", False),
    "Selah": ("ˈsiː.lə", False),
    "Jehovah": ("dʒɪˈhoʊ.və", False),
    "Yahweh": ("ˈjɑː.weɪ", False),
    "Arminian": ("ɑːrˈmɪn.i.ən", False),
    "Arminianism": ("ɑːrˈmɪn.i.ən.ɪz.əm", False),
    "Calvinism": ("ˈkæl.vɪn.ɪz.əm", False),
    "Calvinist": ("ˈkæl.vɪn.ɪst", False),
    "Pelagian": ("pɪˈleɪ.dʒi.ən", False),
    "Socinian": ("soʊˈsɪn.i.ən", False),
    "Antinomian": ("ˌæn.tɪˈnoʊ.mi.ən", False),
}

# Pre-compile regex patterns for each biblical name.
# Sort by length descending so longer names match first (e.g., "Pharisees"
# before "Pharisee").
_PRONUNCIATION_PATTERNS = []
for name in sorted(BIBLICAL_PRONUNCIATIONS, key=len, reverse=True):
    ipa, case_sensitive = BIBLICAL_PRONUNCIATIONS[name]
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(r"(?<![<\w/])" + re.escape(name) + r"(?![>\w])", flags)
    _PRONUNCIATION_PATTERNS.append((pattern, name, ipa))


def apply_pronunciations(text):
    """Wrap biblical names with <phoneme> IPA tags.

    Carefully avoids inserting phoneme tags inside SSML attribute values
    (e.g., inside the alias="..." of a <sub> tag) to prevent nested tags
    that would produce invalid XML.
    """
    # Split text into segments: SSML tags vs. plain text.
    # We only apply pronunciation replacements to plain-text segments.
    def _apply_to_plain_text(plain, patterns=_PRONUNCIATION_PATTERNS):
        for pattern, name, ipa in patterns:
            def _replace(m, _ipa=ipa):
                word = m.group(0)
                return f'<phoneme alphabet="ipa" ph="{_ipa}">{word}</phoneme>'
            plain = pattern.sub(_replace, plain)
        return plain

    # Split on SSML tags (including self-closing ones).  We match the
    # entire tag from '<' to '>' so that attribute content is never
    # processed by the pronunciation replacements.
    tag_re = re.compile(r"(<[^>]+>)")
    segments = tag_re.split(text)
    result = []
    for seg in segments:
        if seg.startswith("<"):
            result.append(seg)
        else:
            result.append(_apply_to_plain_text(seg))
    return "".join(result)


# ---------------------------------------------------------------------------
# C. XML Escaping
# ---------------------------------------------------------------------------

def escape_xml(text):
    """Escape XML special characters. Must run before any SSML tags are added."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


# ---------------------------------------------------------------------------
# D. Sentence Splitting
# ---------------------------------------------------------------------------

# Sentence-ending punctuation, but avoid splitting on abbreviations or
# numbers like "1." or "Rev." etc.
_SENTENCE_END_RE = re.compile(
    r'(?<=[.!?])'          # after sentence-ending punctuation
    r'(?:\s*")?'           # optional closing quote
    r'\s+'                 # whitespace
    r'(?=[A-Z0-9"\u201c])'  # next sentence starts with uppercase, digit, or quote
)

# Comma, semicolon, colon for intra-sentence breaks -- but not inside tags
_PAUSE_PUNCT_RE = re.compile(r'([,;:])\s*(?![^<]*>)')


def split_sentences(text):
    """Split a paragraph into sentences."""
    # Normalize whitespace (newlines within a paragraph become spaces)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = _SENTENCE_END_RE.split(text)
    # Filter empty
    return [s.strip() for s in sentences if s.strip()]


def add_comma_breaks(sentence):
    """Insert <break> tags after commas, semicolons, and colons in a sentence.

    Carefully avoids inserting breaks inside existing SSML tags (attributes,
    tag contents) or inside scripture <sub> alias strings.
    """
    result = []
    i = 0
    while i < len(sentence):
        # If we hit an opening '<', skip to the matching '>'
        if sentence[i] == "<":
            end = sentence.find(">", i)
            if end == -1:
                result.append(sentence[i:])
                break
            result.append(sentence[i : end + 1])
            i = end + 1
            continue

        # Check for comma/semicolon/colon followed by space
        if sentence[i] in ",;:" and i + 1 < len(sentence) and sentence[i + 1] == " ":
            result.append(sentence[i])
            result.append('<break time="400ms"/>')
            result.append(" ")
            i += 2  # skip the space
            continue

        result.append(sentence[i])
        i += 1

    return "".join(result)


# ---------------------------------------------------------------------------
# E. Full Conversion Pipeline
# ---------------------------------------------------------------------------

def parse_title_and_body(text):
    """Extract the title (first line) and body from sermon text.

    Returns (title, sermon_number, body) where sermon_number may be None.

    Detects and skips the standard Spurgeon sermon header block:
      Line 1: title (kept)
      Line 2: bare sermon number like "1006" (extracted, skipped)
      Then a block of ALL-CAPS title + "NO. NNN" + "A SERMON DELIVERED..."
      + "BY [THE REV.] C. H. SPURGEON" + "AT [LOCATION]" -- all skipped.
    The body starts at the first line after the header block.
    """
    lines = text.split("\n")
    title = lines[0].strip()

    # Check if line 2 (first non-empty line after title) is a bare sermon
    # number or a "No. NNN" line.
    body_start = 1
    sermon_number = None
    for idx in range(1, min(len(lines), 5)):
        line = lines[idx].strip()
        if not line:
            continue
        # Bare number (e.g., "1006")
        if re.match(r"^\d+$", line):
            sermon_number = line
            body_start = idx + 1
            break
        # "No. 1234" or "NO. 1234"
        m = re.match(r"^[Nn][Oo]\.?\s*(\d+)", line)
        if m:
            sermon_number = m.group(1)
            body_start = idx + 1
            break
        break

    # Now skip the sermon header block that follows the title/number.
    # The header block consists of:
    #   - ALL-CAPS title line(s) (may include "NO. NNN")
    #   - "A SERMON DELIVERED ON ..."
    #   - "BY [THE REV.] C. H. SPURGEON"
    #   - "AT [LOCATION]"
    # We skip lines that match these patterns until we hit the scripture
    # quote or normal body text.
    header_patterns = [
        re.compile(r"^\s*$"),                          # blank lines
        re.compile(r"^[A-Z][A-Z\s,;:'\-\u2014.!?&]+\s*$"),  # ALL-CAPS lines
        re.compile(r"^NO\.\s*\d+", re.IGNORECASE),    # "NO. 1006"
        re.compile(r"^A SERMON DELIVERED", re.IGNORECASE),
        re.compile(r"^A SERMON\s*,?\s*PREACHED", re.IGNORECASE),
        re.compile(r"^DELIVERED ON", re.IGNORECASE),
        re.compile(r"^BY\s+(THE\s+REV\.\s+)?C\.\s*H\.\s*SPURGEON", re.IGNORECASE),
        re.compile(r"^AT\s+(THE\s+)?[A-Z]", re.IGNORECASE),
        re.compile(r"^ON\s+(LORD['']?S[- ]DAY|SABBATH|SUNDAY|THURSDAY)", re.IGNORECASE),
    ]

    idx = body_start
    while idx < len(lines):
        line = lines[idx].strip()
        if any(p.match(line) for p in header_patterns):
            idx += 1
            continue
        # Stop -- this line is not part of the header
        break

    body_start = idx
    body = "\n".join(lines[body_start:])
    return title, sermon_number, body


def text_to_paragraphs(body):
    """Split body text into paragraphs on blank lines."""
    # Normalize line endings
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    # Split on one or more blank lines
    raw_paragraphs = re.split(r"\n\s*\n", body)
    # Clean up each paragraph (join soft-wrapped lines)
    paragraphs = []
    for p in raw_paragraphs:
        cleaned = " ".join(p.split())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def convert_text_to_ssml(text):
    """Convert a plain text sermon/prayer to SSML.

    The full pipeline:
      1. Parse title + body
      2. XML-escape the raw text
      3. Expand scripture references
      4. Apply biblical pronunciations
      5. Structure into paragraphs and sentences with SSML tags
    """
    title, sermon_number, body = parse_title_and_body(text)

    # XML-escape before adding any SSML
    title = escape_xml(title)
    body = escape_xml(body)

    # Apply scripture references
    title = expand_scripture_references(title)
    body = expand_scripture_references(body)

    # Apply pronunciations
    title = apply_pronunciations(title)
    body = apply_pronunciations(body)

    # Build SSML output
    parts = []
    parts.append("<speak>")
    parts.append('<prosody rate="slow" pitch="-8%" volume="soft">')
    parts.append("")

    # Title
    parts.append("<p>")
    parts.append(
        f'<s><emphasis level="strong">{title}</emphasis></s>'
    )
    parts.append('<break time="1500ms"/>')
    parts.append("</p>")
    parts.append("")

    # Sermon number (if present)
    if sermon_number:
        parts.append("<p>")
        parts.append(
            f'<s><sub alias="Sermon number {sermon_number}">'
            f"No. {sermon_number}</sub>.</s>"
        )
        parts.append('<break time="1200ms"/>')
        parts.append("</p>")
        parts.append("")

    # Body paragraphs
    paragraphs = text_to_paragraphs(body)
    for p_idx, para in enumerate(paragraphs):
        sentences = split_sentences(para)
        if not sentences:
            continue

        parts.append("<p>")
        for s_idx, sentence in enumerate(sentences):
            sentence = add_comma_breaks(sentence)
            parts.append(f"<s>{sentence}</s>")
            # Add inter-sentence break (not after last sentence in paragraph)
            if s_idx < len(sentences) - 1:
                parts.append('<break time="750ms"/>')
        parts.append("</p>")

        # Add inter-paragraph break (not after last paragraph)
        if p_idx < len(paragraphs) - 1:
            parts.append("")
            parts.append('<break time="1200ms"/>')
            parts.append("")

    parts.append("")
    parts.append("</prosody>")
    parts.append("</speak>")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# F. File Processing
# ---------------------------------------------------------------------------

def process_file(input_path, output_path):
    """Read a .txt file and write the corresponding .ssml file."""
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()
    ssml = convert_text_to_ssml(text)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ssml)


def txt_to_ssml_filename(txt_name):
    """Convert a txt filename to an ssml filename.

    Example: 'sermon_001.txt' -> 'sermon_001.ssml'
    """
    base, _ = os.path.splitext(txt_name)
    return base + ".ssml"


def main():
    parser = argparse.ArgumentParser(
        description="Convert plain text sermon files to SSML for TTS."
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        default="sermons",
        help="Directory containing .txt sermon files (default: sermons)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="sermons_ssml",
        help="Directory for output .ssml files (default: sermons_ssml)",
    )
    parser.add_argument(
        "-f",
        "--file",
        default=None,
        help="Process a single .txt file instead of the whole input directory",
    )
    args = parser.parse_args()

    if args.file:
        # Single file mode
        input_path = args.file
        if not os.path.isfile(input_path):
            print(f"Error: file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        output_name = txt_to_ssml_filename(os.path.basename(input_path))
        output_path = os.path.join(args.output_dir, output_name)
        print(f"  {input_path} -> {output_path}")
        process_file(input_path, output_path)
        print("Done. 1 file processed.")
        return

    # Directory mode
    if not os.path.isdir(args.input_dir):
        print(f"Error: input directory not found: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    txt_files = sorted(
        f for f in os.listdir(args.input_dir) if f.lower().endswith(".txt")
    )

    if not txt_files:
        print(f"No .txt files found in {args.input_dir}")
        sys.exit(0)

    print(f"Converting {len(txt_files)} file(s) from {args.input_dir}/ "
          f"to {args.output_dir}/")

    for txt_file in txt_files:
        input_path = os.path.join(args.input_dir, txt_file)
        output_name = txt_to_ssml_filename(txt_file)
        output_path = os.path.join(args.output_dir, output_name)
        print(f"  {txt_file} -> {output_name}")
        process_file(input_path, output_path)

    print(f"Done. {len(txt_files)} file(s) processed.")


if __name__ == "__main__":
    main()
