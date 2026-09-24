# -*- coding: utf-8 -*-
"""วาดโลก 3D + crosshair + HUD — WorldDrawMixin (ย้าย verbatim)"""

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

# ZNEAR มาจาก config (ผ่าน import * ด้านบน) — ใช้ร่วมกับ glrender ให้ clip ตรงกันทั้งสองตัววาด

# offset วงแหวน telegraph ของ dodge aoe (ทุก 30°) — ค่าคงที่ คำนวณครั้งเดียว (เดิม 36 trig call/hazard/เฟรม)
_AOE_RING = [(math.cos(math.radians(a)) * DODGE_AOE_R, math.sin(math.radians(a)) * DODGE_AOE_R)
             for a in range(0, 360, 30)]
_AOE_POSTS = _AOE_RING[::2]        # เสาแนวตั้งทุก 60° — วงบนพื้นอยู่ใต้ขอบจอ แต่ยอดเสาโผล่ในจอเสมอ


def _clip_near(cam_pts):
    """Sutherland-Hodgman clip รูปหลายเหลี่ยม (จุด cam-space x,y,z) กับระนาบ z >= ZNEAR
    คืนรายการจุด cam-space ที่อยู่หน้า near plane (มุมที่หลุดหลังกล้องถูกตัดเป็นจุดบนระนาบ)"""
    out = []
    n = len(cam_pts)
    for i in range(n):
        cx, cy, cz = cam_pts[i]
        nx, ny, nz = cam_pts[(i + 1) % n]
        cur_in = cz >= ZNEAR
        if cur_in:
            out.append((cx, cy, cz))
        if cur_in != (nz >= ZNEAR):
            t = (ZNEAR - cz) / (nz - cz)
            out.append((cx + t * (nx - cx), cy + t * (ny - cy), ZNEAR))
    return out


