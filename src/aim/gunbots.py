# -*- coding: utf-8 -*-
"""บอท GUNFIGHT v2 — BotAIMixin ของ GunMixin (pure logic ไม่มี pygame: tools/duel_sim.py ขับ headless ได้)

ของเดิม (ถึง gun rev 4): บอทเกิดกลางที่โล่ง ยิงสวนแบบ "โยนเหรียญ" 35% ทุก 0.45 วิหลัง 0.35–0.60 วิ ไม่สนแนวสายตา/
ระยะ/การเคลื่อนที่ของตัวเอง → ยืนนิ่งไม่ยิงเลยยังรอดได้ค่ากลาง 3.18 วิ และ HP ติดข้ามบอท (phase-1 trainer-realism B5)
ตอนนี้ (gun rev 5):
  • ที่กำบัง — ดวลทุกตัวใน duel/quick/repo มี "มุมกำแพง" (arena.Box ยาวถึงผนังห้องฝั่งหนึ่ง) บอทแอบหลังกำแพง
    แล้วโผล่จากขอบ ท่าโผล่ (BEHAVIORS): hold ยืนเฝ้ามุมอยู่แล้ว · swing วิ่งออกกว้างเต็มสปีด · stop โผล่แล้ว
    counter-strafe ยิง · jiggle โผล่ไหล่หลอก 1–2 ครั้งแล้วค่อยออกจริง · crouch หมอบโผล่ · strafe ออกมาส่าย ADAD
    ยิงตอนความเร็วเข้า deadzone ; + หมอบตอนเริ่มยิงนัดแรก (crouch_fire / BOT_CROUCH_P) ได้ทุกท่ายกเว้นหมอบโผล่
  • เดินด้วยฟิสิกส์เดียวกับผู้เล่น (movement.step เร่ง/เบรก/counter-strafe) → ความแม่นขณะเคลื่อนที่ตาม deadzone จริง
  • ยิงแบบมีเหตุผล: นัดแรก = ตอนบอทเริ่มเห็นเรา + rt(ระดับ) ∓ PEEK_ADV (บอทเป็นฝ่าย peek หัก / เราวิ่งเข้าหาบอทที่
    ยืนเฝ้า บวก) ; คลาด N(0, σ) ต่อแกนที่หดลงตามเวลา + สเปรด/รีคอยล์ Stability ของปืนบอท (ดึงสวน comp) + โทษ
    เคลื่อนที่ ; กระสุนเป็นรังสีจริงจากตาบอท → ที่กำบังขวาง = ไม่โดน, โดน hitbox ผู้เล่น (หมอบ = หัวต่ำลง)
    ดาเมจตามโซน/ระยะของปืนบอท (guns.damage_for) ; บอทเล็งตำแหน่งเราเมื่อ lag วิก่อน (ส่าย ADAD หลบได้จริง)
  • HP/เกราะผู้เล่นรีเซ็ตทุกดวล (ดวล = บอทหนึ่งตัว) ; ผลดวล ชนะ/แพ้/ไม่นับ → บันไดแรงค์ duel.Ladder (ดริล duel)
ตัวเลขฝีมือบอทต่อระดับอยู่ duel.py (ฟิตด้วย tools/duel_sim.py)"""
import itertools
import math
import random

from .config import ROOM_H, ROOM_X, WALL_Z, mode_current
from . import arena, duel, guns, movement
from .guns import WEAPONS, Bot
from .stability import Stability, cone_offset, patched_block

# เลขเวอร์ชันชุดกล่องไม่ซ้ำตลอดโปรเซส (ไม่รีเซ็ตต่อรอบ) — glrender เทียบเลขนี้เพื่อสร้าง VBO ใหม่ ; ถ้านับใหม่ทุกรอบ
# รอบถัดไปอาจได้เลขซ้ำกับชุดเก่าที่ต่างกัน แล้ว GPU วาดกำแพงค้างของรอบก่อน
_COVER_SEQ = itertools.count(1)

