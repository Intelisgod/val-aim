# -*- coding: utf-8 -*-
"""VAL//AIM — คลาส Game (state machine + run loop + ตะเข็บ FLOWS/register)
คลาสถูกแตกเป็น mixin หลายไฟล์เพื่อคุมขนาดไฟล์ (<700 บรรทัด/<30KB) — เป็น instance เดียว self ร่วมกัน
พฤติกรรมทุกอย่างเหมือนของเดิม 100%"""

import pygame
import math
import random
import json
import os
import sys
import time
import array
from collections import OrderedDict

from .config import *
from .ranks import *
from . import data as _data
from .data import DATA_FILE, load_data, save_data
from .camera import Camera, focal_len, VFOV_RAD
from .target import Target
from . import registry, benchmark, sensitivity, export, plan
from .display import DisplayMixin
from .input import InputMixin
from .audio import AudioMixin
from .round import RoundMixin
from .shooting import ShootMixin
from .update import UpdateMixin
from .worlddraw import WorldDrawMixin
from .menudraw import MenuDrawMixin
from .settingsdraw import SettingsDrawMixin
from .results import ResultsMixin
from .insight import InsightMixin
from .gunplay import GunMixin
from .reactpeek import ReactPeekMixin
from .todaycard import TodayCardMixin