class WorldDrawMixin:
    def fl(self):
        """focal length ของเฟรมนี้ — GUNFIGHT คูณ zoom ตอน ADS/สโคป (ทุกตัววาดต้องใช้ค่านี้ตัวเดียวกัน)"""
        f = focal_len(self.H)
        if self.mode == "gun":
            f *= getattr(self, "gun_zoom", 1.0)
        return f

    def project(self, p, f):
        x, y, z = self.cam.to_cam(p)
        if z < ZNEAR:
            return None
        return (self.W / 2 + f * x / z, self.H / 2 - f * y / z, z)

    def poly(self, pts3, color, width=0, f=None):
        # clip กับ near plane ก่อนฉาย → กำแพงที่มีมุมหลุดหลังกล้องถูกตัดบางส่วน ไม่หายทั้งแผ่น
        cs = _clip_near([self.cam.to_cam(p) for p in pts3])
        if len(cs) < 3:
            return None
        pts = [(self.W / 2 + f * x / z, self.H / 2 - f * y / z) for (x, y, z) in cs]
        r = pygame.draw.polygon(self.screen, color, pts, width)
        self.mark_dirty(r.inflate(4, 4))     # no-op นอกเฟรม play บน GPU world
        return r

    def view_offset(self):
        """กล้องเด้งจากรีคอยล์ที่ 'ตาเห็น' (เรเดียน pitch, yaw) — ใช้เฉพาะตอนวาดโลก ไม่แตะทิศเล็งจริง"""
        if self.state not in ("play", "pause"):
            return None
        if self.mode == "gun" and getattr(self, "gun_stab", None) is not None:
            return self.gun_view_offset()
        if self.mode == "spray" and getattr(self, "spray_stab", None) is not None:
            return self.spray_view_offset()
        return None

    def draw_world(self):
        vo = self.view_offset()
        if not vo or (abs(vo[0]) < 1e-7 and abs(vo[1]) < 1e-7):
            return self._draw_world_raw()
        p0, y0 = self.cam.pitch, self.cam.yaw
        self.cam.pitch = max(-math.radians(89.0), min(math.radians(89.0), p0 + vo[0]))
        self.cam.yaw = y0 + vo[1]
        try:
            self._draw_world_raw()
        finally:
            self.cam.pitch, self.cam.yaw = p0, y0

    def _draw_world_raw(self):
        glr = getattr(self, "_glr", None)
        if getattr(self, "gpu", False) and glr is not None:
            try:
                glr.render(self)                 # GPU: bg/walls/grid/pillars/sniper → framebuffer
                self._world_gpu_frame = True
                # overlay สะอาดอยู่แล้ว — _gl_present เคลียร์ท้ายทุกเฟรม และ surface ใหม่เกิดมาโปร่งใส
                # (เดิม fill((0,0,0,0)) ซ้ำตรงนี้ = เสีย ~14MB memset/เฟรมฟรี ๆ)
                # เปิดติดตาม dirty-rect เฉพาะเฟรม play ปกติ — state อื่น/flow/resume_cd อัพโหลดเต็มแบบเดิม
                self._track_dirty = (self.state == "play" and self.flow is None
                                     and self.resume_cd <= 0)
                self._draw_world_targets()        # เป้า/spray/dodge บน overlay
                return
            except Exception as ex:
                self._track_dirty = False
                self._warn_once("glworld", f"GPU world fail ({ex}) - software")
                self._glr = None
        self._draw_world_bg()
        self._draw_world_targets()

    def _draw_world_bg(self):
        W, H = self.W, self.H
        f = self.fl()
        scr = self.screen
        horizon = H / 2 + f * math.tan(self.cam.pitch) - f * (self.cam.pos[1] - EYE_Y) / 14
        scr.fill(C_SKY_TOP)
        if horizon > 0:
            pygame.draw.rect(scr, C_SKY, (0, 0, W, min(H, int(horizon))))
        if horizon < H:
            pygame.draw.rect(scr, C_FLOOR, (0, max(0, int(horizon)), W, H))
        # ผนังข้าง
        self.poly([(-ROOM_X, 0, 2), (-ROOM_X, 0, WALL_Z), (-ROOM_X, ROOM_H, WALL_Z), (-ROOM_X, ROOM_H, 2)], C_SIDEWALL, f=f)
        self.poly([(ROOM_X, 0, 2), (ROOM_X, 0, WALL_Z), (ROOM_X, ROOM_H, WALL_Z), (ROOM_X, ROOM_H, 2)], C_SIDEWALL, f=f)
        # ผนังหลัง
        self.poly([(-ROOM_X, 0, WALL_Z), (ROOM_X, 0, WALL_Z), (ROOM_X, ROOM_H, WALL_Z), (-ROOM_X, ROOM_H, WALL_Z)], C_WALL, f=f)
        self.poly([(-ROOM_X, 0, WALL_Z), (ROOM_X, 0, WALL_Z), (ROOM_X, ROOM_H, WALL_Z), (-ROOM_X, ROOM_H, WALL_Z)], C_GRID, 2, f=f)
        # ตารางพื้น
        for gx in range(-10, 11, 2):
            a, b = self.project((gx, 0, 2), f), self.project((gx, 0, WALL_Z), f)
            if a and b:
                pygame.draw.line(scr, C_GRID, (a[0], a[1]), (b[0], b[1]), 1)
        for gz in range(2, int(WALL_Z) + 1, 2):
            a, b = self.project((-10, 0, gz), f), self.project((10, 0, gz), f)
            if a and b:
                pygame.draw.line(scr, C_GRID, (a[0], a[1]), (b[0], b[1]), 1)
        # เสา
        if self.S.get("pillars"):
            for px, pz in ((-7, 11), (7, 11), (-7, 4), (7, 4)):
                self.poly([(px - 0.3, 0, pz), (px + 0.3, 0, pz), (px + 0.3, ROOM_H, pz), (px - 0.3, ROOM_H, pz)],
                          (31, 46, 61), f=f)
        # กำแพง sniper + ประตู
        if self.mode == "sniper" and self.state in ("play", "countdown", "pause"):
            wz = SNIPER_WALL_Z
            cwall = (32, 45, 61)
            self.poly([(-ROOM_X, 0, wz), (SNIPER_DOOR_L, 0, wz), (SNIPER_DOOR_L, ROOM_H, wz), (-ROOM_X, ROOM_H, wz)], cwall, f=f)
            self.poly([(SNIPER_DOOR_R, 0, wz), (ROOM_X, 0, wz), (ROOM_X, ROOM_H, wz), (SNIPER_DOOR_R, ROOM_H, wz)], cwall, f=f)
            self.poly([(SNIPER_DOOR_L, SNIPER_DOOR_H, wz), (SNIPER_DOOR_R, SNIPER_DOOR_H, wz),
                       (SNIPER_DOOR_R, ROOM_H, wz), (SNIPER_DOOR_L, ROOM_H, wz)], cwall, f=f)
            self.poly([(SNIPER_DOOR_L, 0, wz), (SNIPER_DOOR_R, 0, wz), (SNIPER_DOOR_R, SNIPER_DOOR_H, wz),
                       (SNIPER_DOOR_L, SNIPER_DOOR_H, wz)], (58, 77, 101), 2, f=f)

    def _draw_world_targets(self):
        W, H = self.W, self.H
        f = self.fl()
        scr = self.screen
        # คลิปบอล sniper ให้เห็นเฉพาะในช่องประตู (ไม่ทับกำแพง)
        door_clip = None
        if self.mode == "sniper" and self.state in ("play", "countdown", "pause"):
            a = self.project((SNIPER_DOOR_L, 0, SNIPER_WALL_Z), f)
            b = self.project((SNIPER_DOOR_R, SNIPER_DOOR_H, SNIPER_WALL_Z), f)
            if a and b:
                door_clip = pygame.Rect(int(min(a[0], b[0])), int(min(a[1], b[1])),
                                        int(abs(b[0] - a[0])) + 1, int(abs(b[1] - a[1])) + 1)
        # เป้า
        pulse = 1 + 0.06 * math.sin(pygame.time.get_ticks() / 1000 * 6)
        for t in sorted(self.targets, key=lambda t: -t.dist(self.cam)):
            if self.mode == "sniper" and not t.visible:
                continue
            pr = self.project(t.pos, f)
            if not pr:
                continue
            sx, sy, z = pr
            r = f * t.radius / z * (0.4 + 0.6 * t.alpha)
            if r < 1:
                continue
            sx, sy, r = int(sx), int(sy), int(r)
            if self.mode == "sniper":
                if door_clip:
                    scr.set_clip(door_clip)
                # pygame.draw.* คืน Rect ขอบเขตพิกเซลที่แตะจริง (ถูก clip แล้ว) — ใช้ mark dirty ได้เลย
                self.mark_dirty(pygame.draw.circle(scr, (170, 35, 48), (sx, sy), r + 2))
                pygame.draw.circle(scr, C_RED, (sx, sy), r)
                pygame.draw.circle(scr, (255, 140, 150), (sx - r // 3, sy - r // 3), max(1, r // 4))
                scr.set_clip(None)
            else:
                # วงนอกสุด (ring pulse) ครอบทุกวงใน — mark วงเดียวพอ
                self.mark_dirty(pygame.draw.circle(scr, (140, 30, 40), (sx, sy),
                                                   max(1, int(r * 1.18 * pulse)), max(2, r // 8)).inflate(2, 2))
                pygame.draw.circle(scr, (255, 255, 255), (sx, sy), int(r * 0.97), max(1, r // 10))
                pygame.draw.circle(scr, C_RED, (sx, sy), int(r * 0.88))
                pygame.draw.circle(scr, (255, 255, 255), (sx, sy), max(1, int(r * 0.12)))
                # ── หัว (head hitzone) — วงเล็กเหนือลำตัว เฉพาะเมื่อ head เปิด ──
                if self.head_enabled():
                    hp = self.project(t.head_pos(), f)
                    if hp:
                        hx, hy, hz = hp
                        hr = max(2, int(f * t.head_radius() / hz * (0.4 + 0.6 * t.alpha)))
                        self.mark_dirty(pygame.draw.circle(scr, (60, 18, 26), (int(hx), int(hy)), hr + 1))
                        pygame.draw.circle(scr, (255, 120, 132), (int(hx), int(hy)), hr)
                        pygame.draw.circle(scr, (255, 235, 235), (int(hx), int(hy)),
                                           max(1, hr // 3))
        # มาร์คกระสุน spray (ลายรีคอยล์) + hazard ของ dodge
        if self.mode == "spray" and self.state in ("play", "pause"):
            self.draw_spray_marks(f)
        if self.mode == "dodge" and self.state in ("play", "pause"):
            self.draw_dodge_world(f)
        if self.mode == "gun" and self.state in ("play", "pause", "countdown"):
            self.draw_gun_world(f)
        if self.rpeek_on() and self.state in ("play", "pause", "countdown"):
            self.draw_rpeek_world(f)        # reaction·peek: กล่อง + หุ่นโผล่จากขอบ (ตัววาดชุดเดียวกับ GUNFIGHT)

    def draw_spray_marks(self, f):
        """วาดรอยกระสุนบนเป้า (spray pattern) อิงมุมเทียบใจกลางเป้า"""
        if not self.targets:
            return
        t = self.targets[0]
        pr = self.project(t.pos, f)
        if not pr:
            return
        bx, by, bz = pr
        # องศา -> พิกเซล: offset เป็น "มุม" เทียบใจกลางเป้า → f·tan(θ) ≈ f·θ ไม่ขึ้นกับระยะ
        # (เดิมหาร z เพิ่ม = รอยถูกบีบ 11 เท่า จนดูเหมือน pattern อยู่ในตัวเป้าตลอด — แก้ 11 ก.ย. 2026)
        ppd = f * (math.pi / 180.0)
        marks = self.spray_marks
        x0 = y0 = 10 ** 9
        x1 = y1 = -(10 ** 9)
        # ไล่ 50 ตัวท้ายด้วย index ตรง ๆ — ไม่ slice copy ทุกเฟรม
        for i in range(max(0, len(marks) - 50), len(marks)):
            yaw_off, pitch_off, on_body, is_head = marks[i]
            mx = int(bx + yaw_off * ppd)
            my = int(by - pitch_off * ppd)
            if is_head:
                c = C_PALE_GOLD
            elif on_body:
                c = (120, 255, 160)
            else:
                c = (90, 110, 130)
            pygame.draw.circle(self.screen, c, (mx, my), 2)
            if mx < x0: x0 = mx
            if mx > x1: x1 = mx
            if my < y0: y0 = my
            if my > y1: y1 = my
        if x1 >= x0:
            # bbox เดียวคลุมทุกรอยกระสุน (รัศมี 2 + กันขอบ)
            self.mark_dirty(pygame.Rect(x0 - 3, y0 - 3, x1 - x0 + 6, y1 - y0 + 6))

    @staticmethod
    def beam_col(hz, now_warn):
        """สีกำแพงลำแสงของ BEAM เฟรมนี้ — None = ช่วงเตือนจังหวะกะพริบดับ (ไม่วาดทั้งลำแสงและรั้ว) ; ใช้ร่วม software/GPU"""
        warn = hz["state"] == "warn"
        if warn and not now_warn:
            return None
        return (255, 170, 0) if warn else (255, 70, 90)

    def dodge_beams(self):
        """BEAM ที่ต้องวาดเฟรมนี้ [(beam_x, stop_x, สีลำแสง)] — glrender วาดเป็นเรขาคณิตโลกเมื่อ world อยู่บน GPU
        (เงื่อนไข state/กะพริบเดียวกับ draw_dodge_world ของ software)"""
        if self.mode != "dodge" or self.state not in ("play", "pause"):
            return []
        now_warn = (pygame.time.get_ticks() // 150) % 2 == 0
        out = []
        for hz in self.dodge_hazards:
            if hz["kind"] == "beam":
                col = self.beam_col(hz, now_warn)
                if col is not None:
                    out.append((hz["beam_x"], hz["stop_x"], col))
        return out

    def draw_dodge_world(self, f):
        """วาด telegraph/active ของ hazard ลงบนพื้น/อากาศ"""
        scr = self.screen
        now_warn = (pygame.time.get_ticks() // 150) % 2 == 0
        gpu_world = getattr(self, "_world_gpu_frame", False)   # glrender วาด BEAM ให้แล้ว (dodge_beams)
        for hz in self.dodge_hazards:
            k = hz["kind"]
            if k == "aoe":
                cx, cz = hz["cx"], hz["cz"]
                col = (255, 80, 60) if hz["state"] != "warn" else (255, 170, 0)
                if hz["state"] == "warn" and not now_warn:
                    continue
                # วงพื้น + วงยอดเสา + เสา 6 ต้น = "แก้วคว่ำ" — วงพื้นรอบเท้าอยู่นอกจอตอนมองระดับหัว
                # (ขอบวง 1.6 ม. = pitch -46°) แต่ยอดเสาที่ 1.3 ม. อยู่แค่ -12° เห็นได้ทุกมุม (2026-09-07)
                for hgt in (0.02, DODGE_AOE_POST_H):
                    seg = []
                    for ox, oz in _AOE_RING:   # offset วงแหวนคงที่ — ตารางคำนวณครั้งเดียวตอน import
                        p = self.project((cx + ox, hgt, cz + oz), f)
                        if p:
                            seg.append((p[0], p[1]))
                    if len(seg) >= 3:
                        self.mark_dirty(pygame.draw.polygon(scr, col, seg, 2))
                for ox, oz in _AOE_POSTS:
                    a = self.project((cx + ox, 0.02, cz + oz), f)
                    b = self.project((cx + ox, DODGE_AOE_POST_H, cz + oz), f)
                    if a and b:
                        self.mark_dirty(pygame.draw.line(scr, col, (a[0], a[1]), (b[0], b[1]), 2))
            elif k == "proj":
                lx = hz["lane_x"]
                if hz["state"] == "warn":
                    # telegraph: ลูกบอลโผล่ที่จุดเกิดแล้วพองขึ้นจนเต็มขนาด + เลนบนพื้นกว้างเท่า hitbox กะพริบ
                    # (เดิมมีแค่เส้นบาง 2px ระดับตา ซึ่งถ้าเลนตรงกับตัวจะยุบเป็นจุดที่เส้นขอบฟ้า มองไม่เห็น)
                    warn_p = min(1.0, max(0.0, (self.gt - hz["born"]) / max(0.05, hz["fire_at"] - hz["born"])))
                    bp = self.project((lx, EYE_Y, hz["z"]), f)
                    if bp:
                        rr = max(3, int(f * DODGE_PROJ_HIT_R * (0.4 + 0.6 * warn_p) / max(0.05, bp[2])))
                        self.mark_dirty(pygame.draw.circle(scr, (255, 170, 0), (int(bp[0]), int(bp[1])), rr, 2))
                    if now_warn:
                        zn = self.cam.pos[2] + 0.35
                        for ex in (lx - DODGE_PROJ_HIT_R, lx + DODGE_PROJ_HIT_R):
                            a = self.project((ex, 0.02, hz["z"]), f)
                            b = self.project((ex, 0.02, zn), f)
                            if a and b:
                                self.mark_dirty(pygame.draw.line(scr, (255, 170, 0), (a[0], a[1]), (b[0], b[1]), 2))
                else:
                    # ช่วงบิน: วาดแค่ลูกบอล (ขนาด = hitbox จริง) ไม่มีเส้น
                    bp = self.project((lx, EYE_Y, hz["z"]), f)
                    if bp:
                        rr = max(3, int(f * DODGE_PROJ_HIT_R / max(0.05, bp[2])))
                        self.mark_dirty(pygame.draw.circle(scr, (255, 90, 60), (int(bp[0]), int(bp[1])), rr))
            else:  # beam — กำแพงเลเซอร์แนว z (ยื่นไปข้างหน้าให้เห็นในจอ) + รั้วเตี้ย "เส้นหยุด" ที่ลำแสงจะมาถึงแค่นั้น
                # เดิมวาดเส้นตั้งที่ z = −2 (ข้างหลังผู้เล่นเกือบทุกตำแหน่ง = project ไม่ได้) → แทบมองไม่เห็นลำแสงเลย
                # GPU world: glrender วาดเป็นเรขาคณิตโลก (segment beam* + dodge_beams) — บน overlay กรอบ dirty ของ poly
                # กำแพงยาว z −2.6..7 กินครึ่งจอ ทุกเฟรมที่มีลำแสงเลยอัพโหลด overlay เกือบเต็ม (p99 dodge 2.2 → 5 ms)
                # software: poly() clip near-plane + mark_dirty กรอบของตัวเองแล้ว (ลำดับวาดเดิม ทับเป้า)
                if gpu_world:
                    continue
                col = self.beam_col(hz, now_warn)
                if col is None:
                    continue
                z0, z1 = DODGE_BEAM_Z
                sx = hz["stop_x"]
                self.poly([(sx, 0.02, z0), (sx, 0.02, z1), (sx, DODGE_AOE_POST_H, z1), (sx, DODGE_AOE_POST_H, z0)],
                          (255, 170, 0), 2, f=f)
                bx = hz["beam_x"]
                self.poly([(bx, 0.02, z0), (bx, 0.02, z1), (bx, DODGE_BEAM_H, z1), (bx, DODGE_BEAM_H, z0)], col, 3, f=f)
                for hy in (EYE_Y, DODGE_BEAM_H * 0.35):    # เส้นกลางระดับตา = ตัดเส้นขอบฟ้า เห็นได้ทุกมุมมอง
                    self.poly([(bx, hy - 0.03, z0), (bx, hy - 0.03, z1), (bx, hy + 0.03, z1), (bx, hy + 0.03, z0)],
                              col, 0, f=f)
        # แฟลชจอเมื่อโดน — surface เดียวใช้ซ้ำ (เดิม alloc 14MB ใหม่ทุกเฟรม); fill ทับทุกพิกเซลรวม alpha
        # จึงให้ผลเหมือนสร้างใหม่เป๊ะ; เต็มจอ → บังคับอัพโหลดเต็มเฟรมนี้
        if self.dodge_flash > 0:
            al = int(120 * (self.dodge_flash / 0.35))
            if self.gpu_post_available():
                self.post_fx_add(tint=(255, 40, 50, al))     # GPU: shader เต็มจอ ไม่ต้อง blit/อัพโหลด 14MB
            else:
                ov = getattr(self, "_flash_ov", None)
                if ov is None or ov.get_size() != (self.W, self.H):
                    ov = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                    self._flash_ov = ov
                ov.fill((255, 40, 50, al))
                scr.blit(ov, (0, 0))
                self.mark_full()

    def draw_crosshair(self):
        ch = dict(self.S["ch"])
        from . import guns as _g

        def spread_gap(sp, base):
            # crosshair ถ่างตามสเปรดจริงของนัดถัดไป (ขยับ/ยิงรัว = ถ่างและแดง) — จากตาราง Riot (stability.py)
            ratio = min(1.0, max(0.0, (sp - base) / 6.0))
            ch["lineGap"] = ch["lineGap"] + round(ratio * 34)
            if sp > base * 1.5 + 0.05:
                ch["color"] = "#FF4655"

        if self.mode in ("strafe", "dodge") and self.state == "play":
            spread_gap(self.move_spread(), _g.WEAPONS[STRAFE_WEAPON]["spread"]["stand"])
        if self.mode == "gun" and self.state == "play":
            if self.gun_zoom > 1.0 and self.gun_w()["kind"] == "sniper":
                self.draw_gun_scope()      # สโคป Op แทน crosshair
                return
            spread_gap(self.gun_next_spread(), _g.WEAPONS[self.gun_weapon]["spread"]["stand"])
        col = hexrgb(ch["color"])
        cx, cy = self.W // 2, self.H // 2

        def rect(x, y, w, h):
            if ch["outline"]:
                pygame.draw.rect(self.screen, (0, 0, 0), (x - 1, y - 1, w + 2, h + 2))
            pygame.draw.rect(self.screen, col, (x, y, w, h))
            # mark จากเรขาคณิตที่คำนวณเอง ไม่ใช้ rect ที่ pygame คืน — ถ้า w/h เป็น 0 (config แก้มือ)
            # pygame คืน rect ขนาดศูนย์ทั้งที่เส้นขอบ outline ถูกวาดจริง → จะหลุดการ track
            self.mark_dirty(pygame.Rect(x - 1, y - 1, w + 2, h + 2))

        if ch["lines"]:
            ln, th, gap = ch["lineLen"], ch["lineThick"], ch["lineGap"]
            off = gap + ln // 2
            rect(cx - off - ln // 2, cy - th // 2, ln, th)
            rect(cx + off - ln // 2, cy - th // 2, ln, th)
            rect(cx - th // 2, cy - off - ln // 2, th, ln)
            rect(cx - th // 2, cy + off - ln // 2, th, ln)
        if ch["dot"]:
            d = ch["dotSize"]
            rect(cx - d // 2, cy - d // 2, d, d)

    def draw_effects(self):
        now = pygame.time.get_ticks()
        cx, cy = self.W // 2, self.H // 2
        if self.hitmarks:
            self.hitmarks = [t0 for t0 in self.hitmarks if now - t0 < 250]
            if self.hitmarks:
                # กากบาท hitmark ทุกอันอยู่ในกรอบ center ± (s สูงสุด 16 + ความหนา) — mark กรอบเดียว
                self.mark_dirty(pygame.Rect(cx - 18, cy - 18, 36, 36))
        for t0 in self.hitmarks:
            p = (now - t0) / 250
            s = 8 + p * 8
            g = 5 + p * 3
            for sx in (-1, 1):
                for sy in (-1, 1):
                    pygame.draw.line(self.screen, (255, 255, 255),
                                     (cx + sx * g, cy + sy * g), (cx + sx * s, cy + sy * s), 2)
        if self.floats:
            self.floats = [fl for fl in self.floats if now - fl["born"] < 600]
        for fl in self.floats:
            p = (now - fl["born"]) / 600
            self.text(fl["t"], 16, fl["c"], (cx + fl["dx"], cy + fl["dy"] - p * 40), bold=True)

    def hud_scale(self):
        # HUD ขยายตามความสูงจอ (อิง 720p เป็นฐาน) จำกัด 1.0–2.2 เท่า
        return max(1.0, min(self.H / 720.0, 2.2))

    def ui_scale(self):
        # หน้า settings/ranks/insight ขยายตามจอ (อิง 1280x720) จำกัด 1.0–2.0 เท่า
        return max(1.0, min(self.W / 1280.0, self.H / 720.0, 2.0))

    def hud_stats(self):
        """สถิติบน HUD แยกซ้าย/กลาง/ขวา — เพิ่มของใหม่ในอนาคตแค่เติมในลิสต์นี้
        แต่ละช่อง = (value, color, label) ; กลาง = ('timer', label, frac, low)"""
        total = self.hits + self.misses
        acc = f"{round(self.hits / total * 100)}%" if total else "--%"
        if self.mode == "reaction":
            t_label, frac = f"{self.reaction_done}/{REACTION_COUNT}", self.reaction_done / REACTION_COUNT
            low = False
        elif self.mode == "sniper":
            t_label, frac = f"{self.sniper_spawned}/{SNIPER_TOTAL}", self.sniper_spawned / SNIPER_TOTAL
            low = False
        else:
            t_label = str(int(math.ceil(self.time_left)))
            frac = self.time_left / self.duration
            low = self.time_left <= 10
        left = [(self.score, C_TEXT, "SCORE"), (self.hits, C_GREEN, "HITS")]
        right = [(acc, C_TEXT, "ACCURACY"), (self.misses, C_RED, "MISSES")]
        # ── ปรับ readout ตามโหมดใหม่ ──
        if self.mode == "spray":
            ob = f"{round(self.spray_onbody / self.spray_shots * 100)}%" if self.spray_shots else "--%"
            left = [(self.score, C_TEXT, "SCORE"), (f"{self.spray_mag}", C_GREEN, "AMMO")]
            right = [(ob, C_TEXT, "บนเป้า"), (f"{self.spray_heads}", C_PALE_GOLD, "HEADS")]
        elif self.mode == "dodge":
            left = [(self.score, C_TEXT, "SCORE"), (f"{self.dodge_hp}", C_GREEN, "HP")]
            dd = f"{self.dodge_dodged}/{self.dodge_total_haz}"
            right = [(dd, C_TEXT, "DODGED"), (f"{self.hits}", C_PALE_GOLD, "KILLS")]
        elif self.mode == "placement":
            pa = f"{self.placement_pending:.1f}°" if self.placement_pending is not None else "--"
            avg = sum(self.placement_preaim) / len(self.placement_preaim) if self.placement_preaim else 0
            left = [(self.score, C_TEXT, "SCORE"), (pa, C_GOLD, "PRE-AIM")]
            right = [(f"{avg:.1f}°", C_TEXT, "AVG ° "), (self.hits, C_GREEN, "KILLS")]
        elif self.mode == "switch":
            sw = round(self.switch_kill_times[-1]) if self.switch_kill_times else 0
            left = [(self.score, C_TEXT, "SCORE"), (f"W{self.switch_wave}", C_GREEN, "WAVE")]
            right = [(f"{sw}ms", C_TEXT, "SWITCH"), (self.hits, C_PALE_GOLD, "KILLS")]
        elif self.mode == "gun":
            left, right = self.gun_hud()
        elif self.head_enabled():
            # โหมดคลาสสิกเมื่อเปิด headshots: โชว์ HS%
            hs = f"{round(self.headshots / self.hits * 100)}%" if self.hits else "--%"
            right = [(acc, C_TEXT, "ACCURACY"), (hs, C_PALE_GOLD, "HS%")]
        center = (t_label, frac, low)
        return left, center, right

    def draw_hud(self):
        W, H = self.W, self.H
        sc = self.hud_scale()
        def S(v):
            return int(round(v * sc))
        big_f = self.font(S(24), True)
        lbl_f = self.font(S(10))
        bh, lh = big_f.get_height(), lbl_f.get_height()
        # ── ความสูง HUD คำนวณจากเนื้อหาจริง (ฟอนต์ + ช่องไฟ) → เพิ่มของแล้วขยายเอง ──
        pad_top, gap_vl, pad_bot = S(6), S(2), S(9)
        y_val = pad_top
        y_lbl = pad_top + bh + gap_vl
        hud_h = y_lbl + lh + pad_bot
        self.hud_h = hud_h
        self.mark_dirty(pygame.Rect(0, 0, W, hud_h + 1))   # แถบ HUD เต็มความกว้าง (รวมเส้นขอบล่าง)
        pygame.draw.rect(self.screen, (8, 20, 28), (0, 0, W, hud_h))
        pygame.draw.line(self.screen, C_BORDER, (0, hud_h), (W, hud_h))
        pygame.draw.line(self.screen, C_RED, (0, hud_h - 1), (W, hud_h - 1))   # accent

        margin, blk_gap = S(28), S(34)
        left, center, right = self.hud_stats()

        def block_w(val, lab):
            # ใช้ memo ความกว้าง (game.text_width) — font.size ทำ shaping ไทยซ้ำทุกเฟรมโดยไม่จำเป็น
            return max(self.text_width(val, S(24), True), self.text_width(lab, S(10)))

        # กลุ่มซ้าย: ชิดซ้าย ไล่ไปขวา (วัดความกว้างจริงต่อช่อง ไม่ทับกันแม้เลขยาว)
        cur = margin
        for val, col, lab in left:
            self.text(val, S(24), col, (cur, y_val), bold=True)
            self.text(lab, S(10), C_DIM, (cur, y_lbl))
            cur += block_w(val, lab) + blk_gap
        # กลุ่มขวา: ชิดขวา ไล่ไปซ้าย
        cur = W - margin
        for val, col, lab in right:
            self.text(val, S(24), col, (cur, y_val), right=True, bold=True)
            self.text(lab, S(10), C_DIM, (cur, y_lbl), right=True)
            cur -= block_w(val, lab) + blk_gap
        # เส้นคั่นแยกโซน (อิงความสูง HUD)
        pygame.draw.line(self.screen, C_BORDER, (W // 2 - S(130), S(8)), (W // 2 - S(130), hud_h - S(8)))
        pygame.draw.line(self.screen, C_BORDER, (W // 2 + S(130), S(8)), (W // 2 + S(130), hud_h - S(8)))
        # โซนกลาง: เวลา/ความคืบหน้า — เลขแถวบน, bar อยู่แนวเดียวกับ label
        t_label, frac, low = center
        self.text(t_label, S(22), C_RED if low else C_TEXT, (W // 2, y_val), center=True, bold=True)
        bar_h = max(4, S(5))
        bar = pygame.Rect(W // 2 - S(100), y_lbl + (lh - bar_h) // 2, S(200), bar_h)
        pygame.draw.rect(self.screen, C_BORDER, bar, border_radius=2)
        fill = bar.copy()
        fill.width = int(bar.width * max(0.0, min(1.0, frac)))
        pygame.draw.rect(self.screen, C_RED, fill, border_radius=2)
        # มุมล่างจอ: โหมด+sens / PB
        foot = S(13)
        self.text(f"{MODE_NAME[self.mode]} · SENS {self.S['sens']:g}", foot, C_DIM, (S(14), H - S(28)))
        if getattr(self, "pb_display", None):
            self.text(self.pb_display, foot, C_GOLD, (W - S(14), H - S(28)), right=True)
        if self.S.get("fps"):
            fps = self.clock.get_fps()
            c = (102, 255, 153) if fps >= 55 else (255, 200, 87) if fps >= 30 else C_RED
            self.text(f"{fps:.0f} FPS", S(13), c, (S(14), hud_h + S(8)))
            # บรรทัดวินิจฉัย: เวลาทำงานจริงต่อเฟรม (ไม่รวมรอ vsync/cap) · เวลา present · เส้นทางอัพโหลด overlay
            # · vsync/cap — ถ้าเฟรมตกจะเห็นทันทีว่าติดที่ CPU วาด (raw สูง) หรือ upload (present สูง/"full")
            raw = self.clock.get_rawtime()
            pm = getattr(self, "_perf_present_ms", None)
            path = getattr(self, "_perf_path", "software")
            cap = self.get_frame_cap()
            vs = "vsync" if getattr(self, "vsync_active", False) else ("cap " + (str(cap) if cap else "∞"))
            diag = f"{raw} ms/frame · present {pm:.1f} ms · {path} · {vs} · {self.W}x{self.H}" if pm is not None else path
            self.text(diag, S(11), C_DIM, (S(14), hud_h + S(26)))
        # คำเตือน strafe
        if self.mode == "strafe" and self.state == "play" and self.static_since > STRAFE_STATIC_WARN:
            r = self.text("! KEEP MOVING !", S(22), C_RED, (W // 2, int(H * 0.24)), center=True, bold=True)
            self.mark_dirty(pygame.draw.rect(self.screen, C_RED, r.inflate(S(24), S(12)), 1, border_radius=4))
        # ── SPRAY: อาวุธ + รีโหลด + เรตติ้งคุมรีคอยล์ ──
        if self.mode == "spray" and self.state == "play":
            wlabel = self.spray_weapon.upper()
            self.text(f"{wlabel}", S(14), C_PALE_GOLD, (W // 2, H - S(54)), center=True, bold=True)
            if self.spray_reloading_until > 0:
                self.text("RELOADING…", S(18), C_GOLD, (W // 2, int(H * 0.30)), center=True, bold=True)
            ob = self.spray_onbody / self.spray_shots if self.spray_shots else 0
            rate, rcol = self.spray_rating(ob)
            if self.spray_shots >= 3:
                self.text(f"คุมรีคอยล์: {rate}", S(14), rcol, (W // 2, int(H * 0.72)), center=True, bold=True)
        # ── DODGE: แถบ HP ──
        if self.mode == "dodge" and self.state == "play":
            bw, bh = S(220), S(12)
            bx = W // 2 - bw // 2
            byb = int(H * 0.80)
            self.mark_dirty(pygame.Rect(bx - 1, byb - 1, bw + 2, bh + 2))   # แถบ HP (รวมเส้นขอบ)
            pygame.draw.rect(self.screen, (40, 20, 24), (bx, byb, bw, bh), border_radius=3)
            frac_hp = self.dodge_hp / DODGE_HP_MAX
            hc = C_GREEN if frac_hp > 0.5 else C_GOLD if frac_hp > 0.25 else C_RED
            pygame.draw.rect(self.screen, hc, (bx, byb, int(bw * frac_hp), bh), border_radius=3)
            pygame.draw.rect(self.screen, C_BORDER, (bx, byb, bw, bh), 1, border_radius=3)
            self.text(f"HP {self.dodge_hp}", S(11), C_DIM, (W // 2, byb - S(12)), center=True, bold=True)
        # ── PLACEMENT: คำแนะนำพรีเอม ──
        if self.mode == "placement" and self.state == "play" and self.placement_pending is not None:
            pa = self.placement_pending
            pcol = C_GREEN if pa <= PLACEMENT_GOOD_DEG else C_GOLD if pa <= 8 else C_RED
            self.text(f"PRE-AIM {pa:.1f}°", S(16), pcol, (W // 2, int(H * 0.72)), center=True, bold=True)
        if self.mode == "gun":
            rp = self.r_hold_progress() if self.state == "play" else None
            if rp is not None and rp >= 0.25:   # แตะ R รีโหลดปกติไม่ต้องขึ้น — โชว์เมื่อเริ่ม "ค้าง" จริง
                left = (1.0 - rp) * self.R_HOLD_RESTART_MS / 1000.0
                self.text(f"ค้าง R อีก {left:.1f} วิ = เริ่มรอบใหม่ (ปล่อย = ยกเลิก)", S(13), C_GOLD,
                          (W // 2, hud_h + S(20)), center=True)
        elif self.r_hint_until > pygame.time.get_ticks():
            self.text("กด R อีกครั้งเพื่อเริ่มใหม่", S(13), C_GOLD, (W // 2, hud_h + S(20)), center=True)
        # ── GUNFIGHT: HP/เกราะ + กระสุน + สถานะดริล ──
        if self.mode == "gun" and self.state == "play":
            self.draw_gun_status()

    def spray_rating(self, on_body_frac):
        """เรตติ้งคุมรีคอยล์จาก % บนเป้า"""
        p = on_body_frac
        if p >= 0.85:
            return "PERFECT", C_PALE_GOLD
        if p >= 0.70:
            return "GREAT", C_GREEN
        if p >= 0.50:
            return "GOOD", C_GOLD
        if p >= 0.30:
            return "OK", (255, 170, 0)
        return "SPRAY CONTROL!", C_RED
