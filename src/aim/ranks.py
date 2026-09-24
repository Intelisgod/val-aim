# -*- coding: utf-8 -*-
"""ตรรกะแรงค์ (Iron→Radiant) + reaction-time rank + helper — verbatim จากต้นฉบับ"""

from .config import *

__all__ = ["hexrgb", "parse_rank", "size_factor", "scaled_ranks", "get_rank", "next_rank",
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

def _spray_base(b):
    """บันได spray: ขีด base ≤ Ascendant I คงเดิม ; เหนือนั้นบีบเป็นเส้นตรงให้ Radiant ตก SPRAY_RADIANT_30S ที่ 30 วิ
    (สเกลเส้นตรงเดียวทำ Radiant เกินคะแนนเต็มที่เกมให้ได้ — เหตุผล/ตัวเลขดู config.SPRAY_TOP_KNEE)"""
    if b <= SPRAY_TOP_KNEE:
        return b
    top = SPRAY_RADIANT_30S / (SIZE_SCALE["medium"] * MODE_SCALE["spray"])
    return SPRAY_TOP_KNEE + (b - SPRAY_TOP_KNEE) * (top - SPRAY_TOP_KNEE) / (RANKS[-1][0] - SPRAY_TOP_KNEE)

def size_factor(md, size):
    """ตัวคูณขีดแรงค์ตามขนาดเป้าของโหมด md — medium = SIZE_SCALE["medium"] ทุกโหมด ; ใหญ่/เล็ก = medium ×
    อัตราส่วนต่อโหมด (config.MODE_SIZE_RATIO — ที่มาจาก sim + ข้อจำกัด + ตารางเทียบประวัติจริงดูที่นั่น) ;
    โหมดไม่มีแถว (placement) = SIZE_SCALE เดิม
    spray: gameplay ไม่ขึ้นกับขนาดเป้าที่เลือก (บอทขนาดคงที่ 0.42 ใน round.target_radius) → ล็อกที่ medium เสมอ
    ปิดช่องโหว่ "เลือกเป้าเล็กได้ขีดถูกลง 40% ฟรี" (พบจากการวัด 2026-08-01 ; ประวัติ spray เดิมเล่น medium ทั้งหมด)"""
    med = SIZE_SCALE["medium"]
    if md == "spray" or size == "medium":
        return med
    row = MODE_SIZE_RATIO.get(md)
    if row and size in row:
        return med * row[size]
    return SIZE_SCALE.get(size, 1.0)

def scaled_ranks(dur, size, md, weapon=None):
    """ขีดแรงค์ของ config — weapon มีผลเฉพาะ spray (config.SPRAY_WEAPON_SCALE ; None/ไม่รู้จัก = Vandal)"""
    f = size_factor(md, size) * TIME_FACTOR.get(dur, dur / 30) * MODE_SCALE.get(md, 1.0)
    if md == "spray":
        f *= SPRAY_WEAPON_SCALE.get(weapon or "vandal", 1.0)
        return [(round(_spray_base(b) * f), n, c) for b, n, c in RANKS]
    return [(round(b * f), n, c) for b, n, c in RANKS]

def get_rank(score, dur, size, md, weapon=None):
    rows = scaled_ranks(dur, size, md, weapon)
    cur = rows[0]
    for row in rows:
        if score >= row[0]:
            cur = row
    return cur

def next_rank(score, dur, size, md, weapon=None):
    for row in scaled_ranks(dur, size, md, weapon):
        if score < row[0]:
            return row
    return None

def rt_thresh(t, variant):
    """ขีด ms ของแรงค์ใน reaction variant — static = ตาราง REACTION_RT_RANKS ตรงๆ ; flick/peek ยืดตามเวลาเคลื่อนเมาส์
    (ที่มาของตัวยืด peek ดู config.PEEK_RT_STRETCH) — server (aimlink._aim_idx) เรียกตัวนี้ตัวเดียวทุก variant"""
    if variant == "flick" and t != float("inf"):
        return round(t * FLICK_RT_STRETCH + FLICK_RT_OFFSET)
    if variant == "peek" and t != float("inf"):
        return round(t * PEEK_RT_STRETCH + PEEK_RT_OFFSET)
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

