# -*- coding: utf-8 -*-
"""HUD ของโหมด CLUTCH 1vN (CLUTCH_DESIGN §8 / §10.2 / §10.5) — ClutchHudMixin
เวลา/spike กลางบน (หลังวางไม่มีเลขวินาทีเว้นแต่เปิด "แสดงวินาที spike") · 1 v N · มินิแมพ north-up มุมซ้ายบน (เห็นเฉพาะศัตรู
ที่กำลังเห็น/เพิ่งเห็น < 2 วิ — ไม่มีข้อมูลทะลุกำแพง) + ชื่อจุด · HP/เกราะซ้ายล่าง · กระสุนขวาล่าง · แถบวาง/กู้กลางจอ (ขีดครึ่งทาง
3.5 วิ) · kill feed ขวาบน · ลูกศรทิศที่โดนยิง · คำใบ้ · "ศัตรูได้ยินเสียงเท้า" · Tab = แมพใหญ่
dirty-rect (display.mark_dirty): ทุกจุดที่วาดบน overlay mark กรอบของตัวเอง (text() mark เอง) — ภาพเต็มจอใช้ post-fx/mark_full
ห้ามใช้ตัวอักษรใน config.UI_FONT_NO_GLYPH (ลูกศร/รูปทรง = วาด polygon เอง)"""
import math
import weakref

import pygame

from .config import C_BORDER, C_DIM, C_GOLD, C_GREEN, C_PALE_GOLD, C_RED, C_TEXT, C_SKY, C_SKY_TOP
from . import clutchmesh, guns
from .clutchscen import DEFUSE_HALF, DEFUSE_T, PLANT_T, SEEN_KEEP, why_text

_C_PANEL = (8, 20, 28, 205)
_C_PLATE = (8, 20, 28, 165)
_C_ENEMY = (255, 70, 85)
_C_SPIKE = (255, 60, 60)


