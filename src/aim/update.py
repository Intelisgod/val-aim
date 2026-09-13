# -*- coding: utf-8 -*-
"""update ต่อโหมด (play/strafe/spray/dodge/placement/switch) + recoil — UpdateMixin (ย้าย verbatim)"""

import pygame
import math
import random
import json
import os
import sys
import array

from .config import *
from .ranks import *
from .data import DATA_FILE, load_data, save_data
from .camera import Camera, focal_len, VFOV_RAD
from .target import Target
from .stability import Stability


class UpdateMixin:
    def strafe_speed(self):
        return math.hypot(self.vel[0], self.vel[1])

    def strafe_spread(self):
        v = self.strafe_speed()
        if v < STRAFE_MIN_SPREAD_SPEED:
            return 0.0
        ratio = min(1.0, (v - STRAFE_MIN_SPREAD_SPEED) / (STRAFE_MAX_SPEED - STRAFE_MIN_SPREAD_SPEED))
        return STRAFE_MAX_SPREAD_RAD * ratio

    def update_play(self, dt):
        self.gt += dt
        md = self.mode
        if self.pending_end is not None and self.gt >= self.pending_end:
            self.pending_end = None
            self.end_game()
            return

        if md not in ("reaction", "sniper"):
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0
                self.end_game()
                return

        if md == "tracking":
            for t in self.targets:
                t.pos[0] += t.vx * dt
                t.pos[1] = t.base_y + math.sin(self.gt * 2 + t.pos[0]) * 0.4
                if t.pos[0] < -7 or t.pos[0] > 7:
                    t.vx *= -1
                    t.pos[0] = max(-7, min(7, t.pos[0]))

        if md == "strafe":
            self.update_strafe(dt)
        if md == "spray":
            self.update_spray(dt)
        if md == "dodge":
            self.update_dodge(dt)
        if md == "placement":
            self.update_placement(dt)
        if md == "switch":
            self.update_switch(dt)
        if md == "gun":
            self.update_gun(dt)

        if md == "reaction" and not self.targets and self.next_spawn_at is not None \
                and self.gt >= self.next_spawn_at and self.pending_end is None:
            if self.lmb_down:
                # ยังกดปุ่มค้าง (นิ้วยังไม่กลับที่) — รอก่อน handle_mouse_up จะตั้งเวลาใหม่ให้เอง
                self.next_spawn_at = self.gt + 0.05
            else:
                self.next_spawn_at = None
                self.spawn_one()

        if md == "sniper":
            if self.next_spawn_at is not None and self.gt >= self.next_spawn_at:
                self.spawn_sniper_ball()
            for t in list(self.targets):
                t.pos[0] += t.vx * dt
                px = t.pos[0]
                t.visible = (SNIPER_DOOR_L - SNIPER_R < px < SNIPER_DOOR_R + SNIPER_R)
                if SNIPER_DOOR_L < px < SNIPER_DOOR_R and t.born < 0:
                    t.born = self.gt
                if (t.vx > 0 and px >= t.end_x) or (t.vx < 0 and px <= t.end_x):
                    self.misses += 1
                    self.sniper_missed += 1
                    self.targets.remove(t)
                    self.add_float("ESCAPED", C_RED)
                    self.play(self.snd_miss)
                    if self.sniper_spawned >= SNIPER_TOTAL:
                        self.pending_end = self.gt + 0.4
                    else:
                        self.next_spawn_at = self.gt + 0.6 + random.random() * 0.8

        for t in self.targets:
            if md in ("reaction", "sniper", "spray"):
                t.alpha = 1.0
            else:
                t.alpha = min(1.0, t.alpha + dt * 4)

    def update_strafe(self, dt):
        dx = (1 if "d" in self.keys_down else 0) - (1 if "a" in self.keys_down else 0)
        dz = (1 if "s" in self.keys_down else 0) - (1 if "w" in self.keys_down else 0)
        if dx or dz:
            # fwd/right ใช้เฉพาะตอนกดปุ่มเดิน — คำนวณเฉพาะใน branch นี้ (เฟรมยืนเฉยไม่เสีย trig)
            fwd = (math.sin(self.cam.yaw), math.cos(self.cam.yaw))     # x,z บนพื้น
            right = (math.cos(self.cam.yaw), -math.sin(self.cam.yaw))
            mag = math.hypot(dx, dz)
            ix = (right[0] * dx + fwd[0] * (-dz)) / mag
            iz = (right[1] * dx + fwd[1] * (-dz)) / mag
            self.vel[0] += ix * STRAFE_ACCEL * dt
            self.vel[1] += iz * STRAFE_ACCEL * dt
            sp = self.strafe_speed()
            if sp > STRAFE_MAX_SPEED:
                self.vel[0] *= STRAFE_MAX_SPEED / sp
                self.vel[1] *= STRAFE_MAX_SPEED / sp
            self.static_since = 0.0
            if self.strafe_respawn and not self.targets:
                self.spawn_targets()
                self.strafe_respawn = False
        else:
            sp = self.strafe_speed()
            if sp > 0:
                dec = STRAFE_FRICTION * dt
                if sp <= dec:
                    self.vel = [0.0, 0.0]
                else:
                    self.vel[0] -= self.vel[0] / sp * dec
                    self.vel[1] -= self.vel[1] / sp * dec
            if self.strafe_speed() <= 0.05:
                self.static_since += dt
                if self.static_since > STRAFE_STATIC_DESPAWN and self.targets and not self.strafe_respawn:
                    self.targets = []
                    self.strafe_respawn = True
        self.cam.pos[0] = max(-1.8, min(1.8, self.cam.pos[0] + self.vel[0] * dt))
        self.cam.pos[2] = max(-1.8, min(1.8, self.cam.pos[2] + self.vel[1] * dt))
        sp = self.strafe_speed()
        if sp > 1.5:
            interval = (220 + 180 * (1 - min(1.0, sp / STRAFE_MAX_SPEED))) / 1000
            if self.gt - self.last_step > interval:
                self.play(self.snd_step)
                self.last_step = self.gt
        if self.strafe_spawn_at is not None and self.gt >= self.strafe_spawn_at:
            self.strafe_spawn_at = None
            if not self.strafe_respawn:
                self.spawn_targets()

    def spray_recoil_kick(self, shot_idx, wp):
        """(legacy — โมเดลเก่าก่อน 11 ก.ย. 2026 ไม่ได้ใช้ในเกมแล้ว เก็บไว้เทียบใน tools/recoil_fit.py --legacy)
        คืน (d_pitch, d_yaw) องศา ของนัดที่ shot_idx (0-based) ตาม pattern โดยประมาณ
        ปัจจุบันใช้ aim/stability.py (เส้นโค้งจริงจากไฟล์เกม) แทน — ดู spray_fire_one"""
        # แนวตั้ง: ไต่เร็วช่วงแรกแล้วอิ่มตัว (approach v_max)
        climb = wp["v_climb"]
        vmax = wp["v_max"]
        # kick ต่อนัด = ส่วนต่างของเส้นโค้งอิ่มตัว
        prev_v = vmax * (1 - math.exp(-climb * shot_idx / 3.0))
        cur_v = vmax * (1 - math.exp(-climb * (shot_idx + 1) / 3.0))
        d_pitch = cur_v - prev_v
        # แนวนอน: เริ่มหลังนัดที่ ~3 แล้วโยกซ้ายขวาเพิ่มขึ้น
        if shot_idx < 3:
            d_yaw = random.uniform(-0.04, 0.04)
        else:
            amp = wp["h_amp"] * min(1.0, (shot_idx - 2) / wp["h_settle"])
            d_yaw = random.uniform(-amp, amp) + 0.3 * amp * math.sin(shot_idx * 1.1)
        return d_pitch, d_yaw

    def update_spray(self, dt):
        wp = SPRAY_WEAPONS[self.spray_weapon]
        if not self.targets:
            self.spawn_spray_bot()
        # รีโหลด
        if self.spray_reloading_until > 0:
            if self.gt >= self.spray_reloading_until:
                self.spray_reloading_until = 0.0
                self.spray_mag = wp["mag"]
                self.spray_stab.reset()
                # นัดแรกของแม็กใหม่นับจาก "ตอนนี้" — เดิมไม่แตะ spray_next_shot ซึ่งค้างอยู่ที่เวลาที่
                # แม็กก่อนหมด: ถือปุ่มค้างผ่านรีโหลด (วิธีเล่นปกติ) ลูปด้านล่างจะ "ตามเก็บหนี้" 1.2 วิ
                # = ~11 นัดในเฟรมเดียว ทุกนัดเช็ค hit กับ aim เดิม → 293 vs 206 นัด/30 วิ คะแนนเฟ้อ ~42%
                # (input.py รีเซ็ตเฉพาะตอนกดเมาส์ใหม่ selftest จึงไม่เคยเห็น)
                self.spray_next_shot = self.gt
            else:
                self._spray_recover(dt)
                return
        if self.spray_firing and self.spray_mag > 0:
            interval = 1.0 / wp["rps"]
            # ยิงทุกนัดที่ถึงเวลา (อาจหลายนัดต่อเฟรมถ้า dt ใหญ่)
            guard = 0
            while self.gt >= self.spray_next_shot and self.spray_mag > 0 and guard < 30:
                guard += 1
                self.spray_fire_one(wp)
                self.spray_mag -= 1
                self.spray_next_shot += interval
                if self.spray_mag <= 0:
                    self.spray_reloading_until = self.gt + SPRAY_RELOAD
                    self.add_float("RELOAD", (255, 170, 0))
                    break
        else:
            self._spray_recover(dt)

    def _spray_recover(self, dt):
        """ฟื้นรีคอยล์ตามเวลา (stability.py: หยุดยิง ~0.4 วิ = pattern รีเซ็ต) — กล้องไม่ขยับ แค่ offset ลด"""
        self.spray_stab.update(self.gt, dt)
        self.recoil_pitch = self.spray_stab.pitch_off
        self.recoil_yaw = self.spray_stab.yaw_off

    def spray_view_offset(self):
        """กล้อง 'เด้ง' ที่ตาเห็นตอนยิง (เรเดียน) — pop วูบเดียวแล้วคืน ไม่กระทบทิศกระสุน"""
        dp, dy = self.spray_stab.camera_offset(self.gt)
        return math.radians(dp), math.radians(dy)

    def spray_fire_one(self, wp):
        # ทิศกระสุนนัดนี้ = crosshair (หลังผู้เล่นดึงสวน) + pattern จากตาราง Riot + สเปรดสุ่ม
        # นัดที่ n ของแม็กเบี่ยงตามเส้นโค้ง PitchRecoil/YawRecoil ของปืน — ไม่ใช่กล้องเด้ง (เหมือนเกมจริง)
        self.spray_shots += 1
        po, yo, sp = self.spray_stab.shoot(self.gt)
        self.recoil_pitch = self.spray_stab.pitch_off
        self.recoil_yaw = self.spray_stab.yaw_off
        d = Stability.shot_dir(po, yo, sp)
        t = self.targets[0] if self.targets else None
        is_head = False
        on_body = False
        if t is not None:
            if t.is_head_hit(self.cam, shot_dir=d):
                is_head = True
                on_body = True
                self.spray_heads += 1
            elif t.is_hit(self.cam, shot_dir=d):
                on_body = True
            if on_body:
                self.spray_onbody += 1
                self.hits += 1
                # คะแนน: ลำตัว +100, หัว +HEAD_BONUS (ขีดแรงค์ปรับผ่าน MODE_SCALE["spray"] ใน config.py)
                self.score += 100 + (HEAD_BONUS if is_head else 0)
                if is_head:
                    self.headshots += 1
                self.hitmarks.append(pygame.time.get_ticks())
            else:
                self.misses += 1
        # รอยกระสุน: ตำแหน่งเชิงมุมของ "กระสุน" เทียบใจกลางเป้า (องศา, ขวา/บน = บวก) เพื่อวาด spray pattern
        # (เดิมเก็บตำแหน่งเป้าเทียบกล้อง → วาดแล้วกลับด้านทั้งซ้ายขวา/บนล่าง — แก้ 11 ก.ย. 2026)
        if t is not None:
            ho = self._aim_offset_deg(t)
            b_yaw = math.degrees(math.atan2(d[0], d[2]))
            b_pitch = math.degrees(math.atan2(d[1], math.hypot(d[0], d[2])))
            self.spray_marks.append((b_yaw - ho[0], b_pitch - ho[1], on_body, is_head))
            if len(self.spray_marks) > 60:
                del self.spray_marks[:len(self.spray_marks) - 60]
        self.play(self.snd_head if is_head else self.snd_spray)

    def _aim_offset_deg(self, t):
        """ตำแหน่งใจกลางเป้า (body) เทียบทิศกล้อง เป็น (yaw_off, pitch_off) องศา"""
        x, y, z = self.cam.to_cam(t.pos)
        if z < 0.05:
            return (0.0, 0.0)
        yaw_off = math.degrees(math.atan2(x, z))
        pitch_off = math.degrees(math.atan2(y, math.hypot(x, z)))
        return (yaw_off, pitch_off)

    def update_dodge(self, dt):
        # การเดิน (ใช้ฟิสิกส์ strafe แต่โซนกว้างกว่า)
        self.dodge_move(dt)
        # เป้าหัวให้ flick
        if not self.targets:
            self.spawn_dodge_target()
        # ปล่อย hazard เป็นจังหวะ
        if self.gt >= self.dodge_next_haz:
            self.spawn_dodge_hazard()
            self.dodge_next_haz = self.gt + random.uniform(*DODGE_HAZ_INTERVAL)
            self.play(self.snd_warn)
        self.update_dodge_hazards(dt)
        if self.dodge_flash > 0:
            self.dodge_flash = max(0.0, self.dodge_flash - dt)

    def dodge_move(self, dt):
        dx = (1 if "d" in self.keys_down else 0) - (1 if "a" in self.keys_down else 0)
        dz = (1 if "s" in self.keys_down else 0) - (1 if "w" in self.keys_down else 0)
        if dx or dz:
            # fwd/right ใช้เฉพาะตอนกดปุ่มเดิน (เหตุผลเดียวกับ update_strafe)
            fwd = (math.sin(self.cam.yaw), math.cos(self.cam.yaw))
            right = (math.cos(self.cam.yaw), -math.sin(self.cam.yaw))
            mag = math.hypot(dx, dz)
            ix = (right[0] * dx + fwd[0] * (-dz)) / mag
            iz = (right[1] * dx + fwd[1] * (-dz)) / mag
            self.vel[0] += ix * STRAFE_ACCEL * dt
            self.vel[1] += iz * STRAFE_ACCEL * dt
            sp = math.hypot(self.vel[0], self.vel[1])
            if sp > STRAFE_MAX_SPEED:
                self.vel[0] *= STRAFE_MAX_SPEED / sp
                self.vel[1] *= STRAFE_MAX_SPEED / sp
        else:
            sp = math.hypot(self.vel[0], self.vel[1])
            if sp > 0:
                dec = STRAFE_FRICTION * dt
                if sp <= dec:
                    self.vel = [0.0, 0.0]
                else:
                    self.vel[0] -= self.vel[0] / sp * dec
                    self.vel[1] -= self.vel[1] / sp * dec
        self.cam.pos[0] = max(-DODGE_ZONE_X, min(DODGE_ZONE_X, self.cam.pos[0] + self.vel[0] * dt))
        self.cam.pos[2] = max(-2.0, min(3.0, self.cam.pos[2] + self.vel[1] * dt))
        sp = math.hypot(self.vel[0], self.vel[1])
        if sp > 1.5 and self.gt - self.last_step > 0.28:
            self.play(self.snd_step)
            self.last_step = self.gt

    def update_dodge_hazards(self, dt):
        px, pz = self.cam.pos[0], self.cam.pos[2]
        for hz in list(self.dodge_hazards):
            k = hz["kind"]
            if hz["state"] == "warn" and self.gt >= hz["fire_at"]:
                hz["state"] = "active"
            if k == "proj":
                if hz["state"] == "active":
                    z_prev = hz["z"]
                    hz["z"] -= hz.get("speed", DODGE_PROJ_SPEED) * dt
                    if not hz["hit_done"]:
                        # hitbox = ตัวลูกบอลเท่านั้น (swept ตามระยะบินเฟรมนี้ กันทะลุ)
                        zc = max(hz["z"], min(z_prev, pz))
                        if math.hypot(px - hz["lane_x"], pz - zc) <= DODGE_PROJ_HIT_R:
                            hz["hit_done"] = True
                            hz["resolved"] = True
                            self.dodge_take_hit("ROCKET")
                            self.dodge_hazards.remove(hz)
                            continue
                        elif hz["z"] < pz - 0.6:
                            # บอลเลยตัวไปโดยไม่แตะ = หลบสำเร็จ ปิดจ็อบ ไม่มีผลย้อนหลัง
                            hz["hit_done"] = True
                            hz["resolved"] = True
                            self.dodge_dodged += 1
                    if hz["z"] < -3.5:
                        self.dodge_hazards.remove(hz)
            elif k == "aoe":
                if self.gt >= hz["detonate_at"] and not hz["hit_done"]:
                    hz["hit_done"] = True
                    hz["state"] = "boom"
                    if math.hypot(px - hz["cx"], pz - hz["cz"]) <= DODGE_AOE_R:
                        self.dodge_take_hit("MOLLY")
                    else:
                        self.dodge_dodged += 1
                    hz["resolved"] = True
                if self.gt >= hz.get("expire_at", 1e9):
                    self.dodge_hazards.remove(hz)
            else:  # beam
                if hz["state"] == "active":
                    hz["beam_x"] += hz["dir"] * hz["speed"] * dt
                    # โดนถ้าลำแสงกวาดผ่านตัว (ภายในความหนา 0.6)
                    if abs(hz["beam_x"] - px) <= 0.6 and not hz["hit_done"]:
                        hz["hit_done"] = True
                        self.dodge_take_hit("BEAM")
                        hz["resolved"] = True
                    if (hz["dir"] > 0 and hz["beam_x"] > DODGE_ZONE_X * 1.4) or \
                       (hz["dir"] < 0 and hz["beam_x"] < -DODGE_ZONE_X * 1.4):
                        if not hz["hit_done"]:
                            self.dodge_dodged += 1
                        self.dodge_hazards.remove(hz)
                elif self.gt >= hz.get("expire_at", 1e9):
                    self.dodge_hazards.remove(hz)

    def dodge_take_hit(self, label):
        self.dodge_hp = max(0, self.dodge_hp - DODGE_HIT_PENALTY)
        self.score = max(0, self.score - 60)
        self.dodge_flash = 0.35
        self.add_float(f"HIT! {label} -60", C_RED)
        self.play(self.snd_hazard)

    def update_placement(self, dt):
        if not self.targets and self.next_spawn_at is None and self.placement_pending is None:
            self.next_spawn_at = self.gt + 0.0
        if self.next_spawn_at is not None and self.gt >= self.next_spawn_at and not self.targets:
            self.next_spawn_at = None
            self.spawn_placement()
        # ถ้าเป้าอยู่นานเกินไปยังไม่ยิง (ปล่อยให้หาย) — กันค้าง
        for t in list(self.targets):
            if self.gt - t.born > 4.0:
                self.misses += 1
                self.placement_preaim.append(getattr(t, "preaim_deg", PLACEMENT_MAX_DEG))
                self.add_float("TOO SLOW", C_RED)
                self.targets.remove(t)
                self.placement_pending = None
                self.next_spawn_at = self.gt + 0.2

    def update_switch(self, dt):
        if not self.targets and self.switch_pending is None and self.switch_wave == 0:
            self.spawn_switch_wave()
        if self.switch_pending is not None and self.gt >= self.switch_pending and not self.targets:
            self.switch_pending = None
            self.spawn_switch_wave()
