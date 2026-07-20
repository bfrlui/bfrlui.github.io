# -*- coding: utf-8 -*-
"""
hkjc_flatten_features.py
========================
Flatten `hkjc_collection.json` (nested multi-source HKJC horse data) into a
flat feature matrix suitable for tabular ML models (LightGBM / XGBoost /
CatBoost).

Grain (one row per):
    (race_date, race_id, horse_id)

Base table  : starters   (1:1, one row per horse-race)
Joined/aggregated sources (all time-filtered to < race_date to avoid leakage):
    vet, trackwork, incidents, exceptional, career

Implements the full feature dictionary from `feature_engineering_spec.html`
sections 2.1 - 2.5, plus the section 1.2 flattening operators that are not
repeated in the dictionary tables (vet_total_incidents_count, vet_recent_90d_flag,
gallop_count_28d, gallop_jockey_match_flag, incidents_count_last_5,
incidents_flag_blocked).

Section 3 (in-race relational scaling) is applied as an optional post-step,
adding *_z (Z-score) and *_pct (percentile rank) columns grouped by race_id.

Outputs:
    hkjc_features.csv   - flattened feature matrix (one row per starter)
    hkjc_features.json  - same data as a list of dicts
    hkjc_feature_dict.json - machine-readable feature dictionary

Usage:
    python hkjc_flatten_features.py
    python hkjc_flatten_features.py --input hkjc_collection.json --no-scale
"""
import argparse
import csv
import json
import os
import re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Generic parsing helpers
# ---------------------------------------------------------------------------

