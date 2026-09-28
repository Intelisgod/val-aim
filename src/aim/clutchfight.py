# -*- coding: utf-8 -*-
"""CLUTCH 1vN — การยิง/โดนยิง/จบรอบ (ClutchFightMixin ของ ClutchMixin)
• override จุดผูกห้องของท่อ GUNFIGHT แบบ dispatch ตาม self.mode (โหมดอื่น = super() เดิมทุกประการ — Game วาง ClutchMixin
  ไว้หน้า GunMixin): gun_wall_hit (กำแพง = รังสีแมพ) · gun_impact (รอยบนผิวแมพ + normal) · gun_bullet (แจ้งสมองบอท
  on_bot_damaged) · gun_on_kill (ไม่มีดวล/บันได/เกิดใหม่) · gun_rmb/gun_reload (ห้ามตอนถือ spike/วาง/กู้ + แจ้งสมองบอท)
• เหตุการณ์จากสมองบอท §11.1 (shot/step/heard/reload/defused/spotted) → ดาเมจ/เกราะ/tagging/ลูกศรทิศ/เสียง/ผลรอบ
• ตัดสินผล: ATK เก็บครบ/ระเบิด = ชนะ, หมดเวลา/ตาย/โดนกู้ = แพ้, ตายหลังวาง = brain.can_bots_defuse ; DEF ต้องกู้เท่านั้น"""
import math

from .config import C_GOLD, C_GREEN, C_RED
from . import clutchaudio, guns
from .clutchscen import END_DELAY, TAG_SLOW


