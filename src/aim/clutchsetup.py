# -*- coding: utf-8 -*-
"""หน้าตั้งค่า CLUTCH 1vN (CLUTCH_DESIGN §0 / §10.1 / §10.5) — FLOW แบบเมนู (แพทเทิร์น sensitivity.SensConvFlow)
ปุ่ม MENU_EXTRAS "CLUTCH 1vN" → เลือกแมพ (Training Yard เสมอ + แมพที่ bake ในเครื่อง), ฝั่ง ATK/DEF, ศัตรู 1–5, ไซต์,
ระดับบอท (ตามแรงค์ DUEL หรือคงที่), ปืน, การวางศัตรู (ตามแมตช์จริง/สุ่มจากจุดยืนยอดนิยม), ตัวเลือก → START
• เกมเพลย์ไม่วิ่งใน FLOW (ไม่มี event/pause/dirty-rect — modes report §2): START = game.clutch_start → mode "clutch" +
  start_countdown แล้ววงจรปกติ countdown → play → pause → results
• ไม่มี GPU world/ตัววาดแมพ → ปิด START + บอกเหตุ (selftest ส่ง force=True ได้)
• ตารางความชำนาญ แมพ × ฝั่ง × N = ขอบล่าง Wilson ของอัตราชนะ + อัตราชนะผู้เล่นจริง (clutchmap.ref_winrates)
• แมพจริง: บรรทัดแจ้ง IP ของ Riot (§10.1) ; ค่าตั้งเก็บใน S["clutch"]"""
import pygame

from .config import C_BORDER, C_DARKER, C_DIM, C_GOLD, C_GREEN, C_PALE_GOLD, C_PANEL, C_RED, C_TEXT
from .data import save_data
from . import clutchmap, duel, guns, registry
from .clutchscen import (TIER_CHOICES, WEAPON_CHOICES, YARD, _module, load_map, map_choices, norm_cfg)
from .clutchresults import clutch_stats, ref_rate, wilson_lb

RIOT_NOTE = "แมพจำลองจากมินิแมพของ Riot Games — ใช้ส่วนตัว ไม่ได้รับรองโดย Riot Games"
TIER_LBL = {6: "Silver I", 9: "Gold I", 12: "Plat I", 15: "Diamond I", 18: "Asc I", 21: "Immortal"}


