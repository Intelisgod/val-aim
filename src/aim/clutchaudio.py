# -*- coding: utf-8 -*-
"""เสียงของโหมด CLUTCH 1vN (CLUTCH_DESIGN §6 / §10.2 / §13) — array ล้วน ไม่ใช้ numpy
เป้า: เสียงบอก "ข้อมูลเดียวกับในเกมจริง" ให้ฝึกฟังเสียงได้ — ใคร/อะไร, ซ้าย-ขวา, หน้า-หลัง, ใกล้-ไกล, ชั้นบน-ล่าง, มีกำแพงคั่นไหม
• สร้างตามรูปแบบ mixer จริง (pygame.mixer.get_init: rate/ขนาด/ช่อง) — เสียงเดิมของเกม (audio._tone เขียน mono 22050
  ลง mixer stereo 44100 = สูง/สั้น 4 เท่า) ผู้ใช้คุ้นแล้ว **ห้ามแตะ** ; ของใหม่ทั้งหมดอยู่ไฟล์นี้และถูกรูปแบบ
• สังเคราะห์ครั้งเดียว (ข้อมูล float ต่อ rate เก็บ _MONO, Sound ต่อรูปแบบ mixer เก็บ _BANK) ; ต่อเฟรมทำงาน O(เสียงที่เกิด)
• mixer ทำฟิลเตอร์สดไม่ได้ → "สี" ของเสียงอบไว้ล่วงหน้าเป็นตัวแปร (variant) ต่อเสียง แล้วเลือกตอนเล่น:
    ''  ตรงหน้า/ข้าง (แห้ง)          'b' ข้างหลัง (low-pass อ่อน = ทึบลงนิด — สเตอริโอแยกหน้า/หลังเองไม่ได้)
    'm' กำแพงบัง (low-pass หนัก + ก้องสั้น) — Riot: occlusion = การกรอง ไม่ใช่ลดระยะ
    'f' ปืนไกล (ทึบ + หางก้อง = ฟังออกว่าไกล)   'u'/'d' ชั้นบน/ล่าง (เสียงเท้า: สูง-บาง / ต่ำ-ทึบ นิดหน่อย)
  ดัง/pan คิดสดทุกครั้งจากตำแหน่ง (spatial — ฟังก์ชันล้วน เทสได้ไม่ต้องมี mixer)
• ช่อง: set_num_channels(32) ครั้งเดียว + จอง 0..RESERVED-1 (Sound.play ของเสียงเดิมไม่มาหยิบช่องที่ถูกตั้ง pan ค้าง) —
  โลก 10 ช่อง, ของเราเอง 3, วาง/กู้ 2, บี๊บ spike 1 (บี๊บไม่หายเพราะช่องเต็ม)
• ทุกฟังก์ชันกันพัง: ไม่มี mixer / headless / play() คืน None = เงียบเฉย ๆ ; ไฟกะพริบ spike (blink) ทำงานแม้ไม่มีเสียง"""
import array
import math
import operator
import random
import time
from bisect import bisect_right
from itertools import accumulate, repeat, zip_longest

import pygame

from .guns import WALK_KNEE, WEAPONS

