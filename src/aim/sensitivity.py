# -*- coding: utf-8 -*-
"""[Module 4] ตัวแปลง sensitivity ข้ามเกม (เจ้าของไฟล์: aim/sensitivity.py)

ให้ผู้เล่นใส่ค่า sens จากเกมอื่น (CS2 / Apex / Overwatch / Valorant) แล้วได้ sens ที่
"ฟีลเท่ากัน" สำหรับ VAL//AIM (yaw 0.07 องศา/count) พร้อมโชว์ cm/360 — แนวเดียวกับ
Sensitivity Matcher ของ Aim Lab / KovaaK's

รูปแบบ UI: หน้าจอแยกเต็มจอผ่านตะเข็บ FLOWS + ปุ่ม MENU_EXTRAS "SENS CONVERT" ในเมนูหลัก
(เลือกแบบนี้เพราะคอลัมน์ SETTINGS_PANELS ถูก Module 2 ใช้อยู่แล้ว วางสองแผงซ้อนกันพื้นที่ไม่พอ)
เชื่อมต่อผ่าน register(game) เท่านั้น — ไม่แตะ game.py/ไฟล์อื่น (เดินตามแบบ aim/benchmark.py)

คณิตหลัก (game-agnostic = cm/360):
    counts_per_360 = 360 / (yaw_deg_per_count * game_sens)
    cm_per_360     = counts_per_360 / DPI * 2.54
แปลงข้ามเกม = จับ cm/360 ให้เท่ากันที่ DPI เดียวกัน
  → ที่ DPI เดียวกัน การจับ cm/360 เท่ากัน ก็คือจับ counts/360 เท่ากัน
    ดังนั้น our_sens = src_sens * yaw_src / yaw_our  (ไม่ขึ้นกับ DPI; DPI ใช้แค่โชว์ cm/360)

สัญญา (contract) ที่ยึด (อ่านจากของจริง registry.py / input.py / benchmark.py):
  - registry.MENU_EXTRAS.append({"label","on_click":fn(game),"_id"})  → ปุ่มในเมนูหลัก
  - registry.FLOWS[name] = factory(game) -> obj(.update(dt), .draw(), .on_exit() ไม่บังคับ)
  - run() delegate update/draw ให้ game.flow ; input.py: ESC ระหว่าง flow → on_exit()+flow=None+menu
  - ตั้ง game.state เป็น sentinel (ไม่ใช่ "play") → คลิกวิ่งเข้า zones ของปุ่ม ไม่ใช่ยิง
  - game.text(s,size,color,pos,center=,bold=,right=) / game.button(rect,label,fn,active=,size=)
  - game.S["sens"], game.S["dpi"] ; data.save_data(game.data) ; game.ui_scale()

ข้อจำกัด "ห้ามผิด": ไม่ใช้ numpy, ฟอนต์ไทยผ่าน game.text, ไม่มี emoji, our yaw = 0.07
ทดสอบคณิตเดี่ยว ๆ:  python -m aim.sensitivity
"""

import pygame

from .config import C_RED, C_TEXT, C_DIM, C_GOLD, C_GREEN, C_PANEL, C_BORDER, C_DARKER
from .data import save_data
from . import registry


# ===========================================================================
# 1) ตารางค่า yaw (องศาต่อ count ที่ sens = 1) + ฟังก์ชันคณิต  (ส่วนนี้ไม่พึ่ง pygame)
# ===========================================================================
GAME_YAW = {
    "valorant":  0.07,     # = VAL_DEG_PER_COUNT (เกมเรา)
    "cs2":       0.022,    # Source engine
    "csgo":      0.022,    # alias ของ Source
    "source":    0.022,
    "apex":      0.022,    # Apex ใช้ Source-based yaw เดียวกัน
    "overwatch": 0.0066,   # OW / OW2
    "ow2":       0.0066,
}

OUR_GAME = "valorant"
OUR_YAW = GAME_YAW[OUR_GAME]   # 0.07

