# -*- coding: utf-8 -*-
"""แผนซ้อมจาก dashboard + routine/วอร์มรวด — อ่าน data/train_plan.json ที่ valorant-stats server เขียนไว้

หน้าตา (ไม่ใช้ MENU_EXTRAS แล้ว — ปุ่มแผนเดิม 5 ปุ่มแถวเดียวล้นจอ 900 px และไม่บอกว่าซ้อมทำไม):
  การ์ด "วันนี้" บนสุดของเมนู (todaycard.py) วาดจาก today(game) : รายการ routine (ทำไม · แรงค์ตอนนี้ → เป้า ·
  ✓ ทำแล้ววันนี้จากแท็ก src/item ใน history) + ปุ่มใหญ่ ROUTINE พร้อมเวลาจริง + ซ้อม x/4 วันสัปดาห์นี้
  คลิกแถว = เล่นข้อนั้น (รอบที่เหลือของวันนี้) ; หน้าผลมีปุ่ม NEXT ใหญ่ (next_info) + บรรทัด "ข้อ 2/5 · เป้า …"
  (result_lines) — ปุ่ม NEXT ไม่อยู่ใน RESULTS_ACTIONS แล้ว (เดิมต่อท้ายแถวปุ่มจนล้นขอบจอ 1280) ; NEXT/ENTER มีเฉพาะหลัง
  รอบที่มาจากคิว — ออกเมนู (MENU หน้าผล / ESC ตอนพักหรือนับถอยหลัง → game.go_menu → leave) = ทิ้งคิว + คืนค่าเมนูเดิม
  ของผู้ใช้ (โหมด/เวลา/ขนาด/ปืน/ดริล ณ ตอนเริ่มคิว) ; ปุ่ม ROUTINE ต่อจากที่ค้างเองจากประวัติวันนี้

แผนอายุเกิน 7 วันถือว่าเก่าเกินเชื่อ — การ์ดบอก "แผนเก่า N วัน — เปิด dashboard" (ไม่หายเงียบ) แล้วปุ่มหลัก
เป็นวอร์มมาตรฐาน ; dashboard เขียนไฟล์ใหม่ทุกครั้งที่วิเคราะห์ ; refresh ถูกเรียกจาก draw_menu (throttle ด้วย mtime)
ไม่มีไฟล์แผน = วอร์มมาตรฐาน: flick → spray·vandal → reaction·static

train_plan.json v2 (DESIGN 2.4 — server เขียน, ไฟล์ v1 ยังอ่านได้เหมือนเดิม): "routine" = ชุดซ้อมตามงบเวลา
{"id": "r-<yyyymmdd>-<hash4>", "budget_min", "items": [{"id", "phase", "mode", "variant", "cfg", "rounds", "why", "target"}]}
ลำดับรอบ/ความยากปรับเอง/วันซ้อม = routine.py (สลับข้อแบบสุ่มไม่รวดทีละข้อ, รอบแรกของวันของแต่ละข้อเล่น config ของแผน,
ข้อหลักโหมดบนบันได (routine.LADDER_MODES — flick/precision/switch ที่ขีดแรงค์ต่อขนาดตรวจกับประวัติจริงแล้ว
config.SIZE_RATIO_CHECKED) ผ่านเป้า 2 รอบติด → รอบฝึกถัดไปขนาดเป้าเล็กลงหนึ่งขั้น : เปลี่ยนแค่ขนาดเป้า ขีดแรงค์ปรับตามขนาด
(ประวัติจริงข้ามขนาดห่างกันราว 2 ขั้น ตัวอย่างน้อย) เป้าแรงค์จึงหมายถึงฝีมือราวเดิม)
ทุกรอบที่เริ่มจากการ์ด/ROUTINE/WARMUP/NEXT ติดแท็กที่มาใน history (round.end_game): src = "routine" | "plan" | "warmup",
rid = id ของ routine (ถ้ามี), item = id รายการใน routine / "p1".."p3" = ลำดับในแผน / "d1".."d3" = วอร์มมาตรฐาน,
phase = warm/block/maint ของรายการ routine ; รอบฝึกที่ขยับขนาดเป้าติด adapt = จำนวนขั้น + plan_size = ขนาดที่แผนตั้ง
(server ตัดรอบ adapt ออกจากโหวต config อ้างอิง/ฟอร์มได้) — รอบที่เริ่มทางอื่น (START/RETRY/deep-link) ไม่มีแท็ก
(เริ่มใหม่กลางรอบ — RR/R ตอนพัก/ค้าง R — ยังเป็นรอบเดิม คงแท็ก) ; dashboard ใช้นับว่าทำตามแผนไปแค่ไหน
"""

import json
import os
import time

from . import registry
from . import routine as R
from .config import DURATIONS, SIZE_TH, REACTION_VARIANTS
from .data import DATA_FILE
from .guns import DRILL_ORDER, WEAPON_ORDER

PLAN_FILE = os.path.join(os.path.dirname(DATA_FILE), "train_plan.json")
MAX_AGE = 7 * 86400
VALID_MODES = ("flick", "precision", "tracking", "reaction", "strafe",
               "sniper", "spray", "dodge", "placement", "switch", "gun")   # ต้องตรง aim_trainer.MODES
# id ที่แผนส่งมาได้ (pure python — ชุดเดียวกับ deep-link aim_trainer.py และ server aimlink): ค่าอื่น = ไม่แตะค่าเมนู
VALID_DRILLS = DRILL_ORDER                 # gun: duel hold quick repo angle peek tap adad (guns.DRILL_ORDER)
VALID_REACTION = REACTION_VARIANTS         # reaction: static flick peek
VALID_GUNS = WEAPON_ORDER
ROUNDS_PER_DRILL = 2          # วอร์ม (ไม่มี routine): โหมดละ 2 รอบ
MAX_ROUTINE_ROUNDS = 5        # routine: rounds ต่อรายการเกินนี้/ไม่ใช่ int = ใช้ ROUNDS_PER_DRILL (ไฟล์แก้มือ/พัง)
DEFAULT_WARMUP = [{"id": "d1", "mode": "flick"},
                  {"id": "d2", "mode": "spray", "variant": "vandal"},
                  {"id": "d3", "mode": "reaction", "variant": "static"}]
DEFAULT_WHY = "วอร์มมาตรฐาน — ยังไม่มีแผนจากแมตช์"

