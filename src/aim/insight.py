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

# ── Aim bias (tip ใน Insight) ──
# เดิมเฉลี่ยตำแหน่งเฉพาะ "นัดพลาด" แล้วเกิน 8 px = bias — ในโหมดหัวนัดที่ต่ำกว่าหัวไปโดนลำตัว = นับ "โดน"
# นัดพลาดจึงเหลือแต่ด้านบน/ข้างหัว (censoring) คนที่เล็งหัวตรงแต่มือสั่นรอบหัวเท่าๆ กันก็โดนบอก "ยิงหลุดทางบน"
# (sim เล็ง isotropic รอบศูนย์หัว: 5 ใน 8 เคสขึ้น tip ปลอม ค่ากลางนัดพลาด y +8.5..+10.9 px แต่ทุกนัด −1.9..+2.5)
# และไม่มีเกณฑ์ความไม่แน่นอน (null จาก spread จริงของผู้ใช้: ขึ้น tip 22-65% ที่ 5 นัดพลาด)
# ตอนนี้: ใช้ "ทุกนัด" (โดนก็บันทึกตำแหน่งเทียบจุดเล็งเหมือนกัน) + ช่วงความเชื่อมั่นต่อแกน — วัด 2026-09-24 ด้วยช็อตจริง
# ของผู้ใช้ (ลบค่ากลางต่อรอบ = ไม่มี bias จริง, 1000 ครั้ง/ช่อง): tip ปลอม ≤ 3.3% ทุกโหมดทุกขนาด 8–180 นัด
# (กฎเดิมบน null ชุดเดียวกัน 2–43% ที่ 20 นัด, 0.4–88% ที่ 60 นัด) ; bias จริง +12 px จับได้ 97–100% ที่ 60 นัด
BIAS_MIN_N = 8       # นัดขั้นต่ำก่อนพูดเรื่อง bias
BIAS_PX = 8          # |ค่ากลาง| ต้องเกินนี้ถึงนับว่ามีผล (≈ รัศมีหัวขนาดกลางที่ 11 ม.) — "เซ็นเตอร์ดี" = ทั้งช่วงอยู่ใน ±นี้
BIAS_Z = 2.24        # สองแกนพร้อมกัน: Bonferroni ของ 95% (z 0.9875) → โอกาสขึ้น tip ปลอมรวม ≤ 5%


def _t_crit(df):
    """ค่าวิกฤต t ที่ความน่าจะเป็นเดียวกับ BIAS_Z (Cornish-Fisher สองพจน์ — คลาด < 1% ที่ df ≥ 5)
    n น้อยต้องใช้ t ไม่ใช่ z: null จาก spread จริงของผู้ใช้ที่ 8 นัด z ล้วนขึ้น tip ปลอม 5.6-7.5% (flick/reaction/tracking)"""
    z = BIAS_Z
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df * df)


def _head_tab(tab):
    """แท็บที่ช็อตวัดเทียบ "หัว" (ref=head): โหมดเล็งหัว (config.HEAD_MODES) + reaction·peek (หัวหุ่นโผล่จากขอบ)"""
    return tab in HEAD_MODES or tab == "reaction-peek"


def aim_bias(groups):
    """ค่ากลาง + ครึ่งความกว้างช่วง 95% (สองแกนพร้อมกัน) ของตำแหน่งจุดเล็งเทียบเป้า
    groups = [[shot, ...] ต่อรอบ] — SE = ค่าที่ใหญ่กว่าระหว่างแบบนัดอิสระกับ cluster-robust ต่อรอบ (CR1)
    เพราะนัดในรอบเดียวกันไม่อิสระกัน (sens/ท่าทางวันนั้น) ; คืน None ถ้านัดไม่พอ
    → {"n", "rounds", "x": (ค่ากลาง, ครึ่งช่วง, ครึ่งช่วงแบบนัดอิสระ), "y": (...)}"""
    groups = [g for g in groups if g]
    shots = [s for g in groups for s in g]
    n = len(shots)
    if n < BIAS_MIN_N:
        return None
    out = {"n": n, "rounds": len(groups)}
    t = _t_crit(n - 1)
    G = len(groups)
    for ax in ("x", "y"):
        m = sum(s[ax] for s in shots) / n
        se2 = sum((s[ax] - m) ** 2 for s in shots) / (n - 1) / n
        cr = sum(sum(s[ax] - m for s in g) ** 2 for g in groups) / (n * n) * G / (G - 1) if G >= 2 else 0.0
        out[ax] = (m, t * math.sqrt(max(se2, cr)), t * math.sqrt(se2))
    return out


