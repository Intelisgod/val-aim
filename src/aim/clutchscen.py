# -*- coding: utf-8 -*-
"""กติกา/ค่าคงที่/ฉากของโหมด CLUTCH 1vN — pure python (ไม่มี pygame, py3.10) : tools/clutch_sim.py และ server import ได้
ค่าคงที่ที่ตรวจแล้ว §10.2 · ค่าตั้ง S["clutch"] (norm_cfg) · แมพ (Training Yard ในตัว + แมพที่ bake ในเครื่อง) ·
เลือกฉากจากคลังฉากจริง / สร้างจากจุดยืนยอดนิยมเมื่อคลังไม่มี side×N×site นั้น (§2.4) · PlayerView/สมองสำรองตามสัญญา §11.1
(ใช้เมื่อ aim/clutchbots.py ของทีม BOTS ยังไม่มี/โหลดไม่ได้ — หุ่นนิ่ง เกมไม่ล่ม)"""
import math

from .config import EYE_Y
from . import clutchmap, guns

# ── ค่าคงที่ที่ตรวจแล้ว (CLUTCH_DESIGN §10.2) ──
PLANT_T, DEFUSE_T, DEFUSE_HALF = 4.0, 7.0, 3.5
SPIKE_T, ROUND_T = 45.0, 100.0
DEFUSE_R, DEFUSE_DY = 2.4, 1.0          # ระยะแนวราบ + ต่างระดับ ; ต้องเห็น spike ด้วย (LOS ตา → spike)
TAG_SLOW, TAG_REC = 0.275, 0.5          # โดนยิง = ความเร็ว ×0.275 แล้วฟื้นเป็นเส้นตรงใน ~0.5 วิ (clutch เท่านั้น)
# ── ค่าประมาณ (ไม่มีตัวเลขทางการ — ตั้งชื่อไว้ที่เดียว) ──
SPIKE_EQUIP_T = 0.5                     # หยิบ spike ขึ้นมือ (ปืน → spike) ; spike → ปืน ใช้ equip ของปืน (guns.WEAPONS)
EYE_TAU = 0.035                         # กล้องไล่ระดับตาแบบนุ่ม (~0.08 วิ ถึง 90%) ตอนก้าวขึ้น/หมอบ
# ── กระโดด/ตก (§13.1 realism pass v2 — ผู้เล่นเท่านั้น ; ใช้ใน clutchmove.py) ──
# ความสูง/เวลากระโดดของ Valorant ไม่มีตัวเลขทางการ (ext_constants #20 UNVERIFIED) : เลือก JUMP_H 1.0 ม. ลอย ≈ 0.65 วิ
#   → g = 8h/T² ≈ 18.9 ม./วิ² (ใช้ทั้งกระโดดและตกขอบ — เดิมตกขอบ 9.8) ; JUMP_V = √(2gh) ≈ 6.15 ม./วิ (ลอย 2v/g = 0.651 วิ)
GRAVITY = 18.9
JUMP_H = 1.0
JUMP_V = math.sqrt(2.0 * GRAVITY * JUMP_H)
CROUCH_TUCK = 0.55                      # หมอบกลางอากาศ = หดขา (= guns.CROUCH_DROP) : ปลายเท้าสูงขึ้นเท่านี้ หัว/กล้องไม่ขยับ
MOUNT_EPS = 0.05                        # ลอยข้ามขึ้นผิวที่ ≤ ปลายเท้า + นี้ได้ → กระโดดเฉย ~1.05 ม. / หมอบกระโดด ~1.6 ม.
#                                         (กล่องครึ่งตัว 1.1 ต้องหมอบกระโดด · ลังเดี่ยว 1.5 ได้ · ลังซ้อน 3.0 ไม่มีทาง)
AIR_ACCEL_K = 0.25                      # แรงเร่งจากปุ่มทิศกลางอากาศ = ×ของบนพื้น ; ไม่มีแรงเสียดทาน/เบรกในอากาศ ; ไม่เร็วเกินเพดาน
# ตกแล้วเจ็บ: JumpFallDamageCurve.json (ไฟล์เกม) x = ความสูงที่ตก (สมมติเป็น ซม. — หน่วย UNVERIFIED) → HP (ไม่ผ่านเกราะ)
#   (0 ซม. คงที่ 0) · 600 → 15 · 1200 → 90 · 1500 → 100 (cubic ตาม tangent ในไฟล์ ; เกิน 15 ม. = 100) — ต่ำกว่า 6 ม. ไม่เจ็บ
FALL_KEYS = ((0.0, 0.0, 0.0, 0.0, "constant"), (6.0, 15.0, 0.0, 0.0, "cubic"),
             (12.0, 90.0, 11.429, 7.362, "cubic"), (15.0, 100.0, 1.293, 1.295, "cubic"))   # tangent ต่อ ซม. ×100 = ต่อ ม.
