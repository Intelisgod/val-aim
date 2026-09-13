# -*- coding: utf-8 -*-
"""เป้า (Target) + head/body hitbox + sample_dir (สุ่มทิศกระสุน)"""

import math
import random

class Target:
    def __init__(self, pos, radius):
        self.pos = list(pos)
        self.radius = radius
        self.vx = 0.0
        self.base_y = pos[1]
        self.born = 0.0          # game-time วินาที (-1 = ยังไม่เริ่มนับ สำหรับ sniper)
        self.alpha = 0.0
        self.end_x = 0.0
        self.visible = True

    def dist(self, cam):
        return math.dist(self.pos, cam.pos)

    def is_hit(self, cam, spread=0.0, shot_dir=None):
        return self._hit_at(cam, self.pos, self.radius, spread, shot_dir)

    # ── head sub-hitbox (realism) ──
    # หัวเป็นวงเล็กเหนือลำตัว: center = body + (0, 1.15R, 0), radius = 0.5R
    def head_radius(self):
        return self.radius * 0.5

    def head_pos(self):
        return [self.pos[0], self.pos[1] + self.radius * 1.15, self.pos[2]]

    @staticmethod
    def sample_dir(spread):
        """สุ่มทิศกระสุน 1 นัดจากกรวยสเปรด (None = ยิงตรงกลางเป๊ะ)"""
        if spread <= 0:
            return None
        phi = random.uniform(0, spread)
        th = random.uniform(0, 2 * math.pi)
        return (math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi))

    def _hit_at(self, cam, center, radius, spread=0.0, shot_dir=None):
        """angular hit test รอบทรงกลมใดๆ; ส่ง shot_dir เดียวกันได้ทั้งหัว+ตัว (1 นัด = 1 ทิศ)"""
        if shot_dir is None and spread > 0:
            shot_dir = self.sample_dir(spread)
        x, y, z = cam.to_cam(center)
        d = math.sqrt(x * x + y * y + z * z)
        if d == 0:
            return True
        if shot_dir is None:
            cosang = z / d
        else:
            cosang = (x * shot_dir[0] + y * shot_dir[1] + z * shot_dir[2]) / d
        ang = math.acos(max(-1.0, min(1.0, cosang)))
        if d <= radius:
            return True
        return ang <= math.asin(min(1.0, radius / d))

    def is_head_hit(self, cam, spread=0.0, shot_dir=None):
        return self._hit_at(cam, self.head_pos(), self.head_radius(), spread, shot_dir)
