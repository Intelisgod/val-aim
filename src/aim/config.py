# -*- coding: utf-8 -*-
"""ค่าคงที่ทั้งหมด (สี/โหมด/แรงค์/สเกล/FOV/EYE/WALL ...) — ย้ายจาก aim_trainer.py เดิม"""

import math

VAL_DEG_PER_COUNT = 0.07     # Valorant yaw = 0.07 องศา/count (ยืนยันจาก KovaaK SensitivityMatcher)
HFOV_DEG = 103.0             # FOV แนวนอนของ Valorant ที่จอ 16:9
# Valorant ล็อก FOV "แนวตั้ง" (~70.53°) แล้วขยายแนวนอนตามสัดส่วนจอ
# ทำแบบเดียวกันเพื่อให้ภาพ/ความรู้สึก sens ตรงเกมจริงในทุกขนาดหน้าต่าง
C_BG, C_DARKER = (15, 25, 35), (8, 20, 28)
C_SKY, C_SKY_TOP = (26, 46, 66), (14, 26, 38)
C_FLOOR, C_GRID = (30, 48, 72), (31, 49, 64)
C_WALL, C_SIDEWALL = (42, 63, 85), (36, 54, 74)
C_RED = (255, 70, 85)
C_TEXT, C_DIM = (236, 232, 225), (127, 155, 181)
C_GOLD, C_GREEN = (212, 175, 55), (60, 179, 113)
C_PANEL, C_BORDER = (26, 38, 52), (31, 49, 64)
C_PALE_GOLD = (255, 239, 176)

MODES = [
    ("flick",     "FLICK",     "เป้าโผล่ทีละจุด ฝึก flick shot"),
    ("precision", "PRECISION", "เป้าเล็ก ระยะไกล ฝึกความแม่นยำ"),
    ("tracking",  "TRACKING",  "เป้าวิ่งซ้าย-ขวา ฝึก tracking"),
    ("reaction",  "REACTION",  "5 เป้า สุ่มเวลา วัด reaction time"),
    ("strafe",    "STRAFE",    "WASD เดิน หยุดยิง ฝึก counter-strafe"),
    ("gun",       "GUNFIGHT",  "ปืนจริง Op/Vandal/Phantom/Sheriff ดาเมจ-สเปรด-สโคปตามเกม"),
    ("spray",     "SPRAY",     "กดยิงค้าง คุมรีคอยล์ Vandal/Phantom"),
    ("dodge",     "DODGE",     "หลบสกิล+เดินหลบ พร้อมเล็งยิงหัว"),
    ("placement", "PLACEMENT", "พรีเอม เล็งระดับหัว วัดองศาคลาด"),
    ("switch",    "SWITCH",    "เคลียร์หลายเป้าไว วัด switch time"),
]
MODE_NAME = {m[0]: m[1] for m in MODES}
# โหมดเก่าที่ถอดจากกริดเมนูแล้ว (11 ก.ย. 2026: SNIPER OP ลูกบอลวิ่งผ่านประตู → แทนด้วย GUNFIGHT/OP HOLD)
# ยังรันได้ผ่าน --mode sniper และประวัติ/insight เดิมยังอ่านชื่อได้
LEGACY_MODES = [("sniper", "SNIPER OP", "เป้าวิ่งผ่านประตู ฝึก scope hold")]
MODE_NAME.update({m[0]: m[1] for m in LEGACY_MODES})
SIZES = {"small": 0.18, "medium": 0.32, "large": 0.55}
# contract ข้ามโปรเจกต์: valorant_server.py (launch_aim_trainer) hardcode สำเนาค่าสองตัวนี้
# ไว้ validate --duration/--size — แก้ค่าที่นี่ต้องแก้ฝั่งนั้นด้วย ไม่งั้น deep-link จะทิ้งค่า
# ใหม่เงียบๆ (fail-open) แล้ว session หลุด config อ้างอิงแบบไม่มี error ให้เห็น
SIZE_TH = {"small": "เล็ก", "medium": "กลาง", "large": "ใหญ่"}
DURATIONS = [15, 30, 60]

