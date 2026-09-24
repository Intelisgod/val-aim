# -*- coding: utf-8 -*-
"""ดริล GUNFIGHT ชุดสมจริง (2026-09-24 lane C5 — DESIGN §2.5 / phase-1 trainer-realism D1–D4) — DrillMixin ของ GunMixin
(pure logic ไม่มี pygame: tools/duel_sim.py ขับ headless ได้ ; วาดด้วยตัววาดเดิมของ GUNFIGHT — กล่อง arena + หุ่นบอท)

  angle : ANGLE HOLD — เราเฝ้ามุม "ประตู / ประตู+กล่อง / ยกพื้น" ที่ระยะไฟต์จริงของปืน มีขอบให้เห็นชัด 2–4 ขอบ บอทโผล่จาก
          ขอบใดขอบหนึ่ง (วิ่งออกกว้าง / โผล่หยุดยิง / จิ้มไหล่หลอก / หมอบโผล่ ; ชุดยกพื้นหัวบอทสูงขึ้น 0.5–1.0 ม.)
          วัด ณ เฟรมแรกที่ "หัว" บอทโผล่ (ไม่นับไหล่ที่จิ้มหลอก): องศาคลาดแนวนอน/แนวตั้ง crosshair → หัว, เวลาถึงนัดแรก,
          ฆ่าได้ก่อนบอทยิงนัดแรก ; คะแนนเพิ่ม = คุณภาพวางเป้า (≤0.5° เต็ม → ≥5° ศูนย์) × รอดดวลนั้น ; มีบันไดแรงค์
  peek  : PEEK & STOP — เราเริ่มหลังกำแพงตรงหน้า บอทเฝ้ามุมอยู่ที่ระยะตามการกระจายระยะคิลจริงของปืน ; นาฬิกา reaction
          ของบอทเริ่มเมื่อ "หัวเรา" พ้นขอบ (เราวิ่งเข้าหา = บวก peeker's advantage 70 ms ให้เรา — gunbots) — วัด
          หัวพ้นขอบ → นัดแรก, ความเร็วตอนยิงนัดแรก (ยิงตอนยังเดิน %), หยุดถึงยิง (เข้า deadzone → คลิก ; ดีสุด 0–50 ms),
          นัดแรกเข้าหัว %, ชนะดวล % ; มีบันไดแรงค์
  tap   : TAP @ RANGE — หัวที่ 20–35 ม. (ยืน / ส่าย ADAD) บอทไม่ยิงสวนแต่โผล่ให้ยิงแค่ 2.2–3.5 วิ — วัดนัดที่ยิงตอน
          สเปรดจากการยิงยังไม่กลับเป็นนัดแรก, หัวโดน % ต่อช่วงระยะ, ความยาวชุดยิง, ช่วงห่างการแตะเทียบ tap efficiency
          ของปืน (ไฟล์เกม: Vandal 4 · Phantom 3 · Sheriff 2 นัด/วิ) ; ไม่จัดแรงค์
  adad  : STRAFING HEADS — บอทส่าย ADAD ความเร็ววิ่ง กลับทิศทุก 0.15–0.45 วิ แล้ว counter-strafe หยุดยิงตาม rt ของระดับ
          (นับจากตอนหยุดนิ่ง) — วัดโดน % ตอนบอทเดิน vs ตอนหยุด และเวลาฆ่าหลังบอทหยุด ("ลงโทษจังหวะหยุด") ; ไม่จัดแรงค์
          (บอทระดับเดียวกับที่บันได DUEL ปืนนี้จบไว้)
ข้อมูลจริงที่ใช้: ระยะ (gunplay.DUEL_DIST_Q — 438 แมตช์), tap efficiency/สเปรด (riot_data ผ่าน Stability), deadzone/เบรก
(movement) ; ค่าประมาณ (ระบุที่ค่าคงที่): น้ำหนักท่าโผล่, ขนาดประตู/กล่อง/ยกพื้น, ช่วงรอ/ช่วงโผล่"""
import math
import random

from .config import EYE_Y, ROOM_X, WALL_Z
from . import arena, duel, guns, movement
from .guns import WEAPONS, HEAD_R, BODY_HW

# ───────────────────────── ANGLE HOLD ─────────────────────────
# ท่าโผล่ของบอท (ค่าประมาณ — ไม่มีข้อมูลท่าจาก API) : ไม่มี hold (ยืนรอในที่โล่ง = ไม่ใช่การจับมุม) และไม่มี strafe
ANGLE_KINDS = (("swing", 0.30), ("stop", 0.30), ("jiggle", 0.20), ("crouch", 0.20))
# ฉากใหม่ทุกดวล → บอทรอนานกว่า DUEL (0.4–1.4 วิ) ให้มีเวลาเห็นขอบแล้ววาง crosshair (rt ~0.2 + flick ~0.3 วิ)
ANGLE_WAIT = (1.0, 2.4)
ANGLE_GOOD, ANGLE_BAD = 0.5, 5.0      # องศาคลาดรวม ≤ 0.5° = วางเป้าเต็ม, ≥ 5° = 0 (= "เฝ้าผิดมุม")
ANGLE_PTS = 150                       # คะแนนวางเป้าเต็มต่อดวลที่รอด (เทียบคิล KILL_BASE 100)
# Insight "crosshair สูง/ต่ำกว่าหัว": ช่วง 95% ต้องไม่คร่อม 0 "และ" เยื้องเกินครึ่งรัศมีหัวที่ระยะคิลค่ากลางของ Vandal
# (HEAD_R 0.14 ม. ที่ 17.3 ม. — gunplay.DUEL_DIST_Q = 0.46° → ครึ่ง 0.23°) — เกณฑ์จากเรขาคณิตหัว ไม่ใช่ค่าที่วัดว่า
# เยื้องเท่าไรเริ่มเสียดวลจริง (ค่าประมาณ) ; เยื้องน้อยกว่านี้ crosshair ยังอยู่บนหัว ไม่ต้องแก้
ANGLE_BIAS_DEG = round(0.5 * math.degrees(math.atan(HEAD_R / 17.3)), 2)
ANGLE_LAYOUTS = (("door", 0.35), ("door_crate", 0.40), ("ledge", 0.25))
DOOR_HW = (0.8, 1.2)                  # ครึ่งความกว้างประตู (ม.) — ประตูไซต์ทั่วไปกว้าง 1.6–2.4 ม. (ประมาณ)
WALL_T, WALL_H = 0.4, 3.0             # ผนังฉาก: หนา / สูง (สูงกว่าหัวบอทบนยกพื้นสูงสุด 2.74 ม.)
CRATE_W, CRATE_D, CRATE_H = (2.4, 3.0), 1.0, 2.1   # กล่อง: กว้างพอซ่อนตัวตรงกลาง, สูงกว่าหัวยืน (1.74)
CRATE_AHEAD = (3.0, 5.5)              # กล่องอยู่หน้าประตูเข้ามาหาเราเท่านี้
LEDGE_H = (0.5, 1.0)                  # ยกพื้น (DESIGN: ความสูงต่าง ±0.5–1.0 ม. ที่เห็นชัด — ในห้องนี้มีแต่ "สูงกว่า")
BEHIND = 0.45                         # บอทยืนหลังผิวด้านหลังของที่กำบังเท่านี้ (เท่า gunbots.COVER_BACK)
DOOR_IN = 0.35                        # บอทโผล่ในประตูได้ไกลสุด = กว้างประตู − ค่านี้ (ไม่ทะลุไปหลังผนังอีกฝั่ง)

