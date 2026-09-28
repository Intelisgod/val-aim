# -*- coding: utf-8 -*-
"""แผนที่ของโหมด CLUTCH 1vN — กริดความสูง + ชน/ไถลกำแพง + รังสี LOS/กระสุน + nav (pure python, ไม่มี pygame, py3.10)

ตาม docs/CLUTCH_DESIGN.md §2.1/§2.3/§3 — กริดนี้คือแหล่งความจริงเดียวของ การชน, LOS, กระสุน, nav, เมช, มินิแมพ
  ช่องละ CELL 0.25 ม. · ช่อง (i, j) ครอบ x ∈ [x0+i·CELL, x0+(i+1)·CELL), z ∈ [z0+j·CELL, …) · idx = j·nx + i
  kind : VOID 0 (นอกแมพ/มวลกำแพง) · FLOOR 1 · SITE 2 (พื้นในไซต์) · BOX 3 (กล่องมีหลังคา) · WALL 4 (กำแพงบาง ทึบถึงฟ้า)
  h    : รหัสความสูง y = (code − 64)·0.05 ม. (−3.2…+9.55) = พื้นของ FLOOR/SITE, หลังกล่องของ BOX ; VOID/WALL ไม่ใช้
  zone : โซนวาง spike 0 ไม่มี · 1 A · 2 B · 3 C
ของแข็งของ LOS/กระสุน = เสาใต้ "ยอด" ของทุกช่อง (พื้น/หลังกล่อง ; VOID/WALL = +inf) ลงไปไม่สิ้นสุด ; นอกกริด = ฟ้าโล่ง
ของแข็งของการเดิน (วงกลมรัศมี r) = VOID/BOX/WALL/นอกกริด + พื้นที่สูงกว่าเท้าเกิน STEP_UP (ขอบ ledge ขาขึ้น)
พิกัดโลก (§1): x ขวา, y ขึ้น, z หน้า(เหนือ) ; yaw 0 = +z หมุนขวาเพิ่ม — ตรงกับ camera.py / arena.angles_to
ไฟล์ด่าน (§10.1): ค้นใน data/maps (ด่านจริงที่ tools/map_bake.py bake บนเครื่องผู้ใช้ — ไม่แจก) ก่อน แล้ว assets/maps ;
  slug "yard" = Training Yard ในตัว (testyard()) ใช้ได้เสมอ — list_maps() ต่อท้ายให้ ("builtin": True)
ส่วนเพิ่มของ API (หลัง core_api.md, เข้ากันได้ย้อนหลัง): YARD · yard_entry() · hold_yaws(h) · ClutchMap.entries (§10.4) ·
  holds 5 ช่อง [x, z, yaw, w, yaw2|None] · scen["rw"] · load(): "yard" + FileNotFoundError เมื่อไม่มีไฟล์ · ref_n ใน index.json
"""
import base64
from array import array
import functools
import gzip
import heapq
import io
import json
import math
import os
import random
import re
import time
import zlib

CELL = 0.25
STEP_UP = 0.45          # ก้าวขึ้นได้สูงสุด (ม.) — สูงกว่านี้ = ขอบ ledge เดินขึ้นไม่ได้ (ลงได้)
PLAYER_R = 0.40         # รัศมีตัวผู้เล่น (เท่า gunplay PLAYER_R เดิม) > ZNEAR กล้องไม่มุดกำแพง
BOT_R = 0.35
SKY = float("inf")
VOID, FLOOR, SITE, BOX, WALL = 0, 1, 2, 3, 4
H0, HQ = 64, 0.05       # y = (code − H0)·HQ
NAV_CELL = 2 * CELL     # ช่อง nav = 2×2 ช่องกริด (0.5 ม.)
DROP_MAX = 4.0          # nav ยอมให้ "ตกลง" ได้ไม่เกินนี้ (ทางเดียว)
BLOCK = 4               # ช่องต่อบล็อกของ DDA ชั้นบน (1 ม.)
MOVE_SUB = 0.1          # substep ของ move ยาวไม่เกิน (ม.) — กันทะลุกำแพง 1 ช่อง
RESOLVE_IT = 8          # รอบดันออกจากช่องทึบต่อ substep (ไม่หลุด = ถอย/หยุด ไม่วาร์ป)
UNSTICK_STEP = 0.05     # ความละเอียดการค้นจุดว่างของ _unstick (ม.)
UNSTICK_PATH_R = 0.05   # รัศมีที่ลากตรวจทางจากจุดติดถึงจุดว่าง (กันมุดช่องมุมทแยงของกำแพงขั้นบันได)
SMOOTH_BAND = 0.15      # แถบรอบตัว (เกิน r) ที่ใช้เกลี่ย normal ตอนตัดความเร็วชนผนัง
WALK_SAMPLE = 0.1       # ระยะสุ่มจุดของ walk_clear
BOX_LOW, BOX_TALL = 1.1, 2.0    # กล่องเตี้ย (หมอบหลบได้) / กล่องสูง — ความสูงเหนือพื้นรอบกล่อง
ZONE_NAMES = ("", "A", "B", "C")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DIR = os.path.join(_ROOT, "assets", "maps")            # ด่านที่แจกไปกับโปรแกรม (v1 ว่าง — §10.1)
_DATA_DIR = os.path.join(_ROOT, "data", "maps")         # ด่านจริงที่ bake บนเครื่องผู้ใช้ (gitignored, ไม่แจก)
_DIRS = [_DATA_DIR, _DIR]                               # ลำดับค้นหา: data/maps ก่อน แล้ว assets/maps
YARD = "yard"                                           # slug ของ Training Yard ในตัว (testyard) — ไม่มีไฟล์
_HY = tuple((c - H0) * HQ for c in range(256))
_NOF = 1 << 20                              # รหัสพื้นของช่องที่ยืนไม่ได้ (VOID/WALL/BOX/นอกกริด)
_STEPC = int(round(STEP_UP / HQ))           # STEP_UP เป็นรหัสความสูง (9)
_EPS = 1e-6
_WALK_T = bytes(1 if k in (FLOOR, SITE) else 0 for k in range(256))
_TOP_T = bytes(1 if k in (FLOOR, SITE, BOX) else 0 for k in range(256))
_SLUG_RE = re.compile(r"\A[a-z0-9_]{1,32}\Z")
_floor = math.floor
_COS40 = math.cos(math.radians(40.0))

# ── legend ของ from_ascii: ตัวอักษร → (kind, y, zone) ──
#   y = ตัวเลข: FLOOR/SITE = ความสูงพื้น (ม.) ; BOX = ความสูง "เหนือพื้นรอบกล่อง" (ม.)
#   y = None  : FLOOR/SITE สูงเท่าพื้นที่ติดกลุ่มนั้น (4 ทิศ, ไม่นับทางลาด) ที่พบบ่อยสุด — ไซต์บนยกพื้นได้เอง
#   y = "x"/"z": ทางลาดตามแกนนั้น — ไล่ความสูงเชิงเส้นระหว่างพื้นที่ไม่ใช่ทางลาด (รวมไซต์) ใกล้สุดสองฝั่งในแถว/คอลัมน์เดียวกัน
LEGEND = {
    "#": (VOID, 0.0, 0), " ": (VOID, 0.0, 0),
    ".": (FLOOR, 0.0, 0),
    "/": (FLOOR, "x", 0), "^": (FLOOR, "z", 0),
    "A": (SITE, None, 1), "B": (SITE, None, 2), "C": (SITE, None, 3),
    "b": (BOX, BOX_LOW, 0), "T": (BOX, BOX_TALL, 0),
    "|": (WALL, 0.0, 0), "-": (WALL, 0.0, 0),
}
for _d in range(1, 10):
    LEGEND[str(_d)] = (FLOOR, round(0.4 * _d, 2), 0)   # '1' 0.4 ม. (ก้าวขึ้นได้) · '2' 0.8 (ledge) … '5' 2.0 · '9' 3.6


def hcode(y):
    """เมตร → รหัสความสูง (ปัดทีละ 0.05 ม., หนีบ 0..255)"""
    return max(0, min(255, int(round(y / HQ)) + H0))


def _pack(b):
    return base64.b64encode(zlib.compress(bytes(b), 9)).decode("ascii")


def _unpack(s, n):
    b = bytearray(zlib.decompress(base64.b64decode(s)))
    if len(b) != n:
        raise ValueError("clutchmap: ขนาดข้อมูลกริดไม่ตรง nx·nz")
    return b


def _winmax(rows, rad, pad):
    """max ในหน้าต่าง (2rad+1)² รอบทุกช่อง (แยกแกน, map(max) = ความเร็วระดับ C) — นอกกริด = pad"""
    if rad <= 0:
        return [list(r) for r in rows]
    nx = len(rows[0])
    side = [pad] * rad
    hm = []
    for row in rows:
        p = side + row + side
        hm.append(list(map(max, *[p[k:k + nx] for k in range(2 * rad + 1)])))
    edge = [[pad] * nx] * rad
    ext = edge + hm + edge
    return [list(map(max, *ext[j:j + 2 * rad + 1])) for j in range(len(rows))]


def _yaw_to(ax, az, bx, bz):
    return math.atan2(bx - ax, bz - az)


class _Nav:
    """กราฟ nav แบบ CSR (array ล้วน ~4 MB ที่ด่าน 150 ม. — แบบ list ของ tuple กิน ~40 MB)
    เส้นออกของโหนด n = out_adj/out_w[out_off[n]:out_off[n+1]] ; เส้นเข้า (กราฟกลับทิศ ใช้ใน DistField) = in_*"""
    __slots__ = ("nnx", "nnz", "nid", "px", "pz", "py", "out_off", "out_adj", "out_w", "in_off", "in_adj", "in_w",
                 "n_edges", "ms")


def _csr(N, key, other, w):
    """เรียงเส้น (key → other, w) ตาม key แบบ counting sort → (off, adj, wt)"""
    cnt = [0] * (N + 1)
    for k in key:
        cnt[k + 1] += 1
    for k in range(N):
        cnt[k + 1] += cnt[k]
    off = array("i", cnt)
    pos = cnt[:]
    adj, wt = array("i", bytes(4 * len(key))), array("f", bytes(4 * len(key)))
    for k, o, ww in zip(key, other, w):
        q = pos[k]
        adj[q], wt[q] = o, ww
        pos[k] = q + 1
    return off, adj, wt


