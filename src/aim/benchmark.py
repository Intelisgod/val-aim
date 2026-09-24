# -*- coding: utf-8 -*-
"""[Module 3] Voltaic-style benchmark + energy score — เจ้าของไฟล์นี้ไฟล์เดียว

โหมด "วัดผลมาตรฐาน": รันชุด scenario ตายตัว 6 อันต่อเนื่อง แล้วให้คะแนนแบบ energy
เทียบ rank สไตล์ Voltaic เพื่อให้ผู้เล่นวัดตัวเองกับมาตรฐานกลาง (ระบบ Iron→Radiant
ของเราเองเทียบคนนอกไม่ได้ — benchmark นี้จึงเป็นสเกลแยกต่างหาก)

โครง Voltaic: 3 หมวด (Clicking / Tracking / Switching) แตกเป็น 6 subcategory
  Dynamic, Static (clicking) · Precise, Reactive (tracking) · Speed, Evasive (switching)
พลังรวม (energy) ตัดสิน rank — ช่วงคร่าว ๆ: Novice ~100–400, Intermediate ~500–800, Advanced ~900+

เชื่อมต่อผ่าน register(game) เท่านั้น (append registry.MENU_EXTRAS + ลง registry.FLOWS) —
ไม่แตะ game.py/ไฟล์อื่น. ดูสัญญา (contract) ที่ aim/registry.py
ข้อจำกัด: ฟอนต์ไทยผ่าน game.text/font, ไม่มี emoji, ไม่ใช้ numpy
"""

import math
import time
import datetime

import pygame

from .config import (C_DARKER, C_RED, C_TEXT, C_DIM, C_PANEL, C_BORDER,
                     C_GOLD, C_PALE_GOLD, MODE_NAME, SIZE_TH)
from .ranks import scaled_ranks, hexrgb
from .data import save_data
from . import registry


# ════════════════════════════════════════════════════════════════════════
# 1) แม็ป 6 subcategory ของ Voltaic → โหมดที่มีอยู่ (พร้อมเหตุผล)
# ────────────────────────────────────────────────────────────────────────
# เลือก "เฉพาะโหมดที่มีระบบแรงค์ตามคะแนน" (get_rank/scaled_ranks ใช้ได้):
#   flick / precision / tracking / switch / dodge
# ไม่ใช้ strafe & sniper เพราะเป็นโหมดฝึกซ้อม "ไม่มีแรงค์" (คะแนน=จำนวนเป้า สเกลคนละโลกกับ
#   ladder คะแนนพัน ๆ → จะ normalize เป็น energy เพี้ยน) และไม่ใช้ reaction เพราะวัดด้วย RT
#   ไม่ใช่ score. ดู draw_results: strafe/sniper = "TRAINING", reaction = get_rt_rank
BENCH_DURATION = 30   # วินาที/scenario (สั้นตามสเปก; 30 = จุด calibrate มาตรฐาน TIME_FACTOR=1.0)

# "why" = ข้อความภาษาคนของแต่ละหมวด — ห้ามใช้ลูกศร/เครื่องหมายถูก/รูปทรง/กรีก เช่น → ✓ ▲ ● Σ (ฟอนต์ UI Leelawadee UI
# ไม่มี glyph ขึ้นเป็นกล่อง ; config.UI_FONT_NO_GLYPH — selftest สแกนทุกข้อความที่วาด)
SCENARIOS = [
    # Clicking
    {"key": "dynamic",  "label": "Dynamic",  "cat": "Clicking",  "mode": "flick",
     "size": "medium", "duration": BENCH_DURATION,
     "why": "flick: เป้าโผล่ทีละจุดให้สะบัดเล็งยิง = คลิกเป้าที่ขยับ/รีโพ (หมวด Dynamic clicking)"},
    {"key": "static",   "label": "Static",   "cat": "Clicking",  "mode": "precision",
     "size": "small",  "duration": BENCH_DURATION,
     "why": "precision: เป้าเล็กระยะไกลนิ่ง ๆ = คลิกแม่นเป้าอยู่กับที่ (หมวด Static clicking)"},
    # Tracking
    {"key": "precise",  "label": "Precise",  "cat": "Tracking",  "mode": "tracking",
     "size": "small",  "duration": BENCH_DURATION,
     "why": "tracking เป้าเล็ก: ต้องเกาะติดแม่น ๆ ต่อเนื่อง (หมวด Precise tracking)"},
    {"key": "reactive", "label": "Reactive", "cat": "Tracking",  "mode": "tracking",
     "size": "large",  "duration": BENCH_DURATION,
     "why": "tracking เป้าใหญ่ที่เด้งเปลี่ยนทิศ: เน้นตอบสนองทิศทางที่เปลี่ยน (หมวด Reactive tracking)"},
    # Switching
    {"key": "speed",    "label": "Speed",    "cat": "Switching", "mode": "switch",
     "size": "medium", "duration": BENCH_DURATION,
     "why": "switch: เคลียร์หลายเป้าต่อ wave ให้ไว = สลับเป้าเร็ว (หมวด Speed switching)"},
    {"key": "evasive",  "label": "Evasive",  "cat": "Switching", "mode": "dodge",
     "size": "medium", "duration": BENCH_DURATION,
     "why": "dodge: หลบสกิล+เดินหลบพร้อมสะบัดยิงหัว = เล็งสลับระหว่างเคลื่อนที่หลบ (หมวด Evasive)"},
]