RANKS = [
    (0, 'Iron I', '#5C5C5C'), (750, 'Iron II', '#5C5C5C'), (1450, 'Iron III', '#5C5C5C'),
    (2150, 'Bronze I', '#9C6B3C'), (2750, 'Bronze II', '#9C6B3C'), (3350, 'Bronze III', '#9C6B3C'),
    (3900, 'Silver I', '#C8C8C8'), (4750, 'Silver II', '#C8C8C8'), (5550, 'Silver III', '#C8C8C8'),
    (6600, 'Gold I', '#D4AF37'), (7550, 'Gold II', '#D4AF37'), (8450, 'Gold III', '#D4AF37'),
    (9250, 'Platinum I', '#5DBFBA'), (10000, 'Platinum II', '#5DBFBA'), (10700, 'Platinum III', '#5DBFBA'),
    (11500, 'Diamond I', '#B97FE0'), (12300, 'Diamond II', '#B97FE0'), (13150, 'Diamond III', '#B97FE0'),
    (14150, 'Ascendant I', '#3CB371'), (15050, 'Ascendant II', '#3CB371'), (16000, 'Ascendant III', '#3CB371'),
    (17200, 'Immortal', '#B7375C'), (20000, 'Radiant', '#FFEFB0'),
]
SIZE_SCALE = {"large": 1.00, "medium": 0.85, "small": 0.60}
TIME_FACTOR = {15: 0.53, 30: 1.0}
# สเกลจูนใหม่ 2026-08-01 จากการวัดสามทาง (อย่าเดาแก้ — ดู tools/rank_ceiling_sim.py):
# (1) บอทหลายระดับฝีมือขับเกมจริง headless (2) benchmark มนุษย์จริง Voltaic/Aimlabs/HumanBenchmark
# (3) ประวัติซ้อมจริง 136 รอบเทียบแรงค์ Valorant จริงของผู้ใช้ (Diamond 1)
# เกณฑ์: Radiant ≈ 105-115% ของบอทระดับ radiant (ต้องเอื้อมถึงแต่ยากระดับโปร) และ
# PB จริงของผู้ใช้ควรตกราว Diamond (เท่า flick ที่เป็น anchor)
MODE_SCALE = {"flick": 1.0, "precision": 1.22, "reaction": 1.0, "strafe": 0.85,
              # tracking: เป้าวิ่งฆ่าช้ากว่า flick โดยธรรมชาติ แต่ขีดเดิมต้องการคิล/วิ "มากกว่า" flick
              # (3.08 vs 3.00 ที่ Radiant) → ลดจาก 0.92
              "tracking": 0.85,
              # spray: 2.15 เดิมวัดตอนยังมีบั๊ก reload-burst (ถือปุ่มค้างผ่านรีโหลดได้ ~11 นัดฟรีในเฟรมเดียว
              # = 293 นัด/30 วิ) แก้บั๊ก 2026-09-05 เหลือ 206 นัด → รัน tools/rank_ceiling_sim.py ก่อน/หลัง
              # บอททุกระดับได้คะแนน 0.63-0.72 เท่า (มัธยฐาน 0.687) → 2.15 × 0.687 = 1.48 แรงค์ที่บอทแต่ละ
              # ระดับได้จึงเท่าเดิม; ประวัติ spray ก่อนแก้ติดป้าย legacy ผ่าน SPRAY_SCORE_REV (ด้านล่าง)
              "spray": 1.48,
              # dodge: ขีดเดิมต้องการ 2.37 คิลหัว/วิ ระหว่างหลบ = เกิน world-top evasive
              # (Voltaic Celestial ~0.9-1.2 คิล/วิ) → ลดจาก 0.70; PB จริงผู้ใช้ 5,430 → Diamond II
              "dodge": 0.50,
              # placement: เพดานกลไก (บอทเหนือมนุษย์+พรีเอมเหมาะที่สุด) = ~17.0k แต่ขีด Radiant เดิม
              # 17,850 = "เป็นไปไม่ได้" ; spawn pacing จำกัดคะแนน → ลดจาก 1.05 ให้ Radiant ≈ 8,500
              # (บอทระดับ radiant ทำ ~7,800)
              "placement": 0.50,
              # switch: ขีดเดิมต้องการ switch 97ms/ตัว (เหนือมนุษย์ — world-top ~400ms) → ลดจาก 1.35
              # Radiant ใหม่ ≈ switch ~350-400ms ต่อเนื่อง = ระดับโปรพอดี
              "switch": 0.75}

