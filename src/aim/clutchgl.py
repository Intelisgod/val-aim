# -*- coding: utf-8 -*-
"""ตัววาดโลก 3D ของโหมด CLUTCH 1vN บน GPU (moderngl) — CLUTCH_DESIGN §7/§11.2, render report §1–§6

ClutchGL(ctx): วาดทั้งฉากลง framebuffer นอกจอ (สีเป็น texture + depth 24 บิตแบบ renderbuffer ; MSAA 4x ถ้าการ์ดรับ
แล้ว resolve) แล้วคัดลอกภาพลง ctx.screen ด้วยสี่เหลี่ยมเต็มจอ → overlay composite ของ display วาดทับต่อได้ทันที
  • การฉายเท่า glrender._GEO_VS เป๊ะ (view_matrix + u_fx=2f/W, u_fy=2f/H, u_zn2=2·ZNEAR, f = game.fl())
    → จุดโลกเดียวกันตกพิกเซลเดียวกับ overlay project() (พิสูจน์ใน tools/clutch_view.py --check)
  • ฉากแมพ = VBO static เดียวจาก clutchmesh (1 draw call) ; กริด kind/h/zone อัปเป็น texture RGBA8 ให้ shader
    ทำเงาชิดกำแพง, เส้นขอบ ledge/กล่อง, สีโซนวาง spike (zone_hint) โดยไม่ต้องสร้างเมชใหม่
  • บอท = หุ่นเอเจนต์สัดส่วนจริง 1:1 (clutchmesh.agent_mesh: หัว/คอ/ลำตัว/แขน/ขา + ปืนต่อกระบอกที่ไหล่ชี้ตาม pitch) อยู่ในกรอบ
    hitbox ของ guns.humanoid_zone (ยื่นพ้น ≤ AGENT_OUT_TOL — clutch_view --check วัด) ; ขาเดิน/วิ่งจาก vx/vz (§13.2 — ไม่มี =
    ต่างตำแหน่งต่อเฟรม), หมอบ, รีโหลด, ล้มตาย ; ไฮไลต์ศัตรู = เส้นขอบแดงด้านในกว้างคงที่ ~2 px (ไม่ขยายออกนอกตัว)
    depth test บังที่มุมกำแพงเองทีละพิกเซล (ไม่มีข้อมูลบอทรั่วทะลุกำแพง) ; bot_model="hitbox" = หุ่นทรง hitbox เป๊ะสำหรับตรวจ
  • มือ/ปืนบุคคลที่หนึ่งจาก view["vm"] (§13.2): มุมขวาล่าง ไม่เข้าวง VM_CLEAR รอบเป้าเล็ง, ความลึกของตัวเอง (ไม่จมกำแพง)
  • ผนัง/พื้นทาสีตามย่าน (A/B/C/Mid/spawn จาก callout — clutchmesh.region_rgba), บัวผนังล่าง, กรอบช่องประตู/ปลายกำแพง
  • จบทุกครั้ง: DEPTH_TEST/CULL_FACE/BLEND ปิด, polygon_offset 0, line_width 1, blend_func SRC_ALPHA/ONE_MINUS_SRC_ALPHA,
    ctx.screen ถูก bind (ตามที่ _gl_present คาด — report §6 ข้อ 1)
draw_clutch_world(game, view) → bool : ทางเข้าจาก worlddraw — ล้มเมื่อไหร่ปิดเฉพาะ clutch GL (ไม่แตะ _glr ของโหมดอื่น)
ความหมายช่องใน view["bots"] (ตามที่ MODE ส่งจริง): dead_t = เวลาเกมตอนตาย (นาฬิกาเดียวกับ view["t"] ; None = ไม่วาดศพ),
  flash = บอทเพิ่งยิง 0..1 (จางใน 60 มิลลิวิ) → แสงไฟปากกระบอกส้มส่องตัวหุ่น (ไม่ใช่ทั้งตัวขาววาบ — ยิงรัวแล้วจะกะพริบทั้งตัว)
  ต้นเส้นกระสุน/ไฟปากกระบอกที่ตรงกับ "ตา" บอท (สมองบอทยิงจาก guns.Bot.eye) ถูกย้ายไปปลายลำกล้องที่วาดจริง (muzzle())
  ครั้งเดียวตอนเห็นเส้นครั้งแรก (ท่าหมอบอนุมานจากความสูงตา) แล้วเส้นนิ่งในโลกตลอดอายุ
  ปืนหุ่นหดถึงผิวกำแพงเมื่อบอทยืนชิด (gun_reach) · ศพล้มไปทิศที่โล่ง (corpse_yaw) · เส้นกระสุนกว้าง/จางใกล้ตาต่อพิกเซล
prepare(cmap) : งาน CPU ของ set_map (เมช + กริด) — pure, เรียกช่วงโหลด/นับถอยหลังได้ กันเฟรมแรกกระตุก ~0.2 วิ

moderngl import แบบ lazy (ครั้งแรกที่สร้าง ClutchGL) — ส่วน pure (เมชหุ่น/สไปก์, view_matrix, selftest) ใช้ได้ไม่มี
moderngl/pygame ; ไวยากรณ์ py3.10
"""
import math
import sys
import time
import weakref
from array import array

from .config import EYE_Y, ZNEAR
from .guns import HEAD_R, HEAD_Y, BODY_Y0, BODY_Y1, BODY_HW, LEG_Y0, LEG_Y1, LEG_HW, CROUCH_DROP
from . import clutchmesh as _cmesh

_mgl = None


def _moderngl():
    global _mgl
    if _mgl is None:
        import moderngl
        _mgl = moderngl
    return _mgl


# ── ค่าคงที่ของภาพ (ปรับจากภาพ QA ของ tools/clutch_view.py) ──
MSAA = 4
SKY_ZEN = (0.30, 0.47, 0.68)         # ฟ้าบนหัว
SKY_HOR = (0.70, 0.77, 0.83)         # ขอบฟ้า = สีหมอก
SKY_GND = (0.46, 0.49, 0.53)         # ใต้ขอบฟ้า (เห็นได้เฉพาะมองข้ามกำแพงจากที่สูง)
FOG_START, FOG_DENSITY = 12.0, 0.0045   # หมอกบาง: 50 ม. ≈ 16%, 100 ม. ≈ 33%
TRACER_LIFE = 0.12                   # วิ — เส้นกระสุนบอทจางหายใน
FLASH_LIFE = 0.06                    # วิ — ไฟปากกระบอก
MARK_FADE = (4.0, 6.0)               # วิ — รอยกระสุนเริ่มจาง/หายหมด (MODE ทิ้งรอยที่อายุ 6 วิ — จางหมดก่อน ไม่หายวับ)
MARK_R = 0.022                       # รัศมีรอยกระสุน (ม.) — รูกระสุน ~4 ซม. รวมขอบจาง
DEAD_FALL = 0.35                     # วิ — ล้มหงายจนนอนราบ
DEAD_FADE = (2.0, 3.0)               # วิ — ศพเริ่มจาง/หายหมด (เลยนี้ไม่วาด)
MAX_TRACERS, MAX_FLASHES, MAX_MARKS = 64, 32, 256
# วัสดุของเมชหุ่น/สไปก์ (in_mat) — เลขเดียวกับ clutchmesh (agent_mesh/viewmodel_mesh)
M_SUIT, M_HEAD, M_GUN, M_SPIKE, M_LIGHT, M_BAND, M_LEGS = 0, 1, 3, 4, 5, 6, 7
BOT_SEG, BOT_RINGS, BOT_HRINGS = 32, 16, 8   # แบ่งรอบวง/ชั้นทรงกลมหัว/ชั้นครึ่งทรงกลมขา
_A_BOT = ("in_pos", "in_nrm", "in_k", "in_mat")   # 8 float ต่อจุดยอด: pos 3, nrm 3, k (กระดูก + 32·var), mat
_A_INST = ("i_pos", "i_st", "i_ex", "i_aim", "i_kl", "i_al", "i_kr", "i_ar")   # instance หุ่น/spike (bot_rows)
ENEMY_RIM = (1.0, 0.16, 0.20)        # สีไฮไลต์ศัตรู (ขอบแดงแบบค่าเริ่มต้นของเกม) — เส้นขอบด้านในกว้างคงที่ ~2 px ทุกระยะ
RIM_PX = (1.1, 2.4)                  # px — ช่วง smoothstep ของเส้นขอบใน (ตามอนุพันธ์ของ N·V ต่อพิกเซล)
VM_LIGHT = (-0.45, 0.80, -0.40)      # ทิศแสงของมือ/ปืนบุคคลที่หนึ่ง (พิกัดกล้อง: บนซ้าย-หลัง)
# วัสดุแมพแยกย่าน (สีจาก clutchmesh.region_rgba) — ค่าประมาณจากภาพแมพจริง (ไม่ใช่ข้อมูลเกม)
FLOOR_TINT = 0.28                    # พื้นทางเดินย้อมโทนย่านแค่นี้ (0 = เทาล้วน)
WAINSCOT_Y = 1.05                    # ม. — ผนังล่าง (บัว) สูงแค่นี้จากพื้น ; เหนือนั้นปูนทาสีอ่อน
JAMB_W = 0.09                        # ม. — กรอบเข้มที่ขอบช่องประตู/ปลายกำแพง (มุมนูน)


def _base_focal(H):
    """focal ของจอสูง H แบบไม่ซูม (camera.focal_len) — มือ/ปืนบุคคลที่หนึ่งไม่ขยายตาม ADS/สโคป"""
    from .camera import focal_len
    return focal_len(H)


def view_matrix(yaw, pitch, pos):
    """world→cam 4x4 column-major — สูตรเดียวกับ glrender.view_matrix ทุกตัว (ไม่ import glrender เพราะมันพา
    gunplay/pygame มาด้วย) ; selftest เทียบกับ camera.to_cam 1e-9"""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    r00, r01, r02 = cy, 0.0, -sy
    r10, r11, r12 = -sp * sy, cp, -sp * cy
    r20, r21, r22 = cp * sy, sp, cp * cy
    px, py, pz = pos[0], pos[1], pos[2]
    return (r00, r10, r20, 0.0,
            r01, r11, r21, 0.0,
            r02, r12, r22, 0.0,
            -(r00 * px + r01 * py + r02 * pz), -(r10 * px + r11 * py + r12 * pz),
            -(r20 * px + r21 * py + r22 * pz), 1.0)


# ─────────────────────────── เมชหุ่น/สไปก์ (pure python) ───────────────────────────
def _tri(out, a, b, c, hint):
    """สามเหลี่ยมหนึ่งรูป (จุด = (pos, nrm, k, mat)) เรียงให้ cross(b−a, c−a)·hint < 0 = ทวนเข็มบนจอเมื่อมองจากด้านนอก
    (โลกมือซ้าย — ธรรมเนียมเดียวกับ clutchmesh ; CULL_FACE front=CCW ตัดด้านในทิ้งได้) ; ทิ้งสามเหลี่ยมเสื่อม"""
    pa, pb, pc = a[0], b[0], c[0]
    ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
    vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    if cx * cx + cy * cy + cz * cz < 1e-18:
        return
    if cx * hint[0] + cy * hint[1] + cz * hint[2] > 0.0:
        b, c = c, b
    for p, n, k, m in (a, b, c):
        out.extend((p[0], p[1], p[2], n[0], n[1], n[2], k, m))


def _ring(r, y, ns):
    return [(r * math.sin(2 * math.pi * j / ns), y, r * math.cos(2 * math.pi * j / ns)) for j in range(ns)]


def _sphere_part(out, cy, r, k, mat, la0, la1, nr, ns):
    """แถบทรงกลมศูนย์ (0, cy, 0) ละติจูด la0→la1 — จุดยอดบนผิวพอดี, normal รัศมี (ผิวเรียบ)"""
    def pt(i, j):
        la = la0 + (la1 - la0) * i / nr
        lo = 2 * math.pi * j / ns
        n = (math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo))
        return ((r * n[0], cy + r * n[1], r * n[2]), n, k, mat)
    for i in range(nr):
        for j in range(ns):
            a, b, c, d = pt(i, j), pt(i, j + 1), pt(i + 1, j + 1), pt(i + 1, j)
            hint = a[1]
            _tri(out, a, b, c, hint)
            _tri(out, a, c, d, hint)


def _cyl_side(out, y0, y1, r, k0, k1, mat, ns):
    for j in range(ns):
        l0, l1 = 2 * math.pi * j / ns, 2 * math.pi * (j + 1) / ns
        n0 = (math.sin(l0), 0.0, math.cos(l0))
        n1 = (math.sin(l1), 0.0, math.cos(l1))
        a = ((r * n0[0], y0, r * n0[2]), n0, k0, mat)
        b = ((r * n1[0], y0, r * n1[2]), n1, k0, mat)
        c = ((r * n1[0], y1, r * n1[2]), n1, k1, mat)
        d = ((r * n0[0], y1, r * n0[2]), n0, k1, mat)
        hint = (n0[0] + n1[0], 0.0, n0[2] + n1[2])
        _tri(out, a, b, c, hint)
        _tri(out, a, c, d, hint)


def _disc(out, y, r, k, mat, up, ns):
    n = (0.0, 1.0 if up else -1.0, 0.0)
    ring = _ring(r, y, ns)
    ctr = ((0.0, y, 0.0), n, k, mat)
    for j in range(ns):
        _tri(out, ctr, (ring[j], n, k, mat), (ring[(j + 1) % ns], n, k, mat), n)


def _box(out, x0, x1, y0, y1, z0, z1, k, mat):
    faces = (((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
             ((-1, 0, 0), [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]),
             ((0, 1, 0), [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)]),
             ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
             ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
             ((0, 0, -1), [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)]))
    for n, q in faces:
        n = (float(n[0]), float(n[1]), float(n[2]))
        v = [(p, n, k, mat) for p in q]
        _tri(out, v[0], v[1], v[2], n)
        _tri(out, v[0], v[2], v[3], n)


def _prism(out, y0, y1, r, k, mat, ns):
    """ปริซึม ns เหลี่ยม (หน้าเรียบ normal ต่อหน้า) + ฝาบน/ล่าง — ชิ้นส่วน spike"""
    ring = [(r * math.sin(2 * math.pi * (j + 0.5) / ns), r * math.cos(2 * math.pi * (j + 0.5) / ns)) for j in range(ns)]
    for j in range(ns):
        (ax, az), (bx, bz) = ring[j], ring[(j + 1) % ns]
        l = math.atan2((ax + bx) / 2, (az + bz) / 2)
        n = (math.sin(l), 0.0, math.cos(l))
        a, b = ((ax, y0, az), n, k, mat), ((bx, y0, bz), n, k, mat)
        c, d = ((bx, y1, bz), n, k, mat), ((ax, y1, az), n, k, mat)
        _tri(out, a, b, c, n)
        _tri(out, a, c, d, n)
    for y, s in ((y1, 1.0), (y0, -1.0)):
        n = (0.0, s, 0.0)
        ctr = ((0.0, y, 0.0), n, k, mat)
        for j in range(ns):
            (ax, az), (bx, bz) = ring[j], ring[(j + 1) % ns]
            _tri(out, ctr, ((ax, y, az), n, k, mat), ((bx, y, bz), n, k, mat), n)


# ปืนของหุ่นหลักฐาน hitbox (bot_mesh — ใช้เป็นเมชตรวจ depth แบบตรง hitbox เป๊ะใน clutch_view และ selftest ; หุ่นที่เห็นในเกม =
# clutchmesh.agent_mesh ซึ่งมีปืนต่อกระบอกของตัวเอง): ถือขวา ระดับอกล่าง ชี้ตาม yaw (+z ท้องถิ่น)
GUN_BOX = (0.105, 0.175, 1.19, 1.31, -0.04, 0.60)
GUN_BARREL = (0.125, 0.155, 1.235, 1.265, 0.60, 0.86)


def bot_mesh(ns=BOT_SEG, nr=BOT_RINGS, nh=BOT_HRINGS, gun=True):
    """หุ่นทรง hitbox ท่ายืนในพิกัดท้องถิ่น (x ขวา, y ขึ้น, z หน้า = ทิศ yaw ; เท้าที่ y 0) → array('f') 8 float/จุดยอด
    k = 1 : ส่วนที่ลดลง CROUCH_DROP·crouch ตอนหมอบ (หัว, ลำตัว, วงบน+โดมบนของขา) ; k = 0 : ติดพื้น (โดมล่างของขา)
    = Bot.head_y/body_y0/body_y1/leg_y1 ทุกท่า — k ตรงกับกระดูก B_STATIC/B_UPPER ของ shader หุ่นเอเจนต์ (ใช้ shader เดียวกัน)
    gun=False = ไม่มีปืน (เมช "hitbox ล้วน" ของ ClutchGL(bot_model="hitbox") สำหรับตรวจ depth เทียบ ray cast CPU)"""
    out = array("f")
    _sphere_part(out, HEAD_Y, HEAD_R, 1.0, M_HEAD, -math.pi / 2, math.pi / 2, nr, ns)
    _cyl_side(out, BODY_Y0, BODY_Y1, BODY_HW, 1.0, 1.0, M_SUIT, ns)
    _disc(out, BODY_Y1, BODY_HW, 1.0, M_SUIT, True, ns)
    _disc(out, BODY_Y0, BODY_HW, 1.0, M_SUIT, False, ns)
    _sphere_part(out, LEG_Y0, LEG_HW, 0.0, M_LEGS, -math.pi / 2, 0.0, nh, ns)
    _cyl_side(out, LEG_Y0, LEG_Y1, LEG_HW, 0.0, 1.0, M_LEGS, ns)
    _sphere_part(out, LEG_Y1, LEG_HW, 1.0, M_LEGS, 0.0, math.pi / 2, nh, ns)
    if gun:
        _box(out, *GUN_BOX, 1.0, M_GUN)
        _box(out, *GUN_BARREL, 1.0, M_GUN)
    return out


