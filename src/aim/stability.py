# -*- coding: utf-8 -*-
"""จำลองระบบ Stability ของ Valorant (รีคอยล์ + สเปรดจากการยิง) จากค่าจริงในไฟล์เกม — aim/riot_data.py

โมเดล (สรุปจาก blueprint: Stability_GEN_VARIABLE ของปืนแต่ละกระบอก)
  • ปืนมี "stability" 2 ตัวนับแยกกัน: n = recoil stability, e = error stability — ยิง 1 นัด +1 ทั้งคู่
  • นัดที่ยิงตอน n จะเบี่ยงจาก crosshair = (PitchRecoil.FiringCurve(n), YawRecoil.FiringCurve(n) × ทิศ)
    องศา และมีสเปรดสุ่มในกรวย Error.FiringCurve(e) องศา   (นัดแรก n=e=0 → รีคอยล์ 0, สเปรด first-bullet)
    → Vandal: นัด 2-8 ไต่ขึ้นถึง ~7.6° แล้วแกว่ง 7.5-8.4°; แกน yaw เริ่มหลังนัด ~4 โตถึง ~2° ที่นัด 12
  • crosshair ของไรเฟิล "ไม่ขยับ" — กระสุนวิ่งตาม pattern เอง ผู้เล่นดึงเมาส์ลงเพื่อให้ crosshair+pattern ทับเป้า
    กล้องมีแค่ "pop" วูบเดียวแล้วคืน (CameraPopTuning) — Sheriff กล้องตาม 80% ของรีคอยล์ (CameraFollowTuning)
    Operator ไม่มีรีคอยล์เลย มีแต่ pop 3.75° และสเปรด 5° ถ้าไม่สโคป / สโคปนัดแรก 0° นัดถัดไปในช่วงสั้น 1°
  • ทิศ yaw: สุ่มซ้าย/ขวาตอนเริ่มชุด หลัง ProtectedBulletCount นัด ทุกนัดมีโอกาส BaseYawSwitchChance สลับข้าง
    (ย่อ ×1.5) และการสลับค่อยๆ เบลนด์ใน TimeToSwitchYaw วินาที
  • หมอบ: recoil ×0.85 สเปรด ×0.85 | ADS ไรเฟิล: recoil ×0.7, สเปรด ×1.15−0.13 (Vandal → 0.1575° ตรง wiki)
  • ฟื้น (การตีความ — เกมไม่เปิดเผยสูตรตรงๆ): ภายใน 1 ช่วง fire rate ไม่ลด; หลังจากนั้นลดเป็นเส้นตรงจนเป็น 0
    ที่ T = max(1/TapEfficiency, RecoveryTimeCurve(n)) หลังนัดสุดท้าย
    → Vandal แตะ 4 นัด/วิ ทุกนัด = first bullet, สเปรย์เต็มแม็กแล้วปล่อย 0.4 วิ = รีเซ็ต (ตรงที่ผู้เล่นรู้กัน)
    → Sheriff ต้องเว้น 0.5 วิ (2 นัด/วิ) ไม่งั้นสเปรดนัดสอง 1.1° นัดสาม 2.75°
ข้อจำกัด: dump เป็น closed beta (เม.ย. 2020) — fire rate/ดาเมจแพตช์ปัจจุบันอยู่ใน guns.py แล้ว รูปทรงรีคอยล์ของ
Vandal/Phantom/Sheriff/Op ไม่มีในบันทึกแพตช์ว่าถูกแก้ จึงใช้ได้ ถ้า Riot แก้ในอนาคตให้รัน tools/riot_dump.py กับ dump ใหม่
"""
import math
import random

from .riot_data import RIOT
try:
    from .config import RECOIL_SCALE
except ImportError:      # ใช้ไฟล์เดี่ยวๆ นอกแพ็กเกจ
    RECOIL_SCALE = 1.0

POP_DURATION = 0.15          # Curve_StabilityVisualization_Pop15 — แกนเวลา 0..1 ของ pop curve = 0.15 วิ
HOLD_MAX = 0.35              # ช่วง "ยังไม่ฟื้น" หลังยิง = 1 ช่วง fire rate ×1.2 แต่ไม่เกินค่านี้ (ปืนช้าอย่าง Op)


def curve_at(keys, x):
    """linear interpolation บน [(t, v)] — นอกช่วง = ค่าปลาย (UE: RCCE_Constant)"""
    if not keys:
        return 0.0
    if x <= keys[0][0]:
        return keys[0][1]
    for i in range(1, len(keys)):
        t1, v1 = keys[i]
        if x <= t1:
            t0, v0 = keys[i - 1]
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * (x - t0) / (t1 - t0)
    return keys[-1][1]


def has(weapon):
    return weapon in RIOT and not weapon.startswith("_")


