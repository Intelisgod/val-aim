# -*- coding: utf-8 -*-
"""ลีดเดอร์บอร์ดออนไลน์ — ส่ง PB ทุก config ขึ้น Google Sheet ของเจ้าของห้อง (online/Code.gs) แล้วดึงของเพื่อนกลับมา

- เข้าห้องด้วย "โค้ดห้อง" (valaim-room:…) = URL ของ Apps Script + รหัสห้อง ; เก็บใน data/online.json แยกจาก
  aim_trainer_data.json (ไฟล์ประวัติคือของมีค่า — โมดูลนี้ไม่เขียนไฟล์นั้นเลย)
- ส่ง = PB ของทุก config จาก history (กติกาเดียวกับ round.same_config / is_personal_best) ; server เก็บค่าที่ดีกว่าเสมอ
- เน็ตทั้งหมดวิ่งใน thread แยก timeout สั้น ล้ม = แค่ขึ้นสถานะ ไม่กระทบเกม ; headless (selftest/เทส) ไม่ยิงเน็ต
- แถวของเพื่อน (rows) อยู่ในหน่วยความจำเท่านั้น — TOP 5 บนเมนูรวมกับ leaderboard ในเครื่องตอนวาด
"""

import os
import json
import time
import base64
import secrets
import threading
import webbrowser
import urllib.request
import urllib.error
from urllib.parse import quote

import pygame

from .config import MODE_REV, SPRAY_SCORE_REV, C_RED, C_DIM, C_TEXT, C_GOLD, C_GREEN, mode_current
from .data import DATA_FILE
from . import registry

ONLINE_FILE = os.path.join(os.path.dirname(DATA_FILE), "online.json")
JOIN_PREFIX = "valaim-room:"
URL_PREFIX = "https://script.google.com/"
TIMEOUT = 15