REFRESH_EVERY = 0.5           # วิ — draw_menu เรียก refresh ทุกเฟรม เช็ค stat ไฟล์ไม่ถี่กว่านี้
_last_check = -1e9
_menu_sig = None              # (ไฟล์, mtime/size, ชั่วโมง) ของไฟล์ที่ _cur อ่านมาล่าสุด
_cur = {"items": None, "updated": None, "routine": None, "meta": {}}   # เนื้อหาไฟล์ล่าสุดที่อ่านได้
_view_cache = (None, None)    # (คีย์, view ของ today) — draw_menu เรียกทุกเฟรม ; คิดใหม่เมื่อไฟล์/ประวัติ/นาทีเปลี่ยน


def _harden_cfg(p):
    # cfg ต้องเป็น dict เท่านั้น (server เขียนแค่ dict/null) — ไฟล์แก้มือใส่ชนิดอื่น
    # จะทำ _start_item ระเบิดกลางคลิก ตัดทิ้งเป็น "ไม่มี cfg" แบบเดียวกับแผนเก่า
    return p if isinstance(p.get("cfg"), dict) else {**p, "cfg": None}


def _routine(d):
    """routine ของ train_plan v2 ผ่าน harden — ไม่มี/ผิดรูป/ไม่มีรายการที่เล่นได้ = None"""
    r = d.get("routine")
    if not isinstance(r, dict):
        return None
    items = []
    for i, it in enumerate(r.get("items") or []):
        if not isinstance(it, dict) or it.get("mode") not in VALID_MODES:
            continue
        n = it.get("rounds")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_ROUTINE_ROUNDS:
            n = ROUNDS_PER_DRILL
        iid = it.get("id") if isinstance(it.get("id"), str) and it.get("id") else f"r{i + 1}"
        why = it.get("why") if isinstance(it.get("why"), str) else ""
        tgt = it.get("target") if isinstance(it.get("target"), str) else None
        items.append({**_harden_cfg(it), "rounds": n, "id": iid, "why": why, "target": tgt})
    if not items:
        return None
    rid = r.get("id") if isinstance(r.get("id"), str) and r.get("id") else None
    b = r.get("budget_min")
    b = round(b) if isinstance(b, (int, float)) and not isinstance(b, bool) and 1 <= b <= 120 else None
    return {"id": rid, "budget_min": b, "items": items}


def _meta(d):
    """lever/adherence ของ v2 (ผ่าน harden — ชนิดผิด = ไม่มี)"""
    lv = d.get("lever") if isinstance(d.get("lever"), dict) else None
    title = lv.get("title") if lv and isinstance(lv.get("title"), str) else None
    adh = d.get("adherence") if isinstance(d.get("adherence"), dict) else {}
    goal = adh.get("goal")
    goal = goal if isinstance(goal, int) and not isinstance(goal, bool) and 1 <= goal <= 7 else R.ADHERENCE_GOAL
    return {"lever": title, "goal": goal}


