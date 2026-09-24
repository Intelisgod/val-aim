# -*- coding: utf-8 -*-
"""ที่กำบังของ GUNFIGHT (pure python — ไม่มี pygame): กล่องแกนตรง (AABB) + ทดสอบรังสี/แนวสายตา

ใช้ร่วมทุกทางที่ "ของทึบ" ต้องมีผล:
  • กระสุนผู้เล่น (gunplay.gun_bullet) และกระสุนบอท (gunbots.gun_bot_fire) — ชนกล่องก่อน = ไม่โดนตัว
  • ใครเห็นใคร (gunbots: จุดบนตัวบอท/ผู้เล่นที่แนวสายตาไม่ผ่านกล่อง) — เริ่มนาฬิกา reaction ของบอท
  • วาด (glrender = GPU, gunplay.draw_gun_world = software + บังบอทที่อยู่หลังกล่อง)
พิกัดโลกเดียวกับกล้อง: x ขวา, y ขึ้น (พื้น = 0), z ไปข้างหน้า"""
import math

INF = float("inf")

# หน้ากล่องที่วาดได้ (ก้นกล่องติดพื้น ไม่ต้องวาด): ชื่อ → (แกน, ทิศ) ; ทิศ −1 = หน้าฝั่งค่าต่ำของแกน
FACES = (("front", 2, -1), ("back", 2, 1), ("left", 0, -1), ("right", 0, 1), ("top", 1, 1))
# สีต่อหน้า (แสงจากด้านบน-หน้า: หน้าสว่างกว่าข้าง ให้เห็นขอบมุมชัด) + เส้นขอบ — GPU (glrender) และ software ใช้ชุดเดียวกัน
FACE_COL = {"front": (46, 64, 86), "back": (46, 64, 86), "left": (36, 51, 70), "right": (36, 51, 70),
            "top": (60, 80, 104)}
EDGE_COL = (92, 118, 148)