# ───────────────────────── โค้ดห้อง ─────────────────────────
def make_join(url, room):
    raw = json.dumps({"u": url, "r": room}, separators=(",", ":")).encode("utf-8")
    return JOIN_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_join(text):
    """หาโค้ดห้องในข้อความ (วางทั้งข้อความแชตมาก็ได้) — คืน (url, room) หรือ None"""
    if not isinstance(text, str) or JOIN_PREFIX not in text:
        return None
    tok = ""
    for c in text.split(JOIN_PREFIX, 1)[1]:
        if not (c.isascii() and (c.isalnum() or c in "-_")):
            break
        tok += c
    try:
        d = json.loads(base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    url, room = d.get("u"), d.get("r")
    if not (isinstance(url, str) and url.startswith(URL_PREFIX) and isinstance(room, str) and room.strip()):
        return None
    return url, room


def load_cfg():
    try:
        with open(ONLINE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("url"), str) and isinstance(d.get("room"), str):
            return d
    except Exception:
        pass
    return {}


def save_cfg(cfg):
    os.makedirs(os.path.dirname(ONLINE_FILE), exist_ok=True)
    tmp = ONLINE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    os.replace(tmp, ONLINE_FILE)


# ───────────────────────── PB ต่อ config ─────────────────────────
def pb_fields(e):
    """ฟิลด์ config ของ entry ตัดให้เหลือเฉพาะที่ same_config ใช้ (ที่เหลือเป็นค่าว่าง) — คีย์เดียวกันฝั่ง server
    reaction = variant · sniper = ไม่ผูก · spray = ปืน + เวลา · gun = ปืน + ดริล + เวลา · ที่เหลือ = เวลา + ขนาด"""
    md = e.get("mode")
    f = {"mode": md, "variant": "", "drill": "", "duration": 0, "size": ""}
    if md == "reaction":
        f["variant"] = e.get("variant") or "static"
    elif md == "spray":
        f["variant"] = e.get("variant") or "vandal"
        f["duration"] = int(e.get("duration") or 0)
    elif md == "gun":
        f["variant"] = e.get("variant") or ""
        f["drill"] = e.get("drill") or "duel"
        f["duration"] = int(e.get("duration") or 0)
    elif md != "sniper":
        f["duration"] = int(e.get("duration") or 0)
        f["size"] = e.get("size") or ""
    # rev = กติการุ่นของโหมด (spray ดู srev เหมือน mode_current) — rev ต่างกัน = คนละตาราง
    f["rev"] = int(e.get("srev", 1) if md == "spray" else e.get("mrev", 1))
    return f


def cfg_key(e):
    f = pb_fields(e)
    return (f["mode"], f["variant"], f["drill"], f["duration"], f["size"], f["rev"])


def better(a, b):
    """กติกาเดียวกับ is_personal_best: reaction = rt ต่ำกว่า (> 0) ; ที่เหลือ = score สูงกว่า"""
    if a.get("mode") == "reaction":
        return a.get("rt", 0) > 0 and not (0 < b.get("rt", 0) <= a.get("rt", 0))
    return a.get("score", 0) > b.get("score", 0)


def collect_pbs(history):
    best = {}
    for e in history:
        if not isinstance(e, dict) or not mode_current(e):
            continue
        if e.get("mode") == "reaction" and not e.get("rt", 0) > 0:
            continue
        if e.get("mode") != "reaction" and not e.get("score", 0) > 0:
            continue
        k = cfg_key(e)
        if k not in best or better(e, best[k]):
            best[k] = e
    out = []
    for e in best.values():
        p = pb_fields(e)
        p.update(score=int(e.get("score", 0)), acc=int(e.get("acc", 0)), rt=int(e.get("rt", 0)),
                 at=int(e.get("at") or 0))
        out.append(p)
    return out


def row_entry(r):
    """แถวจาก server → entry เทียม ที่ส่งเข้า same_config / TOP 5 ได้ตรง ๆ"""
    e = {k: r.get(k) for k in ("mode", "variant", "drill", "duration", "size", "score", "acc", "rt", "at")}
    e["mrev"] = e["srev"] = int(r.get("rev") or 1)
    e["name"] = str(r.get("name") or "")[:14]
    e["pid"] = r.get("pid")
    e["online"] = True
    return e


# ───────────────────────── sync (thread) ─────────────────────────
class Sync:
    def __init__(self):
        self.cfg = load_cfg()
        self.state = "off" if not self.cfg else "idle"   # off / idle / busy / ok / error
        self.msg = ""
        self.rows = []            # entry เทียมจาก row_entry
        self.people = 0
        self.last_ok = 0.0
        self._pending = None
        self._lock = threading.Lock()

    def joined(self):
        return bool(self.cfg.get("url") and self.cfg.get("room"))

    def _post(self, body):
        req = urllib.request.Request(self.cfg["url"], data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        # Apps Script ตอบ 302 ไป googleusercontent — urllib ตามเป็น GET ให้เอง (ผลอยู่ที่ปลายทาง)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        if not isinstance(d, dict):
            raise ValueError("bad reply")
        if not d.get("ok"):
            raise PermissionError(d.get("error") or "rejected")
        return d

    def request(self, game, submit=True):
        """เริ่ม sync เบื้องหลัง (ส่ง PB แล้วดึงตาราง) — กำลังทำอยู่ = จำไว้ทำต่อรอบหน้า"""
        if game is None or getattr(game, "headless", False) or not self.joined():
            return False
        body = None
        if submit:
            body = {"action": "submit", "room": self.cfg["room"], "pid": self.cfg["pid"],
                    "name": (game.data.get("name") or "").strip(),
                    "pbs": collect_pbs(game.data.get("history", []))}
        with self._lock:
            if self.state == "busy":
                self._pending = body if body is not None else (self._pending or False)
                return True
            self.state, self.msg = "busy", ""
        threading.Thread(target=self._run, args=(body,), daemon=True).start()
        return True

    def _run(self, body):
        while True:
            try:
                if body:
                    self._post(body)
                d = self._post({"action": "board", "room": self.cfg["room"]})
                rows = [row_entry(r) for r in d.get("rows", []) if isinstance(r, dict)]
                self.rows = rows
                self.people = len({r["pid"] for r in rows})
                self.last_ok = time.time()
                st, msg = "ok", ""
            except PermissionError as ex:
                st, msg = "error", "รหัสห้องไม่ถูก — ขอโค้ดห้องใหม่จากเจ้าของห้อง" if str(ex) == "room" else f"server ไม่รับ ({ex})"
            except (urllib.error.URLError, OSError, TimeoutError):
                st, msg = "error", "ต่อเน็ตไม่ได้ — จะลองใหม่รอบหน้า"
            except Exception as ex:
                st, msg = "error", f"sync ไม่สำเร็จ ({type(ex).__name__})"
            with self._lock:
                if self._pending is None:
                    self.state, self.msg = st, msg
                    return
                body, self._pending = (self._pending or None), None

    def join(self, url, room):
        cfg = {"url": url, "room": room, "pid": self.cfg.get("pid") or secrets.token_hex(5)}
        save_cfg(cfg)
        self.cfg = cfg
        self.rows, self.people = [], 0
        self.state, self.msg = "idle", ""

    def leave(self):
        cfg = {"pid": self.cfg["pid"]} if self.cfg.get("pid") else {}
        save_cfg(cfg)            # คง pid ไว้ — กลับเข้าห้องเดิมแล้วแถวเดิมเป็นของเราต่อ
        self.cfg = cfg
        self.rows, self.people = [], 0
        self.state, self.msg = "off", ""

    def web_url(self):
        return self.cfg["url"] + "#room=" + quote(self.cfg["room"], safe="")


SYNC = Sync()


def rows_for(game):
    """แถวของห้องที่ config ตรงกับที่เลือกอยู่ (สำหรับ TOP 5) — ไม่ได้เข้าห้อง = []"""
    if not SYNC.joined():
        return []
    return [e for e in SYNC.rows if game.same_config(e)]


def after_round(game):
    """เรียกหลังบันทึกรอบลง history — ส่งเฉพาะรอบที่เป็น PB (ของเก่าส่งไปแล้วตอนเปิดเกม/SYNC)"""
    if getattr(game, "res_pb", False):
        SYNC.request(game)


# ───────────────────────── clipboard / UI ─────────────────────────
def _clip_get():
    try:
        return pygame.scrap.get_text() or ""
    except Exception:
        return ""


def _clip_put(s):
    try:
        pygame.scrap.put_text(s)
        return True
    except Exception:
        return False


def paste_join(game):
    got = parse_join(_clip_get())
    if not got:
        SYNC.state, SYNC.msg = ("error" if SYNC.joined() else "off"), "คลิปบอร์ดไม่มีโค้ดห้อง — คัดลอกโค้ด valaim-room:… ก่อน"
        return False
    SYNC.join(*got)
    SYNC.request(game)
    return True


def _status_line():
    if SYNC.state == "busy":
        return "กำลัง sync…", C_GOLD
    if SYNC.state == "error":
        return SYNC.msg, C_RED
    if SYNC.state == "ok":
        return f"ออนไลน์ · {SYNC.people} คนในห้อง · sync {time.strftime('%H:%M', time.localtime(SYNC.last_ok))}", C_GREEN
    return "เข้าห้องแล้ว — กด SYNC", C_DIM


def _panel(game, x, y, w):
    s = game.ui_scale()

    def S(v):
        return int(round(v * s))

    y0 = y
    game.text("ONLINE LEADERBOARD", S(13), C_RED, (x, y), bold=True)
    y += S(22)
    bh, gap = S(26), S(6)
    if not SYNC.joined():
        game.text(game.fit_text("แข่ง PB กับเพื่อน: คัดลอกโค้ดห้องจากเจ้าของห้อง แล้วกดวาง", S(11), w), S(11), C_DIM, (x, y))
        y += S(20)
        game.button((x, y, S(200), bh), "วางโค้ดห้อง (Ctrl+V)", lambda: paste_join(game), size=S(11))
        y += bh + S(6)
        if SYNC.msg:
            game.text(game.fit_text(SYNC.msg, S(10), w), S(10), C_RED, (x, y))
            y += S(16)
        return y - y0
    line, col = _status_line()
    game.text(game.fit_text(line, S(11), w), S(11), col, (x, y))
    y += S(20)
    acts = [("SYNC", lambda: SYNC.request(game)),
            ("เปิดเว็บ", lambda: webbrowser.open(SYNC.web_url())),
            ("ชวนเพื่อน", lambda: _clip_put(make_join(SYNC.cfg["url"], SYNC.cfg["room"]))
                and setattr(SYNC, "msg", "คัดลอกโค้ดห้องแล้ว — ส่งทาง LINE ให้เพื่อนวางในเกม")),
            ("ออกห้อง", SYNC.leave)]
    bw = (w - gap * (len(acts) - 1)) // len(acts)
    for i, (label, fn) in enumerate(acts):
        game.button((x + i * (bw + gap), y, bw, bh), label, fn, size=S(11), danger=(label == "ออกห้อง"))
    y += bh + S(6)
    if not (game.data.get("name") or "").strip():
        game.text(game.fit_text("ตั้งชื่อผู้เล่นในเมนูก่อน — ไม่งั้นเพื่อนเห็นเป็น P-xxxx", S(10), w), S(10), C_GOLD, (x, y))
        y += S(16)
    elif SYNC.msg and SYNC.state != "error":
        game.text(game.fit_text(SYNC.msg, S(10), w), S(10), C_DIM, (x, y))
        y += S(16)
    return y - y0


def _menu_click(game):
    if SYNC.joined():
        webbrowser.open(SYNC.web_url())
    else:
        game.state = "settings"        # แผง ONLINE LEADERBOARD อยู่ในหน้า settings (ทางเดียวกับปุ่ม SETTINGS)


def register(game):
    """เรียกจาก Game.__init__ — ลงแผง settings + ปุ่มเมนูแบบ idempotent แล้ว sync ครั้งแรก (PB ที่ทำตอนออฟไลน์)"""
    if _panel not in registry.SETTINGS_PANELS_LEFT:
        registry.SETTINGS_PANELS_LEFT.append(_panel)
    if not any(a.get("_id") == "online" for a in registry.MENU_EXTRAS):
        registry.MENU_EXTRAS.append({"label": "ONLINE", "on_click": _menu_click, "_id": "online"})
    SYNC.request(game)
