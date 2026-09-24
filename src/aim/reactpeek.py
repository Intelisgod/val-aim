# -*- coding: utf-8 -*-
"""REACTION · PEEK (variant "peek" ของโหมด reaction — lane C5, phase-1 trainer-realism D7 "reaction v2") — ReactPeekMixin

จุดอ่อนที่วัดได้ของผู้ใช้: reaction·static ระดับ Immortal (157 ms) แต่ reaction·flick 416 ms @71% = ช่องว่างอยู่ที่
"เห็นแล้ว flick ไปยิงหัวที่ไม่ได้อยู่ใต้ crosshair" — โหมดนี้ฝึกตรงนั้นในเรขาคณิตแบบเกม:
  • ยืนที่จุดเริ่ม GUNFIGHT (ระยะถึงผนังหลัง 32 ม.) หน้าห้องมีกล่อง/กำแพง 4–6 ชิ้นที่ระยะไฟต์ไรเฟิลจริง (DUEL_DIST_Q)
  • หลังช่วงรอแบบ exponential (config.RPEEK_FORE — hazard คงที่ เดาจังหวะไม่ได้) หุ่นคนเลื่อนออกจากขอบกล่องที่อยู่ห่าง
    crosshair 15–40° (เลือกจาก crosshair "ตอนนั้น" — เฝ้าขอบเดาไว้ก็ไม่ช่วย) หัวอยู่ระดับหัวจริง (1.60 ม.)
  • จับเวลาจาก "เฟรมแรกที่หัวพ้นขอบ" ถึงคลิกที่โดนหัว (โดนตัว = ยังไม่นับ ต้องหัว) ; ~15% เป็น catch trial ไม่มีอะไรโผล่ ;
    คลิกก่อนหัวโผล่ = +100 ms (กติกาเดียวกับ static/flick) ; หัวโดนภายใน 100 ms = เดา ตัดทิ้ง ; ไม่โดนใน 1.5 วิ = นับ 1500
  • ครบ REACTION_COUNT ครั้ง = จบรอบ ; แรงค์จากเวลาเฉลี่ยด้วยขีด rt_thresh(t, "peek") (ที่มาดู config.PEEK_RT_STRETCH)
วาดด้วยตัววาดของ GUNFIGHT (กล่อง arena บน GPU/software + draw_bot + บังบอทหลังกล่อง) — ไฟล์นี้ไม่ import pygame"""
import math
import random

from .config import (EYE_Y, ROOM_X, WALL_Z, REACTION_COUNT, REACTION_RT_RANKS, RPEEK_FORE, RPEEK_CATCH_P,
                     RPEEK_CATCH_WIN, RPEEK_ANTICIP_MS, RPEEK_OFF_DEG, RPEEK_TIMEOUT, C_RED, C_DIM)
from . import arena, guns, movement

# กติกาหนึ่งบรรทัด (แผงเมนู + ใต้เลขนับถอยหลัง) — เดิมไม่บอกที่ไหนเลยว่าต้องหัว/มีรอบหลอก/กดก่อนโดนบวกเวลา
RPEEK_RULE = "คลิกหัวที่โผล่จากขอบ · โดนตัวไม่นับ · บางครั้งไม่มีอะไรโผล่ (กดก่อน = +100ms) · เร็วกว่า 100ms = เดา ไม่นับ"

RP_BOX_W = (2.4, 3.2)          # กล่อง/กำแพงสั้น: กว้างพอซ่อนหุ่นตรงกลาง (ไหล่ 0.22 ม. + เผื่อ)
RP_BOX_D, RP_BOX_H = 0.6, 2.2
RP_BEHIND = 0.45               # หุ่นยืนหลังผิวหลังกล่อง
RP_OUT = (0.45, 0.9)           # ศูนย์ตัวออกพ้นขอบเท่านี้แล้วหยุด (หัว + ไหล่โผล่ — ท่า "โผล่หยุดยิง")
RP_DIST = (9.0, 26.0)          # ระยะกล่อง (หนีบจากการกระจายระยะคิลไรเฟิลจริง)
RP_BOXES = (4, 6)


