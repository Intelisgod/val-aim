# -*- coding: utf-8 -*-
"""กล้อง 3D + sens model (VAL_DEG_PER_COUNT=0.07) + ล็อก vertical FOV (VFOV_RAD)"""

import math

from .config import VAL_DEG_PER_COUNT, HFOV_DEG, EYE_Y

# Valorant ล็อก FOV “แนวตั้ง” (~70.53°) — คงสูตรเดิมเป๊ะ
VFOV_RAD = 2 * math.atan(math.tan(math.radians(HFOV_DEG / 2)) * 9 / 16)
# tan ของครึ่ง FOV เป็นค่าคงที่ — คำนวณครั้งเดียวตอน import (focal_len ถูกเรียก 2-3 ครั้ง/เฟรม)
_TAN_HALF_VFOV = math.tan(VFOV_RAD / 2)

class Camera:
    def __init__(self):
        self.yaw, self.pitch = 0.0, 0.0
        self.pos = [0.0, EYE_Y, 0.0]
        # cache cos/sin ของ (yaw,pitch) — คีย์ด้วย "ค่า" มุม จึง invalidate ตัวเองเสมอ
        # ไม่ว่าใครแก้ yaw/pitch ทางไหน (apply_mouse/recoil/selftest เขียนตรง) ผลลัพธ์ bit-identical
        # เพราะ math.cos/sin ของ input เดิมให้ค่าเดิมเสมอ แค่ไม่คำนวณซ้ำ ~50-90 ครั้ง/เฟรม
        self._trig_key = None
        self._trig = (1.0, 0.0, 1.0, 0.0)
        self._k_sens = None
        self._k = 0.0

    def _cs(self):
        """คืน (cos_yaw, sin_yaw, cos_pitch, sin_pitch) จาก cache"""
        key = (self.yaw, self.pitch)
        if key != self._trig_key:
            self._trig_key = key
            self._trig = (math.cos(self.yaw), math.sin(self.yaw),
                          math.cos(self.pitch), math.sin(self.pitch))
        return self._trig

    def apply_mouse(self, dx, dy, sens):
        # k ขึ้นกับ sens อย่างเดียว — cache ไว้ (MOUSEMOTION มาถึง ~1000 ครั้ง/วิ บนเมาส์ 1000Hz)
        if sens != self._k_sens:
            self._k_sens = sens
            self._k = math.radians(VAL_DEG_PER_COUNT * sens)
        k = self._k
        self.yaw += dx * k
        self.pitch -= dy * k
        lim = math.radians(89.0)
        self.pitch = max(-lim, min(lim, self.pitch))

    def forward(self):
        cy, sy, cp, sp = self._cs()
        return (sy * cp, sp, cy * cp)

    def to_world_dir(self, d):
        """ทิศใน camera space (x ขวา, y ขึ้น, z หน้า) → ทิศใน world (ผกผันการหมุนของ to_cam)"""
        x1, y2, z2 = d
        cy, sy, cp, sp = self._cs()
        y = y2 * cp + z2 * sp
        z1 = -y2 * sp + z2 * cp
        x = x1 * cy + z1 * sy
        z = -x1 * sy + z1 * cy
        return (x, y, z)

    def to_cam(self, p):
        x, y, z = p[0] - self.pos[0], p[1] - self.pos[1], p[2] - self.pos[2]
        cy, sy, cp, sp = self._cs()
        x1 = x * cy - z * sy
        z1 = x * sy + z * cy
        y2 = y * cp - z1 * sp
        z2 = y * sp + z1 * cp
        return x1, y2, z2

def focal_len(H):
    """ระยะโฟกัสจากความสูงจอ — ล็อก vertical FOV เหมือน Valorant"""
    return (H / 2) / _TAN_HALF_VFOV