GAME_ORDER = ["valorant", "cs2", "apex", "overwatch"]
GAME_LABEL = {"valorant": "Valorant", "cs2": "CS2", "apex": "Apex", "overwatch": "Overwatch"}


def _counts_per_360(yaw, sens):
    denom = yaw * sens
    if denom <= 0:
        return float("inf")
    return 360.0 / denom


def to_cm360(game_key, sens, dpi):
    """ระยะลากเมาส์ (ซม.) ต่อการหมุน 360 องศา ของเกม game_key ที่ sens/dpi นั้น"""
    yaw = GAME_YAW[game_key]
    if dpi <= 0:
        return float("inf")
    return _counts_per_360(yaw, sens) / dpi * 2.54


def from_cm360(cm360, dpi, game_key=OUR_GAME):
    """ย้อนกลับ: cm/360 + dpi -> sens ของเกม game_key ที่ให้ cm/360 นั้น"""
    yaw = GAME_YAW[game_key]
    if cm360 <= 0 or dpi <= 0 or yaw <= 0:
        return 0.0
    counts_per_360 = cm360 * dpi / 2.54
    if counts_per_360 <= 0:
        return 0.0
    return 360.0 / (yaw * counts_per_360)


def convert(src_game, src_sens, dpi):
    """ใส่ (เกมต้นทาง, sens ต้นทาง, DPI) -> sens ของ VAL//AIM ที่ฟีลเท่ากัน"""
    cm = to_cm360(src_game, src_sens, dpi)
    return from_cm360(cm, dpi, OUR_GAME)


def current_cm360(game):
    """cm/360 ปัจจุบันของผู้เล่น อ่านจาก game.S (None ถ้าค่าผิดปกติ)"""
    try:
        sens = float(game.S.get("sens"))
        dpi = float(game.S.get("dpi"))
    except Exception:
        return None
    if sens <= 0 or dpi <= 0:
        return None
    return to_cm360(OUR_GAME, sens, dpi)


def _fmt(v, n):
    try:
        return "%.*f" % (n, float(v))
    except Exception:
        return str(v)


