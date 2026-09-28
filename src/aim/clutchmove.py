# -*- coding: utf-8 -*-
"""CLUTCH 1vN — การเคลื่อนที่ของผู้เล่นแบบเกมจริง (ClutchMoveMixin ของ ClutchMixin ; แยกจาก clutch.py ให้ไฟล์ < 700 บรรทัด)
ตาม docs/CLUTCH_DESIGN.md §13.1/§13.2 — ค่าคงที่อยู่ clutchscen.py บล็อก "กระโดด/ตก" (ที่มา/ความไม่แน่นอนเขียนไว้ที่นั่น)
• บนพื้น = movement.step + ClutchMap.move ของ player_map() (หลังกล่องยืนได้ — บอท/nav ใช้ตัวด่านเดิม ไม่เปลี่ยน) ;
  ลงต่ำกว่าเท้า ≤ STEP_UP (บันได/ทางลาด) = เท้าติดพื้นตามลงทันที ไม่นับเป็น "ลอย" ; ตกขอบที่สูงกว่านั้น = ลอย
• Space = กระโดด (JUMP_V, GRAVITY เดียวกับตกขอบ, อินทิเกรตแบบ exact ไม่ขึ้นกับ FPS) — ห้ามตอนลอย/วาง/กู้/ตาย/จบรอบ
  กลางอากาศ: ปุ่มทิศเร่งได้ AIR_ACCEL_K เท่าของพื้น, ไม่มีเบรก/แรงเสียดทาน, ไม่เร็วเกิน max(ความเร็วตอนนี้, เพดาน) (ไม่มี bhop)
• หมอบกลางอากาศ = หดขา: cl_feet (ระดับเท้าตอนยืนเหยียด) ไม่ขยับ ปลายเท้าจริง (bottom) สูงขึ้น CROUCH_TUCK → กล้องไม่ขยับ
  ปีนผิวที่ ≤ ปลายเท้า + MOUNT_EPS ได้ ; เข้าอากาศ (กระโดด/ตกขอบ) ตอนหมอบอยู่แล้ว = ขาหดตั้งแต่พื้น (cl_feet ลดลง
  CROUCH_TUCK — ปลายเท้า/กล้องที่เดิม) → "กระโดดก่อนแล้วค่อยหมอบ" เท่านั้นที่ได้ความสูงเพิ่ม (เทคนิคจริง)
• กล้อง: กลางอากาศตามลำตัวแบบแข็ง (ไม่มีหน่วงของ EYE_TAU) ; เฟรมแตะพื้นใช้ตำแหน่ง "แตะผิวพอดี" (ไม่จมแล้วเด้ง) แล้วค่อย
  ไล่ระดับหมอบ/ยืนแบบนุ่ม (เข้าหาแบบ exponential — ไม่เลยเป้า = ไม่เด้ง)
• แตะพื้น: ดาเมจตก fall_damage (ไม่ผ่านเกราะ ; ตาย = แพ้ died) · เสียงลงพื้นให้บอท (ค้าง Shift = เงียบ) · โทษความแม่นแตะพื้น
• ปืนลอย/เพิ่งแตะพื้น = guns.air_extra_deg ผ่าน Stability.extra (นัดที่ยิง + crosshair ถ่างเห็นเท่ากัน) ; Classic คลิกขวา =
  clutchfight.gun_alt_spread
• ข้อมูลข้ามทีม §13.2: PlayerView (air/land_t/land_loud/on_box) · game.cl_air/cl_jump_t/cl_land_t/cl_land_loud/
  cl_fall_dmg_t · clutch_vm() = "vm" ของ clutch_view (viewmodel ของทีม VISUAL)"""
import math

from .config import C_RED, EYE_Y, MOVE_ACCEL
from . import guns
from .clutchmap import STEP_UP
from .clutchscen import (AIR_ACCEL_K, CROUCH_TUCK, EYE_TAU, GRAVITY, JUMP_V, MOUNT_EPS, SPIKE_EQUIP_T, fall_damage)
from .movement import speed_cap, wish_dir


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


