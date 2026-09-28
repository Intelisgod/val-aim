# -*- coding: utf-8 -*-
"""selftest ของโหมด CLUTCH ส่วนที่ 3 — realism pass v2 การเคลื่อนที่ (CLUTCH_DESIGN §13.1/§13.2 ; เรียกจาก clutchtest.selftest
ด้วย Game headless ตัวเดียวกัน + สมองบอทปลอม) : ความสูง/เวลาลอยของการกระโดด (60/144 FPS), หมอบกระโดดขึ้นกล่อง 1.1/1.5 ได้
กระโดดเฉยขึ้น 1.1 ไม่ได้ ลังซ้อน 3.0 ไม่มีทาง, กระโดดไม่ได้ตอนวาง/กู้/ลอย, วาง/กู้กลางอากาศไม่ได้, ดาเมจตก 6/12/15 ม. (ไม่ผ่านเกราะ
ตาย = แพ้ died), กล้องแตะพื้นไม่เด้ง, โทษความแม่นลอย/แตะพื้น (นัดที่ยิง + crosshair) เฉพาะ clutch, ไม่ทะลุกำแพง, บอท/nav ไม่เปลี่ยน,
PlayerView/game attrs/clutch_view (vm) ของทีมอื่น, ข้อเท็จจริงโค้ช "กระโดดยิง" — คืน list ข้อความ error"""
import math
import time
import traceback

import pygame

from .config import EYE_Y
from . import clutchmap, clutchscen, guns, stability
from .clutchmap import BOX, FLOOR, WALL, ClutchMap
from .clutchtest import _put, _run, _start

_DT = 1 / 60.0
# แมพสังเคราะห์: เลนกว้าง 2 ม. คั่นด้วย VOID — กล่องลึก 2 ม. เริ่มที่ x = 4.25 ม. ('b' 1.1 · 'c' 1.5 · 'D' 3.0)
_LEG = {"c": (BOX, 1.5, 0), "D": (BOX, 3.0, 0), "H": (FLOOR, 6.05, 0), "K": (FLOOR, 9.05, 0), "L": (FLOOR, -3.0, 0)}
_LANE = "#" + "." * 16 + "{}" * 8 + "." * 30 + "#"


def _box_map():
    rows = []
    for ch in ("b", "c", "D"):
        rows += ["#" * 56] + [_LANE.format(*([ch] * 8))] * 8
    rows.append("#" * 56)
    return ClutchMap.from_ascii(rows, legend=_LEG, slug="movetest")


def _lane_z(cm, k):
    """z กลางเลนที่ k (0 = b, 1 = c, 2 = D) — แถว 0 ของ rows = เหนือสุด"""
    return cm.z0 + (cm.nz - 5 - 9 * k) * cm.cell


def _ledge_map():
    """ขอบผา 6.05 ม. (บน) / 12.05 ม. (ล่าง: 9.05 → −3.0) + กำแพงบาง '|' ที่ปลายเลนล่าง"""
    top = "#" + "H" * 12 + "." * 40 + "#"
    bot = "#" + "K" * 12 + "L" * 36 + "|" + "L" * 3 + "#"
    return ClutchMap.from_ascii(["#" * 54] + [top] * 8 + ["#" * 54] + [bot] * 8 + ["#" * 54], legend=_LEG,
                                slug="movetest2")


def _use_map(g, cm):
    """สลับแมพของรอบที่เริ่มแล้วเป็นแมพสังเคราะห์ (บอทปลอมอยู่พิกัด Yard — ไม่ยิงเอง) ; เวลารอบเหลือเฟือ"""
    g.cmap = cm
    g.cl_round_left = 999.0
    if g.cl_spike and g.cl_spike.get("left") is not None:
        g.cl_spike["left"] = 999.0


def _press(g, key, down=True):
    g.clutch_key(key, down)