# ===========================================================================
# 2) Flow: หน้าจอตัวแปลงเต็มจอ (run() delegate .update/.draw มาที่นี่เมื่อ game.flow ถูกเซ็ต)
# ===========================================================================
class SensConvFlow:
    """ออกได้ด้วย ESC (input.py เรียก .on_exit() แล้วเคลียร์ flow) หรือปุ่ม 'กลับเมนู'
    state ตั้งเป็น sentinel 'sensconv' → คลิกวิ่งเข้า zones ของปุ่ม (ไม่ใช่ยิง), คีย์อื่นถูกเมิน"""

    def __init__(self, game):
        self.g = game
        self.game_key = "cs2"
        self.sens = 0.80
        try:
            self.dpi = int(float(game.S.get("dpi", 800)))
        except Exception:
            self.dpi = 800
        self.applied = False
        game.state = "sensconv"      # sentinel (ไม่ใช่ "play")
        if not getattr(game, "headless", False):
            try:
                game.grab_mouse(False)   # หน้าจอแบบเมนู → ให้เห็น cursor
            except Exception:
                pass

    def update(self, dt):
        pass

    # ---- mutators (game.button เรียก fn() ไม่ส่งอาร์กิวเมนต์) ----
    def _set_game(self, k):
        self.game_key = k
        self.applied = False

    def _bump_sens(self, d):
        self.sens = max(0.01, round(self.sens + d, 3))
        self.applied = False

    def _bump_dpi(self, d):
        self.dpi = int(max(100, min(32000, self.dpi + d)))
        self.applied = False

    def _set_dpi(self, v):
        self.dpi = int(v)
        self.applied = False

    def _apply(self):
        our = convert(self.game_key, self.sens, self.dpi)
        if our <= 0:
            return
        try:
            self.g.S["sens"] = round(our, 3)     # ละเอียด 3 ตำแหน่ง เท่ากับ commit_sens เดิม
            self.g.S["dpi"] = int(self.dpi)
        except Exception:
            return
        try:
            save_data(self.g.data)
        except Exception:
            pass
        self.applied = True

    def on_exit(self):
        # ไม่มี state ของเกมที่ต้องคืน (ตัวแปลงไม่แตะ mode/size) — no-op
        pass

    def _to_menu(self):
        g = self.g
        g.flow = None
        try:
            g.grab_mouse(False)
        except Exception:
            pass
        g.state = "menu"

    # ---- วาด ----
    def _stepper(self, g, x0, colw, y, sc, label, value_str, steps):
        """แถวปรับค่า: label / [-คู่ซ้าย] [กล่องค่ากลาง] [+คู่ขวา] — คืน y ถัดไป
        steps = [(lbl,fn) x4] (2 ตัวแรก=ลด, 2 ตัวหลัง=เพิ่ม)"""
        def S(v):
            return int(round(v * sc))
        g.text(label, S(14), C_RED, (x0, y), bold=True)
        y += S(26)
        bh = S(40)
        bw = S(88)
        gap = S(10)
        (l1, f1), (l2, f2), (r1, fr1), (r2, fr2) = steps
        g.button((x0, y, bw, bh), l1, f1, size=S(14))
        g.button((x0 + bw + gap, y, bw, bh), l2, f2, size=S(14))
        g.button((x0 + colw - 2 * bw - gap, y, bw, bh), r1, fr1, size=S(14))
        g.button((x0 + colw - bw, y, bw, bh), r2, fr2, size=S(14))
        vx0 = x0 + 2 * bw + 2 * gap
        vx1 = x0 + colw - 2 * bw - 2 * gap
        vrect = pygame.Rect(vx0, y, max(S(60), vx1 - vx0), bh)
        pygame.draw.rect(g.screen, C_PANEL, vrect, border_radius=S(6))
        pygame.draw.rect(g.screen, C_BORDER, vrect, 1, border_radius=S(6))
        g.text(value_str, S(22), C_GOLD, vrect.center, center=True, bold=True)
        return y + bh

    def draw(self):
        g = self.g
        W, H = g.W, g.H
        sc = g.ui_scale()

        def S(v):
            return int(round(v * sc))

        g.screen.fill(C_DARKER)
        cx = W // 2
        g.text("ตัวแปลงความไว — SENSITIVITY CONVERTER", S(26), C_TEXT, (cx, S(38)),
               center=True, bold=True)
        g.text("ใส่ค่า sens จากเกมอื่น เพื่อฝึกบนความไวที่ฟีลเท่ากันใน VAL//AIM (0.07°/count)",
               S(13), C_DIM, (cx, S(72)), center=True)

        colw = S(760)
        x0 = cx - colw // 2
        y = S(112)

        # ── เกมต้นทาง ──
        g.text("เกมต้นทาง", S(14), C_RED, (x0, y), bold=True)
        y += S(26)
        n = len(GAME_ORDER)
        gap = S(10)
        bw = (colw - gap * (n - 1)) // n
        bh = S(42)
        bx = x0
        for k in GAME_ORDER:
            g.button((bx, y, bw, bh), GAME_LABEL[k],
                     (lambda kk=k: self._set_game(kk)), active=(self.game_key == k), size=S(15))
            bx += bw + gap
        y += bh + S(22)

        # ── sens ──
        y = self._stepper(g, x0, colw, y, sc, "ความไว (sens) ของเกมต้นทาง", _fmt(self.sens, 3), [
            ("-0.1", lambda: self._bump_sens(-0.1)), ("-0.01", lambda: self._bump_sens(-0.01)),
            ("+0.01", lambda: self._bump_sens(0.01)), ("+0.1", lambda: self._bump_sens(0.1)),
        ])
        y += S(16)

        # ── DPI + presets ──
        y = self._stepper(g, x0, colw, y, sc, "DPI เมาส์ (ใช้ร่วมกันทั้งสองเกม)", str(int(self.dpi)), [
            ("-100", lambda: self._bump_dpi(-100)), ("-50", lambda: self._bump_dpi(-50)),
            ("+50", lambda: self._bump_dpi(50)), ("+100", lambda: self._bump_dpi(100)),
        ])
        y += S(10)
        g.text("ตั้งเร็ว", S(12), C_DIM, (x0, y + S(6)))
        px = x0 + S(72)
        for d in (400, 800, 1600, 3200):
            g.button((px, y, S(92), S(28)), str(d),
                     (lambda dd=d: self._set_dpi(dd)), active=(int(self.dpi) == d), size=S(12))
            px += S(100)
        y += S(28) + S(22)

        # ── การ์ดผลลัพธ์ ──
        our = convert(self.game_key, self.sens, self.dpi)
        cm = to_cm360(self.game_key, self.sens, self.dpi)
        card = pygame.Rect(x0, y, colw, S(94))
        pygame.draw.rect(g.screen, C_PANEL, card, border_radius=S(8))
        pygame.draw.rect(g.screen, C_RED, card, 2, border_radius=S(8))
        g.text("ค่าที่จะใช้ใน VAL//AIM", S(13), C_DIM, (card.x + S(22), card.y + S(14)))
        nr = g.text(_fmt(our, 3), S(40), C_GREEN, (card.x + S(22), card.y + S(36)), bold=True)
        g.text("SENS", S(14), C_DIM, (nr.right + S(12), card.y + S(58)))
        g.text("cm / 360°", S(13), C_DIM, (card.right - S(22), card.y + S(14)), right=True)
        g.text("%s ซม." % _fmt(cm, 2), S(34), C_TEXT, (card.right - S(22), card.y + S(40)),
               right=True, bold=True)
        y += S(94) + S(16)

        # ── cm/360 ปัจจุบันของผู้เล่น ──
        cur = current_cm360(g)
        if cur is not None:
            try:
                cs = _fmt(g.S.get("sens"), 3)
                cd = int(float(g.S.get("dpi")))
            except Exception:
                cs, cd = "?", 0
            g.text("ค่าปัจจุบันของคุณ: sens %s · DPI %d · %s cm/360" % (cs, cd, _fmt(cur, 2)),
                   S(13), C_DIM, (cx, y), center=True)
        y += S(30)

        # ── ปุ่ม ใช้ค่านี้ / กลับเมนู ──
        bw2 = S(220)
        bh2 = S(46)
        half_gap = S(10)
        g.button((cx - bw2 - half_gap, y, bw2, bh2), "ใช้ค่านี้", self._apply,
                 active=self.applied, size=S(16))
        g.button((cx + half_gap, y, bw2, bh2), "กลับเมนู (ESC)", self._to_menu, size=S(16))
        if self.applied:
            g.text("บันทึกแล้ว — ตั้งความไว + DPI ให้เกมและเซฟเรียบร้อย", S(13), C_GREEN,
                   (cx, y + bh2 + S(16)), center=True)
        else:
            g.text("กด \"ใช้ค่านี้\" เพื่อตั้งความไว + DPI ให้ VAL//AIM แล้วเซฟอัตโนมัติ", S(12), C_DIM,
                   (cx, y + bh2 + S(16)), center=True)