# ───────────────────────── ค่าคงที่ (ที่มา: docs/clutch_research/ext_constants.md = "ext #n") ─────────────────────────
# ระยะได้ยิน
FOOTSTEP_R = 32.0          # เท้าวิ่ง — derived: ในรัศมีระเบิด 36 ม. นิดหน่อย (ext #16 MED) ; = clutchbots.FOOTSTEP_R
SPIKE_SND_R = FOOTSTEP_R   # เริ่มวาง/กำลังกู้ range-limited (ext #10 HIGH ; รัศมี UNVERIFIED) — วางเสร็จ = ประกาศทุกคน
RELOAD_SND_R = 12.0        # รีโหลด — เดา (ext #18 UNVERIFIED)
LAND_SND_R = FOOTSTEP_R    # ลงพื้นดัง = วงเดียวกับเท้า (§13.1)
SHOT_R = 90.0              # ปืน — ได้ยินทั้งแมพ (บอททุกตัวรู้ตำแหน่งคนยิง clutchbots.SHOT_*)
BEEP_R = 60.0              # บี๊บ spike (ext #10: TG แหล่งเดียว LOW)
CUE7_R = 120.0             # เสียงเตือน 7 วิ — ทั้งแมพ (named approximation)
# ดังตามระยะ: Riot "loudness-over-distance ค่อนข้างแบน" (AV6, ext #16/§57) → ลดเป็นเส้นตรงใน dB แค่ FALL_DB ตลอดรัศมี
# (ไม่ใช่ 1/r) แต่ยังแยก 5/10/20/30 ม. ออก (ห่างกันขั้นละ ≥ 2.5 dB) — named approximation
FALL_DB = 18.0             # เท้า/รีโหลด/กู้/บี๊บ: dB ที่หายไปตอนถึงขอบรัศมี
FALL_DB_SHOT = 24.0        # ปืน (รัศมี 90 ม.): 30 ม. ≈ −6 dB, 60 ม. ≈ −15 dB
NEAR_D = 1.5               # ม. — ใกล้กว่านี้ดังเต็ม
PAN_W = 0.9                # ความกว้าง pan (1 = ข้างเดียวล้วน — หูอีกข้างได้นิดหน่อยฟังธรรมชาติกว่า)
NEAR_PAN = 0.3             # ม. แนวราบ — ใกล้กว่านี้ (บนหัว/ของตัวเอง) = กลาง
OCC_GAIN = 0.8             # กำแพงบัง: ดังลดนิดเดียว — ตัวบอกหลักคือ "อู้" (ext #17 HIGH: filtering ไม่ใช่ความดัง)
BACK_COS = -0.3            # cos มุมสัมพัทธ์ < นี้ (≈ > 107°) = ข้างหลัง
BACK_GAIN = 0.85           # ข้างหลังเบาลงนิด (เหมือนหูบังเสียงจากหลัง)
ELEV_DY = 2.2              # ม. ต่างระดับเท้า ≥ นี้ = อีกชั้น (> STEP_UP/บันไดขั้นเดียว ; ชั้นแมพ ~3 ม.+)
FAR_SHOT_D = 30.0          # ปืนไกลกว่านี้ (ไม่ถูกบัง) = ตัวแปร 'f' ทึบ + หางก้อง
# สีของตัวแปร (Hz ตัดของ one-pole × รอบ) — named approximations ; ทดสอบใน selftest ว่าเรียงความทึบถูก
BACK_FC, BACK_PASS = 2500.0, 1      # หลัง: อ่อน (4 kHz ≈ −5.5 dB) — แค่เสียความคม
MUFF_FC, MUFF_PASS = 600.0, 2       # บัง: หนัก (อู้)
FAR_FC, FAR_PASS = 1400.0, 2
# ชั้น: บน = สูงขึ้น + ตัดทุ้ม (บาง) ; ล่าง = ต่ำลง + ทุ้มหนา (ตึบผ่านพื้น) — ต่างจาก "หลัง" (ทึบแต่ pitch/ทุ้มเท่าเดิม)
UP_PITCH, UP_CUT, DOWN_PITCH, DOWN_BOOST, LOW_FC = 1.07, 0.55, 0.92, 0.8, 250.0
FAR_ECHO = (0.12, 0.40, 0.30)     # (หน่วง วิ, ป้อนกลับ, ความยาวหาง วิ) — หางก้องของปืนไกล
MUFF_ECHO = (0.07, 0.30, 0.16)
VAR_RMS = {"b": 0.85, "m": 0.75, "f": 0.8, "u": 1.0, "d": 1.0}   # ความดัง (RMS) เทียบเสียงแห้ง
STEP_KEYS = ("", "b", "m", "u", "ub", "um", "d", "db", "dm")
POS_KEYS = ("", "b", "m")
SHOT_KEYS = ("", "b", "f", "m")
# ปืน: เสียงต่อกระบอก — (ยาว วิ, crack: ดัง, τ, ความแหลม 0..1, LP Hz 0=ไม่กรอง ; body: ดัง, f0, f1, τ ; กริ่งกลไก: ดัง, Hz, τ ;
# ยอด) — named approximations ให้ "ฟังแยกกระบอกออก": Vandal crack หนัก, Phantom แน่น-เก็บเสียง, Sheriff ตูม, Ghost ป๊อบเก็บเสียง,
# Classic เบา, Operator ใหญ่สุด (ต้องฟังจริง — ดูรายงาน)
SHOT_TONE = {
    "vandal": (0.32, 0.80, 0.030, 0.65, 0.0, 0.65, 120.0, 55.0, 0.060, 0.12, 520.0, 0.050, 0.85),
    "phantom": (0.24, 0.55, 0.016, 0.20, 3500.0, 0.50, 160.0, 85.0, 0.035, 0.07, 760.0, 0.030, 0.72),
    "sheriff": (0.48, 0.90, 0.040, 0.70, 0.0, 0.80, 85.0, 40.0, 0.110, 0.14, 380.0, 0.080, 0.92),
    "ghost": (0.15, 0.30, 0.009, 0.00, 1800.0, 0.45, 200.0, 115.0, 0.025, 0.05, 950.0, 0.020, 0.55),
    "classic": (0.17, 0.60, 0.011, 0.50, 0.0, 0.35, 230.0, 140.0, 0.030, 0.07, 1150.0, 0.020, 0.62),
    "operator": (0.75, 1.00, 0.060, 0.75, 0.0, 0.95, 62.0, 28.0, 0.200, 0.16, 300.0, 0.150, 0.97),
}
# ความดังของเสียงต่าง ๆ
BOT_STEP_GAIN, BOT_SHOT_GAIN, BOT_RELOAD_GAIN, BOT_LAND_GAIN = 0.9, 1.0, 0.75, 0.9
OWN_STEP_GAIN, OWN_SHOT_GAIN, OWN_RELOAD_GAIN, DRAW_GAIN = 0.28, 0.45, 0.5, 0.45   # ของเราเบากว่าศัตรู (กลาง)
LAND_GAIN, FALL_GAIN, HURT_GAIN = 0.6, 0.9, 0.8
LAND_MIN_DROP = 1.0        # ม. — บอทตกต่ำกว่านี้ (ลงบันได/ขั้น) ไม่นับ "ลงพื้น"
# spike (ext #4 HIGH: W-Spike): บี๊บเดี่ยว → คู่ที่เหลือ 20 วิ → สามที่เหลือ 10 วิ → เสียงปิด 7 วิ (หมดเวลากู้เต็ม) ;
# เร็วขึ้นอีกทีที่ 5 วิ (ext #4 MED: DX+FD) ; อัตรา 1/2/4/8 ต่อวิเป็น LOW (ต้นทางเดียว, ext #4b/VERIFIED ข้อ 4) → ไม่ใช้
# → กลุ่มละ 1 วิ (DX "twice as fast" = 1→2 บี๊บ/วิ ตรงกับกลุ่มคู่) ; ≤ 5 วิ กลุ่มสามทุก 0.5 วิ = 1/2/3/6 บี๊บต่อวิ
BEEP_DOUBLE_LEFT, BEEP_TRIPLE_LEFT, BEEP_FAST_LEFT = 20.0, 10.0, 5.0
BEEP_PERIOD, BEEP_FAST_PERIOD = 1.0, 0.5
BEEP_STEP = 0.11           # วิ ระยะระหว่างบี๊บในกลุ่ม (ต้นถึงต้น) — named approximation
BLINK_T = 0.09             # วิ ไฟกะพริบต่อบี๊บ
SPIKE_T, CUE7_LEFT = 45.0, 7.0
PLANT_T, DEFUSE_HALF = 4.0, 3.5        # W-Spike HIGH (= clutchscen)
PLANT_TICK, DEF_PULSE = 0.25, 0.18     # วิ จังหวะติ๊กตอนวาง / จังหวะเสียงกู้
RELOAD_SEQ = ((0.0, "mag_out"), (0.55, "mag_in"), (0.85, "bolt"))   # สัดส่วนของเวลารีโหลด (ของเราเอง)

# ───────────────────────── ช่องเสียง ─────────────────────────
N_CH, RESERVED = 32, 16
_POOLS = {"world": tuple(range(0, 10)), "own": (10, 11, 12)}
CH_OBJ2, CH_OBJ, CH_SPIKE = 13, 14, 15   # ครึ่งทาง/เตือน 7 วิ/ประกาศวาง · ติ๊กวาง/เสียงกู้ · บี๊บ

_MONO = {}      # rate → {ชื่อ: {key: [float]}}
_BANK = {}      # รูปแบบ mixer → {ชื่อ: {key: Sound}}
_ST = {"setup": False, "rr": {}, "gen_ms": None}


def _beep_sched():
    """ตาราง (วินาทีที่เหลือ, จำนวนบี๊บในกลุ่ม) เรียงจาก 45 → 0 — คิดล่วงหน้าตามเวลาที่เหลือ (ไม่ลอยตามเฟรม)"""
    out, left = [], SPIKE_T
    while left > 1e-6:
        n = 1 if left > BEEP_DOUBLE_LEFT else 2 if left > BEEP_TRIPLE_LEFT else 3
        out.append((round(left, 6), n))
        left -= BEEP_PERIOD if left > BEEP_FAST_LEFT + 1e-6 else BEEP_FAST_PERIOD
    return out


BEEP_SCHED = _beep_sched()
_BEEP_KEYS = [-la for la, _ in BEEP_SCHED]


def beep_due(prev_left, left):
    """กลุ่มบี๊บล่าสุดที่ถึงกำหนด (left ≤ left_at < prev_left) — (left_at, n) หรือ None ; เฟรมกระตุกข้ามหลายกลุ่ม = เล่นแค่กลุ่มล่าสุด"""
    i0, i1 = bisect_right(_BEEP_KEYS, -prev_left), bisect_right(_BEEP_KEYS, -left)
    return BEEP_SCHED[i1 - 1] if i1 > i0 else None


# ───────────────────────── คณิตตามทิศ (ล้วน) ─────────────────────────
def gain_at(d, rng, fall_db=FALL_DB):
    """ดังตามระยะ: เส้นตรงใน dB — 0 dB ที่ ≤ NEAR_D ถึง −fall_db ที่ขอบ rng"""
    k = max(0.0, d - NEAR_D) / max(1e-6, rng - NEAR_D)
    return 10.0 ** (-fall_db * min(1.0, k) / 20.0)


