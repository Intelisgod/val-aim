# -*- coding: utf-8 -*-
"""ระดับฝีมือบอท GUNFIGHT + บันไดแรงค์ดวล (pure python — ไม่มี pygame ; server/tools import ได้)

บอทหนึ่งตัวมี "ระดับ" = ดัชนีใน config.RANKS (0 = Iron I … 22 = Radiant — สเกลเดียวกับแรงค์ของโหมดอื่น)
พารามิเตอร์ต่อระดับ (tier_params) ถอดจากตาราง BOT_TIERS ด้วยการลากเส้นตรงระหว่างจุดยึดของแต่ละแรงค์ใหญ่:
  rt     วินาทีจาก "บอทเห็นเรา" → นัดแรก (crosshair บอทอยู่ที่มุมอยู่แล้ว) ; บอทเป็นฝ่าย peek หัก PEEK_ADV,
         เราเป็นฝ่าย peek เข้าหาบอทที่ยืนเฝ้า บวก PEEK_ADV (gunbots)
  sigma  องศาคลาดของนัดแรก (ต่อแกน, Gaussian) — จากนั้นเข้าเป้าเรื่อยๆ ทุกนัด (SETTLE_TAU / SETTLE_FLOOR)
  head_p โอกาสเล็งหัว (ที่เหลือเล็งอก) — ฟิตให้ HS% ของบอท (หัว / นัดที่โดน) เรียงตามล็อบบี้จริงต่อแรงค์
ค่าที่ใช้ได้มาจาก tools/duel_sim.py (ดูหมายเหตุที่ BOT_TIERS) — แก้ตารางนี้ต้องรัน sim ใหม่ ห้ามเดา

บันได (Ladder): 1-up/1-down — ชนะดวล = บอทตัวถัดไปสูงขึ้น 1 ขั้น, แพ้ = ลง 1 ขั้น → วนอยู่แถวระดับที่เราชนะ 50%
(= "แรงค์ดวล") ; สายบันไดที่ยังไม่เคยกลับทิศ ก้าว 2 ขั้นจนกว่าผลจะกลับทิศครั้งแรก แล้วก้าว 1 (Levitt 1971)
แรงค์ = maximum likelihood ของระดับ 50% จาก LADDER_WINDOW ดวลล่าสุดของสายบันได (ข้ามรอบ — history tier_tr) ;
"นิ่ง" เมื่อ SE ≤ LADDER_SE (หรือเลยปลายตาราง PIN_N ดวลติด) — รอบที่ยังไม่นิ่งไม่เขียน tier_i (ไม่เข้าแรงค์/ค่ากลาง/
dashboard) ; ดวลเดียวบอกได้น้อยมาก (เส้นอัตราชนะแบน ~3pp/ขั้น) จึงต้องรวมหลายรอบ — ที่มา/ตารางวัดดูที่ LADDER_BETA
บันไดแยกต่อ (ปืน, ดริล) ในดริลที่รู้ผลแพ้ชนะ (LADDER_DRILLS: duel / angle / peek) — แต่ละดริลสอบเทียบด้วยตัวคูณ rt
ของตัวเอง (DRILL_RT) ให้ดัชนีหมายถึงระดับคนเดียวกัน"""
import math

from .config import RANKS

TOP = len(RANKS) - 1          # 22 = Radiant
# บันไดเดินได้เลยปลายทั้งสองข้าง 2 ขั้น (บอท "เหนือ Radiant"/"ต่ำกว่า Iron" จากการต่อเส้นตาราง) แต่แรงค์ที่รายงานหนีบ 0..TOP
# — เดิม (แรงค์ = ค่าเฉลี่ยทางเดิน) บันไดที่ชนเพดานเดินขึ้นต่อไม่ได้ ค่าเฉลี่ยจึงถูกดึงลง: sim คน Immortal/Radiant ลู่เข้าแค่
# Asc III (20.0/20.2) และคน Iron II ถูกดันขึ้นเป็น Bronze I (3.0) ; ขั้นเผื่อทำให้อยู่ในช่วง ±0.6 ขั้น — แรงค์แบบ ML
# (LADDER_BETA) ใช้ผลแพ้ชนะที่แต่ละระดับ ไม่โดนปลายดึง (Immortal 21.2 / Radiant 21.5 / Iron II 1.9 — duel_sim ladder)
LADDER_MIN, LADDER_MAX = -2, TOP + 2

