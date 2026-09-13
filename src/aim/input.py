# -*- coding: utf-8 -*-
"""[Module 1] รับ input เมาส์/คีย์ + grab_mouse + raw mouse mode — InputMixin (Module 1 เป็นเจ้าของไฟล์นี้)

raw mouse input (SDL relative mode) ใช้บายพาส "Enhance pointer precision"/สเกลความไวของ
Windows เพื่อให้ความไวเป็น 1:1 จริง — 0.07°/count ตรง Valorant ตามที่แอปโฆษณาไว้
เชื่อมต่อผ่าน contract เท่านั้น (ไม่แตะ game.py):
  - camera.apply_mouse(dx, dy, sens) หมุนมุมกล้อง ; sens อ่านจาก game.S["sens"]
  - grab_mouse(True) ถูกเรียกจาก round.py ตอนเริ่มเล่น/เล่นต่อ, grab_mouse(False) ตอนจบ/พัก
  - แผงตั้งค่าเสริม "Raw input" เสียบผ่าน registry.SETTINGS_PANELS
"""

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

# raw delta ต้องไม่โดนสเกล/accel ของ OS — บังคับปิด "system scale" ของ SDL relative mode
# (ค่า default ของ SDL ปิดอยู่แล้ว แต่ตั้งให้ชัดเผื่อบางเวอร์ชัน/แพลตฟอร์มเปิดมาให้)
# ต้องตั้งก่อน pygame.init(); input.py ถูก import จาก game.py ก่อนสร้าง Game() จึงทันเสมอ
os.environ.setdefault("SDL_MOUSE_RELATIVE_SYSTEM_SCALE", "0")

_RAW_WARNED = False   # เตือน "pygame เก่าไม่รองรับ raw input" แค่ครั้งเดียวต่อโปรเซส


