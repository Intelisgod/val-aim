# -*- coding: utf-8 -*-
"""ไอคอนแรงค์ของจริง (PNG จาก valorant-api.com — โหลดครั้งเดียวไว้ใน assets/rank_icons)
ใช้โดย draw_rank_emblem: มีไฟล์ = ใช้ไอคอนจริง, ไม่มี/โหลดพลาด = คืน None ให้วาดโล่เดิม
ชื่อไฟล์เป็นแบบ HenrikDev ("gold 2.png") — แปลงจากชื่อเทรนเนอร์ที่เป็นเลขโรมัน ("Gold II")
"""

import os
import pygame

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "assets", "rank_icons")
_ROMAN = {"i": "1", "ii": "2", "iii": "3"}
_cache = {}   # (key, h) -> Surface | None


def _key(name):
    """'Gold III' -> 'gold 3' ; 'Immortal' -> 'immortal 3' (เดิมวาด 3 ขีด) ; 'Radiant' -> 'radiant'"""
    parts = str(name).strip().lower().split()
    if not parts:
        return ""
    if parts[-1] in _ROMAN:
        parts[-1] = _ROMAN[parts[-1]]
    elif parts[-1] not in ("1", "2", "3", "radiant", "unranked"):
        parts.append("3")   # tier เดี่ยวไม่มีระดับ (Immortal) — ใช้ไอคอนขั้นสูงสุดของ tier นั้น
    return " ".join(parts)


def icon(rank_name, size):
    """คืน Surface ไอคอนสูง ~size px (คงสัดส่วน) หรือ None ถ้าไม่มี/โหลดไม่ได้ — cache ต่อขนาด"""
    k = (_key(rank_name), int(size))
    if k in _cache:
        return _cache[k]
    surf = None
    try:
        p = os.path.join(_DIR, k[0] + ".png")
        if k[0] and os.path.exists(p):
            img = pygame.image.load(p)
            try:
                img = img.convert_alpha()
            except pygame.error:
                pass   # ยังไม่มี display (selftest/headless) — ใช้ surface ดิบได้
            w = max(1, round(img.get_width() * k[1] / max(img.get_height(), 1)))
            surf = pygame.transform.smoothscale(img, (w, k[1]))
    except Exception:
        surf = None   # fail-open เสมอ — เกมต้องเล่นได้แม้ asset พัง
    _cache[k] = surf
    return surf