SEEN_KEEP = 2.0                         # มินิแมพโชว์ศัตรูที่เห็นอยู่/เพิ่งเห็นภายในเท่านี้ (แบบเกม — ห้ามเห็นทะลุกำแพง)
END_DELAY = 1.6                         # ค้างฉากจบให้เห็นผลก่อนเข้าหน้าผล
FAKE_DEFUSE_S = 1.0                     # กดกู้แล้วปล่อยเร็วกว่านี้ = กู้หลอก (fake/tap defuse)
YARD = "yard"                           # Training Yard ในตัว (clutchmap.testyard — ไม่มี IP ของ Riot ; ตัวเดียวที่ publish)
TIER_CHOICES = ("duel", 6, 9, 12, 15, 18, 21)   # ตามแรงค์ DUEL / Silver I / Gold I / Plat I / Diamond I / Asc I / Immortal
WEAPON_CHOICES = ("vandal", "phantom", "sheriff", "ghost", "classic", "operator")
DEFAULT_CFG = {"map": YARD, "side": "atk", "n": 2, "site": "any", "tier": "duel", "weapon": "vandal",
               "placement": "real", "show_secs": False, "cue_heard": True}
WHY_TH = {"elim": "เก็บครบทุกตัว", "detonated": "spike ระเบิด", "defused": "กู้ spike สำเร็จ",
          "time": "หมดเวลาก่อนวาง spike", "died": "ตาย", "ninja": "กู้เนียนทั้งที่ศัตรูยังอยู่ (ninja)",
          "quit": "จบรอบเอง (นับแพ้)"}

_MODS = {}
_YARD_CM = []


def _module(key):
    """clutchbots / clutchgl แบบ lazy + กันพัง (import ครั้งเดียวต่อโปรเซส ; ไม่มี/พัง = None)"""
    if key not in _MODS:
        try:
            if key == "bots":
                from . import clutchbots as m
            else:
                from . import clutchgl as m
        except Exception:
            m = None
        _MODS[key] = m
    return _MODS[key]


def fall_damage(h):
    """ดาเมจตก (HP, ไม่ผ่านเกราะ) จากความสูงที่ตัวร่วงลงมา h ม. — JumpFallDamageCurve (FALL_KEYS)"""
    if h < FALL_KEYS[1][0]:
        return 0.0
    return max(0.0, guns.curve_ue(FALL_KEYS, h))


def load_map(slug):
    """'yard' = Training Yard ในตัว (สร้างครั้งเดียว) ; แมพจริง = clutchmap.cached (ผิดพลาด → raise ให้ผู้เรียกถอยไป yard)"""
    if slug == YARD:
        if not _YARD_CM:
            cm = clutchmap.testyard()
            cm.slug, cm.name = YARD, "Training Yard"
            _YARD_CM.append(cm)
        return _YARD_CM[0]
    return clutchmap.cached(slug)


def map_choices():
    """[(slug, ชื่อ, ไซต์)] — Training Yard เสมอ + แมพที่ bake แล้วในเครื่องนี้ (clutchmap.list_maps ไม่ raise)"""
    out = [(YARD, "Training Yard", ("A", "B"))]
    for m in clutchmap.list_maps():
        s = m.get("slug")
        if isinstance(s, str) and s != YARD and all(s != o[0] for o in out):
            out.append((s, str(m.get("name") or s), tuple(m.get("sites") or ("A", "B"))))
    return out


