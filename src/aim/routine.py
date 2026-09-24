# -*- coding: utf-8 -*-
"""routine รายวันของ train_plan v2 — ตรรกะล้วน (ไม่มี pygame ; py3.10 import ได้แบบเดียวกับ aim.guns)

plan.py (ปุ่ม/คิว) กับการ์ด "วันนี้" ในเมนู (todaycard.py) ใช้ฟังก์ชันชุดนี้ชุดเดียว:
  interleave / build_queue : ลำดับรอบของ routine — วอร์มก่อนตามลำดับ แล้ว "ข้อหลัก + คงฟอร์ม" สลับกันแบบสุ่ม
                             ไม่เล่นดริลเดียวกันรวดติดกัน (phase-1 research §4: practice แบบสุ่มสลับชนะแบบรวดทีละโหมด
                             ใน transfer ภายหลัง meta-analysis SMD 0.55 / 34 งาน) ; seed = id routine + วันที่
                             → ลำดับเดิมทั้งวัน (กดต่อจากที่ค้างได้) และเปลี่ยนทุกวัน
  done_today               : ข้อไหนทำแล้ววันนี้ — นับจากแท็ก src/rid/item(/phase) ที่ round.end_game เขียน (DESIGN 2.4) ;
                             routine ที่ dashboard เขียนใหม่กลางวัน (id รายการเลื่อน) จับคู่ด้วย (ดริล, phase) แทน id
  adaptive_cfg             : ความยากปรับเอง (กฎ 2:1 ของงาน CS:GO adaptive training — ผ่านเป้า 2 รอบติด = ขยับขั้น)
                             ขยับบนบันไดขนาดเป้าที่มีอยู่แล้ว (ใหญ่ → กลาง → เล็ก) เฉพาะโหมดใน LADDER_MODES — โหมดที่
                             ขีดแรงค์ต่อขนาด (config.MODE_SIZE_RATIO) ตรวจกับประวัติจริงข้ามขนาดแล้ว (config.SIZE_RATIO_CHECKED:
                             ห่างกันไม่เกิน ~2 ขั้น ตัวอย่างน้อย) → สิ่งที่เปลี่ยนคือขนาดเป้า ส่วน "เป้าแรงค์" ยังหมายถึงฝีมือราวเดิม ;
                             ห้ามเพิ่มปุ่มความยากใหม่ (ความเร็วเป้า/เวลาโผล่ ฯลฯ) ที่ขีดแรงค์ไม่ได้สอบเทียบ ;
                             เวลา 15/30/60 ไม่ใช่ขั้นความยาก (TIME_FACTOR สเกลขีดตามเวลา = อัตราต่อวินาทีเท่ากัน)
                             รอบที่ขยับแล้วติด adapt/plan_size ใน history (round.end_game) — server ตัดออกจากโหวต config
                             อ้างอิง/ฟอร์มได้ (รอบฝึกคนละขนาดไม่ใช่ "config ที่ผู้ใช้เลือกซ้อม")
  adherence                : วันซ้อมตามแผนใน 7 วันล่าสุด — นิยามเดียวกับ server aimlink.adherence
  round_seconds            : เวลาจริงต่อรอบ (รวมนับถอยหลัง/หน้าผล) — ค่าคงที่เดียวกับ server (ROUND_OVERHEAD_S)
"""

import datetime
import random
import time

from .config import RANKS, REACTION_RT_RANKS, MODE_SIZE_RATIO, MODE_REV, SIZE_RATIO_CHECKED, mode_current
from .ranks import scaled_ranks, rt_thresh
from . import duel

ROUND_OVERHEAD_S = 14          # = valorant-stats aimlink.ROUND_OVERHEAD_S (วอร์มจริง 09-07: 7 รอบ 4 นาที)
REACTION_ROUND_S = 20          # reaction จบเมื่อครบ 5 เป้า (~20 วิ) ไม่ผูก duration
TAGGED_SRC = ("routine", "plan", "warmup")
ADHERENCE_GOAL = 4             # วันต่อสัปดาห์ — ไฟล์แผนส่ง goal มาได้ (adherence.goal) ไม่มีใช้ค่านี้
ADAPT_PASSES = 2               # ผ่านเป้ากี่รอบติด (ที่ config เดียวกัน) ถึงขยับขั้น
SIZE_LADDER = ("large", "medium", "small")
# โหมดที่ขยับขนาดเป้าได้โดยแรงค์ยังเทียบกันได้ — ขีดต่อขนาดต้องตรวจกับประวัติจริงแล้ว (config.SIZE_RATIO_CHECKED) ไม่ใช่แค่
# "มีขนาดเป้า" หรือ "มีแถวใน MODE_SIZE_RATIO" (ตัวคูณส่วนใหญ่มาจากสมมติฐาน SIZE_MULT ของ sim — ดูหมายเหตุที่ config)
# ประวัติ: 2026-09-24 w3 ใส่ครบ 6 โหมดโดยอ้างว่า sim วัดแล้ว "ทุกขนาดห่างไม่เกิน 1 ขั้น" ; verify3 พบว่าอัตราส่วนเป็นสมมติฐาน
# ของ sim และประวัติจริงไม่ตรงใน tracking (เล็กต่ำกว่า 3–6 ขั้น — ข้อ "ยังไม่ถึงเป้า" ปลอมเมื่อบันไดพาไปเล็ก) → w3-fix เหลือ
# flick / precision / switch ที่ประวัติจริงข้ามขนาดห่างกันไม่เกิน ~2 ขั้น ; tracking/dodge/placement เล่นขนาดตามแผนเสมอ
# spray/gun/reaction ไม่มีขนาดเป้าให้ขยับ (บันไดดวล GUNFIGHT ปรับระดับบอทในรอบอยู่แล้ว) ; strafe/sniper ไม่มีแรงค์
LADDER_MODES = SIZE_RATIO_CHECKED
UNRANKED = ("strafe", "sniper")
FORM_N = 5                     # ฟอร์ม = ดัชนีแรงค์ 5 รอบล่าสุดที่ config เดียวกัน (เฉลี่ย ; gun = ค่ากลาง duel.recent_tier)
PHASE_TH = {"warm": "วอร์ม", "block": "หลัก", "maint": "คงฟอร์ม"}
# id รายการที่ server เขียน (aimlink.build_routine): w1.. วอร์ม / b1.. ข้อหลัก / m1.. คงฟอร์ม — ใช้เดา phase ของรอบเก่า
# ที่ยังไม่มีคีย์ phase ใน history (รอบใหม่ round.end_game เขียน phase เองแล้ว)
PHASE_OF_ID = {"w": "warm", "b": "block", "m": "maint"}
SHORT_TIER = {"Platinum": "Plat", "Diamond": "Dia", "Ascendant": "Asc", "Immortal": "Imm"}


