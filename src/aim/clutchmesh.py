# -*- coding: utf-8 -*-
"""เมช 3D + มินิแมพของแผนที่ CLUTCH (pure python — ไม่มี pygame/numpy, ไวยากรณ์ py3.10) — CLUTCH_DESIGN §3 ท้าย/§7/§8

build(cmap) → dict ของ array('f') ต่อจุดยอด (สามเหลี่ยมแยก ไม่มี index = flat shading ตรง ๆ):
  pos 3f · nrm 3f · col 3f (albedo 0..1) · flag 1f (บิต F_*) · aux 1f (ความสูงเหนือฐานของหน้าแนวตั้ง — แถบฐานเข้ม/AO ใน shader)
เรขาคณิตมาจากยอดของแต่ละช่องใน clutchmap ชุดเดียวกับที่ชน/LOS ใช้ (เห็นอะไร = ชนอะไร):
  • พื้น FLOOR/SITE ที่ระดับพื้น (ทางลาด = ขั้นละ 0.05 ม. ตามกริดจริง) · หลังกล่อง BOX · ฝา VOID/WALL ที่ wall_y
  • หน้าแนวตั้งเฉพาะรอยต่อที่ยอดต่างกัน (ผนัง/ขอบ ledge/ข้างกล่อง) หันไปทางช่องที่ต่ำกว่า — รอยต่อละหนึ่งหน้าพอดี
  • VOID/WALL สูง wall_y = WALL_TOP + max(0, พื้นสูงสุดของด่าน) คงที่ทั้งด่าน (ด่านราบ = 7 ม.) ; LOS ของ VOID/WALL = ∞
รวมหน้า: แต่ละแถวตัดเป็นช่วงที่ค่าเท่ากัน แล้วรวมช่วงเดียวกันเป๊ะในแถวติดกันเป็นสี่เหลี่ยม (run-merge greedy)
winding: มองจากฝั่ง normal เห็นทวนเข็มบนจอ — โลกเป็นแบบมือซ้าย ⇒ cross(v1−v0, v2−v0)·n < 0 ; เปิด CULL_FACE (front=CCW) ได้
minimap_rgba(cmap, px) → (w, h, bytes RGBA) north-up (แถวบน = z มาก, ขวา = +x) สีแบบมินิแมพเกม ใช้ pygame.image.frombuffer
region_rgba(cmap) → สีประจำย่าน (A/B/C/Mid/spawn) ต่อบล็อก 1 ม. จาก callout ของด่าน — ให้ shader ทาผนัง/พื้นแยกย่าน (§13 VISUAL)
agent_mesh()/gun_prims()/viewmodel_mesh()/leg_pose() → หุ่นเอเจนต์ขนาดจริง 1:1 + ปืนต่อกระบอก + มือบุคคลที่หนึ่ง (ดูหัวข้อท้ายไฟล์)
"""
from array import array
from itertools import groupby
import math
import time

from .clutchmap import VOID, FLOOR, SITE, BOX, WALL, H0, HQ

WALL_TOP = 7.0
F_GRID, F_SITE, F_BOX, F_WALL, F_LEDGE, F_CAP = 1, 2, 4, 8, 16, 32
FORMAT = "3f 3f 3f 1f 1f"                     # interleave() — ลำดับเดียวกับ ATTRS
ATTRS = ("in_pos", "in_nrm", "in_col", "in_flag", "in_aux")
_K_SITE, _K_BOX, _K_CAP = 256, 512, 1024
_MAT_WALL, _MAT_BOX, _MAT_LEDGE, _MAT_SITE = 0, 1, 2, 3
_MATOF = {VOID: _MAT_WALL, WALL: _MAT_WALL, BOX: _MAT_BOX, FLOOR: _MAT_LEDGE, SITE: _MAT_SITE}
_C_WALL = (199 / 255, 196 / 255, 188 / 255)      # ปูนสว่าง (แถบฐานเข้มทำใน shader จาก aux)
_C_BOXSIDE = (140 / 255, 100 / 255, 62 / 255)    # ไม้
_C_BOXTOP = (176 / 255, 138 / 255, 92 / 255)
_C_CAP = (88 / 255, 88 / 255, 94 / 255)


def floor_lum(y):
    """ความสว่างพื้นตามความสูงแบบมินิแมพเกม: 118 = พื้นฐาน, สูงขึ้น 0.12 ม. = สว่างขึ้น 1 ระดับ (data report §3)"""
    return max(55.0, min(235.0, 118.0 + y / 0.12))


def floor_rgb(y, site=False):
    """สีพื้น 0..1 — ไซต์ = เขียวมะกอก (152,152,118) ที่ y 0 เลื่อนตามความสูงเท่าพื้น"""
    L = floor_lum(y)
    if site:
        return (min(255.0, L + 34) / 255, min(255.0, L + 34) / 255, L / 255)
    return (L / 255, L / 255, L / 255)


class _Mesh:
    def __init__(self):
        self.pos, self.nrm, self.col, self.flag, self.aux = (array("f") for _ in range(5))
        self.counts = {}
        self.vq = []                                  # หน้าแนวตั้ง (axis, line, a0, a1, lo, hi, dir) — ไว้ตรวจใน selftest

    def quad(self, a, b, c, d, n, col, flag, what):
        """มุม a→b→c→d รอบสี่เหลี่ยม (แต่ละมุม = (x, y, z, aux)) → 2 สามเหลี่ยม เรียงให้ cross·n < 0"""
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        if (uy * vz - uz * vy) * n[0] + (uz * vx - ux * vz) * n[1] + (ux * vy - uy * vx) * n[2] > 0.0:
            b, d = d, b
        self.pos.extend((a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2],
                         a[0], a[1], a[2], c[0], c[1], c[2], d[0], d[1], d[2]))
        self.nrm.extend(n * 6)
        self.col.extend(col * 6)
        self.flag.extend((float(flag),) * 6)
        self.aux.extend((a[3], b[3], c[3], a[3], c[3], d[3]))
        self.counts[what] = self.counts.get(what, 0) + 1


def _runs(row):
    """[(i0, i1, key), …] ช่วงค่าเท่ากันในแถว (ข้าม key < 0)"""
    out, i = [], 0
    for key, grp in groupby(row):
        n = sum(1 for _ in grp)
        if key >= 0:
            out.append((i, i + n, key))
        i += n
    return out


def build(cmap, caps=True):
    """เมชทั้งด่าน → dict(pos, nrm, col, flag, aux = array('f'), n_vert, n_tri, wall_y, counts, ms, bounds)
    caps=False ไม่ทำฝาบน VOID/WALL (มองจากระดับตาไม่เห็นอยู่แล้ว — เก็บไว้ให้ภาพ QA มุมสูง)"""
    t0 = time.perf_counter()
    nx, nz, cs, x0, z0 = cmap.nx, cmap.nz, cmap.cell, cmap.x0, cmap.z0
    K, H = cmap.kind, cmap.h
    hy = [(c - H0) * HQ for c in range(256)]
    codes = set(c for k, c in zip(K, H) if k == FLOOR or k == SITE)
    wall_y = WALL_TOP + max(0.0, max(hy[c] for c in codes) if codes else 0.0)
    ttab, ktab = [wall_y] * (5 * 256), [(_K_CAP if caps else -1)] * (5 * 256)
    for c in range(256):
        ttab[FLOOR * 256 + c] = ttab[SITE * 256 + c] = ttab[BOX * 256 + c] = hy[c]
        ktab[FLOOR * 256 + c], ktab[SITE * 256 + c], ktab[BOX * 256 + c] = c, _K_SITE + c, _K_BOX + c
    kind_rows = [K[j * nx:(j + 1) * nx] for j in range(nz)]
    top_rows, key_rows = [], []
    for j in range(nz):
        ix = [k * 256 + c for k, c in zip(kind_rows[j], H[j * nx:(j + 1) * nx])]
        top_rows.append([ttab[q] for q in ix])
        key_rows.append([ktab[q] for q in ix])
    m = _Mesh()
    up = (0.0, 1.0, 0.0)
    # ── หน้าแนวนอน: พื้น / ไซต์ / หลังกล่อง / ฝากำแพง ──
    opened = {}

    def emit_h(run, ja, jb):
        i0, i1, key = run
        xa, xb, za, zb = x0 + i0 * cs, x0 + i1 * cs, z0 + ja * cs, z0 + jb * cs
        if key == _K_CAP:
            y, col, fl, what = wall_y, _C_CAP, F_CAP | F_WALL, "cap"
        elif key >= _K_BOX:
            y, col, fl, what = hy[key - _K_BOX], _C_BOXTOP, F_BOX, "box_top"
        elif key >= _K_SITE:
            y = hy[key - _K_SITE]
            col, fl, what = floor_rgb(y, True), F_GRID | F_SITE, "site"
        else:
            y = hy[key]
            col, fl, what = floor_rgb(y), F_GRID, "floor"
        m.quad((xa, y, za, 0.0), (xb, y, za, 0.0), (xb, y, zb, 0.0), (xa, y, zb, 0.0), up, col, fl, what)

    for j in range(nz + 1):
        runs = set(_runs(key_rows[j])) if j < nz else set()
        for r in [r for r in opened if r not in runs]:
            emit_h(r, opened.pop(r), j)
        for r in runs:
            if r not in opened:
                opened[r] = j
    # ── หน้าแนวตั้ง: รอยต่อระหว่างแถว (ระนาบ z) และระหว่างคอลัมน์ (ระนาบ x — ใช้กริดสลับแกน) ──
    out_kind = bytes([VOID])

    def vfaces(tops, kinds, axis):
        L, n_al = len(tops), len(tops[0])
        OUT, OUTK = [wall_y] * n_al, out_kind * n_al
        for l in range(L + 1):
            A, KA = (tops[l - 1], kinds[l - 1]) if l > 0 else (OUT, OUTK)
            B, KB = (tops[l], kinds[l]) if l < L else (OUT, OUTK)
            diffs = [i for i, (a, b) in enumerate(zip(A, B)) if a != b]
            run = None
            for i in diffs + [None]:
                if i is not None:
                    a, b = A[i], B[i]
                    attr = (b, a, 1, _MATOF[KA[i]]) if a > b else (a, b, -1, _MATOF[KB[i]])
                    if run is not None and run[1] == i and run[2] == attr:
                        run[1] = i + 1
                        continue
                if run is not None:
                    emit_v(axis, l, run[0], run[1], *run[2])
                run = [i, i + 1, attr] if i is not None else None

    def emit_v(axis, l, a0, a1, lo, hi, dr, mat):
        p = (x0 if axis == "x" else z0) + l * cs
        q0, q1 = (z0 if axis == "x" else x0) + a0 * cs, (z0 if axis == "x" else x0) + a1 * cs
        hgt = hi - lo
        if mat == _MAT_WALL:
            col, fl, what = _C_WALL, F_WALL, "wall"
        elif mat == _MAT_BOX:
            col, fl, what = _C_BOXSIDE, F_BOX, "box_side"
        else:
            col = tuple(v * 0.78 for v in floor_rgb(hi, mat == _MAT_SITE))
            fl, what = F_LEDGE | (F_SITE if mat == _MAT_SITE else 0), "ledge"
        if axis == "z":
            n = (0.0, 0.0, float(dr))
            m.quad((q0, lo, p, 0.0), (q1, lo, p, 0.0), (q1, hi, p, hgt), (q0, hi, p, hgt), n, col, fl, what)
        else:
            n = (float(dr), 0.0, 0.0)
            m.quad((p, lo, q0, 0.0), (p, lo, q1, 0.0), (p, hi, q1, hgt), (p, hi, q0, hgt), n, col, fl, what)
        m.vq.append((axis, l, a0, a1, lo, hi, dr))

    vfaces(top_rows, kind_rows, "z")
    vfaces([list(c) for c in zip(*top_rows)], [bytes(c) for c in zip(*kind_rows)], "x")
    nv = len(m.pos) // 3
    return {"pos": m.pos, "nrm": m.nrm, "col": m.col, "flag": m.flag, "aux": m.aux, "n_vert": nv, "n_tri": nv // 3,
            "wall_y": wall_y, "counts": m.counts, "ms": (time.perf_counter() - t0) * 1000.0, "_vq": m.vq,
            "bounds": (x0, z0, x0 + nx * cs, z0 + nz * cs)}