class ClutchSetupFlow:
    """state sentinel "clutchsetup" (คลิกเข้า zones ของปุ่ม ไม่ใช่ยิง) ; ESC = on_exit (input.py) ; START = เล่น"""

    def __init__(self, game, force=False):
        self.g = game
        self.cfg = game.clutch_cfg()
        self.force = force
        # อ่านดัชนีแมพ/อัตราอ้างอิงครั้งเดียวตอนเปิดหน้า (ไม่อ่านไฟล์ทุกเฟรม)
        self.maps = map_choices()
        self.index = {m.get("slug"): m for m in clutchmap.list_maps() if isinstance(m, dict)}
        self.ref = {(sd, n): ref_rate(sd, n) for sd in ("atk", "def") for n in range(1, 6)}
        self._st = (None, {})
        if all(self.cfg["map"] != m[0] for m in self.maps):
            self.cfg["map"] = YARD                          # แมพที่เลือกไว้ไม่มีในเครื่องนี้แล้ว (ลบ/เครื่องเพื่อน)
        self._fix_site()
        self.msg = None
        game.state = "clutchsetup"
        try:
            game.grab_mouse(False)
        except Exception:
            pass

    def update(self, dt):
        pass

    def _set(self, k, v):
        self.cfg[k] = v
        if k == "map":
            self._fix_site()
        self.msg = None

    def _fix_site(self):
        """ไซต์ที่เลือกไว้ต้องมีในแมพนี้ — C จาก Haven/Lotus แล้วเปลี่ยนเป็นแมพ 2 ไซต์ = กลับเป็นสุ่ม (เดิมค้าง C:
        ไม่มีปุ่มไซต์ไหนติด และได้ฉากสร้างเองสุ่มไซต์ทุกรอบ)"""
        sites = next((m[2] for m in self.maps if m[0] == self.cfg.get("map")), ("A", "B"))
        if self.cfg.get("site") not in ("any",) + tuple(sites):
            self.cfg["site"] = "any"

    def _gl_msg(self):
        """เหตุที่ START ปิด (clutchhud.clutch_gl_reason — ข้อความเดียวกับภาพสำรองในเกม)"""
        return "โหมดนี้" + self.g.clutch_gl_reason()

    def _save(self):
        self.g.S["clutch"] = dict(norm_cfg(self.cfg))
        try:
            save_data(self.g.data)
        except Exception:
            pass

    def on_exit(self):
        self._save()
        self.g.clutch_leave()

    def _back(self):
        g = self.g
        self.on_exit()
        g.flow = None
        g.state = "menu"

    def ready(self):
        return self.force or self.g.clutch_gpu_ready()

    def _start(self):
        if not self.ready():
            self.msg = self._gl_msg()
            return
        self._save()
        try:
            # โหลดแมพ + nav + ข้อมูล GPU ตอนนี้ (หน้าตั้งค่ายังนิ่ง) ไม่ใช่เฟรมแรกของนับถอยหลัง
            from .clutch import prep_assets
            prep_assets(load_map(self.cfg["map"]))
        except Exception:
            self.cfg["map"] = YARD
            self._save()
        self.g.clutch_start(False)

    # ───────────────────────── วาด ─────────────────────────
    def _opts(self, x, y, w, label, items, key, S):
        """แถวตัวเลือก: ป้ายซ้าย + ปุ่มไหลตามความกว้าง (ขึ้นบรรทัดใหม่เอง) — คืน y ถัดไป"""
        g = self.g
        g.text(label, S(12), C_RED, (x, y + S(6)), bold=True)
        lab = S(92)
        bx, bh, gap, fs = x + lab, S(26), S(6), S(12)
        for val, txt in items:
            bw = max(S(40), g.text_width(txt, fs, True) + S(18))
            bw = min(bw, w - lab)
            if bx + bw > x + w and bx > x + lab:
                bx, y = x + lab, y + bh + gap
            cur = self.cfg.get(key) == val if key else bool(self.cfg.get(val))
            fn = (lambda k=key, v=val: self._set(k, v)) if key else (lambda v=val: self._set(v, not self.cfg.get(v)))
            g.button((bx, y, bw, bh), g.fit_text(txt, fs, bw - S(8), True), fn, active=cur, size=fs)
            bx += bw + gap
        return y + bh + S(8)

    def draw(self):
        g = self.g
        W, H = g.W, g.H
        s = g.ui_scale()

        def S(v):
            return int(round(v * s))
        g.screen.fill(C_DARKER)
        cx = W // 2
        g.text("CLUTCH 1vN — เหลือคนเดียว เลาะไปวาง / กู้ spike", S(22), C_TEXT, (cx, S(26)), center=True, bold=True)
        g.text(g.fit_text("ศัตรู 1–5 ตัวบนแมพจำลอง · ATK = เลาะไปวาง spike ให้ทัน · DEF = spike ลงแล้ว เข้าไปกู้ (retake)",
                          S(12), W - S(40)), S(12), C_DIM, (cx, S(52)), center=True)
        cols = [(sd, n) for sd in ("atk", "def") for n in range(1, 6)]
        cell, glab = S(27), S(84)
        gw = glab + cell * len(cols)
        cw = min(W - S(40), S(1180))
        x0 = (W - cw) // 2
        lw = cw - gw - S(24)
        c = self.cfg
        y = S(76)
        y = self._opts(x0, y, lw, "แมพ", [(m[0], m[1]) for m in self.maps], "map", S)
        y = self._opts(x0, y, lw, "ฝั่ง", [("atk", "ATK · วาง spike"), ("def", "DEF · กู้ (retake)")], "side", S)
        y = self._opts(x0, y, lw, "ศัตรู", [(n, f"1v{n}") for n in range(1, 6)], "n", S)
        sites = next((m[2] for m in self.maps if m[0] == c["map"]), ("A", "B"))
        y = self._opts(x0, y, lw, "ไซต์", [("any", "สุ่ม")] + [(x, x) for x in sites], "site", S)
        dt = duel.step_label(g.clutch_duel_tier(c["weapon"]))
        y = self._opts(x0, y, lw, "ระดับบอท", [("duel", f"ตามแรงค์ DUEL ({dt})")] +
                       [(t, TIER_LBL[t]) for t in TIER_CHOICES[1:]], "tier", S)
        y = self._opts(x0, y, lw, "ปืน", [(wp, guns.WEAPONS[wp]["name"]) for wp in WEAPON_CHOICES], "weapon", S)
        y = self._opts(x0, y, lw, "วางศัตรู", [("real", "ตามแมตช์จริง"), ("holds", "สุ่มจากจุดยืนยอดนิยม")],
                       "placement", S)
        y = self._opts(x0, y, lw, "ตัวเลือก", [("show_secs", "แสดงวินาที spike"),
                                              ("cue_heard", "เตือน: ศัตรูได้ยินเสียงเท้า")], None, S)
        self._grid(pygame.Rect(x0 + cw - gw, S(76), gw, 0), cols, cell, glab, S)
        # ── ล่าง: ข้อความแจ้ง + START ──
        by = H - S(54)
        ny = by - S(20)
        notes = []
        if self.msg or not self.ready():
            notes.append((self.msg or self._gl_msg(), C_RED))
        if _module("bots") is None:
            notes.append(("สมองบอทยังไม่พร้อม — ศัตรูเป็นหุ่นนิ่ง (ซ้อมเดิน/วาง/กู้ได้)", C_GOLD))
        if c["map"] != YARD:
            notes.append((RIOT_NOTE, C_DIM))
        for txt, col in reversed(notes):
            g.text(g.fit_text(txt, S(11), W - S(40)), S(11), col, (cx, ny), center=True)
            ny -= S(16)
        bw = S(220)
        g.button((cx - bw - S(8), by, bw, S(42)), "START", self._start, active=self.ready(), size=S(16),
                 disabled=not self.ready())
        g.button((cx + S(8), by, bw, S(42)), "กลับเมนู (ESC)", self._back, size=S(14))

    def _grid(self, r, cols, cell, glab, S):
        """ตารางความชำนาญ: แถว = แมพ, คอลัมน์ = ATK/DEF × 1..5 — % = ขอบล่าง Wilson ของอัตราชนะ (คลิก = เลือกฉากนั้น)"""
        g = self.g
        g.text("ความชำนาญ (ขอบล่างอัตราชนะ %)", S(12), C_RED, (r.x, r.y + S(6)), bold=True)
        y = r.y + S(28)
        half = cell * len(cols) // 2
        for k, lbl in enumerate(("ATK · วาง", "DEF · กู้")):
            g.text(lbl, S(10), C_TEXT, (r.x + glab + k * half + half // 2, y), center=True, bold=True)
        y += S(14)
        for i, (sd, n) in enumerate(cols):
            x = r.x + glab + i * cell
            g.text(f"1v{n}", S(9), C_DIM, (x + cell // 2, y), center=True)
        y += S(14)
        hist = g.data.get("history") or []
        if self._st[0] != len(hist):
            self._st = (len(hist), clutch_stats(hist))
        st = self._st[1]
        rh = S(22)
        for slug, name, _sites in self.maps:
            g.text(g.fit_text(name, S(11), glab - S(6)), S(11), C_TEXT if slug == self.cfg["map"] else C_DIM,
                   (r.x, y + S(4)))
            for i, (sd, n) in enumerate(cols):
                cr = pygame.Rect(r.x + glab + i * cell + 1, y, cell - 2, rh - 2)
                w, k = st.get((slug[:12], f"{sd}{n}"), (0, 0))
                sel = slug == self.cfg["map"] and sd == self.cfg["side"] and n == self.cfg["n"]
                g.zone(cr, lambda a=slug, b=sd, m=n: (self._set("map", a), self._set("side", b), self._set("n", m)))
                lb = wilson_lb(w, k)
                bg = C_PANEL if not k else (int(30 + 60 * lb), int(60 + 120 * lb), int(50 + 40 * lb))
                pygame.draw.rect(g.screen, bg, cr, border_radius=3)
                pygame.draw.rect(g.screen, C_RED if sel else C_BORDER, cr, 2 if sel else 1, border_radius=3)
                if k:
                    g.text(f"{lb * 100:.0f}", S(10), C_TEXT, cr.center, center=True, bold=True)
            y += rh
        g.text("ผู้เล่นจริง %", S(11), C_PALE_GOLD, (r.x, y + S(4)))
        for i, (sd, n) in enumerate(cols):
            v = self.ref.get((sd, n))
            if v is not None:
                g.text(f"{v * 100:.0f}", S(10), C_PALE_GOLD, (r.x + glab + i * cell + cell // 2, y + S(10)), center=True)
        y += rh + S(4)
        w, k = st.get((self.cfg["map"][:12], f"{self.cfg['side']}{self.cfg['n']}"), (0, 0))
        g.text(f"ที่เลือก: ชนะ {w}/{k}" + (f" · ขอบล่าง {wilson_lb(w, k) * 100:.0f}%" if k else " · ยังไม่เคยเล่น"),
               S(11), C_GREEN if k else C_DIM, (r.x, y))
        y += S(30)
        g.text("วิธีเล่น", S(12), C_RED, (r.x, y), bold=True)
        y += S(20)
        n_atk, n_def = self._scen_counts()
        for ln in ("4 = ถือ spike · คลิกซ้ายค้าง 4 วิในไซต์ = วาง (ยืนนิ่ง ยิงไม่ได้)",
                   "ค้าง 4/F ใกล้ spike 7 วิ = กู้ — ครึ่งทาง 3.5 วิ เก็บไว้ ; กดแล้วปล่อยเร็ว = กู้หลอก",
                   "วิ่ง = ศัตรูได้ยิน 32 ม. · Shift เดิน/Ctrl หมอบ = เงียบ · Tab = แมพใหญ่ · 1 = กลับปืน",
                   f"ฉากจริงในคลังของแมพนี้: ATK {n_atk} · DEF {n_def} (ไม่ตรง N = สุ่มจากจุดยืนยอดนิยม)"):
            for part in g.wrap_text(ln, S(11), r.w):
                g.text(part, S(11), C_DIM, (r.x, y))
                y += S(16)

    def _scen_counts(self):
        """จำนวนฉากจริงของแมพที่เลือก (ตามดัชนี — ไม่โหลดแมพเพื่อนับ)"""
        for m in self.maps:
            if m[0] == self.cfg["map"]:
                if m[0] == YARD:
                    cm = load_map(YARD)
                    return (sum(1 for s in cm.scen if s.get("t") == "atk"), sum(1 for s in cm.scen if s.get("t") == "def"))
                ns = (self.index.get(m[0]) or {}).get("n_scen") or {}
                return ns.get("atk", 0), ns.get("def", 0)
        return 0, 0


def open_setup(game, force=False):
    game.flow = ClutchSetupFlow(game, force=force)


def register(game):
    """ปุ่ม "CLUTCH 1vN" บนเมนู + FLOWS (idempotent — เทสสร้าง Game หลายตัว)"""
    registry.FLOWS["clutch_setup"] = lambda g: ClutchSetupFlow(g)
    if not any(it.get("_id") == "clutch" for it in registry.MENU_EXTRAS):
        registry.MENU_EXTRAS.append({"label": "CLUTCH 1vN", "on_click": open_setup, "_id": "clutch"})