# peeker's advantage (วิ) — Riot "Peeking VALORANT's netcode" (2020): ~71 ms ที่ 144 FPS (~141 ms ที่ 60 FPS)
# ฝ่ายที่วิ่งออกจากมุม (peek) เห็นฝ่ายยืนเฝ้าก่อนราวนี้ — ใช้ค่า 144 FPS (เครื่องเล่นจริงของผู้ใช้) ค่าเดียว
PEEK_ADV = 0.070
# เล็งเข้าเป้า: คลาดนัดแรก e0 ~ N(0, sigma) ต่อแกน แล้วหดแบบ exponential เวลา SETTLE_TAU วิ + สั่นใหม่ทุกนัด
# N(0, sigma·SETTLE_FLOOR) — "ยิงนัดแรกหลุด นัดต่อมาเข้าเป้า" แบบคน ไม่ใช่สุ่มใหม่อิสระทุกนัด
SETTLE_TAU = 0.30
SETTLE_FLOOR = 0.35
REACQ = 0.5                   # เห็นเราใหม่หลังหลุดสายตา: reaction × นี้ (เล็งมุมที่เราหายไปรออยู่แล้ว)
DUEL_TIMEOUT = 4.0            # เห็นกันแล้วเกินนี้ยังไม่มีใครตาย → บอทถอยกลับหลังกำบัง (ไม่นับผล)

