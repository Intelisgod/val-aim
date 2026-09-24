# -*- coding: utf-8 -*-
"""แกนการเคลื่อนที่ของผู้เล่น (pure python — ไม่มี pygame) ใช้ร่วม STRAFE / DODGE / GUNFIGHT

โมเดล (ค่าคงที่ + ที่มาอยู่ใน config.py หัวข้อ "การเคลื่อนที่"):
  • ไม่กดทิศ = เบรก  dv/dt = −(K·v + C)                        (Unreal CharacterMovement: friction + braking)
  • กดทิศเดิม        = เร่ง  dv/dt = +ACCEL จนถึงเพดาน vmax
  • กดทิศตรงข้าม     = counter-strafe  dv/dt = −(K·v + C + ACCEL) จนหยุด แล้วเร่งกลับทางใหม่ในเฟรมเดียวกัน
  • เร็วเกินเพดาน (กด Shift/หมอบ/ADS ระหว่างวิ่ง) = เบรกลงมาหาเพดาน ไม่ต่ำกว่า
  • ส่วนความเร็วที่ตั้งฉากกับทิศที่กด = เบรกเหมือนปล่อยปุ่ม
ทุกช่วงอินทิเกรตแบบ exact ภายในเฟรม (ไม่ใช่ Euler) → เวลาเบรก/counter-strafe ไม่ขึ้นกับ FPS (selftest เช็ค 60/144/240)
ความแม่นขณะเคลื่อนที่ (deadzone 27.5% + เส้นโค้ง error_move) อยู่ที่ guns.move_error_deg"""
import math

from .config import MOVE_ACCEL, MOVE_BRAKE_C, MOVE_BRAKE_K, MOVE_CROUCH_MULT, MOVE_WALK_MULT


def _brake(v, dt, extra=0.0, floor=0.0):
    """ความเร็ว (สเกลาร์ ≥ 0) หลังเบรก dv/dt = −(K·v + C + extra) นาน dt แต่ไม่ต่ำกว่า floor
    คืน (ความเร็วใหม่, เวลาที่เหลือในเฟรมหลังแตะ floor — 0 ถ้ายังไม่แตะ)"""
    k, c = MOVE_BRAKE_K, MOVE_BRAKE_C + extra
    if v <= floor:
        return v, dt
    t_floor = math.log((k * v + c) / (k * floor + c)) / k
    if t_floor >= dt:
        return max(floor, (v + c / k) * math.exp(-k * dt) - c / k), 0.0
    return floor, dt - t_floor


def wish_dir(keys, yaw):
    """ทิศที่ผู้เล่นกด (หน่วยเวกเตอร์บนพื้น x,z) จากปุ่ม WASD + มุมกล้อง — (0, 0) ถ้าไม่กด/กดหักล้างกัน"""
    dx = (1 if "d" in keys else 0) - (1 if "a" in keys else 0)
    dz = (1 if "s" in keys else 0) - (1 if "w" in keys else 0)
    if not (dx or dz):
        return 0.0, 0.0
    sy, cy = math.sin(yaw), math.cos(yaw)
    ix = cy * dx - sy * dz          # right = (cos, −sin), fwd = (sin, cos) ; ทิศ = right·dx + fwd·(−dz)
    iz = -sy * dx - cy * dz
    m = math.hypot(ix, iz)
    return ix / m, iz / m


def speed_cap(run_speed, walk=False, crouch=False):
    """เพดานความเร็ว — Shift เดิน / หมอบ คูณลง (ADS/สโคปคูณที่ run_speed ก่อนส่งมา)"""
    v = run_speed
    if crouch:
        v *= MOVE_CROUCH_MULT
    elif walk:
        v *= MOVE_WALK_MULT
    return v


def step(vel, wish, vmax, dt):
    """เดินหนึ่งเฟรม — vel = [vx, vz] (แก้ในที่), wish = ทิศที่กด (หน่วย) หรือ (0, 0), vmax = เพดานตอนนี้"""
    wx, wz = wish
    if wx == 0.0 and wz == 0.0:
        sp = math.hypot(vel[0], vel[1])
        if sp > 0.0:
            ns, _ = _brake(sp, dt)
            f = ns / sp
            vel[0] *= f
            vel[1] *= f
        return
    par = vel[0] * wx + vel[1] * wz
    px, pz = vel[0] - par * wx, vel[1] - par * wz          # ส่วนตั้งฉากกับทิศที่กด = เบรกทิ้ง
    perp = math.hypot(px, pz)
    if perp > 0.0:
        np_, _ = _brake(perp, dt)
        px *= np_ / perp
        pz *= np_ / perp
    if par < 0.0:                                          # counter-strafe
        ns, rest = _brake(-par, dt, extra=MOVE_ACCEL)
        par = -ns if rest <= 0.0 else min(vmax, MOVE_ACCEL * rest)
    elif par > vmax:                                       # เร็วเกินเพดานใหม่ (เพิ่งกด Shift/หมอบ/ADS)
        par, _ = _brake(par, dt, floor=vmax)
    else:
        par = min(vmax, par + MOVE_ACCEL * dt)
    vel[0] = par * wx + px
    vel[1] = par * wz + pz