# ════════════════════════════════════════════════════════════════════════
# 2) ตารางแปลง energy + rank  (ค่าทั้งหมด "ประมาณ" ปรับจูนได้ ไม่ใช่ datamined)
# ────────────────────────────────────────────────────────────────────────
# วิธี normalize: ยืม ladder แรงค์ภายในของเกม (scaled_ranks ปรับ mode/size/duration ให้แล้ว)
# มาหา "ตำแหน่งเทียร์" ของคะแนนดิบ (0=Iron I .. 22=Radiant) ซึ่งเทียบข้ามโหมดได้ในตัว
# แล้วแม็ปเทียร์ → energy ด้วยตารางด้านล่าง. ผู้เล่นกลาง ๆ (ราว Gold) → ~Novice III/Intermediate
# ปรับสเกลทั้งระบบได้ที่ ENERGY_BY_TIER (ต้องมีจำนวนเท่าจำนวนเทียร์ใน RANKS = 23) และ ENERGY_RANKS
ENERGY_BY_TIER = [
    90, 120, 150,     # Iron I/II/III
    180, 215, 250,    # Bronze I/II/III
    280, 310, 340,    # Silver I/II/III
    365, 385, 400,    # Gold I/II/III        → Novice สูงสุด ~400
    500, 540, 580,    # Platinum I/II/III    → Intermediate เริ่ม ~500
    620, 660, 695,    # Diamond I/II/III
    730, 770, 805,    # Ascendant I/II/III
    840,              # Immortal             → Intermediate สูงสุด ~840
    1100,             # Radiant              → Advanced (แตะ Radiant ทุกหมวด = เต็มเพดาน)
]

# (min_energy, label, color) เรียงสูง→ต่ำ — Voltaic-style 3 กลุ่ม กลุ่มละ 3 ชั้น
ENERGY_RANKS = [
    (1050, "Advanced III",     "#FFEFB0"),
    (950,  "Advanced II",      "#FFD479"),
    (860,  "Advanced I",       "#FFC04D"),
    (720,  "Intermediate III", "#B7375C"),
    (610,  "Intermediate II",  "#B97FE0"),
    (500,  "Intermediate I",   "#5DBFBA"),
    (360,  "Novice III",       "#D4AF37"),
    (230,  "Novice II",        "#C8C8C8"),
    (100,  "Novice I",         "#9C6B3C"),
    (0,    "Unranked",         "#5C5C5C"),
]

RADAR_MAX_ENERGY = 1100.0   # ใช้ normalize แกนเรดาร์ให้อยู่ 0..1


# ── ฟังก์ชันแปลงล้วน ๆ (ทดสอบได้ ไม่พึ่ง pygame/game) ───────────────────
def _interp(table, pos):
    """interp เชิงเส้นในลิสต์ตามตำแหน่งทศนิยม pos (clamp ปลายทั้งสอง)"""
    n = len(table)
    if pos <= 0:
        return float(table[0])
    if pos >= n - 1:
        return float(table[-1])
    i = int(pos)
    frac = pos - i
    return table[i] * (1.0 - frac) + table[i + 1] * frac