def spike_mesh():
    """spike ตั้งบนพื้น (ท้องถิ่น, ฐานที่ y 0): ตัวแปดเหลี่ยม + แถบ + ส่วนบน + ไฟ (M_LIGHT กะพริบตาม blink)"""
    out = array("f")
    _prism(out, 0.0, 0.13, 0.15, 0.0, M_SPIKE, 8)
    _prism(out, 0.13, 0.16, 0.155, 0.0, M_BAND, 8)
    _prism(out, 0.16, 0.25, 0.10, 0.0, M_SPIKE, 8)
    _prism(out, 0.25, 0.30, 0.04, 0.0, M_LIGHT, 8)
    return out


SPIKE_LIGHT_Y = 0.30
SNAP_XZ, SNAP_DY = 0.6, 0.12         # ม. — จุดที่ห่างตาบอทไม่เกินนี้ถือเป็น "ยิงจากตา" (บอทเดินได้ ~0.5 ม. ใน 0.12 วิ)
GUN_GAP = 0.02                       # ม. — ปืนหดเหลือห่างผิวของทึบเท่านี้
GUN_NONE = 9.0                       # ค่า "ไม่หดปืน" ในช่อง i_ex.y (ศพ/ไม่มีด่าน)
GUN_Y_LOW = 0.035                    # ม. ใต้จุดกำเนิดปืน — แนวรังสีตรวจชนของ gun_reach (ใต้ท้องตัวปืน)
TRC_ZMIN = 0.2                       # ม. — ตัดเส้นกระสุนส่วนที่ z กล้อง < นี้ (ส่วนนั้นห่างตา < 0.55 ม. ทุก FOV = จางหมดแล้ว)
TRC_NEAR = (0.4, 2.5)                # ม. — เส้นกระสุนจางหายเมื่อเข้าใกล้ตา (คิดต่อพิกเซล — ไม่ใช่แค่ปลายสองข้าง)
TRC_PX = (2.4, 1.3)                  # px ของ overlay — ครึ่งความกว้างเส้นกระสุน ใกล้ (≤ 2 ม.) / ไกล (≥ 20 ม.)
# ทิศที่ลองให้ศพล้ม (บวกกับ yaw ; ท่าล้ม = หงายไปทาง −forward) เรียงตามความเป็นธรรมชาติ: หลัง, หลังเฉียง, ข้าง, หน้าเฉียง, หน้า
CORPSE_TRY = (0.0, math.pi / 4, -math.pi / 4, math.pi / 2, -math.pi / 2, 3 * math.pi / 4, -3 * math.pi / 4, math.pi)
CORPSE_LEN = HEAD_Y + HEAD_R         # ม. — ศพนอนยาวจากเท้าถึงปลายหัว
CORPSE_RAY_Y = 0.25                  # ม. เหนือพื้น — แนวตรวจของทึบใต้ศพ (แกนลำตัวที่นอนอยู่ ≈ BODY_HW)


def weapon_id(name, default=1):
    """ชื่ออาวุธ (guns.WEAPONS key / ชื่อแสดง) → id ของเมช (1 Vandal … 6 Classic) ; ไม่รู้จัก = default"""
    if isinstance(name, int):
        return name if 1 <= name <= 6 else default
    return _cmesh.WEAPON_ID.get(str(name or "").strip().lower(), default)


def _arm_world(p, x, y, z, yaw, crouch=0.0, pitch=0.0, reload=0.0, reach=None):
    """จุดชุดแขน/ปืน (พิกัดหุ่นท่ายืน) → โลก (กระจก shader: หด → รีโหลด → ก้ม/เงยรอบ SH_PIV → หมอบ → yaw)"""
    q = _cmesh.arms_xform(p, pitch, reload, CROUCH_DROP * crouch, reach)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (q[0] * cy + q[2] * sy + x, q[1] + y, -q[0] * sy + q[2] * cy + z)


def gun_reach(cmap, x, y, z, yaw, crouch=0.0, pitch=0.0, weapon=1):
    """ปืน (และมือที่จับ) ของหุ่นยื่นได้ถึงไหน (z ท้องถิ่นของชุดแขนก่อนหมุน) ก่อนชนของทึบ — กันปืนทะลุกำแพงบางไปโผล่ฝั่ง
    ผู้เล่น (§7 ห้ามข้อมูลศัตรูทะลุกำแพง) ; รังสี 2 เส้นที่ขอบซ้าย/ขวาใต้ท้องปืนตามแนวลำกล้อง (รวมก้ม/เงย) — แมพเป็น
    heightfield (ของทึบสูงจากพื้นถึงยอด) อะไรขวางส่วนไหนของตัวปืนก็ขวางแนวล่างด้วย ; cmap None = ไม่หด (GUN_NONE)"""
    if cmap is None:
        return GUN_NONE
    w = weapon_id(weapon)
    g = _cmesh.agent_grip(w)
    zb, zf, _tip = _cmesh.gun_extent(w)
    z0, z1 = g[2] + zb, g[2] + zf
    best = GUN_NONE
    for lx in (g[0] - 0.02, g[0] + 0.02):
        a = (lx, g[1] - GUN_Y_LOW, z0)
        o = _arm_world(a, x, y, z, yaw, crouch, pitch)
        e = _arm_world((a[0], a[1], z1), x, y, z, yaw, crouch, pitch)
        d = (e[0] - o[0], e[1] - o[1], e[2] - o[2])
        L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        t = cmap.ray(o, (d[0] / L, d[1] / L, d[2] / L), L)
        if t is not None:
            best = min(best, max(z0, z0 + t - GUN_GAP))
    return best


def muzzle(x, y, z, yaw, crouch=0.0, cmap=None, pitch=0.0, weapon=1):
    """ปลายลำกล้องของหุ่นในโลก (ต้นเส้นกระสุน/ไฟปากกระบอกให้ตรงปืนที่วาด) — y = พื้นที่บอทยืน
    cmap ให้มา = ปลายปืนที่หดแล้วตาม gun_reach (ตรงกับที่วาดเมื่อบอทยืนชิดกำแพง)"""
    w = weapon_id(weapon)
    reach = gun_reach(cmap, x, y, z, yaw, crouch, pitch, w) if cmap is not None else None
    return _arm_world(_cmesh.agent_muzzle_local(w), x, y, z, yaw, crouch, pitch, 0.0, reach)


def eye_to_muzzle(p, bots, reach=None, weapon=1):
    """p = ต้นเส้นกระสุน/ไฟปากกระบอก ; ถ้าอยู่ที่ตาของบอทตัวที่ยังเป็น (guns.Bot.eye = พื้น + EYE_Y − หมอบ) → ปลายลำกล้อง
    ของบอทตัวนั้น ; ไม่ตรงตาใคร (ผู้เรียกส่ง muzzle() มาเอง / ของอื่น) → คืน p เดิม
    ท่าหมอบ = อนุมานจากความสูงตาตอนยิง (ไม่ใช่ท่าปัจจุบัน — บอทหมอบ/ลุกได้ 0.55 ม. ภายในอายุเส้นกระสุน 0.12 วิ)
    reach = list ตามลำดับ bots จาก gun_reach (None = ปืนยาวเต็ม) ; อาวุธ = b["weapon"] หรือ weapon"""
    best, bd, bc = -1, SNAP_XZ * SNAP_XZ, 0.0
    for i, b in enumerate(bots):
        if not b.get("alive", True):
            continue
        y = b.get("y", 0.0) or 0.0
        cr = (y + EYE_Y - p[1]) / CROUCH_DROP           # ท่าหมอบที่ทำให้ตาอยู่สูงเท่า p
        if cr < -SNAP_DY / CROUCH_DROP or cr > 1.0 + SNAP_DY / CROUCH_DROP:
            continue
        d2 = (p[0] - b["x"]) ** 2 + (p[2] - b["z"]) ** 2
        if d2 < bd:
            best, bd, bc = i, d2, max(0.0, min(1.0, cr))
    if best < 0:
        return p
    b = bots[best]
    r = reach[best] if reach is not None else None
    w = weapon_id(b.get("weapon"), weapon_id(weapon))
    return _arm_world(_cmesh.agent_muzzle_local(w), b["x"], b.get("y", 0.0) or 0.0, b["z"], b.get("yaw", 0.0) or 0.0,
                      bc, b.get("pitch", 0.0) or 0.0, 0.0, None if r is None or r >= GUN_NONE else r)


def _corpse_fit(cmap, x, y, z, fy):
    """ศพล้มทิศ fy: (ระยะที่โล่ง ≤ CORPSE_LEN ตามแกนลำตัว + ไหล่สองข้าง, พื้นใต้ตัวต่างจากเท้ามากสุดกี่ ม. — inf = ไม่มีพื้น)"""
    bx, bz = -math.sin(fy), -math.cos(fy)                # หงายไปทาง −forward
    rx, rz = math.cos(fy), -math.sin(fy)
    t = cmap.ray((x, y + CORPSE_RAY_Y, z), (bx, 0.0, bz), CORPSE_LEN)
    clear = CORPSE_LEN if t is None else t
    for sd in (-BODY_HW * 0.8, BODY_HW * 0.8):           # ไหล่/สะโพกซ้ายขวา (ลำตัว 0.3–1.46 ม. จากเท้า)
        o = (x + rx * sd + bx * 0.3, y + CORPSE_RAY_Y, z + rz * sd + bz * 0.3)
        t = cmap.ray(o, (bx, 0.0, bz), BODY_Y1 - 0.3)
        if t is not None:
            clear = min(clear, 0.3 + t)
    dh = 0.0
    for k in (0.5, 0.9, 1.3, HEAD_Y):                    # พื้นใต้ตัวระดับเดียวกัน (ไม่ห้อยเหนือ ledge / ไม่จมขั้นสูง)
        f = cmap.floor_y(x + bx * k, z + bz * k)
        dh = max(dh, abs(f - y) if f is not None else float("inf"))
    return clear, dh


def corpse_yaw(cmap, x, y, z, yaw):
    """ทิศ yaw ที่ศพล้มหงายแล้วนอนบนพื้นโล่ง (ไม่จมกำแพง/กล่อง/ขั้นสูงข้างหลัง ไม่ลอยเหนือที่ต่ำ) — ลองตาม CORPSE_TRY:
    ทิศแรกที่โล่งตลอดตัวและพื้นเรียบ (ต่าง ≤ 0.12 ม. = ทางลาด) ; ไม่มี = ทิศที่ดีสุดตาม (โล่ง+พื้นต่าง ≤ 0.3, ระยะโล่ง,
    พื้นเรียบกว่า) ; เลือกครั้งเดียวต่อการตาย (ClutchGL cache) ; cmap None = yaw เดิม"""
    if cmap is None:
        return yaw
    best, best_key = yaw, None
    for off in CORPSE_TRY:
        fy = yaw + off
        clear, dh = _corpse_fit(cmap, x, y, z, fy)
        full = clear >= CORPSE_LEN
        if full and dh <= 0.12:
            return fy
        key = (full and dh <= 0.3, clear, -dh)
        if best_key is None or key > best_key:
            best, best_key = fy, key
    return best


# ── ท่าทางต่อบอท (เดิน/วิ่ง/หมอบ/รีโหลด) ──
GAIT_TAU = 0.08            # วิ — ความเร็วที่ใช้ขยับขาเกลี่ยแบบ exponential (กันขากระตุกจากความเร็วต่อเฟรมที่แกว่ง)
RELOAD_TAU = 0.10          # วิ — เข้า/ออกท่ารีโหลด
GAIT_TELEPORT = 3.0        # ม. — ขยับเกินนี้ในเฟรมเดียว = วาร์ป/บอทใหม่ (เริ่มจังหวะก้าวใหม่ ไม่คิดเป็นความเร็ว)
GAIT_RUN = (2.2, 4.6)      # ม./วิ — ช่วงที่ท่าก้าวเปลี่ยนจากเดิน (shift) เป็นวิ่งเต็ม
AIM_PITCH_MAX = 1.1        # เรเดียน — ก้ม/เงยปืนของหุ่นสูงสุดที่วาด (~63°)
_LEG_CACHE = {}


def _legs(crouch, phase, amp, run, mdir):
    key = (round(crouch, 2), round(phase, 2), round(amp, 2), round(run, 1), round(mdir[0], 1), round(mdir[1], 1))
    got = _LEG_CACHE.get(key)
    if got is None:
        if len(_LEG_CACHE) > 4096:
            _LEG_CACHE.clear()
        got = _LEG_CACHE[key] = _cmesh.leg_pose(key[0], key[1], key[2], key[3], (key[4], key[5]))
    return got


def gait_step(state, bots, t):
    """อัปเดตจังหวะก้าวของบอททุกตัว (ต่อเฟรม) → list ตามลำดับ bots: (phase, amp, run, mdir, reload 0..1)
    ความเร็ว = view["bots"][i]["vx","vz"] (§13.2 จาก MODE/BOTS) ; ไม่มี = ต่างตำแหน่ง/เวลาจากเฟรมก่อนของบอทลำดับเดียวกัน
    "walk" จริง = ก้าวแบบย่อง (แกว่งน้อย ช้า) ; state = dict ที่ผู้เรียกเก็บไว้ข้ามเฟรม (แก้ในที่) ; ช่อง QA: "gait_phase"/"gait_amp" ทับค่า"""
    out = []
    keep = {}
    for i, b in enumerate(bots):
        x, z = b["x"], b["z"]
        g = state.get(i)
        rt = 1.0 if (b.get("reload") and b.get("alive", True)) else 0.0
        if g is None or t < g["t"] or math.hypot(x - g["x"], z - g["z"]) > GAIT_TELEPORT:
            g = {"x": x, "z": z, "t": t, "ph": 0.0, "sp": 0.0, "vx": 0.0, "vz": 0.0, "rl": rt}
        dt = t - g["t"]
        vx, vz = b.get("vx"), b.get("vz")
        if vx is None or vz is None:
            if dt > 1e-4:
                vx, vz = (x - g["x"]) / dt, (z - g["z"]) / dt
            else:
                vx, vz = g["vx"], g["vz"]
        vx, vz = float(vx or 0.0), float(vz or 0.0)
        spd = min(7.0, math.hypot(vx, vz))
        if not b.get("alive", True):
            spd = 0.0
        k = 1.0 - math.exp(-dt / GAIT_TAU) if dt > 0 else 0.0
        g["sp"] += (spd - g["sp"]) * k
        g["ph"] = (g["ph"] + spd * dt * math.pi / _cmesh.STEP_LEN) % (2 * math.pi)
        if dt > 0:
            g["rl"] += (rt - g["rl"]) * (1.0 - math.exp(-dt / RELOAD_TAU))
        g.update(x=x, z=z, t=t, vx=vx, vz=vz)
        keep[i] = g
        sp = g["sp"]
        amp = b.get("gait_amp")
        if amp is None:
            amp = max(0.0, min(1.0, (sp - 0.15) / 1.1))
            amp = amp * amp * (3 - 2 * amp)
        run = 0.0 if b.get("walk") else max(0.0, min(1.0, (sp - GAIT_RUN[0]) / (GAIT_RUN[1] - GAIT_RUN[0])))
        yw = b.get("yaw", 0.0) or 0.0
        cy, sy = math.cos(yw), math.sin(yw)
        lx, lz = vx * cy - vz * sy, vx * sy + vz * cy        # ทิศเดินในพิกัดหุ่น
        n = math.hypot(lx, lz)
        mdir = (lx / n, lz / n) if n > 0.05 else (0.0, 1.0)
        ph = b.get("gait_phase")
        out.append((g["ph"] if ph is None else float(ph), float(amp), run, mdir, g["rl"]))
    state.clear()
    state.update(keep)
    return out


BOT_ROW = 32               # float ต่อ instance ของ shader หุ่น


def bot_rows(bots, t, reach=None, fall_yaw=None, gait=None, weapon=1):
    """view["bots"] → แถว instance (live, dead) ของ shader หุ่น BOT_ROW float:
    (x, y, z, yaw) (drop, flash, fall, alpha) (rim, ปืนยาวถึง, sink, kind) (pitch, รีโหลด, id อาวุธ, สะโพก y)
    (เข่าซ้าย xyz, เท้าซ้ายเงย) (ข้อเท้าซ้าย xyz, สะโพก z) (เข่าขวา …) (ข้อเท้าขวา xyz, 0)
    ศพ: อายุ = t − dead_t (เวลาเกมตอนตาย) ล้มใน DEAD_FALL แล้วจางช่วง DEAD_FADE ; dead_t None = ไม่วาด ; ศพ = ท่ายืนตรง
    reach = list ตามลำดับ bots (gun_reach) ; fall_yaw = {ลำดับ: yaw ทิศล้ม} (corpse_yaw) ; gait = gait_step() — None = ยืนนิ่ง"""
    live, dead = [], []
    w0 = weapon_id(weapon)
    for i, b in enumerate(bots):
        y = b.get("y", 0.0) or 0.0
        cr = max(0.0, min(1.0, b.get("crouch", 0.0) or 0.0))
        drop = CROUCH_DROP * cr
        yaw = b.get("yaw", 0.0) or 0.0
        w = weapon_id(b.get("weapon"), w0)
        if b.get("alive", True):
            fl = max(0.0, min(1.0, b.get("flash", 0.0) or 0.0))
            r = reach[i] if reach is not None else GUN_NONE
            ph, amp, run, mdir, rl = gait[i] if gait is not None else (0.0, 0.0, 0.0, (0.0, 1.0), 0.0)
            pitch = max(-AIM_PITCH_MAX, min(AIM_PITCH_MAX, b.get("pitch", 0.0) or 0.0))
            hy, hz, L, R = _legs(cr, ph, amp, run, mdir)
            live.append((b["x"], y, b["z"], yaw, drop, fl, 0.0, 1.0, 1.0, r, 0.0, 0.0, pitch, rl, float(w), hy)
                        + L[0] + (L[2],) + L[1] + (hz,) + R[0] + (R[2],) + R[1] + (0.0,))
            continue
        d0 = b.get("dead_t")
        if d0 is None:
            continue
        age = max(0.0, t - d0)
        if age >= DEAD_FADE[1]:
            continue
        fall = min(1.0, age / DEAD_FALL) ** 2
        a = 1.0 - max(0.0, min(1.0, (age - DEAD_FADE[0]) / (DEAD_FADE[1] - DEAD_FADE[0])))
        fy = fall_yaw.get(i, yaw) if fall_yaw else yaw
        hy, hz, L, R = _legs(cr, 0.0, 0.0, 0.0, (0.0, 1.0))
        dead.append((b["x"], y, b["z"], fy, drop, 0.0, fall, a, 0.0, GUN_NONE, 0.0, 1.0, 0.0, 0.0, float(w), hy)
                    + L[0] + (L[2],) + L[1] + (hz,) + R[0] + (R[2],) + R[1] + (0.0,))
    return live, dead