# ───────────────────────── PEEK & STOP ─────────────────────────
PEEK_WALL_DZ = 0.8                    # กำแพงของเราห่างหน้าเท่านี้ (ม.) — ยืนชิดกำแพงแล้วโผล่ข้าง
PEEK_EDGE_X = 0.6                     # ขอบกำแพงอยู่ทางฝั่งโผล่ของจุดเริ่มเท่านี้
PEEK_DEPTH = (0.35, 0.6)              # ขอบหัวเราหลบหลังขอบเท่านี้ตอนเริ่ม
PEEK_WIDTH = (0.25, 0.9)              # ต้องเดินออกเท่านี้หัวถึงพ้นขอบให้บอทเห็น (น้อย = มุมกว้าง บอทเห็นไว ; มาก = มุมแคบ)
PEEK_CROUCH_P = 0.20                  # บอทหมอบเฝ้า (หัวต่ำ 0.55 ม.) — ค่าประมาณ
PEEK_NEVER = 8.0                      # ไม่โผล่เลยเกินนี้ (วิ) = ดวลไม่นับ บอทเปลี่ยนมุม
PEEK_DIST = (8.0, 30.0)               # หนีบระยะที่สุ่มจาก DUEL_DIST_Q (ห้อง 32 ม.)
PEEK_MOVE_CUT = 0.10                  # Insight: นัดแรกตอนยังเดินเกินนี้ (ช่วง 95% ทั้งช่วง) = เตือน counter-strafe — ค่าประมาณ
# Insight: หยุด (เข้า deadzone) ถึงคลิก — ช่วง 95% ต่อรอบ (t) ต่ำกว่านี้ทั้งช่วง = "ยิงทันทีที่นิ่ง" ; สูงกว่าทั้งช่วง = รอนานไป
# ค่าประมาณจาก Riot dev (counter-strafe ถึงความแม่นระดับเดิน ~55 ms) ไม่ใช่ค่าที่วัดว่าช้ากว่าเท่าไรเริ่มเสียดวล — UI บอก "คร่าว ๆ"
PEEK_STOP_GOOD_MS = 50

# ───────────────────────── TAP @ RANGE ─────────────────────────
TAP_DIST = (20.0, 35.0)               # p75–p90+ ของระยะคิลไรเฟิลจริง (38% ของคิลไรเฟิลไกลกว่า 20 ม.)
TAP_BACK = 3.0                        # ดริลนี้ยืนถอยหลังเพิ่ม (z −21) ให้ถึง 35 ม. ในห้อง (ผนังหลัง z 14)
TAP_BANDS = ((25.0, "20"), (30.0, "25"), (1e9, "30"))   # ช่วงระยะ 20–25 / 25–30 / 30–35 ม.
TAP_KINDS = (("stop", 0.45), ("strafe", 0.35), ("hold", 0.20))   # ยืนนิ่ง (โผล่หยุด/ยืนอยู่แล้ว) 65% · ส่าย 35%
TAP_WINDOW = (2.2, 3.5)               # โผล่ให้ยิงนานเท่านี้หลังเห็นกันแล้วถอย (มีเวลาแตะ 5–10 นัด ไม่ใช่สเปรย์ได้ทั้งแม็ก)
BURST_GAP = 1.2                       # นัดที่ห่างกันไม่เกิน 1.2 × ช่วงยิงของปืน = "กดค้าง/รัว" ชุดเดียวกัน (เท่า Stability._hold)
TAP_GAP_MAX = 3.0                     # ช่วงห่างที่ยาวกว่านี้ = พักรอบอทตัวใหม่ ไม่ใช่จังหวะแตะ
# Insight: ยิงก่อนสเปรดหายเกินนี้ (ช่วง 95% ทั้งช่วง) = แนะนำแตะทีละนัด — ค่าประมาณ (ยังไม่มีข้อมูลว่านัดพวกนี้เสียหัวไปเท่าไร
# เทียบนัดที่รอสเปรดหาย: band เก็บนัด/หัวต่อระยะ ไม่แยกตามจังหวะแตะ) ; UI บอกว่าเป็นเกณฑ์คร่าว ๆ
TAP_SPAM_CUT = 0.25

# ───────────────────────── STRAFING HEADS (ADAD) ─────────────────────────
ADAD_DIST = (8.0, 26.0)
ADAD_STRAFE = (0.6, 1.6)              # ส่ายนานเท่านี้ก่อนหยุดยิงแต่ละครั้ง (วิ) — ค่าประมาณ
ADAD_STOP = (0.5, 0.9)                # หยุดยิงนานเท่านี้หลังนิ่ง แล้วกลับไปส่าย
ADAD_TIMEOUT = 7.0                    # เห็นกันนานเกินนี้ยังไม่จบ = ถอย (ดวลไม่นับ)

NEW_DRILLS = ("angle", "peek", "tap", "adad")
# คีย์ใน history entry (mode "gun") ที่ดริลชุดนี้เพิ่ม — contract ให้ server/dashboard อ่าน (ไม่มีข้อมูล = ไม่มีคีย์)
DRILL_KEYS = {
    "angle": {"pa_n": "จำนวนครั้งที่วัดได้ (หัวบอทโผล่)", "pa_err": "ค่ากลางองศาคลาดรวม crosshair→หัว (°)",
              "pa_h": "ค่ากลางองศาคลาดแนวนอน (°)", "pa_v": "ค่าเฉลี่ยคลาดแนวตั้ง crosshair−หัว (° ; + = เล็งสูงไป)",
              "pa_wrong": "ครั้งที่คลาด ≥ 5° (เฝ้าผิดมุม)", "t1_ms": "ค่ากลางเวลาหัวโผล่ถึงนัดแรก (ms)",
              "pre_kill": "คิลที่เกิดก่อนบอทยิงนัดแรก"},
    "peek": {"pk_n": "ดวลที่รู้ผลและเรายิงแล้ว", "mv_first": "นัดแรกที่ยิงตอนเร็วเกิน deadzone",
             "fs_hs": "นัดแรกที่เข้าหัว", "expo_ms": "ค่ากลาง หัวเราพ้นขอบ (บอทเห็น) → นัดแรกของเรา (ms)",
             "stop_ms": "ค่ากลาง เข้า deadzone → คลิก (ms)", "stop_n": "จำนวนนัดแรกที่หยุดก่อนยิง",
             "pk_w": "ชนะดวล", "pk_l": "แพ้ดวล"},
    "tap": {"tap_n": "คลิกทั้งหมด", "spam": "นัดที่สเปรดจากการยิงยังไม่กลับเป็นนัดแรก",
            "band": "{'20'|'25'|'30': [นัดใส่บอทที่โผล่, หัวโดน]} ช่วง 20–25/25–30/30–35 ม.",
            "bursts": "[ชุด 1, 2, 3, 4+ นัด]", "tap_ms": "ค่ากลางช่วงห่างระหว่างการแตะ (ms)",
            "tap_gaps": "จำนวนช่วงแตะ", "tap_fast": "ช่วงแตะที่สั้นกว่า 1/tap efficiency"},
    "adad": {"hit_mv": "[นัด, โดน] ตอนบอทเร็วเกิน deadzone", "hit_st": "[นัด, โดน] ตอนบอทหยุด",
             "kill_stop_ms": "ค่ากลางเวลาฆ่าหลังบอทหยุดนิ่ง (ms)", "kill_stop_n": "คิลตอนบอทหยุด",
             "kill_mv_n": "คิลตอนบอทยังส่าย"},
}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def wilson(k, n, z=1.96):
    """ช่วงความเชื่อมั่น Wilson ของสัดส่วน k/n → (lo, hi) ; n = 0 → (0, 1)"""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


_T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26, 10: 2.23,
        12: 2.18, 15: 2.13, 20: 2.09, 30: 2.04}


def tcrit(df):
    """t วิกฤต 95% สองหาง — df ที่ไม่มีในตารางใช้แถว df ต่ำกว่าที่ใกล้สุด (t ใหญ่กว่า = ช่วงกว้างกว่า ไม่มั่นใจเกินจริง)"""
    if df < 1:
        return float("inf")
    return _T95[max(k for k in _T95 if k <= df)] if df <= 30 else 1.96 + 2.4 / df


def t_interval(vals):
    """(ค่าเฉลี่ย, ครึ่งช่วง 95% แบบ t) ของค่าต่อรอบ — n < 2 → ครึ่งช่วง inf"""
    n = len(vals)
    if n == 0:
        return 0.0, float("inf")
    m = sum(vals) / n
    if n < 2:
        return m, float("inf")
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    return m, tcrit(n - 1) * sd / math.sqrt(n)