REACTION_RT_RANKS = [
    (150, 'Radiant', '#FFEFB0'), (158, 'Immortal', '#B7375C'),
    (167, 'Ascendant III', '#3CB371'), (176, 'Ascendant II', '#3CB371'), (185, 'Ascendant I', '#3CB371'),
    (195, 'Diamond III', '#B97FE0'), (205, 'Diamond II', '#B97FE0'), (215, 'Diamond I', '#B97FE0'),
    (225, 'Platinum III', '#5DBFBA'), (235, 'Platinum II', '#5DBFBA'), (245, 'Platinum I', '#5DBFBA'),
    (255, 'Gold III', '#D4AF37'), (265, 'Gold II', '#D4AF37'), (275, 'Gold I', '#D4AF37'),
    (285, 'Silver III', '#C8C8C8'), (295, 'Silver II', '#C8C8C8'), (305, 'Silver I', '#C8C8C8'),
    (315, 'Bronze III', '#9C6B3C'), (325, 'Bronze II', '#9C6B3C'), (335, 'Bronze I', '#9C6B3C'),
    (342, 'Iron III', '#5C5C5C'), (350, 'Iron II', '#5C5C5C'), (float('inf'), 'Iron I', '#5C5C5C'),
]
FLICK_RT_STRETCH, FLICK_RT_OFFSET = 1.7, 5
REACTION_COUNT = 5
# ช่องไฟก่อนเป้าถัดไป (สุ่มในช่วงนี้ — เดาไม่ได้ แต่ขั้นต่ำต้องพอให้ปล่อยปุ่ม+ตั้งนิ้ว+ละสายตาจากตัวเลข ms)
# เดิม 0.5–3.5 วิ: ~15% ของเป้าโผล่ภายใน 1 วิหลังคลิก ผู้เล่นเห็นแล้วแต่นิ้วยังไม่กลับที่ → 190ms ทั้งที่ค่าปกติ 140-150
REACTION_GAP_MIN, REACTION_GAP_MAX = 1.2, 3.5
# ถ้ายังกดปุ่มค้างอยู่ตอนถึงเวลา เป้าจะรอจนปล่อยปุ่ม แล้วนับต่ออีกอย่างน้อยเท่านี้ (วิ) ค่อยโผล่
REACTION_RELEASE_GAP = 0.6

# Strafe
STRAFE_MAX_SPEED, STRAFE_ACCEL, STRAFE_FRICTION = 6.75, 150, 70
STRAFE_MIN_SPREAD_SPEED, STRAFE_MAX_SPREAD_RAD = 1.0, 0.030
STRAFE_STATIC_WARN, STRAFE_STATIC_DESPAWN = 2.0, 3.0

# Sniper
SNIPER_TOTAL, SNIPER_SPEED, SNIPER_R = 10, 6.5, 0.32
SNIPER_Y, SNIPER_Z, SNIPER_WALL_Z = 1.55, 11.0, 9.0
SNIPER_DOOR_L, SNIPER_DOOR_R, SNIPER_DOOR_H = 0.6, 2.4, 2.5

EYE_Y, WALL_Z, ROOM_X, ROOM_H = 1.65, 14.0, 10.0, 8.0
ZNEAR = 0.05   # ระนาบ near-clip ใน cam-space — software (worlddraw) กับ GPU (glrender) ต้องใช้ค่าเดียวกัน

# ── Head/Body (realism) ──
HEAD_BONUS = 50          # โบนัสคะแนนต่อ headshot ในโหมดคะแนน (flick/precision/tracking/placement/switch)
HEAD_BONUS_SPRAY = 1     # spray นับ "หัว" เป็นหน่วยแยก ไม่บวกคะแนนดิบ

# ── ประวัติซ้อม (aim_trainer_data.json → history) ──
# เดิมเพดาน 200 รอบ: ผู้ใช้ซ้อม ~27 รอบ/สัปดาห์ ถึงเพดานใน ~7 สัปดาห์ แล้ววันซ้อมเก่าหลุดทีละรอบ →
# กล่อง "ซ้อมแล้วเห็นผลไหม" บน dashboard ย้ายถังเอง (แมตช์ที่เคยนับว่าซ้อมก่อนเล่นกลายเป็นไม่ได้ซ้อม)
# ตัวหนักคือ shots (60 จุด/รอบ ≈ 1.8 KB) ซึ่งใช้แค่วาด shot map หน้า Insight — เก็บเฉพาะรอบล่าสุด
# ที่เหลือเหลือแต่จำนวนใน shots_n (dashboard ใช้แยก "รอบเปล่า" ออกจากรอบที่ยิงแล้วได้ 0)
HISTORY_MAX = 2000          # ≈ 18 เดือนที่อัตราปัจจุบัน ไฟล์ ≈ 0.8 MB (โหลด/เซฟ ≈ 10 ms)
HISTORY_SHOTS_KEEP = 200    # รอบล่าสุดที่ยังมี shots เต็ม (= เพดานเดิมทั้งก้อน)

