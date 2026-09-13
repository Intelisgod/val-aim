# -*- coding: utf-8 -*-
"""การยิง + hit test (head/body) + shoot_placement/switch — ShootMixin (ย้าย verbatim)"""

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


class ShootMixin:
    def angle_to_deg(self, point):
        """มุม (องศา) ระหว่าง camera-forward กับเวกเตอร์ไปยัง point"""
        x, y, z = self.cam.to_cam(point)
        d = math.sqrt(x * x + y * y + z * z)
        if d == 0:
            return 0.0
        cosang = z / d
        return math.degrees(math.acos(max(-1.0, min(1.0, cosang))))

    def add_float(self, txt, color):
        self.floats.append({"t": txt, "c": color, "born": pygame.time.get_ticks(),
                            "dx": 30 + random.random() * 20, "dy": -10 + random.random() * 20})

    def target_screen_off(self, t):
        f = self.fl()
        x, y, z = self.cam.to_cam(t.pos)
        if z < 0.05:
            return (0, 0)
        return (f * x / z, -f * y / z)

    def register_head(self, t, spread=0.0):
        """คืน True ถ้านัดนี้โดน 'หัว' (ทดสอบหัวก่อนเสมอเมื่อ head เปิด)"""
        if not self.head_enabled():
            return False
        return t.is_head_hit(self.cam, spread)

    def hit_test(self, t, spread=0.0, shot_dir=None):
        """ยิงโดน 'หัว' หรือ 'ตัว' = โดน. คืน (โดนไหม, โดนหัวไหม).
        เช็คหัวก่อนเสมอ เพื่อให้ส่วนหัวที่ยื่นพ้นลำตัวยิงโดนจริง (หัวมีผลเฉพาะเมื่อ head เปิด)"""
        if shot_dir is None:
            shot_dir = Target.sample_dir(spread)
        if self.head_enabled() and t.is_head_hit(self.cam, shot_dir=shot_dir):
            return True, True
        return t.is_hit(self.cam, shot_dir=shot_dir), False

    def shoot(self):
        if self.state != "play":
            return
        if getattr(self, "resume_cd", 0) > 0:
            return
        md = self.mode
        if md == "spray":
            # spray ใช้กดค้าง auto-fire — คลิกเดี่ยวไม่ทำอะไร (จัดการใน update_spray)
            return
        if md == "placement":
            self.shoot_placement()
            return
        if md == "switch":
            self.shoot_switch()
            return
        if md == "gun":
            self.gun_shoot()
            return
        if md == "reaction" and not self.targets:
            # กดก่อนเป้าโผล่ = บวกโทษ 100ms เข้า RT รอบถัดไป (กันเก็งจังหวะ)
            self.early_clicks += 1
            self.early_penalty_ms += 100.0
            self.add_float("TOO EARLY! +100ms", (255, 170, 0))
            self.play(self.snd_miss)
            self.next_spawn_at = self.gt + self.reaction_gap()
            return
        if md == "strafe" and not self.strafe_moved:
            self.add_float("STRAFE FIRST!", (255, 170, 0))
            self.play(self.snd_miss)
            self.misses += 1
            self.strafe_shots += 1
            self.strafe_streak = 0
            return

        spread = self.strafe_spread() if md == "strafe" else 0.0
        shot_dir = Target.sample_dir(spread)
        hit_t = None
        hit_head = False
        for t in self.targets:
            if not (t.visible or md != "sniper"):
                continue
            ok, hd = self.hit_test(t, shot_dir=shot_dir)
            if ok:
                hit_t, hit_head = t, hd
                break

        if hit_t:
            is_head = hit_head
            if md == "sniper":
                px = hit_t.pos[0]
                # hitbox ตรงกับช่วงที่บอลโผล่ให้เห็นในประตูพอดี — เห็นแล้ว = ยิงโดนได้เสมอ
                if px < SNIPER_DOOR_L - SNIPER_R or px > SNIPER_DOOR_R + SNIPER_R:
                    return
                rt = (self.gt - hit_t.born) * 1000 if hit_t.born >= 0 else 0
                self.sniper_rts.append(rt)
                self.hits += 1
                self.sniper_hits += 1
                self.add_float(f"{rt:.0f}ms", (102, 255, 153))
                self.targets.remove(hit_t)
                self.play(self.snd_hit)
                self.hitmarks.append(pygame.time.get_ticks())
                if self.sniper_spawned >= SNIPER_TOTAL:
                    self.pending_end = self.gt + 0.4
                else:
                    self.next_spawn_at = self.gt + 0.6 + random.random() * 0.8
                return
            rt = (self.gt - hit_t.born) * 1000
            if md == "reaction" and self.early_penalty_ms:
                rt += self.early_penalty_ms
                self.early_penalty_ms = 0.0
            self.reaction_times.append(rt)
            self.hits += 1
            o = self.target_screen_off(hit_t)   # คำนวณครั้งเดียว (deterministic — ค่าเท่าเดิมเป๊ะ)
            self.shot_data.append({"x": o[0], "y": o[1], "hit": True})
            if md == "reaction":
                self.add_float(f"{rt:.0f}ms", (102, 255, 153))
                self.targets.remove(hit_t)
                self.reaction_done += 1
                if self.reaction_done >= REACTION_COUNT:
                    self.pending_end = self.gt + 0.4
                else:
                    self.next_spawn_at = self.gt + self.reaction_gap()
            elif md == "strafe":
                self.strafe_shots += 1
                if self.strafe_shots == 1:
                    self.strafe_perfect += 1
                    self.strafe_streak += 1
                    self.strafe_best_streak = max(self.strafe_best_streak, self.strafe_streak)
                    self.add_float(f"x{self.strafe_streak} PERFECT!" if self.strafe_streak >= 2 else "PERFECT!",
                                   C_PALE_GOLD)
                else:
                    self.strafe_streak = 0
                    self.add_float("HIT", (102, 255, 153))
                self.strafe_times.append(rt)
                self.targets.remove(hit_t)
                self.strafe_spawn_at = self.gt + 0.45
            elif md == "dodge":
                pts = DODGE_KILL_PTS + (HEAD_BONUS if is_head else 0)
                self.score += pts
                if is_head:
                    self.headshots += 1
                    self.add_float("HEADSHOT +%d" % pts, C_PALE_GOLD)
                else:
                    self.add_float(f"+{pts}", (102, 255, 153))
                self.targets.remove(hit_t)
                self.spawn_dodge_target()
            else:
                base = 150 if md == "precision" else 80 if md == "tracking" else 100
                pts = round(base + max(0.0, 1 - rt / 3000) * 100)
                if is_head:
                    self.headshots += 1
                    pts += HEAD_BONUS
                    self.add_float(f"HEADSHOT +{pts}", C_PALE_GOLD)
                else:
                    self.add_float(f"+{pts}", (102, 255, 153))
                self.score += pts
                self.targets.remove(hit_t)
                self.spawn_targets()
            self.play(self.snd_head if is_head else self.snd_hit)
            self.hitmarks.append(pygame.time.get_ticks())
        else:
            self.misses += 1
            if md in ("reaction", "sniper", "strafe"):
                self.add_float("miss", C_RED)
                if md == "strafe":
                    self.strafe_shots += 1
                    self.strafe_streak = 0
            elif md == "dodge":
                self.add_float("miss", C_RED)   # dodge: พลาดไม่หักคะแนน เน้นหลบ+เล็ง
            else:
                self.score = max(0, self.score - 50)
                self.add_float("-50 MISS", C_RED)
            best, off = 1e18, None
            for t in self.targets:
                o = self.target_screen_off(t)
                d = math.hypot(o[0], o[1])
                if d < best:
                    best, off = d, o
            if off:
                self.shot_data.append({"x": off[0], "y": off[1], "hit": False})
            self.play(self.snd_miss)

    def shoot_placement(self):
        if not self.targets:
            self.misses += 1
            self.add_float("miss", C_RED)
            self.play(self.snd_miss)
            return
        t = self.targets[0]
        ok, is_head = self.hit_test(t)
        if ok:
            rt = (self.gt - t.born) * 1000
            self.reaction_times.append(rt)
            err = getattr(t, "preaim_deg", PLACEMENT_MAX_DEG)
            self.placement_preaim.append(err)
            self.hits += 1
            o = self.target_screen_off(t)
            self.shot_data.append({"x": o[0], "y": o[1], "hit": True})
            # คะแนน = ฐาน + โบนัสพรีเอม(องศายิ่งน้อยยิ่งดี) + โบนัสเร็ว + โบนัสหัว
            preaim_q = max(0.0, (PLACEMENT_MAX_DEG - err) / (PLACEMENT_MAX_DEG - PLACEMENT_GOOD_DEG))
            preaim_q = min(1.0, preaim_q)
            pts = round(80 + preaim_q * 120 + max(0.0, 1 - rt / 1200) * 60)
            if is_head:
                self.headshots += 1
                pts += HEAD_BONUS
            self.score += pts
            tag = "HEADSHOT " if is_head else ""
            self.add_float(f"{tag}+{pts} ({err:.1f}°)", C_PALE_GOLD if is_head else (102, 255, 153))
            self.targets.remove(t)
            self.placement_pending = None
            self.play(self.snd_head if is_head else self.snd_hit)
            self.hitmarks.append(pygame.time.get_ticks())
            self.next_spawn_at = self.gt + 0.18 + random.random() * 0.35
        else:
            self.misses += 1
            self.score = max(0, self.score - 30)
            self.add_float("-30 MISS", C_RED)
            o = self.target_screen_off(t)
            self.shot_data.append({"x": o[0], "y": o[1], "hit": False})
            self.play(self.snd_miss)

    def shoot_switch(self):
        hit_t = None
        hit_head = False
        for t in self.targets:
            ok, hd = self.hit_test(t)
            if ok:
                hit_t, hit_head = t, hd
                break
        if hit_t:
            is_head = hit_head
            self.hits += 1
            o = self.target_screen_off(hit_t)
            self.shot_data.append({"x": o[0], "y": o[1], "hit": True})
            # switch time = เวลาตั้งแต่คิลก่อนหน้า
            sw = self.gt - self.switch_last_kill
            self.switch_kill_times.append(sw * 1000)
            self.switch_last_kill = self.gt
            pts = SWITCH_BASE_PTS + (HEAD_BONUS if is_head else 0)
            if is_head:
                self.headshots += 1
            self.score += pts
            tag = "HEADSHOT " if is_head else ""
            self.add_float(f"{tag}+{pts}", C_PALE_GOLD if is_head else (102, 255, 153))
            self.targets.remove(hit_t)
            self.play(self.snd_head if is_head else self.snd_hit)
            self.hitmarks.append(pygame.time.get_ticks())
            if not self.targets:
                # เคลียร์ wave — โบนัสตามความเร็ว
                clear_t = self.gt - self.switch_wave_start
                self.switch_wave_clears.append(clear_t)
                self.switch_waves_cleared += 1
                bonus = round(max(0.0, 1 - clear_t / 4.0) * SWITCH_CLEAR_BONUS)
                self.score += bonus
                self.add_float(f"WAVE CLEAR +{bonus}", C_GOLD)
                self.switch_pending = self.gt + 0.45
        else:
            self.misses += 1
            self.score = max(0, self.score - 40)
            self.add_float("-40 MISS", C_RED)
            best, off = 1e18, None
            for t in self.targets:
                o = self.target_screen_off(t)
                d = math.hypot(o[0], o[1])
                if d < best:
                    best, off = d, o
            if off:
                self.shot_data.append({"x": off[0], "y": off[1], "hit": False})
            self.play(self.snd_miss)