def to_int(value):
    """Parse an integer from HKJC strings like '40', '-3', '01', '-', '—', ''."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "-", "—", "–", "N/A", "None", "null"):
        return None
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None


def to_float(value):
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s in ("", "-", "—", "–", "N/A", "None", "null"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def parse_date(value, ref_date):
    """Parse HKJC dates: DD/MM/YYYY, DD/MM/YY, or DD/MM (year inferred).

    ref_date : datetime used to infer the year for DD/MM forms and to roll
    back a year when the inferred date would be in the future.
    """
    if not value:
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)          # DD/MM/YYYY
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2})$", s)          # DD/MM/YY
    if m:
        return datetime(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", s)                  # DD/MM
    if m:
        d = int(m.group(1)); mo = int(m.group(2))
        yr = ref_date.year
        try:
            cand = datetime(yr, mo, d)
        except ValueError:
            return None
        if cand > ref_date:
            cand = datetime(yr - 1, mo, d)
        return cand
    return None


def parse_time_to_sec(value):
    """Convert HKJC finishing / gallop time 'M.SS.cc' -> seconds (float).

    e.g. '1.41.86' -> 101.86 , '0.57.41' -> 57.41
    """
    if not value:
        return None
    s = str(value).strip()
    parts = s.split(".")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100.0
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 1:
            return float(parts[0])
    except ValueError:
        return None
    return None


def parse_margin_to_lengths(text):
    """Convert HKJC '頭馬距離' to lengths (float).

    Supports: 整數(5), 分數(3/4), 混合(1-1/4), 文字(頭位/頸位/短頭/鼻位).
    """
    if not text:
        return None
    t = str(text).strip()
    if "頭位" in t:
        return 0.2
    if "頸位" in t:
        return 0.3
    if "短頭" in t:
        return 0.1
    if "鼻位" in t:
        return 0.05
    if t in ("—", "-", "", "同時到達", "頸"):
        return None
    m = re.match(r"^(\d+)-(\d+)/(\d+)$", t)          # 1-1/4
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.match(r"^(\d+)/(\d+)$", t)                # 3/4
    if m:
        return int(m.group(1)) / int(m.group(2))
    m = re.match(r"^(\d+(\.\d+)?)$", t)              # 5 or 5.5
    if m:
        return float(m.group(1))
    return None


def days_between(d1, d2):
    """Absolute days from d1 to d2 (d2 - d1). Returns None if either missing."""
    if d1 is None or d2 is None:
        return None
    return (d2 - d1).days


def race_no_from_tag(tag):
    """'第 1 場' -> 1"""
    if not tag:
        return None
    m = re.search(r"第\s*(\d+)\s*場", str(tag))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Source-specific extractors
# ---------------------------------------------------------------------------

def extract_starters(starter, row):
    """Section 2.1 static & race-dynamics features from the base row."""
    age = to_int(starter.get("馬齡"))
    draw = to_int(starter.get("檔位"))
    decl_w = to_float(starter.get("負磅"))
    weight = to_float(starter.get("排位體重"))
    wchg = to_float(starter.get("排位體重+/-"))
    rating = to_int(starter.get("評分"))
    rchg = to_int(starter.get("評分+/-"))
    last_run = to_int(starter.get("上賽距今日數"))
    imp = str(starter.get("進口類別", "")).strip()

    row["f_horse_age"] = age if age is not None else 0          # median impute later
    row["f_draw"] = draw if draw is not None else 0
    row["f_declared_weight"] = decl_w if decl_w is not None else 0.0
    row["f_horse_weight"] = weight if weight is not None else 0.0
    row["f_weight_change"] = wchg if wchg is not None else 0.0
    row["f_weight_change_pct"] = (wchg / weight) if (wchg is not None and weight) else 0.0
    row["f_current_rating"] = rating if rating is not None else 40
    row["f_rating_change"] = rchg if rchg is not None else 0
    row["f_days_since_last_run"] = last_run if last_run is not None else 60
    row["f_is_imported_type"] = imp if imp else "UNKNOWN"
    return row


def extract_trackwork(trackworks, race_date, jockey, row):
    """Section 2.2 trackwork & fitness features (sliding windows)."""
    # Collect dated entries across all trackwork records for this horse/race.
    gallops, swims, trots, trials = [], [], [], []
    partner = 0
    jock_match = 0
    for tw in trackworks:
        for g in tw.get("快操", []) or []:
            d = parse_date(str(g).split(":")[0].strip(), race_date)
            gallops.append((d, g))
            if "伴跳馬" in g:
                partner = 1
            if jockey and jockey in g:
                jock_match = 1
        for s in tw.get("游泳", []) or []:
            d = parse_date(str(s).split(":")[0].strip(), race_date)
            swims.append(d)
        for t in tw.get("踱步", []) or []:
            d = parse_date(str(t).split(":")[0].strip(), race_date)
            trots.append(d)
        for tr in tw.get("試閘", []) or []:
            d = parse_date(str(tr).split(":")[0].strip(), race_date)
            trials.append(d)

    def count_within(items, days):
        n = 0
        for d in items:
            if d is None:
                continue
            delta = days_between(d, race_date)
            if delta is not None and 0 <= delta <= days:
                n += 1
        return n

    g7 = count_within([d for d, _ in gallops], 7)
    g14 = count_within([d for d, _ in gallops], 14)
    g28 = count_within([d for d, _ in gallops], 28)
    s14 = count_within(swims, 14)
    t14 = count_within(trots, 14)
    tr14 = count_within(trials, 14)

    # Most recent gallop last-sectional time (seconds).
    last_sec = None
    dated = [(d, s) for d, s in gallops if d is not None]
    if dated:
        dated.sort(key=lambda x: x[0], reverse=True)
        pre = dated[0][1].split("(")[0]
        nums = re.findall(r"\d+\.\d+", pre)
        if nums:
            last_sec = float(nums[-1])

    intensity14 = 3.0 * g14 + 2.5 * tr14 + 1.0 * s14 + 0.5 * t14

    row["f_gallop_count_7d"] = g7
    row["f_gallop_count_14d"] = g14
    row["f_gallop_count_28d"] = g28
    row["f_gallop_last_time_sec"] = last_sec if last_sec is not None else 30.0
    row["f_swim_count_14d"] = s14
    row["f_trot_count_14d"] = t14
    row["f_intensity_score_14d"] = intensity14
    row["f_has_partner_gallop"] = partner
    row["f_gallop_jockey_match_flag"] = jock_match
    return row


def extract_vet(vets, race_date, row):
    """Section 2.3 vet features (section 1.2 operators)."""
    days_list, recovery_list, tendon = [], [], 0
    for v in vets:
        d = to_int(v.get("特徵_傷患距今日數"))
        if d is not None:
            days_list.append(d)
            rec = to_int(v.get("特徵_康復期耗時天數"))
            if rec is not None:
                recovery_list.append(rec)
        detail = str(v.get("傷患詳情", ""))
        if re.search(r"肌腱|腿患|韌帶|骨折", detail):
            tendon = 1

    days_since = min(days_list) if days_list else 9999
    recovery = min(recovery_list) if recovery_list else 0
    recent_90 = sum(1 for d in days_list if d <= 90)

    row["f_vet_days_since_injury"] = days_since
    row["f_vet_recovery_days"] = recovery
    row["f_vet_tendon_issue"] = tendon
    row["f_vet_total_incidents_count"] = len(vets)
    row["f_vet_recent_90d_flag"] = 1 if recent_90 > 0 else 0
    return row


def extract_incidents(incidents, race_date, row):
    """Section 2.3 incident features (section 1.2 operators)."""
    last_days = 9999
    slow_out = 0
    gear_lost = 0
    blocked = 0
    count_last5 = 0
    for inc in incidents:
        d = parse_date(inc.get("上次事件日期"), race_date)
        if d is not None:
            delta = days_between(d, race_date)
            if delta is not None and delta >= 0:
                last_days = min(last_days, delta)
                if delta <= 9999:
                    count_last5 += 1
        summary = str(inc.get("競賽事件摘要", ""))
        if re.search(r"慢閘|失去平衡|向內斜跑|向外斜跑", summary):
            slow_out = 1
        if re.search(r"失去蹄鐵|配備脫落", summary):
            gear_lost = 1
        if re.search(r"受阻|受擠壓|無通路", summary):
            blocked = 1

    row["f_incident_last_days"] = last_days
    row["f_incident_slow_out_flag"] = slow_out
    row["f_incident_gear_lost_flag"] = gear_lost
    row["f_incident_blocked_flag"] = blocked
    row["f_incident_count_last_5"] = count_last5
    return row


def extract_exceptional(exceptionals, row):
    """Section 2.4 exceptional / gear-change features."""
    dist_delta = 0
    gear_first = 0
    gear_removed = 0
    rating_drop = 0
    for ex in exceptionals:
        d = to_int(ex.get("途程"))
        if d is not None:
            dist_delta = d
        r = to_int(ex.get("評分"))
        if r is not None:
            rating_drop = r
        gear = str(ex.get("配備", ""))
        if re.search(r"1|\+", gear):
            gear_first = 1
        if "-" in gear:
            gear_removed = 1

    row["f_exp_distance_delta"] = dist_delta
    row["f_exp_gear_first_time"] = gear_first
    row["f_exp_gear_removed"] = gear_removed
    row["f_exp_rating_drop"] = rating_drop
    return row


def extract_career(careers, race_date, cur_distance, cur_course, row):
    """Section 2.5 career historical-form features (leakage-safe)."""
    # --- basic_info aggregates (from the most recent career entry) ---
    basic = None
    for c in careers:
        bi = c.get("basic_info", {})
        if bi:
            basic = bi
            break

    total_runs = 0
    win_rate = 0.0
    top3_rate = 0.0
    if basic:
        m = re.match(r"(\d+)-(\d+)-(\d+)-(\d+)",
                     str(basic.get("冠-亞-季-總出賽次數*", "")))
        if m:
            wins, place, show, total = (int(m.group(i)) for i in range(1, 5))
            total_runs = total
            if total > 0:
                win_rate = wins / total
                top3_rate = (wins + place + show) / total

    # --- career_records: filter to strictly before race_date ---
    records = []
    for c in careers:
        for rec in c.get("career_records", []) or []:
            d = parse_date(rec.get("日期"), race_date)
            if d is not None and d < race_date:
                records.append(rec)
    # Sort most-recent first.
    records.sort(key=lambda r: parse_date(r.get("日期"), race_date), reverse=True)

    def rank_of(rec):
        return to_int(rec.get("名次"))

    avg_rank3 = avg_rank5 = 14.0
    avg_margin3 = 20.0
    if records:
        ranks = [rank_of(r) for r in records[:3] if rank_of(r) is not None]
        if ranks:
            avg_rank3 = sum(ranks) / len(ranks)
        ranks5 = [rank_of(r) for r in records[:5] if rank_of(r) is not None]
        if ranks5:
            avg_rank5 = sum(ranks5) / len(ranks5)
        margins = [parse_margin_to_lengths(r.get("頭馬距離"))
                   for r in records[:3]]
        margins = [m for m in margins if m is not None]
        if margins:
            avg_margin3 = sum(margins) / len(margins)

    # Course/distance specialty (same course + same distance as current race).
    cd_recs = [r for r in records
               if cur_course and cur_course in str(r.get("馬場/跑道/賽道", ""))
               and to_int(r.get("途程")) == cur_distance]
    cd_win_rate = 0.0
    if cd_recs:
        cd_wins = sum(1 for r in cd_recs if rank_of(r) == 1)
        cd_win_rate = cd_wins / len(cd_recs)

    # Best time over the same distance (seconds).
    best_time = 999.0
    same_dist = [parse_time_to_sec(r.get("完成時間"))
                 for r in records if to_int(r.get("途程")) == cur_distance]
    same_dist = [t for t in same_dist if t is not None]
    if same_dist:
        best_time = min(same_dist)

    # Pace style from most recent record's 沿途走位 (first two bends avg).
    pace_code = 3
    if records:
        pos = re.findall(r"\d+", str(records[0].get("沿途走位", "")))
        pos = [int(p) for p in pos[:2]]
        if pos:
            avg_pos = sum(pos) / len(pos)
            if avg_pos <= 3:
                pace_code = 1
            elif avg_pos <= 7:
                pace_code = 2
            else:
                pace_code = 3

    row["f_career_total_runs"] = total_runs
    row["f_career_win_rate"] = win_rate
    row["f_career_top3_rate"] = top3_rate
    row["f_career_avg_rank_last3"] = avg_rank3
    row["f_career_avg_rank_last5"] = avg_rank5
    row["f_career_avg_margin_last3"] = avg_margin3
    row["f_course_cd_win_rate"] = cd_win_rate
    row["f_best_time_sec"] = best_time
    row["f_pace_style_code"] = pace_code
    return row


# ---------------------------------------------------------------------------
# Main flatten routine
# ---------------------------------------------------------------------------

# Feature columns in spec order (numeric/binary only; categorical handled separately).
NUMERIC_FEATURES = [
    "f_horse_age", "f_draw", "f_declared_weight", "f_horse_weight",
    "f_weight_change", "f_weight_change_pct", "f_current_rating", "f_rating_change",
    "f_days_since_last_run",
    "f_gallop_count_7d", "f_gallop_count_14d", "f_gallop_count_28d",
    "f_gallop_last_time_sec", "f_swim_count_14d", "f_trot_count_14d",
    "f_intensity_score_14d", "f_has_partner_gallop", "f_gallop_jockey_match_flag",
    "f_vet_days_since_injury", "f_vet_recovery_days", "f_vet_tendon_issue",
    "f_vet_total_incidents_count", "f_vet_recent_90d_flag",
    "f_incident_last_days", "f_incident_slow_out_flag", "f_incident_gear_lost_flag",
    "f_incident_blocked_flag", "f_incident_count_last_5",
    "f_exp_distance_delta", "f_exp_gear_first_time", "f_exp_gear_removed",
    "f_exp_rating_drop",
    "f_career_total_runs", "f_career_win_rate", "f_career_top3_rate",
    "f_career_avg_rank_last3", "f_career_avg_rank_last5", "f_career_avg_margin_last3",
    "f_course_cd_win_rate", "f_best_time_sec", "f_pace_style_code",
]

# Imputation defaults (spec section 2.1 - 2.5).
IMPUTE = {
    "f_horse_age": 0, "f_draw": 0, "f_declared_weight": 0.0,
    "f_horse_weight": 0.0, "f_weight_change": 0.0, "f_weight_change_pct": 0.0,
    "f_current_rating": 40, "f_rating_change": 0, "f_days_since_last_run": 60,
    "f_gallop_count_7d": 0, "f_gallop_count_14d": 0, "f_gallop_count_28d": 0,
    "f_gallop_last_time_sec": 30.0, "f_swim_count_14d": 0, "f_trot_count_14d": 0,
    "f_intensity_score_14d": 0.0, "f_has_partner_gallop": 0,
    "f_gallop_jockey_match_flag": 0,
    "f_vet_days_since_injury": 9999, "f_vet_recovery_days": 0,
    "f_vet_tendon_issue": 0, "f_vet_total_incidents_count": 0,
    "f_vet_recent_90d_flag": 0,
    "f_incident_last_days": 9999, "f_incident_slow_out_flag": 0,
    "f_incident_gear_lost_flag": 0, "f_incident_blocked_flag": 0,
    "f_incident_count_last_5": 0,
    "f_exp_distance_delta": 0, "f_exp_gear_first_time": 0,
    "f_exp_gear_removed": 0, "f_exp_rating_drop": 0,
    "f_career_total_runs": 0, "f_career_win_rate": 0.0, "f_career_top3_rate": 0.0,
    "f_career_avg_rank_last3": 14.0, "f_career_avg_rank_last5": 14.0,
    "f_career_avg_margin_last3": 20.0, "f_course_cd_win_rate": 0.0,
    "f_best_time_sec": 999.0, "f_pace_style_code": 3,
}

# Continuous features for in-race Z-score (section 3.1).
ZSCORE_FEATURES = [
    "f_declared_weight", "f_horse_weight", "f_current_rating",
    "f_intensity_score_14d", "f_career_avg_rank_last3",
]
# Features for in-race percentile rank (section 3.2).
PCT_FEATURES = ["f_draw", "f_rating_change", "f_best_time_sec"]


def flatten(collection, meta):
    race_date = parse_date(meta.get("race_date"), datetime(2026, 1, 1))
    # Map race number -> (race_id, distance, course).
    race_map = {}
    for i, r in enumerate(meta.get("race", [])):
        no = i + 1
        race_map[no] = {
            "race_id": r.get("race_id"),
            "distance": to_int(r.get("distance")),
            "course": meta.get("race_course", ""),
        }

    rows = []
    for horse_name, horse in collection.items():
        starters = horse.get("starters", []) or []
        for st in starters:
            rno = race_no_from_tag(st.get("_race"))
            info = race_map.get(rno, {})
            race_id = info.get("race_id")
            cur_distance = info.get("distance")
            cur_course = info.get("course")
            jockey = str(st.get("騎師", ""))

            row = {
                "race_date": meta.get("race_date"),
                "race_id": race_id,
                "race_no": rno,
                "horse_id": st.get("horse_id") or st.get("馬匹編號") or horse_name,
                "horse_name": horse_name,
                "jockey": jockey,
                "trainer": st.get("練馬師"),
                "distance": cur_distance,
                "course": cur_course,
            }

            # Match race-day source entries to the same _race tag.
            tag = st.get("_race")
            vet = [v for v in (horse.get("vet", []) or []) if v.get("_race") == tag]
            tw = [t for t in (horse.get("trackwork", []) or []) if t.get("_race") == tag]
            inc = [i for i in (horse.get("incidents", []) or []) if i.get("_race") == tag]
            exc = [e for e in (horse.get("exceptional", []) or []) if e.get("_race") == tag]
            # career is historical (no _race tag) -> use all.
            car = horse.get("career", []) or []

            extract_starters(st, row)
            extract_trackwork(tw, race_date, jockey, row)
            extract_vet(vet, race_date, row)
            extract_incidents(inc, race_date, row)
            extract_exceptional(exc, row)
            extract_career(car, race_date, cur_distance, cur_course, row)

            # Target columns (label, NOT a feature) from the current race result.
            finish = None
            for c in car:
                for rec in c.get("career_records", []) or []:
                    if to_int(rec.get("場次")) == race_id:
                        _r = to_int(rec.get("名次"))
                        finish = _r if _r is not None else None
                        break
                if finish is not None:
                    break
            row["target_finish_position"] = finish if finish is not None else -1
            row["target_won"] = 1 if finish == 1 else 0

            rows.append(row)
    return rows


def apply_in_race_scaling(rows):
    """Section 3: grouped-by-race_id Z-score and percentile-rank columns."""
    from statistics import mean, pstdev

    groups = {}
    for i, r in enumerate(rows):
        groups.setdefault(r.get("race_id"), []).append(i)

    for rid, idxs in groups.items():
        if len(idxs) < 2:
            for f in ZSCORE_FEATURES:
                rows[idxs[0]][f + "_z"] = 0.0
            for f in PCT_FEATURES:
                rows[idxs[0]][f + "_pct"] = 0.5
            continue

        for f in ZSCORE_FEATURES:
            vals = [rows[i][f] for i in idxs]
            mu = mean(vals)
            sd = pstdev(vals)
            for i in idxs:
                v = rows[i][f]
                rows[i][f + "_z"] = (v - mu) / sd if sd > 0 else 0.0

        for f in PCT_FEATURES:
            vals = [rows[i][f] for i in idxs]
            order = sorted(range(len(idxs)), key=lambda k: vals[k])
            n = len(idxs)
            rank = {idxs[order[k]]: k + 1 for k in range(n)}
            for i in idxs:
                rows[i][f + "_pct"] = (rank[i] - 1) / (n - 1) if n > 1 else 0.5
    return rows


def one_hot_import(rows):
    """One-hot encode f_is_imported_type (spec 2.1)."""
    cats = sorted({r["f_is_imported_type"] for r in rows})
    for c in cats:
        col = "f_import_" + re.sub(r"\W+", "", c)
        for r in rows:
            r[col] = 1 if r["f_is_imported_type"] == c else 0
    return rows, cats


def build_feature_dict(rows, import_cats):
    """Emit a machine-readable feature dictionary for documentation."""
    fd = []
    for f in NUMERIC_FEATURES:
        fd.append({"name": f, "dtype": "float" if "." in f or f in (
            "f_gallop_last_time_sec", "f_intensity_score_14d", "f_best_time_sec")
            else "int", "imputation": IMPUTE.get(f)})
    for c in import_cats:
        fd.append({"name": "f_import_" + re.sub(r"\W+", "", c),
                   "dtype": "int (0/1)", "imputation": 0,
                   "note": "one-hot of f_is_imported_type=%s" % c})
    for f in ZSCORE_FEATURES:
        fd.append({"name": f + "_z", "dtype": "float",
                   "note": "in-race Z-score (grouped by race_id)"})
    for f in PCT_FEATURES:
        fd.append({"name": f + "_pct", "dtype": "float",
                   "note": "in-race percentile rank (grouped by race_id)"})
    fd.append({"name": "target_finish_position", "dtype": "int",
               "note": "LABEL: actual finish position (leakage-safe)"})
    fd.append({"name": "target_won", "dtype": "int (0/1)",
               "note": "LABEL: 1 if won"})
    return fd


def main():
    ap = argparse.ArgumentParser(description="Flatten HKJC collection for ML.")
    ap.add_argument("--input", default="hkjc_collection.json")
    ap.add_argument("--output-csv", default="hkjc_features.csv")
    ap.add_argument("--output-json", default="hkjc_features.json")
    ap.add_argument("--no-scale", action="store_true",
                    help="Disable in-race relational scaling (section 3).")
    args = ap.parse_args()

    with open(os.path.join(BASE, args.input), encoding="utf-8") as fh:
        data = json.load(fh)
    meta = data.get("_meta", {})
    collection = data.get("horses", data)

    rows = flatten(collection, meta)
    if not args.no_scale:
        rows = apply_in_race_scaling(rows)
    rows, import_cats = one_hot_import(rows)

    # Column order: keys, numeric features, one-hot, scaled, targets.
    base_keys = ["race_date", "race_id", "race_no", "horse_id", "horse_name",
                 "jockey", "trainer", "distance", "course"]
    one_hot_cols = ["f_import_" + re.sub(r"\W+", "", c) for c in import_cats]
    scaled_cols = [f + "_z" for f in ZSCORE_FEATURES] + [f + "_pct" for f in PCT_FEATURES]
    targets = ["target_finish_position", "target_won"]
    columns = base_keys + NUMERIC_FEATURES + one_hot_cols + scaled_cols + targets

    # Write CSV.
    with open(os.path.join(BASE, args.output_csv), "w", newline="",
              encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Write JSON.
    with open(os.path.join(BASE, args.output_json), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    # Feature dictionary.
    fd = build_feature_dict(rows, import_cats)
    with open(os.path.join(BASE, "hkjc_feature_dict.json"), "w",
              encoding="utf-8") as fh:
        json.dump(fd, fh, ensure_ascii=False, indent=2)

    print("[OK] Flattened %d starter rows -> %s / %s" %
          (len(rows), args.output_csv, args.output_json))
    print("[OK] %d feature columns (%d numeric, %d one-hot, %d scaled, 2 targets)"
          % (len(columns), len(NUMERIC_FEATURES), len(one_hot_cols),
             len(scaled_cols)))
    print("[OK] Feature dictionary -> hkjc_feature_dict.json")


if __name__ == "__main__":
    main()