def _day(ts=None):
    return datetime.datetime.fromtimestamp(time.time() if ts is None else ts).strftime("%Y-%m-%d")


def short_rank(name):
    """'Platinum III' → 'Plat III' (แถวในการ์ดแคบ)"""
    if not name:
        return ""
    head, _, tail = str(name).partition(" ")
    return (SHORT_TIER.get(head, head) + (" " + tail if tail else "")).strip()


def rank_name(i):
    return RANKS[i][1] if isinstance(i, int) and 0 <= i < len(RANKS) else None


def target_index(name):
    """ดัชนีแรงค์ของชื่อเป้า ('Diamond II') — ไม่รู้จัก/None = None"""
    for i, (_b, n, _c) in enumerate(RANKS):
        if n == name:
            return i
    return None


def rank_index(e):
    """ดัชนีแรงค์ 0..22 ของรอบ (22 = Radiant) — สูตรเดียวกับ server aimlink._aim_idx ; โหมดไร้แรงค์ = None"""
    md = e.get("mode")
    if md == "gun":
        t = e.get("tier_i")
        return t if isinstance(t, int) and not isinstance(t, bool) and 0 <= t < len(RANKS) else None
    if md == "reaction":
        rt = e.get("rt") or 0
        if rt <= 0:
            return None
        v = e.get("variant") or "static"
        for i, (t, _n, _c) in enumerate(REACTION_RT_RANKS):
            if rt <= rt_thresh(t, v):
                return len(REACTION_RT_RANKS) - 1 - i
        return 0
    if not md or md in UNRANKED:
        return None
    rows = scaled_ranks(e.get("duration") or 30, e.get("size") or "medium", md,
                        (e.get("variant") or "vandal") if md == "spray" else None)
    sc = e.get("score") or 0
    idx = 0
    for i, row in enumerate(rows):
        if sc >= row[0]:
            idx = i
    return idx


def drill_key(x):
    """(mode, variant, drill) ของรายการแผนหรือรอบใน history — ใช้จับคู่ "ดริลเดียวกัน" (ไม่ดูเวลา/ขนาด)"""
    md = x.get("mode")
    v = x.get("variant") or ""
    if md == "reaction":
        return md, v or "static", ""
    if md == "spray":
        return md, v or "vandal", ""
    if md == "gun":
        dr = (x.get("cfg") or {}).get("drill") if isinstance(x.get("cfg"), dict) else None
        return md, v or "vandal", dr or x.get("drill") or "duel"
    return md, "", ""


def item_cfg(it):
    """{duration, size} ของรายการ (ค่าเพี้ยน/ไม่มี = None ทั้ง dict)"""
    c = it.get("cfg")
    return dict(c) if isinstance(c, dict) else None


def same_cfg(e, md, cfg):
    """รอบ e อยู่ config เดียวกับ cfg ไหม — กติกาเดียวกับ round.same_config (PB/TOP 5/dashboard)"""
    if md in ("reaction", "sniper") or cfg is None:
        return True
    if md in ("spray", "gun"):
        return e.get("duration") == cfg.get("duration")
    return e.get("duration") == cfg.get("duration") and (e.get("size") or "medium") == cfg.get("size")


def _empty(e):
    """รอบเปล่า (ไม่ได้ยิงสักนัด + คะแนน 0) ไม่ใช่ฟอร์มจริง — แบบเดียวกับ server"""
    if e.get("mode") == "reaction" or (e.get("score") or 0) > 0:
        return False
    return not (e.get("shots") or e.get("shots_n") or (e.get("mode") == "gun" and (e.get("shots_fired") or 0) > 0))


def series(hist, it, cfg):
    """ดัชนีแรงค์รอบต่อรอบของดริลนี้ที่ config นี้ (กติการุ่นปัจจุบัน, ตัดรอบเปล่า) เก่า → ใหม่"""
    key = drill_key(it)
    out = []
    for e in hist or []:
        if not isinstance(e, dict) or drill_key(e) != key or not mode_current(e) or _empty(e):
            continue
        if not same_cfg(e, key[0], cfg):
            continue
        r = rank_index(e)
        if r is not None:
            out.append(r)
    return out


def ladder_seeking(hist, it):
    """ข้อ GUNFIGHT ดริลจัดแรงค์ (duel.LADDER_DRILLS, ไม่ใช่ Op) ที่เล่นแล้วแต่แรงค์ดวลยังไม่นิ่ง — แรงค์ต้องใช้ ~100 ดวล
    ข้ามรอบ (duel.LADDER_SE) จึงค้างหลายรอบ → การ์ดบอก "กำลังวัด" แทน "ใหม่" (ยังไม่เคยเล่น)"""
    if it.get("mode") != "gun":
        return False
    _md, weapon, drill = drill_key(it)
    if drill not in duel.LADDER_DRILLS or weapon == "operator":
        return False
    return (duel.ladder_resume(hist, weapon, mode_current, drill)[0] is not None
            and duel.recent_tier(hist, weapon, mode_current, drill=drill) is None)


