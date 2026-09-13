# -*- coding: utf-8 -*-
"""แกนอาวุธจริง (pure python — ไม่มี pygame) : ตารางปืนตามค่าจริงของ Valorant + บอทหุ่นคน + ดาเมจ/เกราะ

ที่มาตัวเลข: wiki.playvalorant.com (ทางการ) ณ patch 12.x ก.ย. 2026 —
  Operator  255/150/120 0-50m · 0.6 rps · mag 5 · reload 3.7 · scope 2.5x/5x · hipfire 5° (crouch 4.5°) scoped 0°
            เดินขณะสโคป +10° วิ่ง +15° · เคลื่อนที่เกิน ~15% ของความเร็ววิ่ง = ไม่แม่นทันที
  Vandal    160/40/34 0-50m · 9.75 rps (ADS 90%) · mag 25 · first-shot 0.25° (crouch 0.21) max 1.0° · ADS 1.25x 0.157°
  Phantom   156/39/33 0-20m, 140/35/29 20-50m · 11 rps (ADS 90%) · mag 30 · 0.2°/0.17 max 0.9° · ADS 1.25x 0.11°
  Sheriff   159/55/46 0-30m, 145/50/42 30-50m · 4 rps · mag 6 · 0.25°/0.19 max 2.75° · เดิน +1.2 วิ่ง +3
เกราะ: heavy shield 50 รับ 66% ของดาเมจแต่ละนัด (ที่เหลือเข้า HP 100) — Vandal 4 นัดตัว/1 หัว, Sheriff 3 ตัว,
Op 1 ตัว / 2 ขา ตรงเกมทุกกรณี (ดู selftest)
"""
import math
import random

RUN_SPEED = 5.4            # m/s (ปืนหลักทุกกระบอกยกเว้น Op 5.13)
PLAYER_HP, PLAYER_SHIELD = 100, 50
SHIELD_ABSORB = 0.66       # เกราะหนักรับ 66% ของดาเมจนัดนั้น

# (ระยะสูงสุดของช่วง (ม.), หัว, ตัว, ขา)
WEAPONS = {
    "operator": {
        "name": "OPERATOR", "kind": "sniper", "auto": False, "rps": 0.6, "mag": 5, "reload": 3.7,
        "run_speed": 5.13, "equip": 1.5,
        "dmg": [(50, 255, 150, 120)],
        # hipfire: ฐาน (ยืน/ย่อ) + ส่วนเพิ่มตามการเคลื่อนที่ (องศา)
        "spread": {"stand": 5.0, "crouch": 4.5, "max": 5.0, "walk": 10.0, "run": 15.0},
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
        "spread": {"stand": 0.25, "crouch": 0.21, "max": 1.0, "walk": 3.0, "run": 6.0},
        "zooms": [1.25], "ads_rps": 0.9, "ads_spread": 0.157, "ads_move": 0.76,
        "unscope_on_shot": False,
        "growth": 0.16, "recover": 0.42,                 # (legacy — ดูหมายเหตุที่ operator)
        "kick": {"spray": "vandal", "recover": 7.0},
    },
    "phantom": {
        "name": "PHANTOM", "kind": "rifle", "auto": True, "rps": 11.0, "mag": 30, "reload": 2.5,
        "run_speed": 5.4, "equip": 1.0,
        "dmg": [(20, 156, 39, 33), (50, 140, 35, 29)],
        "spread": {"stand": 0.2, "crouch": 0.17, "max": 0.9, "walk": 3.0, "run": 6.0},
        "zooms": [1.25], "ads_rps": 0.9, "ads_spread": 0.11, "ads_move": 0.76,
        "unscope_on_shot": False,
        "growth": 0.13, "recover": 0.40,
        "kick": {"spray": "phantom", "recover": 7.0},
    },
    "sheriff": {
        "name": "SHERIFF", "kind": "pistol", "auto": False, "rps": 4.0, "mag": 6, "reload": 2.25,
        "run_speed": 5.4, "equip": 1.0,
        "dmg": [(30, 159, 55, 46), (50, 145, 50, 42)],
        "spread": {"stand": 0.25, "crouch": 0.19, "max": 2.75, "walk": 1.2, "run": 3.0},
        "zooms": [], "unscope_on_shot": False,
        # ยิงรัว = สเปรดพุ่งเร็วมาก (recover ช้า) — นี่คือเหตุผลที่ Sheriff ต้อง "แตะ" ไม่ใช่กด
        "growth": 0.9, "recover": 0.85,
        # เด้งแรงต่อนัด และยิ่งรัวยิ่งเด้ง (นัดที่ 2-4 ในชุดเดียวกัน +0.4°/นัด) ฟื้นเร็ว
        "kick": {"pitch": 1.8, "pitch_per_shot": 0.4, "yaw": 0.35, "recover": 11.0},
    },
}
WEAPON_ORDER = ["operator", "vandal", "phantom", "sheriff"]

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
    """กติกาเกราะ Valorant: เกราะรับ 66% ของนัดนั้น (ไม่เกินเกราะที่เหลือ) ที่เหลือเข้า HP — คืน (hp, shield)"""
    to_shield = min(shield, dmg * SHIELD_ABSORB)
    return hp - (dmg - to_shield), shield - to_shield


# ───────────────────────── สเปรด ─────────────────────────
def move_state(speed, run_speed):
    """'stand' / 'walk' / 'run' จากความเร็วปัจจุบัน — Valorant เริ่มไม่แม่นตั้งแต่ ~15% ของความเร็ววิ่ง"""
    if speed <= 0.15 * run_speed:
        return "stand"
    if speed <= 0.55 * run_speed:
        return "walk"
    return "run"

