# -*- coding: utf-8 -*-
"""โหมด GUNFIGHT (mode id "gun") — ยิงบอทหุ่นคนด้วยปืนจริง (Op/Vandal/Phantom/Sheriff/Ghost/Classic) — GunMixin

ปืนสั้น: Sheriff เล่นได้ทุกดริล, Ghost/Classic เฉพาะ duel/quick/repo (WEAPON_DRILLS) — Classic มีคลิกขวา =
ยิงชุด 3 เม็ด (gun_alt_shoot)
ดริล (gun_drill):
  duel   : ดวลทีละตัว บอทแอบหลังมุมกำแพงที่ระยะตามการกระจายระยะคิลจริงของปืนนั้น แล้วโผล่ (เฝ้ามุม/วิ่งออกกว้าง/
           โผล่หยุดยิง/จิ้มหลอก/หมอบโผล่/ส่าย ADAD) ยิงสวนตามระดับฝีมือ — มีบันไดแรงค์: ชนะ = บอทตัวต่อไปเก่งขึ้น
           1 ขั้น แพ้ = ลง 1 ขั้น → ลู่เข้า "แรงค์ดวล" (ระดับที่เราชนะครึ่งหนึ่ง ; Op ไม่จัดแรงค์) ดู gunbots/duel
  hold   : Op จับมุมช่องกำแพง 27 ม. บอทโผล่จริง / จิ้มหลอก (jiggle) / วิ่งข้าม — ยิงหลอก = เสียลูกเลื่อน 1.67 วิ
           กำแพงบังกระสุนจริง (gun_wall_hit) ไม่ใช่แค่บังภาพ — ยิงโดนได้เฉพาะแนวยิงที่ลอดช่อง (กระสุนบอทก็เช่นกัน)
  quick  : เริ่มไม่สโคปทุกครั้ง บอทโผล่จากมุม 15–30 ม. → สโคปแล้วยิง (hipfire Op 5° = แทบไม่มีทางโดน)
  repo   : ยิงแล้วต้องย้ายที่ ≥2 ม. ภายใน 1.6 วิ (นับจาก "นัดแรก" ของชุด — ยิงต่อเนื่องไม่ต่อเวลา)
           ไม่งั้นโดน pre-fire ตาย — วินัยหลังยิงของคน Op
  angle / peek / tap / adad : ดริลชุดสมจริง (ANGLE HOLD / PEEK & STOP / TAP @ RANGE / STRAFING HEADS) — ดู gundrills.py
บอทยิงสวนแบบมีเหตุผล (แนวสายตา/ที่กำบัง/ระยะ/peeker's advantage) + HP เรารีเซ็ตทุกดวล — ดู gunbots.py
fire rate ไม่ขึ้นกับ FPS: gun_shoot ใช้ตารางเวลานัดถัดไป (gun_next_shot_at) ไม่ใช่ "นัดก่อน + ช่วง"

กติกาปืนอยู่ใน guns.py (ตัวเลขจากเกมจริง) — ไฟล์นี้คือ gameplay/HUD/ผลลัพธ์ ; AI บอทอยู่ gunbots.py
แรงค์: DUEL / ANGLE / PEEK (ปืนที่ไม่ใช่ Op — duel.LADDER_DRILLS) = แรงค์ดวลจากบันได (history tier_i) ;
ดริลอื่นวัดฟอร์มด้วย K/D, TTK, HS%, ACC + ตัวชี้วัดเฉพาะดริล (gundrills.gun_drill_fields)"""
import math
import random

import pygame

from .config import C_RED, C_GREEN, C_TEXT, C_DIM, C_PALE_GOLD, C_GOLD, C_GRID, EYE_Y, ROOM_H, ROOM_X, WALL_Z
from .camera import focal_len
from .ranks import hexrgb
from . import arena, duel, guns
from .guns import WEAPONS, WEAPON_DRILLS, Bot
from .gunbots import BotAIMixin, BOT_CROUCH_P, BOT_CROUCH_HOLD  # noqa: F401 (ค่าเดิมของโมดูลนี้ — ที่อื่นอ้างชื่อนี้)
from .gundrills import DrillMixin
from .movement import MoveMixin
from .stability import Stability

GUN_DRILLS = [("duel", "DUEL", "ดวล 1v1 จากมุม มีแรงค์"), ("hold", "OP HOLD", "จับมุม แยกจิ้มหลอก"),
              ("quick", "QUICKSCOPE", "สโคปแล้วยิงให้ทัน"), ("repo", "REPOSITION", "ยิงแล้วต้องย้ายที่"),
              ("angle", "ANGLE HOLD", "เฝ้ามุมประตู/กล่อง วาง crosshair ระดับหัว มีแรงค์"),
              ("peek", "PEEK & STOP", "โผล่จากกำแพง หยุดนิ่งแล้วยิง มีแรงค์"),
              ("tap", "TAP @ RANGE", "แตะหัวไกล 20–35 ม. ไม่รัว"),
              ("adad", "STRAFING HEADS", "บอทส่าย ADAD ยิงตอนมันหยุด")]
# ป้ายปุ่มสั้นในเมนู/Insight (ปุ่มกว้าง 52 px) — ลำดับตาม GUN_DRILLS
GUN_DRILL_SHORT = {"duel": "DUEL", "hold": "OP HOLD", "quick": "QUICK", "repo": "REPO",
                   "angle": "ANGLE", "peek": "PEEK", "tap": "TAP", "adad": "ADAD"}
# บรรทัดกติกาของดริลในแผงเมนู (draw_rank_panel) — บอกว่าวัดอะไร
GUN_DRILL_RULE = {"angle": "ANGLE: ฉากใหม่ทุกดวล 2–4 ขอบ · วัดองศาคลาดตอนหัวบอทโผล่",
                  "peek": "PEEK: บอทเริ่มนับเมื่อหัวเราพ้นขอบ · วัดหยุดถึงยิง (ดีสุด 0–50ms)",
                  "tap": "TAP: บอทไม่ยิงสวน โผล่ 2–3 วิ · วัดยิงก่อนสเปรดหาย/หัวต่อระยะ",
                  "adad": "ADAD: บอทยิงเฉพาะตอนหยุดนิ่ง · วัดโดนตอนเดิน vs หยุด"}
# คำใบ้บนจอช่วง 3 วิแรกของรอบ (ดริลใหม่ — ผู้เล่นยังไม่รู้ว่าต้องทำอะไร)
GUN_DRILL_HINT = {"angle": "เฝ้าขอบที่บอทจะโผล่ วาง crosshair ระดับหัว (บางฉากบอทยืนบนยกพื้น)",
                  "peek": "กด A/D โผล่จากกำแพง · หยุดนิ่งก่อนคลิก (counter-strafe)",
                  "tap": "หัวไกล 20–35 ม. — แตะทีละนัด/ชุดสั้น รอสเปรดหาย",
                  "adad": "บอทส่ายซ้ายขวา — ยิงตอนมันหยุดนิ่ง ก่อนมันยิงเรา"}
GUN_DRILL_NAME = {d[0]: d[1] for d in GUN_DRILLS}
GUN_ORIGIN_Z = -18.0        # ยืนถอยหลังห้อง → ระยะถึงกำแพงหลัง 32 ม. (ระยะ Op จริง)
GUN_GRID_Z0 = -22           # ตารางพื้นส่วนขยายเริ่มที่ z นี้ (ห้องเดิมมีถึง z=2) — glrender ใช้ค่าเดียวกัน
GUN_MOVE_X, GUN_MOVE_ZB, GUN_MOVE_ZF = 3.0, 1.0, 3.5   # ขอบเขตเดินรอบจุดเริ่ม (ซ้าย/ขวา, ถอย, เดินหน้า)
PLAYER_R = 0.4              # รัศมีตัวผู้เล่นเทียบที่กำบัง (เดินทะลุกำแพงดวลระยะประชิดไม่ได้)
HOLD_WALL_DZ, HOLD_GAP = 27.0, 1.2      # กำแพงห่างจากจุดเริ่ม + ครึ่งความกว้างช่อง
REPO_DIST, REPO_TIME = 2.0, 1.6
KILL_BASE, KILL_TTK_BONUS, KILL_HS_BONUS, DEATH_PEN, BAIT_PEN, PREFIRE_PEN = 100, 100, 40, 100, 30, 60
# fire rate ไม่ขึ้นกับ FPS: นัดที่ยิงได้ "ช้ากว่ากำหนด" เพราะรอเฟรม (late) จะถูกหักคืนในช่วงถัดไป — แต่หักได้
# ไม่เกินความยาวเฟรมที่ทำให้ช้า และเฟรมที่ยาวกว่านี้ (เกมค้าง/สลับหน้าต่าง, dt ถูก clamp 0.1 ใน game.py)
# ไม่ชดเชยเลย → ไม่มี "ยิงตามเก็บ" หลายนัดรวดหลังค้าง (บั๊กแบบเดียวกับ spray reload-burst ที่เคยเจอ)
GUN_FIRE_CARRY_MAX_DT = 0.05
# Classic คลิกขวา: ชุดถัดไปภายใน ALT_HOLD × (1/2.22 วิ) นับว่า "กดติดกัน" (สเปรดโตต่อ) — ตัวคูณเดียวกับ Stability._hold
ALT_HOLD = 1.2
# ดริลที่ปืนแต่ละกระบอกเล่นได้ = guns.WEAPON_DRILLS (ย้ายไป guns.py ให้ server import ได้โดยไม่ต้องมี pygame —
# เหตุผลที่ Ghost/Classic ไม่มี OP HOLD อยู่ที่นั่น)


# duel: ระยะสุ่มตามการกระจายจริงของระยะคิลด้วยปืนนั้น (p10/p25/p50/p75/p90 ม.) — 438 แมตช์ไม่ซ้ำใน snapshot
# 2026-09-23 (ระยะ = ตำแหน่งคนยิง→จุดตายของเหยื่อ ; phase-1 trainer-realism §4 + wave-1 lane-c3): Ghost n 2,986 ·
# Classic 2,057 (กลาง 11.9 ม., 31% ใกล้กว่า 8 ม.) · Vandal 23,997 · ไรเฟิลรวม 33,717 (Phantom ใช้แถวนี้ — วัดแยกได้แค่
# ค่ากลาง 15.8) · Sheriff 2,226 — gun rev 5 เปลี่ยนไรเฟิล/Sheriff จาก 8–30 ม. เท่ากันมาใช้ข้อมูลจริงด้วย (ประวัติรุ่นเก่า
# เป็น legacy อยู่แล้ว) ; Op ไม่มีแถว = 8–30 ม. (ระยะคิล Op จริงกลาง 25.7 p90 42 ม. เกินห้อง 32 ม.)
DUEL_DIST_Q = {"ghost": (6.4, 10.3, 15.6, 21.8, 27.8), "classic": (4.1, 6.8, 11.9, 18.3, 25.1),
               "vandal": (6.9, 11.2, 17.3, 24.4, 31.7), "phantom": (6.7, 10.9, 16.8, 23.9, 31.0),
               "sheriff": (6.9, 11.1, 16.7, 23.5, 30.4)}
_Q_AT = (0.10, 0.25, 0.50, 0.75, 0.90)


def duel_dist(weapon):
    """ระยะบอท duel (ม.): ปืนใน DUEL_DIST_Q = สุ่ม quantile u∈[0.1, 0.9] แล้วลากเส้นตรงระหว่างจุดที่วัด
    (ตัดหาง 10% สองข้าง — ระยะ 1–3 ม. / 40 ม.+ ไม่ใช่ดวลเล็ง) ; ปืนอื่น (Op) = 8–30 ม. เท่ากันทุกระยะ"""
    qs = DUEL_DIST_Q.get(weapon)
    if not qs:
        return random.uniform(8.0, 30.0)
    u = random.uniform(_Q_AT[0], _Q_AT[-1])
    for (u0, d0), (u1, d1) in zip(zip(_Q_AT, qs), zip(_Q_AT[1:], qs[1:])):
        if u <= u1:
            return d0 + (d1 - d0) * (u - u0) / (u1 - u0)
    return qs[-1]


def drills_for(weapon):
    """id ดริลที่ปืนนี้เล่นได้ ตามลำดับ GUN_DRILLS (เมนู/ปุ่ม B/เริ่มรอบใช้ตัวนี้ตัวเดียว)"""
    allowed = WEAPON_DRILLS.get(weapon)
    return [d[0] for d in GUN_DRILLS if allowed is None or d[0] in allowed]


