# -*- coding: utf-8 -*-
"""หน้าผล + ประวัติของโหมด CLUTCH 1vN (CLUTCH_DESIGN §8 / §10.5) — ClutchResultsMixin
• ไม่มีแรงค์/โล่ปลอม (config.UNRANKED_MODES) — หัวหน้าผล = ชนะ/แพ้ + เหตุ ; การ์ด คิล/หัว/แม่น/เวลา
• ข้อเท็จจริงโค้ช: โดนได้ยินเสียงเท้ากี่ครั้ง, โดนเห็นพร้อมกัน ≥ 2 ตัว, ยิงตอนเคลื่อนที่ %, ปะทะแรก→นัดแรก, เวลาเหลือตอนเริ่ม
  วาง/กู้, กู้หลอก + อัตราชนะของผู้เล่นจริงเทียบ (clutchmap.ref_winrates)
• แผนภาพเส้นทาง (static top-down): ทางเดินเรา (เดิน/วิ่ง=มีเสียง) + จุดยิง/คิล/ตาย/วาง/กู้ + ตำแหน่งบอทตอนจบ — อยู่ในหน่วยความจำ
  เท่านั้น ; history มีแค่ตัวเลขเล็ก ๆ (§8 — ไฟล์เซฟ/dashboard อ่านทั้งไฟล์ทุกรอบ)
• ปุ่ม: เล่นต่อ (ฉากใหม่) / ฉากเดิมอีกครั้ง / ตั้งค่า / แคปจอ / เมนู + RESULTS_ACTIONS (การ์ดส่งออก)"""
import math

import pygame

from .config import C_BORDER, C_DARKER, C_DIM, C_GOLD, C_GREEN, C_PALE_GOLD, C_PANEL, C_RED, C_TEXT, mode_current
from . import clutchmap, clutchmesh, duel, guns, registry


def wilson_lb(k, n, z=1.96):
    """ขอบล่าง Wilson 95% ของอัตราชนะ k/n (รอบน้อย = ต่ำไว้ก่อน ไม่หลอกว่าเก่ง)"""
    if n <= 0:
        return 0.0
    p = k / float(n)
    d = 1.0 + z * z / n
    c = p + z * z / (2.0 * n)
    r = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return max(0.0, (c - r) / d)


def clutch_stats(history):
    """{(variant แมพ, drill atkN/defN): (ชนะ, รอบ)} จากรอบกติการุ่นปัจจุบัน"""
    out = {}
    for e in history or []:
        if isinstance(e, dict) and e.get("mode") == "clutch" and mode_current(e):
            k = (e.get("variant"), e.get("drill"))
            w, n = out.get(k, (0, 0))
            out[k] = (w + (1 if e.get("win") else 0), n + 1)
    return out


def ref_rate(side, n):
    """อัตราชนะ clutch ของผู้เล่นจริง (data report §4a) เป็น 0..1 หรือ None — ref_wr ของ index.json เป็น %"""
    try:
        v = (clutchmap.ref_winrates().get(side) or {}).get(str(n))
        v = float(v)
    except Exception:
        return None
    return v / 100.0            # index.json เขียนเป็น % เสมอ (map_bake: round(100·w/c, 1)) — 0.2% ต้องไม่กลายเป็น 20%


