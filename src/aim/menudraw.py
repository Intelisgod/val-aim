# -*- coding: utf-8 -*-
"""เมนูหลัก + Ranks + widget (button/slider/checkbox) — MenuDrawMixin (ย้าย verbatim + ตะเข็บ MENU_EXTRAS)"""

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
from . import registry
from . import rankicons

class MenuDrawMixin:
    def zone(self, rect, fn):
        self.zones.append((pygame.Rect(rect), fn))
        return pygame.Rect(rect)

    def button(self, rect, label, fn, active=False, size=14, danger=False):
        r = self.zone(rect, fn)
        hov = r.collidepoint(pygame.mouse.get_pos())
        br = min(r.h // 2, 18)   # pill
        bg = C_RED if active else (38, 56, 74) if hov else C_PANEL
        pygame.draw.rect(self.screen, bg, r, border_radius=br)
        bcol = C_RED if (active or hov or danger) else C_BORDER
        pygame.draw.rect(self.screen, bcol, r, 2 if (active or hov) else 1, border_radius=br)
        self.text(label, size, C_TEXT if active else C_RED if danger else C_DIM if not hov else C_TEXT,
                  r.center, center=True, bold=True)
        return r

    def checkbox(self, x, y, label, key, obj):
        box = pygame.Rect(x, y, 16, 16)
        def flip():
            obj[key] = not obj.get(key)
            save_data(self.data)
        self.zone((x, y - 2, 170, 20), flip)
        pygame.draw.rect(self.screen, C_PANEL, box, border_radius=2)
        pygame.draw.rect(self.screen, C_BORDER, box, 1, border_radius=2)
        if obj.get(key):
            pygame.draw.rect(self.screen, C_RED, box.inflate(-6, -6), border_radius=1)
        self.text(label, 13, C_TEXT, (x + 24, y - 1))

    def slider(self, sid, x, y, w, lo, hi, step, obj, key, fmt="{}"):
        r = pygame.Rect(x, y, w, 14)
        self.sliders[sid] = (r, lo, hi, step, obj, key)
        self.zone(r.inflate(0, 8), lambda: setattr(self, "drag", sid))
        track = pygame.Rect(x, y + 5, w, 4)
        pygame.draw.rect(self.screen, C_BORDER, track, border_radius=2)
        v = obj[key]
        frac = (v - lo) / (hi - lo)
        hx = x + int(frac * w)
        pygame.draw.rect(self.screen, C_RED, (x, y + 5, hx - x, 4), border_radius=2)
        pygame.draw.circle(self.screen, C_TEXT, (hx, y + 7), 7)
        self.text(fmt.format(v), 13, C_RED, (x + w + 14, y - 2), bold=True)

    def drag_slider(self, mx):
        if not self.drag or self.drag not in self.sliders:
            return
        r, lo, hi, step, obj, key = self.sliders[self.drag]
        frac = max(0.0, min(1.0, (mx - r.x) / r.w))
        v = lo + frac * (hi - lo)
        v = round(v / step) * step
        v = round(v, 4)
        if isinstance(lo, int) and isinstance(step, int):
            v = int(v)
        if obj[key] != v:
            obj[key] = v

    def section_header(self, label, x, y, w, color=C_RED):
        """หัวข้อ section แบบ Aim Lab: label uppercase ตัวเล็ก + เส้นใต้บางสีแดง"""
        self.text(label.upper(), 12, color, (x, y), bold=True)
        ly = y + 18
        pygame.draw.line(self.screen, color, (x, ly), (x + w, ly), 1)

    def mode_icon(self, mid, cx, cy, col):
        """วาดไอคอน vector ของแต่ละโหมดด้วย pygame primitives (ขนาด ~22px)"""
        scr = self.screen
        if mid == "flick":
            pygame.draw.circle(scr, col, (cx, cy), 11, 2)
            pygame.draw.circle(scr, col, (cx, cy), 5, 2)
            pygame.draw.circle(scr, col, (cx, cy), 1)
        elif mid == "precision":
            pygame.draw.circle(scr, col, (cx, cy), 5, 2)
            pygame.draw.line(scr, col, (cx - 11, cy), (cx - 6, cy), 2)
            pygame.draw.line(scr, col, (cx + 6, cy), (cx + 11, cy), 2)
            pygame.draw.line(scr, col, (cx, cy - 11), (cx, cy - 6), 2)
            pygame.draw.line(scr, col, (cx, cy + 6), (cx, cy + 11), 2)
        elif mid == "tracking":
            pygame.draw.circle(scr, col, (cx, cy), 6, 2)
            pygame.draw.line(scr, col, (cx - 12, cy), (cx - 7, cy), 2)
            pygame.draw.polygon(scr, col, [(cx - 12, cy), (cx - 8, cy - 3), (cx - 8, cy + 3)])
            pygame.draw.line(scr, col, (cx + 7, cy), (cx + 12, cy), 2)
            pygame.draw.polygon(scr, col, [(cx + 12, cy), (cx + 8, cy - 3), (cx + 8, cy + 3)])
        elif mid == "reaction":
            pygame.draw.circle(scr, col, (cx, cy), 11, 2)
            pygame.draw.line(scr, col, (cx, cy - 6), (cx, cy + 2), 3)
            pygame.draw.circle(scr, col, (cx, cy + 6), 2)
        elif mid == "strafe":
            for dx, dy, lbl in [(0, -1, "W"), (-1, 0, "A"), (0, 1, "S"), (1, 0, "D")]:
                px, py = cx + dx * 12, cy + dy * 12
                self.text(lbl, 10, col, (px, py), center=True, bold=True)
        elif mid == "gun":
            # ปืน: ลำกล้อง + ด้าม + วงสโคป
            pygame.draw.line(scr, col, (cx - 12, cy - 2), (cx + 10, cy - 2), 3)
            pygame.draw.line(scr, col, (cx - 4, cy - 1), (cx - 7, cy + 9), 3)
            pygame.draw.circle(scr, col, (cx + 2, cy - 7), 4, 1)
            pygame.draw.line(scr, col, (cx + 2, cy - 10), (cx + 2, cy - 4), 1)
        elif mid == "sniper":
            pygame.draw.circle(scr, col, (cx, cy), 11, 2)
            pygame.draw.circle(scr, col, (cx, cy), 6, 1)
            pygame.draw.line(scr, col, (cx - 11, cy), (cx + 11, cy), 1)
            pygame.draw.line(scr, col, (cx, cy - 11), (cx, cy + 11), 1)
            pygame.draw.circle(scr, col, (cx, cy), 1)
        elif mid == "spray":
            # ลายรีคอยล์: เส้นซิกแซกพุ่งขึ้น
            pts = [(cx, cy + 11), (cx - 1, cy + 4), (cx + 3, cy - 1),
                   (cx - 3, cy - 6), (cx + 2, cy - 11)]
            pygame.draw.lines(scr, col, False, pts, 2)
            pygame.draw.circle(scr, col, (cx + 2, cy - 11), 2)
        elif mid == "dodge":
            # คนกับลูกศรหลบ
            pygame.draw.circle(scr, col, (cx - 3, cy - 6), 3, 2)
            pygame.draw.line(scr, col, (cx - 3, cy - 3), (cx - 3, cy + 5), 2)
            pygame.draw.line(scr, col, (cx - 3, cy + 5), (cx - 7, cy + 11), 2)
            pygame.draw.line(scr, col, (cx - 3, cy + 5), (cx + 1, cy + 11), 2)
            pygame.draw.line(scr, col, (cx + 4, cy - 2), (cx + 11, cy - 2), 2)
            pygame.draw.polygon(scr, col, [(cx + 11, cy - 2), (cx + 7, cy - 5), (cx + 7, cy + 1)])
        elif mid == "placement":
            # crosshair ระดับหัว + เส้นแนวระดับ
            pygame.draw.line(scr, col, (cx - 11, cy - 5), (cx + 11, cy - 5), 1)
            pygame.draw.circle(scr, col, (cx, cy - 5), 4, 2)
            pygame.draw.line(scr, col, (cx, cy - 1), (cx, cy + 11), 2)
        elif mid == "switch":
            # สามวงเรียง + ลูกศรสลับ
            for ddx in (-9, 0, 9):
                pygame.draw.circle(scr, col, (cx + ddx, cy - 2), 3, 2)
            pygame.draw.line(scr, col, (cx - 9, cy + 8), (cx + 9, cy + 8), 1)
            pygame.draw.polygon(scr, col, [(cx + 9, cy + 8), (cx + 5, cy + 5), (cx + 5, cy + 11)])
            pygame.draw.polygon(scr, col, [(cx - 9, cy + 8), (cx - 5, cy + 5), (cx - 5, cy + 11)])

    def draw_menu(self):
        W, H = self.W, self.H
        self.screen.fill(C_DARKER)

        # ── จัดเลย์เอาต์แนวตั้งให้สมดุล: รวม controls + แผงล่างเป็น "บล็อกเดียว" แล้วกึ่งกลางแนวตั้ง ──
        # จอเตี้ย/หน้าต่างเล็ก → top ~20 (ชิดบนเหมือนเดิม ไม่ล้น); จอสูง/เต็มจอ → ดันลงกลาง ลบรูช่องว่างกลาง
        extras_present = bool(registry.MENU_EXTRAS)
        ctrl_h = 462 if extras_present else 424     # ความสูงโซนคอนโทรล (title→ปุ่มล่างสุด) วัดจาก top
        panel_gap, panel_cap = 18, 320
        block_h = ctrl_h + panel_gap + panel_cap
        top = max(20, (H - block_h) // 2)

        self.text("VAL//AIM", 42, C_TEXT, (W // 2, top + 24), center=True, bold=True)
        self.text("3D FPS RANGE TRAINER — PYTHON EDITION", 12, C_DIM, (W // 2, top + 58), center=True)

        # การ์ดโหมด — กริด 5 คอลัมน์ × 2 แถว (10 โหมด) เลขกำกับ 1-9,0
        cols, rows = 5, 2
        gap = 10
        max_grid_w = min(W - 80, 5 * 198 + 4 * gap)
        cw = (max_grid_w - (cols - 1) * gap) // cols
        chh = 100
        grid_w = cols * cw + (cols - 1) * gap
        x0, y0 = (W - grid_w) // 2, top + 78
        num_keys = "1234567890"
        for i, (mid, name, desc) in enumerate(MODES):
            cxi, ryi = i % cols, i // cols
            r = pygame.Rect(x0 + cxi * (cw + gap), y0 + ryi * (chh + gap), cw, chh)
            def pick(m=mid):
                self.mode = m
            self.zone(r, pick)
            sel = (mid == self.mode)
            hov = r.collidepoint(pygame.mouse.get_pos())
            # เงา elevation
            pygame.draw.rect(self.screen, (4, 12, 18), r.move(2, 3), border_radius=5)
            pygame.draw.rect(self.screen, (31, 46, 61) if (sel or hov) else C_PANEL, r, border_radius=5)
            pygame.draw.rect(self.screen, C_RED if sel else C_BORDER, r, 2, border_radius=5)
            # แถบ accent บนสุด (เฉพาะตอนเลือก)
            if sel:
                pygame.draw.rect(self.screen, C_RED, (r.x + 2, r.y + 1, r.w - 4, 3), border_radius=2)
            # เลขกำกับคีย์ลัด
            self.text(num_keys[i], 11, C_DIM if not sel else C_RED, (r.x + 8, r.y + 6), bold=True)
            # ไอคอน vector
            ic = C_RED if sel else C_DIM if not hov else C_TEXT
            self.mode_icon(mid, r.centerx, r.y + 24, ic)
            self.text(name, 15, C_RED if sel else C_TEXT, (r.centerx, r.y + 48), center=True, bold=True)
            # ตัดบรรทัดคำอธิบาย: memo ต่อ (desc, ความกว้างการ์ด) — desc คงที่จากตาราง MODES
            # เดิม font.size ต่อคำ ~60-100 ครั้ง/เฟรม (shaping ไทยแพง) ทั้งที่ผลเท่าเดิมทุกเฟรม
            wcache = getattr(self, "_wrap_cache", None)
            if wcache is None:
                wcache = {}
                self._wrap_cache = wcache
            lines = wcache.get((desc, cw))
            if lines is None:
                if len(wcache) > 256:
                    wcache.clear()   # กันโตไม่จำกัดจากการลาก resize ผ่านหลายความกว้าง
                words, line, lines = desc.split(" "), "", []
                fnt = self.font(11)
                for w_ in words:
                    t2 = (line + " " + w_).strip()
                    if fnt.size(t2)[0] > cw - 14:
                        lines.append(line)
                        line = w_
                    else:
                        line = t2
                lines.append(line)
                wcache[(desc, cw)] = lines
            for j, ln in enumerate(lines[:2]):
                self.text(ln, 11, C_DIM, (r.centerx, r.y + 66 + j * 15), center=True)

        # แถวตัวเลือก (ใต้กริด 2 แถว)
        y1 = y0 + rows * chh + (rows - 1) * gap + 18
        x = W // 2 - 430
        if self.mode not in ("reaction", "sniper"):
            self.text("เวลา", 12, C_DIM, (x, y1 + 8))
            for i, d in enumerate(DURATIONS):
                def setd(v=d):
                    self.duration = v
                self.button((x + 50 + i * 58, y1, 52, 30), f"{d}s", setd, active=(self.duration == d), size=13)
            x += 240
            # ขนาดเป้า — spray/gunfight ใช้บอทขนาดคงที่จึงไม่โชว์
            if self.mode not in ("spray", "gun"):
                self.text("ขนาดเป้า", 12, C_DIM, (x, y1 + 8))
                for i, s in enumerate(["small", "medium", "large"]):
                    def sets(v=s):
                        self.size_key = v
                    self.button((x + 70 + i * 62, y1, 56, 30), SIZE_TH[s], sets, active=(self.size_key == s), size=13)
                x += 270
        if self.mode == "reaction":
            self.text("Reaction Type", 12, C_DIM, (x, y1 + 8))
            for i, v in enumerate(["static", "flick"]):
                def setv(vv=v):
                    self.reaction_variant = vv
                self.button((x + 110 + i * 74, y1, 68, 30), v.upper(), setv,
                            active=(self.reaction_variant == v), size=12)
            x += 280
        if self.mode == "spray":
            self.text("อาวุธ (V สลับ)", 12, C_DIM, (x, y1 + 8))
            for i, v in enumerate(["vandal", "phantom"]):
                def setw(vv=v):
                    self.spray_weapon = vv
                    self.spray_mag = SPRAY_WEAPONS[vv]["mag"]
                self.button((x + 110 + i * 84, y1, 78, 30), v.upper(), setw,
                            active=(self.spray_weapon == v), size=12)
            x += 290
        if self.mode == "gun":
            # GUNFIGHT ไม่ใช้ขนาดเป้า (บอทหุ่นคนขนาดจริง) — แถวนี้แทนที่ตัวเลือกขนาด
            from .guns import WEAPON_ORDER, WEAPONS as _WP
            from .gunplay import GUN_DRILLS
            gx = W // 2 - 430 + 240
            self.text("ปืน (V)", 12, C_DIM, (gx, y1 + 8))
            short = {"operator": "OP", "vandal": "VANDAL", "phantom": "PHANTOM", "sheriff": "SHERIFF"}
            for i, v in enumerate(WEAPON_ORDER):
                def setg(vv=v):
                    self.gun_weapon = vv
                self.button((gx + 50 + i * 70, y1, 66, 30), short[v], setg,
                            active=(self.gun_weapon == v), size=10)
            # แถวดริล: บรรทัดที่สอง ฝั่งซ้ายของปุ่ม START (ไม่ทับ)
            gx2, yd = W // 2 - 430, y1 + 40
            self.text("ดริล (B)", 12, C_DIM, (gx2, yd + 8))
            short_d = {"duel": "DUEL", "hold": "OP HOLD", "quick": "QUICK", "repo": "REPO"}
            for i, (did, dname, _d) in enumerate(GUN_DRILLS):
                def setdr(vv=did):
                    self.gun_drill = vv
                self.button((gx2 + 56 + i * 56, yd, 52, 30), short_d[did], setdr,
                            active=(self.gun_drill == did), size=9)
        self.button((W // 2 + 130, y1, 96, 30), "INSIGHT", lambda: self.open_insight(), size=12)
        self.button((W // 2 + 232, y1, 96, 30), "SETTINGS", lambda: setattr(self, "state", "settings"), size=12)
        if self.mode not in ("strafe", "sniper", "spray", "dodge", "gun"):
            self.button((W // 2 + 334, y1, 96, 30), "RANKS", lambda: setattr(self, "state", "ranks"), size=12)

        # ปุ่มเริ่ม
        sr = pygame.Rect(W // 2 - 150, y1 + 46, 300, 50)
        self.zone(sr, self.start_countdown)
        hov = sr.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, (224, 48, 64) if hov else C_RED, sr, border_radius=3)
        self.text("START TRAINING  (ENTER)", 17, (255, 255, 255), sr.center, center=True, bold=True)
        self.text("เมาส์ เล็ง · คลิกซ้าย ยิง · RR เริ่มใหม่ · ESC พัก · F11 เต็มจอ", 12, C_DIM,
                  (W // 2, y1 + 110), center=True)

        # ── ตะเข็บ MENU_EXTRAS: ปุ่มเสริมจากโมดูลอื่น (ว่าง=ไม่เปลี่ยนหน้าตาเดิม) ──
        extras_h = 0
        if registry.MENU_EXTRAS:
            ebw, ebg = 176, 12
            etot = len(registry.MENU_EXTRAS) * ebw + (len(registry.MENU_EXTRAS) - 1) * ebg
            ex = W // 2 - etot // 2
            for _it in registry.MENU_EXTRAS:
                self.button((ex, y1 + 126, ebw, 30), _it["label"],
                            (lambda f=_it["on_click"]: f(self)), size=12)
                ex += ebw + ebg
            extras_h = 40
        # แผงล่าง 3 คอลัมน์: profile | leaderboard | rank chart
        # บล็อกถูกจัดกึ่งกลางแนวตั้งด้วย top แล้ว → แผงต่อท้ายคอนโทรลด้วยระยะคงที่ (ไม่ลอยห่างเป็นรูกลางจอ)
        py = y1 + 134 + extras_h
        ph = min(panel_cap, H - py - 24)
        if ph > 120:
            pw, pgap = 340, 14
            total_w = pw * 3 + pgap * 2
            px0 = W // 2 - total_w // 2
            for ci, drawer in enumerate((self.draw_profile_panel, self.draw_lb_panel, self.draw_rank_panel)):
                pr = pygame.Rect(px0 + ci * (pw + pgap), py, pw, ph)
                pygame.draw.rect(self.screen, (4, 12, 18), pr.move(2, 3), border_radius=5)
                pygame.draw.rect(self.screen, C_PANEL, pr, border_radius=5)
                pygame.draw.rect(self.screen, C_BORDER, pr, 1, border_radius=5)
                drawer(pr)

    def draw_profile_panel(self, r):
        self.section_header("PROFILE", r.x + 14, r.y + 12, r.w - 28)
        name = (self.data.get("name") or "PLAYER").upper()
        self.text(name[:16], 22, C_TEXT, (r.centerx, r.y + 48), center=True, bold=True)
        # ดึงสถิติของโหมด+config ที่เลือก
        if self.mode == "reaction":
            hist = self.history_for("reaction", self.reaction_variant)
            rts = [e.get("rt", 0) for e in hist if e.get("rt", 0) > 0]
            best = min(rts) if rts else None
            rankinfo = get_rt_rank(best, self.reaction_variant) if best else None
            best_lbl = f"{round(best)}ms" if best else "—"
        elif self.mode in ("strafe", "sniper"):
            hist = self.history_for(self.mode)
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = None
            best_lbl = f"{best:,}" if best is not None else "—"
        elif self.mode == "gun":
            hist = [e for e in self.history_for("gun", self.gun_weapon, duration=self.duration)
                    if e.get("drill", "duel") == self.gun_drill]
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = None
            best_lbl = f"{best:,}" if best is not None else "—"
        elif self.mode == "spray":
            hist = [e for e in self.history_for("spray", duration=self.duration)
                    if e.get("variant", "vandal") == self.spray_weapon]
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = get_rank(best, self.duration, self.size_key, "spray") if best is not None else None
            best_lbl = f"{best:,}" if best is not None else "—"
        else:
            hist = self.history_for(self.mode, duration=self.duration, size=self.size_key)
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = get_rank(best, self.duration, self.size_key, self.mode) if best is not None else None
            best_lbl = f"{best:,}" if best is not None else "—"
        sessions = len(hist)
        accs = [e.get("acc", 0) for e in hist if e.get("acc") is not None]
        avg_acc = round(sum(accs) / len(accs)) if accs else 0
        if sessions == 0:
            self.text("ยังไม่มีสถิติ — เริ่มเล่นเลย", 13, C_DIM, (r.centerx, r.centery), center=True)
            return
        # โล่แรงค์ + ชื่อ
        cy = r.y + 110
        if rankinfo:
            _, rname, rcol = rankinfo
            rcol_rgb = hexrgb(rcol) if isinstance(rcol, str) else rcol
            self.draw_rank_emblem(r.centerx, cy, 56, rname, rcol_rgb)
            self.text(rname, 16, rcol_rgb, (r.centerx, cy + 42), center=True, bold=True)
        else:
            self.text("โหมดฝึกซ้อม", 14, C_DIM, (r.centerx, cy + 6), center=True)
        # สถิติย่อย 3 ช่อง
        sy = r.bottom - 56
        stats = [(best_lbl, "BEST"), (str(sessions), "SESSIONS"), (f"{avg_acc}%", "AVG ACC")]
        sw = (r.w - 28) // 3
        for i, (v, l) in enumerate(stats):
            scx = r.x + 14 + sw * i + sw // 2
            self.text(v, 18, C_RED, (scx, sy), center=True, bold=True)
            self.text(l, 10, C_DIM, (scx, sy + 24), center=True)

    def draw_lb_panel(self, r):
        label = MODE_NAME[self.mode]
        if self.mode == "reaction":
            label += f" · {self.reaction_variant.upper()}"
        elif self.mode == "gun":
            label += f" · {self.gun_weapon.upper()} · {self.gun_drill.upper()}"
        self.section_header(f"TOP 5 — {label}", r.x + 14, r.y + 12, r.w - 28, color=C_GOLD)
        rows = [e for e in self.data["leaderboard"] if e.get("mode") == self.mode and spray_current(e) and
                (self.mode != "reaction" or e.get("variant", "static") == self.reaction_variant) and
                (self.mode != "gun" or (e.get("variant") == self.gun_weapon and e.get("drill", "duel") == self.gun_drill))]
        best = {}
        for e in rows:
            nm = (e.get("name") or "ANON").upper()
            cur = best.get(nm)
            if cur is None or (self.mode == "reaction" and e.get("rt", 9e9) < cur.get("rt", 9e9)) \
                    or (self.mode != "reaction" and e.get("score", 0) > cur.get("score", 0)):
                best[nm] = e
        rows = sorted(best.values(),
                      key=(lambda e: e.get("rt", 9e9)) if self.mode == "reaction" else (lambda e: -e.get("score", 0)))[:5]
        if not rows:
            self.text("ยังไม่มีสถิติในโหมดนี้ — เล่นแล้วกด SAVE SCORE", 12, C_DIM, (r.centerx, r.centery), center=True)
            return
        y = r.y + 44
        for i, e in enumerate(rows):
            self.text(f"{i + 1}", 12, C_DIM, (r.x + 16, y), bold=True)
            self.text((e.get("name") or "ANON")[:14], 13, C_TEXT, (r.x + 36, y - 1), bold=True)
            if self.mode == "reaction":
                self.text(f"{e.get('rt', 0)}ms · {e.get('acc', 0)}%", 12, C_RED, (r.right - 14, y), right=True, bold=True)
            else:
                self.text(f"{e.get('score', 0):,} · {e.get('acc', 0)}%", 12, C_RED, (r.right - 14, y), right=True, bold=True)
            y += 24
            if y > r.bottom - 18:
                break

    def draw_rank_emblem(self, cx, cy, size, rank_name, color):
        """วาดสัญลักษณ์แรงค์: ใช้ไอคอนจริงจาก assets/rank_icons ก่อน (ทุกจอที่เรียกได้ไอคอนเดียวกัน)
        ไม่มีไฟล์/โหลดพลาด = โล่เหลี่ยม + chevron วาดเองแบบเดิม (ออฟไลน์/asset หายก็ไม่พัง)"""
        ico = rankicons.icon(rank_name, size)
        if ico is not None:
            self.screen.blit(ico, (cx - ico.get_width() // 2, cy - ico.get_height() // 2))
            return
        if isinstance(color, str):
            color = hexrgb(color)
        base, lvl = parse_rank(rank_name)
        scr = self.screen
        s = size
        dark = tuple(max(0, int(c * 0.45)) for c in color)
        light = tuple(min(255, int(c + 70)) for c in color)
        # โล่หกเหลี่ยมแนวตั้ง (ปลายแหลมบน-ล่าง)
        w, h = int(s * 0.74), s
        pts = [(cx, cy - h // 2), (cx + w // 2, cy - h // 5), (cx + w // 2, cy + h // 5),
               (cx, cy + h // 2), (cx - w // 2, cy + h // 5), (cx - w // 2, cy - h // 5)]
        pygame.draw.polygon(scr, dark, pts)
        inner = [(int(cx + (px - cx) * 0.74), int(cy + (py - cy) * 0.74)) for px, py in pts]
        pygame.draw.polygon(scr, color, inner)
        pygame.draw.polygon(scr, light, pts, max(1, s // 18))
        if base == "Radiant":
            # รัศมีทอง + เพชรกลาง
            for ang in range(0, 360, 45):
                rad = math.radians(ang)
                pygame.draw.line(scr, light,
                                 (cx + math.cos(rad) * s * 0.30, cy + math.sin(rad) * s * 0.30),
                                 (cx + math.cos(rad) * s * 0.52, cy + math.sin(rad) * s * 0.52),
                                 max(1, s // 16))
            d = s * 0.17
            pygame.draw.polygon(scr, (255, 255, 255),
                                [(cx, cy - d), (cx + d * 0.8, cy), (cx, cy + d), (cx - d * 0.8, cy)])
        else:
            n = lvl if lvl else 3   # Immortal/ไม่มีระดับ แสดง 3 ขีด
            cw = max(2, int(s * 0.30))
            ch = max(1, int(s * 0.12))
            spacing = max(2, int(s * 0.17))
            thick = max(1, s // 16)
            for i in range(n):
                yy = cy - (n - 1) * spacing * 0.5 + i * spacing - ch * 0.3
                pygame.draw.lines(scr, (255, 255, 255), False,
                                  [(cx - cw // 2, yy + ch), (cx, yy), (cx + cw // 2, yy + ch)], thick)

    def draw_rank_panel(self, r, sc=1.0):
        # sc>1 = โหมดใหญ่สำหรับหน้า RANKS เต็ม (เมนูเรียก sc=1.0 เล็กเท่าเดิม)
        def Z(v):
            return int(round(v * sc))
        if self.mode in ("strafe", "sniper"):
            self.text("โหมดนี้ไม่มีระบบแรงค์ (โหมดฝึกซ้อม)", Z(12), C_DIM, (r.centerx, r.centery), center=True)
            return
        if self.mode == "gun":
            self.section_header("GUNFIGHT — กติกาปืนตามเกมจริง", r.x + Z(14), r.y + Z(12), r.w - Z(28))
            from .guns import WEAPONS as _WP
            w = _WP[self.gun_weapon]
            bands = " / ".join(f"{b[1]}·{b[2]}·{b[3]} ≤{b[0]}m" for b in w["dmg"])
            lines = [f"{w['name']}: หัว·ตัว·ขา {bands}",
                     f"ยิง {w['rps']:g} นัด/วิ · แม็ก {w['mag']} · รีโหลด {w['reload']}s",
                     f"สเปรดยืน {w['spread']['stand']}° เดิน +{w['spread']['walk']}° วิ่ง +{w['spread']['run']}°",
                     ("สโคป " + "/".join(f"{z:g}x" for z in w["zooms"]) + (" — ยิงแล้วหลุดสโคป" if w.get("unscope_on_shot") else ""))
                     if w["zooms"] else "ไม่มี ADS",
                     "บอท: HP 100 + เกราะ 50 (รับ 66%) — Vandal 4 ตัว/1 หัว, Op 1 ตัว/2 ขา",
                     "คุม: RMB สโคป/ADS · WASD เดิน · CTRL ย่อ · R รีโหลด",
                     "ยังไม่จัดแรงค์ — ดู K/D · TTK · HS% · ACC ในผลลัพธ์"]
            for i, ln in enumerate(lines):
                self.text(ln, Z(11), C_TEXT if i == 0 else C_DIM, (r.x + Z(14), r.y + Z(40) + i * Z(20)))
            return
        if self.mode == "reaction":
            self.section_header(f"RANK CHART — REACTION {self.reaction_variant.upper()}",
                                r.x + Z(14), r.y + Z(12), r.w - Z(28))
            data = [(rt_thresh(t, self.reaction_variant), n, c) for t, n, c in REACTION_RT_RANKS]
            data = list(reversed(data))
            fmt = lambda v: ("> 350ms" if v == float("inf") else f"≤ {v:.0f}ms")
        else:
            self.section_header(f"RANK CHART — {MODE_NAME[self.mode]} {self.duration}s {SIZE_TH[self.size_key]}",
                                r.x + Z(14), r.y + Z(12), r.w - Z(28))
            data = scaled_ranks(self.duration, self.size_key, self.mode)
            fmt = lambda v: f"{v:,}+"
        n = len(data)
        rows_per_col = (n + 1) // 2
        rh = min(Z(22), (r.h - Z(50)) // rows_per_col)
        emb = Z(17)
        for i, (v, name, col) in enumerate(data):
            cx = r.x + Z(14) + (i // rows_per_col) * (r.w // 2)
            cy = r.y + Z(44) + (i % rows_per_col) * rh
            self.draw_rank_emblem(cx + emb // 2, cy + rh // 2, emb, name, col)
            self.text(name, Z(12), hexrgb(col), (cx + emb + Z(6), cy + (rh - Z(14)) // 2), bold=True)
            self.text(fmt(v), Z(11), C_DIM, (cx + r.w // 2 - Z(28), cy + (rh - Z(12)) // 2), right=True)


    def draw_ranks(self):
        W, H = self.W, self.H
        s = self.ui_scale()
        def S(v):
            return int(round(v * s))
        self.screen.fill(C_DARKER)
        self.text("RANK CHART", S(26), C_TEXT, (W // 2, S(34)), center=True, bold=True)
        r = pygame.Rect(W // 2 - S(420), S(70), S(840), H - S(150))
        pygame.draw.rect(self.screen, C_PANEL, r, border_radius=4)
        pygame.draw.rect(self.screen, C_BORDER, r, 1, border_radius=4)
        # หน้า RANKS เต็ม → วาดแถวใหญ่ขึ้น (ฐาน 1.5 เท่าของแผงเล็กในเมนู) คูณ ui_scale
        self.draw_rank_panel(r, sc=s * 1.5)
        if self.mode not in ("reaction",):
            self.text("(หัก -50 คะแนนทุกการพลาด)", S(12), C_DIM, (W // 2, r.bottom + S(14)), center=True)
        self.button((W // 2 - S(70), H - S(56), S(140), S(38)), "กลับ (ESC)", lambda: setattr(self, "state", "menu"), size=S(13))