class MoveMixin:
    """การเดินของผู้เล่นใน Game (STRAFE/DODGE ผ่าน UpdateMixin, GUNFIGHT ผ่าน GunMixin) — ต้องมี self.keys_down,
    self.cam, self.vel ; ปุ่ม "shift" ใน keys_down = เดิน (input.py)"""

    def player_move(self, dt, run_speed, crouch=False):
        """เดินหนึ่งเฟรม: WASD + Shift เดิน + หมอบ (เพดานความเร็วจาก speed_cap) — คืน True ถ้ากดทิศอยู่"""
        wish = wish_dir(self.keys_down, self.cam.yaw)
        cap = speed_cap(run_speed, walk="shift" in self.keys_down, crouch=crouch)
        step(self.vel, wish, cap, dt)
        return wish != (0.0, 0.0)

    def move_within(self, dt, x0, x1, z0, z1):
        """ขยับกล้องตามความเร็ว แล้วหนีบตำแหน่งในโซน — ความเร็วไม่ถูกล้าง (ตั้งใจ): ขอบโซนเป็นกำแพงล่องหน
        ถ้าชนแล้วหยุดทันที = ช่องโหว่ "วิ่งชนขอบแล้วยิงแม่นทันที" ข้ามการฝึก counter-strafe ; ดันขอบค้าง = ยังนับว่าวิ่ง"""
        self.cam.pos[0] = max(x0, min(x1, self.cam.pos[0] + self.vel[0] * dt))
        self.cam.pos[2] = max(z0, min(z1, self.cam.pos[2] + self.vel[1] * dt))


def time_to(v0, v1, counter=False):
    """เวลา (วินาที) ที่เบรกจาก v0 ลงถึง v1 — counter=True = กดปุ่มฝั่งตรงข้าม (ไว้โชว์/เทสต์ ไม่ใช้ในเกม)"""
    k, c = MOVE_BRAKE_K, MOVE_BRAKE_C + (MOVE_ACCEL if counter else 0.0)
    return math.log((k * v0 + c) / (k * v1 + c)) / k


def selftest():
    """คืน list ข้อผิดพลาด — เวลาเบรกตามเป้าในคอนฟิก ไม่ขึ้นกับ FPS, counter-strafe ถือค้างได้ช่วงแม่นหลายเฟรม"""
    from .guns import WEAPONS, is_accurate, move_error_deg
    errors = []
    run = WEAPONS["vandal"]["run_speed"]

    def sim(fps, keys_fn, until, t_max=1.0):
        vel = [run, 0.0]             # วิ่งเต็มสปีดไปทางขวา (+x) มุมกล้อง yaw 0
        t, dt = 0.0, 1.0 / fps
        while t < t_max:
            if until(vel):
                return t
            step(vel, wish_dir(keys_fn(), 0.0), run, dt)
            t += dt
        return None

    for fps in (60, 144, 240):
        dt = 1.0 / fps
        stop = sim(fps, lambda: set(), lambda v: math.hypot(*v) <= 1e-9)
        cs = sim(fps, lambda: {"a"}, lambda v: is_accurate("vandal", math.hypot(*v)))
        # เฟรมที่เห็นผลช้ากว่าเวลาจริงได้ไม่เกิน 1 เฟรม
        if stop is None or not (0.160 - 1e-6 <= stop <= 0.170 + dt):
            errors.append(f"movement: ปล่อยปุ่มหยุดสนิท {stop} วิ ที่ {fps} FPS (ต้อง 160–170 ms)")
        if cs is None or not (0.055 - 1e-6 <= cs <= 0.070 + dt):
            errors.append(f"movement: counter-strafe ถึง deadzone {cs} วิ ที่ {fps} FPS (ต้อง 55–70 ms)")
    # ถือปุ่มฝั่งตรงข้ามค้าง: ช่วงที่แม่น (|v| ≤ deadzone) ต้องยาวหลายเฟรม ไม่ใช่ 1 เฟรม (7 ms) แบบโมเดลเดิม
    vel, acc_t, dt = [run, 0.0], 0.0, 1.0 / 144
    for _ in range(144):
        step(vel, wish_dir({"a"}, 0.0), run, dt)
        if is_accurate("vandal", math.hypot(*vel)):
            acc_t += dt
    if acc_t < 0.05:
        errors.append(f"movement: ถือ counter-strafe ค้างแม่นได้แค่ {acc_t * 1000:.0f} ms")
    if abs(vel[0] + run) > 1e-6:
        errors.append("movement: ถือปุ่มฝั่งตรงข้ามต้องเร่งกลับถึงความเร็ววิ่งเต็ม")
    # Shift ระหว่างวิ่ง = เบรกลงเพดานเดิน ไม่ต่ำกว่า ; ความเร็วเดินได้โทษระดับเดิน (ไม่ใช่ระดับวิ่ง)
    vel = [run, 0.0]
    cap = speed_cap(run, walk=True)
    for _ in range(60):
        step(vel, wish_dir({"d"}, 0.0), cap, 1.0 / 60)
    if abs(vel[0] - cap) > 1e-6:
        errors.append(f"movement: Shift ต้องลดความเร็วลงเพดานเดิน {cap:.2f} (ได้ {vel[0]:.2f})")
    if move_error_deg("vandal", cap) != WEAPONS["vandal"]["spread"]["walk"]:
        errors.append("movement: ความเร็วเดิน (Shift) ต้องได้โทษระดับเดิน")
    return errors
