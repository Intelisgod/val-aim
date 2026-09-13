# -*- coding: utf-8 -*-
"""โหมด GUNFIGHT (mode id "gun") — ยิงบอทหุ่นคนด้วยปืนจริง (Op/Vandal/Phantom/Sheriff) — GunMixin

ดริล (gun_drill):
  duel   : บอทโผล่ทีละตัวระยะ 8–30 ม. ยิงสวนหลัง reaction ของมัน — ฆ่าให้เร็ว รอดให้ได้
  hold   : Op จับมุมช่องกำแพง 27 ม. บอทโผล่จริง / จิ้มหลอก (jiggle) / วิ่งข้าม — ยิงหลอก = เสียลูกเลื่อน 1.67 วิ
           กำแพงบังกระสุนจริง (gun_wall_hit) ไม่ใช่แค่บังภาพ — ยิงโดนได้เฉพาะแนวยิงที่ลอดช่อง
  quick  : เริ่มไม่สโคปทุกครั้ง บอทโผล่ 15–30 ม. → สโคปแล้วยิง (hipfire Op 5° = แทบไม่มีทางโดน)
  repo   : ยิงแล้วต้องย้ายที่ ≥2 ม. ภายใน 1.6 วิ (นับจาก "นัดแรก" ของชุด — ยิงต่อเนื่องไม่ต่อเวลา)
           ไม่งั้นโดน pre-fire ตาย — วินัยหลังยิงของคน Op
fire rate ไม่ขึ้นกับ FPS: gun_shoot ใช้ตารางเวลานัดถัดไป (gun_next_shot_at) ไม่ใช่ "นัดก่อน + ช่วง"

กติกาปืนอยู่ใน guns.py (ตัวเลขจากเกมจริง) — ไฟล์นี้คือ gameplay/HUD/ผลลัพธ์
คะแนนยังไม่จัดแรงค์ (ไม่มีข้อมูลพอสอบเทียบ) — วัดฟอร์มด้วย K/D, TTK, HS%, ACC แทน (ดู results)"""
import math
import random

import pygame

from .config import (C_RED, C_GREEN, C_TEXT, C_DIM, C_PALE_GOLD, C_GOLD, C_GRID, EYE_Y, ROOM_H, ROOM_X, WALL_Z,
                     STRAFE_ACCEL, STRAFE_FRICTION)
from .camera import focal_len
from . import guns
from .guns import WEAPONS, Bot
from .stability import Stability

GUN_DRILLS = [("duel", "DUEL", "ดวล 1v1 ทุกระยะ"), ("hold", "OP HOLD", "จับมุม แยกจิ้มหลอก"),
              ("quick", "QUICKSCOPE", "สโคปแล้วยิงให้ทัน"), ("repo", "REPOSITION", "ยิงแล้วต้องย้ายที่")]
GUN_DRILL_NAME = {d[0]: d[1] for d in GUN_DRILLS}
GUN_ORIGIN_Z = -18.0        # ยืนถอยหลังห้อง → ระยะถึงกำแพงหลัง 32 ม. (ระยะ Op จริง)
GUN_GRID_Z0 = -22           # ตารางพื้นส่วนขยายเริ่มที่ z นี้ (ห้องเดิมมีถึง z=2) — glrender ใช้ค่าเดียวกัน
GUN_MOVE_X, GUN_MOVE_ZB, GUN_MOVE_ZF = 3.0, 1.0, 3.5   # ขอบเขตเดินรอบจุดเริ่ม (ซ้าย/ขวา, ถอย, เดินหน้า)
BOT_RT = (0.35, 0.60)       # reaction ของบอทก่อนยิงสวน (วิ)
BOT_FIRE_GAP = 0.45
BOT_HIT_P = 0.35            # โอกาสนัดของบอทโดนเรา (คูณ 0.6 ถ้าเราขยับ, +0.15 ถ้ายืนนิ่งเกิน 1 วิ)
BOT_HEAD_P = 0.12
BOT_DMG_BODY, BOT_DMG_HEAD = 40, 160
HOLD_WALL_DZ, HOLD_GAP = 27.0, 1.2      # กำแพงห่างจากจุดเริ่ม + ครึ่งความกว้างช่อง
REPO_DIST, REPO_TIME = 2.0, 1.6
KILL_BASE, KILL_TTK_BONUS, KILL_HS_BONUS, DEATH_PEN, BAIT_PEN, PREFIRE_PEN = 100, 100, 40, 100, 30, 60
# fire rate ไม่ขึ้นกับ FPS: นัดที่ยิงได้ "ช้ากว่ากำหนด" เพราะรอเฟรม (late) จะถูกหักคืนในช่วงถัดไป — แต่หักได้
# ไม่เกินความยาวเฟรมที่ทำให้ช้า และเฟรมที่ยาวกว่านี้ (เกมค้าง/สลับหน้าต่าง, dt ถูก clamp 0.1 ใน game.py)
# ไม่ชดเชยเลย → ไม่มี "ยิงตามเก็บ" หลายนัดรวดหลังค้าง (บั๊กแบบเดียวกับ spray reload-burst ที่เคยเจอ)
GUN_FIRE_CARRY_MAX_DT = 0.05


