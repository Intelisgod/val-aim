# -*- coding: utf-8 -*-
"""แกนอาวุธจริง (pure python — ไม่มี pygame) : ตารางปืนตามค่าจริงของ Valorant + บอทหุ่นคน + ดาเมจ/เกราะ

ที่มาตัวเลข: wiki.playvalorant.com (ทางการ) ณ patch 12.x ก.ย. 2026 (โทษเคลื่อนที่ตรวจซ้ำ 2026-09-23) —
  Operator  255/150/120 0-50m · 0.6 rps · mag 5 · reload 3.7 · scope 2.5x/5x · hipfire 5° (crouch 4.5°) scoped 0°
            หมอบเดิน +7.5° เดิน +10° วิ่ง +15° · deadzone 15% ของความเร็ววิ่ง (patch 1.09)
  Vandal    160/40/34 0-50m · 9.75 rps (ADS 90%) · mag 25 · first-shot 0.25° (crouch 0.21) max 1.0° · ADS 1.25x 0.157°
            หมอบเดิน +0.8° เดิน +3° วิ่ง +6° (ไรเฟิลทุกกระบอกตั้งแต่ 9.10)
  Phantom   156/39/33.15 0-20m, 140/35/29.75 20-50m · 11 rps (ADS 90%) · mag 30 · 0.2°/0.17 max 0.9° · ADS 1.25x 0.11°
  Sheriff   159.5/55/46.75 0-30m, 145/50/42.5 30-50m · 4 rps · mag 6 · 0.25°/0.19 max 2.75° · หมอบเดิน +0.5 เดิน +1.2 วิ่ง +3
  Ghost     105/30/25.5 0-30m, 87.5/25/21.25 30-50m · 6.75 rps · mag 13 (9.10: 15→13) · reload 1.5 · วิ่ง 5.73 m/s
            0.3° (crouch 0.23) max 1.65° · หมอบเดิน +0.5 เดิน +1.1 วิ่ง +2.3 (9.10)
  Classic   78/26/22.1 0-30m, 66/22/18.7 30-50m · 6.75 rps · mag 12 · reload 1.75 · วิ่ง 5.73 m/s
            คลิกซ้าย 0.4° (crouch 0.3) max 1.8° · หมอบเดิน +0.5 เดิน +1.1 วิ่ง +2.3
            คลิกขวา = ยิงชุด 3 เม็ดพร้อมกัน 2.22 ชุด/วิ · 1.9° (crouch 1.71) max 5.78° · หมอบเดิน +0 เดิน +0.6 วิ่ง +1.5
  (ดาเมจทศนิยม = ค่าจาก valorant-api.com/v1/weapons ที่ดึงจากไฟล์เกม — wiki ปัดลงเป็นจำนวนเต็มตอนแสดง
   ตรวจซ้ำ 2026-09-24 ทั้ง wiki และ API: tools/sync_weapons.py ต้องไม่เจอค่าต่าง)
เกราะ: heavy shield 50 รับ 66% ของดาเมจแต่ละนัด (ที่เหลือเข้า HP 100) — Vandal 4 นัดตัว/1 หัว, Sheriff 3 ตัว,
Op 1 ตัว / 2 ขา, Ghost 2 หัว / 5 ตัว, Classic 2 หัว / 6 ตัว ตรงเกมทุกกรณี (ดู selftest — Ghost 1 หัวฆ่าได้เฉพาะ
คนไม่ใส่เกราะ ≤30 ม.)
ความแม่นขณะเคลื่อนที่ = move_error_deg: deadzone 27.5% (patch 3.0) + รูปเส้นโค้ง error_move จากไฟล์เกม × ขนาดโทษจาก wiki
"""
import math
import random

from .config import EYE_Y, MOVE_DEADZONE, MOVE_DEADZONE_OP
from .riot_data import RIOT
from .stability import Stability

RUN_SPEED = 5.4            # m/s (ปืนหลักทุกกระบอกยกเว้น Op 5.13 ; Ghost/Classic 5.73 = 6.75 × 0.85)
PLAYER_HP, PLAYER_SHIELD = 100, 50
SHIELD_ABSORB = 0.66       # เกราะหนักรับ 66% ของดาเมจนัดนั้น