def spatial(lis, yaw, src, rng, blocked=False, lis_feet=None, src_feet=None, far_d=None, fall_db=FALL_DB):
    """ผู้ฟังที่ตา lis หัน yaw (กล้อง: หน้า = (sin yaw, cos yaw), ขวา = (cos yaw, −sin yaw)) ฟังเสียงที่ src
    คืน (ดังซ้าย, ดังขวา, key ตัวแปร) หรือ None ถ้าเกิน rng ; lis_feet/src_feet = ระดับเท้าไว้บอกชั้น (None = ไม่คิดชั้น)"""
    dx, dy, dz = src[0] - lis[0], src[1] - lis[1], src[2] - lis[2]
    d = math.sqrt(dx * dx + dy * dy + dz * dz)
    if d > rng:
        return None
    cy, sy = math.cos(yaw), math.sin(yaw)
    right, fwd = dx * cy - dz * sy, dx * sy + dz * cy
    h = math.hypot(right, fwd)
    if h > NEAR_PAN:
        pan, back = PAN_W * right / h, fwd / h < BACK_COS
    else:
        pan, back = 0.0, False
    g = gain_at(d, rng, fall_db)
    key = ""
    if lis_feet is not None and src_feet is not None:
        de = src_feet - lis_feet
        key = "u" if de >= ELEV_DY else "d" if de <= -ELEV_DY else ""
    if back:
        g *= BACK_GAIN
    if blocked:
        key += "m"
        g *= OCC_GAIN
    elif far_d is not None and d >= far_d:
        key += "f"
    elif back:
        key += "b"
    a = (pan + 1.0) * math.pi / 4.0                     # equal-power ; กลาง = 1.0 ทั้งสองข้าง
    return g * math.cos(a) * math.sqrt(2.0), g * math.sin(a) * math.sqrt(2.0), key


def _pick(vs, key):
    """ตัวแปรที่ตรงสุด: key เต็ม → ตัดชั้น (บัง/หลัง/ไกล สำคัญกว่า) → เหลือแค่ชั้น → แห้ง"""
    if not vs:
        return None
    for k in (key, key.lstrip("ud"), key[:1] if key[:1] in ("u", "d") else "", ""):
        s = vs.get(k)
        if s is not None:
            return s
    return None


# ───────────────────────── สังเคราะห์ (float −1..1 ที่ rate ของ mixer) ─────────────────────────
_mul, _add, _sub = operator.mul, operator.add, operator.sub


def _scale(x, k):
    return list(map(_mul, x, repeat(k)))


def _mix(*parts):
    """(รายการ, ดีเลย์ตัวอย่าง) … → ผลรวม (ยาวเท่าตัวยาวสุด)"""
    ls = [[0.0] * off + x if off else x for x, off in parts]
    return list(map(sum, zip_longest(*ls, fillvalue=0.0)))


def _env(n, rate, tau, att=0.001):
    """ซองเสียง: ขึ้นเส้นตรง att วิ แล้วลดแบบ exp (τ วิ)"""
    if n <= 0:
        return []
    e = list(accumulate(repeat(math.exp(-1.0 / (rate * tau)), n - 1), _mul, initial=1.0))
    na = min(n, int(rate * att))
    for i in range(na):
        e[i] *= i / na
    return e


def _sweep(f0, f1, n, rate):
    """คลื่น sine ความถี่ไล่ f0 → f1 (เส้นตรง)"""
    c0, c1 = 2.0 * math.pi * f0 / rate, 2.0 * math.pi * (f1 - f0) / (rate * max(1, n))
    return list(map(math.sin, accumulate(c0 + c1 * i for i in range(n))))


def _lp(x, fc, rate, passes=1):
    a = 1.0 - math.exp(-2.0 * math.pi * fc / rate)
    b = 1.0 - a
    for _ in range(passes):
        x = list(accumulate(x, lambda y, v: b * y + a * v))
    return x


def _bright(x, k):
    """เน้นเสียงสูง (first difference) — k 0..1"""
    return list(map(_sub, x, _scale([0.0] + x[:-1], k))) if k > 0 else x


def _comb(x, delay, g, tail, rate):
    """ก้อง: y[i] = x[i] + g·y[i−d] ต่อหาง tail วิ — ทำทีละบล็อกยาว d (C-speed)"""
    d = max(1, int(rate * delay))
    y = x + [0.0] * int(rate * tail)
    for s in range(d, len(y), d):
        blk = y[s:s + d]
        y[s:s + len(blk)] = map(_add, blk, _scale(y[s - d:s - d + len(blk)], g))
    return y


def _resample(x, ratio):
    """เปลี่ยน pitch (ratio > 1 = สูง/สั้นลง) — linear interpolation"""
    n = int((len(x) - 1) / ratio)
    out = []
    ap = out.append
    for j in range(n):
        p = j * ratio
        i = int(p)
        f = p - i
        ap(x[i] + (x[i + 1] - x[i]) * f)
    return out


def _rms(x, n=None):
    x = x[:n] if n else x
    return math.sqrt(sum(map(_mul, x, x)) / max(1, len(x)))


def _norm(x, peak):
    m = max(map(abs, x)) if x else 0.0
    return _scale(x, peak / m) if m > 1e-9 else x


def _variant(x, key, rate):
    """ตัวแปรสีของเสียง x ตาม key (ตัวอักษรรวมกันได้ เช่น 'um') — ความดัง RMS ตาม VAR_RMS, ยอดไม่เกิน 0.97"""
    y = x
    if "u" in key:
        y = _resample(y, UP_PITCH)
        y = list(map(_sub, y, _scale(_lp(y, LOW_FC, rate), UP_CUT)))   # ตัดทุ้ม = บาง/สูงกว่า
    if "d" in key:
        y = _resample(y, DOWN_PITCH)
        y = list(map(_add, y, _scale(_lp(y, LOW_FC, rate, 2), DOWN_BOOST)))   # ทุ้มหนา
    if "b" in key:
        y = _lp(y, BACK_FC, rate, BACK_PASS)
    if "f" in key:
        y = _lp(_comb(y, *FAR_ECHO, rate), FAR_FC, rate, FAR_PASS)
    if "m" in key:
        y = _lp(_comb(y, *MUFF_ECHO, rate), MUFF_FC, rate, MUFF_PASS)
    want = _rms(x) * math.prod(VAR_RMS.get(c, 1.0) for c in key)
    have = _rms(y, len(x))
    y = _scale(y, want / have) if have > 1e-9 else y
    m = max(map(abs, y)) if y else 0.0
    return _scale(y, 0.97 / m) if m > 0.97 else y