class InputMixin:
    def grab_mouse(self, on):
        """จับ/ปล่อยเมาส์เข้าหน้าต่างเกม + เปิด/ปิด raw mode (chokepoint เดียวของการจับเมาส์)
        on=True  : ซ่อน cursor, ขัง cursor ในจอ, เปิด raw delta (ถ้า S['raw_input'])
        on=False : คืน cursor ปกติ (เรียกตอนจบรอบ/พัก/กลับเมนู)"""
        if self.headless:
            return
        pygame.event.set_grab(on)
        pygame.mouse.set_visible(not on)
        # ── Module 1: raw/relative mouse mode (SDL) เพื่อบายพาส mouse accel ของ OS ──
        self._apply_raw_mouse(on)
        # ล้าง delta ที่ค้าง กันมุมกล้องกระโดดในเฟรมแรกหลัง grab (พฤติกรรมเดิมคงไว้)
        pygame.mouse.get_rel()

    def _apply_raw_mouse(self, on):
        """เปิด/ปิด SDL relative(raw) mouse mode ตามสถานะ grab และค่า S['raw_input'] (default เปิด)

        relative mode: SDL อ่าน raw delta จากเมาส์ตรง ๆ ไม่ผ่าน pointer speed/accel ของ Windows
        และขัง cursor ไว้กลางจอ → cursor ไม่หลุดขอบตอน flick แรง ๆ
        pygame-ce >= 2.5 มี set_relative_mode ; เวอร์ชันเก่ากว่า → fallback เป็นพฤติกรรมเดิม
        (grab + e.rel ที่ยังโดน accel) แล้วเตือนผู้ใช้ครั้งเดียว"""
        global _RAW_WARNED
        want = bool(on) and bool(self.S.get("raw_input", True))
        if hasattr(pygame.mouse, "set_relative_mode"):
            try:
                pygame.mouse.set_relative_mode(want)
            except Exception:
                pass
        elif want and not _RAW_WARNED:
            _RAW_WARNED = True
            print("[VAL//AIM] เวอร์ชัน pygame นี้ยังไม่รองรับ raw input — "
                  "อัปเดตเป็น pygame-ce >= 2.5 เพื่อบายพาส mouse accel "
                  "(ตอนนี้ sens จะยังโดน Enhance pointer precision ของ Windows)")

    def handle_key(self, e):
        k = e.key
        if k == pygame.K_F11:
            self.toggle_fullscreen()
            return True

        # ── ตะเข็บ FLOWS: ระหว่างอยู่ในโหมดพิเศษ ESC = ออกจาก flow กลับเมนู ──
        # (คีย์อื่นปล่อยให้ handler ปกติทำงานต่อ เช่น WASD / ยิง ระหว่าง benchmark)
        if getattr(self, "flow", None) is not None and k == pygame.K_ESCAPE:
            if hasattr(self.flow, "on_exit"):
                try:
                    self.flow.on_exit()
                except Exception:
                    pass
            self.flow = None
            self.grab_mouse(False)
            self.state = "menu"
            return True

        # text input
        if self.text_focus == "dpi":
            if k in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.commit_dpi()
            elif k == pygame.K_BACKSPACE:
                self.dpi_text = self.dpi_text[:-1]
            elif e.unicode.isdigit() and len(self.dpi_text) < 5:
                self.dpi_text += e.unicode
            return True
        if self.text_focus == "sens":
            if k in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.commit_sens()
            elif k == pygame.K_BACKSPACE:
                self.sens_text = self.sens_text[:-1]
            elif e.unicode and (e.unicode.isdigit() or e.unicode == ".") and len(self.sens_text) < 6:
                self.sens_text += e.unicode
            return True
        if self.text_focus == "name":
            if k in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.text_focus = None
                save_data(self.data)
            elif k == pygame.K_BACKSPACE:
                self.data["name"] = self.data.get("name", "")[:-1]
            elif e.unicode and e.unicode.isprintable() and len(self.data.get("name", "")) < 14:
                self.data["name"] = self.data.get("name", "") + e.unicode.upper()
            return True

        st = self.state
        if st == "menu":
            if k == pygame.K_RETURN:
                self.start_countdown()
            elif k == pygame.K_ESCAPE:
                return False
            elif pygame.K_1 <= k <= pygame.K_9:
                idx = k - pygame.K_1            # 1->0 .. 9->8
                if idx < len(MODES):
                    self.mode = MODES[idx][0]
            elif k == pygame.K_0:
                if len(MODES) >= 10:             # '0' = โหมดที่ 10
                    self.mode = MODES[9][0]
            elif k == pygame.K_v and self.mode == "spray":
                self.spray_weapon = "phantom" if self.spray_weapon == "vandal" else "vandal"
                self.spray_mag = SPRAY_WEAPONS[self.spray_weapon]["mag"]
            elif k == pygame.K_v and self.mode == "gun":
                from .guns import WEAPON_ORDER
                self.gun_weapon = WEAPON_ORDER[(WEAPON_ORDER.index(self.gun_weapon) + 1) % len(WEAPON_ORDER)]
            elif k == pygame.K_b and self.mode == "gun":
                from .gunplay import GUN_DRILLS
                ids = [d[0] for d in GUN_DRILLS]
                self.gun_drill = ids[(ids.index(self.gun_drill) + 1) % len(ids)]
        elif st in ("settings", "ranks", "insight"):
            if k == pygame.K_ESCAPE:
                if st == "settings":
                    self.close_settings()
                else:
                    self.state = "menu"
        elif st == "play":
            if k == pygame.K_ESCAPE:
                self.state = "pause"
                self.grab_mouse(False)
            elif k == pygame.K_r:
                now = pygame.time.get_ticks()
                if now - self.last_r < 500:
                    self.start_countdown()
                else:
                    self.last_r = now
                    self.r_hint_until = now + 500
                    if self.mode == "gun":
                        self.gun_reload()      # R เดียว = รีโหลด (RR = เริ่มใหม่ เหมือนเดิม)
            elif k in (pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_c) and self.mode == "gun":
                self.gun_crouch = True
            else:
                name = pygame.key.name(k)
                if name in ("w", "a", "s", "d") and self.mode in ("strafe", "dodge", "gun"):
                    self.keys_down.add(name)
                    if self.mode == "strafe":
                        self.strafe_moved = True
        elif st == "pause":
            if k == pygame.K_ESCAPE:
                self.state = "menu"
            elif k == pygame.K_r:
                self.start_countdown()
        elif st == "countdown":
            if k == pygame.K_ESCAPE:
                self.state = "menu"
                self.grab_mouse(False)
        elif st == "results":
            if k == pygame.K_r:
                self.start_countdown()
            elif k in (pygame.K_m, pygame.K_ESCAPE):
                self.go_menu()
        return True

    def handle_event(self, e):
        """กระจาย event ดิบ (Module 1 เป็นเจ้าของส่วน input) — คืน False เมื่อควรปิดโปรแกรม"""
        if e.type == pygame.VIDEORESIZE:
            self.handle_resize(e)          # อยู่ใน DisplayMixin (display.py)
        elif e.type == pygame.KEYDOWN:
            return self.handle_key(e)
        elif e.type == pygame.KEYUP:
            self.handle_key_up(e)
        elif e.type == pygame.MOUSEMOTION:
            self.handle_mouse_motion(e)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.handle_mouse_down(e)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.handle_mouse_up(e)
        elif e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and e.button == 3:
            if self.mode == "gun":
                self.gun_rmb(e.type == pygame.MOUSEBUTTONDOWN)   # ADS / สโคป
        return True

    def handle_mouse_motion(self, e):
        # raw mode: e.rel เป็น raw delta จาก SDL อยู่แล้ว → ส่งเข้า apply_mouse ตรง ๆ
        # ห้ามคูณสเกลซ้ำ (apply_mouse คูณ VAL_DEG_PER_COUNT*sens ให้แล้ว = 0.07°/count)
        if self.state in ("play", "countdown"):
            sens = self.S["sens"]
            if self.mode == "gun":
                sens *= self.gun_sens_mult()     # ซูมแล้ว sens สเกลตาม focal length เหมือนเกม
            self.cam.apply_mouse(e.rel[0], e.rel[1], sens)
        elif self.drag:
            self.drag_slider(self.scale_mouse(e.pos)[0])

    def handle_mouse_down(self, e):
        self.lmb_down = True
        if self.state == "play":
            if self.mode == "spray" and getattr(self, "resume_cd", 0) <= 0:
                # spray = กดค้าง auto-fire (เริ่มกด)
                self.spray_firing = True
                self.spray_next_shot = self.gt
            else:
                if self.mode == "gun":
                    self.gun_firing = True        # ไรเฟิลกดค้างยิงต่อเนื่องใน update_gun
                self.shoot()
        else:
            if self.text_focus and self.state == "settings":
                self.commit_dpi()
                self.commit_sens()
            mp = self.scale_mouse(e.pos)
            for r, fn in self.last_zones if hasattr(self, "last_zones") else []:
                if r.collidepoint(mp):
                    fn()
                    break
            if self.drag:
                self.drag_slider(mp[0])

    def handle_mouse_up(self, e):
        self.lmb_down = False
        self.lmb_up_at = self.gt
        if self.state == "play" and self.mode == "spray":
            self.spray_firing = False   # ปล่อยเมาส์ = หยุดยิง + เริ่มฟื้นรีคอยล์
        self.gun_firing = False
        if self.state == "play" and self.mode == "reaction" and self.next_spawn_at is not None:
            # นับช่องไฟจากตอน "ปล่อยปุ่ม" ไม่ใช่ตอนกด — เป้าถัดไปไม่โผล่ก่อนนิ้วกลับที่
            self.next_spawn_at = max(self.next_spawn_at, self.gt + REACTION_RELEASE_GAP)
        if self.drag:
            self.drag = None
            save_data(self.data)

    def handle_key_up(self, e):
        u = (e.unicode or "").lower()
        name = pygame.key.name(e.key)
        if name in ("w", "a", "s", "d"):
            self.keys_down.discard(name)
        if e.key in (pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_c):
            self.gun_crouch = False