def _read_all():
    """(items, updated, routine, meta) — ผ่าน harden แล้ว ; อ่านไม่ได้/ไม่ใช่แผน = (None, None, None, {})"""
    try:
        with open(PLAN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None, None, None, {}
    if not isinstance(d, dict):
        return None, None, None, {}
    upd = d.get("updated")
    upd = upd if isinstance(upd, (int, float)) and not isinstance(upd, bool) and upd > 0 else None
    out = [_harden_cfg(p) for p in (d.get("plan") or [])
           if isinstance(p, dict) and p.get("mode") in VALID_MODES]
    return out, upd, _routine(d), _meta(d)


def _read():
    """(items, age_s, routine) — รูปเดิมของ load_plan/load_routine ; ไม่มี updated = age None"""
    items, upd, routine, _m = _read_all()
    return items, (time.time() - upd if upd else None), routine


def _fresh(items, age):
    return items is not None and age is not None and age <= MAX_AGE


def load_plan():
    """รายการแผนที่ยังไม่เก่าเกิน MAX_AGE (เก่า/ไม่มี updated/อ่านไม่ได้ = [])"""
    items, age, _r = _read()
    return items if _fresh(items, age) else []


def load_routine():
    """routine ที่ยังไม่เก่าเกิน MAX_AGE (อายุตาม updated ของไฟล์) — ไม่มี/เก่า = None"""
    items, age, routine = _read()
    return routine if _fresh(items, age) else None


def _label(it):
    v = it.get("variant") or ""
    lbl = it["mode"].upper() + (" · " + v.upper() if v else "")
    if it["mode"] == "gun":
        dr = (it.get("cfg") or {}).get("drill") or it.get("drill")   # ลำดับเดียวกับ _start_item
        if dr:
            lbl += " · " + str(dr).upper()
    return lbl


def _why(it):
    w = it.get("why")
    if isinstance(w, list):                    # รายการ plan v1: why = list ข้อความ
        w = next((x for x in w if isinstance(x, str) and x), "")
    return w if isinstance(w, str) else ""


def _hist(game):
    return ((getattr(game, "data", None) or {}).get("history")) or []


def _drill_key(mode, variant, drill):
    """คีย์ "ดริลเดียวกัน" ของรายการแผน/routine กับ deep-link: โหมด + variant + ดริลปืน (โหมดอื่นไม่มีดริล)"""
    return (mode, variant or "", (drill or None) if mode == "gun" else None)


def _item_key(it):
    return _drill_key(it.get("mode"), it.get("variant"), (it.get("cfg") or {}).get("drill") or it.get("drill"))


def deeplink_src(mode, variant, drill, item, rid=None):
    """แท็กที่มาของรอบที่เปิดจากปุ่มบน dashboard (--plan-item/--rid) -> dict ของ round_src | None
    ปุ่ม "ฝึกใน VAL//AIM" ของคันโยก/แผนเคยเปิดดริลเดียวกับข้อหลักของ routine แต่รอบไม่ถูกนับ (src ว่าง) — ผู้ใช้ถูกบอกให้
    เล่นซ้ำอีก 4 รอบ (review 2026-09-24) ; ติดแท็กเฉพาะเมื่อไฟล์แผนยังสด + รายการ id นี้มีอยู่จริง + เป็นดริลเดียวกับที่
    กำลังเปิด (routine ต้อง id ตรงถ้าส่ง rid มา) ไม่งั้นเล่นอิสระเหมือนเดิม (fail-open)"""
    if not isinstance(item, str) or not item:
        return None
    items, age, routine = _read()
    if not _fresh(items, age):
        return None
    want = _drill_key(mode, variant, drill)
    if routine and (not rid or rid == routine.get("id")):
        for it in routine["items"]:
            if it["id"] == item and _item_key(it) == want:
                return {"src": "routine", "rid": routine.get("id"), "item": item, "phase": it.get("phase"),
                        "target": it.get("target"), "label": _label(it), "why": _why(it)}
    for it in _warm_list(items):
        if it["id"] == item and _item_key(it) == want:
            return {"src": "plan", "rid": (routine or {}).get("id"), "item": item, "label": _label(it), "why": _why(it)}
    return None


def _start_item(game, it, base=None):
    game.mode = it["mode"]
    v = it.get("variant") or ""
    if game.mode == "reaction" and v in VALID_REACTION:
        game.reaction_variant = v
    if game.mode == "spray" and v in ("vandal", "phantom"):
        game.spray_weapon = v
    if game.mode == "gun":
        if v in VALID_GUNS:
            game.gun_weapon = v
        dr = (it.get("cfg") or {}).get("drill") or it.get("drill")
        if isinstance(dr, str) and dr in VALID_DRILLS:
            game.gun_drill = dr         # คู่ที่ปืนนี้เล่นไม่ได้ (เช่น Op + TAP) → gun_fix_drill ตอนเริ่มรอบย้ายไป DUEL
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
    # แท็กที่มาของรอบ (src/rid/item + ข้อมูลโชว์หน้าผล — ดูหัวไฟล์) : round.start_countdown ย้ายไปเป็นแท็กของรอบนี้
    # แล้วล้างทิ้ง → รอบถัดไปที่เริ่มด้วย START/R ไม่ติดแท็กตาม ; end_game เขียนลง history แค่ src/rid/item
    game.next_src = it.get("_src")
    game.start_countdown()


def _round_cfg(game, it):
    """cfg ของรอบนี้: ข้อหลักของ routine ที่ทำไปแล้ววันนี้ ≥ 1 รอบ = ความยากปรับเอง (routine.adaptive_cfg) ;
    รอบแรกของวัน/วอร์ม/คงฟอร์ม = config ของแผน (รอบทดสอบ — dashboard วัดฟอร์มที่ config นี้)"""
    src = it.get("_src") or {}
    if src.get("src") != "routine" or it.get("phase") != "block":
        return it
    hist = _hist(game)
    if not R.done_today(hist, [it], rid=src.get("rid")).get(it["id"]):
        return it
    cfg, steps = R.adaptive_cfg(hist, it)
    if not steps:
        return it
    return dict(it, cfg=cfg, _src=dict(src, step=steps, plan_size=(it.get("cfg") or {}).get("size")))


# ---- คิวต่อเนื่อง: ROUTINE / WARMUP / คลิกแถว — กด NEXT (ENTER) จากหน้า results ----

# ค่าเมนูที่รายการในคิวเปลี่ยนได้ (_start_item) — จำไว้ตอนเริ่มคิว คืนตอนออกจากคิวไปเมนู (leave)
MENU_KEYS = ("mode", "duration", "size_key", "reaction_variant", "spray_weapon", "gun_weapon", "gun_drill")


def _remember_menu(game):
    """ค่าเมนู ณ ตอนเริ่มคิว: plan_menu_cfg = (เวลา, ขนาด) ให้รายการไร้ cfg (ดู _start_item) + plan_menu_state ทั้งชุดให้ leave"""
    game.plan_menu_cfg = (game.duration, game.size_key)
    game.plan_menu_state = {k: getattr(game, k) for k in MENU_KEYS if hasattr(game, k)}


def leave(game):
    """ออกจากคิวกลับเมนู (game.go_menu — MENU หน้าผล, ESC ตอนพัก/นับถอยหลัง): ทิ้งคิวที่ค้าง + คืนค่าเมนูของผู้ใช้
    ณ ตอนเริ่มคิว — เดิมคิวค้างข้ามเมนู (ENTER/SPACE หน้าผลรอบถัดไปพากลับเข้าคิวเก่า) และเมนูค้างที่ config ของรายการ
    สุดท้าย (START ถัดไปเล่นดริล/ขนาดของแผนที่ผู้ใช้ไม่ได้เลือก) ; ไม่เคยเริ่มคิว = ไม่แตะค่าเมนู"""
    game.plan_queue = []
    st = getattr(game, "plan_menu_state", None)
    game.plan_menu_state = None
    for k, v in (st or {}).items():
        setattr(game, k, v)

def _warm_list(items):
    """รายการวอร์มแบบเดิม (ไม่มี routine): แผน ≤3 รายการ (id p1..p3) / ไม่มีแผน = วอร์มมาตรฐาน (d1..d3)"""
    if items:
        return [dict(it, id=f"p{i + 1}") for i, it in enumerate(items[:3])]
    return [dict(it, cfg=None, why=DEFAULT_WHY) for it in DEFAULT_WARMUP]


def _warm_queue(wl):
    q = [it for it in wl for _ in range(ROUNDS_PER_DRILL)]
    return [dict(it, _src={"src": "warmup", "item": it["id"], "k": wl.index(it) + 1, "n": len(wl),
                           "i": j + 1, "of": len(q)}) for j, it in enumerate(q)]


def _queue_for(game):
    """(ชนิด, คิว) ที่ปุ่มหลักจะเล่นตอนนี้ — routine สด = routine.build_queue ; ไม่งั้นวอร์ม"""
    items, age, routine = _read()
    fresh = _fresh(items, age)
    if fresh and routine:
        return "routine", R.build_queue(routine, _hist(game))
    return "warmup", _warm_queue(_warm_list(items if fresh else None))


def start_warmup(game):
    """ปุ่มหลัก ROUTINE/WARMUP (+ --warmup จาก dashboard): routine สด → ทุกข้อที่ยังไม่ครบวันนี้ สลับลำดับแบบสุ่ม ;
    ไม่มี routine → แผน ≤3 รายการ / วอร์มมาตรฐาน รายการละ ROUNDS_PER_DRILL รอบ"""
    _kind, game.plan_queue = _queue_for(game)
    # ค่าเมนู ณ ตอนเริ่มคิว — รายการไร้ cfg ในคิวต้องได้ค่านี้ (ดูหมายเหตุใน _start_item) + leave คืนค่าตอนออกจากคิว
    _remember_menu(game)
    advance(game)


def start_row(game, row):
    """คลิกแถวในการ์ด "วันนี้" = เล่นข้อนั้นข้อเดียว: routine = รอบที่เหลือของวันนี้ (ครบแล้ว = ทั้งข้ออีกครั้ง) ;
    แผน v1 = 1 รอบ (src plan แบบปุ่ม PLAN เดิม) ; วอร์มมาตรฐาน = 1 รอบ (src warmup)"""
    its = row["items"]
    kind = row.get("kind")
    if kind == "routine":
        hist = _hist(game)
        # นับจากรายการทั้งชุด (รอบของ routine อื่นเกลี่ยตามดริล+phase ข้ามแถวได้ — ให้ตรงกับตัวเลขบนการ์ด)
        done = R.done_today(hist, row.get("all") or its, rid=row.get("rid"))
        left = [(it, it["rounds"] - min(it["rounds"], done[it["id"]])) for it in its]
        if not any(n for _it, n in left):
            left = [(it, it["rounds"]) for it in its]
        order = [it for it, n in left for _ in range(n)]
        pos = row.get("pos") or {}
        q = [dict(it, _src={"src": "routine", "rid": row.get("rid"), "item": it["id"], "k": pos.get(it["id"]),
                            "n": row.get("n"), "phase": it.get("phase"), "target": it.get("target"),
                            "i": j + 1, "of": len(order)}) for j, it in enumerate(order)]
    else:
        it = its[0]
        q = [dict(it, _src={"src": "plan" if kind == "plan" else "warmup", "rid": row.get("rid"),
                            "item": it["id"], "k": row.get("k"), "n": row.get("n"), "i": 1, "of": 1})]
    game.plan_queue = q
    _remember_menu(game)
    advance(game)


def advance(game):
    q = getattr(game, "plan_queue", None)
    if not q:
        return
    it = q.pop(0)
    if isinstance(it.get("_src"), dict):         # ป้าย/เหตุผลสำหรับหน้านับถอยหลัง (ไม่ลง history)
        it["_src"].setdefault("label", _label(it))
        it["_src"].setdefault("why", _why(it))
    # base ใช้เฉพาะตอนเดินคิว (ค่าเมนู ณ ตอนเริ่มคิว) — รายการไร้ cfg ได้ค่าเมนู ไม่ใช่ค่าล็อกของรายการก่อน
    _start_item(game, _round_cfg(game, it), base=getattr(game, "plan_menu_cfg", None))


def next_info(game):
    """ปุ่ม NEXT บนหน้าผล (+ ENTER/SPACE): {label, sub, on_click} เฉพาะเมื่อมีคิวค้าง "และ" รอบที่เพิ่งจบมาจากคิว (แท็ก src)
    — รอบที่เริ่มเอง (START/RETRY) ไม่มี NEXT: เดิมคิวเก่าค้างข้าม MENU แล้วรอบอิสระมีปุ่ม NEXT ใหญ่ SPACE พาเข้าวอร์มเก่า"""
    q = getattr(game, "plan_queue", None) or []
    src = getattr(game, "round_src", None)
    if not q or not isinstance(src, dict) or src.get("src") not in R.TAGGED_SRC:
        return None
    sec = R.queue_seconds(q, getattr(game, "duration", 30))
    return {"label": f"NEXT · {_label(q[0])}", "sub": f"เหลือ {len(q)} รอบ {R.minutes_label(sec)} · ENTER",
            "on_click": advance}


def result_lines(game):
    """บรรทัดบนหน้าผลของรอบที่มาจากแผน: (หัวเรื่อง, (ข้อความสถานะ, ชนิดสี) | None, หมายเหตุ | None) ; รอบอิสระ = None
    ชนิดสี: "ok" ผ่านเป้า / "dim" ยังไม่ถึง / "done" ครบทั้งชุด"""
    src = getattr(game, "round_src", None)
    if not isinstance(src, dict) or src.get("src") not in R.TAGGED_SRC:
        return None
    kind = {"routine": "ROUTINE", "plan": "PLAN", "warmup": "WARMUP"}[src["src"]]
    parts = [kind]
    if src.get("k") and src.get("n"):
        parts.append(f"ข้อ {src['k']}/{src['n']}")
    ph = R.PHASE_TH.get(src.get("phase"))
    if ph:
        parts.append(ph)
    tgt = src.get("target")
    if tgt:
        parts.append(f"เป้า {tgt}")
    if src.get("i") and src.get("of") and src["of"] > 1:
        parts.append(f"รอบ {src['i']}/{src['of']}")
    head = " · ".join(parts)
    status = None
    ent = getattr(game, "last_entry", None) or {}
    ti = R.target_index(tgt)
    ri = R.rank_index(ent) if ent else None
    if ti is not None and ri is not None:
        status = (("ถึงเป้าแล้ว", "ok") if ri >= ti
                  else (f"ยังไม่ถึงเป้า — รอบนี้ {R.rank_name(ri)}", "dim"))
    note = None
    if src.get("step"):
        # บอกตรง ๆ ว่าอะไรเปลี่ยน: ขนาดเป้าอย่างเดียว — ขีดแรงค์ปรับตามขนาด (config.MODE_SIZE_RATIO) แต่ตรวจกับประวัติจริง
        # ได้แค่ "ห่างกันราว 2 ขั้น" (config.SIZE_RATIO_CHECKED — ตัวอย่างน้อย) ; w3 เดิมเขียน "วัดแยกไว้ เทียบเป้าเดิมได้" เกินจริง
        note = (f"รอบฝึกเป้า{SIZE_TH.get(ent.get('size'), '')} (แผนตั้ง{SIZE_TH.get(src.get('plan_size'), '')})"
                " — เปลี่ยนแค่ขนาดเป้า ขีดแรงค์ปรับตามขนาด เทียบเป้าเดิมได้คร่าว ๆ (คลาดราว 2 ขั้น)"
                " · รอบแรกของวันยังทดสอบที่ขนาดของแผน")
    q = getattr(game, "plan_queue", None) or []
    nxt = next((x for x in q if x.get("id") == src.get("item") and (x.get("_src") or {}).get("src") == "routine"), None)
    if nxt is not None and nxt.get("phase") == "block":
        cfg, steps = R.adaptive_cfg(_hist(game), nxt)
        if steps and (cfg or {}).get("size") != ent.get("size"):
            # โหมดบนบันไดเท่านั้น (routine.LADDER_MODES — ประวัติจริงข้ามขนาดห่างกันราว 2 ขั้น) ; เดิมเขียน "ยากขึ้นหนึ่งขั้น"
            # (ขีดคะแนนก็ปรับตาม แรงค์ไม่ได้ยากขึ้น) แล้ว w3 เขียน "ฝีมือเท่าเดิม ≈ แรงค์เดิม" ซึ่งเกินกว่าที่ตรวจได้
            note = (f"ถึงเป้า {R.ADAPT_PASSES} รอบติด: รอบหน้าของข้อนี้เป้า{SIZE_TH.get(cfg.get('size'), '')}"
                    " — เปลี่ยนแค่ขนาดเป้า ขีดแรงค์ปรับตามขนาด (ประวัติจริงข้ามขนาดคลาดราว 2 ขั้น)")
    if src["src"] == "routine" and not q:
        # รอบสุดท้ายของชุด: บอกครบชุด ต่อท้ายผลเทียบเป้าของรอบนี้ (ไม่ทับทิ้ง)
        status = ((status[0] + " · ครบทุกข้อของวันนี้แล้ว", "done" if status[1] == "ok" else "dim") if status
                  else ("ครบทุกข้อของวันนี้แล้ว", "done"))
    return head, status, note


# ---- การ์ด "วันนี้" (view model — todaycard.py วาด) ----

def _age_text(age):
    if age is None:
        return "แผนไม่มีวันที่ — เปิด dashboard"
    if age > MAX_AGE:
        return f"แผนเก่า {int(age // 86400)} วัน — เปิด dashboard"
    if age < 3600:
        return "แผนจาก dashboard · อัปเดตไม่ถึงชั่วโมง"
    if age < 86400:
        return f"แผนจาก dashboard · อัปเดต {int(age // 3600)} ชม.ก่อน"
    return f"แผนจาก dashboard · อัปเดต {int(age // 86400)} วันก่อน"


def _rank_pair(hist, it):
    """(ดัชนีฟอร์มตอนนี้ | None, ชื่อเป้า | None)"""
    cur, _n = R.form(hist, it)
    return cur, it.get("target")


def _cta(kind, q, game, done_all, partial):
    sec = R.queue_seconds(q, getattr(game, "duration", 30))
    mins = R.minutes_label(sec)
    if done_all:
        sub = f"ครบแล้ววันนี้ · เล่นซ้ำ {mins}"
    elif partial:
        sub = f"ต่อจากที่ค้าง · เหลือ {mins} ({len(q)} รอบ)"
    else:
        sub = f"{mins} · {len(q)} รอบ"
    return {"title": "ROUTINE" if kind == "routine" else "WARMUP", "sub": sub, "done": done_all,
            "on_click": start_warmup, "rounds": len(q), "seconds": sec}


def today(game, now=None):
    """view ของการ์ด "วันนี้" — state: routine | plan (v1 สด) | stale | none
    {state, status, stale, lever, ladder (มีข้อหลักที่ขยับขนาดเป้าเองได้), rows: [{label, why, phase, rounds, done, cur,
     target, kind, items, seek (แรงค์ดวลเล่นแล้วแต่ยังไม่นิ่ง), ...}], cta: {title, sub, done, on_click, rounds, seconds},
     adh: {days, goal, minutes, today}}"""
    global _view_cache
    hist = _hist(game)
    now = time.time() if now is None else now
    key = (_menu_sig, id(_cur), len(hist), id(hist[-1]) if hist else None, int(now // 60),
           getattr(game, "duration", None), getattr(game, "size_key", None))
    if _view_cache[0] == key:
        return _view_cache[1]
    items, upd, routine, meta = _cur["items"], _cur["updated"], _cur["routine"], _cur["meta"] or {}
    age = now - upd if upd else None
    fresh = _fresh(items, age)
    adh = R.adherence(hist, now, meta.get("goal", R.ADHERENCE_GOAL))
    view = {"stale": items is not None and not fresh, "lever": None, "adh": adh, "ladder": False}
    if fresh and routine:
        its = routine["items"]
        done = R.done_today(hist, its, now, rid=routine["id"])
        pos = {it["id"]: i + 1 for i, it in enumerate(its)}
        rows = []
        for r in R.rows_for(its, done):
            first = r["items"][0]
            lbl = " · ".join(_label(i) for i in r["items"]) if r["phase"] == "warm" else _label(first)
            cur, tgt = (None, None) if r["phase"] == "warm" else _rank_pair(hist, first)
            rows.append({"label": lbl, "why": _why(first), "phase": r["phase"], "rounds": r["rounds"],
                         "done": r["done"], "cur": cur, "target": tgt, "kind": "routine", "items": r["items"],
                         "all": its, "rid": routine["id"], "pos": pos, "n": len(its),
                         "seek": cur is None and R.ladder_seeking(hist, first)})
        q = R.build_queue(routine, hist, now)
        done_all = all(done[i["id"]] >= i["rounds"] for i in its)
        partial = not done_all and any(done.values())
        # กฎ "ถึงเป้า 2 รอบติด = เป้าเล็กลง" บอกเฉพาะเมื่อมีข้อหลักที่ขยับได้จริง (เดิมโชว์ทุก routine — ชุด GUN + Op hold ไม่มีบันได)
        view.update(state="routine", status=_age_text(age), lever=meta.get("lever"), rows=rows,
                    cta=_cta("routine", q, game, done_all, partial), ladder=any(R.can_adapt(i) for i in its))
    else:
        wl = _warm_list(items if fresh else None)
        kind = "plan" if fresh and items else "warmup"
        srcs = ("plan", "warmup") if kind == "plan" else ("warmup",)
        done = R.done_today(hist, wl, now, srcs)
        rows = []
        for i, it in enumerate(wl):
            cur, tgt = _rank_pair(hist, it)
            rows.append({"label": _label(it), "why": _why(it), "phase": "block" if kind == "plan" else "warm",
                         "rounds": ROUNDS_PER_DRILL, "done": min(ROUNDS_PER_DRILL, done[it["id"]]),
                         "cur": cur, "target": tgt, "kind": kind, "items": [it], "k": i + 1, "n": len(wl),
                         "rid": None, "seek": cur is None and R.ladder_seeking(hist, it)})
        q = _warm_queue(wl)
        done_all = all(r["done"] >= r["rounds"] for r in rows)
        note = None
        if items is None:
            status = "ยังไม่มีแผนจาก dashboard"
            note = "เปิด valorant-stats (dashboard) ครั้งเดียว — แผนจากแมตช์จริงจะมาเอง ; ระหว่างนี้ใช้วอร์มมาตรฐาน"
        else:
            status = _age_text(age)
            if not fresh:
                note = "แผนเก่าเกิน 7 วันไม่ใช้แล้ว — เปิด dashboard ให้วิเคราะห์ใหม่ ; ระหว่างนี้ใช้วอร์มมาตรฐาน"
        view.update(state=("plan" if kind == "plan" else ("stale" if items is not None else "none")),
                    status=status, note=note, rows=rows, cta=_cta("warmup", q, game, done_all, False))
    _view_cache = (key, view)
    return view


def refresh(game=None, force=False):
    """อ่าน train_plan.json ใหม่เมื่อไฟล์เปลี่ยน (mtime/size) หรือขึ้นชั่วโมงใหม่ (อายุแผนข้ามเกณฑ์/นับวันใหม่)
    เรียกจาก draw_menu ทุกเฟรม — throttle REFRESH_EVERY ; คืน True ถ้าอ่านไฟล์ใหม่แล้ว"""
    global _last_check, _menu_sig, _cur
    now = time.time()
    if not force and now - _last_check < REFRESH_EVERY:
        return False
    _last_check = now
    try:
        st = os.stat(PLAN_FILE)
        fsig = (st.st_mtime_ns, st.st_size)
    except OSError:
        fsig = None
    sig = (PLAN_FILE, fsig, int(now // 3600))
    if sig == _menu_sig and not force:
        return False
    items, upd, routine, meta = _read_all()
    if items is None and fsig is not None and not force:
        # stat ได้แต่อ่านไม่ได้ = ไฟล์ถูกล็อกชั่วขณะ (server os.replace ทับ / AV สแกน — data.py เจอจริง) หรือเขียนค้างครึ่งไฟล์
        # คงการ์ดเดิมและไม่จำ sig → เฟรมถัดไป (REFRESH_EVERY) ลองใหม่ ; ไฟล์หายจริง stat ล้ม (fsig None) → การ์ด "ไม่มีแผน"
        return False
    _menu_sig = sig
    _cur = {"items": items, "updated": upd, "routine": routine, "meta": meta}   # dict ใหม่ = คีย์ cache ของ today เปลี่ยน
    return True


def register(game):
    """ถูกเรียกตอนสร้าง Game (แบบเดียวกับ benchmark/sensitivity/export) — idempotent
    ถอดปุ่มแผนรุ่นเก่า (plan-*) ออกจาก MENU_EXTRAS ถ้ามีค้าง — การ์ด "วันนี้" แทนที่ทั้งหมด"""
    registry.MENU_EXTRAS[:] = [it for it in registry.MENU_EXTRAS if not str(it.get("_id", "")).startswith("plan-")]
    refresh(game, force=True)


def selftest():
    """pure-logic test ของ cfg lock + base restore + hardening + routine/การ์ด "วันนี้" (เรียกจาก aim.selftest)
    คืน list ข้อผิดพลาด — ใช้ไฟล์ temp + fake game ไม่แตะ train_plan.json จริง ไม่ต้องมีจอ"""
    global PLAN_FILE, ROUNDS_PER_DRILL, _last_check
    import tempfile
    errors = []

    class _G:
        duration, size_key, mode = 30, "medium", None

        def __init__(self):
            self.data = {"history": []}

        def start_countdown(self):
            self.round_src, self.next_src = self.next_src, None

    def play(g, **kw):
        """จำลอง end_game: รอบที่เพิ่งเริ่มลง history พร้อมแท็ก (routine.history_tags ตัวเดียวกับ round.end_game)"""
        e = {"mode": g.mode, "variant": getattr(g, "gun_weapon", "") if g.mode == "gun" else
             getattr(g, "reaction_variant", "static") if g.mode == "reaction" else
             getattr(g, "spray_weapon", "vandal") if g.mode == "spray" else "static",
             "drill": getattr(g, "gun_drill", None), "duration": g.duration, "size": g.size_key,
             "at": time.time(), "score": 1, "mrev": 2}
        e.update(R.history_tags(g.round_src))
        e.update(kw)
        g.data["history"].append(e)
        g.last_entry = e
        return e

    orig_file, orig_rpd = PLAN_FILE, ROUNDS_PER_DRILL
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)

    def write(d):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        st = os.stat(tmp)
        os.utime(tmp, ns=(st.st_mtime_ns + 10 ** 9, st.st_mtime_ns + 10 ** 9))

    def poll():
        global _last_check
        _last_check = -1e9                         # ข้ามแค่ throttle เวลา — ตัวกรอง mtime/size ยังทำงาน
        return refresh()

    try:
        PLAN_FILE, ROUNDS_PER_DRILL = tmp, 1
        write({"updated": time.time(), "plan": [
            {"mode": "tracking", "cfg": {"duration": 60, "size": "large"}},
            {"mode": "placement", "cfg": None},
            {"mode": "spray", "variant": "vandal", "cfg": "junk-not-dict"},
            {"mode": "bogus"},
            # GUNFIGHT จาก dashboard (aimlink.aim_training_plan): ปืน = variant, ดริลอยู่ทั้ง cfg และระดับบน
            {"mode": "gun", "variant": "operator", "drill": "hold",
             "cfg": {"duration": 30, "size": "medium", "drill": "hold"}}]})
        plan = load_plan()
        if len(plan) != 4 or plan[2]["cfg"] is not None:
            errors.append(f"plan selftest: load/harden ผิด ({plan})")
        # gun ต้องรอด load_plan (เดิม VALID_MODES ไม่มี gun → รายการหายเงียบ) และ _start_item ต้องตั้งทั้งปืน+ดริล
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
            for dr in ("angle", "peek", "tap", "adad"):
                gd = _G()
                gd.gun_drill = "duel"
                it = {"mode": "gun", "variant": "vandal", "cfg": {"duration": 30, "size": "medium", "drill": dr}}
                _start_item(gd, it)
                if getattr(gd, "gun_drill", None) != dr or _label(it) != f"GUN · VANDAL · {dr.upper()}":
                    errors.append(f"plan selftest: ดริล {dr} ไม่ถึง game / ป้ายผิด ({getattr(gd, 'gun_drill', None)})")
            for bad in ("bogus", ["peek"], 7):
                gb = _G()
                gb.gun_drill = "duel"
                _start_item(gb, {"mode": "gun", "variant": "vandal", "drill": bad, "cfg": None})
                if gb.gun_drill != "duel":
                    errors.append(f"plan selftest: ดริลแปลก {bad!r} ต้องไม่เปลี่ยนค่าเดิม")
            gr, gr2 = _G(), _G()
            gr.reaction_variant = gr2.reaction_variant = "static"
            _start_item(gr, {"mode": "reaction", "variant": "peek"})
            _start_item(gr2, {"mode": "reaction", "variant": "bogus"})
            if gr.reaction_variant != "peek" or gr2.reaction_variant != "static":
                errors.append("plan selftest: reaction variant peek ต้องผ่าน / variant แปลกต้องไม่แตะค่าเดิม")
        g = _G()
        g.duration, g.size_key = 15, "small"          # "ค่าเมนู" ของผู้ใช้ในเทสนี้
        start_warmup(g)                               # item1: tracking ล็อก 60/large
        if (g.mode, g.duration, g.size_key) != ("tracking", 60, "large"):
            errors.append(f"plan selftest: cfg lock ผิด ({g.mode},{g.duration},{g.size_key})")
        advance(g)                                    # item2: cfg=null ต้องคืนค่าเมนู ไม่ใช่ค่าตกค้าง
        if (g.mode, g.duration, g.size_key) != ("placement", 15, "small"):
            errors.append(f"plan selftest: base restore ผิด ({g.mode},{g.duration},{g.size_key})")
        advance(g)                                    # item3: cfg โดน harden เป็น None → ค่าเมนู
        if (g.mode, g.duration, g.size_key, getattr(g, "spray_weapon", None)) != ("spray", 15, "small", "vandal"):
            errors.append(f"plan selftest: hardened cfg ผิด ({g.mode},{g.duration},{g.size_key})")
        if getattr(g, "plan_queue", None) or next_info(g) is not None:
            errors.append("plan selftest: คิวไม่ถูกใช้จนหมด / NEXT ยังโชว์หลังคิวหมด")
        g.mode = "placement"                          # (ค่าจาก _start_item ของรายการสุดท้าย — เมนูค้างตรงนี้ก่อนแก้)
        leave(g)                                      # จบคิวแล้วกลับเมนู = ค่าเมนูเดิมของผู้ใช้ ณ ตอนเริ่มคิว
        if (g.mode, g.duration, g.size_key) != (None, 15, "small") or getattr(g, "plan_menu_state", 1) is not None:
            errors.append(f"plan selftest: ออกจากคิวต้องคืนค่าเมนูเดิม ({g.mode},{g.duration},{g.size_key})")
        gl = _G()
        gl.mode, gl.duration, gl.size_key, gl.gun_weapon, gl.gun_drill = "gun", 60, "large", "sheriff", "repo"
        start_warmup(gl)                              # ออกกลางคิว (ESC ตอนพัก/นับถอยหลัง → go_menu → leave)
        leave(gl)
        if (gl.mode, gl.duration, gl.size_key, gl.gun_weapon, gl.gun_drill, gl.plan_queue) !=                 ("gun", 60, "large", "sheriff", "repo", []):
            errors.append(f"plan selftest: ออกกลางคิวต้องทิ้งคิว + คืนค่าเมนู ({gl.mode},{gl.duration},{gl.size_key})")
        leave(gl)                                     # ไม่ได้อยู่ในคิว = ไม่แตะค่าเมนู
        gl.mode = "flick"
        leave(gl)
        if gl.mode != "flick":
            errors.append("plan selftest: leave นอกคิวต้องไม่เปลี่ยนค่าเมนู")
        g2 = _G()                                     # เริ่มเดี่ยว (ไม่มี base): cfg เพี้ยน = คงค่าเดิม
        _start_item(g2, {"mode": "flick", "cfg": {"duration": 45, "size": ["boom"]}})
        if (g2.duration, g2.size_key) != (30, "medium"):
            errors.append(f"plan selftest: invalid-cfg fallback ผิด ({g2.duration},{g2.size_key})")
        # ── train_plan v2: routine สด → วอร์มก่อน แล้วข้อที่เหลือสลับ + แท็ก src/rid/item ทุกรอบ ; รายการพังตัดทิ้ง ──
        rid = "r-20260924-ab12"
        write({"updated": time.time(), "v": 2, "plan": [{"mode": "switch"}],
               "lever": {"id": "long_range", "title": "ตายให้ Op บ่อย"}, "adherence": {"goal": 5},
               "routine": {"id": rid, "budget_min": 12, "items": [
                   {"id": "w1", "phase": "warm", "mode": "flick", "rounds": 2, "cfg": {"duration": 30, "size": "medium"}},
                   {"id": "b1", "phase": "block", "mode": "gun", "variant": "ghost", "rounds": 2,
                    "cfg": {"duration": 30, "size": "medium", "drill": "duel"}, "why": "pistol round"},
                   {"id": "b2", "phase": "block", "mode": "switch", "rounds": 3, "target": "Diamond II",
                    "cfg": {"duration": 30, "size": "medium"}, "why": "สลับเป้าหลายตัว"},
                   {"id": "x", "mode": "bogus", "rounds": 1},
                   "junk",
                   {"mode": "reaction", "variant": "static", "rounds": 99, "cfg": "junk", "phase": "maint"}]}})
        poll()
        r = load_routine()
        if not r or [(it["id"], it["rounds"], it["cfg"] is None) for it in r["items"]] != \
                [("w1", 2, False), ("b1", 2, False), ("b2", 3, False), ("r6", ROUNDS_PER_DRILL, True)] \
                or r["budget_min"] != 12:
            errors.append(f"plan selftest: อ่าน/harden routine ผิด ({r})")
        g3 = _G()
        start_warmup(g3)
        seq = [g3.round_src] + [it.get("_src") for it in g3.plan_queue]
        ids = [s["item"] for s in seq]
        if ids[:2] != ["w1", "w1"] or sorted(ids[2:]) != ["b1", "b1", "b2", "b2", "b2", "r6"] \
                or any(s["rid"] != rid or s["src"] != "routine" for s in seq) \
                or any(a == b for a, b in zip(ids[2:], ids[3:])):
            errors.append(f"plan selftest: คิว routine/แท็ก/การสลับข้อผิด ({ids})")
        if (g3.mode, g3.duration) != ("flick", 30) or seq[0].get("k") != 1 or seq[0].get("n") != 4:
            errors.append(f"plan selftest: รอบแรกของ routine ผิด ({g3.mode}, {seq[0]})")
        # ── ความยากปรับเอง: switch (โหมดบนบันได) ผ่านเป้า 2 รอบติดที่กลาง → รอบแรกของวันยังกลาง (ทดสอบ) รอบถัดไปเล็ก ;
        #    รอบฝึกติด adapt/plan_size ใน history (server ตัดออกจากโหวต config อ้างอิงได้) รอบทดสอบไม่ติด ──
        from .ranks import scaled_ranks
        ok_sc = scaled_ranks(30, "medium", "switch")[R.target_index("Diamond II")][0] + 5
        g5 = _G()
        g5.data["history"] = [{"mode": "switch", "duration": 30, "size": "medium", "score": ok_sc, "mrev": 2}] * 2
        start_row(g5, next(rw for rw in today(g5)["rows"] if rw["items"][0]["id"] == "b2"))
        sizes = []
        while True:
            sizes.append(g5.size_key)
            play(g5, score=ok_sc)
            if not g5.plan_queue:
                break
            advance(g5)
        tags = [(e.get("phase"), e.get("adapt"), e.get("plan_size")) for e in g5.data["history"][2:]]
        if sizes != ["medium", "small", "small"] or g5.round_src.get("step") != 1 or \
                tags != [("block", None, None), ("block", 1, "medium"), ("block", 1, "medium")]:
            errors.append(f"plan selftest: รอบทดสอบ/ความยากปรับเอง/แท็ก adapt ผิด ({sizes}, {tags})")
        # ── การ์ด "วันนี้": แถว (วอร์มรวม / ข้อหลัก / คงฟอร์ม) + เป้า + ✓ + ปุ่มหลักพร้อมเวลาจริง + วันซ้อม ──
        g6 = _G()
        v = today(g6)
        if v["state"] != "routine" or [rw["phase"] for rw in v["rows"]] != ["warm", "block", "block", "maint"] \
                or v["lever"] != "ตายให้ Op บ่อย" or v["adh"]["goal"] != 5:
            errors.append(f"plan selftest: การ์ด routine ผิด ({v.get('state')}, {[rw['phase'] for rw in v['rows']]})")
        want_s = 2 * 44 + 2 * 44 + 3 * 44 + 1 * 34
        if v["cta"]["title"] != "ROUTINE" or v["cta"]["seconds"] != want_s or v["cta"]["rounds"] != 8 \
                or f"{round(want_s / 60)} นาที" not in v["cta"]["sub"]:
            errors.append(f"plan selftest: ปุ่ม ROUTINE ต้องบอกเวลาจริง ({v['cta']})")
        if v["rows"][2]["target"] != "Diamond II":
            errors.append("plan selftest: แถวต้องมีเป้าของรายการ")
        g6.data["history"].append({"mode": "flick", "src": "routine", "rid": rid, "item": "w1", "at": time.time(),
                                   "duration": 30, "size": "medium", "score": 5})
        v2 = today(g6)
        if v2["rows"][0]["done"] != 1 or "ต่อจากที่ค้าง" not in v2["cta"]["sub"] or not v2["adh"]["today"]:
            errors.append(f"plan selftest: ✓ ทำแล้ววันนี้/ต่อจากที่ค้างผิด ({v2['rows'][0]}, {v2['cta']})")
        if not v["ladder"]:
            errors.append("plan selftest: ข้อหลัก switch มีเป้า = การ์ดต้องบอกกฎขนาดเป้าเล็กลงเอง")
        write({"updated": time.time(), "v": 2, "plan": [], "routine": {"id": "r-gun", "items": [
            {"id": "b1", "phase": "block", "mode": "gun", "variant": "vandal", "rounds": 4, "target": "Diamond II",
             "cfg": {"duration": 30, "size": "medium", "drill": "peek"}},
            {"id": "b2", "phase": "block", "mode": "gun", "variant": "operator", "rounds": 3,
             "cfg": {"duration": 30, "size": "medium", "drill": "hold"}},
            {"id": "m1", "phase": "maint", "mode": "placement", "rounds": 1, "target": "Diamond II",
             "cfg": {"duration": 30, "size": "medium"}}]}})
        poll()
        if today(_G())["ladder"]:
            errors.append("plan selftest: routine GUN + Op hold (+ คงฟอร์ม) ไม่มีบันไดขนาด — ห้ามบอกกฎเป้าเล็กลง")
        # NEXT เฉพาะหลังรอบที่มาจากคิว — รอบที่เริ่มเอง (START/RETRY) ระหว่างคิวค้างไม่มี NEXT (คิวยังอยู่ ไม่พาเข้าคิวเก่า)
        gq = _G()
        start_warmup(gq)
        free_ok = next_info(gq) is not None
        gq.start_countdown()
        if not free_ok or next_info(gq) is not None or not gq.plan_queue:
            errors.append("plan selftest: NEXT ต้องมีหลังรอบจากคิวเท่านั้น (รอบเริ่มเองไม่มี)")
        # ── ไฟล์เปลี่ยน → การ์ดตาม ; อ่านพลาดชั่วคราว = คงการ์ดเดิม ; แผนเก่า = บอกอายุ + วอร์มมาตรฐาน ; ไม่มีไฟล์ ──
        write({"updated": time.time(), "plan": [{"mode": "flick"}, {"mode": "reaction", "variant": "flick"}]})
        if not poll() or [rw["label"] for rw in today(_G())["rows"]] != ["FLICK", "REACTION · FLICK"] \
                or today(_G())["state"] != "plan":
            errors.append(f"plan selftest: แผน v1 ใหม่แล้วการ์ดไม่เปลี่ยน ({today(_G())['rows']})")
        if poll():
            errors.append("plan selftest: ไฟล์ไม่เปลี่ยนแต่อ่านใหม่ (throttle mtime ไม่ทำงาน)")
        g4 = _G()
        start_warmup(g4)
        if g4.round_src["src"] != "warmup" or g4.round_src["item"] != "p1" or g4.mode != "flick":
            errors.append(f"plan selftest: วอร์มจากแผน v1 แท็กผิด ({g4.round_src})")
        gp = _G()
        start_row(gp, today(gp)["rows"][1])
        if (gp.round_src["src"], gp.round_src["item"], gp.mode, gp.reaction_variant, gp.plan_queue) != \
                ("plan", "p2", "reaction", "flick", []):
            errors.append(f"plan selftest: คลิกแถวแผน v1 = 1 รอบ src plan ({gp.round_src})")
        write({"updated": time.time(), "plan": [{"mode": "switch"}]})
        real = globals()["_read_all"]
        globals()["_read_all"] = lambda: (None, None, None, {})
        try:
            locked = poll()
        finally:
            globals()["_read_all"] = real
        if locked or [rw["label"] for rw in today(_G())["rows"]][:1] != ["FLICK"]:
            errors.append("plan selftest: อ่านพลาดชั่วคราวแล้วการ์ดหาย/เปลี่ยน")
        if not poll() or [rw["label"] for rw in today(_G())["rows"]] != ["SWITCH"]:
            errors.append("plan selftest: หายล็อกแล้วไม่อ่านใหม่")
        write({"updated": time.time() - 10 * 86400 - 60, "plan": [{"mode": "switch"}],
               "routine": {"id": "r-x", "items": [{"id": "w1", "mode": "switch"}]}})
        poll()
        vs = today(_G())
        if vs["state"] != "stale" or vs["status"] != "แผนเก่า 10 วัน — เปิด dashboard" or vs["cta"]["title"] != "WARMUP" \
                or [rw["label"] for rw in vs["rows"]] != ["FLICK", "SPRAY · VANDAL", "REACTION · STATIC"]:
            errors.append(f"plan selftest: แผนเก่าต้องบอกอายุ + วอร์มมาตรฐาน ({vs['state']}, {vs['status']})")
        if load_plan() or load_routine():
            errors.append("plan selftest: แผนเก่าต้องไม่ถูกใช้")
        os.unlink(tmp)
        poll()
        vn = today(_G())
        if vn["state"] != "none" or vn["cta"]["rounds"] != 3 * ROUNDS_PER_DRILL:
            errors.append(f"plan selftest: ไม่มีไฟล์แผน = วอร์มมาตรฐาน ({vn['state']})")
    except Exception as ex:
        import traceback
        errors.append(f"plan selftest: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    finally:
        PLAN_FILE, ROUNDS_PER_DRILL = orig_file, orig_rpd
        refresh(force=True)                           # การ์ดกลับไปตามไฟล์จริง (อ่านอย่างเดียว)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return errors