class GunMixin:
    # ───────────────────────── สถานะ ─────────────────────────
    def reset_gun(self):
        self.gun_weapon = getattr(self, "gun_weapon", "vandal")
        self.gun_drill = getattr(self, "gun_drill", "duel")
        w = WEAPONS[self.gun_weapon]
        self.bots = []
        self.gun_zoom_i = -1
        self.gun_zoom = 1.0
        # รีคอยล์/สเปรดจากค่าจริงในไฟล์เกม (aim/stability.py + riot_data.py) — crosshair ไม่ขยับ กระสุนวิ่งตาม pattern
        self.gun_stab = Stability(self.gun_weapon, w["rps"])
        self.gun_marks = []             # รอยกระสุนบนกำแพง/พื้น [(world_pt, t)] — ให้เห็น pattern เหมือนในเกม
        self.gun_last_shot = -9.0
        self.gun_last_shot_prev = -9.0
        self.gun_next_shot_at = 0.0     # ตารางเวลานัดถัดไป (gt) — ไม่ใช่ "เวลานัดก่อน + ช่วง" ดู gun_shoot
        self.gun_dt = 1.0 / 60          # dt ของเฟรมล่าสุด (update_gun) — เพดานการชดเชยเศษเวลาของ fire rate
        self.gun_mag = w["mag"]
        self.gun_reload_until = 0.0
        self.gun_firing = False
        self.gun_crouch = False
        self.gun_kills = 0
        self.gun_deaths = 0
        self.gun_shots = 0
        self.gun_hits = 0
        self.gun_hs = 0
        self.gun_legs = 0
        self.gun_ttk = []
        self.gun_baited = 0
        self.gun_prefired = 0
        self.gun_scope_times = []       # quick: เวลาโผล่→สโคป (ms)
        self.gun_hp, self.gun_shield = guns.PLAYER_HP, guns.PLAYER_SHIELD
        self.gun_respawn_at = None
        self.gun_next_bot_at = None
        self.gun_origin = None
        self.gun_shot_pos = None        # repo: จุดยืนตอนยิง "นัดแรก" ของชุด (anchor) — ไม่เลื่อนตามนัดถัดๆ ไป
        self.gun_repo_deadline = None   # repo: ต้องห่างจาก anchor ≥ REPO_DIST ก่อนเวลานี้ (None = ไม่มีหนี้ค้าง)
        self.gun_repo_ok = 0            # repo: ย้ายทันกี่ครั้ง
        self.gun_still_since = 0.0
        self.gun_flash = 0.0            # โดนยิง: จอวาบแดง
        self.gun_dmg_taken = 0

    def begin_gun(self):
        self.cam.pos = [0.0, EYE_Y, GUN_ORIGIN_Z]
        self.gun_origin = list(self.cam.pos)
        self.vel = [0.0, 0.0]
        self.gun_next_bot_at = self.gt + 0.9
        self.targets = []

    def gun_w(self):
        return WEAPONS[self.gun_weapon]

    def gun_speed(self):
        return math.hypot(self.vel[0], self.vel[1])

    def gun_run_speed(self):
        w = self.gun_w()
        sp = w["run_speed"]
        if self.gun_zoom > 1.0:
            sp *= w.get("scoped_move", w.get("ads_move", 1.0))
        if self.gun_crouch:
            sp *= 0.5
        return sp

    def gun_sens_mult(self):
        return guns.zoom_sens_mult(self.gun_zoom, self.S.get("scoped_sens", 1.0))

    # ───────────────────────── input ─────────────────────────
    def gun_rmb(self, down):
        """RMB: ปืนไรเฟิล = กดค้าง ADS | Op = กดวน 2.5x → 5x → ออก"""
        if self.state != "play":
            return
        w = self.gun_w()
        zooms = w["zooms"]
        if not zooms:
            return
        if w["kind"] == "sniper":
            if not down:
                return
            self.gun_zoom_i = (self.gun_zoom_i + 1) % (len(zooms) + 1)
            if self.gun_zoom_i == len(zooms):
                self.gun_zoom_i = -1
        else:
            self.gun_zoom_i = 0 if down else -1
        self.gun_zoom = zooms[self.gun_zoom_i] if self.gun_zoom_i >= 0 else 1.0
        if self.gun_drill == "quick" and self.gun_zoom > 1.0:
            for b in self.bots:
                if b.alive and b.exposed and b.meta.get("scope_t") is None:
                    b.meta["scope_t"] = self.gt

    def gun_unscope(self):
        self.gun_zoom_i = -1
        self.gun_zoom = 1.0

    def gun_reload(self):
        w = self.gun_w()
        if self.gun_reload_until > 0 or self.gun_mag >= w["mag"]:
            return
        self.gun_reload_until = self.gt + w["reload"]
        self.gun_unscope()
        self.gun_stab.reset()          # รีโหลด = pattern เริ่มใหม่ (เหมือนเกม)
        self.add_float("RELOADING", C_DIM)

    def gun_view_offset(self):
        """กล้อง 'เด้ง' ที่ตาเห็น (เรเดียน) — pop วูบเดียว + Sheriff ตามรีคอยล์ 80% ไม่กระทบทิศกระสุน"""
        dp, dy = self.gun_stab.camera_offset(self.gt)
        return math.radians(dp), math.radians(dy)

    def gun_ads_state(self):
        """(ads, zoomed): ไรเฟิล/ปืนสั้นกด ADS = ads, Op สโคป = zoomed (ใช้ตาราง ZoomedStability)"""
        if self.gun_zoom <= 1.0:
            return False, False
        return (self.gun_w()["kind"] != "sniper"), (self.gun_w()["kind"] == "sniper")

    def gun_next_spread(self):
        """สเปรดกรวย (องศา) ของนัดถัดไป ณ ตอนนี้ — ไว้วาด crosshair ถ่าง"""
        ads, zoomed = self.gun_ads_state()
        fe = self.gun_stab.spread(self.gt, self.gun_crouch, ads, zoomed)
        return guns.spread_deg(self.gun_weapon, self.gun_zoom, self.gun_speed(), self.gun_crouch, firing_err=fe)

    def gun_hold_wall_z(self):
        """ระนาบ z ของกำแพงดริล hold — None เมื่อไม่ได้อยู่ในดริลนั้น"""
        if self.gun_drill == "hold" and self.gun_origin:
            return self.gun_origin[2] + HOLD_WALL_DZ
        return None

    def gun_wall_hit(self, wd):
        """hold: กระสุนทิศ wd (world) ชน "เนื้อกำแพง" ที่ (s, จุด) — None ถ้าลอดช่องกว้าง 2·HOLD_GAP (เต็มความสูง)
        หรือไม่ได้พุ่งไปทางกำแพง (บอทอยู่หลังกำแพงเสมอ → ต้องลอดช่องเท่านั้นจึงโดนได้)"""
        wz = self.gun_hold_wall_z()
        if wz is None or wd[2] <= 1e-6:
            return None
        ox, oy, oz = self.cam.pos
        s = (wz - oz) / wd[2]
        if s <= 0:
            return None
        p = (ox + wd[0] * s, oy + wd[1] * s, wz)
        if abs(p[0]) < HOLD_GAP or not (-ROOM_X <= p[0] <= ROOM_X and 0.0 <= p[1] <= ROOM_H):
            return None
        return s, p

    def gun_impact(self, d):
        """บันทึกจุดที่กระสุน (ทิศ d ใน camera space) ไปโดนกำแพง/พื้น — วาดเป็นรอยให้เห็น pattern
        ผิวที่เป็นไปได้: เนื้อกำแพง hold (ถ้ามี) → กำแพงหลังห้อง (z = WALL_Z) → พื้น เอาอันใกล้สุด
        (เดิมดริล hold ใช้ระนาบกำแพง hold ทั้งแผ่น = นัดที่ลอดช่องทิ้งรอยลอยกลางอากาศตรงช่อง)"""
        wd = self.cam.to_world_dir(d)
        ox, oy, oz = self.cam.pos
        best = self.gun_wall_hit(wd)
        if wd[2] > 1e-6:
            s = (WALL_Z - oz) / wd[2]
            p = (ox + wd[0] * s, oy + wd[1] * s, WALL_Z)
            if s > 0 and -ROOM_X <= p[0] <= ROOM_X and 0.0 <= p[1] <= ROOM_H and (best is None or s < best[0]):
                best = (s, p)
        # พื้น y = 0
        if wd[1] < -1e-6:
            s = -oy / wd[1]
            p = (ox + wd[0] * s, 0.0, oz + wd[2] * s)
            if best is None or s < best[0]:
                best = (s, p)
        if best is not None:
            self.gun_marks.append((best[1], self.gt))
            if len(self.gun_marks) > 40:
                del self.gun_marks[:len(self.gun_marks) - 40]

    # ───────────────────────── ยิง ─────────────────────────
    def gun_fire_interval(self):
        """ช่วงห่างขั้นต่ำระหว่างนัด (วิ) ณ ตอนนี้ — ไรเฟิล ADS ยิงช้าลง (ads_rps)"""
        w = self.gun_w()
        return 1.0 / (w["rps"] * (w.get("ads_rps", 1.0) if self.gun_zoom > 1 else 1.0))

    def gun_shoot(self):
        """1 นัด — เรียกจาก shoot() (คลิก, ที่ gt ของเฟรมก่อน) และจาก update_gun (auto-fire ค้าง, gt ใหม่)
        ยิงได้ไม่เกิน 1 นัดต่อค่า gt — สองทางนี้ในรอบเดียวกันเกิดคนละ gt จึงห่างกันอย่างน้อย dt เสมอ"""
        w = self.gun_w()
        if self.gun_respawn_at is not None:
            return
        if self.gun_reload_until > 0:
            return
        if self.gun_mag <= 0:
            self.gun_reload()          # แม็กหมด = คลิกแล้วรีโหลดเลย (ก่อนเช็ค fire rate เหมือนเกม)
            return
        if self.gt < self.gun_next_shot_at:
            return
        # fire rate แบบ "ตารางเวลา" ไม่ใช่ "นัดก่อน + ช่วง": เฟรมมาถึงช้ากว่ากำหนด late วิ (รอเฟรมถัดไป)
        # ก็หักคืนจากช่วงถัดไป → เฉลี่ยได้ rps ตรงตาราง ไม่ว่า 60/144/240 FPS (เดิม Vandal 60 FPS ยิงได้
        # ~8.6 นัด/วิ แต่ 240 FPS ~9.6 → คะแนน/ความยากเทียบข้ามเครื่องไม่ได้) เพดานการหักดู GUN_FIRE_CARRY_MAX_DT
        interval = self.gun_fire_interval()
        late = self.gt - self.gun_next_shot_at          # ≥ 0 เสมอ (ผ่านเงื่อนไขด้านบนแล้ว)
        # ชดเชยเฉพาะตอน "ปืนเป็นตัวจำกัด" (late ไม่เกินหนึ่งช่วง = ผู้เล่นกดค้าง/แตะถี่กว่าปืนอยู่แล้ว) —
        # นัดแรกหลังพักยาวเริ่มตารางใหม่จากตอนนี้ตรงๆ ไม่มีของแถม
        carry = min(late, self.gun_dt) if (late <= interval and self.gun_dt <= GUN_FIRE_CARRY_MAX_DT) else 0.0
        self.gun_next_shot_at = self.gt + interval - carry
        self.gun_mag -= 1
        self.gun_shots += 1
        self.gun_last_shot_prev = self.gun_last_shot
        self.gun_last_shot = self.gt
        # pattern + สเปรดจากตาราง Riot: crosshair อยู่ที่เดิม กระสุนนัดนี้เบี่ยง (po, yo) องศา + กรวย sp
        ads, zoomed = self.gun_ads_state()
        po, yo, fe = self.gun_stab.shoot(self.gt, crouch=self.gun_crouch, ads=ads, zoomed=zoomed)
        sp = guns.spread_deg(self.gun_weapon, self.gun_zoom, self.gun_speed(), self.gun_crouch, firing_err=fe)
        d = Stability.shot_dir(po, yo, sp)
        hit_any = False
        # hold: กำแพงบังกระสุนจริง ไม่ใช่แค่บังภาพ — บอท "exposed" (ศูนย์กลางอยู่ในช่อง +0.1) ยังมีไหล่/หัวส่วนที่
        # กำแพงบังอยู่ และยืนเยื้องข้าง (GUN_MOVE_X) ทำให้แนวยิงตัดกำแพงก่อนถึงตัวบอทได้ → เช็คแนวยิงกับกำแพงก่อน
        blocked = self.gun_wall_hit(self.cam.to_world_dir(d)) is not None
        # เช็คบอทใกล้สุดก่อน (คนบังกัน)
        for b in () if blocked else sorted((b for b in self.bots if b.alive and b.exposed),
                                            key=lambda b: b.dist(self.cam)):
            zone = b.hit_zone(self.cam, d)
            if not zone:
                continue
            hit_any = True
            dist = b.dist(self.cam)
            dmg = guns.damage_for(self.gun_weapon, zone, dist)
            killed = b.take(dmg, zone)
            self.gun_hits += 1
            self.hits += 1
            if zone == "head":
                self.gun_hs += 1
                self.headshots += 1
            elif zone == "leg":
                self.gun_legs += 1
            self.shot_data.append({"x": self.bot_screen_off(b)[0], "y": self.bot_screen_off(b)[1], "hit": True})
            if killed:
                self.gun_on_kill(b, zone, dist)
            else:
                col = C_PALE_GOLD if zone == "head" else (C_TEXT if zone == "body" else C_DIM)
                self.add_float(f"{zone.upper()} {dmg}", col)
                self.play(self.snd_hit)
            self.hitmarks.append(pygame.time.get_ticks())
            break
        if not hit_any:
            self.misses += 1
            self.gun_impact(d)
            exposed = [b for b in self.bots if b.alive and b.exposed]
            if w["kind"] == "sniper" and not exposed and self.gun_drill == "hold":
                # ยิงตอนไม่มีใครโผล่ = โดนจิ้มหลอกสำเร็จ — เสียลูกเลื่อน 1.67 วิเปล่าๆ
                self.gun_baited += 1
                self.score = max(0, self.score - BAIT_PEN)
                self.add_float(f"BAITED -{BAIT_PEN}", (255, 170, 0))
            elif blocked and exposed:
                self.add_float("กำแพง", C_RED)      # มีบอทโผล่แต่แนวยิงตัดเนื้อกำแพง — พลาดเพราะมุม ไม่ใช่โดนหลอก
            else:
                self.add_float("miss", C_RED)
            near = min(exposed, key=lambda b: b.dist(self.cam)) if exposed else None
            if near:
                o = self.bot_screen_off(near)
                self.shot_data.append({"x": o[0], "y": o[1], "hit": False})
            self.play(self.snd_miss)
        if w.get("unscope_on_shot"):
            self.gun_unscope()
        if self.gun_drill == "repo":
            # คลิกถูกประมวลผลก่อน update_gun ของเฟรมเดียวกัน — ถ้าเพิ่งย้ายครบระยะในเฟรมนี้ ต้องปิดชุดเก่าก่อน
            # ไม่งั้นนัดนี้แอบไม่มีเส้นตาย (ชุดเก่าถูกเคลียร์ทีหลังโดยไม่ตั้ง anchor ใหม่)
            self.gun_repo_check()
            if self.gun_repo_deadline is None and self.gun_respawn_at is None:
                # anchor = จุดยืน "นัดแรก" ของชุด: นัดต่อๆ ไป (ไรเฟิลกดค้าง) ห้ามเลื่อนเส้นตาย ไม่งั้นยืนที่เดิม
                # ยิงยาวไปเรื่อยๆ ก็ไม่โดนลงโทษ — ตรงข้ามกับสิ่งที่ดริลจะสอน (ยิงแล้วต้องย้าย)
                self.gun_shot_pos = (self.cam.pos[0], self.cam.pos[2])
                self.gun_repo_deadline = self.gt + REPO_TIME

    def gun_repo_check(self):
        """repo: ตัดสินชุดที่ค้างอยู่ — ย้ายจาก anchor ครบ REPO_DIST = ผ่าน / เลยเส้นตาย = โดน pre-fire
        (นัดระหว่างทางไม่ต่อเวลาให้) เรียกทุกเฟรมจาก update_gun และก่อนตั้ง anchor ใหม่ใน gun_shoot"""
        if self.gun_repo_deadline is None:
            return
        moved = math.hypot(self.cam.pos[0] - self.gun_shot_pos[0],
                           self.cam.pos[2] - self.gun_shot_pos[1]) if self.gun_shot_pos else REPO_DIST
        if moved >= REPO_DIST:
            self.gun_repo_deadline = None
            self.gun_repo_ok += 1
            self.add_float("ย้ายทัน ✓", C_GREEN)
            # นัดที่ยิงในเฟรมเดียวกับที่ย้ายครบ (คลิกถูกประมวลผลก่อน gun_move ของเฟรมนั้น) ยังไม่มีชุดของตัวเอง —
            # ไม่งั้นนัดสุดท้ายก่อนข้ามเส้นเป็นนัดฟรี ยืนนิ่งต่อได้ไม่โดนลงโทษ → เริ่มชุดใหม่ที่จุดนี้ให้เลย
            if self.gt - self.gun_last_shot <= self.gun_dt + 1e-9:
                self.gun_shot_pos = (self.cam.pos[0], self.cam.pos[2])
                self.gun_repo_deadline = self.gt + REPO_TIME
        elif self.gt >= self.gun_repo_deadline:
            self.gun_repo_deadline = None
            self.gun_prefired += 1
            self.add_float(f"PRE-FIRED! ย้ายที่หลังยิง -{PREFIRE_PEN}", C_RED)
            self.score = max(0, self.score - PREFIRE_PEN)
            self.gun_player_hit(150, True)

    def gun_on_kill(self, b, zone, dist):
        self.gun_kills += 1
        ttk = self.gt - (b.born if b.born is not None else self.gt)
        if b.meta.get("scope_t") is not None and b.born is not None:
            self.gun_scope_times.append((b.meta["scope_t"] - b.born) * 1000)
        self.gun_ttk.append(ttk * 1000)
        bonus = round(KILL_TTK_BONUS * max(0.0, 1.0 - ttk / 1.5))
        pts = KILL_BASE + bonus + (KILL_HS_BONUS if zone == "head" else 0)
        self.score += pts
        tag = "HEADSHOT" if zone == "head" else ("ONE-TAP" if len(b.damage_taken) == 1 else "KILL")
        self.add_float(f"{tag} +{pts}  ({ttk * 1000:.0f}ms · {dist:.0f}m)", C_PALE_GOLD if zone == "head" else C_GREEN)
        self.play(self.snd_head if zone == "head" else self.snd_hit)
        b.alive = False
        self.gun_next_bot_at = self.gt + (0.7 + random.random() * 0.8)

    def bot_screen_off(self, b):
        f = focal_len(self.H) * self.gun_zoom
        x, y, z = self.cam.to_cam((b.x, 1.2, b.z))
        if z < 0.05:
            return (0, 0)
        return (f * x / z, -f * y / z)

    # ───────────────────────── update ─────────────────────────
    def update_gun(self, dt):
        self.gun_dt = dt                # gun_shoot ใช้เป็นเพดานชดเชยเศษเวลาของ fire rate (คลิกใช้ค่าเฟรมก่อนหน้า)
        self.gun_move(dt)
        w = self.gun_w()
        if self.gun_flash > 0:
            self.gun_flash = max(0.0, self.gun_flash - dt)
        # รีโหลดเสร็จ → เติมแม็ก (reload_until > 0 = กำลังรีโหลด)
        if self.gun_reload_until > 0 and self.gt >= self.gun_reload_until:
            self.gun_reload_until = 0.0
            self.gun_mag = w["mag"]
        # auto-fire (ไรเฟิลกดค้าง)
        if self.gun_firing and w["auto"]:
            self.gun_shoot()
        # ฟื้นรีคอยล์/สเปรดตามเวลา (โมเดลใน stability.py — หยุดยิง 0.4 วิ = pattern รีเซ็ต)
        self.gun_stab.update(self.gt, dt)
        if self.gun_marks and self.gt - self.gun_marks[0][1] > 4.0:
            self.gun_marks = [m for m in self.gun_marks if self.gt - m[1] <= 4.0]
        # ตาย → เกิดใหม่
        if self.gun_respawn_at is not None:
            if self.gt >= self.gun_respawn_at:
                self.gun_respawn_at = None
                self.gun_hp, self.gun_shield = guns.PLAYER_HP, guns.PLAYER_SHIELD
                self.gun_next_bot_at = self.gt + 0.6
            return
        # repo: ยิงแล้วต้องขยับ — วัดจาก anchor (จุดยืนนัดแรกของชุด) จนกว่าจะ "ย้ายครบระยะ" (ผ่าน → นัดถัดไป
        # ตั้ง anchor ใหม่ที่จุดใหม่) หรือ "หมดเวลา" (โดนลงโทษ) เท่านั้น
        self.gun_repo_check()
        if self.gun_respawn_at is not None:      # โดน pre-fire ตายในเฟรมนี้ — ไม่ต้องเกิดบอท/ให้บอทยิงต่อ
            return
        # spawn
        if self.gun_next_bot_at is not None and self.gt >= self.gun_next_bot_at and not any(b.alive for b in self.bots):
            self.gun_next_bot_at = None
            self.gun_spawn()
        # บอท
        for b in list(self.bots):
            if not b.alive:
                if b.meta.get("die_t", None) is None:
                    b.meta["die_t"] = self.gt
                elif self.gt - b.meta["die_t"] > 0.6:
                    self.bots.remove(b)
                continue
            self.gun_bot_ai(b, dt)

    def gun_move(self, dt):
        dx = (1 if "d" in self.keys_down else 0) - (1 if "a" in self.keys_down else 0)
        dz = (1 if "s" in self.keys_down else 0) - (1 if "w" in self.keys_down else 0)
        vmax = self.gun_run_speed()
        if dx or dz:
            fwd = (math.sin(self.cam.yaw), math.cos(self.cam.yaw))
            right = (math.cos(self.cam.yaw), -math.sin(self.cam.yaw))
            mag = math.hypot(dx, dz)
            ix = (right[0] * dx + fwd[0] * (-dz)) / mag
            iz = (right[1] * dx + fwd[1] * (-dz)) / mag
            self.vel[0] += ix * STRAFE_ACCEL * dt
            self.vel[1] += iz * STRAFE_ACCEL * dt
            sp = self.gun_speed()
            if sp > vmax:
                self.vel[0] *= vmax / sp
                self.vel[1] *= vmax / sp
            self.gun_still_since = 0.0
        else:
            sp = self.gun_speed()
            if sp > 0:
                dec = STRAFE_FRICTION * dt
                if sp <= dec:
                    self.vel = [0.0, 0.0]
                else:
                    self.vel[0] -= self.vel[0] / sp * dec
                    self.vel[1] -= self.vel[1] / sp * dec
            if self.gun_speed() <= 0.05:
                self.gun_still_since += dt
        ox, oz = self.gun_origin[0], self.gun_origin[2]
        self.cam.pos[0] = max(ox - GUN_MOVE_X, min(ox + GUN_MOVE_X, self.cam.pos[0] + self.vel[0] * dt))
        self.cam.pos[2] = max(oz - GUN_MOVE_ZB, min(oz + GUN_MOVE_ZF, self.cam.pos[2] + self.vel[1] * dt))
        self.cam.pos[1] = EYE_Y - (0.55 if self.gun_crouch else 0.0)

    def gun_spawn(self):
        oz = self.gun_origin[2]
        drill = self.gun_drill
        if drill == "hold":
            side = random.choice((-1, 1))
            kind = random.choices(("peek", "jiggle", "swing"), weights=(0.5, 0.3, 0.2))[0]
            b = Bot(side * (HOLD_GAP + 0.6), oz + HOLD_WALL_DZ + 0.8)
            b.exposed = False
            b.state = "hidden"
            b.meta = {"side": side, "kind": kind, "t0": self.gt + random.uniform(0.4, 1.8)}
            b.born = None
        else:
            if drill == "duel":
                dist = random.uniform(8.0, 30.0)
            elif drill == "quick":
                dist = random.uniform(15.0, 30.0)
            else:
                dist = random.uniform(20.0, 30.0)
            x = random.uniform(-6.0, 6.0)
            z = min(WALL_Z - 0.8, oz + math.sqrt(max(1.0, dist * dist - x * x)))
            b = Bot(x, z)
            b.born = self.gt
            b.next_fire = self.gt + random.uniform(*BOT_RT)
            if drill == "duel" and random.random() < 0.4:
                b.vx = random.choice((-1.0, 1.0)) * random.uniform(1.2, 2.4)
                b.meta["turn_t"] = self.gt + random.uniform(0.4, 1.0)
        self.bots.append(b)

    def gun_bot_ai(self, b, dt):
        drill = self.gun_drill
        if drill == "hold":
            self.gun_hold_ai(b, dt)
        else:
            if b.vx:
                b.x += b.vx * dt
                if abs(b.x) > 6.5 or self.gt >= b.meta.get("turn_t", 1e9):
                    b.vx = -b.vx if abs(b.x) > 6.5 else b.vx * random.choice((-1, 1))
                    b.meta["turn_t"] = self.gt + random.uniform(0.4, 1.0)
                    if abs(b.x) > 6.5:
                        b.x = max(-6.5, min(6.5, b.x))
        if b.exposed and b.next_fire is not None and self.gt >= b.next_fire:
            b.next_fire = self.gt + BOT_FIRE_GAP
            self.gun_bot_fire(b)

    def gun_hold_ai(self, b, dt):
        m = b.meta
        side = m["side"]
        gap = HOLD_GAP
        speed = 5.4
        if b.state == "hidden":
            if self.gt >= m["t0"]:
                b.state = "out"
                b.exposed = False
        elif b.state == "out":
            b.x -= side * speed * dt          # เคลื่อนเข้าหาช่อง
            if not b.exposed and abs(b.x) < gap + 0.1:
                b.exposed = True
                b.born = self.gt
                if m["kind"] == "peek":
                    b.next_fire = self.gt + random.uniform(*BOT_RT)
            kind = m["kind"]
            if kind == "jiggle" and abs(b.x) < gap - 0.05:
                b.state = "back"
            elif kind == "peek" and abs(b.x) < gap - random.uniform(0.35, 0.8):
                b.state = "hold"
                m["hold_until"] = self.gt + random.uniform(0.45, 0.85)
            elif kind == "swing" and (b.x * side) < -(gap + 0.6):
                b.exposed = False
                b.state = "gone"
        elif b.state == "hold":
            if self.gt >= m["hold_until"]:
                b.state = "back"
        elif b.state == "back":
            b.x += side * speed * dt
            if abs(b.x) > gap + 0.1:
                b.exposed = False
                b.state = "gone"
        if b.state == "gone":
            b.alive = False
            b.meta["die_t"] = self.gt
            b.meta["escaped"] = True
            self.gun_next_bot_at = self.gt + random.uniform(0.5, 1.2)
        # ขณะโผล่: เห็นก็ต่อเมื่อลำตัวอยู่ในช่อง
        if b.state in ("out", "hold", "back"):
            b.exposed = abs(b.x) < gap + 0.1

    def gun_bot_fire(self, b):
        p = BOT_HIT_P
        st = guns.move_state(self.gun_speed(), 5.4)
        if st != "stand":
            p *= 0.6
        elif self.gun_still_since > 1.0:
            p += 0.15
        if random.random() < p:
            head = random.random() < BOT_HEAD_P
            self.gun_player_hit(BOT_DMG_HEAD if head else BOT_DMG_BODY, head)
        else:
            self.play(self.snd_miss)

    def gun_player_hit(self, dmg, head):
        self.gun_hp, self.gun_shield = guns.apply_damage(self.gun_hp, self.gun_shield, dmg)
        self.gun_dmg_taken += dmg
        self.gun_flash = 0.25
        if self.gun_hp <= 0:
            self.gun_deaths += 1
            self.score = max(0, self.score - DEATH_PEN)
            self.add_float(f"YOU DIED -{DEATH_PEN}", C_RED)
            self.gun_respawn_at = self.gt + 1.0
            self.gun_unscope()
            self.gun_firing = False
            for b in self.bots:
                b.alive = False
                b.meta["die_t"] = self.gt
            self.gun_repo_deadline = None
        else:
            self.add_float("-%d" % dmg, C_RED)

    # ───────────────────────── วาด ─────────────────────────
    def draw_gun_world(self, f):
        """บอท + กำแพง hold + แถบ HP — วาดบน overlay หลังฉากพื้นหลัง (f รวม zoom แล้ว)"""
        scr = self.screen
        gpu_world = getattr(self, "_world_gpu_frame", False)   # glrender วาด grid/กำแพง hold ให้แล้ว (static บน GPU)
        if not gpu_world:
            # ตารางพื้นส่วนที่ห้องเดิมไม่มี (z -22..2) — ไม่งั้นพื้นใกล้ตัวเรียบจนกะระยะ/ความเร็วเดินไม่ออก
            grid = C_GRID
            for gz in range(GUN_GRID_Z0, 3, 2):
                a, b2 = self.project((-10, 0, gz), f), self.project((10, 0, gz), f)
                if a and b2:
                    self.mark_dirty(pygame.draw.line(scr, grid, (a[0], a[1]), (b2[0], b2[1]), 1))
            z0 = self.cam.pos[2] + 0.6      # เริ่มหน้ากล้องนิดเดียว (จุดหลังกล้อง project ไม่ได้)
            for gx in range(-10, 11, 2):
                a, b2 = self.project((gx, 0, z0), f), self.project((gx, 0, 2), f)
                if a and b2:
                    self.mark_dirty(pygame.draw.line(scr, grid, (a[0], a[1]), (b2[0], b2[1]), 1))
        # รอยกระสุน (จางใน 4 วิ) — ผู้เล่นเห็นว่า pattern พาไปไหนตอนไม่ดึงสวน
        for pt, t0 in self.gun_marks:
            pr = self.project(pt, f)
            if not pr:
                continue
            age = self.gt - t0
            k = max(0.0, 1.0 - age / 4.0)
            col = (int(60 + 150 * k), int(56 + 140 * k), int(50 + 110 * k))
            r = max(2, int(f * 0.05 / pr[2]))
            self.mark_dirty(pygame.draw.circle(scr, col, (int(pr[0]), int(pr[1])), r).inflate(2, 2))
        clip = None
        if self.gun_drill == "hold" and self.gun_origin and gpu_world:
            # กำแพง hold อยู่บน GPU (ใต้ overlay) → บอทที่อยู่หลังกำแพงต้องถูก "บัง" ด้วย clip ของช่องแทน
            wz = self.gun_origin[2] + HOLD_WALL_DZ
            g = HOLD_GAP
            pts = [self.project(p, f) for p in ((-g, 0, wz), (g, 0, wz), (g, ROOM_H, wz), (-g, ROOM_H, wz))]
            if all(pts):
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                clip = pygame.Rect(int(min(xs)), int(min(ys)), int(max(xs) - min(xs)) + 1, int(max(ys) - min(ys)) + 1)
                clip = clip.clip(pygame.Rect(0, 0, self.W, self.H))
                scr.set_clip(clip)
        try:
            for b in sorted(self.bots, key=lambda b: -b.dist(self.cam)):
                if not b.alive and self.gt - b.meta.get("die_t", self.gt) > 0.15:
                    continue
                self.draw_bot(b, f)
        finally:
            if clip is not None:
                scr.set_clip(None)
        if self.gun_drill == "hold" and self.gun_origin and not gpu_world:
            wz = self.gun_origin[2] + HOLD_WALL_DZ
            cwall = (30, 42, 58)
            g = HOLD_GAP
            self.poly([(-ROOM_X, 0, wz), (-g, 0, wz), (-g, ROOM_H, wz), (-ROOM_X, ROOM_H, wz)], cwall, f=f)
            self.poly([(g, 0, wz), (ROOM_X, 0, wz), (ROOM_X, ROOM_H, wz), (g, ROOM_H, wz)], cwall, f=f)
            self.poly([(-g, 0, wz), (g, 0, wz), (g, ROOM_H, wz), (-g, ROOM_H, wz)], (58, 77, 101), 2, f=f)
            # (poly() mark_dirty กรอบของตัวเองแล้ว — เดิม mark_full ทุกเฟรมของดริล hold)
        if self.gun_flash > 0:
            a = int(110 * self.gun_flash / 0.25)
            if self.gpu_post_available():
                self.post_fx_add(tint=(180, 20, 30, a))
            else:
                scr.blit(self.scrim((180, 20, 30, a)), (0, 0))
                self.mark_full()

    def draw_bot(self, b, f):
        scr = self.screen
        alive = b.alive
        def P(y):
            return self.project((b.x, y, b.z), f)
        top, chest, hip, foot = P(guns.HEAD_Y + guns.HEAD_R), P(guns.BODY_Y1), P(guns.BODY_Y0), P(0.0)
        if not (chest and hip and foot):
            return
        z = chest[2]
        body_hw = max(1, int(f * guns.BODY_HW / z))
        leg_hw = max(1, int(f * guns.LEG_HW / z))
        c_body = (88, 34, 44) if alive else (60, 60, 60)
        c_leg = (70, 28, 36) if alive else (50, 50, 50)
        legs = pygame.Rect(int(foot[0]) - leg_hw, int(hip[1]), leg_hw * 2, max(1, int(foot[1] - hip[1])))
        body = pygame.Rect(int(chest[0]) - body_hw, int(chest[1]), body_hw * 2, max(1, int(hip[1] - chest[1])))
        # dirty-rect: ขา+ลำตัวเป็นกรอบเดียว — เดิม mark เฉพาะขา ลำตัว/ขอบขาวไม่เคยถูกอัพโหลด/เคลียร์บน GPU path
        # → บอทใกล้ไม่มีลำตัว (หัวลอยเหนือขา) และบอทที่เดิน (hold peek/jiggle, duel strafe) ทิ้งเศษแดง-ขาวค้างเป็นแถบ
        self.mark_dirty(legs.union(body).inflate(4, 4))
        pygame.draw.rect(scr, c_leg, legs, border_radius=max(1, leg_hw // 2))
        pygame.draw.rect(scr, c_body, body, border_radius=max(1, body_hw // 2))
        pygame.draw.rect(scr, (255, 255, 255), body, 1, border_radius=max(1, body_hw // 2))
        hp = P(guns.HEAD_Y)
        if hp:
            hr = max(2, int(f * guns.HEAD_R / hp[2]))
            self.mark_dirty(pygame.draw.circle(scr, (60, 18, 26), (int(hp[0]), int(hp[1])), hr + 1).inflate(2, 2))
            pygame.draw.circle(scr, (255, 120, 132) if alive else (90, 90, 90), (int(hp[0]), int(hp[1])), hr)
            pygame.draw.circle(scr, (255, 235, 235), (int(hp[0]), int(hp[1])), max(1, hr // 3))
        # แถบ HP/เกราะ เหนือหัว
        if alive and top:
            hf, sf = b.hp_frac()
            bw = max(14, body_hw * 3)
            bx, by = int(top[0]) - bw // 2, int(top[1]) - 8
            pygame.draw.rect(scr, (20, 20, 24), (bx - 1, by - 1, bw + 2, 5))
            pygame.draw.rect(scr, (235, 235, 235), (bx, by, int(bw * hf), 3))
            if sf > 0:
                pygame.draw.rect(scr, (110, 170, 255), (bx, by - 4, int(bw * sf), 2))
            self.mark_dirty(pygame.Rect(bx - 2, by - 6, bw + 4, 12))

    def draw_gun_scope(self):
        """สโคป Op: มืดรอบนอก + วงกลม + เส้นเล็งบาง (วาดทับ crosshair)
        GPU: vignette+ขอบวงเป็น post-effect shader (glrender.post) — overlay วาดแค่เส้นเล็ง/จุด/ตัวเลข (dirty เล็ก)
        software: surface มืดเจาะวง cache ต่อขนาดจอ (เดิม copy 14MB + เจาะวงใหม่ทุกเฟรม)"""
        W, H = self.W, self.H
        cx, cy = W // 2, H // 2
        r = int(H * 0.46)
        scr = self.screen
        if self.gpu_post_available():
            # แถบ HUD บน (hud_h ของเฟรมก่อน) และแถบสถานะล่าง (HP/กระสุน ~130px) ยังเห็นได้นอกวงสโคป
            self.post_fx_add(scope=(cx, cy, r), band=(getattr(self, "hud_h", 100) + 40, H - 135))
        else:
            ov = getattr(self, "_scope_ov", None)
            if ov is None or ov.get_size() != (W, H):
                ov = pygame.Surface((W, H), pygame.SRCALPHA)
                ov.fill((0, 0, 0, 235))
                pygame.draw.circle(ov, (0, 0, 0, 0), (cx, cy), r)
                pygame.draw.circle(ov, (10, 10, 10, 255), (cx, cy), r, 3)
                self._scope_ov = ov
            scr.blit(ov, (0, 0))
            self.mark_full()
        # เส้นเล็ง 4 ท่อนเว้นกลาง (ไม่ตัดกัน) — ถ้าเป็นเส้นยาว 2 เส้นตัดกัน dirty-rect จะ union เป็นกล่อง 1325² px
        # (48% ของจอ) แล้วเกินขีดอัพโหลดเต็มทุกเฟรมที่สโคป
        gap_c = 24
        lc = (20, 20, 20)
        self.mark_dirty(pygame.draw.line(scr, lc, (cx - r, cy), (cx - gap_c, cy), 1))
        self.mark_dirty(pygame.draw.line(scr, lc, (cx + gap_c, cy), (cx + r, cy), 1))
        # ท่อนบนเริ่มใต้แถบ HUD (ไม่งั้น rect เส้นไป union กับแถบ HUD เต็มความกว้าง = กล่องครึ่งจอ)
        top_y = max(cy - r, getattr(self, "hud_h", 100) + 4)
        self.mark_dirty(pygame.draw.line(scr, lc, (cx, top_y), (cx, cy - gap_c), 1))
        self.mark_dirty(pygame.draw.line(scr, lc, (cx, cy + gap_c), (cx, cy + r), 1))
        self.mark_dirty(pygame.draw.circle(scr, (255, 70, 85), (cx, cy), 2).inflate(2, 2))
        self.text(f"{self.gun_zoom:.1f}x", 14, C_DIM, (cx + r - 60, cy + r - 26), bold=True)

    def draw_gun_status(self):
        """HP/เกราะ + กระสุน มุมล่าง (วาดหลัง HUD)"""
        W, H = self.W, self.H
        w = self.gun_w()
        x, y = 24, H - 96
        hf = max(0.0, self.gun_hp / guns.PLAYER_HP)
        sf = max(0.0, self.gun_shield / guns.PLAYER_SHIELD)
        # dirty-rect: กล่องสถานะ + ข้อความ (text() mark เอง) — เดิม mark_full ทุกเฟรม = อัพโหลด overlay เต็ม 14MB/เฟรม
        # ตลอดโหมด GUNFIGHT (สาเหตุหลักที่เฟรมตกที่ 1440p)
        self.mark_dirty(pygame.draw.rect(self.screen, (8, 20, 28), (x - 8, y - 26, 300, 60), border_radius=6))
        self.text(f"{max(0, int(self.gun_hp))}", 22, C_TEXT, (x, y - 24), bold=True)
        self.text(f"+{max(0, int(self.gun_shield))}", 14, (110, 170, 255), (x + 52, y - 18), bold=True)
        pygame.draw.rect(self.screen, (40, 50, 60), (x, y + 6, 200, 8))
        pygame.draw.rect(self.screen, (235, 235, 235), (x, y + 6, int(200 * hf), 8))
        pygame.draw.rect(self.screen, (110, 170, 255), (x, y + 2, int(200 * sf), 3))
        ammo = f"{self.gun_mag} / {w['mag']}"
        col = C_RED if self.gun_mag == 0 else C_TEXT
        if self.gun_reload_until > 0:
            ammo = "RELOADING %.1f" % max(0.0, self.gun_reload_until - self.gt)
            col = C_GOLD
        self.text(ammo, 20, col, (W - 24, H - 100), right=True, bold=True)
        self.text(f"{w['name']} · {GUN_DRILL_NAME[self.gun_drill]}", 12, C_DIM, (W - 24, H - 74), right=True)
        if self.gun_repo_deadline is not None:
            left = max(0.0, self.gun_repo_deadline - self.gt)
            self.text(f"ย้ายที่! {left:.1f}s", 18, C_RED if left < 0.7 else C_GOLD, (W // 2, H - 110), center=True, bold=True)
        if self.gun_respawn_at is not None:
            self.text("DEAD — เกิดใหม่", 26, C_RED, (W // 2, H // 2 - 80), center=True, bold=True)

    def gun_hud(self):
        kd = f"{self.gun_kills}/{self.gun_deaths}"
        acc = f"{round(self.gun_hits / self.gun_shots * 100)}%" if self.gun_shots else "--%"
        hs = f"{round(self.gun_hs / self.gun_hits * 100)}%" if self.gun_hits else "--%"
        left = [(self.score, C_TEXT, "SCORE"), (kd, C_GREEN, "K / D")]
        right = [(acc, C_TEXT, "ACCURACY"), (hs, C_PALE_GOLD, "HS%")]
        return left, right

    # ───────────────────────── ผลลัพธ์ ─────────────────────────
    def gun_result_cards(self):
        ttk = round(sum(self.gun_ttk) / len(self.gun_ttk)) if self.gun_ttk else 0
        acc = round(self.gun_hits / self.gun_shots * 100) if self.gun_shots else 0
        hs = round(self.gun_hs / self.gun_hits * 100) if self.gun_hits else 0
        spk = f"{self.gun_shots / self.gun_kills:.1f}" if self.gun_kills else "--"
        cards = [(f"{self.gun_kills}/{self.gun_deaths}", "K / D"), (f"{ttk}ms", "AVG TTK"),
                 (f"{acc}%", "ACCURACY"), (f"{hs}%", "HEADSHOT")]
        extra = f"กระสุน/คิล {spk}"
        if self.gun_drill == "hold":
            extra += f" · โดนจิ้มหลอก {self.gun_baited} ครั้ง"
        if self.gun_drill == "repo":
            extra += f" · ย้ายทัน {self.gun_repo_ok} · โดน pre-fire {self.gun_prefired} ครั้ง"
        if self.gun_drill == "quick" and self.gun_scope_times:
            extra += f" · โผล่→สโคป {round(sum(self.gun_scope_times) / len(self.gun_scope_times))}ms"
        return cards, extra

    def gun_fill_entry(self, ent):
        ttk = round(sum(self.gun_ttk) / len(self.gun_ttk)) if self.gun_ttk else 0
        ent["variant"] = self.gun_weapon
        ent["drill"] = self.gun_drill
        ent["acc"] = round(self.gun_hits / self.gun_shots * 100) if self.gun_shots else 0
        ent["rt"] = ttk
        ent["kills"] = self.gun_kills
        ent["deaths"] = self.gun_deaths
        ent["hs"] = self.gun_hs
        ent["shots_fired"] = self.gun_shots
        ent["baited"] = self.gun_baited
        ent["prefired"] = self.gun_prefired
        ent["repo_ok"] = self.gun_repo_ok
        return ent


# ───────────────────────── selftest (pure logic — ไม่ต้องมีจอ) ─────────────────────────
class _FakeGame(GunMixin):
    """Game ปลอมเท่าที่ GunMixin ใช้ — เทสกลไกยิง/ดริลตรงๆ โดยไม่ต้องสร้าง Game(headless) เต็มตัว
    (เรียกจาก aim.selftest ผ่าน gunplay.selftest() แบบเดียวกับ plan.selftest())"""
    def __init__(self, weapon="vandal", drill="duel"):
        from .camera import Camera
        self.cam = Camera()
        self.gt = 0.0
        self.vel = [0.0, 0.0]
        self.keys_down = set()
        self.S = {"scoped_sens": 1.0}
        self.score = 0
        self.hits = self.misses = self.headshots = 0
        self.shot_data, self.hitmarks, self.floats, self.targets = [], [], [], []
        self.snd_hit = self.snd_miss = self.snd_head = None
        self.state, self.W, self.H = "play", 1920, 1080
        self.gun_weapon, self.gun_drill = weapon, drill
        self.reset_gun()
        self.begin_gun()
        self.bots = []
        self.gun_next_bot_at = None          # เทสกลไกล้วน — ไม่ให้บอทเกิด/ยิงสวน (เว้นแต่เทสวางบอทเอง)

    def add_float(self, txt, color=None):
        self.floats.append(txt)

    def play(self, snd):
        pass

    def step(self, dt):
        self.gt += dt
        self.update_gun(dt)

    def aim_world(self, x, y, z):
        dx, dy, dz = x - self.cam.pos[0], y - self.cam.pos[1], z - self.cam.pos[2]
        self.cam.yaw = math.atan2(dx, dz)
        self.cam.pitch = math.atan2(dy, math.hypot(dx, dz))


def selftest():
    """คืน list ข้อผิดพลาด (ว่าง = ผ่าน) — 4 เคสจากรีวิว 11 ก.ย. 2026:
    fire rate ไม่ขึ้นกับ FPS · ไม่มียิงตามเก็บหลังเกมค้าง · REPOSITION ยึด anchor นัดแรก · กำแพง hold บังกระสุน"""
    errors = []
    rng_state = random.getstate()
    random.seed(20260911)
    try:
        # ── 1) fire rate: Vandal กดค้าง 2 วิ ต้องได้จำนวนนัดเท่ากันทุก FPS (เดิม 60 FPS ได้ 18, 144/240 ได้ 20) ──
        rps = WEAPONS["vandal"]["rps"]
        counts = {}
        for fps in (60, 144, 240):
            g = _FakeGame("vandal", "duel")
            g.gun_firing = True
            n = int(2.0 * fps)
            for _ in range(n):
                g.step(1.0 / fps)
            counts[fps] = g.gun_shots
        want = int(2.0 * rps) + 1          # นัดแรกที่ t≈0 + ทุก 1/rps
        if len(set(counts.values())) != 1 or counts[60] != want:
            errors.append(f"gun fire rate ขึ้นกับ FPS: {counts} (ต้องได้ {want} เท่ากันทุกค่า)")
        # ช่วงห่างระหว่างนัด (ยกเว้นเฟรมแรก) ต้องไม่สั้นกว่า 1/rps เกินหนึ่งเฟรม — ไม่มี "ยิงเร็วขึ้น" แอบแฝง
        g = _FakeGame("vandal", "duel")
        g.gun_firing = True
        times = []
        for _ in range(120):
            n0 = g.gun_shots
            g.step(1.0 / 60)
            if g.gun_shots > n0:
                times.append(g.gt)
        gaps = [b - a for a, b in zip(times, times[1:])]
        if gaps and (min(gaps) < 1.0 / rps - 1.0 / 60 - 1e-9 or sum(gaps) / len(gaps) > 1.0 / rps + 2e-3):
            errors.append(f"gun fire rate: ช่วงห่างผิด min {min(gaps):.4f} avg {sum(gaps) / len(gaps):.4f} (1/rps={1 / rps:.4f})")
        # ── 2) เกมค้าง (dt 0.1 ตามที่ game.py clamp): ห้ามยิงตามเก็บ — เฟรมถัดจากเฟรมค้างต้องยังไม่ถึงคิว ──
        g = _FakeGame("vandal", "duel")
        g.gun_firing = True
        for _ in range(30):
            g.step(1.0 / 60)
        g.step(0.1)                           # ค้าง 100 ms (นัดหนึ่งยิงในเฟรมนี้ได้ตามปกติ)
        n_after_stall = g.gun_shots
        g.step(1.0 / 60)
        if g.gun_shots != n_after_stall:
            errors.append("gun fire rate: ยิงตามเก็บทันทีหลังเฟรมค้าง (ต้องรอครบ 1/rps จากนัดล่าสุด)")
        g = _FakeGame("vandal", "duel")
        g.gun_firing = True
        total = 0.0
        while total < 3.0:
            dt = 0.1 if (int(total * 60) % 20 == 7) else 1.0 / 60
            g.gun_mag = 25                    # เติมแม็กตลอด — ให้ตารางเวลาเป็นตัวจำกัดเดียว ไม่ใช่ขนาดแม็ก/รีโหลด
            g.step(dt); total += dt
        if not (int(3.0 * rps) - 3 <= g.gun_shots <= int(3.0 * rps) + 1):
            errors.append(f"gun fire rate: {g.gun_shots} นัดใน 3 วิ ทั้งที่มีเฟรมค้างปน (ต้อง ≤ {int(3.0 * rps) + 1} และไม่หายเกิน 3)")
        # ── 3) REPOSITION: ไรเฟิลกดค้างยืนนิ่ง → ต้องโดน pre-fire (เดิมทุกนัดต่อเวลา 1.6 วิ = ไม่โดนตลอดกาล) ──
        g = _FakeGame("vandal", "repo")
        g.gun_firing = True
        for _ in range(int(60 * 2.0)):
            g.step(1.0 / 60)
        if g.gun_prefired != 1 or g.gun_repo_ok != 0:
            errors.append(f"repo: ยืนยิงต่อเนื่อง 2 วิ ต้องโดน PRE-FIRED 1 ครั้ง (ได้ prefired={g.gun_prefired} ok={g.gun_repo_ok})")
        # ยิงนัดแรกแล้วย้าย ≥ REPO_DIST ทันเวลา → ผ่าน, เส้นตายเคลียร์, นัดถัดไปตั้ง anchor ใหม่ที่จุดใหม่
        g = _FakeGame("operator", "repo")
        g.gun_next_shot_at = 0.0
        g.step(1.0 / 60)
        g.gun_shoot()
        t_first = g.gt
        if g.gun_repo_deadline is None or abs(g.gun_repo_deadline - (t_first + REPO_TIME)) > 1e-9:
            errors.append("repo: นัดแรกต้องตั้งเส้นตาย REPO_TIME")
        for _ in range(12):
            g.step(1.0 / 60)
        g.cam.pos[0] += REPO_DIST + 0.1       # ย้ายที่ (ภายในขอบเขต GUN_MOVE_X)
        g.step(1.0 / 60)
        if g.gun_repo_ok != 1 or g.gun_repo_deadline is not None or g.gun_prefired:
            errors.append(f"repo: ย้ายครบระยะแล้วต้องผ่าน (ok={g.gun_repo_ok} deadline={g.gun_repo_deadline})")
        g.gun_next_shot_at = 0.0
        g.gun_shoot()
        if g.gun_shot_pos is None or abs(g.gun_shot_pos[0] - g.cam.pos[0]) > 1e-9:
            errors.append("repo: นัดแรกหลังผ่านต้องตั้ง anchor ใหม่ที่จุดยืนใหม่")
        # Op ยิงต่อเนื่องแบบ semi-auto ยืนนิ่ง: นัดที่ 2 ห้ามต่อเวลาให้ — โดนลงโทษที่ 1.6 วิจากนัดแรก
        g = _FakeGame("vandal", "repo")
        g.step(1.0 / 60); g.gun_shoot()
        t0 = g.gt
        while g.gt < t0 + 1.0:
            g.step(1.0 / 60); g.gun_shoot()
        if g.gun_repo_deadline is None or abs(g.gun_repo_deadline - (t0 + REPO_TIME)) > 1e-9:
            errors.append("repo: นัดถัดไปห้ามเลื่อนเส้นตายของชุด")
        # race เฟรมเดียวกัน: คลิก (ประมวลผลก่อน gun_move) แล้วข้ามเส้น 2 ม. ในเฟรมนั้น — นัดนั้นต้องได้ชุดใหม่
        # ไม่ใช่นัดฟรี: ยืนนิ่งต่อจากนั้นต้องโดน pre-fire
        g = _FakeGame("operator", "repo")
        g.step(1.0 / 60); g.gun_shoot()               # anchor ที่ x=0
        for _ in range(6):
            g.step(1.0 / 60)
        g.gun_next_shot_at = 0.0
        g.gun_shoot()                                 # คลิกที่ gt ของเฟรมก่อน (ยังห่าง anchor < 2 ม.)
        g.cam.pos[0] += REPO_DIST + 0.1               # gun_move ของเฟรมนี้พาข้ามเส้น
        g.step(1.0 / 60)
        if g.gun_repo_ok != 1 or g.gun_repo_deadline is None:
            errors.append(f"repo: นัดที่ยิงเฟรมเดียวกับที่ย้ายครบต้องเริ่มชุดใหม่ (ok={g.gun_repo_ok} dl={g.gun_repo_deadline})")
        for _ in range(int(60 * 2.0)):
            g.step(1.0 / 60)
        if g.gun_prefired != 1:
            errors.append(f"repo: ยืนนิ่งหลังนัดที่ข้ามเส้นต้องโดน pre-fire (prefired={g.gun_prefired})")
        # ── 4) HOLD: กำแพงบังกระสุนตามแนวยิง ไม่ใช่แค่บังภาพ ──
        g = _FakeGame("operator", "hold")
        oz = g.gun_origin[2]
        wz = oz + HOLD_WALL_DZ
        b = Bot(HOLD_GAP + 0.05, wz + 0.8)   # ศูนย์กลางอยู่ในเกณฑ์ exposed (< gap+0.1) แต่ครึ่งตัวอยู่หลังกำแพง
        b.exposed, b.state, b.born = True, "hold", g.gt
        b.meta = {"side": 1, "kind": "peek", "t0": 0.0, "hold_until": 1e9}
        g.bots = [b]

        def op_shot(px, aim_x, aim_y):
            g.cam.pos[0] = px
            g.gun_stab.reset()
            g.gun_next_shot_at = 0.0
            g.gt += 1.0
            g.gun_unscope(); g.gun_rmb(True)          # สโคป 2.5x → นิ่ง = สเปรด 0 ยิงตรงกลางเป๊ะ
            g.aim_world(aim_x, aim_y, b.z)
            hits0, miss0 = g.gun_hits, g.misses
            g.gun_shoot()
            return g.gun_hits - hits0, g.misses - miss0

        # ยืนเยื้องฝั่งเดียวกับบอท (x=+2.5) เล็งลำตัว → แนวยิงตัดเนื้อกำแพงที่ x≈1.29 > HOLD_GAP = โดนกำแพง
        hit, miss = op_shot(2.5, b.x, 1.2)
        if hit or not miss:
            errors.append(f"hold: ยิงผ่านเนื้อกำแพงยังโดนบอท (hit={hit} miss={miss})")
        elif not g.gun_marks or abs(g.gun_marks[-1][0][2] - wz) > 1e-6 or abs(g.gun_marks[-1][0][0]) < HOLD_GAP:
            errors.append(f"hold: รอยกระสุนต้องอยู่บนเนื้อกำแพง hold ({g.gun_marks[-1][0] if g.gun_marks else None})")
        if b.hp != guns.PLAYER_HP or g.floats[-1] != "กำแพง":
            errors.append("hold: โดนกำแพง = ห้ามหักเลือดบอท และต้องบอกว่าติดกำแพง")
        # ยืนอีกฝั่ง (x=-2.5) แนวยิงลอดช่อง (ตัดระนาบที่ x≈1.14) → โดนตามปกติ
        hit, miss = op_shot(-2.5, b.x, 1.2)
        if not hit:
            errors.append("hold: แนวยิงลอดช่องต้องโดนบอท")
        # ยิงลอดช่องไปที่ว่าง → ไม่ใช่รอยบนกำแพง hold (ต้องไปตกกำแพงหลัง/พื้น) และ Op = BAITED ต่อเมื่อไม่มีใครโผล่
        b2 = Bot(-0.3, wz + 0.8); b2.exposed, b2.state, b2.born = True, "hold", g.gt
        b2.meta = {"side": -1, "kind": "peek", "t0": 0.0, "hold_until": 1e9}
        g.bots = [b2]
        hit, miss = op_shot(0.0, 0.8, 1.2)
        if hit or not miss:
            errors.append("hold: ยิงลอดช่องไปที่ว่างต้องพลาด")
        elif abs(g.gun_marks[-1][0][2] - wz) < 1e-6:
            errors.append("hold: นัดที่ลอดช่องต้องไม่ทิ้งรอยลอยกลางช่อง")
        if g.gun_baited:
            errors.append("hold: มีบอทโผล่อยู่ ยิงพลาดต้องไม่นับเป็น BAITED")
    except Exception as ex:
        errors.append(f"gunplay selftest: {type(ex).__name__}: {ex}")
    finally:
        random.setstate(rng_state)
    return errors
