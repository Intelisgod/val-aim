# -*- coding: utf-8 -*-
"""ตรรกะแรงค์ (Iron→Radiant) + reaction-time rank + helper — verbatim จากต้นฉบับ"""

from .config import *

__all__ = ["hexrgb", "parse_rank", "scaled_ranks", "get_rank", "next_rank",
           "rt_thresh", "get_rt_rank", "next_rt_rank", "VALID_TIERS"]

def hexrgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

VALID_TIERS = {"Iron", "Bronze", "Silver", "Gold", "Platinum", "Diamond",
               "Ascendant", "Immortal", "Radiant"}
_ROMAN = {"I": 1, "II": 2, "III": 3}

def parse_rank(name):
    """'Gold III' -> ('Gold', 3) ; 'Radiant' -> ('Radiant', 0)"""
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in _ROMAN:
        return parts[0], _ROMAN[parts[1]]
    return name, 0

def scaled_ranks(dur, size, md):
    # spray: gameplay ไม่ขึ้นกับขนาดเป้าที่เลือก (บอทขนาดคงที่ 0.42 ใน round.target_radius)
    # → ล็อกตัวคูณขนาดไว้ที่ medium เสมอ ปิดช่องโหว่ "เลือกเป้าเล็กได้ขีดถูกลง 40% ฟรี"
    # (พบจากการวัด 2026-08-01; ประวัติ spray เดิมของผู้ใช้เล่น medium ทั้งหมด — ป้ายแรงค์เก่าไม่ขยับ)
    sz = SIZE_SCALE["medium"] if md == "spray" else SIZE_SCALE.get(size, 1.0)
    f = sz * TIME_FACTOR.get(dur, dur / 30) * MODE_SCALE.get(md, 1.0)
    return [(round(b * f), n, c) for b, n, c in RANKS]

def get_rank(score, dur, size, md):
    cur = scaled_ranks(dur, size, md)[0]
    for row in scaled_ranks(dur, size, md):
        if score >= row[0]:
            cur = row
    return cur

def next_rank(score, dur, size, md):
    for row in scaled_ranks(dur, size, md):
        if score < row[0]:
            return row
    return None

def rt_thresh(t, variant):
    if variant == "flick" and t != float("inf"):
        return round(t * FLICK_RT_STRETCH + FLICK_RT_OFFSET)
    return t

def get_rt_rank(avg_rt, variant):
    for t, n, c in REACTION_RT_RANKS:
        if avg_rt <= rt_thresh(t, variant):
            return (rt_thresh(t, variant), n, c)
    return (float("inf"), 'Iron I', '#5C5C5C')

def next_rt_rank(avg_rt, variant):
    prev = None
    for t, n, c in REACTION_RT_RANKS:
        tt = rt_thresh(t, variant)
        if avg_rt <= tt:
            return (rt_thresh(prev[0], variant), prev[1], prev[2]) if prev else None
        prev = (t, n, c)
    return None