def form(hist, it, cfg=None):
    """(ดัชนีฟอร์ม | None, n) — เฉลี่ย FORM_N รอบล่าสุดที่ config ของรายการ ; ไม่มี cfg = config ของรอบล่าสุด
    (ไม่นับรอบฝึกที่ขยับขนาด — adapt) ; gun = แรงค์ดวลค่ากลาง FORM_N รอบล่าสุดทุกความยาว (duel.recent_tier —
    ตัวเลขเดียวกับแผงโปรไฟล์/Insight ; บันไดเดินต่อข้ามรอบจึงไม่ผูกเวลา)"""
    if it.get("mode") == "gun":
        _md, weapon, drill = drill_key(it)
        r = duel.recent_tier(hist, weapon, mode_current, n=FORM_N, drill=drill)
        return (r[0], r[1]) if r else (None, 0)
    if cfg is None:
        cfg = item_cfg(it)
    if cfg is None and it.get("mode") not in ("reaction", "sniper"):
        key = drill_key(it)
        last = next((e for e in reversed(hist or []) if isinstance(e, dict) and drill_key(e) == key
                     and not e.get("adapt")), None)
        if last is not None:
            cfg = {"duration": last.get("duration"), "size": last.get("size") or "medium"}
    s = series(hist, it, cfg)[-FORM_N:]
    if not s:
        return None, 0
    return int(round(sum(s) / len(s))), len(s)


def ladder_next(mode, cfg):
    """config ขั้นถัดไปบนบันไดขนาดเป้า — บนสุด/โหมดไม่มีบันได = None"""
    if mode not in LADDER_MODES or not cfg or cfg.get("size") not in SIZE_LADDER:
        return None
    i = SIZE_LADDER.index(cfg["size"])
    return dict(cfg, size=SIZE_LADDER[i + 1]) if i + 1 < len(SIZE_LADDER) else None


def can_adapt(it):
    """รายการนี้ขยับขนาดเป้าเองได้ไหม (ข้อหลัก + โหมดบนบันได + มีเป้า + ยังไม่ใช่ขั้นบนสุด) — การ์ดใช้ตัดสินว่าจะบอกกฎนี้ไหม"""
    return (it.get("phase") == "block" and target_index(it.get("target")) is not None
            and ladder_next(it.get("mode"), item_cfg(it)) is not None)


def adaptive_cfg(hist, it):
    """(cfg ที่ควรเล่นรอบฝึกของรายการนี้, จำนวนขั้นที่ขยับจาก cfg ของแผน)

    เดินขึ้นบันไดขนาดเป้าตราบที่ ADAPT_PASSES รอบล่าสุดที่ขั้นนั้น "ถึงเป้า" ทุกรอบ (ดัชนีแรงค์ ≥ เป้า) —
    ไร้สถานะ คิดจาก history ล้วน: รอบทดสอบประจำวันที่ config ของแผน (build_queue ให้รอบแรกของวันเล่น config
    อ้างอิงเสมอ — dashboard วัดฟอร์มที่นั่น) หลุดเป้าเมื่อไร ขั้นที่ขยับไว้ก็หายเอง (ลงขั้นอัตโนมัติ)
    ไม่มีเป้า / โหมดไม่มีบันได / cfg ของแผนเพี้ยน = cfg ของแผนตามเดิม"""
    base = item_cfg(it)
    ti = target_index(it.get("target"))
    if base is None or ti is None or it.get("mode") not in LADDER_MODES:
        return base, 0
    cfg, steps = base, 0
    while True:
        nxt = ladder_next(it["mode"], cfg)
        if nxt is None:
            break
        last = series(hist, it, cfg)[-ADAPT_PASSES:]
        if len(last) < ADAPT_PASSES or min(last) < ti:
            break
        cfg, steps = nxt, steps + 1
    return cfg, steps


def history_tags(src):
    """แท็กที่มาของรอบที่ round.end_game เขียนลง history จาก round_src (ค่าไม่มี = ไม่ใส่คีย์ ; รอบเริ่มเอง = {}):
    src/rid/item (DESIGN 2.4) + phase ของรายการ routine (done_today จับคู่ข้าม routine ที่เขียนใหม่) +
    adapt = จำนวนขั้นที่ขยับขนาดเป้าจากแผน & plan_size = ขนาดที่แผนตั้ง (เฉพาะรอบฝึกที่ขยับ — server ตัดออกจากโหวต
    config อ้างอิง/ฟอร์มได้ ; เดิมไม่มีเครื่องหมาย รอบฝึกเล็กชนะโหวต 10 รอบล่าสุดตั้งแต่วันแรก)"""
    if not isinstance(src, dict):
        return {}
    out = {k: src[k] for k in ("src", "rid", "item", "phase") if src.get(k) is not None}
    if src.get("step"):
        out["adapt"] = src["step"]
        if src.get("plan_size"):
            out["plan_size"] = src["plan_size"]
    return out


def round_phase(e):
    """phase ของรอบใน history: คีย์ phase (round.end_game เขียน) → เดาจาก id รายการแบบ server (w1/b2/m3) → None"""
    ph = e.get("phase")
    if ph in PHASE_TH:
        return ph
    iid = e.get("item")
    if isinstance(iid, str) and len(iid) > 1 and iid[1:].isdigit():
        return PHASE_OF_ID.get(iid[0])
    return None