def interleave(mesh):
    """array('f') แบบสลับต่อจุดยอดตาม FORMAT/ATTRS (vbo เดียว: ctx.buffer(interleave(mesh)))"""
    nv = mesh["n_vert"]
    out = array("f", bytes(44 * nv))                  # 11 float ต่อจุดยอด — เติมทีละคอลัมน์ด้วย slice ก้าว 11 (ระดับ C)
    for base, src in ((0, mesh["pos"]), (3, mesh["nrm"]), (6, mesh["col"])):
        for k in range(3):
            out[base + k::11] = src[k::3]
    out[9::11] = mesh["flag"]
    out[10::11] = mesh["aux"]
    return out


# ── มินิแมพ ──
def _cell_rgba(kind, code, edge):
    if kind == VOID:
        return b"\x00\x00\x00\x00"
    if kind == WALL or edge:
        return b"\xf0\xf0\xf0\xff"                    # เส้นขอบขาวแบบมินิแมพเกม (ขอบติด VOID / กำแพงบาง)
    y = (code - H0) * HQ
    L = floor_lum(y)
    if kind == BOX:
        v = int(min(255.0, L + 48))
        return bytes((v, v, v, 255))
    if kind == SITE:
        return bytes((int(min(255.0, L + 34)), int(min(255.0, L + 34)), int(L), 255))
    return bytes((int(L), int(L), int(L), 255))


def minimap_rgba(cmap, px):
    """ภาพมินิแมพ (w, h, bytes RGBA แถวบนก่อน) ด้านยาว = px พิกเซล — north-up: บน = +z, ขวา = +x (§1 minimap)
    พื้นไล่เฉดตามความสูง (สูง = สว่าง), ไซต์เขียวมะกอก, กล่องสว่างกว่าพื้น, ขอบติด VOID ขาว, VOID โปร่งใส
    pure python ~0.1–0.3 วิที่ 512 px บนด่าน 600² — สร้างครั้งเดียวต่อด่านแล้ว cache"""
    nx, nz = cmap.nx, cmap.nz
    s = float(px) / max(nx, nz)
    w, h = max(1, int(round(nx * s))), max(1, int(round(nz * s)))
    K, H = cmap.kind, cmap.h
    tab = [_cell_rgba(k, c, e) for k in range(5) for c in range(256) for e in (0, 1)]
    vo = [bytes(1 if k == VOID else 0 for k in K[j * nx:(j + 1) * nx]) for j in range(nz)]
    ones = b"\x01" * nx
    icol = [min(nx - 1, int((u + 0.5) / s)) for u in range(w)]
    need = sorted(set(min(nz - 1, int((v + 0.5) / s)) for v in range(h)))
    rows = {}
    for j in need:
        r0 = vo[j]
        edge = list(map(max, vo[j + 1] if j + 1 < nz else ones, vo[j - 1] if j > 0 else ones,
                        b"\x01" + r0[:-1], r0[1:] + b"\x01"))
        base = j * nx
        rows[j] = [tab[(k * 256 + c) * 2 + e] for k, c, e in zip(K[base:base + nx], H[base:base + nx], edge)]
    out = []
    for v in range(h):
        row = rows[min(nz - 1, int((v + 0.5) / s))]
        out.append(b"".join([row[i] for i in icol]))
    out.reverse()                                     # แถวบนของภาพ = z มาก (เหนือ)
    return w, h, b"".join(out)


def minimap_xy(cmap, w, h, x, z):
    """พิกัดโลก → พิกเซลบนภาพ minimap_rgba ขนาด w×h (float ; วาดลูกศรผู้เล่น/ศัตรู/spike)"""
    return ((x - cmap.x0) / (cmap.nx * cmap.cell) * w, (1.0 - (z - cmap.z0) / (cmap.nz * cmap.cell)) * h)


# ─────────────────────────── สีประจำย่าน (A/B/C/Mid/spawn) ───────────────────────────
# ผนัง/พื้นแต่ละย่านสีต่างกันแบบแผนที่จริง (ในเกมแต่ละไซต์/มิดมีโทนวัสดุของตัวเอง) — ไม่ใช้ texture ของ Riot: สีจับจาก callout
# ของด่าน (ชื่อขึ้นต้น A/B/C/Mid/Attacker/Defender) แบ่งพื้นที่ด้วยระยะเดินบนบล็อก 1 ม. (BFS หลายต้นทาง — เส้นแบ่งย่านอยู่ที่
# ช่องทางเดิน ไม่ตัดทะลุกำแพง) ; shader สุ่มแบบ LINEAR → สีไล่เปลี่ยนนุ่ม ~1 ม. ตรงรอยต่อย่าน
REGION_BLOCK = 4                                      # ช่องต่อบล็อก (4 × 0.25 = 1 ม.)
REGION_RGB = {                                        # โทนปูน/ทาสี (คูณกับความสว่างผนังใน shader) — ต่างกันพอแยกย่านได้ ไม่ฉูดฉาด
    "A": (0.93, 0.80, 0.64),                          # ทรายอุ่น/ดินเผา
    "B": (0.70, 0.80, 0.92),                          # ฟ้าหม่น
    "C": (0.76, 0.88, 0.70),                          # เขียวเสจ
    "M": (0.86, 0.80, 0.90),                          # มิด: ม่วงเทาอ่อน
    "T": (0.92, 0.70, 0.62),                          # spawn ฝั่งบุก: อิฐแดงหม่น
    "D": (0.64, 0.86, 0.84),                          # spawn ฝั่งกัน: เขียวน้ำทะเล
    "?": (0.86, 0.85, 0.82),                          # ไม่มีข้อมูล = ปูนเดิม
}


def _region_of(name):
    s = (name or "").strip().lower()
    if s.startswith("attacker"):
        return "T"
    if s.startswith("defender"):
        return "D"
    if s.startswith("mid"):
        return "M"
    for k in ("a", "b", "c"):
        if s.startswith(k + " ") or s == k:
            return k.upper()
    return "?"


def region_seeds(cmap):
    """[(x, z, ย่าน)] ต้นทางของสีย่าน: callout ที่รู้ย่าน + ศูนย์ไซต์ + spawn ; ด่านไม่มีเมทาดาทาเลย = []"""
    out = []
    for c in getattr(cmap, "calls", None) or ():
        try:
            r = _region_of(c[0])
            if r != "?":
                out.append((float(c[1]), float(c[2]), r))
        except (TypeError, ValueError, IndexError):
            continue
    for name, st in (getattr(cmap, "sites", None) or {}).items():
        c = st.get("c") if isinstance(st, dict) else None
        if c and str(name).upper() in ("A", "B", "C"):
            out.append((float(c[0]), float(c[1]), str(name).upper()))
    for side, r in (("atk", "T"), ("def", "D")):
        s = (getattr(cmap, "spawns", None) or {}).get(side)
        if s:
            out.append((float(s[0]), float(s[1]), r))
    return out


