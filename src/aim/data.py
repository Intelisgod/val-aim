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
    """คืน (status, data): status = ok / missing / unreadable / corrupt
    unreadable = ไฟล์มีอยู่แต่เปิดอ่านไม่ได้ (โดนล็อก/permission บน Windows — มักชั่วคราว)
    corrupt    = อ่านได้แต่ parse ไม่ผ่าน — มีแค่กรณีนี้ที่ "ไฟล์เสียจริง"
    (23 ก.ย. 2026: ไฟล์ดี ๆ โดนย้ายเป็น .corrupt ทั้งที่เหมือน backup ทุกไบต์ เพราะโค้ดเดิม
    เหมาว่า "อ่านไม่ได้ = เสีย" — แยกสองกรณีนี้ออกจากกัน อ่านไม่ได้ให้ลองซ้ำก่อนแล้วห้ามแตะไฟล์)"""
    if not os.path.exists(path):
        return "missing", None
    raw = None
    for attempt in range(3):
        try:
            with open(path, "rb") as f:
                raw = f.read()
            break
        except OSError:
            if attempt < 2:
                time.sleep(0.15)
    if raw is None:
        return "unreadable", None
    try:
        return "ok", json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        return "corrupt", None

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

def _valid_data(d):
    """โครงสร้างขั้นต่ำที่โมดูลอื่นพึ่ง — ไฟล์เก่าที่ขาดคีย์ optional ผ่านได้ แต่ container ผิดชนิดไม่ผ่าน"""
    if not isinstance(d, dict):
        return False
    for key in ("history", "leaderboard", "benchmark_history"):
        if key in d and (not isinstance(d[key], list)
                         or any(not isinstance(e, dict) for e in d[key])):
            return False
    settings = d.get("settings", {})
    return (isinstance(settings, dict)
            and isinstance(settings.get("ch", {}), dict)
            and isinstance(d.get("name", ""), str))