# (ระยะสูงสุดของช่วง (ม.), หัว, ตัว, ขา)
WEAPONS = {
    "operator": {
        "name": "OPERATOR", "kind": "sniper", "auto": False, "rps": 0.6, "mag": 5, "reload": 3.7,
        "run_speed": 5.13, "equip": 1.5,
        "dmg": [(50, 255, 150, 120)],
        # hipfire: ฐาน (ยืน/ย่อ) + ส่วนเพิ่มตามการเคลื่อนที่ (องศา)
        "spread": {"stand": 5.0, "crouch": 4.5, "max": 5.0, "walk": 10.0, "run": 15.0, "crouch_move": 7.5},
        "deadzone": MOVE_DEADZONE_OP,
        "zooms": [2.5, 5.0],            # RMB วน 2.5x → 5x → ออกสโคป
        "scoped_spread": 0.0,            # นิ่ง+สโคป = แม่นเป๊ะ; ขยับขณะสโคปใช้ค่า walk/run ด้านบน
        "scoped_move": 0.72,             # ความเร็วเดินขณะสโคป
        "unscope_on_shot": True,         # ชักกระสุนหลังยิง = หลุดสโคป (เหมือนเกม)
        # growth/recover/kick = โมเดลเก่า (ก่อน 11 ก.ย. 2026) — ตอนนี้รีคอยล์/สเปรดจากการยิงมาจาก aim/stability.py
        # (เส้นโค้งในไฟล์เกม) คีย์เหล่านี้เหลือให้ GunHeat/kick_for legacy อ่านได้เท่านั้น
        "growth": 0.0, "recover": 0.3,
        "kick": {"pitch": 3.0, "yaw": 0.25, "recover": 9.0},
    },
    "vandal": {
        "name": "VANDAL", "kind": "rifle", "auto": True, "rps": 9.75, "mag": 25, "reload": 2.5,
        "run_speed": 5.4, "equip": 1.0,
        "dmg": [(50, 160, 40, 34)],
        "spread": {"stand": 0.25, "crouch": 0.21, "max": 1.0, "walk": 3.0, "run": 6.0, "crouch_move": 0.8},
        "zooms": [1.25], "ads_rps": 0.9, "ads_spread": 0.157, "ads_move": 0.76,
        "unscope_on_shot": False,
        "growth": 0.16, "recover": 0.42,                 # (legacy — ดูหมายเหตุที่ operator)
        "kick": {"spray": "vandal", "recover": 7.0},
    },
    "phantom": {
        "name": "PHANTOM", "kind": "rifle", "auto": True, "rps": 11.0, "mag": 30, "reload": 2.5,
        "run_speed": 5.4, "equip": 1.0,
        # ขา = ตัว × 0.85 ตามไฟล์เกม (เดิม 33/29 ที่ wiki ปัดลง) — ต่างกันแค่ชุด 3 ตัว + 1 ขา ≤20 ม. (150 → 150.15)
        # ที่เดิมพอดี 150 ตายหรือไม่ตายแล้วแต่ทศนิยมลอยตัว ; ตอนนี้ตายแน่นอนเหมือนเกม
        "dmg": [(20, 156, 39, 33.15), (50, 140, 35, 29.75)],
        "spread": {"stand": 0.2, "crouch": 0.17, "max": 0.9, "walk": 3.0, "run": 6.0, "crouch_move": 0.8},
        "zooms": [1.25], "ads_rps": 0.9, "ads_spread": 0.11, "ads_move": 0.76,
        "unscope_on_shot": False,
        "growth": 0.13, "recover": 0.40,
        "kick": {"spray": "phantom", "recover": 7.0},
    },
    "sheriff": {
        "name": "SHERIFF", "kind": "pistol", "auto": False, "rps": 4.0, "mag": 6, "reload": 2.25,
        "run_speed": 5.4, "equip": 1.0,
        # เดิม 159/55/46 · 145/50/42 (ค่าที่ wiki ปัดลง) — ไม่เปลี่ยนจำนวนนัดที่ต้องใช้ในชุดไหนเลย (หัว/ตัว/ขา 3 นัด
        # ผสมกันใกล้ 150 สุดคือ 1 ตัว + 2 ขา = 148.5 ยังไม่ตายเหมือนเดิม) แค่ให้ตรงไฟล์เกม/sync_weapons
        "dmg": [(30, 159.5, 55, 46.75), (50, 145, 50, 42.5)],
        "spread": {"stand": 0.25, "crouch": 0.19, "max": 2.75, "walk": 1.2, "run": 3.0, "crouch_move": 0.5},
        "zooms": [], "unscope_on_shot": False,
        # ยิงรัว = สเปรดพุ่งเร็วมาก (recover ช้า) — นี่คือเหตุผลที่ Sheriff ต้อง "แตะ" ไม่ใช่กด
        "growth": 0.9, "recover": 0.85,
        # เด้งแรงต่อนัด และยิ่งรัวยิ่งเด้ง (นัดที่ 2-4 ในชุดเดียวกัน +0.4°/นัด) ฟื้นเร็ว
        "kick": {"pitch": 1.8, "pitch_per_shot": 0.4, "yaw": 0.35, "recover": 11.0},
    },
    # ปืนสั้นรอบ pistol/eco — 16% ของการตายของผู้ใช้ (Ghost 161, Classic 129 ศพ จาก 2 บัญชี) ; ไม่มี legacy
    # growth/recover/kick (รีคอยล์/สเปรดจากการยิงมาจาก stability.py ทั้งหมด — Classic ใช้ BLOCK_OVERRIDES ที่นั่น)
    "ghost": {
        "name": "GHOST", "kind": "pistol", "auto": False, "rps": 6.75, "mag": 13, "reload": 1.5,
        "run_speed": 5.7375, "equip": 0.75,
        "dmg": [(30, 105, 30, 25.5), (50, 87.5, 25, 21.25)],
        "spread": {"stand": 0.3, "crouch": 0.23, "max": 1.65, "walk": 1.1, "run": 2.3, "crouch_move": 0.5},
        "zooms": [], "unscope_on_shot": False,
    },
    "classic": {
        "name": "CLASSIC", "kind": "pistol", "auto": False, "rps": 6.75, "mag": 12, "reload": 1.75,
        "run_speed": 5.7375, "equip": 0.75,
        "dmg": [(30, 78, 26, 22.1), (50, 66, 22, 18.7)],
        "spread": {"stand": 0.4, "crouch": 0.3, "max": 1.8, "walk": 1.1, "run": 2.3, "crouch_move": 0.5},
        "zooms": [], "unscope_on_shot": False,
        # คลิกขวา (alt fire "Shotgun" ใน API): 3 เม็ดออกพร้อมกันในกรวยเดียว เม็ดละดาเมจเท่าตาราง dmg
        # สเปรด/โทษเคลื่อนที่จาก wiki ; การโตของสเปรดเมื่อกดขวาติดกัน (patch 2.0 "escalates progressively")
        # ไม่มีตัวเลขเปิดเผย → ประมาณ: ชุดที่ 1 = 1.9° ไต่เป็นเส้นตรงถึง max ที่ชุดที่ 3 (esc_bursts = 2)
        # ฟื้นเป็นศูนย์ใน esc_reset วิหลังพ้นช่วงยิง (ประมาณเช่นกัน — ดู gunplay.gun_alt_spread)
        "alt": {"pellets": 3, "rps": 2.22,
                "spread": {"stand": 1.9, "crouch": 1.71, "max": 5.78, "max_crouch": 5.21,
                           "walk": 0.6, "run": 1.5, "crouch_move": 0.0},
                "esc_bursts": 2, "esc_reset": 0.5},
    },
}
# ลำดับปุ่ม V / insight / เมนู — ปืนหลักก่อน แล้วปืนสั้น (เมนูแบ่งสองกลุ่มตาม kind == "pistol")
# id ตรง contract DESIGN §2.5 (valorant-stats aimlink.AIM_GUN_WEAPONS ต้องมีครบชุดนี้)
WEAPON_ORDER = ["operator", "vandal", "phantom", "sheriff", "ghost", "classic"]