# ── SPRAY (recoil control) ──
# รีคอยล์/สเปรดของ SPRAY และ GUNFIGHT มาจากเส้นโค้งในไฟล์เกมจริง (aim/riot_data.py ← tools/riot_dump.py)
# จำลองใน aim/stability.py: crosshair ไม่ขยับ กระสุนวิ่งตาม pattern (Vandal ไต่ถึง ~7.6° ที่นัด 8 แล้วแกว่ง
# + yaw ~2° หลังนัด 12) ผู้เล่นดึงเมาส์ลงหักล้าง — ค่าใน SPRAY_WEAPONS เหลือแค่ rps/mag/falloff ที่ยังใช้
# (v_climb/v_max/h_amp/h_settle = โมเดลเก่าก่อน 11 ก.ย. 2026 เก็บไว้ให้ spray_recoil_kick legacy อ่านได้)
# ค่าหัวเรื่องยืนยันจากเว็บ (มิ.ย. 2026): Vandal 9.75 rด/s, แม็ก 25 ; Phantom 11.0 rด/s, แม็ก 30
RECOIL_SCALE = 1.0               # ตัวคูณ pattern ทุกปืน — ปรับจากผล tools/recoil_fit.py ถ้าวัดในเกมแล้วขนาดต่างจาก dump
SPRAY_TARGET_Z = 11.0            # ระยะเป้า (เมตร)
SPRAY_RECOVER = 7.0              # (legacy) ความเร็วฟื้นรีคอยล์ของโมเดลเก่า — stability.py ใช้ RecoveryTimeCurve จากไฟล์เกมแทน
SPRAY_RELOAD = 1.2               # ดีเลย์รีโหลด (วินาที)
SPRAY_FALLOFF_Z = 9.0            # Phantom: ระยะเริ่ม damage falloff (ไม่กระทบ hit แค่บอกผู้เล่น)
# เวอร์ชันสูตรคะแนน spray — entry ใน history ที่ srev ไม่ตรง = คะแนนยุคบั๊ก reload-burst (ก่อน 2026-09-05)
# ห้ามเอามาเทียบ PB/แรงค์/leaderboard กับรอบใหม่ (PB เดิม 31,950 เอื้อมไม่ถึงในกติกาใหม่ตลอดกาล)
# แต่ยังเก็บไว้ในไฟล์ — dashboard ยังใช้วันเวลา (at) ของมันวัด "ซ้อมแล้วเห็นผลไหม" ได้
# ประวัติที่ไม่มีคีย์ srev ถือเป็นเวอร์ชัน 1
# rev 3 (2026-09-11): รีคอยล์เปลี่ยนเป็น pattern จริงจากไฟล์เกม (crosshair นิ่ง, มีสเปรด, สูงสุด ~8° ไม่ใช่ 11°)
# → ความยากคนละแบบ คะแนน rev 2 เทียบกับ rev 3 ไม่ได้
SPRAY_SCORE_REV = 3

def spray_current(e):
    """True ถ้า entry ประวัติ/leaderboard คิดคะแนนด้วยสูตร spray ปัจจุบัน (โหมดอื่นคืน True เสมอ)"""
    return e.get("mode") != "spray" or e.get("srev", 1) == SPRAY_SCORE_REV
SPRAY_WEAPONS = {
    "vandal":  {"rps": 9.75, "mag": 25, "v_climb": 0.85, "v_max": 11.0,
                "h_amp": 0.55, "h_settle": 9, "falloff": False},
    "phantom": {"rps": 11.0, "mag": 30, "v_climb": 0.70, "v_max": 9.5,
                "h_amp": 0.45, "h_settle": 8, "falloff": True},
}

# ── DODGE (หลบสกิล + เดินหลบ) ──
DODGE_DURATION_HAZ = True
DODGE_TELEGRAPH = 0.75           # เวลาเตือนก่อนสกิลลง (วินาที) — projectile/aoe ใช้เป็นฐาน
DODGE_PROJ_SPEED = 14.0          # ความเร็วลูกพุ่ง (เมตร/วินาที) — fallback ถ้า hazard ไม่มี speed ของตัวเอง
DODGE_PROJ_FLIGHT = 1.1          # เวลาบินจากจุดเกิดถึงตัวผู้เล่น (วินาที) คงที่ทุกตำแหน่งยืน — เดิมความเร็วคงที่
                                 # ยืนหน้าสุด z=3 เหลือแค่ 0.71 วิ (10 ม.) ยืนหลังสุดได้ 1.07 วิ = โดนถี่ขึ้นแค่เพราะเดินหน้า