def _synth(rate):
    """เสียงแห้งทั้งหมด {ชื่อ: (float list, keys ตัวแปรที่ต้องอบ)} — seed คงที่ (ไม่ยุ่ง random ของเกม)"""
    rng = random.Random(7)
    noise = [rng.uniform(-1.0, 1.0) for _ in range(rate)]

    def n_(sec):
        return max(1, int(rate * sec))

    def nz(sec, off=0):
        n = n_(sec)
        out = []
        while len(out) < n:
            out += noise[off % rate:off % rate + n - len(out)]
            off = 0
        return out

    def burst(sec, tau, amp, att=0.0005, off=0, bright=0.0, fc=0.0):
        x = list(map(_mul, nz(sec, off), _env(n_(sec), rate, tau, att)))
        x = _bright(x, bright)
        if fc:
            x = _lp(x, fc, rate)
        return _scale(_norm(x, 1.0), amp)

    def tone(f0, f1, sec, tau, amp, att=0.002, harm=0.0):
        n = n_(sec)
        s = _sweep(f0, f1, n, rate)
        if harm:
            s = list(map(_add, s, _scale(_sweep(2 * f0, 2 * f1, n, rate), harm)))
        return _scale(list(map(_mul, s, _env(n, rate, tau, att))), amp)

    def beep_tone():                                   # บี๊บ spike: แหลมสั้น ปลายไม่แตก (ซองขึ้น-ลงเส้นตรง)
        n = n_(0.065)
        s = _sweep(1650.0, 1650.0, n, rate)
        return [0.5 * v * min(1.0, i / (0.003 * rate)) * min(1.0, (n - i) / (0.012 * rate)) for i, v in enumerate(s)]

    def at(sec):
        return int(rate * sec)

    S = {}
    for w, (dur, ca, ct, cb, cf, ba, f0, f1, bt, ra, rf, rt, peak) in SHOT_TONE.items():
        crack = burst(dur, ct, ca, off=at(0.05) * len(w), bright=cb, fc=cf)
        body = tone(f0, f1, dur, bt, ba, att=0.0008)
        ring = tone(rf, rf * 0.97, dur, rt, ra, att=0.0005, harm=0.5)
        x = list(map(math.tanh, _scale(_mix((crack, 0), (body, 0), (ring, at(0.004))), 1.4)))
        S["shot_" + w] = (_norm(x, peak), SHOT_KEYS)
    for i, p in enumerate((1.0, 1.08)):                # สองเท้าสลับกัน (ไม่ให้ซ้ำเป็นเครื่องจักร)
        heel = burst(0.03, 0.004, 0.55, off=at(0.2 + 0.1 * i), bright=0.9)
        body = tone(95 * p, 55 * p, 0.10, 0.022, 0.7)
        scuff = burst(0.06, 0.018, 0.35, att=0.004, off=at(0.4 + 0.1 * i), fc=2500.0)
        S["step%d" % i] = (_norm(_mix((heel, 0), (body, 0), (scuff, at(0.012))), 0.8), STEP_KEYS)

    def click(off, f, amp=0.5):
        return _mix((burst(0.012, 0.003, amp, off=off, bright=0.8), 0), (tone(f, f, 0.03, 0.008, amp * 0.4), 0))

    mag_out = _mix((click(at(0.6), 1800.0), 0), (burst(0.07, 0.03, 0.25, att=0.01, off=at(0.65), fc=3000.0), at(0.02)))
    mag_in = _mix((click(at(0.7), 1200.0, 0.6), 0), (click(at(0.72), 1350.0, 0.5), at(0.025)))
    bolt = _mix((click(at(0.8), 2200.0, 0.55), 0), (click(at(0.82), 1900.0, 0.6), at(0.08)))
    S["mag_out"], S["mag_in"], S["bolt"] = (_norm(mag_out, 0.7), ("",)), (_norm(mag_in, 0.8), ("",)), (_norm(bolt, 0.75), ("",))
    S["reload"] = (_norm(_mix((mag_out, 0), (mag_in, at(0.35))), 0.8), POS_KEYS)   # บอท: ถอด-ใส่แม็กในเสียงเดียว
    whoosh = burst(0.18, 0.05, 0.4, att=0.06, off=at(0.3), fc=1500.0)
    S["draw"] = (_norm(_mix((whoosh, 0), (click(at(0.33), 2000.0, 0.45), at(0.13))), 0.6), ("",))
    S["draw_spike"] = (_norm(_mix((whoosh, 0), (tone(1300, 1700, 0.05, 0.03, 0.3), at(0.12))), 0.55), ("",))
    land = _mix((tone(80, 40, 0.25, 0.05, 0.8), 0), (burst(0.12, 0.03, 0.5, off=at(0.5), fc=1800.0), 0),
                (click(at(0.55), 1500.0, 0.15), at(0.03)))
    S["land"] = (_norm(land, 0.85), POS_KEYS)
    fall = _mix((list(map(math.tanh, tone(60, 28, 0.4, 0.12, 1.6))), 0),
                (burst(0.2, 0.06, 0.6, off=at(0.9), fc=2500.0), 0))
    S["fall"] = (_norm(fall, 0.95), ("",))
    hurt = _mix((tone(130, 60, 0.12, 0.05, 0.6), 0), (burst(0.12, 0.03, 0.2, att=0.002, off=at(0.15)), 0))
    S["hurt"] = (_norm(hurt, 0.7), ("",))
    bp = beep_tone()
    for k in (1, 2, 3):
        S["beep%d" % k] = (_mix(*[(bp, at(BEEP_STEP * j)) for j in range(k)]), POS_KEYS)
    S["cue7"] = (_mix((tone(700, 1900, 0.35, 0.3, 0.45, att=0.02), 0), (tone(1900, 1900, 0.2, 0.08, 0.3), at(0.33))), ("",))
    S["planted"] = (_mix((tone(988, 988, 0.14, 0.1, 0.45, harm=0.3), 0), (tone(740, 740, 0.24, 0.12, 0.45, harm=0.3), at(0.15))),
                    ("",))
    for k, f in enumerate((880.0, 1046.0, 1175.0, 1318.0)):   # ติ๊กคีย์แพดตอนวาง — สูงขึ้นทุกวินาที
        S["ptick%d" % k] = (tone(f, f, 0.05, 0.02, 0.35, harm=0.4), ("",))
    for k, f in ((1, 420.0), (2, 560.0)):                     # เสียงกู้: ครึ่งหลัง (≥ 3.5 วิ) สูงขึ้น = ฟังออกว่าเลยครึ่ง
        n = n_(0.16)
        e = _env(n, rate, 0.08, 0.01)
        bz = [0.32 * e[i] * math.sin(2 * math.pi * f * i / rate) * (0.6 + 0.4 * math.sin(2 * math.pi * 30 * i / rate))
              for i in range(n)]
        S["def%d" % k] = (bz, POS_KEYS)
    S["half"] = (tone(900, 1500, 0.12, 0.08, 0.5), POS_KEYS)
    return S


