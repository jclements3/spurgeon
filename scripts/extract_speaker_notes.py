#!/usr/bin/env python3
"""Extract concise speaker/bullet outlines from Spurgeon sermon text files.

Reads plain-text sermon files (title on line 1, sermon number on line 2,
blank line 3, then header block and body) and generates a one-page speaker
outline per sermon using pattern-based heuristic extraction (no AI).

Output fits on a single printed page (~60 lines, ~80 chars wide).
"""

import argparse
import os
import re
import sys
import textwrap


# ---------------------------------------------------------------------------
# OCR / PDF broken-word repair
# ---------------------------------------------------------------------------
# Common pattern: a space inserted inside a word, e.g. "i mmutability",
# "th ought", "po rtion".  We fix single-letter fragments glued to the next
# word, and two-letter fragments when the result is a plausible English word.
_BROKEN_WORD_RE = re.compile(
    r'\b([a-zA-Z])\s+([a-zA-Z]{3,})\b'
)
# Also catch two-letter prefix splits like "th ought", "po rtion"
_BROKEN_WORD2_RE = re.compile(
    r'\b([a-zA-Z]{2})\s+([a-zA-Z]{3,})\b'
)


def _repair_broken_words(text):
    """No-op: broken words are already fixed by extract_sermons.py."""
    return text


