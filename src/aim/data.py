# -*- coding: utf-8 -*-
"""โหลด/เซฟ aim_trainer_data.json — เก็บใน data/ ระดับ root โปรเจกต์ (แบบเดียวกับ valorant-stats)"""

import json
import os
import time

from .config import DEFAULT_SETTINGS, HISTORY_MAX, HISTORY_SHOTS_KEEP

# โครงสร้าง: aim-trainer/src/aim/data.py → root = dirname สามชั้น แล้วเข้า data/
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_FILE = os.path.join(_ROOT, "data", "aim_trainer_data.json")
BACKUP_FILE = DATA_FILE.replace(".json", ".backup.json")

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _atomic_write(path, blob):
    """เขียนลง .tmp แล้ว replace — ไฟดับกลางเขียนจะไม่ได้ไฟล์ครึ่งๆ กลางๆ
    และ dashboard ที่อ่านไฟล์นี้อยู่จะไม่มีวันเห็นไฟล์ที่ยังเขียนไม่จบ"""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def trim_history(h):
    """ตัดประวัติตามเพดาน HISTORY_MAX (ทิ้งเก่าสุดก่อน) และถอด shots ออกจากรอบที่เก่ากว่า
    HISTORY_SHOTS_KEEP รอบล่าสุด (จำจำนวนไว้ใน shots_n) — แก้ list ในที่ คืน h เดิม
    เรียกทุกครั้งหลัง append ใน round.end_game; selftest เรียกตรงกับ list ปลอม"""
    if len(h) > HISTORY_MAX:
        del h[:len(h) - HISTORY_MAX]
    for e in h[:-HISTORY_SHOTS_KEEP]:
        sh = e.get("shots")
        if sh:
            e["shots_n"] = len(sh)
            e["shots"] = []
    return h

def load_data():
    base = {"settings": json.loads(json.dumps(DEFAULT_SETTINGS)), "name": "", "leaderboard": [], "history": []}
    d = _read_json(DATA_FILE)
    if d is None and os.path.exists(DATA_FILE):
        # ไฟล์เสีย — กู้จาก backup แล้วเก็บตัวเสียไว้ ห้ามให้ save_data รอบหน้าเขียนทับ
        # (ไฟล์นี้คือประวัติซ้อมทั้งหมด และมักซ่อมมือได้เพราะพังแค่ไม่กี่ไบต์)
        d = _read_json(BACKUP_FILE)
        try:
            os.replace(DATA_FILE, DATA_FILE + time.strftime(".corrupt-%Y%m%d-%H%M%S"))
        except OSError:
            pass
    if isinstance(d, dict):
        base.update(d)   # คีย์ที่โมดูลอื่นเพิ่มเอง (เช่น benchmark_history) ต้องไม่หายตอนเซฟรอบถัดไป
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
        s.update(base["settings"] if isinstance(base["settings"], dict) else {})
        ch = dict(DEFAULT_SETTINGS["ch"])
        ch.update(s.get("ch") or {})
        s["ch"] = ch
        base["settings"] = s
    return base

def save_data(d):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        blob = json.dumps(d, ensure_ascii=False).encode("utf-8")
        prev = None
        try:
            with open(DATA_FILE, "rb") as f:
                prev = f.read()
        except OSError:
            pass
        if prev:
            _atomic_write(BACKUP_FILE, prev)   # สำรองของเดิมไว้หนึ่งชุดก่อนทับ
        _atomic_write(DATA_FILE, blob)
    except Exception:
        pass