class ClutchHudMixin:
    # ───────────────────────── มินิแมพ ─────────────────────────
    def _cl_mini_px(self):
        return int(round(180 * self.hud_scale()))

    def _cl_map_cache(self):
        """cache ต่อตัวแมพ (WeakKeyDictionary: แมพถูกทิ้งจาก clutchmap.cached = ของมันหายตาม) — เดิมคีย์ id(cmap):
        แมพใหม่ได้ที่อยู่หน่วยความจำเดิมของแมพที่ถูกทิ้ง = มินิแมพของแมพเก่าทั้งรอบ (ESC กลางรอบ + หมุน ≥ 3 แมพ)"""
        cache = getattr(self, "_cl_mini", None)
        if cache is None:
            cache = self._cl_mini = weakref.WeakKeyDictionary()
        per = cache.get(self.cmap)
        if per is None:
            per = cache[self.cmap] = {}
        return per

    def clutch_minimap(self, px):
        """พื้นผิวมินิแมพขนาดด้านยาว px (clutchmesh.minimap_rgba ≤ ~0.1 วิ) — cache ต่อแมพ × ขนาด (แมพละ 4 ขนาดล่าสุด)"""
        per = self._cl_map_cache()
        s = per.get(px)
        if s is None:
            gen = min(px, 720)
            w, h, buf = clutchmesh.minimap_rgba(self.cmap, gen)
            s = pygame.image.frombuffer(bytes(buf), (w, h), "RGBA").copy()
            if gen != px:
                k = px / float(gen)
                s = pygame.transform.smoothscale(s, (max(1, int(w * k)), max(1, int(h * k))))
            if len([k for k in per if isinstance(k, int)]) >= 4:
                per.pop(next(k for k in per if isinstance(k, int)))
            per[px] = s
        return s

    def _cl_big_px(self):
        return int(min(self.W, self.H) * 0.78)

    def clutch_hud_prepare(self):
        """งานหนักของ HUD ทำตอนตั้งรอบ (START บล็อกอยู่แล้ว) ไม่ใช่เฟรมเล่น: มินิแมพ + แมพใหญ่ของ Tab (เดิมสร้างตอนกด Tab
        ครั้งแรกของแต่ละแมพ = เฟรมนั้น 32–64 ms)"""
        if self.cmap is not None:
            self.clutch_minimap(self._cl_mini_px())
            self.clutch_minimap(self._cl_big_px())

    def clutch_tab_panel(self, rect, surf, S):
        """แผงแมพใหญ่สำเร็จรูป (พื้นแผง + ภาพแมพ ขนาดกรอบ box) สำหรับวาดเป็น texture ของ GPU — ต่อแมพ × ขนาด (cache)
        พิกเซลเท่าการวาดลง overlay ใส (pygame ผสม alpha แบบเดียวกัน)"""
        pad = S(6)
        box = rect.inflate(pad * 2, pad * 2)
        per = self._cl_map_cache()
        key = ("panel", rect.w, rect.h, pad, surf.get_size())
        pn = per.get(key)
        if pn is None:
            for k in [k for k in per if isinstance(k, tuple) and k[0] == "panel"]:
                del per[k]                                      # ขนาดจอเก่า
            pn = pygame.Surface(box.size, pygame.SRCALPHA)
            pn.fill((0, 0, 0, 0))
            pygame.draw.rect(pn, _C_PANEL, pn.get_rect(), border_radius=pad)
            ir = surf.get_rect(center=rect.center)
            pn.blit(surf, (ir.x - box.x, ir.y - box.y))
            per[key] = pn
        return pn, box

    def clutch_draw_minimap(self, rect, surf, S, big=False, panel=True):
        """แผงมินิแมพใน rect (mark ครั้งเดียวทั้งแผง — ทุกอย่างถูก clip ในกรอบนี้)
        panel=False = พื้นแผง + ภาพแมพวาดที่อื่นแล้ว (texture ของ GPU — Tab) : วาดแค่เครื่องหมาย และ mark กรอบของแต่ละชิ้น"""
        scr, cm, g = self.screen, self.cmap, self.gt
        pad = S(6)
        box = rect.inflate(pad * 2, pad * 2)
        ir = surf.get_rect(center=rect.center)
        if panel:
            self.mark_dirty(box.inflate(2, 2))
            pygame.draw.rect(scr, _C_PANEL, box, border_radius=S(6))
            scr.blit(surf, ir)
            mk = lambda r: None                                  # noqa: E731 — ทั้งแผง mark แล้ว
        else:
            mk = lambda r: self.mark_dirty(r.inflate(4, 4))       # noqa: E731
        prev = scr.get_clip()
        scr.set_clip(box)
        try:
            def P(x, z):
                u, v = clutchmesh.minimap_xy(cm, ir.w, ir.h, x, z)
                return ir.x + u, ir.y + v
            fs = S(16 if big else 12)
            for name, d in sorted(cm.sites.items()):
                c = d.get("c")
                if c:
                    self.text(name, fs, C_PALE_GOLD, P(c[0], c[1]), center=True, bold=True)
            sp = self.cl_spike
            if sp is not None and sp["state"] in ("planted", "defused", "detonated"):
                x, y = P(sp["x"], sp["z"])
                r = S(6 if big else 4)
                col = C_GREEN if sp["state"] == "defused" else _C_SPIKE
                mk(pygame.draw.polygon(scr, col, [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]))
            for b in self.bots:                                 # เฉพาะที่เราเห็นอยู่/เพิ่งเห็น (< SEEN_KEEP) ณ จุดที่เห็นล่าสุด
                if b.alive and g - b.meta.get("pseen", -99.0) < SEEN_KEEP:     # (ไม่ใช่ตำแหน่งจริงตอนนี้ = ข้อมูลทะลุกำแพง)
                    q = b.meta.get("pseen_xz") or (b.x, b.z)
                    mk(pygame.draw.circle(scr, _C_ENEMY, [int(v) for v in P(q[0], q[1])], S(4 if big else 3)))
            p, yaw = self.cam.pos, self.cam.yaw
            cx, cy = P(p[0], p[2])
            fw, fx = math.sin(yaw), -math.cos(yaw)                  # ทิศบนภาพ (บน = +z เหนือ)
            half = math.atan(self.W / (2.0 * self.fl()))
            L = S(34 if big else 22)
            for a in (yaw - half, yaw + half):
                mk(pygame.draw.line(scr, (200, 210, 220), (cx, cy), (cx + math.sin(a) * L, cy - math.cos(a) * L), 1))
            r = S(7 if big else 5)
            col = (120, 130, 140) if self.cl_dead else (90, 230, 160)
            mk(pygame.draw.polygon(scr, col, [(cx + fw * r * 1.4, cy + fx * r * 1.4),
                                              (cx - fw * r * 0.8 + fx * r * 0.8, cy - fx * r * 0.8 - fw * r * 0.8),
                                              (cx - fw * r * 0.8 - fx * r * 0.8, cy - fx * r * 0.8 + fw * r * 0.8)]))
        finally:
            scr.set_clip(prev)

    # ───────────────────────── HUD หลัก ─────────────────────────
    def _cl_plate(self, r, S):
        """แผ่นรองโปร่งแสงใต้ข้อความ HUD — โลก 3D สว่าง (ปูน/ฟ้า) ตัวหนังสือเปล่าอ่านไม่ออก ; mark_dirty กรอบเอง"""
        self.mark_dirty(pygame.draw.rect(self.screen, _C_PLATE, r, border_radius=S(5)))

    def _cl_label(self, txt, size, col, pos, S, bold=True, align="center", maxw=None):
        """ข้อความ + แผ่นรอง (align center = pos คือจุดกลาง ; right/left = pos คือมุมบนขวา/ซ้าย)"""
        if maxw:
            txt = self.fit_text(txt, size, maxw, bold)
        w, h, pad = self.text_width(txt, size, bold), self.font(size, bold).get_height(), S(6)
        if align == "center":
            r = pygame.Rect(pos[0] - w // 2 - pad, pos[1] - h // 2 - S(1), w + 2 * pad, h + S(2))
        elif align == "right":
            r = pygame.Rect(pos[0] - w - pad, pos[1] - S(1), w + 2 * pad, h + S(2))
        else:
            r = pygame.Rect(pos[0] - pad, pos[1] - S(1), w + 2 * pad, h + S(2))
        self._cl_plate(r, S)
        return self.text(txt, size, col, pos, center=align == "center", right=align == "right", bold=bold)

    def clutch_hud(self):
        W, H, g = self.W, self.H, self.gt
        sc = self.hud_scale()

        def S(v):
            return int(round(v * sc))
        # hud_h = ใต้ 1 v N : เส้นเล็งแนวตั้งของสโคป Op เริ่มใต้นี้ (draw_gun_scope) — สโคปของ clutch ไม่ทิ้งพิกเซล overlay เลย
        # (band (0, 0): HUD ทั้งหมดเห็นตอนสโคปเหมือนทาง software)
        self.hud_h = S(64)
        if self.cmap is None:
            return
        if self.gun_flash > 0:                                  # โดนยิง: จอวาบแดง (GPU = post-fx ไม่ต้องอัพโหลดเต็ม)
            a = int(110 * self.gun_flash / 0.25)
            if self.gpu_post_available():
                self.post_fx_add(tint=(180, 20, 30, a))
            else:
                self.flash_fill((180, 20, 30, a))               # ไม่ใช่ scrim(): cache ต่อ alpha = จอเต็มสะสม ~1.5 GB
                #                                                   ต่อ ~10 ครั้งที่โดนยิง (1440p)
        cfg = self.clutch_cfg()
        mp = self._cl_mini_px()
        mr = pygame.Rect(S(14), S(14), mp, mp)
        self.clutch_draw_minimap(mr, self.clutch_minimap(mp), S)
        y = mr.bottom + S(10)
        call = self.cmap.callout(self.cam.pos[0], self.cam.pos[2])
        if call:
            self._cl_label(call, S(14), C_TEXT, (mr.x + S(6), y), S, align="left", maxw=mp - S(12))
            y += S(24)
        if self.S.get("fps"):
            self._cl_label(f"{self.clock.get_fps():.0f} FPS · {getattr(self, '_perf_path', 'software')}", S(11),
                           C_TEXT, (mr.x + S(6), y), S, bold=False, align="left")
        self._clutch_top(S, cfg)
        self._clutch_feed(S)
        self._clutch_status(S)
        self._clutch_center(S, cfg)
        self._clutch_dmg(S)
        if self.cl_tab:
            bp = self._cl_big_px()
            br = pygame.Rect(0, 0, bp, bp)
            br.center = (W // 2, H // 2)
            surf = self.clutch_minimap(bp)
            if self.gpu_post_available() and getattr(self, "_gl_tab_ok", True):
                # GPU: แผง + ภาพแมพ (คงที่) เป็น texture อัพโหลดครั้งเดียว วาดใต้ overlay (display._gl_tabmap) — overlay มีแค่
                # เครื่องหมาย ; เดิมวาดแผง ~1 Mpx ลง overlay + อัพโหลดทุกเฟรมที่ค้าง Tab (1440p: CPU 3 → 9 ms/เฟรม)
                pn, box = self.clutch_tab_panel(br, surf, S)
                self.post_fx_add(tabmap=(pn, box))
                self.clutch_draw_minimap(br, surf, S, big=True, panel=False)
            else:
                self.clutch_draw_minimap(br, surf, S, big=True)
        rp = self.r_hold_progress() if self.state == "play" else None
        if rp is not None and rp >= 0.25:                       # ค้าง R = เริ่มรอบใหม่ (ฉากเดิม) — เตือนก่อนแบบ GUNFIGHT
            left = (1.0 - rp) * self.R_HOLD_RESTART_MS / 1000.0
            self._cl_label(f"ค้าง R อีก {left:.1f} วิ = เริ่มรอบใหม่ (ปล่อย = ยกเลิก)", S(13), C_GOLD, (W // 2, S(140)), S)

    def _clutch_top(self, S, cfg):
        """กลางบน: เวลารอบ (ก่อนวาง) หรือไอคอน spike (หลังวาง — ไม่มีเลขวินาทีตามเกมจริง เว้นแต่เปิดในตั้งค่า) + 1 v N"""
        W, sp = self.W, self.cl_spike
        cx = W // 2
        top = pygame.Rect(0, 0, S(124), S(68))
        if sp["state"] in ("defused", "detonated"):             # ป้าย DEFUSED/BOOM ขวาไอคอนต้องอยู่บนแผ่นรอง (ขยายสมมาตร)
            lbl = "DEFUSED" if sp["state"] == "defused" else "BOOM"
            top.w = max(S(124), 2 * (S(20) + self.text_width(lbl, S(14), True) + S(8)))
        top.midtop = (cx, S(8))
        self._cl_plate(top, S)
        if self.clutch_side == "atk" and sp["state"] == "carried":
            left = int(math.ceil(max(0.0, self.cl_round_left or 0.0)))
            self.text(f"{left // 60}:{left % 60:02d}", S(26), C_RED if left <= 10 else C_TEXT, (cx, S(28)),
                      center=True, bold=True)
        else:
            from . import clutchaudio
            bl = clutchaudio.blink(self) if sp["state"] == "planted" else 0.0
            col = {"defused": C_GREEN, "detonated": C_GOLD}.get(sp["state"], (int(150 + 105 * bl), 40, 50))
            r = S(11)
            pts = [(cx, S(28) - r), (cx + r, S(28)), (cx, S(28) + r), (cx - r, S(28))]
            self.mark_dirty(pygame.draw.polygon(self.screen, col, pts).inflate(4, 4))
            pygame.draw.polygon(self.screen, (20, 20, 24), pts, 2)
            if sp["state"] == "planted" and cfg["show_secs"]:
                self.text(f"{sp['left']:.0f}", S(18), C_TEXT, (cx + S(20), S(18)), bold=True)
            elif sp["state"] in ("defused", "detonated"):
                self.text("DEFUSED" if sp["state"] == "defused" else "BOOM", S(14), col, (cx + S(20), S(20)), bold=True)
        alive = sum(1 for b in self.bots if b.alive)
        w1, wv = self.text_width("1", S(18), True), self.text_width(" v ", S(16), True)
        x0 = cx - (w1 + wv + self.text_width(str(alive), S(18), True)) // 2
        self.text("1", S(18), C_GREEN if not self.cl_dead else C_DIM, (x0, S(46)), bold=True)
        self.text(" v ", S(16), C_TEXT, (x0 + w1, S(48)), bold=True)
        self.text(str(alive), S(18), _C_ENEMY, (x0 + w1 + wv, S(46)), bold=True)
        if cfg["cue_heard"] and self.gt - self.cl_heard_t < 1.2:
            self._cl_label("ศัตรูได้ยินเสียงเท้า", S(14), C_GOLD, (cx, S(92)), S)
        bd = self.cl_bot_defuse
        if bd is not None and self.cl_result is None:
            p = self.cam.pos
            if math.hypot(p[0] - sp["x"], p[2] - sp["z"]) <= 32.0:
                self._cl_label("ได้ยินเสียงกู้ spike!", S(15), C_RED, (cx, S(118)), S)

    def _clutch_feed(self, S):
        W, g = self.W, self.gt
        maxw = W // 2 - S(110)
        rows = [f for f in self.cl_feed if g - f[2] < 5.0][-4:]
        for i, (txt, col, _t) in enumerate(rows):
            self._cl_label(txt, S(13), col, (W - S(16), S(14) + i * S(24)), S, align="right", maxw=maxw)

    def _clutch_status(self, S):
        """HP/เกราะซ้ายล่าง · กระสุน/ของในมือขวาล่าง"""
        W, H, scr = self.W, self.H, self.screen
        x, y = S(24), H - S(52)
        bw = S(200)
        hf = min(1.0, max(0.0, self.gun_hp / guns.PLAYER_HP))
        sf = min(1.0, max(0.0, self.gun_shield / guns.PLAYER_SHIELD))
        self.mark_dirty(pygame.draw.rect(scr, (8, 20, 28), (x - S(8), y - S(26), S(230), S(50)), border_radius=S(6)))
        self.text(f"{max(0, int(self.gun_hp))}", S(22), C_TEXT if hf > 0.3 else C_RED, (x, y - S(24)), bold=True)
        self.text(f"+{max(0, int(self.gun_shield))}", S(14), (110, 170, 255), (x + S(52), y - S(18)), bold=True)
        pygame.draw.rect(scr, (40, 50, 60), (x, y + S(8), bw, S(8)))
        pygame.draw.rect(scr, (235, 235, 235), (x, y + S(8), int(bw * hf), S(8)))
        pygame.draw.rect(scr, (110, 170, 255), (x, y + S(3), int(bw * sf), S(3)))
        w = self.gun_w()
        if self.cl_equip == "spike":
            main, col = "SPIKE", C_GOLD
        elif self.gun_reload_until > 0:
            main, col = "RELOADING %.1f" % max(0.0, self.gun_reload_until - self.gt), C_GOLD
        else:
            main, col = f"{self.gun_mag} / {w['mag']}", C_RED if self.gun_mag == 0 else C_TEXT
        sub = w["name"] + (" · กำลังหยิบ" if self.gt < self.cl_equip_until else "")
        bw2 = max(self.text_width(main, S(22), True), self.text_width(sub, S(12))) + S(24)
        self.mark_dirty(pygame.draw.rect(scr, (8, 20, 28), (W - S(12) - bw2, H - S(78), bw2, S(52)),
                                         border_radius=S(6)))
        self.text(main, S(22), col, (W - S(24), H - S(76)), right=True, bold=True)
        self.text(sub, S(12), C_DIM, (W - S(24), H - S(46)), right=True)

    def _clutch_center(self, S, cfg):
        """แถบวาง/กู้ (ขีดครึ่งทาง 3.5 วิ) + คำใบ้ + ป้ายผลตอนจบ + หมุด spike (DEF 3 วิแรก)"""
        W, H, g, scr = self.W, self.H, self.gt, self.screen
        sp, s = self.cl_spike, (self.clutch_scen or {}).get("s", "?")
        bar = None
        if self.cl_plant_t0 is not None:
            bar = ("กำลังวาง SPIKE — ห้ามปล่อยคลิก", (g - self.cl_plant_t0) / PLANT_T, None)
        elif self.cl_defuse_t0 is not None:
            bar = ("กำลังกู้ SPIKE" + (" · เก็บครึ่งทางแล้ว" if self.cl_defuse_base >= DEFUSE_HALF else ""),
                   self.clutch_defuse_prog() / DEFUSE_T, DEFUSE_HALF / DEFUSE_T)
        if bar is not None:
            r = pygame.Rect(W // 2 - S(120), H // 2 + S(64), S(240), S(12))
            self.mark_dirty(r.inflate(4, S(8) + 4))                 # รวมขีดครึ่งทางที่ยื่นบน/ล่าง
            pygame.draw.rect(scr, (30, 36, 44), r)
            pygame.draw.rect(scr, C_GOLD, (r.x, r.y, int(r.w * max(0.0, min(1.0, bar[1]))), r.h))
            if bar[2] is not None:
                tx = r.x + int(r.w * bar[2])
                pygame.draw.line(scr, C_TEXT, (tx, r.y - S(3)), (tx, r.bottom + S(2)), 2)
            pygame.draw.rect(scr, C_BORDER, r, 1)
            self._cl_label(bar[0], S(14), C_TEXT, (W // 2, r.y - S(16)), S)
        res = self.cl_result
        if res is not None:
            self._cl_label("ชนะ" if res["win"] else "แพ้", S(40), C_GREEN if res["win"] else C_RED,
                           (W // 2, int(H * 0.36)), S)
            self._cl_label(why_text(self.clutch_side, res["why"], (sp or {}).get("state") != "carried"), S(16), C_TEXT,
                           (W // 2, int(H * 0.36) + S(40)), S, bold=False)
        maxw = W - S(60)
        if self.cl_dead:
            hint = "คุณตาย — รอสรุปผล"
        elif self.clutch_side == "atk" and sp["state"] == "carried":
            if self.cl_equip == "spike":
                if not self.clutch_in_zone():
                    hint = f"ต้องเข้าไปในพื้นที่วาง (ไซต์ {s}) ก่อนคลิกค้าง · 1 = กลับปืน"
                elif self.cl_air:
                    hint = "ลอยอยู่ — ต้องยืนบนพื้น/หลังกล่องก่อนวาง"
                elif not self.clutch_plant_floor_ok():
                    hint = "ยืนคร่อมขอบต่างระดับ — ขยับเข้าไปบนพื้นเรียบก่อนวาง · 1 = กลับปืน"
                else:
                    hint = "คลิกซ้ายค้าง 4 วิ = วาง spike (ยืนนิ่ง ยิงไม่ได้) · 1 = กลับปืน"
            else:
                hint = "กด 4 ถือ spike · คลิกค้างในไซต์เพื่อวาง · Tab = แมพใหญ่"
        elif self.clutch_side == "atk":
            hint = "SPIKE ลงแล้ว — เฝ้าไว้อย่าให้กู้ได้ · Tab = แมพใหญ่"
        elif sp["state"] == "planted":
            hint = ("ค้าง 4/F 7 วิ = กู้ (ครึ่งทาง 3.5 วิ เก็บไว้)" if self.clutch_can_defuse()
                    else "กด 4/F ค้างใกล้ spike เพื่อกู้ · Tab = แมพใหญ่")
        else:
            hint = ""
        if hint and res is None:
            self._cl_label(hint, S(13), C_TEXT, (W // 2, H - S(98)), S, bold=False, maxw=maxw)
        if g < 3.0 and res is None:
            n = len(self.bots)
            goal = (f"เลาะไปวาง spike ที่ไซต์ {s} ก่อนหมดเวลา — ศัตรู {n} ตัว" if self.clutch_side == "atk"
                    else f"spike ลงที่ไซต์ {s} แล้ว — ไปกู้ให้ทัน ศัตรู {n} ตัว")
            mw = W - 2 * (self._cl_mini_px() + S(36))
            self._cl_label(goal, S(16), C_GOLD, (W // 2, int(H * 0.28)), S, maxw=mw)
            self._cl_label("Space = กระโดด · กระโดดแล้วกด Ctrl ค้าง (หดขา) = ขึ้นกล่องครึ่งตัว/ลัง · ค้าง Shift ตอนลง = เงียบ",
                           S(12), C_TEXT, (W // 2, int(H * 0.28) + S(30)), S, bold=False, maxw=mw)
        if self.cl_warn and g < 6.0:
            self._cl_label(self.cl_warn, S(12), C_RED, (W // 2, H - S(124)), S, bold=False, maxw=maxw)
        if self.clutch_side == "def" and g < 3.0 and sp["state"] == "planted":
            vo = self.view_offset()                             # ฉายด้วยกล้องที่เด้งตามรีคอยล์แบบเดียวกับโลก GL (draw_world)
            p0, y0 = self.cam.pitch, self.cam.yaw
            if vo:
                self.cam.pitch = max(-math.radians(89.0), min(math.radians(89.0), p0 + vo[0]))
                self.cam.yaw = y0 + vo[1]
            try:
                pr = self.project((sp["x"], sp["y"] + 0.3, sp["z"]), self.fl())
            finally:
                self.cam.pitch, self.cam.yaw = p0, y0
            if pr and 0 <= pr[0] < W and 0 <= pr[1] < H:
                x, y, r = int(pr[0]), int(pr[1]), S(7)
                self.mark_dirty(pygame.draw.polygon(scr, _C_SPIKE, [(x, y - r), (x + r, y), (x, y + r), (x - r, y)])
                                .inflate(4, 4))
                d = math.hypot(sp["x"] - self.cam.pos[0], sp["z"] - self.cam.pos[2])
                self._cl_label(f"SPIKE {d:.0f}m", S(12), _C_SPIKE, (x, y - S(20)), S)

    def _clutch_dmg(self, S):
        """ลูกศรทิศที่โดนยิง (โค้งรอบกลางจอ ชี้ไปหาคนยิง) — จางใน 1.2 วิ ; polygon เอง (ไม่มีตัวอักษรลูกศรในฟอนต์)"""
        cx, cy = self.W // 2, self.H // 2
        r0, r1 = S(84), S(104)
        for bearing, t0 in self.cl_dmg_ind:
            k = max(0.0, 1.0 - (self.gt - t0) / 1.2)
            rel = bearing - self.cam.yaw
            arc = [rel - 0.28 + 0.14 * i for i in range(5)]
            pts = [(cx + math.sin(a) * r1, cy - math.cos(a) * r1) for a in arc]
            pts += [(cx + math.sin(a) * r0, cy - math.cos(a) * r0) for a in reversed(arc)]
            self.mark_dirty(pygame.draw.polygon(self.screen, (255, 60, 70, int(80 + 150 * k)), pts).inflate(4, 4))

    # ───────────────────────── ภาพสำรอง (ไม่มี GPU/ตัววาดแมพ) + กติกาใต้เลขนับถอยหลัง ─────────────────────────
    def clutch_gl_reason(self):
        """ทำไมไม่มีโลก 3D (ต่อท้าย "โหมดนี้"/"โหมด CLUTCH"): GPU ปิด = เปิดใน SETTINGS ; ตัววาดแมพล้มในเซสชันนี้ (ธงค้างทั้งเซสชัน)
        = ต้องเปิดโปรแกรมใหม่ — เดิมบอก "เปิดใน SETTINGS" ทั้งที่ GPU เปิดอยู่แล้ว"""
        if not (getattr(self, "_clutch_gl_failed", False) or getattr(self, "_clutch_gl_off", False)) \
                and not self.gpu_world_active():
            return "ต้องใช้ GPU (เปิดใน SETTINGS)"
        return "ใช้ไม่ได้: ตัววาดแมพ 3D ล้ม — ปิดแล้วเปิดโปรแกรมใหม่"

    def clutch_draw_soft(self):
        """software/headless: ฟ้า + พื้น + ข้อความเหตุ (clutch_gl_reason) — ถูก ไม่พัง และไม่วาดห้องซ้อมเดิม (§7)"""
        W, H, scr = self.W, self.H, self.screen
        hz = int(max(0, min(H, H / 2 + self.fl() * math.tan(self.cam.pitch))))
        scr.fill(C_SKY_TOP)
        if hz > 0:
            pygame.draw.rect(scr, C_SKY, (0, 0, W, hz))
        if hz < H:
            pygame.draw.rect(scr, (46, 50, 44), (0, hz, W, H - hz))
        self.mark_full()
        sc = self.hud_scale()
        self.text(f"โหมด CLUTCH {self.clutch_gl_reason()} — นี่คือภาพสำรอง", int(15 * sc), C_PALE_GOLD,
                  (W // 2, int(H * 0.2)), center=True, bold=True)

    def clutch_rule(self):
        """บรรทัดกติกาใต้เลขนับถอยหลัง (insight.countdown_rule)"""
        s = (self.clutch_scen or {}).get("s", "?")
        n = len(self.bots) if self.brain is not None else self.clutch_n
        if self.clutch_side == "atk":
            return (f"ATK 1v{n} · เลาะไปวาง spike ที่ไซต์ {s} ก่อนหมดเวลา · 4 = ถือ spike · คลิกค้าง 4 วิ = วาง · "
                    f"1 = ปืน · Tab = แมพ")
        return f"DEF 1v{n} · spike ลงไซต์ {s} แล้ว — ค้าง 4/F ใกล้ spike 7 วิ = กู้ (ครึ่งทาง 3.5 วิ เก็บไว้) · Tab = แมพ"