def tracer_rows(trs, bots, vm, reach=None, cache=None, weapon=1):
    """view["tracers"] → แถว instance ของ shader เส้นกระสุน 10 float: (ต้น xyz, อายุ) (ปลาย xyz, อายุขัย) (s0, s1)
    • ต้นที่ตาบอท → ปลายลำกล้อง (eye_to_muzzle) แล้วจำไว้ใน cache {(ต้น, ปลาย): ต้นที่ย้ายแล้ว} ตั้งแต่เฟรมแรกที่เห็น → เส้นนิ่ง
      ในโลกแม้บอทหัน/หมอบ/ตายระหว่างอายุเส้น ; คืน (rows, cache ใหม่ที่มีเฉพาะเส้นที่ยังอยู่)
    • ตัดส่วนที่อยู่หลัง/ชิดกล้อง (z กล้อง < TRC_ZMIN) → s0..s1 = ช่วงที่เหลือบนเส้นเดิม (0 = ต้น, 1 = ปลาย) ; ไม่เหลือ = ไม่วาด
      (ความกว้าง/การจางใกล้ตาคิดต่อพิกเซลใน shader — เส้นพลาดเฉียดหัวไม่เป็นลิ่มกว้างทั้งจอ)"""
    old = cache or {}
    new, rows = {}, []
    for a, c, age in trs:
        key = (a, c)
        s = old.get(key)
        if s is None:
            s = eye_to_muzzle(a, bots, reach, weapon)
        new[key] = s
        za = vm[2] * s[0] + vm[6] * s[1] + vm[10] * s[2] + vm[14]
        zc = vm[2] * c[0] + vm[6] * c[1] + vm[10] * c[2] + vm[14]
        if za < TRC_ZMIN and zc < TRC_ZMIN:
            continue
        s0, s1 = 0.0, 1.0
        if za < TRC_ZMIN:
            s0 = (TRC_ZMIN - za) / (zc - za)
        elif zc < TRC_ZMIN:
            s1 = (TRC_ZMIN - za) / (zc - za)
        if s1 - s0 < 1e-6:
            continue
        rows.append((s[0], s[1], s[2], age, c[0], c[1], c[2], TRACER_LIFE, s0, s1))
    return rows, new


def surface_normal(cmap, p, d):
    """normal ของผิวที่รังสีทิศ d ชนที่จุด p (จาก cmap.ray) — กริดแกนตรง: จุดชนอยู่บนเส้นแบ่งช่องแกน x และรังสีข้ามเข้าช่อง
    ที่ยอดสูงกว่าจุดชน (ผนัง/ข้างกล่อง/ขอบ ledge) → ±x, แกน z → ±z ; อื่น ๆ (ชนหลังพื้น/หลังกล่อง แม้ห่างเส้นแบ่งช่องหรือตีน
    กำแพงแค่มิลลิเมตร) → +y — ใช้วาง decal รอยกระสุน (view["marks"])"""
    cs = cmap.cell
    gx, gz = (p[0] - cmap.x0) / cs, (p[2] - cmap.z0) / cs
    rx, rz = round(gx), round(gz)
    on_x = abs(gx - rx) * cs < 1e-5 and abs(d[0]) > 1e-12      # ray หยุดบนเส้นแบ่งช่องพอดี = อาจเป็นหน้าแนวตั้ง
    on_z = abs(gz - rz) * cs < 1e-5 and abs(d[2]) > 1e-12      #   (พื้นข้างตีนกำแพงห่างแค่ 1 มม. ก็ไม่นับ)
    if on_x or on_z:
        top = p[1] + 1e-4
        ia, ib = (rx - 1, rx) if d[0] > 0 else (rx, rx - 1)   # ช่องก่อน/หลังข้ามเส้น x
        ja, jb = (rz - 1, rz) if d[2] > 0 else (rz, rz - 1)
        i0 = ia if on_x else math.floor(gx)
        j0 = ja if on_z else math.floor(gz)
        if on_x and cmap.top_y(ib, j0) > top:
            return (-math.copysign(1.0, d[0]), 0.0, 0.0)
        if on_z and cmap.top_y(i0, jb) > top:
            return (0.0, 0.0, -math.copysign(1.0, d[2]))
        if on_x and on_z and cmap.top_y(ib, jb) > top:      # มุมพอดี (ข้ามทั้งสองแกน) — ขอบนูนของของทึบ
            return (-math.copysign(1.0, d[0]), 0.0, 0.0) if abs(d[0]) >= abs(d[2]) else \
                (0.0, 0.0, -math.copysign(1.0, d[2]))
    return (0.0, 1.0, 0.0)


def bot_xform(p, x, y, z, yaw, drop=0.0, fall=0.0, k=1.0):
    """กระจก python ของ vertex shader หุ่น (ใช้ใน selftest/เครื่องมือ): ท้องถิ่น → โลก
    หมอบ: y −= k·drop ; ตาย: หมุนหงายรอบแกน x ท้องถิ่นที่เท้า fall·90° แล้วยกขึ้นให้ลำตัวนอนบนพื้น ; แล้วหมุน yaw"""
    px, py, pz = p[0], p[1] - k * drop, p[2]
    if fall > 0.0:
        a = fall * math.pi / 2
        ca, sa = math.cos(a), math.sin(a)
        py, pz = py * ca + pz * sa + BODY_HW * sa, -py * sa + pz * ca
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (px * cy + pz * sy + x, py + y, -px * sy + pz * cy + z)


# ─────────────────────────── shaders ───────────────────────────
_CAM = """
layout(std140) uniform Cam {
    mat4 u_view;     // world→cam (view_matrix)
    vec4 u_proj;     // 2f/W, 2f/H, 2·ZNEAR, f (px ของ overlay)
    vec4 u_eye;      // ตำแหน่งตา xyz, w = เวลาเกม t
    vec4 u_right;    // แกนขวาของกล้องในโลก, w = กว้าง fbo (px)
    vec4 u_up;       // แกนบนของกล้องในโลก, w = สูง fbo (px)
    vec4 u_fog;      // สีหมอก rgb, w = ความหนาแน่น/ม.
};
vec4 proj(vec3 w){
    vec3 c = (u_view * vec4(w, 1.0)).xyz;
    // = glrender._GEO_VS เป๊ะ: w = z (perspective), z_c = z − 2·ZNEAR → clip ที่ z = ZNEAR, depth = 1 − ZNEAR/z
    return vec4(c.x * u_proj.x, c.y * u_proj.y, c.z - u_proj.z, c.z);
}
vec3 fogged(vec3 col, vec3 p, float k){
    // ระยะหมอก d²/(d + FOG_START): เริ่มแบบกำลังสอง (ไม่มีหักมุม → ไม่เกิดวงแหวนบนกำแพงเรียบ) ไกลแล้ว ≈ d − FOG_START
    float d = distance(p, u_eye.xyz);
    return mix(col, u_fog.rgb, k * (1.0 - exp(-d * d / (d + %.1f) * u_fog.w)));
}
float shade(vec3 n){      // ambient cube (น้ำหนัก n²): ผนังสี่ทิศได้เฉดต่างกันหมด (ขอบมุมอ่านง่าย) ; พื้น = 1 ; ทแยง = ผสมนุ่ม
    vec3 n2 = n * n;
    return dot(n2, mix(vec3(0.64, 0.45, 0.72), vec3(0.80, 1.00, 0.90), step(0.0, n)));
}
""" % FOG_START

_FS_TRI_VS = """#version 330
in vec2 in_pos;
void main(){ gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

_SKY_FS = """#version 330
""" + _CAM + """
uniform vec3 u_zen;
uniform vec3 u_hor;
uniform vec3 u_gnd;
out vec4 f_color;
void main(){
    vec2 ndc = gl_FragCoord.xy / vec2(u_right.w, u_up.w) * 2.0 - 1.0;
    vec3 dw = transpose(mat3(u_view)) * vec3(ndc.x / u_proj.x, ndc.y / u_proj.y, 1.0);
    float e = dw.y / length(dw);
    vec3 c = e >= 0.0 ? mix(u_hor, u_zen, pow(e, 0.6)) : mix(u_hor, u_gnd, clamp(-e * 5.0, 0.0, 1.0));
    f_color = vec4(c, 1.0);
}
"""

_BLIT_FS = """#version 330
uniform sampler2D u_tex;
uniform vec2 u_dst;
out vec4 f_color;
void main(){ f_color = vec4(texture(u_tex, gl_FragCoord.xy / u_dst).rgb, 1.0); }
"""

_MAP_VS = """#version 330
""" + _CAM + """
in vec3 in_pos;
in vec3 in_nrm;
in vec3 in_col;
in float in_flag;
in float in_aux;
centroid out vec3 v_pos;
flat out vec3 v_nrm;
out vec3 v_col;
flat out int v_flag;
centroid out float v_aux;
void main(){
    v_pos = in_pos; v_nrm = in_nrm; v_col = in_col; v_flag = int(in_flag + 0.5); v_aux = in_aux;
    gl_Position = proj(in_pos);
}
"""

_MAP_FS = """#version 330
""" + _CAM + """
uniform sampler2D u_grid;   // RGBA8 ต่อช่อง: kind, รหัสความสูง, zone
uniform vec4 u_geo;         // x0, z0, 1/cell, cell
uniform vec3 u_dim;         // nx, nz, wall_y
uniform int u_zone;         // โซนที่ไฮไลต์ (0 = ไม่มี)
uniform sampler2D u_nf;     // สนาม normal เกลี่ยต่อช่อง (RG มาสก์ทึบ, BA ความสูงพื้น) — LINEAR
uniform vec3 u_ledge;       // สีหน้า ledge สูง (ปูนอมเหลืองกว่ากำแพงนิด)
uniform sampler2D u_dens;   // มาสก์ทึบ (VOID/WALL/BOX) เบลอ R 2 ช่อง ต่อช่อง — LINEAR (เงาชิดกำแพงเรียบ)
uniform sampler2D u_reg;    // สีประจำย่าน (clutchmesh.region_rgba) ต่อบล็อก — LINEAR (ไล่สีนุ่มตรงรอยต่อย่าน)
uniform vec4 u_rgeo;        // x0, z0, 1/ขนาดบล็อก (ม.), -
uniform vec2 u_rdim;        // จำนวนบล็อก
centroid in vec3 v_pos;      // centroid: พิกเซลขอบ MSAA ไม่ประมาณค่าเลยหน้าไปช่องข้างเคียง (เคยเป็นเส้นบางตามขอบ)
flat in vec3 v_nrm;
in vec3 v_col;
flat in int v_flag;
centroid in float v_aux;
out vec4 f_color;

float floor_smooth(vec2 g, float fb){                // พื้นแบบ bilinear จากกลางช่องที่เดินได้ (ทางลาดขั้น 5 ซม. → ลาดเรียบ)
    // เฉพาะช่องที่สูงต่างจากฐาน fb ไม่เกิน 16 ซม. (ขั้นทางลาด) — ledge จริงแนวเฉียงไม่ถูกเฉลี่ยเข้ามา (เคยเป็นสามเหลี่ยมสีพื้น)
    vec2 u = g - 0.5;
    ivec2 i0 = ivec2(floor(u));
    vec2 f = u - vec2(i0);
    float acc = 0.0, ws = 0.0;
    for (int k = 0; k < 4; k++) {
        ivec2 o = ivec2(k & 1, k >> 1);
        ivec2 c = i0 + o;
        if (c.x < 0 || c.y < 0 || c.x >= int(u_dim.x) || c.y >= int(u_dim.y)) continue;
        vec4 t = texelFetch(u_grid, c, 0);
        int kk = int(t.r * 255.0 + 0.5);
        float h = (floor(t.g * 255.0 + 0.5) - 64.0) * 0.05;
        if ((kk != 1 && kk != 2) || abs(h - fb) > 0.16) continue;
        float w = (o.x == 1 ? f.x : 1.0 - f.x) * (o.y == 1 ? f.y : 1.0 - f.y);
        acc += w * h;
        ws += w;
    }
    return ws > 1e-4 ? acc / ws : fb;
}

vec3 floor_col(float y, bool site){                  // = clutchmesh.floor_rgb (แก้คู่กัน)
    float L = clamp(118.0 + y / 0.12, 55.0, 235.0) / 255.0;
    return site ? vec3(min(1.0, L + 34.0 / 255.0), min(1.0, L + 34.0 / 255.0), L) : vec3(L);
}

float cell_top_k(ivec2 c, out int zone, out int kind){
    zone = 0;
    kind = 0;
    if (c.x < 0 || c.y < 0 || c.x >= int(u_dim.x) || c.y >= int(u_dim.y)) return u_dim.z;
    vec4 g = texelFetch(u_grid, c, 0);
    kind = int(g.r * 255.0 + 0.5);
    zone = int(g.b * 255.0 + 0.5);
    if (kind == 0 || kind == 4) return u_dim.z;           // VOID/WALL = ทึบถึงยอดกำแพง
    return (floor(g.g * 255.0 + 0.5) - 64.0) * 0.05;
}

float cell_top(ivec2 c, out int zone){
    int k;
    return cell_top_k(c, zone, k);
}

vec3 region(vec2 xz){                                    // สีย่านที่จุด xz (ผนังถามที่ด้านหน้าของมัน)
    return texture(u_reg, (xz - u_rgeo.xy) * u_rgeo.z / u_rdim).rgb;
}

float ao_dens(vec2 xz){                                  // เงาชิดกำแพง/กล่องแบบเรียบ: มาสก์ทึบเบลอ R 0.5 ม. (ขอบตรง = 0.5)
    float dn = texture(u_dens, (xz - u_geo.xy) * u_geo.z / u_dim.xy).r;
    return mix(1.0, 0.58, smoothstep(0.0, 0.5, dn));
}

float ao_near(ivec2 c, vec2 f, float y){             // เงาชิดของที่สูงกว่า (≥ 20 ซม.) ในรัศมี 0.3 ม. — ใช้กับขั้นทางลาด
    float ao = 1.0;
    int zz;
    int kk;
    for (int k = 0; k < 9; k++) {
        ivec2 o = ivec2(k %% 3 - 1, k / 3 - 1);
        if (k == 4 || cell_top_k(c + o, zz, kk) <= y + 0.2 || kk == 0 || kk == 3 || kk == 4) continue;
        vec2 dd = max(max(vec2(o) - f, f - vec2(o) - 1.0), 0.0);
        ao = min(ao, mix(0.60, 1.0, smoothstep(0.0, 0.30, length(dd) * u_geo.w)));
    }
    return min(ao, ao_dens((vec2(c) + f) * u_geo.w + u_geo.xy));
}