# id ดริล GUNFIGHT ตามลำดับเมนู + ดริลที่ปืนแต่ละกระบอกเล่นได้ — อยู่โมดูลนี้เพราะ pure python (ชื่อ/คำอธิบายดริลอยู่
# gunplay.GUN_DRILLS ซึ่งพึ่ง pygame) : valorant-stats (stdlib ล้วน) import WEAPON_ORDER/DRILL_ORDER/WEAPON_DRILLS
# ได้ตรงแทนสำเนา hardcode (aimlink.AIM_GUN_WEAPONS/AIM_GUN_DRILLS หลุดซิงก์ตอนเพิ่ม Ghost/Classic) ; gunplay.selftest
# เช็คว่า DRILL_ORDER ตรง GUN_DRILLS
DRILL_ORDER = ("duel", "hold", "quick", "repo", "angle", "peek", "tap", "adad")
# ดริลชุดสมจริง (2026-09-24 lane C5 — DESIGN §2.5, ดู gundrills.py):
#   angle = จับมุมประตู/กล่อง 2–4 ขอบ บอทโผล่จากขอบ (มีแรงค์) · peek = เราโผล่จากหลังกำแพงไปหาบอทที่เฝ้ามุม (มีแรงค์)
#   tap = แตะ/ชุดสั้นใส่หัวที่ 20–35 ม. (ไม่จัดแรงค์) · adad = บอทส่าย ADAD แล้วหยุดยิง (ไม่จัดแรงค์)
# ปืนที่ไม่อยู่ใน WEAPON_DRILLS = ทุกดริล (Vandal/Phantom/Sheriff ครบ 8 — Sheriff แตะ 2 นัด/วิ ที่ระยะไกลคือทักษะหลัก)
# OP HOLD (27 ม., บอทเกราะหนักโผล่ 0.45–0.85 วิ) ไม่เปิดให้ Ghost/Classic: ทั้งคู่ต้อง 2 หัว — แตะติดกันนัดที่ 2
# สเปรดโตแล้ว (Classic 0.76° / Ghost 0.65° เทียบหัวรัศมี 0.29° ที่ 27 ม. → เข้าหัว 15–20%) แตะรอให้หาย (≥0.25 วิ)
# ก็แทบไม่ทันช่วงโผล่ และ Classic นัดแรกเองเข้าหัวแค่ ~52% (0.4°) = ดริลวัดดวง ไม่ใช่วินัยจับมุม ; ระยะคิลจริงของ
# ปืนสั้นเกิน 27 ม. แค่ 8–11% (gunplay.DUEL_DIST_Q) — เหตุผลเดียวกันจึงไม่มี TAP (20–35 ม.) ให้ปืนสั้นสองกระบอกนี้
# Op: ไม่มี TAP (นัดเดียวจบ ไม่มีเรื่องแตะ/สเปรดสะสม) และไม่มี ADAD (ดริลวัด "ยิงตอนบอทหยุด" ของปืนที่ต้องยิงหลายนัด)
WEAPON_DRILLS = {"operator": ("duel", "hold", "quick", "repo", "angle", "peek"),
                 "ghost": ("duel", "quick", "repo", "angle", "peek", "adad"),
                 "classic": ("duel", "quick", "repo", "angle", "peek", "adad")}