def cluster_ratio(pairs):
    """สัดส่วนรวม Σk/Σn ของหลายรอบ + ช่วง 95% ที่นับว่านัด/ดวลในรอบเดียวกันไม่อิสระกัน (รอบ = cluster ; DESIGN §1)
    — Wilson ของนัดรวมทุกรอบแคบเกินจริง: นัดในชุดยิงเดียวกัน/ฟอร์มวันเดียวกันไปทางเดียวกัน
    SE แบบ ratio estimator: √(G/(G−1) · Σ(k_i − p·n_i)²) / Σn , ครึ่งช่วง t(G−1) ; ใช้ช่วงที่กว้างกว่าระหว่างอันนี้กับ
    Wilson (ทุกรอบสัดส่วนเท่ากันเป๊ะ SE cluster เป็น 0 ได้ — ห้ามแคบกว่าช่วงของนัดอิสระ)
    pairs = [(k, n)] ต่อรอบ (รอบ n = 0 ไม่นับ) → (p, lo, hi, se, G, N) — se = SE ที่ใช้จริง (ตัวที่ใหญ่กว่า)"""
    ps = [(k, n) for k, n in pairs if n > 0]
    N = sum(n for _k, n in ps)
    if not N:
        return 0.0, 0.0, 1.0, float("inf"), 0, 0
    K = sum(k for k, _n in ps)
    p, G = K / N, len(ps)
    wlo, whi = wilson(K, N)
    se_b = math.sqrt(p * (1 - p) / N)
    if G < 2:
        return p, wlo, whi, se_b, G, N
    se = math.sqrt(G / (G - 1) * sum((k - p * n) ** 2 for k, n in ps)) / N
    h = tcrit(G - 1) * se
    return p, min(wlo, max(0.0, p - h)), max(whi, min(1.0, p + h)), max(se, se_b), G, N


def more_needed_se(p, se, n, thr, g=None):
    """ต้องมีอีกกี่หน่วย (สัดส่วนเท่าเดิม) ช่วง 95% ถึงไม่คร่อมขีด thr ; None ถ้าเกิน 5,000
    ฉายช่วงแบบเดียวกับ cluster_ratio: [min(Wilson, p − t·se'), max(Wilson, p + t·se')] ที่ n' = n + เพิ่ม, se' = se·√(n/n')
    (หน่วยต่อรอบเท่าเดิม), t ของจำนวนรอบที่จะมี (g = จำนวนรอบตอนนี้ ; ไม่ให้ = 1.96) — เดิม ±1.96·se สมมาตร พังที่สัดส่วน
    0/100% (se = 0 → บอก "ต้องอีก ~1" ทั้งที่ 0/30 ยังคร่อม 10% ต้องถึง ~35) และมองข้าม t ของรอบน้อย"""
    if abs(p - thr) < 1e-9 or not n or se == float("inf"):
        return None
    for extra in list(range(1, 50)) + list(range(50, 5001, 10)):
        m = n + extra
        wlo, whi = wilson(p * m, m)
        gf = round(g * m / n) if g else 0
        h = (tcrit(gf - 1) if gf >= 2 else 1.96) * se * math.sqrt(n / m)
        if min(wlo, p - h) > thr or max(whi, p + h) < thr:
            return extra
    return None


def _median(vals):
    s = sorted(vals)
    if not s:
        return None
    k = len(s) // 2
    return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2.0


def tap_eff(weapon):
    """tap efficiency ของปืน (นัด/วิ ที่สเปรดกลับเป็นนัดแรกทุกนัด) จากไฟล์เกม — None ถ้าไม่มี (Op)"""
    from .stability import patched_block
    return (patched_block(weapon) or {}).get("tap_eff")