# ── ตารางจุดยึด (ดัชนี RANKS, rt วิ, sigma องศา, head_p) — สอบเทียบ 2026-09-24 ด้วย tools/duel_sim.py (Vandal, 144 FPS) ──
# ค่าเริ่ม phase-1 (trainer-realism F3): rt Iron ~500 → Radiant ~205 ms, σ 2.0° → 0.35°, head_p 0.10 → 0.30 ; ตอนนั้น
# คนจำลอง Radiant ชนะบอท Radiant 81% (บอทบนอ่อนไป) และ HS% บอทกลับลำดับ (Iron 21% > Diamond 13%)
# วิธี (fit n 2,000 ดวล/ขั้น × 2 รอบ ต่อจุดยึด): σ คงค่าเริ่ม ; head_p ฟิตให้ HS% บอท (หัว/นัดที่โดน) ดวลกับคนระดับเดียวกัน
# = เส้นแนวโน้ม HS% ล็อบบี้จริง (ถ่วงจำนวนผู้เล่น: 11.9 + 0.754·ดัชนี) ; rt ฟิตให้คนจำลองระดับเดียวกันชนะ 50% ;
# แล้วถดถอยให้เรียบ (ln rt และ head_p เป็นเส้นตรงตามดัชนี — ผลรายจุดแกว่งเพราะอัตราชนะไวต่อ rt แค่ ~1pp/10 ms)
# ตรวจ (n 1,000/ช่อง, seed ใหม่): แนวทแยง 44.6–53.3% ; แต่ละแถวลดลงทางเดียวตามระดับบอท ; HS% บอท 14→31% เรียงตาม
# ล็อบบี้ตั้งแต่ Bronze (Iron 15.6 > Bronze 14.1 — ชุดยาวของ Iron ไต่ขึ้นหัว) ; บันไดลู่เข้าแรงค์คนจำลอง ±0.6 ขั้น
# (Bronze–Ascendant) ; ผู้ใช้ (static 157 ms, flick 416 ms @71%, HS 25.6%) ลู่เข้า 15.7 = Diamond II (8 รัน 14.2–16.8)
BOT_TIERS = [
    (1,  0.530, 2.00, 0.386),    # Iron II
    (4,  0.458, 1.55, 0.415),    # Bronze II
    (7,  0.396, 1.30, 0.444),    # Silver II
    (10, 0.343, 1.10, 0.473),    # Gold II
    (13, 0.297, 0.90, 0.502),    # Platinum II
    (16, 0.257, 0.70, 0.531),    # Diamond II
    (19, 0.222, 0.55, 0.561),    # Ascendant II
    (21, 0.202, 0.45, 0.580),    # Immortal
    (22, 0.192, 0.35, 0.590),    # Radiant
]
# วินัยอื่นต่อระดับ (ค่าประมาณ — ลากเส้นตรง Iron I → Radiant ; sim ใช้ชุดเดียวกัน จึงถูกดูดซับในการฟิต rt/head_p):
#   comp       สัดส่วนรีคอยล์ที่ดึงสวน (ค่ากลางของ spray_comp ใน tools/rank_ceiling_sim.py: iron .468 → radiant .752)
#   run_shoot  โอกาส "วิ่งยิง" ตอนถึงจังหวะยิงแต่ยังไม่หยุด (swing) — แรงค์ต่ำยิงทั้งที่วิ่ง แรงค์สูงหยุดก่อน
#   burst      นัดต่อชุดของไรเฟิล (แรงค์ต่ำสาดยาว แรงค์สูงแตะ/ชุดสั้น) ; ปืนสั้นแตะตาม tap efficiency เสมอ
#   body_drop  จุดเล็ง "ตัว" ต่ำกว่าศูนย์หัวกี่เมตร — แรงค์ต่ำวาง crosshair ต่ำ (สะโพก/ท้อง) แรงค์สูงระดับอก ; ไม่มีข้อนี้
#              รีคอยล์ที่ดึงไม่สุดของแรงค์ต่ำพาชุดยาวไต่จากอกขึ้นหัวจน HS% บอท Iron (21%) สูงกว่า Diamond (13%) — กลับ
#              ลำดับล็อบบี้จริง (Iron 10% → Diamond 24%) ที่ต้องรักษา
#   lag        วินาทีที่บอทตามตำแหน่งเราไม่ทัน (เล็งจุดที่เราอยู่เมื่อ lag วิก่อน) = rt × LAG_FRAC
LAG_FRAC = 0.5
_EDGE = {"comp": (0.45, 0.78), "run_shoot": (0.60, 0.03), "burst": (5.0, 2.0), "body_drop": (0.75, 0.35)}
BURST_PAUSE = 0.30            # ไรเฟิล: พักระหว่างชุด (วิ) — Vandal 2-3 นัดฟื้นเป็นนัดแรกใน ~0.25 วิ
# ตัวคูณ rt ต่อปืนของบอท (ดวลกระจก — บอทถือปืนเดียวกับเรา): ตารางฟิตบน Vandal ; Phantom ใช้ได้ตรง (แนวทแยง 45–52%)
# แต่ปืนสั้นคนระดับเดียวกันชนะแค่ Sheriff 38–50% / Ghost 35–44% / Classic 36–46% (ต้องหลายนัด/แตะช้า — บอทได้เปรียบจาก
# peeker's advantage + เล็งที่เข้าเป้าตามเวลา) → คูณ rt ด้วยเส้นตรงตามดัชนี (ตัวคูณที่ Iron I, ที่ Radiant) ฟิตสองกลุ่ม
# จุดยึด ต่ำ (Iron–Plat) / สูง (Diamond–Radiant) ให้ค่าเฉลี่ยแนวทแยงแต่ละกลุ่ม = 50% (tools/duel_sim.py fit-weapon) —
# ตัวคูณเดียวทั้งตารางให้ค่าเฉลี่ย 50% ได้แต่ปลายบนง่ายไป (Asc–Rad 57–63%)
# ผลฟิต 2026-09-24 (n 800/จุดยึด): แนวทแยงหลังคูณ Sheriff 45–56% · Ghost 47–54% (Iron 61%) · Classic 47–54%
WEAPON_RT = {"sheriff": (1.654, 1.185), "ghost": (1.883, 1.265), "classic": (1.712, 1.251)}
LADDER_START = 9              # Gold I — บันไดใหม่เริ่มกลางกระดาน (ก้าว 2 ขั้นจนผลกลับทิศ)
# ── แรงค์ดวลแบบ "แม่นพอถึงบอก" (w3-fix 2026-09-24) — ประมาณระดับด้วย maximum likelihood ข้ามรอบ ──
# ดวลเดียวบอกระดับได้น้อยมาก: tools/duel_sim.py (PYTHONHASHSEED=0, n 800/ขั้น) คนจำลองผู้ใช้ชนะบอท Gold I 70%,
# Plat II 60%, Diamond I 49%, Asc II 43%, Radiant 32% — ชันแค่ ~3pp/ขั้น ; ฟิต logistic ต่อคนจำลอง: ความชัน β (log-odds
# ต่อขั้น) DUEL/Vandal 0.118–0.133 ทุกจุดยึด Iron–Radiant + ผู้ใช้, ANGLE 0.12–0.14, PEEK 0.15–0.18, Sheriff 0.13–0.15,
# Ghost 0.17–0.19, Classic 0.14–0.15 → ใช้ 0.12 (ชันน้อยสุด = SE ไม่ต่ำกว่าจริง ; ดริล/ปืนที่ชันกว่านิ่งช้ากว่าจำเป็นนิดหน่อย)
# ข้อมูล Fisher ต่อดวล ≤ β²/4 → SE ≤ 1.7 ขั้นต้องมี ~96 ดวล ; บันไดเดิม (w3: กลับทิศ + 3 ดวล แล้วเฉลี่ยทางเดินรอบเดียว)
# รอบแรกที่ "นิ่ง" อยู่ใน ±2 ขั้นของระดับจริงแค่ 12–38% (verify3: คน Diamond II ได้ Silver II ×2, Silver I, Gold I)
# กติกา: ทุกดวลของสายบันได (ปืน, ดริล) ใน LADDER_WINDOW ดวลล่าสุด (ข้ามรอบ — history tier_tr) → θ̂ = ระดับที่ชนะ 50% จาก
# logistic ความชัน LADDER_BETA (ML — ไม่ต้องตัดช่วงไต่หาทิ้ง ต่างจากค่าเฉลี่ยทางเดิน) ; SE = 1/√ข้อมูล Fisher ที่ θ̂
# "นิ่ง" = SE ≤ LADDER_SE ; หรือเลยปลายตาราง PIN_N ดวลติด (แพ้บอท ≤ Iron I / ชนะบอท ≥ Radiant) และ θ̂ อยู่นอกตาราง
# (รายงานได้แค่ปลายตาราง — ไม่งั้นคนไม่ยิงเลยไม่มีวันนิ่ง) ; รอบที่เคยชนปลายแล้วนิ่งจนจบรอบ
# สอบเทียบ (tools/duel_sim.py settle 40 30 — เกมจริง headless, PYTHONHASHSEED=0 ; ±2 = |tier_i − ระดับจริง| ≤ 2.5):
#   รอบแรกที่นิ่งอยู่ใน ±2 ขั้น ผู้ใช้ (15.73) ที่ 4/6/8/10 ดวลต่อรอบ: 78/85/82/80% (เดิม w3 12/20/25/32%) — นิ่งรอบที่
#   25/17/13/10 (เดิมรอบแรก) ; รอบต่อ ๆ มา 83–93% (เดิม 55–64%) ; จุดยึด Iron II–Radiant รอบแรก 70–100% (Asc II 70–75% และ
#   Plat II 72% ที่ 8/รอบ — เส้นแบนกว่า β ~0.10) ; ค่าที่ลู่เข้า (duel_sim ladder/user) เท่าเดิม: ผู้ใช้ 15.73 → 15.69,
#   ปลายตารางตรงขึ้น (ML ไม่โดนปลายบันไดดึง): Iron II 2.33 → 1.93, Immortal 20.57 → 21.22, Radiant 20.83 → 21.51
#   ทางเลือกที่ลองในตัวจำลองเร็ว (Bernoulli จากเส้นที่วัด): SE 1.6 + หน้าต่าง 140 / β 0.11 + 150 ดีขึ้น ≤ 2pp แต่ช้ากว่า 1–2 รอบ ;
#   ค่าเฉลี่ยทางเดิน (แบบเดิม) หน้าต่าง 80–100 ดวล ติดที่ ~78% เพราะช่วงไต่หาจาก Gold I ลากค่าลง
LADDER_BETA = 0.12
LADDER_WINDOW = 120
LADDER_SE = 1.7
PIN_N = 2
# ดริลที่มีบันไดแรงค์ (history tier_i) — ทุกดริลที่เป็น "ดวลรู้ผลแพ้ชนะ" และสอบเทียบกับคนจำลองต่อแรงค์แล้ว:
#   duel = บอทโผล่จากมุม (ท่าผสม) · angle = เราเฝ้ามุม บอทเป็นฝ่ายโผล่ (peeker's advantage ของบอท) ·
#   peek = เราเป็นฝ่ายโผล่ใส่บอทที่เฝ้ามุม — ดริล TAP (บอทไม่ยิง) / ADAD (วัดจังหวะหยุด) / QUICK / REPO / OP HOLD ไม่จัดแรงค์
# บันไดแยกต่อ (ปืน, ดริล) : ladder_start/recent_tier กรองดริล ; แต่ละดริลสอบเทียบให้ "คนระดับ X ลู่เข้า X" เท่ากัน
# (DRILL_RT) ดัชนีจึงเทียบข้ามดริลได้ — ผู้ใช้คนเดียวกันได้ต่างกันต่อดริล = จุดอ่อนเฉพาะสถานการณ์
LADDER_DRILLS = ("duel", "angle", "peek")
# ตัวคูณ rt บอทต่อดริล (ที่ Iron I, ที่ Radiant ; ลากเส้นตรงตามดัชนี — แบบเดียวกับ WEAPON_RT) — ตาราง BOT_TIERS ฟิตบน
# ดริล duel ; angle/peek เปลี่ยนว่าใครได้เปรียบ (บอทเป็นฝ่ายโผล่ / เราเป็นฝ่ายโผล่) → ฟิตให้แนวทแยงคนระดับ X vs บอท X
# ของกลุ่มต่ำ/สูง = 50% ด้วย tools/duel_sim.py fit-drill (n 600/จุดยึด × 2 รอบ, PYTHONHASHSEED=0, Vandal) ; ไม่มีคีย์ = 1.0
# ก่อนฟิต (ตัวคูณ 1.0, n 300/ช่อง) แนวทแยงคนระดับ X vs บอท X:
#   angle  48 44 44 42 40 38 40 52 43 % — บอทเป็นฝ่ายโผล่ได้ peeker's advantage + คนเฝ้าผิดขอบได้ (เดาถูก 1/จำนวนขอบ)
#   peek   40 34 29 27 27 33 30 34 24 % — คนต้องโผล่เข้ามุมที่ไม่รู้ตำแหน่ง: หยุด + flick ขณะบอทวางเป้าที่มุมรออยู่
#          (ตัวคูณสูง = rt ของ "ผู้เฝ้า" รวมค่าความตื่นตัวที่คนจริงเฝ้ามุมนาน ๆ ไม่รู้จังหวะ — ตีความ ไม่ใช่ค่าวัด)
# หลังฟิต แนวทแยง (seed ใหม่): angle 54 47 45 50 48 49 49 51 52 (เฉลี่ย 49.4%) · peek 59 50 52 50 52 54 49 49 44 (51.0%)
# บันไดลู่เข้า (8 รัน × 30 รอบ × 10 ดวล): คนทุกจุดยึดลู่เข้าแรงค์ตัวเอง ±1 ขั้น (ปลาย Iron/Radiant เหมือน DUEL) ;
# ผู้ใช้จำลอง (static 157, flick 416 @71%) ANGLE 14.6 = Diamond I · PEEK 13.0 = Platinum II (DUEL 15.7 = Diamond II)
DRILL_RT = {"angle": (1.164, 1.28), "peek": (1.593, 2.15)}