# ---------------------------------------------------------------------------
# Scripture reference pattern
# ---------------------------------------------------------------------------
# Matches patterns like "John 3:16", "1 Corinthians 1:23, 24",
# "Genesis 1:1-3", "2 Kings 7:19", "Psalm 23:1", etc.
SCRIPTURE_RE = re.compile(
    r'(?:'
    r'(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|'
    r'1\s*Samuel|2\s*Samuel|1\s*Kings|2\s*Kings|1\s*Chronicles|2\s*Chronicles|'
    r'Ezra|Nehemiah|Esther|Job|Psalms?|Proverbs?|Ecclesiastes|'
    r'Song\s*of\s*Solomon|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|'
    r'Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|'
    r'Haggai|Zechariah|Malachi|'
    r'Matthew|Mark|Luke|John|Acts|Romans|'
    r'1\s*Corinthians|2\s*Corinthians|Galatians|Ephesians|Philippians|'
    r'Colossians|1\s*Thessalonians|2\s*Thessalonians|'
    r'1\s*Timothy|2\s*Timothy|Titus|Philemon|Hebrews|James|'
    r'1\s*Peter|2\s*Peter|1\s*John|2\s*John|3\s*John|Jude|Revelation|'
    # Common abbreviations
    r'Gen|Exod?|Lev|Num|Deut|Josh|Judg|Sam|Kgs|Chr|Neh|Esth|'
    r'Psa?|Prov|Eccl|Isa|Jer|Lam|Ezek|Dan|Hos|Mic|Nah|Hab|Zeph|'
    r'Hag|Zech|Mal|Matt?|Mk|Lk|Jn|Rom|Cor|Gal|Eph|Phil|Col|'
    r'Thess|Tim|Heb|Jas|Pet|Rev)'
    r')\s*'
    r'\d+\s*:\s*\d+(?:\s*[-,]\s*\d+)*',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Illustration keyword patterns
# ---------------------------------------------------------------------------
ILLUSTRATION_STARTERS = re.compile(
    r'\b(?:suppose|imagine|picture|consider\s+the\s+case|'
    r'I\s+remember|A\s+certain\s+man|A\s+certain\s+woman|'
    r'let\s+me\s+illustrate|by\s+way\s+of\s+illustration|'
    r'there\s+was\s+once|there\s+is\s+a\s+story|'
    r'I\s+have\s+heard|I\s+have\s+read|'
    r'an?\s+(?:old|young|poor|rich|good|certain)\s+(?:man|woman|farmer|soldier|king|sailor)|'
    r'like\s+a\s+(?:man|ship|soldier|tree|river|fountain|bird)|'
    r'as\s+if|as\s+though|it\s+is\s+as\s+when|'
    r'it\s+is\s+like|just\s+as)\b',
    re.IGNORECASE
)

# Words that signal strong theological/quotable content
STRONG_WORDS = re.compile(
    r'\b(?:Christ|Jesus|God|grace|salvation|faith|cross|blood|eternal|'
    r'glory|redemption|sovereign|mercy|gospel|heaven|hell|'
    r'justified|sanctified|atone|atonement|resurrection|'
    r'Saviour|Savior|Redeemer|Lord|Spirit|Holy)\b',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Roman numeral / structural division patterns
# ---------------------------------------------------------------------------
# "I. First ...", "II. Now ...", "III. ..."
ROMAN_DIVISION_RE = re.compile(
    r'^(I{1,3}V?|IV|V|VI{0,3})\.\s+(.+)', re.MULTILINE
)

# "First,", "Secondly,", "Thirdly,", "In the first place", etc.
ORDINAL_DIVISION_RE = re.compile(
    r'^(?:First(?:ly)?,|Second(?:ly)?,|Third(?:ly)?,|Fourth(?:ly)?,|'
    r'Fifth(?:ly)?,|In\s+the\s+(?:first|second|third|fourth|fifth)\s+place)',
    re.MULTILINE | re.IGNORECASE
)

# ALL CAPS section headers (at least 4 caps words)
CAPS_HEADER_RE = re.compile(
    r'^([A-Z][A-Z\s,\'-]{15,})$', re.MULTILINE
)


def parse_sermon(filepath):
    """Parse a sermon file into its components."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # Repair broken words from PDF extraction artifacts
    text = _repair_broken_words(text)

    lines = text.split('\n')
    if len(lines) < 3:
        return None

    title = lines[0].strip()
    sermon_num = lines[1].strip()

    # Find the header block: everything before the body text begins.
    # The header typically contains the title repeated in caps, "NO. X",
    # "A SERMON DELIVERED ON...", "BY THE REV...", "AT ...",
    # then the scripture quotation.
    # The body starts after the scripture reference block.

    # Join body text (skip first 3 lines: title, number, blank)
    body_lines = lines[3:]
    body = '\n'.join(body_lines)

    # Extract date/location from header
    date_location = extract_date_location(body_lines)

    # Find the opening scripture (the quoted text block in the header)
    opening_scripture = extract_opening_scripture(body_lines)

    # Find where the actual sermon body begins (after the header block)
    body_start = find_body_start(body_lines)
    sermon_body_lines = body_lines[body_start:]
    sermon_body = '\n'.join(sermon_body_lines)

    # Extract structural divisions
    divisions = extract_divisions(sermon_body, sermon_body_lines)

    # Extract all scripture references from the body
    scriptures = extract_scripture_refs(sermon_body)

    # Extract illustrations
    illustrations = extract_illustrations(sermon_body_lines)

    # Extract quotable sentences
    quotes = extract_quotes(sermon_body_lines)

    # Extract application points (usually near the end)
    applications = extract_applications(sermon_body_lines)

    return {
        'title': title,
        'sermon_num': sermon_num,
        'date_location': date_location,
        'opening_scripture': opening_scripture,
        'divisions': divisions,
        'scriptures': scriptures,
        'illustrations': illustrations,
        'quotes': quotes,
        'applications': applications,
    }


def extract_date_location(lines):
    """Extract date and location from the sermon header."""
    date_str = ''
    location_str = ''
    for line in lines[:15]:
        line_stripped = line.strip()
        # "A SERMON DELIVERED ON SABBATH MORNING, JANUARY 7, 1855,"
        m = re.search(
            r'(?:DELIVERED|PREACHED)\s+ON\s+.*?,\s*'
            r'((?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|'
            r'SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d+,?\s*\d{4})',
            line_stripped, re.IGNORECASE
        )
        if m:
            date_str = m.group(1).strip().rstrip(',')

        m2 = re.search(
            r'(?:DELIVERED|PREACHED)\s+ON\s+(.*?)(?:,\s*(?:JANUARY|FEBRUARY|'
            r'MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|'
            r'NOVEMBER|DECEMBER))',
            line_stripped, re.IGNORECASE
        )
        if m2:
            occasion = m2.group(1).strip().rstrip(',')
            if occasion:
                date_str = occasion + ', ' + date_str if date_str else occasion

        # "AT NEW PARK STREET CHAPEL, SOUTHWARK."
        m3 = re.match(r'AT\s+(.+?)\.?\s*$', line_stripped, re.IGNORECASE)
        if m3:
            location_str = m3.group(1).strip()

    if date_str or location_str:
        parts = []
        if date_str:
            parts.append(date_str)
        if location_str:
            parts.append(location_str)
        return '; '.join(parts)
    return ''


def extract_opening_scripture(lines):
    """Extract the main scripture text from the sermon header.

    This is typically a quoted passage followed by a book/chapter:verse
    reference, appearing in the first ~20 lines after the header metadata.
    """
    # Look for the scripture quotation block in the header.
    # It's usually enclosed in quotes and followed by a reference line.
    in_quote = False
    quote_lines = []
    ref_line = ''

    for i, line in enumerate(lines[:25]):
        stripped = line.strip()
        if not stripped:
            # If we were collecting a quote and hit blank, check next
            if in_quote and quote_lines:
                continue
            continue

        # Check if this line starts a scripture quotation
        if stripped.startswith('"') and not in_quote:
            in_quote = True
            quote_lines = [stripped]
            continue

        if in_quote:
            quote_lines.append(stripped)
            # Check if this line or next contains a scripture reference
            if SCRIPTURE_RE.search(stripped):
                ref_match = SCRIPTURE_RE.search(stripped)
                if ref_match:
                    ref_line = ref_match.group(0)
                break

    if ref_line:
        return ref_line
    # Fallback: find the first scripture reference in the header area
    for line in lines[:25]:
        m = SCRIPTURE_RE.search(line)
        if m:
            return m.group(0)
    return ''


def find_body_start(lines):
    """Find where the sermon body begins after the header block.

    The header contains: title, NO. X, delivery info, scripture quotation.
    The body starts with the first paragraph of regular prose.
    We look for the first line after the scripture reference that starts
    with a regular word (not all caps, not blank, not metadata).
    """
    found_scripture = False
    for i, line in enumerate(lines[:30]):
        stripped = line.strip()
        if SCRIPTURE_RE.search(stripped):
            found_scripture = True
            continue
        if found_scripture and stripped and not stripped.startswith('NO.'):
            # Check this is body text, not still header
            # Header lines tend to be all caps or very short
            if len(stripped) > 40 or (stripped[0].isupper() and not stripped.isupper()):
                return i
    # Fallback: skip first 10 lines
    return min(10, len(lines) - 1)


def extract_divisions(body, body_lines):
    """Extract major structural divisions from the sermon body."""
    divisions = []

    # Strategy 1: Roman numeral patterns ("I. First ...", "II. Now ...")
    for m in ROMAN_DIVISION_RE.finditer(body):
        numeral = m.group(1)
        rest = m.group(2).strip()
        # Grab continuation lines (the heading often spans 2-3 lines,
        # especially when there is an ALL CAPS topic phrase)
        end_pos = m.end()
        for extra_line in body[end_pos:end_pos + 500].split('\n')[1:5]:
            extra = extra_line.strip()
            if not extra:
                break
            # Stop if we hit a numbered sub-point or another sentence start
            if re.match(r'^\d+\.', extra):
                break
            # Continue if it looks like a heading continuation
            # (ALL CAPS, or very short continuation of prior line)
            if extra.isupper() or len(rest) < 60:
                rest += ' ' + extra
            else:
                break
        # Clean up the division text: take the first sentence or ~100 chars
        div_text = _clean_division_text(rest)
        divisions.append((numeral, div_text, m.start()))

    if divisions:
        # Assign scripture references to each division
        return _assign_scriptures_to_divisions(divisions, body)

    # Strategy 2: Ordinal markers ("First,", "Secondly,", etc.)
    ordinal_map = {
        'first': 'I', 'second': 'II', 'third': 'III',
        'fourth': 'IV', 'fifth': 'V'
    }
    for m in ORDINAL_DIVISION_RE.finditer(body):
        marker = m.group(0).strip().rstrip(',').lower()
        for key, numeral in ordinal_map.items():
            if key in marker:
                # Get the rest of the sentence
                pos = m.end()
                end_pos = body.find('.', pos)
                if end_pos == -1 or end_pos - pos > 200:
                    end_pos = min(pos + 150, len(body))
                rest = body[pos:end_pos].strip().lstrip(',').strip()
                div_text = _clean_division_text(rest)
                divisions.append((numeral, div_text, m.start()))
                break

    if divisions:
        return _assign_scriptures_to_divisions(divisions, body)

    # Strategy 3: Paragraph topic sentences (for unstructured sermons)
    # Take the first sentence of substantial paragraphs
    divisions = _extract_topic_sentences(body_lines)

    return _assign_scriptures_to_divisions(divisions, body)


def _clean_division_text(text):
    """Clean division text to a concise title-case heading (under 60 chars).

    Strategy:
    1. If an ALL-CAPS topic phrase is embedded, extract and title-case it.
    2. Otherwise, strip transitional phrasing and extract the core topic.
    3. Result is always a clean phrase in title case, never a sentence fragment
       ending in '...'.
    """
    # Remove spurgeon gems URLs and page artifacts
    text = re.sub(r'www\.spurgeongems\.org', '', text)
    text = re.sub(r'Volume\s+\d+', '', text)
    text = re.sub(r'Sermons?\s+#[\d,\s]+', '', text)
    # Remove line breaks and extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Repair any broken words
    text = _repair_broken_words(text)

    # --- Strategy 1: ALL CAPS topic phrase embedded in the text ---
    caps_match = re.search(r'[A-Z][A-Z\s,\'\"\-\u2018\u2019\u201c\u201d]{8,}', text)
    if caps_match:
        caps_topic = caps_match.group(0).strip().rstrip(',').strip()
        result = caps_topic.title()
        # Remove trailing articles/prepositions that got caught
        result = re.sub(r'\s+$', '', result)
        if len(result) > 58:
            result = _trim_to_phrase_boundary(result, 58)
        return result

    # --- Strategy 2: Strip transitional phrasing, extract core topic ---
    # Remove common transitional sentence starters
    transitional = re.compile(
        r'^(?:Having\s+(?:thus\s+)?(?:shown|said|considered|noticed|noted|observed)\s+'
        r'.*?,\s*(?:we\s+)?(?:pass\s+on\s+to|now\s+(?:come|turn)\s+to|'
        r'(?:shall|will|let\s+us)\s+(?:now\s+)?(?:consider|notice|observe))\s*'
        r'|We\s+(?:now\s+)?(?:come|turn|proceed|pass)\s+(?:on\s+)?to\s+'
        r'|(?:Let\s+us|I\s+shall)\s+(?:now\s+)?(?:consider|notice|observe|examine)\s+'
        r'|(?:Now|Next|Then)[,\s]+(?:we\s+)?(?:come|turn|proceed|pass)\s+(?:on\s+)?to\s+'
        r')',
        re.IGNORECASE
    )
    cleaned = transitional.sub('', text).strip()
    if cleaned:
        text = cleaned

    # Try to extract a noun-phrase topic: take content up to the first
    # clause boundary (period, semicolon, colon, dash, or subordinate clause)
    clause_end = re.search(r'[.;:\u2014]|\s+(?:which|that|where|when|who|because|since|for\s)', text)
    if clause_end and clause_end.start() > 5:
        text = text[:clause_end.start()].strip()

    # Remove leading/trailing conjunctions and filler
    text = re.sub(r'^(?:and|but|or|now|then|next|also)[,\s]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[,\s]+$', '', text)

    # Title-case the result
    text = _title_case_heading(text)

    # Enforce length limit at a clean word boundary
    if len(text) > 58:
        text = _trim_to_phrase_boundary(text, 58)

    return text


def _title_case_heading(text):
    """Convert text to title case, keeping small words lowercase mid-phrase."""
    small_words = {
        'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so',
        'in', 'on', 'at', 'to', 'by', 'of', 'up', 'as', 'is', 'if',
        'it', 'be', 'we', 'us', 'no',
    }
    words = text.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in small_words:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return ' '.join(result)


def _trim_to_phrase_boundary(text, max_len):
    """Trim text to max_len at a clean word boundary, no trailing '...'."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # Find last space to avoid cutting mid-word
    last_space = truncated.rfind(' ')
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    # Strip trailing prepositions/articles that dangle
    truncated = re.sub(
        r'\s+(?:a|an|the|and|but|or|of|in|on|at|to|by|for|with|from|as|is|are|was|were|that|which|this)\s*$',
        '', truncated, flags=re.IGNORECASE
    )
    return truncated.rstrip(' ,;:-')


def _extract_topic_sentences(body_lines):
    """For unstructured sermons, extract paragraph-opening sentences."""
    divisions = []
    numerals = ['I', 'II', 'III', 'IV', 'V']
    num_idx = 0
    prev_blank = False
    char_count = 0

    for i, line in enumerate(body_lines):
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            continue

        # Skip page artifacts
        if re.match(r'^\d+$', stripped):
            continue
        if 'spurgeongems' in stripped.lower() or 'Volume' in stripped:
            prev_blank = False
            continue

        char_count += len(stripped)

        # A new paragraph after a blank line with substantial text
        if prev_blank and len(stripped) > 50 and num_idx < len(numerals):
            # Skip if too early (first ~500 chars is usually still intro)
            if char_count > 500:
                # Take first sentence
                sentence = _first_sentence(stripped, body_lines, i)
                if sentence and len(sentence) > 20:
                    divisions.append((numerals[num_idx], _clean_division_text(sentence), 0))
                    num_idx += 1
                    if num_idx >= 4:
                        break

        prev_blank = False

    return divisions


def _first_sentence(line, lines, idx):
    """Extract the first sentence starting from line idx."""
    text = line.strip()
    # Accumulate until we find a sentence-ending period
    j = idx + 1
    while j < min(idx + 5, len(lines)):
        next_line = lines[j].strip()
        if not next_line:
            break
        text += ' ' + next_line
        j += 1

    text = re.sub(r'\s+', ' ', text)
    text = _repair_broken_words(text)
    # Find first period followed by space or end
    m = re.search(r'[.!?]\s', text)
    if m and m.start() < 200:
        return text[:m.start() + 1]
    if len(text) > 150:
        return _extract_complete_phrase(text, max_len=150)
    return text


def _assign_scriptures_to_divisions(divisions, body):
    """For each division, find nearby scripture references."""
    if not divisions:
        return []

    result = []
    for i, (numeral, text, pos) in enumerate(divisions):
        # Look for scriptures in the text after this division until the next
        if i + 1 < len(divisions):
            next_pos = divisions[i + 1][2]
        else:
            next_pos = len(body)

        section = body[pos:next_pos]
        refs = SCRIPTURE_RE.findall(section)
        # Deduplicate and limit
        seen = set()
        unique_refs = []
        for r in refs:
            r_clean = re.sub(r'\s+', ' ', r).strip()
            if r_clean not in seen:
                seen.add(r_clean)
                unique_refs.append(r_clean)
        result.append({
            'numeral': numeral,
            'heading': text,
            'scriptures': unique_refs[:3],
            'section_text': section,
        })
    return result


def extract_scripture_refs(text):
    """Extract all scripture references from the text."""
    refs = SCRIPTURE_RE.findall(text)
    seen = set()
    unique = []
    for r in refs:
        r_clean = re.sub(r'\s+', ' ', r).strip()
        if r_clean not in seen:
            seen.add(r_clean)
            unique.append(r_clean)
    return unique


def extract_illustrations(body_lines):
    """Find paragraphs that contain illustration/analogy markers.

    Instead of extracting raw sentence fragments, this identifies the
    topic/concept of each illustration and returns a short descriptor like:
      "Illustration of a ship without a rudder (directionless faith)"
    """
    illustrations = []
    full_text = '\n'.join(body_lines)

    for i, line in enumerate(body_lines):
        stripped = line.strip()
        if not stripped or len(stripped) < 30:
            continue

        m = ILLUSTRATION_STARTERS.search(stripped)
        if m:
            # Build a description of what the illustration is about
            descriptor = _summarize_illustration(stripped, m, body_lines, i)
            if descriptor and len(descriptor) > 10:
                # Avoid duplicates
                if not any(s[:25] == descriptor[:25] for s in illustrations):
                    illustrations.append(descriptor)
                    if len(illustrations) >= 6:
                        break

    return illustrations


def _summarize_illustration(line, marker_match, lines, line_idx):
    """Produce a short topic descriptor for an illustration.

    Extracts the introductory sentence and distills it to a concise
    description of the analogy/story concept, e.g.:
      "A ship without a rudder -- directionless faith"
      "An old soldier's confidence -- assurance in Christ"
    """
    # Build multi-line context (the paragraph containing the illustration)
    text = line.strip()
    j = line_idx + 1
    while j < min(line_idx + 5, len(lines)):
        next_l = lines[j].strip()
        if not next_l:
            break
        text += ' ' + next_l
        j += 1
    text = re.sub(r'\s+', ' ', text).strip()
    text = _repair_broken_words(text)

    marker_pos = marker_match.start()
    marker_text = marker_match.group(0)

    # Find the sentence containing the marker
    safe_pos = min(marker_pos, len(text) - 1)
    start = 0
    for k in range(safe_pos, 0, -1):
        if text[k] in '.!?' and k < safe_pos - 2:
            start = k + 1
            break

    end = len(text)
    for k in range(safe_pos + 1, len(text)):
        if text[k] in '.!?':
            end = k + 1
            break

    intro_sentence = text[start:end].strip()

    # Now extract the core concept from the intro sentence.
    # Look for "like a ___", "as a ___", "suppose ___", "imagine ___",
    # "picture ___", "consider the case of ___", etc.
    concept = _extract_illustration_concept(intro_sentence, marker_text)
    if concept:
        return concept

    # Fallback: use the introductory sentence, trimmed to a clean phrase
    if len(intro_sentence) > 75:
        intro_sentence = _trim_to_phrase_boundary(intro_sentence, 75)
    return intro_sentence


def _extract_illustration_concept(sentence, marker):
    """Extract a concise concept descriptor from an illustration sentence."""
    marker_lower = marker.lower().strip()

    # Pattern: "like a X" / "as a X" -- extract the analogy subject
    like_match = re.search(
        r'(?:like|as)\s+(?:a|an|the)\s+([^,\.;]+)',
        sentence, re.IGNORECASE
    )
    if like_match:
        analogy = like_match.group(0).strip()
        analogy = _trim_to_phrase_boundary(analogy, 50)
        # Try to find what it illustrates: look for preceding context
        before = sentence[:like_match.start()].strip().rstrip(',').rstrip('-').strip()
        topic = _extract_trailing_topic(before)
        if topic and len(topic) > 5:
            return f"{analogy} -- {_title_case_heading(topic)}"
        return analogy.capitalize()

    # Pattern: "suppose/imagine/picture + clause" -- extract the scenario
    scenario_match = re.search(
        r'(?:suppose|imagine|picture|consider)\s+(.+?)(?:[,;.]|\s+and\s+)',
        sentence, re.IGNORECASE
    )
    if scenario_match:
        scenario = scenario_match.group(1).strip()
        if len(scenario) > 55:
            scenario = _trim_to_phrase_boundary(scenario, 55)
        return scenario[0].upper() + scenario[1:] if scenario else scenario

    # Pattern: "a certain man/woman/farmer..." -- extract the character + action
    char_match = re.search(
        r'((?:a|an)\s+(?:\w+\s+)?(?:man|woman|farmer|soldier|king|sailor|'
        r'traveler|traveller|boy|girl|child|person|merchant|beggar)\s+[^,\.;]{5,})',
        sentence, re.IGNORECASE
    )
    if char_match:
        desc = char_match.group(1).strip()
        if len(desc) > 55:
            desc = _trim_to_phrase_boundary(desc, 55)
        return desc[0].upper() + desc[1:] if desc else desc

    # Pattern: "I remember/have heard/have read + story hint"
    story_match = re.search(
        r'I\s+(?:remember|have\s+heard|have\s+read)\s+(.+?)(?:[,;.])',
        sentence, re.IGNORECASE
    )
    if story_match:
        hint = story_match.group(1).strip()
        if len(hint) > 55:
            hint = _trim_to_phrase_boundary(hint, 55)
        return hint[0].upper() + hint[1:] if hint else hint

    return ''


def _extract_trailing_topic(text):
    """Extract a short trailing topic phrase from text preceding an analogy."""
    # Take the last clause or short phrase
    # Split on commas/semicolons and take the last meaningful chunk
    parts = re.split(r'[,;]', text)
    for part in reversed(parts):
        part = part.strip()
        if len(part) > 5:
            if len(part) > 40:
                part = _trim_to_phrase_boundary(part, 40)
            return part
    return ''


def extract_quotes(body_lines):
    """Find short, punchy sentences with strong theological content."""
    quotes = []

    # Build full text with line joins for better sentence splitting
    full_text = ' '.join(
        l.strip() for l in body_lines
        if l.strip()
        and not l.strip().isupper()
        and 'spurgeongems' not in l.lower()
        and not re.match(r'^\d+$', l.strip())
    )
    full_text = re.sub(r'\s+', ' ', full_text)

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', full_text)

    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 30 or len(sent) > 120:
            continue
        # Must end with punctuation to be a complete sentence
        if not sent[-1] in '.!?':
            continue
        # Must start with a capital letter
        if not sent[0].isupper():
            continue
        # Count strong theological words
        strong_count = len(STRONG_WORDS.findall(sent))
        if strong_count >= 2:
            # Prefer declarative sentences; skip fragments starting with
            # weak conjunctions unless very theologically dense
            if re.match(r'^(?:And|But|Or|For|If|When|While|So|Yet)\s', sent):
                if strong_count < 3:
                    continue
            quotes.append(sent)

    # Score and sort: prefer shorter, more theologically dense
    scored = []
    for q in quotes:
        strong_count = len(STRONG_WORDS.findall(q))
        # Higher score = better quote
        score = strong_count * 10 - len(q) * 0.08
        # Bonus for exclamation marks (emphatic)
        if '!' in q:
            score += 3
        scored.append((score, q))

    scored.sort(key=lambda x: -x[0])
    # Deduplicate by first 30 chars
    seen = set()
    result = []
    for score, q in scored:
        key = q[:30]
        if key not in seen:
            seen.add(key)
            result.append(q)
            if len(result) >= 8:
                break

    return result


def extract_applications(body_lines):
    """Extract application/call-to-action points, typically near the end."""
    applications = []
    # Look at the last ~30% of the sermon
    start = max(0, len(body_lines) - len(body_lines) // 3)
    tail_lines = body_lines[start:]

    # Look for application markers
    app_markers = re.compile(
        r'\b(?:let\s+us|let\s+me\s+(?:urge|beseech|entreat|exhort)|'
        r'I\s+(?:beseech|entreat|urge|exhort)\s+you|'
        r'may\s+(?:God|the\s+Lord)|'
        r'go\s+(?:home|away|forth)\s+and|'
        r'(?:come|turn|fly|flee)\s+to\s+(?:Christ|Jesus|God|the\s+Saviour)|'
        r'believe\s+(?:on|in)\s+(?:Him|Christ|Jesus|the\s+Lord)|'
        r'trust\s+(?:in\s+)?(?:Him|Christ|Jesus|God)|'
        r'repent|receive\s+(?:Him|Christ))\b',
        re.IGNORECASE
    )

    # Build joined text for the tail section
    tail_text = ' '.join(
        l.strip() for l in tail_lines
        if l.strip()
        and not l.strip().isupper()
        and 'spurgeongems' not in l.lower()
        and not re.match(r'^\d+$', l.strip())
    )
    tail_text = re.sub(r'\s+', ' ', tail_text)

    # Split into sentences and check each
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', tail_text)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 30 or len(sent) > 130:
            continue
        if app_markers.search(sent):
            if len(sent) > 120:
                sent = sent[:117] + '...'
            if not any(s[:25] == sent[:25] for s in applications):
                applications.append(sent)
                if len(applications) >= 4:
                    break

    return applications


def extract_subpoints(section_text, max_points=3):
    """Extract key sub-points from a division's section text.

    Produces complete phrases that end at clean boundaries (sentence end
    or natural phrase break), never mid-word or mid-clause.
    """
    subpoints = []
    # Remove page artifacts
    text = re.sub(r'www\.spurgeongems\.org', '', section_text)
    text = re.sub(r'Volume\s+\d+', '', text)
    text = re.sub(r'Sermons?\s+#[\d,\s]+', '', text)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    # Clean up extra internal spaces from OCR artifacts
    text = re.sub(r'  +', ' ', text)
    text = _repair_broken_words(text)

    # Look for numbered sub-points: "1. ...", "2. ..." at line starts
    numbered = re.finditer(r'(?:^|\n)\s*(\d+)\.\s+([A-Z])', text)
    num_points = []
    for nm in numbered:
        # Get the rest of the sentence
        rest = text[nm.end() - 1:]  # include the capital letter
        sentence = _extract_complete_phrase(rest, max_len=75)
        if len(sentence) > 15:
            num_points.append(sentence)
    if num_points:
        return num_points[:max_points]

    # Otherwise, find key sentences: look for sentences with strong words
    paragraphs = re.split(r'\n\s*\n', text)
    for para in paragraphs[1:]:  # skip first para (it's the heading itself)
        para = re.sub(r'\s+', ' ', para).strip()
        if len(para) < 40:
            continue
        # Get first sentence of paragraph
        m = re.search(r'[.!?]\s', para)
        if m and 20 < m.start() < 150:
            sent = para[:m.start() + 1].strip()
            if STRONG_WORDS.search(sent) and len(sent) > 20:
                if len(sent) > 75:
                    sent = _extract_complete_phrase(sent, max_len=75)
                if not any(s[:25] == sent[:25] for s in subpoints):
                    subpoints.append(sent)
                    if len(subpoints) >= max_points:
                        break

    return subpoints


def _extract_complete_phrase(text, max_len=75):
    """Extract a complete phrase from text, ending at a clean boundary.

    Tries to end at a sentence boundary (period, !, ?). If the sentence
    is too long, trims at a clause boundary (comma, semicolon, dash) or
    a natural phrase break -- never mid-word.
    """
    text = re.sub(r'\s+', ' ', text).strip()

    # If there's a sentence end within our budget, use it
    sent_end = re.search(r'[.!?](?:\s|$)', text[:max_len + 5])
    if sent_end and sent_end.start() <= max_len:
        return text[:sent_end.start() + 1].strip()

    # No sentence end in range -- look for a clause boundary
    if len(text) > max_len:
        chunk = text[:max_len]
        # Try to break at a clause boundary: last comma, semicolon, or dash
        for sep in ['; ', ', ', ' -- ', ' - ']:
            last_sep = chunk.rfind(sep)
            if last_sep > max_len // 2:
                return chunk[:last_sep].strip()
        # Break at last word boundary
        return _trim_to_phrase_boundary(chunk, max_len)

    return text.strip()


def format_output(data):
    """Format the extracted data into the speaker notes template."""
    lines = []
    wrap = textwrap.TextWrapper(width=78, subsequent_indent='     ')
    wrap_bullet = textwrap.TextWrapper(width=78, initial_indent='   ', subsequent_indent='     ')
    wrap_quote = textwrap.TextWrapper(width=78, initial_indent='   ', subsequent_indent='     ')

    # Title and metadata
    title = data['title']
    if len(title) > 78:
        title = title[:75] + '...'
    lines.append(title.upper())
    lines.append(f"Sermon #{data['sermon_num']}")

    if data['opening_scripture']:
        lines.append(f"Scripture: {data['opening_scripture']}")

    if data['date_location']:
        dl = data['date_location']
        # "Date/Location: " is 16 chars, leave room for 80 total
        max_dl = 80 - 16
        if len(dl) > max_dl:
            dl = dl[:max_dl - 3] + '...'
        lines.append(f"Date/Location: {dl}")

    lines.append('\u2550' * 55)
    lines.append('')

    # Major divisions with sub-points
    divisions = data['divisions']
    if not divisions:
        # If no divisions found, just list some scripture refs
        lines.append('[No clear structural divisions detected]')
        lines.append('')
    else:
        for div in divisions[:5]:
            heading = div['heading']
            numeral = div['numeral']
            heading_wrapped = wrap.wrap(f"{numeral}. {heading}")
            lines.extend(heading_wrapped)

            # Sub-points
            section_text = div.get('section_text', '')
            subpoints = extract_subpoints(section_text)
            for sp in subpoints[:3]:
                sp_lines = wrap_bullet.wrap(f"\u2022 {sp}")
                lines.extend(sp_lines)

            # Scripture references for this division
            div_refs = div.get('scriptures', [])
            if div_refs:
                ref_str = '; '.join(div_refs[:2])
                lines.append(f"   \u2192 Scripture: {ref_str}")

            lines.append('')

    # Separator
    lines.append('\u2500' * 55)

    # Key Illustrations
    illustrations = data['illustrations'][:3]
    if illustrations:
        lines.append('Key Illustrations:')
        for ill in illustrations:
            ill_lines = wrap_quote.wrap(f"\u2022 {ill}")
            lines.extend(ill_lines)
        lines.append('')

    # Key Quotes
    quotes = data['quotes'][:3]
    if quotes:
        lines.append('Key Quotes:')
        for q in quotes:
            q_text = f'\u2022 "{q}"'
            q_lines = wrap_quote.wrap(q_text)
            lines.extend(q_lines)
        lines.append('')

    # Application
    applications = data['applications'][:2]
    if applications:
        lines.append('Application:')
        for app in applications:
            app_lines = wrap_quote.wrap(f"\u2022 {app}")
            lines.extend(app_lines)
    elif quotes or illustrations:
        # No explicit application found; skip section
        pass

    lines.append('\u2500' * 55)

    # Enforce 60-line limit by trimming from the bottom sections
    if len(lines) > 60:
        lines = _trim_to_fit(lines, 60)

    return '\n'.join(lines) + '\n'


def _trim_to_fit(lines, max_lines):
    """Trim output to fit within max_lines, cutting lower-priority content."""
    if len(lines) <= max_lines:
        return lines

    # Find section boundaries (Unicode box-drawing separators)
    sep_char = '\u2500'
    sep_indices = [i for i, l in enumerate(lines)
                   if l.startswith(sep_char * 10)]

    # Strategy: keep the divisions section, trim bottom sections
    if len(sep_indices) >= 2:
        top_section = lines[:sep_indices[0] + 1]
        bottom_section = lines[sep_indices[0] + 1:]
        available = max_lines - len(top_section) - 1
        if available > 0:
            bottom_trimmed = bottom_section[:available]
            if not bottom_trimmed[-1].startswith(sep_char * 10):
                bottom_trimmed.append(sep_char * 55)
            return top_section + bottom_trimmed
        else:
            return lines[:max_lines - 1] + [sep_char * 55]
    else:
        return lines[:max_lines - 1] + [sep_char * 55]


def process_file(input_path, output_dir):
    """Process a single sermon file and write the speaker notes."""
    data = parse_sermon(input_path)
    if data is None:
        print(f"  SKIP (too short): {input_path}")
        return False

    output = format_output(data)

    os.makedirs(output_dir, exist_ok=True)
    basename = os.path.basename(input_path)
    output_path = os.path.join(output_dir, basename)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Extract speaker notes / bullet outlines from Spurgeon sermon text files.'
    )
    parser.add_argument(
        '--input-dir', default='sermons',
        help='Directory containing sermon .txt files (default: sermons)'
    )
    parser.add_argument(
        '--output-dir', default='sermons_notes',
        help='Directory for output speaker notes (default: sermons_notes)'
    )
    parser.add_argument(
        '--file', default=None,
        help='Process a single file instead of a directory'
    )
    args = parser.parse_args()

    if args.file:
        filepath = args.file
        if not os.path.isfile(filepath):
            print(f"Error: file not found: {filepath}", file=sys.stderr)
            sys.exit(1)
        print(f"Processing: {filepath}")
        ok = process_file(filepath, args.output_dir)
        if ok:
            basename = os.path.basename(filepath)
            print(f"  -> {os.path.join(args.output_dir, basename)}")
        return

    input_dir = args.input_dir
    if not os.path.isdir(input_dir):
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(
        f for f in os.listdir(input_dir)
        if f.endswith('.txt')
    )

    if not files:
        print(f"No .txt files found in {input_dir}")
        sys.exit(1)

    print(f"Processing {len(files)} sermon files from {input_dir}/")
    print(f"Output directory: {args.output_dir}/")
    print()

    success = 0
    for i, filename in enumerate(files, 1):
        filepath = os.path.join(input_dir, filename)
        print(f"[{i:4d}/{len(files)}] {filename}")
        ok = process_file(filepath, args.output_dir)
        if ok:
            success += 1

    print()
    print(f"Done. {success}/{len(files)} files processed.")


if __name__ == '__main__':
    main()