# ───────────────────────── settings panel (ผ่าน registry) ─────────────────────────
def _raw_input_panel(game, x, y, w):
    """แผง 'RAW INPUT' ในหน้า settings — toggle S['raw_input'] (default เปิด)
    signature ตาม contract: fn(game, x, y, w) -> height(px) ; x,y,w สเกลมาแล้ว
    (เชื่อมผ่าน registry เท่านั้น — ไม่แตะ game.py)"""
    s = game.ui_scale()

    def S(v):
        return int(round(v * s))

    # ให้ checkbox โชว์สถานะตรงกับ default ที่ grab_mouse ใช้ (เปิด) แม้ S ยังไม่มีคีย์นี้
    game.S.setdefault("raw_input", True)
    y0 = y
    game.text("RAW INPUT", S(13), C_RED, (x, y), bold=True)
    y += S(22)
    game.checkbox(x, y, "Raw input — บายพาส mouse accel (แนะนำเปิด)", "raw_input", game.S)
    y += S(22)
    game.text("ปิด accel/สเกลของ Windows → 0.07°/count ตรง Valorant", S(10), C_DIM, (x, y))
    y += S(16)
    return y - y0


# ลงทะเบียนแผงตอน import (input.py ถูก import ครั้งเดียวจาก game.py) — กันลงซ้ำ
if _raw_input_panel not in registry.SETTINGS_PANELS:
    registry.SETTINGS_PANELS.append(_raw_input_panel)