def region_rgba(cmap):
    """(bw, bh, bytes RGBA) ต่อบล็อก REGION_BLOCK ช่อง — RGB = สีย่าน (REGION_RGB), A = 255 บล็อกที่มีพื้นเดินได้ / 0 ไม่มี
    ย่านของบล็อก = ต้นทางที่ใกล้สุดตามระยะเดินบนบล็อก (BFS 8 ทิศ) ; บล็อกทึบล้วนได้สีของบล็อกเดินได้ที่ติดกัน (ผนังด้านนั้น)"""
    B = REGION_BLOCK
    nx, nz = cmap.nx, cmap.nz
    bw, bh = (nx + B - 1) // B, (nz + B - 1) // B
    K = cmap.kind
    walk = bytearray(bw * bh)
    for j in range(nz):
        row = K[j * nx:(j + 1) * nx]
        bj = (j // B) * bw
        for i, k in enumerate(row):
            if k == FLOOR or k == SITE or k == BOX:
                walk[bj + i // B] = 1
    names = list(REGION_RGB)
    reg = [-1] * (bw * bh)
    frontier = []
    for x, z, r in region_seeds(cmap):
        bi = int((x - cmap.x0) / cmap.cell) // B
        bj = int((z - cmap.z0) / cmap.cell) // B
        if 0 <= bi < bw and 0 <= bj < bh:
            q = bj * bw + bi
            if reg[q] < 0:
                reg[q] = names.index(r)
                frontier.append(q)
    nb = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    while frontier:                                   # BFS หลายต้นทางพร้อมกัน (ระดับต่อระดับ = ใกล้สุดก่อน)
        nxt = []
        for q in frontier:
            qi, qj = q % bw, q // bw
            for di, dj in nb:
                a, b = qi + di, qj + dj
                if 0 <= a < bw and 0 <= b < bh:
                    p = b * bw + a
                    if reg[p] < 0 and walk[p]:
                        reg[p] = reg[q]
                        nxt.append(p)
        frontier = nxt
    fill = names.index("?")
    out = bytearray(4 * bw * bh)
    for q in range(bw * bh):
        r = reg[q]
        if r < 0:                                     # ทึบ/ไปไม่ถึง: ยืมจากบล็อกข้างที่มีย่าน (ผนังรับสีฝั่งที่มันหันไป)
            qi, qj = q % bw, q // bw
            for di, dj in nb:
                a, b = qi + di, qj + dj
                if 0 <= a < bw and 0 <= b < bh and reg[b * bw + a] >= 0 and walk[b * bw + a]:
                    r = reg[b * bw + a]
                    break
        c = REGION_RGB[names[r if r >= 0 else fill]]
        out[4 * q:4 * q + 4] = bytes((int(c[0] * 255 + 0.5), int(c[1] * 255 + 0.5), int(c[2] * 255 + 0.5),
                                      255 if walk[q] else 0))
    return bw, bh, bytes(out)


# ─────────────────────────── หุ่นเอเจนต์ + ปืน + มือบุคคลที่หนึ่ง (pure) ───────────────────────────
# สัดส่วนจริง 1:1 ในกรอบ hitbox ของ guns.humanoid_zone (หัวทรงกลม r 0.14 @ 1.60, ลำตัวทรงกระบอก r 0.22 ช่วง 0.90–1.46,
# ขาแคปซูล r 0.17 ช่วง 0–0.90 ; หมอบ = ท่อนบนลด 0.55) — ทุกส่วนของตัว (ไม่นับปืน/แขนท่อนล่าง/มือที่ยื่นไปจับปืน ซึ่งเกมจริงก็
# ยื่นพ้นตัว) อยู่นอก hitbox ไม่เกิน AGENT_OUT_TOL และ hitbox ที่มองไม่เห็นหนาไม่เกิน ~AGENT_IN_TOL (clutch_view --check วัดจริง)
# จุดยอด 8 float: pos 3, nrm 3, bone (= กระดูก + 32·var), mat — ตรงรูปแบบเมชหุ่นเดิมของ clutchgl (k = กระดูก 0/1)
AGENT_OUT_TOL = 0.035          # ม. — ผิวตัวยื่นพ้น hitbox สูงสุดที่ยอม (selftest ตรวจจุดยอดทุกท่า)
AGENT_IN_TOL = 0.06            # ม. — ความหนา hitbox ที่ไม่มีภาพทับ (มองด้านข้าง: ขาสองข้างแคบกว่าแคปซูลขาอ้วน 0.34 ม.)
B_STATIC, B_UPPER, B_ARMS, B_PELVIS = 0, 1, 2, 3
B_THIGH_L, B_SHIN_L, B_KNEE_L, B_FOOT_L = 4, 5, 6, 7
B_THIGH_R, B_SHIN_R, B_KNEE_R, B_FOOT_R = 8, 9, 10, 11
# วัสดุ (เลขเดียวกับ clutchgl: 0–7 เดิม)
M_SUIT, M_HEAD, M_SKIN, M_GUN, M_SPIKE, M_LIGHT, M_BAND, M_LEGS = 0, 1, 2, 3, 4, 5, 6, 7
M_ARMOR, M_GLOVE, M_BOOT, M_GUNHI, M_SLEEVE = 8, 9, 10, 12, 13
# อาวุธ: id ใน instance (1..6) ; var 7/8/9 = ชุดแขนปืนยาว/สไนเปอร์/ปืนพก ; var 10 = spike (viewmodel)
WEAPON_ID = {"vandal": 1, "phantom": 2, "operator": 3, "sheriff": 4, "ghost": 5, "classic": 6}
V_RIFLE_ARMS, V_SNIPER_ARMS, V_PISTOL_ARMS, V_SPIKE = 7, 8, 9, 10
ARMS_OF = {1: V_RIFLE_ARMS, 2: V_RIFLE_ARMS, 3: V_SNIPER_ARMS, 4: V_PISTOL_ARMS, 5: V_PISTOL_ARMS, 6: V_PISTOL_ARMS}
# โครงขา (ม., ท่ายืน) — สะโพก ±HIP_X สูง HIP_Y, ข้อเท้า ±ANKLE_X สูง ANKLE_Y ; ขายืนตรง = THIGH_L + SHIN_L = HIP_Y − ANKLE_Y
HIP_X, HIP_Y, HIP_Z = 0.088, 0.86, -0.01
ANKLE_X, ANKLE_Y = 0.064, 0.08
THIGH_L, SHIN_L = 0.40, 0.38
KNEE_R = 0.066                 # รัศมีสนับเข่า (ด้านหน้า)
CROUCH_KNEE_OUT = 0.22         # เข่าแบะออกด้านข้างตอนหมอบ (สัดส่วนของทิศ pole)
FOOT = (0.042, -0.065, 0.128)  # รองเท้า: ครึ่งกว้าง, ส้น z, ปลายเท้า z (เล็กกว่าเท้าคนจริงนิด ให้อยู่ในแคปซูลขาตอนยืน)
STRIDE_WALK, STRIDE_RUN = 0.045, 0.065   # ม. — เท้าแกว่งหน้า/หลังสุด (ถูกจำกัดด้วยแคปซูลขา r 0.17 — ไม่ใช่ก้าวจริง ~0.7 ม.)
FOOT_LIFT_WALK, FOOT_LIFT_RUN = 0.05, 0.10   # ม. — ยกเท้าช่วงแกว่ง (เข่างอให้อ่านออกว่าเดิน/วิ่ง)
STEP_LEN = 0.75                # ม. ต่อครึ่งรอบก้าว (จังหวะเท้า ~3.6 ก้าว/วิที่ความเร็ววิ่ง 5.4)
SH_PIV = (0.0, 1.40, 0.0)      # จุดหมุนก้ม/เงยของแขน+ปืน (กลางไหล่)
RELOAD_PITCH, RELOAD_YAW = -0.50, 0.28   # เรเดียน — ท่ารีโหลด: ปืนเอียงลงและหันเข้าหาอก


def _nrm(v):
    L = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / L, v[1] / L, v[2] / L) if L > 1e-12 else (0.0, 1.0, 0.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _tri(out, a, b, c, hint):
    """สามเหลี่ยม (จุด = (pos, nrm, bone, mat)) เรียงให้ cross(b−a, c−a)·hint < 0 (ทวนเข็มเมื่อมองจากด้านนอก — กติกาเดียวกับ
    เมชแมพ/หุ่นเดิม) ; ทิ้งสามเหลี่ยมเสื่อม"""
    cr = _cross(_sub(b[0], a[0]), _sub(c[0], a[0]))
    if _dot(cr, cr) < 1e-18:
        return
    if _dot(cr, hint) > 0.0:
        b, c = c, b
    for p, n, k, m in (a, b, c):
        out.extend((p[0], p[1], p[2], n[0], n[1], n[2], k, m))


def _loft(out, rings, bone, mat, caps=(True, True), nspace=None):
    """ต่อวงแหวน (list ของ list จุด — จำนวนจุดเท่ากันทุกวง, วงปิด) เป็นผิวเรียบ ; normal ต่อจุดคิดจากเพื่อนบ้าน (ผิวโค้งนุ่ม — ขอบ
    ไฮไลต์ศัตรูต่อเนื่อง) หันออกจากแกน ; caps = ปิดวงแรก/วงสุดท้ายด้วยพัด ; nspace = วงแหวนชุดเดียวกันในพิกัดที่ใช้คิด normal
    (ขาใช้ความยาวกระดูกเป็นสัดส่วน 0..1 — คิด normal จากความยาวจริง)"""
    R = nspace or rings
    nr, ns = len(rings), len(rings[0])
    ctr = [_mul(tuple(sum(p[i] for p in ring) for i in range(3)), 1.0 / ns) for ring in R]
    N = []
    for i in range(nr):
        row = []
        for j in range(ns):
            tu = _sub(R[i][(j + 1) % ns], R[i][j - 1])
            tv = _sub(R[min(nr - 1, i + 1)][j], R[max(0, i - 1)][j])
            n = _nrm(_cross(tv, tu))
            if _dot(n, _sub(R[i][j], ctr[i])) < 0:
                n = _mul(n, -1.0)
            row.append(n)
        N.append(row)
    for i in range(nr - 1):
        for j in range(ns):
            j1 = (j + 1) % ns
            a, b = (rings[i][j], N[i][j], bone, mat), (rings[i][j1], N[i][j1], bone, mat)
            c, d = (rings[i + 1][j1], N[i + 1][j1], bone, mat), (rings[i + 1][j], N[i + 1][j], bone, mat)
            h = _add(_add(a[1], b[1]), _add(c[1], d[1]))
            _tri(out, a, b, c, h)
            _tri(out, a, c, d, h)
    for i, on in ((0, caps[0]), (nr - 1, caps[1])):
        if not on:
            continue
        ax = _nrm(_sub(ctr[0], ctr[-1])) if i == 0 else _nrm(_sub(ctr[-1], ctr[0]))
        if nr == 1:
            ax = (0.0, 1.0, 0.0)
        c = (_mul(tuple(sum(p[q] for p in rings[i]) for q in range(3)), 1.0 / ns), ax, bone, mat)
        for j in range(ns):
            _tri(out, c, (rings[i][j], ax, bone, mat), (rings[i][(j + 1) % ns], ax, bone, mat), ax)


def _spow(v, e):
    return math.copysign(abs(v) ** e, v)


def _sring(y, a, b, ns, n_exp=2.6, rmax=None, cx=0.0, cz=0.0):
    """วงแหวนซูเปอร์วงรีระดับ y (ครึ่งกว้าง a ตาม x, ครึ่งหนา b ตาม z) — θ 0 = หน้า (+z) ; rmax = ตัดรัศมีไม่ให้เกิน"""
    out = []
    for j in range(ns):
        t = 2 * math.pi * j / ns
        x, z = a * _spow(math.sin(t), 2.0 / n_exp), b * _spow(math.cos(t), 2.0 / n_exp)
        r = math.hypot(x, z)
        if rmax is not None and r > rmax:
            x, z = x * rmax / r, z * rmax / r
        out.append((x + cx, y, z + cz))
    return out


def _ellipsoid(out, c, rad, bone, mat, nr=12, ns=24, la=(-math.pi / 2, math.pi / 2)):
    """ทรงรี ศูนย์ c รัศมี (rx, ry, rz) ช่วงละติจูด la — normal จาก gradient (ผิวเรียบ)"""
    def pt(i, j):
        a = la[0] + (la[1] - la[0]) * i / nr
        o = 2 * math.pi * j / ns
        u = (math.cos(a) * math.sin(o), math.sin(a), math.cos(a) * math.cos(o))
        p = (c[0] + rad[0] * u[0], c[1] + rad[1] * u[1], c[2] + rad[2] * u[2])
        n = _nrm((u[0] / rad[0], u[1] / rad[1], u[2] / rad[2]))
        return (p, n, bone, mat)
    for i in range(nr):
        for j in range(ns):
            a, b, cc, d = pt(i, j), pt(i, j + 1), pt(i + 1, j + 1), pt(i + 1, j)
            h = _add(_add(a[1], b[1]), _add(cc[1], d[1]))
            _tri(out, a, b, cc, h)
            _tri(out, a, cc, d, h)


def _frame(u):
    """แกนตั้งฉากกับทิศ u (หน่วย): (side, fwd) — side อิง +x (หรือ +y ถ้า u ขนาน x)"""
    ref = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
    s = _nrm(_sub(ref, _mul(u, _dot(u, ref))))
    return s, _cross(u, s)


def _tube(out, A, B, radii, bone, mat, ns=12, caps=(True, True)):
    """ท่อจาก A ไป B ; radii = [(t, rx, rz)] ตามความยาว (rx ตามแกน side, rz ตามแกน fwd ของ _frame)"""
    u = _nrm(_sub(B, A))
    s, f = _frame(u)
    rings = []
    for t, rx, rz in radii:
        c = _add(A, _mul(_sub(B, A), t))
        rings.append([_add(c, _add(_mul(s, rx * math.sin(2 * math.pi * j / ns)), _mul(f, rz * math.cos(2 * math.pi * j / ns))))
                      for j in range(ns)])
    _loft(out, rings, bone, mat, caps)


def _bone_tube(out, radii, L, bone, mat, ns=14):
    """ท่อขาในพิกัดกระดูก: y = −t (สัดส่วน 0 ข้อบน → 1 ข้อล่าง), x/z = ม. ; shader วางตามข้อต่อจริงของแต่ละเฟรม
    (normal คิดจากความยาวจริง L ของกระดูก)"""
    rings, nsp = [], []
    for t, rx, rz in radii:
        r = [(rx * math.sin(2 * math.pi * j / ns), -t, rz * math.cos(2 * math.pi * j / ns)) for j in range(ns)]
        rings.append(r)
        nsp.append([(p[0], p[1] * L, p[2]) for p in r])
    _loft(out, rings, bone, mat, (True, True), nspace=nsp)


def _box(out, x0, x1, y0, y1, z0, z1, bone, mat, xf=None):
    """กล่องหน้าเรียบ ; xf(p) = ฟังก์ชันแปลงจุด (เช่นเอียงแม็กกาซีน) — normal คิดใหม่จากหน้าหลังแปลง"""
    P = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    if xf is not None:
        P = [xf(p) for p in P]
    ctr = _mul(tuple(sum(p[i] for p in P) for i in range(3)), 1.0 / 8)
    for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        v = [P[i] for i in q]
        n = _nrm(_cross(_sub(v[1], v[0]), _sub(v[3], v[0])))
        fc = _mul(_add(_add(v[0], v[1]), _add(v[2], v[3])), 0.25)
        if _dot(n, _sub(fc, ctr)) < 0:
            n = _mul(n, -1.0)
        a, b, c, d = ((p, n, bone, mat) for p in v)
        _tri(out, a, b, c, n)
        _tri(out, a, c, d, n)


def _zcyl(out, cx, cy, z0, z1, r, bone, mat, ns=12, xf=None):
    """ทรงกระบอกตามแกน z (ลำกล้อง/ท่อเก็บเสียง/กล้อง) — ผิวข้างเรียบ + ฝาสองข้าง"""
    rings = []
    for z in (z0, z1):
        rings.append([(cx + r * math.sin(2 * math.pi * j / ns), cy + r * math.cos(2 * math.pi * j / ns), z)
                      for j in range(ns)])
    if xf is not None:
        rings = [[xf(p) for p in ring] for ring in rings]
    _loft(out, rings, bone, mat, (True, True))


def gun_prims(weapon_id):
    """ชิ้นส่วนปืนในพิกัดปืน (ม.): จุดกำเนิด = บนด้ามจับ (ง่ามมือขวา), +z = ทิศลำกล้อง, +y = บน
    → [(ชนิด, พารามิเตอร์, mat)] ; ชนิด box (x0,x1,y0,y1,z0,z1), slant (x0,x1,y_top,y_bot,z0,z1,shear dz/dy), zcyl (cx,cy,z0,z1,r)
    ขนาดใกล้ปืนจริงที่ต้นแบบ (Vandal ~ AK 0.96 ม., Phantom ~ M4 0.92, Operator ~ 1.26, Sheriff ลูกโม่ลำกล้องยาว ~0.3,
    Ghost มีท่อเก็บเสียง ~0.34, Classic ~0.2)"""
    G, H = M_GUN, M_GUNHI
    if weapon_id == 2:                                   # Phantom
        return [("box", (-0.020, 0.020, -0.060, 0.030, -0.34, -0.12), G), ("box", (-0.024, 0.024, -0.030, 0.055, -0.13, 0.20), G),
                ("box", (-0.014, 0.014, 0.055, 0.078, -0.08, 0.17), H), ("slant", (-0.016, 0.016, -0.005, -0.105, -0.035, 0.015, -0.25), G),
                ("slant", (-0.017, 0.017, -0.030, -0.170, 0.075, 0.135, 0.10), H), ("box", (-0.027, 0.027, -0.030, 0.050, 0.20, 0.40), G),
                ("zcyl", (0.0, 0.012, 0.40, 0.585, 0.021), H)]
    if weapon_id == 3:                                   # Operator
        return [("box", (-0.024, 0.024, -0.095, 0.030, -0.44, -0.14), G), ("box", (-0.018, 0.018, 0.030, 0.060, -0.36, -0.20), H),
                ("box", (-0.028, 0.028, -0.030, 0.050, -0.15, 0.24), G), ("slant", (-0.016, 0.016, -0.005, -0.105, -0.035, 0.015, -0.25), G),
                ("box", (-0.020, 0.020, -0.120, -0.030, 0.05, 0.14), G), ("box", (-0.024, 0.024, -0.035, 0.040, 0.24, 0.46), G),
                ("zcyl", (0.0, 0.010, 0.24, 0.80, 0.014), G), ("zcyl", (0.0, 0.010, 0.76, 0.84, 0.021), H),
                ("box", (-0.010, 0.010, 0.050, 0.075, -0.05, -0.01), G), ("box", (-0.010, 0.010, 0.050, 0.075, 0.15, 0.19), G),
                ("zcyl", (0.0, 0.098, -0.10, 0.24, 0.024), H), ("zcyl", (0.0, 0.098, 0.18, 0.27, 0.031), H),
                ("zcyl", (0.0, 0.098, -0.14, -0.07, 0.029), H)]
    if weapon_id == 4:                                   # Sheriff
        return [("slant", (-0.017, 0.017, 0.000, -0.110, -0.045, 0.000, -0.32), H), ("box", (-0.017, 0.017, -0.010, 0.050, -0.030, 0.050), G),
                ("zcyl", (0.0, 0.022, 0.000, 0.060, 0.025), G), ("box", (-0.012, 0.012, 0.012, 0.052, 0.050, 0.235), G),
                ("box", (-0.005, 0.005, 0.040, 0.072, -0.055, -0.020), G), ("box", (-0.004, 0.004, 0.052, 0.064, 0.215, 0.230), G)]
    if weapon_id == 5:                                   # Ghost
        return [("slant", (-0.016, 0.016, -0.005, -0.110, -0.050, 0.000, -0.20), G), ("box", (-0.016, 0.016, 0.000, 0.038, -0.055, 0.130), H),
                ("box", (-0.014, 0.014, -0.018, 0.000, -0.030, 0.115), G), ("zcyl", (0.0, 0.019, 0.130, 0.290, 0.018), G)]
    if weapon_id == 6:                                   # Classic
        return [("slant", (-0.016, 0.016, -0.005, -0.105, -0.050, 0.000, -0.20), G), ("box", (-0.015, 0.015, 0.000, 0.036, -0.055, 0.140), H),
                ("box", (-0.013, 0.013, -0.018, 0.000, -0.030, 0.120), G)]
    return [("box", (-0.020, 0.020, -0.070, 0.030, -0.36, -0.13), H), ("box", (-0.025, 0.025, -0.030, 0.050, -0.14, 0.22), G),   # Vandal
            ("box", (-0.020, 0.020, 0.050, 0.065, -0.10, 0.18), G), ("slant", (-0.016, 0.016, -0.005, -0.105, -0.035, 0.015, -0.25), G),
            ("slant", (-0.018, 0.018, -0.030, -0.190, 0.100, 0.170, 0.35), G), ("box", (-0.024, 0.024, -0.020, 0.045, 0.22, 0.42), H),
            ("zcyl", (0.0, 0.055, 0.22, 0.44, 0.012), G), ("zcyl", (0.0, 0.020, 0.42, 0.60, 0.011), G),
            ("box", (-0.006, 0.006, 0.020, 0.078, 0.540, 0.560), G), ("box", (-0.012, 0.012, 0.050, 0.075, 0.080, 0.100), G)]


def gun_extent(weapon_id):
    """(z หลังสุด, z หน้าสุด, (x, y, z) ปลายลำกล้อง) ในพิกัดปืน"""
    zs, tip = [], None
    for kind, p, _m in gun_prims(weapon_id):
        if kind == "zcyl":
            zs += [p[2], p[3]]
            if tip is None or p[3] > tip[2] or (p[3] == tip[2] and p[1] < tip[1]):
                if p[4] < 0.03:                         # ท่อเล็ก = ลำกล้อง/ท่อเก็บเสียง (ไม่ใช่กล้องเล็ง)
                    tip = (p[0], p[1], p[3])
        else:
            zs += [p[4], p[5]]
    zmax = max(zs)
    if tip is None or tip[2] < zmax - 1e-6:
        tip = (0.0, 0.03, zmax)
    return min(zs), zmax, tip


def _emit_gun(out, weapon_id, place, bone, var, ns=10):
    """ปืนลง out: place(p) แปลงพิกัดปืน → พิกัดหุ่น/กล้อง ; bone += 32·var (เลือกแสดงตามอาวุธใน shader)"""
    bv = float(bone + 32 * var)
    for kind, p, m in gun_prims(weapon_id):
        if kind == "box":
            _box(out, *p, bv, m, xf=place)
        elif kind == "slant":
            x0, x1, yt, yb, z0, z1, sh = p
            _box(out, x0, x1, yb, yt, z0, z1, bv, m,
                 xf=lambda q, yt=yt, sh=sh: place((q[0], q[1], q[2] + (q[1] - yt) * sh)))
        else:
            _zcyl(out, p[0], p[1], p[2], p[3], p[4], bv, m, ns=ns, xf=place)


# ท่าแขน 3rd person ต่อชุด (พิกัดหุ่นท่ายืน, pitch 0): ด้ามปืน (จุดกำเนิดปืน), ไหล่→ศอก→ข้อมือ ขวา/ซ้าย, ถุงมือซ้าย (ใต้การ์ดมือ)
_ARM_POSE = {
    V_RIFLE_ARMS: {"grip": (0.085, 1.425, 0.30),
                   "R": ((0.175, 1.39, 0.0), (0.215, 1.20, 0.15), (0.100, 1.335, 0.265)),
                   "L": ((-0.175, 1.39, 0.0), (-0.170, 1.23, 0.28), (0.055, 1.390, 0.540)), "lh": (0.070, 1.400, 0.605)},
    V_SNIPER_ARMS: {"grip": (0.085, 1.400, 0.32),
                    "R": ((0.175, 1.39, 0.0), (0.215, 1.19, 0.16), (0.100, 1.310, 0.285)),
                    "L": ((-0.175, 1.39, 0.0), (-0.170, 1.22, 0.30), (0.050, 1.365, 0.580)), "lh": (0.068, 1.375, 0.640)},
    V_PISTOL_ARMS: {"grip": (0.040, 1.400, 0.44),
                    "R": ((0.175, 1.39, 0.0), (0.170, 1.28, 0.22), (0.058, 1.350, 0.405)),
                    "L": ((-0.175, 1.39, 0.0), (-0.120, 1.27, 0.22), (0.016, 1.340, 0.405)), "lh": (0.022, 1.345, 0.445)},
}
_GUNS_OF = {V_RIFLE_ARMS: (1, 2), V_SNIPER_ARMS: (3,), V_PISTOL_ARMS: (4, 5, 6)}


def agent_mesh(ns=28):
    """หุ่นเอเจนต์ (ท่ายืนในพิกัดท้องถิ่น: x ขวา, y ขึ้น, z หน้า, เท้าที่ y 0) → array('f') 8 float/จุดยอด
    กระดูก: B_UPPER ลำตัว/คอ/หัว (ลดตามหมอบเท่า hitbox) · B_ARMS แขน+ปืน (ลดตามหมอบ + ก้ม/เงยรอบ SH_PIV + ท่ารีโหลด)
    · B_PELVIS สะโพก (ตามความสูงสะโพกจาก leg_pose) · ต้นขา/หน้าแข้ง (ท่อในพิกัดกระดูก วางระหว่างข้อต่อ) · เข่า/เท้า (ตามข้อต่อ)"""
    out = array("f")
    U = float(B_UPPER)
    # ลำตัว: ซูเปอร์วงรี (เต็มกรอบทรงกระบอก r 0.22 ด้านหน้า-หลังบางกว่าเล็กน้อย) + ไหล่มนปิดรอบคอ
    tor = [(0.900, 0.186, 0.168), (0.960, 0.190, 0.172), (1.050, 0.198, 0.180), (1.150, 0.208, 0.190),
           (1.250, 0.214, 0.196), (1.340, 0.216, 0.196), (1.400, 0.212, 0.188), (1.440, 0.196, 0.170),
           (1.462, 0.150, 0.125), (1.470, 0.075, 0.066)]
    _loft(out, [_sring(y, a, b, ns, rmax=0.226) for y, a, b in tor], U, M_SUIT)
    _tube(out, (0.0, 1.42, -0.005), (0.0, 1.52, 0.0), [(0.0, 0.056, 0.056), (1.0, 0.052, 0.052)], U, M_SKIN, ns=14)
    _ellipsoid(out, (0.0, 1.60, 0.004), (0.128, 0.140, 0.134), U, M_HEAD, nr=14, ns=ns)
    # สะโพก/เชิงกราน
    pel = [(0.735, 0.140, 0.112), (0.770, 0.163, 0.130), (0.850, 0.174, 0.140), (0.930, 0.178, 0.146), (0.960, 0.170, 0.140)]
    _loft(out, [_sring(y, a, b, ns, rmax=0.19) for y, a, b in pel], float(B_PELVIS), M_LEGS)
    for th, sh, kn, ft, sx in ((B_THIGH_L, B_SHIN_L, B_KNEE_L, B_FOOT_L, -1.0), (B_THIGH_R, B_SHIN_R, B_KNEE_R, B_FOOT_R, 1.0)):
        _bone_tube(out, [(-0.06, 0.072, 0.092), (0.0, 0.084, 0.110), (0.18, 0.085, 0.114), (0.55, 0.076, 0.102),
                         (0.88, 0.064, 0.084), (1.04, 0.058, 0.072)], THIGH_L, float(th), M_LEGS)
        _bone_tube(out, [(-0.04, 0.056, 0.072), (0.05, 0.061, 0.088), (0.32, 0.064, 0.100), (0.72, 0.055, 0.080),
                         (1.02, 0.048, 0.062)], SHIN_L, float(sh), M_LEGS)
        _ellipsoid(out, (0.0, 0.0, 0.010), (0.058, 0.062, KNEE_R - 0.010), float(kn), M_ARMOR, nr=8, ns=16)
        F = float(ft)
        _tube(out, (0.0, -0.03, -0.005), (0.0, 0.12, -0.005), [(0.0, 0.056, 0.072), (1.0, 0.052, 0.066)], F, M_BOOT, ns=14)
        _box(out, -FOOT[0], FOOT[0], -0.080, 0.025, FOOT[1], FOOT[2], F, M_BOOT,
             xf=lambda p: (p[0] * (0.85 if p[2] > 0.1 else 1.0), p[1] - (0.03 if p[1] > 0 and p[2] > 0.1 else 0.0), p[2]))
    # แขน + ปืน ต่อชุด (เลือกแสดงตามอาวุธใน shader)
    for var, pose in _ARM_POSE.items():
        bv = float(B_ARMS + 32 * var)
        for side in ("R", "L"):
            s, e, w = pose[side]
            _ellipsoid(out, s, (0.070, 0.068, 0.074), bv, M_ARMOR, nr=8, ns=16)
            _tube(out, s, e, [(0.0, 0.054, 0.054), (0.55, 0.050, 0.050), (1.0, 0.044, 0.044)], bv, M_SLEEVE, ns=12)
            _ellipsoid(out, e, (0.046, 0.046, 0.046), bv, M_SLEEVE, nr=6, ns=12)
            _tube(out, e, w, [(0.0, 0.043, 0.043), (0.6, 0.040, 0.038), (1.0, 0.034, 0.032)], bv, M_SLEEVE, ns=12)
        g = pose["grip"]
        _box(out, g[0] - 0.026, g[0] + 0.026, g[1] - 0.105, g[1] - 0.005, g[2] - 0.060, g[2] + 0.035, bv, M_GLOVE)   # มือขวากำด้าม
        lh = pose["lh"]
        _box(out, lh[0] - 0.028, lh[0] + 0.028, lh[1] - 0.045, lh[1] + 0.010, lh[2] - 0.050, lh[2] + 0.050, bv, M_GLOVE)
        for w in _GUNS_OF[var]:
            _emit_gun(out, w, lambda p, g=g: (p[0] + g[0], p[1] + g[1], p[2] + g[2]), B_ARMS, w)
    return out


def agent_grip(weapon_id):
    return _ARM_POSE[ARMS_OF.get(weapon_id, V_RIFLE_ARMS)]["grip"]


def agent_muzzle_local(weapon_id):
    """ปลายลำกล้องในพิกัดหุ่นท่ายืน pitch 0 (ก่อนหมุนรอบ SH_PIV)"""
    g = agent_grip(weapon_id)
    tip = gun_extent(weapon_id)[2]
    return (g[0] + tip[0], g[1] + tip[1], g[2] + tip[2])


def arms_xform(p, pitch=0.0, reload=0.0, drop=0.0, reach=None):
    """กระจก python ของ shader: จุดชุดแขน/ปืน (พิกัดหุ่นท่ายืน) → พิกัดหุ่นหลังหดปืน (z ≤ reach), ท่ารีโหลด, ก้ม/เงย, หมอบ"""
    x, y, z = p[0], p[1], p[2]
    if reach is not None:
        z = min(z, reach)
    x, y, z = x - SH_PIV[0], y - SH_PIV[1], z - SH_PIV[2]
    ry = RELOAD_YAW * reload                           # หันเข้าหาอก (รอบแกน y)
    cy, sy = math.cos(ry), math.sin(ry)
    x, z = x * cy - z * sy, x * sy + z * cy
    a = pitch + RELOAD_PITCH * reload                  # ก้ม/เงย (รอบแกน x) — +a = ปลายปืนขึ้น
    ca, sa = math.cos(a), math.sin(a)
    y, z = y * ca + z * sa, -y * sa + z * ca
    return (x + SH_PIV[0], y + SH_PIV[1] - drop, z + SH_PIV[2])


def _ik(H, A, Lt, Ls, pole):
    """ข้อเข่าจากสะโพก H ข้อเท้า A ความยาว Lt/Ls งอไปทาง pole — ยืดสุดแล้ว = เข่าอยู่บนเส้นตรง"""
    d = _sub(A, H)
    L = math.sqrt(_dot(d, d))
    if L < 1e-6:
        return _add(H, _mul(pole, Lt))
    u = _mul(d, 1.0 / L)
    L = min(L, Lt + Ls - 1e-6)
    a = (Lt * Lt - Ls * Ls + L * L) / (2 * L)
    h = math.sqrt(max(0.0, Lt * Lt - a * a))
    pp = _sub(pole, _mul(u, _dot(pole, u)))
    pl = math.sqrt(_dot(pp, pp))
    pp = _mul(pp, 1.0 / pl) if pl > 1e-9 else (0.0, 0.0, 1.0)
    return _add(_add(H, _mul(u, a)), _mul(pp, h))


def _knee_rmax(y, drop):
    """ระยะจากแกนตัวที่ศูนย์เข่ายื่นได้ (ผิวสนับเข่า ~KNEE_R) ให้ผิวไม่พ้น hitbox เกิน AGENT_OUT_TOL — ในช่วงทรงกระบอกลำตัว
    (หมอบ: ลำตัวลงมาถึงระดับเข่า) กว้างกว่าช่วงแคปซูลขา"""
    body = y >= 0.90 - drop - 0.01
    return (0.22 if body else 0.17) - KNEE_R + 0.6 * AGENT_OUT_TOL


def leg_pose(crouch=0.0, phase=0.0, amp=0.0, run=0.0, mdir=(0.0, 1.0)):
    """ข้อต่อขาในพิกัดหุ่น (ก่อนหมุน yaw): crouch 0..1, phase = จังหวะก้าว (เรเดียน), amp 0..1 = แรงก้าว (หยุด = 0),
    run 0..1 = ย่อง→วิ่ง, mdir = ทิศเดินในพิกัดหุ่น (x, z) หน่วย
    → (hip_y, hip_z, (เข่าซ้าย, ข้อเท้าซ้าย, เท้าซ้ายเงย), (ขวา …)) — ข้อเท้าแกว่งไม่เกิน STRIDE_* ให้เท้าอยู่ในแคปซูลขา ;
    ย่อตัว/ยกเท้าแล้วเข่าจะยื่นพ้นแคปซูลขา (r 0.17) → ย่อความยาวกระดูกที่เห็นลงพร้อมกันจนเข่าอยู่ในกรอบ (_knee_rmax)"""
    c = max(0.0, min(1.0, crouch))
    drop = 0.55 * c
    hip_y = HIP_Y - drop - 0.012 * amp * (0.5 - 0.5 * math.cos(2 * phase))
    hip_z = HIP_Z - 0.03 * c
    stride = (STRIDE_WALK + (STRIDE_RUN - STRIDE_WALK) * run) * (1.0 - 0.35 * c) * amp
    lift = (FOOT_LIFT_WALK + (FOOT_LIFT_RUN - FOOT_LIFT_WALK) * run) * (1.0 - 0.5 * c) * amp
    out = []
    for sx, ph in ((-1.0, phase), (1.0, phase + math.pi)):
        s, co = math.sin(ph), math.cos(ph)
        up = lift * max(0.0, co) ** 1.5                   # ช่วงเท้าเคลื่อนไปหน้า (sin เพิ่ม) = ยกเท้า
        sd = stride * s
        A = (sx * (ANKLE_X + 0.01 * c) + mdir[0] * sd * 0.6, ANKLE_Y + up, -0.02 * c + mdir[1] * sd)
        H = (sx * HIP_X, hip_y, hip_z)
        pole = _nrm((sx * CROUCH_KNEE_OUT * c, 0.0, 1.0))
        K = _ik(H, A, THIGH_L, SHIN_L, pole)
        if math.hypot(K[0], K[2]) > _knee_rmax(K[1], drop):
            lo, hi = 0.25, 1.0                            # หาสเกลความยาวขาที่มากสุดที่เข่ายังอยู่ในกรอบ (bisection)
            for _ in range(9):
                m = 0.5 * (lo + hi)
                Km = _ik(H, A, THIGH_L * m, SHIN_L * m, pole)
                if math.hypot(Km[0], Km[2]) > _knee_rmax(Km[1], drop):
                    hi = m
                else:
                    lo, K = m, Km
            if lo == 0.25:
                K = _ik(H, A, THIGH_L * lo, SHIN_L * lo, pole)
        fp = -0.35 * up / max(1e-6, FOOT_LIFT_RUN) + 0.12 * c       # ปลายเท้าชี้ลงตอนยก ; หมอบ = ส้นยกนิด
        out.append((K, A, fp))
    return hip_y, hip_z, out[0], out[1]


def seg_xform(p, A, B):
    """กระจก python ของ shader: จุดท่อขา (พิกัดกระดูก: y = −t) → พิกัดหุ่น ระหว่างข้อต่อ A (บน) → B (ล่าง)"""
    u = _nrm(_sub(B, A))
    s, f = _frame(u)
    t = -p[1]
    return _add(_add(A, _mul(_sub(B, A), t)), _add(_mul(s, p[0]), _mul(f, p[2])))


def foot_xform(p, A, pitch):
    ca, sa = math.cos(pitch), math.sin(pitch)
    return (p[0] + A[0], p[1] * ca + p[2] * sa + A[1], -p[1] * sa + p[2] * ca + A[2])


def agent_pose_xform(v, bone, pose, weapon_id=1, reach=None):
    """จุดยอดของ agent_mesh → พิกัดหุ่น (ก่อน yaw) ตามท่า pose = dict(crouch, pitch, reload, legs=leg_pose(...))
    (กระจกของ vertex shader clutchgl — selftest ใช้วัดว่าผิวอยู่ในกรอบ hitbox ทุกท่า) ; None = ชิ้นนี้ไม่แสดงกับอาวุธนี้"""
    b, var = bone % 32, bone // 32
    if var and var != weapon_id and var != ARMS_OF.get(weapon_id):
        return None
    drop = 0.55 * pose.get("crouch", 0.0)
    hip_y, hip_z, L, R = pose["legs"]
    if b == B_UPPER:
        return (v[0], v[1] - drop, v[2])
    if b == B_ARMS:
        return arms_xform(v, pose.get("pitch", 0.0), pose.get("reload", 0.0), drop, reach)
    if b == B_PELVIS:
        return (v[0], v[1] + hip_y - HIP_Y, v[2] + hip_z)
    for (th, sh, kn, ft), (K, A, fp), sx in (((B_THIGH_L, B_SHIN_L, B_KNEE_L, B_FOOT_L), L, -1.0),
                                             ((B_THIGH_R, B_SHIN_R, B_KNEE_R, B_FOOT_R), R, 1.0)):
        if b == th:
            return seg_xform(v, (sx * HIP_X, hip_y, hip_z), K)
        if b == sh:
            return seg_xform(v, K, A)
        if b == kn:
            return _add(v, K)
        if b == ft:
            return foot_xform(v, A, fp)
    return tuple(v)


# ── มือ/ปืนบุคคลที่หนึ่ง (พิกัดกล้อง: x ขวา, y บน, z หน้า — ม.) ──
# วางปืนมุมขวาล่างแบบเกม: ด้ามปืนที่ VM_POS[ชุด] (ใต้-ขวาของตา) ปลายลำกล้องยังห่างเป้าเล็งกลางจอเสมอ (selftest ตรวจ VM_CLEAR)
VM_POS = {V_RIFLE_ARMS: (0.200, -0.128, 0.33), V_SNIPER_ARMS: (0.220, -0.150, 0.40), V_PISTOL_ARMS: (0.165, -0.125, 0.40),
          V_SPIKE: (0.110, -0.430, 0.64)}
VM_YAW = {V_RIFLE_ARMS: -0.13, V_SNIPER_ARMS: -0.11, V_PISTOL_ARMS: -0.20, V_SPIKE: -0.12}   # เรเดียน (ลบ = ปลายชี้เข้ากลางจอ
                                                                                         #   → เห็นข้างขวาของปืนแบบเกม)
VM_ROLL = {V_RIFLE_ARMS: -0.10, V_SNIPER_ARMS: -0.08, V_PISTOL_ARMS: -0.12, V_SPIKE: 0.0}   # เอียงปืนตามเข็มนิด
VM_FOCAL_K = 1.30             # มือ/ปืนฉายด้วย focal × นี้ (FOV แคบกว่าโลก แบบ viewmodel FOV ของเกม FPS ทั่วไป — ปืนไม่บิดเข้ากลางจอ
                              # ตามเปอร์สเปกทีฟกว้าง 103° ; ขนาดสัมพัทธ์ระหว่างปืนยังจริง 1:1)
VM_CLEAR = 0.10               # สัดส่วนความสูงจอ — รัศมีรอบเป้าเล็งที่ viewmodel ห้ามเข้า (1080p = 108 px)
_VM_SLEEVE = ((0.020, -0.075, -0.030), (0.150, -0.330, -0.330))   # แขนเสื้อขวา: ข้อมือ → ออกขอบจอขวาล่าง (พิกัดปืน)


def viewmodel_mesh():
    """มือ + ปืนทุกกระบอก + spike ในพิกัดปืนของแต่ละชุด (แปลงเป็นพิกัดกล้องใน shader ด้วยเมทริกซ์ต่อเฟรม) → array('f')
    bone = 32·var: var = id ปืน (ตัวปืน) / 7–9 มือของชุดนั้น / 10 spike + มือ"""
    out = array("f")
    for var, guns in _GUNS_OF.items():
        bv = float(32 * var)
        # มือขวากำด้าม + แขนเสื้อลากออกขอบจอขวาล่าง ; มือซ้ายใต้การ์ดมือ + แขนเสื้อออกล่างกลาง
        _box(out, -0.028, 0.028, -0.110, -0.004, -0.065, 0.035, bv, M_GLOVE)
        _tube(out, _VM_SLEEVE[0], _VM_SLEEVE[1], [(0.0, 0.036, 0.034), (0.5, 0.045, 0.043), (1.0, 0.052, 0.050)], bv, M_SLEEVE, ns=12)
        if var == V_PISTOL_ARMS:
            lh, ls = (-0.012, -0.060, 0.010), (-0.170, -0.330, -0.300)
        elif var == V_SNIPER_ARMS:
            lh, ls = (-0.004, -0.052, 0.330), (-0.230, -0.300, 0.020)
        else:
            lh, ls = (-0.004, -0.045, 0.300), (-0.230, -0.300, -0.010)
        _box(out, lh[0] - 0.030, lh[0] + 0.030, lh[1] - 0.030, lh[1] + 0.024, lh[2] - 0.055, lh[2] + 0.050, bv, M_GLOVE)
        _tube(out, (lh[0] - 0.02, lh[1] - 0.02, lh[2] - 0.04), ls, [(0.0, 0.034, 0.032), (0.5, 0.043, 0.041), (1.0, 0.050, 0.048)],
              bv, M_SLEEVE, ns=12)
        for w in guns:
            _emit_gun(out, w, lambda p: p, 0, w, ns=14)
    # spike ในสองมือ (แท่งแปดเหลี่ยมแบบ clutchgl.spike_mesh — วาดเอง ไม่ import เพื่อกันวน)
    sv = float(32 * V_SPIKE)
    for y0, y1, r, m in ((0.0, 0.13, 0.15, M_SPIKE), (0.13, 0.16, 0.155, M_BAND), (0.16, 0.25, 0.10, M_SPIKE), (0.25, 0.30, 0.04, M_LIGHT)):
        ring0 = [(r * math.sin(2 * math.pi * (j + 0.5) / 8), y0, r * math.cos(2 * math.pi * (j + 0.5) / 8)) for j in range(8)]
        ring1 = [(p[0], y1, p[2]) for p in ring0]
        _loft(out, [ring0, ring1], sv, m)
    for sx in (-1.0, 1.0):
        _box(out, sx * 0.16 - 0.03, sx * 0.16 + 0.03, 0.02, 0.13, -0.05, 0.05, sv, M_GLOVE)
        _tube(out, (sx * 0.16, 0.05, -0.02), (sx * 0.30, -0.25, -0.30), [(0.0, 0.036, 0.034), (1.0, 0.050, 0.048)], sv, M_SLEEVE, ns=12)
    return out


def vm_matrix(vm, t, H=1080.0):
    """view["vm"] (§13.2) → (ชุด var, เมทริกซ์ 4x4 column-major พิกัดปืน → พิกัดกล้อง) หรือ None = ไม่วาด (ถือ Op เปิดสโคป /
    ไม่มีข้อมูล) — ท่า: ยกปืนตอนสลับ (equip_k), จุ่มตอนรีโหลด, เด้งถอยตอนยิง (fire_t), โยกตามเดิน, เลื่อนตอนหมอบ/ลอย/ADS"""
    if not vm:
        return None
    w = WEAPON_ID.get(str(vm.get("weapon") or "vandal").lower(), 1)
    spike = vm.get("equip") == "spike"
    if vm.get("ads") and w == 3 and not spike:
        return None                                       # Op เปิดสโคป: เห็นแต่วงสโคป (กติกา §12)
    var = V_SPIKE if spike else ARMS_OF[w]
    px, py, pz = VM_POS[var]
    yaw, pitch, roll = VM_YAW[var], 0.012, VM_ROLL[var]
    ek = max(0.0, min(1.0, float(vm.get("equip_k", 1.0) if vm.get("equip_k") is not None else 1.0)))
    e = 1.0 - (1.0 - ek) ** 3                             # ยกขึ้นเร็วแล้วชะลอ
    py -= 0.20 * (1.0 - e)
    pitch -= 0.9 * (1.0 - e)
    roll += 0.35 * (1.0 - e)
    rk = vm.get("reload_k")
    if rk is not None and not spike:
        r = math.sin(math.pi * max(0.0, min(1.0, float(rk))))   # จุ่ม-กลับ
        py -= 0.05 * r
        pitch -= 0.30 * r
        roll += 0.45 * r
        px -= 0.02 * r
    if vm.get("planting") or vm.get("defusing"):
        py -= 0.16
        pitch -= 0.5
    ft = vm.get("fire_t")
    if ft is not None and not spike:
        k = max(0.0, t - float(ft))
        kick = math.exp(-k / 0.055) if k < 0.4 else 0.0   # เด้งถอยหลัง + ยกปลาย แล้วคืนตัว
        big = 1.7 if w == 3 else (1.3 if w == 4 else 1.0)
        pz -= 0.030 * kick * big
        py -= 0.004 * kick * big
        pitch += 0.045 * kick * big
    sp = max(0.0, min(1.0, float(vm.get("speed", 0.0) or 0.0) / 5.4))
    if sp > 0.02 and not vm.get("air"):
        ph = t * (6.0 + 4.0 * sp)                         # โยกเลขแปดตามก้าว
        px += 0.010 * sp * math.sin(ph)
        py -= 0.008 * sp * abs(math.cos(ph))
    if vm.get("air"):
        py -= 0.015
        pitch += 0.04
    cr = max(0.0, min(1.0, float(vm.get("crouch", 0.0) or 0.0)))
    px -= 0.012 * cr
    py += 0.010 * cr
    if vm.get("ads") and not spike:
        px -= 0.012                                       # ยกเข้าหาแนวสายตานิดหนึ่ง (ไม่บังเป้าเล็ง — VM_CLEAR)
        py += 0.004
    kk = vm.get("kick") or (0.0, 0.0)
    pitch -= 0.25 * math.radians(float(kk[0] or 0.0))     # จอเด้งขึ้นจาก recoil แล้ว ปืนตามไม่ทัน = ลดลงเทียบจอเล็กน้อย
    yaw -= 0.25 * math.radians(float(kk[1] or 0.0))
    # เมทริกซ์: หมุน roll (z) → pitch (x) → yaw (y) แล้วเลื่อน
    cr_, sr = math.cos(roll), math.sin(roll)
    cp, sp_ = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)

    def rot(v):
        x, y, z = v
        x, y = x * cr_ - y * sr, x * sr + y * cr_
        y, z = y * cp + z * sp_, -y * sp_ + z * cp
        x, z = x * cy + z * sy, -x * sy + z * cy
        return (x, y, z)
    ex, ey, ez = rot((1.0, 0.0, 0.0)), rot((0.0, 1.0, 0.0)), rot((0.0, 0.0, 1.0))
    return var, (ex[0], ex[1], ex[2], 0.0, ey[0], ey[1], ey[2], 0.0, ez[0], ez[1], ez[2], 0.0, px, py, pz, 1.0), w


# ─────────────────────────────── selftest ───────────────────────────────
def _check(cmap, mesh, errors, tag):
    """ตรวจเมชจาก array จริง: ไม่มีสามเหลี่ยมเสื่อม, winding ถูก, normal แกนหลักยาว 1, สี 0..1,
    ฝาแนวนอนคลุมทุกช่องครั้งเดียวที่ความสูงถูก, รอยต่อที่ยอดต่างกันมีหน้าแนวตั้งคลุมครั้งเดียวพอดี (ไม่ขาด ไม่ซ้อน)"""
    P, N, C = mesh["pos"], mesh["nrm"], mesh["col"]
    nv, cs, x0, z0, nx, nz = mesh["n_vert"], cmap.cell, cmap.x0, cmap.z0, cmap.nx, cmap.nz
    if not (len(P) == len(N) == len(C) == 3 * nv and len(mesh["flag"]) == len(mesh["aux"]) == nv and nv % 6 == 0):
        errors.append(f"clutchmesh {tag}: ความยาว array ไม่ตรงกัน")
        return
    if min(C) < 0.0 or max(C) > 1.0:
        errors.append(f"clutchmesh {tag}: สีนอกช่วง 0..1")
    bad_w = degen = 0
    hcov = {}
    vcov = {}
    for q in range(nv // 6):
        k = q * 18
        n = (N[k], N[k + 1], N[k + 2])
        if abs(abs(n[0]) + abs(n[1]) + abs(n[2]) - 1.0) > 1e-6 or max(abs(v) for v in n) != 1.0:
            bad_w += 1
        for t in (k, k + 9):
            a, b, c = P[t:t + 3], P[t + 3:t + 6], P[t + 6:t + 9]
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            if cx * cx + cy * cy + cz * cz < 1e-12:
                degen += 1
            if cx * n[0] + cy * n[1] + cz * n[2] >= 0.0:
                bad_w += 1
        xs, ys, zs = P[k:k + 18:3], P[k + 1:k + 18:3], P[k + 2:k + 18:3]
        ia, ib = int(round((min(xs) - x0) / cs)), int(round((max(xs) - x0) / cs))
        ja, jb = int(round((min(zs) - z0) / cs)), int(round((max(zs) - z0) / cs))
        lo, hi = round(min(ys), 4), round(max(ys), 4)
        if n[1] != 0.0:
            for j in range(ja, jb):
                for i in range(ia, ib):
                    hcov.setdefault(j * nx + i, []).append(lo)
        elif n[2] != 0.0:
            for i in range(ia, ib):
                key = ("z", ja, i, lo, hi, int(n[2]))
                vcov[key] = vcov.get(key, 0) + 1
        else:
            for j in range(ja, jb):
                key = ("x", ia, j, lo, hi, int(n[0]))
                vcov[key] = vcov.get(key, 0) + 1
    if bad_w or degen:
        errors.append(f"clutchmesh {tag}: winding/normal ผิด {bad_w}, สามเหลี่ยมเสื่อม {degen}")
    wy = mesh["wall_y"]
    tops = [wy if cmap._top[c] == float("inf") else cmap._top[c] for c in range(nx * nz)]
    miss = [c for c in range(nx * nz) if len(hcov.get(c, ())) != 1 or abs(hcov[c][0] - tops[c]) > 1e-3]
    if miss:
        errors.append(f"clutchmesh {tag}: หน้าแนวนอนคลุมช่องผิด {len(miss)} ช่อง (เช่น {miss[0]})")
    want = {}
    for j in range(nz + 1):
        for i in range(nx):
            a = tops[(j - 1) * nx + i] if j > 0 else wy
            b = tops[j * nx + i] if j < nz else wy
            if a != b:
                want[("z", j, i, round(min(a, b), 4), round(max(a, b), 4), 1 if a > b else -1)] = 1
    for i in range(nx + 1):
        for j in range(nz):
            a = tops[j * nx + i - 1] if i > 0 else wy
            b = tops[j * nx + i] if i < nx else wy
            if a != b:
                want[("x", i, j, round(min(a, b), 4), round(max(a, b), 4), 1 if a > b else -1)] = 1
    if vcov != want:
        extra = [k for k in vcov if vcov[k] != want.get(k)]
        lack = [k for k in want if k not in vcov]
        errors.append(f"clutchmesh {tag}: หน้าแนวตั้งไม่ตรงรอยต่อ (เกิน/ซ้อน {len(extra)}, ขาด {len(lack)}, "
                      f"เช่น {(extra or lack)[:2]})")


def selftest():
    from .clutchmap import testyard, synthetic
    errors = []
    T0 = time.perf_counter()
    cm = testyard()
    me = build(cm)
    _check(cm, me, errors, "testyard")
    cnt = me["counts"]
    if any(cnt.get(k, 0) == 0 for k in ("floor", "site", "box_top", "box_side", "wall", "ledge", "cap")) or \
            not 400 < me["n_tri"] < 20000 or abs(me["wall_y"] - 9.0) > 1e-9:
        errors.append(f"clutchmesh: จำนวนหน้า testyard ผิดปกติ ({me['n_tri']} สามเหลี่ยม {cnt}, wall_y {me['wall_y']})")
    # ขอบ Heaven ด้านตะวันออก (x = 11, z 10…16) = หน้า ledge สูง 0 → 2 ม. หันไปทาง +x ครบทั้งแนว
    cs = cm.cell
    lx = int(round((11.0 - cm.x0) / cs))
    ledge = sum(q[3] - q[2] for q in me["_vq"] if q[0] == "x" and q[1] == lx and q[4] == 0.0 and
                abs(q[5] - 2.0) < 1e-9 and q[6] == 1)
    if ledge != int(round(6.0 / cs)):
        errors.append(f"clutchmesh: หน้าขอบ Heaven ด้าน B ไม่ครบ ({ledge * cs} ม. จาก 6)")
    nocap = build(cm, caps=False)
    if nocap["counts"].get("cap") or nocap["n_tri"] >= me["n_tri"]:
        errors.append("clutchmesh: caps=False ยังมีฝา")
    if len(interleave(me)) != me["n_vert"] * 11:
        errors.append("clutchmesh: interleave ยาวผิด")
    # ── มินิแมพ: ขนาด, north-up, สีตามชนิด/ความสูง ──
    t = time.perf_counter()
    w, h, px = minimap_rgba(cm, 256)
    ms_mm_small = (time.perf_counter() - t) * 1000

    def pix(x, z):
        u, v = minimap_xy(cm, w, h, x, z)
        k = (int(v) * w + int(u)) * 4
        return tuple(px[k:k + 4])
    heav, ground, site, box, void, def_sp = pix(7.5, 13), pix(-1, -10), pix(-12, 10), pix(-14.25, 6.75), \
        pix(-19.6, 0), pix(0, 17)
    if (w, h) != (256, 256) or len(px) != w * h * 4 or void[3] != 0 or ground[3] != 255 or \
            not heav[0] > ground[0] or not (site[0] == site[1] > site[2]) or not box[0] > ground[0] or \
            pix(14.5, -7)[0] >= ground[0] or def_sp != ground or minimap_xy(cm, w, h, 0, 17)[1] > h * 0.2:
        errors.append(f"clutchmesh: มินิแมพผิด (heaven {heav} ground {ground} site {site} box {box} void {void})")
    # ── แผนที่ขนาดด่านจริง (600² = 150 ม.) — เป้า ≤ 60k สามเหลี่ยม ──
    big = synthetic()
    mb = build(big)
    _check(big, mb, errors, "600x600")
    rag = synthetic(jitter=0.5)                     # ขอบหยักสุด (พลิกช่องริมขอบครึ่งหนึ่ง) = เพดานบนของด่านจริง
    mr = build(rag)
    _check(rag, mr, errors, "600x600 ragged")
    if mb["n_tri"] > 60000 or mr["n_tri"] > 60000:
        errors.append(f"clutchmesh: 600² ได้ {mb['n_tri']} / ขอบหยัก {mr['n_tri']} สามเหลี่ยม > 60k")
    t = time.perf_counter()
    bw, bh, bpx = minimap_rgba(big, 512)
    ms_mm = (time.perf_counter() - t) * 1000
    if (bw, bh) != (512, 512) or len(bpx) != 512 * 512 * 4 or ms_mm > 500:
        errors.append(f"clutchmesh: มินิแมพ 512 px ของ 600² ผิด/ช้า ({bw}x{bh}, {ms_mm:.0f} ms)")
    print(f"CLUTCHMESH SELFTEST {'OK' if not errors else 'FAIL'} (testyard {me['n_tri']} tri {me['ms']:.0f} ms | "
          f"600x600 {mb['n_tri']} tri {mb['ms']:.0f} ms, ragged-edge 600x600 {mr['n_tri']} tri {mr['ms']:.0f} ms "
          f"(limit 60000) | minimap 256px {ms_mm_small:.0f} ms, "
          f"512px on 600x600 {ms_mm:.0f} ms | total {time.perf_counter() - T0:.1f} s)")
    return errors