class ClutchMoveMixin:
    def reset_clutch_move(self):
        """สถานะกระโดด/ตกต่อรอบ (reset_clutch เรียก) — เวลาเป็นเวลาเกม gt ; −9 = ยังไม่เคย"""
        self.cl_air, self.cl_tuck, self.cl_jump_q, self.cl_on_box = False, False, False, False
        self.cl_apex, self.cl_sup = 0.0, 0.0
        self.cl_jump_t = self.cl_land_t = self.cl_fall_dmg_t = -9.0
        self.cl_land_loud, self.cl_jump_shots, self.cl_jumps = False, 0, 0

    def clutch_can_jump(self):
        return (self.cmap is not None and not self.cl_air and not self.clutch_rooted() and self.cl_result is None
                and self.state == "play")

    def clutch_bottom(self):
        """ปลายเท้าจริง (ม.) — กลางอากาศขาหด = cl_feet + CROUCH_TUCK"""
        return self.cl_feet + (CROUCH_TUCK if self.cl_tuck else 0.0)

    def _clutch_enter_air(self, vy):
        """เริ่มลอย (กระโดด/ตกขอบ) — หมอบอยู่ = ขาหดตั้งแต่พื้น (ปลายเท้า/กล้องอยู่ที่เดิม)"""
        if self.gun_crouch and not self.cl_tuck:
            self.cl_feet -= CROUCH_TUCK
            self.cl_tuck = True
        self.cl_air, self.cl_vy, self.cl_apex = True, vy, self.cl_feet

    def clutch_air_step(self, dt):
        """ปุ่มทิศกลางอากาศ: เร่ง MOVE_ACCEL × AIR_ACCEL_K ตามทิศที่กด ไม่มีเบรก ; ขนาดไม่เกิน max(ความเร็วเดิม, เพดาน)"""
        wx, wz = wish_dir(self.keys_down, self.cam.yaw)
        if wx == 0.0 and wz == 0.0:
            return
        v = self.vel
        sp0 = math.hypot(v[0], v[1])
        cap = speed_cap(self.gun_run_speed() * self.clutch_tag_mult(), walk="shift" in self.keys_down)
        a = MOVE_ACCEL * AIR_ACCEL_K * dt
        nx, nz = v[0] + wx * a, v[1] + wz * a
        lim = max(sp0, cap)
        s = math.hypot(nx, nz)
        if s > lim > 0.0:
            nx, nz = nx * lim / s, nz * lim / s
        self.vel = [nx, nz]

    def clutch_move(self, dt):
        """WASD/อากาศ + ชน/ไถลกำแพง (player_map().move) + กระโดด/ตก/ปีน — ปลายเท้าไม่ต่ำกว่าผิวที่ยืน ;
        วาง/กู้/ตาย/จบรอบ = ยืนนิ่ง (rooted — หันกล้องได้ ; ตายกลางอากาศยังร่วงตามแรงโน้มถ่วง)"""
        pm = self.cmap.player_map()
        if self.clutch_rooted() or self.cl_result is not None:
            self.vel = [0.0, 0.0]
        elif self.cl_air:
            self.clutch_air_step(dt)
        else:
            self.player_move(dt, self.gun_run_speed() * self.clutch_tag_mult(), crouch=self.gun_crouch)
        if self.cl_jump_q:
            self.cl_jump_q = False
            if self.clutch_can_jump():
                self._clutch_enter_air(JUMP_V)
                self.cl_jump_t = self.gt
                self.cl_jumps += 1
        if self.cl_air:                                          # หมอบ = หดขา ; ปล่อย = เหยียด (ถ้าใต้ตัวมีที่ว่าง)
            if self.gun_crouch:
                self.cl_tuck = True
            elif self.cl_tuck and self.cl_feet >= self.cl_sup:
                self.cl_tuck = False
        tuck = CROUCH_TUCK if self.cl_tuck else 0.0
        p, f0 = self.cam.pos, self.cl_feet
        step = tuck + MOUNT_EPS if self.cl_air else STEP_UP
        nx, nz, sup = pm.move(p[0], p[2], f0 + tuck, self.vel, dt, step=step)
        if sup is None:
            sup = f0 + tuck
        self.cl_sup = sup
        phys = None                                              # ลำตัวขยับจริงเฟรมนี้ (กล้องตามแบบแข็ง) — None = บนพื้น
        if not self.cl_air and sup < f0 - STEP_UP - 1e-6:       # ขอบสูงกว่าก้าวลง = เริ่มตก (เฟรมนี้ร่วงเลย)
            self._clutch_enter_air(0.0)
            tuck = CROUCH_TUCK if self.cl_tuck else 0.0
            f0 = self.cl_feet
        if self.cl_air:
            vy = self.cl_vy
            y1 = f0 + vy * dt - 0.5 * GRAVITY * dt * dt
            self.cl_vy = vy - GRAVITY * dt
            self.cl_apex = max(self.cl_apex, y1)
            if self.cl_vy <= 0.0 and y1 + tuck <= sup + 1e-9:  # ปลายเท้า (รวมขาที่หด) แตะผิว
                phys = (sup - tuck) - f0
                self._clutch_land(sup, tuck)
            else:
                self.cl_feet = max(y1, sup - tuck)               # ขาขึ้นแล้วผิวดันขึ้น (ปีนผ่านขอบ) — ไม่จมผิว
                phys = self.cl_feet - f0
        else:
            self.cl_feet = sup                                   # ก้าวขึ้น ≤ STEP_UP / ลงบันได-ทางลาด = ติดพื้น
        self.cl_on_box = not self.cl_air and self.cmap.on_box(nx, nz)
        self._clutch_eye(dt, phys)
        self.cam.pos = [nx, self.cl_eye, nz]

    def _clutch_eye(self, dt, phys):
        """ระดับกล้อง: ลอย/เฟรมแตะพื้น = ตามลำตัวแบบแข็ง (phys) ; แล้วไล่เป้า (ยืน/หมอบ/ก้าวขึ้นลง) แบบนุ่ม EYE_TAU"""
        if phys is not None:
            self.cl_eye += phys
        if self.cl_air:
            want = self.cl_feet + EYE_Y                          # ขาหด ≠ ย่อตัว — หัว/กล้องอยู่ระดับยืนของ cl_feet
        else:
            want = self.cl_feet + EYE_Y - (guns.CROUCH_DROP if self.gun_crouch else 0.0)
        d = want - self.cl_eye
        self.cl_eye = want if abs(d) > 3.0 else self.cl_eye + d * (1.0 - math.exp(-dt / EYE_TAU))
        self.cl_eye = max(self.cl_eye, self.cl_feet + 0.3)

    def _clutch_land(self, sup, tuck):
        """แตะพื้น: ดาเมจตก (ระยะที่ลำตัวร่วงจากจุดสูงสุด) · เสียงลงพื้น (ค้าง Shift = เงียบ) · เวลาแตะพื้น (โทษความแม่น)"""
        h = self.cl_apex - (sup - tuck)
        self.cl_feet, self.cl_vy = sup, 0.0
        self.cl_air = self.cl_tuck = False
        self.cl_land_t = self.gt
        self.cl_land_loud = "shift" not in self.keys_down
        dmg = fall_damage(h)
        if dmg > 0.0 and not self.cl_dead and self.cl_result is None:
            self.clutch_fall_hit(dmg)

    def clutch_fall_hit(self, dmg):
        """ดาเมจตกเข้า HP ตรง (ไม่ผ่านเกราะ — JumpFallDamageCurve) + จอวาบแดง/ป้ายลอยแบบโดนยิง ; ตาย = แพ้ died
        เสียง: ทีม AUDIO เล่นเสียงตกกระแทกเองจาก cl_fall_dmg_t — ไม่เรียก clutchaudio.hurt ซ้ำ (เสียงซ้อน)"""
        self.gun_hp = round(self.gun_hp - dmg, 6)
        self.gun_dmg_taken += dmg
        self.gun_flash = 0.25
        self.cl_fall_dmg_t = self.gt
        self.add_float("-%d" % dmg, C_RED)
        if self.gun_hp <= 0:
            self.clutch_feed("คุณตกจากที่สูง", C_RED)
            self.clutch_player_died()

    def clutch_jump_key(self, down):
        """Space: กดใหม่ = ขอกระโดด (ทำในเฟรมถัดไป ; ค้าง/key repeat ไม่กระโดดซ้ำ)"""
        if not down:
            self.cl_hold.discard("jump")
        elif getattr(self, "resume_cd", 0) > 0:
            return                                               # นับกลับหลังพัก (ทุกอย่างหยุด) — ไม่เก็บคิวไว้กระโดดตอนเริ่ม
        elif "jump" not in self.cl_hold:
            self.cl_hold.add("jump")
            self.cl_jump_q = True

    # ───────────────────────── ความแม่นตอนลอย/แตะพื้น ─────────────────────────
    def clutch_air_err(self):
        """Stability.extra ของปืนผู้เล่นในรอบ clutch (องศา) — guns.air_extra_deg"""
        if self.mode != "clutch":
            return 0.0
        return guns.air_extra_deg(self.gun_weapon, self.gun_speed(), self.gun_crouch, self.cl_air,
                                  self.gt - self.cl_land_t)

    # ───────────────────────── ข้อมูลข้ามทีม (§11.1 + §13.2) ─────────────────────────
    def clutch_pv(self):
        pv, p = self.cl_pv, self.cam.pos
        pv.x, pv.z = p[0], p[2]
        pv.feet = self.clutch_bottom()                           # ขาหดกลางอากาศ: ปลายเท้าสูงขึ้น + ท่าหมอบ = หัวที่เดิม
        pv.crouch = 1.0 if (self.gun_crouch or self.cl_tuck) else 0.0
        pv.vx, pv.vz = self.vel[0], self.vel[1]
        pv.run_speed = self.gun_run_speed()
        pv.alive, pv.weapon = not self.cl_dead, self.gun_weapon
        pv.planting, pv.defusing = self.cl_plant_t0 is not None, self.cl_defuse_t0 is not None
        pv.spike_out = self.cl_equip == "spike"
        pv.air, pv.land_t, pv.land_loud, pv.on_box = self.cl_air, self.cl_land_t, self.cl_land_loud, self.cl_on_box
        return pv

    def clutch_vm(self):
        """viewmodel มุมมองบุคคลที่หนึ่ง (§13.2 "vm" ของ clutch_view — ทีม VISUAL วาด)"""
        g, w = self.gt, self.gun_w()
        spike = self.cl_equip == "spike"
        dur = SPIKE_EQUIP_T if spike else w.get("equip", 1.0)
        rk = None
        if self.gun_reload_until > 0:
            rk = _clamp01(1.0 - (self.gun_reload_until - g) / max(1e-6, w["reload"]))
        try:
            kick = tuple(float(v) for v in self.gun_stab.camera_offset(g))
        except Exception:
            kick = (0.0, 0.0)
        crouch = 0.0 if self.cl_air else _clamp01((self.cl_feet + EYE_Y - self.cl_eye) / guns.CROUCH_DROP)
        return {"weapon": self.gun_weapon, "equip": "spike" if spike else "gun",
                "equip_k": _clamp01(1.0 - max(0.0, self.cl_equip_until - g) / max(1e-6, dur)), "reload_k": rk,
                "ads": self.gun_zoom > 1.0, "crouch": crouch, "speed": math.hypot(self.vel[0], self.vel[1]),
                "air": self.cl_air, "fire_t": getattr(self, "gun_last_shot", -9.0),
                "planting": self.cl_plant_t0 is not None, "defusing": self.cl_defuse_t0 is not None, "kick": kick}

    @staticmethod
    def clutch_view_bot(b, g):
        """บอท 1 ตัวของ clutch_view (§11.2 + §13.2) — meta ที่ทีม BOTS เติม อ่านแบบมีค่าเริ่มต้นเสมอ"""
        m = b.meta
        vel = m.get("vel") or getattr(b, "vel", None) or (0.0, 0.0)
        return {"x": b.x, "y": b.y0, "z": b.z, "yaw": m.get("yaw", 0.0), "crouch": b.crouch, "alive": b.alive,
                "dead_t": m.get("dead_t"), "flash": max(0.0, 1.0 - (g - m.get("cl_shot_t", -9.0)) / 0.06),
                "vx": float(vel[0]), "vz": float(vel[1]), "pitch": m.get("pitch", 0.0),
                "walk": bool(m.get("walk", False)), "reload": bool(m.get("reload", False)),
                "weapon": getattr(b, "weapon", None) or "vandal"}   # ปืนในมือบอท (ภาพ) — ไม่งั้น GL วาดด้วยปืนผู้เล่น