def _jump_run(g, cm, lane, jump_x, tuck, secs=1.4):
    """วิ่ง +x ในเลน แล้วกระโดดเมื่อ x ≥ jump_x (tuck = หมอบหลังกระโดด 0.05 วิ) → ระดับเท้าตอนแตะพื้นครั้งแรก"""
    _put(g, 1.5, _lane_z(cm, lane), math.pi / 2)
    g.gun_crouch = False
    g.keys_down = {"w"}
    st = {"jumped": None, "land": None}

    def each():
        if st["jumped"] is None and g.cam.pos[0] >= jump_x:
            _press(g, pygame.K_SPACE, True)
            _press(g, pygame.K_SPACE, False)
            st["jumped"] = g.gt
        if tuck and st["jumped"] is not None and g.gt - st["jumped"] >= 0.05:
            g.gun_crouch = True
        if st["jumped"] is not None and st["land"] is None and g.gt - st["jumped"] > 0.05 and not g.cl_air:
            st["land"] = (g.cl_feet, g.cam.pos[0])
    _run(g, secs, _DT, each)
    g.keys_down, g.gun_crouch = set(), False
    return st["land"]


def _move_checks(g):
    errors = []
    E = errors.append
    t0 = time.perf_counter()
    shot_raw = stability.Stability.__dict__["shot_dir"]         # staticmethod ตัวจริง (คืนค่าแบบเดิมใน finally)
    shot0 = stability.Stability.shot_dir
    try:
        # ── ค่าคงที่ ──
        if abs(clutchscen.JUMP_V - math.sqrt(2 * 18.9 * 1.0)) > 1e-9 or clutchscen.GRAVITY != 18.9:
            E("clutch jump: GRAVITY/JUMP_V ไม่ตาม §13.1")
        fd = [clutchscen.fall_damage(h) for h in (5.99, 6.0, 9.0, 12.0, 15.0, 30.0)]
        if fd[0] != 0.0 or abs(fd[1] - 15) > 1e-9 or abs(fd[3] - 90) > 1e-9 or abs(fd[4] - 100) > 1e-9 or fd[5] != 100 \
                or not 15 < fd[2] < 90:
            E(f"clutch fall_damage: 5.99/6/9/12/15/30 ม. = {fd} (ต้อง 0/15/…/90/100/100)")
        lk = [guns.curve_ue(guns.LAND_KEYS, t) for t in (0.0, 0.1, 0.2, 0.3)]
        if abs(lk[0] - 0.5) > 1e-9 or not 0.0 < lk[1] < 0.5 or lk[2] != 0.0 or lk[3] != 0.0:
            E(f"clutch landing curve: {lk}")
        # ── กระโดดบนพื้นเรียบ: ความสูง 1.0 ม. ลอย ≈ 0.65 วิ (60/144 FPS) + กล้องแตะพื้นไม่เด้ง ──
        cm = _box_map()
        _start(g, side="atk", n=2)
        _use_map(g, cm)
        for fps in (60.0, 144.0):
            _put(g, 1.5, _lane_z(cm, 0), 0.0)
            f0 = g.cl_feet
            _press(g, pygame.K_SPACE, True)
            top, t_air, eyes, landed_t = f0, 0.0, [], None
            dt = 1.0 / fps
            for i in range(int(1.2 * fps)):
                g.update_play(dt)
                if g.cl_air:
                    t_air += dt
                    top = max(top, g.cl_feet)
                elif t_air > 0 and landed_t is None:
                    landed_t = i
                if landed_t is not None:
                    eyes.append(g.cl_eye)
            _press(g, pygame.K_SPACE, False)
            if abs(top - f0 - 1.0) > 0.01 or abs(t_air - 0.6506) > 1.5 * dt:
                E(f"clutch jump {fps:.0f}fps: สูง {top - f0:.3f} ม. ลอย {t_air:.3f} วิ (ต้อง 1.0 / 0.651)")
            want = g.cl_feet + EYE_Y
            if not eyes or min(eyes) < want - 1e-6 or any(b > a + 1e-9 for a, b in zip(eyes, eyes[1:])) \
                    or abs(eyes[-1] - want) > 1e-3:
                E(f"clutch jump {fps:.0f}fps: กล้องแตะพื้นเด้ง/จม (ต่ำสุด {min(eyes or [0]) - want:+.4f})")
            if g.cl_jumps < 1 or not g.cl_land_loud or g.cl_land_t < 0:
                E("clutch jump: ไม่นับการกระโดด/เวลาแตะพื้น/เสียงลงพื้น")
        # Space ผ่าน input.py จริง (state play) ; ค้างไว้ไม่กระโดดซ้ำ ; กลางอากาศกดซ้ำไม่ได้ (ไม่มี double jump)
        _put(g, 1.5, _lane_z(cm, 0), 0.0)
        n0 = g.cl_jumps
        kd = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=44)
        ku = pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=44)
        g.handle_event(kd)
        _run(g, 0.2)
        g.handle_event(kd)                                        # key repeat ระหว่างค้าง
        _run(g, 0.05)
        g.handle_event(ku)
        g.handle_event(kd)                                        # กดใหม่กลางอากาศ
        _run(g, 1.0)
        g.handle_event(ku)
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.3)
        _press(g, pygame.K_SPACE, False)
        if g.cl_jumps - n0 != 2:
            E(f"clutch jump: Space จาก input = กระโดดครั้งเดียวต่อการกด ไม่มี double jump (ได้ {g.cl_jumps - n0} ต้อง 2)")
        _run(g, 1.0)
        # ── ปีนกล่อง: หมอบกระโดดขึ้น 1.1 ได้ / กระโดดเฉยไม่ได้ ; ลัง 1.5 หมอบกระโดดได้ ; ลังซ้อน 3.0 ไม่ได้เลย ──
        face = 4.25
        got = {}
        for lane, jx, tuck in ((0, face - 1.9, True), (0, face - 1.9, False), (1, face - 2.1, True),
                               (2, face - 2.1, True), (2, face - 1.9, False)):
            got[(lane, tuck)] = _jump_run(g, cm, lane, jx, tuck)
        tops = (1.1, 1.5, 3.0)
        on = {k: (v is not None and abs(v[0] - tops[k[0]]) < 0.02 and v[1] > face) for k, v in got.items()}
        if not on[(0, True)] or on[(0, False)] or not on[(1, True)] or on[(2, True)] or on[(2, False)]:
            E(f"clutch mount: หมอบกระโดด 1.1 {on[(0, True)]} (ต้อง True) · กระโดดเฉย 1.1 {on[(0, False)]} (False) · "
              f"หมอบกระโดด 1.5 {on[(1, True)]} (True) · 3.0 {on[(2, True)]}/{on[(2, False)]} (False) {got}")
        # ยืนบนกล่อง = on_box + PlayerView (ปลายเท้า/เสียงลงพื้น) ; ค้าง Shift ตอนลง = เงียบ
        _put(g, 5.0, _lane_z(cm, 0), 0.0)
        g.update_play(_DT)
        pv = g.clutch_pv()
        if abs(g.cl_feet - 1.1) > 1e-6 or not g.cl_on_box or not pv.on_box or abs(pv.feet - 1.1) > 1e-6:
            E(f"clutch box top: ยืนบนหลังกล่อง feet {g.cl_feet} on_box {g.cl_on_box}/{pv.on_box}")
        g.keys_down = {"shift"}
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.9)
        _press(g, pygame.K_SPACE, False)
        pv = g.clutch_pv()
        if pv.land_loud or g.cl_land_loud or pv.land_t != g.cl_land_t or pv.air:
            E("clutch landing: ค้าง Shift ตอนลง = เงียบ (land_loud False) + PlayerView ตรง game")
        g.keys_down = set()
        # กลางอากาศขาหด: PlayerView ปลายเท้าสูงขึ้น + ท่าหมอบ → ตาบอทเห็นหัวที่ระดับกล้องเดิม
        _put(g, 1.5, _lane_z(cm, 0), 0.0)
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.1)
        g.gun_crouch = True
        _run(g, 0.05)
        pv = g.clutch_pv()
        if not (pv.air and pv.crouch == 1.0 and abs(pv.eye()[1] - g.cam.pos[1]) < 0.03
                and abs(pv.feet - g.cl_feet - clutchscen.CROUCH_TUCK) < 1e-9):
            E(f"clutch tuck: PlayerView กลางอากาศขาหด eye {pv.eye()[1]:.3f} vs กล้อง {g.cam.pos[1]:.3f}")
        _run(g, 1.0)
        g.gun_crouch = False
        _press(g, pygame.K_SPACE, False)
        _run(g, 0.3)
        # ── โทษความแม่น: ลอย = โทษกระโดดของปืน (นัดที่ยิง + crosshair) · แตะพื้น 0.2 วิ · โหมดอื่นไม่โดน ──
        cones = []
        stability.Stability.shot_dir = staticmethod(lambda po, yo, sp: (cones.append(sp), shot0(po, yo, sp))[1])
        for wp, want in (("vandal", 10.0), ("operator", 20.0), ("sheriff", 7.0)):
            _start(g, side="atk", n=2, weapon=wp)
            _use_map(g, cm)
            _put(g, 1.5, _lane_z(cm, 0), 0.0, -0.3)
            base = g.gun_next_spread()
            _press(g, pygame.K_SPACE, True)
            _run(g, 0.2)
            air_cs = g.gun_next_spread()
            cones.clear()
            g.gun_next_shot_at = 0.0
            g.shoot()
            fired = list(cones)
            for _ in range(600):
                if not g.cl_air or g.state != "play":
                    break
                g.update_play(1 / 240.0)
            lerr = g.clutch_air_err()                             # เพิ่งแตะพื้น (≤ 1/240 วิ)
            land = g.gun_next_spread()
            g.gun_stab.extra = None
            land0 = g.gun_next_spread()
            g.gun_stab.extra = g.clutch_air_err
            _run(g, 0.25)
            after, aerr = g.gun_next_spread(), g.clutch_air_err()
            _press(g, pygame.K_SPACE, False)
            lp = 0.0 if wp == "operator" else want * 0.5
            if not fired or fired[0] < want - 1e-6 or air_cs < want - 1e-6 or g.cl_jump_shots != 1:
                E(f"clutch air error {wp}: นัดกลางอากาศ {fired[:1]} crosshair {air_cs:.2f} (ต้อง ≥ {want}) "
                  f"jump_shots {g.cl_jump_shots}")
            if abs(lerr - lp) > 0.03 * want or abs(land - land0 - lerr) > 1e-6 or aerr != 0.0 or after > base + 0.3:
                E(f"clutch landing error {wp}: แตะพื้น +{lerr:.2f} (ต้อง ≈ +{lp}) crosshair {land:.2f}/{land0:.2f} "
                  f"หลัง 0.25 วิ +{aerr:.2f} {after:.2f} (ต้องกลับ {base:.2f})")
        stability.Stability.shot_dir = shot_raw
        facts = " ".join(t for t, _c in g.clutch_facts())
        ent = g.clutch_fill_entry({})
        if "กระโดดยิง 1 นัด" not in facts or ent.get("jump_shots") != 1:
            E(f"clutch jump shots: ข้อเท็จจริงโค้ช/history ต้องมี กระโดดยิง 1 นัด ({ent.get('jump_shots')})")
        _start(g, side="atk", n=2, weapon="classic")
        _use_map(g, cm)
        _put(g, 1.5, _lane_z(cm, 0), 0.0)
        a0 = g.gun_alt_spread()
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.2)
        a1 = g.gun_alt_spread()
        _press(g, pygame.K_SPACE, False)
        if abs(a1 - a0 - guns.JUMP_ERR_ALT) > 1e-6:
            E(f"clutch Classic RMB ลอย: +{a1 - a0:.2f}° (ต้อง +{guns.JUMP_ERR_ALT})")
        _run(g, 1.0)
        g.state = "pause"
        g.end_game()
        g.go_menu()
        g.mode, g.gun_weapon, g.gun_drill = "gun", "vandal", "duel"
        g.start_countdown()
        g.begin_play()
        if g.gun_stab.extra is not None or g.gun_stab._extra() != 0.0:
            E("clutch air error: GUNFIGHT ต้องไม่มีโทษลอย (Stability.extra ต้องว่าง)")
        g.state = "pause"
        g.end_game()
        g.go_menu()
        # ── กระโดดไม่ได้ตอนวาง/กู้ ; วาง/กู้กลางอากาศไม่ได้ (Yard จริง) ──
        _start(g, side="atk", n=2)
        _put(g, -12.0, 9.5, 0.0)
        g.clutch_key(pygame.K_4, True)
        _run(g, 0.7)
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.05)
        _press(g, pygame.K_SPACE, False)
        g.lmb_down = True
        _run(g, 0.3)
        air_plant = g.cl_plant_t0 is not None and g.cl_jumps == 1
        _run(g, 1.0)
        started = g.cl_plant_t0 is not None
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.3)
        _press(g, pygame.K_SPACE, False)
        if air_plant or not started or g.cl_air or g.cl_jumps != 1 or g.cl_plant_t0 is None:
            E(f"clutch plant: วางกลางอากาศ {air_plant} / กระโดดระหว่างวาง jumps {g.cl_jumps} air {g.cl_air}")
        g.lmb_down = False
        g.state = "pause"
        g.end_game()
        _start(g, side="def", n=2)
        _put(g, -11.0, 9.5)
        g.clutch_key(pygame.K_f, True)
        _run(g, 0.3)
        d0 = g.cl_defuse_t0 is not None
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.3)
        _press(g, pygame.K_SPACE, False)
        if not d0 or g.cl_air or g.cl_jumps != 0 or g.cl_defuse_t0 is None:
            E(f"clutch defuse: กระโดดระหว่างกู้ต้องไม่ได้ (jumps {g.cl_jumps})")
        g.clutch_key(pygame.K_f, False)
        _run(g, 0.1)
        _press(g, pygame.K_SPACE, True)
        _run(g, 0.1)
        g.clutch_key(pygame.K_f, True)
        _run(g, 0.1)
        if g.cl_defuse_t0 is not None or not g.cl_air:
            E("clutch defuse: เริ่มกู้กลางอากาศต้องไม่ได้")
        g.clutch_key(pygame.K_f, False)
        _press(g, pygame.K_SPACE, False)
        g.state = "pause"
        g.end_game()
        # ── ตก: 6.05 ม. → HP −15 (เกราะเท่าเดิม) · 12.05 ม. → HP −90 · 15 ม. → ตาย = แพ้ died ──
        lm = _ledge_map()
        z_top, z_bot = lm.z0 + (lm.nz - 1 - 4) * lm.cell, lm.z0 + (lm.nz - 1 - 13) * lm.cell
        for zz, want in ((z_top, clutchscen.fall_damage(6.05)), (z_bot, clutchscen.fall_damage(12.05))):
            _start(g, side="atk", n=2)
            _use_map(g, lm)
            _put(g, 2.0, zz, math.pi / 2)
            g.keys_down = {"w"}
            _run(g, 0.5)
            g.keys_down = set()
            _run(g, 1.5)
            lost = guns.PLAYER_HP - g.gun_hp
            if abs(lost - want) > 0.01 or g.gun_shield != guns.PLAYER_SHIELD or g.cl_fall_dmg_t < 0 or g.cl_dead:
                E(f"clutch fall: เสีย HP {lost:.2f} (ต้อง {want:.2f}) เกราะ {g.gun_shield} (ต้องไม่ลด)")
            if not lm.walkable(g.cam.pos[0], g.cam.pos[2]) or g.cam.pos[0] > 12.25 - clutchmap.PLAYER_R + 1e-6:
                E(f"clutch fall: ทะลุกำแพงบาง/ออกนอกพื้น x {g.cam.pos[0]:.3f}")
            g.state = "pause"
            g.end_game()
        _start(g, side="atk", n=2)
        _use_map(g, lm)
        _put(g, 8.0, z_bot, 0.0)
        g.cl_feet += 15.0
        g.cl_eye += 15.0
        g.cl_air, g.cl_vy, g.cl_apex = True, 0.0, g.cl_feet
        _run(g, 4.0)
        e = g.last_entry if g.state == "results" else {}
        if (e.get("win"), e.get("why"), e.get("deaths")) != (0, "died", 1):
            E(f"clutch fall 15 ม.: ต้องตาย = แพ้ died ({e.get('win')}, {e.get('why')})")
        # ── ไม่ทะลุ: dt 0.1 วิ วิ่งเร็ว 6.75 ม./วิ กลางอากาศใส่กำแพงบาง/ลังซ้อน ; กระโดดข้างขั้นไม่โดนดันออก ──
        _start(g, side="atk", n=2)
        _use_map(g, lm)
        _put(g, 8.0, z_bot, math.pi / 2)
        bad = 0
        for _ in range(30):
            g.vel = [6.75, 0.0]
            if not g.cl_air:
                _press(g, pygame.K_SPACE, False)
                _press(g, pygame.K_SPACE, True)
            g.update_play(0.1)
            x = g.cam.pos[0]
            if x > 12.25 - clutchmap.PLAYER_R + 1e-6 or not lm.walkable(x, g.cam.pos[2]):
                bad += 1
        _press(g, pygame.K_SPACE, False)
        _use_map(g, cm)
        _put(g, 1.5, _lane_z(cm, 2), math.pi / 2)
        for _ in range(30):
            g.vel = [6.75, 0.0]
            if not g.cl_air:
                _press(g, pygame.K_SPACE, False)
                _press(g, pygame.K_SPACE, True)
            g.gun_crouch = True
            g.update_play(0.1)
            if g.cam.pos[0] > face - clutchmap.PLAYER_R + 1e-6 or g.cl_feet > 0.01 and not g.cl_air:
                bad += 1
        g.gun_crouch = False
        _press(g, pygame.K_SPACE, False)
        if bad:
            E(f"clutch tunnel: ทะลุกำแพงบาง/ลังซ้อน {bad} เฟรม")
        sm = ClutchMap.from_ascii(["#" * 20] + ["#" + "." * 8 + "1" * 10 + "#"] * 8 + ["#" * 20])
        _use_map(g, sm)
        sx = sm.x0 + 9 * sm.cell - 0.2                            # วงกลมทับขั้น 0.4 ม. อยู่ 0.2 ม.
        _put(g, sx, sm.z0 + 4.5 * sm.cell, 0.0)
        g.cl_feet, g.cl_eye = 0.0, EYE_Y
        g.cam.pos = [sx, EYE_Y, sm.z0 + 4.5 * sm.cell]
        _press(g, pygame.K_SPACE, True)
        _run(g, 1.0)
        _press(g, pygame.K_SPACE, False)
        if abs(g.cam.pos[0] - sx) > 1e-6:
            E(f"clutch jump by step: ไม่ควรโดนดันออกข้าง ({g.cam.pos[0] - sx:+.3f} ม.)")
        g.state = "pause"
        g.end_game()
        # ── บอท/nav ไม่เปลี่ยน: ด่านเดิม BOX ยังทึบ, nav ไม่มีโหนดบนกล่อง, move ค่าเริ่มขึ้นกล่องไม่ได้ ──
        pm = cm.player_map()
        bx, bz = 5.25, _lane_z(cm, 0)
        if cm.floor_y(bx, bz) is not None or abs(pm.floor_y(bx, bz) - 1.1) > 1e-9 or cm.player_map() is not pm \
                or cm.nav_node(bx, bz) is not None and abs(cm.nav_pos(cm.nav_node(bx, bz))[0] - bx) < 0.3:
            E("clutch player_map: ด่านเดิมต้องไม่เปลี่ยน (BOX ทึบสำหรับบอท/nav)")
        x, z, vel = 3.0, bz, [6.75, 0.0]
        for _ in range(40):
            vel[0] = 6.75
            x, z, f = cm.move(x, z, 0.0, vel, 0.05, clutchmap.BOT_R)
        if x > face - clutchmap.BOT_R + 1e-6 or f != 0.0:
            E(f"clutch bots: move ค่าเริ่มต้องไม่ปีนกล่อง (x {x:.3f} f {f})")
        # "กล่อง" เตี้ย/ต่ำกว่าพื้น (เศษ bake ของแมพจริง) ต้องทึบเหมือนเดิมสำหรับผู้เล่นด้วย — ไม่มีหลุม/ขั้นที่บอทถือว่าทึบ
        lb = ClutchMap.from_ascii(["#" * 12] + ["#..ee..ff..#"] * 4 + ["#" * 12],
                                  legend={"e": (BOX, 0.3, 0), "f": (BOX, -0.4, 0)}).player_map()
        if any(lb.floor_y(*lb.center(i, 2)) is not None for i in (3, 4, 7, 8)):
            E("clutch player_map: กล่องเตี้ย ≤ STEP_UP / ต่ำกว่าพื้น ต้องยังทึบ")
        wall = [c for c in range(len(lm.kind)) if lm.kind[c] == WALL]
        if not wall or lm.player_map().floor_y(*lm.center(wall[0] % lm.nx, wall[0] // lm.nx)) is not None:
            E("clutch player_map: กำแพงบางต้องยืนไม่ได้")
    except Exception as ex:
        E(f"clutch move selftest พัง: {type(ex).__name__}: {ex} {traceback.format_exc(limit=4)}")
    finally:
        stability.Stability.shot_dir = shot_raw
        g.keys_down, g.gun_crouch, g.lmb_down = set(), False, False
        if g.state == "play":
            g.state = "pause"
            g.end_game()
    g.clutch_move_ms = round((time.perf_counter() - t0) * 1000)
    return errors