class GunMixin(MoveMixin, BotAIMixin, DrillMixin):
    # ───────────────────────── สถานะ ─────────────────────────
    def gun_fix_drill(self):
        """ดริลที่เลือกไว้ใช้กับปืนนี้ไม่ได้ (Ghost/Classic ไม่มี OP HOLD) → ย้ายไปดริลแรกที่ใช้ได้ (DUEL)
        เรียกทุกครั้งที่เปลี่ยนปืน (เมนู/V) และตอนเริ่มรอบ (แผน/deep-link ส่งคู่ที่ใช้ไม่ได้มาก็ไม่พัง)"""
        ok = drills_for(self.gun_weapon)
        if self.gun_drill not in ok:
            self.gun_drill = ok[0]

    def reset_gun(self):
        self.gun_weapon = getattr(self, "gun_weapon", "vandal")
        self.gun_drill = getattr(self, "gun_drill", "duel")
        if self.gun_weapon not in WEAPONS:
            self.gun_weapon = "vandal"
        self.gun_fix_drill()
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
        self.gun_flash = 0.0            # โดนยิง: จอวาบแดง
        self.gun_dmg_taken = 0
        self.gun_alt_e = 0.0            # Classic คลิกขวา: ระดับการโตของสเปรด (จำนวนชุดสะสม) ณ ชุดล่าสุด
        self.gun_alt_last = -9.0        # เวลายิงชุดล่าสุด (gt)
        self.gun_alt_bursts = 0         # ยิงคลิกขวากี่ชุดในรอบนี้
        self.gun_bots_reset()           # ที่กำบัง/ดวล/บันได (gunbots)
        self.gun_drills_reset()         # ตัวชี้วัดของดริล angle/peek/tap/adad (gundrills)

    def begin_gun(self):
        self.cam.pos = [0.0, EYE_Y, GUN_ORIGIN_Z]
        self.gun_origin = list(self.cam.pos)
        self.vel = [0.0, 0.0]
        self.gun_next_bot_at = self.gt + 0.9
        self.targets = []
        self.gun_drill_begin()          # TAP ยืนถอยหลังเพิ่ม (ระยะถึง 35 ม.)
        self.gun_bots_begin()           # บันไดแรงค์ (duel/angle/peek) / ระดับบอทคงที่ + กำแพง OP HOLD เป็นกล่อง

    def gun_w(self):
        return WEAPONS[self.gun_weapon]

    def gun_speed(self):
        return math.hypot(self.vel[0], self.vel[1])

    def gun_run_speed(self):
        """ความเร็ววิ่งของปืนในมือตอนนี้ (รวม ADS/สโคป) — หมอบ/Shift เดินคูณต่อใน movement.speed_cap"""
        w = self.gun_w()
        sp = w["run_speed"]
        if self.gun_zoom > 1.0:
            sp *= w.get("scoped_move", w.get("ads_move", 1.0))
        return sp

    def gun_sens_mult(self):
        return guns.zoom_sens_mult(self.gun_zoom, self.S.get("scoped_sens", 1.0))

    # ───────────────────────── input ─────────────────────────
    def gun_rmb(self, down):
        """RMB: ปืนไรเฟิล = กดค้าง ADS | Op = กดวน 2.5x → 5x → ออก | Classic = ยิงชุด 3 เม็ด (กดทีละชุด)"""
        if self.state != "play":
            return
        w = self.gun_w()
        if w.get("alt"):
            if down:
                self.gun_alt_shoot()
            return
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
        """กระสุนทิศ wd (world) ชน "ที่กำบัง" (gun_covers: มุมกำแพงดวล / กำแพง OP HOLD สองแผ่น) ที่ (s, จุด) ของ
        กล่องแรก — None ถ้าไม่ชน (hold: ลอดช่องกว้าง 2·HOLD_GAP เต็มความสูง → บอทหลังกำแพงโดนได้เฉพาะแนวที่ลอดช่อง)"""
        if not self.gun_covers:
            return None
        o = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        s, _ = arena.first_hit(o, wd, self.gun_covers)
        if s is None or s <= 0.0:
            return None
        return s, (o[0] + wd[0] * s, o[1] + wd[1] * s, o[2] + wd[2] * s)

    def _gun_bot_t(self, b, wd):
        """ระยะตามรังสี (ทิศ wd จากตาเรา) ถึงแกนตัวบอท — เทียบกับที่กำบัง: กล่องที่ชนก่อนแกนตัว = บังนัดนั้น"""
        dx, dz = b.x - self.cam.pos[0], b.z - self.cam.pos[2]
        h2 = wd[0] * wd[0] + wd[2] * wd[2]
        return (dx * wd[0] + dz * wd[2]) / h2 if h2 > 1e-12 else 0.0

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

    def gun_fire_gate(self, interval):
        """ยิงได้ตอนนี้ไหม (ไม่ตาย/ไม่รีโหลด/มีกระสุน/ถึงคิว) — ได้ = จองคิวนัดถัดไปที่ gt + interval แล้วคืน True
        ใช้ร่วมคลิกซ้าย (gun_shoot) และคลิกขวา Classic (gun_alt_shoot) → สองโหมดแชร์ตารางเวลาเดียวกัน"""
        if self.gun_respawn_at is not None:
            return False
        if self.gun_reload_until > 0:
            return False
        if self.gun_mag <= 0:
            self.gun_reload()          # แม็กหมด = คลิกแล้วรีโหลดเลย (ก่อนเช็ค fire rate เหมือนเกม)
            return False
        if self.gt < self.gun_next_shot_at:
            return False
        # fire rate แบบ "ตารางเวลา" ไม่ใช่ "นัดก่อน + ช่วง": เฟรมมาถึงช้ากว่ากำหนด late วิ (รอเฟรมถัดไป)
        # ก็หักคืนจากช่วงถัดไป → เฉลี่ยได้ rps ตรงตาราง ไม่ว่า 60/144/240 FPS (เดิม Vandal 60 FPS ยิงได้
        # ~8.6 นัด/วิ แต่ 240 FPS ~9.6 → คะแนน/ความยากเทียบข้ามเครื่องไม่ได้) เพดานการหักดู GUN_FIRE_CARRY_MAX_DT
        late = self.gt - self.gun_next_shot_at          # ≥ 0 เสมอ (ผ่านเงื่อนไขด้านบนแล้ว)
        # ชดเชยเฉพาะตอน "ปืนเป็นตัวจำกัด" (late ไม่เกินหนึ่งช่วง = ผู้เล่นกดค้าง/แตะถี่กว่าปืนอยู่แล้ว) —
        # นัดแรกหลังพักยาวเริ่มตารางใหม่จากตอนนี้ตรงๆ ไม่มีของแถม
        carry = min(late, self.gun_dt) if (late <= interval and self.gun_dt <= GUN_FIRE_CARRY_MAX_DT) else 0.0
        self.gun_next_shot_at = self.gt + interval - carry
        return True

    def gun_shoot(self):
        """1 นัด — เรียกจาก shoot() (คลิก, ที่ gt ของเฟรมก่อน) และจาก update_gun (auto-fire ค้าง, gt ใหม่)
        ยิงได้ไม่เกิน 1 นัดต่อค่า gt — สองทางนี้ในรอบเดียวกันเกิดคนละ gt จึงห่างกันอย่างน้อย dt เสมอ"""
        if not self.gun_fire_gate(self.gun_fire_interval()):
            return
        self.gun_mag -= 1
        self.gun_shots += 1
        self.gun_last_shot_prev = self.gun_last_shot
        self.gun_last_shot = self.gt
        # pattern + สเปรดจากตาราง Riot: crosshair อยู่ที่เดิม กระสุนนัดนี้เบี่ยง (po, yo) องศา + กรวย sp
        ads, zoomed = self.gun_ads_state()
        po, yo, fe = self.gun_stab.shoot(self.gt, crouch=self.gun_crouch, ads=ads, zoomed=zoomed)
        sp = guns.spread_deg(self.gun_weapon, self.gun_zoom, self.gun_speed(), self.gun_crouch, firing_err=fe)
        first = self.gun_first_shot()
        self.gun_last_zone = self.gun_bullet(Stability.shot_dir(po, yo, sp))
        if first is not None:
            first["shot_zone"] = self.gun_last_zone
        self.gun_after_shot()
        # สเปรดนัดแรกของท่า/ADS ตอนนี้ — TAP นับนัดที่ยิงทั้งที่สเปรดจากการยิงยังไม่กลับเป็นนัดแรก (fe > fe0)
        blk = self.gun_stab.block(zoomed)
        fe0 = Stability._error(blk, 0.0, self.gun_crouch, ads and not zoomed) if blk else None
        self.gun_drill_on_shot(fe, fe0)

    def gun_bullet(self, d, quiet=False, burst_dead=()):
        """กระสุน/เม็ด 1 ลูก ทิศ d (camera space): ชนกำแพง hold → บอทใกล้สุดที่โผล่ → รอยบนผิว ; คืน zone ที่โดนหรือ None
        quiet: เม็ดของชุดคลิกขวา — ไม่ขึ้น "miss"/เสียงพลาดรายเม็ด (gun_alt_shoot สรุปทีเดียวต่อชุด)
        burst_dead: บอทที่เพิ่งตายจากเม็ดก่อนหน้าในชุดเดียวกัน (3 เม็ดออกพร้อมกัน) — เม็ดที่ทับตัวมันนับ "โดน"
        (ACC/HS%) แต่ไม่มีดาเมจ ไม่งั้นชุดที่ฆ่าด้วยเม็ดแรกจะโดนนับพลาดฟรี 2 เม็ด"""
        w = self.gun_w()
        # ที่กำบังบังกระสุนจริง ไม่ใช่แค่บังภาพ — บอทที่โผล่มาแค่ไหล่ยังมีตัวส่วนที่กำแพงบังอยู่ และเรายืนเยื้องข้าง
        # (GUN_MOVE_X) ทำให้แนวยิงตัดกำแพงก่อนถึงตัวบอทได้ → เทียบระยะตามแนวยิง: กล่องที่ชนก่อนแกนตัวบอท = บังนัดนั้น
        wd = self.cam.to_world_dir(d)
        cov = self.gun_wall_hit(wd)
        blocked = cov is not None
        # เช็คบอทใกล้สุดก่อน (คนบังกัน) — ทุกตัวที่ยังไม่ตาย (โผล่หรือไม่ ที่กำบังเป็นตัวตัดสิน)
        for b in sorted((b for b in self.bots if b.alive or b in burst_dead), key=lambda b: b.dist(self.cam)):
            zone = b.hit_zone(self.cam, d)
            if not zone:
                continue
            if cov is not None and cov[0] < self._gun_bot_t(b, wd) - 0.25:
                continue                     # กำแพงอยู่หน้าบอทตามแนวยิงนี้
            self.gun_hits += 1
            self.hits += 1
            if zone == "head":
                self.gun_hs += 1
                self.headshots += 1
            elif zone == "leg":
                self.gun_legs += 1
            o = self.bot_screen_off(b)
            self.shot_data.append({"x": o[0], "y": o[1], "hit": True, "ref": "head"})
            if not b.alive:
                return zone
            dist = b.dist(self.cam)
            dmg = guns.damage_for(self.gun_weapon, zone, dist)
            killed = b.take(dmg, zone)
            if killed:
                self.gun_on_kill(b, zone, dist)
            else:
                col = C_PALE_GOLD if zone == "head" else (C_TEXT if zone == "body" else C_DIM)
                self.add_float(f"{zone.upper()} {guns.dmg_label(dmg)}", col)
                self.play(self.snd_hit)
            self.hitmarks.append(pygame.time.get_ticks())
            return zone
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
        elif not quiet:
            self.add_float("miss", C_RED)
        near = min(exposed, key=lambda b: b.dist(self.cam)) if exposed else None
        if near:
            o = self.bot_screen_off(near)
            self.shot_data.append({"x": o[0], "y": o[1], "hit": False, "ref": "head"})
        if not quiet:
            self.play(self.snd_miss)
        return None

    # ── Classic คลิกขวา: 3 เม็ดพร้อมกันในกรวยเดียว ──
    def gun_alt_level(self):
        """ระดับการโตของสเปรดคลิกขวา (จำนวนชุดสะสม) ณ ตอนนี้ — คงที่ภายใน ALT_HOLD ช่วงยิง (กดรัวเร็วสุดที่ FPS ไหน
        ก็ยังนับว่า "ติดกัน") แล้วลดเป็นเส้นตรงถึง 0 ใน esc_reset วิ (รูปเดียวกับการฟื้นของ Stability — ค่าประมาณ ดู guns.py)"""
        a = self.gun_w()["alt"]
        gap = self.gt - self.gun_alt_last
        hold = ALT_HOLD / a["rps"]
        if gap <= hold:
            return self.gun_alt_e
        return self.gun_alt_e * max(0.0, 1.0 - (gap - hold) / a["esc_reset"])

    def gun_alt_spread(self):
        """กรวยสเปรด (องศา) ของชุดคลิกขวาถัดไป: 1.9° (หมอบ 1.71) ไต่ถึง max 5.78° (5.21) ตามชุดที่กดติดกัน
        + โทษเคลื่อนที่ของ alt (เดิน +0.6 วิ่ง +1.5 หมอบเดิน +0 — wiki)"""
        a = self.gun_w()["alt"]
        sp = a["spread"]
        lo, hi = (sp["crouch"], sp["max_crouch"]) if self.gun_crouch else (sp["stand"], sp["max"])
        base = lo + (hi - lo) * min(1.0, self.gun_alt_level() / a["esc_bursts"])
        return base + guns.move_error_deg(self.gun_weapon, self.gun_speed(), self.gun_crouch, alt=True)

    def gun_alt_shoot(self):
        """ยิงชุดคลิกขวา: เม็ด = min(3, กระสุนที่เหลือ) แต่ละเม็ดสุ่มในกรวยเดียวกันรอบ crosshair (ไม่มี pattern รีคอยล์)
        ดาเมจต่อเม็ดเท่าตารางคลิกซ้าย · คิวถัดไป (ทั้งซ้ายและขวา) = 1/2.22 วิ · กล้องเด้งเท่านัดปกติ"""
        a = self.gun_w().get("alt")
        if not a or getattr(self, "resume_cd", 0) > 0:
            return
        if not self.gun_fire_gate(1.0 / a["rps"]):
            return
        n = min(a["pellets"], self.gun_mag)
        cone = self.gun_alt_spread()
        self.gun_alt_e = min(float(a["esc_bursts"]), self.gun_alt_level() + 1.0)
        self.gun_alt_last = self.gt
        self.gun_alt_bursts += 1
        self.gun_mag -= n
        self.gun_shots += n
        self.gun_last_shot_prev = self.gun_last_shot
        self.gun_last_shot = self.gt
        self.gun_stab.pop(self.gt)
        alive0 = [b for b in self.bots if b.alive and b.exposed]
        first = self.gun_first_shot()
        hit_n = 0
        best = None                           # โซนดีสุดของชุด (หัว > ตัว > ขา) — "นัดแรกเข้าหัว" ของดริล PEEK
        for _ in range(n):
            dead = [b for b in alive0 if not b.alive]
            zone = self.gun_bullet(Stability.shot_dir(0.0, 0.0, cone), quiet=True, burst_dead=dead)
            if zone:
                hit_n += 1
                if best is None or ("head", "body", "leg").index(zone) < ("head", "body", "leg").index(best):
                    best = zone
        if not hit_n:
            self.add_float("miss", C_RED)
            self.play(self.snd_miss)
        elif n > 1:
            self.add_float(f"BURST {hit_n}/{n}", C_DIM)
        self.gun_last_zone = best
        if first is not None:
            first["shot_zone"] = best
        self.gun_after_shot(n)
        self.gun_drill_on_shot(None, None, n)

    def gun_first_shot(self):
        """ก่อนกระสุนตัดสิน (gun_shoot / gun_alt_shoot): นัดแรกของดวลที่ยังเปิดอยู่ → เวลาเห็นบอทถึงนัดแรก (first_ms)
        + เวลา/ความเร็ว/หยุดถึงยิงของนัดนั้น (gundrills) — คืน dict ดวลถ้านัดนี้คือนัดแรก ให้ผู้เรียกเติมโซนที่โดนทีหลัง
        (เดิมจดหลังกระสุน: นัดแรกที่ฆ่าเลย (one-tap) ปิดดวลไปก่อน → ไม่เคยถูกนับ ค่ากลาง first_ms จึงช้ากว่าจริง)"""
        dl = self.gun_duel
        if not dl or dl["done"] or "shot_t" in dl:
            return None
        b = dl.get("bot")
        if "first" not in dl and b is not None and b.born is not None:
            dl["first"] = self.gt - b.born
            self.gun_first_ms.append(round(dl["first"] * 1000))
        self.gun_drill_first_shot(dl)
        return dl

    def gun_after_shot(self, n=1):
        """หลังยิง (นัดเดี่ยว หรือชุดคลิกขวา n เม็ด): นับนัดที่ยิงขณะเคลื่อนที่, Op หลุดสโคป, repo ตั้ง anchor/เส้นตาย"""
        w = self.gun_w()
        if not guns.is_accurate(self.gun_weapon, self.gun_speed()):
            self.gun_moving_shots += n      # เร็วเกิน deadzone = สเปรด +เดิน/วิ่ง (นิสัยที่ต้องลดเป็น 0)
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
            self.add_float("ย้ายทัน", C_GREEN)            # (ฟอนต์ UI ไม่มี ✓)
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
        # TTK นับจากที่เราเห็นบอทครั้งแรก (บอทที่โดนฆ่าตอนจิ้มหลอกยังไม่มี born → นับจากเห็นไหล่ครั้งแรก)
        t0 = b.born if b.born is not None else b.meta.get("seen_t0", self.gt)
        ttk = self.gt - t0
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
        self.gun_drill_on_kill(b)
        if self.gun_duel and self.gun_duel.get("bot") is b:
            self.gun_duel_end("win")

    def bot_screen_off(self, b):
        """หัวบอทเทียบ crosshair (px, รวมซูม) — shot map/aim bias ของ GUNFIGHT วัดเทียบ "หัว" (ติด ref=head)
        เดิมวัดเทียบอก y=1.2 ขณะตาอยู่ 1.65 / หัว 1.60 → เล็งหัวเป๊ะก็ออก "ยิงหลุดทางบน" (ดู config.HEAD_MODES)"""
        f = focal_len(self.H) * self.gun_zoom
        x, y, z = self.cam.to_cam((b.x, b.head_y(), b.z))      # หัวตามท่า (บอทหมอบ = หัวต่ำลง)
        if z < 0.05:
            return (0, 0)
        return (f * x / z, -f * y / z)

    # ───────────────────────── update ─────────────────────────
    def update_gun(self, dt):
        self.gun_dt = dt                # gun_shoot ใช้เป็นเพดานชดเชยเศษเวลาของ fire rate (คลิกใช้ค่าเฟรมก่อนหน้า)
        self.gun_move(dt)
        self.gun_track_player()         # บอทเล็งตำแหน่งเราย้อนหลัง lag วิ (gunbots)
        self.gun_track_stop()           # เวลาที่เราเพิ่งหยุดเข้า deadzone (หยุดถึงยิงของ PEEK — gundrills)
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
            if self.gun_respawn_at is not None:  # บอทยิงเราตายในเฟรมนี้ — ตัวอื่นไม่ต้องขยับต่อ
                break
        self.gun_drill_frame()          # ANGLE: องศาคลาด ณ เฟรมแรกที่หัวบอทโผล่

    def gun_move(self, dt):
        # ฟิสิกส์เดียวกับ STRAFE/DODGE (aim/movement.py): เบรก 165 ms, counter-strafe ถึง deadzone 60 ms,
        # Shift เดิน / หมอบเดิน — เดิมเร่ง 150 / เบรก 70 m/s² หยุดสนิทใน 77 ms
        self.player_move(dt, self.gun_run_speed(), crouch=self.gun_crouch)
        ox, oz = self.gun_origin[0], self.gun_origin[2]
        self.move_within(dt, ox - GUN_MOVE_X, ox + GUN_MOVE_X, oz - GUN_MOVE_ZB, oz + GUN_MOVE_ZF)
        # เดินทะลุที่กำบังไม่ได้ (มุมกำแพงดวลระยะประชิดอยู่ในโซนเดินได้) — ผลักกลับมาหน้ากล่อง ผู้เล่นเข้าหาจากด้านหน้าเสมอ
        for bx in self.gun_covers:
            (x0, _y0, z0), (x1, _y1, z1) = bx.lo, bx.hi
            p = self.cam.pos
            if x0 - PLAYER_R < p[0] < x1 + PLAYER_R and z0 - PLAYER_R < p[2] < z1 + PLAYER_R:
                p[2] = z0 - PLAYER_R
                if self.vel[1] > 0:
                    self.vel[1] = 0.0
        self.cam.pos[1] = EYE_Y - (guns.CROUCH_DROP if self.gun_crouch else 0.0)

    def gun_spawn(self):
        """ดวลใหม่ — hold: บอทหลังกำแพง OP HOLD (โผล่ช่อง/จิ้มหลอก/วิ่งข้าม) ; angle/peek/tap/adad: gundrills ;
        ดริลอื่น: มุมกำแพง + บอทโผล่ (gunbots)"""
        oz = self.gun_origin[2]
        drill = self.gun_drill
        b = self.gun_drill_spawn()
        if b is not None:
            return b
        if drill == "hold":
            side = random.choice((-1, 1))
            kind = random.choices(("peek", "jiggle", "swing"), weights=(0.5, 0.3, 0.2))[0]
            b = self.gun_new_bot(side * (HOLD_GAP + 0.6), oz + HOLD_WALL_DZ + 0.8, self.gun_tier_now())
            b.state = "hidden"
            b.meta.update(side=side, kind=kind, t0=self.gt + random.uniform(0.4, 1.8))
            self.bots.append(b)
            self.gun_start_duel(b)
            return b
        if drill == "duel":
            dist = duel_dist(self.gun_weapon)
        elif drill == "quick":
            dist = random.uniform(15.0, 30.0)
        else:
            dist = random.uniform(20.0, 30.0)
        return self.gun_spawn_cover(dist)

    def gun_bot_ai(self, b, dt):
        if "p" not in b.meta or b.weapon is None:
            b.update_crouch(dt)             # หุ่นนิ่ง (เทสต์วางเอง) — ไม่เดิน ไม่ยิง
            return
        if self.gun_drill == "hold":
            b.update_crouch(dt)
            self.gun_hold_ai(b, dt)
            if b.alive:
                self.gun_hold_fire(b)
        elif not self.gun_drill_ai(b, dt):  # PEEK = บอทเฝ้ามุม, ADAD = ส่าย/หยุดยิง (gundrills) ; ที่เหลือโผล่จากมุม
            self.gun_cover_ai(b, dt)

    def gun_hold_ai(self, b, dt):
        m = b.meta
        side = m["side"]
        gap = HOLD_GAP
        speed = WEAPONS[b.weapon]["run_speed"] if b.weapon else 5.4
        b.vel[0] = 0.0
        if b.state == "hidden":
            if self.gt >= m["t0"]:
                b.state = "out"
                b.exposed = False
        elif b.state == "out":
            b.x -= side * speed * dt          # เคลื่อนเข้าหาช่อง
            b.vel[0] = -side * speed
            if not b.exposed and abs(b.x) < gap + 0.1:
                b.exposed = True
                b.born = self.gt
            kind = m["kind"]
            if kind == "jiggle" and abs(b.x) < gap - 0.05:
                b.state = "back"
            elif kind == "peek" and abs(b.x) < gap - random.uniform(0.35, 0.8):
                b.state = "hold"
                b.vel[0] = 0.0
                m["hold_until"] = self.gt + random.uniform(0.45, 0.85)
            elif kind == "swing" and (b.x * side) < -(gap + 0.6):
                b.exposed = False
                b.state = "gone"
        elif b.state == "hold":
            if self.gt >= m["hold_until"]:
                b.state = "back"
        elif b.state == "back":
            b.x += side * speed * dt
            b.vel[0] = side * speed
            if abs(b.x) > gap + 0.1:
                b.exposed = False
                b.state = "gone"
        if b.state == "gone":
            b.alive = False
            b.meta["die_t"] = self.gt
            b.meta["escaped"] = True
            self.gun_next_bot_at = self.gt + random.uniform(0.5, 1.2)
            self.gun_duel_end("nc")           # จิ้มหลอก/วิ่งข้าม/ถอยกลับ = ไม่นับผล
        # ขณะโผล่: เห็นก็ต่อเมื่อลำตัวอยู่ในช่อง
        if b.state in ("out", "hold", "back"):
            b.exposed = abs(b.x) < gap + 0.1

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
            self.gun_duel_end("loss")
            for b in self.bots:
                b.alive = False
                b.meta["die_t"] = self.gt
            self.gun_repo_deadline = None
        else:
            self.add_float(("HEAD -%d" if head else "-%d") % dmg, C_RED)

    # ───────────────────────── วาด ─────────────────────────
    def draw_gun_world(self, f):
        """บอท + กำแพง hold + แถบ HP — วาดบน overlay หลังฉากพื้นหลัง (f รวม zoom แล้ว)"""
        scr = self.screen
        gpu_world = getattr(self, "_world_gpu_frame", False)   # glrender วาด grid/กำแพง hold ให้แล้ว (static บน GPU)
        if not gpu_world:
            self.draw_arena_grid(f)
        covers = self.draw_arena_covers(f, gpu_world)
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        # รอยกระสุน (จางใน 4 วิ) — ผู้เล่นเห็นว่า pattern พาไปไหนตอนไม่ดึงสวน ; รอยที่มีกำแพงบังอยู่ไม่วาด
        # (overlay อยู่บนกำแพง GPU เสมอ — ไม่เช็ค = รอยบนผนังหลังโผล่ทะลุกำแพงดวล)
        for pt, t0 in self.gun_marks:
            if covers and arena.segment_blocked(eye, pt, covers):
                continue
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
                if not b.alive and b.meta.get("escaped") and b.meta.get("holder"):
                    continue                 # บอทเฝ้ามุม (PEEK) ที่หมดเวลา — หายไปเฉย ๆ ไม่ใช่ศพเทา (ยืนกลางที่โล่ง)
                r = self.draw_bot(b, f)
                if r is not None and covers:
                    self.draw_cover_occlusion(covers, b, r, f, gpu_world)
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

    def draw_arena_grid(self, f):
        """software path: ตารางพื้นส่วนที่ห้องเดิมไม่มี (z -22..2) — ไม่งั้นพื้นใกล้ตัวเรียบจนกะระยะ/ความเร็วเดินไม่ออก
        (GPU วาด segment "gungrid" ใน glrender) ; ใช้ร่วม GUNFIGHT + reaction·peek"""
        scr = self.screen
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

    def draw_arena_covers(self, f, gpu_world):
        """ที่กำบัง (gun_covers ที่ draw=True): GPU วาดใน glrender (VBO สร้างใหม่เมื่อชุดกล่องเปลี่ยน) ; software วาดที่นี่
        ไกล → ใกล้ — คืนลิสต์กล่องที่วาดได้ (ไว้บังบอทที่อยู่หลังกล่อง)"""
        covers = [bx for bx in self.gun_covers if bx.draw]
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        if covers and not gpu_world:
            for bx in sorted(covers, key=lambda q: -q.dist2(eye)):
                self.draw_cover_box(bx, f)
        return covers

    def draw_bot(self, b, f):
        """วาดหุ่นบอท (ขา/ลำตัว/หัว/แถบ HP) — คืน Rect ที่ครอบทุกพิกเซลที่วาด (mark_dirty แล้ว) หรือ None ถ้าอยู่หลังกล้อง"""
        scr = self.screen
        alive = b.alive
        def P(y):
            return self.project((b.x, y, b.z), f)
        top, chest, hip, foot = P(b.head_y() + guns.HEAD_R), P(b.body_y1()), P(b.body_y0()), P(b.leg_y0())
        if not (chest and hip and foot):
            return None
        z = chest[2]
        body_hw = max(1, int(f * guns.BODY_HW / z))
        leg_hw = max(1, int(f * guns.LEG_HW / z))
        c_body = (88, 34, 44) if alive else (60, 60, 60)
        c_leg = (70, 28, 36) if alive else (50, 50, 50)
        legs = pygame.Rect(int(foot[0]) - leg_hw, int(hip[1]), leg_hw * 2, max(1, int(foot[1] - hip[1])))
        body = pygame.Rect(int(chest[0]) - body_hw, int(chest[1]), body_hw * 2, max(1, int(hip[1] - chest[1])))
        # dirty-rect: ขา+ลำตัวเป็นกรอบเดียว — เดิม mark เฉพาะขา ลำตัว/ขอบขาวไม่เคยถูกอัพโหลด/เคลียร์บน GPU path
        # → บอทใกล้ไม่มีลำตัว (หัวลอยเหนือขา) และบอทที่เดิน (hold peek/jiggle, duel strafe) ทิ้งเศษแดง-ขาวค้างเป็นแถบ
        drawn = legs.union(body).inflate(4, 4)
        self.mark_dirty(drawn)
        pygame.draw.rect(scr, c_leg, legs, border_radius=max(1, leg_hw // 2))
        pygame.draw.rect(scr, c_body, body, border_radius=max(1, body_hw // 2))
        pygame.draw.rect(scr, (255, 255, 255), body, 1, border_radius=max(1, body_hw // 2))
        hp = P(b.head_y())
        if hp:
            hr = max(2, int(f * guns.HEAD_R / hp[2]))
            hrect = pygame.draw.circle(scr, (60, 18, 26), (int(hp[0]), int(hp[1])), hr + 1).inflate(2, 2)
            self.mark_dirty(hrect)
            drawn = drawn.union(hrect)
            pygame.draw.circle(scr, (255, 120, 132) if alive else (90, 90, 90), (int(hp[0]), int(hp[1])), hr)
            pygame.draw.circle(scr, (255, 235, 235), (int(hp[0]), int(hp[1])), max(1, hr // 3))
        # แถบ HP/เกราะ เหนือหัว (หุ่น reaction·peek ไม่มี — หัวเดียวจบ แถบเต็มตลอดเป็นแค่สิ่งรบกวนสายตา)
        if alive and top and not b.meta.get("no_bar"):
            hf, sf = b.hp_frac()
            bw = max(14, body_hw * 3)
            bx, by = int(top[0]) - bw // 2, int(top[1]) - 8
            pygame.draw.rect(scr, (20, 20, 24), (bx - 1, by - 1, bw + 2, 5))
            pygame.draw.rect(scr, (235, 235, 235), (bx, by, int(bw * hf), 3))
            if sf > 0:
                pygame.draw.rect(scr, (110, 170, 255), (bx, by - 4, int(bw * sf), 2))
            brect = pygame.Rect(bx - 2, by - 6, bw + 4, 12)
            self.mark_dirty(brect)
            drawn = drawn.union(brect)
        return drawn

    def _cover_face_pts(self, bx, name, f):
        """มุมหน้ากล่องบนจอ (clip near-plane แบบเดียวกับ poly/glrender) — None ถ้าหลุดหลังกล้องทั้งหน้า"""
        from .worlddraw import _clip_near
        cs = _clip_near([self.cam.to_cam(p) for p in bx.face_pts(name)])
        if len(cs) < 3:
            return None
        return [(self.W / 2 + f * x / z, self.H / 2 - f * y / z) for (x, y, z) in cs]

    def draw_cover_box(self, bx, f):
        """software path: วาดหน้ากล่องที่หันหาตา (สีต่อหน้า + ขอบ 2px) — สีเดียวกับ glrender (arena.FACE_COL)"""
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        for name in bx.visible_faces(eye):
            pts = self._cover_face_pts(bx, name, f)
            if pts is None:
                continue
            self.mark_dirty(pygame.draw.polygon(self.screen, arena.FACE_COL[name], pts).inflate(4, 4))
            pygame.draw.polygon(self.screen, arena.EDGE_COL, pts, 2)

    def draw_cover_occlusion(self, covers, b, rect, f, gpu_world):
        """กล่องที่อยู่ "หน้า" บอท (arena.Box.occludes) ต้องบังตัวบอทที่เพิ่งวาดบน overlay — จำกัดในกรอบบอท (mark แล้ว):
        GPU = เจาะ overlay ให้โปร่ง (เห็นกล่องที่ glrender วาดไว้ข้างใต้พอดีพิกเซล) ; software = วาดหน้ากล่องทับซ้ำ
        (เดิมไม่มีที่กำบัง บอทวาดบนสุดเสมอ — ถ้าไม่บัง บอทที่แอบหลังกำแพงจะโผล่ให้เห็นทะลุกำแพง)"""
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        # ยกพื้นใต้เท้าบอทตัวนี้ (ANGLE ledge) ไม่ใช่ของที่อยู่หน้าตัวมัน — occludes แบบเผื่อตอบ True เสมอแล้วหน้าบนจะทับขา
        # (ยกพื้นที่อยู่หน้าบอทอีกตัวบนพื้นราบยังต้องบังขาตามปกติ)
        def under(bx):
            return bx.ledge and bx.lo[0] <= b.x <= bx.hi[0] and bx.lo[2] <= b.z <= bx.hi[2]
        occ = [bx for bx in covers if not under(bx) and bx.occludes(eye, (b.x, 1.0 + b.y0, b.z))]
        if not occ:
            return
        scr = self.screen
        area = rect.clip(pygame.Rect(0, 0, self.W, self.H))
        if area.w <= 0 or area.h <= 0:
            return
        prev = scr.get_clip()
        scr.set_clip(area.clip(prev) if prev else area)
        try:
            for bx in sorted(occ, key=lambda q: -q.dist2(eye)):
                for name in bx.visible_faces(eye):
                    pts = self._cover_face_pts(bx, name, f)
                    if pts is None:
                        continue
                    if gpu_world:
                        pygame.draw.polygon(scr, (0, 0, 0, 0), pts)
                    else:
                        pygame.draw.polygon(scr, arena.FACE_COL[name], pts)
                        pygame.draw.polygon(scr, arena.EDGE_COL, pts, 2)
        finally:
            scr.set_clip(prev)

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
        """HP/เกราะ + กระสุน มุมล่าง (วาดหลัง HUD) — ทุกขนาด/ระยะคูณ hud_scale ตัวเดียวกับ draw_hud
        (เดิมพิกเซลตายตัว: ที่ 2560×1440 บรรทัดบอท/TAP ที่ H-56 ถูก 'PB …' ของ HUD (ขยาย ×2 แล้ว) ทับ — review 2026-09-24)"""
        W, H = self.W, self.H
        sc = self.hud_scale()

        def S(v):
            return int(round(v * sc))
        w = self.gun_w()
        x, y = S(24), H - S(96)
        bw = S(200)
        # หนีบ 0..1: แถบกว้างเกิน bw จะทะลุกรอบสถานะที่ mark_dirty ไว้ (ภาพค้างบน GPU dirty-rect)
        hf = min(1.0, max(0.0, self.gun_hp / guns.PLAYER_HP))
        sf = min(1.0, max(0.0, self.gun_shield / guns.PLAYER_SHIELD))
        # dirty-rect: กล่องสถานะ + ข้อความ (text() mark เอง) — เดิม mark_full ทุกเฟรม = อัพโหลด overlay เต็ม 14MB/เฟรม
        # ตลอดโหมด GUNFIGHT (สาเหตุหลักที่เฟรมตกที่ 1440p)
        self.mark_dirty(pygame.draw.rect(self.screen, (8, 20, 28), (x - S(8), y - S(26), S(300), S(60)),
                                         border_radius=S(6)))
        self.text(f"{max(0, int(self.gun_hp))}", S(22), C_TEXT, (x, y - S(24)), bold=True)
        self.text(f"+{max(0, int(self.gun_shield))}", S(14), (110, 170, 255), (x + S(52), y - S(18)), bold=True)
        pygame.draw.rect(self.screen, (40, 50, 60), (x, y + S(6), bw, S(8)))
        pygame.draw.rect(self.screen, (235, 235, 235), (x, y + S(6), int(bw * hf), S(8)))
        pygame.draw.rect(self.screen, (110, 170, 255), (x, y + S(2), int(bw * sf), S(3)))
        ammo = f"{self.gun_mag} / {w['mag']}"
        col = C_RED if self.gun_mag == 0 else C_TEXT
        if self.gun_reload_until > 0:
            ammo = "RELOADING %.1f" % max(0.0, self.gun_reload_until - self.gt)
            col = C_GOLD
        # สูงบรรทัดฟอนต์ ~1.35 × ขนาด: กระสุน 20 px สูง 27 — วางที่ -102 ไม่ชนบรรทัดปืน/ดริลที่ -74 (เดิม -100 ทับ 1 px)
        self.text(ammo, S(20), col, (W - S(24), H - S(102)), right=True, bold=True)
        self.text(f"{w['name']} · {GUN_DRILL_NAME[self.gun_drill]}", S(12), C_DIM, (W - S(24), H - S(74)), right=True)
        # ระดับบอทตอนนี้ (บันไดแรงค์ขยับทุกดวลใน DUEL/ANGLE/PEEK) — สีตามแรงค์ ; TAP บอทไม่ยิง = โชว์วินัยแตะแทน
        if self.gun_drill == "tap":
            tp = self.gun_tap
            self.text(f"ยิงก่อนสเปรดหาย {tp['spam']}/{tp['n']} นัด", S(12), C_PALE_GOLD, (W - S(24), H - S(56)),
                      right=True, bold=True)
        else:
            tier = self.gun_tier_now()
            lad = self.gun_ladder
            tag = f"บอท {duel.step_label(tier)}" + (f" · ดวล {lad.wins}/{lad.n}" if lad is not None and lad.n else "")
            self.text(tag, S(12), hexrgb(duel.tier_color(tier)), (W - S(24), H - S(56)), right=True, bold=True)
        hint = GUN_DRILL_HINT.get(self.gun_drill)
        if hint and self.gt < 3.0:
            self.text(hint, S(16), C_GOLD, (W // 2, int(H * 0.30)), center=True, bold=True)
        if self.gun_repo_deadline is not None:
            left = max(0.0, self.gun_repo_deadline - self.gt)
            self.text(f"ย้ายที่! {left:.1f}s", S(18), C_RED if left < 0.7 else C_GOLD, (W // 2, H - S(110)),
                      center=True, bold=True)
        if self.gun_respawn_at is not None:
            self.text("DEAD — เกิดใหม่", S(26), C_RED, (W // 2, H // 2 - S(80)), center=True, bold=True)

    def gun_hud(self):
        kd = f"{self.gun_kills}/{self.gun_deaths}"
        acc = f"{round(self.gun_hits / self.gun_shots * 100)}%" if self.gun_shots else "--%"
        hs = f"{round(self.gun_hs / self.gun_hits * 100)}%" if self.gun_hits else "--%"
        left = [(self.score, C_TEXT, "SCORE"), (kd, C_GREEN, "K / D")]
        right = [(acc, C_TEXT, "ACCURACY"), (hs, C_PALE_GOLD, "HS%")]
        return left, right

    # ───────────────────────── ผลลัพธ์ ─────────────────────────
    def gun_result_cards(self):
        dc = self.gun_drill_cards()         # ANGLE/PEEK/TAP/ADAD: การ์ดตัวชี้วัดเฉพาะดริล (gundrills)
        if dc is not None:
            return dc
        ttk = round(sum(self.gun_ttk) / len(self.gun_ttk)) if self.gun_ttk else 0
        acc = round(self.gun_hits / self.gun_shots * 100) if self.gun_shots else 0
        hs = round(self.gun_hs / self.gun_hits * 100) if self.gun_hits else 0
        spk = f"{self.gun_shots / self.gun_kills:.1f}" if self.gun_kills else "--"
        cards = [(f"{self.gun_kills}/{self.gun_deaths}", "K / D"), (f"{ttk}ms", "AVG TTK"),
                 (f"{acc}%", "ACCURACY"), (f"{hs}%", "HEADSHOT")]
        extra = f"กระสุน/คิล {spk}"
        lad = self.gun_ladder
        if lad is not None and lad.n:
            extra += f" · ชนะดวล {lad.wins}/{lad.n}"
        if self.gun_first_ms:
            fs = sorted(self.gun_first_ms)
            extra += f" · เห็นบอทถึงนัดแรก {fs[len(fs) // 2]}ms"
        if self.gun_moving_shots:
            extra += f" · ยิงตอนยังเดิน {round(self.gun_moving_shots / max(1, self.gun_shots) * 100)}%"
        if self.gun_drill == "hold":
            extra += f" · โดนจิ้มหลอก {self.gun_baited} ครั้ง"
        if self.gun_drill == "repo":
            extra += f" · ย้ายทัน {self.gun_repo_ok} · โดน pre-fire {self.gun_prefired} ครั้ง"
        if self.gun_drill == "quick" and self.gun_scope_times:
            extra += f" · โผล่ถึงสโคป {round(sum(self.gun_scope_times) / len(self.gun_scope_times))}ms"
        if self.gun_alt_bursts:
            extra += f" · คลิกขวา {self.gun_alt_bursts} ชุด"
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
        if self.gun_alt_bursts:
            ent["alt_bursts"] = self.gun_alt_bursts     # Classic คลิกขวา (เม็ดนับรวมใน shots_fired แล้ว)
        # บันไดแรงค์ (DESIGN §2.5): duel = tier_i (ดัชนี RANKS ที่ลู่เข้า) + tier_n (ดวลที่ตัดสินผล) ; ดริลอื่น tier_bot
        self.gun_ladder_fields(ent)
        if self.gun_first_ms:
            fs = sorted(self.gun_first_ms)
            ent["first_ms"] = fs[len(fs) // 2]          # ค่ากลาง เห็นบอท → นัดแรกของเรา (ms)
        if self.gun_shots:
            ent["moving_pct"] = round(self.gun_moving_shots / self.gun_shots * 100)   # ยิงตอนเร็วเกิน deadzone
        self.gun_drill_fields(ent)          # ตัวชี้วัดเฉพาะดริล angle/peek/tap/adad (gundrills.DRILL_KEYS)
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


def _selftest_sidearms():
    """Ghost/Classic (2026-09-24): ดริลที่เปิด · สเปรด/โทษเดินตาม wiki · Classic คลิกขวา · ระยะ duel ตามข้อมูลจริง"""
    errors = []
    # ── ดริล: Ghost/Classic ไม่มี OP HOLD/TAP ; Op ไม่มี TAP/ADAD ; เลือกคู่ที่ใช้ไม่ได้ (แผน/deep-link) → เริ่มรอบเป็น DUEL ──
    for wp in ("ghost", "classic"):
        if drills_for(wp) != ["duel", "quick", "repo", "angle", "peek", "adad"]:
            errors.append(f"{wp}: ดริลต้องเป็น duel/quick/repo/angle/peek/adad (ได้ {drills_for(wp)})")
        for bad in ("hold", "tap"):
            g = _FakeGame(wp, bad)
            if g.gun_drill != "duel":
                errors.append(f"{wp}+{bad} ต้องถูกย้ายเป็น duel ตอนเริ่มรอบ (ได้ {g.gun_drill})")
    if drills_for("sheriff") != [d[0] for d in GUN_DRILLS] or drills_for("vandal") != [d[0] for d in GUN_DRILLS]:
        errors.append("Sheriff/Vandal ต้องเล่นได้ทุกดริล")
    if drills_for("operator") != ["duel", "hold", "quick", "repo", "angle", "peek"]:
        errors.append(f"operator: 4 ดริลเดิม + angle/peek (ได้ {drills_for('operator')})")
    if [d[0] for d in GUN_DRILLS][:4] != ["duel", "hold", "quick", "repo"]:
        errors.append("ดริลเดิม 4 ตัวต้องอยู่ลำดับเดิม (ปุ่ม B/เมนู/ประวัติ)")
    # สำเนา pure python ใน guns.py (server import) ต้องตรงกับที่เกมใช้ทุกปืน
    if list(guns.DRILL_ORDER) != [d[0] for d in GUN_DRILLS] or \
            any(guns.weapon_drills(w) != drills_for(w) for w in guns.WEAPON_ORDER) or \
            not set(guns.WEAPON_DRILLS) <= set(guns.WEAPON_ORDER):
        errors.append(f"guns.DRILL_ORDER/weapon_drills ไม่ตรง GUN_DRILLS ({guns.DRILL_ORDER})")
    # ── สเปรดจากการยิง (Stability): นัดแรก/สูงสุดตรง wiki, แตะ ≤4 นัด/วิ = นัดแรกทุกนัด ──
    for wp, first, mx in (("ghost", 0.3, 1.65), ("classic", 0.4, 1.8)):
        s = Stability(wp, WEAPONS[wp]["rps"])
        spam = [round(s.shoot(i / WEAPONS[wp]["rps"])[2], 3) for i in range(5)]
        if spam[0] != first or abs(max(spam) - mx) > 1e-6 or spam != sorted(spam):
            errors.append(f"{wp}: สเปรดรัว {spam} (ต้องเริ่ม {first}° โตถึง {mx}°)")
        s = Stability(wp, WEAPONS[wp]["rps"])
        taps = [round(s.shoot(i * 0.25)[2], 3) for i in range(5)]
        if any(v != first for v in taps):
            errors.append(f"{wp}: แตะ 4 นัด/วิ ต้องแม่นเท่านัดแรกทุกนัด {taps}")
        s = Stability(wp, WEAPONS[wp]["rps"])
        cr = s.shoot(0.0, crouch=True)[2]
        if abs(cr - WEAPONS[wp]["spread"]["crouch"]) > 0.006:
            errors.append(f"{wp}: สเปรดหมอบ {cr:.3f}° (wiki {WEAPONS[wp]['spread']['crouch']}°)")
        run = WEAPONS[wp]["run_speed"]
        got = (guns.move_error_deg(wp, 0.27 * run), guns.move_error_deg(wp, 0.30 * run),
               guns.move_error_deg(wp, run), guns.move_error_deg(wp, 0.4 * run, crouch=True))
        if got != (0.0, 1.1, 2.3, 0.5):
            errors.append(f"{wp}: โทษเคลื่อนที่ (deadzone/เดิน/วิ่ง/หมอบเดิน) {got} ต้อง (0, 1.1, 2.3, 0.5)")
    # ── Classic คลิกขวา: 3 เม็ด/ชุด, 2.22 ชุด/วิ, 1.9° → 5.78° เมื่อกดติดกัน, พักแล้วกลับ 1.9° ──
    g = _FakeGame("classic", "duel")
    alt = WEAPONS["classic"]["alt"]
    g.step(1.0 / 60)
    cones = []
    for i in range(4):
        cones.append(round(g.gun_alt_spread(), 3))
        n0, m0 = g.gun_shots, g.gun_mag
        g.gun_rmb(True)
        if (g.gun_shots - n0, m0 - g.gun_mag) != (3, 3):
            errors.append(f"classic RMB ชุดที่ {i + 1}: ต้องออก 3 เม็ด กิน 3 นัด (ได้ {g.gun_shots - n0}/{m0 - g.gun_mag})")
        g.gun_rmb(True)                       # กดซ้ำทันที = ยังไม่ถึงคิว 1/2.22 วิ
        if g.gun_shots - n0 != 3:
            errors.append("classic RMB: กดซ้ำก่อนครบ 1/2.22 วิ ต้องไม่ออก")
        g.gun_shoot()                         # คลิกซ้ายก็ต้องรอคิวเดียวกัน
        if g.gun_shots - n0 != 3:
            errors.append("classic: คลิกซ้ายหลังคลิกขวาต้องรอคิว 1/2.22 วิเหมือนกัน")
        while g.gt < g.gun_next_shot_at:      # กดขวารัวเร็วสุดที่ปืนยอม (60 FPS)
            g.step(1.0 / 60)
    if cones[:3] != [1.9, 3.84, 5.78] or cones[3] != 5.78:
        errors.append(f"classic RMB สเปรดต่อชุด {cones} (ต้อง 1.9 → 3.84 → 5.78 ค้าง max)")
    for _ in range(int(60 * (ALT_HOLD / alt["rps"] + alt["esc_reset"] + 0.05))):
        g.step(1.0 / 60)
    if abs(g.gun_alt_spread() - 1.9) > 1e-6:
        errors.append(f"classic RMB: พักครบแล้วต้องกลับ 1.9° (ได้ {g.gun_alt_spread():.2f})")
    g.vel = [WEAPONS["classic"]["run_speed"], 0.0]
    if abs(g.gun_alt_spread() - (1.9 + 1.5)) > 1e-6:
        errors.append(f"classic RMB วิ่ง: ต้อง 1.9 + 1.5° (ได้ {g.gun_alt_spread():.2f})")
    g.vel = [0.0, 0.0]
    g.gun_mag = 2; g.gun_next_shot_at = 0.0; g.gun_reload_until = 0.0   # (ชุดที่ 4 ใช้แม็กหมด → กดซ้ำเริ่มรีโหลดไว้)
    n0 = g.gun_shots
    g.gun_rmb(True)
    if g.gun_shots - n0 != 2 or g.gun_mag != 0:
        errors.append("classic RMB: เหลือ 2 นัด ต้องออก 2 เม็ด")
    # คลิกขวาเข้าหัวทั้ง 3 เม็ด (กรวย 0 = ตรงเป๊ะ): เม็ด 2 ฆ่า (78 + 78 ≥ 150) เม็ด 3 ทับศพ → นับ "โดน" ไม่ใช่พลาด
    g = _FakeGame("classic", "duel")
    b = Bot(0.0, g.cam.pos[2] + 5.0)
    g.bots = [b]
    g.step(1.0 / 60)
    g.aim_world(b.x, guns.HEAD_Y, b.z)
    g.gun_alt_spread = lambda: 0.0
    g.gun_rmb(True)
    if b.alive or len(b.damage_taken) != 2 or (g.gun_hits, g.gun_shots, g.gun_hs, g.misses) != (3, 3, 3, 0):
        errors.append(f"classic RMB 3 หัว: ต้องตายที่เม็ด 2 และนับโดน 3/3 "
                      f"(dmg {b.damage_taken} hits {g.gun_hits}/{g.gun_shots} hs {g.gun_hs} miss {g.misses})")
    # Ghost: RMB ไม่ทำอะไร (ไม่มี ADS/alt)
    g = _FakeGame("ghost", "duel")
    g.step(1.0 / 60)
    g.gun_rmb(True)
    if g.gun_shots or g.gun_zoom != 1.0:
        errors.append("ghost: RMB ต้องไม่ยิง/ไม่ซูม")
    # ── ระยะ duel ตามการกระจายระยะคิลจริงของปืนนั้น (gun rev 5: ไรเฟิล/Sheriff ด้วย) ; Op คง 8–30 ม. ──
    for wp, qs in DUEL_DIST_Q.items():
        ds = sorted(duel_dist(wp) for _ in range(4000))
        med = ds[len(ds) // 2]
        if not (qs[0] - 1e-9 <= ds[0] and ds[-1] <= qs[-1] + 1e-9 and abs(med - qs[2]) < 0.8):
            errors.append(f"{wp}: ระยะ duel {ds[0]:.1f}–{ds[-1]:.1f} กลาง {med:.1f} (ข้อมูลจริง {qs[0]}–{qs[-1]} กลาง {qs[2]})")
    if set(DUEL_DIST_Q) != set(guns.WEAPON_ORDER) - {"operator"}:
        errors.append(f"duel: ปืนที่ไม่ใช่ Op ต้องมีการกระจายระยะจริงครบ (มี {sorted(DUEL_DIST_Q)})")
    ds = [duel_dist("operator") for _ in range(2000)]
    if min(ds) < 8.0 or max(ds) > 30.0:
        errors.append("operator: ระยะ duel ต้องคง 8–30 ม.")
    return errors


def _v2_bot(g, x, z, tier=16, kind="hold", crouch_fire=False):
    """บอท v2 วางเองสำหรับเทสต์: ท่า kind ยืนที่ (x, z) ช่วง fight ทันที (ไม่มีที่กำบัง เว้นแต่เทสต์ใส่เอง)"""
    b = g.gun_new_bot(x, z, tier)
    b.meta.update(kind=kind, side=1, edge=x - 0.5, dir=-1, x_hide=x + 1.0, x_to=x, phase="fight",
                  t_go=g.gt, crouch_fire=crouch_fire)
    g.bots = [b]
    g.gun_start_duel(b)
    return b


def _selftest_bot_crouch():
    """บอทหมอบตอนเริ่มยิงนัดแรก: หัวลด CROUCH_DROP ใน CROUCH_TIME, เล็งหัวระดับยืนพลาด, ลุกกลับหลังช่วงหมอบ"""
    errors = []
    g = _FakeGame("vandal", "duel")
    b = _v2_bot(g, 0.0, g.cam.pos[2] + 15.0, crouch_fire=True)
    g.gun_hp = 10 ** 6                       # เทสท่าบอทล้วน — ไม่ให้เราตายกลางเทส
    g.step(1.0 / 60)
    if b.crouch_to or b.crouch:
        errors.append("crouch: ยังไม่ยิงนัดแรก ต้องยืนอยู่")
    while b.meta["t_first"] is None and g.gt < 2.0:
        g.gun_hp = 10 ** 6
        g.step(1.0 / 60)                     # ถึงคิวยิงนัดแรก (rt ของระดับหลังเห็นกัน)
    t_fire = b.meta["t_first"]
    if t_fire is None:
        errors.append("crouch: บอทไม่ยิงเลยใน 2 วิ")
        return errors
    while g.gt < t_fire + guns.CROUCH_TIME + 0.02:
        g.gun_hp = 10 ** 6
        g.step(1.0 / 60)
    if abs(b.crouch - 1.0) > 1e-9 or abs(b.head_y() - (guns.HEAD_Y - guns.CROUCH_DROP)) > 1e-9:
        errors.append(f"crouch: หลังยิงนัดแรก {guns.CROUCH_TIME}s ต้องหมอบสุด (crouch={b.crouch:.2f})")
    g.aim_world(b.x, guns.HEAD_Y, b.z)       # ค้างเป้าระดับหัวยืน (pre-aim เดิม)
    if b.hit_zone(g.cam) is not None:
        errors.append(f"crouch: เล็งหัวระดับยืนต้องข้ามหัวบอทที่หมอบ (ได้ {b.hit_zone(g.cam)})")
    g.aim_world(b.x, b.head_y(), b.z)
    if b.hit_zone(g.cam) != "head":
        errors.append("crouch: เล็งหัวที่ลดลงต้องได้ head")
    off = g.bot_screen_off(b)                # ตอนนี้เล็งหัวที่ลดลงอยู่ → shot map ต้องได้ ~0 (วัดเทียบหัวตามท่า)
    if abs(off[0]) > 0.5 or abs(off[1]) > 0.5:
        errors.append(f"crouch: shot map ต้องวัดเทียบหัวที่ลดลง (offset {off})")
    g.aim_world(b.x, b.body_y1() - 0.2, b.z)
    if b.hit_zone(g.cam) != "body":
        errors.append("crouch: อกบอทหมอบต้องได้ body")
    while b.meta.get("crouch_until") is not None and g.gt < t_fire + BOT_CROUCH_HOLD[1] + 0.1:
        g.gun_hp = 10 ** 6
        g.step(1.0 / 60)
    for _ in range(12):
        g.gun_hp = 10 ** 6
        g.step(1.0 / 60)
    if b.crouch or b.crouch_to or b.meta.get("crouch_until") is not None:
        errors.append(f"crouch: ต้องลุกยืนภายใน {BOT_CROUCH_HOLD[1]}s + {guns.CROUCH_TIME}s (crouch={b.crouch:.2f})")
    for _ in range(90):                      # หมอบครั้งเดียวต่อบอท (นัดต่อๆ ไปไม่หมอบซ้ำ)
        g.gun_hp = 10 ** 6
        g.step(1.0 / 60)
    if b.crouch_to:
        errors.append("crouch: หมอบซ้ำหลังลุกแล้ว (ต้องครั้งเดียวต่อบอท)")
    # สัดส่วนบอทที่หมอบตอนยิง ≈ BOT_CROUCH_P × (ท่าที่ไม่ใช่หมอบโผล่) ; OP HOLD ไม่มี
    from .gunbots import BEHAVIORS
    w_crouch = dict(BEHAVIORS)["crouch"] / sum(w for _k, w in BEHAVIORS)
    want = BOT_CROUCH_P * (1.0 - w_crouch)
    for drill in ("duel", "quick", "repo"):
        g = _FakeGame("vandal", drill)
        n, flags = 1500, []
        for _ in range(n):
            g.bots = []
            g.gun_spawn()
            flags.append(bool(g.bots[0].meta.get("crouch_fire")))
        p = sum(flags) / n
        if abs(p - want) > 0.04:
            errors.append(f"crouch: บอท {drill} หมอบตอนยิง {p:.1%} (คาด {want:.0%})")
    g = _FakeGame("vandal", "hold")
    g.gun_spawn()
    if g.bots[0].meta.get("crouch_fire"):
        errors.append("crouch: ดริล hold ต้องไม่มีบอทหมอบ")
    return errors


def _dummy_ttd(tier, n, seed):
    """คนยืนนิ่งไม่ยิง vs บอทระดับ tier (duel, Vandal) — เวลาตายนับจากบอทเริ่มเห็นเรา (วิ) ; ไม่ตายใน 14 วิ = inf"""
    out = []
    for k in range(n):
        random.seed(seed + k)
        g = _FakeGame("vandal", "duel")
        g.gun_ladder = None
        g.gun_fixed_tier = tier
        b = g.gun_spawn()
        while g.gt < 14.0 and not g.gun_deaths and b.alive:
            g.step(1.0 / 144)
        los = b.meta.get("los_t0")
        out.append(g.gt - los if (g.gun_deaths and los is not None) else float("inf"))
    return sorted(out)


def _selftest_bots_v2():
    """บอท v2 (gunbots/duel): ตายไวเมื่อยืนนิ่งกับบอทระดับสูง · ที่กำบังบังกระสุนทั้งสองฝั่ง · peeker's advantage ·
    HP รีเซ็ตทุกดวล · บันไดขึ้น/ลงถูก · history มี tier_i/tier_n · บอทยิงเมื่อหยุดใน deadzone เท่านั้น (เว้นตัววิ่งยิง)"""
    from . import arena
    errors = []
    # ── 1) คนยืนนิ่งไม่ยิงเลย: บอท Immortal ฆ่าใน < 1 วิหลังเห็นกัน ≥ 75% (sim n 300: 91%) ; Iron ช้ากว่าชัด ──
    imm = _dummy_ttd(21, 120, 7100)
    iron = _dummy_ttd(1, 120, 7300)
    p_imm = sum(1 for x in imm if x < 1.0) / len(imm)
    p_iron = sum(1 for x in iron if x < 1.0) / len(iron)
    if p_imm < 0.75:
        errors.append(f"bots: ยืนนิ่งไม่ยิง vs Immortal ตาย < 1 วิ แค่ {p_imm:.0%} (ต้อง ≥ 75% — เดิมบอทโยนเหรียญ 7%)")
    if not (p_iron < p_imm - 0.3 and iron[len(iron) // 2] > imm[len(imm) // 2]):
        errors.append(f"bots: Iron ต้องฆ่าช้ากว่า Immortal ชัดเจน (P<1s {p_iron:.0%} vs {p_imm:.0%})")
    # ── 2) ที่กำบัง: กระสุนบอทผ่านกำแพงไม่ได้ / ไม่มีกำแพงโดน ; กระสุนเราผ่านกำแพงไม่ได้ ──
    g = _FakeGame("vandal", "duel")
    oz = g.cam.pos[2]
    b = _v2_bot(g, 0.0, oz + 15.0, tier=22)
    b.meta["p"] = dict(b.meta["p"], sigma=0.0, lag=0.0)
    b.meta["aim_head"] = True
    g.gun_track_player()
    wall = arena.Box(-2.0, 2.0, 0.0, 3.0, oz + 7.0, oz + 7.6)
    g.gun_set_covers([wall])
    hp0 = (g.gun_hp, g.gun_shield)
    for _ in range(3):
        g.gt += 0.5
        g.gun_bot_fire(b)
    if (g.gun_hp, g.gun_shield) != hp0:
        errors.append(f"cover: กระสุนบอททะลุกำแพง (HP {hp0} → {(g.gun_hp, g.gun_shield)})")
    g.gun_set_covers([])
    for _ in range(3):
        g.gt += 0.5
        g.gun_bot_fire(b)
    if g.gun_deaths == 0 and (g.gun_hp, g.gun_shield) == hp0:
        errors.append("cover: ไม่มีกำแพงแล้วบอทเล็งหัวคลาด 0 ต้องยิงโดน")
    g = _FakeGame("vandal", "duel")
    b = _v2_bot(g, 0.0, oz + 15.0)
    g.gun_set_covers([arena.Box(-2.0, 2.0, 0.0, 3.0, oz + 7.0, oz + 7.6)])
    g.aim_world(b.x, b.head_y(), b.z)
    g.gun_next_shot_at = 0.0
    g.step(1.0 / 60)
    g.aim_world(b.x, b.head_y(), b.z)
    g.gun_next_shot_at = 0.0
    g.gun_shoot()
    if b.hp != guns.PLAYER_HP or g.gun_hits:
        errors.append("cover: ยิงหัวบอทที่อยู่หลังกำแพงต้องโดนกำแพง ไม่ใช่บอท")
    elif not g.gun_marks or abs(g.gun_marks[-1][0][2] - (oz + 7.0)) > 1e-6:
        errors.append(f"cover: รอยกระสุนต้องอยู่ผิวหน้ากำแพง ({g.gun_marks[-1][0] if g.gun_marks else None})")
    g.gun_bot_los(b)
    if b.exposed or b.meta["los"]:
        errors.append("cover: บอทหลังกำแพงต้องมองไม่เห็นกันทั้งสองฝั่ง")
    # ── 3) peeker's advantage: บอทวิ่งออกมา = rt − PA ; บอทยืนเฝ้าแล้วเราวิ่งเข้ามา = rt + PA ; นิ่งทั้งคู่ = rt ──
    for label, bot_v, me_v, want in (("peek", 5.4, 0.0, -duel.PEEK_ADV), ("hold", 0.0, 5.4, duel.PEEK_ADV),
                                     ("still", 0.0, 0.0, 0.0)):
        g = _FakeGame("vandal", "duel")
        b = _v2_bot(g, 0.0, g.cam.pos[2] + 15.0)
        b.vel[0] = bot_v
        g.vel = [me_v, 0.0]
        g.gt = 1.0
        g.gun_bot_los(b)
        got = (b.meta["fire_at"] - g.gt) if b.meta["fire_at"] is not None else None
        if got is None or abs(got - (b.meta["p"]["rt"] + want)) > 1e-9:
            errors.append(f"peek adv ({label}): นัดแรกหลังเห็นกัน {got} (ต้อง rt {b.meta['p']['rt']:.3f} {want:+.3f})")
    # ── 4) HP รีเซ็ตทุกดวล (เดิมรีเซ็ตเฉพาะตอนเกิดใหม่) ──
    g = _FakeGame("vandal", "duel")
    g.gun_hp, g.gun_shield = 12, 0
    g.gun_spawn()
    if (g.gun_hp, g.gun_shield) != (guns.PLAYER_HP, guns.PLAYER_SHIELD):
        errors.append(f"duel: เริ่มดวลใหม่ HP ต้องเต็ม (ได้ {g.gun_hp}/{g.gun_shield})")
    # ── 5) บันได 1-up/1-down: สายใหม่ก้าว 2 จนกลับทิศ (นับข้ามรอบ), แล้วก้าว 1, ปลายเผื่อ ±2 ขั้น, ค่าที่รายงานหนีบ 0..22 ──
    lad = duel.Ladder()
    seq = [lad.record(w) for w in (True, True, False, False, True)]
    if lad.fresh is not True or seq != [duel.LADDER_START + 2, duel.LADDER_START + 4, duel.LADDER_START + 3,
                                        duel.LADDER_START + 2, duel.LADDER_START + 3]:
        errors.append(f"ladder: บันไดใหม่เดินผิด {seq} (เริ่ม {duel.LADDER_START} ก้าว 2 จนกลับทิศแล้วก้าว 1)")
    if lad.estimate() is None:
        errors.append("ladder: estimate ต้องมีค่าเมื่อมีดวลที่ตัดสินแล้ว")
    lad = duel.Ladder(15, prior=duel.even_prior(15))
    if (lad.record(True), lad.record(False)) != (16, 15):
        errors.append("ladder: สายที่เคยกลับทิศแล้ว (prior) ต้องก้าว 1 ขั้นตั้งแต่ดวลแรก")
    top = duel.Ladder(duel.LADDER_MAX)
    top.record(True)
    bot = duel.Ladder(duel.LADDER_MIN)
    bot.record(False)
    if top.cur != duel.LADDER_MAX or bot.cur != duel.LADDER_MIN or top.estimate() != duel.TOP or bot.estimate() != 0:
        errors.append(f"ladder: ปลายบันได/ค่าที่รายงานผิด ({top.cur}/{top.estimate()} , {bot.cur}/{bot.estimate()})")
    # ── 5b) "นิ่ง" = แม่นพอ: θ̂ (ML, ความชัน LADDER_BETA) จาก LADDER_WINDOW ดวลล่าสุดของสายข้ามรอบ มี SE ≤ LADDER_SE
    #        หรือชนปลายตาราง PIN_N ดวลติดทั้งที่ θ̂ อยู่นอกตาราง ; ดวลเดียวบอกได้น้อย → รอบแรก ๆ ยังไม่นิ่ง ──
    lad = duel.Ladder()
    for w in (True, True, False, True, False, True, False, False):
        lad.record(w)                                        # กลับทิศแล้ว แต่ 8 ดวล SE ~6 ขั้น
    nd = lad.need()
    if lad.settled() or lad.unbracketed() is not None or not isinstance(nd, int) or not 80 <= nd <= duel.LADDER_WINDOW:
        errors.append(f"ladder: 8 ดวลแรกยังไม่นิ่ง ต้องบอกดวลที่ขาด ~90 ({lad.settled()}, {nd})")
    even = duel.Ladder(12, prior=duel.even_prior(12))       # ชนะครึ่งหนึ่งที่ Plat I 120 ดวล = นิ่งที่ Plat I
    even.record(True)
    if not even.settled() or even.estimate() != 12 or even.need() != 0 or even.spread() != 2:
        errors.append(f"ladder: สายที่มีข้อมูลพอต้องนิ่งที่ระดับชนะ 50% ({even.estimate()}, SE {even.se():.2f})")
    mix = duel.Ladder(16, prior=duel.even_prior(12, 60) + duel.even_prior(18, 60))
    mix.record(True)
    if mix.estimate() != 15:
        errors.append(f"ladder: ML ต้องรวมผลทุกระดับ (ครึ่ง ๆ ที่ Plat I + ครึ่ง ๆ ที่ Asc I = Diamond I) ได้ {mix.estimate()}")
    lose = duel.Ladder()
    for _ in range(3):
        lose.record(False)                                   # 9 → 7 → 5 → 3 : แพ้รวด
    if lose.settled() or lose.unbracketed() != -1 or lose.need() is not None or lose.step != 2:
        errors.append(f"ladder: แพ้รวดยังไม่นิ่ง/ยังหาระดับ ก้าว 2 ({lose.settled()}, {lose.need()})")
    nxt = duel.Ladder(lose.cur, prior=lose.window())          # รอบหน้า: ยังก้าว 2 ; ชนะดวลแรก = กลับทิศข้ามรอบ
    if nxt.step != 2:
        errors.append("ladder: รอบต่อจากสายที่ยังไม่กลับทิศต้องก้าว 2 ต่อ")
    nxt.record(True)
    if nxt.step != 1 or nxt.unbracketed() is not None:
        errors.append("ladder: กลับทิศข้ามรอบต้องจับได้ (ก้าว 1)")
    pin = duel.Ladder(duel.LADDER_MIN + 1, prior=[(9, False), (7, False), (5, False), (3, False), (1, False)])
    for _ in range(2):
        pin.record(False)                                    # ไม่ยิงเลย: แพ้ที่ −1, −2 = ชนปลายล่าง 2 ดวลติด
    if not (pin.settled() and pin.was_pinned) or pin.estimate() != 0:
        errors.append(f"ladder: ชนปลายล่างต้องนิ่งที่ Iron I ({pin.trials}, θ̂ {pin.theta()})")
    pin.record(True)                                         # verify3: ชนะบอท −2 หนึ่งดวลหลังชนปลาย — รอบนี้ยังนิ่ง
    if not pin.settled() or pin.estimate() != 0:
        errors.append("ladder: รอบที่ชนปลายแล้วต้องนิ่งจนจบรอบ (ชนะดวลเดียวไม่ทำให้แรงค์หาย)")
    mid = duel.Ladder(duel.TOP, prior=duel.even_prior(15))    # คน Diamond I ชนะบอท Radiant สองดวล ≠ ชนปลาย
    mid.record(True)
    mid.record(True)
    if mid.was_pinned or mid.estimate() > 17:
        errors.append(f"ladder: ชนะบอท Radiant สองดวลของคนกลางตารางไม่ใช่ 'เลยปลาย' ({mid.estimate()})")
    g = _FakeGame("vandal", "duel")
    for _ in range(3):
        g.gun_ladder.record(True)                            # รอบแรกชนะรวด 3 ดวล — ไม่มี tier_i แต่มี tier_tr/tier_end
    ent = g.gun_fill_entry({})
    if "tier_i" in ent or ent.get("tier_n") != 3 or ent.get("tier_end") != duel.LADDER_START + 6 \
            or ent.get("tier_tr") != [[duel.LADDER_START, 1], [duel.LADDER_START + 2, 1], [duel.LADDER_START + 4, 1]]:
        errors.append(f"entry: สายที่ยังไม่นิ่งห้ามมี tier_i ต้องมี tier_tr/tier_end ({ent})")
    hist = [dict(ent, mode="gun", variant="vandal", drill="duel")]
    res = duel.ladder_resume(hist, "vandal", lambda e: True)
    if res != (duel.LADDER_START + 6, [(duel.LADDER_START, True), (duel.LADDER_START + 2, True),
                                       (duel.LADDER_START + 4, True)]):
        errors.append(f"ladder_resume: ต้องคืน tier_end + ดวลของรอบก่อนให้รอบหน้า ({res})")
    more = [{"mode": "gun", "variant": "vandal", "tier_end": 12, "tier_tr": [[k % 20, k % 2] for k in range(80)]},
            {"mode": "gun", "variant": "vandal", "tier_end": 11, "tier_tr": [[11, 0]] * 50}]
    st, pr = duel.ladder_resume(hist + more, "vandal", lambda e: True)
    if st != 11 or len(pr) != duel.LADDER_WINDOW or pr[-50:] != [(11, False)] * 50 or pr[0] != (duel.clamp_step(10), False):
        errors.append(f"ladder_resume: ต้องต่อดวลย้อนหลังหลายรอบจนครบหน้าต่าง ({st}, {len(pr)}, {pr[:2]})")
    st, pr = duel.ladder_resume(hist + [{"mode": "gun", "variant": "vandal", "tier_end": 12}] + more[1:], "vandal",
                                lambda e: True)
    if (st, len(pr)) != (11, 50):
        errors.append(f"ladder_resume: รอบที่ไม่มี tier_tr ต้องตัดสายไว้แค่นั้น ({st}, {len(pr)})")
    # ── 6) ในเกม: ฆ่าบอท = บันไดขึ้น, ตาย = ลง, บอทถอย = ไม่นับ ; entry duel มี tier_i/tier_n/tier_end/tier_tr ──
    g = _FakeGame("vandal", "duel")
    g.gun_ladder = duel.Ladder(12, prior=duel.even_prior(12))
    b = g.gun_spawn()
    b.take(999, "head")
    g.gun_on_kill(b, "head", 15.0)
    b = g.gun_spawn()
    g.gun_player_hit(999, True)
    g.gun_respawn_at = None
    b = g.gun_spawn()
    b.meta["phase"] = "retreat"
    b.x = b.meta["x_hide"]
    b.meta["los_t0"] = g.gt
    g.gun_cover_ai(b, 1.0 / 60)
    if [t for t, _ in g.gun_ladder.trials] != [12, 13] or g.gun_ladder.cur != 12 or \
            [r for _t, r in g.gun_duel_log] != ["win", "loss", "nc"]:
        errors.append(f"ladder in-game: ชนะ/แพ้/ถอย ต้องได้ 12→13→12 และ log win/loss/nc "
                      f"(trials {g.gun_ladder.trials} log {g.gun_duel_log})")
    ent = g.gun_fill_entry({})
    if not (ent.get("tier_i") == 12 and ent.get("tier_n") == 2 and ent.get("tier_end") == 12
            and ent.get("tier_tr") == [[12, 1], [13, 0]] and "tier_bot" not in ent):
        errors.append(f"entry: duel ต้องมี tier_i/tier_n/tier_end/tier_tr ({ent})")
    for wp, drill in (("operator", "duel"), ("vandal", "hold"), ("vandal", "quick"), ("sheriff", "repo")):
        g = _FakeGame(wp, drill)
        ent = g.gun_fill_entry({})
        if "tier_i" in ent or "tier_n" in ent or not isinstance(ent.get("tier_bot"), int):
            errors.append(f"entry: {wp}/{drill} ไม่จัดแรงค์ — ห้ามมี tier_i (ได้ {ent})")
    g = _FakeGame("vandal", "duel")
    ent = g.gun_fill_entry({})
    if "tier_i" in ent or "tier_end" in ent:
        errors.append(f"entry: บันไดใหม่ที่ยังไม่มีดวลตัดสิน ห้ามบันทึก tier_i/tier_end ({ent})")
    # ── 7) บอทเดินฟิสิกส์เดียวกับผู้เล่น: ไม่เร็วเกินความเร็ววิ่ง, ยิงตอนเร็วเกิน deadzone เฉพาะตัว "วิ่งยิง" ──
    shots, over = [], []
    for k in range(60):
        random.seed(9100 + k)
        g = _FakeGame("vandal", "duel")
        g.gun_ladder = None
        g.gun_fixed_tier = 10
        b = g.gun_spawn()
        fire0 = g.gun_bot_fire

        def spy(bb, _f=fire0):
            shots.append((bb.speed(), bb.meta["run_shoot"], guns.is_accurate(bb.weapon, bb.speed())))
            _f(bb)
        g.gun_bot_fire = spy
        while g.gt < 6.0 and not g.gun_deaths and b.alive:
            g.gun_hp = 10 ** 6
            g.step(1.0 / 144)
            if b.speed() > WEAPONS[b.weapon]["run_speed"] + 1e-6:
                over.append(b.speed())
    bad = [s for s in shots if not s[1] and not s[2]]
    if not shots or bad or over:
        errors.append(f"bots: ยิงตอนยังเร็วเกิน deadzone ทั้งที่ไม่ใช่ตัววิ่งยิง {len(bad)}/{len(shots)} นัด ; "
                      f"เร็วเกินวิ่ง {len(over)} เฟรม")
    # ── 8) ดาเมจตามระยะของปืนบอท: Phantom โดนตัวที่ 25 ม. = 35 (ช่วง 20–50 ม.) ไม่ใช่ 39 ──
    g = _FakeGame("phantom", "duel")
    b = _v2_bot(g, 0.0, g.cam.pos[2] + 25.0, tier=22)
    b.meta["p"] = dict(b.meta["p"], sigma=0.0, lag=0.0, comp=1.0)
    b.meta["aim_head"] = False
    g.gun_track_player()
    got = []
    g.gun_player_hit = lambda dmg, head: got.append(dmg)
    for _ in range(4):
        g.gt += 0.6
        g.gun_bot_fire(b)
    if not got or any(d != guns.damage_for("phantom", "body", 25.0) for d in got):
        errors.append(f"bots: Phantom ยิงตัวที่ 25 ม. ต้องได้ดาเมจช่วงไกล {guns.damage_for('phantom', 'body', 25.0)} (ได้ {got})")
    return errors


def _selftest_angle():
    """ANGLE HOLD: ฉาก 2–4 ขอบ (3 แบบ) · บอทซ่อนแล้วมองไม่เห็น · วัดองศาคลาด ณ เฟรมแรกที่หัวโผล่ (เทียบหัวระดับยืน รวม
    ยกพื้น) · คะแนนวางเป้า × รอด · entry มี tier_i/pa_* ; Op ไม่จัดแรงค์"""
    from . import arena
    from .gundrills import ANGLE_PTS
    errors = []
    g = _FakeGame("vandal", "angle")
    names = {}
    for _ in range(300):
        name, boxes, spots = g.angle_layout()
        names[name] = names.get(name, 0) + 1
        want = {"door": 2, "door_crate": 4, "ledge": 2}[name]
        if len(spots) != want or not all(-ROOM_X <= sp["x_hide"] <= ROOM_X for sp in spots):
            errors.append(f"angle: ฉาก {name} มี {len(spots)} ขอบ (ต้อง {want}) / จุดซ่อนนอกห้อง")
            break
        if name == "ledge" and not (any(sp["y0"] >= 0.5 for sp in spots) and any(bx.ledge for bx in boxes)):
            errors.append("angle: ฉากยกพื้นต้องมีจุดโผล่สูง ≥ 0.5 ม. และกล่อง ledge")
            break
    if set(names) != {"door", "door_crate", "ledge"}:
        errors.append(f"angle: ต้องสุ่มได้ครบ 3 แบบฉาก (ได้ {names})")
    eye = (g.cam.pos[0], g.cam.pos[1], g.cam.pos[2])
    seen_early = 0
    for _ in range(200):
        g.bots = []
        b = g.gun_spawn()
        if arena.any_visible(eye, b.points(), g.gun_covers):
            seen_early += 1
        d = math.hypot(b.x - g.cam.pos[0], b.z - g.cam.pos[2])
        if not (6.9 <= d <= 31.7):           # p10–p90 ของระยะคิล Vandal จริง (กล่องหน้าประตูใกล้กว่าประตู 3–5.5 ม.)
            errors.append(f"angle: ระยะบอท {d:.1f} ม. นอกช่วงไฟต์จริง")
            break
    if seen_early:
        errors.append(f"angle: บอทที่ยังซ่อนมองเห็นได้ {seen_early}/200 ดวล (ต้องซ่อนหลังขอบจริง)")
    # วัดองศาคลาด: วางหัวบอทไว้ในที่โล่ง แล้วเล็งห่างหัวระดับยืน (+1.0° ขวา, −0.5° ต่ำ) → exp = (1.0, −0.5) ;
    # บอทหมอบ/ยืนบนยกพื้น: เทียบหัว "ระดับยืน" ของจุดนั้น (รวม y0) ไม่ใช่หัวที่หมอบอยู่
    for crouch, y0 in ((0.0, 0.0), (1.0, 0.0), (0.0, 0.8)):
        g = _FakeGame("vandal", "angle")
        g.gun_set_covers([])
        b = g.gun_new_bot(0.0, g.cam.pos[2] + 17.0, 16)
        b.crouch = b.crouch_to = crouch
        b.y0 = y0
        b.meta.update(kind="stop", side=1, edge=0.5, dir=-1, x_hide=1.5, x_to=0.0, phase="fight", t_go=0.0)
        g.bots = [b]
        g.gun_start_duel(b)
        g.aim_world(b.x, guns.HEAD_Y + y0, b.z)
        g.cam.yaw -= math.radians(1.0)
        g.cam.pitch -= math.radians(0.5)
        g.gun_drill_frame()
        ex = g.gun_duel.get("exp")
        if ex is None or abs(ex[0] - 1.0) > 0.02 or abs(ex[1] + 0.5) > 0.02:
            errors.append(f"angle: วัดคลาด (crouch {crouch}, y0 {y0}) ได้ {ex} (ต้อง 1.0, −0.5)")
    # คะแนน: รอดดวล = ANGLE_PTS × คุณภาพ (≤0.5° เต็ม, 2.75° ครึ่ง, ≥5° ศูนย์) ; ตายในดวลนั้น = ไม่ได้
    for err, res, want in ((0.3, "win", ANGLE_PTS), (2.75, "nc", ANGLE_PTS // 2), (6.0, "win", 0), (0.3, "loss", 0)):
        g = _FakeGame("vandal", "angle")
        g.gun_ladder = None
        b = g.gun_new_bot(0.0, g.cam.pos[2] + 15.0, 16)
        g.bots = [b]
        g.gun_start_duel(b)
        g.gun_duel.update(exp=(err, 0.0), exp_t=g.gt)
        s0 = g.score
        g.gun_duel_end(res)
        if g.score - s0 != want:
            errors.append(f"angle: คะแนนวางเป้า คลาด {err}° ผล {res} ได้ {g.score - s0} (ต้อง {want})")
    # รอบจริงสั้น ๆ ด้วยคนเล็งหัวทันทีที่เห็น (ยิงเมื่อหัวพ้นขอบ) → entry มี tier_i + pa_* ; Op = tier_bot
    for wp, ranked in (("vandal", True), ("operator", False)):
        random.seed(4242)
        g = _FakeGame(wp, "angle")
        if g.gun_ladder is not None:
            # สายที่นิ่งแล้ว (ต่อจากประวัติ) — สายใหม่ชนะรวด 8 ดวลยังไม่นิ่ง = ไม่มี tier_i (เทสบันไดอยู่ข้อ 5 ของ bots v2)
            g.gun_ladder = duel.Ladder(g.gun_ladder.cur, prior=duel.even_prior(g.gun_ladder.cur))
        g.gun_next_bot_at = 0.0
        while g.gt < 25.0:
            live = [bb for bb in g.bots if bb.alive and bb.exposed]
            if live:
                bb = live[0]
                g.aim_world(bb.x, bb.head_y(), bb.z)
                if wp == "operator" and g.gun_zoom == 1.0:
                    g.gun_rmb(True)
                if not arena.segment_blocked(tuple(g.cam.pos), (bb.x, bb.head_y(), bb.z), g.gun_covers):
                    g.gun_shoot()
            g.step(1.0 / 144)
        ent = g.gun_fill_entry({})
        if ("tier_i" in ent) != ranked or not ent.get("pa_n") or "pa_err" not in ent or "pa_v" not in ent:
            errors.append(f"angle {wp}: entry ต้องมี pa_* {'และ tier_i' if ranked else 'ไม่มี tier_i'} ({ent})")
    return errors


def _selftest_peek():
    """PEEK & STOP: เริ่มหลังกำแพง (มองไม่เห็นกันทั้งสองฝั่ง) · นาฬิกาบอทเริ่มเมื่อ "หัวเรา" พ้นขอบ (ไหล่ยังไม่นับ) +
    peeker's advantage ของเรา · หยุดถึงยิง / ยิงตอนเดิน วัดถูก · entry มี tier_i + pk_*"""
    from . import arena
    from .gundrills import PEEK_DIST
    errors = []
    g = _FakeGame("vandal", "peek")
    for _ in range(300):
        L = g.peek_layout()
        eye0 = (L["xc"], EYE_Y, g.gun_origin[2])
        beye = (L["bx"], EYE_Y, L["bz"])
        if (arena.any_visible(eye0, guns.humanoid_points(L["bx"], L["bz"]), [L["wall"]])
                or arena.any_visible(beye, guns.head_points(L["xc"], g.gun_origin[2]), [L["wall"]])):
            errors.append(f"peek: ตอนเริ่มมองเห็นกันแล้ว ({L})")
            break
        if not (PEEK_DIST[0] - 0.5 <= L["d"] <= PEEK_DIST[1] + 0.5):
            errors.append(f"peek: ระยะบอท {L['d']:.1f} ม. นอกช่วง")
            break
    # spawn: ย้ายเรากลับหลังกำแพงใหม่ ความเร็ว 0
    g.cam.pos[0], g.vel = 2.5, [5.0, 0.0]
    b = g.gun_spawn()
    L = b.meta["peek"]
    if abs(g.cam.pos[0] - L["xc"]) > 1e-9 or g.vel != [0.0, 0.0] or not b.meta.get("holder"):
        errors.append("peek: เริ่มดวลต้องย้ายเรากลับจุดเริ่มหลังกำแพง ความเร็ว 0")
    # นาฬิกาบอท: ขยับออกทีละ 1 ซม. — ช่วงที่เห็นไหล่แต่ยังไม่เห็นหัว บอทต้องยังไม่เริ่มนับ ; หัวพ้นขอบ = los + fire_at
    s = L["side"]
    g.vel = [s * 5.4, 0.0]
    shoulder_only = 0
    for _ in range(400):
        g.cam.pos[0] += s * 0.01
        g.gt += 0.001
        g.gun_bot_los(b)
        head = arena.any_visible(b.eye(), guns.head_points(g.cam.pos[0], g.cam.pos[2]), g.gun_covers)
        body = arena.any_visible(b.eye(), guns.humanoid_points(g.cam.pos[0], g.cam.pos[2]), g.gun_covers)
        if body and not head:
            shoulder_only += 1
            if b.meta["los"]:
                errors.append("peek: บอทเริ่มนับตั้งแต่เห็นไหล่ (ต้องรอหัวพ้นขอบ)")
                break
        if head:
            want = b.meta["p"]["rt"] + duel.PEEK_ADV
            if not b.meta["los"] or abs(b.meta["fire_at"] - g.gt - want) > 1e-9:
                errors.append(f"peek: หัวพ้นขอบแล้วนาฬิกาบอทต้องเริ่ม rt+PA ({b.meta['fire_at']} vs {g.gt + want})")
            break
    if not shoulder_only:
        errors.append("peek: ไม่เคยมีช่วงที่เห็นแค่ไหล่ (จุดตัวอย่างหัว/ไหล่ผิด)")
    # หยุดถึงยิง: วิ่งออกจนหัวพ้นขอบ → ปล่อยปุ่ม → นิ่งใน deadzone แล้วรอ 6 เฟรม (41.7 ms) → ยิง ; อีกดวลยิงตอนวิ่ง
    for mode in ("stop", "run"):
        random.seed(777)
        g = _FakeGame("vandal", "peek")
        # สายที่นิ่งแล้ว — ดวลเดียวของสายใหม่ยังไม่นิ่ง (ไม่มี tier_i)
        g.gun_ladder = duel.Ladder(g.gun_ladder.cur, prior=duel.even_prior(g.gun_ladder.cur))
        b = g.gun_spawn()
        key = g.gun_peek_key()
        g.cam.yaw = 0.0
        waited = None
        shot = False
        for _ in range(144 * 4):
            g.gun_hp = 10 ** 6
            if not b.meta["los"]:
                g.keys_down = {key}
            elif mode == "run":
                g.gun_next_shot_at = 0.0
                g.gun_shoot()
                shot = True
            else:
                g.keys_down = set()
                if guns.is_accurate("vandal", g.gun_speed()):
                    waited = 0 if waited is None else waited + 1
                    if waited == 6:
                        g.gun_next_shot_at = 0.0
                        g.gun_shoot()
                        shot = True
            if shot:
                break
            g.step(1.0 / 144)
        if not shot:
            errors.append(f"peek {mode}: ไม่ได้ยิงเลย (โผล่ไม่ถึงบอท)")
            continue
        if g.gun_duel and not g.gun_duel["done"]:
            g.gun_duel_end("win")
        ent = g.gun_fill_entry({})
        if mode == "stop" and (ent.get("stop_n") != 1 or not 35 <= ent.get("stop_ms", -1) <= 50
                               or ent.get("mv_first") != 0):
            errors.append(f"peek: หยุด 6 เฟรมแล้วยิง ต้องได้ stop_ms ~42 และไม่ใช่นัดตอนเดิน ({ent})")
        if mode == "run" and (ent.get("mv_first") != 1 or "stop_ms" in ent or "expo_ms" not in ent):
            errors.append(f"peek: ยิงตอนวิ่งต้องนับ mv_first และมี expo_ms ({ent})")
        if "tier_i" not in ent or ent.get("pk_w") != 1:
            errors.append(f"peek: entry ต้องมี tier_i และ pk_w ({ent})")
    return errors


def _selftest_tap():
    """TAP @ RANGE: ระยะ 20–35 ม. (ยืนถอย 3 ม.) · บอทไม่ยิงสวน · นับนัดยิงก่อนสเปรดหาย/ชุด/จังหวะแตะ/ช่วงระยะ"""
    from .gundrills import TAP_BACK
    errors = []
    g = _FakeGame("vandal", "tap")
    if abs(g.gun_origin[2] - (GUN_ORIGIN_Z - TAP_BACK)) > 1e-9:
        errors.append("tap: ต้องยืนถอยหลังเพิ่ม TAP_BACK")
    ds = []
    for _ in range(400):
        g.bots = []
        b = g.gun_spawn()
        ds.append(math.hypot(b.meta["edge"] - g.cam.pos[0], b.z - g.cam.pos[2]))
    ds.sort()
    if ds[0] < 19.0 or ds[-1] > 36.0 or not 25.0 <= ds[len(ds) // 2] <= 30.0:
        errors.append(f"tap: ระยะ {ds[0]:.1f}–{ds[-1]:.1f} กลาง {ds[len(ds) // 2]:.1f} (ต้อง 20–35)")
    # ยืนนิ่งไม่ยิง 20 วิ: ไม่โดนยิงเลย (บอทเป้าซ้อม) และบอทถอยไปเองตามช่วงโผล่
    random.seed(55)
    g = _FakeGame("vandal", "tap")
    g.gun_next_bot_at = 0.0
    while g.gt < 20.0:
        g.step(1.0 / 60)
    if g.gun_dmg_taken or g.gun_deaths or [r for _t, r in g.gun_duel_log].count("nc") < 3:
        errors.append(f"tap: บอทต้องไม่ยิง และถอยเองเมื่อหมดช่วงโผล่ (dmg {g.gun_dmg_taken} log {g.gun_duel_log})")

    def fire(gap, n, weapon="vandal"):
        gg = _FakeGame(weapon, "tap")
        gg.step(1.0 / 144)
        for _ in range(n):
            gg.gun_next_shot_at = 0.0
            gg.gun_shoot()
            steps = int(round(gap * 144))
            for _s in range(max(1, steps)):
                gg.step(1.0 / 144)
        return gg.gun_fill_entry({})
    held = fire(1.0 / 9.75, 10)
    slow = fire(0.30, 8)
    fast = fire(0.18, 8)
    sher = fire(0.55, 5, "sheriff")
    if held.get("spam", 0) < 8 or held.get("bursts") != [0, 0, 0, 1]:
        errors.append(f"tap: กดค้าง 10 นัด = ยิงก่อนสเปรดหาย ≥ 8 และเป็นชุดเดียว 4+ ({held})")
    if slow.get("spam") != 0 or slow.get("tap_fast") != 0 or slow.get("bursts") != [8, 0, 0, 0]:
        errors.append(f"tap: แตะทุก 0.30 วิ (Vandal 4/วิ) ต้องไม่มียิงก่อนสเปรดหาย/แตะเร็วเกิน ({slow})")
    if not fast.get("spam") or fast.get("tap_fast") != fast.get("tap_gaps"):
        errors.append(f"tap: แตะทุก 0.18 วิ ต้องนับยิงก่อนสเปรดหาย + แตะเร็วเกินทุกช่วง ({fast})")
    if sher.get("spam") != 0 or sher.get("tap_fast") != 0:
        errors.append(f"tap: Sheriff แตะทุก 0.55 วิ (2/วิ) ต้องสะอาด ({sher})")
    # ช่วงระยะ: ยิงหัวบอทนิ่งที่ 22 / 27 / 32 ม. → นับลงช่อง 20 / 25 / 30 และหัวโดน
    g = _FakeGame("vandal", "tap")
    g.step(1.0 / 144)
    for dist, key in ((22.0, "20"), (27.0, "25"), (32.0, "30")):
        b = Bot(0.0, g.cam.pos[2] + dist)
        g.bots = [b]
        g.gun_start_duel(b)
        g.aim_world(b.x, b.head_y(), b.z)
        g.gun_stab.reset()
        g.gun_next_shot_at = 0.0
        g.gt += 1.0
        g.gun_shoot()
        if g.gun_tap["band"][key] != [1, 1]:
            errors.append(f"tap: นัดหัวที่ {dist} ม. ต้องลงช่อง {key} ({g.gun_tap['band']})")
    if drills_for("operator").count("tap") or drills_for("ghost").count("tap"):
        errors.append("tap: Op/Ghost ต้องไม่มีดริล TAP")
    return errors


def _selftest_adad():
    """STRAFING HEADS: บอทยิงเฉพาะตอนหยุดนิ่ง (นัดแรกหลังหยุด = rt ของระดับ) · ส่ายไม่เกินความเร็ววิ่ง · แยกโดนตอนเดิน/หยุด"""
    errors = []
    shots, bad, starts = [], [], []
    for k in range(20):
        random.seed(8800 + k)
        g = _FakeGame("vandal", "adad")
        g.gun_ladder = None
        g.gun_fixed_tier = 16
        b = g.gun_spawn()
        fire0 = g.gun_bot_fire

        def spy(bb, _f=fire0, _g=g):
            m = bb.meta
            shots.append(m["adad"])
            if m["adad"] != "stop" or not guns.is_accurate(bb.weapon, bb.speed()):
                bad.append((m["adad"], bb.speed()))
            if m.get("stop_t") is not None and m.get("_first_for") != m["stop_t"]:
                m["_first_for"] = m["stop_t"]
                starts.append(_g.gt - m["stop_t"] - m["p"]["rt"])
            _f(bb)
        g.gun_bot_fire = spy
        while g.gt < 8.0 and b.alive and not g.gun_deaths:
            g.gun_hp = 10 ** 6
            g.step(1.0 / 144)
            if b.speed() > WEAPONS[b.weapon]["run_speed"] + 1e-6:
                bad.append(("speed", b.speed()))
    if not shots or bad:
        errors.append(f"adad: บอทยิงนอกช่วงหยุดนิ่ง/เร็วเกินวิ่ง {bad[:3]} (ยิง {len(shots)} นัด)")
    if not starts or max(abs(x) for x in starts) > 1.0 / 144 + 1e-9:
        errors.append(f"adad: นัดแรกหลังหยุดต้องเท่า rt ของระดับ (คลาด {max(starts) if starts else None})")
    # โดนตอนบอทเดิน vs หยุด: คนเล็งหัวสมบูรณ์ (Sheriff นัดเดียวจบ) ยิงตัวคี่ตอนมันส่าย ตัวคู่รอจังหวะหยุด —
    # ต้องมีทั้งสองกอง และคิลทุกตัวถูกจัดเข้ากองตามจังหวะที่ตาย
    random.seed(9900)
    g = _FakeGame("sheriff", "adad")
    g.gun_next_bot_at = 0.0
    g.gun_ladder = None
    g.gun_fixed_tier = 10
    last = -1.0
    while g.gt < 30.0:
        g.gun_hp = 10 ** 6
        live = [bb for bb in g.bots if bb.alive and bb.exposed]
        if live and g.gt - last >= 0.5:
            bb = live[0]
            if (bb.meta.get("adad") == "stop") == (g.gun_kills % 2 == 0):
                g.aim_world(bb.x, bb.head_y(), bb.z)
                g.gun_shoot()
                last = g.gt
        g.step(1.0 / 144)
    ent = g.gun_fill_entry({})
    if not ent.get("hit_mv", [0])[0] or not ent.get("hit_st", [0])[0] or \
            ent.get("kill_stop_n", 0) + ent.get("kill_mv_n", 0) != g.gun_kills:
        errors.append(f"adad: ต้องแยกนัดตอนบอทเดิน/หยุด และคิลทุกตัวอยู่ในกองใดกองหนึ่ง ({ent}, kills {g.gun_kills})")
    return errors


def _selftest_drills():
    errors = []
    for fn in (_selftest_angle, _selftest_peek, _selftest_tap, _selftest_adad):
        try:
            errors += fn()
        except Exception as ex:
            import traceback
            errors.append(f"{fn.__name__}: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    return errors


def selftest():
    """คืน list ข้อผิดพลาด (ว่าง = ผ่าน) — 4 เคสจากรีวิว 11 ก.ย. 2026:
    fire rate ไม่ขึ้นกับ FPS · ไม่มียิงตามเก็บหลังเกมค้าง · REPOSITION ยึด anchor นัดแรก · กำแพง hold บังกระสุน
    + ปืนสั้น Ghost/Classic และบอทหมอบ (2026-09-24) + บอท v2/บันไดแรงค์ (_selftest_bots_v2)
    + ดริลชุดสมจริง ANGLE / PEEK / TAP / ADAD (_selftest_drills)"""
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
        errors += _selftest_sidearms()
        errors += _selftest_bot_crouch()
        errors += _selftest_bots_v2()
        errors += _selftest_drills()        # ANGLE / PEEK / TAP / ADAD (lane C5)
    except Exception as ex:
        errors.append(f"gunplay selftest: {type(ex).__name__}: {ex}")
    finally:
        random.setstate(rng_state)
    return errors