def _tier_pos(score, duration, size, mode):
    """ตำแหน่งทศนิยมของ score ใน ladder แรงค์ภายใน: 0.0=Iron I .. (n-1)=Radiant
    ใช้ scaled_ranks เดิม (ปรับ mode/size/duration แล้ว) → เทียบข้ามโหมดได้"""
    rows = scaled_ranks(duration, size, mode)   # [(thresh,name,color)...] เรียงต่ำ→สูง
    th = [r[0] for r in rows]
    if score <= th[0]:
        return 0.0
    for i in range(len(th) - 1):
        lo, hi = th[i], th[i + 1]
        if score < hi:
            return i + ((score - lo) / (hi - lo) if hi > lo else 0.0)
    return float(len(th) - 1)


def subcat_energy(scn, raw_score):
    """คะแนนดิบของ scenario → energy (int). normalize ผ่านเทียร์แรงค์ภายในแล้วแม็ป ENERGY_BY_TIER"""
    tp = _tier_pos(raw_score, scn["duration"], scn["size"], scn["mode"])
    return int(round(_interp(ENERGY_BY_TIER, tp)))


def overall_energy(energies):
    """พลังรวม = ค่าเฉลี่ย 6 หมวด (เฉลี่ยเพื่อให้สเกลรวมอยู่ช่วงเดียวกับรายหมวด ~100–1200)"""
    es = list(energies)
    return int(round(sum(es) / len(es))) if es else 0


def energy_rank(energy):
    """energy → (label, color_hex) ตามช่วง Voltaic-style"""
    for lo, name, col in ENERGY_RANKS:
        if energy >= lo:
            return name, col
    return ENERGY_RANKS[-1][1], ENERGY_RANKS[-1][2]