def _plan_cfg_of(e):
    """config ที่ "แผนตั้ง" ของรอบใน history — รอบฝึกที่ขยับขนาด (adapt) เทียบด้วยขนาดของแผน (plan_size) ไม่ใช่ขนาดที่เล่น"""
    if e.get("adapt") and e.get("plan_size"):
        return dict(e, size=e["plan_size"])
    return e


def done_today(hist, items, now=None, srcs=("routine",), rid=None):
    """{id รายการ: จำนวนรอบที่ทำแล้ววันนี้} — นับเฉพาะรอบวันนี้ที่ติดแท็ก src ใน srcs + ดริลเดียวกับรายการ
    rid = id ของ routine ปัจจุบัน (None = จับคู่ด้วย id รายการอย่างเดียว — วอร์ม/แผน v1):
      รอบของ routine นี้ (rid ตรง) → นับเข้ารายการตาม item
      รอบของ routine อื่นวันนี้ → จับคู่ด้วย (โหมด/variant/ดริล, phase, config) แทน id: dashboard เขียน routine ใหม่ทุกครั้ง
        ที่วิเคราะห์ และ server ตั้ง id คงฟอร์มตามลำดับ "ห่างจากซ้อมล่าสุด" (m1..m4) — ซ้อมแล้วลำดับเลื่อน (PLACEMENT ที่
        เล่นเป็น m3 กลายเป็น m4) id เดิมจึงชี้ผิดข้อ ; เกลี่ยเข้ารายการดริล+phase เดียวกันที่ยังไม่ครบ — config ตรงก่อน
        (เวลา/ขนาดของแผน ; รอบฝึกที่ขยับขนาดใช้ plan_size) แล้วตามลำดับ (b1 ก่อน b2) ไม่นับซ้ำ (เต็มทุกข้อแล้ว = ทบที่ข้อแรก
        ที่ config ตรง) ; config ต่างยังนับได้ (dashboard เปลี่ยนเวลา/ขนาดของข้อเดิม = ดริลเดิมที่ทำแล้ว) ;
        รอบที่ไม่รู้ phase (id แปลก ไม่มีคีย์ phase) จับคู่ดริลเดียวกันทุก phase — config แยกข้อที่ดริลซ้ำกันคนละ phase"""
    day = _day(now)
    by = {it["id"]: it for it in items}
    out = {it["id"]: 0 for it in items}
    other = []
    for e in hist or []:
        if not isinstance(e, dict) or e.get("src") not in srcs:
            continue
        at = e.get("at")
        if not isinstance(at, (int, float)) or _day(at) != day:
            continue
        if rid is not None and e.get("rid") != rid:
            other.append(e)
            continue
        it = by.get(e.get("item"))
        if it is not None and drill_key(e) == drill_key(it):
            out[it["id"]] += 1
    for e in other:
        k, ph = drill_key(e), round_phase(e)
        cands = [it for it in items if drill_key(it) == k and (ph is None or (it.get("phase") or "block") == ph)]
        if cands:
            pe = _plan_cfg_of(e)
            same = [it for it in cands if same_cfg(pe, k[0], item_cfg(it))]
            pool = same + [it for it in cands if it not in same]
            dst = next((it for it in pool if out[it["id"]] < it["rounds"]), pool[0])
            out[dst["id"]] += 1
    return out


def round_seconds(mode, duration=None):
    """เวลาจริงต่อรอบ (วิ) รวมนับถอยหลัง + หน้าผล — สูตรเดียวกับ server aimlink._round_s"""
    if mode == "reaction":
        return REACTION_ROUND_S + ROUND_OVERHEAD_S
    if mode == "sniper":
        return 30 + ROUND_OVERHEAD_S
    return (duration if duration in (15, 30, 60) else 30) + ROUND_OVERHEAD_S


def queue_seconds(queue, menu_duration=30):
    """เวลารวมของคิว (วิ) — รายการไม่มี cfg เล่นที่เวลาของเมนู"""
    return sum(round_seconds(q.get("mode"), (item_cfg(q) or {}).get("duration", menu_duration)) for q in queue)


def minutes_label(sec):
    return f"~{max(1, int(round(sec / 60.0)))} นาที"


def adherence(hist, now=None, goal=ADHERENCE_GOAL):
    """วันที่ซ้อมตามแผน (รอบติดแท็ก routine/plan/warmup) ใน 7 วันล่าสุด + นาที — นิยามเดียวกับ server aimlink.adherence"""
    now = time.time() if now is None else now
    lo = now - 7 * 86400
    tagged = [e for e in hist or [] if isinstance(e, dict) and e.get("src") in TAGGED_SRC
              and isinstance(e.get("at"), (int, float)) and lo <= e["at"] <= now + 60]
    days = {_day(e["at"]) for e in tagged}
    sec = sum(round_seconds(e.get("mode"), e.get("duration")) for e in tagged)
    return {"days": len(days), "goal": goal, "minutes": round(sec / 60.0, 1), "today": _day(now) in days}