def _lerp_anchor(i, col):
    pts = [(a[0], a[col]) for a in BOT_TIERS]
    if i <= pts[0][0]:
        (x0, y0), (x1, y1) = pts[0], pts[1]
    elif i >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        if i == x1:
            return y1
    else:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= i <= x1:
                break
    return y0 + (y1 - y0) * (i - x0) / (x1 - x0)


def clamp_tier(i):
    """ดัชนีแรงค์ที่รายงาน/โชว์ได้ (0..TOP)"""
    return max(0, min(TOP, int(i)))


def clamp_step(i):
    """ขั้นที่บันไดเดินได้ (LADDER_MIN..LADDER_MAX — เลยปลายตารางแรงค์ได้ 2 ขั้น)"""
    return max(LADDER_MIN, min(LADDER_MAX, int(i)))


def tier_params(i, weapon=None, drill=None):
    """พารามิเตอร์บอทที่ขั้น i (LADDER_MIN..LADDER_MAX ; นอก 0..22 = ต่อเส้นสองจุดยึดปลาย) ถือปืน weapon ในดริล drill
    — dict: rt, sigma, head_p, comp, run_shoot, burst, body_drop, lag"""
    i = clamp_step(i)
    u = max(0.0, min(1.0, i / TOP))
    m0, m1 = WEAPON_RT.get(weapon, (1.0, 1.0))
    d0, d1 = DRILL_RT.get(drill, (1.0, 1.0))
    rt = max(0.12, _lerp_anchor(i, 1) * (m0 + (m1 - m0) * u) * (d0 + (d1 - d0) * u))
    p = {"tier": i, "rt": rt, "sigma": max(0.10, _lerp_anchor(i, 2)),
         "head_p": min(1.0, max(0.0, _lerp_anchor(i, 3))), "lag": rt * LAG_FRAC}
    for k, (a, b) in _EDGE.items():
        p[k] = a + (b - a) * u
    p["burst"] = max(1, int(round(p["burst"])))
    return p