def norm_cfg(d):
    """S["clutch"] → ค่าตั้งที่ใช้ได้เสมอ (คีย์หาย/ค่าเพี้ยนจากไฟล์ = ค่าเริ่มต้นของคีย์นั้น)"""
    c = dict(DEFAULT_CFG)
    d = d if isinstance(d, dict) else {}
    s = d.get("map")
    if isinstance(s, str) and clutchmap._SLUG_RE.match(s):
        c["map"] = s
    if d.get("side") in ("atk", "def"):
        c["side"] = d["side"]
    if isinstance(d.get("n"), int) and not isinstance(d.get("n"), bool) and 1 <= d["n"] <= 5:
        c["n"] = d["n"]
    if d.get("site") in ("any", "A", "B", "C"):
        c["site"] = d["site"]
    if d.get("tier") in TIER_CHOICES:
        c["tier"] = d["tier"]
    if d.get("weapon") in WEAPON_CHOICES:
        c["weapon"] = d["weapon"]
    if d.get("placement") in ("real", "holds"):
        c["placement"] = d["placement"]
    for k in ("show_secs", "cue_heard"):
        if isinstance(d.get(k), bool):
            c[k] = d[k]
    return c


def _wsample(spots, k, rng):
    """สุ่ม k จุดไม่ซ้ำแบบถ่วงน้ำหนัก (ช่อง 4 ของจุด = w ; ไม่มี = 1)"""
    pool = [list(s) for s in spots if isinstance(s, (list, tuple)) and len(s) >= 3]
    out = []
    while pool and len(out) < k:
        tot = sum(max(1e-6, float(s[3]) if len(s) > 3 and s[3] else 1.0) for s in pool)
        r, acc = rng.random() * tot, 0.0
        for i, s in enumerate(pool):
            acc += max(1e-6, float(s[3]) if len(s) > 3 and s[3] else 1.0)
            if r <= acc:
                out.append(pool.pop(i))
                break
        else:
            out.append(pool.pop())
    return out


def _yaw_to(ax, az, bx, bz):
    return math.atan2(bx - ax, bz - az)


def _ground(cm, x, z):
    """ระดับเท้าที่ยืนจริง (support_y) → พื้นใต้จุด → 0"""
    s = cm.support_y(x, z)
    return s if s is not None else (cm.floor_y(x, z) or 0.0)


def _start_on_path(cm, spawn, goal, rng):
    """จุดเริ่มบนทาง nav จาก spawn ไปเป้าหมาย ห่างเป้าหมาย 20–45 ม. ตามทางเดิน (§2.4 ฉากสร้างเอง) — หาทางไม่ได้ = spawn"""
    path = cm.astar((spawn[0], spawn[1]), (goal[0], goal[1]), max_nodes=20000)
    if not path or len(path) < 2:
        return spawn[0], spawn[1]
    want, acc = rng.uniform(20.0, 45.0), 0.0
    for a, b in zip(path[::-1], path[-2::-1]):             # เดินย้อนจากเป้าหมายไปหา spawn
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if acc + seg >= want and seg > 1e-9:
            u = (want - acc) / seg
            x, z = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
            return (x, z) if cm.disc_clear(x, z) else (b[0], b[1])
        acc += seg
    return spawn[0], spawn[1]


def _hidden_start(cm, spawn, goal, enemies, rng):
    """จุดเริ่มฉากสร้างเองที่ศัตรูคนใดก็มองไม่เห็นตอนเริ่ม (บอทยิงก่อนผู้เล่นได้ขยับ = ตายฟรี ; เดิมเห็นกันทันที ATK 30/60 ·
    DEF 88/120) : สุ่มบนทางเดิน ≤ 10 ครั้ง (_start_on_path) → ไม่ได้ = จุดซ่อนที่เดินได้ใกล้จุดสุ่มแรกสุด (วง 0.5–12 ม. บนกราฟ
    nav) → ไม่มีเลย = จุดสุ่มแรก (ด่านเล็ก/ศัตรูคุมทุกทาง)"""
    eyes = [(e[0], (cm.floor_y(e[0], e[1]) or 0.0) + EYE_Y, e[1]) for e in enemies]
    bp = getattr(_module("bots"), "body_points", None)          # จุดตัวอย่างแบบที่สมองบอทใช้มอง (ไหล่ตั้งฉากแนวสายตา)

    def hidden(x, z):
        f = _ground(cm, x, z)
        return not any(cm.any_visible(eye, bp(eye, x, z, f) if bp else guns.humanoid_points(x, z, 0.0, f))
                       for eye in eyes)
    first = None
    for _ in range(10):
        x, z = _start_on_path(cm, spawn, goal, rng)
        first = first or (x, z)
        if hidden(x, z) and clutchmap.start_safe(cm, x, z, enemies):     # ไกล ≥ 10 ม. + ขยับ 1.5 ม. ก็ยังไม่โดนเห็น
            return x, z
    for _ in range(10):
        x, z = _start_on_path(cm, spawn, goal, rng)
        if hidden(x, z):
            return x, z
    x0, z0 = first
    for k in range(1, 25):
        r = 0.5 * k
        for q in range(16):
            a = 2.0 * math.pi * q / 16.0
            x, z = x0 + r * math.sin(a), z0 + r * math.cos(a)
            if cm.disc_clear(x, z) and cm.nav_node(x, z) is not None and hidden(x, z):
                return x, z
    return x0, z0


