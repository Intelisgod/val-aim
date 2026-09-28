# -*- coding: utf-8 -*-
"""วอร์มส่วนตัว — ชุดวอร์ม 3 ข้อที่คิดจากประวัติซ้อมของผู้เล่นเอง (ตรรกะล้วน ไม่มี pygame แบบเดียวกับ routine.py)

ใช้เมื่อไม่มีแผนสดจาก dashboard (เครื่องเพื่อนที่ไม่มี valorant-stats / แผนเก่าเกิน 7 วัน) — เดิมทุกคนได้วอร์มมาตรฐาน
ชุดเดียวกัน (flick → spray → reaction ที่ config เมนู) ไม่ว่าจะเก่งหรืออ่อนโหมดไหน:
  ข้อ 1 วอร์มมือ  : โหมดเล็งคลิก (flick/precision/tracking/switch) ที่เล่นบ่อยสุด ที่ config ที่เล่นประจำ
  ข้อ 2 จุดอ่อน  : โหมดมีแรงค์ที่ฟอร์มต่ำสุด (ไม่ซ้ำข้อ 1, ไม่นับ reaction) ที่ config ประจำของโหมดนั้น
  ข้อ 3 reaction : variant ที่เล่นบ่อยสุด (ไม่เคยเล่น = static)
เป้าของข้อที่รู้ฟอร์ม = แรงค์ขั้นถัดไปจากฟอร์มตอนนี้ (routine.form — ค่าเฉลี่ย 5 รอบล่าสุดที่ config นั้น)

คิดจากประวัติ "ก่อนวันนี้" เท่านั้น → ชุดคงที่ทั้งวัน (ซ้อมแล้วจุดอ่อนเปลี่ยนกลางวัน รายการไม่สลับจนนับ ✓ ผิดข้อ) ;
ย้อนหลัง WINDOW_DAYS วัน ; ต้องรู้จักอย่างน้อย MIN_KNOWN โหมด (โหมดละ ≥ MIN_ROUNDS รอบที่ config ประจำ, กติการุ่นปัจจุบัน)
ไม่งั้น None → วอร์มมาตรฐาน (ผู้เล่นใหม่)
id รายการ d1..d3 ชุดเดียวกับวอร์มมาตรฐาน (แท็ก src warmup เดิม ; done_today จับคู่ id + ดริล จึงไม่นับข้ามโหมด)
"""

import datetime
import time
from collections import Counter

from .config import RANKS, mode_current
from . import routine as R

WINDOW_DAYS = 30
MIN_ROUNDS = 3          # รอบที่ config ประจำของโหมด ถึงจะนับว่า "รู้ฟอร์ม"
MIN_KNOWN = 2           # โหมดที่รู้ฟอร์มขั้นต่ำ — น้อยกว่านี้ยังเลือกจุดอ่อนไม่ได้ (ผู้เล่นใหม่ = วอร์มมาตรฐาน)
CLICK_MODES = ("flick", "precision", "tracking", "switch")
# โหมดที่เป็นข้อจุดอ่อนได้: มีแรงค์ + รอบสั้น ; gun ใช้แรงค์ดวลข้ามรอบ (~100 ดวล) วอร์ม 2 รอบไม่พอวัด, strafe/sniper ไม่มีแรงค์
WEAK_MODES = ("flick", "precision", "tracking", "switch", "placement", "dodge", "spray")
WHY_HAND = "เล่นบ่อยสุดของคุณ — วอร์มมือที่ config ที่คุ้น"
WHY_WEAK = "จุดอ่อนตอนนี้ — แรงค์ต่ำสุดในโหมดที่คุณเล่น"
WHY_REACT = "ปลุก reaction ก่อนเข้าเกม"
WHY_PROBE = "ยังวัดจุดอ่อนไม่ได้ — เล่นโหมดนี้ให้ครบ 3 รอบที่ config เดียวกัน แล้วจะเทียบได้"


def _day_start(now):
    d = datetime.datetime.fromtimestamp(now)
    return datetime.datetime(d.year, d.month, d.day).timestamp()


def _recent(hist, now):
    lo, hi = now - WINDOW_DAYS * 86400, _day_start(now)
    out = []
    for e in hist or []:
        if not isinstance(e, dict) or e.get("adapt") or not mode_current(e) or R._empty(e):
            continue
        at = e.get("at")
        if isinstance(at, (int, float)) and not isinstance(at, bool) and lo <= at < hi:
            out.append(e)
    return out