def tier_name(i):
    return RANKS[clamp_tier(i)][1]


def step_label(i):
    """ป้ายขั้นบันได (รวมขั้นเผื่อนอกตาราง): 'Radiant +1' / 'Iron I −2' / ชื่อแรงค์ปกติ"""
    i = clamp_step(i)
    if i > TOP:
        return f"{RANKS[TOP][1]} +{i - TOP}"
    if i < 0:
        return f"{RANKS[0][1]} -{-i}"
    return RANKS[i][1]


def tier_color(i):
    return RANKS[clamp_tier(i)][2]


def mle_level(trials, beta=None):
    """θ̂ = ระดับบอทที่ชนะ 50% (logistic ความชัน beta log-odds/ขั้น คงที่) จาก [(ระดับบอท, ชนะ?)] — bisection บน score
    Σ(ชนะ − σ(β(θ − ระดับ))) ซึ่งลดลงทางเดียวตาม θ ; ชนะหมด/แพ้หมด = ขอบช่วงค้น (นอกตารางไกล) ; ว่าง = None"""
    if not trials:
        return None
    beta = LADDER_BETA if beta is None else beta

    def score(th):
        return sum((1.0 if w else 0.0) - 1.0 / (1.0 + math.exp(-beta * (th - t))) for t, w in trials)
    lo, hi = LADDER_MIN - 10.0, LADDER_MAX + 10.0
    if score(lo) <= 0:
        return lo
    if score(hi) >= 0:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if score(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fisher_info(trials, th, beta=None):
    """ข้อมูล Fisher ของ θ จากดวลชุดนี้ = Σ β²·p(1−p) (ดวลที่บอทห่างจาก θ มาก บอกได้น้อยกว่า)"""
    beta = LADDER_BETA if beta is None else beta
    s = 0.0
    for t, _w in trials:
        p = 1.0 / (1.0 + math.exp(-beta * (th - t)))
        s += beta * beta * p * (1.0 - p)
    return s


def even_prior(level, n=None):
    """ดวลสมมุติ n ดวล (ค่าเริ่ม LADDER_WINDOW) ที่ระดับ level ชนะ/แพ้สลับกัน = สายบันไดที่นิ่งแล้วที่ level พอดี
    (θ̂ = level, SE = 2/(β√n)) — ใช้ใน selftest/regression/sim เท่านั้น"""
    return [(clamp_step(level), k % 2 == 0) for k in range(LADDER_WINDOW if n is None else n)]


class Ladder:
    """บันไดแรงค์ดวล 1-up/1-down บนดัชนี RANKS — หนึ่ง "สาย" ต่อ (ปืน, ดริล) เดินต่อข้ามรอบ
    start=None = สายใหม่ เริ่มที่ seed (None = LADDER_START ; ดริล angle/peek ที่ยังไม่เคยเล่นใช้ tier_end ของ DUEL ปืนเดียวกัน
      เป็น seed — สเกลเดียวกัน) ; start = ระดับบอทตัวถัดไปที่รอบก่อนจบไว้ (tier_end)
    prior = [(ระดับบอท, ชนะ?)] ของรอบก่อน ๆ ในสายเดียวกัน (เก่า → ใหม่ ; ladder_resume อ่านจาก history tier_tr)
    ก้าว 2 จนผลในสาย (prior + รอบนี้) กลับทิศครั้งแรก แล้วก้าว 1 ; แรงค์ = θ̂ จาก LADDER_WINDOW ดวลล่าสุดของสาย
    นิ่ง (รายงานเป็นแรงค์ได้) = มีดวลในรอบนี้ และ SE ≤ LADDER_SE หรือรอบนี้เคยชนปลายตาราง (pinned)"""

    def __init__(self, start=None, seed=None, prior=None):
        self.fresh = start is None             # สายใหม่ (ไม่มีรอบก่อน)
        if start is not None:
            self.cur = clamp_step(start)
        else:
            self.cur = LADDER_START if seed is None else clamp_step(seed)
        self.prior = [(clamp_step(t), bool(w)) for t, w in (prior or [])][-LADDER_WINDOW:]
        self.trials = []                       # [(ดัชนีบอทของดวลนั้น, ชนะ?)] ของรอบนี้
        self.was_pinned = False                # รอบนี้เคยชนปลายตาราง = นิ่งจนจบรอบ (ชนะบอท −2 หนึ่งดวลไม่ทำให้แรงค์หาย)
        self._fit = None                       # (จำนวนดวลที่คิดแล้ว, θ̂, ข้อมูล Fisher) — หน้าผลเรียกทุกเฟรม

    def _seq(self):
        return self.prior + self.trials

    def reversed(self):
        """ผลในสายเคยกลับทิศแล้ว (ชนะ→แพ้ หรือ แพ้→ชนะ) — นับข้ามรอบ"""
        s = self._seq()
        return any(a[1] != b[1] for a, b in zip(s, s[1:]))

    @property
    def step(self):
        return 1 if self.reversed() else 2

    def record(self, won):
        """บันทึกผลดวลที่บอทระดับ cur — คืนระดับใหม่"""
        d = 1 if won else -1
        self.trials.append((self.cur, bool(won)))
        self._fit = None
        self.cur = clamp_step(self.cur + d * self.step)
        if self.pinned():
            self.was_pinned = True
        return self.cur

    @property
    def n(self):
        return len(self.trials)

    @property
    def wins(self):
        return sum(1 for _, w in self.trials if w)

    def window(self):
        """ดวลที่ใช้ประมาณแรงค์ = LADDER_WINDOW ดวลล่าสุดของสาย (รวมรอบนี้)"""
        return self._seq()[-LADDER_WINDOW:]

    def _mle(self):
        k = len(self.prior) + len(self.trials)
        if self._fit is None or self._fit[0] != k:
            w = self.window()
            th = mle_level(w)
            self._fit = (k, th, fisher_info(w, th) if th is not None else 0.0)
        return self._fit

    def theta(self):
        """θ̂ ทศนิยม (อาจเลยปลายตาราง) — None ถ้าสายยังไม่มีดวล"""
        return self._mle()[1]

    def se(self):
        """ความคลาดมาตรฐานของ θ̂ (ขั้น) — สายยังไม่มีดวล = None"""
        _k, th, inf = self._mle()
        if th is None:
            return None
        return 1.0 / math.sqrt(inf) if inf > 0 else float("inf")

    def pinned(self):
        """ตอนนี้เลยปลายตาราง: PIN_N ดวลล่าสุดของสาย แพ้บอท ≤ Iron I / ชนะบอท ≥ Radiant ทั้งหมด และ θ̂ อยู่นอกตาราง
        — แรงค์ที่รายงานได้มีแค่ปลายตาราง (คนระดับกลางที่บังเอิญชนะบอท Radiant สองดวล θ̂ ยังอยู่กลางตาราง = ไม่ใช่)"""
        tail = self._seq()[-PIN_N:]
        if len(tail) < PIN_N or not (all(t <= 0 and not w for t, w in tail)
                                     or all(t >= TOP and w for t, w in tail)):
            return False
        th = self.theta()
        return th is not None and (th < 0 or th > TOP)

    def settled(self):
        """รายงานแรงค์ได้ไหม: มีดวลที่ตัดสินในรอบนี้ และ (SE ≤ LADDER_SE หรือรอบนี้เคยชนปลายตาราง)"""
        if not self.trials:
            return False
        return self.was_pinned or self.se() <= LADDER_SE

    def need(self):
        """ดวลที่ยังต้องเล่นให้นิ่ง (ขั้นต่ำ — ดวลที่บอทตรงระดับพอดีให้ข้อมูล β²/4) ; SE ถึงแล้ว = 0 ;
        ผลในสายยังไม่กลับทิศ (ชนะรวด/แพ้รวด) = None (ยังบอกไม่ได้)"""
        se = self.se()
        if se is not None and se <= LADDER_SE:
            return 0
        if not self.reversed():
            return None
        inf = self._mle()[2]
        return max(1, int(math.ceil((1.0 / LADDER_SE ** 2 - inf) / (LADDER_BETA ** 2 / 4.0))))

    def spread(self):
        """ครึ่งความกว้างช่วง 80% ของแรงค์ (ขั้น, ปัดเป็นจำนวนเต็ม ≥ 1) = 1.28 × SE — None ถ้าบอกไม่ได้"""
        se = self.se()
        if se is None or se == float("inf"):
            return None
        return max(1, int(math.floor(1.2816 * se + 0.5)))

    def estimate(self):
        """ดัชนีแรงค์ = θ̂ ปัดเศษ หนีบ 0..TOP ; None ถ้ารอบนี้ยังไม่มีดวลที่ตัดสิน
        เป็น "แรงค์" ได้เมื่อ settled() เท่านั้น (ผู้เรียกเช็คเอง — history/หน้าผล/การ์ดแชร์)"""
        if not self.trials:
            return None
        return clamp_tier(math.floor(self.theta() + 0.5))

    def unbracketed(self):
        """ผลในสายยังไม่เคยกลับทิศ (ยังหาระดับไม่เจอ): +1 ชนะรวด / −1 แพ้รวด ; กลับทิศแล้ว/รอบนี้ยังไม่มีดวล = None"""
        if not self.trials or self.reversed():
            return None
        return 1 if self.trials[-1][1] else -1


def ladder_start(history, weapon, current, drill="duel"):
    """จุดเริ่มบันไดของ (ปืน, ดริล) = tier_end ของรอบล่าสุดของคู่นั้น (กติการุ่นปัจจุบัน — current(e) = config.mode_current)
    None ถ้าไม่เคยเล่น → บันไดใหม่ (tier_end อาจเลยปลาย 0..22 ได้ 2 ขั้น — ขั้นเผื่อของบันได)"""
    for e in reversed(history or []):
        if (e.get("mode") == "gun" and e.get("drill", "duel") == drill and e.get("variant") == weapon
                and current(e) and isinstance(e.get("tier_end"), int)):
            return clamp_step(e["tier_end"])
    return None


def _trials_of(e):
    """tier_tr ของ entry → [(ระดับ, ชนะ?)] ; ไม่มี/รูปแบบเพี้ยน = None"""
    tr = e.get("tier_tr")
    if not isinstance(tr, list):
        return None
    out = []
    for x in tr:
        if not (isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[0], int) and not isinstance(x[0], bool)
                and x[1] in (0, 1) and not isinstance(x[1], float)):
            return None
        out.append((clamp_step(x[0]), bool(x[1])))
    return out


