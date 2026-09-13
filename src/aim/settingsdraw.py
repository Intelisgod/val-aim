# -*- coding: utf-8 -*-
"""หน้า Settings (crosshair/mouse/display) + ตะเข็บ SETTINGS_PANELS — SettingsDrawMixin (แยกจาก menudraw เพื่อคุมขนาดไฟล์)"""

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
class SettingsDrawMixin:
    def draw_settings(self):
        W, H = self.W, self.H
        s = self.ui_scale()
        def S(v):
            return int(round(v * s))
        self.screen.fill(C_DARKER)
        self.text("SETTINGS", S(26), C_TEXT, (W // 2, S(30)), center=True, bold=True)
        ch = self.S["ch"]
        lx = W // 2 - S(420)
        # ── crosshair ──
        self.text("CROSSHAIR", S(13), C_RED, (lx, S(66)), bold=True)
        prev = pygame.Rect(lx, S(90), S(380), S(110))
        gstep = S(20)
        for gy in range(prev.y, prev.bottom, gstep):
            for gx in range(prev.x, prev.right, gstep):
                c = (30, 48, 72) if ((gx + gy) // gstep) % 2 == 0 else (24, 38, 56)
                pygame.draw.rect(self.screen, c, (gx, gy, gstep, gstep))
        pygame.draw.rect(self.screen, C_BORDER, prev, 1)
        self.preview_crosshair(prev.centerx, prev.centery, ch)
        y = S(212)
        self.text("สี", S(12), C_DIM, (lx, y))
        for i, c in enumerate(CH_COLORS):
            box = pygame.Rect(lx + S(60) + i * S(30), y - S(2), S(22), S(22))
            def setc(cc=c):
                ch["color"] = cc
                save_data(self.data)
            self.zone(box, setc)
            pygame.draw.rect(self.screen, hexrgb(c), box, border_radius=3)
            if ch["color"] == c:
                pygame.draw.rect(self.screen, C_TEXT, box.inflate(S(4), S(4)), 2, border_radius=4)
        y += S(34)
        self.checkbox(lx, y, "ขอบดำ (Outline)", "outline", ch)
        self.checkbox(lx + S(180), y, "จุดกลาง (Dot)", "dot", ch)
        self.checkbox(lx + S(360), y, "เส้น (Lines)", "lines", ch)
        y += S(34)
        for sid, lbl, lo, hi, key in (("dotsz", "Dot Size", 1, 6, "dotSize"),
                                      ("linelen", "Line Length", 2, 20, "lineLen"),
                                      ("lineth", "Line Thickness", 1, 6, "lineThick"),
                                      ("linegap", "Line Gap", 0, 15, "lineGap")):
            self.text(lbl, S(12), C_DIM, (lx, y))
            self.slider(sid, lx + S(130), y + S(2), S(190), lo, hi, 1, ch, key)
            y += S(32)
        # ── mouse ──
        rx = W // 2 + S(40)
        self.text("MOUSE / SENSITIVITY", S(13), C_RED, (rx, S(66)), bold=True)
        self.text("Mouse DPI", S(12), C_DIM, (rx, S(96)))
        dpi_r = pygame.Rect(rx + S(130), S(90), S(110), S(30))
        def focus_dpi():
            self.text_focus = "dpi"
            self.dpi_text = ""
        self.zone(dpi_r, focus_dpi)
        pygame.draw.rect(self.screen, C_PANEL, dpi_r, border_radius=3)
        pygame.draw.rect(self.screen, C_RED if self.text_focus == "dpi" else C_BORDER, dpi_r, 1, border_radius=3)
        shown = self.dpi_text if self.text_focus == "dpi" else str(self.S["dpi"])
        if self.text_focus == "dpi" and (pygame.time.get_ticks() // 400) % 2 == 0:
            shown += "|"
        self.text(shown, S(14), C_GOLD, dpi_r.center, center=True, bold=True)
        self.text("Sensitivity", S(12), C_DIM, (rx, S(136)))
        self.slider("sens", rx + S(100), S(138), S(175), 0.05, 5.0, 0.01, self.S, "sens", "")
        sens_r = pygame.Rect(rx + S(295), S(130), S(85), S(30))
        def focus_sens():
            self.text_focus = "sens"
            self.sens_text = ""
        self.zone(sens_r, focus_sens)
        pygame.draw.rect(self.screen, C_PANEL, sens_r, border_radius=3)
        pygame.draw.rect(self.screen, C_RED if self.text_focus == "sens" else C_BORDER, sens_r, 1, border_radius=3)
        sh = self.sens_text if self.text_focus == "sens" else f"{self.S['sens']:g}"
        if self.text_focus == "sens" and (pygame.time.get_ticks() // 400) % 2 == 0:
            sh += "|"
        self.text(sh, S(13), C_GOLD, sens_r.center, center=True, bold=True)
        self.text("คลิกช่องแล้วพิมพ์ค่าตรงๆ ได้ เช่น 0.37 (ละเอียด 3 ตำแหน่ง)", S(10), C_DIM, (rx + S(100), S(164)))
        # info cards
        dpi, sv = self.S["dpi"], self.S["sens"]
        edpi = round(dpi * sv)
        cm = 13062.8 / (dpi * sv) if dpi * sv > 0 else 0
        for i, (val, lbl) in enumerate([(f"{edpi}", "eDPI"), (f"{cm:.2f}", "cm/360"), (f"{cm / 2.54:.2f}", "inch/360")]):
            card = pygame.Rect(rx + i * S(130), S(176), S(120), S(56))
            pygame.draw.rect(self.screen, C_PANEL, card, border_radius=3)
            pygame.draw.rect(self.screen, C_BORDER, card, 1, border_radius=3)
            self.text(val, S(18), C_RED, (card.centerx, card.y + S(16)), center=True, bold=True)
            self.text(lbl, S(10), C_DIM, (card.centerx, card.y + S(38)), center=True)
        self.text("ใส่ค่า sens เดียวกับใน Valorant ได้เลย (0.07°/count เท่าเกมจริง)", S(11), C_DIM, (rx, S(244)))
        # ── display ──
        self.text("RANGE / DISPLAY", S(13), C_RED, (rx, S(280)), bold=True)
        self.checkbox(rx, S(306), "แสดงเสาในห้อง (Pillars)", "pillars", self.S)
        self.checkbox(rx, S(332), "FPS Counter", "fps", self.S)
        self.checkbox(rx, S(358), "เสียงเอฟเฟกต์ (Sound)", "sound", self.S)
        # headshots ในโหมดคลาสสิก (ปิดไว้กันแรงค์เดิมเพี้ยน) — โหมดใหม่ใช้หัวเสมอ
        self.checkbox(rx, S(384), "หัวช็อตในโหมดคลาสสิก (Headshots)", "headshots", self.S)
        self.button((rx, S(414), S(230), S(34)),
                    "ออกเต็มจอ (F11)" if self.fullscreen else "เต็มจอ (F11)",
                    self.toggle_fullscreen, size=S(13))
        # ── ตะเข็บ SETTINGS_PANELS: แผงเสริมจากโมดูลอื่น (คอลัมน์ขวาใต้ display) ──
        _py = S(456)
        for _panel in registry.SETTINGS_PANELS:
            try:
                _used = _panel(self, rx, _py, S(380))
                _py += int(_used or 0) + S(8)
            except Exception:
                pass
        # ปุ่ม
        self.button((W // 2 - S(170), H - S(70), S(150), S(40)), "RESET ค่าเริ่มต้น", self.reset_settings, size=S(13))
        self.button((W // 2 + S(20), H - S(70), S(150), S(40)), "กลับเมนู (ESC)", lambda: self.close_settings(), size=S(13))

    def preview_crosshair(self, cx, cy, ch):
        col = hexrgb(ch["color"])
        def rect(x, y, w, h):
            if ch["outline"]:
                pygame.draw.rect(self.screen, (0, 0, 0), (x - 1, y - 1, w + 2, h + 2))
            pygame.draw.rect(self.screen, col, (x, y, w, h))
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

    def reset_settings(self):
        self.data["settings"] = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.S = self.data["settings"]
        save_data(self.data)

    def close_settings(self):
        self.commit_dpi()
        self.commit_sens()
        save_data(self.data)
        self.state = "menu"

    def commit_dpi(self):
        if self.text_focus == "dpi":
            try:
                v = int(self.dpi_text)
                if 100 <= v <= 32000:
                    self.S["dpi"] = v
            except ValueError:
                pass
            self.text_focus = None
            save_data(self.data)

    def commit_sens(self):
        if self.text_focus == "sens":
            try:
                v = float(self.sens_text)
                if 0.01 <= v <= 10:
                    self.S["sens"] = round(v, 3)
            except ValueError:
                pass
            self.text_focus = None
            save_data(self.data)
