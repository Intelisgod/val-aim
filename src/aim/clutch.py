# -*- coding: utf-8 -*-
"""โหมด CLUTCH 1vN (mode id "clutch") — ClutchMixin บน Game: เหลือคนเดียว เลาะไปวาง spike (ATK) / retake แล้วกู้ (DEF)
บนแมพจำลอง (aim/clutchmap.py) ปะทะบอท 1–5 ตัว — สัญญา/ค่าคงที่ docs/CLUTCH_DESIGN.md §5, §10 (ทับของเดิม), §11
  • สมองบอท = aim/clutchbots.py (ทีม BOTS, §11.1) · โลก 3D = aim/clutchgl.py (ทีม GL, §11.2) — import แบบ lazy/กันพัง:
    ไม่มีโมดูล/พัง → บอทหุ่นนิ่ง (_DummyBrain) และภาพสำรอง software (ไม่มีห้องซ้อมเดิมเด็ดขาด) เกมไม่ล่ม
  • ปืนผู้เล่น = ท่อ GUNFIGHT เดิมทั้งชุด (gun_shoot/gun_rmb/gun_reload/Stability) — โหมดนี้ override จุดเดียวที่ผูกห้อง:
    gun_wall_hit (กำแพง = รังสีแมพ) / gun_impact (รอยบนผิวแมพ) / gun_bullet (แจ้งดาเมจให้สมองบอท) / gun_on_kill (ไม่มีดวล/เกิดใหม่)
  • ตัวจับเวลา/ถือกด ทุกอันใช้เวลาเกม gt (หยุดตอนพัก) ; หน้าต่างหลุดโฟกัส = พักเอง + ล้างปุ่มค้าง
HUD = clutchhud.py · หน้าผล/ประวัติ = clutchresults.py · เสียง = clutchaudio.py · หน้าตั้งค่า = clutchsetup.py"""
import math
import random
import time

import pygame

from .config import EYE_Y, C_GOLD, mode_current
from . import clutchaudio, duel, guns
from .clutchhud import ClutchHudMixin
from .clutchresults import ClutchResultsMixin
from .clutchfight import ClutchFightMixin
from .clutchmove import ClutchMoveMixin
from .clutchscen import (DEFUSE_DY, DEFUSE_HALF, DEFUSE_R, DEFUSE_T, FAKE_DEFUSE_S,
                         PLANT_T, SPIKE_EQUIP_T, SPIKE_T, TAG_REC, TAG_SLOW, YARD, _DummyBrain, _PV, _ground,
                         _module, load_map, norm_cfg, pick_scenario, scen_left)
from .clutchmap import STEP_UP


def prep_assets(cm):
    """งานหนักของแมพทำก่อนเล่น (หน้าตั้งค่า/เริ่มนับถอยหลัง) ไม่ใช่เฟรมแรกของรอบ: กราฟ nav (~0.3–0.5 วิ บนแมพจริง —
    ClutchBrain.prepare สร้างเองถ้ายังไม่มี) + ข้อมูลอัป GPU ของ clutchgl (prepare ถ้ามี — ไม่อยู่ในสัญญา §11.2 จึงเรียกแบบ
    getattr) ; ทำซ้ำ = no-op (cache ในตัว) ; พัง = ข้าม (เฟรมแรกทำเอง)"""
    try:
        cm.ensure_nav()
        cm.player_map()                 # พื้นของผู้เล่นรวมหลังกล่อง (§13.1 ; ~40–50 ms บนแมพจริง — ไม่ให้ไปกระตุกเฟรมแรก)
    except Exception:
        pass
    gl = _module("gl")
    fn = getattr(gl, "prepare", None) if gl is not None else None
    if fn is not None:
        try:
            fn(cm)
        except Exception:
            pass


