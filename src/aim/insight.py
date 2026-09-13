# -*- coding: utf-8 -*-
"""Insight วิเคราะห์ฟอร์ม + tips + countdown/pause — InsightMixin (ย้าย verbatim)"""

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
from . import data as _data   # อ้าง DATA_FILE แบบ dynamic — ตอนเทสถูก redirect ไป temp


class InsightMixin:
    def open_insight(self):
        self.insight_tab = self.mode if self.mode != "reaction" else f"reaction-{self.reaction_variant}"
        self.state = "insight"

    def insight_sessions(self, tab):
        if tab == "reaction-static":
            return [e for e in self.data["history"] if e.get("mode") == "reaction" and e.get("variant", "static") == "static"]
        if tab == "reaction-flick":
            return [e for e in self.data["history"] if e.get("mode") == "reaction" and e.get("variant") == "flick"]
        # spray: ตัดรอบยุคบั๊ก reload-burst ออกจากกราฟ/ค่าเฉลี่ย — คะแนนคนละสูตร (config.SPRAY_SCORE_REV)
        return [e for e in self.data["history"] if e.get("mode") == tab and spray_current(e)]

    def draw_insight(self):
        W, H = self.W, self.H
        s = self.ui_scale()
        def S(v):
            return int(round(v * s))
        self.screen.fill(C_DARKER)
        self.text("PERFORMANCE INSIGHT", S(24), C_TEXT, (W // 2, S(26)), center=True, bold=True)
        tabs = ["flick", "precision", "tracking", "reaction-static", "reaction-flick", "strafe", "sniper",
                "spray", "dodge", "placement", "switch", "gun"]
        tw = min(S(120), (W - S(40)) // len(tabs))
        x0 = (W - tw * len(tabs)) // 2
        for i, tb in enumerate(tabs):
            def pick(t=tb):
                self.insight_tab = t
            lbl = tb.replace("reaction-", "react-").upper()
            self.button((x0 + i * tw, S(52), tw - S(6), S(30)), lbl, pick, active=(self.insight_tab == tb), size=S(11))
        tab = self.insight_tab
        is_react = tab.startswith("reaction")
        all_sessions = self.insight_sessions(tab)
        cfg_tab = tab in ("flick", "precision", "tracking", "strafe")
        if cfg_tab:
            # วิเคราะห์เฉพาะ session ที่ config เดียวกัน — คะแนนถึงจะเทียบกันได้จริง
            cy0 = S(90)
            self.text("CONFIG", S(11), C_DIM, (W // 2 - S(340), cy0 + S(7)))
            for i, d in enumerate(DURATIONS):
                def setd(v=d):
                    self.duration = v
                self.button((W // 2 - S(270) + i * S(56), cy0, S(50), S(28)), f"{d}s", setd,
                            active=(self.duration == d), size=S(12))
            for i, sk in enumerate(["small", "medium", "large"]):
                def sets(v=sk):
                    self.size_key = v
                self.button((W // 2 - S(90) + i * S(60), cy0, S(54), S(28)), SIZE_TH[sk], sets,
                            active=(self.size_key == sk), size=S(12))
            sessions = [e for e in all_sessions
                        if e.get("duration") == self.duration and e.get("size") == self.size_key]
        else:
            sessions = all_sessions
        if not sessions:
            if all_sessions:
                msg = f"ยังไม่มีข้อมูลของ config นี้ ({self.duration}s · {SIZE_TH[self.size_key]}) — เลือก config อื่นด้านบน"
            else:
                msg = "ยังไม่มีข้อมูล session ของโหมดนี้ — เล่นให้จบรอบ ระบบจะบันทึกอัตโนมัติ"
            self.text(msg, S(14), C_DIM, (W // 2, H // 2), center=True)
            self.button((W // 2 - S(70), H - S(56), S(140), S(38)), "กลับ (ESC)", lambda: setattr(self, "state", "menu"), size=S(13))
            return
        # การ์ดสถิติ
        scores = [e.get("score", 0) for e in sessions]
        accs = [e.get("acc", 0) for e in sessions]
        rts = [e.get("rt", 0) for e in sessions if e.get("rt", 0) > 0]
        if is_react and rts:
            cards = [(f"{min(rts)}ms", "BEST RT"), (f"{round(sum(rts) / len(rts))}ms", "AVG RT"),
                     (f"±{round(self.stdev(rts))}ms", "VARIANCE"), (str(len(sessions)), "SESSIONS")]
        else:
            cards = [(f"{max(scores):,}", "BEST"), (f"{round(sum(scores) / len(scores)):,}", "AVG"),
                     (f"{sum(accs) / len(accs):.0f}%", "AVG ACC" if tab not in ("strafe", "sniper")
                      else "AVG PERFECT" if tab == "strafe" else "AVG HIT RATE"),
                     (str(len(sessions)), "SESSIONS")]
        cw = S(170)
        x0 = (W - (cw + S(10)) * 4) // 2
        cards_y = S(128) if cfg_tab else S(96)
        for i, (v, l) in enumerate(cards):
            card = pygame.Rect(x0 + i * (cw + S(10)), cards_y, cw, S(62))
            pygame.draw.rect(self.screen, C_PANEL, card, border_radius=4)
            pygame.draw.rect(self.screen, C_BORDER, card, 1, border_radius=4)
            self.text(v, S(20), C_TEXT, (card.centerx, card.y + S(18)), center=True, bold=True)
            self.text(l, S(10), C_DIM, (card.centerx, card.y + S(44)), center=True)
        # กราฟ
        gy = cards_y + S(78)
        gh = max(S(140), H - gy - S(170))
        heat = pygame.Rect(W // 2 - S(400), gy, S(250), gh)
        trend = pygame.Rect(W // 2 - S(130), gy, S(530), gh)
        all_shots = []
        for e in sessions:
            all_shots.extend(e.get("shots") or [])
        self.draw_shotmap(heat, all_shots, "AGGREGATED SHOT MAP")
        if is_react and rts:
            self.draw_trend(trend, rts, "REACTION TIME (ms) — ต่ำ = ดี", invert=True)
        else:
            ttl = "SCORE OVER SESSIONS"
            if cfg_tab:
                ttl += f" ({self.duration}s · {SIZE_TH[self.size_key]})"
            self.draw_trend(trend, scores, ttl)
        # tips
        ty = gy + gh + S(10)
        tips = self.build_tips(tab, sessions, all_shots)
        for i, tip in enumerate(tips[:3]):
            self.text("• " + tip, S(13), C_TEXT, (W // 2 - S(400), ty + i * S(22)))
        if not tips:
            self.text("เล่นเพิ่มอีกหน่อย — ระบบจะวิเคราะห์ pattern หลังมีข้อมูล ≥ 3 sessions",
                      S(12), C_DIM, (W // 2 - S(400), ty))
        lbl = "ลบข้อมูลทั้งหมด" if self.reset_confirm < pygame.time.get_ticks() else "คลิกอีกครั้งเพื่อยืนยัน!"
        self.button((W // 2 - S(380), H - S(56), S(190), S(38)), lbl, self.reset_all_data, size=S(12), danger=True)
        self.button((W // 2 + S(200), H - S(56), S(140), S(38)), "กลับ (ESC)", lambda: setattr(self, "state", "menu"), size=S(13))

    @staticmethod
    def stdev(arr):
        if len(arr) < 2:
            return 0.0
        m = sum(arr) / len(arr)
        return math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr))

    def build_tips(self, tab, sessions, shots):
        tips = []
        is_react = tab.startswith("reaction")
        key = "rt" if is_react else "score"
        if len(sessions) >= 4:
            half = len(sessions) // 2
            old = [e.get(key, 0) for e in sessions[:half]]
            new = [e.get(key, 0) for e in sessions[-half:]]
            oa, na = sum(old) / len(old), sum(new) / len(new)
            better = na < oa if is_react else na > oa
            pct = abs((na - oa) / oa * 100) if oa else 0
            if pct >= 5:
                tips.append(f"{'กำลังเก่งขึ้น' if better else 'ฟอร์มตก'} — {half} เกมล่าสุด"
                            f"{'ดีขึ้น' if better else 'แย่ลง'} {pct:.0f}% เทียบช่วงแรก")
        misses = [s for s in shots if not s.get("hit")]
        if len(shots) >= 8 and len(misses) >= 5 and tab not in ("strafe", "sniper"):
            mx = sum(s["x"] for s in misses) / len(misses)
            my = sum(s["y"] for s in misses) / len(misses)
            dirs = []
            # ค่า x,y = ตำแหน่งเป้าเทียบ crosshair ตอนยิงพลาด → กระสุนหลุดไป "ฝั่งตรงข้าม"
            if mx > 8:
                dirs.append("ซ้าย")    # เป้าอยู่ขวาของ crosshair = flick ขวาไม่สุด
            if mx < -8:
                dirs.append("ขวา")
            if my > 8:
                dirs.append("บน")     # เป้าอยู่ใต้ crosshair = ยิงสูงไป
            if my < -8:
                dirs.append("ล่าง")
            if dirs:
                tips.append(f"Aim bias: ยิงหลุดทาง{'-'.join(dirs)}ของเป้าบ่อย — ลาก flick ให้สุดกว่าเดิม หรือทดลองปรับ sens แล้วเทียบกราฟ")
            else:
                tips.append("Aim เซ็นเตอร์ดี — การพลาดกระจายรอบเป้าสม่ำเสมอ ไม่มี bias")
        if is_react:
            rts = [e.get("rt", 0) for e in sessions if e.get("rt", 0) > 0]
            if len(rts) >= 3:
                sd = self.stdev(rts)
                cv = sd / (sum(rts) / len(rts)) * 100 if rts else 0
                if cv > 15:
                    tips.append(f"Reaction time ไม่นิ่ง — แกว่ง ±{sd:.0f}ms ฝึกความสม่ำเสมอ")
                elif cv < 8:
                    tips.append(f"Reaction time สม่ำเสมอมาก (±{sd:.0f}ms) — ระดับเชี่ยวชาญ")
        if tab == "strafe" and len(sessions) >= 3:
            m = sum(e.get("acc", 0) for e in sessions) / len(sessions)
            tips.append(f"Perfect counter-strafe เฉลี่ย {m:.0f}%" +
                        (" — กดทิศตรงข้ามก่อนยิงให้เร็วขึ้น" if m < 50 else ""))
        if tab == "sniper" and len(sessions) >= 3:
            m = sum(e.get("acc", 0) for e in sessions) / len(sessions)
            tips.append(f"Hit rate เฉลี่ย {m:.0f}%" + (" — เน้นกะจังหวะบอลผ่านประตู" if m < 50 else " — แม่นมาก!"))
        if tab == "gun" and len(sessions) >= 3:
            # GUNFIGHT: สรุปแยกปืน — K/D และ TTK (rt) คือตัววัดหลัก ไม่ใช่คะแนน
            by_w = {}
            for e in sessions:
                by_w.setdefault(e.get("variant", "?"), []).append(e)
            for wname, es in sorted(by_w.items(), key=lambda kv: -len(kv[1]))[:4]:
                k = sum(e.get("kills", 0) for e in es); d = sum(e.get("deaths", 0) for e in es)
                ttk = [e.get("rt", 0) for e in es if e.get("rt", 0) > 0]
                hs = [e.get("hs", 0) for e in es]
                tips.append(f"{wname.upper()}: K/D {k}/{d} ({k / max(1, d):.1f}) · TTK เฉลี่ย "
                            f"{(sum(ttk) / len(ttk)) if ttk else 0:.0f}ms · {len(es)} รอบ"
                            + (" — โดนสวนตายบ่อย: ยิงจากที่กำบัง/ย้ายที่หลังยิง" if d > k else ""))
        if not is_react and tab not in ("strafe", "sniper", "gun") and len(sessions) >= 3:
            m = sum(e.get("acc", 0) for e in sessions) / len(sessions)
            if m >= 80:
                tips.append(f"Accuracy เฉลี่ย {m:.0f}% — ระดับโปร ลองลดขนาดเป้าหรือเพิ่มความเร็ว")
            elif m < 50:
                tips.append(f"Accuracy แค่ {m:.0f}% — เน้นแม่นก่อน ค่อยเร็วทีหลัง")
        return tips

    def reset_all_data(self):
        now = pygame.time.get_ticks()
        if self.reset_confirm < now:
            self.reset_confirm = now + 4000
            return
        # สำรองไฟล์ปัจจุบันเป็นชื่อประทับเวลาก่อนล้าง — BACKUP_FILE ปกติมีรุ่นเดียว
        # การเซฟครั้งถัดไป (แม้แค่แก้ settings) จะทับมัน ทำให้ข้อมูลที่เพิ่งลบกู้ไม่ได้ถาวร
        # ไฟล์ pre-wipe อยู่นอกวงจร backup ปกติ ไม่ถูก rotate/เขียนทับ
        import shutil
        import time
        try:
            src = _data.DATA_FILE
            if os.path.exists(src):
                shutil.copy2(src, src.replace(
                    ".json", time.strftime(".pre-wipe-%Y%m%d-%H%M%S.json")))
        except Exception:
            pass
        self.data["history"] = []
        self.data["leaderboard"] = []
        save_data(self.data)
        self.reset_confirm = 0

    def draw_countdown(self):
        self.draw_world()
        # scrim จาก cache (display.scrim) — เดิม alloc+fill surface เต็มจอใหม่ทุกเฟรมตลอด 3.35 วิ
        self.screen.blit(self.scrim((8, 20, 28, 170)), (0, 0))
        # เฟรม GO: begin_play() เพิ่งสลับ state เป็น play "ก่อน" draw_countdown ถูกเรียก (game.py)
        # → draw_world เปิด dirty-track ไปแล้ว แต่ scrim นี้คลุมทั้งจอ — ต้องบังคับอัพโหลดเต็ม
        # ไม่งั้น scrim ถูก bake ค้างใน GL texture แล้วมืดทั้งสนามตลอดรอบ
        self.mark_full()
        n = self.countdown
        label = "GO!" if n <= 0.35 else str(int(math.ceil(n - 0.35)))
        self.text(label, 140, C_RED, (self.W // 2, self.H // 2), center=True, bold=True)

    def draw_pause(self):
        self.draw_world()
        self.screen.blit(self.scrim((8, 20, 28, 200)), (0, 0))
        self.mark_full()   # กันเชิงป้องกัน — state pause ปกติไม่ track อยู่แล้ว (แพทเทิร์นเดียวกับ countdown)
        self.text("PAUSED", 56, C_TEXT, (self.W // 2, self.H // 2 - 70), center=True, bold=True)
        self.button((self.W // 2 - 160, self.H // 2, 150, 44), "เล่นต่อ", self.resume_play, size=15)
        self.button((self.W // 2 + 10, self.H // 2, 150, 44), "จบรอบ", self.end_game, size=15)
        self.text("ESC = กลับเมนู", 13, C_DIM, (self.W // 2, self.H // 2 + 70), center=True)