def weapon_drills(weapon):
    """id ดริลที่ปืนนี้เล่นได้ ตามลำดับ DRILL_ORDER (pure python — server ใช้ตัวนี้ ; เกมใช้ gunplay.drills_for)"""
    allowed = WEAPON_DRILLS.get(weapon)
    return [d for d in DRILL_ORDER if allowed is None or d in allowed]


def dmg_label(v):
    """ดาเมจที่โชว์ผู้เล่น (ป้ายลอย/ตาราง) — ปัดลงเป็นจำนวนเต็มแบบ wiki/ในเกม (22.1 → 22, 87.5 → 87)"""
    return str(int(v))

def damage_for(weapon, zone, dist_m):
    """ดาเมจ 1 นัดของปืน ที่ส่วนร่างกาย ('head'/'body'/'leg') ระยะ dist_m — เกินช่วงสุดท้ายใช้ช่วงสุดท้าย"""
    bands = WEAPONS[weapon]["dmg"]
    row = bands[-1]
    for b in bands:
        if dist_m <= b[0]:
            row = b
            break
    return row[{"head": 1, "body": 2, "leg": 3}[zone]]

def shots_to_kill(weapon, zone, dist_m, hp=PLAYER_HP, shield=PLAYER_SHIELD):
    """จำนวนนัดที่ต้องใช้ฆ่าเป้า hp+shield ด้วยส่วนร่างกายเดิมทุกนัด (ไว้เทียบกับตารางเกม)"""
    n = 0
    while hp > 0 and n < 50:
        hp, shield = apply_damage(hp, shield, damage_for(weapon, zone, dist_m))
        n += 1
    return n

def apply_damage(hp, shield, dmg):
    """กติกาเกราะ Valorant: เกราะรับ 66% ของนัดนั้น (ไม่เกินเกราะที่เหลือ) ที่เหลือเข้า HP — คืน (hp, shield)
    ปัดที่ 1e-6: ดาเมจรวมพอดี 150 (Ghost 5 ตัว = 5×30, Ghost ไกล 6×25, Sheriff ไกล 3×50) ต้องตายแน่นอน —
    ทศนิยมลอยตัวของ 0.66 เคยเหลือ HP ±7e-15 แล้วแต่ลำดับนัด (ตายบ้างไม่ตายบ้าง)"""
    to_shield = min(shield, dmg * SHIELD_ABSORB)
    return round(hp - (dmg - to_shield), 6), round(shield - to_shield, 6)


# ───────────────────────── ความแม่นขณะเคลื่อนที่ ─────────────────────────
WALK_KNEE = 0.55            # สัดส่วนความเร็วที่โทษเริ่มไต่จากระดับเดินไประดับวิ่ง (error_move ในไฟล์เกม: 0.55→0.58)

def deadzone(weapon):
    """สัดส่วนของความเร็ววิ่งของปืน ที่ความเร็วต่ำกว่านี้ = แม่นเต็มที่ (27.5% ทุกปืน, Op 15%)"""
    return WEAPONS[weapon].get("deadzone", MOVE_DEADZONE)

def is_accurate(weapon, speed):
    """ความเร็ว (m/s) นี้อยู่ใน deadzone ไหม (ยิงแล้วไม่มีโทษเคลื่อนที่)"""
    return speed <= deadzone(weapon) * WEAPONS[weapon]["run_speed"] + 1e-9

_SHAPES = {}

def _move_shape(weapon):
    """รูปเส้นโค้ง error_move ของปืนจากไฟล์เกม → [(สัดส่วนความเร็ว, u)] ; u 0 = แม่น, 1 = โทษเดิน, 2 = โทษวิ่ง
    dump เป็นยุค beta (deadzone 30%) → เลื่อน "ขั้น" ของ deadzone (คีย์ศูนย์ตัวสุดท้าย + คีย์แรกที่ไม่ศูนย์) มาที่ deadzone
    ปัจจุบัน ส่วนช่วงเดิน→วิ่ง (0.55→0.58) คงตามไฟล์ ; ปืนที่เส้นโค้งเป็นทางลาดจากศูนย์ (Sheriff/Ghost ยุค beta —
    ก่อน patch 3.0 ให้ทุกปืนมี deadzone + โทษเดิน/วิ่งแยกระดับ) ใช้รูปมาตรฐานใน _defaults แทน
    ขนาดโทษ (องศา) ไม่เอาจากไฟล์ (beta 2.1/4.2) — ใช้ wiki ปัจจุบันใน WEAPONS[...]["spread"] walk/run"""
    if weapon in _SHAPES:
        return _SHAPES[weapon]
    keys = ((RIOT.get(weapon) or {}).get("stability") or {}).get("error_move")
    # ทางลาดจากศูนย์ = ไม่มี deadzone (คีย์แรกต้องเป็น "ศูนย์ที่ความเร็ว > 0") — Sheriff เริ่ม 0.25,
    # Ghost เริ่ม (0, 0) แล้วลาดขึ้น → ทั้งคู่ใช้รูปมาตรฐาน
    if not keys or keys[0][1] != 0.0 or keys[0][0] <= 0.0:
        keys = RIOT["_defaults"]["stability"]["error_move"]
    nz = next(i for i, (_, v) in enumerate(keys) if v > 0.0)
    walk_v, run_v = keys[nz][1], max(v for _, v in keys)
    shift = deadzone(weapon) - keys[nz - 1][0]
    out = []
    for i, (x, v) in enumerate(keys):
        if i in (nz - 1, nz):
            x += shift
        u = v / walk_v if v <= walk_v else 1.0 + (v - walk_v) / max(1e-9, run_v - walk_v)
        out.append((x, u))
    _SHAPES[weapon] = out
    return out