class ClutchMixin(ClutchHudMixin, ClutchResultsMixin, ClutchFightMixin, ClutchMoveMixin):
    # ───────────────────────── ตั้งค่า/เริ่มรอบ ─────────────────────────
    def clutch_cfg(self):
        return norm_cfg(self.S.get("clutch"))

    def clutch_duel_tier(self, weapon):
        """ระดับบอท "ตามแรงค์ DUEL ของฉัน" = ตรรกะ gun_fixed_tier (บันไดดวลของปืนนี้ → Vandal → Gold I)"""
        hist = (getattr(self, "data", None) or {}).get("history", [])
        st = duel.ladder_start(hist, "vandal" if weapon == "operator" else weapon, mode_current)
        if st is None:
            st = duel.ladder_start(hist, "vandal", mode_current)
        return duel.LADDER_START if st is None else duel.clamp_tier(st)

    def clutch_tier_of(self, cfg):
        return self.clutch_duel_tier(cfg["weapon"]) if cfg["tier"] == "duel" else int(cfg["tier"])

    def reset_clutch(self):
        """สถานะต่อรอบ (reset_round เรียกทุกโหมด — ถูกเสมอ) ; สิ่งที่ข้ามรอบ (clutch_last/_saved) ไม่แตะ"""
        self.brain = self.cmap = self.clutch_scen = self.cl_pv = self.cl_spike = None
        self.clutch_scen_i, self.clutch_seed, self.clutch_side, self.clutch_n, self.clutch_tier = -1, 0, "atk", 1, 0
        self.cl_feet, self.cl_vy, self.cl_eye = 0.0, 0.0, EYE_Y
        self.cl_equip, self.cl_equip_until = "gun", 0.0
        self.cl_plant_t0 = self.cl_defuse_t0 = self.cl_round_left = self.cl_result = None
        self.cl_defuse_base, self.cl_hold, self.cl_tab = 0.0, set(), False
        self.cl_dead, self.cl_ready, self.cl_tag_t = False, False, -9.0
        self.cl_heard, self.cl_heard_t, self.cl_multi, self.cl_multi_on = 0, -9.0, 0, False
        self.cl_contact_t = self.cl_rt = self.cl_plant_left = self.cl_defuse_left = None
        self.cl_any_seen, self.cl_fake, self.cl_defuse_n = False, 0, 0
        self.cl_feed, self.cl_dmg_ind, self.cl_tracers, self.cl_flashes, self.cl_marks = [], [], [], [], []
        self.cl_path, self.cl_events, self.cl_next_path, self.cl_last_fight = [], [], 0.0, -9.0
        self.cl_bot_defuse, self.cl_bots_end, self.cl_t_end, self.cl_warn = None, [], None, None
        self.cl_snd, self.cl_objective = {}, False
        self.cl_focus_pause = False     # หลุดโฟกัสตอนนับถอยหลัง → เริ่มรอบแล้วพักทันที (clutch_begin)
        self.reset_clutch_move()        # กระโดด/ตก/ขาหด/เวลาแตะพื้น (clutchmove.py §13)

    def clutch_setup_round(self, restart=False):
        """เรียกจาก start_countdown หลังสร้างกล้องใหม่ (เห็นจุดเกิดจริงตั้งแต่นับถอยหลัง) — โหลดแมพ, เลือกฉาก (seed เก็บไว้
        ให้ "ฉากเดิมอีกครั้ง"/R ระหว่างพัก), สร้างสมองบอท, วางผู้เล่น/spike"""
        cfg = self.clutch_cfg()
        last = getattr(self, "clutch_last", None)
        same = (restart or getattr(self, "clutch_same_next", False)) and last is not None
        self.clutch_same_next = False
        slug = cfg["map"]
        try:
            cm = load_map(slug)
        except Exception as ex:
            self.cl_warn = f"โหลดแมพ {cfg['map']} ไม่ได้ — ใช้ Training Yard แทน ({type(ex).__name__})"
            cm, slug, same = load_map(YARD), YARD, False
        if cfg["site"] != "any" and cfg["site"] not in (cm.sites or {}):
            cfg["site"] = "any"     # ไซต์ C ค้างจากแมพ 3 ไซต์ (ไฟล์เซฟ/ปุ่มผล) บนแมพ 2 ไซต์ = สุ่ม — เดิมได้ฉากสร้างเองทุกรอบ
        key = (slug, cfg["side"], cfg["n"], cfg["site"])
        same = same and last["key"] == key
        prep_assets(cm)
        seed = last["seed"] if same else random.getrandbits(31)
        if same:
            i, sc = last["scen_i"], dict(last["scen"])
        else:
            avoid = last["scen_i"] if last is not None and last["key"] == key else None
            i, sc = pick_scenario(cm, cfg["side"], cfg["n"], cfg["site"], random.Random(seed), avoid,
                                  run_speed=guns.WEAPONS[cfg["weapon"]]["run_speed"])
        sc.setdefault("s", "A")
        self.clutch_last = {"key": key, "seed": seed, "scen_i": i, "scen": dict(sc)}
        self.cmap, self.clutch_scen, self.clutch_scen_i, self.clutch_seed = cm, sc, i, seed
        self.clutch_side, self.clutch_n = cfg["side"], cfg["n"]
        self.gun_weapon, self.gun_drill = cfg["weapon"], "duel"   # ดริลอื่นมีกติกาห้อง (repo pre-fire ฯลฯ) — clutch ใช้ duel เสมอ
        self.reset_gun()
        self.gun_stab.extra = self.clutch_air_err               # โทษลอย/แตะพื้น (§13.1) — ทั้งนัดที่ยิงและ crosshair ถ่าง
        self.clutch_tier = self.clutch_tier_of(cfg)
        self.brain = self._clutch_brain(cm, sc, cfg, random.Random(seed + 1))
        self.bots = self.brain.bots                             # gun_bullet ไล่ self.bots — ลิสต์เดียวกับของสมองบอท
        px, pz, yaw = sc["p"][0], sc["p"][1], sc["p"][2]
        self.cl_feet = _ground(cm, px, pz)
        self.cl_eye = self.cl_feet + EYE_Y
        self.cam.pos = [px, self.cl_eye, pz]
        self.cam.yaw, self.cam.pitch = yaw, 0.0
        if self.clutch_side == "atk":
            self.cl_spike = {"state": "carried", "x": px, "y": self.cl_feet, "z": pz, "left": None}
            self.cl_round_left = scen_left(sc, "atk")
        else:
            k = sc.get("k") or (cm.sites.get(sc["s"]) or {}).get("c") or [px, pz]
            self.cl_spike = {"state": "planted", "x": k[0], "y": _ground(cm, k[0], k[1]), "z": k[1],
                             "left": scen_left(sc, "def")}
        self.cl_pv = self._clutch_pv_new()
        self.clutch_hud_prepare()
        clutchaudio.prepare(self)

    def _clutch_brain(self, cm, sc, cfg, rng):
        """ClutchBrain ตามสัญญา §11.1 — ปืนบอทตามกติกา gun_bot_weapon (เราถือ Op → บอทถือ Vandal) ;
        ไม่มีโมดูล/สร้างไม่ได้ → หุ่นนิ่ง (บอกบนจอ)"""
        fac = getattr(self, "clutch_brain_factory", None)       # selftest ฉีดตัวปลอม
        if fac is None:
            mod = _module("bots")
            fac = getattr(mod, "ClutchBrain", None) if mod is not None else None
        bw = "vandal" if cfg["weapon"] == "operator" else cfg["weapon"]
        if fac is not None:
            try:
                return fac(cm, sc, self.clutch_side, self.clutch_tier, bw, rng, 0.0, placement=cfg["placement"])
            except Exception as ex:
                self._warn_once("clutchbrain", f"CLUTCH: สร้างสมองบอทไม่ได้ ({ex}) — หุ่นนิ่ง")
        self.cl_warn = self.cl_warn or "สมองบอทยังไม่พร้อม — ศัตรูเป็นหุ่นนิ่ง (ซ้อมเดิน/วาง/กู้ได้)"
        return _DummyBrain(cm, sc, self.clutch_side, self.clutch_tier, bw, rng, 0.0)

    def _clutch_pv_new(self):
        cls = None
        if getattr(self, "clutch_brain_factory", None) is None:
            mod = _module("bots")
            cls = getattr(mod, "PlayerView", None) if mod is not None else None
        try:
            return cls() if cls is not None else _PV()
        except Exception:
            return _PV()

    PREP_BUDGET_S = 0.002       # งบเวลาเตรียม nav ต่อเฟรมนับถอยหลัง (60 fps ต้อง ~1,200 โหนด/เฟรม ; เกินนี้กิน 240 Hz)

    def clutch_countdown_tick(self):
        """ระหว่างนับถอยหลัง (game.run): เตรียม nav ของบอทแบบหั่นเวลา (§11.1 prepare) — ไม่ให้เฟรมแรกของรอบกระตุก
        งบเป็นเวลา (≥ prepare(500) หนึ่งครั้ง/เฟรม) ไม่ใช่จำนวนโหนดคงที่: เดิม 500/เฟรมที่ 60 fps × 201 เฟรมไม่พอฝั่ง ATK
        → เฟรมแรกของรอบ (clutch_begin ทำที่เหลือ) กระตุก 8–84 ms ทุกรอบ/ทุก R"""
        if self.brain is not None and not self.cl_ready:
            t_end = time.perf_counter() + self.PREP_BUDGET_S
            try:
                while True:
                    self.cl_ready = bool(self.brain.prepare(500))
                    if self.cl_ready or time.perf_counter() >= t_end:
                        break
            except Exception as ex:
                self._warn_once("clutchprep", f"CLUTCH: prepare พัง ({ex})")
                self.cl_ready = True

    def clutch_begin(self):
        """begin_play: เตรียม nav ที่เหลือให้ครบก่อนเริ่มจริง (เทส/เครื่องช้าที่นับถอยหลังไม่ทัน) ; หลุดโฟกัสระหว่าง
        นับถอยหลัง = เริ่มรอบ (begin_play ทำบัญชีเฟรม/PB ครบแล้ว) แล้วพักทันที — กดเล่นต่อ = นับ 3 วิแบบปกติ"""
        for _ in range(2000):
            if self.brain is None or self.cl_ready:
                break
            try:
                self.cl_ready = bool(self.brain.prepare(5000))
            except Exception as ex:
                self._warn_once("clutchprep", f"CLUTCH: prepare พัง ({ex})")
                break
        self.cl_ready = True
        self.cl_next_path = 0.0
        if self.cl_focus_pause:
            self.cl_focus_pause = False
            self.state = "pause"
            self.grab_mouse(False)

    def clutch_leave(self):
        """ออกจาก clutch ไปเมนู (game.go_menu / ตั้งค่า→กลับ): คืนโหมด/ปืน/ดริลเดิมของเมนู — แผงเมนูไม่มีแรงค์ปลอมของ clutch"""
        sv = getattr(self, "clutch_saved", None)
        if self.mode == "clutch" and sv:
            self.mode, self.gun_weapon, self.gun_drill = sv
        self.clutch_saved = None
        self.cl_hold, self.cl_tab = set(), False

    def clutch_start(self, same=False):
        """เริ่มรอบ clutch จากหน้าตั้งค่า/ปุ่มหน้าผล (same = ฉากเดิมอีกครั้ง)"""
        if self.mode != "clutch" and not getattr(self, "clutch_saved", None):
            self.clutch_saved = (self.mode, self.gun_weapon, self.gun_drill)
        self.mode, self.flow = "clutch", None
        self.clutch_same_next = bool(same)
        self.start_countdown()

    # ───────────────────────── ต่อเฟรม ─────────────────────────
    def update_clutch(self, dt):
        if self.cmap is None or self.brain is None:
            return
        self.gun_dt = dt
        over = self.cl_result is not None
        self.clutch_move(dt)
        self.clutch_weapon_tick(dt)
        if not over:
            self.clutch_objective(dt)
            try:
                evs = self.brain.update(dt, self.gt, self.clutch_pv()) or []
            except Exception as ex:
                self._warn_once("clutchbrain_up", f"CLUTCH: สมองบอทพัง ({ex}) — บอทหยุด")
                evs = []
            for ev in evs:
                if isinstance(ev, dict):
                    self.clutch_event(ev)
            bd = None
            try:
                bd = self.brain.bot_defuse()
            except Exception:
                pass
            self.cl_bot_defuse = bd
        self.clutch_perceive()
        if self.cl_result is None:
            self.clutch_check_end()
        self.clutch_record()
        clutchaudio.update(self, dt)
        g = self.gt
        self.cl_tracers = [x for x in self.cl_tracers if g - x[2] < 0.25]
        self.cl_flashes = [x for x in self.cl_flashes if g - x[3] < 0.08]
        self.cl_dmg_ind = [x for x in self.cl_dmg_ind if g - x[1] < 1.2]
        if self.cl_marks and g - self.cl_marks[0][2] > 6.0:
            self.cl_marks = [m for m in self.cl_marks if g - m[2] <= 6.0]

    def clutch_rooted(self):
        return self.cl_plant_t0 is not None or self.cl_defuse_t0 is not None or self.cl_dead

    def clutch_tag_mult(self):
        k = (self.gt - self.cl_tag_t) / TAG_REC
        return 1.0 if k >= 1.0 else TAG_SLOW + (1.0 - TAG_SLOW) * max(0.0, k)

    def clutch_weapon_tick(self, dt):
        w = self.gun_w()
        if self.gun_flash > 0:
            self.gun_flash = max(0.0, self.gun_flash - dt)
        if self.gun_reload_until > 0 and self.gt >= self.gun_reload_until:
            self.gun_reload_until = 0.0
            self.gun_mag = w["mag"]
        if self.gun_firing and w["auto"]:
            self.clutch_fire()
        self.gun_stab.update(self.gt, dt)

    def clutch_eye(self):
        return (self.cam.pos[0], self.cam.pos[1], self.cam.pos[2])

    # ───────────────────────── spike: วาง / กู้ / เวลา ─────────────────────────
    def clutch_in_zone(self):
        return self.cmap.zone_at(self.cam.pos[0], self.cam.pos[2]) is not None

    def clutch_plant_floor_ok(self):
        """ใต้จุดศูนย์กลางตัวเป็นพื้นระดับเดียวกับเท้า (±STEP_UP) — ยืนคร่อมขอบ ledge โดยตัวยังเกาะขอบบน = พื้นใต้จุดอยู่ชั้นล่าง
        spike จะไปลงชั้นล่าง (สมองบอทใช้ floor_y ใต้จุด) ขณะที่ภาพ/ระยะกู้ของโหมดอยู่ชั้นบน → ห้ามวางตรงนั้น
        พื้นของผู้เล่น (player_map) นับหลังกล่องด้วย — ยืนบนกล่องในพื้นที่วาง = วางบนกล่องได้ (§13.1 ; กติกาโซนเดิม)"""
        fy = self.cmap.player_map().floor_y(self.cam.pos[0], self.cam.pos[2])
        return fy is not None and abs(fy - self.cl_feet) <= STEP_UP

    def clutch_can_plant(self):
        return (not self.cl_dead and self.cl_equip == "spike" and self.gt >= self.cl_equip_until
                and self.cl_spike["state"] == "carried" and self.clutch_in_zone() and not self.cl_air
                and self.clutch_plant_floor_ok())

    def clutch_can_defuse(self):
        sp = self.cl_spike
        if self.cl_dead or sp is None or sp["state"] != "planted" or self.cl_air:
            return False                                         # เริ่ม/กู้ต่อกลางอากาศไม่ได้ (ต้องยืนบนผิว เหมือนวาง)
        p = self.cam.pos
        if math.hypot(p[0] - sp["x"], p[2] - sp["z"]) > DEFUSE_R or abs(self.cl_feet - sp["y"]) > DEFUSE_DY:
            return False
        return not self.cmap.blocked(self.clutch_eye(), (sp["x"], sp["y"] + 0.15, sp["z"]))

    def clutch_objective(self, dt):
        g, sp = self.gt, self.cl_spike
        if self.clutch_side == "atk":
            if sp["state"] == "carried":
                self.cl_round_left = max(0.0, self.cl_round_left - dt)
                if self.cl_plant_t0 is not None:
                    if not self.lmb_down or self.cl_dead or self.cl_equip != "spike":
                        self.clutch_plant_stop()
                    elif g - self.cl_plant_t0 >= PLANT_T:
                        self.clutch_planted()
                elif self.lmb_down and self.clutch_can_plant():
                    self.cl_plant_t0, self.cl_plant_left = g, round(self.cl_round_left, 1)
                    self.vel = [0.0, 0.0]
                    self.clutch_ev("plant_start")
                    self._brain_call("on_plant_start", g, self.clutch_eye())
                if sp["state"] == "carried" and self.cl_round_left <= 0.0:
                    self.clutch_end(False, "time")
            elif sp["state"] == "planted":
                sp["left"] = max(0.0, sp["left"] - dt)
                if sp["left"] <= 0.0:
                    sp["state"] = "detonated"
                    self.clutch_end(True, "detonated")
            return
        if sp["state"] != "planted":
            return
        sp["left"] = max(0.0, sp["left"] - dt)
        held = "4" in self.cl_hold or "f" in self.cl_hold
        if self.cl_defuse_t0 is not None:
            prog = self.cl_defuse_base + (g - self.cl_defuse_t0)
            if not held or not self.clutch_can_defuse():
                self.clutch_defuse_stop(released=not held)
            elif prog >= DEFUSE_T:
                sp["state"] = "defused"
                self.cl_defuse_t0 = None
                self.clutch_ev("defuse")
                alive = any(b.alive for b in self.bots)
                self.clutch_end(True, "ninja" if alive else "defused")
                return
        elif held and self.clutch_can_defuse():
            self.cl_defuse_t0, self.cl_defuse_left = g, round(sp["left"], 1)
            self.cl_defuse_n += 1
            self.vel = [0.0, 0.0]
            self.gun_firing = False
            self.gun_unscope()
            self.gun_reload_until = 0.0                          # เริ่มกู้ = ยกเลิกรีโหลดที่ค้าง (แม็กเท่าเดิม — แบบสลับอาวุธ)
            self._brain_call("on_defuse_start", g, self.clutch_eye(), self.cl_defuse_base >= DEFUSE_HALF)
        if sp["left"] <= 0.0 and sp["state"] == "planted":
            sp["state"] = "detonated"
            self.clutch_end(False, "detonated")

    def clutch_defuse_prog(self):
        """วินาทีที่กู้แล้ว (รวมที่เก็บไว้ครึ่งทาง 3.5 วิ)"""
        if self.cl_defuse_t0 is None:
            return self.cl_defuse_base
        return min(DEFUSE_T, self.cl_defuse_base + (self.gt - self.cl_defuse_t0))

    def clutch_defuse_stop(self, released=False):
        """หยุดกู้ — released = ผู้เล่นปล่อยปุ่มเอง: เท่านั้นที่นับ "กู้หลอก" (ตาย/ระเบิด/จบรอบ/หลุดโฟกัส/หลุดระยะ ไม่นับ)"""
        if self.cl_defuse_t0 is None:
            return
        run = self.gt - self.cl_defuse_t0
        if self.cl_defuse_base + run >= DEFUSE_HALF:
            self.cl_defuse_base = DEFUSE_HALF                    # ครึ่งทางแรกเก็บไว้ (checkpoint 3.5 วิ)
        if released and run < FAKE_DEFUSE_S:
            self.cl_fake += 1
        self.cl_defuse_t0 = None
        self.cl_equip_until = self.gt + guns.WEAPONS[self.gun_weapon].get("equip", 1.0)
        self._brain_call("on_defuse_stop", self.gt)

    def clutch_plant_stop(self):
        """ยกเลิกการวาง (ปล่อยคลิก/สลับปืน/ตาย) — ความคืบหน้ารีเซ็ต (§10.2)"""
        if self.cl_plant_t0 is None:
            return
        self.cl_plant_t0 = None
        self._brain_call("on_plant_cancel", self.gt)

    def clutch_planted(self):
        p, sp = self.cam.pos, self.cl_spike
        fy = self.cmap.player_map().floor_y(p[0], p[2])         # = spike_y ของสมองบอท (floor_y ใต้จุด ; บนกล่อง = y ที่ส่งไป
        #                                                         on_planted = หลังกล่อง) — ภาพ/ระยะกู้ตรงกัน
        sp.update(state="planted", x=p[0], y=self.cl_feet if fy is None else fy, z=p[2], left=SPIKE_T,
                  site=self.cmap.zone_at(p[0], p[2]))           # ไซต์ที่วางจริง (history) — ฉากป้าย B อาจวางได้ที่ A
        self.cl_plant_t0 = None
        self.cl_equip = "gun"
        self.cl_equip_until = self.gt + guns.WEAPONS[self.gun_weapon].get("equip", 1.0)
        self.clutch_ev("plant")
        self.clutch_feed("วาง SPIKE แล้ว", C_GOLD)
        self._brain_call("on_planted", self.gt, (p[0], self.cl_feet, p[2]))

    def clutch_equip(self, what):
        """4 = หยิบ spike (ATK ก่อนวาง) · 1/2 = กลับปืน — เวลาหยิบตาม §10.2 ; ระหว่างหยิบยิงไม่ได้"""
        if self.cl_dead or self.cl_result is not None or what == self.cl_equip:
            return
        if what == "spike":
            if self.clutch_side != "atk" or self.cl_spike["state"] != "carried":
                return
            self.gun_reload_until = 0.0                          # สลับอาวุธ = ยกเลิกรีโหลด (แม็กเท่าเดิม)
            self.gun_unscope()
            self.cl_equip, self.cl_equip_until = "spike", self.gt + SPIKE_EQUIP_T
        else:
            self.clutch_plant_stop()
            self.cl_equip = "gun"
            self.cl_equip_until = self.gt + guns.WEAPONS[self.gun_weapon].get("equip", 1.0)
        self.gun_firing = False

    def clutch_key(self, key, down):
        """คีย์เฉพาะโหมด (input.py เรียกตอน play) — 4 หยิบ spike/ค้างกู้ · F ค้างกู้ · 1/2 ปืน · Tab แมพใหญ่ · Space กระโดด
        ; True = ใช้คีย์นี้ (Space ของหน้าผล = ปุ่ม NEXT ของคิว อยู่คนละ state — ไม่ผ่านที่นี่)"""
        name = {pygame.K_4: "4", pygame.K_KP4: "4", pygame.K_f: "f", pygame.K_1: "1", pygame.K_2: "1",
                pygame.K_TAB: "tab", pygame.K_SPACE: "jump"}.get(key)
        if name is None:
            return False
        if name == "jump":
            self.clutch_jump_key(down)
            return True
        if not down:
            self.cl_hold.discard(name)
            if name == "tab":
                self.cl_tab = False
            return True
        if name == "tab":
            self.cl_tab = True
        elif name == "1":
            self.clutch_equip("gun")
        else:
            self.cl_hold.add(name)
            if name == "4" and self.clutch_side == "atk":
                self.clutch_equip("spike")
        return True

    def clutch_focus_lost(self):
        """หน้าต่างหลุดโฟกัส (alt-tab): พักเอง + ล้างทุกปุ่มที่ค้าง — KEYUP อาจไม่มาเลย (เดินค้าง/ยิงค้าง/กู้ค้าง)
        กำลังกู้ = หยุดกู้ตรงนี้ (ไม่ใช่ "ปล่อยปุ่ม" → ไม่นับกู้หลอก ; เวลาเกมหยุดระหว่างพัก ผลเท่าหยุดตอนกลับมา)
        นับถอยหลังอยู่ = จำไว้ แล้วพักทันทีที่รอบเริ่ม (clutch_begin) — เดิมรอบเริ่มเล่นเองทั้งที่ไม่มีคนอยู่ (ตาย = แพ้ลง history)"""
        if self.cl_defuse_t0 is not None:
            self.clutch_defuse_stop()
        self.keys_down = set()
        self.cl_hold, self.cl_tab = set(), False
        self.lmb_down = self.gun_firing = self.gun_crouch = False
        self.r_hold_since = None
        self.cl_jump_q = False                                   # Space ที่กดก่อนหลุดโฟกัสไม่กระโดดตอนกลับมา
        if self.state == "play":
            self.state = "pause"
            self.grab_mouse(False)
        elif self.state == "countdown":
            self.cl_focus_pause = True

    def clutch_focus_gained(self):
        """alt-tab กลับมาก่อนนับถอยหลังจบ = ไม่ต้องพักตอนเริ่มรอบ"""
        self.cl_focus_pause = False

    # ───────────────────────── การรับรู้ของผู้เล่น + บันทึกเส้นทาง ─────────────────────────
    def clutch_perceive(self):
        """ผู้เล่นเห็นบอทตัวไหน (ในกรอบภาพ + LOS จริงของแมพ) → b.exposed (ท่อยิง/shot map) + มินิแมพ (เห็นภายใน 2 วิ)
        + จุดปะทะแรก (reaction) + โดนเห็นพร้อมกัน ≥ 2 ตัว (สมองบอท seen_count)"""
        eye, f = self.clutch_eye(), self.fl()
        W, H = self.W, self.H
        to_cam, blocked = self.cam.to_cam, self.cmap.blocked
        any_seen = False
        for b in self.bots:
            seen = False
            if b.alive and not self.cl_dead and math.hypot(b.x - eye[0], b.z - eye[2]) < 90.0:
                # จุดตัวอย่างที่ "อยู่ในกรอบภาพจริง" และไม่ถูกบัง อย่างน้อยหนึ่งจุด — เดิมเช็คกรอบที่จุดกลางตัว ×1.05 + LOS
                # จุดใดก็ได้ = บอทพ้นขอบจอ ~35 px ยังนับว่าเห็น (มินิแมพ/shot map รั่ว)
                for p in b.points():
                    cx, cy, cz = to_cam(p)
                    if cz > 0.1 and 0 <= W / 2 + f * cx / cz < W and 0 <= H / 2 - f * cy / cz < H \
                            and not blocked(eye, p):
                        seen = True
                        break
            b.exposed = seen
            if seen:
                b.meta["pseen"] = self.gt
                b.meta["pseen_xz"] = (b.x, b.z)                 # มินิแมพวาดจุดที่เห็นล่าสุด — ไม่ตามตัวจริงหลังหลุดสายตา
                any_seen = True
        if any_seen and not self.cl_any_seen:
            self.cl_contact_t = self.gt
        self.cl_any_seen = any_seen
        n = 0
        try:
            n = int(self.brain.seen_count() or 0)
        except Exception:
            pass
        if n >= 2 and not self.cl_multi_on:
            self.cl_multi += 1
        self.cl_multi_on = n >= 2

    def clutch_ev(self, kind):
        p = self.cam.pos
        self.cl_events.append((kind, p[0], p[2], self.gt))

    def clutch_feed(self, txt, col):
        self.cl_feed.append((txt, col, self.gt))
        del self.cl_feed[:-5]

    def clutch_record(self):
        """เส้นทางผู้เล่นทุก 0.2 วิ (x, z, วิ่ง=ได้ยินเสียงเท้า) — เก็บในหน่วยความจำเท่านั้น (history เล็กเสมอ §8)"""
        if self.gt < self.cl_next_path or self.cl_dead or len(self.cl_path) >= 900:
            return
        self.cl_next_path = self.gt + 0.2
        run = math.hypot(self.vel[0], self.vel[1]) > guns.WALK_KNEE * self.gun_run_speed()
        self.cl_path.append((self.cam.pos[0], self.cam.pos[2], run))

    # ───────────────────────── วาดโลก + ข้อมูลให้ GL (§11.2) ─────────────────────────
    def clutch_view(self):
        g, sp = self.gt, self.cl_spike
        bots = [self.clutch_view_bot(b, g) for b in self.bots]  # + vx/vz/pitch/walk/reload (§13.2)
        spike = None
        if sp is not None and sp["state"] in ("planted", "defused", "carried"):
            p = self.cam.pos
            xyz = (p[0], self.cl_feet, p[2]) if sp["state"] == "carried" else (sp["x"], sp["y"], sp["z"])
            spike = {"x": xyz[0], "y": xyz[1], "z": xyz[2], "state": sp["state"],
                     "blink": clutchaudio.blink(self) if sp["state"] == "planted" else 0.0}
        zh = self.clutch_scen.get("s") if (self.cl_equip == "spike" and self.clutch_scen) else None
        return {"map": self.cmap, "yaw": self.cam.yaw, "pitch": self.cam.pitch, "pos": tuple(self.cam.pos),
                "f": self.fl(), "W": self.W, "H": self.H, "t": g, "bots": bots, "spike": spike,
                "tracers": [(a, b, g - t0) for a, b, t0 in self.cl_tracers],
                "flashes": [(x, y, z, g - t0) for x, y, z, t0 in self.cl_flashes],
                "marks": [(pt, n, g - t0) for pt, n, t0 in self.cl_marks], "zone_hint": zh,
                "vm": self.clutch_vm()}                         # viewmodel มุมมองบุคคลที่หนึ่ง (§13.2 — clutchmove)

    def clutch_gpu_ready(self):
        """GPU world ใช้ได้ + มีตัววาดแมพ (clutchgl) + ยังไม่พังในเซสชันนี้ — หน้าตั้งค่าปิด START ถ้า False"""
        return bool(self.gpu_world_active() and _module("gl") is not None and not getattr(self, "_clutch_gl_off", False)
                    and not getattr(self, "_clutch_gl_failed", False))    # ธงล้มของ clutchgl เอง (ทีม GL)

    def clutch_draw_world(self):
        """worlddraw._draw_world_raw → โลก clutch: GL (clutchgl.draw_clutch_world) หรือภาพสำรอง — ไม่วาดห้องซ้อมเดิมเด็ดขาด"""
        if self.cmap is not None and getattr(self, "gpu", False) and getattr(self, "_gl", None) is not None:
            gl = _module("gl")
            ok = False
            if gl is not None and not getattr(self, "_clutch_gl_off", False):
                try:
                    ok = bool(gl.draw_clutch_world(self, self.clutch_view()))
                except Exception as ex:                          # สัญญาบอก "ไม่ raise" — raise = พังจริง ปิดเลย
                    self._warn_once("clutchgl", f"CLUTCH GL fail ({ex}) — ภาพสำรอง")
                    self._clutch_gl_off = True
                # False ติดกันครึ่งวิ = ปิด GL ของ clutch ทั้งเซสชัน (GPU world ของโหมดอื่นไม่โดน) ; False ครั้งเดียว = ภาพสำรองเฟรมนั้น
                self._clutch_gl_nok = 0 if ok else getattr(self, "_clutch_gl_nok", 0) + 1
                if self._clutch_gl_nok >= 30:
                    self._clutch_gl_off = True
            if ok:
                self._world_gpu_frame = True
                self._track_dirty = self.state == "play" and self.flow is None and self.resume_cd <= 0
                return
        self.clutch_draw_soft()
