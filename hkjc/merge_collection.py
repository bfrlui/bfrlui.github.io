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
# Default racing day / racecourse. These can be overridden from the command
# line:  python merge_collection.py 15/07/2026 HV
RACE_DATE = "15/07/2026"

# Racecourse code for the racing day (HV = Happy Valley, ST = Sha Tin). Used to
# fetch the per-race header (race name, distance, class, track, etc.) from HKJC.
RACECOURSE = "HV"

# Human-readable racecourse name mapping (code -> Chinese name).
RACECOURSE_NAME = {"HV": "跑馬地", "ST": "沙田"}

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


def _parse_race_header_from_html(html):
    """
    Parse the structured race header from a HKJC racecard/localresults HTML
    page. Returns an OrderedDict with the fields needed for "_meta.race", or
    None if the header could not be located/parsed.

    The header lives in a <thead> row "第 N 場 (race_id)" followed by a
    <tbody class="f_fs13"> whose rows carry:
      - "第五班 - 1650米 - (40-0)"  -> race_class + distance
      - "場地狀況 :" 好地          -> track_condition
      - "摩法神采讓賽" / "賽道 :" 草地 - "C" 賽道  -> race_name + track
      - "HK$ 875,000"              -> prize_money
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # 1) race_id from the "第 N 場 (race_id)" header row.
    race_id = None
    head = soup.select_one("thead td")
    if head:
        m = re.search(r"第\s*\d+\s*場\s*\((\d+)\)", head.get_text(" ", strip=True))
        if m:
            race_id = int(m.group(1))

    # 2) Parse the structured rows in tbody.f_fs13.
    race_name = track_condition = track = prize_money = None
    distance = race_class = None

    for row in soup.select("tbody.f_fs13 tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        cells = [clean_text(c) for c in cells if c]
        if not cells:
            continue
        text = " ".join(cells)

        # "第五班 - 1650米 - (40-0)"
        m = re.search(r"第?([一二三四五六七八九十]+)班", text)
        if m and distance is None:
            class_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                         "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            race_class = class_map.get(m.group(1))
            dm = re.search(r"(\d+)\s*米", text)
            if dm:
                distance = int(dm.group(1))

        # "場地狀況 :" 好地
        if "場地狀況" in text:
            val = text.split("場地狀況", 1)[1].strip(" :")
            if val:
                track_condition = val

        # "摩法神采讓賽" / "賽道 :" 草地 - "C" 賽道
        if "賽道" in text:
            # race name is the cell before "賽道 :"
            for i, c in enumerate(cells):
                if "賽道" in c and i > 0:
                    name_candidate = cells[i - 1]
                    if name_candidate and "賽道" not in name_candidate:
                        race_name = name_candidate
            track_val = text.split("賽道", 1)[1].strip(" :")
            if track_val:
                track = track_val  # keep original double quotes

        # "HK$ 875,000"  (first cell only, ignore the trailing 時間 cells)
        for c in cells:
            if re.search(r"HK\$\s*[\d,]+", c):
                prize_money = c.strip()
                break

    if race_id is None and not (race_name or distance):
        return None

    return OrderedDict([
        ("race_id", race_id),
        ("race_name", race_name),
        ("distance", distance),
        ("race_class", race_class),
        ("track_condition", track_condition),
        ("track", track),
        ("prize_money", prize_money),
    ])


def _fetch_race_header(race_no):
    """
    Fetch the per-race header from HKJC, mirroring the logic of
    RacingRAGEngine._fetch_race_info: try the "racecard" page first, and if it
    fails (e.g. the race is already over and racecard is no longer available)
    fall back to the "localresults" page. Returns None if both fail.
    """
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    urls = [
        (f"https://racing.hkjc.com/zh-hk/local/information/racecard"
         f"?racedate={RACE_DATE}&Racecourse={RACECOURSE}&RaceNo={race_no}",
         "racecard"),
        (f"https://racing.hkjc.com/zh-hk/local/information/localresults"
         f"?racedate={RACE_DATE}&Racecourse={RACECOURSE}&RaceNo={race_no}",
         "localresults"),
    ]

    for url, page_name in urls:
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.encoding = "utf-8"
            if res.status_code != 200:
                continue
            header = _parse_race_header_from_html(res.text)
            if header:
                if page_name == "localresults":
                    print(f"[INFO] 第 {race_no} 場賽事標頭已由 {page_name} 備用頁面取得。")
                return header
        except Exception as e:
            print(f"[WARN] 抓取第 {race_no} 場賽事標頭失敗 ({page_name}): {e}")

    print(f"[WARN] 第 {race_no} 場賽事標頭解析失敗 (可能該場次不存在)")
    return None


def build_race_meta():
    """Build the "_meta.race" list by fetching each race's header from HKJC."""
    # Determine the set of race numbers present in the race-day sources.
    race_nos = set()
    for _, fname in RACE_DAY_SOURCES:
        data = load(fname)
        for race in data.keys():
            digits = "".join(filter(str.isdigit, str(race)))
            if digits:
                race_nos.add(int(digits))

    races = []
    for race_no in sorted(race_nos):
        header = _fetch_race_header(race_no)
        if header:
            races.append(header)
    return races


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
        ("race_course", RACECOURSE_NAME.get(RACECOURSE, RACECOURSE)),
        ("race", build_race_meta()),
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
    import sys

    # Optional command-line args:  python merge_collection.py <race_date> <racecourse>
    #   e.g.  python merge_collection.py 15/07/2026 HV
    if len(sys.argv) > 1:
        RACE_DATE = sys.argv[1]
    if len(sys.argv) > 2:
        RACECOURSE = sys.argv[2].upper()
        if RACECOURSE not in RACECOURSE_NAME:
            print(f"[WARN] 未知馬場代碼 '{RACECOURSE}'，將原樣輸出。")

    merge()