# ท่าโผล่ + น้ำหนักสุ่ม (ค่าประมาณจากนิสัยที่เจอในแรงค์กลาง-บน — ไม่มีข้อมูลท่าจาก API ; sim ใช้ชุดเดียวกัน)
BEHAVIORS = (("hold", 0.15), ("swing", 0.25), ("stop", 0.25), ("jiggle", 0.15), ("crouch", 0.10), ("strafe", 0.10))
BEHAVIOR_TH = {"hold": "เฝ้ามุม", "swing": "วิ่งออกกว้าง", "stop": "โผล่หยุดยิง", "jiggle": "จิ้มหลอก",
               "crouch": "หมอบโผล่", "strafe": "ส่าย ADAD"}
# หมอบตอนเริ่มยิงนัดแรก (crouch on first bullets — นิสัยที่เจอบ่อยตั้งแต่ Diamond) และช่วงที่หมอบค้างก่อนลุก (วิ)
# ค่าประมาณ ไม่มีข้อมูลวัดจากแมตช์ (API ไม่บอกท่าของผู้ยิง) ; 0 = ปิดพฤติกรรมนี้
BOT_CROUCH_P = 0.35
BOT_CROUCH_HOLD = (0.5, 1.1)
# มุมกำแพง: หนา COVER_T สูง COVER_H (สูงกว่าตา = มองข้ามไม่ได้) บอทยืนหลังผิวด้านหลัง COVER_BACK ม.
COVER_T, COVER_H, COVER_BACK = 0.6, 3.0, 0.45
EDGE_OUT = 0.8          # ขอบกำแพงอยู่เลยจุดยืนดวล (x ที่สุ่มตามระยะ) ไปทางผนังเท่านี้ — ท่า stop จบใกล้จุดนั้นพอดี
HIDE_IN = guns.BODY_HW + 0.8   # จุดแอบ: ศูนย์ตัวลึกจากขอบเท่านี้ (ไหล่ไม่โผล่แม้ผู้เล่นยืนเยื้องสุดโซนที่ระยะ ≥ 4 ม.)
# ระยะที่ตัวบอทออกพ้นขอบ (ม.) ต่อท่า — jiggle = แค่ไหล่
OUT = {"hold": (0.35, 0.55), "stop": (0.6, 0.95), "crouch": (0.6, 0.95), "swing": (1.6, 3.0),
       "strafe": (1.0, 1.8), "jiggle": (0.05, 0.25)}
STRAFE_SPAN = (0.5, 3.0)      # ส่าย ADAD ในช่วงนี้นอกขอบ
STRAFE_TURN = (0.15, 0.45)    # กลับทิศทุก ๆ (วิ)
WAIT = (0.4, 1.4)             # รอหลังกำแพงก่อนโผล่ (เดาจังหวะไม่ได้)
STOP_LEAD = 0.06              # swing: เริ่ม counter-strafe ก่อนจังหวะยิงเท่านี้ (60 ms ถึง deadzone — movement.selftest)
NEVER_SEEN = 9.0              # โผล่แล้วไม่เคยเห็นกันเลยเกินนี้ (เราหลบเงากำแพง) → บอทถอย ดวลไม่นับ
TRAIL_KEEP = 1.0              # เก็บตำแหน่งผู้เล่นย้อนหลัง (วิ) — บอทเล็งตำแหน่งเมื่อ lag วิก่อน