def interleave(pairs, rng):
    """[(item, n รอบ)] → ลำดับรอบแบบสุ่มสลับ ไม่ให้ดริลเดียวกันติดกันเมื่อเลี่ยงได้ (b1/b2 ที่เป็นดริลเดียวกัน = ชนิดเดียว)

    จัดได้โดยไม่ติดกัน → สุ่มถ่วงตามจำนวนที่เหลือ เฉพาะตัวเลือกที่หลังวางแล้วยังจัดส่วนที่เหลือได้ไม่ติดกัน
    จัดไม่ได้ (ดริลหลักเยอะกว่าที่เหลือรวม +1) → ดริลรองแต่ละรอบแทรกคั่นดริลหลักที่ "ช่อง" สุ่มไม่ซ้ำกัน
    (ไม่วางดริลรองติดกัน ไม่ขึ้นต้นด้วยดริลรอง) = แบ่งดริลหลักเป็นท่อนสุ่มแทนที่จะรวดยาวท้ายชุด
    ในชนิดเดียวกันใช้รายการตามลำดับเดิม (b1 ก่อน b2) — ลำดับทั้งหมดขึ้นกับ rng อย่างเดียว (seed เดิม = ลำดับเดิม)"""
    left = [[it, n] for it, n in pairs if n > 0]
    out, prev = [], None
    while left:
        cnt = {}
        for it, n in left:
            k = drill_key(it)
            cnt[k] = cnt.get(k, 0) + n
        total = sum(cnt.values())

        def ok(k):
            rest = total - 1
            return all(2 * (v - (kk == k)) <= rest + (0 if kk == k else 1) for kk, v in cnt.items())

        cands = [k for k in cnt if k != prev] or list(cnt)
        good = [k for k in cands if ok(k)]
        if good:
            pick = _weighted(good, cnt, rng)
        else:
            kmax = max(cnt, key=lambda k: cnt[k])
            minors = [k for k in cnt if k != kmax]
            m = sum(cnt[k] for k in minors)
            if prev == kmax and minors and rng.random() < m / cnt[kmax]:
                pick = _weighted(minors, cnt, rng)
            else:
                pick = kmax
        rec = next(r for r in left if drill_key(r[0]) == pick)
        out.append(rec[0])
        rec[1] -= 1
        if rec[1] <= 0:
            left.remove(rec)
        prev = pick
    return out


def _weighted(keys, cnt, rng):
    x = rng.random() * sum(cnt[k] for k in keys)
    for k in keys:
        x -= cnt[k]
        if x < 0:
            return k
    return keys[-1]


def build_queue(routine, hist, now=None, seed=None):
    """คิวรอบของ routine: วอร์ม (ตามลำดับ) → ข้อหลัก + คงฟอร์ม สลับแบบสุ่ม ; ข้ามรอบที่ทำแล้ววันนี้ (กดต่อจากที่ค้าง)
    ทำครบทุกข้อแล้ว = ทั้งชุดใหม่อีกรอบ (ผู้ใช้กดเอง) ; แต่ละรอบพกแท็ก _src สำหรับ history + ข้อมูลโชว์หน้าผล
    (k/n = ข้อที่เท่าไรจากกี่ข้อ, i/of = รอบที่เท่าไรของคิวนี้) — round.end_game เขียนลง history แค่ history_tags
    (src/rid/item/phase + adapt/plan_size ของรอบฝึกที่ขยับขนาด)"""
    items = routine["items"]
    done = done_today(hist, items, now, rid=routine.get("id"))
    left = {it["id"]: max(0, it["rounds"] - done[it["id"]]) for it in items}
    if not any(left.values()):
        left = {it["id"]: it["rounds"] for it in items}
    rng = random.Random(seed if seed is not None else f"{routine.get('id')}|{_day(now)}")
    warm = [it for it in items if it.get("phase") == "warm"]
    rest = [it for it in items if it.get("phase") != "warm"]
    order = [it for it in warm for _ in range(left[it["id"]])]
    order += interleave([(it, left[it["id"]]) for it in rest], rng)
    pos = {it["id"]: i + 1 for i, it in enumerate(items)}
    return [dict(it, _src={"src": "routine", "rid": routine.get("id"), "item": it["id"],
                           "k": pos[it["id"]], "n": len(items), "phase": it.get("phase"),
                           "target": it.get("target"), "i": j + 1, "of": len(order)})
            for j, it in enumerate(order)]


def rows_for(items, done):
    """แถวของการ์ด "วันนี้": วอร์มรวมเป็นแถวเดียว, รายการดริลเดียวกันใน phase เดียวกันรวมแถว (b1/b2 4+3 รอบ)
    คืน [{"items": [...], "phase", "rounds", "done"}] ตามลำดับเดิม"""
    rows = []
    for it in items:
        ph = it.get("phase") or "block"
        key = ("warm",) if ph == "warm" else (ph, drill_key(it))
        row = next((r for r in rows if r["key"] == key), None)
        if row is None:
            row = {"key": key, "items": [], "phase": ph, "rounds": 0, "done": 0}
            rows.append(row)
        row["items"].append(it)
        row["rounds"] += it["rounds"]
        row["done"] += min(it["rounds"], done.get(it["id"], 0))
    return rows