class ClutchMap:
    """แผนที่หนึ่งด่าน — ดู docstring ของโมดูล ; เมทาดาทา (§2.3 + §10.4) เป็น list/dict ธรรมดา:
    sites {"A": {"c": [x, z], "plants": [[x, z, w], …]}} · spawns {"atk": [x, z], "def": [x, z]} ·
    calls [[ชื่อ, x, z], …] ·
    holds {"A": {"def": [[x, z, yaw, w, yaw2|None], …], "atk_post": […]}} — yaw2 = ทิศหันโหมดที่สองของคลัสเตอร์
      (§10.4 ; None = มีทิศเดียว) ; ไฟล์รุ่นเก่า 4 ช่อง [x, z, yaw, w] ยังอ่านได้ — ใช้ hold_yaws(h) อ่านทิศแบบไม่สนรุ่น
    entries {"A": {"atk": [{"e": [x, z], "stage": [x, z]}, …], "def": […]}} — ช่องทางเข้าไซต์ 1–3 ทางต่อฝั่ง (§10.4):
      e = จุดที่เส้นทางเข้าเขตระยะเดิน ~12 ม. จากศูนย์ไซต์ ; stage = จุดรอรวมพล ~6–8 ม. ถอยออกไปตามทาง (ศูนย์ไซต์มองไม่เห็น)
      ฝั่ง atk = ทางจากฝั่งผู้บุก, def = ทางจากฝั่งผู้ป้องกัน (บอท retake/rotate กระจายตามนี้) ; ด่านเก่าไม่มี = {}
    scen [{"t": "atk"|"def", "s", "n", "p": [x, z, yaw], "e": [[x, z, yaw], …], "k": [x, z], "left", "vis", "rw"}, …]
      (rw = คนจริงในฉากนั้นชนะไหม 0/1 — ด่าน bake เท่านั้น)"""

    def __init__(self, nx, nz, kind, h, zone=None, cell=CELL, x0=0.0, z0=0.0, slug="", name="", flat=False,
                 sites=None, spawns=None, calls=None, holds=None, scen=None, stats=None, entries=None):
        n = nx * nz
        if nx <= 0 or nz <= 0 or len(kind) != n or len(h) != n or (zone is not None and len(zone) != n):
            raise ValueError("clutchmap: ขนาดกริดไม่ตรง nx·nz")
        if max(kind) > WALL or (zone is not None and max(zone) >= len(ZONE_NAMES)):
            raise ValueError("clutchmap: ชนิดช่อง/โซนนอกช่วง")
        self.slug, self.name = slug, name or slug
        self.cell, self.nx, self.nz = float(cell), int(nx), int(nz)
        self.x0, self.z0, self.flat = float(x0), float(z0), bool(flat)
        self.kind, self.h = bytearray(kind), bytearray(h)
        self.zone = bytearray(zone) if zone is not None else bytearray(n)
        self.sites = sites or {}
        self.spawns = spawns or {}
        self.calls = calls or []
        self.holds = holds or {}
        self.scen = scen or []
        self.stats = stats or {}
        self.entries = entries or {}
        self._nav = None
        self._derive()

    # ── โหลด/บันทึก (§2.3) ──
    @classmethod
    def load(cls, slug):
        """โหลด <slug>.json.gz จาก data/maps ก่อน แล้ว assets/maps (path อิงแพ็กเกจ แบบ rankicons._DIR)
        slug ต้องเป็น a-z0-9_ ; slug "yard" = Training Yard ในตัว (testyard() ใหม่ทุกครั้ง — ไม่อ่านไฟล์)
        ไม่มีไฟล์ในทั้งสองที่ = FileNotFoundError"""
        if not _SLUG_RE.match(str(slug)):
            raise ValueError(f"clutchmap: slug ไม่ถูกต้อง {slug!r}")
        if slug == YARD:
            return testyard()
        path = _find_map(slug)
        if path is None:
            raise FileNotFoundError(f"clutchmap: ไม่มีด่าน {slug!r} ใน {_DIRS}")
        return cls.load_file(path)

    @classmethod
    def load_file(cls, path):
        with gzip.open(path, "rb") as f:
            d = json.loads(f.read().decode("utf-8"))
        if d.get("v") != 1:
            raise ValueError(f"clutchmap: รุ่นไฟล์ไม่รองรับ ({d.get('v')})")
        nx, nz = int(d["nx"]), int(d["nz"])
        n = nx * nz
        return cls(nx, nz, _unpack(d["kind"], n), _unpack(d["h"], n), _unpack(d["zone"], n),
                   cell=d.get("cell", CELL), x0=d["x0"], z0=d["z0"], slug=d.get("slug", ""),
                   name=d.get("name", ""), flat=d.get("flat", False), sites=d.get("sites"), spawns=d.get("spawns"),
                   calls=d.get("calls"), holds=d.get("holds"), scen=d.get("scen"), stats=d.get("stats"),
                   entries=d.get("entries"))

    def to_dict(self):
        return {"v": 1, "slug": self.slug, "name": self.name, "cell": self.cell, "nx": self.nx, "nz": self.nz,
                "x0": self.x0, "z0": self.z0, "flat": self.flat,
                "kind": _pack(self.kind), "h": _pack(self.h), "zone": _pack(self.zone),
                "sites": self.sites, "spawns": self.spawns, "calls": self.calls, "holds": self.holds,
                "entries": self.entries, "scen": self.scen, "stats": self.stats}

    def save(self, path):
        """เขียน <slug>.json.gz รูปแบบ §2.3 (gzip mtime 0 = ไฟล์เหมือนเดิมทุกครั้งที่ข้อมูลเหมือนเดิม — diff ใน git นิ่ง)"""
        raw = json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        buf = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as g:
            g.write(raw)
        with open(path, "wb") as f:
            f.write(buf.getvalue())

    # ── ข้อมูลอนุพันธ์ (สร้างตอนโหลดทุกครั้ง — ไม่อยู่ในไฟล์) ──
    def _derive(self):
        nx, nz = self.nx, self.nz
        self._inv = 1.0 / self.cell
        self._r5 = 2.0 * self.cell + 1e-9      # ทางลัด ok5 ใช้ได้กับวงกลมรัศมีไม่เกินนี้
        hy = _HY
        wk = self.kind.translate(_WALK_T)
        tk = self.kind.translate(_TOP_T)
        H = self.h
        self._top = [hy[c] if t else SKY for t, c in zip(tk, H)]
        self._fy = [hy[c] if w else SKY for w, c in zip(wk, H)]
        self._fc = fc = [c if w else _NOF for w, c in zip(wk, H)]
        # บล็อก 4×4 (1 ม.) เก็บยอดต่ำสุด/สูงสุด — DDA ชั้นบนข้ามบล็อกที่รังสีลอยเหนือทั้งบล็อก
        top = self._top
        bnx, bnz = (nx + BLOCK - 1) // BLOCK, (nz + BLOCK - 1) // BLOCK
        rmax, rmin = [], []
        for j in range(nz):
            row = top[j * nx:(j + 1) * nx]
            rmax.append([max(row[b:b + BLOCK]) for b in range(0, nx, BLOCK)])
            rmin.append([min(row[b:b + BLOCK]) for b in range(0, nx, BLOCK)])
        bmax, bmin = [], []
        for bj in range(bnz):
            a, b = rmax[bj * BLOCK:(bj + 1) * BLOCK], rmin[bj * BLOCK:(bj + 1) * BLOCK]
            bmax.extend(map(max, *a) if len(a) > 1 else a[0])
            bmin.extend(map(min, *b) if len(b) > 1 else b[0])
        self._bnx, self._bnz, self._bmax, self._bmin = bnx, bnz, bmax, bmin
        # ok5: หน้าต่าง 5×5 รอบช่องเดินได้ ไม่มีอะไรสูงกว่าพื้นช่องนี้เกิน STEP_UP → วงกลม r ≤ 2·CELL ที่จุดใดในช่องนี้ก็ไม่ชน
        # cc : วงกลม BOT_R ที่ "กลางช่อง" ไม่ชน (หน้าต่างรัศมี kb) — ใช้เลือกจุดตัวแทน nav
        rows = [fc[j * nx:(j + 1) * nx] for j in range(nz)]
        kb = max(1, int(math.ceil(BOT_R / self.cell - 0.5 - 1e-9)))
        self._ok5 = self._flag(rows, _winmax(rows, 2, _NOF))
        self._cc = self._flag(rows, _winmax(rows, kb, _NOF))

    def player_map(self):
        """มุมมองของด่านสำหรับ "การเดินของผู้เล่น" เท่านั้น (CLUTCH_DESIGN §13.1): หลังกล่อง (BOX) เป็นพื้นยืนได้ที่ความสูง
        หลังกล่อง — กระโดด/หมอบกระโดดขึ้นกล่องได้, เดินชนข้างกล่องที่สูงกว่า STEP_UP ยังเป็นผนังเหมือนเดิม
        = สำเนาตื้น (kind/h/zone/ยอด LOS/nav ใช้ร่วมกับด่านจริง) ที่แทนแค่ _fy/_fc/_ok5 ; สร้างครั้งแรกที่เรียกแล้วจำไว้
        (ด่านจริง ~40–50 ms — prep_assets ของโหมดเรียกไว้ก่อนเริ่มรอบ)
        บอท/nav/ฉาก/รังสี ใช้ตัวด่านเดิมเสมอ (ไม่เปลี่ยนพฤติกรรม) — floor_y/support_y/move/disc_clear ของมุมมองนี้นับหลังกล่อง
        กล่องที่ยืนได้ = กลุ่มช่อง BOX (ติดกัน 4 ทิศ) ที่หลังกล่องต่ำสุดสูงกว่าพื้นรอบกลุ่มที่ต่ำสุด ≥ STEP_UP (กล่องจริง) ;
        กลุ่มเตี้ย/ต่ำกว่าพื้น (เศษจากการ bake: ด่านจริงมี "กล่อง" สูง −0.6…+0.4 ม. จากพื้นข้าง ๆ) หรือไม่ติดพื้นเลย = ทึบเหมือนเดิม
        — ไม่งั้นผู้เล่นเดินลง "หลุม"/ก้าวขึ้นช่องที่บอทถือว่าทึบได้"""
        pm = self.__dict__.get("_pmap")
        if pm is None:
            pm = object.__new__(type(self))
            pm.__dict__.update(self.__dict__)
            hy, nx, nz = _HY, self.nx, self.nz
            wk = bytearray(self.kind.translate(_WALK_T))
            for comp in self._box_groups(_STEPC):
                for c in comp:
                    wk[c] = 1
            pm._fy = [hy[c] if w else SKY for w, c in zip(wk, self.h)]
            pm._fc = fc = [c if w else _NOF for w, c in zip(wk, self.h)]
            rows = [fc[j * nx:(j + 1) * nx] for j in range(nz)]
            pm._ok5 = pm._flag(rows, _winmax(rows, 2, _NOF))
            pm._pmap = pm
            self._pmap = pm
        return pm

    def _box_groups(self, min_code):
        """กลุ่มช่อง BOX ติดกัน 4 ทิศ ที่ (หลังกล่องต่ำสุด − พื้น FLOOR/SITE ติดกลุ่มที่ต่ำสุด) ≥ min_code (หน่วยรหัสความสูง)"""
        kind, H, nx, n = self.kind, self.h, self.nx, len(self.kind)
        seen = bytearray(n)
        out = []
        for c0 in range(n):
            if kind[c0] != BOX or seen[c0]:
                continue
            comp, stack, fl = [], [c0], None
            seen[c0] = 1
            while stack:
                c = stack.pop()
                comp.append(c)
                i = c % nx
                for nb in ((c - 1) if i > 0 else -1, (c + 1) if i < nx - 1 else -1, c - nx, c + nx):
                    if not 0 <= nb < n:
                        continue
                    k = kind[nb]
                    if k == BOX and not seen[nb]:
                        seen[nb] = 1
                        stack.append(nb)
                    elif k in (FLOOR, SITE) and (fl is None or H[nb] < fl):
                        fl = H[nb]
            if fl is not None and min(H[c] for c in comp) - fl >= min_code:
                out.append(comp)
        return out

    def on_box(self, x, z):
        """จุดนี้อยู่บนช่องกล่อง (BOX) ไหม — ผู้เล่นยืนบนหลังกล่อง (PlayerView.on_box §13.2)"""
        c = self._idx(x, z)
        return c >= 0 and self.kind[c] == BOX

    def _flag(self, rows, mrows):
        out = bytearray()
        for fr, mr in zip(rows, mrows):
            out += bytes([1 if (f < _NOF and m <= f + _STEPC) else 0 for f, m in zip(fr, mr)])
        return out

    # ── ช่อง ──
    def cell_of(self, x, z):
        i = _floor((x - self.x0) * self._inv)
        j = _floor((z - self.z0) * self._inv)
        if 0 <= i < self.nx and 0 <= j < self.nz:
            return i, j
        return None

    def center(self, i, j):
        return self.x0 + (i + 0.5) * self.cell, self.z0 + (j + 0.5) * self.cell

    def _idx(self, x, z):
        i = _floor((x - self.x0) * self._inv)
        j = _floor((z - self.z0) * self._inv)
        if 0 <= i < self.nx and 0 <= j < self.nz:
            return j * self.nx + i
        return -1

    def _fy_at(self, x, z):
        c = self._idx(x, z)
        return self._fy[c] if c >= 0 else SKY

    def floor_y(self, x, z):
        """ความสูงพื้นใต้จุด (ม.) หรือ None ถ้าไม่ใช่ FLOOR/SITE"""
        f = self._fy_at(x, z)
        return None if f == SKY else f

    def top_y(self, i, j):
        """ยอดของแข็งของช่อง (LOS/กระสุน): พื้น/หลังกล่อง ; SKY สำหรับ VOID/WALL/นอกกริด"""
        if 0 <= i < self.nx and 0 <= j < self.nz:
            return self._top[j * self.nx + i]
        return SKY

    def walkable(self, x, z):
        return self._fy_at(x, z) != SKY

    def disc_clear(self, x, z, r=PLAYER_R, feet=None):
        """วงกลมรัศมี r ยืนที่ (x, z) ได้ไหม (ไม่ทับ VOID/BOX/WALL และไม่ทับพื้นที่สูงกว่าเท้าเกิน STEP_UP)
        feet = ความสูงเท้า (None = พื้นใต้จุดศูนย์กลาง)"""
        f = self._fy_at(x, z)
        if f == SKY:
            return False
        ref = f if feet is None or feet < f else feet
        return not self._disc_hit(x, z, ref + STEP_UP + _EPS, r)

    def _disc_hit(self, x, z, lim, r):
        """วงกลม (x, z, r) ทับช่องที่พื้นสูงเกิน lim (ช่องยืนไม่ได้/นอกกริด = สูงไม่สิ้นสุด) ไหม — แตะพอดีไม่นับ"""
        inv, nx, nz, fy = self._inv, self.nx, self.nz, self._fy
        fx = (x - self.x0) * inv
        fz = (z - self.z0) * inv
        ci, cj = _floor(fx), _floor(fz)
        if 0 <= ci < nx and 0 <= cj < nz:
            c = cj * nx + ci
            if self._ok5[c] and r <= self._r5 and fy[c] + STEP_UP <= lim:
                return False
        rc = r * inv
        rr = (r - _EPS) * inv
        rr2 = rr * rr
        for j in range(_floor(fz - rc), _floor(fz + rc) + 1):
            dz = fz - j - 1.0 if fz > j + 1.0 else (j - fz if fz < j else 0.0)
            dz2 = dz * dz
            if dz2 >= rr2:
                continue
            rowin = 0 <= j < nz
            base = j * nx
            for i in range(_floor(fx - rc), _floor(fx + rc) + 1):
                if rowin and 0 <= i < nx and fy[base + i] <= lim:
                    continue
                dx = fx - i - 1.0 if fx > i + 1.0 else (i - fx if fx < i else 0.0)
                if dx * dx + dz2 < rr2:
                    return True
        return False

    def support_y(self, x, z, r=PLAYER_R):
        """ระดับเท้าที่วงกลม r ที่ (x, z) ยืนอยู่จริง (ม.) หรือ None ถ้าจุดศูนย์กลางไม่อยู่บนพื้น
        = พื้นใต้จุดศูนย์กลาง ถ้าวงกลมลงไปยืนระดับนั้นได้ ; ไม่งั้น (คร่อมร่อง/หลุมแคบกว่าตัว หรือยังเกาะขอบที่สูงกว่า
        เกิน STEP_UP อยู่) = พื้นต่ำสุดใต้วงกลมที่ไม่มีพื้นอื่นใต้วงกลมสูงกว่ามันเกิน STEP_UP — ไม่นับ VOID/BOX/WALL"""
        s = self._support(x, z, r)
        return None if s == SKY else s

    def _support(self, x, z, r):
        inv, nx, nz, fc = self._inv, self.nx, self.nz, self._fc
        fx = (x - self.x0) * inv
        fz = (z - self.z0) * inv
        ci, cj = _floor(fx), _floor(fz)
        if not (0 <= ci < nx and 0 <= cj < nz):
            return SKY
        c = cj * nx + ci
        c0 = fc[c]
        if c0 >= _NOF:
            return SKY
        if self._ok5[c] and r <= self._r5:
            return _HY[c0]
        rc = r * inv
        rr = (r - _EPS) * inv
        rr2 = rr * rr
        higher = []                                           # รหัสพื้นที่สูงกว่าช่องกลางซึ่งวงกลมทับ (รวม ≤ STEP_UP)
        for j in range(max(0, _floor(fz - rc)), min(nz - 1, _floor(fz + rc)) + 1):
            dz = fz - j - 1.0 if fz > j + 1.0 else (j - fz if fz < j else 0.0)
            dz2 = dz * dz
            if dz2 >= rr2:
                continue
            base = j * nx
            for i in range(max(0, _floor(fx - rc)), min(nx - 1, _floor(fx + rc)) + 1):
                q = fc[base + i]
                if q <= c0 or q >= _NOF:
                    continue
                dx = fx - i - 1.0 if fx > i + 1.0 else (i - fx if fx < i else 0.0)
                if dx * dx + dz2 < rr2:
                    higher.append(q)
        if not higher:
            return _HY[c0]
        m = max(higher)
        if m <= c0 + _STEPC:
            return _HY[c0]
        return _HY[min(q for q in higher if q >= m - _STEPC)]

    # ── การเดิน + ชน ──
    def move(self, x, z, feet_y, vel, dt, r=PLAYER_R, step=STEP_UP):
        """เดินวงกลมรัศมี r จาก (x, z) ตาม vel=[vx, vz] (ม./วิ) นาน dt → (x, z, ระดับเท้าที่ยืนได้ | None)
        step = ขึ้นได้สูงสุดเหนือเท้า (ค่าเริ่ม STEP_UP = เดินบนพื้น ; บอท/nav ใช้ค่านี้เสมอ) — ผู้เล่นกลางอากาศส่งค่าเล็ก
          (§13.1 กติกาปีน: ลอยข้ามได้แค่ผิวที่ ≤ เท้า + ขาที่หดตอนหมอบ + 0.05) ; ช่องที่วงกลมทับอยู่แล้วตอนเริ่ม (≤ STEP_UP
          เหนือเท้า เช่นกระโดดข้างขั้นบันได) ไม่นับเป็นผนัง — ไม่โดนดันออกข้างตอนกระโดด
        • substep ≤ MOVE_SUB (ไม่ทะลุกำแพง 1 ช่องแม้ dt 0.1 วิ ที่ 6.75 ม./วิ)
        • ชน = ดันออกตามจุดใกล้สุดบนช่องทึบ (ใกล้สุดก่อน ไม่แยกแกน x/z ที่สะดุดทุกขั้นบันได) แล้วตัดส่วนความเร็ว
          ที่พุ่งเข้าผนังทิ้ง (แก้ vel ในที่ — ดู _clip_vel: ผนังเฉียง/ขั้นบันไดไถลลื่น, วิ่งเข้ามุมห้องหยุดสนิท)
        • ดันไม่หลุด (ติดซอกแคบกว่าตัว เช่นประตู 0.75 ม. ที่ผู้เล่นกว้าง 0.8) หรือดันไกลเกิน 2 เท่าของ substep = ถอยกลับ
          จุดก่อน substep (ว่างแน่นอน) ลองครึ่ง/เสี้ยวทาง ไม่ได้ = หยุดตรงนั้น vel = 0 → ไม่มีวาร์ป/ทะลุกำแพงเด็ดขาด
        • ก้าวขึ้นได้ ≤ STEP_UP เทียบ max(feet_y, พื้นที่เดินผ่านมา) ; เดินลง/ตกขอบได้
        • คืนระดับเท้าที่ยืนได้ = support_y: ปกติ = พื้นใต้จุดศูนย์กลาง ; คร่อมร่อง/หลุมที่แคบกว่าตัว = ยืนบนขอบร่อง ;
          เดินออกจากขอบ ledge สูง = ยังยืนระดับบนจนตัวพ้นขอบทั้งวง (แบบแคปซูลเกาะขอบ = แบบเดียวกับ walk_clear ของ nav)
          ผู้เรียกทำแรงโน้มถ่วงเอง (ค่าคืนต่ำกว่าเท้า = กำลังตก — ห้ามให้เท้าต่ำกว่าค่าคืน) ; ระหว่างตกแล้วเดินกลับเข้าหาขอบ
          ที่สูงกว่าเท้าเกิน STEP_UP ขอบนั้นเป็นกำแพง
        • เริ่มในของแข็ง (วางผิดที่/เท้าต่ำกว่าที่ยืนจริง) = ยกเท้าขึ้นระดับ support_y ถ้าพอ ไม่งั้นหาจุดว่างใกล้สุด ≤ 3 ม.
          ที่ลากจุดศูนย์กลางไปถึงได้โดยไม่ผ่านของแข็ง ; None = จุดศูนย์กลางไม่อยู่บนพื้น (หาจุดว่างไม่ได้เลย)"""
        f0 = self._fy_at(x, z)
        ref = feet_y if (f0 == SKY or feet_y >= f0) else f0
        lim = ref + step + _EPS
        if step < STEP_UP and self._disc_hit(x, z, lim, r):
            top = self._disc_top(x, z, r)
            if top <= ref + STEP_UP:
                lim = top + _EPS
        if self._disc_hit(x, z, lim, r):
            s = self._support(x, z, r)
            if s != SKY and s > ref and not self._disc_hit(x, z, s + STEP_UP + _EPS, r):
                ref, lim = s, s + STEP_UP + _EPS             # คร่อมร่องแคบ/ยังเกาะขอบ = เท้าอยู่ระดับขอบ
            else:
                x, z = self._unstick(x, z, lim, r)
                if self._disc_hit(x, z, lim, r):
                    vel[0] = vel[1] = 0.0
                    s = self._support(x, z, r)
                    return x, z, (None if s == SKY else s)
        n = int(math.hypot(vel[0], vel[1]) * dt / MOVE_SUB) + 1
        k = dt / n
        for _ in range(n):
            dx, dz = vel[0] * k, vel[1] * k
            if dx == 0.0 and dz == 0.0:
                break
            res = self._resolve(x + dx, z + dz, lim, r, x, z, dx * dx + dz * dz)
            if res is None:
                for frac in (0.5, 0.25):                      # ติดซอก: ลองเดินแค่ครึ่ง/เสี้ยวทาง (เข้าชิดผนังให้สุด)
                    res = self._resolve(x + dx * frac, z + dz * frac, lim, r, x, z,
                                        (dx * dx + dz * dz) * frac * frac)
                    if res is not None:
                        break
                if res is None:                               # ไปไม่ได้เลย = หยุดนิ่งที่จุดเดิม (ว่างแน่นอน)
                    vel[0] = vel[1] = 0.0
                    break
            x, z, touched = res
            if touched:
                self._clip_vel(x, z, lim, r, vel, touched)
            f = self._fy_at(x, z)
            if f != SKY and f > ref:
                ref = f
                lim = max(lim, ref + step + _EPS)
        s = self._support(x, z, r)
        return x, z, (None if s == SKY else s)

    def _disc_top(self, x, z, r):
        """พื้นสูงสุดใต้วงกลม (x, z, r) — ช่องยืนไม่ได้/นอกกริด = SKY (ใช้กับ move ตอนลอย)"""
        inv, nx, nz, fy = self._inv, self.nx, self.nz, self._fy
        fx = (x - self.x0) * inv
        fz = (z - self.z0) * inv
        rc = r * inv
        rr = (r - _EPS) * inv
        rr2 = rr * rr
        top = -SKY
        for j in range(_floor(fz - rc), _floor(fz + rc) + 1):
            dz = fz - j - 1.0 if fz > j + 1.0 else (j - fz if fz < j else 0.0)
            dz2 = dz * dz
            if dz2 >= rr2:
                continue
            rowin = 0 <= j < nz
            for i in range(_floor(fx - rc), _floor(fx + rc) + 1):
                dx = fx - i - 1.0 if fx > i + 1.0 else (i - fx if fx < i else 0.0)
                if dx * dx + dz2 >= rr2:
                    continue
                v = fy[j * nx + i] if rowin and 0 <= i < nx else SKY
                if v > top:
                    top = v
        return top

    def _resolve(self, x, z, lim, r, px, pz, d2max):
        """ดันวงกลมที่ (x, z) ออกจากช่องทึบ (พื้นสูงเกิน lim) → (x, z, normal ที่ชน) หรือ None ถ้าดันไม่หลุด/ไกลจาก
        จุดก่อน substep (px, pz) เกิน 2 เท่าของระยะ substep (√d2max) — กันวาร์ป/ทะลุกำแพง"""
        inv, nx, nz, fy, cs = self._inv, self.nx, self.nz, self._fy, self.cell
        x0, z0 = self.x0, self.z0
        ci = _floor((x - x0) * inv)
        cj = _floor((z - z0) * inv)
        if 0 <= ci < nx and 0 <= cj < nz:
            c = cj * nx + ci
            if self._ok5[c] and r <= self._r5 and fy[c] + STEP_UP <= lim:
                return x, z, None                             # ทางลัด: รอบตัวโล่งทั้งหมด
        rr = r - _EPS
        rr2 = rr * rr
        touched = []
        for _it in range(RESOLVE_IT):
            hits = []
            for j in range(_floor((z - r - z0) * inv), _floor((z + r - z0) * inv) + 1):
                cz0 = z0 + j * cs
                qz = cz0 if z < cz0 else (cz0 + cs if z > cz0 + cs else z)
                dz2 = (z - qz) ** 2
                if dz2 >= rr2:
                    continue
                rowin = 0 <= j < nz
                base = j * nx
                for i in range(_floor((x - r - x0) * inv), _floor((x + r - x0) * inv) + 1):
                    if rowin and 0 <= i < nx and fy[base + i] <= lim:
                        continue
                    cx0 = x0 + i * cs
                    qx = cx0 if x < cx0 else (cx0 + cs if x > cx0 + cs else x)
                    d2 = (x - qx) ** 2 + dz2
                    if d2 < rr2:
                        hits.append((d2, i, j))
            if not hits:
                break
            hits.sort()
            for _d2, i, j in hits:                            # ใกล้สุดก่อน → รอยต่อช่องบนผนังเรียบไม่ให้ normal เฉียง
                cx0, cz0 = x0 + i * cs, z0 + j * cs
                qx = cx0 if x < cx0 else (cx0 + cs if x > cx0 + cs else x)
                qz = cz0 if z < cz0 else (cz0 + cs if z > cz0 + cs else z)
                ddx, ddz = x - qx, z - qz
                d2 = ddx * ddx + ddz * ddz
                if d2 >= rr2:
                    continue
                if d2 > 1e-18:
                    d = math.sqrt(d2)
                    ux, uz, push = ddx / d, ddz / d, r - d
                else:                                         # จุดศูนย์กลางอยู่ในช่องทึบ: ออกทางหน้าที่ใกล้สุด
                    opts = ((x - cx0, -1.0, 0.0), (cx0 + cs - x, 1.0, 0.0),
                            (z - cz0, 0.0, -1.0), (cz0 + cs - z, 0.0, 1.0))
                    dd, ux, uz = min(opts)
                    push = dd + r
                x += ux * push
                z += uz * push
                touched.append((ux, uz))
        if (x - px) ** 2 + (z - pz) ** 2 > 4.0 * d2max + 1e-12 or self._disc_hit(x, z, lim, r):
            return None
        return x, z, touched

    def _clip_vel(self, x, z, lim, r, vel, touched):
        """ตัดความเร็วส่วนที่พุ่งเข้าผนัง — ใช้ normal "เกลี่ย" จากช่องทึบรอบตัว (ถ่วงตามความลึก r + SMOOTH_BAND)
        ผนังขั้นบันได/ผนังเฉียงจึงไถลลื่นเหมือนผนังเรียบ (normal ของมุมขั้นเอียง ±26° ทำให้เสียความเร็วทุกขั้น)
        ส่วน normal ที่ต่างจากตัวเกลี่ยเกิน 40° (มุมห้องจริง/ซอกกล่อง) ยังตัดตรง ๆ → วิ่งเข้ามุมแล้วหยุดสนิท (แม่น)"""
        if not touched:
            return
        inv, nx, nz, fy, cs = self._inv, self.nx, self.nz, self._fy, self.cell
        x0, z0 = self.x0, self.z0
        R = r + SMOOTH_BAND
        sx = sz = 0.0
        for j in range(_floor((z - R - z0) * inv), _floor((z + R - z0) * inv) + 1):
            cz0 = z0 + j * cs
            qz = cz0 if z < cz0 else (cz0 + cs if z > cz0 + cs else z)
            rowin = 0 <= j < nz
            for i in range(_floor((x - R - x0) * inv), _floor((x + R - x0) * inv) + 1):
                if rowin and 0 <= i < nx and fy[j * nx + i] <= lim:
                    continue
                cx0 = x0 + i * cs
                qx = cx0 if x < cx0 else (cx0 + cs if x > cx0 + cs else x)
                ddx, ddz = x - qx, z - qz
                d = math.sqrt(ddx * ddx + ddz * ddz)
                if 1e-9 < d < R:
                    w = (R - d) / d
                    sx += w * ddx
                    sz += w * ddz
        m = math.hypot(sx, sz)
        if m > 1e-9:
            sx, sz = sx / m, sz / m
            vn = vel[0] * sx + vel[1] * sz
            if vn < 0.0:
                vel[0] -= vn * sx
                vel[1] -= vn * sz
        for ux, uz in touched:
            if m > 1e-9 and ux * sx + uz * sz >= _COS40:
                continue
            vn = vel[0] * ux + vel[1] * uz
            if vn < 0.0:
                vel[0] -= vn * ux
                vel[1] -= vn * uz

    def _unstick(self, x, z, lim, r):
        """เริ่มในของแข็ง (สปอว์น/ผู้เรียกวางผิดที่) → จุดว่างใกล้สุดในรัศมี 3 ม. (วงแหวนทุก 5 ซม., ทิศห่างกัน ≤ 5 ซม.)
        ที่ลากจุดศูนย์กลาง (วงกลม 5 ซม.) ตรงไปถึงได้โดยออกจากของแข็งที่เริ่มแล้วไม่เข้าของแข็งอีก — ไม่วาร์ปข้ามกำแพงบาง
        ไม่เจอ = คืนจุดเดิม"""
        for ring in range(1, int(3.0 / UNSTICK_STEP) + 1):
            rho = ring * UNSTICK_STEP
            nd = max(8, min(256, int(2.0 * math.pi * rho / UNSTICK_STEP)))
            for k in range(nd):
                a = 2.0 * math.pi * k / nd
                qx, qz = x + rho * math.sin(a), z + rho * math.cos(a)
                if self._disc_hit(qx, qz, lim, r):
                    continue
                n = int(rho / (0.25 * self.cell)) + 1
                out, ok = False, True
                for s in range(1, n + 1):
                    u = s / n
                    hit = self._disc_hit(x + (qx - x) * u, z + (qz - z) * u, lim, UNSTICK_PATH_R)
                    if not hit:
                        out = True
                    elif out:
                        ok = False
                        break
                if ok:
                    return qx, qz
        return x, z

    # ── รังสี (heightfield 3D, DDA สองชั้น) ──
    def ray(self, o, d, tmax):
        """t แรก (d เป็นหน่วย) ที่รังสีเข้าของแข็ง = ต่ำกว่ายอดของช่องที่อยู่ ; None ถ้าไม่ชนภายใน tmax/ออกนอกกริด
        จุดเริ่มอยู่ในของแข็ง → 0.0 ; เฉียดยอดพอดี (y == ยอด) ไม่นับชน ; รังสีขาลงในช่อง = ชนที่ระนาบยอดตรงจุด y = ยอด"""
        ox, oy, oz = o
        dx, dy, dz = d
        inv, nx, nz = self._inv, self.nx, self.nz
        rx, rz = (ox - self.x0) * inv, (oz - self.z0) * inv      # หน่วยช่อง
        ux, uz = dx * inv, dz * inv
        t0, t1 = 0.0, float(tmax)
        if ux > 0.0:
            a, b = -rx / ux, (nx - rx) / ux
        elif ux < 0.0:
            a, b = (nx - rx) / ux, -rx / ux
        elif 0.0 <= rx < nx:
            a, b = -SKY, SKY
        else:
            return None
        if a > t0:
            t0 = a
        if b < t1:
            t1 = b
        if uz > 0.0:
            a, b = -rz / uz, (nz - rz) / uz
        elif uz < 0.0:
            a, b = (nz - rz) / uz, -rz / uz
        elif 0.0 <= rz < nz:
            a, b = -SKY, SKY
        else:
            return None
        if a > t0:
            t0 = a
        if b < t1:
            t1 = b
        if t0 > t1:
            return None
        bnx, bnz, bmax, bmin = self._bnx, self._bnz, self._bmax, self._bmin
        bi = min(max(int(rx + ux * t0) // BLOCK, 0), bnx - 1)
        bj = min(max(int(rz + uz * t0) // BLOCK, 0), bnz - 1)
        if ux > 0.0:
            sx, tdx, tmx = 1, BLOCK / ux, ((bi + 1) * BLOCK - rx) / ux
        elif ux < 0.0:
            sx, tdx, tmx = -1, -BLOCK / ux, (bi * BLOCK - rx) / ux
        else:
            sx, tdx, tmx = 0, SKY, SKY
        if uz > 0.0:
            sz, tdz, tmz = 1, BLOCK / uz, ((bj + 1) * BLOCK - rz) / uz
        elif uz < 0.0:
            sz, tdz, tmz = -1, -BLOCK / uz, (bj * BLOCK - rz) / uz
        else:
            sz, tdz, tmz = 0, SKY, SKY
        t = t0
        while True:
            tn = tmx if tmx < tmz else tmz
            if tn > t1:
                tn = t1
            b = bj * bnx + bi
            ya, yb = oy + dy * t, oy + dy * tn
            if (ya if ya < yb else yb) < bmax[b]:
                if bmin[b] == SKY:
                    return t                                  # บล็อกทึบทั้งบล็อก (VOID/WALL ล้วน)
                hit = self._ray_cells(bi, bj, t, tn, rx, rz, ux, uz, oy, dy)
                if hit is not None:
                    return hit
            if tn >= t1:
                return None
            if tmx < tmz:
                bi += sx
                t = tmx
                tmx += tdx
                if bi < 0 or bi >= bnx:
                    return None
            else:
                bj += sz
                t = tmz
                tmz += tdz
                if bj < 0 or bj >= bnz:
                    return None

    def _ray_cells(self, bi, bj, t, tn, rx, rz, ux, uz, oy, dy):
        nx, top = self.nx, self._top
        ilo, jlo = bi * BLOCK, bj * BLOCK
        ihi, jhi = min(ilo + BLOCK, nx) - 1, min(jlo + BLOCK, self.nz) - 1
        ci = min(max(int(rx + ux * t), ilo), ihi)
        cj = min(max(int(rz + uz * t), jlo), jhi)
        if ux > 0.0:
            sx, cdx, cmx = 1, 1.0 / ux, (ci + 1 - rx) / ux
        elif ux < 0.0:
            sx, cdx, cmx = -1, -1.0 / ux, (ci - rx) / ux
        else:
            sx, cdx, cmx = 0, SKY, SKY
        if uz > 0.0:
            sz, cdz, cmz = 1, 1.0 / uz, (cj + 1 - rz) / uz
        elif uz < 0.0:
            sz, cdz, cmz = -1, -1.0 / uz, (cj - rz) / uz
        else:
            sz, cdz, cmz = 0, SKY, SKY
        while True:
            cn = cmx if cmx < cmz else cmz
            if cn > tn:
                cn = tn
            tp = top[cj * nx + ci]
            if oy + dy * t < tp:
                return t                                      # เข้าทางด้านข้าง (หรือเริ่มในของแข็ง)
            if dy < 0.0 and oy + dy * cn < tp:
                th = (tp - oy) / dy                           # ลงทะลุระนาบยอดกลางช่อง
                return th if th > t else t
            if cn >= tn:
                return None
            if cmx < cmz:
                ci += sx
                t = cmx
                cmx += cdx
                if ci < ilo or ci > ihi:
                    return None
            else:
                cj += sz
                t = cmz
                cmz += cdz
                if cj < jlo or cj > jhi:
                    return None

    def blocked(self, p, q):
        """ส่วนเส้น p→q ชนของแข็งก่อนถึง q ไหม — q แตะผิว (ยืนบนพื้น/ชิดผนังพอดี) ไม่นับบัง"""
        dx, dy, dz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 1e-9:
            return False
        t = self.ray(p, (dx / L, dy / L, dz / L), L)
        return t is not None and t < L - 1e-4

    def any_visible(self, eye, pts):
        """มีจุดไหนใน pts ที่ eye มองเห็นไหม (หยุดที่จุดแรกที่เห็น — เรียงจุดหัว/อกก่อน)"""
        for p in pts:
            if not self.blocked(eye, p):
                return True
        return False

    # ── เดินตรงได้ไหม (ใช้ทั้งสร้าง nav และดึงเส้นทาง) ──
    def walk_clear(self, ax, az, bx, bz, r=BOT_R, feet=None, max_drop=DROP_MAX):
        """วงกลม r เดินตรงจาก a ไป b ได้โดยไม่แตะของแข็งเลยไหม (สุ่มจุดทุก ≤ WALK_SAMPLE)
        ก้าวขึ้น ≤ STEP_UP ; ตกลงได้ ≤ max_drop — ช่วงที่เพิ่งพ้นขอบยังถือว่าเท้าอยู่ระดับบนไกล r (ยังไม่ทันตก)"""
        fa = self._fy_at(ax, az)
        if fa == SKY:
            return False
        ref0 = fa if feet is None or feet < fa else feet
        dx, dz = bx - ax, bz - az
        L = math.hypot(dx, dz)
        n = int(L / WALK_SAMPLE) + 1
        keep = r + L / n                   # จุดบนขอบจริงอาจอยู่เลยจุดสุ่มสุดท้ายบนที่สูงไปได้ถึงหนึ่งช่วงสุ่ม
        inv, nx, nz, fy, ok5 = self._inv, self.nx, self.nz, self._fy, self._ok5
        x0, z0, fast = self.x0, self.z0, r <= self._r5
        win = [(0.0, ref0)]                # (s, พื้น) ในช่วง keep ล่าสุด แบบ monotone (พื้นลดลงจากหัวไปท้าย) → หัว = max
        for k in range(n + 1):
            u = k / n
            x, z = ax + dx * u, az + dz * u
            i = _floor((x - x0) * inv)     # = _fy_at inline
            j = _floor((z - z0) * inv)
            if not (0 <= i < nx and 0 <= j < nz):
                return False
            c = j * nx + i
            f = fy[c]
            if f == SKY:
                return False
            s = L * u
            while win and win[-1][1] <= f:
                win.pop()
            win.append((s, f))
            while win[0][0] < s - keep:
                win.pop(0)
            ref = win[0][1]
            if f < ref - max_drop:
                return False
            lim = ref + STEP_UP + _EPS
            if fast and ok5[c] and f + STEP_UP <= lim:
                continue                   # ทางลัดเดียวกับต้น _disc_hit (รอบช่องนี้โล่ง) โดยไม่เสียค่าเรียกเมธอด
            if self._disc_hit(x, z, lim, r):
                return False
        return True

    # ── nav (§3: ช่อง 0.5 ม., เผื่อรัศมี BOT_R, 8 ทิศ, ขึ้น ≤ STEP_UP, ตก ≤ 4 ม. ทางเดียว, ไม่ตัดมุม) ──
    def ensure_nav(self):
        """สร้างกราฟ nav ครั้งแรกที่ต้องใช้ (หรือเรียกเองตอนโหลดด่าน/นับถอยหลัง) — คืนอ็อบเจกต์ภายใน"""
        if self._nav is None:
            self._nav = self._build_nav()
        return self._nav

    def _rep_score(self, c):
        """ระยะ² (หน่วยช่อง) จากกลางช่อง c ถึงช่องทึบใกล้สุดในหน้าต่าง 5×5 — มาก = กลางทางเดิน"""
        if self._ok5[c]:
            return 99.0
        nx, nz, fc = self.nx, self.nz, self._fc
        ci, cj = c % nx, c // nx
        lim = fc[c] + _STEPC
        best = 99.0
        for dj in range(-2, 3):
            j = cj + dj
            ez = abs(dj) - 0.5 if dj else 0.0
            for di in range(-2, 3):
                i = ci + di
                if 0 <= i < nx and 0 <= j < nz and fc[j * nx + i] <= lim:
                    continue
                ex = abs(di) - 0.5 if di else 0.0
                d2 = ex * ex + ez * ez
                if d2 < best:
                    best = d2
        return best

    def _build_nav(self):
        t0 = time.perf_counter()
        nx, nz = self.nx, self.nz
        cc, ok5 = self._cc, self._ok5
        nnx, nnz = (nx + 1) // 2, (nz + 1) // 2
        nid = array("i", [-1]) * (nnx * nnz)
        opn = bytearray(nnx * nnz)
        px, pz, py = array("d"), array("d"), array("d")
        fy = self._fy
        for b in range(nnz):
            j0 = 2 * b
            for a in range(nnx):
                i0 = 2 * a
                best, bsc, allok = -1, -1.0, True
                for di, dj in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    i, j = i0 + di, j0 + dj
                    if i >= nx or j >= nz:
                        allok = False
                        continue
                    c = j * nx + i
                    if not ok5[c]:
                        allok = False
                    if cc[c]:
                        sc = self._rep_score(c)
                        if sc > bsc:
                            best, bsc = c, sc
                k = b * nnx + a
                opn[k] = 1 if allok else 0
                if best >= 0:
                    nid[k] = len(px)
                    x, z = self.center(best % nx, best // nx)
                    px.append(x)
                    pz.append(z)
                    py.append(fy[best])
        N = len(px)
        es, ed, ew = array("i"), array("i"), array("f")
        for b in range(nnz):
            for a in range(nnx):
                n = nid[b * nnx + a]
                if n < 0:
                    continue
                for da, db in ((1, 0), (0, 1), (1, 1), (-1, 1)):
                    a2, b2 = a + da, b + db
                    if a2 < 0 or a2 >= nnx or b2 >= nnz:
                        continue
                    m = nid[b2 * nnx + a2]
                    if m < 0:
                        continue
                    if da == 0 or db == 0:
                        free = opn[b * nnx + a] and opn[b2 * nnx + a2]
                    else:
                        al = a if a < a2 else a2
                        free = (opn[b * nnx + al] and opn[b * nnx + al + 1] and opn[b2 * nnx + al]
                                and opn[b2 * nnx + al + 1])
                    if free:
                        fwd = bwd = True
                    else:
                        fwd = self.walk_clear(px[n], pz[n], px[m], pz[m], BOT_R)
                        bwd = self.walk_clear(px[m], pz[m], px[n], pz[n], BOT_R)
                    if fwd or bwd:
                        w = math.hypot(px[m] - px[n], pz[m] - pz[n])
                        if fwd:
                            es.append(n)
                            ed.append(m)
                            ew.append(w)
                        if bwd:
                            es.append(m)
                            ed.append(n)
                            ew.append(w)
        nav = _Nav()
        nav.nnx, nav.nnz, nav.nid, nav.px, nav.pz, nav.py = nnx, nnz, nid, px, pz, py
        nav.out_off, nav.out_adj, nav.out_w = _csr(N, es, ed, ew)
        nav.in_off, nav.in_adj, nav.in_w = _csr(N, ed, es, ew)
        nav.n_edges = len(es)
        nav.ms = (time.perf_counter() - t0) * 1000.0
        return nav

    def _nav_near(self, x, z):
        """โหนดในช่อง nav 3×3 รอบจุด เรียงใกล้→ไกล"""
        nav = self.ensure_nav()
        a = _floor((x - self.x0) * self._inv / 2)
        b = _floor((z - self.z0) * self._inv / 2)
        out = []
        for bb in range(b - 1, b + 2):
            if bb < 0 or bb >= nav.nnz:
                continue
            for aa in range(a - 1, a + 2):
                if 0 <= aa < nav.nnx:
                    n = nav.nid[bb * nav.nnx + aa]
                    if n >= 0:
                        out.append(((nav.px[n] - x) ** 2 + (nav.pz[n] - z) ** 2, n))
        out.sort()
        return [n for _d, n in out]

    def nav_node(self, x, z):
        """โหนด nav ของจุด (ช่อง nav ของจุดเอง ไม่งั้นโหนดใกล้สุดในช่อง 3×3) หรือ None"""
        nav = self.ensure_nav()
        a = _floor((x - self.x0) * self._inv / 2)
        b = _floor((z - self.z0) * self._inv / 2)
        if 0 <= a < nav.nnx and 0 <= b < nav.nnz and nav.nid[b * nav.nnx + a] >= 0:
            return nav.nid[b * nav.nnx + a]
        near = self._nav_near(x, z)
        return near[0] if near else None

    def nav_pos(self, node):
        nav = self.ensure_nav()
        return nav.px[node], nav.py[node], nav.pz[node]

    def nav_count(self):
        nav = self.ensure_nav()
        return len(nav.px)

    def dist_field(self, goal_xz):
        """ระยะเดินจริงทุกโหนดถึงเป้า (Dijkstra บนกราฟกลับทิศ) — แบ่งทำทีละช่วง: df.step(max_nodes) → done"""
        return DistField(self, goal_xz)

    def _start_node(self, df, x, z):
        """โหนดเริ่มที่ "เดินตรงถึงได้" จาก (x, z) และรู้ระยะแล้ว — เลือกที่ (ระยะถึงโหนด + ระยะโหนดถึงเป้า) น้อยสุด
        → (โหนด, ระยะรวม, ระดับเท้า) ; เท้า = support_y ของวงกลม BOT_R (บอทที่ยังเกาะขอบ/เพิ่งเดินพ้นขอบลงมา
        วงกลมยังทับขอบบนอยู่ — ถ้าคิดเท้าที่พื้นใต้จุดศูนย์กลาง ขอบนั้นจะกลายเป็นกำแพงแล้วคืน None ทั้งที่ไปได้)"""
        nav = self.ensure_nav()
        feet = self._support(x, z, BOT_R)
        feet = None if feet == SKY else feet
        cand = []
        for n in self._nav_near(x, z):
            if df.fin[n]:
                cand.append((math.hypot(nav.px[n] - x, nav.pz[n] - z) + df.dist[n], n))
        cand.sort()
        for tot, n in cand:
            if self.walk_clear(x, z, nav.px[n], nav.pz[n], BOT_R, feet):
                return n, tot, feet
        return None, None, feet

    def path_len(self, df, x, z):
        """ระยะเดิน (ม.) จาก (x, z) ถึงเป้าของ df — None ถ้าไปไม่ถึง/ยังคำนวณไม่ถึงโหนดนี้"""
        return self._start_node(df, x, z)[1]

    def next_waypoint(self, df, x, z, look=8):
        """จุดถัดไปที่ควรเดินตรงไป (ดึงเส้นให้ตึงตามสายโหนดลงเขาของ df สูงสุด look โหนด) — เดินตรงถึงได้เสมอ
        (walk_clear ด้วยเท้า = support_y(x, z, BOT_R) ; ยืนปกติ = พื้นใต้จุดศูนย์กลาง)
        โหนดถัดไปถูกบัง = คืนจุดบนเส้นเชื่อมแทน (บอทเยื้องแนวโหนดไม่ค้าง) ; ถึงโหนดเป้าแล้วเดินตรงถึงจุดเป้าได้ = คืนจุดเป้า
        None ถ้าไม่มีทาง/ยังไม่ถึงโหนดนี้ — ผู้เรียกควรขอใหม่ทุก ~0.1–0.25 วิ หรือเมื่อเข้าใกล้จุดเดิม < 0.3 ม.
        งานต่อเฟรม (งบบอท 1.5 ms): เรียกไม่เกินหนึ่งบอทต่อเฟรม (วนคิว) — ~0.15 ms เฉลี่ย, ~0.4 ms สูงสุด"""
        nav = self.ensure_nav()
        px, pz = nav.px, nav.pz
        s, _tot, feet = self._start_node(df, x, z)
        if s is None:
            return None
        best, prev, n = (px[s], pz[s]), s, s
        for _ in range(look):
            n = df.nxt[n]
            if n < 0:
                break
            if self.walk_clear(x, z, px[n], pz[n], BOT_R, feet):
                best, prev = (px[n], pz[n]), n
                if n == df.gnode and self.walk_clear(x, z, df.goal[0], df.goal[1], BOT_R, feet):
                    return df.goal
                continue
            # โหนดถัดไปถูกมุมบัง (บอทเยื้องจากแนวโหนด) → จุดกลางเส้นเชื่อม prev→n (เส้นเชื่อม nav เดินตรงได้ทั้งเส้น)
            for f in (0.75, 0.5, 0.25):
                qx, qz = px[prev] + (px[n] - px[prev]) * f, pz[prev] + (pz[n] - pz[prev]) * f
                if self.walk_clear(x, z, qx, qz, BOT_R, feet):
                    best = (qx, qz)
                    break
            break
        if s == df.gnode and best == (px[s], pz[s]) and self.walk_clear(x, z, df.goal[0], df.goal[1], BOT_R, feet):
            return df.goal
        return best

    def astar(self, a_xz, b_xz, max_nodes=20000):
        """เส้นทาง A* (จุดโหนด nav, จุดเรียงแนวเดียวกันถูกยุบ) จาก a ถึง b — None ถ้าไม่มีทาง/เกินงบ max_nodes
        ราคา ~1–2.7 µs ต่อโหนดที่ขยาย (งบ 20000 เต็ม = สูงสุด ~30 ms บนด่าน 150 ม.) → ในเฟรมเกมใช้ max_nodes ≤ ~400
        (≈ ≤ 1 ms) หรือดีกว่า: เป้าที่ต้องไล่บ่อย (ตำแหน่งล่าสุดของผู้เล่น) ใช้ dist_field แบบหั่นช่วงแทน"""
        nav = self.ensure_nav()
        s, g = self.nav_node(*a_xz), self.nav_node(*b_xz)
        if s is None or g is None:
            return None
        px, pz, off, adj, wt = nav.px, nav.pz, nav.out_off, nav.out_adj, nav.out_w
        gx, gz = px[g], pz[g]
        gsc = {s: 0.0}
        came = {}
        heap = [(math.hypot(px[s] - gx, pz[s] - gz), 0.0, s)]
        closed = set()
        while heap:
            _f, gs, n = heapq.heappop(heap)
            if n == g:
                path = [n]
                while n in came:
                    n = came[n]
                    path.append(n)
                path.reverse()
                return _merge_collinear([(px[k], pz[k]) for k in path])
            if n in closed:
                continue
            closed.add(n)
            if len(closed) > max_nodes:
                return None
            for e in range(off[n], off[n + 1]):
                m = adj[e]
                ng = gs + wt[e]
                if ng < gsc.get(m, SKY):
                    gsc[m] = ng
                    came[m] = n
                    heapq.heappush(heap, (ng + math.hypot(px[m] - gx, pz[m] - gz), ng, m))
        return None

    # ── ความหมาย ──
    def zone_at(self, x, z):
        c = self._idx(x, z)
        zid = self.zone[c] if c >= 0 else 0
        return ZONE_NAMES[zid] if 0 < zid < len(ZONE_NAMES) else None

    def callout(self, x, z):
        """ชื่อจุด (callout) ที่ใกล้สุด — "" ถ้าด่านไม่มีรายชื่อ"""
        best, bd = "", SKY
        for c in self.calls:
            d = (c[1] - x) ** 2 + (c[2] - z) ** 2
            if d < bd:
                best, bd = c[0], d
        return best

    # ── สร้างแผนที่สังเคราะห์จาก ASCII ──
    @classmethod
    def from_ascii(cls, rows, cell=CELL, legend=None, x0=0.0, z0=0.0, **meta):
        """แผนที่จากข้อความ — rows[0] = แถวเหนือสุด (z มาก), ตัวอักษรที่ i = คอลัมน์ i (x มากไปทางขวา) = มินิแมพ north-up
        legend (เติม/ทับ LEGEND): '#'/' ' VOID · '.' พื้น y 0 · '1'..'9' พื้น y = 0.4·d ('1' ก้าวขึ้นได้, '2'+ = ledge)
        '/' ทางลาดแกน x · '^' ทางลาดแกน z · 'A' 'B' 'C' พื้นไซต์ (โซน 1/2/3, สูงเท่าพื้นรอบไซต์ที่พบบ่อยสุด) ·
        'b' กล่องเตี้ย +1.1 ม. · 'T' กล่องสูง +2.0 ม. (เหนือพื้นรอบกล่องที่พบบ่อยสุด) · '|' '-' กำแพงบาง
        meta = slug/name/flat/sites/spawns/calls/holds/scen/stats ส่งต่อให้ ClutchMap"""
        leg = dict(LEGEND)
        if legend:
            leg.update(legend)
        nz = len(rows)
        nx = max(len(r) for r in rows)
        n = nx * nz
        kind, zone = bytearray(n), bytearray(n)
        yv = [None] * n
        ramp, inherit, boxrel = {}, [], {}
        for r, row in enumerate(rows):
            j = nz - 1 - r
            for i in range(nx):
                ch = row[i] if i < len(row) else "#"
                if ch not in leg:
                    raise ValueError(f"from_ascii: ตัวอักษร {ch!r} ไม่อยู่ใน legend (แถว {r} คอลัมน์ {i})")
                k, y, zid = leg[ch]
                c = j * nx + i
                kind[c], zone[c] = k, zid
                if k in (FLOOR, SITE):
                    if y is None:
                        inherit.append(c)
                    elif isinstance(y, str):
                        ramp[c] = y
                    else:
                        yv[c] = float(y)
                elif k == BOX:
                    boxrel[c] = float(y or 0.0)
        # ต่อกลุ่มที่ติดกัน (4 ทิศ) ความสูงฐาน = พื้นติดกลุ่มที่รู้ค่าแล้วซึ่งพบบ่อยสุด (เท่ากันเลือกต่ำ) ; ไซต์ = ฐานเลย,
        # กล่อง = ฐาน + ความสูงกล่อง — ไซต์ติดแท่น 0.4 ม. ด้านเดียวจึงไม่ถูกยกเป็นหย่อม ๆ
        def settle(group, rel):
            seen = set()
            for c0 in sorted(group):
                if c0 in seen:
                    continue
                comp, stack, around = [], [c0], {}
                seen.add(c0)
                while stack:
                    c = stack.pop()
                    comp.append(c)
                    i = c % nx
                    for nb in ((c - 1) if i > 0 else -1, (c + 1) if i < nx - 1 else -1, c - nx, c + nx):
                        if not 0 <= nb < n:
                            continue
                        if nb in group:
                            if nb not in seen and (rel is None or rel[nb] == rel[c0]):
                                seen.add(nb)
                                stack.append(nb)
                        elif kind[nb] in (FLOOR, SITE) and yv[nb] is not None:
                            hc = hcode(yv[nb])
                            around[hc] = around.get(hc, 0) + 1
                base = _HY[min(around, key=lambda q: (-around[q], q))] if around else 0.0
                for c in comp:
                    yv[c] = base + (rel[c0] if rel is not None else 0.0)

        # 1) ไซต์ก่อน (จากพื้นหลักรอบไซต์ — ไม่นับทางลาดที่ยังไม่รู้ค่า) → 2) ทางลาดไล่ถึงพื้นหลัก/ไซต์ใกล้สุดสองฝั่ง
        #    (ทางลาดวิ่งชนไซต์ก็ไล่ถึงระดับไซต์ ไม่แบนค้างครึ่งทาง) → 3) กล่องจากพื้นทุกชนิด
        settle(set(inherit), None)
        for c, ax in ramp.items():
            i, j = c % nx, c // nx
            step, lo, hi = (1, i, nx) if ax == "x" else (nx, j, nz)
            ends = []
            for sgn in (-1, 1):
                p, cc = lo, c
                while True:
                    p += sgn
                    cc += sgn * step
                    if p < 0 or p >= hi:
                        break
                    if kind[cc] not in (FLOOR, SITE):
                        break
                    if yv[cc] is not None and cc not in ramp:
                        ends.append((abs(p - lo), yv[cc]))
                        break
            if len(ends) == 2:
                (d0, y0), (d1, y1) = ends
                yv[c] = y0 + (y1 - y0) * d0 / (d0 + d1)
            else:
                yv[c] = ends[0][1] if ends else 0.0
        settle(set(boxrel), boxrel)
        h = bytearray([H0]) * n
        for c in range(n):
            if yv[c] is not None:
                h[c] = hcode(yv[c])
        return cls(nx, nz, kind, h, zone, cell=cell, x0=x0, z0=z0, **meta)


def _merge_collinear(pts):
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        ax, az = pts[k][0] - out[-1][0], pts[k][1] - out[-1][1]
        bx, bz = pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]
        if abs(ax * bz - az * bx) > 1e-9 or ax * bx + az * bz < 0:
            out.append(pts[k])
    out.append(pts[-1])
    return out


class DistField:
    """ระยะเดินจริงทุกโหนดถึงจุดเป้า — Dijkstra บนกราฟกลับทิศ แบ่งทำทีละช่วง (หั่นช่วงไหนผลก็เหมือนทำรวดเดียว:
    heap เรียง (ระยะ, เลขโหนด) ตายตัว) ; dist[n] = ระยะ, nxt[n] = โหนดถัดไปทางลงเขา (−1 = เป้า/ไปไม่ถึง), fin = รู้ผลแล้ว"""

    def __init__(self, cm, goal_xz):
        nav = cm.ensure_nav()
        N = len(nav.px)
        self.cm = cm
        self.goal = (float(goal_xz[0]), float(goal_xz[1]))
        self.dist = [SKY] * N
        self.nxt = [-1] * N
        self.fin = bytearray(N)
        self.heap = []
        self.done = False
        self.settled = 0
        g = cm.nav_node(*self.goal)
        self.gnode = -1 if g is None else g
        if g is None:
            self.done = True
        else:
            d0 = math.hypot(nav.px[g] - self.goal[0], nav.pz[g] - self.goal[1])
            self.dist[g] = d0
            self.heap = [(d0, g)]

    def step(self, max_nodes=500):
        """ทำต่ออีกไม่เกิน max_nodes โหนด → True เมื่อเสร็จทั้งแผนที่
        ค่าเริ่ม 500 ≈ 0.35 ms (p50) ต่อครั้งบนด่าน 150 ม. — ด่านจริง ~27–33k โหนด ≈ 55–65 ครั้ง ≈ 0.4 วิที่ 144 FPS
        (4000 ≈ 3 ms กินงบบอททั้งเฟรม 1.5 ms) ; เริ่มตอนนับถอยหลังหรือใช้ run() ตอนโหลดถ้าไม่ต้องรอ"""
        if self.done:
            return True
        heap, dist, nxt, fin = self.heap, self.dist, self.nxt, self.fin
        nav = self.cm._nav
        off, adj, wt = nav.in_off, nav.in_adj, nav.in_w
        pop, push = heapq.heappop, heapq.heappush
        k = 0
        while heap and k < max_nodes:
            d, n = pop(heap)
            if fin[n]:
                continue
            fin[n] = 1
            k += 1
            for e in range(off[n], off[n + 1]):
                m = adj[e]
                nd = d + wt[e]
                if nd < dist[m]:
                    dist[m] = nd
                    nxt[m] = n
                    push(heap, (nd, m))
        self.settled += k
        if not heap:
            self.done = True
        return self.done

    def run(self):
        while not self.step(1 << 30):
            pass
        return self


# ── ดัชนีด่านที่ bake แล้ว (data/maps ก่อน แล้ว assets/maps) + Training Yard ในตัว ──
def _find_map(slug):
    """path ของ <slug>.json.gz ที่ใช้จริงตามลำดับ _DIRS — None ถ้าไม่มี"""
    for d in _DIRS:
        p = os.path.join(d, slug + ".json.gz")
        if os.path.exists(p):
            return p
    return None


def _read_index(d):
    try:
        with open(os.path.join(d, "index.json"), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def yard_entry():
    """รายการของ Training Yard ในตัว (ไม่ต้องสร้างแผนที่) — "builtin": True ; ใช้ได้เสมอแม้ไม่มีด่าน bake เลย"""
    sc = _yard_scen()
    return {"slug": YARD, "name": "Training Yard", "sites": ["A", "B"],
            "n_scen": {"atk": sum(1 for q in sc if q["t"] == "atk"), "def": sum(1 for q in sc if q["t"] == "def")},
            "flat": False, "builtin": True}


def list_maps():
    """รายการด่าน [{"slug", "name", "sites", "n_scen", "flat", …}, …] — ไม่เคย raise
    = index.json ของ data/maps (ด่านจริงที่ bake บนเครื่องนี้) ตามด้วยของ assets/maps (slug ซ้ำใช้ของ data/maps)
    เฉพาะรายการที่มีไฟล์ .json.gz อยู่จริงในโฟลเดอร์นั้น (รายการเสียทีละตัว ข้ามเฉพาะตัวนั้น)
    แล้วต่อท้ายด้วย Training Yard ในตัวเสมอ ({"slug": "yard", "name": "Training Yard", …, "builtin": True})"""
    out, seen = [], set()
    for d in _DIRS:
        try:
            maps = _read_index(d).get("maps")
            if not isinstance(maps, list):
                continue
            for m in maps:
                slug = m.get("slug") if isinstance(m, dict) else None
                if isinstance(slug, str) and _SLUG_RE.match(slug) and slug != YARD and slug not in seen and \
                        os.path.exists(os.path.join(d, slug + ".json.gz")):
                    seen.add(slug)
                    out.append(m)
        except Exception:
            continue
    try:
        out.append(yard_entry())
    except Exception:
        pass
    return out


def ref_winrates():
    """อัตราชนะ clutch ของผู้เล่นจริง ("ref_wr" ของ index.json ตัวแรกที่มีตามลำดับ _DIRS) — {} ถ้าไม่มี
    รูป {"atk": {"1": %, …, "5": %}, "def": {…}} ; จำนวนตัวอย่างอยู่ที่ "ref_n" รูปเดียวกัน (ถ้ามี)"""
    for d in _DIRS:
        r = _read_index(d).get("ref_wr")
        if isinstance(r, dict) and r:
            return r
    return {}


def hold_yaws(hd):
    """ทิศหันของ hold หนึ่งจุด → [yaw] หรือ [yaw, yaw2] (อ่านได้ทั้งรูปใหม่ 5 ช่องและรุ่นเก่า 4 ช่อง)"""
    out = [hd[2]]
    if len(hd) > 4 and hd[4] is not None:
        out.append(hd[4])
    return out


# ── จุดเกิดปลอดภัย (ผู้ใช้ 2026-09-28: "1v5 เกิดมากลางดงศัตรู 2 ตัว ตายทันที") ──
# ฉากจริง ~30–40% คือเสี้ยววินาทีหลังเพื่อนร่วมทีมตาย = ศัตรูเห็นเราอยู่แล้ว ; สำหรับการซ้อม "เลาะ" จุดเกิดต้อง: ศัตรูใกล้สุด
# ≥ SAFE_START_R, ไม่มีใครเห็นหัว/อก/สะโพกเรา และขยับ SAFE_STEP ไปทางไหน (8 ทิศ) ก็ยังไม่มีศัตรูในระยะ SAFE_STEP_R เห็น
# (ศัตรูไกลกว่านั้นที่เห็นเมื่อเราก้าวออก = มุมที่ต้องเคลียร์ตามปกติของเกม ไม่ใช่ "เกิดกลางดง")
SAFE_START_R = 10.0
SAFE_STEP = 1.5
SAFE_STEP_R = 15.0
SAFE_ESTEP_R = 20.0      # ศัตรูในระยะนี้ที่ขยับ SAFE_STEP แล้วเห็นเรา = ไม่ปลอดภัย (บอท rotate เดินผ่านมุมที่เรายืน 0.7 ม. ก็ยิง —
                         # Haven ATK #530 โดนตอน 0.65 วิ ทั้งที่ตอนเริ่มไม่มีใครเห็น)
_SAFE_EYE = 1.65                          # ตาบอท/ผู้เล่นยืน (config.EYE_Y)
# จุดตัวอย่าง 7 จุดแบบเดียวกับที่สมองบอทใช้มอง (clutchbots.body_points — ข้างหัว/ไหล่ตั้งฉากแนวสายตา) : ค่าจาก guns
# HEAD_Y 1.60 · HEAD_R 0.14 · BODY_Y0/Y1 0.90/1.46 · BODY_HW 0.22 (คัดลอก — clutchmap import clutchbots/guns ไม่ได้/ไม่ควร)
_SAFE_BODY = ((0.0, 1.60), (0.0, 1.18), (-0.22, 1.40), (0.22, 1.40), (-0.14, 1.60), (0.14, 1.60), (0.0, 0.90))


def _feet(cm, x, z, r):
    f = cm.support_y(x, z, r)
    if f is None:
        f = cm.floor_y(x, z)
    return 0.0 if f is None else f


def start_seen(cm, px, pz, enemies):
    """มีศัตรูใน enemies ([x, z, …]) ที่ตา (ยืน) เห็นหัว/อก/สะโพกของผู้เล่นที่ยืนที่ (px, pz) ไหม"""
    fp = _feet(cm, px, pz, PLAYER_R)
    for e in enemies:
        fe = _feet(cm, e[0], e[1], BOT_R)
        dx, dz = px - e[0], pz - e[1]
        L = math.hypot(dx, dz)
        ux, uz = (dz / L, -dx / L) if L > 1e-6 else (1.0, 0.0)
        pts = [(px + ux * o, fp + h, pz + uz * o) for o, h in _SAFE_BODY]
        if cm.any_visible((e[0], fe + _SAFE_EYE, e[1]), pts):
            return True
    return False


def start_safe(cm, px, pz, enemies, near=SAFE_START_R, step=SAFE_STEP, step_r=SAFE_STEP_R):
    """จุดเกิดผู้เล่นปลอดภัยไหม (ดูบนหัวข้อ) — ราคา ≤ 5 ศัตรู × 9 จุด × 3 รังสี ≈ 1 ms"""
    if any(math.hypot(e[0] - px, e[1] - pz) < near for e in enemies):
        return False
    if start_seen(cm, px, pz, enemies):
        return False
    close = [e for e in enemies if math.hypot(e[0] - px, e[1] - pz) < step_r]
    if close:
        for k in range(8):
            a = k * math.pi / 4.0
            x, z = px + step * math.sin(a), pz + step * math.cos(a)
            if cm.walkable(x, z) and start_seen(cm, x, z, close):
                return False
    for e in enemies:                                   # ศัตรูขยับก้าวแรก (เดิน rotate/พีค) แล้วเห็นเราทันทีไหม
        if math.hypot(e[0] - px, e[1] - pz) >= SAFE_ESTEP_R:
            continue
        for k in range(8):
            a = k * math.pi / 4.0
            x, z = e[0] + step * math.sin(a), e[1] + step * math.cos(a)
            if cm.walkable(x, z) and start_seen(cm, px, pz, [(x, z)]):
                return False
    return True


_CACHE = {}
_CACHE_MAX = 2          # ด่าน 150 ม. + nav ≈ 17 MB — จำแค่ 2 ด่านล่าสุด


def cached(slug):
    """load(slug) แบบจำไว้ (เล่นด่านเดิมซ้ำไม่ต้องโหลด/สร้าง nav ใหม่) — เก็บ _CACHE_MAX ด่านที่ใช้ล่าสุด
    cached("yard") = Training Yard ตัวเดียวกันทุกครั้ง (อย่าแก้ข้อมูลในนั้น)"""
    cm = _CACHE.pop(slug, None)
    if cm is None:
        cm = ClutchMap.load(slug)
    _CACHE[slug] = cm
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    return cm


# ── ด่านทดสอบในตัว = Training Yard (slug "yard" — ด่านเดียวที่แจกไปกับโปรแกรม §10.1) ──
def _yard_scen():
    """ฉากของ Training Yard (สร้างใหม่ทุกครั้ง — ผู้เรียกแก้ได้)"""
    pi = math.pi
    yA = _yaw_to(-9, 6.5, -10.6, -3)
    # จุดเริ่มผู้เล่นต้องไม่อยู่ในสายตาศัตรูตอนเริ่ม (บอทยิงก่อนผู้เล่นขยับ = ตายใน ~2 วิ 37–40/40 seed) — ฉาก 1/2/3/5/6
    # ย้ายไปจุดซ่อนที่เดินได้ใกล้สุด (review 2026-09-28) หันหาเป้าหมาย (ศูนย์ไซต์ ATK / spike DEF)
    cA, cB = (-11.75, 10.2), (14.69, 10.5)
    return [
        {"t": "atk", "s": "A", "n": 1, "p": [-12.0, -7.0, 0.0], "e": [[-12.0, 12.5, pi]], "left": 60},
        {"t": "atk", "s": "A", "n": 2, "p": [-13.0, -9.0, _yaw_to(-13, -9, *cA)],       # (−13, −9) เดิม (−12, −8): ก้าวออก
                                                                                           # 1.5 ม. ไม่โดนตัวที่ 15 ม. เห็น (start_safe)
         "e": [[-12.0, 12.5, pi], [-9.0, 6.5, yA]], "left": 55},
        {"t": "atk", "s": "B", "n": 3, "p": [-3.0, -7.0, _yaw_to(-3.0, -7.0, *cB)],       # เดิม (−2.5, −7.5): ศัตรู
                                                                                           # ก้าวแรกเห็นเรา (start_safe)
         "e": [[14.5, 9.0, pi], [7.5, 14.0, pi / 2], [12.5, 2.0, pi]], "left": 70},
        {"t": "atk", "s": "B", "n": 5, "p": [2.0, -17.0, _yaw_to(2, -17, *cB)],
         "e": [[14.5, 9.0, pi], [7.5, 14.0, pi / 2], [12.5, 2.0, pi], [11.5, 16.5, pi], [-2.0, 16.0, pi / 2]],
         "left": 80},
        {"t": "def", "s": "A", "n": 2, "p": [0.0, 12.0, -1.3], "k": [-12.0, 9.5],
         "e": [[-7.0, 1.0, _yaw_to(-7, 1, -12, 9.5)], [-15.0, 2.0, _yaw_to(-15, 2, -12, 9.5)]], "left": 32},
        {"t": "def", "s": "B", "n": 3, "p": [-6.5, 12.5, _yaw_to(-6.5, 12.5, 14.5, 12.0)], "k": [14.5, 12.0],
         "e": [[13.0, 1.0, 0.0], [9.0, 12.5, pi / 2], [17.5, 16.0, _yaw_to(17.5, 16, 14.5, 12)]], "left": 35},
        {"t": "def", "s": "B", "n": 4, "p": [-6.5, 12.5, _yaw_to(-6.5, 12.5, 15.5, 8.5)], "k": [15.5, 8.5],
         "e": [[13.0, 1.0, 0.0], [9.0, 12.5, pi / 2], [17.5, 16.0, _yaw_to(17.5, 16, 14.5, 12)],
               [5.0, -12.0, 0.8]], "left": 40},
    ]


# entries ของ Training Yard — ได้จาก tools/map_bake.py build_entries() (อัลกอริทึมเดียวกับด่านจริง) แล้วคัดลอกมา
# (คำนวณตอนสร้างทุกครั้งต้องสร้าง nav + dist field ~0.3 วิ) ; selftest ตรวจว่า e/stage ยังถูกต้องกับเรขาคณิตปัจจุบัน
# และ stage ทุกจุดศูนย์ไซต์มองไม่เห็น (§10.4 — map_bake ทิ้งทางที่หาจุดรอซ่อนไม่ได้ ไม่ใช้จุดที่ถูกมองเห็นแทน)
_YARD_ENTRIES = {
    "A": {"atk": [{"e": [-6.88, 0.62], "stage": [-3.38, -4.88]}, {"e": [-13.38, -0.88], "stage": [-11.38, -5.38]},
                  {"e": [-3.38, 11.12], "stage": [-0.88, 5.12]}],
          "def": [{"e": [-1.38, 13.62], "stage": [3.62, 16.38]}, {"e": [-3.88, 18.12], "stage": [9.12, 18.12]},
                  {"e": [-5.34, 1.59], "stage": [1.12, 2.62]}]},
    "B": {"atk": [{"e": [8.62, 1.62], "stage": [1.62, -1.88]}],        # อีก 2 ทางไม่มีจุดรอที่ซ่อนจากไซต์ได้ = ทิ้ง (§10.4)
          "def": [{"e": [7.12, 16.62], "stage": [0.12, 17.12]}, {"e": [5.12, 5.62], "stage": [1.12, 9.12]},
                  {"e": [8.62, 1.62], "stage": [2.62, 0.62]}]},
}


def testyard():
    """ด่านทดสอบ 40×40 ม. (x, z ∈ [−20, 20], ขอบ VOID 1 ม.) — มีทุกอย่างที่ด่านจริงมี:
      ATK spawn (0, −17) ใต้ · DEF spawn (0, 17) เหนือ
      A site (โซน 1) x −16…−8, z 5…13 พื้น 0 ; กล่องสูง x −15…−13.5 z 6…7.5 ; กล่องเตี้ย x −11…−10 z 8…9 และ
        x −13…−11 z 11…12 ; แท่น (dais) +0.4 ม. x −12…−10 z 13…15 (ก้าวขึ้นได้)
      Heaven ยกพื้น 2.0 ม. x 4…11, z 10…16 (ขอบ 2 ม. สามด้าน: ตะวันตก x=4, เหนือ z=16, ตะวันออก x=11 มองลง B)
        ทางลาด x 4…7, z 4…10 ไล่ 0 → 2.0 ม. ขึ้นทางเหนือ (≈18°) ; ใต้ Heaven x 7…11 z 4…10 พื้น 0 + กล่องสูง x 8.5…10 z 6…7.5
      B site (โซน 2) x 12…17, z 7…15 ; กล่องเตี้ย x 15…17 z 9…10 ; กล่องสูง x 12.5…14 z 13…14.5
      B main ร่อง −0.8 ม. x 13…16, z −10…−4 ทางลาดลง z −13…−10 และขึ้น z −4…−1 (ขอบข้างร่อง = ledge 0.8 ม.)
      Mid: กล่องสูง x −2.5…−1 z 3…4.5 ติดกล่องเตี้ย x −1…0 z 3…4 ; กล่องเตี้ย x 2…3 z −1…0
      กำแพงบาง (WALL) x 0…0.25, z −6…2 และ x −3…1, z 8…8.25
      แนวกั้น VOID z −4…−3, x −19…−4 มีช่องประตู: 1.0 ม. x −15…−14 (ผู้เล่นผ่าน) · 0.75 ม. x −11…−10.25 (บอทผ่าน
        ผู้เล่นไม่ผ่าน — ช่อง 0.8 ม. จริงหลังปัดลงกริด 0.25) · 0.5 ม. x −7…−6.5 (ไม่มีใครผ่าน)
      กำแพงเฉียง 45° (VOID หนา 2 ช่อง) จาก (2, −16) ถึง (10, −8) = ขั้นบันไดทดสอบการไถล
      VOID: ฉากกั้น A/Mid x −6…−4 z 2…13 ; มุม x −19…−12 z −19…−14 ; x 12…19 z −19…−14 ; x 16…19 z −2…5 ; x −19…−16 z 15…19"""
    W = 160
    g = [["#"] * W for _ in range(W)]

    def rect(xa, za, xb, zb, ch):
        i0, i1 = int(round((xa + 20) * 4)), int(round((xb + 20) * 4))
        j0, j1 = int(round((za + 20) * 4)), int(round((zb + 20) * 4))
        for j in range(max(0, j0), min(W, j1)):
            for i in range(max(0, i0), min(W, i1)):
                g[j][i] = ch

    rect(-19, -19, 19, 19, ".")
    for r in ((-6, 2, -4, 13), (-19, -19, -12, -14), (12, -19, 19, -14), (16, -2, 19, 5), (-19, 15, -16, 19)):
        rect(*r, "#")
    rect(-19, -4, -4, -3, "#")
    rect(-15, -4, -14, -3, ".")
    rect(-11, -4, -10.25, -3, ".")
    rect(-7, -4, -6.5, -3, ".")
    rect(4, 10, 11, 16, "5")
    rect(4, 4, 7, 10, "^")
    rect(-16, 5, -8, 13, "A")
    rect(12, 7, 17, 15, "B")
    rect(-12, 13, -10, 15, "1")
    rect(13, -10, 16, -4, "v")
    rect(13, -13, 16, -10, "^")
    rect(13, -4, 16, -1, "^")
    for r in ((-11, 8, -10, 9), (-13, 11, -11, 12), (15, 9, 17, 10), (-1, 3, 0, 4), (2, -1, 3, 0)):
        rect(*r, "b")
    for r in ((-15, 6, -13.5, 7.5), (12.5, 13, 14, 14.5), (-2.5, 3, -1, 4.5), (8.5, 6, 10, 7.5)):
        rect(*r, "T")
    rect(0, -6, 0.25, 2, "|")
    rect(-3, 8, 1, 8.25, "-")
    for j in range(W):                                  # กำแพงเฉียง: กลางช่อง x − z ∈ {18.0, 18.25}, 2 ≤ x ≤ 10
        for i in range(W):
            xc, zc = -20 + (i + 0.5) * 0.25, -20 + (j + 0.5) * 0.25
            if 2.0 <= xc <= 10.0 and 18.0 <= xc - zc < 18.5:
                g[j][i] = "#"
    rows = ["".join(g[j]) for j in range(W - 1, -1, -1)]
    pi = math.pi
    yA = _yaw_to(-9, 6.5, -10.6, -3)
    sites = {"A": {"plants": [[-12.0, 9.5, 5], [-9.5, 10.5, 3], [-14.5, 11.5, 2]]},
             "B": {"plants": [[14.5, 12.0, 4], [15.5, 8.5, 3], [13.0, 10.5, 1]]}}
    for s in sites.values():
        tw = sum(p[2] for p in s["plants"])
        s["c"] = [round(sum(p[0] * p[2] for p in s["plants"]) / tw, 2),
                  round(sum(p[1] * p[2] for p in s["plants"]) / tw, 2)]
    # holds [x, z, yaw, w, yaw2|None] — yaw2 = ทิศโหมดที่สอง (holder มองสลับ §10.3)
    holds = {
        "A": {"def": [[-12.0, 12.5, pi, 5, _yaw_to(-12, 12.5, -7, 3)], [-9.0, 6.5, yA, 3, None],
                      [-7.0, 3.0, _yaw_to(-7, 3, 0, -2), 2, _yaw_to(-7, 3, -10.6, -3)], [-11.0, 14.0, pi, 2, None]],
              "atk_post": [[-7.0, 1.0, _yaw_to(-7, 1, -12, 9.5), 3, None],
                           [-15.0, 2.0, _yaw_to(-15, 2, -12, 9.5), 3, _yaw_to(-15, 2, -8, 14)],
                           [-7.0, 14.0, _yaw_to(-7, 14, -12, 9.5), 2, None]]},
        "B": {"def": [[14.5, 9.0, pi, 4, _yaw_to(14.5, 9, 7.5, 13)], [7.5, 14.0, pi / 2, 3, None],
                      [12.5, 2.0, pi, 2, None], [11.5, 16.5, pi, 1, None]],
              "atk_post": [[13.0, 1.0, 0.0, 3, None], [9.0, 12.5, pi / 2, 3, _yaw_to(9, 12.5, 14.5, 17)],
                           [17.5, 16.0, _yaw_to(17.5, 16, 14.5, 12), 2, None]]},
    }
    scen = _yard_scen()
    calls = [["A Site", -12.0, 9.0], ["A Main", -12.0, -8.0], ["A Doors", -10.5, -3.5], ["A Dais", -11.0, 14.0],
             ["A Link", -7.0, 3.0], ["Mid", 0.0, 0.0], ["Mid Rail", -1.0, 9.5], ["Heaven", 7.5, 13.0],
             ["Ramp", 5.5, 7.0], ["Under Heaven", 9.0, 5.0], ["B Site", 14.5, 11.0], ["B Main", 14.5, -7.0],
             ["B Lane", 14.0, 2.0], ["Diagonal", 6.0, -12.5], ["Attacker Spawn", 0.0, -17.0],
             ["Defender Spawn", 0.0, 17.0]]
    cm = ClutchMap.from_ascii(rows, legend={"v": (FLOOR, -0.8, 0)}, x0=-20.0, z0=-20.0, slug=YARD,
                              name="Training Yard", sites=sites, spawns={"atk": [0.0, -17.0], "def": [0.0, 17.0]},
                              calls=calls, holds=holds, scen=scen,
                              entries=json.loads(json.dumps(_YARD_ENTRIES)))     # สำเนาลึก — ผู้เรียกแก้ได้
    for sc in cm.scen:                                   # vis: ศัตรูคนใดมองเห็นหัว/อกผู้เล่นตอนเริ่ม (แบบ bake)
        p = sc["p"]
        fp = cm.floor_y(p[0], p[1]) or 0.0
        pts = [(p[0], fp + 1.60, p[1]), (p[0], fp + 1.18, p[1])]
        sc["vis"] = int(any(cm.any_visible((e[0], (cm.floor_y(e[0], e[1]) or 0.0) + 1.65, e[1]), pts)
                            for e in sc["e"]))
    walk = sum(1 for k in cm.kind if k in (FLOOR, SITE))
    cm.stats = {"walk_m2": round(walk * CELL * CELL), "n_scen": {"atk": sum(s["t"] == "atk" for s in scen),
                                                                "def": sum(s["t"] == "def" for s in scen)}}
    return cm


@functools.lru_cache(maxsize=3)
def synthetic(n=600, seed=1, jitter=0.0):
    """แผนที่สุ่มขนาดด่านจริง (n×n ช่อง = 150 ม. ที่ n 600) ความหนาแน่นแบบมินิแมพจริง — ห้อง/ทางเดินหลายระดับ,
    ทางเดินเฉียงหลายมุม + ห้องกลม (ผนังขั้นบันได), ทางลาด, กล่อง ~70, กำแพงบาง, ไซต์ — ใช้วัดเวลา/จำนวนสามเหลี่ยม
    jitter = โอกาสพลิกช่องริมขอบ (พื้น↔VOID) ทีละช่อง = ขอบหยักแบบ raster มินิแมพจริง (0.5 = หยักสุด ใช้พิสูจน์เพดานเมช)"""
    rng = random.Random(seed)
    N = n * n
    K, Hc = bytearray(N), bytearray([H0]) * N

    def put(j, i0, i1, k, code):
        if 0 <= j < n:
            i0, i1 = max(2, i0), min(n - 2, i1)
            if i1 > i0 and 2 <= j < n - 2:
                K[j * n + i0:j * n + i1] = bytes([k]) * (i1 - i0)
                Hc[j * n + i0:j * n + i1] = bytes([code]) * (i1 - i0)

    levels = (64, 64, 64, 64, 64, 80, 88, 94, 52)
    rooms = []
    for _ in range(26):
        w, d = rng.randint(30, 96), rng.randint(30, 96)
        i0, j0 = rng.randint(10, n - 10 - w), rng.randint(10, n - 10 - d)
        code = rng.choice(levels)
        if rng.random() < 0.25:
            cx, cz, rad = i0 + w / 2, j0 + d / 2, min(w, d) / 2
            for j in range(int(cz - rad), int(cz + rad) + 1):
                hw = math.sqrt(max(0.0, rad * rad - (j + 0.5 - cz) ** 2))
                put(j, int(cx - hw), int(cx + hw), FLOOR, code)
        else:
            for j in range(j0, j0 + d):
                put(j, i0, i0 + w, FLOOR, code)
        rooms.append((i0 + w // 2, j0 + d // 2, code))
    for k in range(len(rooms) - 1):                      # ทางเดินเชื่อมห้อง: รูปตัว L หรือเฉียงตรงถึงกลางห้อง (มุมใดก็ได้)
        (ax, az, _c), (bx, bz, _c2) = rooms[k], rooms[k + 1]
        wd = rng.randint(14, 26)
        if rng.random() < 0.45:
            ja, jb = (az, bz) if az < bz else (bz, az)
            xa, xb = (ax, bx) if az < bz else (bx, ax)
            for j in range(ja, jb + 1):
                cx = xa + (xb - xa) * (j - ja) / max(1, jb - ja)
                put(j, int(cx - wd / 2), int(cx + wd / 2), FLOOR, 64)
        else:
            for j in range(min(az, bz) - wd // 2, max(az, bz) + wd // 2):
                put(j, ax - wd // 2, ax + wd // 2, FLOOR, 64)
            for j in range(bz - wd // 2, bz + wd // 2):
                put(j, min(ax, bx), max(ax, bx), FLOOR, 64)
    for _ in range(12):                                  # ทางลาดตามแกน x
        i0, j0 = rng.randint(20, n - 60), rng.randint(20, n - 40)
        ln, wd, c0 = rng.randint(16, 32), rng.randint(10, 20), rng.choice((64, 80))
        rise = rng.choice((10, 16, 24))
        for j in range(j0, j0 + wd):
            for i in range(i0, i0 + ln):
                if K[j * n + i] == FLOOR:
                    Hc[j * n + i] = c0 + rise * (i - i0) // ln
    for _ in range(70):                                  # กล่อง
        for _try in range(20):
            i0, j0 = rng.randint(10, n - 20), rng.randint(10, n - 20)
            w, d = rng.randint(4, 12), rng.randint(4, 12)
            c = j0 * n + i0
            if all(K[(j0 + dj) * n + i0 + di] == FLOOR for dj in (0, d - 1) for di in (0, w - 1)):
                code = min(255, Hc[c] + rng.choice((22, 22, 40)))
                for j in range(j0, j0 + d):
                    put(j, i0, i0 + w, BOX, code)
                break
    for _ in range(10):                                  # กำแพงบาง
        i0, j0 = rng.randint(20, n - 60), rng.randint(20, n - 60)
        ln = rng.randint(8, 40)
        if rng.random() < 0.5:
            put(j0, i0, i0 + ln, WALL, 64)
        else:
            for j in range(j0, j0 + ln):
                put(j, i0, i0 + 1, WALL, 64)
    for (cx, cz, _c) in rooms[:3]:                       # ไซต์
        for j in range(cz - 20, cz + 20):
            for i in range(cx - 24, cx + 24):
                c = j * n + i
                if 0 <= c < N and K[c] == FLOOR:
                    K[c] = SITE
    if jitter > 0.0:
        K0, H0_ = bytes(K), bytes(Hc)
        for c in range(2 * n, N - 2 * n):
            if not 2 <= c % n < n - 2:
                continue
            k = K0[c]
            if k in (FLOOR, SITE):
                if (K0[c - 1] == VOID or K0[c + 1] == VOID or K0[c - n] == VOID or K0[c + n] == VOID) and \
                        rng.random() < jitter:
                    K[c] = VOID
            elif k == VOID:
                nb = [q for q in (c - 1, c + 1, c - n, c + n) if K0[q] in (FLOOR, SITE)]
                if nb and rng.random() < jitter:
                    K[c], Hc[c] = FLOOR, H0_[nb[0]]
    return ClutchMap(n, n, K, Hc, None, x0=-n * CELL / 2, z0=-n * CELL / 2, slug="synthetic", name="Synthetic")


# ─────────────────────────────── selftest ───────────────────────────────
def _ray_brute(cm, o, d, tmax, step=0.01):
    """อ้างอิงแบบดิบ: เดินทีละ 1 ซม. หาจุดแรกที่ y < ยอดของช่อง (นอกกริด = ฟ้าโล่ง)"""
    ox, oy, oz = o
    dx, dy, dz = d
    x0, z0, inv, nx, nz, top = cm.x0, cm.z0, cm._inv, cm.nx, cm.nz, cm._top
    for k in range(int(tmax / step) + 1):
        t = k * step
        i = _floor((ox + dx * t - x0) * inv)
        j = _floor((oz + dz * t - z0) * inv)
        if 0 <= i < nx and 0 <= j < nz and oy + dy * t < top[j * nx + i]:
            return t
    return None


def _ray_agree(td, tbr, L, step=0.01):
    """ตรงกันไหม: ทั้งคู่ไม่ชน / แบบดิบเจอในช่วง [t, t+1 ซม.] ของ DDA / DDA ชนในเซนติเมตรสุดท้ายที่แบบดิบไม่ได้สุ่ม
    → (ตรง, DDA พลาดของแข็งที่แบบดิบเจอ = อันตราย มองทะลุ)"""
    if td is None and tbr is None:
        return True, False
    if td is not None and tbr is not None and td - 1e-9 <= tbr <= td + step + 1e-9:
        return True, False
    if td is not None and tbr is None and td > L - step - 1e-9:
        return True, False
    return False, td is None or (tbr is not None and tbr < td - 1e-9)


def _walk_points(cm, rng, k, r=PLAYER_R):
    out = []
    while len(out) < k:
        x = rng.uniform(cm.x0, cm.x0 + cm.nx * cm.cell)
        z = rng.uniform(cm.z0, cm.z0 + cm.nz * cm.cell)
        if cm.disc_clear(x, z, r):
            out.append((x, z))
    return out


def _seg_walkable(cm, ax, az, bx, bz, step=0.01):
    """จุดศูนย์กลางเดินเส้นตรง a→b ผ่านแต่ช่องพื้น (FLOOR/SITE) — ใช้จับการทะลุกำแพงบาง/วาร์ปผ่านของแข็ง"""
    n = int(math.hypot(bx - ax, bz - az) / step) + 1
    for k in range(n + 1):
        u = k / n
        if cm._fy_at(ax + (bx - ax) * u, az + (bz - az) * u) == SKY:
            return False
    return True


def _sim_walk(cm, x, z, feet, yaw_wish, secs, vmax=5.4, r=PLAYER_R, fps=144.0):
    """กดเดินทิศ yaw_wish (เรเดียน) นาน secs ด้วย movement.step จริง + move (ตกแบบง่าย) → (x, z, feet)"""
    from .movement import step as mstep
    vel = [0.0, 0.0]
    wish = (math.sin(yaw_wish), math.cos(yaw_wish))
    dt = 1.0 / fps
    for _ in range(int(secs * fps)):
        mstep(vel, wish, vmax, dt)
        x, z, f = cm.move(x, z, feet, vel, dt, r)
        if f is not None:
            feet = f if f > feet else max(f, feet - 9.8 * dt * 0.5)
    return x, z, feet


def selftest():
    errors = []
    T0 = time.perf_counter()
    t = time.perf_counter()
    cm = testyard()
    ms_build = (time.perf_counter() - t) * 1000
    rng = random.Random(0xC1A7)
    # ── เมทาดาทาของ testyard ถูกต้อง (ทีมอื่นใช้แทนด่านจริง) ──
    for side, p in cm.spawns.items():
        if not cm.disc_clear(p[0], p[1], PLAYER_R):
            errors.append(f"testyard: spawn {side} ยืนไม่ได้")
    for s, d in cm.sites.items():
        for p in d["plants"] + [d["c"]]:
            if cm.zone_at(p[0], p[1]) != s:
                errors.append(f"testyard: จุดวาง {s} {p} ไม่อยู่ในโซน {s}")
    for s, hd in cm.holds.items():
        for kind_, lst in hd.items():
            for p in lst:
                if not cm.disc_clear(p[0], p[1], BOT_R):
                    errors.append(f"testyard: hold {s}/{kind_} {p} ยืนไม่ได้")
    for sc in cm.scen:
        if not cm.disc_clear(sc["p"][0], sc["p"][1], PLAYER_R) or \
                any(not cm.disc_clear(e[0], e[1], BOT_R) for e in sc["e"]) or len(sc["e"]) != sc["n"]:
            errors.append(f"testyard: ฉาก {sc['t']}{sc['n']} {sc['s']} มีจุดยืนไม่ได้/จำนวนศัตรูผิด")
        if sc["t"] == "def" and cm.zone_at(*sc["k"]) != sc["s"]:
            errors.append(f"testyard: spike ของฉาก def {sc['s']} ไม่อยู่ในโซน")
    if cm.callout(-12.5, 10) != "A Site" or cm.callout(7, 13.5) != "Heaven" or cm.zone_at(0, 0) is not None:
        errors.append("testyard: callout/zone_at ผิด")
    if abs(cm.floor_y(7.5, 13) - 2.0) > 1e-9 or abs(cm.floor_y(14.5, -7) + 0.8) > 1e-9 or \
            abs(cm.floor_y(-11, 14) - 0.4) > 1e-9 or cm.floor_y(-5, 5) is not None or cm.floor_y(0.1, 0) is not None:
        errors.append("testyard: ความสูงพื้น/ช่องทึบผิด")
    i, j = cm.cell_of(-10.5, 8.5)
    ib, jb = cm.cell_of(-14, 7)
    if abs(cm.top_y(i, j) - 1.1) > 1e-9 or abs(cm.top_y(ib, jb) - 2.0) > 1e-9 or \
            cm.top_y(*cm.cell_of(-5, 5)) != SKY or cm.top_y(*cm.cell_of(0.1, 0)) != SKY:
        errors.append("testyard: ยอดกล่อง/กำแพงผิด")
    ys = [cm.floor_y(5.5, z) for z in (4.1, 5.5, 7.0, 8.5, 9.9)]
    if not all(b > a for a, b in zip(ys, ys[1:])) or ys[0] > 0.1 or ys[-1] < 1.9:
        errors.append(f"testyard: ทางลาดไม่ไล่ระดับ {ys}")
    # from_ascii: ทางลาดวิ่งชนไซต์ต้องไล่ถึงระดับไซต์ (ไซต์ติดแท่น 2.0 ม.) — เคยแบนค้าง 1.25 เหลือขอบ 0.75 ม. กลางทาง
    for row in ("#...." + "/" * 8 + "AAAA5555#", "#...." + "/" * 8 + "5555AAAA#"):
        rs = ClutchMap.from_ascii([row] * 3)
        ry = [rs.floor_y(*rs.center(i, 1)) for i in range(5, 13)]
        sy = rs.floor_y(*rs.center(13 if row[13] == "A" else 17, 1))
        if abs(sy - 2.0) > 1e-9 or not all(b > a for a, b in zip(ry, ry[1:])) or not 0.0 < ry[0] < ry[-1] < 2.0 or \
                ry[-1] < 1.7:
            errors.append(f"from_ascii: ทางลาดชนไซต์ไม่ไล่ถึงระดับไซต์ {row!r} → {ry} ไซต์ {sy}")
    # ── รังสี: กรณีขอบ ──
    tb = cm.ray((-10.5, 1.0, 6.0), (0.0, 0.0, 1.0), 10.0)       # ต่ำกว่าหลังกล่องเตี้ย (x −11…−10, z 8…9, ยอด 1.1)
    if tb is None or abs(tb - 2.0) > 1e-9 or cm.ray((-10.5, 1.1, 6.0), (0.0, 0.0, 1.0), 10.0) is not None:
        errors.append(f"ray: ชนข้างกล่อง/เฉียดหลังกล่องพอดีผิด ({tb})")
    if cm.ray((-10.5, 1.1 - 1e-6, 6.0), (0.0, 0.0, 1.0), 10.0) is None:
        errors.append("ray: ต่ำกว่าหลังกล่องนิดเดียวต้องชน")
    dd = (0.0, -0.3, math.sqrt(1 - 0.09))                        # ขาลงแตะหลังกล่องพอดีที่ขอบไกล → ชนระนาบยอด
    t_top = (1.65 - 1.1) / 0.3
    o2 = (-10.5, 1.65, 9.0 - t_top * dd[2] - 1e-7)
    th = cm.ray(o2, dd, 10.0)
    if th is None or abs(th - t_top) > 1e-5:
        errors.append(f"ray: ขาลงถึงหลังกล่องที่ขอบไกลผิด ({th} vs {t_top})")
    if abs((cm.ray((3.0, 1.65, 0.5), (0.0, -1.0, 0.0), 5.0) or -1) - 1.65) > 1e-9 or \
            cm.ray((3.0, 1.65, 0.5), (0.0, 1.0, 0.0), 50.0) is not None or \
            abs((cm.ray((-10.5, 3.0, 8.5), (0.0, -1.0, 0.0), 5.0) or -1) - 1.9) > 1e-9:
        errors.append("ray: รังสีแนวดิ่งผิด")
    if cm.ray((-5.0, 1.0, 5.0), (1.0, 0.0, 0.0), 3.0) != 0.0 or cm.ray((0.1, 30.0, 0.0), (0.0, -1.0, 0.0), 40) != 0.0:
        errors.append("ray: เริ่มในของแข็ง/เหนือกำแพงต้องชนที่ 0")
    if cm.blocked((3.0, 1.65, 0.5), (3.0, 0.0, 3.5)) or not cm.blocked((3.0, 1.65, 0.5), (3.0, -0.01, 3.5)):
        errors.append("ray: blocked — จุดปลายแตะพื้นพอดีต้องไม่นับบัง / ใต้พื้นต้องบัง")
    if not cm.blocked((-2.0, 1.65, -3.0), (2.0, 1.65, -3.0)) or cm.blocked((-2.0, 1.65, 5.0), (2.0, 1.65, 5.0)):
        errors.append("ray: กำแพงบาง WALL ต้องบังทุกความสูง")
    if not cm.blocked((12.0, 1.65, 13.0), (6.0, 2.0 + 1.60, 13.0)) or \
            cm.blocked((12.0, 1.65, 13.0), (10.8, 2.0 + 1.60, 13.0)):
        errors.append("ray: ขอบ Heaven บังหัวคนบนยกพื้นไกลขอบ แต่ไม่บังคนยืนชิดขอบ — ผิด")
    # ── รังสี: เทียบแบบดิบ 1 ซม. 10k เส้น ──
    t = time.perf_counter()
    pts = _walk_points(cm, rng, 400, 0.3)
    ok = bad = miss = 0
    worst = []
    for k in range(10000):
        a = pts[rng.randrange(len(pts))]
        fa = cm.floor_y(*a)
        u = k % 10
        if u < 4:                                              # ตา → ตัวคน (แบบ LOS จริง)
            b = pts[rng.randrange(len(pts))]
            o = (a[0], fa + rng.choice((1.65, 1.10)), a[1])
            q = (b[0], cm.floor_y(*b) + rng.uniform(0.1, 1.75), b[1])
        elif u < 7:                                            # ตา → ทิศสุ่ม
            o = (a[0], fa + 1.65, a[1])
            yw, pt = rng.uniform(-math.pi, math.pi), rng.uniform(-0.5, 0.35)
            L = rng.uniform(0.5, 14.0) if u < 6 else rng.uniform(20.0, 40.0)
            cp = math.cos(pt) * L
            q = (o[0] + math.sin(yw) * cp, o[1] + math.sin(pt) * L, o[2] + math.cos(yw) * cp)
        else:                                                  # จุดเริ่มสุ่มทั้งแมพ (รวมในกล่อง/กำแพง/นอกกริด) มุมชัน
            o = (rng.uniform(-21, 21), rng.uniform(-1.5, 4.0), rng.uniform(-21, 21))
            q = (rng.uniform(-21, 21), rng.uniform(-1.5, 4.0), rng.uniform(-21, 21))
            if u == 9:
                q = (o[0] + rng.uniform(-2, 2), o[1] + rng.choice((-1, 1)) * rng.uniform(2, 6),
                     o[2] + rng.uniform(-2, 2))
        dx, dy, dz = q[0] - o[0], q[1] - o[1], q[2] - o[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 0.05:
            continue
        d = (dx / L, dy / L, dz / L)
        td, tbr = cm.ray(o, d, L), _ray_brute(cm, o, d, L)
        good, missed = _ray_agree(td, tbr, L)
        ok += good
        bad += not good
        miss += missed
        if not good and len(worst) < 3:
            worst.append((o, d, L, td, tbr))
    # กริดขนาดไม่ลงตัวบล็อก (37×23: บล็อกขอบไม่เต็ม) สุ่มชนิด/ความสูงทุกช่อง + รังสีจากนอกกริด
    orng = random.Random(7)
    om = ClutchMap(37, 23, bytes(orng.choice((0, 1, 1, 1, 2, 3, 4)) for _ in range(37 * 23)),
                   bytes(orng.randint(40, 110) for _ in range(37 * 23)), x0=-3.1, z0=2.7)
    for k in range(1500):
        o = (orng.uniform(-5, 8), orng.uniform(-2, 5), orng.uniform(0.5, 11))
        q = (orng.uniform(-5, 8), orng.uniform(-2, 5), orng.uniform(0.5, 11))
        dx, dy, dz = q[0] - o[0], q[1] - o[1], q[2] - o[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 0.05:
            continue
        d = (dx / L, dy / L, dz / L)
        td, tbr = om.ray(o, d, L), _ray_brute(om, o, d, L)
        good, missed = _ray_agree(td, tbr, L)
        ok += good
        bad += not good
        miss += missed
    n_rays = ok + bad
    agree = ok / max(1, n_rays)
    ms_brute = (time.perf_counter() - t) * 1000
    if agree < 0.999:
        errors.append(f"ray: ตรงกับแบบดิบ {agree:.4%} < 99.9% ({bad} เส้น เช่น {worst[:2]})")
    # ── ชน/เดิน ──
    from .movement import step as mstep
    # ไม่ทะลุกำแพง 1 ช่อง: dt 0.1 วิ ที่ 6.75 ม./วิ ทั้ง WALL บาง และ VOID ช่องเดียว หลายมุม หลายรัศมี
    thin = ClutchMap.from_ascii(["." * 20 + "|" + "." * 20] * 12 + ["." * 20 + "#" + "." * 20] * 12)
    for r in (PLAYER_R, BOT_R, 0.1):
        for ang in (0.0, 0.3, 0.7, 1.2):
            for zc in (1.5, 4.5):
                x, z = 2.0, zc
                vel = [6.75 * math.cos(ang), 6.75 * math.sin(ang) * (1 if zc < 3 else -1)]
                for _ in range(30):
                    vel = [6.75 * math.cos(ang), vel[1]]
                    x, z, _f = thin.move(x, z, 0.0, vel, 0.1, r)
                    if x > 5.0 - r + 1e-6:
                        errors.append(f"move: ทะลุกำแพง 1 ช่อง (r {r}, มุม {ang})")
                        break
    # ไถลเลียบกำแพงเฉียง 45° (ขั้นบันได) ≥ 80% ของการไถลเลียบกำแพงตรง ที่มุมกดเข้าหาผนังเท่ากัน
    # (ผนังเฉียงฝั่งตะวันตกเฉียงเหนือ: มุมนูนของขั้นอยู่บนเส้น x − z = 17.75 ; อ้างอิง = หน้าตะวันออกของฉาก A/Mid x = −4)
    slide = []
    for into in (0.0, 0.2, 0.45):
        xs, zs = 3.35, -13.25
        xe, ze, _f = _sim_walk(cm, xs, zs, 0.0, math.pi / 4 + into, 1.2)
        along = ((xe - xs) + (ze - zs)) / math.sqrt(2)
        xr, zr, _f = _sim_walk(cm, -3.6, 12.5, 0.0, math.pi + into, 1.2)
        ref_along = 12.5 - zr
        slide.append(along / max(1e-9, ref_along))
        if ref_along <= 0 or along / ref_along < 0.8 or (into > 0 and abs(xr + 3.6) > 0.01):
            errors.append(f"move: ไถลกำแพงเฉียง 45° ได้ {along:.2f} ม. vs กำแพงตรง {ref_along:.2f} ม. (กดเข้า {into})")
    # ขอบ Heaven 2 ม.: เดินขึ้นไม่ได้, เดินลง/ตกได้ ; ทางลาดขึ้นได้ ; ขั้น 0.4 ขึ้นได้ ; ร่อง 0.8 ปีนข้างไม่ได้
    x, z, f = _sim_walk(cm, 12.5, 12.0, 0.0, -math.pi / 2, 1.5)             # จาก B เดินตะวันตกเข้าหน้าผา
    if x < 11.0 + PLAYER_R - 1e-3 or f > 0.01:
        errors.append(f"move: ปีนขอบ 2 ม. ขึ้น Heaven ได้ ({x:.2f}, {f})")
    x, z, f = _sim_walk(cm, 9.0, 12.0, 2.0, math.pi / 2, 1.2)               # จาก Heaven เดินออกตะวันออก
    if x < 11.5 or f > 0.01:
        errors.append(f"move: เดินตกขอบ Heaven ไม่ได้ ({x:.2f}, {f})")
    x, z, f = _sim_walk(cm, 5.5, 2.0, 0.0, 0.0, 2.0)                        # ทางลาดขึ้นเหนือ
    if f < 1.99 or z < 11.0:
        errors.append(f"move: เดินขึ้นทางลาดไม่ถึง Heaven ({z:.2f}, {f})")
    x2, z2, f2 = _sim_walk(cm, -10.5, 12.3, 0.0, 0.0, 0.45)                 # ขั้น 0.4 ขึ้น dais (z 13…15)
    if f2 < 0.39:
        errors.append(f"move: ก้าวขึ้นขั้น 0.4 ม. ไม่ได้ ({z2:.2f}, {f2})")
    x, z, f = _sim_walk(cm, 14.5, -7.0, -0.8, -math.pi / 2, 1.0)             # ในร่อง −0.8 เดินชนข้างร่อง
    if f > -0.79 or x < 13.0 + PLAYER_R - 1e-3:
        errors.append(f"move: ปีนข้างร่อง 0.8 ม. ได้ ({x:.2f}, {f})")
    # ช่องแคบ (กริด 0.2 ม. = ช่องกว้างจริง 0.8 / 0.6 ม.): 0.8 ผ่านได้ (ตรงกลางหรือเยื้องเล็กน้อย = ไถลเข้าช่อง), 0.6 ไม่ผ่าน
    for gap, want in ((4, True), (3, False)):
        rows = ["." * 20] * 8 + ["#" * 8 + "." * gap + "#" * (12 - gap)] + ["." * 20] * 8
        gm = ClutchMap.from_ascii(rows, cell=0.2)
        cx = (8 + gap / 2) * 0.2
        for off in (0.0, 0.05, -0.08):
            x, z, _f = _sim_walk(gm, cx + off, 0.6, 0.0, 0.0, 2.0)
            if (z > 2.2) != want:
                errors.append(f"move: ช่อง {gap * 0.2:.1f} ม. เยื้อง {off} ผ่าน={z > 2.2} (ควร {want})")
    for gx, want_p, want_b in ((-14.5, True, True), (-10.625, False, True), (-6.75, False, False)):
        for r, want in ((PLAYER_R, want_p), (BOT_R, want_b)):
            x, z, _f = _sim_walk(cm, gx, -5.5, 0.0, 0.0, 1.5, r=r)
            if (z > -2.5) != want:
                errors.append(f"move: ประตู testyard x {gx} r {r} ผ่าน={z > -2.5} (ควร {want})")
    # สุ่มเดินมั่ว (ทุกเฟรมที่ 7 ใช้ dt 0.1) บน testyard + ด่านขอบหยักขนาดจริง ผู้เรียกทำตกตามค่าคืน:
    # ไม่จบในของแข็ง, จุดศูนย์กลางบนพื้นเสมอ, ไม่วาร์ป (เฟรมละ ≤ 2·ความเร็ว·dt), เส้นทางจุดศูนย์กลางไม่ผ่านช่องทึบ
    # (ไม่ทะลุกำแพงบาง) และไม่ได้ความสูงเกิน STEP_UP ในเฟรมเดียว — review 2026-09-27: เคยวาร์ป 1–4 ม. ผ่านของแข็ง
    big = synthetic(jitter=0.5)
    n_wander = 0
    for wm, npts, nfr in ((cm, 30, 100), (big, 16, 300)):
        for (x, z) in _walk_points(wm, rng, npts):
            r = rng.choice((PLAYER_R, BOT_R))
            feet = wm.floor_y(x, z)
            vel = [0.0, 0.0]
            yw = rng.uniform(-math.pi, math.pi)
            for fr in range(nfr):
                if fr % 25 == 0:
                    yw = rng.uniform(-math.pi, math.pi)
                dt = 1 / 60 if fr % 7 else 0.1
                mstep(vel, (math.sin(yw), math.cos(yw)), 6.75, dt)
                sp = math.hypot(vel[0], vel[1])
                px, pz = x, z
                x, z, f = wm.move(x, z, feet, vel, dt, r)
                n_wander += 1
                why = None
                if f is None or wm._disc_hit(x, z, 1e9, r - 1e-4):
                    why = "จบในของแข็ง"
                elif math.hypot(x - px, z - pz) > 2.0 * sp * dt + 1e-6:
                    why = f"วาร์ป {math.hypot(x - px, z - pz):.2f} ม."
                elif not _seg_walkable(wm, px, pz, x, z):
                    why = "ทางผ่านช่องทึบ"
                elif dt < 0.05 and f > feet + STEP_UP + 1e-9:
                    why = f"ขึ้นสูง {f - feet:.2f} ม. ในเฟรมเดียว"
                if why:
                    errors.append(f"move: {why} ({px:.3f}, {pz:.3f}) → ({x:.3f}, {z:.3f}) r {r} ด่าน {wm.slug}")
                    break
                feet = f if f >= feet else max(f, feet - 9.8 * dt * 0.5)
    # ── บั๊กที่ review 2026-09-27 เจอ (ต้องไม่กลับมา) ──
    # ร่อง 0.25 ม. ลึก 0.8 (แคบกว่าตัว): ยืนคร่อม = อยู่บนขอบร่อง ไม่ตกลงไปแล้วถูกดันกระเด็นเข้ากล่อง/นอกกริด
    gut = ClutchMap.from_ascii(["#" * 24] + ["#" + "2" * 10 + "." + "2" * 5 + "bbbb" + "22" + "#"] * 14 + ["#" * 24])
    for r in (PLAYER_R, BOT_R):
        x, z, feet, vy = 2.875, 2.0, 0.8, 0.0
        if abs((gut.support_y(x, z, r) or -1.0) - 0.8) > 1e-9 or gut.floor_y(x, z) != 0.0:
            errors.append(f"support_y: คร่อมร่องแคบต้องยืนบนขอบ 0.8 ม. ({gut.support_y(x, z, r)})")
        for fr in range(144):
            px, pz = x, z
            x, z, f = gut.move(x, z, feet, [0.0, 0.0], 1 / 144, r)
            if f is None or math.hypot(x - px, z - pz) > 1e-9 or f < 0.8 - 1e-9:
                errors.append(f"move: ยืนคร่อมร่องแคบแล้วตก/ถูกดัน ({px:.3f}, {pz:.3f}) → ({x:.3f}, {z:.3f}) พื้น {f} r {r}")
                break
            if f >= feet:
                feet, vy = f, 0.0
            else:
                vy -= 9.8 / 144
                feet = max(f, feet + vy / 144)
        x2, z2, f2 = gut.move(2.875, 2.0, 0.0, [0.0, 0.0], 1 / 144, r)      # ผู้เรียกส่งเท้า = ก้นร่อง → ยกขึ้นยืนบนขอบ
        if (x2, z2) != (2.875, 2.0) or f2 is None or abs(f2 - 0.8) > 1e-9:
            errors.append(f"move: เท้าต่ำกว่าที่ยืนได้ต้องยกขึ้นขอบร่อง ไม่ดันตัวออก ({x2:.3f}, {z2:.3f}, {f2})")
    # ด่านขอบหยัก: บอทเท้า 0.0 เหนือหลุม 1 ช่องของพื้น 0.8 เคยถูกดันไกล 1.48 ม. เข้ากล่อง (สถานะจริงจาก review)
    bx0, bz0 = 29.792699887255, -36.48658440890003
    if big.floor_y(bx0, bz0) != 0.0 or abs((big.support_y(bx0, bz0, BOT_R) or -1.0) - 0.8) > 1e-9:
        errors.append("selftest: synthetic(jitter=0.5) เปลี่ยน — ฉากหลุมที่ (29.79, −36.49) ใช้ทดสอบไม่ได้แล้ว ต้องหาใหม่")
    x2, z2, f2 = big.move(bx0, bz0, 0.0, [1.3432495218820002, 2.798101871889644], 1 / 144, BOT_R)
    if f2 is None or math.hypot(x2 - bx0, z2 - bz0) > 0.05 or big._disc_hit(x2, z2, 1e9, BOT_R - 1e-4):
        errors.append(f"move: หลุมแคบบนด่านขอบหยักยังดันไกล → ({x2:.3f}, {z2:.3f}, {f2})")
    # ทางเดิน 1.0 ม. ข้างกำแพงบาง ปลายเป็นประตู 0.75 ม. (แคบกว่าผู้เล่น): วิ่งเฉียงเข้าประตู = หยุดชิดวงกบ
    # ห้ามวาร์ปข้ามกำแพงบางเข้าห้องปิดข้าง ๆ (เคยย้ายไป "กลางช่องว่างใกล้สุด" ซึ่งอยู่อีกฝั่งกำแพง)
    room = "." * 15
    tw = ClutchMap.from_ascii(["#" * 22, "#....|" + room + "#", "#...#|" + room + "#"] +
                              ["#....|" + room + "#"] * 16 + ["#" * 22])
    for ang in (0.0, 10.0, 25.0):
        x, z, _f = _sim_walk(tw, 0.75, 1.5, 0.0, math.radians(ang), 2.0, vmax=6.75)
        if not (0.65 - 1e-6 <= x <= 0.85 + 1e-6) or z >= 4.25:            # ประตูอยู่แถว z 4.25…4.5
            errors.append(f"move: ทางเดินแคบ + ประตู 0.75 ม. มุม {ang}° จบที่ ({x:.3f}, {z:.3f}) (ต้องค้างในทางเดิน)")
    x2, z2, _f = tw.move(1.0, 3.0, 0.0, [0.0, 0.0], 1 / 144)               # เริ่มทับกำแพงบาง 0.15 ม. → ออกฝั่งทางเดิน
    if not (0.65 - 1e-6 <= x2 <= 0.85 + 1e-6) or abs(z2 - 3.0) > 0.3 or tw._disc_hit(x2, z2, 1e9, PLAYER_R - 1e-4):
        errors.append(f"move: เริ่มทับกำแพงบางต้องถูกดันกลับฝั่งทางเดิน ได้ ({x2:.3f}, {z2:.3f})")
    # ดันเข้าประตู 0.75 ม. ของ testyard ค้างไว้ (หลายมุม): พิงวงกบนิ่ง ไม่กระตุกถอยทีละ ~0.24 ม. (เคย 1–9 ครั้ง/2 วิ)
    pops = 0
    for ang in (0.0, 5.0, 10.0, 20.0):
        x, z, vel = -10.9, -5.5, [0.0, 0.0]
        a = math.radians(ang)
        for fr in range(216):
            mstep(vel, (math.sin(a), math.cos(a)), 6.75, 1 / 144)
            px, pz = x, z
            x, z, _f = cm.move(x, z, 0.0, vel, 1 / 144)
            if math.hypot(x - px, z - pz) > 6.75 / 144 + 0.02:
                pops += 1
        if z > -4.0 - 0.1:
            errors.append(f"move: ผู้เล่นผ่าน/มุดประตู 0.75 ม. ได้ (มุม {ang}°, z {z:.3f})")
    if pops:
        errors.append(f"move: ดันประตูแคบค้างแล้วกระตุก/วาร์ป {pops} ครั้ง")
    # ── nav ──
    t = time.perf_counter()
    nav = cm.ensure_nav()
    ms_nav = (time.perf_counter() - t) * 1000
    ga = cm.sites["A"]["c"]
    df1 = cm.dist_field(ga)
    df1.step(1 << 30)
    df2 = cm.dist_field(ga)
    steps = 0
    while not df2.step(37):
        steps += 1
    if df1.dist != df2.dist or df1.nxt != df2.nxt or steps < 5:
        errors.append("nav: dist_field แบบหั่นช่วงไม่ตรงกับทำรวดเดียว")
    unreach = [n for n in range(len(nav.px)) if df1.dist[n] == SKY]
    if unreach:
        errors.append(f"nav: {len(unreach)} โหนดไปไม่ถึง A site (เช่น {cm.nav_pos(unreach[0])})")
    dfa = cm.dist_field(cm.spawns["atk"]).run()
    dfh = cm.dist_field((7.5, 13.0)).run()                          # เป้าบน Heaven
    lb_up = cm.path_len(dfh, 12.5, 12.0)                            # จาก B ขึ้น Heaven ต้องอ้อมทางลาด
    dfb = cm.dist_field((12.3, 12.0)).run()
    lb_dn = cm.path_len(dfb, 10.0, 12.0)                            # จาก Heaven ลง B = ตกลงตรง ๆ
    if lb_up is None or lb_up < 14.0 or lb_dn is None or lb_dn > 3.5 or any(v == SKY for v in dfa.dist):
        errors.append(f"nav: ขึ้น Heaven {lb_up} (ตรง 5 ม. ต้องอ้อมทางลาด > 14) / ลง {lb_dn} (≤ 3.5 ม.) / ถึง spawn ครบไหม")
    for gx, want in ((-14.5, True), (-10.625, True), (-6.75, False)):   # ประตู 1.0 / 0.75 ม. บอทผ่าน, 0.5 ไม่ผ่าน
        dfg = cm.dist_field((gx, -1.5)).run()
        pl = cm.path_len(dfg, gx, -5.5)
        if (pl is not None and pl < 6.0) != want:
            errors.append(f"nav: ผ่านประตู x {gx} ได้ {pl} (ควร {want})")
    bad_wp = 0
    for (x, z) in _walk_points(cm, rng, 300, BOT_R):
        wp = cm.next_waypoint(df1, x, z)
        if wp is None or not cm.walk_clear(x, z, wp[0], wp[1], BOT_R):
            bad_wp += 1
    if bad_wp:
        errors.append(f"nav: next_waypoint คืนจุดที่เดินตรงไม่ถึง/None {bad_wp} ครั้ง")
    for sc in cm.scen:                                  # บอทเดินตามจุดจริงด้วย move ถึงเป้าทุกฉาก
        if sc["t"] != "atk":
            continue
        x, z = sc["e"][0][0], sc["e"][0][1]
        feet = cm.floor_y(x, z)
        dfp = cm.dist_field(sc["p"][:2]).run()
        vel, wp = [0.0, 0.0], None
        for fr in range(144 * 25):
            if math.hypot(sc["p"][0] - x, sc["p"][1] - z) < 0.3:
                break
            if wp is None or fr % 20 == 0 or math.hypot(wp[0] - x, wp[1] - z) < 0.3:
                wp = cm.next_waypoint(dfp, x, z)
                if wp is None:
                    break
            dx, dz = wp[0] - x, wp[1] - z
            dl = math.hypot(dx, dz)
            mstep(vel, (dx / dl, dz / dl) if dl > 0.05 else (0.0, 0.0), 5.4, 1 / 144)
            x, z, f = cm.move(x, z, feet, vel, 1 / 144, BOT_R)
            feet = f if f is not None and f > feet else max(f if f is not None else feet, feet - 0.07)
        if math.hypot(sc["p"][0] - x, sc["p"][1] - z) > 0.6:
            errors.append(f"nav: บอทเดินจาก {sc['e'][0][:2]} ไป {sc['p'][:2]} ไม่ถึง (ค้างที่ {x:.2f}, {z:.2f})")
    # บอทเดินตกขอบ Heaven ด้านตะวันออกลง B: path_len/next_waypoint ต้องมีค่าทุกเฟรม (เคย None ~0.06–0.3 วิ ตอนวงกลม
    # ยังทับขอบบน — ถ้าผู้เล่นตายหลังวาง spike ตอนนั้น บอทจะถูกนับว่าไปกู้ไม่ถึง) ; ยืนเกาะขอบ = support 2.0 ม.
    dfB = cm.dist_field(cm.sites["B"]["c"]).run()
    x, z, feet, vy, vel = 9.8, 12.0, 2.0, 0.0, [0.0, 0.0]
    n_none = 0
    for fr in range(144):
        mstep(vel, (1.0, 0.0), 5.4, 1 / 144)
        x, z, f = cm.move(x, z, feet, vel, 1 / 144, BOT_R)
        if f >= feet:
            feet, vy = f, 0.0
        else:
            vy -= 9.8 / 144
            feet = max(f, feet + vy / 144)
        if cm.path_len(dfB, x, z) is None or cm.next_waypoint(dfB, x, z) is None:
            n_none += 1
    wp = cm.next_waypoint(dfB, 11.15, 12.0)
    if n_none or cm.path_len(dfB, 11.15, 12.0) is None or wp is None or \
            abs((cm.support_y(11.15, 12.0, BOT_R) or -1.0) - 2.0) > 1e-9 or \
            not cm.walk_clear(11.15, 12.0, wp[0], wp[1], BOT_R, 2.0):
        errors.append(f"nav: บอทกลางทางตกขอบ path_len/next_waypoint เป็น None {n_none} เฟรม / เกาะขอบ {wp}")
    path = cm.astar(cm.spawns["atk"], cm.sites["B"]["c"], 20000)
    if not path or math.hypot(path[-1][0] - cm.sites["B"]["c"][0], path[-1][1] - cm.sites["B"]["c"][1]) > 0.8 or \
            any(not cm.walk_clear(a[0], a[1], b[0], b[1], BOT_R) for a, b in zip(path, path[1:])) or \
            cm.astar(cm.spawns["atk"], cm.sites["B"]["c"], 10) is not None:
        errors.append("nav: astar ผิด (ไม่ถึง/ช่วงเดินไม่ได้/งบโหนดไม่ทำงาน)")
    # ── entries ของ Training Yard (§10.4): ทางเข้า 1–3 ทางต่อฝั่ง ; e/stage ยืนได้ ; stage ศูนย์ไซต์มองไม่เห็นและไกลกว่า e ──
    n_ent = hidden = 0
    for s_, sd in cm.sites.items():
        dfs_ = cm.dist_field(sd["c"]).run()
        fc = cm.floor_y(*sd["c"]) or 0.0
        eye = (sd["c"][0], fc + 1.65, sd["c"][1])
        for side in ("atk", "def"):
            lst = cm.entries.get(s_, {}).get(side, [])
            if not 1 <= len(lst) <= 3:
                errors.append(f"testyard: entries {s_}/{side} มี {len(lst)} ทาง (ต้อง 1–3)")
            for q in lst:
                n_ent += 1
                ex, ez = q["e"]
                sx, sz = q["stage"]
                pe, ps = cm.path_len(dfs_, ex, ez), cm.path_len(dfs_, sx, sz)
                fs = cm.floor_y(sx, sz)
                if not (cm.disc_clear(ex, ez, PLAYER_R) and cm.disc_clear(sx, sz, PLAYER_R)) or pe is None or \
                        ps is None or ps < pe + 3.0 or (pe > 13.0 and cm.zone_at(ex, ez) != s_) or fs is None:
                    errors.append(f"testyard: entry {s_}/{side} {q} ผิด (e {pe}, stage {ps})")
                hidden += cm.blocked(eye, (sx, fs + 1.2, sz)) if fs is not None else 0
    if hidden < n_ent:                                   # §10.4: stage ทุกจุดพ้นสายตาจากศูนย์ไซต์
        errors.append(f"testyard: stage พ้นสายตาศูนย์ไซต์แค่ {hidden}/{n_ent}")
    for s_, hd in cm.holds.items():
        for key, lst in hd.items():
            for q in lst:
                if len(q) != 5 or hold_yaws(q)[0] != q[2] or (q[4] is not None and hold_yaws(q) != [q[2], q[4]]):
                    errors.append(f"testyard: hold {s_}/{key} ต้องเป็น [x, z, yaw, w, yaw2|None] ({q})")
    if hold_yaws([1.0, 2.0, 0.5, 3]) != [0.5]:
        errors.append("hold_yaws: อ่านรูปเก่า 4 ช่องไม่ได้")
    # ── โหลด/รายการด่าน: data/maps ก่อน assets/maps, ด่านใน data ทับชื่อเดียวกันใน assets, Training Yard ในตัวเสมอ ──
    import tempfile
    tmpd = tempfile.mkdtemp(prefix="clutchmap_")
    tdata, tass = os.path.join(tmpd, "data"), os.path.join(tmpd, "assets")
    os.makedirs(tdata)
    os.makedirs(tass)
    dirs0 = list(_DIRS)
    try:
        _DIRS[:] = [tdata, tass]
        lm = list_maps()
        if [m["slug"] for m in lm] != [YARD] or not lm[0].get("builtin") or lm[0]["name"] != "Training Yard" or \
                lm[0]["n_scen"] != cm.stats["n_scen"] or ref_winrates() != {}:
            errors.append(f"list_maps: ไม่มีด่าน bake ต้องมีแต่ Training Yard ในตัว ({lm}) / ref {{}}")
        cy = ClutchMap.load(YARD)
        if cy.slug != YARD or cy.kind != cm.kind or cy.entries != cm.entries or cached(YARD) is not cached(YARD):
            errors.append("load/cached: 'yard' ต้องได้ Training Yard (testyard)")
        cm.save(os.path.join(tass, "testyard.json.gz"))
        with open(os.path.join(tass, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "maps": [{"slug": "testyard", "name": "Test Yard", "sites": ["A", "B"],
                                         "n_scen": cm.stats["n_scen"], "flat": False},
                                        {"slug": "ghost", "name": "ไม่มีไฟล์"}, {"slug": 123}, "junk", None,
                                        {"slug": "../testyard"}, {"slug": "testyard\n"}, {"slug": YARD}],
                       "ref_wr": {"atk": {"2": 17.6}}}, f)                # รายการเสียปนมา = ข้ามเฉพาะตัวนั้น
        cm2 = ClutchMap.load("testyard")
        if (cm2.kind, cm2.h, cm2.zone, cm2.sites, cm2.scen, cm2.calls, cm2.holds, cm2.spawns, cm2.x0, cm2.nx,
                cm2.entries) != (cm.kind, cm.h, cm.zone, cm.sites, cm.scen, cm.calls, cm.holds, cm.spawns, cm.x0,
                                 cm.nx, cm.entries):
            errors.append("save/load: ข้อมูลไม่ตรงหลังโหลดกลับ")
        b1 = open(os.path.join(tass, "testyard.json.gz"), "rb").read()
        cm2.save(os.path.join(tass, "testyard.json.gz"))
        if open(os.path.join(tass, "testyard.json.gz"), "rb").read() != b1:
            errors.append("save: ไฟล์ไม่ deterministic")
        if [m["slug"] for m in list_maps()] != ["testyard", YARD] or ref_winrates().get("atk", {}).get("2") != 17.6:
            errors.append("list_maps: ต้องคืนเฉพาะด่านที่มีไฟล์จริง + Training Yard ท้ายสุด")
        # data/maps: ชื่อเดียวกันทับ assets + ด่านเพิ่ม ; ref_wr ของ data มาก่อน
        cm2.name = "Data Yard"
        cm2.save(os.path.join(tdata, "testyard.json.gz"))
        cm2.save(os.path.join(tdata, "other.json.gz"))
        with open(os.path.join(tdata, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "maps": [{"slug": "other", "name": "Other"}, {"slug": "testyard", "name": "Data Yard"}],
                       "ref_wr": {"atk": {"2": 20.0}}}, f)
        if [(m["slug"], m["name"]) for m in list_maps()] != [("other", "Other"), ("testyard", "Data Yard"),
                                                             (YARD, "Training Yard")] or \
                ClutchMap.load("testyard").name != "Data Yard" or ref_winrates()["atk"]["2"] != 20.0:
            errors.append("list_maps/load: data/maps ต้องมาก่อนและทับ assets/maps")
        os.remove(os.path.join(tdata, "testyard.json.gz"))
        if ClutchMap.load("testyard").name != cm.name or \
                [m["slug"] for m in list_maps()] != ["other", "testyard", YARD]:
            errors.append("load: ไฟล์ใน data หาย ต้องตกไปใช้ assets")
        for bad, exc in (("../x", ValueError), ("nosuch", FileNotFoundError)):
            try:
                ClutchMap.load(bad)
                errors.append(f"load: {bad!r} ต้อง raise {exc.__name__}")
            except exc:
                pass
        big = synthetic(jitter=0.5)                      # ขอบหยักแบบ raster จริง = ไฟล์ใหญ่/nav หนักกว่าแบบเรียบ
        big.save(os.path.join(tass, "synthetic.json.gz"))
        t = time.perf_counter()
        ClutchMap.load("synthetic")
        ms_load = (time.perf_counter() - t) * 1000
        kb_big = os.path.getsize(os.path.join(tass, "synthetic.json.gz")) / 1024
    finally:
        _DIRS[:] = dirs0
        _CACHE.clear()
        import shutil
        shutil.rmtree(tmpd, ignore_errors=True)
    if ms_load > 1500:
        errors.append(f"load: แผนที่ 600² ใช้ {ms_load:.0f} ms > 1.5 วิ")
    # ── guns.humanoid_zone y0 (ผู้เล่นบนยกพื้น) ──
    from .guns import humanoid_zone
    o, dz_ = (0.0, 3.6, -10.0), (0.0, 0.0, 1.0)
    if humanoid_zone(o, dz_, 0.0, 0.0, 0.0, y0=2.0)[0] != "head" or humanoid_zone(o, dz_, 0.0, 0.0)[0] is not None or \
            humanoid_zone((0.0, 1.60, -10.0), dz_, 0.0, 0.0)[0] != "head" or \
            humanoid_zone((0.0, 2.3, -10.0), dz_, 0.0, 0.0, 0.0, y0=2.0)[0] != "leg" or \
            humanoid_zone((0.0, 3.6 - 0.55, -10.0), dz_, 0.0, 0.0, 1.0, y0=2.0)[0] != "head":
        errors.append("guns.humanoid_zone: y0 ยกหุ่นทั้งตัวไม่ถูก")
    # ── เวลา: รังสี 40 ม. ที่มองเห็นกันจริงบนแผนที่ขนาดด่านจริง + move ──
    pairs = []
    bp = _walk_points(big, rng, 3000, 0.3)
    for k in range(0, len(bp) - 1, 2):
        a, b = bp[k], bp[k + 1]
        dl = math.hypot(b[0] - a[0], b[1] - a[1])
        if 25.0 < dl < 60.0:
            o = (a[0], big.floor_y(*a) + 1.65, a[1])
            q = (a[0] + (b[0] - a[0]) * 40 / dl, 0.0, a[1] + (b[1] - a[1]) * 40 / dl)
            fq = big.floor_y(q[0], q[2])
            if fq is None:
                continue
            q = (q[0], fq + 1.4, q[2])
            if not big.blocked(o, q):
                pairs.append((o, q))
    rays = []
    for o, q in pairs[:200]:
        dx, dy, dz = q[0] - o[0], q[1] - o[1], q[2] - o[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        rays.append((o, (dx / L, dy / L, dz / L), L))
    t = time.perf_counter()
    for _ in range(5):
        for o, d, L in rays:
            big.ray(o, d, L)
    us_ray = (time.perf_counter() - t) * 1e6 / max(1, 5 * len(rays))
    t = time.perf_counter()
    rnd = 0
    for a in bp[:1000]:
        yw = rng.uniform(-math.pi, math.pi)
        big.ray((a[0], big.floor_y(*a) + 1.65, a[1]), (math.sin(yw), 0.0, math.cos(yw)), 40.0)
        rnd += 1
    us_rnd = (time.perf_counter() - t) * 1e6 / rnd
    if len(rays) < 30 or us_ray > 120:
        errors.append(f"ray: 40 ม. ใช้ {us_ray:.0f} µs (เป้า ≤ 60, {len(rays)} เส้น)")
    t = time.perf_counter()
    for _ in range(2000):
        cm.move(15.55, 3.0, 0.0, [0.4, 5.4], 1 / 144)
    us_mv_wall = (time.perf_counter() - t) * 1e6 / 2000
    t = time.perf_counter()
    for _ in range(2000):
        cm.move(-1.0, -10.0, 0.0, [3.0, 4.4], 1 / 144)
    us_mv_open = (time.perf_counter() - t) * 1e6 / 2000
    t = time.perf_counter()
    big.ensure_nav()
    ms_nav_big = (time.perf_counter() - t) * 1000
    print(f"CLUTCHMAP SELFTEST {'OK' if not errors else 'FAIL'} (testyard {cm.nx}x{cm.nz} {ms_build:.0f} ms | "
          f"ray 40 m LOS {us_ray:.1f} us, random 40 m {us_rnd:.1f} us | brute-force agree {agree:.3%} of {n_rays}, "
          f"dda-miss {miss}, {ms_brute:.0f} ms | move {us_mv_open:.1f} us open / {us_mv_wall:.1f} us at wall, "
          f"stair slide {min(slide):.0%}, fuzz {n_wander} frames no warp | entries {n_ent} ok | nav testyard {len(nav.px)} nodes {nav.n_edges} edges {ms_nav:.0f} ms, "
          f"600x600 {len(big._nav.px)} nodes {ms_nav_big:.0f} ms | load 600x600 {ms_load:.0f} ms {kb_big:.0f} KB | "
          f"total {time.perf_counter() - T0:.1f} s)")
    return errors