def gen_scenario(cm, side, n, site, rng):
    """ฉากสร้างเองเมื่อคลังฉากจริงไม่มี side×N×site นี้ (§2.4): ศัตรู N จุดสุ่มถ่วงน้ำหนักจาก holds ของไซต์
    (ATK = จุดเฝ้าของ DEF · DEF = จุดหลังวางของ ATK) + จุดเริ่มบนทางเดิน 20–45 ม. จากเป้าหมาย"""
    names = sorted(cm.sites) or ["A"]
    s = rng.choice([x for x in names if site in ("any", x)] or names)
    sd = cm.sites.get(s) or {}
    c = sd.get("c") or [0.0, 0.0]
    hk = "def" if side == "atk" else "atk_post"
    e = _wsample((cm.holds.get(s) or {}).get(hk) or [], n, rng)
    if len(e) < n:
        e += _wsample([h for k, v in cm.holds.items() if k != s for h in (v.get(hk) or [])], n - len(e), rng)
    tries = 0
    while len(e) < n and tries < 400:                      # holds ไม่พอ = จุดเดินได้สุ่มรอบไซต์ 4–14 ม.
        tries += 1
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(4.0, 14.0)
        x, z = c[0] + math.sin(a) * r, c[1] + math.cos(a) * r
        if cm.disc_clear(x, z, clutchmap.BOT_R):
            e.append([x, z, _yaw_to(x, z, c[0], c[1])])
    sc = {"t": side, "s": s, "n": n, "e": [[p[0], p[1], p[2]] for p in e[:n]], "gen": 1}
    goal = c
    if side == "def":
        pl = _wsample(sd.get("plants") or [[c[0], c[1], 1]], 1, rng)[0]
        sc["k"] = goal = [pl[0], pl[1]]
    sp = cm.spawns.get(side) or [c[0], c[1] - 30.0]
    px, pz = _hidden_start(cm, sp, goal, sc["e"], rng)
    sc["p"] = [px, pz, _yaw_to(px, pz, goal[0], goal[1])]
    sc["left"] = round(rng.uniform(40.0, 75.0) if side == "atk" else rng.uniform(25.0, 40.0))
    return sc


def scen_left(sc, side):
    """เวลาเริ่มของฉากตามกติกาโหมด: ATK = เวลารอบก่อนวาง 25–90 วิ (ไม่มี = 60) ; DEF = เวลา spike 15–42 วิ (ไม่มี = 35)"""
    if side == "atk":
        return max(25.0, min(90.0, float(sc.get("left") or 60)))
    return max(15.0, min(42.0, float(sc.get("left") or 35)))


