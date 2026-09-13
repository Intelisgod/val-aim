# -*- coding: utf-8 -*-
"""แผนซ้อมจาก dashboard + วอร์มรวด — อ่าน data/train_plan.json ที่ valorant-stats server เขียนไว้

ตะเข็บที่ใช้ (ดู registry.py):
  MENU_EXTRAS     : ปุ่ม "WARMUP ~15 MIN" + ปุ่มแผนวันนี้ ≤2 อัน ใต้ START
  RESULTS_ACTIONS : ปุ่ม "NEXT · <โหมด>" โผล่เฉพาะตอนมีคิววอร์มค้าง (ถอดออกเมื่อคิวหมด)

แผนอายุเกิน 7 วันถือว่าเก่าเกินเชื่อ — ไม่แสดง (dashboard เขียนไฟล์ใหม่ทุกครั้งที่วิเคราะห์)
ไม่มีไฟล์แผน = ปุ่มวอร์มยังใช้ได้ ด้วยชุด default: flick → spray·vandal → reaction·static
"""

import json
import os
import time

from . import registry
from .config import DURATIONS, SIZE_TH
from .data import DATA_FILE

PLAN_FILE = os.path.join(os.path.dirname(DATA_FILE), "train_plan.json")
MAX_AGE = 7 * 86400
VALID_MODES = ("flick", "precision", "tracking", "reaction", "strafe",
               "sniper", "spray", "dodge", "placement", "switch", "gun")   # ต้องตรง aim_trainer.MODES
ROUNDS_PER_DRILL = 2          # วอร์ม: โหมดละ 2 รอบ ≈ 12-15 นาทีรวม

_next_act = None              # dict ที่แขวนอยู่ใน RESULTS_ACTIONS — mutate label ตามคิว