class BotAIMixin:
    # ───────────────────────── สถานะต่อรอบ ─────────────────────────
    def gun_bots_reset(self):
        """เรียกจาก reset_gun — สถานะบอท/ดวล/บันไดของรอบใหม่"""
        self.gun_covers = []            # arena.Box ที่มีผลตอนนี้ (กำแพงดวล หรือกำแพง OP HOLD)
        self.gun_cover_ver = 0          # เวอร์ชันชุดกล่อง (_COVER_SEQ ; 0 = ว่าง) — glrender สร้าง VBO ใหม่เมื่อเลขเปลี่ยน
        self.gun_ladder = None
        self.gun_fixed_tier = duel.LADDER_START
        self.gun_duel = None            # ดวลที่กำลังเล่น {tier, t0, done}
        self.gun_duel_log = []          # [(ระดับบอท, 'win'|'loss'|'nc')]
        self.gun_ptrail = []            # [(gt, x, z, crouch)] ตำแหน่งผู้เล่นย้อนหลัง
        self.gun_first_ms = []          # เวลาเห็นบอท → นัดแรกของเรา (ms) ต่อดวล
        self.gun_moving_shots = 0       # นัดที่เรายิงตอนเร็วเกิน deadzone

    def gun_is_ladder(self):
        """ดริลที่มีบันไดแรงค์ (duel.LADDER_DRILLS: DUEL / ANGLE / PEEK) ทุกปืนยกเว้น Op (บอท Op-ดวลถือไรเฟิล = คนละเกม
        ยังไม่สอบเทียบ)"""
        return self.gun_drill in duel.LADDER_DRILLS and self.gun_weapon != "operator"

    def gun_bot_weapon(self):
        """ปืนของบอท = ปืนเดียวกับเรา (ดวลกระจก) ยกเว้นเราถือ Op → บอทถือ Vandal (ไรเฟิล peek ใส่ Op แบบเกมจริง)"""
        return "vandal" if self.gun_weapon == "operator" else self.gun_weapon

    def gun_bots_begin(self):
        """เรียกจาก begin_gun — บันได (ดริลจัดแรงค์) หรือระดับบอทคงที่ (ดริลอื่น) + กำแพง OP HOLD เป็นกล่อง"""
        hist = (getattr(self, "data", None) or {}).get("history", [])
        if self.gun_is_ladder():
            # สายบันไดเดินต่อข้ามรอบ: เริ่มที่ tier_end รอบก่อน + ดวลของรอบก่อน ๆ (tier_tr) ในหน้าต่างประมาณแรงค์
            # (duel.ladder_resume) — แรงค์ต้องใช้ข้อมูลหลายรอบ (duel.LADDER_SE)
            start, prior = duel.ladder_resume(hist, self.gun_weapon, mode_current, self.gun_drill)
            # angle/peek ที่ยังไม่เคยเล่น: สายใหม่ (ก้าว 2) แต่เริ่มที่ระดับที่ DUEL ปืนนี้จบไว้ — สเกลเดียวกัน (DRILL_RT)
            seed = (duel.ladder_start(hist, self.gun_weapon, mode_current)
                    if start is None and self.gun_drill != "duel" else None)
            self.gun_ladder = duel.Ladder(start, seed=seed, prior=prior)
        else:
            # ดริลไม่จัดแรงค์ใช้บอทระดับที่บันไดดวลของปืนนี้ (หรือ Vandal) จบไว้ล่าสุด — ความยากตามฝีมือจริง
            st = duel.ladder_start(hist, self.gun_bot_weapon(), mode_current)
            if st is None:
                st = duel.ladder_start(hist, "vandal", mode_current)
            self.gun_fixed_tier = duel.LADDER_START if st is None else st
        if self.gun_drill == "hold":
            from .gunplay import HOLD_WALL_DZ, HOLD_GAP
            wz = self.gun_origin[2] + HOLD_WALL_DZ
            # ตรงกับกำแพงที่วาด (glrender "holdwall" / poly ใน draw_gun_world) — draw=False กันวาดซ้ำ
            self.gun_set_covers([arena.Box(-ROOM_X, -HOLD_GAP, 0.0, ROOM_H, wz, wz + 0.3, draw=False),
                                 arena.Box(HOLD_GAP, ROOM_X, 0.0, ROOM_H, wz, wz + 0.3, draw=False)])

    def gun_set_covers(self, boxes):
        self.gun_covers = list(boxes)
        self.gun_cover_ver = next(_COVER_SEQ)

    def gun_tier_now(self):
        return self.gun_ladder.cur if self.gun_ladder is not None else self.gun_fixed_tier

    # ───────────────────────── ดวล ─────────────────────────
    def gun_start_duel(self, b):
        """บอทตัวใหม่ = ดวลใหม่: HP/เกราะเราเต็ม (เดิมรีเซ็ตเฉพาะตอนเกิดใหม่ → ตายเพราะสะสมดาเมจข้ามบอท)"""
        self.gun_hp, self.gun_shield = guns.PLAYER_HP, guns.PLAYER_SHIELD
        self.gun_duel = {"tier": b.meta.get("tier", self.gun_tier_now()), "t0": self.gt, "done": False,
                         "bot": b}

    def gun_duel_end(self, result):
        """ปิดดวลปัจจุบัน — result 'win' (เราฆ่า) / 'loss' (เราตาย) / 'nc' (ไม่นับ: บอทถอย/หมดเวลา)"""
        d = self.gun_duel
        if d is None or d["done"]:
            return
        d["done"] = True
        self.gun_duel_log.append((d["tier"], result))
        self.gun_drill_duel_end(d, result)          # ตัวชี้วัดต่อดวลของดริลใหม่ (gundrills) — คะแนนวางเป้า ANGLE ฯลฯ
        lad = self.gun_ladder
        if lad is None or result == "nc":
            return
        old = lad.cur
        new = lad.record(result == "win")
        if new != old:
            verb = "ขึ้น" if new > old else "ลง"          # (ฟอนต์ UI ไม่มี ▲▼ → เป็นกล่องสี่เหลี่ยม)
            self.add_float(f"บอท{verb}เป็น {duel.step_label(new)}", (185, 127, 224))

    # ───────────────────────── ผู้เล่น (เป้าของบอท) ─────────────────────────
    def gun_player_crouch(self):
        return 1.0 if self.gun_crouch else 0.0

    def gun_track_player(self):
        """จดตำแหน่งผู้เล่นทุกเฟรม (update_gun หลัง gun_move) — บอทเล็งจุดที่เราอยู่เมื่อ lag วิก่อน"""
        tr = self.gun_ptrail
        tr.append((self.gt, self.cam.pos[0], self.cam.pos[2], self.gun_player_crouch()))
        cut = self.gt - TRAIL_KEEP
        k = 0
        while k < len(tr) - 2 and tr[k + 1][0] < cut:
            k += 1
        if k:
            del tr[:k]

    def gun_player_at(self, t):
        """(x, z, crouch) ของผู้เล่น ณ เวลา t (ย้อนหลังได้ ≤ TRAIL_KEEP)"""
        tr = self.gun_ptrail
        for i in range(len(tr) - 1, -1, -1):
            if tr[i][0] <= t:
                return tr[i][1:]
        if tr:
            return tr[0][1:]
        return self.cam.pos[0], self.cam.pos[2], self.gun_player_crouch()

    def gun_player_pts(self, head_only=False):
        """จุดบนตัวเราที่บอทมองหา — head_only = เฉพาะหัว (ดริล PEEK: นาฬิกาบอทเริ่มเมื่อหัวเราพ้นขอบ ตาม DESIGN)"""
        fn = guns.head_points if head_only else guns.humanoid_points
        return fn(self.cam.pos[0], self.cam.pos[2], self.gun_player_crouch())

    # ───────────────────────── เกิด ─────────────────────────
    def gun_new_bot(self, x, z, tier):
        """บอท v2 ระดับ tier ที่ (x, z) — ปืนตาม gun_bot_weapon ; สุ่มทุกอย่างของตัวนี้ตอนเกิด (sim ทำซ้ำได้)"""
        b = Bot(x, z)
        b.weapon = self.gun_bot_weapon()
        p = duel.tier_params(tier, b.weapon, self.gun_drill)
        b.stab = Stability(b.weapon, WEAPONS[b.weapon]["rps"])
        b.born = None
        b.exposed = False
        b.meta = {"tier": p["tier"], "p": p, "aim_head": random.random() < p["head_p"],
                  "run_shoot": random.random() < p["run_shoot"],
                  "los": False, "los_t0": None, "engaged": False, "fire_at": None, "next_shot": 0.0,
                  "burst_i": 0, "e0": None, "t_first": None, "spawn_t": self.gt,
                  "shots": 0, "hits": 0, "heads": 0}
        return b

    def gun_spawn_cover(self, dist, lat_max=6.0, kinds=BEHAVIORS, xf=None):
        """ดวลใหม่: มุมกำแพงที่ระยะ dist + บอทแอบหลังกำแพง (หรือยืนเฝ้ามุม) — คืนบอท
        kinds = ชุดท่าโผล่ + น้ำหนัก (ดริล TAP/ADAD ส่งชุดของตัวเอง) ; xf = ตำแหน่งข้างที่กำหนดเอง (TAP ถึง 35 ม.)"""
        oz = self.gun_origin[2]
        lat = min(lat_max, 0.5 * dist)             # ระยะใกล้: ด้านข้างไม่เกินครึ่งหนึ่งของระยะ (ไม่เกิดข้างตัว)
        if xf is None:
            xf = random.uniform(-lat, lat)
        side = (1 if xf > 0 else -1) if abs(xf) > 0.5 else random.choice((-1, 1))
        zb = min(WALL_Z - 0.8, oz + math.sqrt(max(1.0, dist * dist - xf * xf)))
        edge = max(-ROOM_X + 1.8, min(ROOM_X - 1.8, xf + side * EDGE_OUT))
        x0, x1 = (edge, ROOM_X) if side > 0 else (-ROOM_X, edge)
        z1 = zb - COVER_BACK
        self.gun_set_covers([arena.Box(x0, x1, 0.0, COVER_H, z1 - COVER_T, z1)])
        names, weights = zip(*kinds)
        kind = random.choices(names, weights=weights)[0]
        lo, hi = OUT[kind]
        x_hide = edge + side * HIDE_IN
        x_to = self._gun_room_x(edge - side * random.uniform(lo, hi))
        b = self.gun_new_bot(x_to if kind == "hold" else x_hide, zb, self.gun_tier_now())
        m = b.meta
        m.update(kind=kind, side=side, edge=edge, dir=-side, x_hide=x_hide, x_to=x_to,
                 phase="fight" if kind == "hold" else "wait", t_go=self.gt + random.uniform(*WAIT))
        if kind == "jiggle":
            m["n_jig"] = random.choice((1, 2))
            m["commit"] = random.choice(("stop", "swing"))
            m["bait"] = True
        elif kind == "crouch":
            b.crouch = b.crouch_to = 1.0
        elif kind == "strafe":
            m["sdir"] = -side
            m["turn_t"] = None
        # สุ่มหลังค่าอื่นของ spawn นี้ทั้งหมด (ลำดับสุ่มคงที่ — ขับซ้ำใน sim ได้)
        m["crouch_fire"] = kind != "crouch" and random.random() < BOT_CROUCH_P
        self.bots.append(b)
        self.gun_start_duel(b)
        return b

    @staticmethod
    def _gun_room_x(x):
        return max(-ROOM_X + 0.5, min(ROOM_X - 0.5, x))

    # ───────────────────────── สายตา ─────────────────────────
    def gun_bot_los(self, b):
        """อัปเดต "เราเห็นบอท" (b.exposed/b.born) และ "บอทเห็นเรา" (m['los']) — ขอบขาขึ้นของบอทเห็นเรา = ตั้งเวลา
        นัดแรก: rt ของระดับ ∓ peeker's advantage (ใครกำลังวิ่งออกมาตอนเริ่มเห็นกัน)"""
        m = b.meta
        t = self.gt
        covers = self.gun_covers
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        seen = arena.any_visible(eye, b.points(), covers)
        b.exposed = seen
        if seen and "seen_t0" not in m:
            m["seen_t0"] = t
        if seen and b.born is None and not m.get("bait"):
            b.born = t                     # TTK นับจากตอนที่เราเห็นบอทครั้งแรก (ไม่นับไหล่ที่จิ้มหลอก)
        sees = arena.any_visible(b.eye(), self.gun_player_pts(m.get("see_pts") == "head"), covers)
        if sees and not m["los"]:
            m["los"] = True
            if m["los_t0"] is None and not m.get("bait"):
                m["los_t0"] = t
            if not m.get("bait"):
                if b.speed() > 0.5:
                    pa = -duel.PEEK_ADV            # บอทกำลัง peek ออกมา = เห็นเราก่อนที่เราจะเห็นมัน
                elif self.gun_speed() > guns.deadzone(self.gun_weapon) * self.gun_run_speed():
                    pa = duel.PEEK_ADV             # เราวิ่งเข้าหาบอทที่ยืนเฝ้า = เราได้เปรียบ
                else:
                    pa = 0.0
                rt = m["p"]["rt"] * (duel.REACQ if m["engaged"] else 1.0)
                m["fire_at"] = t + rt + pa
                m["engaged"] = True
        elif not sees and m["los"]:
            m["los"] = False
            m["fire_at"] = None

    # ───────────────────────── AI ต่อเฟรม ─────────────────────────
    def gun_cover_ai(self, b, dt):
        """บอทดวล (duel/quick/repo): เดินตามท่า → เห็นกัน → ยิงตามจังหวะระดับ ; ถอยเมื่อยืดเยื้อ"""
        m = b.meta
        t = self.gt
        side, dirx = m["side"], m["dir"]
        if m.get("crouch_until") is not None and t >= m["crouch_until"]:
            m["crouch_until"] = None
            b.crouch_to = 0.0              # ลุกหลังสาดชุดแรกจบ
        b.update_crouch(dt)
        # หมดเวลา: เห็นกันนานเกินหรือไม่เคยเห็นกันเลย → ถอยกลับหลังกำแพง (ดวลไม่นับ) ; ดริล TAP ตั้งช่วงโผล่ต่อตัวเอง
        if m["phase"] != "retreat" and ((m["los_t0"] is not None and t - m["los_t0"] > m.get("timeout", duel.DUEL_TIMEOUT))
                                         or (m["los_t0"] is None and t - m["spawn_t"] > NEVER_SEEN)):
            m["phase"] = "retreat"
            m["fire_at"] = None
        phase = m["phase"]
        wish = 0.0
        if phase == "wait" and t >= m["t_go"]:
            phase = m["phase"] = "out"
        if phase == "out":
            past = (b.x - m["x_to"]) * dirx
            kind = m["kind"]
            if kind == "jiggle":
                if past >= 0:
                    phase = m["phase"] = "back"
                else:
                    wish = dirx
            elif past >= 0 or (kind in ("stop", "crouch") and m["los"]):
                phase = m["phase"] = "fight"       # ถึงจุด / เห็นเราแล้ว → เบรก (counter-strafe) แล้วยิง
            elif (kind == "swing" and not m["run_shoot"] and m["fire_at"] is not None
                  and t >= m["fire_at"] - STOP_LEAD):
                phase = m["phase"] = "fight"       # วิ่งกว้างแต่มีวินัย: หยุดให้ทันจังหวะยิง
            else:
                wish = dirx
        if phase == "back":                        # jiggle: กลับหลังกำแพง แล้วจิ้มใหม่หรือออกจริง
            if (b.x - m["x_hide"]) * side >= 0:
                m["n_jig"] -= 1
                m["phase"] = "wait"
                m["t_go"] = t + random.uniform(0.25, 0.6)
                if m["n_jig"] <= 0:
                    m["kind"] = m["commit"]
                    m["bait"] = False
                    lo, hi = OUT[m["kind"]]
                    out = random.uniform(lo, hi)
                    if m.get("max_out"):
                        out = min(out, m["max_out"])        # ANGLE ในประตู: ไม่ออกเลยไปหลังผนังอีกฝั่ง
                    m["x_to"] = self._gun_room_x(m["edge"] - side * out)
            else:
                wish = float(side)
        if phase == "fight":
            if m["kind"] == "strafe":
                wish = self._gun_strafe_wish(b)
            else:
                wish = self._gun_brake_wish(b)
        if phase == "retreat":
            wish = float(side)
            if (b.x - m["x_hide"]) * side >= 0 and b.alive:
                b.alive = False                    # ถอยพ้นสายตาแล้ว — หายไป ดวลไม่นับ
                m["escaped"] = True
                m["die_t"] = t
                self.gun_duel_end("nc")
                self.gun_next_bot_at = t + random.uniform(0.4, 0.9)
                return
        run = WEAPONS[b.weapon]["run_speed"]
        cap = movement.speed_cap(run, crouch=b.crouch_to >= 0.5)
        movement.step(b.vel, (wish, 0.0) if wish else (0.0, 0.0), cap, dt)
        b.x = self._gun_room_x(b.x + b.vel[0] * dt)
        self.gun_bot_los(b)
        if phase in ("out", "fight"):
            self.gun_bot_try_fire(b)

    def _gun_brake_wish(self, b):
        """หยุดแบบ counter-strafe (กดทิศตรงข้ามจนเกือบนิ่ง แล้วปล่อย) — ถึง deadzone ใน ~60 ms เท่าผู้เล่น"""
        vx = b.vel[0]
        if abs(vx) > 0.3:
            return -1.0 if vx > 0 else 1.0
        return 0.0

    def _gun_strafe_wish(self, b):
        """ส่าย ADAD นอกขอบกำแพง: กลับทิศทุก STRAFE_TURN วิ (ตัวกลับทิศเองที่ปลายช่วง)"""
        m = b.meta
        t = self.gt
        lo = m["edge"] - m["side"] * STRAFE_SPAN[0]
        hi = self._gun_room_x(m["edge"] - m["side"] * STRAFE_SPAN[1])
        if m["turn_t"] is None:
            m["turn_t"] = t + random.uniform(*STRAFE_TURN)
        if t >= m["turn_t"]:
            m["sdir"] = -m["sdir"]
            m["turn_t"] = t + random.uniform(*STRAFE_TURN)
        # ปลายช่วง: ห้ามหลบกลับหลังกำแพง / ห้ามออกไกลเกิน
        if (b.x - lo) * m["side"] > 0:
            m["sdir"] = -m["side"]
        elif (b.x - hi) * m["dir"] > 0:
            m["sdir"] = m["side"]
        return float(m["sdir"])

    # ───────────────────────── ยิง ─────────────────────────
    def gun_bot_try_fire(self, b):
        """ยิงเมื่อ: เห็นเรา + ถึงจังหวะ (fire_at) + ถึงคิวนัดถัดไป + หยุดนิ่งพอ (เว้นแต่ตัวนี้ "วิ่งยิง")"""
        m = b.meta
        t = self.gt
        if (not m["los"] or m["fire_at"] is None or t < m["fire_at"] or t < m["next_shot"] or m.get("bait")
                or m.get("no_fire")):
            return                          # no_fire = เป้าซ้อมที่ไม่ยิงสวน (ดริล TAP)
        if not guns.is_accurate(b.weapon, b.speed()) and not m["run_shoot"]:
            return                          # ยังเร็วเกิน deadzone — รอ counter-strafe ให้นิ่งก่อน (บอทมีวินัย)
        if m["t_first"] is None and m.get("crouch_fire") and "crouch_until" not in m:
            # หมอบตอนเริ่มยิงนัดแรก — หัวลด CROUCH_DROP ใน CROUCH_TIME วิ ; คนที่ค้างเป้าระดับหัวยืนจะยิงข้ามหัว
            b.crouch_to = 1.0
            m["crouch_until"] = t + random.uniform(*BOT_CROUCH_HOLD)
        self.gun_bot_fire(b)
        m["next_shot"] = t + self.gun_bot_gap(b)

    def gun_bot_gap(self, b):
        """ช่วงถึงนัดถัดไปของบอท: ไรเฟิลยิงเป็นชุดละ burst นัดตาม rps แล้วพัก BURST_PAUSE ; ปืนนัดเดียวแตะตาม
        tap efficiency ของปืน (Sheriff 2/วิ, Ghost 4/วิ — ถี่กว่านั้นสเปรดโต) ; Classic ไม่มีค่า = rps"""
        w = WEAPONS[b.weapon]
        m = b.meta
        if w["auto"]:
            m["burst_i"] += 1
            if m["burst_i"] >= m["p"]["burst"]:
                m["burst_i"] = 0
                return max(duel.BURST_PAUSE, 1.0 / w["rps"])
            return 1.0 / w["rps"]
        tap = (patched_block(b.weapon) or {}).get("tap_eff") or w["rps"]
        return 1.0 / min(w["rps"], tap)

    def gun_bot_fire(self, b):
        """กระสุนบอท 1 นัด: เล็งหัว/อกของตำแหน่งเราเมื่อ lag วิก่อน + คลาดที่หดตามเวลา + สเปรด/รีคอยล์ปืนบอท
        + โทษเคลื่อนที่ → รังสีจากตาบอท ชนกำแพงก่อน = ไม่โดน ; โดนหัว/ตัว/ขาตาม hitbox ผู้เล่น (หมอบได้)"""
        m = b.meta
        p = m["p"]
        t = self.gt
        px, pz, pcr = self.gun_player_at(t - p["lag"])
        hy = guns.HEAD_Y - guns.CROUCH_DROP * pcr
        ay = hy if m["aim_head"] else hy - p["body_drop"]
        eye = b.eye()
        yaw0, pitch0 = arena.angles_to(eye, (px, ay, pz))
        sig = p["sigma"]
        if m["e0"] is None:
            m["e0"] = (random.gauss(0.0, sig), random.gauss(0.0, sig))
            m["t_first"] = t
        k = math.exp(-(t - m["t_first"]) / duel.SETTLE_TAU)
        fl = sig * duel.SETTLE_FLOOR
        ex = m["e0"][0] * k + random.gauss(0.0, fl)
        ey = m["e0"][1] * k + random.gauss(0.0, fl)
        crouch = b.crouch >= 0.5
        po, yo, sp = b.stab.shoot(t, crouch=crouch)
        sp += guns.move_error_deg(b.weapon, b.speed(), crouch)
        c = 1.0 - p["comp"]
        dyaw, dpitch = cone_offset(sp)
        d = arena.dir_from_angles(yaw0 + math.radians(ex + yo * c) + dyaw,
                                  pitch0 + math.radians(ey + po * c) + dpitch)
        m["shots"] += 1
        zone, tz = guns.humanoid_zone(eye, d, self.cam.pos[0], self.cam.pos[2], self.gun_player_crouch())
        if zone:
            tc, _ = arena.first_hit(eye, d, self.gun_covers)
            if tc is not None and tc < tz:
                zone = None                 # กำแพงขวางแนวกระสุน (เราอยู่หลังที่กำบัง/บอทยังไม่พ้นขอบ)
        if not zone:
            self.play(self.snd_miss)
            return
        m["hits"] += 1
        if zone == "head":
            m["heads"] += 1
        dist = math.hypot(b.x - self.cam.pos[0], b.z - self.cam.pos[2])
        self.gun_player_hit(guns.damage_for(b.weapon, zone, dist), zone == "head")

    # ───────────────────────── OP HOLD: บอทโผล่ช่องกำแพงยิงแบบมีเหตุผลเหมือนกัน ─────────────────────────
    def gun_hold_fire(self, b):
        """บอท peek ใน OP HOLD: เริ่มโผล่ (exposed ขาขึ้นใน gun_hold_ai) = บอทเป็นฝ่าย peek → นัดแรก rt − PEEK_ADV
        ยิงเฉพาะตอนยืนค้างในช่อง (นิ่ง = แม่น) ; กำแพงเป็นกล่องใน gun_covers → กระสุนต้องลอดช่องจริง"""
        m = b.meta
        if "p" not in m or b.weapon is None:
            return
        t = self.gt
        if b.exposed and not m["los"]:
            m["los"] = True
            if m["kind"] == "peek":
                m["fire_at"] = t + m["p"]["rt"] - duel.PEEK_ADV
        elif not b.exposed:
            m["los"] = False
        if (b.state == "hold" and m["los"] and m["fire_at"] is not None and t >= m["fire_at"]
                and t >= m["next_shot"]):
            self.gun_bot_fire(b)
            m["next_shot"] = t + self.gun_bot_gap(b)

    # ───────────────────────── สรุปรอบ ─────────────────────────
    def gun_ladder_fields(self, ent):
        """ช่องบันไดใน history entry: ดริลจัดแรงค์ = tier_i (ดัชนี RANKS จาก ~LADDER_WINDOW ดวลล่าสุดของสาย — เฉพาะรอบที่
        นิ่งแล้ว duel.Ladder.settled) + tier_n (ดวลที่ตัดสินผลรอบนี้) + tier_w (ชนะ) + tier_end (ระดับบอทตอนจบ ใช้เริ่มรอบหน้า)
        + tier_tr ([[ระดับบอท, 1 ชนะ/0 แพ้], …] ของรอบนี้ — รอบหน้าอ่านต่อเป็นข้อมูลของสาย duel.ladder_resume) ;
        ยังไม่นิ่ง = ไม่มี tier_i (ไม่เข้าแรงค์ดวล/ค่ากลาง/dashboard) ; ดริลอื่น = tier_bot (ระดับบอทที่ใช้ ไม่จัดแรงค์)"""
        lad = self.gun_ladder
        if lad is not None:
            est = lad.estimate()
            if est is not None:
                if lad.settled():
                    ent["tier_i"] = est
                ent["tier_n"] = lad.n
                ent["tier_w"] = lad.wins
            if lad.n or not lad.fresh:
                # สายใหม่ที่ยังไม่มีดวลตัดสินผล ไม่บันทึก — รอบหน้ายังเริ่มสายใหม่ (ก้าว 2 ขั้น)
                ent["tier_end"] = lad.cur
                ent["tier_tr"] = [[t, 1 if w else 0] for t, w in lad.trials]
        else:
            ent["tier_bot"] = self.gun_fixed_tier
        return ent