def _path_len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def scen_need(cm, sc, side, run_speed):
    """วินาทีขั้นต่ำที่ต้องใช้ทำภารกิจของฉากแม้ไม่มีศัตรูเลย (ทาง A* จริงของผู้เล่น ÷ ความเร็ววิ่งของปืนที่เลือก) ;
    None = หาทางไม่ได้ (ในงบ A*) — DEF: เดินถึงวงกู้ DEFUSE_R + กู้ 7 วิ ; ATK: เดินถึงช่องแรกของพื้นที่วางของไซต์ + วาง 4 วิ
    (หยิบ spike ระหว่างเดินได้) — ราคา A* หนึ่งครั้ง (~1 ms, สูงสุด ~30 ms บนแมพจริง) : เรียกตอนเลือกฉากเท่านั้น"""
    p = sc.get("p") or [0.0, 0.0]
    if side == "def":
        k = sc.get("k") or (cm.sites.get(sc.get("s")) or {}).get("c")
        if not k:
            return None
        path = cm.astar((p[0], p[1]), (k[0], k[1]), max_nodes=80000)
        if not path:
            return None
        L = _path_len([(p[0], p[1])] + list(path) + [(k[0], k[1])])
        return max(0.0, L - DEFUSE_R) / run_speed + DEFUSE_T
    s = sc.get("s")
    c = (cm.sites.get(s) or {}).get("c")
    if not c:
        return None
    if cm.zone_at(p[0], p[1]) == s:
        return PLANT_T
    path = cm.astar((p[0], p[1]), (c[0], c[1]), max_nodes=80000)
    if not path:
        return None
    acc = 0.0
    for a, b in zip([(p[0], p[1])] + list(path), list(path) + [(c[0], c[1])]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(seg / 0.25))
        for q in range(1, steps + 1):
            u = q / float(steps)
            if cm.zone_at(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u) == s:
                return (acc + seg * u) / run_speed + PLANT_T
        acc += seg
    return acc / run_speed + PLANT_T


def scen_safe(cm, i):
    """ฉาก i ของแมพเกิดปลอดภัยไหม (clutchmap.start_safe) — จำผลไว้บนตัวแมพ (แมพถูก cache ข้ามรอบ ; ~1 ms/ฉาก ครั้งแรก)"""
    memo = cm.__dict__.setdefault("_safe_memo", {})
    ok = memo.get(i)
    if ok is None:
        s = cm.scen[i]
        ok = memo[i] = clutchmap.start_safe(cm, s["p"][0], s["p"][1], s.get("e") or [])
    return ok


FEAS_MARGIN = 0.5                       # วิ — เผื่อหันตัว/หยุดนิ่งก่อนเริ่มวาง/กู้ ในเกณฑ์ "ชนะได้แม้ไม่มีศัตรู"


def scen_feasible(cm, sc, side, run_speed):
    """ชนะได้ไหมถ้าไม่มีศัตรูเลยและเดินทางสั้นสุด (ด้วยปืนที่เลือก) — หาทางไม่ได้ = ไม่ตัดสิน (True)"""
    need = scen_need(cm, sc, side, run_speed)
    return need is None or need + FEAS_MARGIN <= scen_left(sc, side)


def pick_scenario(cm, side, n, site, rng, avoid=None, run_speed=None):
    """(ดัชนี, ฉาก) จากคลังฉากจริงของแมพ (§2.4) ที่ตรง side/N/site — สุ่มลำดับ (ไม่ซ้ำฉากก่อนหน้าถ้ามีตัวเลือก) ;
    ไม่มีเลย = สร้างจาก holds (ดัชนี -1)
    • เลือกไซต์เจาะจง + ATK: ข้ามฉากที่ผู้เล่นเริ่มอยู่ในพื้นที่วางของอีกไซต์ (ป้ายไซต์ของ bake = ไซต์ที่รอบจริงวางในที่สุด —
      Ascent #114/#838 ป้าย B แต่เริ่มในโซน A วาง A ได้ใน 4.7 วิ)
    • run_speed (ม./วิ ของปืนที่เลือก) = ข้ามฉากที่ชนะไม่ได้แม้ไม่มีศัตรู (scen_feasible — เช่น DEF Ascent #637 เดิน 86 ม.
      มีเวลา 19 วิ) สุ่มใหม่ไม่เกิน 6 ครั้ง ; ฉากเดิมอีกครั้ง/R ไม่ผ่านที่นี่ (ใช้ดัชนีเดิม)"""
    pool = [i for i, s in enumerate(cm.scen or []) if s.get("t") == side and int(s.get("n", 0)) == n
            and (site == "any" or (s.get("s") == site and (
                side != "atk" or cm.zone_at(s["p"][0], s["p"][1]) in (None, site))))]
    # จุดเกิดต้องปลอดภัย (clutchmap.start_safe — ผู้ใช้เจอ "เกิดกลางดงศัตรู ตายทันที") ; ไม่มีฉากจริงที่ปลอดภัยเลย =
    # ถอยไปฉากสร้างจาก holds (_hidden_start หาจุดเริ่มที่ไม่มีใครเห็น) แทนการยอมเกิดกลางดง
    pool = [i for i in pool if scen_safe(cm, i)]
    if pool:
        if avoid in pool and len(pool) > 1:
            pool.remove(avoid)
        i = rng.choice(pool)
        for _ in range(6):
            if not run_speed or len(pool) <= 1 or scen_feasible(cm, cm.scen[i], side, run_speed):
                break
            pool.remove(i)
            i = rng.choice(pool)
        return i, dict(cm.scen[i])
    return -1, gen_scenario(cm, side, n, site, rng)