def move_error_deg(weapon, speed, crouch=False, alt=False):
    """โทษความแม่นจากการเคลื่อนที่ (องศา บวกเข้ากรวยสเปรด) — 0 ใน deadzone
    หมอบเดินใช้โทษเฉพาะของหมอบ (Vandal +0.8°, Sheriff +0.5°) ไม่ใช่โทษเดิน +3° แบบเดิม
    alt=True: ตารางโทษของโหมดยิงรอง (Classic คลิกขวา เดิน +0.6 วิ่ง +1.5 หมอบเดิน +0) รูปเส้นโค้งเดียวกัน"""
    w = WEAPONS[weapon]
    frac = speed / w["run_speed"]
    if frac <= deadzone(weapon) + 1e-9:
        return 0.0
    sp = w["alt"]["spread"] if alt else w["spread"]
    if crouch:
        return sp.get("crouch_move", sp["walk"])
    shape = _move_shape(weapon)
    u = shape[-1][1] if frac >= shape[-1][0] else shape[0][1]
    for (x0, u0), (x1, u1) in zip(shape, shape[1:]):
        if x0 <= frac <= x1:
            u = u0 if x1 == x0 else u0 + (u1 - u0) * (frac - x0) / (x1 - x0)
            break
    if u <= 1.0:
        return sp["walk"] * u
    return sp["walk"] + (sp["run"] - sp["walk"]) * (u - 1.0)

def move_state(speed, run_speed, dz=MOVE_DEADZONE):
    """'stand' / 'walk' / 'run' จากความเร็ว (ใช้กับบอท/ป้าย) — แม่นใต้ deadzone 27.5%, เกิน 55% = ระดับวิ่ง"""
    if speed <= dz * run_speed + 1e-9:
        return "stand"
    if speed <= WALK_KNEE * run_speed:
        return "walk"
    return "run"


# ───────────────────────── สเปรด ─────────────────────────
def spread_deg(weapon, zoom, speed, crouch, heat=0.0, firing_err=None):
    """สเปรดกรวย (องศา) ของนัดถัดไป
    zoom: 1.0 = hipfire, >1 = ADS/สโคป
    firing_err: สเปรดจากการยิง (first bullet + ยิงติดกัน) ที่คำนวณจากตาราง Riot แล้ว (aim/stability.py)
                — ถ้าส่งมา ใช้แทนตาราง spread/heat ของไฟล์นี้ทั้งหมด เหลือแค่บวก error จากการเคลื่อนที่
    heat: (legacy) สเปรดสะสมจาก GunHeat — ใช้เมื่อไม่มี firing_err"""
    w = WEAPONS[weapon]
    sp = w["spread"]
    mv = move_error_deg(weapon, speed, crouch)
    if firing_err is not None:
        return firing_err + mv
    if w["kind"] == "sniper":
        if zoom > 1.0:
            base = w["scoped_spread"]
        else:
            base = sp["crouch"] if crouch else sp["stand"]
        return base + mv
    if zoom > 1.0 and w.get("ads_spread") is not None:
        base = w["ads_spread"] * (0.85 if crouch else 1.0)
        cap = sp["max"] * 0.63
    else:
        base = sp["crouch"] if crouch else sp["stand"]
        cap = sp["max"]
    return min(cap, base + heat) + mv

class GunHeat:
    """สเปรดสะสมจากการยิงติดกัน — โตนัดละ growth, คลายลงเป็นศูนย์ภายใน recover วิหลังนัดสุดท้าย"""
    def __init__(self, weapon):
        self.w = WEAPONS[weapon]
        self.heat = 0.0
        self.last_shot = -9.0

    def on_shot(self, t):
        # ปืนที่เพิ่มหลังเลิกใช้โมเดลนี้ (Ghost/Classic) ไม่มีคีย์ legacy — heat คงศูนย์
        if t - self.last_shot > self.w.get("recover", 0.3):
            self.heat = 0.0
        self.heat = min(self.w["spread"]["max"], self.heat + self.w.get("growth", 0.0))
        self.last_shot = t

    def value(self, t):
        dt = t - self.last_shot
        rec = self.w.get("recover", 0.3)
        if dt >= rec:
            return 0.0
        return self.heat * (1.0 - dt / rec)

def kick_for(weapon, burst_idx, ads, crouch, spray_table, spray_kick_fn):
    """รีคอยล์กล้องของนัดที่ burst_idx (0 = นัดแรกของชุด) -> (d_pitch, d_yaw) องศา
    ไรเฟิล: ใช้ pattern ของโหมด SPRAY (spray_kick_fn(idx, spray_table[key])) — ADS ลด 25%, ย่อลด 15%
    ปืนอื่น: เด้งคงที่ + ส่วนเพิ่มตามนัดในชุด"""
    k = WEAPONS[weapon].get("kick") or {}
    if "spray" in k:
        dp, dy = spray_kick_fn(burst_idx, spray_table[k["spray"]])
    else:
        dp = k.get("pitch", 0.0) + k.get("pitch_per_shot", 0.0) * min(burst_idx, 3)
        dy = random.uniform(-k.get("yaw", 0.0), k.get("yaw", 0.0))
    scale = (0.75 if ads else 1.0) * (0.85 if crouch else 1.0)
    return dp * scale, dy * scale

