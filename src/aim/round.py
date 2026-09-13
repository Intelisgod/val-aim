# -*- coding: utf-8 -*-
"""วงจรรอบ/สถานะรอบ + spawn เป้าทุกโหมด — RoundMixin (ย้าย verbatim)"""

import pygame
import math
import random
import json
import os
import sys
import time
import array

from .config import *
from .ranks import *
from .data import DATA_FILE, load_data, save_data, trim_history
from .camera import Camera, focal_len, VFOV_RAD
from .target import Target
from .stability import Stability


class RoundMixin:
    def reset_round(self):
        self.gt = 0.0
        self.score = 0
        self.hits = 0
        self.misses = 0
        self.reaction_times = []
        self.shot_data = []
        self.time_left = float(self.duration)
        self.countdown = 0.0
        self.cd_last_beep = 99
        self.pending_end = None
        self.resume_cd = 0.0
        # reaction
        self.reaction_done = 0
        self.next_spawn_at = None
        self.lmb_down = False       # ปุ่มซ้ายค้างอยู่ไหม — reaction ไม่ปล่อยเป้าใหม่จนกว่าจะปล่อยปุ่ม
        self.lmb_up_at = 0.0
        self.early_penalty_ms = 0.0
        self.early_clicks = 0
        # strafe
        self.vel = [0.0, 0.0]
        self.static_since = 0.0
        self.strafe_respawn = False
        self.strafe_target_idx = 0
        self.strafe_shots = 0
        self.strafe_perfect = 0
        self.strafe_streak = 0
        self.strafe_best_streak = 0
        self.strafe_times = []
        self.strafe_moved = True
        self.strafe_spawn_at = None
        self.last_step = 0.0
        # sniper
        self.sniper_spawned = 0
        self.sniper_hits = 0
        self.sniper_missed = 0
        self.sniper_rts = []
        # head/body
        self.headshots = 0
        self.best_streak = 0
        # spray
        self.spray_weapon = getattr(self, "spray_weapon", "vandal")
        self.spray_firing = False
        self.spray_next_shot = 0.0
        self.spray_shots = 0
        self.spray_onbody = 0
        self.spray_heads = 0
        self.spray_mag = SPRAY_WEAPONS[self.spray_weapon]["mag"]
        self.spray_reloading_until = 0.0
        # รีคอยล์แบบเกมจริง (aim/stability.py จากไฟล์เกม): crosshair ไม่ขยับ กระสุนเบี่ยงตาม pattern
        # recoil_pitch/yaw = offset ปัจจุบันของ pattern (องศา) — ผู้เล่นดึงเมาส์ลงเท่านี้ให้กระสุนกลับมาที่เป้า
        self.spray_stab = Stability(self.spray_weapon, SPRAY_WEAPONS[self.spray_weapon]["rps"])
        self.recoil_pitch = 0.0      # องศา pattern แนวตั้ง (บวก = กระสุนสูงกว่า crosshair)
        self.recoil_yaw = 0.0        # องศา pattern แนวนอน (บวก = ขวา)
        self.spray_marks = []        # รอยกระสุนบนเป้า: (yaw, pitch องศาของกระสุนเทียบใจกลางเป้า, hit, head)
        # dodge
        self.dodge_hp = DODGE_HP_MAX
        self.dodge_hazards = []      # list of dict hazard
        self.dodge_next_haz = 0.0
        self.dodge_dodged = 0
        self.dodge_total_haz = 0
        self.dodge_flash = 0.0
        # placement
        self.placement_preaim = []   # องศาคลาดต่อเป้า
        self.placement_spot_i = -1
        self.placement_pending = None
        # switch
        self.switch_wave = 0
        self.switch_waves_cleared = 0
        self.switch_kill_times = []  # เวลา switch ระหว่างคิล (วินาที)
        self.switch_wave_clears = [] # เวลาเคลียร์ต่อ wave
        self.switch_last_kill = 0.0
        self.switch_wave_start = 0.0
        self.switch_pending = None
        self.floats = []
        self.hitmarks = []
        self.keys_down = set()
        # gunfight
        self.reset_gun()

    def start_countdown(self):
        self.reset_round()
        self.cam = Camera()
        self.targets = []
        self.state = "countdown"
        self.countdown = 3.35
        self.cd_last_beep = 99
        self.grab_mouse(True)

    def begin_play(self):
        self.state = "play"
        self.gt = 0.0
        # PB ของ config ปัจจุบัน — คำนวณครั้งเดียวตอนเริ่ม ไม่ query history ทุกเฟรม
        self.pb_display = None
        if self.mode == "reaction":
            prev = [e["rt"] for e in self.history_for("reaction", self.reaction_variant)
                    if e.get("rt", 0) > 0]
            if prev:
                self.pb_display = f"PB {min(prev)}ms"
        elif self.mode == "sniper":
            prev = [e.get("score", 0) for e in self.history_for("sniper")]
            if prev and max(prev) > 0:
                self.pb_display = f"PB {max(prev)}"
        elif self.mode == "spray":
            prev = [e.get("score", 0) for e in self.history_for("spray", duration=self.duration)
                    if e.get("variant", "vandal") == self.spray_weapon]
            if prev and max(prev) > 0:
                self.pb_display = f"PB {max(prev):,}"
        else:
            prev = [e.get("score", 0) for e in
                    self.history_for(self.mode, duration=self.duration, size=self.size_key)]
            if prev and max(prev) > 0:
                self.pb_display = f"PB {max(prev):,}"
        if self.mode == "reaction":
            self.next_spawn_at = self.gt + self.reaction_gap()
        elif self.mode == "sniper":
            self.next_spawn_at = self.gt + 0.6 + random.random() * 0.8
        elif self.mode == "spray":
            self.spawn_spray_bot()
            self.spray_mag = SPRAY_WEAPONS[self.spray_weapon]["mag"]
        elif self.mode == "dodge":
            self.spawn_dodge_target()
            self.dodge_next_haz = self.gt + 0.8   # ให้ขยับตั้งหลักก่อนสกิลแรก
        elif self.mode == "placement":
            self.next_spawn_at = self.gt + 0.25
        elif self.mode == "switch":
            self.spawn_switch_wave()
        elif self.mode == "gun":
            self.begin_gun()
        else:
            self.spawn_targets()
        if self.mode == "strafe":
            self.strafe_moved = True   # เป้าแรกยกเว้น

    def end_game(self):
        self.state = "results"
        self.grab_mouse(False)
        self.score_saved = False
        self.text_focus = None
        # สรุปผล
        total = self.hits + self.misses
        self.res_acc = round(self.hits / total * 100) if total else 0
        rts = self.reaction_times
        self.res_avg_rt = round(sum(rts) / len(rts)) if rts else 0
        if self.mode == "reaction":
            self.score = max(0, round((1000 - self.res_avg_rt) * REACTION_COUNT))
        elif self.mode == "strafe":
            self.score = self.hits
        elif self.mode == "sniper":
            self.score = self.sniper_hits
        # spray/dodge/placement/switch: self.score สะสมระหว่างเล่นแล้ว ไม่ override
        # headshot %
        self.res_hs = round(self.headshots / self.hits * 100) if self.hits else 0
        if self.mode == "spray":
            self.res_onbody = round(self.spray_onbody / self.spray_shots * 100) if self.spray_shots else 0
        # personal best จาก history
        self.res_pb = self.is_personal_best()
        # บันทึก history อัตโนมัติ
        ent = {"mode": self.mode, "variant": self.reaction_variant, "score": self.score,
               "acc": self.res_acc, "rt": self.res_avg_rt, "duration": self.duration,
               "size": self.size_key, "streak": self.strafe_best_streak,
               "hs": self.headshots, "shots": self.shot_data[-60:], "ts": pygame.time.get_ticks(),
               "at": int(time.time())}  # epoch จริง — dashboard ใช้ join กับวันที่แมตช์ (ts เดิมคือ ticks ใช้ไม่ได้)
        if self.mode == "strafe":
            th = self.hits
            ent["acc"] = round(self.strafe_perfect / th * 100) if th else 0
            ent["rt"] = round(sum(self.strafe_times) / len(self.strafe_times)) if self.strafe_times else 0
        if self.mode == "sniper":
            ent["acc"] = round(self.sniper_hits / SNIPER_TOTAL * 100)
            ent["rt"] = round(sum(self.sniper_rts) / len(self.sniper_rts)) if self.sniper_rts else 0
        if self.mode == "spray":
            ent["acc"] = self.res_onbody       # "บนเป้า %" แทน accuracy
            ent["variant"] = self.spray_weapon
            ent["srev"] = SPRAY_SCORE_REV      # สูตรคะแนนรุ่นนี้ — รอบยุคบั๊ก reload-burst ไม่มีคีย์นี้
        if self.mode == "dodge":
            ent["dodged"] = self.dodge_dodged
            ent["total_haz"] = self.dodge_total_haz
        if self.mode == "placement":
            ent["rt"] = round(sum(self.placement_preaim) / len(self.placement_preaim) * 10) \
                if self.placement_preaim else 0   # เก็บองศาเฉลี่ย x10 ในช่อง rt (เลี่ยงเพิ่มคีย์)
        if self.mode == "switch":
            ent["rt"] = round(sum(self.switch_kill_times) / len(self.switch_kill_times)) \
                if self.switch_kill_times else 0   # avg switch time (ms)
            ent["streak"] = self.switch_waves_cleared
        if self.mode == "gun":
            self.gun_fill_entry(ent)      # variant = ปืน, drill, kills/deaths, rt = avg TTK
        self.last_entry = ent
        h = self.data["history"]
        h.append(ent)
        trim_history(h)                  # เพดาน + ถอด shots รอบเก่า — เหตุผลดู config.HISTORY_MAX
        save_data(self.data)

    def history_for(self, md, variant=None, duration=None, size=None):
        out = []
        for e in self.data["history"]:
            if e.get("mode") != md:
                continue
            if md == "spray" and not spray_current(e):
                continue        # คะแนนยุคบั๊ก reload-burst — เทียบ PB กับรอบใหม่ไม่ได้ (config.SPRAY_SCORE_REV)
            if md == "reaction" and variant and e.get("variant", "static") != variant:
                continue
            if md == "gun" and variant and e.get("variant") != variant:
                continue
            if duration is not None and e.get("duration") != duration:
                continue
            if size is not None and e.get("size") != size:
                continue
            out.append(e)
        return out

    def is_personal_best(self):
        # PB เทียบเฉพาะ config เดียวกัน (เวลา+ขนาดเป้า) ถึงจะแฟร์
        if self.mode == "reaction":
            hist = self.history_for("reaction", self.reaction_variant)
        elif self.mode == "sniper":
            hist = self.history_for("sniper")
        elif self.mode == "spray":
            hist = [e for e in self.history_for("spray", duration=self.duration)
                    if e.get("variant", "vandal") == self.spray_weapon]
        elif self.mode == "gun":
            hist = [e for e in self.history_for("gun", self.gun_weapon, duration=self.duration)
                    if e.get("drill", "duel") == self.gun_drill]
        else:
            hist = self.history_for(self.mode, duration=self.duration, size=self.size_key)
        if self.mode == "reaction":
            if self.res_avg_rt <= 0:
                return False
            prev = [e["rt"] for e in hist if e.get("rt", 0) > 0]
            return not prev or self.res_avg_rt < min(prev)
        prev = [e.get("score", 0) for e in hist]
        return self.score > 0 and (not prev or self.score > max(prev))

    def target_radius(self):
        r = SIZES[self.size_key]
        if self.mode == "precision":
            return r * 0.6
        if self.mode == "reaction":
            return SIZES["large"]
        if self.mode == "spray":
            return 0.42          # บอทลำตัวขนาดคงที่ ระยะกลาง
        if self.mode in ("placement", "switch", "dodge"):
            return r             # ใช้ขนาดที่ผู้เล่นเลือก (head = 0.5R)
        return r

    def head_modes(self):
        """โหมดที่ใช้ head/body เป็นกลไกหลักเสมอ"""
        return self.mode in ("spray", "dodge", "placement", "switch", "gun")

    def head_enabled(self):
        """หัวมีผล (วาด+โบนัส) หรือไม่ในเฟรมนี้ — โหมดใหม่เปิดเสมอ, คลาสสิกตาม setting"""
        return self.head_modes() or self.S.get("headshots", False)

    def reaction_gap(self):
        """ช่องไฟสุ่มก่อนเป้า reaction ถัดไป (วิ) — ดู REACTION_GAP_MIN/MAX ใน config"""
        return REACTION_GAP_MIN + random.random() * (REACTION_GAP_MAX - REACTION_GAP_MIN)

    def rand_pos(self):
        return [random.uniform(-7, 7), random.uniform(1.2, 5.7), random.uniform(10, 13)]

    def spawn_one(self):
        r = self.target_radius()
        if self.mode == "reaction" and self.reaction_variant == "static":
            f = self.cam.forward()
            p = [self.cam.pos[0] + f[0] * 8, max(1.0, self.cam.pos[1] + f[1] * 8), self.cam.pos[2] + f[2] * 8]
        else:
            p = self.rand_pos()
            for _ in range(15):
                if all(math.hypot(p[0] - t.pos[0], p[1] - t.pos[1]) > r * 3 for t in self.targets):
                    break
                p = self.rand_pos()
        t = Target(p, r)
        t.born = self.gt
        if self.mode == "tracking":
            t.vx = random.choice([-1, 1]) * (1.2 + random.random() * 1.8)
        self.targets.append(t)
        return t

    def spawn_targets(self):
        want = 1 if self.mode in ("flick", "strafe", "reaction") else 3
        while len(self.targets) < want:
            self.spawn_one()
            if self.mode == "strafe":
                self.strafe_shots = 0
                self.strafe_target_idx += 1
                self.strafe_moved = (self.strafe_target_idx == 1)

    def spawn_sniper_ball(self):
        if self.sniper_spawned >= SNIPER_TOTAL:
            return
        self.sniper_spawned += 1
        from_left = random.random() < 0.5
        t = Target([-15.0 if from_left else 15.0, SNIPER_Y, SNIPER_Z], SNIPER_R)
        t.vx = SNIPER_SPEED if from_left else -SNIPER_SPEED
        t.end_x = 15.0 if from_left else -15.0
        t.born = -1.0
        t.visible = False
        self.targets.append(t)
        self.next_spawn_at = None

    def spawn_spray_bot(self):
        """บอทลำตัวนิ่งระยะกลางสำหรับฝึกคุมรีคอยล์"""
        r = self.target_radius()
        # ลำตัวอยู่ระดับอก เพื่อให้หัวอยู่ราวระดับสายตา
        t = Target([0.0, EYE_Y + 0.05, SPRAY_TARGET_Z], r)
        t.born = self.gt
        t.alpha = 1.0
        self.targets.append(t)
        return t

    def spawn_placement(self):
        """หัวบอทโผล่ที่ 'มุม' หนึ่งจุด ระดับหัวเสมอ + วัด pre-aim error ทันที"""
        r = self.target_radius()
        i = random.randrange(len(PLACEMENT_SPOTS))
        # กันโผล่ซ้ำจุดเดิมติดกัน
        if i == self.placement_spot_i and len(PLACEMENT_SPOTS) > 1:
            i = (i + 1) % len(PLACEMENT_SPOTS)
        self.placement_spot_i = i
        sx, sz = PLACEMENT_SPOTS[i]
        y = random.uniform(PLACEMENT_Y_LO, PLACEMENT_Y_HI)
        t = Target([sx, y, sz], r)
        t.born = self.gt
        t.alpha = 0.0
        # วัด pre-aim error: มุมระหว่าง forward กับหัวเป้า ณ วินาทีที่โผล่
        err = self.angle_to_deg(t.head_pos())
        t.preaim_deg = err
        self.placement_pending = err
        self.targets.append(t)
        return t

    def spawn_switch_wave(self):
        """หลายเป้าพร้อมกัน ระดับหัว เรียงแนวนอน (สถานการณ์ retake 1vX)"""
        self.targets = []
        r = self.target_radius()
        # จำนวนเป้าปรับตามขนาด: เป้าเล็ก = ยากกว่า → มากกว่า
        n = {"small": 4, "medium": 3, "large": 3}.get(self.size_key, 3)
        z = 12.0
        xs = []
        spread = 7.0
        for k in range(n):
            xs.append(-spread + (2 * spread) * (k / (n - 1)) if n > 1 else 0.0)
        random.shuffle(xs)
        for x in xs:
            jx = x + random.uniform(-0.6, 0.6)
            y = random.uniform(PLACEMENT_Y_LO, PLACEMENT_Y_HI)
            t = Target([max(-8.5, min(8.5, jx)), y, z + random.uniform(-1.0, 1.0)], r)
            t.born = self.gt
            t.alpha = 0.0
            self.targets.append(t)
        self.switch_wave += 1
        self.switch_wave_start = self.gt
        self.switch_last_kill = self.gt

    def spawn_dodge_hazard(self):
        """สร้าง hazard 1 อัน: telegraph → active → resolve (ลอจิกล้วนตัวเลข)"""
        self.dodge_total_haz += 1
        kind = random.choice(["proj", "proj", "aoe", "aoe", "beam"])
        px, pz = self.cam.pos[0], self.cam.pos[2]
        hz = {"kind": kind, "state": "warn", "born": self.gt,
              "fire_at": self.gt + DODGE_TELEGRAPH, "resolved": False, "hit_done": False}
        if kind == "proj":
            # พุ่งมาตามเลนจาก z ไกล เล็งตำแหน่งผู้เล่นปัจจุบัน (เลน x คงที่)
            hz["lane_x"] = max(-DODGE_ZONE_X, min(DODGE_ZONE_X, px + random.uniform(-1.2, 1.2)))
            hz["z"] = 13.0
            hz["impact_z"] = pz
            # เวลาบินคงที่ (config.DODGE_PROJ_FLIGHT) — ยืนหน้า/หลังได้เวลาตอบสนองเท่ากัน
            hz["speed"] = (hz["z"] - pz) / DODGE_PROJ_FLIGHT
        elif kind == "aoe":
            # วงพื้นตกข้างหน้าผู้เล่น (ผู้เล่นยังอยู่ในวง ต้องเดินออก) — เหตุผลดู config.DODGE_AOE_AHEAD
            hz["cx"] = max(-DODGE_ZONE_X, min(DODGE_ZONE_X, px + random.uniform(-DODGE_AOE_SIDE, DODGE_AOE_SIDE)))
            hz["cz"] = max(-1.5, min(2.5, pz + random.uniform(*DODGE_AOE_AHEAD)))
            hz["detonate_at"] = self.gt + DODGE_TELEGRAPH + 0.15
            hz["expire_at"] = hz["detonate_at"] + DODGE_AOE_LIFE
        else:  # beam — กำแพงกวาดข้ามโซนแนวนอน
            hz["dir"] = random.choice([-1, 1])
            hz["beam_x"] = DODGE_ZONE_X * (1.4 if hz["dir"] > 0 else -1.4)
            hz["fire_at"] = self.gt + DODGE_TELEGRAPH
            hz["speed"] = 7.5
            hz["expire_at"] = hz["fire_at"] + (2 * DODGE_ZONE_X * 1.4) / 7.5 + 0.3
        self.dodge_hazards.append(hz)

    def spawn_dodge_target(self):
        """เป้าหัวสำหรับ flick ยิงระหว่างหลบ (ระดับหัว)"""
        r = self.target_radius()
        x = random.uniform(-6.5, 6.5)
        y = random.uniform(PLACEMENT_Y_LO, PLACEMENT_Y_HI)
        t = Target([x, y, random.uniform(10.5, 12.5)], r)
        t.born = self.gt
        t.alpha = 0.0
        self.targets.append(t)
        return t

    def resume_play(self):
        self.state = "play"
        self.resume_cd = 3.0
        self.grab_mouse(True)