class Box:
    """กล่องทึบแกนตรง [x0,x1]×[y0,y1]×[z0,z1] — draw=False = มีผลกับกระสุน/สายตาแต่ไม่วาดผ่านชุดนี้
    (เช่นกำแพง OP HOLD ที่ glrender วาดเป็น static segment อยู่แล้ว)
    ledge=True = ยกพื้นที่บอทยืนอยู่ "บน" (ดริล ANGLE) — บังกระสุน/สายตาตามปกติ แต่ไม่ใช่ของที่อยู่ "หน้า" บอทที่ยืนบนมัน:
    ตัววาดไม่วาดมันทับบอทตัวนั้น (occludes แบบเผื่อของกล่องใต้เท้าตอบ True เสมอ → หน้าบนของยกพื้นจะทับขาบอท) ;
    บอทตัวอื่นที่อยู่หลังยกพื้นยังโดนบังตามปกติ (gunplay.draw_cover_occlusion)"""
    __slots__ = ("lo", "hi", "draw", "ledge")

    def __init__(self, x0, x1, y0, y1, z0, z1, draw=True, ledge=False):
        self.lo = (min(x0, x1), min(y0, y1), min(z0, z1))
        self.hi = (max(x0, x1), max(y0, y1), max(z0, z1))
        self.draw = draw
        self.ledge = ledge

    def __repr__(self):
        return f"Box({self.lo} → {self.hi}{'' if self.draw else ', hidden'}{', ledge' if self.ledge else ''})"

    def ray(self, o, d):
        """t ≥ 0 ที่รังสี o + t·d เข้ากล่อง (slab method) — None ถ้าไม่โดน ; o อยู่ในกล่อง = 0
        d ไม่ต้องเป็นหน่วย (t เป็นสัดส่วนของ d) — segment_blocked ใช้ d = q − p แล้วดู t < 1"""
        t0, t1 = 0.0, INF
        lo, hi = self.lo, self.hi
        for a in range(3):
            da = d[a]
            if -1e-12 < da < 1e-12:
                if o[a] < lo[a] or o[a] > hi[a]:
                    return None
                continue
            ta = (lo[a] - o[a]) / da
            tb = (hi[a] - o[a]) / da
            if ta > tb:
                ta, tb = tb, ta
            if ta > t0:
                t0 = ta
            if tb < t1:
                t1 = tb
            if t0 > t1:
                return None
        return t0

    def face_pts(self, name):
        """มุม 4 จุดของหน้า (เรียงรอบขอบ — วาด polygon ได้ตรง)"""
        (x0, y0, z0), (x1, y1, z1) = self.lo, self.hi
        if name == "front":
            return [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
        if name == "back":
            return [(x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1)]
        if name == "left":
            return [(x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1)]
        if name == "right":
            return [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)]
        return [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]   # top

    def visible_faces(self, eye):
        """ชื่อหน้าที่หันเข้าหาตา (ตาอยู่นอกระนาบหน้านั้น) — กล่องนูน: วาดแค่หน้าพวกนี้ ไม่ต้องใช้ depth buffer"""
        out = []
        for name, a, s in FACES:
            if (s < 0 and eye[a] < self.lo[a]) or (s > 0 and eye[a] > self.hi[a]):
                out.append(name)
        return out

    def occludes(self, eye, p):
        """กล่องนี้อาจอยู่ "หน้า" จุด p เมื่อมองจาก eye ไหม — มีระนาบหน้ากล่องที่แยก eye (ด้านนอก) กับ p (ด้านใน)
        (กล่องนูนกับจุด: ไม่มีระนาบแยก = p อยู่หน้ากล่องหรือข้างๆ → กล่องต้องวาดก่อน p) ; ตอบ True แบบเผื่อ
        (กล่องที่ไม่ทับ p บนจอก็ได้ True ได้) — ผู้เรียกวาดทับเฉพาะในกรอบของ p จึงไม่ผิดภาพ"""
        lo, hi = self.lo, self.hi
        for a in range(3):
            if eye[a] < lo[a] < p[a]:
                return True
            if eye[a] > hi[a] > p[a]:
                return True
        return False

    def dist2(self, p):
        """ระยะกำลังสองจาก p ถึงจุดที่ใกล้สุดของกล่อง (เรียงลำดับวาดไกล → ใกล้)"""
        s = 0.0
        for a in range(3):
            v = p[a]
            if v < self.lo[a]:
                s += (self.lo[a] - v) ** 2
            elif v > self.hi[a]:
                s += (v - self.hi[a]) ** 2
        return s


def first_hit(o, d, boxes):
    """(t, box) ของกล่องแรกที่รังสี o + t·d ชน — (None, None) ถ้าไม่ชนเลย"""
    best, hit = None, None
    for b in boxes:
        t = b.ray(o, d)
        if t is not None and (best is None or t < best):
            best, hit = t, b
    return best, hit


def segment_blocked(p, q, boxes):
    """เส้นตรง p → q ผ่านกล่องใดไหม (ปลาย q แตะผิวกล่องพอดีไม่นับ — รอยกระสุนบนผิวกล่องยังมองเห็นได้)"""
    d = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
    for b in boxes:
        t = b.ray(p, d)
        if t is not None and t < 1.0 - 1e-6:
            return True
    return False


def any_visible(eye, pts, boxes):
    """มีจุดไหนใน pts ที่แนวสายตาจาก eye ไม่ถูกกล่องบังไหม (ไม่มีกล่อง = เห็นทุกจุด)"""
    if not boxes:
        return bool(pts)
    for q in pts:
        if not segment_blocked(eye, q, boxes):
            return True
    return False


def dir_from_angles(yaw, pitch):
    """ทิศหน่วยในโลกจากมุม yaw/pitch แบบเดียวกับกล้อง (camera.forward)"""
    cp = math.cos(pitch)
    return (math.sin(yaw) * cp, math.sin(pitch), math.cos(yaw) * cp)


def angles_to(o, p):
    """(yaw, pitch) เรเดียนจาก o มอง p — ผกผันของ dir_from_angles"""
    dx, dy, dz = p[0] - o[0], p[1] - o[1], p[2] - o[2]
    return math.atan2(dx, dz), math.atan2(dy, math.hypot(dx, dz))