void main(){
    vec3 n = v_nrm;
    vec3 ln = n;                                          // normal ที่ใช้ให้แสง (เกลี่ยได้) — n = normal จริงของหน้า
    vec3 col = v_col;
    float cs = u_geo.w;
    if ((v_flag & 32) != 0) {                             // F_CAP ฝาบนมวลกำแพง (เห็นจากมุมสูงเท่านั้น)
        f_color = vec4(fogged(col, v_pos, 1.0), 1.0);
        return;
    }
    if (n.y > 0.5) {                                      // ── พื้น/ไซต์/หลังกล่อง ──
        vec2 gp = (v_pos.xz - u_geo.xy) * u_geo.z;
        ivec2 c = ivec2(floor(gp));
        vec2 f = gp - vec2(c);
        float y = v_pos.y;
        float pw = max(length(fwidth(v_pos.xz)), 1e-4);  // ม. ต่อพิกเซล (ให้เส้นกว้าง ≥ 1 px ทุกระยะ)
        float ao = 1.0, lip = 0.0, zedge = 0.0;
        int zc;
        cell_top(c, zc);
        for (int dz = -1; dz <= 1; dz++) {
            for (int dx = -1; dx <= 1; dx++) {
                if (dx == 0 && dz == 0) continue;
                int zn, kn;
                float tn = cell_top_k(c + ivec2(dx, dz), zn, kn);
                vec2 lo = vec2(float(dx), float(dz));
                vec2 dd = max(max(lo - f, f - lo - 1.0), 0.0);
                float d = length(dd) * cs;
                bool mass = kn == 0 || kn == 3 || kn == 4;        // กำแพง/กล่อง ใช้ ao_dens (เรียบตามแนวเฉียง)
                if (tn > y + 0.2 && !mass) ao = min(ao, mix(0.60, 1.0, smoothstep(0.0, 0.30, d)));   // เงาชิด ledge
                else if (tn < y - 0.2) lip = max(lip, 1.0 - smoothstep(0.0, max(0.035, 1.5 * pw), d));  // ขอบ ledge
                if (u_zone > 0 && zc == u_zone && zn != u_zone)
                    zedge = max(zedge, 1.0 - smoothstep(0.0, max(0.06, 2.0 * pw), d));
            }
        }
        if ((v_flag & 1) != 0) ao = min(ao, ao_dens(v_pos.xz));   // พื้นเท่านั้น (หลังกล่องอยู่ในมาสก์ตัวเอง)
        if ((v_flag & 1) != 0) {                          // F_GRID เส้นตาราง 1 ม. (กะระยะ) จางลงเมื่อไกล
            // เส้นอยู่กลางช่องกริด (x0 + ½ช่อง + k ม.) ไม่ทับขอบช่อง — บนทางลาดขั้น 5 ซม. เส้นที่ขอบช่องจะขาดเป็นประ
            vec2 fw = max(fwidth(v_pos.xz), vec2(1e-4));
            vec2 gd = abs(fract(v_pos.xz - u_geo.xy - 0.5 * cs + 0.5) - 0.5) / fw;
            float line = 1.0 - min(min(gd.x, gd.y), 1.0);
            col *= 1.0 - 0.17 * line * (1.0 - smoothstep(0.04, 0.2, max(fw.x, fw.y)));
        }
        if ((v_flag & 3) == 1) {                          // พื้นทางเดิน (ไม่ใช่ไซต์/หลังกล่อง): ย้อมโทนย่านจาง ๆ
            vec3 rc = region(v_pos.xz);
            col *= mix(vec3(1.0), rc / max(rc.r, max(rc.g, rc.b)), %.2f);
        }
        if (u_zone > 0 && zc == u_zone) {                 // โซนวาง spike ตอนถือ spike: เหลืองกะพริบช้า + ขอบโซน
            float pulse = 0.5 + 0.5 * sin(u_eye.w * 4.0);
            col = mix(col, vec3(1.0, 0.80, 0.28), 0.24 + 0.10 * pulse);
            col = mix(col, vec3(1.0, 0.93, 0.55), 0.85 * zedge);
        }
        col *= ao;
        col = mix(col, min(col * 1.35 + 0.10, vec3(1.0)), 0.9 * lip);
    } else {                                              // ── หน้าแนวตั้ง: กำแพง / ขอบ ledge / ข้างกล่อง ──
        ivec2 na = ivec2(int(round(n.x)), int(round(n.z)));                         // normal จริงตามแกนกริด
        ivec2 cf = ivec2(floor((v_pos.xz + n.xz * (0.25 * cs) - u_geo.xy) * u_geo.z));   // ช่องหน้า (ด้านต่ำ)
        ivec2 tx = ivec2(-na.y, na.x);                                               // แกนสัมผัสของหน้า
        int zz;
        float tb = cell_top(cf - na, zz);                 // ช่องหลัง (ด้านสูง)
        float thr = 0.5 * (cell_top(cf, zz) + tb);        // ทึบ = ยอดเกินกึ่งกลางขั้นของหน้านี้ (แยกกำแพง/ledge/กล่องเอง)
        float below = tb - v_pos.y;                       // ห่างจากขอบบนของหน้านี้ (ม.)
        float hgt = below + v_aux;
        // ขั้นบันไดของกำแพงเฉียงจากกริด = หน้าสั้น (≤ 4 ช่อง) ที่ปลายหนึ่งเป็นมุมนูน อีกปลายเป็นมุมเว้า → ใช้ normal เกลี่ย
        // (ไม่เป็นลายทางสลับ) ; หน้าอื่นทั้งหมด (กำแพงตรง, หัวกำแพงหนา 1 ม. ที่นูนทั้งสองปลาย, ช่องเว้า) = normal จริง มุมคม
        // — สำคัญตอนเล็งมุม ; ≤ 4 ช่องทำให้ทุกพิกเซลของหน้าเดียวกันเห็นปลายทั้งสองในหน้าต่าง ±3 → จัดประเภทเหมือนกันทั้งหน้า
        int run = 1, ends = 0;                            // ends: บิต 1 = เจอมุมนูน, บิต 2 = เจอมุมเว้า
        for (int sd = -1; sd <= 1; sd += 2) {
            for (int k = 1; k <= 3; k++) {
                ivec2 o = cf + tx * (sd * k);
                if (cell_top(o, zz) > thr) { ends |= 2; break; }
                if (cell_top(o - na, zz) <= thr) { ends |= 1; break; }
                run++;
            }
        }
        bool stair = run <= 4 && ends == 3;
        if (stair) {                                      // normal เกลี่ยจากสนามที่คำนวณไว้ตอน set_map (_NF_FS) — ดึงครั้งเดียว
            vec4 nf = texture(u_nf, ((v_pos.xz - u_geo.xy) * u_geo.z + n.xz * 0.75) / u_dim.xy);
            vec2 acc = (v_flag & 16) != 0 ? nf.ba : nf.rg;   // ledge: สนามความสูง ; กำแพง/กล่อง: มาสก์ทึบ
            float L = length(acc);
            // ขั้นสั้นของกำแพงเฉียงตื้น (~10°) ทำมุมกับทิศรวม ~80° — รับทุกทิศที่ยังออกด้านหน้าหน้านี้
            if (L > 1e-5 && dot(acc / L, n.xz) > 0.05) ln = vec3(acc.x / L, 0.0, acc.y / L);
        }
        float pw = max(length(fwidth(v_pos)), 1e-4);
        float aa = max(0.012, 1.2 * pw);
        bool riser = (v_flag & 16) != 0 && hgt <= 0.16;
        // ผนังริมทางลาด (พื้นหน้าหน้าเป็นขั้น 5 ซม. ทีละช่อง): ใช้พื้นแบบเรียบ (bilinear) เป็นฐานแทนฐานจริงของแต่ละหน้า
        // → เงาไล่/แถบฐานเป็นเส้นเรียบตามทางลาด ไม่เป็นฟันเลื่อย ; ส่วนใต้เส้นพื้นเรียบทาสีพื้น ; ต่างเกิน 16 ซม. (ledge จริง
        //   ตั้งฉากกำแพง) ใช้ฐานจริง
        float fs = floor_smooth((v_pos.xz - u_geo.xy) * u_geo.z + n.xz * 0.5, v_pos.y - v_aux);
        bool rampb = abs(fs - (v_pos.y - v_aux)) < 0.16;
        float ay = rampb ? v_pos.y - fs : v_aux;
        bool under = rampb && ay < 0.0 && !riser;
        if (under) {
            float kf = texelFetch(u_grid, clamp(cf, ivec2(0), ivec2(u_dim.xy) - 1), 0).r * 255.0;
            col = floor_col(v_pos.y, abs(kf - 2.0) < 0.5);
            ln = vec3(0.0, 1.0, 0.0);
        } else if (riser) {                                      // ขั้น 5–15 ซม. ของทางลาด (ความสูงกริด) → ทาเหมือนพื้นชั้นบน
            col = v_col / 0.78;                           //   ทางลาดจึงดูเป็นทางลาด ไม่ใช่บันไดลายทาง
            ln = vec3(0.0, 1.0, 0.0);
            vec2 gq = (v_pos.xz - u_geo.xy) * u_geo.z + n.xz * 0.01;        // เงาชิดกำแพงต่อผ่านขั้น (ไม่เป็นฟันหวี)
            col *= ao_near(ivec2(floor(gq)), gq - floor(gq), v_pos.y);
            float tc = dot(v_pos.xz - u_geo.xy - 0.5 * cs, vec2(-n.z, n.x));   // เส้นตาราง 1 ม. ต่อผ่านขั้น (ไม่ขาดเป็นประ)
            float ftc = max(fwidth(tc), 1e-4);
            float line = 1.0 - min(abs(fract(tc + 0.5) - 0.5) / ftc, 1.0);
            col *= 1.0 - 0.17 * line * (1.0 - smoothstep(0.04, 0.2, ftc));
        } else if ((v_flag & 8) != 0) {                   // F_WALL ปูนทาสีตามย่าน + บัว/ผนังล่างเข้ม + แถบชั้น + ขอบช่องประตู
            vec3 rc = region(v_pos.xz + n.xz * 0.4);      // สีย่านฝั่งที่ผนังหันไป
            vec3 wains = mix(rc * 0.62, rc * rc * 0.80, 0.5);   // ผนังล่าง (บัว) — โทนเดียวกันแต่เข้ม/อิ่มกว่า
            col = mix(wains, rc * 0.90, smoothstep(%.2f - aa, %.2f + aa, ay));
            float capl = 1.0 - smoothstep(0.0, max(0.018, 1.2 * pw), abs(ay - %.2f - 0.02));   // คิ้วบัว (สว่าง)
            col = mix(col, min(rc * 1.05 + 0.04, vec3(1.0)), 0.55 * capl);
            col *= mix(1.0, 0.80, smoothstep(2.6, 7.0, ay));   // สูงขึ้นเข้มลง (ไม่เป็นแผ่นขาวทั้งผืน)
            col *= mix(0.74, 1.0, smoothstep(0.0, 1.0, ay));
            col *= mix(0.45, 1.0, smoothstep(0.10 - aa, 0.10 + aa, ay));   // ขอบบัวเชิงผนังเข้ม
            if (!stair) {                                 // รอยต่อแผ่นเฉพาะกำแพงตรง (บนขั้นบันไดจะเป็นเส้นถี่มั่ว)
                float t = dot(v_pos.xz, vec2(-n.z, n.x));
                float ft = fwidth(t);
                float seam = 1.0 - min(abs(fract(t / 2.0 + 0.5) - 0.5) * 2.0 / max(ft, 1e-4), 1.0);
                col *= 1.0 - 0.10 * seam * (1.0 - smoothstep(0.03, 0.12, ft));
                // กรอบช่องประตู/ปลายกำแพง: มุมนูน (ของทึบหลังผนังสิ้นสุด + หน้าผนังยังโล่ง) ห่าง ≤ JAMB_W → แถบเข้ม + สันสว่าง
                float tp = dot((v_pos.xz - u_geo.xy) * u_geo.z, vec2(tx));
                float fr = fract(tp);
                int z1, z2, z3, z4;
                bool eP = cell_top(cf + tx - na, z1) <= thr && cell_top(cf + tx, z2) <= thr;
                bool eM = cell_top(cf - tx - na, z3) <= thr && cell_top(cf - tx, z4) <= thr;
                float dj = min(eP ? (1.0 - fr) * cs : 9.0, eM ? fr * cs : 9.0);
                float jb = 1.0 - smoothstep(%.3f - aa, %.3f + aa, dj);
                float jl = 1.0 - smoothstep(0.0, max(0.012, 1.3 * pw), dj);
                col = mix(col, rc * 0.42, 0.85 * jb * (1.0 - jl));
                col = mix(col, min(rc * 1.1 + 0.08, vec3(1.0)), 0.7 * jl);
            }
        } else if ((v_flag & 4) != 0) {                   // F_BOX ลังไม้: ไม้กระดานแนวนอน + ฐานเข้ม
            float fa = max(fwidth(v_aux), 1e-4);
            float plank = 1.0 - min(abs(fract(v_aux / 0.275 + 0.5) - 0.5) * 0.275 / fa, 1.0);
            col *= 1.0 - 0.22 * plank * (1.0 - smoothstep(0.02, 0.08, fa));
            col *= mix(0.62, 1.0, smoothstep(0.05 - aa, 0.05 + aa, ay));
        } else {                                          // F_LEDGE ขอบต่างระดับ: เตี้ย = สีพื้นเข้มลง ; สูง (≥ 1.6 ม.) = ปูนแบบกำแพง
            col = mix(col * 1.15, u_ledge * region(v_pos.xz + n.xz * 0.4) / 0.86, smoothstep(0.4, 1.6, hgt));   //   ไม่เป็นแท่งเทาดำทั้งผืน
            col *= mix(0.78, 1.0, smoothstep(0.0, 0.8, ay));
        }
        if (!riser && !under) {
            float lipv = 1.0 - smoothstep(0.0, max(0.025, 1.5 * pw), below);
            col = mix(col, min(col * 1.3 + 0.08, vec3(1.0)), 0.8 * lipv);
        }
    }
    col *= shade(ln);
    f_color = vec4(fogged(col, v_pos, 1.0), 1.0);
}
""" % (FLOOR_TINT, WAINSCOT_Y, WAINSCOT_Y, WAINSCOT_Y, JAMB_W, JAMB_W)

# สนาม normal เกลี่ยของผนังขั้นบันได (กำแพงเฉียงจากกริด) — วาดครั้งเดียวต่อด่านลง texture RGBA16F ขนาด nx×nz
# ต่อช่อง (ประเมินที่กลางช่อง, เคอร์เนล w = (1 − r²/R²)², R 6 ช่อง = 1.5 ม., 169 texel ต่อช่อง ครั้งเดียว):
#   RG = −∇ Σ w·ทึบ (VOID/WALL/BOX) → ทิศออกจากของทึบ ; BA = −∇ ของความสูงพื้นแบบ normalized convolution (เฉพาะช่องเดินได้)
# shader ฉากสุ่มแบบ bilinear ที่ ¾ ช่องหน้าผิว (ดึงครั้งเดียวต่อพิกเซล) — จำลองบนขั้นบันไดชัน 1:1…1:8: ทิศคลาดจากแนวจริง
# ≤ ±2° (R 3.4 ได้ ±9° ที่ 1:8 ; คำนวณสดต่อพิกเซลแพงกว่า ~0.8 ms ที่ 1440p ด่านขอบหยักสุด)
_NF_FS = """#version 330
uniform sampler2D u_grid;
uniform vec3 u_dim;
layout(location = 0) out vec4 f_color;
layout(location = 1) out vec4 f_dens;
void main(){
    ivec2 c0 = ivec2(gl_FragCoord.xy);
    vec2 sg = vec2(0.0), gN = vec2(0.0), gD = vec2(0.0);
    float N = 0.0, Dn = 0.0, ms = 0.0, mw = 0.0;
    for (int dz = -6; dz <= 6; dz++) {
        for (int dx = -6; dx <= 6; dx++) {
            vec2 d = vec2(float(-dx), float(-dz));
            float q = 1.0 - dot(d, d) / 36.0;
            if (q <= 0.0) continue;
            ivec2 c = c0 + ivec2(dx, dz);
            int k = 0;
            float h = 0.0;
            if (c.x >= 0 && c.y >= 0 && c.x < int(u_dim.x) && c.y < int(u_dim.y)) {
                vec4 g = texelFetch(u_grid, c, 0);
                k = int(g.r * 255.0 + 0.5);
                h = (floor(g.g * 255.0 + 0.5) - 64.0) * 0.05;
            }
            float q2 = max(0.0, 1.0 - dot(d, d) / 4.0);      // เคอร์เนลเล็ก R 2 ช่อง ของ ao_dens
            mw += q2 * q2;
            if (k == 0 || k == 3 || k == 4) {
                sg += q * d;
                ms += q2 * q2;
            } else {
                vec2 gw = (-4.0 / 36.0) * q * d;
                N += q * q * h; Dn += q * q; gN += gw * h; gD += gw;
            }
        }
    }
    vec2 gF = Dn > 1e-6 ? (gN * Dn - N * gD) / (Dn * Dn) : vec2(0.0);
    f_color = vec4(sg, -gF);
    f_dens = vec4(ms / mw);
}
"""

_ACT_VS = """#version 330
""" + _CAM + """
in vec3 in_pos;
in vec3 in_nrm;
in float in_k;     // กระดูก + 32·var (clutchmesh.B_* / var = ชิ้นที่แสดงเฉพาะอาวุธนั้น)
in float in_mat;
in vec4 i_pos;     // x, y(พื้นที่ยืน), z, yaw
in vec4 i_st;      // drop (ม.), flash 0..1, fall 0..1, alpha
in vec4 i_ex;      // rim 0..1, light 0..1 (spike) | ปืนยื่นได้ถึง z ท้องถิ่น (บอท — gun_reach), sink (ม.), kind (0 บอท, 1 ศพ, 2 spike, 3 spike กู้แล้ว)
in vec4 i_aim;     // pitch (เรเดียน), รีโหลด 0..1, id อาวุธ (0 = ไม่มี), สะโพก y
in vec4 i_kl;      // เข่าซ้าย xyz, เท้าซ้ายเงย
in vec4 i_al;      // ข้อเท้าซ้าย xyz, สะโพก z
in vec4 i_kr;      // เข่าขวา xyz, เท้าขวาเงย
in vec4 i_ar;      // ข้อเท้าขวา xyz, -
uniform vec3 u_muz[7];   // ปลายลำกล้องต่ออาวุธ (พิกัดหุ่นท่ายืน) — แสงไฟปากกระบอกส่องตัว
out vec3 v_w;
out vec3 v_n;
out vec3 v_loc;
flat out int v_mat;
flat out vec4 v_st;
flat out vec4 v_ex;
flat out vec3 v_mz;
flat out int v_bone;
const vec3 PIV = vec3(%.4f, %.4f, %.4f);
vec3 arms(vec3 q, float reach, float drop, bool isn){
    // ชุดแขน+ปืน: หดตามของทึบ (จุด) → หันเข้าอกตามรีโหลด → ก้ม/เงยรอบ PIV → หมอบ = clutchmesh.arms_xform
    if (!isn) { q.z = min(q.z, reach); q -= PIV; }
    float ry = %.4f * i_aim.y;
    float cy = cos(ry), sy = sin(ry);
    q = vec3(q.x * cy - q.z * sy, q.y, q.x * sy + q.z * cy);
    float a = i_aim.x + %.4f * i_aim.y;
    float ca = cos(a), sa = sin(a);
    q = vec3(q.x, q.y * ca + q.z * sa, -q.y * sa + q.z * ca);
    return isn ? q : q + PIV - vec3(0.0, drop, 0.0);
}
vec3 seg(vec3 p, vec3 A, vec3 B, inout vec3 n){
    // ท่อขาในพิกัดกระดูก (y = −t) → ระหว่างข้อต่อ A → B = clutchmesh.seg_xform
    vec3 u = normalize(B - A);
    vec3 rf = abs(u.x) < 0.9 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
    vec3 s = normalize(rf - u * dot(u, rf));
    vec3 f = cross(u, s);
    n = s * n.x - u * n.y + f * n.z;
    return A + (B - A) * (-p.y) + s * p.x + f * p.z;
}
void main(){
    int kb = int(in_k + 0.5);
    int bone = kb %% 32, var = kb / 32;
    int w = int(i_aim.z + 0.5);
    int arm = w == 3 ? 8 : (w >= 4 ? 9 : 7);
    v_st = i_st;
    v_ex = i_ex;
    v_mat = int(in_mat + 0.5);
    v_bone = bone;
    if (var != 0 && var != w && var != arm) {           // ชิ้นของอาวุธอื่น → ยุบนอกจอ (ไม่ raster)
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        v_w = vec3(0.0); v_n = vec3(0.0, 1.0, 0.0); v_loc = vec3(0.0); v_mz = vec3(0.0);
        return;
    }
    vec3 p = in_pos;
    vec3 n = in_nrm;
    float drop = i_st.x;
    if (bone == 1) p.y -= drop;
    else if (bone == 2) { p = arms(p, i_ex.y, drop, false); n = arms(n, 0.0, 0.0, true); }
    else if (bone == 3) p += vec3(0.0, i_aim.w - %.4f, i_al.w);
    else if (bone >= 4) {
        bool rt = bone >= 8;
        int b = bone - (rt ? 8 : 4);                       // 0 ต้นขา, 1 หน้าแข้ง, 2 เข่า, 3 เท้า
        vec3 K = rt ? i_kr.xyz : i_kl.xyz;
        vec3 A = rt ? i_ar.xyz : i_al.xyz;
        vec3 H = vec3(rt ? %.4f : -%.4f, i_aim.w, i_al.w);
        if (b == 0) p = seg(p, H, K, n);
        else if (b == 1) p = seg(p, K, A, n);
        else if (b == 2) p += K;
        else {
            float fp = rt ? i_kr.w : i_kl.w;
            float ca = cos(fp), sa = sin(fp);
            p = vec3(p.x, p.y * ca + p.z * sa, -p.y * sa + p.z * ca) + A;
            n = vec3(n.x, n.y * ca + n.z * sa, -n.y * sa + n.z * ca);
        }
    }
    v_loc = p;
    v_mz = arms(u_muz[clamp(w, 0, 6)], 9.0, drop, false);
    if (i_st.z > 0.0) {                                   // ล้มหงายรอบแกน x ที่เท้า + ยกให้ลำตัวนอนบนพื้น
        float a = i_st.z * 1.5707963;
        float ca = cos(a), sa = sin(a);
        p = vec3(p.x, p.y * ca + p.z * sa + %.4f * sa, -p.y * sa + p.z * ca);
        n = vec3(n.x, n.y * ca + n.z * sa, -n.y * sa + n.z * ca);
    }
    p.y -= i_ex.z;
    float cy = cos(i_pos.w), sy = sin(i_pos.w);
    v_w = vec3(p.x * cy + p.z * sy, p.y, -p.x * sy + p.z * cy) + i_pos.xyz;
    v_n = vec3(n.x * cy + n.z * sy, n.y, -n.x * sy + n.z * cy);
    gl_Position = proj(v_w);
}
""" % (_cmesh.SH_PIV + (_cmesh.RELOAD_YAW, _cmesh.RELOAD_PITCH, _cmesh.HIP_Y, _cmesh.HIP_X, _cmesh.HIP_X, BODY_HW))

_ACT_FS = """#version 330
""" + _CAM + """
uniform vec3 u_rim;
uniform int u_body_only;    // 1 = ไม่วาดชุดแขน/ปืน (clutch_view วัดตัวหุ่นเทียบกรอบ hitbox)
in vec3 v_w;
in vec3 v_n;
in vec3 v_loc;
flat in int v_mat;
flat in vec4 v_st;
flat in vec4 v_ex;
flat in vec3 v_mz;
flat in int v_bone;
out vec4 f_color;
void main(){
    if (u_body_only == 1 && v_bone == 2) discard;
    vec3 N = normalize(v_n);
    vec3 V = normalize(u_eye.xyz - v_w);
    vec3 base;
    float emit = 0.0;
    int m = v_mat;
    bool corpse = v_ex.w > 0.5 && v_ex.w < 1.5;
    if ((m == 3 || m == 12) && corpse) discard;           // ศพ: ปืนหลุดมือ (ไม่งั้นล้มหงายแล้วปืนชี้ฟ้า)
    float hy = %.4f - v_st.x;                             // ขอบบนลำตัวตามท่า
    if (m == 0) {                                         // ลำตัว: เสื้อ + เสื้อเกราะอก/หลัง + เข็มขัด
        base = vec3(0.17, 0.19, 0.20);
        if (v_loc.y > hy - 0.40 && v_loc.y < hy - 0.07) base = vec3(0.33, 0.32, 0.28);
        if (v_loc.y < hy - 0.50) base = vec3(0.09, 0.09, 0.09);
    } else if (m == 7) {
        base = vec3(0.23, 0.23, 0.21);                    // กางเกง
    } else if (m == 1) {                                  // หัว: ผม/หมวกด้านบน-หลัง, หน้าด้านหน้า, แถบตาเข้ม (บอกทิศที่มอง)
        float hc = %.4f - v_st.x;
        base = vec3(0.11, 0.10, 0.11);
        if (v_loc.z > 0.035 && v_loc.y < hc + 0.045) base = vec3(0.60, 0.45, 0.37);
        if (v_loc.z > 0.08 && abs(v_loc.y - hc - 0.018) < 0.020) base = vec3(0.05, 0.05, 0.06);
    } else if (m == 2) {
        base = vec3(0.58, 0.44, 0.36);                    // ผิว (คอ)
    } else if (m == 13) {
        base = vec3(0.17, 0.19, 0.20);                    // แขนเสื้อ
    } else if (m == 3) {
        base = vec3(0.08, 0.08, 0.09);
    } else if (m == 12) {
        base = vec3(0.24, 0.24, 0.26);
    } else if (m == 8) {
        base = vec3(0.35, 0.34, 0.30);                    // สนับ/บ่า
    } else if (m == 9) {
        base = vec3(0.30, 0.25, 0.20);                    // ถุงมือหนัง
    } else if (m == 10) {
        base = vec3(0.13, 0.12, 0.11);                    // รองเท้า
    } else if (m == 4) {
        base = vec3(0.34, 0.35, 0.38);
    } else if (m == 6) {
        base = v_ex.w > 2.5 ? vec3(0.30, 0.85, 0.95) : vec3(0.85, 0.72, 0.30);
    } else {                                              // M_LIGHT ไฟ spike: แดงกะพริบ (กู้แล้ว = ฟ้าหรี่)
        vec3 on = v_ex.w > 2.5 ? vec3(0.35, 0.85, 1.0) : vec3(1.0, 0.10, 0.06);
        base = mix(vec3(0.22, 0.03, 0.03), on, v_ex.y);
        emit = 0.6 + 0.4 * v_ex.y;
    }
    vec3 col = base * mix(shade(N), 1.0, emit);
    if (v_ex.w < 0.5) {
        // ไฮไลต์ศัตรูแบบเกม: เส้นขอบแดงด้านใน "กว้างคงที่เป็นพิกเซล" (N·V → 0 ที่ขอบเงา ; fwidth = เปลี่ยนต่อพิกเซล) — อยู่ใน
        // เงาของหุ่นเสมอ (ไม่ขยายออกนอกตัว = ไม่มีเส้นแดงโผล่พ้นมุมกำแพงก่อนตัว) ; ไกลมาก (หุ่นไม่กี่ px) ทั้งตัวกลายเป็นแดง
        float ndv = abs(dot(N, V));
        float fw = max(fwidth(ndv), 1e-4);
        float edge = 1.0 - smoothstep(%.2f * fw, %.2f * fw + 0.03, ndv);
        col = mix(col, u_rim, clamp(edge, 0.0, 1.0) * v_ex.x);
        col = mix(col, u_rim, 0.30 * pow(1.0 - ndv, 3.0) * v_ex.x);
    }
    // บอทเพิ่งยิง (flash): แสงไฟปากกระบอกส้มส่องหุ่นรอบปลายปืน (~0.6 ม.) + ทั้งตัวอุ่นขึ้นนิด — ชี้ว่าใครยิง
    vec3 dl = v_mz - v_loc;
    col += vec3(1.0, 0.70, 0.34) * v_st.y * (0.85 * exp(-dot(dl, dl) * 3.0) + 0.06);
    if (corpse) col = vec3(0.44, 0.42, 0.42) * (m == 1 ? 0.85 : 1.0) * shade(N);   // ศพ: เทาหม่น ไม่มีขอบแดง
    f_color = vec4(fogged(col, v_w, 0.6), v_st.w);
}
""" % ((BODY_Y1, HEAD_Y) + RIM_PX)

# มือ + ปืนบุคคลที่หนึ่ง (พิกัดกล้อง) — ความลึกบีบไว้ที่ window depth 0..0.01 (ฉากที่ใกล้สุดจริง ≥ ~0.8 เพราะชนกำแพงห่าง ≥ 0.3 ม.)
# → วาดทับฉากเสมอ ไม่จมกำแพงแม้ยืนชิด (ไม่ต้องเคลียร์ depth) แต่บังกันเองถูก ; ฉายด้วย f ไม่ซูม (ADS/สโคปไม่ขยายปืน)
_VM_VS = """#version 330
uniform mat4 u_m;       // พิกัดปืน → พิกัดกล้อง (clutchmesh.vm_matrix)
uniform vec4 u_vp;      // 2f/W, 2f/H (f ไม่ซูม), ชุดที่แสดง (var), id อาวุธ
in vec3 in_pos;
in vec3 in_nrm;
in float in_k;
in float in_mat;
out vec3 v_c;
out vec3 v_n;
flat out int v_mat;
void main(){
    int var = int(in_k + 0.5) / 32;
    v_mat = int(in_mat + 0.5);
    if (var != int(u_vp.z + 0.5) && var != int(u_vp.w + 0.5)) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        v_c = vec3(0.0); v_n = vec3(0.0, 1.0, 0.0);
        return;
    }
    vec3 c = (u_m * vec4(in_pos, 1.0)).xyz;
    v_c = c;
    v_n = mat3(u_m) * in_nrm;
    float dz = -1.0 + 0.02 * clamp(c.z / 2.0, 0.0, 1.0);
    gl_Position = vec4(c.x * u_vp.x, c.y * u_vp.y, dz * c.z, c.z);
}
"""

_VM_FS = """#version 330
uniform float u_blink;
in vec3 v_c;
in vec3 v_n;
flat in int v_mat;
out vec4 f_color;
void main(){
    vec3 N = normalize(v_n);
    int m = v_mat;
    vec3 base = vec3(0.10, 0.10, 0.11);
    float emit = 0.0;
    if (m == 12) base = vec3(0.30, 0.30, 0.32);
    else if (m == 9) base = vec3(0.36, 0.30, 0.24);
    else if (m == 0 || m == 13) base = vec3(0.20, 0.23, 0.25);
    else if (m == 4) base = vec3(0.34, 0.35, 0.38);
    else if (m == 6) base = vec3(0.55, 0.46, 0.20);
    else if (m == 5) { base = mix(vec3(0.25, 0.04, 0.04), vec3(1.0, 0.12, 0.08), u_blink); emit = 0.7; }
    vec3 L = normalize(vec3(%.3f, %.3f, %.3f));
    float d = max(dot(N, L), 0.0);
    float rim = pow(1.0 - clamp(abs(N.z), 0.0, 1.0), 2.0);
    vec3 col = base * mix(0.42 + 0.75 * d, 1.0, emit) + base * 0.35 * rim;
    // ยิ่งห่างจากกล้องยิ่งจาง (ปลายลำกล้อง) เล็กน้อยแบบเงาในเกม ; ใกล้มาก (แขนเสื้อ) เข้มลง
    col *= mix(0.80, 1.0, smoothstep(0.05, 0.30, v_c.z));
    f_color = vec4(col, 1.0);
}
""" % VM_LIGHT

# เส้นกระสุน = สี่เหลี่ยมขยายบนจอ (screen-space) รอบช่วง s0..s1 ที่ tracer_rows ตัดส่วนหลังกล้องทิ้งแล้ว ; ความกว้างและการจาง
# ใกล้ตาคิดต่อพิกเซลจากจุดบนเส้นจริง (v_s แบบ perspective-correct) — เดิมคิดที่ปลายสองข้าง: เส้นพลาดเฉียดหัวที่ปลายทั้งสองไกล
# กลายเป็นลิ่มกว้าง 500 px สว่างเต็มผ่านกลางจอ
_TRC_VS = """#version 330
""" + _CAM + """
in vec2 in_c;       // (ปลาย 0|1 ของช่วงที่วาด, ด้าน −1..1)
in vec4 i_a;        // จุดเริ่ม (ปากกระบอก) xyz, อายุ (วิ)
in vec4 i_b;        // จุดปลาย (จุดโดน) xyz, อายุขัย (วิ)
in vec2 i_s;        // ช่วงที่วาด s0..s1 บนเส้น a→b (z กล้อง ≥ TRC_ZMIN ทั้งช่วง)
out float v_s;
flat out vec3 v_pa;
flat out vec3 v_pb;
flat out vec4 v_seg;  // ปลายทั้งสองบนจอ (px ของ fbo, มุมล่างซ้าย = gl_FragCoord)
flat out float v_age;
void main(){
    vec4 c0 = proj(mix(i_a.xyz, i_b.xyz, i_s.x));
    vec4 c1 = proj(mix(i_a.xyz, i_b.xyz, i_s.y));
    vec2 sz = vec2(u_right.w, u_up.w);
    vec2 q0 = (c0.xy / c0.w * 0.5 + 0.5) * sz;
    vec2 q1 = (c1.xy / c1.w * 0.5 + 0.5) * sz;
    vec2 dir = q1 - q0;
    float L = length(dir);
    dir = L > 1e-3 ? dir / L : vec2(1.0, 0.0);
    float k = u_right.w * u_proj.x / (2.0 * u_proj.w);   // px ของ fbo ต่อ px ของ overlay (world_scale)
    vec4 c = in_c.x < 0.5 ? c0 : c1;
    vec2 q = (in_c.x < 0.5 ? q0 : q1) + vec2(-dir.y, dir.x) * (%.2f * k + 1.0) * in_c.y;
    gl_Position = vec4((q / sz * 2.0 - 1.0) * c.w, c.z, c.w);   // depth ตามเส้นจริง (ระนาบเดียวกัน — บังกำแพงถูก)
    v_s = mix(i_s.x, i_s.y, in_c.x);
    v_pa = i_a.xyz;
    v_pb = i_b.xyz;
    v_seg = vec4(q0, q1);
    v_age = clamp(1.0 - i_a.w / i_b.w, 0.0, 1.0);
}
""" % TRC_PX[0]

_TRC_FS = """#version 330
""" + _CAM + """
in float v_s;
flat in vec3 v_pa;
flat in vec3 v_pb;
flat in vec4 v_seg;
flat in float v_age;
out vec4 f_color;
void main(){
    float dist = distance(mix(v_pa, v_pb, v_s), u_eye.xyz);    // จุดบนเส้นที่พิกเซลนี้แทน → ระยะจากตา
    float k = u_right.w * u_proj.x / (2.0 * u_proj.w);
    float px = mix(%.2f, %.2f, smoothstep(2.0, 20.0, dist)) * k;   // ครึ่งความกว้างคงที่เป็นพิกเซล (ใกล้/ไกล)
    vec2 d = v_seg.zw - v_seg.xy;
    vec2 r = gl_FragCoord.xy - v_seg.xy;
    float L = length(d);
    float side = (L > 1e-3 ? abs(d.x * r.y - d.y * r.x) / L : length(r)) / px;
    if (side >= 1.0) discard;
    // จางตามอายุ ; โคนปากกระบอกจางกว่าหัวกระสุน ; ใกล้ตา < %.1f ม. จางหาย (กระสุนเฉียดหัว/พุ่งใส่เราไม่ทิ่มจอ)
    float a = v_age * mix(0.45, 1.0, clamp(v_s, 0.0, 1.0)) * smoothstep(%.2f, %.2f, dist) * (1.0 - side * side);
    f_color = vec4(vec3(1.0, 0.84, 0.52) * a * 0.95, 1.0);
}
""" % (TRC_PX + (TRC_NEAR[1],) + TRC_NEAR)

_BB_VS = """#version 330
""" + _CAM + """
in vec2 in_c;       // มุม ±1
in vec4 i_p;        // จุดศูนย์ xyz, รัศมี (ม.)
in vec4 i_c;        // สี rgb, ความแรง
out vec2 v_uv;
out vec4 v_col;
void main(){
    vec3 p = i_p.xyz;
    vec3 toe = u_eye.xyz - p;
    float dist = length(toe);
    p += toe / max(dist, 1e-4) * min(0.15, dist * 0.5);  // ขยับเข้าหากล้องนิด กันจมในปืน/ตัวสไปก์
    float s = max(i_p.w, dist * 7.0 / u_proj.w);         // รัศมีอย่างน้อย ~7 px
    v_uv = in_c;
    v_col = i_c;
    gl_Position = proj(p + (u_right.xyz * in_c.x + u_up.xyz * in_c.y) * s);
}
"""

_BB_FS = """#version 330
in vec2 v_uv;
in vec4 v_col;
out vec4 f_color;
void main(){
    float r = length(v_uv);
    float core = exp(-r * r * 9.0);
    vec2 q = abs(v_uv);
    float star = exp(-q.x * 18.0) * exp(-q.y * 2.6) + exp(-q.y * 18.0) * exp(-q.x * 2.6);
    float a = (core + 0.5 * star) * (1.0 - smoothstep(0.75, 1.0, r));
    f_color = vec4(v_col.rgb * v_col.a * a, 1.0);
}
"""

_MARK_VS = """#version 330
""" + _CAM + """
in vec2 in_c;
in vec4 i_p;        // จุด xyz, เวลาเกิด (t เกม)
in vec4 i_n;        // normal xyz, รัศมี
out vec2 v_uv;
out float v_a;
void main(){
    vec3 n = normalize(i_n.xyz);
    vec3 t = normalize(cross(n, abs(n.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
    vec3 b = cross(n, t);
    v_uv = in_c;
    v_a = 1.0 - smoothstep(%.2f, %.2f, u_eye.w - i_p.w);
    gl_Position = proj(i_p.xyz + n * 0.003 + (t * in_c.x + b * in_c.y) * i_n.w);
}
""" % MARK_FADE

_MARK_FS = """#version 330
in vec2 v_uv;
in float v_a;
out vec4 f_color;
void main(){
    float r = length(v_uv);
    float a = (1.0 - smoothstep(0.45, 1.0, r)) * v_a;
    if (a < 0.004) discard;
    vec3 c = mix(vec3(0.03, 0.028, 0.025), vec3(0.20, 0.18, 0.16), smoothstep(0.15, 0.9, r));
    f_color = vec4(c, 0.95 * a);
}
"""


# ─────────────────────────── ส่วน CPU ของ set_map (pure) ───────────────────────────
_PREP = weakref.WeakKeyDictionary()


def prepare(cmap, mesh=None):
    """เตรียมข้อมูลอัป GPU ของด่าน: vbo (interleave ตาม clutchmesh.FORMAT) + กริด RGBA8 (kind, h, zone, 0)
    เก็บแคชคู่กับ cmap (weakref) — MODE เรียกตอนโหลด/นับถอยหลังได้ ไม่งั้น set_map ทำเองในเฟรมแรก (~0.1–0.2 วิ)"""
    got = _PREP.get(cmap)
    if got is not None and mesh is None:
        return got
    t0 = time.perf_counter()
    me = mesh if mesh is not None else _cmesh.build(cmap)
    n = cmap.nx * cmap.nz
    grid = bytearray(4 * n)
    grid[0::4] = cmap.kind
    grid[1::4] = cmap.h
    grid[2::4] = cmap.zone
    d = {"vbo": _cmesh.interleave(me), "n_vert": me["n_vert"], "n_tri": me["n_tri"], "wall_y": me["wall_y"],
         "grid": bytes(grid), "region": _cmesh.region_rgba(cmap), "ms": (time.perf_counter() - t0) * 1000.0}
    _PREP[cmap] = d
    return d


def _flat(items, n):
    a = array("f")
    for it in items[:n]:
        a.extend(it)
    return a


# ─────────────────────────── ClutchGL ───────────────────────────
class ClutchGL:
    """ตัววาดฉาก CLUTCH บน context ของ display (หรือ standalone ของเครื่องมือ QA) — ดู docstring โมดูล"""

    def __init__(self, ctx, msaa=MSAA, world_scale=1.0, bot_model="agent"):
        """bot_model: "agent" = หุ่นเอเจนต์ที่เห็นในเกม ; "hitbox" = หุ่นทรง hitbox เป๊ะไม่มีปืน (clutch_view --check ใช้วัด
        depth เทียบ ray cast CPU แบบพิกเซลต่อพิกเซล)"""
        mgl = _moderngl()
        self.ctx = ctx
        self.bot_model = bot_model
        self.body_only = False   # QA: True = วาดหุ่นไม่มีแขน/ปืน
        self.cmap = None
        self.world_scale = float(world_scale)
        self.stats = {}
        self._objs = []
        self._map = ()
        self._fb = None
        self._fb_key = None
        self._inst = {}
        self._mk_key = None
        self._zone = -1
        self._fall = {}          # {(ลำดับบอท, dead_t, cmap): yaw ทิศล้ม} — เลือกครั้งเดียวต่อการตาย (corpse_yaw)
        self._trc_snap = {}      # {(ต้น, ปลาย): ต้นที่ย้ายไปปลายลำกล้องแล้ว} — เส้นกระสุนนิ่งในโลกตลอดอายุ
        self._fl_snap = {}       # เหมือนกันสำหรับไฟปากกระบอก
        self._gait = {}          # {ลำดับบอท: จังหวะก้าว/ความเร็ว/รีโหลด} ข้ามเฟรม (gait_step)
        self.msaa = msaa if (msaa and getattr(ctx, "max_samples", 0) >= msaa) else 0
        P = self._prog
        self.p_sky = P(_FS_TRI_VS, _SKY_FS)
        self.p_blit = P(_FS_TRI_VS, _BLIT_FS, cam=False)
        self.p_map = P(_MAP_VS, _MAP_FS)
        self.p_act = P(_ACT_VS, _ACT_FS)
        self.p_trc = P(_TRC_VS, _TRC_FS)
        self.p_bb = P(_BB_VS, _BB_FS)
        self.p_mark = P(_MARK_VS, _MARK_FS)
        self.p_nf = P(_FS_TRI_VS, _NF_FS, cam=False)
        self.p_vm = P(_VM_VS, _VM_FS, cam=False)
        self.p_sky["u_zen"].value = SKY_ZEN
        self.p_sky["u_hor"].value = SKY_HOR
        self.p_sky["u_gnd"].value = SKY_GND
        self.p_act["u_rim"].value = ENEMY_RIM
        self.p_act["u_muz"].value = [(0.0, 1.3, 0.5)] + [_cmesh.agent_muzzle_local(w) for w in range(1, 7)]
        self.p_blit["u_tex"].value = 0
        self.p_map["u_grid"].value = 1
        self.p_map["u_nf"].value = 2
        self.p_map["u_dens"].value = 3
        self.p_map["u_reg"].value = 4
        self.p_map["u_ledge"].value = tuple(c * 0.84 for c in (0.80, 0.77, 0.70))
        self.p_nf["u_grid"].value = 1
        self.ubo = self._keep(ctx.buffer(reserve=36 * 4))
        B = lambda data: self._keep(ctx.buffer(array("f", data).tobytes()))
        self.b_tri = B((-1.0, -1.0, 3.0, -1.0, -1.0, 3.0))                 # สามเหลี่ยมคลุมจอ
        self.b_quad = B((-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0))      # มุม billboard/รอยกระสุน (strip)
        self.b_trq = B((0.0, -1.0, 1.0, -1.0, 0.0, 1.0, 1.0, 1.0))         # มุมเส้นกระสุน (strip)
        bm = _cmesh.agent_mesh() if bot_model == "agent" else bot_mesh(gun=False)
        sm, vmm = spike_mesh(), _cmesh.viewmodel_mesh()
        self.b_bot = self._keep(ctx.buffer(bm.tobytes()))
        self.b_spk = self._keep(ctx.buffer(sm.tobytes()))
        self.b_vm = self._keep(ctx.buffer(vmm.tobytes()))
        self._bot_nv, self._spk_nv, self._vm_nv = len(bm) // 8, len(sm) // 8, len(vmm) // 8
        self.v_vm = self._keep(ctx.vertex_array(self.p_vm, [(self.b_vm, "3f 3f 1f 1f", *_A_BOT)]))
        self.v_sky = self._keep(ctx.vertex_array(self.p_sky, [(self.b_tri, "2f", "in_pos")]))
        self.v_blit = self._keep(ctx.vertex_array(self.p_blit, [(self.b_tri, "2f", "in_pos")]))
        self.v_nf = self._keep(ctx.vertex_array(self.p_nf, [(self.b_tri, "2f", "in_pos")]))
        del mgl

    # ── ของ GL ──
    def _keep(self, o):
        self._objs.append(o)
        return o

    def _prog(self, vs, fs, cam=True):
        p = self._keep(self.ctx.program(vertex_shader=vs, fragment_shader=fs))
        if cam:
            p["Cam"].binding = 0
        return p

    def _inst_vao(self, name, need, stride, build):
        """VAO แบบ instanced ที่ buffer instance โตเองเมื่อไม่พอ (ปล่อยของเก่าทิ้ง) → (vao, buf)"""
        cur = self._inst.get(name)
        if cur is not None and cur[2] >= need:
            return cur[0], cur[1]
        cap = max(16, need, (cur[2] * 2) if cur else 0)
        if cur is not None:
            for o in (cur[0], cur[1]):
                self._drop(o)
        buf = self._keep(self.ctx.buffer(reserve=cap * stride, dynamic=True))
        vao = self._keep(build(buf))
        self._inst[name] = (vao, buf, cap)
        return vao, buf

    def _drop(self, o):
        try:
            self._objs.remove(o)
        except ValueError:
            pass
        try:
            o.release()
        except Exception:
            pass

    def release(self):
        """ปล่อยของ GL ทุกชิ้น (display._teardown_gl เรียกก่อนทิ้ง context) — เรียกซ้ำได้"""
        for o in reversed(self._objs):
            try:
                o.release()
            except Exception:
                pass
        self._objs = []
        self._inst = {}
        self._map = ()
        self._fb = None
        self._fb_key = None
        self.cmap = None

    # ── ด่าน ──
    def set_map(self, cmap, mesh=None):
        """สร้าง VBO static ของด่าน (+ texture กริด) ใหม่ ปล่อยของด่านเก่า ; cmap None = ไม่มีด่าน (วาดแค่ฟ้า/ของลอย)"""
        for o in self._map:
            self._drop(o)
        self._map = ()
        self.cmap = None
        self._fall, self._trc_snap, self._fl_snap = {}, {}, {}
        if cmap is None:
            return
        mgl = _moderngl()
        ctx = self.ctx
        d = prepare(cmap, mesh)
        vbo = self._keep(ctx.buffer(d["vbo"].tobytes()))
        vao = self._keep(ctx.vertex_array(self.p_map, [(vbo, _cmesh.FORMAT) + _cmesh.ATTRS]))
        tex = self._keep(ctx.texture((cmap.nx, cmap.nz), 4, d["grid"]))
        tex.filter = (mgl.NEAREST, mgl.NEAREST)
        tex.repeat_x = tex.repeat_y = False
        dim = (float(cmap.nx), float(cmap.nz), float(d["wall_y"]))
        # สนาม normal เกลี่ย (_NF_FS) — วาดครั้งเดียวลง texture ครึ่ง float แล้วทิ้ง fbo
        nf = self._keep(ctx.texture((cmap.nx, cmap.nz), 4, dtype="f2"))
        nf.filter = (mgl.LINEAR, mgl.LINEAR)
        nf.repeat_x = nf.repeat_y = False
        dens = self._keep(ctx.texture((cmap.nx, cmap.nz), 1))
        dens.filter = (mgl.LINEAR, mgl.LINEAR)
        dens.repeat_x = dens.repeat_y = False
        fbo = ctx.framebuffer([nf, dens])
        try:
            fbo.use()
            ctx.disable(mgl.DEPTH_TEST | mgl.CULL_FACE | mgl.BLEND)
            tex.use(1)
            self.p_nf["u_dim"].value = dim
            self.v_nf.render(mgl.TRIANGLES, vertices=3)
        finally:
            fbo.release()
            _restore_state(ctx)
        bw, bh, rpx = d["region"]
        reg = self._keep(ctx.texture((bw, bh), 4, rpx))
        reg.filter = (mgl.LINEAR, mgl.LINEAR)
        reg.repeat_x = reg.repeat_y = False
        self._map = (vao, vbo, tex, nf, dens, reg)
        self._map_nv = d["n_vert"]
        pm = self.p_map
        pm["u_rgeo"].value = (cmap.x0, cmap.z0, 1.0 / (cmap.cell * _cmesh.REGION_BLOCK), 0.0)
        pm["u_rdim"].value = (float(bw), float(bh))
        pm["u_geo"].value = (cmap.x0, cmap.z0, 1.0 / cmap.cell, cmap.cell)
        pm["u_dim"].value = dim
        self.cmap = cmap
        self.stats["map_tri"] = d["n_tri"]

    # ── framebuffer นอกจอ ──
    def _ensure_fb(self, size):
        key = (size, self.msaa)
        if key == self._fb_key:
            return
        ctx = self.ctx
        if self._fb is not None:
            for o in self._fb:
                self._drop(o)
        self._fb = None
        self._fb_key = None
        mgl = _moderngl()
        tex = self._keep(ctx.texture(size, 4))
        tex.filter = (mgl.LINEAR, mgl.LINEAR)
        tex.repeat_x = tex.repeat_y = False
        objs = [tex]
        if self.msaa:
            try:
                rb = self._keep(ctx.renderbuffer(size, 4, samples=self.msaa))
                db = self._keep(ctx.depth_renderbuffer(size, samples=self.msaa))
                objs += [rb, db]
                draw = self._keep(ctx.framebuffer([rb], db))
                objs.append(draw)
                res = self._keep(ctx.framebuffer([tex]))
                objs.append(res)
                self._fb = tuple(objs)
                self._draw_fb, self._res_fb, self._tex = draw, res, tex
                self._fb_key = key
                return
            except Exception as ex:
                for o in objs[1:]:
                    self._drop(o)
                objs = [tex]
                self.msaa = 0
                self.stats["msaa_fail"] = str(ex)
                key = (size, 0)
        db = self._keep(ctx.depth_renderbuffer(size))
        draw = self._keep(ctx.framebuffer([tex], db))
        self._fb = (tex, db, draw)
        self._draw_fb, self._res_fb, self._tex = draw, None, tex
        self._fb_key = key

    # ── วาด ──
    def render(self, view, target=None):
        """วาดทั้งโลกลง target (ปกติ = ctx.screen) — view ตาม CLUTCH_DESIGN §11.2 ; คืนสถานะ GL สะอาดเสมอ (finally)
        ขนาด fbo = viewport ของ target × world_scale (การฉายเป็น NDC ของ W×H overlay → สเกลไหนก็ภาพเดียวกัน)"""
        t0 = time.perf_counter()
        mgl = _moderngl()
        ctx = self.ctx
        dst = target if target is not None else ctx.screen
        vp = dst.viewport
        tw, th = max(2, int(vp[2])), max(2, int(vp[3]))
        size = (max(2, int(round(tw * self.world_scale))), max(2, int(round(th * self.world_scale))))
        try:
            self._ensure_fb(size)
            W, H, f = float(view["W"]), float(view["H"]), float(view["f"])
            pos = view["pos"]
            t = float(view.get("t", 0.0))
            vm = view_matrix(view["yaw"], view["pitch"], pos)
            self.ubo.write(array("f", vm + (2.0 * f / W, 2.0 * f / H, 2.0 * ZNEAR, f,
                                           pos[0], pos[1], pos[2], t,
                                           vm[0], vm[4], vm[8], float(size[0]),
                                           vm[1], vm[5], vm[9], float(size[1])) +
                                  SKY_HOR + (FOG_DENSITY,)).tobytes())
            self.ubo.bind_to_uniform_block(0)
            fb = self._draw_fb
            fb.use()
            fb.depth_mask = True
            ctx.disable(mgl.DEPTH_TEST | mgl.CULL_FACE | mgl.BLEND)
            ctx.clear(SKY_HOR[0], SKY_HOR[1], SKY_HOR[2], 1.0, depth=1.0)
            self.v_sky.render(mgl.TRIANGLES, vertices=3)
            ctx.enable(mgl.DEPTH_TEST | mgl.CULL_FACE)
            ctx.front_face = "ccw"
            ctx.cull_face = "back"
            if self._map and self.cmap is not None:
                z = view.get("zone_hint")
                zi = {"A": 1, "B": 2, "C": 3}.get(z, 0) if z else 0
                if zi != self._zone:
                    self._zone = zi
                    self.p_map["u_zone"].value = zi
                self._map[2].use(1)
                self._map[3].use(2)
                self._map[4].use(3)
                self._map[5].use(4)
                self._map[0].render(mgl.TRIANGLES, vertices=self._map_nv)
            # ── spike + บอท (ทึบ ; ศพจางวาดท้ายสุดในชุดเดียวกันพร้อม blend) ──
            sp = view.get("spike")
            if sp and sp.get("state") in ("planted", "defused"):
                vao, buf = self._inst_vao("spk", 1, 4 * BOT_ROW, lambda b: self.ctx.vertex_array(
                    self.p_act, [(self.b_spk, "3f 3f 1f 1f", *_A_BOT), (b, "4f 4f 4f 4f 4f 4f 4f 4f/i", *_A_INST)]))
                blink = max(0.0, min(1.0, float(sp.get("blink", 0.0))))
                buf.write(array("f", (sp["x"], sp["y"], sp["z"], 0.0, 0.0, 0.0, 0.0, 1.0,
                                      0.0, blink, 0.0, 3.0 if sp["state"] == "defused" else 2.0) +
                                (0.0,) * (BOT_ROW - 12)).tobytes())
                vao.render(mgl.TRIANGLES, vertices=self._spk_nv, instances=1)
            bots = view.get("bots") or ()
            cm = self.cmap
            vmv = view.get("vm") or {}
            wdef = weapon_id(vmv.get("weapon"))                # บอทถืออาวุธตามผู้เล่น (gun_bot_weapon) ถ้า MODE ไม่ส่ง "weapon" ต่อบอท
            # ปืนหดถึงผิวของทึบ (gun_reach — รังสี 2 เส้น/บอท ~15 µs) ; ทิศล้มของศพเลือกครั้งเดียวต่อการตาย (cache ตามลำดับ + dead_t)
            reach = [gun_reach(cm, b["x"], b.get("y", 0.0) or 0.0, b["z"], b.get("yaw", 0.0) or 0.0,
                               b.get("crouch", 0.0) or 0.0, max(-AIM_PITCH_MAX, min(AIM_PITCH_MAX, b.get("pitch", 0.0) or 0.0)),
                               weapon_id(b.get("weapon"), wdef)) if b.get("alive", True) else GUN_NONE for b in bots]
            fyaw, fc = {}, {}
            for i, b in enumerate(bots):
                if b.get("alive", True) or b.get("dead_t") is None:
                    continue
                key = (i, b["dead_t"], cm)
                fy = self._fall.get(key)
                if fy is None:
                    fy = corpse_yaw(cm, b["x"], b.get("y", 0.0) or 0.0, b["z"], b.get("yaw", 0.0) or 0.0)
                fc[key] = fyaw[i] = fy
            self._fall = fc
            gait = gait_step(self._gait, bots, t)
            self.p_act["u_body_only"].value = 1 if self.body_only else 0
            live, dead = bot_rows(bots, t, reach, fyaw, gait, wdef)
            nb = len(live) + len(dead)
            if nb:
                vao, buf = self._inst_vao("bot", nb, 4 * BOT_ROW, lambda b: self.ctx.vertex_array(
                    self.p_act, [(self.b_bot, "3f 3f 1f 1f", *_A_BOT), (b, "4f 4f 4f 4f 4f 4f 4f 4f/i", *_A_INST)]))
                buf.write(_flat(live + dead, nb).tobytes())
                if dead:
                    ctx.enable(mgl.BLEND)
                    ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
                vao.render(mgl.TRIANGLES, vertices=self._bot_nv, instances=nb)   # ลำดับ instance คงที่: ตัวเป็นก่อนศพ
            # ── รอยกระสุน (decal: ไม่เขียน depth + polygon offset กัน z-fighting) ──
            ctx.disable(mgl.CULL_FACE)
            ctx.enable(mgl.BLEND)
            ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
            fb.depth_mask = False
            marks = view.get("marks") or ()
            if marks:
                self._draw_marks(marks[-MAX_MARKS:], t)
            # ── ของเรืองแสง (บวกแสง): เส้นกระสุน, ไฟปากกระบอก, แสงไฟ spike ──
            ctx.blend_func = mgl.ONE, mgl.ONE
            trs = [(tuple(a), tuple(c), age) for a, c, age in (view.get("tracers") or ())[-MAX_TRACERS:]
                   if age < TRACER_LIFE]
            rows, self._trc_snap = tracer_rows(trs, bots, vm, reach, self._trc_snap, wdef)
            if rows:
                vao, buf = self._inst_vao("trc", len(rows), 40, lambda b: self.ctx.vertex_array(
                    self.p_trc, [(self.b_trq, "2f", "in_c"), (b, "4f 4f 2f/i", "i_a", "i_b", "i_s")]))
                buf.write(_flat(rows, len(rows)).tobytes())
                vao.render(mgl.TRIANGLE_STRIP, vertices=4, instances=len(rows))
            glow = []
            fsnap = {}
            for fx in (view.get("flashes") or ())[-MAX_FLASHES:]:
                if fx[3] < FLASH_LIFE:
                    k = 1.0 - fx[3] / FLASH_LIFE
                    key = (fx[0], fx[1], fx[2])
                    m = self._fl_snap.get(key) or eye_to_muzzle(key, bots, reach, wdef)
                    fsnap[key] = m
                    glow.append((m[0], m[1], m[2], 0.20 + 0.10 * k, 1.0, 0.78, 0.40, 1.6 * k))
            self._fl_snap = fsnap
            if sp and sp.get("state") == "planted" and sp.get("blink", 0.0) > 0.02:
                bl = min(1.0, float(sp["blink"]))
                glow.append((sp["x"], sp["y"] + SPIKE_LIGHT_Y - 0.02, sp["z"], 0.22, 1.0, 0.12, 0.08, 1.2 * bl))
            if glow:
                vao, buf = self._inst_vao("bb", len(glow), 32, lambda b: self.ctx.vertex_array(
                    self.p_bb, [(self.b_quad, "2f", "in_c"), (b, "4f 4f/i", "i_p", "i_c")]))
                buf.write(_flat(glow, len(glow)).tobytes())
                vao.render(mgl.TRIANGLE_STRIP, vertices=4, instances=len(glow))
            fb.depth_mask = True
            # ── มือ/ปืนบุคคลที่หนึ่ง (depth 0..0.01 ของตัวเอง — ทับฉากเสมอ ไม่จมกำแพง) ──
            ctx.disable(mgl.BLEND)
            vmx = _cmesh.vm_matrix(vmv, t) if vmv else None
            if vmx is not None:
                ctx.enable(mgl.CULL_FACE)
                var, mat, wv = vmx
                fvm = float(view.get("f_vm") or _base_focal(H) * _cmesh.VM_FOCAL_K)
                self.p_vm["u_m"].write(array("f", mat).tobytes())
                self.p_vm["u_vp"].value = (2.0 * fvm / W, 2.0 * fvm / H, float(var),
                                           float(wv) if var != _cmesh.V_SPIKE else -1.0)
                self.p_vm["u_blink"].value = float(max(0.0, min(1.0, (sp or {}).get("blink", 0.0) or 0.0)))
                self.v_vm.render(mgl.TRIANGLES, vertices=self._vm_nv)
                self.stats["vm"] = var
            ctx.disable(mgl.DEPTH_TEST | mgl.BLEND | mgl.CULL_FACE)
            ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
            # ── resolve MSAA → texture → วาดเต็ม target (สเกลได้, ไม่พลิกแกน v เพราะเป็น texture ของ GL เอง) ──
            if self._res_fb is not None:
                ctx.copy_framebuffer(self._res_fb, fb)
            dst.use()
            self._tex.use(0)
            self.p_blit["u_dst"].value = (float(tw), float(th))
            self.v_blit.render(mgl.TRIANGLES, vertices=3)
            self.stats["bots"] = nb
        finally:
            self._clean(dst)
        self.stats["cpu_ms"] = (time.perf_counter() - t0) * 1000.0

    def _draw_marks(self, marks, t):
        """รอยกระสุน: instance = (จุด, เวลาเกิด = t − age) (normal, รัศมี) — ข้อมูลคงที่ตราบที่ชุดรอยเดิม
        → เทียบตำแหน่งกับเฟรมก่อน ถ้าเหมือนเดิมไม่ต้องแพ็ก/อัปใหม่ (อายุเดินเองใน shader ด้วย u_eye.w)"""
        mgl = _moderngl()
        key = [m[0] for m in marks]
        vao, buf = self._inst_vao("mark", len(marks), 32, lambda b: self.ctx.vertex_array(
            self.p_mark, [(self.b_quad, "2f", "in_c"), (b, "4f 4f/i", "i_p", "i_n")]))
        if self._mk_key is None or self._mk_key[0] != key or self._mk_key[1] is not buf or \
                abs(self._mk_key[2] - (t - marks[-1][2])) > 0.05:
            a = array("f")
            for p, n, age in marks:
                a.extend((p[0], p[1], p[2], t - age, n[0], n[1], n[2], MARK_R))
            buf.write(a.tobytes())
            self._mk_key = (key, buf, t - marks[-1][2])
        ctx = self.ctx
        ctx.polygon_offset = (-1.0, -4.0)
        vao.render(mgl.TRIANGLE_STRIP, vertices=4, instances=len(marks))
        ctx.polygon_offset = (0.0, 0.0)

    def _clean(self, dst=None):
        _restore_state(self.ctx, dst)


def _restore_state(ctx, dst=None):
    """สถานะที่ overlay composite (display._gl_present) คาด: ไม่มี depth/cull/blend ค้าง, offset 0, เส้น 1 px,
    blend_func ค่าคงที่ของ display, ctx.screen ถูก bind (standalone ไม่มี screen → bind dst)"""
    try:
        mgl = _moderngl()
        ctx.disable(mgl.DEPTH_TEST | mgl.CULL_FACE | mgl.BLEND)
        ctx.polygon_offset = (0.0, 0.0)
        ctx.blend_func = mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA
        ctx.line_width = 1.0
        fb = ctx.screen if ctx.screen is not None else dst
        if fb is not None:
            fb.use()
    except Exception:
        pass


def draw_clutch_world(game, view):
    """วาดโลก CLUTCH บน GPU ของ display — True = วาดแล้ว (ตั้ง game._world_gpu_frame ให้ด้วย)
    False = ไม่มี GPU / เคยล้ม → ผู้เรียกวาดภาพสำรอง software ; ไม่ raise เด็ดขาด
    ล้มครั้งแรก: log stderr ครั้งเดียว, ปล่อยของ, ตั้ง game._clutch_gl_failed (ปิดเฉพาะ clutch GL ทั้ง session —
    GPU world ของโหมดอื่น (_glr) ไม่ถูกแตะ)"""
    if getattr(game, "_clutch_gl_failed", False):
        return False
    ctx = getattr(game, "_gl", None)
    if ctx is None or not getattr(game, "gpu", False):
        return False
    try:
        cg = getattr(game, "_clutch_gl", None)
        if cg is not None and cg.ctx is not ctx:          # context ใหม่ (สร้างหน้าต่างใหม่) → ของเก่าใช้ไม่ได้แล้ว
            try:
                cg.release()
            except Exception:
                pass
            cg = None
        if cg is None:
            cg = ClutchGL(ctx)
            game._clutch_gl = cg
        cm = view.get("map")
        if cm is not cg.cmap:
            cg.set_map(cm)
        cg.render(view)
        game._world_gpu_frame = True
        return True
    except Exception as ex:
        game._clutch_gl_failed = True
        msg = f"CLUTCH GPU world ล้ม ({type(ex).__name__}: {ex}) — ใช้ภาพสำรองแทน (โหมดอื่นไม่กระทบ)"
        warn = getattr(game, "_warn_once", None)
        try:
            if callable(warn):
                warn("clutchgl", msg)
            else:
                print(f"[VAL//AIM] {msg}", file=sys.stderr)
        except Exception:
            pass
        cg = getattr(game, "_clutch_gl", None)
        game._clutch_gl = None
        if cg is not None:
            try:
                cg.release()
            except Exception:
                pass
        _restore_state(ctx)
        return False


# ─────────────────────────────── selftest (pure — ไม่ต้องมี moderngl) ───────────────────────────────
def _bot_verts(mesh):
    for q in range(0, len(mesh), 8):
        yield mesh[q:q + 3], mesh[q + 3:q + 6], mesh[q + 6], int(mesh[q + 7])


def _seg_dist(p, a, b):
    """ระยะจุด p ถึงส่วนของเส้นแนวตั้ง a→b (x, z เท่ากัน)"""
    y = min(max(p[1], min(a[1], b[1])), max(a[1], b[1]))
    return math.sqrt((p[0] - a[0]) ** 2 + (p[1] - y) ** 2 + (p[2] - a[2]) ** 2)


def _close(a, b, eps=1e-9):
    return len(a) == len(b) and all(abs(u - v) <= eps for u, v in zip(a, b))


def _hit_sd(p, drop):
    """ระยะมีเครื่องหมายจากจุด p (พิกัดหุ่น) ถึงผิว hitbox รวม (บวก = อยู่นอก) — เรขาคณิต guns.humanoid_zone"""
    d_head = math.dist(p, (0.0, HEAD_Y - drop, 0.0)) - HEAD_R
    r = math.hypot(p[0], p[2])
    b0, b1 = BODY_Y0 - drop, BODY_Y1 - drop
    dy = max(b0 - p[1], p[1] - b1)
    d_body = math.hypot(max(r - BODY_HW, 0.0), dy) if dy > 0 else max(r - BODY_HW, dy)
    yy = min(max(p[1], LEG_Y0), LEG_Y1 - drop)
    return min(d_head, d_body, math.dist(p, (0.0, yy, 0.0)) - LEG_HW)


def _tri_dist0(pts):
    """ระยะจากจุดกำเนิด (กลางจอ) ถึงสามเหลี่ยม 2 มิติ (0 = ทับ)"""
    (ax, ay), (bx, by), (cx, cy) = pts
    d1 = (0 - bx) * (ay - by) - (ax - bx) * (0 - by)
    d2 = (0 - cx) * (by - cy) - (bx - cx) * (0 - cy)
    d3 = (0 - ax) * (cy - ay) - (cx - ax) * (0 - ay)
    if not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0)):
        return 0.0
    best = 1e18
    for (px_, py_), (qx, qy) in (((ax, ay), (bx, by)), ((bx, by), (cx, cy)), ((cx, cy), (ax, ay))):
        ex, ey = qx - px_, qy - py_
        L2 = ex * ex + ey * ey
        t = max(0.0, min(1.0, (-px_ * ex - py_ * ey) / L2)) if L2 > 0 else 0.0
        best = min(best, math.hypot(px_ + ex * t, py_ + ey * t))
    return best


def vm_clear_px(vmd, Wd, Hd, vmm=None):
    """ระยะ (px) จากกลางจอถึงสามเหลี่ยมที่ใกล้สุดของมือ/ปืนบุคคลที่หนึ่งท่า vmd บนจอ Wd×Hd (inf = ไม่วาด)"""
    M = _cmesh
    got = M.vm_matrix(vmd, 10.0)
    if got is None:
        return float("inf")
    vmm = vmm if vmm is not None else M.viewmodel_mesh()
    var, m, wv = got
    f = _base_focal(Hd) * M.VM_FOCAL_K
    best = float("inf")
    for q in range(0, len(vmm), 24):
        kb = int(vmm[q + 6] + 0.5) // 32
        if kb != var and kb != (wv if var != M.V_SPIKE else -1):
            continue
        pts = []
        for v in range(3):
            o = q + 8 * v
            x, y, z = vmm[o], vmm[o + 1], vmm[o + 2]
            c = (m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13],
                 m[2] * x + m[6] * y + m[10] * z + m[14])
            pts.append((f * c[0] / c[2], -f * c[1] / c[2]) if c[2] > 0.02 else None)
        if None in pts:
            continue
        best = min(best, _tri_dist0(pts))
    return best


VM_TEST_POSES = [{}, {"fire_t": 9.98}, {"reload_k": 0.5}, {"equip_k": 0.3}, {"ads": True}, {"speed": 5.4}, {"crouch": 1.0},
                 {"air": True}, {"kick": (6.0, -3.0)}, {"ads": True, "fire_t": 9.99, "kick": (4.0, 2.0), "crouch": 1.0},
                 {"planting": True}]


def _selftest_agent(rng):
    """หุ่นเอเจนต์: ผิวตัว (ไม่นับชุดแขน/ปืน) อยู่นอก hitbox ไม่เกิน AGENT_OUT_TOL (เท้า 6 ซม.) ทุกท่า ; ท่อขาต่อข้อต่อตรง ;
    มือ/ปืนบุคคลที่หนึ่งไม่เข้าวง VM_CLEAR รอบเป้าเล็งทุกท่า/ทุกอาวุธ/ทุกสัดส่วนจอ ; จังหวะก้าวจากความเร็ว/ตำแหน่ง ; สีย่าน"""
    errors = []
    M = _cmesh
    mesh = M.agent_mesh()
    worst = {}
    for c in (0.0, 0.5, 1.0):
        for amp, run in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)):
            for ph in (0.0, 1.3, 2.4, 3.9, 5.2):
                md = rng.choice(((0.0, 1.0), (1.0, 0.0), (0.7071, -0.7071)))
                pose = {"crouch": c, "legs": M.leg_pose(c, ph, amp, run, md)}
                drop = CROUCH_DROP * c
                for q in range(0, len(mesh), 16):             # ทุกจุดที่สอง (~10k จุด/ท่า)
                    kb = int(mesh[q + 6] + 0.5)
                    if kb // 32:
                        continue
                    d = _hit_sd(M.agent_pose_xform(mesh[q:q + 3], kb, pose), drop)
                    k = "foot" if kb % 32 in (M.B_FOOT_L, M.B_FOOT_R) else "body"
                    worst[k] = max(worst.get(k, -1.0), d)
    if worst.get("body", 1.0) > M.AGENT_OUT_TOL or worst.get("foot", 1.0) > 0.06:
        errors.append(f"clutchgl: หุ่นเอเจนต์ยื่นพ้น hitbox (ตัว {worst.get('body', 0) * 100:.1f} ซม., เท้า "
                      f"{worst.get('foot', 0) * 100:.1f} ซม.)")
    hy, hz, L, R = M.leg_pose(0.0)
    top = M.seg_xform((0.0, 0.0, 0.0), (-M.HIP_X, hy, hz), L[0])
    bot = M.seg_xform((0.0, -1.0, 0.0), L[0], L[1])
    if math.dist(top, (-M.HIP_X, hy, hz)) > 1e-9 or math.dist(bot, L[1]) > 1e-9 or abs(L[0][1] - (M.ANKLE_Y + M.SHIN_L)) > 0.01:
        errors.append(f"clutchgl: ท่อขาไม่ต่อข้อต่อ ({top}, {bot}, เข่า {L[0]})")
    # viewmodel ไม่บังเป้าเล็ง: ทุกสามเหลี่ยมที่แสดงอยู่นอกวง VM_CLEAR·H (ระยะจากกลางจอถึงสามเหลี่ยมบนจอ)
    vmm = M.viewmodel_mesh()
    bad, near = [], float("inf")
    for wname in ("vandal", "phantom", "operator", "sheriff", "ghost", "classic", "spike"):
        for ps in VM_TEST_POSES:
            vmd = {"weapon": "vandal" if wname == "spike" else wname, "equip": "spike" if wname == "spike" else "gun"}
            vmd.update(ps)
            for (Wd, Hd) in ((1920, 1080), (3440, 1440)):
                d = vm_clear_px(vmd, Wd, Hd, vmm) / Hd
                near = min(near, d)
                if d < M.VM_CLEAR:
                    bad.append((wname, tuple(ps), round(d, 3)))
    if bad:
        errors.append(f"clutchgl: มือ/ปืนบุคคลที่หนึ่งเข้าใกล้เป้าเล็ง {len(bad)} กรณี (เช่น {bad[:3]})")
    if M.vm_matrix({"weapon": "operator", "ads": True}, 1.0) is not None or M.vm_matrix(None, 1.0) is not None:
        errors.append("clutchgl: Op เปิดสโคป/ไม่มี vm ต้องไม่วาดมือ")
    # จังหวะก้าว: ไม่มี vx/vz → ความเร็วจากตำแหน่ง ; มี "walk" = ไม่วิ่ง
    st = {}
    g1 = None
    for k in range(0, 30):
        g1 = gait_step(st, [{"x": 0.0, "z": 5.4 * k / 60.0, "yaw": 0.0}], 1.0 + k / 60.0)
    g2 = gait_step({}, [{"x": 0.0, "z": 0.0, "yaw": math.pi / 2, "vx": 2.5, "vz": 0.0, "walk": True}], 3.0)
    if not (g1[0][1] > 0.9 and g1[0][2] > 0.9 and abs(g1[0][3][1] - 1.0) < 1e-6) or g2[0][2] != 0.0 or \
            abs(g2[0][3][1] - 1.0) > 1e-6:
        errors.append(f"clutchgl: gait_step ผิด ({g1}, {g2})")
    from .clutchmap import testyard
    bw, bh, px = M.region_rgba(testyard())
    if len(px) != 4 * bw * bh or len(set(px[q:q + 3] for q in range(0, len(px), 4))) < 3:
        errors.append("clutchgl: region_rgba ไม่แบ่งย่าน")
    _selftest_agent.stats = (worst, near)
    return errors


def selftest():
    errors = []
    T0 = time.perf_counter()
    # ── view_matrix = camera.to_cam (สูตรเดียวกับ glrender) ──
    import random
    from .camera import Camera
    rng = random.Random(0x5C1)
    cam = Camera()
    worst = 0.0
    for _ in range(2000):
        cam.yaw, cam.pitch = rng.uniform(-math.pi, math.pi), rng.uniform(-1.55, 1.55)
        cam.pos = [rng.uniform(-80, 80), rng.uniform(-3, 12), rng.uniform(-80, 80)]
        m = view_matrix(cam.yaw, cam.pitch, cam.pos)
        p = (rng.uniform(-90, 90), rng.uniform(-4, 14), rng.uniform(-90, 90))
        gl = tuple(m[i] * p[0] + m[4 + i] * p[1] + m[8 + i] * p[2] + m[12 + i] for i in range(3))
        worst = max(worst, max(abs(a - b) for a, b in zip(gl, cam.to_cam(p))))
    if worst >= 1e-9:
        errors.append(f"clutchgl: view_matrix != camera.to_cam (ต่างสุด {worst:.3g})")
    # ── เมชหุ่น: ทุกจุดยอดของหัว/ลำตัว/ขาอยู่บนผิว hitbox (guns.humanoid_zone) พอดีทุกท่าหมอบ + ด้านนอกถูก + ปิดสนิท ──
    mesh = bot_mesh()
    nv = len(mesh) // 8
    off = 0
    edges = {}
    bad_w = 0
    for crouch in (0.0, 0.5, 1.0):
        drop = CROUCH_DROP * crouch
        hc = (0.0, HEAD_Y - drop, 0.0)
        b0, b1 = BODY_Y0 - drop, BODY_Y1 - drop
        l0, l1 = (0.0, LEG_Y0, 0.0), (0.0, LEG_Y1 - drop, 0.0)
        for (p, n, k, mat) in _bot_verts(mesh):
            if mat == M_GUN:
                continue
            q = (p[0], p[1] - k * drop, p[2])
            if mat == M_HEAD:
                e = abs(math.dist(q, hc) - HEAD_R)
            elif mat == M_SUIT:
                rad = math.hypot(q[0], q[2])
                e = abs(rad - BODY_HW) if abs(n[1]) < 0.5 else (abs(q[1] - (b1 if n[1] > 0 else b0)) +
                                                                 max(0.0, rad - BODY_HW))
                if abs(n[1]) < 0.5 and not (b0 - 1e-6 <= q[1] <= b1 + 1e-6):
                    e = 1.0
            else:
                e = abs(_seg_dist(q, l0, l1) - LEG_HW)
            off = max(off, e)
    tris = nv // 3
    for tri in range(tris):
        vs = [mesh[(tri * 3 + i) * 8:(tri * 3 + i) * 8 + 8] for i in range(3)]
        if int(vs[0][7]) == M_GUN:
            continue
        pa, pb, pc = vs[0][:3], vs[1][:3], vs[2][:3]
        u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        v = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        nn = [sum(x[3 + i] for x in vs) for i in range(3)]
        if cr[0] * nn[0] + cr[1] * nn[1] + cr[2] * nn[2] >= 0.0:
            bad_w += 1
        key = [tuple(round(c, 5) for c in x[:3]) + (x[6],) for x in vs]
        for i in range(3):
            e = tuple(sorted((key[i], key[(i + 1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    # ขอบที่ใช้ไม่ครบ 2 ครั้ง = รูรั่ว ยกเว้นรอยต่อวงล่าง/บนของขา-ลำตัวที่ k ต่างกัน (เทียบรวม k แล้ว = ต้องครบ 2)
    open_e = sum(1 for c in edges.values() if c != 2)
    if off > 1e-5 or bad_w or open_e:
        errors.append(f"clutchgl: เมชหุ่นไม่ตรง hitbox (ห่างผิวสุด {off:.2g} ม., winding ผิด {bad_w}, ขอบเปิด {open_e})")
    # เมชแนบในผิว (inscribed) — ขอบรูปหลายเหลี่ยมเล็กกว่ารัศมีจริงสุด r·(1 − cos(π/n)) ; หัว 0.14 ม. = 0.67 มม.
    sag = BODY_HW * (1 - math.cos(math.pi / BOT_SEG))
    if sag > 0.0012:
        errors.append(f"clutchgl: แบ่งรอบวงหยาบเกิน (sagitta {sag * 1000:.2f} มม.)")
    # ── ท่าทาง/ทิศ: ปืนชี้ตาม yaw, หมอบลดหัว 0.55, ศพนอนราบเหนือพื้นไม่จมทะลุพื้น ──
    yaw = 0.7
    tip = bot_xform((0.14, 1.25, GUN_BARREL[5]), 3.0, 1.2, -2.0, yaw)
    dx, dz = tip[0] - 3.0, tip[2] + 2.0
    along = dx * math.sin(yaw) + dz * math.cos(yaw)        # ตามทิศ forward (sin yaw, cos yaw)
    side = dx * math.cos(yaw) - dz * math.sin(yaw)         # ตามแกนขวา (cos yaw, −sin yaw)
    if abs(along - GUN_BARREL[5]) > 1e-9 or abs(side - 0.14) > 1e-9 or abs(tip[1] - 2.45) > 1e-9:
        errors.append(f"clutchgl: ปืนไม่ชี้ตาม yaw ({tip})")
    hy = bot_xform((0.0, HEAD_Y, 0.0), 0, 0.4, 0, 0.0, drop=CROUCH_DROP)[1]
    if abs(hy - (0.4 + HEAD_Y - CROUCH_DROP)) > 1e-9:
        errors.append("clutchgl: หมอบแล้วหัวไม่ลด CROUCH_DROP")
    lying = [bot_xform(p, 0, 0.0, 0, 0.0, fall=1.0, k=k) for p, n, k, mat in _bot_verts(mesh) if mat != M_GUN]
    ymin = min(p[1] for p in lying)
    head_back = bot_xform((0.0, HEAD_Y, 0.0), 0, 0.0, 0, 0.0, fall=1.0)
    if ymin < -LEG_HW - 1e-6 or max(p[1] for p in lying) > 0.6 or head_back[2] > -1.4:
        errors.append(f"clutchgl: ท่าล้มผิด (ต่ำสุด {ymin:.2f}, หัวที่ {head_back})")
    ml = _cmesh.agent_muzzle_local(1)
    mz = muzzle(1.0, 0.5, 2.0, math.pi / 2, crouch=1.0)          # หันไป +x, หมอบ → ปลายปืนอยู่ +x ตามแขน, ต่ำลง 0.55
    if abs(mz[0] - (1.0 + ml[2])) > 1e-9 or abs(mz[1] - (0.5 + ml[1] - CROUCH_DROP)) > 1e-9 or abs(mz[2] - (2.0 - ml[0])) > 1e-9:
        errors.append(f"clutchgl: muzzle ผิด {mz}")
    up = muzzle(0.0, 0.0, 0.0, 0.0, pitch=0.5)                   # เงยปืน = ปลายลำกล้องสูงขึ้นตามมุมรอบไหล่
    if not up[1] > ml[1] + 0.2 or abs(math.dist(up, _cmesh.SH_PIV) - math.dist(ml, _cmesh.SH_PIV)) > 1e-9:
        errors.append(f"clutchgl: muzzle ไม่เงยตาม pitch {up}")
    # ── view จาก MODE: dead_t = เวลาเกมตอนตาย (ล้ม/จางตามอายุ t − dead_t) ; ต้นกระสุนที่ตาบอท → ปลายลำกล้องที่วาด ──
    bl = [{"x": 1.0, "y": 0.5, "z": 2.0, "yaw": 0.3, "crouch": 1.0, "alive": True, "dead_t": None, "flash": 2.0},
          {"x": 5.0, "y": 0.0, "z": 5.0, "yaw": 0.0, "crouch": 0.0, "alive": False, "dead_t": 40.0, "flash": 0.0},
          {"x": 6.0, "y": 0.0, "z": 5.0, "yaw": 0.0, "crouch": 0.0, "alive": False, "dead_t": 30.0, "flash": 0.0},
          {"x": 7.0, "y": 0.0, "z": 5.0, "yaw": 0.0, "crouch": 0.0, "alive": False, "dead_t": None, "flash": 0.0}]
    lv, dd = bot_rows(bl, 40.1)
    if len(lv) != 1 or lv[0][5] != 1.0 or len(dd) != 1 or dd[0][0] != 5.0 or \
            abs(dd[0][6] - (0.1 / DEAD_FALL) ** 2) > 1e-9 or dd[0][7] != 1.0:
        errors.append(f"clutchgl: bot_rows ผิด (live {lv}, dead {dd})")
    if bot_rows(bl, 40.0 + DEAD_FADE[0] + 0.5)[1][0][7] != 0.5:
        errors.append("clutchgl: ศพไม่จางตาม DEAD_FADE")
    eye = (1.0, 0.5 + EYE_Y - CROUCH_DROP, 2.0)
    if not _close(eye_to_muzzle(eye, bl), muzzle(1.0, 0.5, 2.0, 0.3, 1.0)) or \
            eye_to_muzzle((1.0, 3.0, 2.0), bl) == muzzle(1.0, 0.5, 2.0, 0.3, 1.0) or \
            eye_to_muzzle((5.0, EYE_Y, 5.0, 0.01), bl) != (5.0, EYE_Y, 5.0, 0.01):
        errors.append("clutchgl: eye_to_muzzle ผิด")
    sm = spike_mesh()
    if len(sm) % 24 or min(sm[1::8]) < 0.0 or abs(max(sm[1::8]) - SPIKE_LIGHT_Y) > 1e-6:
        errors.append("clutchgl: เมช spike ผิด")
    # ── prepare: กริด RGBA ตรง kind/h/zone ของด่าน ──
    from .clutchmap import testyard
    cm = testyard()
    d = prepare(cm)
    g = d["grid"]
    # surface_normal กับรังสีจริงของด่าน: ยิงเข้ากำแพงบาง x 0…0.25 จากฝั่ง −x → (−1, 0, 0) ; ยิงลงพื้น → (0, 1, 0)
    o = (-3.0, 1.2, -2.0)
    for dvec, want in (((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)), ((0.0, -1.0, 0.0), (0.0, 1.0, 0.0)),
                       ((0.0, 0.0, 1.0), (0.0, 0.0, -1.0))):
        t = cm.ray(o, dvec, 60.0)
        hp = (o[0] + dvec[0] * t, o[1] + dvec[1] * t, o[2] + dvec[2] * t) if t is not None else None
        if hp is None or surface_normal(cm, hp, dvec) != want:
            errors.append(f"clutchgl: surface_normal {dvec} → {hp and surface_normal(cm, hp, dvec)} (ต้อง {want})")
    # รังสีกดลงพื้นเรียบใกล้เส้นแบ่งช่อง ต้องได้ +y (เคยได้ ±x/±z 3.5% → รอยกระสุนตั้งจมพื้นครึ่งดวง) ; ผนังยังได้แนวนอน
    bad_f = bad_w = 0
    for k in range(400):
        gx = -15.0 + 0.25 * rng.randrange(120) + rng.choice((-1e-3, 1e-3, 0.0))   # จุดชนบน/ชิดเส้นแบ่งช่อง
        gz = -15.0 + 0.25 * rng.randrange(120) + rng.uniform(-0.12, 0.12)
        if k & 1:
            gx, gz = gz, gx
        fl = cm.floor_y(gx, gz)
        if fl is None or any(cm.floor_y(gx + a, gz + b) != fl for a in (-0.3, 0.3) for b in (-0.3, 0.3)):
            continue
        yw, pt = rng.uniform(-math.pi, math.pi), -rng.uniform(0.1, 0.7)
        dv = (math.sin(yw) * math.cos(pt), math.sin(pt), math.cos(yw) * math.cos(pt))
        o = (gx - dv[0] * 3.0, fl - dv[1] * 3.0, gz - dv[2] * 3.0)
        t = cm.ray(o, dv, 6.0)
        if t is None or abs(t - 3.0) > 1e-6:
            continue
        bad_f += surface_normal(cm, (gx, fl, gz), dv) != (0.0, 1.0, 0.0)
    dv = (-0.7037441829966082, -0.536134008209342, -0.4661592540536135)      # พื้นห่างตีนผนังบาง 1 มม. (ข้ามช่องเข้าผนัง)
    bad_f += surface_normal(cm, (0.251, 0.0, -2.1065589800131446), dv) != (0.0, 1.0, 0.0)
    for zz in (-5.9, -3.0, -1.2, 1.9):                        # ผนังบาง x 0…0.25 ยิงเฉียงจากฝั่ง −x ทุกมุม
        for ang in (-60.0, -20.0, 20.0, 60.0):
            dv = (math.cos(math.radians(ang)), -0.05, math.sin(math.radians(ang)))
            n = math.sqrt(sum(v * v for v in dv))
            dv = tuple(v / n for v in dv)
            o = (-0.8, 1.2, zz - dv[2] / dv[0] * 0.8)
            t = cm.ray(o, dv, 3.0)
            if t is not None and abs(o[0] + dv[0] * t) < 1e-6:
                bad_w += surface_normal(cm, tuple(o[i] + dv[i] * t for i in range(3)), dv) != (-1.0, 0.0, 0.0)
    if bad_f or bad_w:
        errors.append(f"clutchgl: surface_normal พื้นเรียบได้แนวนอน {bad_f} ครั้ง / ผนังผิด {bad_w} ครั้ง")
    # ── ปืนชิดกำแพงบาง: บอทชิดผนัง x 0…0.25 (ศูนย์ x 0.6 = ใกล้สุดที่ BOT_R ยอม) หันเข้าผนัง → ปืนหดไม่เลยผิว x 0.25 ──
    rc = gun_reach(cm, 0.6, 0.0, -2.0, -math.pi / 2)
    tipw = muzzle(0.6, 0.0, -2.0, -math.pi / 2, cmap=cm)
    tip_full = muzzle(0.6, 0.0, -2.0, -math.pi / 2)
    if not (rc < GUN_NONE and tipw[0] >= 0.25 + GUN_GAP - 1e-6 and tip_full[0] < 0.0) or \
            gun_reach(cm, -12.0, 0.0, -9.0, 0.0) != GUN_NONE or gun_reach(None, 0.6, 0.0, -2.0, 0.0) != GUN_NONE:
        errors.append(f"clutchgl: gun_reach ผิด (reach {rc:.3f}, ปลายปืน x {tipw[0]:.3f})")
    lv, _ = bot_rows([{"x": 0.6, "y": 0.0, "z": -2.0, "yaw": -math.pi / 2, "alive": True}], 1.0, [rc])
    if lv[0][9] != rc:
        errors.append("clutchgl: bot_rows ไม่ส่งความยาวปืนเข้า i_ex.y")
    # ── ศพ: หลังชิดผนังบาง → ล้มไปทิศอื่นที่โล่ง (หัว/ลำตัวไม่จมผนัง) ; กลางโล่ง → หงายหลังตรงตามเดิม ──
    fy = corpse_yaw(cm, 0.6, 0.0, -2.0, math.pi / 2)             # หัน +x หลังชนผนัง
    hd = bot_xform((0.0, HEAD_Y + HEAD_R, 0.0), 0.6, 0.0, -2.0, fy, fall=1.0)
    if abs(fy - math.pi / 2) < 1e-9 or cm.blocked((0.6, CORPSE_RAY_Y, -2.0), (hd[0], CORPSE_RAY_Y, hd[2])) or \
            corpse_yaw(cm, -12.0, 0.0, -9.0, 0.4) != 0.4 or corpse_yaw(None, 0.0, 0.0, 0.0, 0.4) != 0.4:
        errors.append(f"clutchgl: corpse_yaw ล้มเข้าผนัง (yaw {fy:.2f}, หัวที่ {hd})")
    _, dd = bot_rows([{"x": 0.6, "y": 0.0, "z": -2.0, "yaw": 0.3, "alive": False, "dead_t": 1.0}], 1.5, None, {0: fy})
    if dd[0][3] != fy or dd[0][9] != GUN_NONE:
        errors.append("clutchgl: bot_rows ไม่ใช้ทิศล้มของศพ")
    # ── เส้นกระสุน: ต้นที่ตาตอนยิง (หมอบ 0.28) ยังย้ายไปปลายปืนแม้บอทหมอบต่อเป็น 0.83 ก่อนเส้นหาย ; เส้นนิ่งตาม cache ;
    #    เส้นพลาดเฉียดหัวถูกตัดที่ z กล้อง TRC_ZMIN ; เส้นหลังกล้องทั้งเส้นไม่วาด ──
    b0 = {"x": 3.0, "y": 0.0, "z": 15.0, "yaw": math.pi, "crouch": 0.28, "alive": True}
    shot_eye = (3.0, EYE_Y - CROUCH_DROP * 0.28, 15.0)
    b1 = dict(b0, crouch=0.83)
    if not _close(eye_to_muzzle(shot_eye, [b1]), muzzle(3.0, 0.0, 15.0, math.pi, 0.28)):
        errors.append("clutchgl: eye_to_muzzle ไม่ย้ายต้นกระสุนเมื่อบอทหมอบระหว่างอายุเส้น")
    vm0 = view_matrix(0.0, 0.0, (0.0, EYE_Y, 0.0))
    near = (shot_eye, (-0.97, 1.55, -10.0), 0.03)
    back = ((1.0, 1.6, -3.0), (2.0, 1.6, -20.0), 0.03)
    rows, cache = tracer_rows([near, back], [b0], vm0)
    m0 = muzzle(3.0, 0.0, 15.0, math.pi, 0.28)
    if len(rows) != 1 or rows[0][8] != 0.0 or abs(rows[0][9] - (m0[2] - TRC_ZMIN) / (m0[2] + 10.0)) > 1e-9 or \
            not _close(rows[0][:3], m0):
        errors.append(f"clutchgl: tracer_rows ตัด/ย้ายเส้นผิด {rows}")
    rows2, _ = tracer_rows([near], [dict(b1, yaw=math.pi - 0.8)], vm0, None, cache)
    if not rows2 or rows2[0][:3] != rows[0][:3]:
        errors.append("clutchgl: tracer_rows ต้นเส้นขยับตามบอท (ไม่ใช้ cache)")
    errors += _selftest_agent(rng)
    if len(g) != 4 * cm.nx * cm.nz or g[0::4] != bytes(cm.kind) or g[1::4] != bytes(cm.h) or \
            g[2::4] != bytes(cm.zone) or len(d["vbo"]) != 11 * d["n_vert"] or prepare(cm) is not d:
        errors.append("clutchgl: prepare() กริด/vbo ผิด")
    print(f"CLUTCHGL SELFTEST {'OK' if not errors else 'FAIL'} (bot mesh {nv // 3} tri, spike {len(sm) // 24} tri, "
          f"max off-surface {off:.1e} m, sagitta {sag * 1000:.2f} mm | total {time.perf_counter() - T0:.2f} s)")
    return errors