class InsightMixin:
    def open_insight(self):
        self.insight_tab = self.mode if self.mode != "reaction" else f"reaction-{self.reaction_variant}"
        self.state = "insight"

    def insight_sessions(self, tab):
        if tab == "reaction-static":
            return [e for e in self.data["history"] if e.get("mode") == "reaction" and e.get("variant", "static") == "static"]
        if tab in ("reaction-flick", "reaction-peek"):
            v = tab.split("-", 1)[1]
            return [e for e in self.data["history"] if e.get("mode") == "reaction" and e.get("variant") == v]
        # ตัดรอบกติกาเก่าออกจากกราฟ/ค่าเฉลี่ย — spray ยุคบั๊ก reload-burst, gun hitbox แคปซูล (config.MODE_REV)
        return [e for e in self.data["history"] if e.get("mode") == tab and mode_current(e)]

    def gun_insight_sessions(self):
        return [e for e in self.insight_sessions("gun")
                if (e.get("variant") or "vandal") == self.gun_weapon
                and (e.get("drill") or "duel") == self.gun_drill
                and (e.get("duration") or 30) == self.duration]

    def configured_insight_sessions(self, tab):
        if tab == "gun":
            return self.gun_insight_sessions()
        sessions = self.insight_sessions(tab)
        if tab == "spray":
            # spray: บอทขนาดคงที่ (round.target_radius คืน 0.42 เสมอ เมนูก็ซ่อนปุ่มขนาด) — size ที่บันทึก
            # คือค่าค้างจากโหมดก่อนหน้า ห้ามใช้แยก config ไม่งั้นรอบที่เล่นเหมือนกันหายไปครึ่ง; config = เวลา + ปืน
            return [e for e in sessions
                    if (e.get("duration") or 30) == self.duration
                    and (e.get("variant") or "vandal") == self.spray_weapon]
        if tab in ("flick", "precision", "tracking", "strafe", "dodge", "placement", "switch"):
            sessions = [e for e in sessions
                        if (e.get("duration") or 30) == self.duration
                        and (e.get("size") or "medium") == self.size_key]
        return sessions

    def draw_insight(self):
        W, H = self.W, self.H
        s = self.ui_scale()
        def S(v):
            return int(round(v * s))
        self.screen.fill(C_DARKER)
        self.text("PERFORMANCE INSIGHT", S(24), C_TEXT, (W // 2, S(26)), center=True, bold=True)
        tabs = ["flick", "precision", "tracking", "reaction-static", "reaction-flick", "reaction-peek", "strafe",
                "sniper", "spray", "dodge", "placement", "switch", "gun"]
        tw = min(S(120), (W - S(40)) // len(tabs))
        x0 = (W - tw * len(tabs)) // 2
        for i, tb in enumerate(tabs):
            def pick(t=tb):
                self.insight_tab = t
            lbl = tb.replace("reaction-", "react-").upper()
            fs = S(11)
            while fs > 8 and self.text_width(lbl, fs, True) > tw - S(6) - 4:
                fs -= 1                       # 13 แท็บในจอแคบ (900 px) — ป้ายยาว (REACT-STATIC) ห้ามล้นปุ่ม
            self.button((x0 + i * tw, S(52), tw - S(6), S(30)), lbl, pick, active=(self.insight_tab == tb), size=fs)
        tab = self.insight_tab
        is_react = tab.startswith("reaction")
        all_sessions = self.insight_sessions(tab)
        gun_tab = tab == "gun"
        cfg_tab = tab in ("flick", "precision", "tracking", "strafe", "spray", "dodge", "placement", "switch")
        if cfg_tab:
            # วิเคราะห์เฉพาะ session ที่ config เดียวกัน — คะแนนถึงจะเทียบกันได้จริง
            cy0 = S(90)
            self.text("CONFIG", S(11), C_DIM, (W // 2 - S(340), cy0 + S(7)))
            for i, d in enumerate(DURATIONS):
                def setd(v=d):
                    self.duration = v
                self.button((W // 2 - S(270) + i * S(56), cy0, S(50), S(28)), f"{d}s", setd,
                            active=(self.duration == d), size=S(12))
            if tab == "spray":
                # spray ไม่มีขนาดเป้า — ปุ่มปืนแทนที่ตำแหน่งปุ่มขนาด
                for i, weapon in enumerate(("vandal", "phantom")):
                    self.button((W // 2 - S(90) + i * S(105), cy0, S(100), S(28)),
                                weapon.upper(), lambda w=weapon: setattr(self, "spray_weapon", w),
                                active=(self.spray_weapon == weapon), size=S(11))
            else:
                for i, sk in enumerate(["small", "medium", "large"]):
                    def sets(v=sk):
                        self.size_key = v
                    self.button((W // 2 - S(90) + i * S(60), cy0, S(54), S(28)), SIZE_TH[sk], sets,
                                active=(self.size_key == sk), size=S(12))
            sessions = self.configured_insight_sessions(tab)
        elif gun_tab:
            from .guns import WEAPON_ORDER
            from .gunplay import GUN_DRILLS
            groups = [("gun_weapon", WEAPON_ORDER),
                      ("gun_drill", [d[0] for d in GUN_DRILLS]),
                      ("duration", DURATIONS)]
            for row, (attr, values) in enumerate(groups):
                bw = min(S(112), (W - S(20)) // len(values))     # ดริล 8 ปุ่ม: หดให้พอดีจอแคบ (900 px)
                left = (W - len(values) * bw) // 2
                for i, value in enumerate(values):
                    label = f"{value}s" if attr == "duration" else str(value).upper()
                    self.button((left + i * bw, S(88 + row * 32), bw - S(6), S(28)),
                                label, lambda a=attr, v=value: setattr(self, a, v),
                                active=(getattr(self, attr) == value), size=S(11))
            sessions = self.gun_insight_sessions()
        else:
            sessions = all_sessions
        if not sessions:
            if all_sessions:
                if gun_tab:
                    config_label = f"{self.gun_weapon.upper()} · {self.gun_drill.upper()} · {self.duration}s"
                elif tab == "spray":
                    config_label = f"{self.duration}s · {self.spray_weapon.upper()}"
                else:
                    config_label = f"{self.duration}s · {SIZE_TH[self.size_key]}"
                msg = f"ยังไม่มีข้อมูลของ config นี้ ({config_label}) — เลือก config อื่นด้านบน"
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
            if gun_tab and self.gun_is_ladder():
                # DUEL/ANGLE/PEEK: การ์ดแรกเป็นแรงค์ดวลของดริลนี้ (ค่ากลาง tier_i 5 รอบล่าสุด) แทนคะแนนสูงสุด —
                # คะแนนขึ้นกับระดับบอทที่เจอ
                from . import duel
                rt = duel.recent_tier(self.data["history"], self.gun_weapon, mode_current, drill=self.gun_drill)
                if rt is not None:
                    cards[0] = (RANKS[rt[0]][1], f"DUEL TIER · {rt[2]} ดวล")
        cw = S(170)
        x0 = (W - (cw + S(10)) * 4) // 2
        cards_y = S(190) if gun_tab else S(128) if cfg_tab else S(96)
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
        head_tab = _head_tab(tab)
        empty_msg = None
        if head_tab:
            # โหมดเล็งหัว: ใช้เฉพาะช็อตที่วัดเทียบหัว (ref=head) — ช็อตเก่าวัดเทียบลำตัว (หัวสูงกว่า 1.15R)
            # แก้ย้อนไม่ได้เพราะไม่ได้เก็บระยะเป้า ถ้าปนกันแผนที่จะเลื่อนขึ้นทั้งก้อน (ดู config.HEAD_MODES)
            legacy = len(all_shots)
            all_shots = [s for s in all_shots if s.get("ref") == "head"]
            if legacy and not all_shots:
                empty_msg = "ช็อตรอบเก่าวัดเทียบลำตัว — เล่นรอบใหม่เพื่อดูแผนที่เทียบหัว"
        self.draw_shotmap(heat, all_shots, "AGGREGATED SHOT MAP", ref="head" if head_tab else None,
                          empty_msg=empty_msg)
        tier_vals = []
        if gun_tab and self.gun_is_ladder():
            # DUEL/ANGLE/PEEK: กราฟแรงค์ดวลต่อรอบ (ทุกความยาวรอบ — บันไดเดินต่อข้ามรอบ) แทนคะแนนที่ขึ้นกับระดับบอท
            tier_vals = [e["tier_i"] for e in self.insight_sessions("gun")
                         if (e.get("variant") or "vandal") == self.gun_weapon
                         and (e.get("drill") or "duel") == self.gun_drill and isinstance(e.get("tier_i"), int)]
        if is_react and rts:
            self.draw_trend(trend, rts, "REACTION TIME (ms) — ต่ำ = ดี", invert=True)
        elif tier_vals:
            self.draw_trend(trend, tier_vals, f"DUEL TIER ({self.gun_weapon.upper()} · 0 Iron I – 22 Radiant · ทุกความยาวรอบ)")
        else:
            ttl = "SCORE OVER SESSIONS"
            if gun_tab:
                ttl += f" ({self.gun_weapon.upper()} · {self.gun_drill.upper()} · {self.duration}s)"
            elif tab == "spray":
                ttl += f" ({self.duration}s · {self.spray_weapon.upper()})"
            elif cfg_tab:
                ttl += f" ({self.duration}s · {SIZE_TH[self.size_key]})"
            self.draw_trend(trend, scores, ttl)
        # tips
        ty = gy + gh + S(10)
        tips = self.build_tips(tab, sessions, all_shots, self.bias_groups(tab, sessions))
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

    TREND_MAX_N = 10     # เทียบ n รอบล่าสุดกับ n รอบก่อนหน้า (สมมาตร) n = min(10, len//2)
    TREND_MIN_N = 4      # ต่ำกว่านี้ต่อฝั่ง = noise ล้วน (เดิม 2 ต่อ 2 → "ฟอร์มตก 57%" จาก 5 รอบ gun)
    TREND_MIN_T = 2.0    # |ส่วนต่าง| ต้องเกิน ~2 SE (Welch) — ต่างแค่ % แต่แกว่งกว่านั้น = ยังสรุปไม่ได้ ไม่ขึ้น tip

    def build_tips(self, tab, sessions, shots, shot_groups=None):
        """shot_groups = ช็อตแยกต่อรอบ (Insight ส่งมา — SE แบบ cluster) ; ไม่ส่ง = ถือว่า shots เป็นก้อนเดียว"""
        tips = []
        is_react = tab.startswith("reaction")
        key = "rt" if is_react else "score"
        n = min(self.TREND_MAX_N, len(sessions) // 2)
        if n >= self.TREND_MIN_N:
            old = [e.get(key, 0) for e in sessions[-2 * n:-n]]
            new = [e.get(key, 0) for e in sessions[-n:]]
            oa, na = sum(old) / n, sum(new) / n
            better = na < oa if is_react else na > oa
            pct = abs((na - oa) / oa * 100) if oa else 0
            se = math.sqrt((self.stdev(old) ** 2 + self.stdev(new) ** 2) / (n - 1))   # stdev = แบบประชากร → หาร n-1
            sig = (abs(na - oa) >= self.TREND_MIN_T * se) if se > 0 else na != oa
            if pct >= 5 and sig:
                tips.append(f"{'กำลังเก่งขึ้น' if better else 'ฟอร์มตก'} — {n} รอบล่าสุด"
                            f"{'ดีขึ้น' if better else 'แย่ลง'} {pct:.0f}% เทียบ {n} รอบก่อนหน้า")
        if tab not in ("strafe", "sniper"):
            tip = self.bias_tip(tab, shot_groups if shot_groups is not None else [shots])
            if tip:
                tips.append(tip)
        if is_react:
            rts = [e.get("rt", 0) for e in sessions if e.get("rt", 0) > 0]
            if len(rts) >= 3:
                sd = self.stdev(rts)
                cv = sd / (sum(rts) / len(rts)) * 100 if rts else 0
                if cv > 15:
                    tips.append(f"Reaction time ไม่นิ่ง — แกว่ง ±{sd:.0f}ms ฝึกความสม่ำเสมอ")
                elif cv < 8:
                    tips.append(f"Reaction time สม่ำเสมอมาก (±{sd:.0f}ms) — ระดับเชี่ยวชาญ")
        if tab == "reaction-peek":
            from .reactpeek import rpeek_tips
            tips = rpeek_tips(sessions) + tips
        if tab == "strafe" and len(sessions) >= 3:
            m = sum(e.get("acc", 0) for e in sessions) / len(sessions)
            tips.append(f"Perfect counter-strafe เฉลี่ย {m:.0f}%" +
                        (" — กดทิศตรงข้ามก่อนยิงให้เร็วขึ้น" if m < 50 else ""))
        if tab in ("strafe", "dodge"):
            # นัดที่ยิงขณะเร็วเกิน deadzone (entry ตั้งแต่ strafe/dodge rev 2) — วิ่งยิง = สเปรด +6° แทบไม่โดน
            mv = [e["moving_pct"] for e in sessions if "moving_pct" in e]
            if len(mv) >= 3:
                m = sum(mv) / len(mv)
                tips.append(f"ยิงขณะเคลื่อนที่เฉลี่ย {m:.0f}% ของนัด ({len(mv)} รอบ)" +
                            (" — ปล่อยปุ่ม/กดทิศตรงข้ามให้นิ่งก่อนคลิก (วิ่งยิงกระจาย 6°)" if m >= 10
                             else " — หยุดก่อนยิงได้ดี"))
        if tab == "sniper" and len(sessions) >= 3:
            m = sum(e.get("acc", 0) for e in sessions) / len(sessions)
            tips.append(f"Hit rate เฉลี่ย {m:.0f}%" + (" — เน้นกะจังหวะบอลผ่านประตู" if m < 50 else " — แม่นมาก!"))
        if tab == "gun":
            # GUNFIGHT v2: แรงค์ดวล + ตัวชี้วัดเฉพาะดริล (ANGLE/PEEK/TAP/ADAD — gundrills.drill_tips) + นิสัยที่ตัดสินดวลจริง
            # (เห็นบอท→นัดแรก, ยิงตอนยังเดิน) — ขึ้นก่อน tip อื่น
            from .gundrills import drill_tips
            st = sorted(e["rt"] for e in self.data["history"] if e.get("mode") == "reaction"
                        and e.get("variant", "static") == "static" and e.get("rt", 0) > 0)
            dtips = drill_tips(self.gun_drill, sessions, st[len(st) // 2] if st else None)
            lt = self.gun_ladder_tips(sessions)
            tips = (lt[:1] + dtips + lt[1:] if dtips else lt) + tips
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
            # ปืนสั้น: กระสุน/คิล เทียบขั้นต่ำจากตารางดาเมจจริง — เกินขั้นต่ำตัวไปมาก = รัวจนสเปรดโต (ต้องแตะเป็นจังหวะ)
            # ไม่รวมรอบที่ใช้คลิกขวา Classic (เม็ด 3 ลูกต่อชุดทำให้ตัวเลขพองโดยไม่ได้แปลว่ารัว)
            from .guns import WEAPONS as _WP, shots_to_kill as _stk
            from .stability import patched_block
            wv = self.gun_weapon
            es = [e for e in sessions if not e.get("alt_bursts")]
            k = sum(e.get("kills", 0) for e in es)
            sf = sum(e.get("shots_fired", 0) for e in es)
            if _WP.get(wv, {}).get("kind") == "pistol" and k >= 5 and sf:
                d0 = _WP[wv]["dmg"][0][0] - 1
                hmin, bmin = _stk(wv, "head", d0), _stk(wv, "body", d0)
                tap = (patched_block(wv) or {}).get("tap_eff")
                spk = sf / k
                tip = f"{wv.upper()}: กระสุน/คิล {spk:.1f} (ขั้นต่ำ {hmin} หัว / {bmin} ตัว, {k} คิล)"
                if spk > bmin + 1 and tap:
                    tip += f" — แตะไม่เกิน {tap:g} นัด/วิ: ถี่กว่านั้นสเปรดโตทุกนัด"
                tips.append(tip)
        if not is_react and tab not in ("strafe", "sniper", "gun") and len(sessions) >= 3:
            m = sum(e.get("acc", 0) for e in sessions) / len(sessions)
            if m >= 80:
                tips.append(f"Accuracy เฉลี่ย {m:.0f}% — ระดับโปร ลองลดขนาดเป้าหรือเพิ่มความเร็ว")
            elif m < 50:
                tips.append(f"Accuracy แค่ {m:.0f}% — เน้นแม่นก่อน ค่อยเร็วทีหลัง")
        return tips

    def gun_ladder_tips(self, sessions):
        """tip ของ GUNFIGHT v2: แรงค์ดวล (DUEL) + เวลาเห็นบอท→นัดแรก เทียบ reaction·static ของตัวเอง + นัดที่ยิงตอนยังเดิน
        (ตัวเลขจาก history ของผู้ใช้เอง ไม่ใช้ขีดตัดสินลอย ๆ — ส่วนต่างกับ reaction = เวลาหา/เล็ง ที่ฝึกลดได้)"""
        from . import duel
        tips = []
        hist = self.data["history"]
        wv = self.gun_weapon
        dr = self.gun_drill
        if self.gun_is_ladder():
            rt = duel.recent_tier(hist, wv, mode_current, drill=dr)
            name = "" if dr == "duel" else f" {dr.upper()}"
            start, prior = duel.ladder_resume(hist, wv, mode_current, dr)
            lad = duel.Ladder(start, prior=prior) if start is not None else None
            if rt is None and lad is not None:
                # เล่นแล้วแต่สายบันไดยังไม่นิ่ง — ยังไม่มี tier_i ให้โชว์ ; บอกจำนวนดวลที่ยังขาดจริง (duel.Ladder.need —
                # เดิมเขียน "กลับทิศแล้วดวลต่ออีก 3 ครั้ง" ซึ่งเกินจริงหนึ่งดวลและไม่ใช่เกณฑ์ความแม่น)
                nd = lad.need()
                if nd is None:
                    more = f"{'ชนะ' if prior and prior[-1][1] else 'แพ้'}รวดมาตลอด บันไดยังหาระดับไม่เจอ"
                elif nd == 0:
                    more = "ข้อมูลพอแล้ว เล่นอีกรอบก็ได้แรงค์"
                else:
                    more = f"ต้องดวลรวมอีก ~{nd} ดวล — ดวลเดียวบอกระดับได้น้อย ต้องรวมหลายรอบ"
                tips.append(f"แรงค์ดวล {wv.upper()}{name}: ยังไม่นิ่ง — {more} ; เล่นต่อได้เลย รอบหน้าเริ่มจากบอท "
                            f"{duel.step_label(start)}")
            elif rt is None:
                tips.append(f"{wv.upper()} {dr.upper()} มีแรงค์ดวล — เล่นจบรอบเพื่อเริ่มบันได (ชนะ = บอทเก่งขึ้น 1 ขั้น "
                            f"แพ้ = ลง)")
            else:
                idx, k, nd = rt
                # tier_i แต่ละรอบคิดจาก ~LADDER_WINDOW ดวลล่าสุดของสายแล้ว — ช่วง ± = 80% จาก SE ของสายตอนนี้
                sp = lad.spread() if lad is not None else None
                more = (f" — แต่ละรอบคิดจาก {len(lad.window())} ดวลล่าสุด คลาดราว ±{sp} ขั้น" if sp is not None
                        and lad.se() <= duel.LADDER_SE else "")
                tips.append(f"แรงค์ดวล {wv.upper()}{name}: {RANKS[idx][1]} (ค่ากลาง {k} รอบล่าสุด, {nd} ดวล){more}")
        fm = sorted(e["first_ms"] for e in sessions if isinstance(e.get("first_ms"), (int, float)))
        if len(fm) >= 3:
            med = fm[len(fm) // 2]
            st = sorted(e["rt"] for e in hist if e.get("mode") == "reaction"
                        and e.get("variant", "static") == "static" and e.get("rt", 0) > 0)
            if st:
                base = st[len(st) // 2]
                tips.append(f"เห็นบอทถึงนัดแรก ค่ากลาง {med}ms ({len(fm)} รอบ) vs reaction·static {base}ms — ส่วนต่าง "
                            f"{med - base}ms คือเวลาหา/เล็ง: วาง crosshair ที่ขอบกำแพงระดับหัวรอไว้")
            else:
                tips.append(f"เห็นบอทถึงนัดแรก ค่ากลาง {med}ms ({len(fm)} รอบ) — วาง crosshair ที่ขอบกำแพงระดับหัวรอไว้")
        mv = [e["moving_pct"] for e in sessions if isinstance(e.get("moving_pct"), (int, float))]
        if len(mv) >= 3:
            # ค่าต่อรอบ → ช่วง t ข้ามรอบ (รอบ = cluster) ; เตือนเมื่อทั้งช่วงเกินเกณฑ์คร่าว ๆ เดียวกับ PEEK (ยังไม่ได้วัด)
            from .gundrills import t_interval, PEEK_MOVE_CUT
            m, h = t_interval(mv)
            cut = 100 * PEEK_MOVE_CUT
            rng = f"ช่วง {max(0.0, m - h):.0f}–{min(100.0, m + h):.0f}%, {len(mv)} รอบ"
            if m - h >= cut:
                tips.append(f"ยิงตอนยังเดิน {m:.0f}% ของนัด ({rng} ; เกณฑ์คร่าว ๆ {cut:.0f}%) — counter-strafe ให้นิ่งก่อนคลิก")
            elif m >= cut:
                tips.append(f"ยิงตอนยังเดิน {m:.0f}% ของนัด ({rng}) — ยังสรุปไม่ได้ว่าเกินเกณฑ์คร่าว ๆ {cut:.0f}%")
        return tips

    @staticmethod
    def bias_groups(tab, sessions):
        """ช็อตแยกต่อรอบให้ aim bias (SE แบบ cluster) — โหมดคลาสสิกที่เปิด headshots แล้วได้หัว (hs>0) ตัดออก:
        ช็อตวัดเทียบใจกลางลำตัวแต่ผู้เล่นตั้งใจเล็งหัว (สูงกว่า 1.15R) → snapshot: ทุกรอบ flick ที่ hs>0 ค่ากลาง
        y +27..+48 px ส่วนรอบ hs=0 อยู่ −5..+3 px → ถ้าปนกัน tip จะบอก "เยื้องบน" ปลอม"""
        head = _head_tab(tab)
        return [e.get("shots") or [] for e in sessions if head or not e.get("hs")]

    def bias_tip(self, tab, groups):
        """tip จุดเล็งเยื้อง — จากทุกนัด (โดน+พลาด) ต่อแกน ต้องชัดทางสถิติ (|ค่ากลาง| ≥ ครึ่งช่วง 95%) และเกิน BIAS_PX
        ถึงจะบอกทิศ ; ช่วงแคบพอแต่ไม่เยื้อง = เซ็นเตอร์ดี ; ช่วงยังกว้าง = ยังสรุปไม่ได้ + ต้องอีกกี่นัด (ไม่เดาทิศจาก noise)"""
        head = _head_tab(tab)
        if head:
            # ช็อตยุคก่อน ref=head วัดเทียบใจกลางลำตัว → bias "บน" ปลอมเสมอ ห้ามเอามาคิด (ดู config.HEAD_MODES)
            groups = [[s for s in g if s.get("ref") == "head"] for g in groups]
        b = aim_bias(groups)
        if not b:
            return None
        what = "หัว" if head else "เป้า"
        (mx, hx, ix), (my, hy, iy) = b["x"], b["y"]
        n = b["n"]
        # ค่า x,y = ตำแหน่งเป้า (หัว ในโหมดหัว) เทียบ crosshair ตอนยิง → จุดเล็งเยื้องไป "ฝั่งตรงข้าม"
        dirs, det = [], []
        if abs(mx) > BIAS_PX and abs(mx) >= hx:
            dirs.append("ซ้าย" if mx > 0 else "ขวา")      # เป้าอยู่ขวาของ crosshair = flick ขวาไม่สุด
            det.append(f"{abs(mx):.0f}±{hx:.0f}")
        if abs(my) > BIAS_PX and abs(my) >= hy:
            dirs.append("บน" if my > 0 else "ล่าง")       # เป้าอยู่ใต้ crosshair = ยิงสูงไป
            det.append(f"{abs(my):.0f}±{hy:.0f}")
        if dirs:
            fix = ("วาง crosshair ไว้ระดับหัวก่อนเจอ ไม่ต้องลากขึ้นทุกครั้ง" if dirs == ["ล่าง"] and head
                   else "ลด crosshair ลงมาระดับหัวพอดี — ตั้งเผื่อสูงไปหรือ flick เลยหัว" if dirs == ["บน"] and head
                   else "ลาก flick ให้สุดกว่าเดิม หรือทดลองปรับ sens แล้วเทียบกราฟ")
            return (f"Aim bias: จุดเล็งเฉลี่ยเยื้องทาง{'-'.join(dirs)}ของ{what} {' / '.join(det)} px "
                    f"({n} นัด) — {fix}")
        off = max(abs(mx) + hx, abs(my) + hy)          # ขอบบนของช่วง = เยื้องได้มากสุดเท่าที่ข้อมูลยังเชื่อได้
        if off <= BIAS_PX or max(hx, hy) <= BIAS_PX / 2:
            # ทั้งช่วงอยู่ใน ±BIAS_PX (หรือช่วงแคบพอและค่ากลางไม่ถึงเกณฑ์) = ยืนยันได้ว่าไม่เยื้องจนมีผล
            return f"Aim เซ็นเตอร์ดี — จุดเล็งเฉลี่ยห่างศูนย์{what}ไม่เกิน ~{off:.0f} px ({n} นัด) ไม่มี bias ต้องแก้"
        # ช่วงยังกว้าง: ต้องได้ครึ่งช่วง ≈ BIAS_PX/2 ถึงจะแยก "เยื้องจริง" กับ "เซ็นเตอร์" ได้ (ช่วงหดตาม √จำนวน)
        # ถ้าช่วงกว้างเพราะแต่ละรอบเยื้องคนละทาง (cluster ≫ นัดอิสระ) ยิงเพิ่มในรอบเดิมไม่ช่วย — บอกเป็นจำนวนรอบ
        grow = (max(hx, hy) / (BIAS_PX / 2)) ** 2
        if max(hx, hy) > 1.5 * max(ix, iy) and b["rounds"] >= 2:
            more = f"{max(1, math.ceil(b['rounds'] * grow) - b['rounds'])} รอบ (แต่ละรอบเยื้องไม่เท่ากัน)"
        else:
            more = f"{max(10, int(math.ceil((n * grow - n) / 10.0)) * 10)} นัด"
        return (f"Aim ยังสรุปไม่ได้ว่าเยื้องไหม — จุดเล็งเฉลี่ยยังแกว่ง ±{max(hx, hy):.0f} px ({n} นัด) "
                f"ต้องอีก ~{more}")

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
        save_data(self.data, merge=False)   # ล้างจริง — ห้าม merge รอบเก่าบนดิสก์กลับมา
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
        s = self.ui_scale()
        y = self.H // 2 + int(100 * s)
        # รอบจาก routine/วอร์ม: บอกว่าข้อไหน ทำไม — คิวสลับลำดับแบบสุ่ม ผู้เล่นต้องรู้ก่อนเริ่มว่ากำลังจะเจออะไร
        src = getattr(self, "round_src", None)
        if isinstance(src, dict) and src.get("label"):
            kind = {"routine": "ROUTINE", "plan": "PLAN", "warmup": "WARMUP"}.get(src.get("src"), "")
            pos = f" ข้อ {src['k']}/{src['n']}" if src.get("k") and src.get("n") else ""
            self.text(f"{kind}{pos} · {src['label']}", int(18 * s), C_GOLD, (self.W // 2, y), center=True, bold=True)
            y += int(28 * s)
            if src.get("why"):
                self.text(self.fit_text(src["why"], int(13 * s), self.W - int(60 * s)), int(13 * s), C_DIM,
                          (self.W // 2, y), center=True)
                y += int(26 * s)
        # กติกาของดริลใหม่/REACTION·PEEK ใต้เลขนับถอยหลัง (เดิมมีแค่เลข "3" แล้วคำใบ้ในเกมโผล่ 3 วิ)
        rule = self.countdown_rule()
        if rule:
            self.text(self.fit_text(rule, int(14 * s), self.W - int(60 * s)), int(14 * s), C_PALE_GOLD,
                      (self.W // 2, y), center=True, bold=True)

    def countdown_rule(self):
        """บรรทัดกติกาของรอบที่กำลังจะเริ่ม (None = โหมดที่อธิบายตัวเองได้)"""
        if self.mode == "reaction" and self.reaction_variant == "peek":
            from .reactpeek import RPEEK_RULE
            return RPEEK_RULE
        if self.mode == "gun":
            from .gunplay import GUN_DRILL_RULE
            return GUN_DRILL_RULE.get(self.gun_drill)
        return None

    def draw_pause(self):
        self.draw_world()
        self.screen.blit(self.scrim((8, 20, 28, 200)), (0, 0))
        self.mark_full()   # กันเชิงป้องกัน — state pause ปกติไม่ track อยู่แล้ว (แพทเทิร์นเดียวกับ countdown)
        # ขยายตามจอแบบเดียวกับเมนู/หน้าผล (ui_scale อิง 1280×720) — เดิมพิกเซลตายตัว ที่ 2560×1440 ปุ่มเหลือครึ่งเดียว
        s = self.ui_scale()

        def S(v):
            return int(round(v * s))
        cx, cy = self.W // 2, self.H // 2
        self.text("PAUSED", S(56), C_TEXT, (cx, cy - S(70)), center=True, bold=True)
        self.button((cx - S(160), cy, S(150), S(44)), "เล่นต่อ", self.resume_play, size=S(15))
        self.button((cx + S(10), cy, S(150), S(44)), "จบรอบ", self.end_game, size=S(15))
        src = getattr(self, "round_src", None)
        # รอบจากชุดซ้อม: ESC = ออกจากชุด (game.go_menu ทิ้งคิว + คืนค่าเมนู) — บอกให้รู้ว่ากลับมาต่อได้จากปุ่มบนการ์ด
        esc = ("ESC = ออกจากชุดซ้อม กลับเมนู (กด ROUTINE ต่อจากที่ค้างได้)" if isinstance(src, dict)
               and src.get("src") == "routine" else "ESC = กลับเมนู")
        self.text(self.fit_text(f"{esc} · R = เริ่มรอบใหม่", S(13), self.W - S(40)), S(13), C_DIM,
                  (cx, cy + S(70)), center=True)