def _usual(rounds, md):
    """(variant, cfg) ที่เล่นบ่อยสุดของโหมด — cfg ตามกติกา same_cfg (reaction ไม่ผูก, spray = เวลา)"""
    if md == "reaction":
        return Counter(R.drill_key(e)[1] for e in rounds).most_common(1)[0][0], None
    if md == "spray":
        (v, dur), _n = Counter((R.drill_key(e)[1], e.get("duration")) for e in rounds).most_common(1)[0]
        return v, {"duration": dur}
    (dur, size), _n = Counter((e.get("duration"), e.get("size") or "medium") for e in rounds).most_common(1)[0]
    return "", {"duration": dur, "size": size}


def _item(iid, md, variant, cfg, cur, why):
    it = {"id": iid, "mode": md, "cfg": cfg, "why": why}
    if variant:
        it["variant"] = variant
    if cur is not None:
        it["target"] = RANKS[min(cur + 1, len(RANKS) - 1)][1]
    return it


def build(hist, now=None):
    """รายการวอร์มส่วนตัว [d1, d2, d3] หรือ None (ประวัติยังไม่พอ)"""
    now = time.time() if now is None else now
    recent = _recent(hist, now)
    by = {}
    for e in recent:
        by.setdefault(e.get("mode"), []).append(e)
    known = {}                      # mode -> (variant, cfg, form, n รอบทั้งหมดของโหมด)
    for md, rounds in by.items():
        if md not in WEAK_MODES and md != "reaction":
            continue
        variant, cfg = _usual(rounds, md)
        probe = {"mode": md, "variant": variant, "cfg": cfg}
        n_cfg = len([1 for e in rounds if R.drill_key(e) == R.drill_key(probe) and R.same_cfg(e, md, cfg)])
        if n_cfg < MIN_ROUNDS:
            continue
        cur, _n = R.form(recent, probe)
        if cur is not None:
            known[md] = (variant, cfg, cur, len(rounds))
    if len(known) < MIN_KNOWN:
        return None
    click = [m for m in CLICK_MODES if m in known]
    hand = max(click or [m for m in known if m != "reaction"] or list(known),
               key=lambda m: (known[m][3], -CLICK_MODES.index(m) if m in CLICK_MODES else -99))
    weak_pool = [m for m in WEAK_MODES if m in known and m != hand]
    weak = min(weak_pool, key=lambda m: (known[m][2], known[m][3])) if weak_pool else None
    items = [_item("d1", hand, known[hand][0], known[hand][1], known[hand][2], WHY_HAND)]
    if weak is not None:
        items.append(_item("d2", weak, known[weak][0], known[weak][1], known[weak][2], WHY_WEAK))
    else:
        # รู้ฟอร์มแค่ข้อ 1 + reaction — ข้อ 2 = โหมดมีแรงค์ที่เคยเล่นแต่ยังไม่ครบ MIN_ROUNDS (เล่นบ่อยสุดก่อน) ให้ได้ฟอร์มมาเทียบ ;
        # ไม่มีเลย = spray (โหมดวอร์มมาตรฐาน) — ป้ายบอกตรง ๆ ว่ายังวัดจุดอ่อนไม่ได้ ไม่เรียกว่า "จุดอ่อน"
        probe = [m for m in WEAK_MODES if m in by and m != hand]
        if probe:
            md = max(probe, key=lambda m: len(by[m]))
            v, cfg = _usual(by[md], md)
            items.append(_item("d2", md, v, cfg, None, WHY_PROBE))
        else:
            items.append({"id": "d2", "mode": "spray", "variant": "vandal", "cfg": None, "why": WHY_PROBE})
    if "reaction" in known:
        v, _c, cur, _n = known["reaction"]
        items.append(_item("d3", "reaction", v, None, cur, WHY_REACT))
    else:
        rv = Counter(R.drill_key(e)[1] for e in by.get("reaction", [])).most_common(1)
        items.append({"id": "d3", "mode": "reaction", "variant": rv[0][0] if rv else "static", "cfg": None,
                      "why": WHY_REACT})
    return items
