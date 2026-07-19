# -*- coding: utf-8 -*-
"""
Merge HKJC horse data JSON files into one collection keyed by the join field 馬名.

Design goals (for a growing "big data collection"):
  * Each source file is namespaced under its own sub-key so field collisions
    (e.g. 6次近績 / 練馬師 appear in both trackwork and starters) never overwrite.
  * Each attached record keeps a "_race" provenance tag (which 第 N 場 it came from).
  * Per-horse data is stored as a LIST per source, so a horse that later appears
    in multiple races/files is captured without loss.
  * career is inherently per-horse (keyed by 馬名) -> stored as a LIST, one
    entry per career file, each tagged with its _race (parsed from the filename).
  * Each race-day entry gets a "_race_date" provenance tag. career is historical
    (not generated on a racing day) so it carries no _race_date.
  * NOTE: 同廄馬匹摘要 (per-race stablemate summary) is currently ignored and
    will be handled later.
"""
import json
import os
import re
import unicodedata
from collections import OrderedDict

BASE = os.path.dirname(os.path.abspath(__file__))

# Invisible / non-breaking characters scraped from HKJC web pages that should be
# normalized away so the output JSON stays clean ASCII-space / standard text.
_INVISIBLE_MAP = {
    "\u00a0": " ",   # NO-BREAK SPACE
    "\u200b": "",    # ZERO WIDTH SPACE
    "\u200c": "",    # ZERO WIDTH NON-JOINER
    "\u200d": "",    # ZERO WIDTH JOINER
    "\u00ad": "",    # SOFT HYPHEN
    "\u200e": "",    # LEFT-TO-RIGHT MARK
    "\u200f": "",    # RIGHT-TO-LEFT MARK
    "\u2028": " ",   # LINE SEPARATOR
    "\u2029": " ",   # PARAGRAPH SEPARATOR
    "\ufeff": "",    # BYTE ORDER MARK
    "\u2060": "",    # WORD JOINER
}


def clean_text(value):
    """Recursively strip invisible/unicode characters from all strings."""
    if isinstance(value, str):
        for bad, good in _INVISIBLE_MAP.items():
            if bad in value:
                value = value.replace(bad, good)
        # Collapse any resulting multiple spaces and trim.
        value = re.sub(r"\s+", " ", value).strip()
        return value
    if isinstance(value, list):
        return [clean_text(v) for v in value]
    if isinstance(value, dict):
        return OrderedDict((k, clean_text(v)) for k, v in value.items())
    return value

# The racing day the web-page sources were scraped from. career is historical
# and not tied to a single racing day, so it has no _race_date.
RACE_DATE = "15/07/2026"

# Race-day sources (scraped from HKJC web pages on RACE_DATE). Each entry gets a
# _race_date tag.
RACE_DAY_SOURCES = [
    ("vet",        "hkjc_vet_features_v2.json"),
    ("trackwork",  "hkjc_trackwork_perfect.json"),
    ("starters",   "hkjc_starters_perfect.json"),
    ("incidents",  "hkjc_incidents_perfect.json"),
    ("exceptional", "hkjc_exceptional_ultimate.json"),
]

# Career-history sources. Each file is keyed by horse name (historical data,
# no _race_date). The race number is parsed from the filename
# (hkjc_career_history_raw_race_N.json -> 第 N 場) and stored as _race.
CAREER_FILES = [
    "hkjc_career_history_raw_race_1.json",
    "hkjc_career_history_raw_race_2.json",
    "hkjc_career_history_raw_race_3.json",
    "hkjc_career_history_raw_race_4.json",
    "hkjc_career_history_raw_race_5.json",
    "hkjc_career_history_raw_race_6.json",
    "hkjc_career_history_raw_race_7.json",
    "hkjc_career_history_raw_race_8.json",
    "hkjc_career_history_raw_race_9.json",
]

JOIN_KEY = "馬名"
OUTPUT_FILE = "hkjc_collection.json"


def race_from_filename(fname):
    """Extract the race number from a career filename, e.g. race_2 -> 第 2 場."""
    m = re.search(r"race_(\d+)", fname)
    return f"第 {int(m.group(1))} 場" if m else None


def load(name):
    with open(os.path.join(BASE, name), encoding="utf-8") as fh:
        return clean_text(json.load(fh))


def merge():
    collection = OrderedDict()          # 馬名 -> merged record
    stats = OrderedDict()

    def get_horse(name):
        if name not in collection:
            collection[name] = OrderedDict()
            collection[name][JOIN_KEY] = name
        return collection[name]

    # --- Race-day sources (each entry tagged with _race_date) ---
    for src_key, fname in RACE_DAY_SOURCES:
        data = load(fname)
        stats[src_key] = 0

        if src_key == "exceptional":
            # race -> {個別馬匹因素: [...], 同廄馬匹摘要: [...]}
            for race, val in data.items():
                factors = val.get("個別馬匹因素", [])
                for item in factors:
                    name = item.get(JOIN_KEY)
                    if not name:
                        continue
                    horse = get_horse(name)
                    entry = OrderedDict(item)
                    entry["_race"] = race
                    entry["_race_date"] = RACE_DATE
                    horse.setdefault(src_key, []).append(entry)
                    stats[src_key] += 1
            continue

        # Generic race-keyed list files: race -> [ {馬名, ...}, ... ]
        for race, lst in data.items():
            for item in lst:
                name = item.get(JOIN_KEY)
                if not name:
                    continue
                horse = get_horse(name)
                entry = OrderedDict(item)
                entry["_race"] = race
                entry["_race_date"] = RACE_DATE
                horse.setdefault(src_key, []).append(entry)
                stats[src_key] += 1

    # --- Career-history sources (keyed by horse name, no _race_date) ---
    stats["career"] = 0
    for fname in CAREER_FILES:
        race = race_from_filename(fname)
        data = load(fname)
        for name, rec in data.items():
            horse = get_horse(name)
            entry = OrderedDict(rec)
            if race:
                entry["_race"] = race
            horse.setdefault("career", []).append(entry)
            stats["career"] += 1

    # Attach auxiliary sections
    out = OrderedDict()
    out["_meta"] = OrderedDict([
        ("join_key", JOIN_KEY),
        ("race_date", RACE_DATE),
        ("source_files", [f for _, f in RACE_DAY_SOURCES] + list(CAREER_FILES)),
        ("total_horses", len(collection)),
        ("records_per_source", stats),
        ("generated_from", "merge_collection.py"),
    ])
    out["horses"] = collection

    with open(os.path.join(BASE, OUTPUT_FILE), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print("Merged collection written to", OUTPUT_FILE)
    print("Total horses:", len(collection))
    print("Records per source:", dict(stats))


if __name__ == "__main__":
    merge()