def sample_dir(spread_deg_):
    """สุ่มทิศกระสุนใน cam-space จากกรวยสเปรด (องศา) — None = ตรงกลางเป๊ะ
    ตัวสุ่มเดียวทั้งโปรเจกต์ = Stability.shot_dir (กระจายสม่ำเสมอบนพื้นที่กรวย) — เดิมสุ่มมุมแบบ uniform
    กระสุนกองกลางกรวย (ครึ่งรัศมีได้ 50% แทน 25%)"""
    if spread_deg_ <= 0:
        return None
    return Stability.shot_dir(0.0, 0.0, spread_deg_)

def zoom_sens_mult(zoom, scoped_mult=1.0):
    """ตัวคูณ sens ตอนซูม — สเกลตาม focal length (เหมือน Scoped Sensitivity Multiplier = 1.0 ของเกม)"""
    return (scoped_mult / zoom) if zoom > 1.0 else 1.0


# ───────────────────────── บอทหุ่นคน ─────────────────────────
HEAD_R = 0.14                   # รัศมีหัว (ม.)
HEAD_Y = 1.60                   # จุดศูนย์กลางหัวจากพื้น
BODY_Y0, BODY_Y1, BODY_HW = 0.90, 1.46, 0.22   # ลำตัว: ช่วงสูง + ครึ่งความกว้าง
LEG_Y0, LEG_Y1, LEG_HW = 0.0, 0.90, 0.17
BOT_H = HEAD_Y + HEAD_R
# หมอบ: ตัวทั้งท่อนบนลดลง CROUCH_DROP (ค่าเดียวกับที่กล้องผู้เล่นลดตอนกด CTRL ใน GUNFIGHT — ไม่มีตัวเลขทางการ
# ของความสูงหมอบ) ขาหดเหลือ LEG_Y1 − DROP ; ใช้เวลา CROUCH_TIME วิ ลง/ขึ้น (ประมาณจากคลิป — ไม่ใช่ค่าจากไฟล์เกม)
CROUCH_DROP = 0.55
CROUCH_TIME = 0.12

def _ray_point_dist(p, d):
    """ระยะจากจุด p (cam-space) ถึงรังสีจาก origin ทิศ d (unit) — inf ถ้าอยู่หลังกล้อง"""
    t = p[0] * d[0] + p[1] * d[1] + p[2] * d[2]
    if t <= 0:
        return float("inf")
    cx, cy, cz = p[0] - d[0] * t, p[1] - d[1] * t, p[2] - d[2] * t
    return math.sqrt(cx * cx + cy * cy + cz * cz)

def _ray_seg_dist(a, b, d):
    """ระยะสั้นสุดระหว่างรังสี (origin, d) กับส่วนของเส้น a-b (cam-space)"""
    # ตามสูตร closest points ของสองเส้น แล้ว clamp พารามิเตอร์ของ segment ใน [0,1], ของรังสี ≥ 0
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    uu = ux * ux + uy * uy + uz * uz
    ud = ux * d[0] + uy * d[1] + uz * d[2]
    ad = a[0] * d[0] + a[1] * d[1] + a[2] * d[2]
    au = a[0] * ux + a[1] * uy + a[2] * uz
    den = uu - ud * ud
    if den < 1e-9:
        s = 0.0
    else:
        s = (ud * ad - au) / den
        s = max(0.0, min(1.0, s))
    t = ad + s * ud
    if t < 0:
        t = 0.0
    px, py, pz = a[0] + ux * s - d[0] * t, a[1] + uy * s - d[1] * t, a[2] + uz * s - d[2] * t
    return math.sqrt(px * px + py * py + pz * pz)

def _ray_cyl_hit(a, b, d, r):
    """รังสีจาก origin ทิศ d (unit, cam-space) โดนทรงกระบอก "ปลายตัด" แกน a→b รัศมี r ไหม
    (ต่างจากแคปซูลตรงที่ไม่มีโดมครึ่งทรงกลมยื่นเกินปลาย — ลำตัวบอทบนสุดแบนที่ BODY_Y1 = ใต้คางพอดี)"""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    L = math.sqrt(ux * ux + uy * uy + uz * uz)
    if L < 1e-9:
        return False
    ux, uy, uz = ux / L, uy / L, uz / L
    wx, wy, wz = -a[0], -a[1], -a[2]                       # origin เทียบจุด a
    du = d[0] * ux + d[1] * uy + d[2] * uz
    wu = wx * ux + wy * uy + wz * uz
    px, py, pz = d[0] - du * ux, d[1] - du * uy, d[2] - du * uz   # ส่วนตั้งฉากแกน
    qx, qy, qz = wx - wu * ux, wy - wu * uy, wz - wu * uz
    A = px * px + py * py + pz * pz
    B = px * qx + py * qy + pz * qz
    C = qx * qx + qy * qy + qz * qz - r * r
    if A < 1e-12:                                          # ขนานแกน: อยู่ในรัศมีตลอดหรือไม่เลย
        if C > 0:
            return False
        return (wu <= L) if du > 0 else (wu >= 0) if du < 0 else (0 <= wu <= L)
    disc = B * B - A * C
    if disc < 0:
        return False
    sq = math.sqrt(disc)
    t0, t1 = (-B - sq) / A, (-B + sq) / A
    if t1 < 0:
        return False
    t0 = max(t0, 0.0)
    h0, h1 = wu + t0 * du, wu + t1 * du                    # ความสูงตามแกนตอนเข้า/ออกทรงกระบอกไม่จำกัด
    return max(h0, h1) >= 0.0 and min(h0, h1) <= L