def _preserve_invalid(path):
    """ย้ายไฟล์เสียไปเก็บข้าง ๆ (ห้ามลบ — มักซ่อมมือได้เพราะพังแค่ไม่กี่ไบต์)
    ชื่อ = วันเวลาอ่านง่าย + เศษนาโนวิ กันชนกันเมื่อกู้ซ้ำในวินาทีเดียว"""
    os.replace(path, path + time.strftime(".corrupt-%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000:06d}")

# สถานะให้ game.py โชว์แบนเนอร์ — LOAD_WARNING เคลียร์เมื่อเซฟสำเร็จครั้งถัดไป
LAST_SAVE_ERROR = None
LOAD_WARNING = None
# โหลดมาจากไหน: main / backup / fresh (ไม่มีทั้งคู่หรือใช้ไม่ได้) — ไว้ดีบัก/เทส
LOAD_SOURCE = None
# ค้างกระทบยอดคีย์ที่ไม่ใช่ history หลังโหลดตอนไฟล์หลัก "อ่านไม่ได้" (โดนล็อก): ไฟล์หลักบนดิสก์ใหม่กว่า
# ของในหน่วยความจำ (backup = ช้ากว่าหนึ่งเซฟ หรือค่า default ถ้า backup ใช้ไม่ได้) — เซฟแรกที่อ่านไฟล์หลักได้
# ต้องเอา settings/name ของดิสก์คืนมา (ยกเว้นที่ผู้เล่นแก้เองหลังโหลด) + รวม leaderboard/benchmark_history
# ไม่งั้น sens ย้อนเป็นค่าเก่าเงียบๆ แล้วเซฟถัดไปทับ backup ด้วย = หายถาวร (23 ก.ย. 2026: sens 0.123→0.4)
# {"obj": dict ที่ load_data คืน, "settings": สำเนา settings ณ ตอนโหลด, "name": ชื่อ ณ ตอนโหลด} หรือ None
_RECONCILE = None
_MISSING = object()

def load_data():
    global LOAD_WARNING, LOAD_SOURCE, _RECONCILE
    base = {"settings": json.loads(json.dumps(DEFAULT_SETTINGS)), "name": "", "leaderboard": [], "history": []}
    st, d = _read_json(DATA_FILE)
    if st == "ok" and not _valid_data(d):
        st = "corrupt"
    rewrite_main = False
    warn = None
    if st != "ok":
        bst, bd = _read_json(BACKUP_FILE)
        d = bd if (bst == "ok" and _valid_data(bd)) else None
        if st == "corrupt":
            # ไฟล์เสียจริง — เก็บแยกไว้ ห้ามให้ save_data เอาไปทับ backup ที่ยังดี
            try:
                _preserve_invalid(DATA_FILE)
            except OSError:
                pass  # save_data ตรวจซ้ำก่อนทับ
            rewrite_main = d is not None
            warn = ("ไฟล์ประวัติเสีย กู้จาก backup แล้ว — ไฟล์เดิมเก็บไว้ที่ .corrupt-*"
                            if d is not None else "ไฟล์ประวัติเสียและ backup ใช้ไม่ได้ — เริ่มประวัติใหม่ (ไฟล์เดิมเก็บไว้ที่ .corrupt-*)")
        elif st == "unreadable":
            # เปิดอ่านไม่ได้ (โดนล็อก) ≠ เสีย — ไม่ย้าย ไม่เขียนทับ ใช้ backup ไปก่อน
            # ถ้า backup เก่ากว่าไฟล์หลัก save_data จะ merge ประวัติที่หายกลับมาให้ตอนเซฟ
            warn = "อ่านไฟล์ประวัติไม่ได้ (ถูกโปรแกรมอื่นล็อก?) — ใช้ backup ชั่วคราว"
        elif st == "missing" and d is not None:
            # ไฟล์หลักหาย (เช่นถูกย้ายเป็น .corrupt ไปแล้ว) แต่ backup ดี — เขียนคืนทันที
            # ไม่งั้น dashboard ที่อ่านไฟล์หลักอย่างเดียวจะไม่เห็นข้อมูลซ้อมจนกว่าจะซ้อมจบรอบ
            rewrite_main = True
            warn = "ไฟล์ประวัติหาย กู้จาก backup แล้ว"
    if isinstance(d, dict):
        base.update(d)   # คีย์ที่โมดูลอื่นเพิ่มเอง (เช่น benchmark_history) ต้องไม่หายตอนเซฟรอบถัดไป
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
        s.update(base["settings"] if isinstance(base["settings"], dict) else {})
        ch = dict(DEFAULT_SETTINGS["ch"])
        ch.update(s.get("ch") or {})
        s["ch"] = ch
        base["settings"] = s
    LOAD_SOURCE = "main" if st == "ok" else ("backup" if d is not None else "fresh")
    _RECONCILE = None
    if rewrite_main:
        save_data(base)   # ไฟล์หลักไม่มีอยู่ตอนนี้ → prev=None → ไม่แตะ backup, แค่สร้างไฟล์หลักคืน
    if st == "unreadable":
        # ตั้งหลัง rewrite_main (กรณีนี้ไม่มี rewrite อยู่แล้ว) — ดู _RECONCILE ด้านบน
        _RECONCILE = {"obj": base, "settings": json.loads(json.dumps(base["settings"])),
                      "name": base.get("name", "")}
    LOAD_WARNING = warn   # ตั้งหลังเซฟ — ให้แถบแจ้งค้างไว้จนผู้เล่นเซฟเองครั้งถัดไป
    return base

def _entry_key(e):
    return (e.get("at") or 0, e.get("ts") or 0, e.get("mode"), e.get("variant"), e.get("score"), e.get("duration"))

def _merge_lost_history(d, prev_d):
    """ไฟล์บนดิสก์มีรอบซ้อมที่ในหน่วยความจำไม่มี (โหลดจาก backup เก่าเพราะไฟล์หลักโดนล็อก,
    หรือเปิดเทรนเนอร์สองตัว) — เอากลับมารวมก่อนทับ ไม่งั้นรอบพวกนั้นหายเงียบ ๆ
    คืนจำนวนรอบที่กู้กลับมา"""
    have = {_entry_key(e) for e in d.get("history") or []}
    lost = [e for e in prev_d.get("history") or [] if _entry_key(e) not in have]
    if not lost:
        return 0
    h = (d.get("history") or []) + lost
    h.sort(key=lambda e: (e.get("at") or 0))   # stable — รอบยุค ts-only (ไม่มี at) คงลำดับเดิมหน้าสุด
    d["history"] = trim_history(h)
    return len(lost)

def _adopt_unchanged(mem, disk, snap):
    """คีย์ที่ผู้เล่นไม่ได้แก้หลังโหลด (ค่าในหน่วยความจำ == ค่า ณ ตอนโหลด) → ใช้ค่าบนดิสก์ (ใหม่กว่า)
    แก้ mem ในที่ — game.S เป็น alias ของ data["settings"] ห้ามสร้าง dict ใหม่แทน; dict ซ้อน (ch) ไล่ต่อคีย์"""
    for k, dv in disk.items():
        mv, sv = mem.get(k, _MISSING), snap.get(k, _MISSING)
        if isinstance(dv, dict) and isinstance(mv, dict) and isinstance(sv, dict):
            _adopt_unchanged(mv, dv, sv)
        elif mv == sv:
            mem[k] = json.loads(json.dumps(dv))

def _union_by(mem, disk, key, sort_key, cap):
    """รวมรายการบนดิสก์ที่หน่วยความจำไม่มี (เทียบด้วย key) — เรียงเวลา (stable) แล้วตัดเก่าสุดตามเพดาน"""
    have = {key(e) for e in mem}
    lost = [e for e in disk if isinstance(e, dict) and key(e) not in have]
    if not lost:
        return mem
    out = mem + lost
    out.sort(key=sort_key)
    return out[-cap:]

def _reconcile_nonhistory(d, prev_d, snap, merge):
    """เซฟแรกที่อ่านไฟล์หลักได้หลังโหลดตอนมันโดนล็อก (ดู _RECONCILE) — history มี _merge_lost_history แล้ว
    ส่วนนี้คืน settings/name ของดิสก์ (เว้นที่แก้หลังโหลด), รวม leaderboard/benchmark_history, คีย์ส่วนขยาย"""
    ms = prev_d.get("settings")
    if isinstance(ms, dict) and isinstance(d.get("settings"), dict):
        _adopt_unchanged(d["settings"], ms, snap["settings"])
    if isinstance(prev_d.get("name"), str) and d.get("name", "") == snap["name"]:
        d["name"] = prev_d["name"]
    lists = [("benchmark_history", lambda e: (e.get("t") or 0, e.get("total")), lambda e: e.get("t") or 0, 60)]
    if merge:   # merge=False = ผู้ใช้สั่งล้าง history+leaderboard เอง ห้ามดึงกลับ
        lists.append(("leaderboard", lambda e: _entry_key(e) + (e.get("name"),), lambda e: e.get("at") or 0, 100))
    for k, key, sort_key, cap in lists:
        disk = prev_d.get(k)
        if isinstance(disk, list) and disk:
            d[k] = _union_by(d.get(k) or [], disk, key, sort_key, cap)
    for k, v in prev_d.items():
        if k not in d:
            d[k] = v      # คีย์ที่โมดูลอื่นเพิ่มไว้บนดิสก์แต่ backup ยังไม่มี

def save_data(d, *, merge=True):
    """คืน True/False — ล้มเหลวเก็บสาเหตุไว้ที่ LAST_SAVE_ERROR จนกว่าจะเซฟสำเร็จ (game.py โชว์ปุ่มลองใหม่)
    merge=False เฉพาะตอนผู้ใช้สั่งล้างประวัติเอง (insight.reset_all_data) — ไม่งั้นรอบบนดิสก์จะถูกกู้กลับ"""
    global LAST_SAVE_ERROR, LOAD_WARNING, _RECONCILE
    try:
        if not _valid_data(d):
            raise ValueError("Invalid trainer data structure")
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        pst, prev_d = _read_json(DATA_FILE)
        if pst == "unreadable":
            raise OSError(f"อ่านไฟล์เดิมไม่ได้ (ถูกล็อก?): {DATA_FILE}")
        prev = None
        rec = _RECONCILE if (_RECONCILE is not None and _RECONCILE["obj"] is d) else None
        if pst == "corrupt" or (pst == "ok" and not _valid_data(prev_d)):
            _preserve_invalid(DATA_FILE)      # ของเสียห้ามไปทับ backup ที่ยังดี
        elif pst == "ok":
            if rec is not None:
                _reconcile_nonhistory(d, prev_d, rec, merge)
            if merge:
                _merge_lost_history(d, prev_d)
            with open(DATA_FILE, "rb") as f:
                prev = f.read()
        blob = json.dumps(d, ensure_ascii=False).encode("utf-8")
        if prev:
            _atomic_write(BACKUP_FILE, prev)   # สำรองของเดิมไว้หนึ่งชุดก่อนทับ
        _atomic_write(DATA_FILE, blob)
        if rec is not None:
            # กระทบยอดแล้ว (หรือไฟล์หลักเสีย/หายไป = ไม่มีของใหม่กว่าให้กู้) — ไฟล์หลักตอนนี้คือของเราเอง
            _RECONCILE = None
        LAST_SAVE_ERROR = None
        LOAD_WARNING = None
        return True
    except Exception as exc:
        LAST_SAVE_ERROR = f"{type(exc).__name__}: {exc}"
        return False