# ════════════════════════════════════════════════════════════════════════
# 3-5) Flow: รันทีละ scenario อัตโนมัติ (ใช้วงจร countdown→play→results เดิม) + หน้าสรุป
# ────────────────────────────────────────────────────────────────────────
class BenchmarkFlow:
    """object ที่ run() จะ delegate .update(dt)/.draw() ให้เมื่อ game.flow ถูกเซ็ต
    ออกได้ด้วย ESC (input.py เรียก .on_exit() แล้วเคลียร์ flow). คุมวงจรเองโดยเรียก
    game.start_countdown()/begin_play()/update_play() ตามสถานะ — ไม่แตะ game.py"""

    # round.end_game อ่านธงนี้จาก game.flow: รอบ scenario ไม่ลง history (ไม่ append/ไม่ save) —
    # ผลเก็บเฉพาะ last_entry ให้ _finish_scenario อ่าน ; ออก flow (ESC/กลับเมนู) = flow เป็น None ธงหายเอง
    suppress_history = True

    def __init__(self, game):
        self.g = game
        self.idx = 0
        self.raw = []         # คะแนนดิบต่อ scenario
        self.energies = []    # energy ต่อ scenario
        self.phase = "run"    # "run" = กำลังเล่น scenario | "done" = หน้าสรุป
        self.total = 0
        self.rank_name, self.rank_color = "Unranked", "#5C5C5C"
        self.prev_info = ""
        # เก็บค่าที่ผู้เล่นเลือกไว้ก่อน เพื่อคืนตอนออก (benchmark ไปเปลี่ยน mode/size/duration)
        self._saved_cfg = (game.mode, game.duration, game.size_key,
                           getattr(game, "reaction_variant", "static"),
                           getattr(game, "spray_weapon", "vandal"))
        self._begin(0)

    # ---- วงจรต่อ scenario ----
    def _begin(self, i):
        g = self.g
        scn = SCENARIOS[i]
        g.mode = scn["mode"]
        g.size_key = scn["size"]
        g.duration = scn["duration"]
        g.start_countdown()   # → state="countdown", countdown=3.35, grab_mouse(True)

    def update(self, dt):
        if self.phase == "done":
            return
        g = self.g
        st = g.state
        if st == "countdown":
            # จำลองตรรกะ countdown ของ run() (เสียงบี๊บ + เริ่มเล่นเมื่อหมดเวลา)
            prev = g.countdown
            g.countdown -= dt
            try:
                n_prev = int(math.ceil(max(0, prev - 0.35)))
                n_now = int(math.ceil(max(0, g.countdown - 0.35)))
                if n_now != n_prev:
                    g.play(g.snd_beep_hi if n_now == 0 else g.snd_beep)
                elif prev == 3.35 and getattr(g, "cd_last_beep", 0) == 99:
                    g.cd_last_beep = 3
                    g.play(g.snd_beep)
            except Exception:
                pass
            if g.countdown <= 0:
                g.begin_play()
        elif st == "play":
            g.update_play(dt)         # end_game() ภายในจะตั้ง state="results" + last_entry เมื่อจบ
            if g.state == "results":
                self._finish_scenario()
        elif st == "results":
            # เผื่อหลุดมาถึงตรงนี้ — ปิด scenario ให้เรียบร้อย
            self._finish_scenario()

    def _finish_scenario(self):
        g = self.g
        raw = 0
        le = getattr(g, "last_entry", None)
        if isinstance(le, dict):
            raw = int(le.get("score", 0) or 0)
        self.raw.append(raw)
        self.energies.append(subcat_energy(SCENARIOS[self.idx], raw))
        # รอบ benchmark ไม่ลง history/PB ปกติ (เก็บแยกใน benchmark_history แทน) — end_game ไม่ append ให้เลย
        # (ธง suppress_history) ; ห้ามกลับไปใช้ "append แล้ว pop" — pop หลัง save ถูก merge กู้กลับจากดิสก์
        self.idx += 1
        if self.idx >= len(SCENARIOS):
            self._finish_all()
        else:
            self._begin(self.idx)

    def _finish_all(self):
        g = self.g
        self.phase = "done"
        g.grab_mouse(False)
        # sentinel state: ไม่ตรง handler คีย์อันตราย (R/ESC→pause) แต่ปุ่มยังคลิกได้ + ESC ออก flow ได้
        g.state = "benchmark"
        self.total = overall_energy(self.energies)
        self.rank_name, self.rank_color = energy_rank(self.total)
        # ข้อมูลครั้งก่อน (อ่านก่อน append ของรอบนี้) — ไว้แนะนำ re-benchmark
        bh = g.data.setdefault("benchmark_history", [])
        prev = bh[-1] if bh else None
        if isinstance(prev, dict) and prev.get("t"):
            days = max(0, int((time.time() - prev["t"]) / 86400))
            self.prev_info = "ครั้งก่อน %d วันก่อน · รวม %s (%s)" % (
                days, prev.get("total", "?"), prev.get("rank", "?"))
            if days >= 14:
                self.prev_info += "  — ถึงเวลารีเบนช์มาร์กแล้ว"
        # 5) เก็บผลลง benchmark_history (คีย์ใหม่ ไม่ชนของเดิม) ผ่าน save_data
        rec = {
            "t": time.time(),
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total": self.total,
            "rank": self.rank_name,
            "subcats": [
                {"key": s["key"], "label": s["label"], "cat": s["cat"], "mode": s["mode"],
                 "size": s["size"], "duration": s["duration"], "raw": r, "energy": e}
                for s, r, e in zip(SCENARIOS, self.raw, self.energies)
            ],
        }
        bh.append(rec)
        if len(bh) > 60:
            del bh[:len(bh) - 60]
        save_data(g.data)

    # ---- วาด ----
    def draw(self):
        if self.phase == "done":
            self._draw_summary()
        else:
            self._draw_running()

    def _draw_running(self):
        g = self.g
        if g.state == "play":
            g.draw_world()
            g.draw_crosshair()
            g.draw_effects()
            g.draw_hud()
        else:
            g.draw_countdown()
        self._draw_banner()

    def _draw_banner(self):
        g = self.g
        scn = SCENARIOS[self.idx]
        W = g.W
        # แถบ banner ใช้ซ้ำข้ามเฟรม (สร้างใหม่เฉพาะตอนความกว้างจอเปลี่ยน) — เดิม alloc ทุกเฟรมตลอด benchmark
        bar = getattr(self, "_bar", None)
        if bar is None or bar.get_width() != W:
            bar = pygame.Surface((W, 34), pygame.SRCALPHA)
            bar.fill((8, 20, 28, 180))
            self._bar = bar
        g.screen.blit(bar, (0, 0))
        g.text("BENCHMARK  [%d/%d]" % (self.idx + 1, len(SCENARIOS)), 14, C_PALE_GOLD, (16, 9), bold=True)
        g.text("%s · %s — %s %s %ss" % (scn["cat"], scn["label"], MODE_NAME[scn["mode"]],
                                        SIZE_TH[scn["size"]], scn["duration"]),
               13, C_TEXT, (W // 2, 10), center=True)
        g.text("ESC = ออก", 12, C_DIM, (W - 14, 10), right=True)

    def _draw_summary(self):
        g = self.g
        W, H = g.W, g.H
        g.screen.fill(C_DARKER)
        g.text("VOLTAIC-STYLE BENCHMARK", 15, C_DIM, (W // 2, 24), center=True)
        # การ์ด total energy + rank
        g.text("%d" % self.total, 68, C_RED, (W // 2, 64), center=True, bold=True)
        g.text("ENERGY รวม (เฉลี่ย 6 หมวด)", 15, C_DIM, (W // 2, 110), center=True)
        rcol = hexrgb(self.rank_color)
        nm = self.rank_name
        rnw = g.font(20, True).size(nm)[0]
        em, gpx = 34, 12
        lx = W // 2 - (em + gpx + rnw) // 2
        g.draw_rank_emblem(lx + em // 2, 146, em, nm, rcol)
        g.text(nm, 20, rcol, (lx + em + gpx + rnw // 2, 146), center=True, bold=True)

        # เรดาร์ 6 แกน (ซ้าย) + รายละเอียดต่อหมวด (ขวา) จัดกลุ่มกลางจอ
        radar_w, radar_h, gap, list_w = 380, 300, 46, 360
        group_w = radar_w + gap + list_w
        gx = W // 2 - group_w // 2
        gy = 184
        axes = [(SCENARIOS[i]["label"], max(0.0, min(1.0, self.energies[i] / RADAR_MAX_ENERGY)))
                for i in range(len(SCENARIOS))]
        g.draw_radar(pygame.Rect(gx, gy, radar_w, radar_h), axes, "PROFILE 6 ด้าน")

        lx2 = gx + radar_w + gap
        ly = gy + 16
        for i, s in enumerate(SCENARIOS):
            e = self.energies[i]
            raw = self.raw[i]
            ecol = hexrgb(energy_rank(e)[1])
            g.text("%s" % s["label"], 16, C_TEXT, (lx2, ly), bold=True)
            g.text("%d" % e, 17, ecol, (lx2 + list_w, ly), right=True, bold=True)
            g.text("%s · %s · %ss · ดิบ %s" % (MODE_NAME[s["mode"]], SIZE_TH[s["size"]],
                                              s["duration"], format(raw, ",")),
                   11, C_DIM, (lx2, ly + 21))
            ly += 46

        # ปุ่มเล่นซ้ำ / กลับเมนู
        bw, bh_, by = 210, 46, gy + radar_h + 34
        g.button((W // 2 - bw - 10, by, bw, bh_), "วัดผลใหม่", self._restart, size=15)
        g.button((W // 2 + 10, by, bw, bh_), "กลับเมนู (ESC)", self._exit_to_menu, size=15)
        # 6) แนะนำ re-benchmark
        g.text("แนะนำ: วัดผลซ้ำทุก 2–4 สัปดาห์ เพื่อติดตามพัฒนาการ (แนวทาง Voltaic)",
               12, C_DIM, (W // 2, by + bh_ + 22), center=True)
        if self.prev_info:
            g.text(self.prev_info, 12, C_GOLD, (W // 2, by + bh_ + 42), center=True)

    # ---- ปุ่ม/ออก ----
    def _restart(self):
        self.idx = 0
        self.raw = []
        self.energies = []
        self.prev_info = ""
        self.phase = "run"
        self._begin(0)

    def on_exit(self):
        """เรียกโดย input.py เมื่อกด ESC (และโดย _exit_to_menu) — คืนค่า config ที่ผู้เล่นเลือกไว้"""
        g = self.g
        try:
            (g.mode, g.duration, g.size_key, g.reaction_variant, g.spray_weapon) = self._saved_cfg
        except Exception:
            pass

    def _exit_to_menu(self):
        g = self.g
        self.on_exit()
        g.flow = None
        g.grab_mouse(False)
        g.state = "menu"


# ════════════════════════════════════════════════════════════════════════
# ลงทะเบียนเข้า registry (idempotent) — ถูกเรียกครั้งเดียวตอนสร้าง Game
# ────────────────────────────────────────────────────────────────────────
def _start_benchmark(game):
    game.flow = registry.FLOWS["benchmark"](game)


def register(game):
    """append ปุ่มเมนู + ลง FLOWS แบบกันซ้ำ (มีหลาย Game instance ในโปรเซสเดียวได้ตอนเทส)"""
    registry.FLOWS["benchmark"] = lambda g: BenchmarkFlow(g)
    for it in registry.MENU_EXTRAS:
        if it.get("_id") == "benchmark":
            return
    registry.MENU_EXTRAS.append({"label": "BENCHMARK", "on_click": _start_benchmark, "_id": "benchmark"})


# ════════════════════════════════════════════════════════════════════════
# เทสฟังก์ชันแปลง energy — เสียบเข้า `--selftest` โดยไม่ต้องแก้ aim/selftest.py
# (selftest.py ไม่มี hook เรียกเทสระดับโมดูล จึง gate ด้วย sys.argv ตอน import แทน)
# ────────────────────────────────────────────────────────────────────────
def _energy_selftests():
    errs = []
    scn = SCENARIOS[0]                       # flick/medium/30 เป็นฐานคำนวณ threshold จริง
    rows = scaled_ranks(scn["duration"], scn["size"], scn["mode"])

    def thr(name):
        for t, n, c in rows:
            if n == name:
                return t
        return None

    # 1) energy_rank อยู่กลุ่มที่ถูก
    for e, grp in [(50, "Unranked"), (360, "Novice"), (560, "Intermediate"), (1100, "Advanced")]:
        got = energy_rank(e)[0]
        if not got.startswith(grp):
            errs.append("energy_rank(%d)=%s ไม่อยู่กลุ่ม %s" % (e, got, grp))
    # 2) subcat_energy เพิ่มตามคะแนน (monotonic)
    e_lo = subcat_energy(scn, 0)
    e_mid = subcat_energy(scn, thr("Gold I") or 5000)
    e_hi = subcat_energy(scn, (thr("Radiant") or 20000) * 3)
    if not (e_lo < e_mid < e_hi):
        errs.append("subcat_energy ไม่ monotonic: %d/%d/%d" % (e_lo, e_mid, e_hi))
    # 3) ผู้เล่นระดับ Gold (กลาง ๆ) → energy ย่าน Novice สูง/Intermediate ต่ำ
    if not (300 <= e_mid <= 520):
        errs.append("Gold→energy=%d หลุดย่านคาด (~300–520)" % e_mid)
    if not energy_rank(e_mid)[0].startswith(("Novice", "Intermediate")):
        errs.append("Gold→rank=%s ควรเป็น Novice/Intermediate" % energy_rank(e_mid)[0])
    # 4) overall = ค่าเฉลี่ย
    if overall_energy([100, 200, 300, 400, 500, 600]) != 350:
        errs.append("overall_energy เฉลี่ยผิด: %d" % overall_energy([100, 200, 300, 400, 500, 600]))
    # 5) แตะ Radiant ทุกหมวด → Advanced (เพดานบน)
    radE = subcat_energy(scn, (thr("Radiant") or 20000) * 3)
    if not energy_rank(overall_energy([radE] * 6))[0].startswith("Advanced"):
        errs.append("Radiant ทุกหมวด → ควรได้ Advanced")
    # 6) ตาราง energy: จำนวนเทียร์ตรง + เรียงขึ้นไม่ลด
    if len(ENERGY_BY_TIER) != len(rows):
        errs.append("ENERGY_BY_TIER=%d != tiers=%d" % (len(ENERGY_BY_TIER), len(rows)))
    if any(ENERGY_BY_TIER[i] > ENERGY_BY_TIER[i + 1] for i in range(len(ENERGY_BY_TIER) - 1)):
        errs.append("ENERGY_BY_TIER ไม่เรียงขึ้น")
    return errs


def selftest(game=None):
    """คืน list[str] ของ error (ว่าง=ผ่าน) — ตามแบบแผนของ aim/export.py เผื่อมี hook ในอนาคต"""
    return list(_energy_selftests())


import sys as _sys
if "--selftest" in _sys.argv:
    try:
        _err = _energy_selftests()
    except Exception as _ex:                  # noqa: BLE001
        _err = ["benchmark energy selftest crashed: %r" % (_ex,)]
    if _err:
        print("BENCHMARK ENERGY SELFTEST FAIL")
        for _x in _err:
            print(" -", _x)
        _sys.exit(1)
    print("BENCHMARK ENERGY SELFTEST OK (%d subcats)" % len(SCENARIOS))