def humanoid_zone(o, d, x, z, crouch=0.0):
    """รังสีจาก o ทิศ d (world, หน่วย) โดนหุ่นคนที่ยืนที่ (x, z) ท่า crouch (0 ยืน → 1 หมอบ) ส่วนไหน
    → (zone, t) ; zone = 'head'/'body'/'leg'/None, t = ระยะตามรังสีถึงแกนของส่วนนั้น (เทียบกับที่กำบัง)
    เรขาคณิตเดียวกับ Bot.hit_zone ทุกประการ (หัวทรงกลม → ลำตัวทรงกระบอกปลายตัด → ขา) แต่คิดในพิกัดโลก — ใช้กับ
    กระสุนบอทที่ยิง "ผู้เล่น" (ผู้เล่นยืนบนพื้น ตา EYE 1.65 = ศูนย์หัว 1.60 + 0.05 ; หมอบลด CROUCH_DROP เท่ากัน)"""
    drop = CROUCH_DROP * crouch
    ox, oy, oz = o
    rx, rz = x - ox, z - oz

    def along(p):
        return p[0] * d[0] + p[1] * d[1] + p[2] * d[2]
    head = (rx, HEAD_Y - drop - oy, rz)
    if _ray_point_dist(head, d) <= HEAD_R:
        return "head", along(head)
    b0 = (rx, BODY_Y0 - drop - oy, rz)
    b1 = (rx, BODY_Y1 - drop - oy, rz)
    if _ray_cyl_hit(b0, b1, d, BODY_HW):
        return "body", along(((b0[0] + b1[0]) / 2, (b0[1] + b1[1]) / 2, (b0[2] + b1[2]) / 2))
    l0 = (rx, LEG_Y0 - oy, rz)
    l1 = (rx, LEG_Y1 - drop - oy, rz)
    if _ray_seg_dist(l0, l1, d) <= LEG_HW:
        return "leg", along(((l0[0] + l1[0]) / 2, (l0[1] + l1[1]) / 2, (l0[2] + l1[2]) / 2))
    return None, None


def humanoid_points(x, z, crouch=0.0, y0=0.0):
    """จุดตัวอย่างบนหุ่น (ศูนย์หัว, ข้างหัว, ไหล่สองข้าง, อก, สะโพก) — "เห็นกัน" ถ้าแนวสายตาถึงจุดใดจุดหนึ่งไม่ผ่านที่กำบัง
    ไหล่คือขอบลำตัว ±BODY_HW = ส่วนที่โผล่พ้นมุมก่อนหัว (เห็นไหล่ก่อนเห็นหัวแบบในเกม) ; 3 จุดแรก = หัว (head_points)
    y0 = ความสูงพื้นที่ยืน (บอทบนยกพื้น/ledge ของดริล ANGLE — 0 = พื้นห้อง)"""
    drop = CROUCH_DROP * crouch - y0
    hy, sy = HEAD_Y - drop, BODY_Y1 - 0.06 - drop
    return [(x, hy, z), (x - HEAD_R, hy, z), (x + HEAD_R, hy, z),
            (x - BODY_HW, sy, z), (x + BODY_HW, sy, z),
            (x, (BODY_Y0 + BODY_Y1) / 2 - drop, z), (x, BODY_Y0 - drop, z)]


def head_points(x, z, crouch=0.0, y0=0.0):
    """เฉพาะจุดบนหัว (ศูนย์ + ข้างซ้าย/ขวา) — "หัวพ้นขอบแล้ว" (ดริล PEEK เริ่มนาฬิกาบอทเมื่อหัวเราพ้นขอบ,
    ANGLE วัดองศาคลาดตอนหัวบอทโผล่, REACTION·PEEK เริ่มจับเวลาเมื่อหัวโผล่)"""
    return humanoid_points(x, z, crouch, y0)[:3]