class DrillMixin:
    # ───────────────────────── สถานะต่อรอบ ─────────────────────────
    def gun_drills_reset(self):
        """เรียกจาก reset_gun — ตัวชี้วัดของดริลใหม่ต่อรอบ"""
        self.gun_layout = None          # angle: {"name", "spots"} ฉากของดวลปัจจุบัน
        self.gun_drec = []              # บันทึกต่อดวล (angle/peek) — สรุปลง history ตอนจบรอบ
        self.gun_stop_t = None          # peek: เวลาที่ความเร็วเราเพิ่งลดเข้า deadzone (หลังจากเคยเร็วเกิน)
        self.gun_moved = False
        self.gun_last_zone = None       # โซนที่นัด/ชุดล่าสุดโดน (gun_shoot / gun_alt_shoot)
        self.gun_tap = {"n": 0, "spam": 0, "band": {"20": [0, 0], "25": [0, 0], "30": [0, 0]},
                        "bursts": [0, 0, 0, 0], "cur": 0, "gaps": [], "last": None}
        self.gun_adad = {"mv": [0, 0], "st": [0, 0], "kill_ms": [], "mv_kills": 0}

    def gun_drill_begin(self):
        """เรียกจาก begin_gun — TAP ยืนถอยหลังเพิ่ม TAP_BACK (ให้ถึง 35 ม. ในห้อง)"""
        if self.gun_drill == "tap":
            self.cam.pos[2] -= TAP_BACK
            self.gun_origin = list(self.cam.pos)

    # ───────────────────────── เกิด ─────────────────────────
    def gun_drill_spawn(self):
        """ดวลใหม่ของดริลชุดนี้ — คืนบอท (None = ไม่ใช่ดริลของโมดูลนี้ ผู้เรียกใช้ทางเดิม)"""
        d = self.gun_drill
        if d == "angle":
            return self.gun_spawn_angle()
        if d == "peek":
            return self.gun_spawn_peek()
        if d == "tap":
            return self.gun_spawn_tap()
        if d == "adad":
            return self.gun_spawn_adad()
        return None

    def _gun_duel_dist(self, lo, hi):
        from .gunplay import duel_dist
        return _clamp(duel_dist(self.gun_weapon), lo, hi)

    # ── ANGLE: ฉาก (กล่อง + จุดโผล่) ──
    def angle_layout(self, name=None):
        """สุ่มฉาก ANGLE — คืน (กล่อง, จุดโผล่) ; จุดโผล่ = dict edge/side (ทิศจากขอบไปที่ซ่อน)/zb/y0/x_hide/max_out"""
        oz = self.gun_origin[2]
        if name is None:
            names, w = zip(*ANGLE_LAYOUTS)
            name = random.choices(names, weights=w)[0]
        D = self._gun_duel_dist(9.0, 27.0)
        cx = random.uniform(-2.5, 2.5)
        zw = min(oz + D, WALL_Z - 1.6)                 # ผิวหน้าผนังฉาก (หลังผนังต้องมีที่ให้บอทยืน)
        zb = zw + WALL_T + BEHIND
        boxes, spots = [], []
        if name in ("door", "door_crate"):
            g = random.uniform(*DOOR_HW)
            boxes += [arena.Box(-ROOM_X, cx - g, 0.0, WALL_H, zw, zw + WALL_T),
                      arena.Box(cx + g, ROOM_X, 0.0, WALL_H, zw, zw + WALL_T)]
            mo = 2 * g - DOOR_IN
            spots += [dict(edge=cx - g, side=-1, zb=zb, y0=0.0, max_out=mo, where="ประตูซ้าย"),
                      dict(edge=cx + g, side=1, zb=zb, y0=0.0, max_out=mo, where="ประตูขวา")]
            if name == "door_crate":
                s = random.choice((-1, 1))
                cw = random.uniform(*CRATE_W)
                zc = max(oz + 6.0, zw - random.uniform(*CRATE_AHEAD))
                xc = _clamp(cx + s * (g + random.uniform(0.6, 1.6) + cw / 2), -ROOM_X + cw / 2 + 1.5,
                            ROOM_X - cw / 2 - 1.5)
                boxes.append(arena.Box(xc - cw / 2, xc + cw / 2, 0.0, CRATE_H, zc, zc + CRATE_D))
                zbc = zc + CRATE_D + BEHIND
                spots += [dict(edge=xc - cw / 2, side=1, zb=zbc, y0=0.0, max_out=None, hide_in=cw / 2,
                               where="กล่องซ้าย"),
                          dict(edge=xc + cw / 2, side=-1, zb=zbc, y0=0.0, max_out=None, hide_in=cw / 2,
                               where="กล่องขวา")]
        else:                                          # ledge: ผนังมีขอบ + ยกพื้นข้างหลัง / ผนังพื้นราบอีกฝั่ง
            s1 = random.choice((-1, 1))
            h = random.uniform(*LEDGE_H)
            e1 = _clamp(cx + s1 * random.uniform(0.5, 1.5), -ROOM_X + 4.0, ROOM_X - 4.0)
            x_far = ROOM_X if s1 > 0 else -ROOM_X
            boxes.append(arena.Box(e1, x_far, 0.0, WALL_H, zw, zw + WALL_T))
            out_max = 1.4                              # เดินบนยกพื้นพ้นขอบได้ไกลสุด (ยกพื้นยื่นเลยขอบไปอีก 0.6)
            px0 = e1 + s1 * (guns.BODY_HW + 1.6)       # ยกพื้นยาวจากหลังจุดซ่อนถึงเลยขอบ
            px1 = e1 - s1 * (out_max + 0.6)
            boxes.append(arena.Box(px0, px1, 0.0, h, zw + WALL_T, zw + WALL_T + 1.3, ledge=True))
            spots.append(dict(edge=e1, side=s1, zb=zw + WALL_T + BEHIND + 0.2, y0=h, max_out=out_max,
                              where="ยกพื้น"))
            e2 = _clamp(e1 - s1 * random.uniform(3.0, 5.0), -ROOM_X + 2.5, ROOM_X - 2.5)
            zw2 = _clamp(zw + random.uniform(-3.0, 1.0), oz + 8.0, WALL_Z - 1.6)
            x_far2 = -ROOM_X if s1 > 0 else ROOM_X
            boxes.append(arena.Box(e2, x_far2, 0.0, WALL_H, zw2, zw2 + WALL_T))
            spots.append(dict(edge=e2, side=-s1, zb=zw2 + WALL_T + BEHIND, y0=0.0, max_out=None, where="มุมพื้น"))
        for sp in spots:
            sp["x_hide"] = sp["edge"] + sp["side"] * sp.get("hide_in", guns.BODY_HW + 0.8)
        return name, boxes, spots

    def _gun_hidden_from_me(self, x, z, y0, covers, crouch=0.0):
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        return not arena.any_visible(eye, guns.humanoid_points(x, z, crouch, y0), covers)

    def gun_spawn_angle(self):
        """ดวล ANGLE ใหม่: ฉากใหม่ (2–4 ขอบ) + บอทซ่อนหลังขอบหนึ่ง รอ ANGLE_WAIT แล้วโผล่ตามท่า"""
        for _try in range(8):
            name, boxes, spots = self.angle_layout()
            order = list(range(len(spots)))
            random.shuffle(order)
            pick = next((spots[k] for k in order
                         if self._gun_hidden_from_me(spots[k]["x_hide"], spots[k]["zb"], spots[k]["y0"], boxes)), None)
            if pick is not None:
                break
        self.gun_set_covers(boxes)
        self.gun_layout = {"name": name, "spots": spots}
        sp = pick if pick is not None else spots[0]
        kinds, weights = zip(*ANGLE_KINDS)
        kind = random.choices(kinds, weights=weights)[0]
        b = self._gun_peeker(sp, kind, ANGLE_WAIT)
        b.meta["spot"] = sp["where"]
        return b

    def _gun_peeker(self, sp, kind, wait):
        """บอทซ่อนที่จุดโผล่ sp แล้วโผล่ด้วยท่า kind (เดินด้วย gunbots.gun_cover_ai ตัวเดียวกับ DUEL)"""
        from .gunbots import OUT, BOT_CROUCH_P
        side, edge = sp["side"], sp["edge"]
        lo, hi = OUT[kind]
        out = random.uniform(lo, hi)
        if sp.get("max_out"):
            out = min(out, sp["max_out"])
        x_to = self._gun_room_x(edge - side * out)
        b = self.gun_new_bot(sp["x_hide"], sp["zb"], self.gun_tier_now())
        b.y0 = sp["y0"]
        m = b.meta
        m.update(kind=kind, side=side, edge=edge, dir=-side, x_hide=sp["x_hide"], x_to=x_to, phase="wait",
                 t_go=self.gt + random.uniform(*wait), max_out=sp.get("max_out"))
        if kind == "jiggle":
            m["n_jig"] = random.choice((1, 2))
            m["commit"] = random.choice(("stop", "swing"))
            m["bait"] = True
        elif kind == "crouch":
            b.crouch = b.crouch_to = 1.0
        m["crouch_fire"] = kind != "crouch" and random.random() < BOT_CROUCH_P
        self.bots.append(b)
        self.gun_start_duel(b)
        return b

    # ── PEEK: กำแพงของเรา + บอทเฝ้ามุม ──
    def peek_layout(self):
        """สุ่มดวล PEEK — คืน dict: side (ทิศโผล่ +1 ขวา/−1 ซ้าย), wall (Box), xc (จุดเริ่มเรา), bx/bz (บอท), w (ต้องเดิน
        ออกกี่ ม. หัวถึงพ้นขอบ), d (ระยะ) ; ตรวจแล้วว่าตอนเริ่มไม่เห็นกันทั้งสองฝั่ง และโผล่ในโซนเดินแล้วเห็นกันแน่"""
        ox, oz = self.gun_origin[0], self.gun_origin[2]
        s = random.choice((-1, 1))
        xe = ox + s * PEEK_EDGE_X
        zf = oz + PEEK_WALL_DZ
        wall = arena.Box(xe, -s * ROOM_X, 0.0, WALL_H, zf, zf + WALL_T)
        best = None
        for _try in range(16):
            d = self._gun_duel_dist(*PEEK_DIST)
            a = random.uniform(*PEEK_DEPTH)
            w = random.uniform(*PEEK_WIDTH)
            xc = xe - s * (a + HEAD_R)
            # เส้นสายตาตาบอท → ขอบหัวเรา ผ่านระนาบหน้ากำแพง (zf) ที่ขอบพอดีเมื่อเราเดินออกไป w ม.:
            # u (ระยะนอกขอบ) ของหัวเรา = −a + w ; ของตาบอท = ub ; เส้นตรงที่สัดส่วน f = 0.8/dz → ub = (a − w)(1 − f)/f
            dz = d
            for _it in range(3):
                f = PEEK_WALL_DZ / max(1.0, dz)
                ub = (a - w) * (1.0 - f) / f
                bx = _clamp(xe + s * ub, -ROOM_X + 0.6, ROOM_X - 0.6)
                dz = math.sqrt(max(1.0, d * d - (bx - xc) ** 2))
            bz = min(oz + dz, WALL_Z - 0.8)
            eye0 = (xc, EYE_Y, oz)
            bot_eye = (bx, EYE_Y, bz)
            start_ok = (not arena.any_visible(eye0, guns.humanoid_points(bx, bz), [wall])
                        and not arena.any_visible(bot_eye, guns.head_points(xc, oz), [wall]))
            xo = _clamp(xc + s * 2.2, ox - 2.9, ox + 2.9)             # โผล่สุดโซนเดิน = ต้องเห็นกันแน่
            out_ok = arena.any_visible(bot_eye, guns.head_points(xo, oz), [wall])
            if start_ok and out_ok and oz + 6.0 < bz:
                best = dict(side=s, wall=wall, xc=xc, bx=bx, bz=bz, w=w, d=math.hypot(bx - xc, bz - oz),
                            edge=xe, zf=zf)
                break
        if best is None:                               # ไม่น่าเกิด — มุมแคบปลอดภัย: บอทตรงหน้าไกล หลังแนวกำแพง
            xc = xe - s * 0.64
            best = dict(side=s, wall=wall, xc=xc, bx=xe - s * 1.5, bz=oz + 16.0, w=0.8, d=16.0, edge=xe, zf=zf)
        return best

    def gun_spawn_peek(self):
        """ดวล PEEK ใหม่: ย้ายเรากลับหลังกำแพงใหม่ (ความเร็ว 0) — บอทเฝ้ามุมนิ่ง เห็น "หัวเรา" แล้วยิงตาม rt ของระดับ"""
        from .gunbots import BOT_CROUCH_P
        L = self.peek_layout()
        self.gun_set_covers([L["wall"]])
        self.cam.pos[0], self.cam.pos[2] = L["xc"], self.gun_origin[2]
        self.vel = [0.0, 0.0]
        self.gun_stop_t, self.gun_moved = None, False
        b = self.gun_new_bot(L["bx"], L["bz"], self.gun_tier_now())
        m = b.meta
        crouch = random.random() < PEEK_CROUCH_P
        if crouch:
            b.crouch = b.crouch_to = 1.0
        m.update(kind="hold", holder=True, see_pts="head", phase="fight", side=L["side"], edge=L["edge"],
                 peek=L, t_go=self.gt)
        m["crouch_fire"] = not crouch and random.random() < BOT_CROUCH_P
        self.bots.append(b)
        self.gun_start_duel(b)
        return b

    def gun_peek_key(self):
        """ปุ่มที่ต้องกดเพื่อโผล่ของดวล PEEK ปัจจุบัน ('a'/'d' เมื่อหันหน้าตรง) — ไว้ให้ selftest/sim/ป้าย HUD"""
        b = (self.gun_duel or {}).get("bot")
        s = (b.meta.get("peek") or {}).get("side", 1) if b is not None else 1
        return "d" if s > 0 else "a"

    # ── TAP / ADAD: บอทโผล่จากมุมกำแพงแบบ DUEL (gun_spawn_cover) แล้วปรับท่า ──
    def gun_spawn_tap(self):
        oz = self.gun_origin[2]
        dist = random.uniform(*TAP_DIST)
        zmax = WALL_Z - 0.8 - oz
        xmin = math.sqrt(max(0.0, dist * dist - zmax * zmax))
        xf = random.choice((-1, 1)) * random.uniform(xmin, max(xmin, min(ROOM_X - 2.2, 0.45 * dist)))
        b = self.gun_spawn_cover(dist, kinds=TAP_KINDS, xf=xf)
        m = b.meta
        m.update(no_fire=True, timeout=random.uniform(*TAP_WINDOW), crouch_fire=False)
        return b

    def gun_spawn_adad(self):
        dist = self._gun_duel_dist(*ADAD_DIST)
        b = self.gun_spawn_cover(dist, kinds=(("strafe", 1.0),))
        m = b.meta
        m.update(adad="out", crouch_fire=False, stop_t=None, t_strafe=None)
        return b

    # ───────────────────────── AI ต่อเฟรม ─────────────────────────
    def gun_drill_ai(self, b, dt):
        """AI ของดริลชุดนี้ — คืน True ถ้าจัดการแล้ว (angle/tap ใช้ gun_cover_ai ของ DUEL ตรงๆ)"""
        m = b.meta
        if m.get("holder"):
            self.gun_holder_ai(b, dt)
            return True
        if m.get("adad"):
            self.gun_adad_ai(b, dt)
            return True
        return False

    def gun_holder_ai(self, b, dt):
        """บอทเฝ้ามุม (PEEK): ยืนนิ่ง — เห็นหัวเรา = เริ่มนาฬิกา (gun_bot_los) ; ไม่มีใครโผล่/ยืดเยื้อ = ดวลไม่นับ"""
        m = b.meta
        t = self.gt
        if m.get("crouch_until") is not None and t >= m["crouch_until"]:
            m["crouch_until"] = None
            b.crouch_to = 0.0
        b.update_crouch(dt)
        if ((m["los_t0"] is not None and t - m["los_t0"] > duel.DUEL_TIMEOUT)
                or (m["los_t0"] is None and t - m["spawn_t"] > PEEK_NEVER)):
            b.alive = False
            m["escaped"] = True
            m["die_t"] = t
            self.gun_duel_end("nc")
            self.gun_next_bot_at = t + random.uniform(0.4, 0.9)
            return
        run = WEAPONS[b.weapon]["run_speed"]
        movement.step(b.vel, (0.0, 0.0), movement.speed_cap(run, crouch=b.crouch_to >= 0.5), dt)
        self.gun_bot_los(b)
        self.gun_bot_try_fire(b)

    def gun_adad_ai(self, b, dt):
        """บอท ADAD: ออกจากมุม → ส่าย (ไม่ยิง) ADAD_STRAFE วิ → counter-strafe หยุด ; นิ่งแล้ว (deadzone) นาฬิกา rt เริ่ม
        → ยิงเป็นชุดจนครบ ADAD_STOP วิ → กลับไปส่าย ; เห็นกันนานเกิน ADAD_TIMEOUT = ถอย (ไม่นับ)"""
        m = b.meta
        t = self.gt
        side = m["side"]
        b.update_crouch(dt)
        ph = m["adad"]
        if ph not in ("retreat", "wait") and m["los_t0"] is not None and t - m["los_t0"] > ADAD_TIMEOUT:
            ph = m["adad"] = "retreat"
        if m["phase"] == "wait" and t >= m["t_go"]:
            m["phase"] = "out"
        wish = 0.0
        if m["phase"] == "wait":
            pass
        elif ph == "out":
            if (b.x - m["x_to"]) * m["dir"] >= 0:
                ph = m["adad"] = "strafe"
                m["t_strafe"] = t + random.uniform(*ADAD_STRAFE)
                m["turn_t"] = None
            else:
                wish = m["dir"]
        if ph == "strafe":
            if t >= m["t_strafe"]:
                ph = m["adad"] = "stop"
                m["stop_t"] = None
            else:
                wish = self._gun_strafe_wish(b)
        if ph == "stop":
            wish = self._gun_brake_wish(b)
            if m["stop_t"] is None and guns.is_accurate(b.weapon, b.speed()) and abs(b.vel[0]) <= 0.3:
                m["stop_t"] = t
                m["stop_until"] = t + random.uniform(*ADAD_STOP)
                m["e0"] = None                          # เล็งใหม่ทุกครั้งที่หยุด (คลาดนัดแรกสุ่มใหม่ แล้วหดตามเวลา)
            elif m["stop_t"] is not None and t >= m["stop_until"]:
                ph = m["adad"] = "strafe"
                m["t_strafe"] = t + random.uniform(*ADAD_STRAFE)
                m["stop_t"] = None
        if ph == "retreat":
            wish = float(side)
            if (b.x - m["x_hide"]) * side >= 0 and b.alive:
                b.alive = False
                m["escaped"] = True
                m["die_t"] = t
                self.gun_duel_end("nc")
                self.gun_next_bot_at = t + random.uniform(0.4, 0.9)
                return
        run = WEAPONS[b.weapon]["run_speed"]
        movement.step(b.vel, (wish, 0.0) if wish else (0.0, 0.0), movement.speed_cap(run), dt)
        b.x = self._gun_room_x(b.x + b.vel[0] * dt)
        self.gun_bot_los(b)
        # นาฬิกายิงของ ADAD = ตอนหยุดนิ่ง (ไม่ใช่ตอนเริ่มเห็นกัน): ระหว่างส่ายไม่มีคิวยิง
        if ph == "stop" and m["stop_t"] is not None:
            if m.get("stop_fire_for") != m["stop_t"]:
                m["stop_fire_for"] = m["stop_t"]
                m["fire_at"] = m["stop_t"] + m["p"]["rt"]
            self.gun_bot_try_fire(b)
        else:
            m["fire_at"] = None

    # ───────────────────────── ติดตามทุกเฟรม ─────────────────────────
    def gun_track_stop(self):
        """เรียกทุกเฟรมหลัง gun_move — จำเวลาที่ความเร็วเราเพิ่งเข้า deadzone หลังจากเคยเร็วเกิน (หยุดถึงยิงของ PEEK)"""
        if not guns.is_accurate(self.gun_weapon, self.gun_speed()):
            self.gun_moved = True
            self.gun_stop_t = None
        elif self.gun_moved and self.gun_stop_t is None:
            self.gun_stop_t = self.gt

    def gun_drill_frame(self):
        """เรียกทุกเฟรมหลัง AI บอท — ANGLE: วัดองศาคลาด ณ เฟรมแรกที่หัวบอทโผล่ (ไม่นับจังหวะจิ้มหลอก)"""
        if self.gun_drill != "angle":
            return
        dl = self.gun_duel
        b = dl.get("bot") if dl else None
        if b is None or dl["done"] or not b.alive or "exp_t" in dl or b.meta.get("bait"):
            return
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        if not arena.any_visible(eye, b.head_points(), self.gun_covers):
            return
        # เทียบกับ "หัวระดับยืน" ของจุดนั้น (รวมยกพื้น) — ตำแหน่งที่ควรวาง crosshair ก่อนเจอ ; หมอบโผล่ (20%) หัวต่ำลง 0.55 ม.
        # ถ้าเทียบหัวจริง คนที่วางระดับหัวยืนเป๊ะจะโดนนับว่า "เล็งสูงไป" เฉลี่ย ~0.4° ทั้งที่วางถูกแล้ว
        x, y, z = self.cam.to_cam((b.x, guns.HEAD_Y + b.y0, b.z))
        if z <= 0.05:
            h, v = 180.0, 0.0                          # หันหลังให้มุม = คลาดสุด
        else:
            h = math.degrees(math.atan2(x, z))
            v = math.degrees(math.atan2(y, math.hypot(x, z)))
        dl["exp_t"] = self.gt
        dl["exp"] = (abs(h), -v)                       # (แนวนอน |°|, แนวตั้ง crosshair − หัว: + = เล็งสูงไป)

    # ───────────────────────── ยิง ─────────────────────────
    def gun_drill_first_shot(self, dl):
        """นัดแรกของดวล (gunplay.gun_first_shot — ก่อนกระสุนตัดสิน ; ผู้เรียกเติม shot_zone หลังตัดสิน) —
        เวลา, ยิงตอนเดินไหม, หยุดถึงยิง"""
        dl["shot_t"] = self.gt
        acc = guns.is_accurate(self.gun_weapon, self.gun_speed())
        dl["shot_mv"] = not acc
        dl["shot_stop"] = (self.gt - self.gun_stop_t) if (acc and self.gun_stop_t is not None) else None

    def gun_drill_on_shot(self, fe, fe0, n=1):
        """ทุกคลิก (นัดเดี่ยว หรือชุดคลิกขวา n เม็ด) หลังกระสุนตัดสินแล้ว — fe = สเปรดจากการยิงของนัดนี้, fe0 = ของนัดแรก"""
        d = self.gun_drill
        b = (self.gun_duel or {}).get("bot")
        if d == "tap":
            tp = self.gun_tap
            tp["n"] += 1
            if fe is not None and fe0 is not None and fe > fe0 + 1e-6:
                tp["spam"] += 1
            last = tp["last"]
            gap = (self.gt - last) if last is not None else None
            if gap is not None and gap <= BURST_GAP * self.gun_fire_interval() + 1e-9:
                tp["cur"] += 1
            else:
                if tp["cur"]:
                    tp["bursts"][min(tp["cur"], 4) - 1] += 1
                tp["cur"] = 1
                if gap is not None and gap <= TAP_GAP_MAX:
                    tp["gaps"].append(gap)
            tp["last"] = self.gt
            if b is not None and b.exposed:
                dist = b.dist(self.cam)
                key = next(k for lim, k in TAP_BANDS if dist < lim)
                tp["band"][key][0] += 1
                tp["band"][key][1] += self.gun_last_zone == "head"
        elif d == "adad" and b is not None and b.exposed:
            key = "st" if guns.is_accurate(b.weapon, b.speed()) else "mv"
            self.gun_adad[key][0] += 1
            self.gun_adad[key][1] += self.gun_last_zone is not None

    def gun_drill_on_kill(self, b):
        dl = self.gun_duel
        if dl is None or dl.get("bot") is not b:
            return
        dl["pre"] = b.meta.get("t_first") is None       # ฆ่าได้ก่อนบอทยิงนัดแรก
        if self.gun_drill == "adad":
            st = b.meta.get("stop_t")
            if b.meta.get("adad") == "stop" and st is not None:
                self.gun_adad["kill_ms"].append(round((self.gt - st) * 1000))
            else:
                self.gun_adad["mv_kills"] += 1

    def gun_drill_duel_end(self, d, result):
        """ปิดดวล (gunbots.gun_duel_end) — เก็บ dict ดวลไว้สรุปตอนจบรอบ (โซนนัดแรกถูกเติมหลังกระสุนตัดสิน ซึ่งอาจเกิด
        "หลัง" ดวลปิดเพราะนัดนั้นฆ่าเลย — จึงสรุปทีหลังใน drill_records ไม่ใช่ตอนนี้) ; ANGLE ให้คะแนนวางเป้าเมื่อรอด"""
        if self.gun_drill not in ("angle", "peek"):
            return
        d["res"] = result
        self.gun_drec.append(d)
        if self.gun_drill == "angle" and "exp" in d and result != "loss":
            err = math.hypot(*d["exp"])
            pts = round(ANGLE_PTS * _clamp((ANGLE_BAD - err) / (ANGLE_BAD - ANGLE_GOOD), 0.0, 1.0))
            if pts:
                self.score += pts
                self.add_float(f"วางเป้า {err:.1f}° +{pts}", (255, 239, 176))

    def drill_records(self):
        """ดวลที่ปิดแล้วของรอบนี้ → บันทึกต่อดวลแบบแบน: res, zone (นัดแรก), angle: h/v/err/t1/pre ; peek: mv/stop/expo"""
        out = []
        for d in self.gun_drec:
            rec = {"res": d["res"]}
            b = d.get("bot")
            if "shot_t" in d:
                rec["zone"] = d.get("shot_zone")
                rec["mv"] = bool(d.get("shot_mv"))
                if d.get("shot_stop") is not None:
                    rec["stop"] = d["shot_stop"] * 1000
                los = b.meta.get("los_t0") if b is not None else None
                if los is not None and d["shot_t"] >= los:
                    rec["expo"] = (d["shot_t"] - los) * 1000
            if "exp" in d:
                h, v = d["exp"]
                rec.update(h=h, v=v, err=math.hypot(h, v))
                if "shot_t" in d and d["shot_t"] >= d["exp_t"]:
                    rec["t1"] = (d["shot_t"] - d["exp_t"]) * 1000
            if d["res"] == "win":
                rec["pre"] = bool(d.get("pre"))
            out.append(rec)
        return out

    # ───────────────────────── สรุปรอบ ─────────────────────────
    def gun_drill_fields(self, ent):
        """ตัวชี้วัดของดริลลง history entry (คีย์สั้น ; ไม่มีข้อมูล = ไม่ใส่คีย์) — ความหมายดู DRILL_KEYS"""
        d = self.gun_drill
        recs = self.drill_records()
        if d == "angle":
            ex = [r for r in recs if "err" in r]
            if ex:
                vs = [r["v"] for r in ex]
                ent["pa_n"] = len(ex)
                ent["pa_err"] = round(_median([r["err"] for r in ex]), 2)
                ent["pa_h"] = round(_median([r["h"] for r in ex]), 2)
                ent["pa_v"] = round(sum(vs) / len(vs), 2)
                ent["pa_wrong"] = sum(1 for r in ex if r["err"] >= ANGLE_BAD)
            t1 = [r["t1"] for r in recs if "t1" in r]
            if t1:
                ent["t1_ms"] = round(_median(t1))
            wins = [r for r in recs if r["res"] == "win"]
            if wins:
                ent["pre_kill"] = sum(1 for r in wins if r.get("pre"))
        elif d == "peek":
            sh = [r for r in recs if "mv" in r and r["res"] in ("win", "loss")]
            if sh:
                ent["pk_n"] = len(sh)
                ent["mv_first"] = sum(1 for r in sh if r["mv"])
                ent["fs_hs"] = sum(1 for r in sh if r.get("zone") == "head")
            ex = [r["expo"] for r in recs if "expo" in r]
            if ex:
                ent["expo_ms"] = round(_median(ex))
            st = [r["stop"] for r in recs if "stop" in r]
            if st:
                ent["stop_ms"] = round(_median(st))
                ent["stop_n"] = len(st)
            ent["pk_w"] = sum(1 for r in recs if r["res"] == "win")
            ent["pk_l"] = sum(1 for r in recs if r["res"] == "loss")
        elif d == "tap":
            tp = self.gun_tap
            bursts = list(tp["bursts"])
            if tp["cur"]:
                bursts[min(tp["cur"], 4) - 1] += 1
            if tp["n"]:
                ent["tap_n"] = tp["n"]
                ent["spam"] = tp["spam"]
                ent["band"] = {k: list(v) for k, v in tp["band"].items()}
                ent["bursts"] = bursts
            if tp["gaps"]:
                te = tap_eff(self.gun_weapon)
                ent["tap_ms"] = round(_median(tp["gaps"]) * 1000)
                ent["tap_gaps"] = len(tp["gaps"])
                ent["tap_fast"] = sum(1 for g in tp["gaps"] if te and g < 1.0 / te - 1e-9)
        elif d == "adad":
            ad = self.gun_adad
            if ad["mv"][0] or ad["st"][0]:
                ent["hit_mv"] = list(ad["mv"])
                ent["hit_st"] = list(ad["st"])
            if ad["kill_ms"]:
                ent["kill_stop_ms"] = round(_median(ad["kill_ms"]))
                ent["kill_stop_n"] = len(ad["kill_ms"])
            if ad["mv_kills"]:
                ent["kill_mv_n"] = ad["mv_kills"]
        return ent

    def gun_drill_cards(self):
        """การ์ดผลลัพธ์ 4 ใบ + บรรทัดสรุปของดริลชุดนี้ (None = ใช้การ์ด GUNFIGHT เดิม)"""
        d = self.gun_drill
        if d not in NEW_DRILLS:
            return None
        ent = self.gun_drill_fields({})
        kd = (f"{self.gun_kills}/{self.gun_deaths}", "K / D")
        hs = round(self.gun_hs / self.gun_hits * 100) if self.gun_hits else 0
        if d == "angle":
            n = ent.get("pa_n", 0)
            cards = [kd, (f"{ent['pa_err']:.1f}°" if n else "--", "วางเป้าคลาด"),
                     (f"{ent['pa_v']:+.1f}°" if n else "--", "สูง(+) / ต่ำ(−)"),
                     (f"{ent.get('pre_kill', 0)}/{self.gun_kills}", "ฆ่าก่อนบอทยิง")]
            extra = (f"เห็นหัวถึงนัดแรก {ent['t1_ms']}ms" if "t1_ms" in ent else "ยังไม่มีนัดหลังเห็นหัว")
            extra += f" · เฝ้าผิดมุม (≥{ANGLE_BAD:g}°) {ent.get('pa_wrong', 0)}/{n} · HS {hs}%"
            return cards, extra
        if d == "peek":
            w, l = ent.get("pk_w", 0), ent.get("pk_l", 0)
            pn = ent.get("pk_n", 0)
            cards = [(f"{round(100 * w / (w + l))}%" if w + l else "--", "ชนะดวล"),
                     (f"{ent['expo_ms']}ms" if "expo_ms" in ent else "--", "โผล่ถึงนัดแรก"),
                     (f"{round(100 * ent['mv_first'] / pn)}%" if pn else "--", "นัดแรกตอนยังเดิน"),
                     (f"{round(100 * ent['fs_hs'] / pn)}%" if pn else "--", "นัดแรกเข้าหัว")]
            extra = (f"หยุดถึงยิง {ent['stop_ms']}ms ({ent['stop_n']} ครั้ง · เกณฑ์คร่าว ๆ ≤{PEEK_STOP_GOOD_MS}ms)"
                     if "stop_ms" in ent
                     else "ยังไม่มีนัดที่หยุดก่อนยิง")
            extra += f" · K/D {self.gun_kills}/{self.gun_deaths} · ดวล {w}/{w + l}"
            return cards, extra
        if d == "tap":
            n = ent.get("tap_n", 0)
            band = ent.get("band") or {}
            sh = sum(v[0] for v in band.values())
            hh = sum(v[1] for v in band.values())
            te = tap_eff(self.gun_weapon)
            cards = [(f"{round(100 * hh / sh)}%" if sh else "--", "หัวโดน/นัด"),
                     (f"{round(100 * ent['spam'] / n)}%" if n else "--", "ยิงก่อนสเปรดหาย"),
                     (f"{round(100 * ent['tap_fast'] / ent['tap_gaps'])}%" if ent.get("tap_gaps") else "--",
                      "แตะเร็วเกิน"),
                     (str(self.gun_kills), "KILLS")]
            parts = [f"{k}–{int(k) + 5} ม. {round(100 * v[1] / v[0])}%" for k, v in sorted(band.items()) if v[0]]
            extra = " · ".join(parts) if parts else "ยังไม่มีนัดใส่บอทที่โผล่"
            if n:
                b = ent["bursts"]
                extra += f" · ชุด 1/2/3/4+ นัด: {b[0]}/{b[1]}/{b[2]}/{b[3]}"
            if "tap_ms" in ent and te:
                extra += f" · แตะห่าง {ent['tap_ms']}ms (ควร ≥{round(1000 / te)}ms)"
            return cards, extra
        mv, st = ent.get("hit_mv", [0, 0]), ent.get("hit_st", [0, 0])
        cards = [kd, (f"{round(100 * mv[1] / mv[0])}%" if mv[0] else "--", "โดน·บอทเดิน"),
                 (f"{round(100 * st[1] / st[0])}%" if st[0] else "--", "โดน·บอทหยุด"),
                 (f"{ent['kill_stop_ms']}ms" if "kill_stop_ms" in ent else "--", "ฆ่าหลังบอทหยุด")]
        extra = (f"ยิงตอนบอทเดิน {mv[0]} นัด / ตอนหยุด {st[0]} นัด · ฆ่าตอนหยุด {ent.get('kill_stop_n', 0)} "
                 f"ตอนเดิน {ent.get('kill_mv_n', 0)} · HS {hs}%")
        return cards, extra


