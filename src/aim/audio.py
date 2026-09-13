# -*- coding: utf-8 -*-
"""เสียงสังเคราะห์ (_tone) + ชุดเสียง (init_audio) + play — array ล้วน ไม่ใช้ numpy"""

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


class AudioMixin:
    def _tone(self, f0, f1, ms, vol):
        try:
            rate = 22050
            n = int(rate * ms / 1000)
            buf = array.array("h")
            ph = 0.0
            for i in range(n):
                fr = f0 + (f1 - f0) * i / n
                ph += 2 * math.pi * fr / rate
                env = 1.0 - i / n
                buf.append(int(32000 * vol * env * math.sin(ph)))
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except Exception:
            return None

    def play(self, snd):
        if snd and self.S.get("sound", True):
            try:
                snd.play()
            except Exception:
                pass

    def init_audio(self):
        """สร้างชุดเสียงสังเคราะห์ (ย้ายจาก __init__ เดิม) — array ล้วน ไม่ใช้ numpy"""
        self.snd_hit = self._tone(880, 440, 120, 0.5)
        self.snd_miss = self._tone(220, 200, 80, 0.35)
        self.snd_beep = self._tone(800, 800, 150, 0.45)
        self.snd_beep_hi = self._tone(1200, 1200, 150, 0.45)
        self.snd_step = self._tone(95, 85, 70, 0.18)
        self.snd_head = self._tone(1500, 700, 140, 0.55)   # headshot: แหลม-ชัด
        self.snd_spray = self._tone(520, 480, 45, 0.30)    # เสียงยิงรัวเบาๆ ต่อนัด
        self.snd_hazard = self._tone(160, 110, 220, 0.5)   # โดนสกิล dodge
        self.snd_warn = self._tone(440, 600, 90, 0.3)      # telegraph เตือน