class ClutchFightMixin:
    def clutch_can_fire(self):
        return (not self.cl_dead and self.cl_result is None and self.cl_equip == "gun" and self.gt >= self.cl_equip_until
                and self.cl_plant_t0 is None and self.cl_defuse_t0 is None)

    def clutch_shoot(self):
        """คลิกซ้าย (shoot) — ถือ spike = วาง (จัดการใน clutch_objective ตาม lmb_down) ; ถือปืน = ยิง"""
        if self.cl_equip == "gun":
            self.clutch_fire()

    def clutch_fire(self):
        if not self.clutch_can_fire():
            return
        n0 = self.gun_shots
        self.gun_shoot()
        if self.gun_shots > n0:
            self.clutch_after_fire(self.gun_shots - n0)

    def clutch_after_fire(self, n=1):
        g = self.gt
        if self.cl_air:
            self.cl_jump_shots += n                              # กระโดดยิง (โค้ช: "กระโดดยิง N นัด")
        if self.cl_rt is None and self.cl_contact_t is not None and g - self.cl_contact_t <= 2.0:
            self.cl_rt = round((g - self.cl_contact_t) * 1000)
        if g - self.cl_last_fight >= 1.0:
            self.cl_last_fight = g
            self.clutch_ev("fight")
        self._brain_call("on_player_shot", g, self.clutch_eye())

    def gun_rmb(self, down):
        if self.mode != "clutch":
            return super().gun_rmb(down)
        if down and not self.clutch_can_fire():
            return
        n0 = self.gun_shots
        super().gun_rmb(down)
        if self.gun_shots > n0:                                 # Classic คลิกขวา = ยิงชุด
            self.clutch_after_fire(self.gun_shots - n0)

    def gun_alt_spread(self):
        """clutch: กรวยคลิกขวา Classic + โทษลอย (+2.25° แทนโทษความเร็ว — guns.air_extra_deg alt) ; โหมดอื่น = เดิม"""
        sp = super().gun_alt_spread()
        if self.mode != "clutch":
            return sp
        return sp + guns.air_extra_deg(self.gun_weapon, self.gun_speed(), self.gun_crouch, self.cl_air,
                                       self.gt - self.cl_land_t, alt=True)

    def gun_reload(self):
        if self.mode != "clutch":
            return super().gun_reload()
        if self.cl_dead or self.cl_equip != "gun" or self.cl_result is not None:
            return
        if self.cl_plant_t0 is not None or self.cl_defuse_t0 is not None:
            return                                              # วาง/กู้อยู่ = มือไม่ว่าง (เดิมรีโหลดได้ระหว่างกู้)
        was = self.gun_reload_until
        super().gun_reload()
        if self.gun_reload_until > 0 >= was:
            self._brain_call("on_player_reload", self.gt, self.clutch_eye())

    def gun_wall_hit(self, wd):
        """clutch: กำแพง/พื้น/กล่อง = รังสีของแมพ (แหล่งความจริงเดียวของกระสุน §2.1) ; โหมดอื่น = กล่องห้องเดิม"""
        if self.mode != "clutch" or self.cmap is None:
            return super().gun_wall_hit(wd)
        o = self.clutch_eye()
        t = self.cmap.ray(o, wd, 250.0)
        if t is None or t <= 0.0:
            return None
        return t, (o[0] + wd[0] * t, o[1] + wd[1] * t, o[2] + wd[2] * t)

    def gun_impact(self, d):
        """clutch: รอยกระสุนบนผิวแมพจริง + normal ของหน้าที่โดน (GL วาด decal) — ไม่มีผนังหลังห้อง/พื้น y=0 สมมติ"""
        if self.mode != "clutch" or self.cmap is None:
            return super().gun_impact(d)
        wd = self.cam.to_world_dir(d)
        hit = self.gun_wall_hit(wd)
        if hit is None:
            return
        pt = hit[1]
        # normal ของหน้าที่โดน = กติกาเดียวกับตัววาด (clutchgl.surface_normal: จุดชนบนเส้นแบ่งช่อง + ช่องถัดไปสูงกว่า = ผนัง)
        # — เดิมเดาจากช่องห่าง ±3 ซม. ทำรอยบนพื้นเรียบตั้งชัน ~25% (รีวิว GL)
        from .clutchgl import surface_normal
        nrm = surface_normal(self.cmap, pt, wd)
        self.cl_marks.append((pt, nrm, self.gt))
        if len(self.cl_marks) > 60:
            del self.cl_marks[:len(self.cl_marks) - 60]

    def gun_bullet(self, d, quiet=False, burst_dead=()):
        """clutch: ท่อเดิมทุกอย่าง + แจ้งสมองบอทเมื่อกระสุนเราทำดาเมจ (on_bot_damaged ; ตายแจ้งใน gun_on_kill)"""
        if self.mode != "clutch" or self.brain is None:
            return super().gun_bullet(d, quiet, burst_dead)
        snap = [(b, len(b.damage_taken)) for b in self.bots if b.alive]
        zone = super().gun_bullet(d, quiet, burst_dead)
        for b, n in snap:
            if b.alive and len(b.damage_taken) > n:
                z, dmg = b.damage_taken[-1]
                self._brain_call("on_bot_damaged", b, self.gt, dmg, z, self.clutch_eye())
        return zone

    def gun_on_kill(self, b, zone, dist):
        """clutch: ไม่มีดวล/บันได/เกิดบอทใหม่ — นับคิล, kill feed, รอยบนแผนภาพ, แจ้งสมองบอท"""
        if self.mode != "clutch":
            return super().gun_on_kill(b, zone, dist)
        self.gun_kills += 1
        b.alive = False
        b.meta["dead_t"] = self.gt
        i = self.bots.index(b) + 1 if b in self.bots else 0
        self.clutch_feed(f"คุณ  {'HEADSHOT ' if zone == 'head' else ''}ศัตรู {i}  ({dist:.0f}m)", C_GREEN)
        self.add_float("HEADSHOT" if zone == "head" else "KILL", C_GOLD if zone == "head" else C_GREEN)
        self.play(self.snd_head if zone == "head" else self.snd_hit)
        self.cl_events.append(("kill", b.x, b.z, self.gt))
        self._brain_call("on_bot_killed", b, self.gt, self.clutch_eye())

    # ───────────────────────── เหตุการณ์จากสมองบอท (§11.1) ─────────────────────────
    def _brain_call(self, name, *a):
        fn = getattr(self.brain, name, None) if self.brain is not None else None
        if fn is None:
            return None
        try:
            return fn(*a)
        except Exception as ex:
            self._warn_once("clutch_" + name, f"CLUTCH: brain.{name} พัง ({ex})")
            return None

    def clutch_event(self, ev):
        k, b, g = ev.get("k"), ev.get("bot"), self.gt
        if k == "shot":
            fr, to = ev.get("from"), ev.get("to")
            if fr and to:
                self.cl_tracers.append((tuple(fr), tuple(to), g))
                self.cl_flashes.append((fr[0], fr[1], fr[2], g))
                self._clutch_audio(clutchaudio.gunshot, fr, weapon=getattr(b, "weapon", None))
            if b is not None:
                b.meta["cl_shot_t"] = g
            if ev.get("zone") and ev.get("dmg", 0) > 0 and not self.cl_dead:
                self.clutch_player_hit(float(ev["dmg"]), ev["zone"], fr or (b.x, 1.6, b.z), b)
        elif k in ("step", "reload"):
            pos = ev.get("pos") or ((b.x, b.y0, b.z) if b is not None else None)
            if pos is not None and k == "step":
                self._clutch_audio(clutchaudio.step, pos, bot=b)       # เท้าบอทรายตัว (keyword ใหม่ของทีม AUDIO)
            elif pos is not None:
                clutchaudio.reload(self, pos)
        elif k == "heard":
            self.cl_heard += 1
            self.cl_heard_t = g
        elif k == "defused":
            if self.clutch_side == "atk" and self.cl_spike["state"] == "planted":
                self.cl_spike["state"] = "defused"
                self.clutch_feed("ศัตรูกู้ SPIKE สำเร็จ", C_RED)
                self.clutch_end(False, "defused")
        elif k == "spotted" and b is not None:
            b.meta["cl_spotted_t"] = g

    def _clutch_audio(self, fn, pos, **kw):
        """เสียงตามตำแหน่งพร้อม keyword ใหม่ของทีม AUDIO (§13.2: gunshot weapon=, step bot=) — clutchaudio รุ่นที่ยังไม่รับ
        keyword (TypeError) = เรียกแบบเดิม fn(game, pos)"""
        try:
            fn(self, pos, **kw)
        except TypeError:
            fn(self, pos)

    def clutch_player_hit(self, dmg, zone, frm, bot):
        self.gun_hp, self.gun_shield = guns.apply_damage(self.gun_hp, self.gun_shield, dmg)
        self.gun_dmg_taken += dmg
        self.gun_flash = 0.25
        self.cl_tag_t = self.gt
        sp, cap = math.hypot(self.vel[0], self.vel[1]), self.gun_run_speed() * TAG_SLOW
        if sp > cap:                                             # tagging: ความเร็วตกทันที แล้วค่อยฟื้น (clutch_tag_mult)
            self.vel = [self.vel[0] * cap / sp, self.vel[1] * cap / sp]
        p = self.cam.pos
        self.cl_dmg_ind.append((math.atan2(frm[0] - p[0], frm[2] - p[2]), self.gt))
        clutchaudio.hurt(self)
        self.add_float(("HEAD -%d" if zone == "head" else "-%d") % dmg, C_RED)
        if self.gun_hp <= 0:
            i = self.bots.index(bot) + 1 if bot in self.bots else 0
            self.clutch_feed(f"ศัตรู {i}  {'HEADSHOT ' if zone == 'head' else ''}คุณ", C_RED)
            self.clutch_player_died()

    def clutch_player_died(self):
        """ตาย: หลังวางแล้ว (ATK) ตัดสินจากระยะเดินของบอทถึง spike (brain.can_bots_defuse §10.3) ; อื่น ๆ = แพ้"""
        self.cl_dead = True
        self.gun_deaths += 1
        self.gun_firing = False
        self.gun_unscope()
        self.clutch_plant_stop()
        self.clutch_defuse_stop()
        self.clutch_ev("death")
        sp = self.cl_spike
        if self.clutch_side == "atk" and sp["state"] == "planted":
            can = self._brain_call("can_bots_defuse", self.gt, (sp["x"], sp["z"]), sp["left"])
            self.clutch_end(not can, "died" if can else "detonated")
        else:
            self.clutch_end(False, "died")

    def clutch_check_end(self):
        if self.clutch_side == "atk" and self.bots and not any(b.alive for b in self.bots):
            self.clutch_end(True, "elim")                        # ATK: เก็บครบ = ชนะ (ก่อนหรือหลังวาง) ; DEF ต้องกู้เท่านั้น

    def clutch_end(self, win, why, delay=END_DELAY):
        if self.cl_result is not None:
            return
        self.cl_result = {"win": 1 if win else 0, "why": why, "t": self.gt}
        self.clutch_plant_stop()
        if self.cl_defuse_t0 is not None:
            self.clutch_defuse_stop()
        self.gun_firing = False
        self.pending_end = self.gt + delay

    def clutch_finalize(self):
        """end_game (ก่อนคิด PB): ผลที่ยังไม่ตัดสิน = จบรอบเองจากหน้าพัก (นับแพ้) ; คะแนน §8"""
        if self.cl_result is None:
            self.cl_result = {"win": 0, "why": "quit", "t": self.gt}
        sp = self.cl_spike or {}
        obj = sp.get("state") in ("planted", "detonated") if self.clutch_side == "atk" else sp.get("state") == "defused"
        if self.clutch_side == "atk" and self.cl_result["why"] == "defused":
            obj = True                                           # วางได้แล้ว (โดนกู้ทีหลัง) ก็ยังนับวางสำเร็จ
        self.cl_objective = bool(obj)
        self.score = 1000 * self.cl_result["win"] + 150 * self.gun_kills + 250 * (1 if obj else 0)
        self.cl_t_end = self.cl_result["t"]                     # เวลาตอนตัดสินผล — ไม่รวมป้ายผลค้าง END_DELAY 1.6 วิ
        self.cl_bots_end = [(b.x, b.z, b.alive) for b in self.bots]