# ===========================================================================
# 3) register — ปุ่มเมนู + FLOWS (idempotent) ; Game.__init__ เรียกให้อัตโนมัติ
# ===========================================================================
def _start_sensconv(game):
    game.flow = registry.FLOWS["sensconv"](game)


def register(game):
    registry.FLOWS["sensconv"] = lambda g: SensConvFlow(g)
    for it in registry.MENU_EXTRAS:
        if it.get("_id") == "sensconv":
            return
    registry.MENU_EXTRAS.append({"label": "SENS CONVERT", "on_click": _start_sensconv, "_id": "sensconv"})


# ===========================================================================
# 4) unit test การแปลง — คืน list[str] (ว่าง = ผ่าน) ; คอนเวนชันเดียวกับ export.selftest(g)
#    รันใน --selftest ผ่าน argv-gate ท้ายไฟล์ (แบบเดียวกับ benchmark.py)
#    รันเดี่ยว ๆ:  python -m aim.sensitivity
# ===========================================================================
def selftest(game=None):
    """เทสคณิตการแปลง sens — คืน list ของข้อความ error (ว่าง = ผ่าน). game ไม่จำเป็น (คณิตล้วน)"""
    errs = []

    def approx(a, b, tol_pct=0.5):
        if b == 0:
            return abs(a) < 1e-9
        return abs(a - b) / abs(b) * 100.0 <= tol_pct

    def chk(cond, msg):
        if not cond:
            errs.append("sensitivity: " + msg)

    cm = to_cm360("cs2", 0.8, 800)
    chk(approx(cm, 64.94, 0.2), "CS2 0.8@800 cm/360=%.4f (คาด ~64.94)" % cm)

    our = convert("cs2", 0.8, 800)
    chk(approx(to_cm360("valorant", our, 800), cm, 0.5), "round-trip cm/360 เพี้ยน")

    for gk, sens, dpi in [("apex", 2.0, 1600), ("overwatch", 5.5, 800),
                          ("cs2", 1.25, 400), ("valorant", 0.40, 800)]:
        back = from_cm360(to_cm360(gk, sens, dpi), dpi, gk)
        chk(approx(back, sens, 0.01), "inverse %s: %.5f != %.5f" % (gk, back, sens))

    chk(approx(convert("valorant", 0.40, 800), 0.40, 0.001), "identity valorant ผิด")

    ratio = convert("cs2", 1.0, 800)
    chk(approx(ratio, 0.022 / 0.07, 0.001), "ratio CS2->VAL=%.5f" % ratio)
    chk(approx(1.0 / ratio, 3.1818, 0.1) if ratio else False, "ตัวหาร CS2->VAL ควร ~3.18")

    chk(approx(convert("cs2", 0.8, 400), convert("cs2", 0.8, 1600), 0.0001),
        "convert ไม่ควรขึ้นกับ DPI")

    chk(approx(to_cm360("valorant", 0.40, 800), 13062.857 / (800 * 0.40), 0.01),
        "ไม่ตรงกับสูตร cm/360 เดิมของแอป")

    chk(to_cm360("csgo", 1.0, 800) == to_cm360("cs2", 1.0, 800), "alias csgo ผิด")
    chk(to_cm360("ow2", 3.0, 800) == to_cm360("overwatch", 3.0, 800), "alias ow2 ผิด")

    return errs


if __name__ == "__main__":
    import sys
    _e = selftest()
    print("SENSITIVITY SELFTEST", "OK" if not _e else "FAIL",
          "(CS2 0.8@800 = %.2f cm/360 -> VAL sens %.3f)"
          % (to_cm360("cs2", 0.8, 800), convert("cs2", 0.8, 800)))
    for _x in _e:
        print(" -", _x)
    sys.exit(1 if _e else 0)


# argv-gate: รันตอนถูก import ระหว่าง `aim_trainer.py --selftest` (แบบเดียวกับ benchmark.py —
# เทสเป็นคณิตล้วน ไม่ต้องมี Game/ไฟล์ จึงรันตอน import ได้ปลอดภัย)
import sys as _sys
if "--selftest" in _sys.argv:
    try:
        _err = selftest()
    except Exception as _ex:                  # noqa: BLE001
        _err = ["sensitivity selftest crashed: %r" % (_ex,)]
    if _err:
        print("SENSITIVITY SELFTEST FAIL")
        for _x in _err:
            print(" -", _x)
        _sys.exit(1)
    print("SENSITIVITY SELFTEST OK")

