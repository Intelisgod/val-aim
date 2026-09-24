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
from . import plan as _plan

class MenuDrawMixin:
    def zone(self, rect, fn):
        self.zones.append((pygame.Rect(rect), fn))
        return pygame.Rect(rect)

    def button(self, rect, label, fn, active=False, size=14, danger=False, disabled=False):
        if disabled:
            # ตัวเลือกที่ใช้ไม่ได้ในบริบทนี้ (เช่น OP HOLD ตอนถือ Ghost) — โชว์ให้รู้ว่ามี แต่ไม่รับคลิก
            r = pygame.Rect(rect)
            pygame.draw.rect(self.screen, C_DARKER, r, border_radius=min(r.h // 2, 18))
            pygame.draw.rect(self.screen, C_BORDER, r, 1, border_radius=min(r.h // 2, 18))
            self.text(label, size, (70, 82, 96), r.center, center=True, bold=True)
            return r
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

    def cached_panel(self, slot, key, rect, draw, ref=None):
        """แผงที่เนื้อหาเปลี่ยนไม่บ่อย (การ์ด "วันนี้" / ตารางแรงค์ในเมนู): วาดจริงครั้งเดียว แล้ว blit พิกเซลที่จับไว้ทุกเฟรม
        เดิมวาดใหม่หมดทุกเฟรม ~1.1 ms ต่อแผง (text blit ~50 ครั้ง) — เมนู p50 3.3 → 5.9 ms หลังเพิ่มการ์ด "วันนี้"
        วาดจริงเมื่อ: key (ผู้เรียกใส่ทุกอย่างที่เปลี่ยนเนื้อหา) / กรอบ / ขนาด+รูปแบบ surface / hover ของ zone ในแผง เปลี่ยน
        - draw() วาดลง self.screen ที่พิกัดจอเดิม แต่ถูก clip ไว้ในกรอบ rect → พิกเซลนอกกรอบไม่ถูกวาดทั้งเฟรมวาดจริง
          และเฟรม blit (ทุกเฟรมเหมือนกัน) ; พื้นใต้กรอบต้องทึบและเหมือนกันทุกเฟรม (fill ของเมนู / พื้นแผงที่ผู้เรียกวาดก่อน)
        - zone ที่ draw() ลงทะเบียนถูกเก็บไว้เติมคืนทุกเฟรมตามลำดับเดิม ; hover = zone ไหนมีเมาส์ (ผู้วาดเช็ค hover
          ด้วยกรอบเดียวกับ zone) เปลี่ยนเมื่อไร = วาดใหม่ — จึงไม่ต้องใส่ตำแหน่งเมาส์ในคีย์
        - ref: ของที่ key อ้างด้วย id() — ถือไว้ในแคชกัน id ถูกใช้ซ้ำหลังของเดิมถูกเก็บกวาด
        - เทส/selftest ที่ดัก self.text ต้องเรียก invalidate_panels() ก่อน (เฟรม blit ไม่เรียก text เลย)"""
        scr = self.screen
        area = pygame.Rect(rect).clip(scr.get_rect())
        if area.w <= 0 or area.h <= 0:
            draw()
            return
        cache = getattr(self, "_panel_cache", None)
        if cache is None:
            cache = self._panel_cache = {}
        fmt = (scr.get_size(), scr.get_bitsize(), scr.get_masks())
        mouse = pygame.mouse.get_pos()
        ent = cache.get(slot)
        if ent is not None and ent["key"] == key and ent["area"] == area and ent["fmt"] == fmt \
                and tuple(z.collidepoint(mouse) for z, _f in ent["zones"]) == ent["hov"]:
            scr.blit(ent["img"], area)
            self.zones.extend(ent["zones"])
            self.mark_dirty(area)      # no-op ในเมนู (state นี้อัพโหลดเต็มเสมอ) — คง invariant dirty-rect ไว้เผื่อที่อื่นเรียก
            return
        z0 = len(self.zones)
        prev = scr.get_clip()
        scr.set_clip(area.clip(prev))
        try:
            draw()
        finally:
            scr.set_clip(prev)
        zones = self.zones[z0:]
        img = scr.subsurface(area).copy()
        img.set_alpha(None)            # พื้นใต้แผงทึบ → blit เป็น copy ตรงไม่ blend (เร็วกว่า ~30%) พิกเซลเท่าเดิมเป๊ะ
        cache[slot] = {"key": key, "area": area, "fmt": fmt, "img": img, "zones": zones, "ref": ref,
                       "hov": tuple(z.collidepoint(mouse) for z, _f in zones)}

    def invalidate_panels(self):
        """ทิ้งแคชแผงทั้งหมด → เฟรมถัดไปวาดจริง (เทสที่นับข้อความที่วาด / หลังเปลี่ยนของที่ไม่อยู่ในคีย์)"""
        self._panel_cache = {}

    def section_header(self, label, x, y, w, color=C_RED, upper=True, size=12):
        """หัวข้อ section แบบ Aim Lab: label uppercase ตัวเล็ก + เส้นใต้บางสีแดง
        upper=False เมื่อ label มีหน่วยตัวเล็ก (เช่น "30s") ที่ผู้เรียกจัดตัวพิมพ์มาแล้ว ; size = ฟอนต์ (เมนูส่ง S(12))"""
        self.text(label.upper() if upper else label, size, color, (x, y), bold=True)
        ly = y + size * 3 // 2
        pygame.draw.line(self.screen, color, (x, ly), (x + w, ly), 1)

    def fit_text(self, s, size, maxw, bold=False):
        """ตัดข้อความให้กว้างไม่เกิน maxw px (ต่อท้าย "…") — memo ต่อ (ข้อความ, ขนาด, ความกว้าง) เพราะถูกเรียกทุกเฟรม"""
        s = str(s)
        cache = getattr(self, "_fit_cache", None)
        if cache is None or len(cache) > 512:
            cache = self._fit_cache = {}
        key = (s, size, maxw, bold)
        hit = cache.get(key)
        if hit is not None:
            return hit
        out = s
        if maxw <= 0:
            out = ""
        elif self.text_width(s, size, bold) > maxw:
            lo, hi = 0, len(s)
            while lo < hi:                   # ยาวสุดที่ (ตัด + "…") ยังพอดี
                mid = (lo + hi + 1) // 2
                if self.text_width(s[:mid].rstrip() + "…", size, bold) <= maxw:
                    lo = mid
                else:
                    hi = mid - 1
            out = (s[:lo].rstrip() + "…") if lo else ""
        cache[key] = out
        return out

    def wrap_text(self, s, size, maxw):
        """ตัดบรรทัดตามช่องว่าง (memo ต่อ ข้อความ/ขนาด/ความกว้าง) — คำเดียวยาวเกินบรรทัดถูกตัด "…" """
        cache = getattr(self, "_wrap_cache", None)
        if cache is None or len(cache) > 256:
            cache = self._wrap_cache = {}     # กันโตไม่จำกัดจากการลาก resize ผ่านหลายความกว้าง
        key = (s, size, maxw)
        lines = cache.get(key)
        if lines is None:
            lines, line = [], ""
            for w_ in str(s).split(" "):
                t2 = (line + " " + w_).strip()
                if line and self.text_width(t2, size) > maxw:
                    lines.append(line)
                    line = w_
                else:
                    line = t2
            lines.append(line)
            lines = [self.fit_text(ln, size, maxw) for ln in lines]
            cache[key] = lines
        return lines

    def mode_icon(self, mid, cx, cy, col, s=1.0):
        """วาดไอคอน vector ของแต่ละโหมดด้วย pygame primitives (ขนาด ~22px × s — เมนูส่ง ui_scale มา)"""
        scr = self.screen

        def Z(v):
            return int(round(v * s))

        def w(v):
            return max(1, Z(v))
        if mid == "flick":
            pygame.draw.circle(scr, col, (cx, cy), Z(11), w(2))
            pygame.draw.circle(scr, col, (cx, cy), Z(5), w(2))
            pygame.draw.circle(scr, col, (cx, cy), w(1))
        elif mid == "precision":
            pygame.draw.circle(scr, col, (cx, cy), Z(5), w(2))
            pygame.draw.line(scr, col, (cx - Z(11), cy), (cx - Z(6), cy), w(2))
            pygame.draw.line(scr, col, (cx + Z(6), cy), (cx + Z(11), cy), w(2))
            pygame.draw.line(scr, col, (cx, cy - Z(11)), (cx, cy - Z(6)), w(2))
            pygame.draw.line(scr, col, (cx, cy + Z(6)), (cx, cy + Z(11)), w(2))
        elif mid == "tracking":
            pygame.draw.circle(scr, col, (cx, cy), Z(6), w(2))
            pygame.draw.line(scr, col, (cx - Z(12), cy), (cx - Z(7), cy), w(2))
            pygame.draw.polygon(scr, col, [(cx - Z(12), cy), (cx - Z(8), cy - Z(3)), (cx - Z(8), cy + Z(3))])
            pygame.draw.line(scr, col, (cx + Z(7), cy), (cx + Z(12), cy), w(2))
            pygame.draw.polygon(scr, col, [(cx + Z(12), cy), (cx + Z(8), cy - Z(3)), (cx + Z(8), cy + Z(3))])
        elif mid == "reaction":
            pygame.draw.circle(scr, col, (cx, cy), Z(11), w(2))
            pygame.draw.line(scr, col, (cx, cy - Z(6)), (cx, cy + Z(2)), w(3))
            pygame.draw.circle(scr, col, (cx, cy + Z(6)), w(2))
        elif mid == "strafe":
            for dx, dy, lbl in [(0, -1, "W"), (-1, 0, "A"), (0, 1, "S"), (1, 0, "D")]:
                px, py = cx + dx * Z(12), cy + dy * Z(12)
                self.text(lbl, Z(10), col, (px, py), center=True, bold=True)
        elif mid == "gun":
            # ปืน: ลำกล้อง + ด้าม + วงสโคป
            pygame.draw.line(scr, col, (cx - Z(12), cy - Z(2)), (cx + Z(10), cy - Z(2)), w(3))
            pygame.draw.line(scr, col, (cx - Z(4), cy - Z(1)), (cx - Z(7), cy + Z(9)), w(3))
            pygame.draw.circle(scr, col, (cx + Z(2), cy - Z(7)), Z(4), w(1))
            pygame.draw.line(scr, col, (cx + Z(2), cy - Z(10)), (cx + Z(2), cy - Z(4)), w(1))
        elif mid == "sniper":
            pygame.draw.circle(scr, col, (cx, cy), Z(11), w(2))
            pygame.draw.circle(scr, col, (cx, cy), Z(6), w(1))
            pygame.draw.line(scr, col, (cx - Z(11), cy), (cx + Z(11), cy), w(1))
            pygame.draw.line(scr, col, (cx, cy - Z(11)), (cx, cy + Z(11)), w(1))
            pygame.draw.circle(scr, col, (cx, cy), w(1))
        elif mid == "spray":
            # ลายรีคอยล์: เส้นซิกแซกพุ่งขึ้น
            pts = [(cx, cy + Z(11)), (cx - Z(1), cy + Z(4)), (cx + Z(3), cy - Z(1)),
                   (cx - Z(3), cy - Z(6)), (cx + Z(2), cy - Z(11))]
            pygame.draw.lines(scr, col, False, pts, w(2))
            pygame.draw.circle(scr, col, (cx + Z(2), cy - Z(11)), w(2))
        elif mid == "dodge":
            # คนกับลูกศรหลบ
            pygame.draw.circle(scr, col, (cx - Z(3), cy - Z(6)), Z(3), w(2))
            pygame.draw.line(scr, col, (cx - Z(3), cy - Z(3)), (cx - Z(3), cy + Z(5)), w(2))
            pygame.draw.line(scr, col, (cx - Z(3), cy + Z(5)), (cx - Z(7), cy + Z(11)), w(2))
            pygame.draw.line(scr, col, (cx - Z(3), cy + Z(5)), (cx + Z(1), cy + Z(11)), w(2))
            pygame.draw.line(scr, col, (cx + Z(4), cy - Z(2)), (cx + Z(11), cy - Z(2)), w(2))
            pygame.draw.polygon(scr, col, [(cx + Z(11), cy - Z(2)), (cx + Z(7), cy - Z(5)), (cx + Z(7), cy + Z(1))])
        elif mid == "placement":
            # crosshair ระดับหัว + เส้นแนวระดับ
            pygame.draw.line(scr, col, (cx - Z(11), cy - Z(5)), (cx + Z(11), cy - Z(5)), w(1))
            pygame.draw.circle(scr, col, (cx, cy - Z(5)), Z(4), w(2))
            pygame.draw.line(scr, col, (cx, cy - Z(1)), (cx, cy + Z(11)), w(2))
        elif mid == "switch":
            # สามวงเรียง + ลูกศรสลับ
            for ddx in (-9, 0, 9):
                pygame.draw.circle(scr, col, (cx + Z(ddx), cy - Z(2)), Z(3), w(2))
            pygame.draw.line(scr, col, (cx - Z(9), cy + Z(8)), (cx + Z(9), cy + Z(8)), w(1))
            pygame.draw.polygon(scr, col, [(cx + Z(9), cy + Z(8)), (cx + Z(5), cy + Z(5)), (cx + Z(5), cy + Z(11))])
            pygame.draw.polygon(scr, col, [(cx - Z(9), cy + Z(8)), (cx - Z(5), cy + Z(5)), (cx - Z(5), cy + Z(11))])

    # เลย์เอาต์เมนู (หน่วย = px ที่ ui_scale 1.0 บนจอ 1280×720 ; คูณ S() ทุกค่า — 2560×1440 ได้ ×2 ทั้งหน้า
    # แบบเดียวกับหน้า Insight/Ranks ; เดิมเมนูตัวหนังสือ 10–15 px ตายตัวเป็นเกาะเล็กกลางจอ 2K):
    #   หัว (ชื่อ + แถวปุ่มรอง INSIGHT/SETTINGS/BENCHMARK/SENS CONVERT…) → การ์ด "วันนี้" (routine — ปุ่มหลัก)
    #   → กริดโหมด 5×2 (เล่นอิสระ) → แถวตัวเลือก + START → แผงล่าง profile | TOP 5 | ตารางแรงค์
    MENU_TOP_H, CARD_H, GRID_CARD_H, GRID_GAP = 44, 190, 56, 8
    MENU_CONTENT_W, MENU_DESIGN_H = 1040, 716

    def draw_menu(self):
        W, H = self.W, self.H
        s = self.ui_scale()

        def S(v):
            return int(round(v * s))
        self.screen.fill(C_DARKER)
        _plan.refresh(self)     # การ์ด "วันนี้" ตาม train_plan.json ล่าสุด (throttle ในตัว — อ่านไฟล์เฉพาะตอนเปลี่ยน)
        cw = min(W - S(40), S(self.MENU_CONTENT_W))
        xl = (W - cw) // 2
        # จอสูงกว่าสัดส่วน 16:9 → ดันทั้งบล็อกลงกลาง ; จอเตี้ย (900×560) → ชิดบน แผงล่างหายเอง (ph < 120)
        top = max(S(10), (H - S(self.MENU_DESIGN_H)) // 2)

        # ── หัว: ชื่อซ้าย · แถวปุ่มรองขวา (ตะเข็บ MENU_EXTRAS + INSIGHT/SETTINGS) — เดิมปุ่มเสริมเรียงใต้ START
        #    5 ปุ่ม × 176 px = 928 px ล้นหน้าต่าง 900 ; ตอนนี้ปุ่มกว้างตามป้าย ย่อฟอนต์/ตัดป้ายเมื่อที่ไม่พอ ──
        tr = self.text("VAL//AIM", S(28), C_TEXT, (xl, top), bold=True)
        tools = [(it["label"], (lambda f=it["on_click"]: f(self)), it.get("disabled")) for it in registry.MENU_EXTRAS]
        tools += [("INSIGHT", lambda: self.open_insight(), False),
                  ("SETTINGS", lambda: setattr(self, "state", "settings"), False)]
        room = xl + cw - (tr.right + S(16))
        fs, gap_t = S(11), S(8)
        while True:
            ws = [self.text_width(lbl, fs, True) + S(26) for lbl, _f, _d in tools]
            if sum(ws) + gap_t * (len(ws) - 1) <= room or fs <= max(8, S(8)):
                break
            fs -= 1
        bx = xl + cw - (sum(ws) + gap_t * (len(ws) - 1))
        for (lbl, fn, dis), bw in zip(tools, ws):
            self.button((max(bx, tr.right + S(8)), top + S(4), bw, S(28)), self.fit_text(lbl, fs, bw - S(8), True), fn,
                        size=fs, disabled=bool(dis))
            bx += bw + gap_t
        self.text("3D FPS RANGE TRAINER", S(10), C_DIM, (tr.right + S(10), top + S(17)))

        # ── การ์ด "วันนี้" (todaycard.py) ──
        card = pygame.Rect(xl, top + S(self.MENU_TOP_H), cw, S(self.CARD_H))
        self.draw_today_card(card, s)

        # ── กริดโหมด 5 × 2 (เล่นอิสระ) เลขกำกับ 1-9,0 — ไอคอนซ้าย ชื่อ + คำอธิบายขวา ──
        cols, rows = 5, 2
        gap = S(self.GRID_GAP)
        cwi = (cw - (cols - 1) * gap) // cols
        chh = S(self.GRID_CARD_H)
        y0 = card.bottom + S(10)
        num_keys = "1234567890"
        for i, (mid, name, desc) in enumerate(MODES):
            cxi, ryi = i % cols, i // cols
            r = pygame.Rect(xl + cxi * (cwi + gap), y0 + ryi * (chh + gap), cwi, chh)

            def pick(m=mid):
                self.mode = m
            self.zone(r, pick)
            sel = (mid == self.mode)
            hov = r.collidepoint(pygame.mouse.get_pos())
            br = S(5)
            pygame.draw.rect(self.screen, (4, 12, 18), r.move(S(2), S(3)), border_radius=br)
            pygame.draw.rect(self.screen, (31, 46, 61) if (sel or hov) else C_PANEL, r, border_radius=br)
            pygame.draw.rect(self.screen, C_RED if sel else C_BORDER, r, max(1, S(2)), border_radius=br)
            if sel:
                pygame.draw.rect(self.screen, C_RED, (r.x + S(2), r.y + 1, r.w - S(4), S(3)), border_radius=S(2))
            self.text(num_keys[i], S(10), C_RED if sel else C_DIM, (r.x + S(6), r.y + S(4)), bold=True)
            ic = C_RED if sel else C_DIM if not hov else C_TEXT
            self.mode_icon(mid, r.x + S(27), r.y + chh // 2 + S(3), ic, s)
            tx = r.x + S(50)
            self.text(self.fit_text(name, S(14), r.right - tx - S(4), True), S(14), C_RED if sel else C_TEXT,
                      (tx, r.y + S(6)), bold=True)
            # ตัดบรรทัดคำอธิบาย: memo ต่อ (desc, ความกว้าง, ขนาดฟอนต์) — desc คงที่จากตาราง MODES
            # เดิม font.size ต่อคำ ~60-100 ครั้ง/เฟรม (shaping ไทยแพง) ทั้งที่ผลเท่าเดิมทุกเฟรม
            for j, ln in enumerate(self.wrap_text(desc, S(10), r.right - tx - S(6))[:2]):
                self.text(ln, S(10), C_DIM, (tx, r.y + S(26) + j * S(13)))

        # ── แถวตัวเลือก (ใต้กริด) — ตำแหน่งอิงกลางจอ ±430 (สเกลตาม S) ──
        y1 = y0 + rows * chh + (rows - 1) * gap + S(12)
        x = W // 2 - S(430)
        if self.mode not in ("reaction", "sniper"):
            self.text("เวลา", S(12), C_DIM, (x, y1 + S(7)))
            for i, d in enumerate(DURATIONS):
                def setd(v=d):
                    self.duration = v
                self.button((x + S(50) + i * S(58), y1, S(52), S(30)), f"{d}s", setd, active=(self.duration == d),
                            size=S(13))
            x += S(240)
            # ขนาดเป้า — spray/gunfight ใช้บอทขนาดคงที่จึงไม่โชว์
            if self.mode not in ("spray", "gun"):
                self.text("ขนาดเป้า", S(12), C_DIM, (x, y1 + S(7)))
                for i, sz in enumerate(["small", "medium", "large"]):
                    def sets(v=sz):
                        self.size_key = v
                    self.button((x + S(70) + i * S(62), y1, S(56), S(30)), SIZE_TH[sz], sets,
                                active=(self.size_key == sz), size=S(13))
                x += S(270)
        if self.mode == "reaction":
            self.text("Reaction Type", S(12), C_DIM, (x, y1 + S(7)))
            for i, v in enumerate(REACTION_VARIANTS):        # static / flick / peek (หัวโผล่จากขอบกล่อง)
                def setv(vv=v):
                    self.reaction_variant = vv
                self.button((x + S(110) + i * S(74), y1, S(68), S(30)), v.upper(), setv,
                            active=(self.reaction_variant == v), size=S(12))
            x += S(280)
        if self.mode == "spray":
            self.text("อาวุธ (V สลับ)", S(12), C_DIM, (x, y1 + S(7)))
            for i, v in enumerate(["vandal", "phantom"]):
                def setw(vv=v):
                    self.spray_weapon = vv
                    self.spray_mag = SPRAY_WEAPONS[vv]["mag"]
                self.button((x + S(110) + i * S(84), y1, S(78), S(30)), v.upper(), setw,
                            active=(self.spray_weapon == v), size=S(12))
            x += S(290)
        if self.mode == "gun":
            # GUNFIGHT ไม่ใช้ขนาดเป้า (บอทหุ่นคนขนาดจริง) — แถวนี้แทนที่ตัวเลือกขนาด
            from .guns import WEAPON_ORDER, WEAPONS as _WP
            from .gunplay import GUN_DRILLS, drills_for
            self.gun_fix_drill()            # คู่ปืน/ดริลที่มาจาก deep-link/แผน/Insight ต้องตรงกับที่ START จะเล่นจริง
            short = {"operator": "OP", "vandal": "VANDAL", "phantom": "PHANTOM", "sheriff": "SHERIFF",
                     "ghost": "GHOST", "classic": "CLASSIC"}

            def setg(vv):
                self.gun_weapon = vv
                self.gun_fix_drill()        # Ghost/Classic ไม่มี OP HOLD → กลับ DUEL
            # ปืนหลักแถวบน (ต่อจากปุ่มเวลา) · ปืนสั้นแถวสองขวาปุ่ม START
            gx = W // 2 - S(430 - 240)
            self.text("ปืน (V)", S(12), C_DIM, (gx, y1 + S(7)))
            prim = [v for v in WEAPON_ORDER if _WP[v]["kind"] != "pistol"]
            side = [v for v in WEAPON_ORDER if _WP[v]["kind"] == "pistol"]
            for i, v in enumerate(prim):
                self.button((gx + S(50) + i * S(70), y1, S(66), S(30)), short.get(v, v.upper()), lambda vv=v: setg(vv),
                            active=(self.gun_weapon == v), size=S(10))
            yd = y1 + S(40)
            sx = W // 2 + S(166)              # ปุ่มสุดท้ายจบที่ W/2+430 = สมมาตรกับขอบซ้ายของแถว (W/2−430)
            self.text("ปืนสั้น", S(12), C_DIM, (sx, yd + S(7)))
            for i, v in enumerate(side):
                self.button((sx + S(52) + i * S(72), yd, S(68), S(30)), short.get(v, v.upper()), lambda vv=v: setg(vv),
                            active=(self.gun_weapon == v), size=S(10))
            # แถวดริล: ฝั่งซ้ายของปุ่ม START (ไม่ทับ) 2 บรรทัด × 4 — บรรทัดล่าง = ดริลชุดสมจริง (ANGLE/PEEK/TAP/ADAD) สูง 28
            # จบที่ y1+101 เหนือบรรทัดคำใบ้ปุ่ม (y1+102..118) ; ดริลที่ปืนนี้เล่นไม่ได้ = ปุ่มจาง กดไม่ได้
            from .gunplay import GUN_DRILL_SHORT
            gx2 = W // 2 - S(430)
            self.text("ดริล (B)", S(12), C_DIM, (gx2, yd + S(7)))
            ok_d = drills_for(self.gun_weapon)
            for i, (did, dname, _d) in enumerate(GUN_DRILLS):
                def setdr(vv=did):
                    self.gun_drill = vv
                row, col = divmod(i, 4)
                self.button((gx2 + S(56) + col * S(56), yd + row * S(33), S(52), S(30 - 2 * row)), GUN_DRILL_SHORT[did],
                            setdr, active=(self.gun_drill == did), size=S(9), disabled=(did not in ok_d))
        if self.mode not in ("strafe", "sniper", "spray", "dodge", "gun"):
            self.button((W // 2 + S(334), y1, S(96), S(30)), "RANKS", lambda: setattr(self, "state", "ranks"),
                        size=S(12))

        # ปุ่มเริ่มเล่นอิสระ (โหมด/ค่าที่เลือกด้านบน) — ปุ่มรอง: ขอบแดงบนพื้นแผง ; ปุ่มหลักคือ ROUTINE ในการ์ด "วันนี้"
        sr = pygame.Rect(W // 2 - S(150), y1 + S(46), S(300), S(46))
        self.zone(sr, self.start_countdown)
        hov = sr.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, (38, 56, 74) if hov else C_PANEL, sr, border_radius=S(4))
        pygame.draw.rect(self.screen, C_RED, sr, max(1, S(2)), border_radius=S(4))
        self.text("START TRAINING  (ENTER)", S(15), C_TEXT, sr.center, center=True, bold=True)
        keys_hint = ("เมาส์ เล็ง · คลิกซ้าย ยิง · R รีโหลด · ค้าง R เริ่มใหม่ · ESC พัก · F11 เต็มจอ"
                     if self.mode == "gun" else "เมาส์ เล็ง · คลิกซ้าย ยิง · RR เริ่มใหม่ · ESC พัก · F11 เต็มจอ")
        self.text(keys_hint, S(11), C_DIM, (W // 2, y1 + S(110)), center=True)

        # แผงล่าง 3 คอลัมน์: profile | leaderboard | rank chart — กว้างเท่าคอลัมน์เนื้อหา
        py = y1 + S(124)
        ph = min(S(300), H - py - S(14))
        if ph > S(120):
            pgap = S(14)
            pw = (cw - 2 * pgap) // 3
            for ci, drawer in enumerate((self.draw_profile_panel, self.draw_lb_panel, self.draw_rank_panel_menu)):
                pr = pygame.Rect(xl + ci * (pw + pgap), py, pw, ph)
                pygame.draw.rect(self.screen, (4, 12, 18), pr.move(S(2), S(3)), border_radius=S(5))
                pygame.draw.rect(self.screen, C_PANEL, pr, border_radius=S(5))
                pygame.draw.rect(self.screen, C_BORDER, pr, 1, border_radius=S(5))
                drawer(pr, s)

    def draw_rank_panel_menu(self, r, s):
        """ตารางแรงค์/กติกาปืนในเมนู = draw_rank_panel ผ่าน cached_panel — เนื้อหาขึ้นกับตัวเลือกโหมดในคีย์นี้เท่านั้น
        (ตารางขีดคงที่ + ตาราง WEAPONS/กติกาดริล ; ไม่อ่านประวัติ) — เพิ่มตัวแปรใหม่ใน draw_rank_panel ต้องเติมคีย์ด้วย"""
        key = (self.mode, self.duration, self.size_key, self.reaction_variant, self.spray_weapon,
               self.gun_weapon, self.gun_drill, s)
        self.cached_panel("rank", key, r, lambda: self.draw_rank_panel(r, s))

    def draw_profile_panel(self, r, s=1.0):
        """s = ui_scale ของเมนู (ผู้เรียกตรงอื่น/เทสต์ = 1.0 ขนาดเดิม)"""
        def S(v):
            return int(round(v * s))
        self.section_header("PROFILE", r.x + S(14), r.y + S(12), r.w - S(28), size=S(12))
        name = (self.data.get("name") or "PLAYER").upper()
        self.text(name[:16], S(20), C_TEXT, (r.centerx, r.y + S(46)), center=True, bold=True)
        # ดึงสถิติของโหมด+config ที่เลือก (กติกาเดียวกับ PB — round.same_config)
        hist = self.config_history()
        if self.mode == "reaction":
            rts = [e.get("rt", 0) for e in hist if e.get("rt", 0) > 0]
            best = min(rts) if rts else None
            rankinfo = get_rt_rank(best, self.reaction_variant) if best else None
            best_lbl = f"{round(best)}ms" if best else "—"
        elif self.mode in ("strafe", "sniper"):
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = None
            best_lbl = f"{best:,}" if best is not None else "—"
        elif self.mode == "gun":
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = None
            if self.gun_is_ladder():
                # DUEL/ANGLE/PEEK: แรงค์ดวล = ค่ากลาง tier_i 5 รอบล่าสุดของปืน+ดริลนี้ (ทุกความยาวรอบ — บันไดเดินต่อข้ามรอบ)
                from . import duel
                rt = duel.recent_tier(self.data["history"], self.gun_weapon, mode_current, drill=self.gun_drill)
                if rt is not None:
                    rankinfo = RANKS[rt[0]]
            best_lbl = f"{best:,}" if best is not None else "—"
        elif self.mode == "spray":
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = (get_rank(best, self.duration, self.size_key, "spray", self.spray_weapon)
                        if best is not None else None)
            best_lbl = f"{best:,}" if best is not None else "—"
        else:
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else None
            rankinfo = get_rank(best, self.duration, self.size_key, self.mode) if best is not None else None
            best_lbl = f"{best:,}" if best is not None else "—"
        sessions = len(hist)
        accs = [e.get("acc", 0) for e in hist if e.get("acc") is not None]
        avg_acc = round(sum(accs) / len(accs)) if accs else 0
        if sessions == 0:
            legacy = sum(1 for e in self.data["history"] if e.get("mode") == self.mode and not mode_current(e))
            if legacy:
                # มีรอบแต่เป็นกติกาเก่า (config.MODE_REV) — บอกเหตุ ไม่ใช่ "ยังไม่มีสถิติ" เฉยๆ
                self.text(f"{legacy} รอบเก่าใช้กติกาเดิม (ไม่นับเทียบ)", S(13), C_DIM, (r.centerx, r.centery - S(10)),
                          center=True)
                self.text("เล่นรอบใหม่เพื่อเริ่มสถิติชุดใหม่", S(13), C_DIM, (r.centerx, r.centery + S(12)), center=True)
            else:
                self.text("ยังไม่มีสถิติ — เริ่มเล่นเลย", S(13), C_DIM, (r.centerx, r.centery), center=True)
            return
        # สถิติย่อย 3 ช่องชิดล่าง ; โล่แรงค์กลางช่องว่างระหว่างชื่อกับสถิติ (เดิมตำแหน่งตายตัว — แผงเตี้ย 196 px
        # ชื่อแรงค์ทับตัวเลขสถิติ)
        sy = r.bottom - S(48)
        if rankinfo:
            _, rname, rcol = rankinfo
            rcol_rgb = hexrgb(rcol) if isinstance(rcol, str) else rcol
            top_y, bot_y = r.y + S(62), sy - S(8)
            emb = min(S(56), bot_y - top_y - S(24))
            if emb >= S(20):
                cy = top_y + emb // 2 + max(0, (bot_y - top_y - emb - S(22)) // 2)
                self.draw_rank_emblem(r.centerx, cy, emb, rname, rcol_rgb)
                self.text(rname, S(15), rcol_rgb, (r.centerx, cy + emb // 2 + S(11)), center=True, bold=True)
            else:
                self.text(rname, S(15), rcol_rgb, (r.centerx, (top_y + bot_y) // 2), center=True, bold=True)
        else:
            self.text("โหมดฝึกซ้อม", S(14), C_DIM, (r.centerx, (r.y + S(62) + sy) // 2), center=True)
        stats = [(best_lbl, "BEST"), (str(sessions), "SESSIONS"), (f"{avg_acc}%", "AVG ACC")]
        sw = (r.w - S(28)) // 3
        for i, (v, l) in enumerate(stats):
            scx = r.x + S(14) + sw * i + sw // 2
            self.text(v, S(18), C_RED, (scx, sy), center=True, bold=True)
            self.text(l, S(10), C_DIM, (scx, sy + S(22)), center=True)

    def draw_lb_panel(self, r, s=1.0):
        def S(v):
            return int(round(v * s))
        # กรอง config เดียวกับ PB (round.same_config) — เดิมกรองแค่โหมด/variant/ปืน+ดริล จึงเอาคะแนน 15s มาจัด
        # อันดับปนกับ 30s (TIME_FACTOR 0.53 = ต่างกันราว 2 เท่า) และ spray/ขนาดเป้าต่างกันปนกัน
        cfg = self.config_label()         # ตัวพิมพ์จัดมาแล้ว ("30s" ห้าม upper เป็น "30S")
        label = MODE_NAME[self.mode].upper() + (f" · {cfg}" if cfg else "")
        if self.text_width(f"TOP 5 — {label}", S(12), True) > r.w - S(28):
            label = cfg or label          # ป้ายยาว (gun) — config สำคัญกว่าชื่อโหมดที่เห็นบนการ์ดอยู่แล้ว
        self.section_header(f"TOP 5 — {label}", r.x + S(14), r.y + S(12), r.w - S(28), color=C_GOLD, upper=False,
                            size=S(12))
        rows = [e for e in self.data["leaderboard"] if self.same_config(e)]
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
            self.text(self.fit_text("ยังไม่มีสถิติในโหมดนี้ — เล่นแล้วกด SAVE SCORE", S(12), r.w - S(20)), S(12), C_DIM,
                      (r.centerx, r.centery), center=True)
            return
        y = r.y + S(44)
        for i, e in enumerate(rows):
            self.text(f"{i + 1}", S(12), C_DIM, (r.x + S(16), y), bold=True)
            self.text((e.get("name") or "ANON")[:14], S(13), C_TEXT, (r.x + S(36), y - 1), bold=True)
            if self.mode == "reaction":
                self.text(f"{e.get('rt', 0)}ms · {e.get('acc', 0)}%", S(12), C_RED, (r.right - S(14), y), right=True,
                          bold=True)
            else:
                self.text(f"{e.get('score', 0):,} · {e.get('acc', 0)}%", S(12), C_RED, (r.right - S(14), y), right=True,
                          bold=True)
            y += S(24)
            if y > r.bottom - S(18):
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
        hs = int(round(12 * min(sc, 2.0)))    # หัวแผง: เมนู 2K = 24 px ; หน้า RANKS (sc = 1.5 × ui_scale) ไม่เกินนี้
        if self.mode in ("strafe", "sniper"):
            self.text("โหมดนี้ไม่มีระบบแรงค์ (โหมดฝึกซ้อม)", Z(12), C_DIM, (r.centerx, r.centery), center=True)
            if self.mode == "strafe":
                # ไรเฟิลจริง (Vandal): ความเร็วเกิน 27.5% ของวิ่ง = กระสุนกระจาย — ต้องหยุดก่อนยิงเหมือนในเกม
                self.text("WASD วิ่ง · SHIFT เดิน · CTRL หมอบ", Z(11), C_DIM, (r.centerx, r.centery + Z(22)), center=True)
                self.text("วิ่งยิง +6° · เดิน +3° · หมอบเดิน +0.8° — หยุดให้นิ่งก่อนคลิก", Z(11), C_DIM,
                          (r.centerx, r.centery + Z(40)), center=True)
            return
        if self.mode == "gun":
            self.section_header("GUNFIGHT — กติกาปืนตามเกมจริง", r.x + Z(14), r.y + Z(12), r.w - Z(28), size=hs)
            from .guns import WEAPONS as _WP, dmg_label as _dl, shots_to_kill as _stk
            w = _WP[self.gun_weapon]
            bands = " / ".join(f"{_dl(b[1])}·{_dl(b[2])}·{_dl(b[3])} ≤{b[0]}m" for b in w["dmg"])
            alt = w.get("alt")
            if w["zooms"]:
                rmb = ("สโคป " + "/".join(f"{z:g}x" for z in w["zooms"])
                       + (" — ยิงแล้วหลุดสโคป" if w.get("unscope_on_shot") else ""))
            elif alt:
                rmb = (f"RMB ยิงชุด {alt['pellets']} เม็ด {alt['rps']:g} ชุด/วิ · สเปรด"
                       f" {alt['spread']['stand']:g}–{alt['spread']['max']:g}° (ประชิด)")
            else:
                rmb = "ไม่มี ADS"
            # นัดที่ต้องใช้ฆ่าบอท (เกราะหนัก) ในช่วงระยะแรกของปืนที่เลือก — คำนวณจากตารางจริง ไม่ใช่ข้อความตายตัว
            d0 = w["dmg"][0][0] - 1
            kill = f"หัว {_stk(self.gun_weapon, 'head', d0)} · ตัว {_stk(self.gun_weapon, 'body', d0)}" \
                   f" · ขา {_stk(self.gun_weapon, 'leg', d0)} นัด (≤{w['dmg'][0][0]}m)"
            lines = [f"{w['name']}: หัว·ตัว·ขา {bands}",
                     f"ยิง {w['rps']:g} นัด/วิ · แม็ก {w['mag']} · รีโหลด {w['reload']}s",
                     f"สเปรดยืน {w['spread']['stand']}° หมอบเดิน +{w['spread']['crouch_move']}° เดิน +{w['spread']['walk']}°"
                     f" วิ่ง +{w['spread']['run']}°",
                     rmb,
                     f"บอท HP 100 + เกราะ 50 (รับ 66%): {kill}",
                     "คุม: RMB สโคป/ADS/ยิงชุด · WASD · SHIFT เดิน · CTRL ย่อ · R รีโหลด",
                     "บอทโผล่จากมุม ยิงตามแนวสายตา · peek ได้เปรียบ 70ms · HP เต็มทุกดวล",
                     (f"{self.gun_drill.upper()} มีแรงค์: ชนะ = บอทตัวต่อไปเก่งขึ้น 1 ขั้น · แพ้ = ลง 1 ขั้น"
                      if self.gun_is_ladder()
                      else "ดริลนี้ไม่จัดแรงค์ (แรงค์ดวลมีใน DUEL/ANGLE/PEEK ปืนที่ไม่ใช่ Op)")]
            from .gunplay import GUN_DRILL_RULE
            rule = GUN_DRILL_RULE.get(self.gun_drill)
            if rule:
                # กติกาของดริลคือคำอธิบายหลักของดริลใหม่ — ขึ้นบรรทัดที่ 2 (ใต้ชื่อปืน) และตัดบรรทัดทั่วไป "บอทโผล่จากมุม…"
                # ที่ดริลนี้อธิบายเองแล้ว (เดิมต่อท้ายเป็นบรรทัดที่ 10 ตกขอบแผง/ขอบจอ 16:9 ครึ่งบรรทัด)
                lines = [lines[0], rule] + [ln for ln in lines[1:] if not ln.startswith("บอทโผล่จากมุม")]
            y0 = r.y + Z(40)
            pitch = min(Z(20), max(Z(13), (r.bottom - Z(6) - y0) // max(1, len(lines))))   # ทุกบรรทัดอยู่ในแผง
            for i, ln in enumerate(lines):
                fs = min(Z(11), max(Z(8), pitch - Z(4)))
                while fs > Z(8) and self.text_width(ln, fs) > r.w - Z(28):
                    fs -= 1                   # บรรทัดยาว (ชื่อปืน/ดริล) ห้ามล้นแผง
                self.text(ln, fs, C_TEXT if i == 0 else (C_GOLD if ln == rule else C_DIM),
                          (r.x + Z(14), y0 + i * pitch))
            return
        if self.mode == "reaction":
            self.section_header(f"RANK CHART — REACTION {self.reaction_variant.upper()}",
                                r.x + Z(14), r.y + Z(12), r.w - Z(28), size=hs)
            data = [(rt_thresh(t, self.reaction_variant), n, c) for t, n, c in REACTION_RT_RANKS]
            data = list(reversed(data))
            # แถวปลายเปิด (Iron I) = "ช้ากว่าขีดของแถวถัดไป" ของ variant ที่เลือก — เดิมตายตัว "> 350ms" (ขีด STATIC)
            # PEEK จึงอ่านได้ว่า 400 ms = Iron I แต่ 361 ms = Radiant
            worst = max((v for v, _n, _c in data if v != float("inf")), default=350)
            fmt = lambda v: (f"> {worst:.0f}ms" if v == float("inf") else f"≤ {v:.0f}ms")
            if self.reaction_variant == "peek":
                from .reactpeek import RPEEK_RULE
                self.text(self.fit_text(RPEEK_RULE, Z(11), r.w - Z(28)), Z(11), C_GOLD,
                          (r.centerx, r.bottom - Z(16)), center=True)
        else:
            # spray: บอทขนาดคงที่ แต่บันไดแยกปืน → หัวตารางบอกปืนแทนขนาดเป้า
            what = self.spray_weapon.upper() if self.mode == "spray" else SIZE_TH[self.size_key]
            self.section_header(f"RANK CHART — {MODE_NAME[self.mode]} {self.duration}s {what}",
                                r.x + Z(14), r.y + Z(12), r.w - Z(28), upper=False, size=hs)
            data = scaled_ranks(self.duration, self.size_key, self.mode, self.spray_weapon)
            fmt = lambda v: f"{v:,}+"
        n = len(data)
        rows_per_col = (n + 1) // 2
        foot = Z(22) if self.mode == "reaction" and self.reaction_variant == "peek" else 0   # บรรทัดกติกา PEEK ท้ายแผง
        rh = min(Z(22), (r.h - Z(50) - foot) // rows_per_col)
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