def _crouch_mult(v):
    # StabilityStateMultipliers ในไฟล์บางกระบอกเป็น 1.25-1.5 (น่าจะเป็น array ของหลายสถานะที่ dump เหลือค่าเดียว)
    # ใช้เฉพาะเมื่อเป็นตัวลด (ไรเฟิลระบุ 0.85 ชัดเจน) ไม่งั้นถือว่าหมอบไม่เปลี่ยน
    return v if (v is not None and v <= 1.0) else 1.0


class Stability:
    """สถานะรีคอยล์/สเปรดของปืน 1 กระบอกในมือผู้เล่น — เรียก shoot() ทุกนัด, update() ทุกเฟรม"""

    def __init__(self, weapon, rps):
        self.weapon = weapon
        self.row = RIOT.get(weapon) if has(weapon) else None
        self.rps = rps
        self.reset()

    def reset(self):
        self.n0 = 0.0          # recoil stability ณ นัดล่าสุด (หลัง +1)
        self.e0 = 0.0          # error stability ณ นัดล่าสุด
        self.last_shot = None
        self.burst = 0         # นัดในชุดยิงนี้ (รีเซ็ตเมื่อ n ฟื้นเป็น 0)
        self.yaw_dir = random.choice((-1.0, 1.0))
        self.yaw_mult = self.yaw_dir
        self.pitch_off = 0.0   # pattern offset ปัจจุบัน (องศา, + = สูงกว่า crosshair)
        self.yaw_off = 0.0     # (+ = ขวา)
        self.pop_t = None
        self.pop_pitch = 0.0
        self.pop_yaw = 0.0
        self._ads = False
        self._crouch = False

    # ── ตารางค่า ──
    def block(self, zoomed=False):
        if self.row is None:
            return None
        if zoomed and self.row.get("zoomed_stability"):
            return self.row["zoomed_stability"]
        return self.row["stability"]

    def _hold(self):
        return min(HOLD_MAX, 1.2 / max(0.1, self.rps))

    def _reset_time(self, st, n):
        tap = st.get("tap_eff") or 0.0
        t = max((1.0 / tap) if tap else 0.0, curve_at(st.get("recovery"), n))
        return max(t, self._hold() + 0.05)

    def _decayed(self, t):
        """(n, e) ณ เวลา t ตามโมเดลฟื้น"""
        if self.last_shot is None or self.row is None:
            return 0.0, 0.0
        st = self.block(False)
        gap = t - self.last_shot
        hold = self._hold()
        if gap <= hold:
            return self.n0, self.e0
        n_t = self._reset_time(st, self.n0)
        e_t = self._reset_time(st, self.e0)
        n = self.n0 * max(0.0, 1.0 - (gap - hold) / max(1e-6, n_t - hold))
        e = self.e0 * max(0.0, 1.0 - (gap - hold) / max(1e-6, e_t - hold))
        return n, e

    # ── ต่อเฟรม ──
    def update(self, t, dt=0.0):
        if self.row is None:
            return
        n, e = self._decayed(t)
        if self.last_shot is not None and n <= 0.0 and self.burst:
            self.burst = 0
            self.yaw_dir = random.choice((-1.0, 1.0))
            self.yaw_mult = self.yaw_dir
        # เบลนด์ทิศ yaw ตอนสลับข้าง
        st = self.block(False)
        sw = st.get("yaw_switch_time") or 0.3
        if dt > 0 and self.yaw_mult != self.yaw_dir:
            step = 2.0 * dt / sw
            self.yaw_mult = (min(self.yaw_dir, self.yaw_mult + step) if self.yaw_dir > self.yaw_mult
                             else max(self.yaw_dir, self.yaw_mult - step))
        self._recompute_offset(n, st)

    def _recompute_offset(self, n, st):
        pm = curve_at(st.get("pitch"), n)
        ym = curve_at(st.get("yaw"), n)
        if self._ads:
            pm *= st.get("pitch_ads") or 1.0
            ym *= st.get("yaw_ads") or 1.0
        if self._crouch:
            pm *= _crouch_mult(st.get("pitch_crouch"))
            ym *= _crouch_mult(st.get("yaw_crouch"))
        self.pitch_off = pm * RECOIL_SCALE
        self.yaw_off = ym * self.yaw_mult * RECOIL_SCALE

    # ── สเปรดของนัดถัดไป (ไว้วาด crosshair ถ่าง) ──
    def spread(self, t, crouch=False, ads=False, zoomed=False):
        if self.row is None:
            return 0.0
        st = self.block(zoomed)
        _, e = self._decayed(t)
        return self._error(st, e, crouch, ads and not zoomed)

    @staticmethod
    def _error(st, e, crouch, ads):
        err = curve_at(st.get("error"), e)
        if ads:
            err = err * (st.get("error_ads_mult") or 1.0) + (st.get("error_ads_add") or 0.0)
        if crouch:
            err *= _crouch_mult(st.get("error_crouch"))
        return max(0.0, err)

    # ── ยิง 1 นัด ──
    def shoot(self, t, crouch=False, ads=False, zoomed=False):
        """คืน (pitch_off, yaw_off, spread) องศา ของนัดนี้ — offset คือจุดที่กระสุนเบี่ยงจาก crosshair"""
        if self.row is None:
            return 0.0, 0.0, 0.0
        self._ads = bool(ads or zoomed)
        self._crouch = bool(crouch)
        n, e = self._decayed(t)
        if n <= 0.0:
            self.burst = 0
            self.yaw_dir = random.choice((-1.0, 1.0))
            self.yaw_mult = self.yaw_dir
        st = self.block(zoomed)
        self._recompute_offset(n, st)
        spread = self._error(st, e, crouch, ads and not zoomed)
        out = (self.pitch_off, self.yaw_off, spread)
        # นัดถัดไป — stability ไม่โตเกินปลายเส้นโค้ง (ไม่งั้นแม็กยาวๆ จะฟื้นช้ากว่าที่ RecoveryTimeCurve บอก)
        prev_pitch = self.pitch_off
        n_cap = max((st.get("pitch") or [(0, 0)])[-1][0], (st.get("yaw") or [(0, 0)])[-1][0], 1.0)
        e_cap = max((st.get("error") or [(0, 0)])[-1][0], 1.0)
        self.n0 = min(n_cap, n + 1.0)
        self.e0 = min(e_cap, e + 1.0)
        self.last_shot = t
        self.burst += 1
        prot = st.get("yaw_protected") or 0
        chance = st.get("yaw_switch") or 0.0
        if chance > 0 and self.burst > prot:
            if crouch:
                chance *= st.get("yaw_switch_crouch") or 1.0
            if random.random() < chance:
                self.yaw_dir = -self.yaw_dir
        # camera pop
        vis = self.row.get("visual") or {}
        delta = curve_at(st.get("pitch"), self.n0) - prev_pitch
        pmin = vis.get("pop_pitch_min")
        pmax = vis.get("pop_pitch_max")
        amp_p = pmin if pmin is not None else 3.0
        if pmax is not None:
            amp_p = min(pmax, max(amp_p, abs(delta)))
        ymin = vis.get("pop_yaw_min")
        amp_y = ymin if ymin is not None else 0.0
        if self._ads:
            amp_p *= vis.get("pop_ads_pitch") or 1.0
            amp_y *= vis.get("pop_ads_yaw") or 1.0
        self.pop_t = t
        self.pop_pitch = amp_p
        self.pop_yaw = amp_y * random.choice((-1.0, 1.0))
        return out

    # ── สิ่งที่ "ตา" เห็น: กล้องเด้ง (ไม่กระทบทิศกระสุน) ──
    def camera_offset(self, t):
        """(d_pitch, d_yaw) องศา ที่กล้องเบี่ยงจากทิศเล็งจริง ณ เวลา t — follow × pattern + pop"""
        if self.row is None:
            return 0.0, 0.0
        vis = self.row.get("visual") or {}
        fp = vis.get("follow_pitch") or 0.0
        fy = vis.get("follow_yaw") or 0.0
        dp = fp * self.pitch_off
        dy = fy * self.yaw_off
        if self.pop_t is not None:
            u = (t - self.pop_t) / POP_DURATION
            if 0.0 <= u <= 1.0:
                dp += self.pop_pitch * curve_at(vis.get("pop_pitch_curve") or [(0, 0), (0.01, 0.25), (1, 0)], u)
                dy += self.pop_yaw * curve_at(vis.get("pop_yaw_curve") or [(0, 0), (0.01, 0.25), (1, 0)], u)
        return dp, dy

    @staticmethod
    def shot_dir(pitch_off, yaw_off, spread):
        """ทิศกระสุนใน camera space (x ขวา, y ขึ้น, z หน้า) จาก pattern offset + สเปรดสุ่มในกรวย"""
        p = math.radians(pitch_off)
        y = math.radians(yaw_off)
        if spread > 0:
            phi = math.radians(spread) * math.sqrt(random.random())   # กระจายสม่ำเสมอบนพื้นที่กรวย
            th = random.uniform(0, 2 * math.pi)
            y += phi * math.cos(th)
            p += phi * math.sin(th)
        cp = math.cos(p)
        return (math.sin(y) * cp, math.sin(p), math.cos(y) * cp)


def pattern_table(weapon, shots, ads=False, crouch=False):
    """ตาราง (นัด, pitch°, yaw°) ของสเปรย์ต่อเนื่องแบบ deterministic (yaw ไปทางขวา ไม่สลับ) — ไว้ทดสอบ/แสดงผล"""
    st = RIOT[weapon]["stability"]
    out = []
    for i in range(shots):
        pm = curve_at(st.get("pitch"), i)
        ym = curve_at(st.get("yaw"), i)
        if ads:
            pm *= st.get("pitch_ads") or 1.0
            ym *= st.get("yaw_ads") or 1.0
        if crouch:
            pm *= _crouch_mult(st.get("pitch_crouch"))
            ym *= _crouch_mult(st.get("yaw_crouch"))
        out.append((i + 1, pm * RECOIL_SCALE, ym * RECOIL_SCALE))
    return out