def ladder_resume(history, weapon, current, drill="duel"):
    """(start, prior) ของ Ladder รอบใหม่ของ (ปืน, ดริล) จาก history (กติการุ่นปัจจุบัน — current = config.mode_current):
    start = tier_end ของรอบล่าสุดของสาย (ไม่เคยเล่น = None → สายใหม่) ; prior = ดวลของรอบก่อน ๆ ต่อกัน (เก่า → ใหม่ ;
    tier_tr ของแต่ละรอบ) ย้อนไปจนครบ LADDER_WINDOW — รอบที่มี tier_end แต่ tier_tr ไม่มี/เพี้ยน = ตัดสายไว้แค่นั้น"""
    start, prior = None, []
    for e in reversed(history or []):
        if not (e.get("mode") == "gun" and e.get("drill", "duel") == drill and e.get("variant") == weapon
                and current(e) and isinstance(e.get("tier_end"), int)):
            continue
        if start is None:
            start = clamp_step(e["tier_end"])
        tr = _trials_of(e)
        if tr is None:
            break
        prior[:0] = tr
        if len(prior) >= LADDER_WINDOW:
            break
    return start, prior[-LADDER_WINDOW:]


def recent_tier(history, weapon, current, n=5, drill="duel"):
    """แรงค์ดวลปัจจุบันของ (ปืน, ดริล) = ค่ากลางของ tier_i ใน n รอบล่าสุดของคู่นั้น → (ดัชนี, จำนวนรอบ, ดวลรวม) หรือ None"""
    rows = [e for e in (history or []) if e.get("mode") == "gun" and e.get("drill", "duel") == drill
            and e.get("variant") == weapon and current(e) and isinstance(e.get("tier_i"), int)][-n:]
    if not rows:
        return None
    ts = sorted(e["tier_i"] for e in rows)
    mid = len(ts) // 2
    med = ts[mid] if len(ts) % 2 else (ts[mid - 1] + ts[mid]) / 2.0
    return clamp_tier(math.floor(med + 0.5)), len(rows), sum(e.get("tier_n", 0) for e in rows)
