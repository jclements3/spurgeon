#!/usr/bin/env python3
"""Build www/data/manifest.json from sermons/ and txt/ directories."""

import json
import os
import re

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERMONS_DIR = os.path.join(PROJ, "sermons")
NOTES_DIR = os.path.join(PROJ, "sermons_notes")
PRAYERS_DIR = os.path.join(PROJ, "txt")
OUT = os.path.join(PROJ, "www", "data", "manifest.json")

# Volume ranges: each volume contains ~53 sermons (volumes 1-63)
# Based on the New Park Street Pulpit (vols 1-6, sermons 1-347)
# and Metropolitan Tabernacle Pulpit (vols 7-63, sermons 348-3563).
# Approximate: ~53-57 sermons per volume.
# We'll compute from the notes files which have date info, but a simple
# approximation is: vol = ((num - 1) // 57) + 1, capped at 63.
# More accurate mapping based on known boundaries:
VOLUME_BOUNDARIES = [
    (1, 53, 1), (54, 110, 2), (111, 167, 3), (168, 224, 4),
    (225, 281, 5), (282, 347, 6), (348, 404, 7), (405, 461, 8),
    (462, 518, 9), (519, 575, 10), (576, 632, 11), (633, 689, 12),
    (690, 746, 13), (747, 803, 14), (804, 860, 15), (861, 917, 16),
    (918, 974, 17), (975, 1031, 18), (1032, 1088, 19), (1089, 1145, 20),
    (1146, 1202, 21), (1203, 1259, 22), (1260, 1316, 23), (1317, 1373, 24),
    (1374, 1430, 25), (1431, 1487, 26), (1488, 1544, 27), (1545, 1601, 28),
    (1602, 1658, 29), (1659, 1715, 30), (1716, 1772, 31), (1773, 1829, 32),
    (1830, 1886, 33), (1887, 1943, 34), (1944, 2000, 35), (2001, 2057, 36),
    (2058, 2114, 37), (2115, 2171, 38), (2172, 2228, 39), (2229, 2285, 40),
    (2286, 2342, 41), (2343, 2399, 42), (2400, 2456, 43), (2457, 2513, 44),
    (2514, 2570, 45), (2571, 2627, 46), (2628, 2684, 47), (2685, 2741, 48),
    (2742, 2798, 49), (2799, 2855, 50), (2856, 2912, 51), (2913, 2969, 52),
    (2970, 3026, 53), (3027, 3083, 54), (3084, 3140, 55), (3141, 3197, 56),
    (3198, 3254, 57), (3255, 3311, 58), (3312, 3368, 59), (3369, 3425, 60),
    (3426, 3482, 61), (3483, 3539, 62), (3540, 3563, 63),
]


def get_volume(num):
    for lo, hi, vol in VOLUME_BOUNDARIES:
        if lo <= num <= hi:
            return vol
    return 63


def extract_scripture_from_notes(filename):
    """Extract scripture reference from notes file (line 3: 'Scripture: ...')."""
    path = os.path.join(NOTES_DIR, filename)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("Scripture:"):
                    return line[len("Scripture:"):].strip()
    except Exception:
        pass
    return ""


def extract_scripture_from_sermon(filepath):
    """Fallback: try to find a scripture reference in the sermon text."""
    # Look for pattern like "Book Chapter:Verse" in first 15 lines
    books = (
        r"Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|"
        r"1 Samuel|2 Samuel|1 Kings|2 Kings|1 Chronicles|2 Chronicles|"
        r"Ezra|Nehemiah|Esther|Job|Psalm|Psalms|Proverbs|Ecclesiastes|"
        r"Song of Solomon|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|"
        r"Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|"
        r"Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|"
        r"1 Corinthians|2 Corinthians|Galatians|Ephesians|Philippians|"
        r"Colossians|1 Thessalonians|2 Thessalonians|1 Timothy|2 Timothy|"
        r"Titus|Philemon|Hebrews|James|1 Peter|2 Peter|1 John|2 John|"
        r"3 John|Jude|Revelation"
    )
    pattern = re.compile(r"(" + books + r")\s+\d+:\d+")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 15:
                    break
                m = pattern.search(line)
                if m:
                    # Grab from match start to end of recognizable ref
                    rest = line[m.start():]
                    ref_match = re.match(
                        r"(" + books + r")\s+\d+:\d+(?:-\d+)?", rest
                    )
                    if ref_match:
                        return ref_match.group(0).strip()
                    return m.group(0).strip()
    except Exception:
        pass
    return ""


def build_sermons():
    entries = []
    files = sorted(os.listdir(SERMONS_DIR))
    for fname in files:
        if not fname.endswith(".txt"):
            continue
        m = re.match(r"(\d+)_(.+)\.txt$", fname)
        if not m:
            continue
        num = int(m.group(1))
        file_stem = fname[:-4]  # remove .txt

        filepath = os.path.join(SERMONS_DIR, fname)
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            title = f.readline().strip()

        # Get scripture from notes first, fallback to sermon text
        scripture = extract_scripture_from_notes(fname)
        if not scripture:
            scripture = extract_scripture_from_sermon(filepath)

        vol = get_volume(num)

        entries.append({
            "num": num,
            "title": title,
            "file": file_stem,
            "scripture": scripture,
            "volume": vol,
        })
    return entries


def build_prayers():
    entries = []
    files = sorted(os.listdir(PRAYERS_DIR))
    for fname in files:
        if not fname.endswith(".txt"):
            continue
        # Match numbered prayers 01-50
        m = re.match(r"(\d{2})[A-Z]", fname)
        if not m:
            continue
        num = int(m.group(1))
        if num < 1 or num > 50:
            continue
        # Skip the apostrophe variant
        if "'" in fname:
            continue
        file_stem = fname[:-4]

        filepath = os.path.join(PRAYERS_DIR, fname)
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            title = f.readline().strip().rstrip(".")

        entries.append({
            "num": num,
            "title": title,
            "file": file_stem,
        })

    # Deduplicate by number (keep first)
    seen = set()
    deduped = []
    for e in entries:
        if e["num"] not in seen:
            seen.add(e["num"])
            deduped.append(e)
    return deduped


def main():
    sermons = build_sermons()
    prayers = build_prayers()

    manifest = {
        "sermons": sermons,
        "prayers": prayers,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="ascii") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)

    print(f"Wrote {len(sermons)} sermons and {len(prayers)} prayers to {OUT}")


if __name__ == "__main__":
    main()