class _PV:
    """PlayerView ตามสัญญา §11.1 + §13.2 (ใช้เมื่อ clutchbots ไม่มีคลาสนี้) — attribute ล้วน โหมดเติมทุกเฟรม
    air = ลอยอยู่ · land_t = เวลาเกมที่แตะพื้นครั้งล่าสุด (−9 = ยังไม่เคย) · land_loud = ครั้งนั้นมีเสียง (ไม่ได้ค้าง Shift) ·
    on_box = ยืนบนหลังกล่อง"""
    def __init__(self):
        self.x = self.z = self.feet = self.crouch = self.vx = self.vz = 0.0
        self.run_speed, self.alive, self.weapon = guns.RUN_SPEED, True, "vandal"
        self.planting = self.defusing = self.spike_out = False
        self.air, self.land_t, self.land_loud, self.on_box = False, -9.0, False, False

    def eye(self):
        return (self.x, self.feet + EYE_Y - guns.CROUCH_DROP * self.crouch, self.z)


class _DummyBrain:
    """สมองสำรองตอนไม่มี/โหลด clutchbots ไม่ได้: หุ่นนิ่งตามจุดในฉาก ไม่ยิง ไม่ได้ยิน — โหมดยังเล่นได้ (ซ้อมเดิน/วาง/กู้)"""
    def __init__(self, cmap, scen, side, tier, weapon, rng, t0, placement="real"):
        self.bots = []
        for e in scen.get("e") or []:
            b = guns.Bot(e[0], e[1])
            b.y0 = cmap.support_y(e[0], e[1], clutchmap.BOT_R) or cmap.floor_y(e[0], e[1]) or 0.0
            b.weapon, b.exposed = weapon, False
            b.meta = {"yaw": e[2] if len(e) > 2 else 0.0, "pitch": 0.0, "state": "dummy", "sees": False}
            self.bots.append(b)

    def prepare(self, max_nodes=500):
        return True

    def update(self, dt, t, pv):
        return []

    def bot_defuse(self):
        return None

    def can_bots_defuse(self, t, spike_xz, spike_left):
        return any(b.alive and math.hypot(b.x - spike_xz[0], b.z - spike_xz[1]) / 6.75 + 1.0 + DEFUSE_T <= spike_left
                   for b in self.bots)

    def seen_count(self):
        return 0

    def __getattr__(self, name):                          # on_* ทุกตัวของสัญญา = ไม่ทำอะไร
        if name.startswith("on_"):
            return lambda *a, **k: None
        raise AttributeError(name)


def why_text(side, why, planted=True):
    """เหตุผลแพ้/ชนะเป็นภาษาไทย ตามฝั่งของผู้เล่น (defused/detonated/died ความหมายกลับกันระหว่าง ATK กับ DEF)
    planted = spike ลงแล้ว (ATK ตายหลังวาง = ตัดสินจากศัตรูไปกู้ทัน ; ตายก่อนวาง = "ตาย" เฉย ๆ — history ใช้ "died" ทั้งคู่)"""
    if side == "atk" and why == "defused":
        return "ศัตรูกู้ spike ได้"
    if side == "def" and why == "detonated":
        return "spike ระเบิด — กู้ไม่ทัน"
    if side == "atk" and why == "detonated":
        return "spike ระเบิด"
    if side == "atk" and why == "died" and planted:
        return "ตาย (หลังวาง = ศัตรูไปกู้ทัน)"
    return WHY_TH.get(why, why)