DODGE_PROJ_R = 1.3               # (legacy — โหมดใหม่ไม่ใช้: hitbox คือตัวบอลอย่างเดียว)
DODGE_PROJ_HIT_R = 0.8           # รัศมี hitbox ลูกบอล = ขนาดบอลที่วาดบนจอเป๊ะ
DODGE_AOE_R = 1.6                # รัศมี molly/aoe (เมตร)
# molly ตกตรงไหน/เห็นยังไง — ผู้ใช้รายงาน 2026-09-07: "วงส้มเกิดใกล้ตัวเกินไป มองไม่เห็น อยู่ดีๆ ก็โดน"
# เดิมจุดศูนย์กลางสุ่มรอบตัว ±1.0/±0.6 ม. → วงรัศมี 1.6 อยู่ใต้เท้าทั้งวง: มองระดับหัว (VFOV ±35°) ขอบวง
# ที่ 1.6 ม. อยู่ที่ pitch -46° = นอกจอทั้งวง เห็นได้ก็ต่อเมื่อก้มมอง ซึ่งไม่มีใครทำระหว่าง flick หัว
DODGE_AOE_AHEAD = (0.3, 1.0)     # ศูนย์กลางตกข้างหน้าผู้เล่นเสมอ (เมตร) — ขอบหน้าวงอยู่ในจอ + ผู้เล่นยังอยู่ในวงตอนตก
DODGE_AOE_SIDE = 0.8             # เยื้องซ้าย/ขวาสูงสุด (เดิม 1.0): hypot(0.8, 1.0) = 1.28 < 1.6 → ต้องขยับออกเสมอ
DODGE_AOE_POST_H = 1.3           # เสาเตือนรอบขอบวงสูงเท่านี้ (เมตร) — ยอดเสาอยู่ต่ำกว่าตา 0.35 ม. เห็นได้ทุกมุมมอง
DODGE_AOE_LIFE = 1.1             # เวลา aoe ติดพื้นหลังจุดระเบิด (วินาที)
DODGE_HP_MAX = 100
DODGE_HIT_PENALTY = 22           # โดนสกิล = ลด HP + หักคะแนน
DODGE_ZONE_X = 4.5               # ขอบเขตเดินหลบ (เมตร, ±X)
DODGE_HAZ_INTERVAL = (1.3, 2.3)  # ช่วงสุ่มเวลาระหว่างสกิล (วินาที)
DODGE_KILL_PTS = 120

# ── PLACEMENT (crosshair placement / pre-aim) ──
PLACEMENT_Y_LO, PLACEMENT_Y_HI = EYE_Y, 1.85   # หัวอยู่ระดับนี้เสมอ (วินัยเล็งระดับหัว)
PLACEMENT_SPOTS = [   # จุด "มุม" รอบห้อง (x, z) ที่หัวบอทจะโผล่ — ใกล้เสา/ขอบ/ประตู
    (-7.5, 11.5), (-3.5, 12.5), (0.0, 13.0), (3.5, 12.5), (7.5, 11.5),
    (-8.5, 8.0), (8.5, 8.0), (-5.5, 10.0), (5.5, 10.0),
]
PLACEMENT_GOOD_DEG = 3.0    # พรีเอมคลาด <= ค่านี้ = ดีมาก (โบนัสเต็ม)
PLACEMENT_MAX_DEG = 18.0    # คลาดเกินนี้ = ไม่มีโบนัสพรีเอม

# ── SWITCH (target switching / 1vX) ──
SWITCH_BASE_PTS = 100
SWITCH_CLEAR_BONUS = 400    # โบนัสสูงสุดต่อ wave ถ้าเคลียร์ไว

DEFAULT_SETTINGS = {
    "ch": {"color": "#00FF00", "outline": True, "dot": True, "dotSize": 2,
           "lines": True, "lineLen": 6, "lineThick": 2, "lineGap": 3},
    "dpi": 800, "sens": 0.40,
    "pillars": False, "fps": False, "sound": True,
    # headshots: เปิดหัว/โบนัส headshot ในโหมดคลาสสิก 6 โหมด (ปิดไว้กันแรงค์เดิมเพี้ยน)
    # โหมดใหม่ (spray/dodge/placement/switch) ใช้ head/body เสมอ ไม่ขึ้นกับ toggle นี้
    "headshots": False,
    # GUNFIGHT: ตัวคูณ sens ตอนสโคป/ADS (= Scoped Sensitivity Multiplier ในเกม, 1.0 = สเกลตาม focal length)
    "scoped_sens": 1.0,
}
CH_COLORS = ["#00FF00", "#FFFFFF", "#FFFF00", "#00FFFF", "#FF00FF", "#FF4655", "#FF8800", "#000000"]