class Game(DisplayMixin, InputMixin, AudioMixin, RoundMixin, ShootMixin, UpdateMixin, WorldDrawMixin, MenuDrawMixin, SettingsDrawMixin, ResultsMixin, InsightMixin, GunMixin, ReactPeekMixin, TodayCardMixin):
    DEFAULT_W, DEFAULT_H = 2560, 1440   # default 2K

    def __init__(self, headless=False):
        self.headless = headless
        # แก้ภาพเบลอบน Windows ที่ตั้ง display scaling >100%:
        # ประกาศ DPI-aware เพื่อให้ 1 พิกเซลเกม = 1 พิกเซลจริง (ไม่โดน OS ขยายภาพ)
        if not headless and sys.platform == "win32":
            try:
                import ctypes
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
                except Exception:
                    ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass
        self.init_display()
        self.clock = pygame.time.Clock()
        self.fullscreen = False
        self.font_cache = {}
        # cache ผลลัพธ์ font.render (LRU) — เดิม render ใหม่ทุกเฟรมทุกข้อความ แพงสุดในหน้าเมนู
        # (ฟอนต์ไทยผ่าน harfbuzz shaping ~0.03-0.25ms/ครั้ง x 15-170 ครั้ง/เฟรมตามหน้าจอ)
        self.text_cache = OrderedDict()
        self._size_cache = {}

        self.data = load_data()
        self.S = self.data["settings"]
        # init_display วิ่งก่อนมี settings → render scale ที่เซฟไว้ต้องใช้ตรงนี้ (มีผลเฉพาะ GPU present-only)
        # (vsync/gpu ที่เซฟไว้ยังไม่มีผลตอนเปิดเกม — บั๊ก load order เดิม รอผู้ใช้ตัดสิน ดู memory fps-upgrade)
        self.apply_render_scale()

        self.mode = "flick"
        self.duration = 30
        self.size_key = "medium"
        self.reaction_variant = "static"
        self.gun_weapon = "vandal"      # GUNFIGHT: ปืน + ดริล (คงไว้ข้ามรอบเหมือน spray_weapon)
        self.gun_drill = "duel"
        self.state = "menu"      # menu/settings/ranks/insight/countdown/play/pause/results
        self.insight_tab = "flick"
        self.reset_confirm = 0

        self.cam = Camera()
        self.targets = []
        self.zones = []          # (rect, fn) สร้างใหม่ทุกเฟรมตอนวาด
        self.drag = None         # (slider_id)
        self.sliders = {}
        self.text_focus = None
        self.dpi_text = ""
        self.sens_text = ""
        self.score_saved = False
        self.last_r = -9.0
        self.r_hint_until = 0.0
        self.floats = []
        self.hitmarks = []
        self.keys_down = set()

        self.init_audio()
        self.reset_round()
        # ── ตะเข็บโมดูลเสริม: flow + auto-register (benchmark/sensitivity/export) ──
        self.flow = None
        for _ext in (benchmark, sensitivity, export, plan):
            try:
                _ext.register(self)
            except Exception:
                pass

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.font_cache:
            self.font_cache[key] = pygame.font.SysFont(
                "leelawadeeui,leelawadee,tahoma,segoeui,arial", size, bold=bold)
        return self.font_cache[key]

    TEXT_CACHE_MAX = 512   # จำกัดจำนวน surface ใน cache (~4-8MB จริง) — ข้อความหมุนเวียน (เลข FPS/คะแนน) ถูก evict เอง

    def text(self, s, size, color, pos, center=False, bold=False, right=False, surf=None):
        # tuple(color) กันคีย์ชนกันระหว่าง list/tuple/pygame.Color; antialias เป็น True เสมอจึงไม่อยู่ในคีย์
        key = (str(s), size, tuple(color), bold)
        img = self.text_cache.get(key)
        if img is None:
            img = self.font(size, bold).render(key[0], True, color)
            self.text_cache[key] = img
            if len(self.text_cache) > self.TEXT_CACHE_MAX:
                self.text_cache.popitem(last=False)
        else:
            self.text_cache.move_to_end(key)
        r = img.get_rect()
        if center:
            r.center = pos
        elif right:
            r.topright = pos
        else:
            r.topleft = pos
        (surf or self.screen).blit(img, r)
        if surf is None:
            self.mark_dirty(r)   # dirty-rect ของ GL present (no-op นอกเฟรม play บน GPU world)
        return r

    def text_width(self, s, size, bold=False):
        """ความกว้างข้อความแบบ memo — ใช้จัด layout (HUD block) โดยไม่ต้อง shape ฟอนต์ซ้ำทุกเฟรม"""
        key = (str(s), size, bold)
        w = self._size_cache.get(key)
        if w is None:
            if len(self._size_cache) > 1024:
                self._size_cache.clear()
            w = self.font(size, bold).size(key[0])[0]
            self._size_cache[key] = w
        return w

    def go_menu(self):
        self.state = "menu"
        self.text_focus = None
        # ออกไปเมนู (หน้าผล / ESC ตอนพักหรือนับถอยหลัง) = เลิกคิว routine/วอร์มที่ค้าง + คืนค่าเมนูเดิมของผู้ใช้ (plan.leave ;
        # ปุ่ม ROUTINE บนการ์ดต่อจากที่ค้างเองจากประวัติวันนี้) — เดิมคิวค้างข้ามเมนู แล้วรอบอิสระถัดมามีปุ่ม NEXT ใหญ่
        # ที่พากลับเข้าวอร์มเก่า และเมนูค้างที่โหมด/ขนาดของรายการสุดท้ายในคิว
        plan.leave(self)

    def save_score(self):
        if self.score_saved or not hasattr(self, "last_entry"):
            return
        e = dict(self.last_entry)
        e.pop("shots", None)
        e["name"] = (self.data.get("name") or "ANON")[:14]
        lb = self.data["leaderboard"]
        lb.append(e)
        if len(lb) > 100:
            del lb[:len(lb) - 100]
        save_data(self.data)
        self.score_saved = True

    def request_exit(self):
        if getattr(self, "_discard_unsaved", False) or save_data(self.data):
            return True
        self._quit_after_save = True
        self.flow = None
        self.state = "menu"
        self.grab_mouse(False)
        return False

    def retry_save(self):
        # Persist the existing history, without running end_game/save_score again.
        if save_data(self.data) and getattr(self, "_quit_after_save", False):
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def discard_unsaved_and_exit(self):
        self._discard_unsaved = True
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    def draw_save_status(self):
        if not _data.LAST_SAVE_ERROR:
            self._quit_after_save = False
            if not _data.LOAD_WARNING:
                return
        if self.state in ("play", "countdown"):
            return
        scale = self.ui_scale()
        if not _data.LAST_SAVE_ERROR:
            # โหลดมาจาก backup/ไฟล์หลักอ่านไม่ได้ — แถบบางบอกไว้ หายเองเมื่อเซฟสำเร็จครั้งถัดไป
            h = int(26 * scale)
            pygame.draw.rect(self.screen, C_PANEL, (0, 0, self.W, h))
            self.text(_data.LOAD_WARNING, int(12 * scale), C_RED, (int(12 * scale), int(6 * scale)))
            self.zones = [z for z in self.zones if z[0].top >= h]
            return
        h = int(70 * scale)
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, self.W, h))
        self.text("บันทึกไม่สำเร็จ — ผลยังอยู่ในหน่วยความจำ กรุณาลองบันทึกซ้ำ (" + _data.LAST_SAVE_ERROR[:90] + ")",
                  int(13 * scale), C_RED, (int(12 * scale), int(8 * scale)))
        # Remove covered hit targets; the retry banner owns this strip.
        self.zones = [z for z in self.zones if z[0].top >= h]
        self.button((int(12 * scale), int(32 * scale), int(165 * scale), int(30 * scale)),
                    "ลองบันทึกซ้ำ", self.retry_save, size=int(12 * scale))
        if getattr(self, "_quit_after_save", False):
            self.button((int(190 * scale), int(32 * scale), int(230 * scale), int(30 * scale)),
                        "ปิดโดยทิ้งข้อมูลที่ยังไม่บันทึก", self.discard_unsaved_and_exit,
                        size=int(12 * scale), danger=True)

    def run(self, max_frames=None):
        running = True
        frame = 0
        self._perf_present_ms = None
        while running:
            dt = min(self.clock.tick(240) / 1000.0, 0.1)
            self.zones = []
            # หมายเหตุ: ห้ามเคลียร์ self.sliders ตรงนี้ — event มาก่อนการวาดเฟรมนี้
            # ถ้าเคลียร์ การลาก slider จะหาข้อมูล slider ของเฟรมก่อนไม่เจอ
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = not self.request_exit()
                elif self.handle_event(e) is False:
                    # handle_event อยู่ใน InputMixin (input.py) — คืน False เมื่อควรปิดโปรแกรม
                    running = not self.request_exit()

            if not running:
                break
            if self.flow is not None:
                # ── ตะเข็บ FLOWS: โหมดพิเศษ (เช่น benchmark) คุม update/draw แทน state ปกติ ──
                self.flow.update(dt)
                if self.flow is not None:
                    self.flow.draw()
            elif self.state == "countdown":
                prev = self.countdown
                self.countdown -= dt
                n_prev = int(math.ceil(max(0, prev - 0.35)))
                n_now = int(math.ceil(max(0, self.countdown - 0.35)))
                if n_now != n_prev:
                    self.play(self.snd_beep_hi if n_now == 0 else self.snd_beep)
                elif prev == 3.35 and self.cd_last_beep == 99:
                    self.cd_last_beep = 3
                    self.play(self.snd_beep)
                if self.countdown <= 0:
                    self.begin_play()
                self.draw_countdown()
            elif self.state == "play":
                if self.resume_cd > 0:
                    # นับถอยหลังหลังกดเล่นต่อ — หยุดเกม แต่เมาส์ยังหมุนมุมกล้องได้
                    self.resume_cd -= dt
                    self.draw_world()
                    self.draw_crosshair()
                    self.draw_effects()
                    self.draw_hud()
                    if self.resume_cd > 0:
                        # scrim ทึบแสงเต็มจอจาก cache (display.py) — เดิม alloc 14MB ใหม่ทุกเฟรม
                        self.screen.blit(self.scrim((8, 20, 28, 90)), (0, 0))
                        self.text(str(int(math.ceil(self.resume_cd))), 120, C_RED,
                                  (self.W // 2, self.H // 2), center=True, bold=True)
                else:
                    self.update_play(dt)
                    if self.state == "play":
                        self.draw_world()
                        self.draw_crosshair()
                        self.draw_effects()
                        self.draw_hud()
                    else:
                        self.draw_results()
            elif self.state == "pause":
                self.draw_pause()
            elif self.state == "results":
                self.draw_results()
            elif self.state == "settings":
                self.draw_settings()
            elif self.state == "ranks":
                self.draw_ranks()
            elif self.state == "insight":
                self.draw_insight()
            else:
                self.draw_menu()

            self.draw_save_status()
            self.last_zones = list(self.zones)
            _tp = time.perf_counter()
            self.present()   # [GPU phase 1] display.py: GL composite+swap ถ้าเปิด GPU, ไม่งั้น pygame.display.flip()
            # perf HUD (S['fps']): เวลาที่ใช้ใน present (upload overlay + composite + swap/vsync) เฉลี่ยแบบ EMA
            _pm = (time.perf_counter() - _tp) * 1000.0
            self._perf_present_ms = _pm if self._perf_present_ms is None else self._perf_present_ms * 0.9 + _pm * 0.1
            frame += 1
            if max_frames and frame >= max_frames:
                running = False
        if max_frames and not getattr(self, "_discard_unsaved", False):
            save_data(self.data)
        pygame.quit()