# ───────────────────────── Insight (ข้ามรอบ — pure) ─────────────────────────
def _pct(p):
    return f"{100 * p:.0f}"


def drill_tips(drill, sessions, react_static_ms=None):
    """tip ของดริลชุดใหม่จาก history ของผู้ใช้เอง — ทุกคำตัดสินมี n + ช่วง 95% ; ยังแยกไม่ออก = "ยังสรุปไม่ได้"
    sessions = entry ของดริลนี้ (ปืน/ดริล/เวลาเดียวกัน กติการุ่นปัจจุบัน) เรียงเก่า → ใหม่
    สัดส่วนที่รวมนัด/ดวลข้ามรอบใช้ช่วงแบบ cluster (cluster_ratio — รอบ = cluster) ไม่ใช่ Wilson ของนัดรวม ;
    ค่าต่อรอบ (หยุดถึงยิง, ยิงตอนเดิน %) ใช้ช่วง t ข้ามรอบ ; เกณฑ์ที่ยังไม่ได้วัด (TAP_SPAM_CUT / PEEK_MOVE_CUT /
    PEEK_STOP_GOOD_MS / ANGLE_BIAS_DEG) ทุกคำตัดสินบอกว่าเป็นเกณฑ์คร่าว ๆ ; คร่อมเกณฑ์ = ยังสรุปไม่ได้ + ต้องอีก ~N"""
    tips = []
    if drill == "angle":
        rows = [e for e in sessions if e.get("pa_n")]
        if len(rows) >= 3:
            n = sum(e["pa_n"] for e in rows)
            med = _median([e["pa_err"] for e in rows])
            m, h = t_interval([e["pa_v"] for e in rows])
            if h < float("inf") and abs(m) >= ANGLE_BIAS_DEG and abs(m) > h:
                where = "สูงกว่าหัว" if m > 0 else "ต่ำกว่าหัว"
                fix = "ลด crosshair ลงมาที่ระดับหัว" if m > 0 else "ยก crosshair ขึ้นระดับหัว (ไม่ใช่อก)"
                tips.append(f"จับมุม: crosshair {where} เฉลี่ย {abs(m):.1f}° (ช่วง {abs(m) - h:.1f}–{abs(m) + h:.1f}°, "
                            f"{len(rows)} รอบ {n} ครั้ง ; เกินเกณฑ์คร่าว ๆ ครึ่งหัว {ANGLE_BIAS_DEG:.2f}°) — {fix}")
            else:
                tips.append(f"จับมุม: คลาดรวมค่ากลาง {med:.1f}° ({len(rows)} รอบ {n} ครั้ง) — ระดับหัวไม่เยื้องบน/ล่างชัด "
                            f"({m:+.1f}° ±{h:.1f})")
            p, lo, hi, _se, g, _n = cluster_ratio([(e.get("pa_wrong", 0), e["pa_n"]) for e in rows])
            wr = sum(e.get("pa_wrong", 0) for e in rows)
            tips.append(f"เฝ้าผิดมุม (บอทโผล่ห่าง crosshair ≥{ANGLE_BAD:g}°) {wr}/{n} = {_pct(p)}% ({g} รอบ, "
                        f"ช่วง {_pct(lo)}–{_pct(hi)}%) — ขอบไหนใกล้/เปิดกว้างสุดให้เฝ้าขอบนั้นก่อน")
    elif drill == "peek":
        rows = [e for e in sessions if e.get("pk_n")]
        if len(rows) >= 3:
            p, lo, hi, se, g, n = cluster_ratio([(e.get("mv_first", 0), e["pk_n"]) for e in rows])
            mv = sum(e.get("mv_first", 0) for e in rows)
            cut = f"เกณฑ์คร่าว ๆ {_pct(PEEK_MOVE_CUT)}%"
            if lo >= PEEK_MOVE_CUT:
                tips.append(f"นัดแรกยิงตอนยังเดิน {_pct(p)}% ({mv}/{n} ดวล {g} รอบ, ช่วง {_pct(lo)}–{_pct(hi)}% ; "
                            f"{cut}) — กดทิศตรงข้าม (counter-strafe) ให้นิ่งก่อนคลิก วิ่งยิงกระจาย 6°")
            elif hi <= PEEK_MOVE_CUT:
                tips.append(f"นัดแรกยิงตอนนิ่งเกือบทุกดวล ({mv}/{n} ยิงตอนเดิน, ช่วง {_pct(lo)}–{_pct(hi)}% ต่ำกว่า"
                            f"{cut}) — วินัยหยุดก่อนยิงดีแล้ว")
            else:
                more = more_needed_se(p, se, n, PEEK_MOVE_CUT, g)
                tips.append(f"นัดแรกตอนยังเดิน {mv}/{n} — ยังสรุปไม่ได้ (ช่วง {_pct(lo)}–{_pct(hi)}% คร่อม{cut}"
                            + (f", ต้องอีก ~{more} ดวล)" if more else ")"))
            # หยุดถึงยิง: ค่าต่อรอบ (ค่ากลางในรอบ) → ช่วง t ข้ามรอบ (รอบ = cluster) — เดิมตัดสินจากค่ากลางเฉย ๆ ไม่มีช่วง
            st = [e["stop_ms"] for e in rows if "stop_ms" in e]
            if len(st) >= 3:
                sm, sh = t_interval(st)
                rng = f"{sm:.0f}ms (ช่วง {max(0.0, sm - sh):.0f}–{sm + sh:.0f}, {len(st)} รอบ ; เกณฑ์คร่าว ๆ {PEEK_STOP_GOOD_MS}ms)"
                if sm + sh <= PEEK_STOP_GOOD_MS:
                    tips.append(f"หยุดถึงยิง เฉลี่ย {rng} — ยิงทันทีที่นิ่ง ดีแล้ว")
                elif sm - sh > PEEK_STOP_GOOD_MS:
                    tips.append(f"หยุดถึงยิง เฉลี่ย {rng} — นิ่งแล้วรอนานไป = ให้บอทยิงก่อนฟรี ๆ")
                else:
                    tips.append(f"หยุดถึงยิง เฉลี่ย {rng} — ยังสรุปไม่ได้ว่าเร็วพอ")
            ex = [e["expo_ms"] for e in rows if "expo_ms" in e]
            if len(ex) >= 3:
                em = _median(ex)
                if react_static_ms:
                    tips.append(f"หัวพ้นขอบถึงนัดแรก ค่ากลาง {em:.0f}ms vs reaction·static {react_static_ms:.0f}ms — "
                                f"ส่วนต่าง {em - react_static_ms:.0f}ms = เวลาหยุด+เล็ง: วาง crosshair ที่มุมก่อนโผล่")
                else:
                    tips.append(f"หัวพ้นขอบถึงนัดแรก ค่ากลาง {em:.0f}ms ({len(ex)} รอบ)")
    elif drill == "tap":
        rows = [e for e in sessions if e.get("tap_n")]
        if len(rows) >= 3:
            p, lo, hi, se, g, n = cluster_ratio([(e.get("spam", 0), e["tap_n"]) for e in rows])
            sp = sum(e.get("spam", 0) for e in rows)
            cut = f"เกณฑ์คร่าว ๆ {_pct(TAP_SPAM_CUT)}%"
            if lo >= TAP_SPAM_CUT:
                verdict = f" — เกิน{cut}: ระยะ 20 ม.+ แตะทีละนัดหรือชุด 2 นัด"
            elif hi <= TAP_SPAM_CUT:
                verdict = f" — ต่ำกว่า{cut} รอสเปรดหายก่อนยิงได้ดี"
            else:
                more = more_needed_se(p, se, n, TAP_SPAM_CUT, g)
                verdict = f" — ยังสรุปไม่ได้ (คร่อม{cut}" + (f", ต้องอีก ~{more} นัด)" if more else ")")
            tips.append(f"ยิงก่อนสเปรดกลับเป็นนัดแรก {_pct(p)}% ของนัด ({sp}/{n} นัด {g} รอบ, ช่วง {_pct(lo)}–{_pct(hi)}%)"
                        + verdict)
            parts = []
            for k in sorted({k for e in rows for k in (e.get("band") or {})}):
                per = [(e.get("band") or {}).get(k) or [0, 0] for e in rows]
                bp, blo, bhi, _bse, _bg, s = cluster_ratio([(v[1], v[0]) for v in per])
                if s >= 10:
                    parts.append(f"{k}–{int(k) + 5} ม. {_pct(bp)}% ({_pct(blo)}–{_pct(bhi)}, n {s})")
            if parts:
                tips.append("หัวโดนต่อนัด: " + " · ".join(parts))
            fp, flo, fhi, _fse, _fg, gaps = cluster_ratio([(e.get("tap_fast", 0), e.get("tap_gaps", 0)) for e in rows])
            if gaps >= 10:
                f = sum(e.get("tap_fast", 0) for e in rows)
                tips.append(f"แตะเร็วกว่าจังหวะที่สเปรดหาย {_pct(fp)}% ของช่วงแตะ ({f}/{gaps}, ช่วง {_pct(flo)}–"
                            f"{_pct(fhi)}%)")
    elif drill == "adad":
        rows = [e for e in sessions if e.get("hit_mv") or e.get("hit_st")]
        if len(rows) >= 3:
            mv = [tuple(e.get("hit_mv") or [0, 0]) for e in rows]
            st = [tuple(e.get("hit_st") or [0, 0]) for e in rows]
            pm, mlo, mhi, _sem, _gm, ms = cluster_ratio([(h, s) for s, h in mv])
            ps, slo, shi, _ses, _gs, ss = cluster_ratio([(h, s) for s, h in st])
            if ms >= 10 and ss >= 10:
                # ส่วนต่าง "โดนตอนหยุด − โดนตอนเดิน" จากรอบเดียวกัน: SE แบบ cluster ของผลต่าง ratio สองตัว
                # (ส่วนเบี่ยงต่อรอบ d_i = (h_st − ps·n_st)/ΣSt − (h_mv − pm·n_mv)/ΣMv) ; ห้ามแคบกว่าแบบนัดอิสระ
                g = len(rows)
                d = [(sh - ps * sn) / ss - (mh - pm * mn) / ms for (mn, mh), (sn, sh) in zip(mv, st)]
                se_cl = math.sqrt(g / (g - 1) * sum(x * x for x in d))
                se = max(se_cl, math.sqrt(pm * (1 - pm) / ms + ps * (1 - ps) / ss))
                t = tcrit(g - 1)
                diff = ps - pm
                if diff - t * se > 0:
                    verdict = " — ยิงตอนบอทหยุดคุ้มกว่าชัดเจน: รอจังหวะหยุดแล้วลงโทษทันที"
                elif diff + t * se < 0:
                    verdict = " — ตามบอทตอนส่ายได้ดีกว่าตอนหยุด (แปลก: เช็คว่ายิงตอนมันหยุดช้าไปไหม)"
                else:
                    # ความต่างเท่าเดิม ต้องมีนัดกี่เท่าช่วง ±t·SE ถึงไม่คร่อม 0 (SE หดตาม √n)
                    grow = (t * se / abs(diff)) ** 2 if abs(diff) > 1e-9 else None
                    more = round((ms + ss) * (grow - 1)) if grow and grow < 50 else None
                    verdict = " — ยังแยกไม่ออก" + (f" (ต้องอีก ~{more} นัด)" if more else "")
                tips.append(f"โดนตอนบอทเดิน {_pct(pm)}% ({_pct(mlo)}–{_pct(mhi)}, n {ms}) vs ตอนหยุด "
                            f"{_pct(ps)}% ({_pct(slo)}–{_pct(shi)}, n {ss} ; {g} รอบ)" + verdict)
            ks = [e["kill_stop_ms"] for e in rows if "kill_stop_ms" in e]
            if len(ks) >= 3:
                tips.append(f"ฆ่าหลังบอทหยุด ค่ากลาง {_median(ks):.0f}ms ({len(ks)} รอบ) — บอทยิงนัดแรกหลังหยุดตาม "
                            f"reaction ของระดับ (~200–500 ms) ฆ่าให้ทันก่อนนั้น")
    return tips