def selftest():
    """คืน list ข้อผิดพลาด (เรียกจาก aim.selftest) — pure logic ไม่มีไฟล์/จอ"""
    errors = []
    now = time.mktime((2026, 9, 24, 20, 0, 0, 0, 0, -1))

    def it(i, mode, phase, rounds, variant="", cfg=None, target=None):
        return {"id": i, "mode": mode, "variant": variant, "phase": phase, "rounds": rounds,
                "cfg": cfg if cfg is not None else {"duration": 30, "size": "medium"}, "target": target}

    items = [it("w1", "flick", "warm", 1), it("w2", "tracking", "warm", 1, cfg={"duration": 30, "size": "large"}),
             it("b1", "gun", "block", 4, "vandal", {"duration": 30, "size": "medium", "drill": "peek"}),
             it("b2", "gun", "block", 3, "operator", {"duration": 30, "size": "medium", "drill": "hold"}),
             it("m1", "placement", "maint", 1, target="Diamond II"), it("m2", "strafe", "maint", 1),
             it("m3", "reaction", "maint", 1, "flick", None, "Platinum I")]
    items[6]["cfg"] = None
    routine = {"id": "r-20260924-ab12", "items": items}
    # ── คิว: วอร์มขึ้นก่อนตามลำดับ ; ที่เหลือสลับ ไม่ติดกัน ; seed เดิม = ลำดับเดิม ; seed ต่าง = ลำดับต่าง ──
    q1 = build_queue(routine, [], now, seed=7)
    q2 = build_queue(routine, [], now, seed=7)
    ids = [q["id"] for q in q1]
    if ids != [q["id"] for q in q2]:
        errors.append("routine: seed เดียวกันต้องได้ลำดับเดียวกัน")
    if ids[:2] != ["w1", "w2"] or sorted(ids[2:]) != sorted(["b1"] * 4 + ["b2"] * 3 + ["m1", "m2", "m3"]):
        errors.append(f"routine: วอร์มต้องมาก่อน + ครบทุกรอบ ({ids})")
    if any(a == b for a, b in zip(ids[2:], ids[3:])):
        errors.append(f"routine: ดริลเดียวกันติดกันทั้งที่จัดแยกได้ ({ids})")
    if ids[2:] == ["b1"] * 4 + ["b2"] * 3 + ["m1", "m2", "m3"]:
        errors.append("routine: คิวยังเรียงแบบรวดทีละข้อ (ไม่สลับ)")
    orders = {tuple(q["id"] for q in build_queue(routine, [], now, seed=s)) for s in range(12)}
    if len(orders) < 6:
        errors.append(f"routine: seed ต่างกันควรได้ลำดับหลากหลาย (ได้ {len(orders)} แบบจาก 12)")
    if build_queue(routine, [], now)[5]["_src"] != build_queue(routine, [], now)[5]["_src"]:
        errors.append("routine: seed ปริยาย (id+วัน) ต้องคงที่ทั้งวัน")
    s0 = q1[0]["_src"]
    if (s0["src"], s0["rid"], s0["item"], s0["k"], s0["n"], s0["i"], s0["of"]) != \
            ("routine", "r-20260924-ab12", "w1", 1, 7, 1, 12):
        errors.append(f"routine: แท็ก/ตำแหน่งรอบผิด ({s0})")
    # ดริลหลักเยอะกว่าที่เหลือรวม (8 vs 2): ติดกันน้อยสุดเท่าที่เป็นไปได้ (8 − 2 − 1 = 5 คู่) ไม่ขึ้นต้นด้วยดริลรอง
    # และจุดแทรกดริลรองสุ่มจริง (ไม่กองต้นชุดทุกครั้ง)
    big = [it("b1", "placement", "block", 5), it("b2", "placement", "block", 3),
           it("m1", "switch", "maint", 1), it("m2", "flick", "maint", 1)]
    spots = set()
    for sd in range(20):
        o = [x["mode"] for x in interleave([(x, x["rounds"]) for x in big], random.Random(sd))]
        adj = sum(a == b == "placement" for a, b in zip(o, o[1:]))
        if len(o) != 10 or o[0] != "placement" or adj != 5:
            errors.append(f"routine: ดริลรองต้องคั่นดริลหลัก ({o})")
            break
        spots.add(tuple(i for i, m in enumerate(o) if m != "placement"))
    if len(spots) < 5:
        errors.append(f"routine: จุดแทรกดริลรองไม่สุ่ม ({sorted(spots)})")
    # ── ทำแล้ววันนี้: ข้ามรอบที่ทำแล้ว ; เมื่อวาน/แท็กอื่น/ดริลไม่ตรงไม่นับ ; ครบแล้ว = ทั้งชุดใหม่ ──
    hist = [{"mode": "flick", "src": "routine", "rid": "r-old", "item": "w1", "at": now - 3600, "score": 1},
            {"mode": "gun", "variant": "vandal", "drill": "peek", "src": "routine", "item": "b1", "at": now - 60},
            {"mode": "gun", "variant": "vandal", "drill": "duel", "src": "routine", "item": "b1", "at": now - 50},
            {"mode": "gun", "variant": "vandal", "drill": "peek", "src": "plan", "item": "b1", "at": now - 40},
            {"mode": "tracking", "src": "routine", "item": "w2", "at": now - 86400}]
    d = done_today(hist, items, now)
    if (d["w1"], d["w2"], d["b1"]) != (1, 0, 1):
        errors.append(f"routine: done_today ผิด ({d})")
    q3 = build_queue(routine, hist, now, seed=7)
    if [q["id"] for q in q3].count("b1") != 3 or q3[0]["id"] != "w2":
        errors.append(f"routine: ต่อจากที่ค้างผิด ({[q['id'] for q in q3]})")
    full = [{"mode": x["mode"], "variant": x["variant"], "drill": (x["cfg"] or {}).get("drill"), "src": "routine",
             "item": x["id"], "at": now - 10} for x in items for _ in range(x["rounds"])]
    if len(build_queue(routine, full, now, seed=7)) != 12:
        errors.append("routine: ทำครบแล้วกดอีก = ทั้งชุดใหม่")
    # ── dashboard เขียน routine ใหม่กลางวัน (verify-c: r-…25d8 เล่นครบ 13 รอบ → r-…c155 ตั้ง id คงฟอร์มใหม่ตามลำดับ
    #    "ห่างจากซ้อมล่าสุด" — PLACEMENT ที่เล่นเป็น m3 กลายเป็น m4) : จับคู่ด้วย (ดริล, phase) ต้องยัง "ครบแล้ววันนี้" ;
    #    ข้อหลักดริลเดียวกันสองรายการ (b1 4 + b2 3) เกลี่ยไม่นับซ้ำ ; รอบเก่าไม่มีคีย์ phase เดาจาก id ; ดริลอื่นไม่นับ ──
    peek = {"duration": 30, "size": "medium", "drill": "peek"}
    old = {"id": "r-20260924-25d8", "items": [
        it("w1", "flick", "warm", 1), it("b1", "gun", "block", 4, "vandal", peek),
        it("b2", "gun", "block", 3, "vandal", peek), it("m1", "spray", "maint", 1, "vandal"),
        it("m2", "tracking", "maint", 1), it("m3", "placement", "maint", 1), it("m4", "switch", "maint", 1)]}
    played = []
    for q in build_queue(old, [], now, seed=3):
        e = {"mode": q["mode"], "variant": q["variant"], "drill": (q["cfg"] or {}).get("drill"), "at": now - 600,
             **{k: q["_src"][k] for k in ("src", "rid", "item")}}
        if len(played) % 2:
            e["phase"] = q["_src"]["phase"]            # ครึ่งหนึ่งมีคีย์ phase (รอบใหม่) อีกครึ่งเดาจาก id (รอบเก่า)
        played.append(e)
    new = {"id": "r-20260924-c155", "items": old["items"][:4] + [
        it("m2", "switch", "maint", 1), it("m3", "tracking", "maint", 1), it("m4", "placement", "maint", 1)]}
    dn = done_today(played, new["items"], now, rid=new["id"])
    if dn != {x["id"]: x["rounds"] for x in new["items"]}:
        errors.append(f"routine: routine เขียนใหม่ (id เลื่อน) ต้องยังครบวันนี้ ({dn})")
    pk = {"mode": "gun", "variant": "vandal", "drill": "peek", "src": "routine", "at": now - 30}
    five = [dict(pk, rid=old["id"], item="b1")] * 3 + [dict(pk, rid=old["id"], item="b2")] * 2
    mixed = [dict(pk, rid=new["id"], item="b2")] * 2 + [dict(pk, rid=old["id"], item="b1")] * 3
    d5, dm = done_today(five, new["items"], now, rid=new["id"]), done_today(mixed, new["items"], now, rid=new["id"])
    if (d5["b1"], d5["b2"], dm["b1"], dm["b2"]) != (4, 1, 3, 2):
        errors.append(f"routine: ดริลเดียวกันต้องเกลี่ย b1 ก่อน b2 ไม่นับซ้ำ ({d5}, {dm})")
    odd = [{"mode": "switch", "src": "routine", "rid": "r-x", "item": "zz", "at": now - 5},       # id แปลก = ทุก phase
           dict(pk, rid="r-x", item="b1", drill="duel")]                                          # ดริลอื่น = ไม่นับ
    do = done_today(odd, new["items"], now, rid=new["id"])
    if do["m2"] != 1 or do["b1"] or do["b2"]:
        errors.append(f"routine: รอบ id แปลกต้องจับดริลเดียวกัน / ดริลต่างไม่นับ ({do})")
    # ดริลเดียวกันสองข้อคนละ config (วอร์ม flick ใหญ่ 15 วิ + คงฟอร์ม flick กลาง 30 วิ) : รอบเก่าไม่มี phase/id แปลก
    # ต้องลงข้อที่ config ตรง ไม่ใช่ข้อแรกเสมอ ; รอบฝึกที่ขยับขนาด (adapt) เทียบด้วยขนาดของแผน ; config ต่างล้วน = ยังนับ
    two = [it("w1", "flick", "warm", 1, cfg={"duration": 15, "size": "large"}),
           it("m1", "flick", "maint", 1, cfg={"duration": 30, "size": "medium"}),
           it("b1", "dodge", "block", 2)]
    fl = {"mode": "flick", "src": "routine", "rid": "r-x", "item": "zz", "at": now - 5}
    dc = done_today([dict(fl, duration=30, size="medium")], two, now, rid="r-now")
    da = done_today([{"mode": "dodge", "src": "routine", "rid": "r-x", "item": "b9", "at": now - 5, "duration": 30,
                      "size": "small", "adapt": 1, "plan_size": "medium"}], two, now, rid="r-now")
    dx = done_today([dict(fl, duration=60, size="small")] * 2, two, now, rid="r-now")
    if (dc["w1"], dc["m1"], da["b1"], dx["w1"], dx["m1"]) != (0, 1, 1, 1, 1):
        errors.append(f"routine: จับคู่ข้าม routine ต้องเลือกข้อที่ config ตรงก่อน ({dc}, {da}, {dx})")
    # ── ความยากปรับเอง: ผ่านเป้า 2 รอบติดที่ config เดียวกัน → ขั้นถัดไปบนบันไดขนาด ; ไม่ผ่าน/รอบเดียว = คงเดิม ──
    rows = scaled_ranks(30, "medium", "switch")
    ti = target_index("Diamond II")
    ok_sc, bad_sc = rows[ti][0] + 10, rows[ti - 1][0] + 10
    p = it("b1", "switch", "block", 4, target="Diamond II")

    def pl(sc, size="medium", md="switch"):
        return {"mode": md, "score": sc, "duration": 30, "size": size, "mrev": 2, "shots_n": 5}
    cases = [([pl(ok_sc), pl(ok_sc)], "small", 1), ([pl(bad_sc), pl(ok_sc)], "medium", 0),
             ([pl(ok_sc)], "medium", 0), ([pl(ok_sc), pl(bad_sc)], "medium", 0),
             ([{**pl(ok_sc), "mrev": 1}, pl(ok_sc)], "medium", 0),          # รอบกติกาเก่าไม่นับ
             ([pl(ok_sc), pl(ok_sc), pl(ok_sc, "large")], "small", 1)]      # config อื่นไม่ตัดสาย
    for h, want, st in cases:
        cfg, steps = adaptive_cfg(h, p)
        if (cfg["size"], steps) != (want, st):
            errors.append(f"routine: adaptive_cfg ผิด ({[e['score'] for e in h]} → {cfg}, {steps})")
    # บันไดขนาดเฉพาะโหมดที่ขีดต่อขนาดตรวจกับประวัติจริงแล้ว (config.SIZE_RATIO_CHECKED) — tracking/dodge/placement ห้ามขยับ
    if any(md not in MODE_SIZE_RATIO for md in LADDER_MODES) or set(LADDER_MODES) != {"flick", "precision", "switch"}:
        errors.append("routine: บันไดขนาดต้องมีเฉพาะโหมดที่ขีดต่อขนาดตรวจกับประวัติจริงแล้ว")
    for md in ("tracking", "dodge", "placement"):
        mo = scaled_ranks(30, "medium", md)[ti][0] + 10
        if adaptive_cfg([pl(mo, md=md)] * 3, dict(p, mode=md))[1] or can_adapt(dict(p, mode=md)):
            errors.append(f"routine: {md} ต้องไม่อยู่บนบันไดขนาด (ขีดต่อขนาดยังไม่ตรงคนจริง/ยังไม่ได้ตรวจ)")
    if not can_adapt(p) or can_adapt(dict(p, target=None)) or can_adapt(dict(p, phase="maint")) \
            or can_adapt(dict(p, cfg={"duration": 30, "size": "small"})):
        errors.append("routine: can_adapt ต้องจริงเฉพาะข้อหลัก + โหมดบนบันได + มีเป้า + ยังไม่ขั้นบนสุด")
    lg = dict(p, cfg={"duration": 30, "size": "large"})
    rl = scaled_ranks(30, "large", "switch")[ti][0] + 10
    two = [dict(pl(rl, "large")), dict(pl(rl, "large")), pl(ok_sc), pl(ok_sc)]
    if adaptive_cfg(two, lg) != ({"duration": 30, "size": "small"}, 2):
        errors.append(f"routine: บันไดต้องขยับต่อเนื่อง large→medium→small ({adaptive_cfg(two, lg)})")
    if adaptive_cfg(two + [pl(ok_sc, 'small')] * 2, dict(p, cfg={"duration": 30, "size": "small"}))[1] != 0:
        errors.append("routine: ขั้นบนสุดแล้วต้องไม่ขยับต่อ")
    gun = it("b1", "gun", "block", 4, "vandal", {"duration": 30, "size": "medium", "drill": "duel"}, "Diamond II")
    if adaptive_cfg([{"mode": "gun", "variant": "vandal", "drill": "duel", "duration": 30, "tier_i": 22,
                      "mrev": MODE_REV["gun"], "score": 9}] * 3, gun)[1] != 0:
        errors.append("routine: GUNFIGHT ไม่มีบันไดขนาด — ห้ามขยับ (บันไดดวลปรับบอทในรอบเอง)")
    if adaptive_cfg([pl(ok_sc)] * 3, dict(p, target=None))[1] != 0:
        errors.append("routine: ไม่มีเป้า = ไม่ขยับ")
    # ── ฟอร์ม/แรงค์ + วันซ้อม ──
    f_i, f_n = form([pl(bad_sc), pl(ok_sc), pl(ok_sc)], p)
    if f_n != 3 or f_i != ti:
        errors.append(f"routine: form ผิด ({f_i}, {f_n})")
    if form([pl(ok_sc)] * 3 + [dict(pl(bad_sc, "small"), adapt=1)], dict(p, cfg=None))[1] != 3:
        errors.append("routine: form ไม่มี cfg ต้องไม่ยึด config ของรอบฝึกที่ขยับขนาด (adapt)")
    # gun = ค่ากลาง tier_i ทุกความยาว (duel.recent_tier ตัวเดียวกับแผงโปรไฟล์) — verify-c: [9,11,14,14] การ์ด Plat I
    # (เฉลี่ยเฉพาะ 30 วิ) แต่แผงโปรไฟล์ Plat II
    gh = [{"mode": "gun", "variant": "vandal", "drill": "peek", "duration": d, "tier_i": t, "mrev": MODE_REV["gun"],
           "tier_n": 3}
          for d, t in ((30, 9), (15, 11), (30, 14), (60, 14))]
    if form(gh, it("b1", "gun", "block", 4, "vandal", peek)) != (13, 4):
        errors.append(f"routine: form gun ต้องเท่า duel.recent_tier ({form(gh, it('b1', 'gun', 'block', 4, 'vandal', peek))})")
    if rank_index({"mode": "reaction", "variant": "static", "rt": 140}) != len(RANKS) - 1 or \
            rank_index({"mode": "strafe", "score": 30}) is not None:
        errors.append("routine: rank_index reaction/strafe ผิด")
    adh = adherence([{"src": "routine", "at": now - 100, "mode": "flick", "duration": 30},
                     {"src": "warmup", "at": now - 2 * 86400, "mode": "reaction"},
                     {"src": "plan", "at": now - 8 * 86400, "mode": "flick"},
                     {"at": now - 50, "mode": "flick"}], now)
    if (adh["days"], adh["today"], adh["minutes"]) != (2, True, round((44 + 34) / 60.0, 1)):
        errors.append(f"routine: adherence ผิด ({adh})")
    r = rows_for(items, {"w1": 1, "b1": 2})
    if [(x["phase"], x["rounds"], x["done"]) for x in r][:3] != [("warm", 2, 1), ("block", 4, 2), ("block", 3, 0)]:
        errors.append(f"routine: แถวการ์ดผิด ({[(x['phase'], x['rounds'], x['done']) for x in r]})")
    if short_rank("Platinum III") != "Plat III" or short_rank("Radiant") != "Radiant":
        errors.append("routine: short_rank ผิด")
    return errors