def _mono(rate):
    """{ชื่อ: {key: float list}} ต่อ rate (แคช) — วัดเวลาสร้างไว้ใน _ST['gen_ms']"""
    m = _MONO.get(rate)
    if m is None:
        t0 = time.perf_counter()
        m = {}
        for name, (x, keys) in _synth(rate).items():
            m[name] = {k: (x if k == "" else _variant(x, k, rate)) for k in keys}
        _ST["gen_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        _MONO[rate] = m
    return m


def _fmt():
    try:
        return pygame.mixer.get_init()
    except Exception:
        return None


def _enabled(game):
    return bool(_fmt()) and (getattr(game, "S", None) or {}).get("sound", True)


def _mk(mono, fmt):
    """float −1..1 (mono ที่ rate ของ mixer) → Sound ตามรูปแบบจริง (int16 / float32, 1–2 ช่อง)"""
    freq, size, ch = fmt
    ch = max(1, min(2, int(ch)))
    if abs(size) == 16:
        m = array.array("h", map(int, _scale(mono, 30000.0)))
    elif size == 32:
        m = array.array("f", mono)
    else:
        return None
    if ch == 2:
        s = array.array(m.typecode, bytes(len(m) * m.itemsize * 2))
        s[0::2] = m
        s[1::2] = m
        m = s
    return pygame.mixer.Sound(buffer=m.tobytes())


def _bank():
    fmt = _fmt()
    if not fmt:
        return None
    b = _BANK.get(fmt)
    if b is None:
        b = {}
        try:
            for name, vs in _mono(fmt[0]).items():
                b[name] = {k: _mk(x, fmt) for k, x in vs.items()}
        except Exception:
            b = {}
        _BANK[fmt] = b
    return b


def reset_mixer_state():
    """mixer เพิ่ง init ใหม่ในโปรเซสเดิม (Game ใหม่หลัง pygame.quit — เทส/เครื่องมือ): คลังเสียงเป็นของ mixer เก่า + จำนวนช่องที่
    "จอง" ค้างใน SDL_mixer (16) ทั้งที่ mixer ใหม่มี 8 ช่อง = Sound.play ของโหมดใดก็ได้ segfault → ล้างให้หมด ;
    prepare() ตั้งช่อง 32/จองใหม่เองตอนเริ่มรอบ clutch ถัดไป (audio.init_audio เรียกทุกครั้งที่สร้าง Game) ; ข้อมูล float (_MONO) เก็บไว้"""
    _BANK.clear()
    _ST["setup"] = False
    _ST["rr"] = {}
    try:
        if pygame.mixer.get_init():
            pygame.mixer.set_reserved(0)
    except Exception:
        pass


def prepare(game):
    """เริ่มรอบ: สร้างคลังเสียง (ครั้งแรก) + ช่องเสียง 32/จอง + ล้างตารางเวลาเสียงของรอบ"""
    game.cl_snd = {}
    try:
        _bank()
        if not _ST["setup"] and _fmt():
            pygame.mixer.set_num_channels(max(N_CH, pygame.mixer.get_num_channels()))
            pygame.mixer.set_reserved(RESERVED)
            _ST["setup"] = True
    except Exception:
        pass


# ───────────────────────── เล่นเสียง ─────────────────────────
def _channel(pool):
    """ช่องว่างในกอง (ไม่งั้นวนทับตัวเก่าสุด) หรือช่องคงที่ (int)"""
    try:
        if isinstance(pool, int):
            return pygame.mixer.Channel(pool)
        ids = _POOLS[pool]
        for i in ids:
            c = pygame.mixer.Channel(i)
            if not c.get_busy():
                return c
        k = _ST["rr"].get(pool, 0) % len(ids)
        _ST["rr"][pool] = k + 1
        return pygame.mixer.Channel(ids[k])
    except Exception:
        return None


def _play(game, name, vol_l, vol_r, key="", pool="world"):
    if not _enabled(game):
        return None
    snd = _pick((_bank() or {}).get(name), key)
    if snd is None:
        return None
    ch = _channel(pool)
    if ch is None:
        return None
    try:
        ch.play(snd)
        ch.set_volume(max(0.0, min(1.0, vol_l)), max(0.0, min(1.0, vol_r)))   # หลัง play (play รีเซ็ตระดับเสียง)
    except Exception:
        return None
    return ch


def _own(game, name, gain, pool="own"):
    return _play(game, name, gain, gain, "", pool)


def play_at(game, name, pos, rng, gain=1.0, spike=False, pool=None, lift=1.0, feet=None, far_d=None, fall_db=FALL_DB):
    """เสียงที่ตำแหน่งโลก pos: pan ตามทิศ, ดังตามระยะ, หลัง = ทึบนิด, กำแพงบัง = อู้, ต่างชั้น = สีเปลี่ยน ; เกิน rng = ไม่ได้ยิน
    lift = ยกจุดปลายรังสีบัง (เสียงจากเท้า → ระดับอก) ; feet = y ระดับเท้าของแหล่ง (บอกชั้น) ; far_d = ระยะเริ่มตัวแปร 'f'"""
    try:
        cam = game.cam
        p = cam.pos
        if (pos[0] - p[0]) ** 2 + (pos[1] - p[1]) ** 2 + (pos[2] - p[2]) ** 2 > rng * rng:
            return None
        cm = getattr(game, "cmap", None)
        q = (pos[0], pos[1] + lift, pos[2])
        near = abs(q[0] - p[0]) + abs(q[2] - p[2]) < 0.5
        blocked = cm is not None and not near and cm.blocked((p[0], p[1], p[2]), q)
        lf = getattr(game, "cl_feet", None) if feet is not None else None
        r = spatial(p, cam.yaw, pos, rng, blocked, lf, feet, far_d, fall_db)
        if r is None:
            return None
        return _play(game, name, r[0] * gain, r[1] * gain, r[2], pool or (CH_SPIKE if spike else "world"))
    except Exception:
        return None


def _bot_at(game, pos, r=0.6):
    """บอทที่ยืนตรงจุด pos (event ไม่ส่งตัวบอทมา) — O(จำนวนบอท)"""
    best, bd = None, r * r
    for b in getattr(game, "bots", None) or ():
        d = (b.x - pos[0]) ** 2 + (b.z - pos[2]) ** 2
        if d <= bd:
            best, bd = b, d
    return best


def gunshot(game, pos, weapon=None):
    """เสียงปืนบอทที่ปากกระบอก pos — weapon = กระบอกของบอท (None = หาจากบอทที่ยืนตรงนั้น, ไม่เจอ = Vandal)"""
    try:
        if weapon is None:
            b = _bot_at(game, pos, 1.0)
            weapon = getattr(b, "weapon", None)
        name = "shot_" + (weapon if weapon in SHOT_TONE else "vandal")
    except Exception:
        name = "shot_vandal"
    return play_at(game, name, pos, SHOT_R, BOT_SHOT_GAIN, lift=0.0, far_d=FAR_SHOT_D, fall_db=FALL_DB_SHOT)


def step(game, pos, bot=None):
    """เสียงเท้าบอท (event "step" มาเฉพาะบอทวิ่ง — จังหวะตามความเร็วมาจาก clutchbots) ; บอทเดิน (meta walk) = เงียบเสมอ"""
    try:
        b = bot if bot is not None else _bot_at(game, pos)
        if b is not None and (getattr(b, "meta", None) or {}).get("walk"):
            return None
        st = getattr(game, "cl_snd", None)
        k = 0
        if st is not None:
            ft = st.setdefault("foot", {})
            k = ft[id(b)] = 1 - ft.get(id(b), 1)
    except Exception:
        k = 0
    return play_at(game, "step%d" % k, pos, FOOTSTEP_R, BOT_STEP_GAIN, feet=pos[1])


def reload(game, pos):
    return play_at(game, "reload", pos, RELOAD_SND_R, BOT_RELOAD_GAIN, feet=pos[1])


def hurt(game):
    return _own(game, "hurt", HURT_GAIN)


def blink(game):
    """0..1 แสงกะพริบของ spike ตามจังหวะบี๊บ (กลุ่มคู่/สาม = กะพริบตามจำนวน) — GL/HUD วาดไฟแดง ; ไม่ต้องมี mixer"""
    st = getattr(game, "cl_snd", None) or {}
    dt = game.gt - st.get("beep_at", -9.0)
    if dt < 0.0:
        return 0.0
    i = min(st.get("beep_n", 1) - 1, int(dt / BEEP_STEP))
    return max(0.0, 1.0 - (dt - i * BEEP_STEP) / BLINK_T)


# ───────────────────────── ต่อเฟรม ─────────────────────────
def _changed(st, key, v):
    """ค่าเปลี่ยนจากที่เห็นครั้งก่อน (ครั้งแรกของรอบ = จำไว้เฉย ๆ ไม่นับ)"""
    old = st.get(key, _changed)
    st[key] = v
    return old is not _changed and old != v


def _tick_own(game, st):
    """เสียงของเราเอง (กลาง, เบากว่าศัตรู): ยิง, ชักอาวุธ, รีโหลด, เท้าวิ่ง, ลงพื้น, ตกเจ็บ — อ่านจาก attribute ของโหมด (§13.2)"""
    g = game.gt
    shots = getattr(game, "gun_shots", 0)
    old = st.get("shots")
    st["shots"] = shots
    if old is not None and shots > old:
        _own(game, "shot_" + (game.gun_weapon if game.gun_weapon in SHOT_TONE else "vandal"), OWN_SHOT_GAIN)
    eu = getattr(game, "cl_equip_until", 0.0)
    if _changed(st, "eq_u", eu) and eu > g - 1e-6:
        _own(game, "draw_spike" if getattr(game, "cl_equip", "gun") == "spike" else "draw", DRAW_GAIN)
    ru = getattr(game, "gun_reload_until", 0.0)
    if _changed(st, "rl_u", ru):
        st["rl"] = []
        if ru > g:
            dur = WEAPONS.get(game.gun_weapon, {}).get("reload", 2.0)
            st["rl"] = [(ru - dur + f * dur, nm) for f, nm in RELOAD_SEQ]
    q = st.get("rl")
    while q and g >= q[0][0]:
        _own(game, q.pop(0)[1], OWN_RELOAD_GAIN)
    if _changed(st, "land_t", getattr(game, "cl_land_t", -9.0)) and getattr(game, "cl_land_loud", True):
        _own(game, "land", LAND_GAIN)                   # ลงพื้นเงียบ (Shift) = ไม่มีเสียง ; กระโดดขึ้น = เงียบเสมอ (§13.1)
    if _changed(st, "fall_t", getattr(game, "cl_fall_dmg_t", -9.0)):
        _own(game, "fall", FALL_GAIN)
    # เท้าวิ่ง: เกณฑ์เดียวกับที่บอทได้ยินเรา (clutchbots._hear_steps) — ได้ยินเท้าตัวเอง = ศัตรูก็ได้ยิน
    if (getattr(game, "cl_dead", False) or game.cl_plant_t0 is not None or game.cl_defuse_t0 is not None
            or getattr(game, "cl_air", False)):
        return
    v = getattr(game, "vel", None) or (0.0, 0.0)
    sp = math.hypot(v[0], v[1])
    run = max(0.1, game.gun_run_speed())
    if sp > WALK_KNEE * run + 1e-6 and g - st.get("own_step", -9.0) >= 0.22 + 0.18 * (1.0 - min(1.0, sp / run)):
        st["own_step"] = g
        st["own_foot"] = k = 1 - st.get("own_foot", 1)
        _own(game, "step%d" % k, OWN_STEP_GAIN)


def _tick_bots(game, st):
    """บอทตกจากที่สูงแล้วลงพื้น (meta air) = เสียงลงพื้นตามทิศ (ไม่มี event นี้จากสมองบอท)"""
    air = st.setdefault("bair", {})
    for b in getattr(game, "bots", None) or ():
        m, k = getattr(b, "meta", None) or {}, id(b)
        if not b.alive:
            air.pop(k, None)
        elif m.get("air"):
            air.setdefault(k, b.y0)
        elif k in air:
            y0 = air.pop(k)
            if y0 - b.y0 >= LAND_MIN_DROP and not m.get("walk"):
                play_at(game, "land", (b.x, b.y0, b.z), LAND_SND_R, BOT_LAND_GAIN, feet=b.y0)


def _tick_spike(game, st):
    """spike: ประกาศวางเสร็จ, บี๊บตามตาราง (เดี่ยว/คู่/สาม), เตือน 7 วิ, ติ๊กตอนวาง, เสียงกู้ (เรา/บอท) + ครึ่งทาง 3.5 วิ"""
    sp, g = game.cl_spike, game.gt
    if sp is None:
        return
    over = game.cl_result is not None
    state = sp.get("state")
    prev = st.get("sp_state")
    st["sp_state"] = state
    spos = (sp["x"], sp["y"], sp["z"])
    if state == "planted" and not over:
        if prev == "carried":
            _own(game, "planted", 0.8, CH_OBJ2)         # วางเสร็จ = รู้ทั้งแมพ (§10.2)
        left = sp["left"]
        bl = st.get("bl")
        due = beep_due(left + 1e-6 if bl is None else bl, left)
        st["bl"] = left
        if due is not None:
            st["beep_at"], st["beep_n"] = g - max(0.0, due[0] - left), due[1]
            play_at(game, "beep%d" % due[1], spos, BEEP_R, 0.9, pool=CH_SPIKE, lift=0.4, feet=spos[1])
        if left <= CUE7_LEFT and not st.get("cue7"):
            st["cue7"] = True
            play_at(game, "cue7", spos, CUE7_R, 1.0, pool=CH_OBJ2, lift=0.4)
    t0 = game.cl_plant_t0
    if t0 is not None:                                  # วาง (ผู้เล่น ATK): ติ๊กคีย์แพดทุก 0.25 วิ สูงขึ้นทุกวินาที
        if st.get("pt0") != t0:
            st["pt0"], st["pk"] = t0, -1
        k = int((g - t0) / PLANT_TICK)
        if k > st["pk"] and g - t0 < PLANT_T:
            st["pk"] = k
            _own(game, "ptick%d" % min(3, int(g - t0)), 0.6, CH_OBJ)
    if game.cl_defuse_t0 is not None:                   # เรากู้ (DEF)
        prog = game.clutch_defuse_prog()
        hp = st.get("half_p", prog)
        st["half_p"] = prog
        if hp < DEFUSE_HALF <= prog:
            _own(game, "half", 0.8, CH_OBJ2)
        if g >= st.get("def_t", -1.0):
            st["def_t"] = g + DEF_PULSE
            _own(game, "def2" if prog >= DEFUSE_HALF else "def1", 0.55, CH_OBJ)
    else:
        st.pop("half_p", None)
    bd = getattr(game, "cl_bot_defuse", None)
    if bd is not None and not over:                     # บอทกู้ (ATK หลังวาง): ตามทิศที่ spike, ได้ยินเฉพาะใน SPIKE_SND_R
        prog = bd[1]
        hp = st.get("bhalf_p", prog)
        st["bhalf_p"] = prog
        if hp < DEFUSE_HALF <= prog:
            play_at(game, "half", spos, SPIKE_SND_R, 0.9, pool=CH_OBJ2, lift=0.4, feet=spos[1])
        if g >= st.get("bdef_t", -1.0):
            st["bdef_t"] = g + DEF_PULSE
            play_at(game, "def2" if prog >= DEFUSE_HALF else "def1", spos, SPIKE_SND_R, 0.8, pool=CH_OBJ, lift=0.4,
                    feet=spos[1])
    else:
        st.pop("bhalf_p", None)


def update(game, dt):
    """ตารางเสียงต่อเฟรม (§13.2: AUDIO อ่าน attribute ของโหมดเอง) — แต่ละส่วนพังแยกกัน ไม่ล้มเฟรมของเกม"""
    st = getattr(game, "cl_snd", None)
    if st is None:
        st = game.cl_snd = {}
    for fn in (_tick_spike, _tick_own, _tick_bots):
        try:
            fn(game, st)
        except Exception as ex:
            w = getattr(game, "_warn_once", None)
            if w is not None:
                w("clutchaudio_" + fn.__name__, f"CLUTCH: เสียงพัง ({type(ex).__name__}: {ex})")


# ───────────────────────── selftest ─────────────────────────
def _hf(x, rate=44100, fc=2000.0):
    """สัดส่วนพลังงานเหนือ ~2 kHz (x − low-pass 2 รอบ) — ตัววัดความ "สว่าง/คม" ของเสียง"""
    d = list(map(_sub, x, _lp(x, fc, rate, 2)))
    return sum(map(_mul, d, d)) / max(1e-12, sum(map(_mul, x, x)))


def _lf(x, rate):
    """สัดส่วนพลังงานทุ้ม (< LOW_FC) — ตัววัดความ "หนา" ของเสียง"""
    lo = _lp(x, LOW_FC, rate, 2)
    return sum(map(_mul, lo, lo)) / max(1e-12, sum(map(_mul, x, x)))


def selftest():
    """คณิตตามทิศ/ระยะ/บัง/ชั้น, ความทึบของตัวแปร, ตารางบี๊บ 45 → 0, เสียงปืนครบ 6 กระบอก, ไม่มี mixer ไม่พัง ; คืนรายการ error"""
    E = []
    try:
        o, y0 = (0.0, 1.65, 0.0), 0.0
        # ── pan: หัน +z ; ขวา = +x ──
        r = spatial(o, 0.0, (10.0, 0.0, 0.0), FOOTSTEP_R)
        l_ = spatial(o, 0.0, (-10.0, 0.0, 0.0), FOOTSTEP_R)
        if not (r and l_ and r[1] > 3 * r[0] and l_[0] > 3 * l_[1] and r[2] == "" and l_[2] == ""):
            E.append(f"clutchaudio: pan ซ้าย/ขวาผิด {r} {l_}")
        ry = spatial(o, math.pi / 2, (10.0, 0.0, 0.0), FOOTSTEP_R)          # หันไป +x → เสียงที่ +x อยู่ตรงหน้า
        if not (ry and abs(ry[0] - ry[1]) < 1e-6 and ry[2] == ""):
            E.append(f"clutchaudio: หมุน yaw แล้วเสียงหน้าไม่อยู่กลาง {ry}")
        f = spatial(o, 0.0, (0.0, 0.0, 10.0), FOOTSTEP_R)
        bk = spatial(o, 0.0, (0.0, 0.0, -10.0), FOOTSTEP_R)
        if not (f and bk and f[2] == "" and bk[2] == "b" and abs(bk[0] - bk[1]) < 1e-6 and bk[0] < f[0]):
            E.append(f"clutchaudio: หน้า/หลังแยกไม่ออก {f} {bk}")
        side = spatial(o, 0.0, (10.0, 0.0, -1.0), FOOTSTEP_R)
        if not side or side[2] != "":
            E.append(f"clutchaudio: ข้างตัว (มุม ~96°) ไม่ควรเป็นเสียงหลัง {side}")
        m = spatial(o, 0.0, (0.0, 0.0, 10.0), FOOTSTEP_R, blocked=True)
        if not (m and m[2] == "m" and abs(m[0] - f[0] * OCC_GAIN) < 1e-9):
            E.append(f"clutchaudio: กำแพงบังต้องอู้ ('m') + ดัง ×{OCC_GAIN} {m}")
        # ── ชั้น ──
        up = spatial(o, 0.0, (0.0, 3.0, 8.0), FOOTSTEP_R, lis_feet=y0, src_feet=3.0)
        dn = spatial(o, 0.0, (0.0, -3.0, -8.0), FOOTSTEP_R, lis_feet=y0, src_feet=-3.0)
        dm = spatial(o, 0.0, (0.0, -3.0, 8.0), FOOTSTEP_R, blocked=True, lis_feet=y0, src_feet=-3.0)
        same = spatial(o, 0.0, (0.0, 1.0, 8.0), FOOTSTEP_R, lis_feet=y0, src_feet=1.0)
        if not (up and dn and dm and same and up[2] == "u" and dn[2] == "db" and dm[2] == "dm" and same[2] == ""):
            E.append(f"clutchaudio: ชั้นบน/ล่างผิด {up} {dn} {dm} {same}")
        # ── ระยะ: 5/10/20/30 ม. แยกออก (≥ 2 dB ต่อขั้น), เกินรัศมี = เงียบ ──
        gs = [spatial(o, 0.0, (0.0, 1.65, d), FOOTSTEP_R)[0] for d in (5.0, 10.0, 20.0, 30.0)]
        db = [20 * math.log10(gs[i] / gs[i + 1]) for i in range(3)]
        if min(db) < 2.0 or spatial(o, 0.0, (0.0, 1.65, 33.0), FOOTSTEP_R) is not None:
            E.append(f"clutchaudio: ดังตามระยะแยกไม่ออก {[round(x, 1) for x in db]} dB")
        if abs(20 * math.log10(gain_at(FOOTSTEP_R, FOOTSTEP_R)) + FALL_DB) > 1e-6 or gain_at(1.0, 32.0) != 1.0:
            E.append("clutchaudio: gain_at ปลายทางผิด")
        fr = spatial(o, 0.0, (0.0, 1.65, 40.0), SHOT_R, far_d=FAR_SHOT_D, fall_db=FALL_DB_SHOT)
        nr = spatial(o, 0.0, (0.0, 1.65, 10.0), SHOT_R, far_d=FAR_SHOT_D, fall_db=FALL_DB_SHOT)
        if not (fr and nr and fr[2] == "f" and nr[2] == ""):
            E.append(f"clutchaudio: ปืนไกลต้องเป็นตัวแปร 'f' {fr} {nr}")
        if _pick({"": 1, "m": 2, "u": 3}, "um") != 2 or _pick({"": 1, "u": 3}, "ub") != 3 or _pick({"": 1}, "f") != 1:
            E.append("clutchaudio: _pick ลำดับถอยผิด")
        # ── ตารางบี๊บ: เดินเวลา 45 → 0 ด้วยเฟรม 144 Hz ──
        left, prev, got = SPIKE_T, None, []
        while left > 0.0:
            d = beep_due(left + 1e-6 if prev is None else prev, left)
            prev = left
            if d:
                got.append(d)
            left = max(0.0, left - 1.0 / 144)
        cnt = {n: sum(1 for _, k in got if k == n) for n in (1, 2, 3)}
        bad = [(la, n) for la, n in got if n != (1 if la > 20 else 2 if la > 10 else 3)]
        gaps = {round(got[i][0] - got[i + 1][0], 6) for i in range(len(got) - 1)}
        if (cnt != {1: 25, 2: 10, 3: 15} or bad or got[0] != (45.0, 1) or gaps != {1.0, 0.5}
                or [la for la, _ in got if la <= 5.0] != [5.0 - 0.5 * i for i in range(10)]):
            E.append(f"clutchaudio: ตารางบี๊บผิด {cnt} {bad[:3]} {sorted(gaps)}")
        if beep_due(21.0, 19.5) != (20.0, 2) or beep_due(3.2, 1.9) != (2.0, 3):   # เฟรมกระตุก = กลุ่มล่าสุดกลุ่มเดียว
            E.append("clutchaudio: beep_due ตอนเฟรมกระตุกผิด")
        # ── คลังเสียง (float) + ความทึบของตัวแปร ──
        rate = 44100
        mono = _mono(rate)
        miss = [w for w in WEAPONS if "shot_" + w not in mono]
        if miss or any(set(mono["shot_" + w]) != set(SHOT_KEYS) for w in SHOT_TONE):
            E.append(f"clutchaudio: เสียงปืนไม่ครบ {miss}")
        ln = {w: len(mono["shot_" + w][""]) for w in SHOT_TONE}
        if not (ln["operator"] > ln["sheriff"] > ln["vandal"] > ln["phantom"] > ln["classic"] > ln["ghost"]):
            E.append(f"clutchaudio: ความยาวเสียงปืนเรียงผิด {ln}")
        hf = {w: _hf(mono["shot_" + w][""]) for w in SHOT_TONE}
        if not (hf["ghost"] < hf["vandal"] and hf["phantom"] < hf["vandal"] and hf["operator"] < hf["classic"]):
            E.append(f"clutchaudio: สีเสียงปืน (เก็บเสียง/หนัก) ผิด { {k: round(v, 3) for k, v in hf.items()} }")
        st_ = mono["step0"]
        h = {k: _hf(st_[k]) for k in STEP_KEYS}
        lo = {k: _lf(st_[k], rate) for k in STEP_KEYS}
        if not (h[""] > h["b"] > h["m"] and h["u"] > h[""] and h["db"] < h["d"] and h["um"] < h["u"]
                and 0.18 < h["b"] / h[""] < 0.63):                                 # หลัง = ทึบแค่ "อ่อน" (−2..−7.5 dB)
            E.append(f"clutchaudio: ความทึบตัวแปรเท้าเรียงผิด { {k: round(v, 4) for k, v in h.items()} }")
        if not (lo["d"] > lo[""] > lo["u"] and lo["d"] > lo["b"] and abs(lo["b"] - lo[""]) < abs(lo["d"] - lo[""])):
            E.append(f"clutchaudio: ทุ้มของชั้นล่าง/บนผิด (ต้องแยกจาก 'หลัง') { {k: round(v, 3) for k, v in lo.items()} }")
        for nm in ("shot_vandal", "shot_operator"):
            s = mono[nm]
            if not (len(s["f"]) > len(s[""]) and len(s["m"]) > len(s[""]) and _hf(s["m"]) < _hf(s["f"]) < _hf(s[""])):
                E.append(f"clutchaudio: {nm} ไกล/บัง ต้องทึบ + มีหางก้อง")
        if any(max(map(abs, x)) > 0.98 for vs in mono.values() for x in vs.values()):
            E.append("clutchaudio: มีเสียงเกิน 0.98 (จะ clip)")
        # ── ไม่มี mixer / ปิดเสียง: ทุกทางเงียบ ไม่พัง ; blink ยังทำงาน ──
        E += _selftest_nomixer()
        if pygame.mixer.get_init():
            b = _bank() or {}
            if len(b) != len(mono) or any(s is None for vs in b.values() for s in vs.values()):
                E.append("clutchaudio: สร้าง Sound จากคลังไม่ครบ")
        print(f"CLUTCH AUDIO bank: {sum(len(v) for v in mono.values())} sounds / {len(mono)} names, "
              f"synth {_ST['gen_ms']} ms @ {rate} Hz")
        if (_ST["gen_ms"] or 0) > 3000:
            E.append(f"clutchaudio: สร้างคลังเสียงช้าเกิน ({_ST['gen_ms']} ms)")
    except Exception as ex:
        import traceback
        E.append(f"clutchaudio selftest พัง: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    return E


class _FakeCam:
    def __init__(self):
        self.pos, self.yaw = [0.0, 1.65, 0.0], 0.0


class _FakeBot:
    def __init__(self, x, z, weapon="sheriff"):
        self.x, self.z, self.y0, self.alive, self.weapon = x, z, 0.0, True, weapon
        self.meta = {"air": False, "walk": False}


class _FakeGame:
    """พอให้ update/เสียงต่าง ๆ เดินได้ (ไม่ใช่ Game จริง)"""
    def __init__(self):
        self.S, self.cam, self.cmap, self.gt = {"sound": True}, _FakeCam(), None, 0.0
        self.bots = [_FakeBot(5.0, 5.0), _FakeBot(-3.0, 8.0, "operator")]
        self.cl_spike = {"state": "carried", "x": 2.0, "y": 0.0, "z": 3.0, "left": None}
        self.cl_result = self.cl_plant_t0 = self.cl_defuse_t0 = self.cl_bot_defuse = None
        self.cl_feet, self.cl_dead, self.cl_air, self.cl_equip, self.cl_equip_until = 0.0, False, False, "gun", 0.0
        self.cl_land_t, self.cl_land_loud, self.cl_fall_dmg_t, self.cl_defuse_base = -9.0, True, -9.0, 0.0
        self.gun_shots, self.gun_weapon, self.gun_reload_until, self.vel = 0, "vandal", 0.0, [0.0, 0.0]
        self.warn = []

    def gun_run_speed(self):
        return 5.4

    def clutch_defuse_prog(self):
        return 0.0 if self.cl_defuse_t0 is None else min(7.0, self.cl_defuse_base + self.gt - self.cl_defuse_t0)

    def _warn_once(self, k, msg):
        self.warn.append(msg)


def _selftest_nomixer():
    """รอบจำลองสั้น ๆ โดยบังคับ "ไม่มี mixer" — ห้ามพัง, ไม่มีเสียงไหนคืนช่อง, ไฟกะพริบตามบี๊บ"""
    global _fmt
    E, keep = [], _fmt
    try:
        _fmt = lambda: None                                  # noqa: E731 — จำลองเครื่องไม่มี mixer
        g = _FakeGame()
        prepare(g)
        outs = [gunshot(g, (5.0, 1.5, 5.0)), gunshot(g, (1.0, 1.5, 1.0), weapon="ghost"), step(g, (5.0, 0.0, 5.0)),
                reload(g, (5.0, 0.0, 5.0)), hurt(g)]
        dt, blinks = 1.0 / 60, 0.0
        for i in range(60 * 12):
            g.gt += dt
            if i == 30:
                g.gun_shots, g.cl_equip_until, g.gun_reload_until = 3, g.gt + 1.0, g.gt + 2.5
                g.cl_land_t, g.cl_fall_dmg_t, g.vel = g.gt, g.gt, [5.4, 0.0]
            if i == 60:
                g.cl_plant_t0 = g.gt
            if i == 60 + 240:
                g.cl_plant_t0 = None
                g.cl_spike.update(state="planted", left=SPIKE_T)
            if i == 400:
                g.cl_bot_defuse = (g.bots[0], 0.0)
                g.bots[1].meta["air"] = True
                g.bots[1].y0 = 2.0
            if i == 401:
                g.bots[1].meta["air"], g.bots[1].y0 = False, 0.0
            if g.cl_spike["state"] == "planted":
                g.cl_spike["left"] = max(0.0, g.cl_spike["left"] - dt)
            if g.cl_bot_defuse is not None:
                g.cl_bot_defuse = (g.bots[0], g.cl_bot_defuse[1] + dt)
            update(g, dt)
            blinks = max(blinks, blink(g))
        if any(o is not None for o in outs) or g.warn:
            E.append(f"clutchaudio: ไม่มี mixer ต้องเงียบไม่พัง {outs} {g.warn[:2]}")
        if blinks < 0.5 or g.cl_snd.get("beep_n") != 1:
            E.append("clutchaudio: ไฟกะพริบ spike ต้องทำงานแม้ไม่มี mixer")
        if g.cl_snd.get("pk") != 15 or g.cl_snd.get("rl"):
            E.append(f"clutchaudio: ตารางติ๊กวาง/รีโหลดผิด pk={g.cl_snd.get('pk')} rl={g.cl_snd.get('rl')}")
        g.S["sound"] = False                                 # ปิดเสียงในตั้งค่า (มี mixer ก็ต้องเงียบ)
        _fmt = keep
        if gunshot(g, (5.0, 1.5, 5.0)) is not None or hurt(g) is not None:
            E.append("clutchaudio: ปิดเสียงแล้วยังเล่น")
    except Exception as ex:
        E.append(f"clutchaudio: ไม่มี mixer แล้วพัง {type(ex).__name__}: {ex}")
    finally:
        _fmt = keep
    return E