def spread_deg(weapon, zoom, speed, crouch, heat=0.0, firing_err=None):
    """สเปรดกรวย (องศา) ของนัดถัดไป
    zoom: 1.0 = hipfire, >1 = ADS/สโคป
    firing_err: สเปรดจากการยิง (first bullet + ยิงติดกัน) ที่คำนวณจากตาราง Riot แล้ว (aim/stability.py)
                — ถ้าส่งมา ใช้แทนตาราง spread/heat ของไฟล์นี้ทั้งหมด เหลือแค่บวก error จากการเดิน/วิ่ง
    heat: (legacy) สเปรดสะสมจาก GunHeat — ใช้เมื่อไม่มี firing_err"""
    w = WEAPONS[weapon]
    sp = w["spread"]
    st = move_state(speed, w["run_speed"])
    if firing_err is not None:
        base = firing_err
        if st == "walk":
            base += sp["walk"]
        elif st == "run":
            base += sp["run"]
        return base
    if w["kind"] == "sniper":
        if zoom > 1.0:
            base = w["scoped_spread"]
        else:
            base = sp["crouch"] if crouch else sp["stand"]
        if st == "walk":
            base += sp["walk"]
        elif st == "run":
            base += sp["run"]
        return base
    if zoom > 1.0 and w.get("ads_spread") is not None:
        base = w["ads_spread"] * (0.85 if crouch else 1.0)
        cap = sp["max"] * 0.63
    else:
        base = sp["crouch"] if crouch else sp["stand"]
        cap = sp["max"]
    base = min(cap, base + heat)
    if st == "walk":
        base += sp["walk"]
    elif st == "run":
        base += sp["run"]
    return base

class GunHeat:
    """สเปรดสะสมจากการยิงติดกัน — โตนัดละ growth, คลายลงเป็นศูนย์ภายใน recover วิหลังนัดสุดท้าย"""
    def __init__(self, weapon):
        self.w = WEAPONS[weapon]
        self.heat = 0.0
        self.last_shot = -9.0

    def on_shot(self, t):
        if t - self.last_shot > self.w["recover"]:
            self.heat = 0.0
        self.heat = min(self.w["spread"]["max"], self.heat + self.w["growth"])
        self.last_shot = t

    def value(self, t):
        dt = t - self.last_shot
        rec = self.w["recover"]
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
    """สุ่มทิศกระสุนใน cam-space จากกรวยสเปรด (องศา) — None = ตรงกลางเป๊ะ"""
    if spread_deg_ <= 0:
        return None
    phi = random.uniform(0, math.radians(spread_deg_))
    th = random.uniform(0, 2 * math.pi)
    return (math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi))

def zoom_sens_mult(zoom, scoped_mult=1.0):
    """ตัวคูณ sens ตอนซูม — สเกลตาม focal length (เหมือน Scoped Sensitivity Multiplier = 1.0 ของเกม)"""
    return (scoped_mult / zoom) if zoom > 1.0 else 1.0


# ───────────────────────── บอทหุ่นคน ─────────────────────────
HEAD_R = 0.14                   # รัศมีหัว (ม.)
HEAD_Y = 1.60                   # จุดศูนย์กลางหัวจากพื้น
BODY_Y0, BODY_Y1, BODY_HW = 0.90, 1.46, 0.22   # ลำตัว: ช่วงสูง + ครึ่งความกว้าง
LEG_Y0, LEG_Y1, LEG_HW = 0.0, 0.90, 0.17
BOT_H = HEAD_Y + HEAD_R

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

class Bot:
    """หุ่นยืน (x, z) บนพื้น หันหน้าหากล้องเสมอ — hitbox: หัวทรงกลม, ลำตัว/ขาเป็นแคปซูลตั้ง"""
    def __init__(self, x, z, hp=PLAYER_HP, shield=PLAYER_SHIELD):
        self.x, self.z = x, z
        self.hp, self.shield = hp, shield
        self.alive = True
        self.vx = 0.0                # ความเร็วด้านข้าง (ม./วิ) — peek/strafe
        self.born = 0.0              # เวลาที่เริ่มเปิดตัวให้ยิงได้ (gt)
        self.exposed = True          # โผล่พ้นที่กำบังไหม (hold drill)
        self.state = "stand"         # stand / peek / jiggle / swing / retreat / hidden
        self.next_fire = None        # เวลา (gt) ที่บอทจะยิงสวน
        self.damage_taken = []       # (zone, dmg)
        self.x0 = x                  # จุดเริ่ม (ใช้กับ retreat)
        self.meta = {}

    @property
    def pos(self):
        return [self.x, 0.0, self.z]

    def dist(self, cam):
        return math.hypot(self.x - cam.pos[0], self.z - cam.pos[2])

    def hit_zone(self, cam, shot_dir=None):
        """ส่วนที่กระสุนโดน: 'head' / 'body' / 'leg' / None — เช็คหัวก่อน (หัวยื่นพ้นไหล่)"""
        d = shot_dir or (0.0, 0.0, 1.0)
        head = cam.to_cam((self.x, HEAD_Y, self.z))
        if _ray_point_dist(head, d) <= HEAD_R:
            return "head"
        b0 = cam.to_cam((self.x, BODY_Y0, self.z)); b1 = cam.to_cam((self.x, BODY_Y1, self.z))
        if _ray_seg_dist(b0, b1, d) <= BODY_HW:
            return "body"
        l0 = cam.to_cam((self.x, LEG_Y0, self.z)); l1 = cam.to_cam((self.x, LEG_Y1, self.z))
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