class ClutchResultsMixin:
    # ───────────────────────── history ─────────────────────────
    def clutch_fill_entry(self, ent):
        """ฟิลด์ history ของรอบ clutch (§8) — variant = slug แมพ ≤12 (a-z0-9_), drill = atk1..def5"""
        res = self.cl_result or {"win": 0, "why": "quit"}
        slug = self.cmap.slug if self.cmap is not None else self.clutch_cfg()["map"]
        shots = self.gun_shots
        site = (self.clutch_scen or {}).get("s", "")
        if self.clutch_side == "atk" and (self.cl_spike or {}).get("site"):
            site = self.cl_spike["site"]                          # ไซต์ที่วางจริง (ฉากป้าย B วางที่ A ได้)
        ent.update(variant=str(slug)[:12], drill=f"{self.clutch_side}{self.clutch_n}",
                   site=site, win=res["win"], why=res["why"],
                   kills=self.gun_kills, deaths=1 if self.cl_dead else 0, hs=self.gun_hs, shots_fired=shots,
                   acc=round(self.gun_hits / shots * 100) if shots else 0, rt=self.cl_rt or 0,
                   t_used=round(self.cl_t_end if self.cl_t_end is not None else self.gt, 1), tier_bot=self.clutch_tier,
                   weapon=self.gun_weapon, heard=self.cl_heard, multi=self.cl_multi,
                   moving_pct=round(self.gun_moving_shots / shots * 100) if shots else 0,
                   plant_t=self.cl_plant_left, defuse_t=self.cl_defuse_left, scen=self.clutch_scen_i,
                   duration=0, size="")
        if self.clutch_side == "def":
            ent["fake"] = self.cl_fake
        if getattr(self, "cl_jump_shots", 0):
            ent["jump_shots"] = self.cl_jump_shots                # §13 เฉพาะรอบที่มี (history เล็กเสมอ §8)
        return ent

    # ───────────────────────── สรุปผล ─────────────────────────
    def clutch_rname(self):
        """ป้ายใต้ผล — ไม่ใช่ชื่อแรงค์ (ไม่มีโล่) : แมพ · ฝั่ง 1vN · ระดับบอท"""
        name = self.cmap.name if self.cmap is not None else "CLUTCH"
        return f"{name} · {self.clutch_side.upper()} 1v{self.clutch_n} · บอท {duel.step_label(self.clutch_tier)}", "#7F9BB5"

    def clutch_result_cards(self):
        shots, hits = self.gun_shots, self.gun_hits
        acc = f"{round(hits / shots * 100)}%" if shots else "—"         # ไม่ได้ยิง = ไม่มีค่า (ไม่ใช่ 0% สีแดง)
        hs = f"{round(self.gun_hs / hits * 100)}%" if hits else "—"
        t = self.cl_t_end if self.cl_t_end is not None else self.gt
        cards = [(f"{self.gun_kills}/{self.clutch_n}", "KILLS"), (hs, "HEADSHOT"), (acc, "ACCURACY"),
                 (f"{t:.0f}s", "TIME")]
        return cards, f"คะแนน {self.score:,}"

    def clutch_facts(self):
        """[(ข้อความ, สี)] ข้อเท็จจริงสำหรับโค้ช (§8/§10.5)"""
        out = []
        h = self.cl_heard
        out.append((f"ศัตรูได้ยินเสียงเท้าเรา {h} ครั้ง" + (" — ใกล้ศัตรูให้เดิน Shift/หมอบ (เงียบ)" if h else " — เงียบดี"),
                    C_GOLD if h else C_GREEN))
        m = self.cl_multi
        out.append((f"โดนเห็นพร้อมกัน ≥ 2 ตัว {m} ครั้ง" + (" — แยกดวลทีละตัว" if m else ""), C_GOLD if m else C_GREEN))
        if self.gun_shots:
            mv = round(self.gun_moving_shots / self.gun_shots * 100)
            out.append((f"ยิงตอนยังเคลื่อนที่ {mv}% ({self.gun_moving_shots}/{self.gun_shots} นัด)",
                        C_GOLD if mv >= 20 else C_DIM))
        js = getattr(self, "cl_jump_shots", 0)
        if js:
            out.append((f"กระโดดยิง {js} นัด — กลางอากาศกระสุนกระจาย 7-20 องศา (ลงพื้นก่อนยิง)", C_GOLD))
        out.append((f"เห็นศัตรูถึงนัดแรก {self.cl_rt} ms" if self.cl_rt else "ไม่มีจังหวะเห็นแล้วยิงภายใน 2 วิ", C_DIM))
        if self.clutch_side == "atk":
            out.append((f"เวลาเหลือตอนเริ่มวาง {self.cl_plant_left:.0f} วิ" if self.cl_plant_left is not None
                        else "ยังไม่ได้เริ่มวาง spike", C_DIM))
        else:
            out.append((f"spike เหลือตอนเริ่มกู้ {self.cl_defuse_left:.0f} วิ · กดกู้ {self.cl_defuse_n} ครั้ง"
                        f" · กู้หลอก {self.cl_fake}" if self.cl_defuse_left is not None else "ยังไม่ได้เริ่มกู้", C_DIM))
        out.append((self._clutch_rate_line(), C_PALE_GOLD))
        return out

    def _clutch_rate_line(self):
        """อัตราชนะของเราในฉากนี้ (แมพ × ฝั่ง×N) + ของผู้เล่นจริง — หน้าผลวาดทุกเฟรม: คิดใหม่เมื่อ history เปลี่ยนเท่านั้น"""
        hist = self.data.get("history") or []
        slug = (self.cmap.slug if self.cmap is not None else self.clutch_cfg()["map"])[:12]
        key = (len(hist), slug, self.clutch_side, self.clutch_n)
        c = getattr(self, "_cl_rate", None)
        if c is not None and c[0] == key:
            return c[1]
        w, n = clutch_stats(hist).get((slug, f"{self.clutch_side}{self.clutch_n}"), (0, 0))
        ref = ref_rate(self.clutch_side, self.clutch_n)
        line = f"ฉากนี้ของคุณ: ชนะ {w}/{n}" + (f" (ขอบล่าง {wilson_lb(w, n) * 100:.0f}%)" if n else "")
        if ref is not None:
            line += f" · ผู้เล่นจริง 1v{self.clutch_n} ชนะ {ref * 100:.0f}%"
        self._cl_rate = (key, line)
        return line

    # ───────────────────────── วาดหน้าผล ─────────────────────────
    def draw_clutch_results(self):
        from .clutchscen import why_text
        W, H = self.W, self.H
        s = self.ui_scale()

        def S(v):
            return int(round(v * s))
        self.screen.fill(C_DARKER)
        res = self.cl_result or {"win": 0, "why": "quit"}
        sc = self.clutch_scen or {}
        wname = guns.WEAPONS.get(self.gun_weapon, {}).get("name", self.gun_weapon.upper())
        head = (f"CLUTCH 1vN — {self.cmap.name if self.cmap is not None else '?'} · {self.clutch_side.upper()} "
                f"1v{self.clutch_n} · ไซต์ {sc.get('s', '?')} · {wname}")
        self.text(self.fit_text(head, S(15), W - S(40)), S(15), C_DIM, (W // 2, S(26)), center=True)
        win = bool(res["win"])
        self.text("WIN" if win else "LOSE", S(56), C_GREEN if win else C_RED, (W // 2, S(76)), center=True, bold=True)
        self.text(why_text(self.clutch_side, res["why"], (self.cl_spike or {}).get("state") != "carried"), S(16), C_TEXT,
                  (W // 2, S(118)), center=True, bold=True)
        rname, rcol = self.clutch_rname()
        pb = "PERSONAL BEST!  " if self.res_pb else ""
        self.text(self.fit_text(f"{pb}{rname} · คะแนน {self.score:,}", S(13), W - S(40), bool(pb)), S(13),
                  C_GREEN if pb else C_DIM, (W // 2, S(144)), center=True, bold=bool(pb))
        by = H - S(62)
        y0 = S(166)
        ch = by - S(12) - y0
        lw = int(min(S(470), (W - S(60)) * 0.54))
        side = max(S(120), min(ch, W - lw - S(64)))
        lx = (W - (lw + S(20) + side)) // 2
        cards, _extra = self.clutch_result_cards()
        cw = (lw - 3 * S(8)) // 4
        for i, (v, lbl) in enumerate(cards):
            card = pygame.Rect(lx + i * (cw + S(8)), y0, cw, S(60))
            pygame.draw.rect(self.screen, C_PANEL, card, border_radius=4)
            pygame.draw.rect(self.screen, C_BORDER, card, 1, border_radius=4)
            col = C_TEXT
            if lbl == "ACCURACY" and v.endswith("%"):
                pv = int(v.rstrip("%"))
                col = C_GREEN if pv >= 70 else C_GOLD if pv >= 45 else C_RED
            self.text(v, S(20), col, (card.centerx, card.y + S(20)), center=True, bold=True)
            self.text(self.fit_text(lbl, S(10), cw - S(6)), S(10), C_DIM, (card.centerx, card.y + S(44)), center=True)
        fy = y0 + S(72)
        self.text("สิ่งที่เห็นจากรอบนี้", S(12), C_RED, (lx, fy), bold=True)
        fy += S(20)
        lines = self.clutch_facts() + [(t, c) for t, c in self.results_latency_lines()][-1:]
        for txt, col in lines:
            if fy + S(16) > by - S(10):
                break
            self.text(self.fit_text(txt, S(12), lw), S(12), col, (lx, fy))
            fy += S(19)
        self.clutch_draw_replay(pygame.Rect(lx + lw + S(20), y0, side, side), S)
        if getattr(self, "shot_saved_until", 0) > pygame.time.get_ticks():
            self.text(self.shot_saved_msg, S(13), C_GREEN, (W // 2, by - S(16)), center=True, bold=True)
        row = [("เล่นต่อ (ฉากใหม่)", lambda: self.clutch_start(False), True),
               ("ฉากเดิมอีกครั้ง", lambda: self.clutch_start(True), False),
               ("ตั้งค่า", self.clutch_open_setup, False), ("แคปจอ", self.capture_screen, False),
               ("MENU (M)", self.go_menu, False)]
        row += [(a["label"], (lambda f=a["on_click"]: f(self)), False) for a in registry.RESULTS_ACTIONS]
        widths = [190, 170, 110, 110, 110] + [150] * len(registry.RESULTS_ACTIONS)
        gap = S(10)
        k = min(s, (W - S(24) - gap * (len(widths) - 1)) / float(sum(widths)))
        widths = [int(w * k) for w in widths]
        bx = (W - (sum(widths) + gap * (len(widths) - 1))) // 2
        fs = max(9, min(S(13), int(13 * k)))
        for (lbl, fn, main), bw in zip(row, widths):
            self.button((bx, by, bw, S(42)), self.fit_text(lbl, fs, bw - S(10), True), fn, size=fs, active=main)
            bx += bw + gap

    def clutch_open_setup(self):
        from . import clutchsetup
        clutchsetup.open_setup(self)

    def clutch_draw_replay(self, rect, S):
        """แผนภาพเส้นทาง (top-down, north-up) — เดิน = ฟ้า, วิ่ง (มีเสียง) = ส้ม ; ยิง/คิล/ตาย/วาง/กู้ ; บอทตอนจบ"""
        scr = self.screen
        pygame.draw.rect(scr, C_PANEL, rect, border_radius=4)
        pygame.draw.rect(scr, C_BORDER, rect, 1, border_radius=4)
        self.text("เส้นทางของคุณ", S(11), C_DIM, (rect.x + S(8), rect.y + S(6)), bold=True)
        cm = self.cmap
        if cm is None:
            return
        inner = rect.inflate(-S(12), -S(46))
        inner.y = rect.y + S(24)
        px = max(16, min(inner.w, inner.h))
        img = self.clutch_minimap(px)
        ir = img.get_rect(center=inner.center)
        scr.blit(img, ir)

        def P(x, z):
            u, v = clutchmesh.minimap_xy(cm, ir.w, ir.h, x, z)
            return int(ir.x + u), int(ir.y + v)
        prev = scr.get_clip()
        scr.set_clip(rect)
        try:
            pts = self.cl_path
            for a, b in zip(pts, pts[1:]):
                pygame.draw.line(scr, (255, 150, 60) if b[2] else (110, 190, 255), P(a[0], a[1]), P(b[0], b[1]), 2)
            if pts:
                pygame.draw.circle(scr, C_GREEN, P(pts[0][0], pts[0][1]), S(4))
            for x, z, alive in self.cl_bots_end:
                pygame.draw.circle(scr, (255, 70, 85) if alive else (120, 120, 120), P(x, z), S(4))
            sp = self.cl_spike or {}
            if sp.get("state") in ("planted", "defused", "detonated"):
                x, y = P(sp["x"], sp["z"])
                r = S(5)
                pygame.draw.polygon(scr, C_GREEN if sp["state"] == "defused" else (255, 60, 60),
                                    [(x, y - r), (x + r, y), (x, y + r), (x - r, y)])
            for kind, x, z, _t in self.cl_events:
                c = P(x, z)
                if kind == "fight":
                    pygame.draw.circle(scr, C_GOLD, c, S(3))
                elif kind in ("kill", "death"):
                    r = S(5) if kind == "kill" else S(7)
                    col = (255, 90, 90) if kind == "kill" else (240, 240, 240)
                    pygame.draw.line(scr, col, (c[0] - r, c[1] - r), (c[0] + r, c[1] + r), 2)
                    pygame.draw.line(scr, col, (c[0] - r, c[1] + r), (c[0] + r, c[1] - r), 2)
        finally:
            scr.set_clip(prev)
        lx, ly = rect.x + S(8), rect.bottom - S(18)
        for lbl, col in (("เดิน", (110, 190, 255)), ("วิ่ง (มีเสียง)", (255, 150, 60)), ("ยิง", C_GOLD),
                         ("คิล", (255, 90, 90)), ("บอท", (255, 70, 85))):
            if lx + S(11) + self.text_width(lbl, S(10)) > rect.right - S(4):
                break
            pygame.draw.rect(scr, col, (lx, ly + S(4), S(8), S(8)))
            lx = self.text(lbl, S(10), C_DIM, (lx + S(11), ly)).right + S(8)