class Bot:
    """หุ่นยืน (x, z) บนพื้น หันหน้าหากล้องเสมอ — hitbox: หัวทรงกลม, ลำตัวทรงกระบอกปลายตัด, ขาแคปซูลตั้ง
    crouch 0..1 = ท่าหมอบ (0 ยืน, 1 หมอบสุด) — hitbox/ภาพใช้ head_y()/body_y0()/body_y1()/leg_y1() ตามท่า
    บอท v2 (gunbots): vel = [vx, vz] เดินด้วยฟิสิกส์เดียวกับผู้เล่น (movement.step), weapon/stab = ปืนของบอท
    (สเปรด/รีคอยล์ Stability + โทษเคลื่อนที่ move_error_deg แบบเดียวกับที่ผู้เล่นโดน)"""
    def __init__(self, x, z, hp=PLAYER_HP, shield=PLAYER_SHIELD):
        self.x, self.z = x, z
        self.hp, self.shield = hp, shield
        self.alive = True
        self.vel = [0.0, 0.0]        # ความเร็ว (ม./วิ) แกน x, z — บอท v2 (movement.step)
        self.weapon = None           # ปืนของบอท (None = บอท OP HOLD แบบเดิมที่ไม่ยิงผ่าน gun_bot_fire)
        self.stab = None
        self.vx = 0.0                # ความเร็วด้านข้าง (ม./วิ) — peek/strafe
        self.born = 0.0              # เวลาที่เริ่มเปิดตัวให้ยิงได้ (gt)
        self.exposed = True          # โผล่พ้นที่กำบังไหม (hold drill)
        self.state = "stand"         # stand / peek / jiggle / swing / retreat / hidden
        self.next_fire = None        # เวลา (gt) ที่บอทจะยิงสวน
        self.damage_taken = []       # (zone, dmg)
        self.x0 = x                  # จุดเริ่ม (ใช้กับ retreat)
        self.crouch = 0.0            # ท่าตอนนี้ (0 ยืน → 1 หมอบ) เลื่อนหา crouch_to ด้วยความเร็ว 1/CROUCH_TIME
        self.crouch_to = 0.0
        self.y0 = 0.0                # ความสูงพื้นที่ยืน (ม.) — ยกพื้น/ledge ของดริล ANGLE ; 0 = พื้นห้อง (ทุกดริลเดิม)
        self.meta = {}

    @property
    def pos(self):
        return [self.x, 0.0, self.z]

    def dist(self, cam):
        return math.hypot(self.x - cam.pos[0], self.z - cam.pos[2])

    def speed(self):
        return math.hypot(self.vel[0], self.vel[1])

    def eye(self):
        """ตำแหน่งตา/ปากกระบอกของบอท (ศูนย์หัว + 0.05 เท่าผู้เล่น)"""
        return (self.x, self.head_y() + (EYE_Y - HEAD_Y), self.z)

    def points(self):
        return humanoid_points(self.x, self.z, self.crouch, self.y0)

    def head_points(self):
        return head_points(self.x, self.z, self.crouch, self.y0)

    # ── ความสูงตามท่า (ม.) — รวมความสูงพื้นที่ยืน y0 (ยกพื้น) ──
    def drop(self):
        return CROUCH_DROP * self.crouch - self.y0

    def head_y(self):
        return HEAD_Y - self.drop()

    def body_y0(self):
        return BODY_Y0 - self.drop()

    def body_y1(self):
        return BODY_Y1 - self.drop()

    def leg_y0(self):
        return LEG_Y0 + self.y0

    def leg_y1(self):
        return LEG_Y1 - self.drop()

    def update_crouch(self, dt):
        """เลื่อนท่าไปหา crouch_to — ลง/ขึ้นเต็มช่วงใน CROUCH_TIME วิ"""
        if self.crouch != self.crouch_to:
            step = dt / CROUCH_TIME
            self.crouch = (min(self.crouch_to, self.crouch + step) if self.crouch_to > self.crouch
                           else max(self.crouch_to, self.crouch - step))

    def hit_zone(self, cam, shot_dir=None):
        """ส่วนที่กระสุนโดน: 'head' / 'body' / 'leg' / None — เช็คหัวก่อน (หัวยื่นพ้นไหล่)"""
        d = shot_dir or (0.0, 0.0, 1.0)
        head = cam.to_cam((self.x, self.head_y(), self.z))
        if _ray_point_dist(head, d) <= HEAD_R:
            return "head"
        b0 = cam.to_cam((self.x, self.body_y0(), self.z)); b1 = cam.to_cam((self.x, self.body_y1(), self.z))
        # ลำตัวปลายตัด (ตรงกับสี่เหลี่ยมที่วาด hip→chest) — เดิมเป็นแคปซูล โดมบนสูงถึง 1.46+0.22 = 1.68 ม.
        # เหนือศูนย์กลางหัว (1.60) → นัดเฉียดข้างหัว 0.15 ม. ที่ระดับหัวนับเป็น body 40 ดาเมจแทนที่จะพลาด
        if _ray_cyl_hit(b0, b1, d, BODY_HW):
            return "body"
        l0 = cam.to_cam((self.x, self.leg_y0(), self.z)); l1 = cam.to_cam((self.x, self.leg_y1(), self.z))
        if _ray_seg_dist(l0, l1, d) <= LEG_HW:
            return "leg"
        return None

    def take(self, dmg, zone):
        self.hp, self.shield = apply_damage(self.hp, self.shield, dmg)
        self.damage_taken.append((zone, dmg))
        if self.hp <= 0:
            self.alive = False
        return not self.alive

    def hp_frac(self):
        return max(0.0, self.hp / PLAYER_HP), max(0.0, self.shield / PLAYER_SHIELD)