def fore_period(rng=random):
    """ช่วงรอแบบ exponential ตัดปลาย (inverse CDF) — hazard คงที่ระหว่าง [min, max] : รอนานแล้วโอกาสโผล่ต่อวินาทีเท่าเดิม"""
    lo, mean, hi = RPEEK_FORE
    span = hi - lo
    u = rng.random()
    return lo - mean * math.log(1.0 - u * (1.0 - math.exp(-span / mean)))


def _ang_between(fwd, v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n <= 1e-9:
        return 0.0
    c = (fwd[0] * v[0] + fwd[1] * v[1] + fwd[2] * v[2]) / n
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def build_layout(origin, rng=random):
    """ฉาก reaction·peek: กล่อง 4–6 ชิ้นไม่บังกันเอง + จุดโผล่ซ้าย/ขวาของแต่ละกล่อง → (กล่อง, จุดโผล่)
    จุดโผล่ = dict x_hide/x_to/zb/edge/side ; ตรวจแล้วว่าหุ่นที่จุดซ่อนมองไม่เห็นจากตา และหัวที่จุดโผล่มองเห็น"""
    from .gunplay import DUEL_DIST_Q, _Q_AT
    ox, oy, oz = origin
    qs = DUEL_DIST_Q["phantom"]                 # แถว "ไรเฟิลรวม" (33,717 คิล)

    def rifle_dist():
        u = rng.uniform(_Q_AT[0], _Q_AT[-1])
        for (u0, d0), (u1, d1) in zip(zip(_Q_AT, qs), zip(_Q_AT[1:], qs[1:])):
            if u <= u1:
                return max(RP_DIST[0], min(RP_DIST[1], d0 + (d1 - d0) * (u - u0) / (u1 - u0)))
        return RP_DIST[1]
    want = rng.randint(*RP_BOXES)
    boxes, spans = [], []
    for _try in range(80):
        if len(boxes) >= want:
            break
        d = rifle_dist()
        w = rng.uniform(*RP_BOX_W)
        x = rng.uniform(-ROOM_X + w / 2 + 1.6, ROOM_X - w / 2 - 1.6)
        if abs(x - ox) > d - 2.0:
            continue
        z = oz + math.sqrt(d * d - (x - ox) ** 2)
        if z + RP_BOX_D + RP_BEHIND + 0.5 > WALL_Z:
            continue
        # ช่วงมุมที่กล่องนี้บัง (รวมที่หุ่นโผล่ออกข้างละ ~1.2 ม.) — ห้ามทับกล่องอื่น ไม่งั้นขอบถูกบังหรือหุ่นโผล่หลังกล่องหน้า
        a0 = math.degrees(math.atan2(x - w / 2 - 1.3 - ox, z - oz))
        a1 = math.degrees(math.atan2(x + w / 2 + 1.3 - ox, z - oz))
        if any(not (a1 < s0 - 1.5 or a0 > s1 + 1.5) for s0, s1 in spans):
            continue
        boxes.append(arena.Box(x - w / 2, x + w / 2, 0.0, RP_BOX_H, z, z + RP_BOX_D))
        spans.append((a0, a1))
    eye = (ox, oy, oz)
    spots = []
    for bx in boxes:
        (x0, _y0, _z0), (x1, _y1, z1) = bx.lo, bx.hi
        zb = z1 + RP_BEHIND
        xm = (x0 + x1) / 2
        for edge, side in ((x0, 1), (x1, -1)):
            x_to = edge - side * rng.uniform(*RP_OUT)
            if not (-ROOM_X + 0.5 < x_to < ROOM_X - 0.5):
                continue
            hidden = not arena.any_visible(eye, guns.humanoid_points(xm, zb), boxes)
            shown = arena.any_visible(eye, guns.head_points(x_to, zb), boxes)
            if hidden and shown:
                spots.append(dict(edge=edge, side=side, x_hide=xm, x_to=x_to, zb=zb,
                                  head=(x_to, guns.HEAD_Y, zb)))
    return boxes, spots


def pick_spot(spots, eye, fwd, rng=random):
    """จุดโผล่ที่หัว (ตอนหยุด) อยู่ห่าง crosshair ในช่วง RPEEK_OFF_DEG — ไม่มี = จุดที่ใกล้ช่วงนั้นที่สุด → (spot, องศา)"""
    lo, hi = RPEEK_OFF_DEG
    scored = []
    for sp in spots:
        h = sp["head"]
        a = _ang_between(fwd, (h[0] - eye[0], h[1] - eye[1], h[2] - eye[2]))
        scored.append((0.0 if lo <= a <= hi else min(abs(a - lo), abs(a - hi)), a, sp))
    ok = [s for s in scored if s[0] == 0.0]
    if ok:
        _p, a, sp = rng.choice(ok)
        return sp, a
    _p, a, sp = min(scored, key=lambda s: s[0])
    return sp, a


class ReactPeekMixin:
    def rpeek_on(self):
        return self.mode == "reaction" and getattr(self, "reaction_variant", "static") == "peek"

    def arena_on(self):
        """มีฉาก arena (พื้นขยาย + กล่อง gun_covers) ให้ตัววาดไหม — GUNFIGHT ทุกดริล และ reaction·peek (glrender ใช้)"""
        return self.mode == "gun" or self.rpeek_on()

    def rpeek_reset(self):
        """เรียกจาก reset_round — สถานะ/ตัวชี้วัดของรอบ"""
        self.rp = {"state": "idle", "t_next": None, "bot": None, "spot": None, "t_on": None, "clicked": False,
                   "off": [], "fs_hit": 0, "n_on": 0, "catch": 0, "fa": 0, "antic": 0, "slow": 0, "body": 0}

    def rpeek_setup(self):
        """เรียกหลังสร้างกล้องใหม่ใน start_countdown — ยืนจุดเริ่ม GUNFIGHT + สร้างฉาก (เห็นตั้งแต่นับถอยหลัง)"""
        from .gunplay import GUN_ORIGIN_Z
        self.cam.pos = [0.0, EYE_Y, GUN_ORIGIN_Z]
        boxes, spots = build_layout(tuple(self.cam.pos))
        for _try in range(6):
            if len(spots) >= 4:
                break
            boxes, spots = build_layout(tuple(self.cam.pos))
        self.gun_set_covers(boxes)
        self.rp["spots"] = spots

    def rpeek_begin(self):
        """begin_play ของ variant นี้ — เริ่มช่วงรอแรก"""
        if not self.rp.get("spots"):
            self.rpeek_setup()
        self.rp["state"] = "wait"
        self.rp["t_next"] = self.gt + fore_period()

    # ───────────────────────── ต่อเฟรม ─────────────────────────
    def rpeek_update(self, dt):
        rp = self.rp
        t = self.gt
        st = rp["state"]
        if st == "wait" and t >= rp["t_next"]:
            if getattr(self, "lmb_down", False):
                rp["t_next"] = t + 0.05              # ยังกดค้าง (นิ้วยังไม่กลับที่) — รอปล่อยก่อน เหมือน static/flick
            elif random.random() < RPEEK_CATCH_P:
                rp["state"] = "catch"
                rp["t_next"] = t + RPEEK_CATCH_WIN
                rp["catch"] += 1
            else:
                self._rpeek_spawn()
        elif st == "catch" and t >= rp["t_next"]:
            rp["state"] = "wait"
            rp["t_next"] = t + fore_period()
        b = rp["bot"]
        if b is None:
            return
        m = b.meta
        run = guns.WEAPONS["vandal"]["run_speed"]
        if rp["state"] == "peek":
            past = (b.x - rp["spot"]["x_to"]) * (-rp["spot"]["side"])
            if m.get("stopping") or past >= 0:
                m["stopping"] = True
                wish = (-1.0 if b.vel[0] > 0 else 1.0) if abs(b.vel[0]) > 0.3 else 0.0   # counter-strafe หยุด
            else:
                wish = -float(rp["spot"]["side"])
            movement.step(b.vel, (wish, 0.0) if wish else (0.0, 0.0), run, dt)
            b.x += b.vel[0] * dt
            if rp["t_on"] is None:
                eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
                if arena.any_visible(eye, b.head_points(), self.gun_covers):
                    rp["t_on"] = t
                    rp["n_on"] += 1
                    rp["clicked"] = False
                    x, y, z = self.cam.to_cam((b.x, b.head_y(), b.z))
                    rp["off"].append(_ang_between((0.0, 0.0, 1.0), (x, y, z)))
            elif t - rp["t_on"] > RPEEK_TIMEOUT:
                # ไม่โดนหัวทันเวลา = ในเกมโดนยิงไปแล้ว → นับเวลาเต็ม (ไม่ใช่ตัดทิ้ง — ไม่งั้นเลือกช้าเพื่อเลี่ยงค่าแย่ได้)
                rp["slow"] += 1
                self._rpeek_record(RPEEK_TIMEOUT * 1000.0, hit=False)
                self.add_float("ช้าไป — โดนยิงก่อน", C_RED)
                self._rpeek_leave(b)
        elif rp["state"] == "leave":
            movement.step(b.vel, (float(rp["spot"]["side"]), 0.0), run, dt)
            b.x += b.vel[0] * dt
            if (b.x - rp["spot"]["x_hide"]) * rp["spot"]["side"] >= 0 or t - rp["t_leave"] > 1.0:
                self._rpeek_next()

    def _rpeek_spawn(self):
        rp = self.rp
        eye = (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])
        sp, _a = pick_spot(rp["spots"], eye, self.cam.forward())
        b = guns.Bot(sp["x_hide"], sp["zb"])
        b.born = None
        b.exposed = False
        b.meta = {"no_bar": True}
        rp.update(state="peek", bot=b, spot=sp, t_on=None, clicked=False)

    def _rpeek_leave(self, b):
        """หมดเวลา: หุ่นถอยกลับหลังกล่อง (ไม่หายกลางที่โล่ง) แล้วเริ่มครั้งถัดไป"""
        self.rp["state"] = "leave"
        self.rp["t_leave"] = self.gt

    def _rpeek_next(self):
        rp = self.rp
        rp["bot"] = None
        rp["spot"] = None
        rp["t_on"] = None
        if self.reaction_done >= REACTION_COUNT:
            rp["state"] = "done"
            if self.pending_end is None:
                self.pending_end = self.gt + 0.4
            return
        rp["state"] = "wait"
        rp["t_next"] = self.gt + fore_period()

    def _rpeek_record(self, rt, hit):
        """นับหนึ่งครั้ง (รวมโทษกดก่อน) — เข้า reaction_times เหมือน static/flick"""
        if self.early_penalty_ms:
            rt += self.early_penalty_ms
            self.early_penalty_ms = 0.0
        self.reaction_times.append(rt)
        self.reaction_done += 1

    # ───────────────────────── ยิง ─────────────────────────
    def rpeek_shoot(self):
        rp = self.rp
        st = rp["state"]
        b = rp["bot"]
        if st in ("wait", "catch", "idle") or (st == "peek" and rp["t_on"] is None):
            # กดก่อนหัวโผล่ (รวม catch trial ที่ไม่มีอะไรโผล่) = โทษ +100 ms เข้าครั้งถัดไป แบบเดียวกับ static/flick
            self.early_clicks += 1
            self.early_penalty_ms += 100.0
            if st == "catch":
                rp["fa"] += 1
            self.add_float("TOO EARLY! +100ms", (255, 170, 0))
            self.play(self.snd_miss)
            if st == "wait":
                rp["t_next"] = self.gt + fore_period()
            return
        if st != "peek" or b is None:
            return
        first = not rp["clicked"]
        rp["clicked"] = True
        d = (0.0, 0.0, 1.0)
        zone = b.hit_zone(self.cam, d)
        if zone:
            cov = self.gun_wall_hit(self.cam.to_world_dir(d))
            if cov is not None and cov[0] < self._gun_bot_t(b, self.cam.to_world_dir(d)) - 0.25:
                zone = None                           # ขอบกล่องบังอยู่
        o = self.bot_screen_off(b)
        self.shot_data.append({"x": o[0], "y": o[1], "hit": zone == "head", "ref": "head"})
        if zone != "head":
            self.misses += 1
            if zone:
                rp["body"] += 1
                self.add_float("ตัว — ต้องหัว", C_DIM)
            else:
                self.add_float("miss", C_RED)
            self.play(self.snd_miss)
            return
        rt = (self.gt - rp["t_on"]) * 1000.0
        if rt < RPEEK_ANTICIP_MS:
            # เร็วกว่าที่คนตอบสนองได้ = วางเป้ารอแล้วคลิกเดา — ไม่นับ (ไม่เข้า hits/เวลา) เริ่มครั้งใหม่
            rp["antic"] += 1
            self.add_float(f"เร็วเกินคน (<{RPEEK_ANTICIP_MS}ms) ไม่นับ", (255, 170, 0))
            b.alive = False
            b.meta["die_t"] = self.gt
            self._rpeek_next()
            return
        if first:
            rp["fs_hit"] += 1
        self.hits += 1
        self.headshots += 1
        self._rpeek_record(rt, hit=True)
        self.add_float(f"{rt:.0f}ms", (102, 255, 153))
        self.play(self.snd_head)
        self.hit_marker()
        b.alive = False
        b.meta["die_t"] = self.gt
        self._rpeek_next()

    # ───────────────────────── วาด / สรุป ─────────────────────────
    def draw_rpeek_world(self, f):
        """ฉาก reaction·peek บน overlay: พื้นขยาย + กล่อง (software) + หุ่น + บังหุ่นที่อยู่หลังกล่อง"""
        gpu_world = getattr(self, "_world_gpu_frame", False)
        if not gpu_world:
            self.draw_arena_grid(f)
        covers = self.draw_arena_covers(f, gpu_world)
        b = self.rp.get("bot")
        if b is None or (not b.alive and self.gt - b.meta.get("die_t", self.gt) > 0.15):
            return
        r = self.draw_bot(b, f)
        if r is not None and covers:
            self.draw_cover_occlusion(covers, b, r, f, gpu_world)

    def rpeek_fields(self, ent):
        """คีย์เพิ่มใน history entry ของ reaction·peek"""
        rp = self.rp
        if rp["off"]:
            s = sorted(rp["off"])
            ent["rp_off"] = round(s[len(s) // 2], 1)       # ค่ากลางองศาจาก crosshair ถึงหัว ณ เฟรมที่โผล่
        ent["rp_n"] = rp["n_on"]
        ent["rp_fs"] = rp["fs_hit"]                        # ครั้งที่คลิกแรกหลังโผล่โดนหัว
        for k in ("catch", "fa", "antic", "slow", "body"):
            if rp[k]:
                ent["rp_" + k] = rp[k]
        return ent

    def rpeek_cards(self):
        rp = self.rp
        n = max(1, rp["n_on"] - rp["antic"])
        s = sorted(rp["off"])
        off = f"{s[len(s) // 2]:.0f}°" if s else "--"
        return [(str(self.hits), "HEAD HITS"), (f"{round(100 * rp['fs_hit'] / n)}%", "นัดแรกเข้าหัว"),
                (off, "ห่าง crosshair"), (f"{rp['slow']}/{rp['antic']}", "ช้า / เดาไม่นับ")]

    def rpeek_note(self):
        rp = self.rp
        return (f"รอบหลอก (ไม่มีอะไรโผล่) {rp['catch']} ครั้ง (กดผิด {rp['fa']}) · โดนตัวแทนหัว {rp['body']} · "
                f"ช้าเกิน {RPEEK_TIMEOUT:g} วิ {rp['slow']} · เดาเร็วเกินคน {rp['antic']}")


def selftest(g):
    """reaction·peek (เรียกจาก aim.selftest ด้วย Game headless) — คืน list ข้อผิดพลาด:
    ช่วงรอ exponential (ขอบเขต/ค่าเฉลี่ย/ไร้ความจำ) · ฉาก (ซ่อนจริง/โผล่เห็นหัว) · เลือกขอบ 15–40° จาก crosshair ·
    นับเวลาจากหัวพ้นขอบ · ต้องโดนหัว · เดา <100 ms ไม่นับ · กดก่อน +100 ms · catch ~15% · ช้าเกิน = 1500 ·
    ครบ 5 ครั้งจบรอบ + entry rp_* · ขีดแรงค์ peek เรียงถูก"""
    from .ranks import get_rt_rank, rt_thresh
    errors = []
    rng_state = random.getstate()
    try:
        rng = random.Random(5)
        lo, mean, hi = RPEEK_FORE
        xs = [fore_period(rng) for _ in range(40000)]
        span = hi - lo
        want = lo + mean - span * math.exp(-span / mean) / (1 - math.exp(-span / mean))
        m = sum(xs) / len(xs)
        if min(xs) < lo - 1e-9 or max(xs) > hi + 1e-9 or abs(m - want) > 0.03:
            errors.append(f"rpeek: ช่วงรอ {min(xs):.2f}–{max(xs):.2f} เฉลี่ย {m:.3f} (ต้อง {lo}–{hi} เฉลี่ย {want:.3f})")
        # ไร้ความจำ: รอมา 1.0 วิแล้ว โอกาสรออีก ≥0.5 วิ เท่ากับรอมา 1.5 วิแล้ว (hazard คงที่ — uniform เดิมไม่เท่า)
        def surv(a, b):
            n_a = sum(1 for x in xs if x > a)
            return sum(1 for x in xs if x > b) / n_a
        s1, s2 = surv(1.0, 1.5), surv(1.5, 2.0)
        if abs(s1 - s2) > 0.03:
            errors.append(f"rpeek: ช่วงรอต้องไร้ความจำ (P>1.5|>1.0 {s1:.3f} vs P>2.0|>1.5 {s2:.3f})")
        # ฉาก + เลือกขอบ
        from .gunplay import GUN_ORIGIN_Z
        eye = (0.0, EYE_Y, GUN_ORIGIN_Z)
        offs, n_sp = [], []
        for k in range(150):
            boxes, spots = build_layout(eye, rng)
            n_sp.append(len(spots))
            for sp in spots:
                if arena.any_visible(eye, guns.humanoid_points(sp["x_hide"], sp["zb"]), boxes):
                    errors.append("rpeek: จุดซ่อนมองเห็นได้")
                    break
            fwd = (math.sin(rng.uniform(-0.5, 0.5)), 0.0, 1.0)
            n = math.sqrt(fwd[0] ** 2 + 1.0)
            if len(spots) >= 3:
                _sp, a = pick_spot(spots, eye, (fwd[0] / n, 0.0, 1.0 / n), rng)
                offs.append(a)
        inside = sum(1 for a in offs if RPEEK_OFF_DEG[0] <= a <= RPEEK_OFF_DEG[1]) / max(1, len(offs))
        if sorted(n_sp)[len(n_sp) // 2] < 6 or inside < 0.9:
            errors.append(f"rpeek: จุดโผล่ต่อฉาก (ค่ากลาง {sorted(n_sp)[len(n_sp) // 2]}) / เลือกได้ใน 15–40° {inside:.0%}")
        # เล่นจริง: เห็นหัว → เล็งหัวเป๊ะ → คลิก ; เวลา = จากหัวพ้นขอบ (≥ 100 ms) ; นับเฉพาะหัว
        g.mode, g.reaction_variant, g.duration = "reaction", "peek", 15
        g.start_countdown()
        g.begin_play()
        if tuple(g.cam.pos) != (0.0, EYE_Y, GUN_ORIGIN_Z) or len(g.gun_covers) < 3 or not g.rp.get("spots"):
            errors.append("rpeek: ต้องยืนจุดเริ่ม GUNFIGHT และมีฉากกล่องตั้งแต่เริ่ม")
        g.shoot()                                  # กดก่อนหัวโผล่ = +100 ms
        if g.early_clicks != 1 or g.early_penalty_ms != 100.0:
            errors.append("rpeek: กดก่อนหัวโผล่ต้องโดนโทษ +100 ms")
        phase = {"body": False, "antic": False, "slow": False}
        guard = 0
        while g.state == "play" and guard < 144 * 90:
            guard += 1
            rp = g.rp
            b = rp.get("bot")
            if rp["state"] == "peek" and rp["t_on"] is not None and b is not None and b.alive:
                dt_on = g.gt - rp["t_on"]
                if not phase["antic"]:
                    # ครั้งแรก: เล็งหัวรอไว้แล้วคลิกทันทีที่โผล่ (< 100 ms) → เดา ไม่นับ — เล็งขอบหัวด้านที่พ้นขอบกล่องแล้ว
                    # (เฟรมแรกที่โผล่ ศูนย์หัวยังอยู่หลังกล่อง: คลิกศูนย์หัว = โดนกล่อง ถูกต้องตามจริง)
                    phase["antic"] = True
                    d0 = g.reaction_done
                    _aim(g, (b.x - rp["spot"]["side"] * 0.12, b.head_y(), b.z))
                    g.shoot()
                    if g.reaction_done != d0 or rp["antic"] != 1 or g.hits:
                        errors.append("rpeek: คลิกโดนหัวภายใน 100 ms ต้องไม่นับ (เดา)")
                elif not phase["body"] and dt_on >= 0.25:
                    phase["body"] = True
                    _aim(g, (b.x, b.body_y1() - 0.15, b.z))
                    h0 = g.hits
                    g.shoot()                      # โดนตัว = ยังไม่นับ ต้องหัว
                    if g.hits != h0 or rp["body"] != 1:
                        errors.append("rpeek: คลิกโดนตัวต้องไม่นับเป็นโดน")
                elif not phase["slow"]:
                    pass                           # ครั้งนี้ปล่อยให้หมดเวลา → นับ 1500 ms
                elif dt_on >= 0.3:
                    _aim(g, (b.x, b.head_y(), b.z))
                    g.shoot()
            if rp["state"] == "leave" and not phase["slow"]:
                phase["slow"] = True
                if abs(g.reaction_times[-1] - RPEEK_TIMEOUT * 1000.0 - 100.0) > 1e-6:
                    errors.append(f"rpeek: หมดเวลาต้องนับ 1500 ms (+โทษกดก่อน 100) ได้ {g.reaction_times[-1]}")
            g.update_play(1 / 144)
        e = getattr(g, "last_entry", {}) or {}
        if g.state != "results" or e.get("variant") != "peek" or e.get("mode") != "reaction":
            errors.append(f"rpeek: รอบต้องจบเมื่อครบ {REACTION_COUNT} ครั้ง (state {g.state})")
        else:
            rts = g.reaction_times
            if len(rts) != REACTION_COUNT or min(rts) < RPEEK_ANTICIP_MS or \
                    not all(k in e for k in ("rp_n", "rp_fs", "rp_off", "rp_antic", "rp_slow", "rp_body")):
                errors.append(f"rpeek: entry/เวลาผิด ({rts}, {e})")
            if not all(RPEEK_OFF_DEG[0] - 5 <= a <= RPEEK_OFF_DEG[1] + 5 for a in g.rp["off"]):
                errors.append(f"rpeek: หัวโผล่ห่าง crosshair {g.rp['off']} (ต้อง ~15–40°)")
        # catch trial ~15%: เดินช่วงรอยาว ๆ โดยไม่ยิง นับ catch / (catch + โผล่) — seed คงที่ ทำซ้ำได้
        random.seed(20260924)
        g.mode, g.reaction_variant = "reaction", "peek"
        g.start_countdown()
        g.begin_play()
        n_peek = 0
        prev = None
        for _ in range(144 * 800):
            st = g.rp["state"]
            if st == "peek" and prev != "peek":
                n_peek += 1
            if st == "peek" and g.rp["t_on"] is not None and g.gt - g.rp["t_on"] > 0.2:
                g.rp["bot"].alive = False
                g._rpeek_next()                   # จบครั้งนี้แบบไม่นับ (เทสต์นับแค่สัดส่วน catch)
                g.reaction_done = 0
            prev = st
            g.update_play(1 / 144)
        c = g.rp["catch"]
        frac = c / max(1, c + n_peek)
        if not 0.10 <= frac <= 0.20 or c + n_peek < 300:
            errors.append(f"rpeek: catch trial {c}/{c + n_peek} = {frac:.2f} (ต้อง ~{RPEEK_CATCH_P})")
        # ขีดแรงค์ peek: เรียงเพิ่มขึ้น, ยืดกว่า flick, ผู้ใช้จำลอง 639 ms = Gold I (tools/peek_react_fit.py)
        ths = [rt_thresh(t, "peek") for t, _n, _c in REACTION_RT_RANKS if t != float("inf")]
        if ths != sorted(ths) or rt_thresh(150, "peek") <= rt_thresh(150, "flick") or \
                get_rt_rank(639, "peek")[1] != "Gold I":
            errors.append(f"rpeek: ขีดแรงค์ peek ผิด ({ths[:3]}…, 639 ms → {get_rt_rank(639, 'peek')[1]})")
    except Exception as ex:
        import traceback
        errors.append(f"rpeek selftest: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    finally:
        random.setstate(rng_state)
    return errors


def _aim(g, p):
    dx, dy, dz = p[0] - g.cam.pos[0], p[1] - g.cam.pos[1], p[2] - g.cam.pos[2]
    g.cam.yaw = math.atan2(dx, dz)
    g.cam.pitch = math.atan2(dy, math.hypot(dx, dz))


def rpeek_tips(sessions):
    """tip ข้ามรอบของ reaction·peek (ต้อง ≥ 3 รอบ) — คลิกแรกเข้าหัว % (Wilson) + ห่าง crosshair ค่ากลาง"""
    from .gundrills import wilson
    rows = [e for e in sessions if e.get("rp_n")]
    tips = []
    if len(rows) >= 3:
        n = sum(e["rp_n"] - e.get("rp_antic", 0) for e in rows)
        k = sum(e.get("rp_fs", 0) for e in rows)
        if n > 0:
            lo, hi = wilson(k, n)
            tips.append(f"คลิกแรกหลังหัวโผล่เข้าหัว {100 * k / n:.0f}% ({k}/{n}, ช่วง {100 * lo:.0f}–{100 * hi:.0f}%)" +
                        (" — flick ช้าลงนิดให้คลิกแรกโดน ดีกว่าคลิกรัวแก้" if hi < 0.6 else ""))
        offs = sorted(e["rp_off"] for e in rows if "rp_off" in e)
        if offs:
            tips.append(f"หัวโผล่ห่าง crosshair ค่ากลาง {offs[len(offs) // 2]:.0f}° ({len(rows)} รอบ) — "
                        f"ในเกมจริงวาง crosshair ที่ขอบระดับหัวรอไว้ = เหลือแค่ reaction")
    return tips