def load_plan():
    try:
        with open(PLAN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - (d.get("updated") or 0) > MAX_AGE:
            return []
        out = []
        for p in (d.get("plan") or []):
            if p.get("mode") not in VALID_MODES:
                continue
            # cfg ต้องเป็น dict เท่านั้น (server เขียนแค่ dict/null) — ไฟล์แก้มือใส่ชนิดอื่น
            # จะทำ _start_item ระเบิดกลางคลิก ตัดทิ้งเป็น "ไม่มี cfg" แบบเดียวกับแผนเก่า
            if not isinstance(p.get("cfg"), dict):
                p = {**p, "cfg": None}
            out.append(p)
        return out
    except Exception:
        return []


def _label(it):
    v = it.get("variant") or ""
    lbl = it["mode"].upper() + (" · " + v.upper() if v else "")
    if it["mode"] == "gun":
        dr = (it.get("cfg") or {}).get("drill") or it.get("drill")   # ลำดับเดียวกับ _start_item
        if dr:
            lbl += " · " + str(dr).upper()
    return lbl


def _start_item(game, it, base=None):
    game.mode = it["mode"]
    v = it.get("variant") or ""
    if game.mode == "reaction" and v in ("static", "flick"):
        game.reaction_variant = v
    if game.mode == "spray" and v in ("vandal", "phantom"):
        game.spray_weapon = v
    if game.mode == "gun":
        from .guns import WEAPON_ORDER
        from .gunplay import GUN_DRILLS
        if v in WEAPON_ORDER:
            game.gun_weapon = v
        dr = (it.get("cfg") or {}).get("drill") or it.get("drill")
        if dr in [d[0] for d in GUN_DRILLS]:
            game.gun_drill = dr
    # ล็อก duration/size ตาม config อ้างอิงที่ dashboard วัดฟอร์มอยู่ — ไม่งั้น session ที่ซ้อม
    # ตามแผนไปตกอยู่ config อื่น แล้ว dashboard ไม่นับ (ซ้อมแล้วเลขไม่ขยับ)
    # ค่านอกลิสต์/แผนเก่าไม่มี cfg = คงค่าเมนู — ในคิววอร์มต้องคืนเป็น base (ค่าเมนู ณ ตอนเริ่มคิว)
    # ไม่ใช่ปล่อยค่าล็อกของรายการก่อนหน้าค้างไว้ ไม่งั้นโหมดที่ไม่เคยซ้อม (cfg=null) โดน seed
    # ref config ที่ผู้ใช้ไม่เคยเลือกเอง
    cfg = it.get("cfg") or {}
    if cfg.get("duration") in DURATIONS:
        game.duration = cfg["duration"]
    elif base:
        game.duration = base[0]
    if isinstance(cfg.get("size"), str) and cfg["size"] in SIZE_TH:
        game.size_key = cfg["size"]      # isinstance กันค่า unhashable โยน TypeError ใส่ `in dict`
    elif base:
        game.size_key = base[1]
    game.start_countdown()


# ---- วอร์มรวด: คิว drill ต่อเนื่อง กด NEXT จากหน้า results ----

def start_warmup(game):
    plan = load_plan()[:3] or [{"mode": "flick"},
                               {"mode": "spray", "variant": "vandal"},
                               {"mode": "reaction", "variant": "static"}]
    game.plan_queue = [dict(it) for it in plan for _ in range(ROUNDS_PER_DRILL)]
    # ค่าเมนู ณ ตอนเริ่มคิว — รายการไร้ cfg ในคิวต้องได้ค่านี้ (ดูหมายเหตุใน _start_item)
    game.plan_menu_cfg = (game.duration, game.size_key)
    advance(game)


def advance(game):
    q = getattr(game, "plan_queue", None)
    if not q:
        return
    it = q.pop(0)
    _sync_next_button(game)
    # base ใช้เฉพาะตอนเดินคิว — ปุ่ม PLAN เดี่ยว (register) เรียก _start_item ตรงโดยไม่มี base
    # เพราะค่าปัจจุบันตอนนั้นคือค่าเมนูอยู่แล้ว
    _start_item(game, it, base=getattr(game, "plan_menu_cfg", None))


def _sync_next_button(game):
    """มีคิวค้าง = โชว์ปุ่ม NEXT บนหน้า results / คิวหมด = ถอดปุ่มออก ไม่ทิ้งปุ่มเปล่า"""
    global _next_act
    q = getattr(game, "plan_queue", None) or []
    if q:
        if _next_act is None:
            _next_act = {"label": "", "on_click": advance, "_id": "plan-next"}
            registry.RESULTS_ACTIONS.append(_next_act)
        _next_act["label"] = f"NEXT · {_label(q[0])} ({len(q)})"
    elif _next_act is not None:
        try:
            registry.RESULTS_ACTIONS.remove(_next_act)
        except ValueError:
            pass
        _next_act = None


def selftest():
    """pure-logic test ของ cfg lock + base restore + hardening (เรียกจาก aim.selftest)
    คืน list ข้อผิดพลาด — ใช้ไฟล์ temp + fake game ไม่แตะ train_plan.json จริง ไม่ต้องมีจอ"""
    global PLAN_FILE, ROUNDS_PER_DRILL, _next_act
    import tempfile
    errors = []

    class _G:
        duration, size_key, mode = 30, "medium", None
        def start_countdown(self):
            pass

    orig_file, orig_rpd = PLAN_FILE, ROUNDS_PER_DRILL
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        PLAN_FILE, ROUNDS_PER_DRILL = tmp, 1
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"updated": time.time(), "plan": [
                {"mode": "tracking", "cfg": {"duration": 60, "size": "large"}},
                {"mode": "placement", "cfg": None},
                {"mode": "spray", "variant": "vandal", "cfg": "junk-not-dict"},
                {"mode": "bogus"},
                # GUNFIGHT จาก dashboard (aimlink.aim_training_plan): ปืน = variant, ดริลอยู่ทั้ง cfg และระดับบน
                {"mode": "gun", "variant": "operator", "drill": "hold",
                 "cfg": {"duration": 30, "size": "medium", "drill": "hold"}}]}, f)
        plan = load_plan()
        if len(plan) != 4 or plan[2]["cfg"] is not None:
            errors.append(f"plan selftest: load/harden ผิด ({plan})")
        # gun ต้องรอด load_plan (เดิม VALID_MODES ไม่มี gun → รายการหายเงียบ ปุ่ม PLAN ไม่ขึ้น)
        # และ _start_item ต้องตั้งทั้งปืน+ดริล ป้ายปุ่มต้องบอกดริลด้วย ไม่งั้นเปิดผิดชุด/หาประวัติต่อปืนไม่เจอ
        gun_it = plan[3] if len(plan) > 3 else None
        if not gun_it or gun_it.get("mode") != "gun":
            errors.append("plan selftest: รายการ gun ถูกทิ้งจาก load_plan")
        else:
            gg = _G()
            _start_item(gg, gun_it)
            if (gg.mode, getattr(gg, "gun_weapon", None), getattr(gg, "gun_drill", None),
                    gg.duration, gg.size_key) != ("gun", "operator", "hold", 30, "medium"):
                errors.append(f"plan selftest: gun weapon/drill ไม่ถึง game ({gg.__dict__})")
            if _label(gun_it) != "GUN · OPERATOR · HOLD":
                errors.append(f"plan selftest: ป้าย gun ไม่มีดริล ({_label(gun_it)})")
            gg2 = _G()
            _start_item(gg2, {"mode": "gun", "variant": "sheriff", "drill": "repo", "cfg": None})
            if (getattr(gg2, "gun_weapon", None), getattr(gg2, "gun_drill", None)) != ("sheriff", "repo"):
                errors.append("plan selftest: gun drill ระดับบน (ไม่มี cfg) ต้องใช้ได้")
        g = _G()
        g.duration, g.size_key = 15, "small"          # "ค่าเมนู" ของผู้ใช้ในเทสนี้
        start_warmup(g)                               # item1: tracking ล็อก 60/large
        if (g.mode, g.duration, g.size_key) != ("tracking", 60, "large"):
            errors.append(f"plan selftest: cfg lock ผิด ({g.mode},{g.duration},{g.size_key})")
        advance(g)                                    # item2: cfg=null ต้องคืนค่าเมนู ไม่ใช่ค่าตกค้าง
        if (g.mode, g.duration, g.size_key) != ("placement", 15, "small"):
            errors.append(f"plan selftest: base restore ผิด ({g.mode},{g.duration},{g.size_key})")
        advance(g)                                    # item3: cfg โดน harden เป็น None → ค่าเมนู
        if (g.mode, g.duration, g.size_key, getattr(g, "spray_weapon", None)) != \
                ("spray", 15, "small", "vandal"):
            errors.append(f"plan selftest: hardened cfg ผิด ({g.mode},{g.duration},{g.size_key})")
        if getattr(g, "plan_queue", None):
            errors.append("plan selftest: คิวไม่ถูกใช้จนหมด")
        if _next_act is not None:
            errors.append("plan selftest: ปุ่ม NEXT ไม่ถูกถอดหลังคิวหมด")
        g2 = _G()                                     # ปุ่ม PLAN เดี่ยว (ไม่มี base): cfg เพี้ยน = คงค่าเดิม
        _start_item(g2, {"mode": "flick", "cfg": {"duration": 45, "size": ["boom"]}})
        if (g2.duration, g2.size_key) != (30, "medium"):
            errors.append(f"plan selftest: invalid-cfg fallback ผิด ({g2.duration},{g2.size_key})")
    except Exception as ex:
        errors.append(f"plan selftest: {type(ex).__name__}: {ex}")
    finally:
        PLAN_FILE, ROUNDS_PER_DRILL = orig_file, orig_rpd
        _sync_next_button(_G())                       # เผื่อเทสพังกลางคัน — เก็บปุ่มออกจาก registry
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return errors


def register(game):
    """ถูกเรียกครั้งเดียวตอนสร้าง Game (แบบเดียวกับ benchmark/sensitivity/export)"""
    if any(it.get("_id") == "plan-warmup" for it in registry.MENU_EXTRAS):
        return
    registry.MENU_EXTRAS.append({"label": "WARMUP ~15 MIN", "on_click": start_warmup,
                                 "_id": "plan-warmup"})
    for i, it in enumerate(load_plan()[:2]):
        registry.MENU_EXTRAS.append({"label": f"PLAN {i + 1} · {_label(it)}",
                                     "on_click": (lambda g, it=it: _start_item(g, it)),
                                     "_id": f"plan-{i}"})
