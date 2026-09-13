# -*- coding: utf-8 -*-
"""หน้าสรุปผล + radar + shotmap/trend + capture/clipboard — ResultsMixin (ย้าย verbatim + ตะเข็บ)"""

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
from . import data as _data, registry

class ResultsMixin:
    def draw_shotmap(self, r, shots, title):
        pygame.draw.rect(self.screen, (10, 21, 32), r, border_radius=3)
        pygame.draw.rect(self.screen, C_BORDER, r, 1, border_radius=3)
        self.text(title, 10, C_DIM, (r.centerx, r.y + 10), center=True, bold=True)
        area = r.inflate(-20, -44)
        area.y += 12
        cx, cy = area.centerx, area.centery
        for i in range(1, 8):
            x = area.x + i * area.w // 8
            y = area.y + i * area.h // 8
            pygame.draw.line(self.screen, (31, 49, 64), (x, area.y), (x, area.bottom), 1)
            pygame.draw.line(self.screen, (31, 49, 64), (area.x, y), (area.right, y), 1)
        pygame.draw.line(self.screen, (90, 110, 130), (cx, area.y), (cx, area.bottom), 1)
        pygame.draw.line(self.screen, (90, 110, 130), (area.x, cy), (area.right, cy), 1)
        pygame.draw.circle(self.screen, C_PALE_GOLD, (cx, cy), 4, 1)
        if not shots:
            self.text("no shots", 11, C_DIM, (cx, cy + 24), center=True)
            return
        max_off = max(60.0, max(max(abs(s.get("x", 0)), abs(s.get("y", 0))) for s in shots))
        scale = (area.w / 2 * 0.9) / max_off
        # กลับแกน: กลางแผนที่ = ใจกลางเป้า, จุด = ตำแหน่งที่กระสุนตก (แบบ Aim Lab)
        # (ข้อมูลเก็บเป็น "เป้าเทียบ crosshair" จึงต้องคูณ -1 ตอนวาด)
        for s in shots[-150:]:
            x = cx - s.get("x", 0) * scale
            y = cy - s.get("y", 0) * scale
            c = C_GREEN if s.get("hit") else C_RED
            pygame.draw.circle(self.screen, c, (int(x), int(y)), 4 if s.get("hit") else 5, 0 if s.get("hit") else 1)
        self.text("จุด = ตำแหน่งกระสุนเทียบใจกลางเป้า · เขียว=โดน แดง=พลาด", 10, C_DIM,
                  (r.centerx, r.bottom - 12), center=True)

    def draw_trend(self, r, vals, title, invert=False):
        pygame.draw.rect(self.screen, (10, 21, 32), r, border_radius=3)
        pygame.draw.rect(self.screen, C_BORDER, r, 1, border_radius=3)
        self.text(title, 10, C_DIM, (r.centerx, r.y + 10), center=True, bold=True)
        vals = vals[-20:]
        if len(vals) < 2:
            self.text("เล่นอีก 1 เกมเพื่อดูกราฟ", 11, C_DIM, r.center, center=True)
            return
        area = r.inflate(-60, -56)
        vmax, vmin = max(vals) * 1.1 or 1, (min(vals) * 0.9 if invert else 0)
        rng = (vmax - vmin) or 1
        self.text(f"{vmax:,.0f}", 10, C_DIM, (r.x + 8, area.y - 6))
        self.text(f"{vmin:,.0f}", 10, C_DIM, (r.x + 8, area.bottom - 8))
        best = min(vals) if invert else max(vals)
        pts = []
        for i, v in enumerate(vals):
            x = area.x + (i / (len(vals) - 1)) * area.w
            y = area.y + (1 - (v - vmin) / rng) * area.h
            pts.append((x, y))
        by = area.y + (1 - (best - vmin) / rng) * area.h
        pygame.draw.line(self.screen, (120, 110, 80), (area.x, by), (area.right, by), 1)
        pygame.draw.lines(self.screen, C_RED, False, pts, 2)
        for i, (x, y) in enumerate(pts):
            c = C_PALE_GOLD if i == len(pts) - 1 else C_GREEN if vals[i] == best else C_RED
            pygame.draw.circle(self.screen, c, (int(x), int(y)), 3)
        self.text(f"last {len(vals)} games", 10, C_DIM, (r.centerx, r.bottom - 12), center=True)

    def draw_radar(self, r, axes, title):
        """เรดาร์ 6 แกน: axes = [(label, value0..1), ...] (สูงสุด 6)"""
        self.section_header(title, r.x + 14, r.y + 12, r.w - 28)
        cx, cy = r.centerx, r.centery + 8
        rad = min(r.w, r.h - 40) // 2 - 26
        n = len(axes)
        ang0 = -math.pi / 2
        def pt(frac, i):
            a = ang0 + i * 2 * math.pi / n
            return (cx + math.cos(a) * rad * frac, cy + math.sin(a) * rad * frac)
        # วงกรอบ (rings)
        for ring in (0.33, 0.66, 1.0):
            poly = [pt(ring, i) for i in range(n)]
            pygame.draw.polygon(self.screen, C_BORDER, poly, 1)
        # แกนรัศมี
        for i in range(n):
            pygame.draw.line(self.screen, C_BORDER, (cx, cy), pt(1.0, i), 1)
        # polygon ค่าจริง
        vpoly = [pt(max(0.04, min(1.0, axes[i][1])), i) for i in range(n)]
        try:
            surf = pygame.Surface(r.size, pygame.SRCALPHA)
            local = [(p[0] - r.x, p[1] - r.y) for p in vpoly]
            pygame.draw.polygon(surf, (*C_RED, 70), local)
            self.screen.blit(surf, r.topleft)
        except Exception:
            pass
        pygame.draw.polygon(self.screen, C_RED, vpoly, 2)
        for p in vpoly:
            pygame.draw.circle(self.screen, C_RED, (int(p[0]), int(p[1])), 3)
        # label รอบนอก
        for i, (lbl, _v) in enumerate(axes):
            lp = pt(1.22, i)
            self.text(lbl, 10, C_DIM, (int(lp[0]), int(lp[1])), center=True, bold=True)

    def _best_hit_run(self):
        """ยิงโดนติดต่อกันยาวสุดในรอบ (นับจาก shot_data)"""
        best = cur = 0
        for s in self.shot_data:
            if s.get("hit"):
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    @staticmethod
    def _consist(vals):
        """ความสม่ำเสมอ 0..1 จากสัมประสิทธิ์การกระจาย (CV) — กระจายน้อย=สูง"""
        vals = [v for v in vals if v > 0]
        if len(vals) < 2:
            return 0.6
        m = sum(vals) / len(vals)
        if m <= 0:
            return 0.6
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        return max(0.0, min(1.0, 1.0 - sd / m))

    def results_radar_axes(self):
        """คำนวณ 6 แกนของรอบที่จบ คืน list[(label, 0..1)] — ทุกโหมดมีครบ 6 แกน"""
        md = self.mode
        def clamp(x):
            return max(0.0, min(1.0, x))
        if md == "strafe":
            total = self.hits + self.misses
            acc_s = clamp(self.hits / total) if total else 0
            perfect = clamp(self.strafe_perfect / self.strafe_shots) if self.strafe_shots else 0
            vol = clamp(self.hits / max(6.0, 0.8 * self.duration))
            rts = [t for t in self.strafe_times if t > 0]
            speed = clamp((600 - sum(rts) / len(rts)) / (600 - 180)) if rts else 0
            return [("SCORE", vol), ("ACC", acc_s), ("SPEED", speed),
                    ("PERFECT", perfect), ("CONSIST", self._consist(self.strafe_times)),
                    ("STREAK", clamp(self.strafe_best_streak / 8.0))]
        if md == "sniper":
            total = self.hits + self.misses
            acc_s = clamp(self.hits / total) if total else 0
            done = clamp(self.sniper_hits / max(1, SNIPER_TOTAL))
            hist = self.history_for("sniper")
            bs = [e.get("score", 0) for e in hist if e.get("score", 0) > 0]
            best = max(bs + [self.score, 1])
            rts = [t for t in self.sniper_rts if t > 0]
            speed = clamp((650 - sum(rts) / len(rts)) / (650 - 200)) if rts else 0
            return [("SCORE", clamp(self.score / best)), ("ACC", acc_s), ("SPEED", speed),
                    ("HITS", done), ("CONSIST", self._consist(self.sniper_rts)),
                    ("STREAK", clamp(self._best_hit_run() / 6.0))]
        # ── เรดาร์โหมดใหม่ ──
        if md == "spray":
            hist = self.history_for("spray", duration=self.duration)
            scores = [e.get("score", 0) for e in hist]
            best = max(scores) if scores else self.score
            ob = self.spray_onbody / self.spray_shots if self.spray_shots else 0
            hs = self.spray_heads / self.spray_onbody if self.spray_onbody else 0
            ctrl = clamp((ob - 0.2) / 0.7)
            return [("คุมเป้า", clamp(ob)), ("HEAD%", clamp(hs)),
                    ("SCORE", clamp(self.score / best) if best else 0),
                    ("CONTROL", ctrl), ("VOLUME", clamp(self.spray_shots / 80.0)),
                    ("STABLE", clamp(ob))]
        if md == "dodge":
            dodged = self.dodge_dodged / self.dodge_total_haz if self.dodge_total_haz else 0
            survive = self.dodge_hp / DODGE_HP_MAX
            total = self.hits + self.misses
            hit_rate = clamp(self.hits / total) if total else 0
            hs = self.headshots / self.hits if self.hits else 0
            return [("DODGE", clamp(dodged)), ("SURVIVE", clamp(survive)),
                    ("KILLS", clamp(self.hits / 12.0)), ("ACC", clamp((self.res_acc or 0) / 100.0)),
                    ("HEAD%", clamp(hs)), ("SCORE", clamp(self.score / 1800.0))]
        if md == "placement":
            avg = sum(self.placement_preaim) / len(self.placement_preaim) if self.placement_preaim else PLACEMENT_MAX_DEG
            preaim_q = clamp((PLACEMENT_MAX_DEG - avg) / (PLACEMENT_MAX_DEG - PLACEMENT_GOOD_DEG))
            total = self.hits + self.misses
            hit_rate = clamp(self.hits / total) if total else 0
            hs = self.headshots / self.hits if self.hits else 0
            rts = [t for t in self.reaction_times if t > 0]
            speed = clamp((700 - (sum(rts) / len(rts))) / (700 - 200)) if rts else 0
            return [("PRE-AIM", preaim_q), ("ACC", clamp((self.res_acc or 0) / 100.0)),
                    ("SPEED", speed), ("HEAD%", clamp(hs)), ("HITS", hit_rate),
                    ("SCORE", clamp(self.score / 2400.0))]
        if md == "switch":
            sw = sum(self.switch_kill_times) / len(self.switch_kill_times) if self.switch_kill_times else 1000
            speed = clamp((900 - sw) / (900 - 250))
            total = self.hits + self.misses
            hit_rate = clamp(self.hits / total) if total else 0
            hs = self.headshots / self.hits if self.hits else 0
            return [("SWITCH", speed), ("ACC", clamp((self.res_acc or 0) / 100.0)),
                    ("WAVES", clamp(self.switch_waves_cleared / 8.0)),
                    ("KILLS", clamp(self.hits / 20.0)), ("HEAD%", clamp(hs)),
                    ("SCORE", clamp(self.score / 4000.0))]
        if md == "gun":
            ttk = sum(self.gun_ttk) / len(self.gun_ttk) if self.gun_ttk else 2000
            kills, deaths = self.gun_kills, self.gun_deaths
            acc_g = clamp(self.gun_hits / self.gun_shots) if self.gun_shots else 0
            hs = clamp(self.gun_hs / self.gun_hits) if self.gun_hits else 0
            return [("SPEED", clamp((1500 - ttk) / (1500 - 350))), ("ACC", acc_g),
                    ("SURVIVE", clamp(kills / (kills + deaths)) if (kills + deaths) else 0),
                    ("KILLS", clamp(kills / (0.5 * self.duration))), ("HEAD%", hs),
                    ("SCORE", clamp(self.score / (120.0 * self.duration)))]
        acc = clamp((self.res_acc or 0) / 100.0)
        if md == "reaction":
            rts = [t for t in self.reaction_times if t > 0]
            if not rts:
                return None
            avg = sum(rts) / len(rts)
            speed = clamp((400 - avg) / (400 - 150))
            mn, mx = min(rts), max(rts)
            consistency = clamp(1 - (mx - mn) / 250.0)
            total = self.hits + self.misses
            hit_rate = clamp(self.hits / total) if total else 0
            hist = self.history_for("reaction", self.reaction_variant)
            prev = [e.get("rt", 0) for e in hist if e.get("rt", 0) > 0]
            best = min(prev) if prev else avg
            score_n = clamp((400 - avg) / (400 - max(140, best * 0.9)))
            streak = clamp(self.hits / 8.0)
            return [("SPEED", speed), ("ACC", acc), ("HITS", hit_rate),
                    ("CONSIST", consistency), ("SCORE", score_n), ("STREAK", streak)]
        # โหมดคะแนน flick/precision/tracking — ครบ 6 แกน ไม่ยุบ
        hist = self.history_for(md, duration=self.duration, size=self.size_key)
        scores = [e.get("score", 0) for e in hist if e.get("score", 0) > 0]
        best = max(scores + [self.score, 1])
        score_n = clamp(self.score / best)
        # HITS = ปริมาณคิล เทียบอัตราที่คาดหวังตามเวลา (แยกจาก ACC)
        rate_ref = {"flick": 1.2, "precision": 0.9, "tracking": 3.2}.get(md, 1.2)
        hit_vol = clamp(self.hits / (rate_ref * self.duration)) if self.duration else 0
        # SPEED = เก็บเป้าเร็ว ใช้หน้าต่าง RT เฉพาะโหมด (tracking ช้ากว่าโดยธรรมชาติ)
        rts = [t for t in self.reaction_times if t > 0]
        if rts:
            avg = sum(rts) / len(rts)
            fast, slow = (450.0, 1500.0) if md == "tracking" else (180.0, 650.0)
            speed = clamp((slow - avg) / (slow - fast))
        else:
            speed = clamp(self.score / (best * 1.2))
        return [("SCORE", score_n), ("ACC", acc), ("SPEED", speed),
                ("HITS", hit_vol), ("CONSIST", self._consist(rts)),
                ("STREAK", clamp(self._best_hit_run() / 12.0))]

    def draw_results(self):
        W, H = self.W, self.H
        self.screen.fill(C_DARKER)
        md = self.mode
        self.text("TRAINING COMPLETE — " + MODE_NAME[md], 15, C_DIM, (W // 2, 30), center=True)
        # คะแนนใหญ่ + แรงค์
        if md == "reaction":
            big, sub = f"{self.res_avg_rt}", "ms (เฉลี่ย)"
            _, rname, rcol = get_rt_rank(self.res_avg_rt, self.reaction_variant)
            nxt = next_rt_rank(self.res_avg_rt, self.reaction_variant)
            nxt_txt = f"Next: {nxt[1]} (ต้อง ≤ {nxt[0]:.0f}ms)" if nxt else "MAX RANK — RADIANT!"
            if self.early_clicks:
                nxt_txt += f"  ·  กดก่อนเป้าโผล่ {self.early_clicks} ครั้ง (โดนโทษ +100ms)"
        elif md == "strafe":
            big, sub = f"{self.hits}", "targets"
            rname, rcol = "TRAINING", "#7F9BB5"
            nxt_txt = f"Perfect counter-strafe: {self.strafe_perfect}/{self.hits}"
        elif md == "sniper":
            big, sub = f"{self.sniper_hits}", f"/ {SNIPER_TOTAL}"
            rname, rcol = "SNIPER TRAINING", "#B97FE0"
            nxt_txt = ""
        elif md == "gun":
            big, sub = f"{self.score:,}", ""
            from .gunplay import GUN_DRILL_NAME
            rname = f"GUNFIGHT · {self.gun_w()['name']} · {GUN_DRILL_NAME[self.gun_drill]}"
            rcol = "#B97FE0"
            _cards, nxt_txt = self.gun_result_cards()
            nxt_txt = "ยังไม่จัดแรงค์ (รอสอบเทียบ) · " + nxt_txt
        else:
            big, sub = f"{self.score:,}", ""
            _, rname, rcol = get_rank(self.score, self.duration, self.size_key, md)
            nxt = next_rank(self.score, self.duration, self.size_key, md)
            nxt_txt = f"Next: {nxt[1]} (ขาดอีก {nxt[0] - self.score:,})" if nxt else "MAX RANK!"
        r1 = self.text(big, 64, C_RED, (W // 2, 86), center=True, bold=True)
        if sub:
            self.text(sub, 20, C_DIM, (r1.right + 40, 96), center=True)
        rcol_rgb = hexrgb(rcol) if isinstance(rcol, str) else rcol
        if parse_rank(rname)[0] in VALID_TIERS:
            rnw = self.font(18, True).size(rname)[0]
            em, gpx = 34, 12
            lx = W // 2 - (em + gpx + rnw) // 2
            self.draw_rank_emblem(lx + em // 2, 138, em, rname, rcol_rgb)
            self.text(rname, 18, rcol_rgb, (lx + em + gpx + rnw // 2, 138), center=True, bold=True)
        else:
            self.text(rname, 18, rcol_rgb, (W // 2, 138), center=True, bold=True)
        pb = "PERSONAL BEST!  " if self.res_pb else ""
        self.text(pb + nxt_txt, 13, C_GREEN if pb else C_DIM, (W // 2, 164), center=True, bold=bool(pb))
        # การ์ดสถิติ
        if md == "strafe":
            avg_t = round(sum(self.strafe_times) / len(self.strafe_times)) if self.strafe_times else 0
            pf = round(self.strafe_perfect / self.hits * 100) if self.hits else 0
            cards = [(str(self.hits), "TARGETS"), (f"{pf}%", "PERFECT"),
                     (str(self.strafe_best_streak), "BEST STREAK"), (f"{avg_t}ms", "AVG TIME")]
        elif md == "sniper":
            avg_rt = round(sum(self.sniper_rts) / len(self.sniper_rts)) if self.sniper_rts else 0
            cards = [(str(self.sniper_hits), "BALLS HIT"), (str(self.sniper_missed), "ESCAPED"),
                     (f"{round(self.sniper_hits / SNIPER_TOTAL * 100)}%", "HIT RATE"), (f"{avg_rt}ms", "AVG RT")]
        elif md == "reaction":
            mn = round(min(self.reaction_times)) if self.reaction_times else 0
            mx = round(max(self.reaction_times)) if self.reaction_times else 0
            cards = [(str(self.hits), "HITS"), (str(self.misses), "MISSES"),
                     (f"{mn}ms", "MIN RT"), (f"{mx}ms", "MAX RT")]
        elif md == "spray":
            ob = round(self.spray_onbody / self.spray_shots * 100) if self.spray_shots else 0
            hs = round(self.spray_heads / self.spray_onbody * 100) if self.spray_onbody else 0
            cards = [(f"{ob}%", "ON-TARGET"), (str(self.spray_shots), "BULLETS"),
                     (str(self.spray_heads), "HEADSHOTS"), (f"{hs}%", "HEAD RATE")]
        elif md == "dodge":
            dd = f"{self.dodge_dodged}/{self.dodge_total_haz}"
            cards = [(str(self.hits), "KILLS"), (dd, "DODGED"),
                     (str(self.headshots), "HEADSHOTS"), (str(self.dodge_hp), "HP LEFT")]
        elif md == "placement":
            avg = sum(self.placement_preaim) / len(self.placement_preaim) if self.placement_preaim else 0
            hs = round(self.headshots / self.hits * 100) if self.hits else 0
            cards = [(str(self.hits), "KILLS"), (f"{avg:.1f}°", "AVG PRE-AIM"),
                     (f"{self.res_acc}%", "ACCURACY"), (f"{hs}%", "HEAD RATE")]
        elif md == "switch":
            sw = round(sum(self.switch_kill_times) / len(self.switch_kill_times)) if self.switch_kill_times else 0
            fastest = round(min(self.switch_wave_clears), 2) if self.switch_wave_clears else 0
            cards = [(str(self.switch_waves_cleared), "WAVES"), (f"{sw}ms", "AVG SWITCH"),
                     (f"{fastest}s", "FASTEST"), (f"{self.res_acc}%", "ACCURACY")]
        elif md == "gun":
            cards, _extra = self.gun_result_cards()
        else:
            cards = [(str(self.hits), "TARGETS HIT"), (str(self.misses), "MISSES"),
                     (f"{self.res_acc}%", "ACCURACY"), (f"{self.res_avg_rt}ms", "AVG REACT")]
        cw = 150
        x0 = (W - (cw + 12) * 4) // 2
        # จัด block (การ์ด 74 + ช่องว่าง 16 + กราฟ gh) ให้อยู่กึ่งกลางช่วงระหว่าง header(~180) กับปุ่มล่าง(by)
        by = H - 92
        head_end = 180
        gap_cg = 16
        gh = min(320, max(150, (by - 24) - (head_end + 74 + gap_cg)))
        block_h = 74 + gap_cg + gh
        cards_y = head_end + max(0, ((by - 24) - head_end - block_h) // 2)
        for i, (v, l) in enumerate(cards):
            card = pygame.Rect(x0 + i * (cw + 12), cards_y, cw, 74)
            pygame.draw.rect(self.screen, C_PANEL, card, border_radius=4)
            pygame.draw.rect(self.screen, C_BORDER, card, 1, border_radius=4)
            acc_col = C_TEXT
            if l in ("ACCURACY", "PERFECT", "HIT RATE"):
                pv = int(v.rstrip("%"))
                acc_col = C_GREEN if pv >= 70 else C_GOLD if pv >= 45 else C_RED
            self.text(v, 24, acc_col, (card.centerx, card.y + 22), center=True, bold=True)
            self.text(l, 10, C_DIM, (card.centerx, card.y + 52), center=True)
        # shot map + (radar) + history
        gy = cards_y + 74 + gap_cg
        radar_axes = self.results_radar_axes()
        if radar_axes:
            # 3 คอลัมน์: shot map | radar | history
            self.draw_shotmap(pygame.Rect(W // 2 - 390, gy, 250, gh), self.shot_data, "SHOT MAP")
            rrad = pygame.Rect(W // 2 - 128, gy, 256, gh)
            pygame.draw.rect(self.screen, C_PANEL, rrad, border_radius=4)
            pygame.draw.rect(self.screen, C_BORDER, rrad, 1, border_radius=4)
            self.draw_radar(rrad, radar_axes, "STAT RADAR")
            hist_rect = pygame.Rect(W // 2 + 140, gy, 250, gh)
        else:
            # ไม่มีเรดาร์ (strafe/sniper): shot map + history กว้างเหมือนเดิม
            self.draw_shotmap(pygame.Rect(W // 2 - 390, gy, 250, gh), self.shot_data, "SHOT MAP")
            hist_rect = pygame.Rect(W // 2 - 120, gy, 510, gh)
        if md == "reaction":
            hist = self.history_for("reaction", self.reaction_variant)
            vals = [e.get("rt", 0) for e in hist if e.get("rt", 0) > 0]
            self.draw_trend(hist_rect, vals, "RT HISTORY — ต่ำ = ดี", invert=True)
        elif md == "sniper":
            hist = self.history_for("sniper")
            vals = [e.get("score", 0) for e in hist]
            self.draw_trend(hist_rect, vals, "HIT HISTORY (SNIPER OP)")
        elif md == "spray":
            hist = [e for e in self.history_for("spray", duration=self.duration)
                    if e.get("variant", "vandal") == self.spray_weapon]
            vals = [e.get("score", 0) for e in hist]
            self.draw_trend(hist_rect, vals, f"SCORE HISTORY (SPRAY {self.spray_weapon.upper()} · {self.duration}s)")
        elif md == "gun":
            hist = [e for e in self.history_for("gun", self.gun_weapon, duration=self.duration)
                    if e.get("drill", "duel") == self.gun_drill]
            vals = [e.get("score", 0) for e in hist]
            self.draw_trend(hist_rect, vals, f"SCORE HISTORY ({self.gun_w()['name']} · {self.gun_drill.upper()} · {self.duration}s)")
        else:
            hist = self.history_for(md, duration=self.duration, size=self.size_key)
            vals = [e.get("score", 0) for e in hist]
            self.draw_trend(hist_rect, vals, f"SCORE HISTORY ({MODE_NAME[md]} · {self.duration}s · {SIZE_TH[self.size_key]})")
        # ข้อความยืนยันแคปจอ (อยู่เหนือแถวปุ่ม)
        if getattr(self, "shot_saved_until", 0) > pygame.time.get_ticks():
            self.text(self.shot_saved_msg, 13, C_GREEN, (W // 2, by - 18), center=True, bold=True)
        # ชื่อ + ปุ่ม (จัดกึ่งกลางแถว)
        bw_name, bw_save, bw_cap, bw_retry, bw_menu = 170, 150, 120, 120, 110
        bg2 = 10
        row_w = bw_name + bw_save + bw_cap + bw_retry + bw_menu + bg2 * 4
        bx = (W - row_w) // 2
        name_r = pygame.Rect(bx, by, bw_name, 42)
        def focus_name():
            self.text_focus = "name"
        self.zone(name_r, focus_name)
        pygame.draw.rect(self.screen, C_PANEL, name_r, border_radius=3)
        pygame.draw.rect(self.screen, C_RED if self.text_focus == "name" else C_BORDER, name_r, 1, border_radius=3)
        nm = self.data.get("name", "")
        shown = nm if nm else "PLAYER NAME"
        if self.text_focus == "name" and (pygame.time.get_ticks() // 400) % 2 == 0:
            shown = nm + "|"
        self.text(shown, 14, C_GOLD if nm else C_DIM, name_r.center, center=True, bold=True)
        bx += bw_name + bg2
        self.button((bx, by, bw_save, 42),
                    "บันทึกแล้ว" if self.score_saved else "SAVE SCORE", self.save_score, size=13,
                    active=self.score_saved)
        bx += bw_save + bg2
        self.button((bx, by, bw_cap, 42), "แคปจอ", self.capture_screen, size=13)
        bx += bw_cap + bg2
        self.button((bx, by, bw_retry, 42), "RETRY (R)", self.start_countdown, size=13)
        bx += bw_retry + bg2
        self.button((bx, by, bw_menu, 42), "MENU (M)", self.go_menu, size=13)
        # ── ตะเข็บ RESULTS_ACTIONS: ปุ่มเสริมจากโมดูลอื่น (เช่น export การ์ด) ต่อท้ายปุ่มเดิม ──
        _ax = bx + bw_menu + bg2
        for _act in registry.RESULTS_ACTIONS:
            self.button((_ax, by, 150, 42), _act["label"],
                        (lambda f=_act["on_click"]: f(self)), size=13)
            _ax += 150 + bg2

    def capture_screen(self):
        import datetime
        # อ้างผ่านโมดูลแบบ dynamic — ตอน --selftest ไฟล์ data ถูก redirect ไป temp
        # ถ้าใช้ DATA_FILE ที่ import มาตรงๆ ภาพเทสจะหลุดไปลงโฟลเดอร์ data/ จริงของผู้เล่น
        folder = os.path.dirname(_data.DATA_FILE)
        fn = os.path.join(folder, "valaim_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".png")
        saved = False
        try:
            pygame.image.save(self.screen, fn)
            saved = True
        except Exception:
            saved = False
        # ก๊อปลง clipboard เพื่อเอาไปแปะอวด (ข้ามตอน headless กัน selftest ไปยุ่งกับ clipboard จริง)
        copied = self.copy_to_clipboard(self.screen) if not self.headless else False
        if copied and saved:
            self.shot_saved_msg = "ก๊อปลง clipboard แล้ว (Ctrl+V แปะได้เลย) + เซฟไฟล์: " + os.path.basename(fn)
        elif copied:
            self.shot_saved_msg = "ก๊อปลง clipboard แล้ว — Ctrl+V แปะอวดได้เลย"
        elif saved:
            self.shot_saved_msg = "บันทึกภาพแล้ว: " + os.path.basename(fn)
        else:
            self.shot_saved_msg = "บันทึกภาพไม่สำเร็จ"
        self.shot_saved_until = pygame.time.get_ticks() + 3500

    def copy_to_clipboard(self, surface):
        """ก๊อปภาพหน้าจอลง Windows clipboard เป็น CF_DIB ไว้แปะอวดในแชต/โซเชียลได้ทันที
        ใช้ ctypes ของ Windows ตรง ๆ ไม่ต้องลงไลบรารีเพิ่ม; แพลตฟอร์มอื่นคืน False (ยังเซฟไฟล์อยู่)"""
        if sys.platform != "win32":
            return False
        try:
            import io
            import ctypes
            from ctypes import wintypes
            buf = io.BytesIO()
            pygame.image.save(surface, buf, "capture.bmp")   # BMP = BITMAPFILEHEADER(14) + DIB
            raw = buf.getvalue()
            buf.close()
            if len(raw) <= 14 or raw[:2] != b"BM":
                return False
            dib = raw[14:]                       # ตัด file header 14 ไบต์ เหลือ DIB ตามที่ CF_DIB ต้องการ
            CF_DIB, GMEM_MOVEABLE = 8, 0x0002
            k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
            k32.GlobalAlloc.restype = ctypes.c_void_p
            k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
            k32.GlobalLock.restype = ctypes.c_void_p
            k32.GlobalLock.argtypes = [ctypes.c_void_p]
            k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            k32.GlobalFree.argtypes = [ctypes.c_void_p]
            u32.SetClipboardData.restype = ctypes.c_void_p
            u32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
            h = k32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
            if not h:
                return False
            ptr = k32.GlobalLock(h)
            if not ptr:
                k32.GlobalFree(h)
                return False
            ctypes.memmove(ptr, dib, len(dib))
            k32.GlobalUnlock(h)
            if not u32.OpenClipboard(0):
                k32.GlobalFree(h)
                return False
            try:
                u32.EmptyClipboard()
                if not u32.SetClipboardData(CF_DIB, h):
                    k32.GlobalFree(h)
                    return False
                # สำเร็จ → ระบบเป็นเจ้าของ memory แล้ว ห้าม GlobalFree ซ้ำ
            finally:
                u32.CloseClipboard()
            return True
        except Exception:
            return False
