# -*- coding: utf-8 -*-
"""selftest ของโหมด CLUTCH ส่วนที่ 2 — ข้อบกพร่องที่ review รวมทีม (2026-09-28) ยืนยันบนสมองบอท/แมพจริงแล้ว (เรียกจาก
clutchtest.selftest ด้วย Game headless ตัวเดียวกันและสมองบอทปลอม FakeBrain) : หลุดโฟกัสตอนนับถอยหลัง, เมาส์ตอนบอทหยุดนิ่ง,
กู้หลอก/รีโหลดระหว่างกู้, t_used, วางคร่อมขอบ, ไซต์ค้าง, ฉากชนะไม่ได้, ไซต์ผิดโซน, จุดเริ่มในสายตาศัตรู (Yard/ฉากสร้างเอง),
cache มินิแมพ/แมพใหญ่, จุดที่เห็นล่าสุดบนมินิแมพ, บอทพ้นขอบจอ, ค้าง R, แฟลชโดนยิง, why_text/อักษร/อัตราอ้างอิง/ข้อความ GL,
ป้ายบนสุด, หมุด spike + รีคอยล์, สโคปไม่ตัด HUD, Tab เป็น texture ของ GPU, งบเวลาเตรียม nav — คืน list ข้อความ error"""
import gc
import math
import random
import traceback
import weakref

import pygame

from .config import EYE_Y, UI_FONT_NO_GLYPH
from . import clutchmap, clutchresults, clutchscen, guns
from .clutchtest import _put, _run, _start


def _hud_texts(g, draw):
    """(ข้อความ, rect) ที่ HUD วาดในการเรียก draw() — ครอบ g.text ตัวปัจจุบัน (ตัวตรวจ glyph ของ selftest ยังทำงาน)"""
    txt0, got = g.text, []

    def cap(s, *a, **k):
        r = txt0(s, *a, **k)
        got.append((str(s), pygame.Rect(r)))
        return r
    g.text = cap
    try:
        draw()
    finally:
        g.text = txt0
    return got


def _covered(surf, rects):
    left = surf.copy()
    for r in rects:
        left.fill((0, 0, 0, 0), r)
    return left.get_bounding_rect().w == 0


def _mm_xy(cm, ir, x, z):
    """พิกัดบนภาพมินิแมพที่วางใน ir (สูตรเดียวกับ clutch_draw_minimap)"""
    from . import clutchmesh
    u, v = clutchmesh.minimap_xy(cm, ir.w, ir.h, x, z)
    return ir.x + u, ir.y + v


def _fix_checks(g):
    """ข้อบกพร่องที่ review รวมทีม (2026-09-28) ยืนยันบนสมองบอท/แมพจริงแล้ว — แต่ละข้อต้องไม่กลับมา (สมองบอทปลอม, Yard)"""
    errors = []
    E = errors.append
    Ev = pygame.event.Event
    FL, FG = getattr(pygame, "WINDOWFOCUSLOST", None), getattr(pygame, "WINDOWFOCUSGAINED", None)
    W0, H0, scr0, gp0 = g.W, g.H, g.screen, pygame.key.get_pressed
    try:
        # ── หลุดโฟกัสตอนนับถอยหลัง: รอบเริ่ม (begin_play ทำบัญชีเฟรม/PB ครบ) แล้วพักทันที — เดิมเริ่มเล่นเองแล้วตาย = แพ้ลง
        #    history ; alt-tab กลับมาก่อนเริ่ม = ไม่พัก ; ESC ตอนนับถอยหลัง = ธงไม่รั่วไปรอบหน้า ──
        if FL is not None:
            g.S["clutch"] = dict(clutchscen.DEFAULT_CFG, map="yard", site="A")
            g.frame_ms = [777.0]
            g.clutch_start(False)
            g.handle_event(Ev(FL))
            st0 = g.state
            g.begin_play()
            if (st0, g.state, g.gt, g.cl_ready, g.frame_ms) != ("countdown", "pause", 0.0, True, []):
                E(f"clutch focus: หลุดโฟกัสตอนนับถอยหลังต้องเริ่มรอบแล้วพัก ({st0} → {g.state}, gt {g.gt}, "
                  f"ready {g.cl_ready}, frame_ms {g.frame_ms[:1]})")
            g.resume_play()
            if g.state != "play" or g.resume_cd != 3.0:
                E("clutch focus: เล่นต่อหลังพักตอนเริ่ม ต้องนับ 3 วิแบบปกติ")
            g.state = "pause"
            g.end_game()
            if FG is not None:
                g.clutch_start(False)
                g.handle_event(Ev(FL))
                g.handle_event(Ev(FG))
                g.begin_play()
                if g.state != "play":
                    E("clutch focus: alt-tab กลับมาก่อนนับถอยหลังจบต้องไม่พัก")
                g.state = "pause"
                g.end_game()
            g.clutch_start(False)
            g.handle_event(Ev(FL))
            g.go_menu()
            _start(g)
            if g.state != "play":
                E("clutch focus: ธงพักตอนเริ่มรั่วข้ามรอบ (ESC ตอนนับถอยหลังแล้วเริ่มใหม่)")
            g.state = "pause"
            g.end_game()
        # ── เมาส์หันกล้องไม่ได้ตอนบอทหยุดนิ่ง (นับถอยหลัง / นับกลับหลังพัก) — เล็งรอหัวบอทนิ่ง = คิลฟรี ; โหมดอื่นหันได้เหมือนเดิม ──
        mv = Ev(pygame.MOUSEMOTION, rel=(300, 0), pos=(0, 0), buttons=(0, 0, 0))
        g.S["clutch"] = dict(clutchscen.DEFAULT_CFG, map="yard", site="A")
        g.clutch_start(False)
        y0 = g.cam.yaw
        g.handle_event(mv)
        cd_turn = g.cam.yaw != y0
        g.begin_play()
        g.resume_cd = 2.0
        g.handle_event(mv)
        rc_turn = g.cam.yaw != y0
        g.resume_cd = 0.0
        g.handle_event(mv)
        play_turn = g.cam.yaw != y0
        g.state = "pause"
        g.end_game()
        g.go_menu()
        md0 = g.mode
        g.mode = "gun"
        g.start_countdown()
        y1 = g.cam.yaw
        g.handle_event(mv)
        gun_turn = g.cam.yaw != y1
        g.state, g.mode = "menu", md0
        if cd_turn or rc_turn or not play_turn or not gun_turn:
            E(f"clutch mouse: หันได้ตอนนับถอยหลัง {cd_turn} / นับกลับ {rc_turn} (ต้องไม่ได้) ; ตอนเล่น {play_turn} / "
              f"GUNFIGHT นับถอยหลัง {gun_turn} (ต้องได้)")
        # ── กู้: เริ่มกู้ = ยกเลิกรีโหลด ; รีโหลดไม่ได้ระหว่างกู้ ; หลุดโฟกัส/ตายระหว่างกู้ไม่นับ "กู้หลอก" ; t_used ไม่รวมป้ายผล ──
        br = _start(g, side="def", n=2)
        _put(g, -11.0, 9.5)
        g.gun_mag = 3
        g.gun_reload()
        rel0 = g.gun_reload_until > 0
        g.clutch_key(pygame.K_f, True)
        _run(g, 0.3)
        started = g.cl_defuse_t0 is not None and g.gun_reload_until == 0.0
        g.gun_reload()
        blocked = g.gun_reload_until == 0.0 and g.gun_mag == 3
        if not (rel0 and started and blocked):
            E(f"clutch reload: เริ่มกู้ต้องยกเลิกรีโหลด ({rel0}, {started}) + รีโหลดระหว่างกู้ไม่ได้ ({blocked})")
        if FL is not None:
            g.handle_event(Ev(FL))
            ok = g.state == "pause" and g.cl_defuse_t0 is None and g.cl_fake == 0
            g.resume_play()
            g.resume_cd = 0.0
            _run(g, 0.2)
            if not ok or g.cl_fake:
                E(f"clutch fake: alt-tab ระหว่างกู้ต้องไม่นับกู้หลอก (fake {g.cl_fake})")
        g.clutch_key(pygame.K_f, True)
        _run(g, 0.2)
        started = g.cl_defuse_t0 is not None
        b0 = br.bots[0]
        br.script = [(g.gt, {"k": "shot", "bot": b0, "from": b0.eye(), "to": tuple(g.cam.pos), "zone": "head",
                             "dmg": 999.0})]
        _run(g, 3.0)
        e = g.last_entry
        t_res = g.cl_result["t"] if g.cl_result else None
        if not started or (e.get("why"), e.get("fake")) != ("died", 0):
            E(f"clutch fake: ตายระหว่างกู้ต้องไม่นับกู้หลอก ({e.get('why')}, fake {e.get('fake')})")
        if t_res is None or e.get("t_used") != round(t_res, 1) or e.get("t_used", 99) > g.gt - 1.0:
            E(f"clutch t_used: ต้องเป็นเวลาตอนตัดสินผล {t_res} ไม่รวมป้ายผล 1.6 วิ (ได้ {e.get('t_used')}, จบ {g.gt:.2f})")
        # ── วาง spike: ห้ามวางคร่อมขอบต่างระดับ + บอกเหตุบน HUD ; spike ลงพื้นใต้จุด (= spike_y ของสมองบอท) ;
        #    history เก็บไซต์ที่วางจริง (ฉากป้ายไซต์อื่นแต่เริ่มในโซนนี้) ──
        g.W, g.H = 1280, 720
        g.screen = pygame.Surface((1280, 720), pygame.SRCALPHA)
        br = _start(g, side="atk", n=2)
        g.clutch_scen["s"] = "B"
        _put(g, -12.0, 9.5, 0.0)
        g.clutch_key(pygame.K_4, True)
        _run(g, 0.7)
        g.cl_feet = 0.9                                      # ตัวยังเกาะขอบบน 0.9 ม. แต่ใต้จุดศูนย์กลางเป็นพื้น 0
        ledge = not g.clutch_can_plant() and not g.clutch_plant_floor_ok()
        hint = any("ต่างระดับ" in s for s, _r in _hud_texts(g, g.draw_hud))
        g.cl_feet = 0.0
        g.lmb_down = True
        _run(g, 4.3)
        g.lmb_down = False
        sp = g.cl_spike
        g.state = "pause"
        g.end_game()
        if not ledge or not hint or sp["state"] != "planted" or sp["y"] != g.cmap.floor_y(sp["x"], sp["z"]) \
                or g.last_entry.get("site") != "A":
            E(f"clutch plant: คร่อมขอบ ({ledge}, hint {hint}) / spike y {sp.get('y')} / ไซต์ที่วาง "
              f"{g.last_entry.get('site')} (ต้อง A)")
        # ── เลือกฉาก: ไซต์ C ค้างจากแมพ 3 ไซต์ → สุ่ม (หน้าตั้งค่า + ค่าที่เซฟไว้แล้ว) — เดิมฉากสร้างเองทุกรอบ ──
        from . import clutchsetup
        fl = clutchsetup.ClutchSetupFlow(g, force=True)
        fl.cfg["site"] = "C"
        fl._set("map", clutchscen.YARD)
        site_ui = fl.cfg["site"]
        g.flow, g.state = None, "menu"
        g.S["clutch"] = dict(clutchscen.DEFAULT_CFG, map="yard", site="C", side="atk", n=2)
        g.clutch_start(False)
        if site_ui != "any" or g.clutch_scen_i < 0 or g.clutch_scen.get("gen") or g.clutch_last["key"][3] != "any":
            E(f"clutch site: ไซต์ C บนแมพ 2 ไซต์ต้องกลับเป็นสุ่ม (หน้าตั้งค่า {site_ui}, ฉาก {g.clutch_scen_i})")
        g.begin_play()
        g.state = "pause"
        g.end_game()
        # ── ฉากชนะไม่ได้แม้ไม่มีศัตรู = ไม่ถูกเลือก (ความเร็วปืน) ; ATK เลือกไซต์ = ไม่เริ่มในโซนอีกไซต์ ──
        cmt = clutchmap.testyard()
        d2 = [s for s in cmt.scen if s["t"] == "def" and s["n"] == 2][0]
        a3 = [s for s in cmt.scen if s["t"] == "atk" and s["n"] == 3][0]
        far = dict(d2, p=[15.0, -12.0, 0.0], left=15)
        cmt.scen = [dict(d2), far, dict(a3), dict(a3, p=[-12.0, 9.0, 0.0])]
        need = clutchscen.scen_need(cmt, far, "def", 2.0)
        pk = {clutchscen.pick_scenario(cmt, "def", 2, "any", random.Random(s), run_speed=2.0)[0] for s in range(12)}
        raw = {clutchscen.pick_scenario(cmt, "def", 2, "any", random.Random(s))[0] for s in range(12)}
        if not (need and need > 15.0) or pk != {0} or 1 not in raw:
            E(f"clutch feasible: ฉากต้องใช้ {need} วิ (มี 15) ต้องไม่ถูกเลือก ({pk} / ไม่กรอง {raw})")
        pb = {clutchscen.pick_scenario(cmt, "atk", 3, "B", random.Random(s))[0] for s in range(12)}
        pa = {clutchscen.pick_scenario(cmt, "atk", 3, "any", random.Random(s))[0] for s in range(12)}
        if pb != {2} or 3 not in pa:
            E(f"clutch site: ATK เลือกไซต์ B ต้องไม่ได้ฉากที่เริ่มในโซน A ({pb} / สุ่ม {pa})")
        # ── Training Yard: ทุกฉากเริ่มนอกสายตาศัตรู ; ฉากสร้างเองก็เช่นกัน (จุดตัวอย่างแบบสมองบอท) ──
        cmy = clutchscen.load_map("yard")
        bp = getattr(clutchscen._module("bots"), "body_points", None)

        def seen(sc):
            p = sc["p"]
            f = clutchscen._ground(cmy, p[0], p[1])
            out = 0
            for q in sc["e"]:
                eye = (q[0], (cmy.floor_y(q[0], q[1]) or 0.0) + EYE_Y, q[1])
                out += cmy.any_visible(eye, bp(eye, p[0], p[1], f) if bp else guns.humanoid_points(p[0], p[1], 0.0, f))
            return out
        bad = [i for i, sc in enumerate(cmy.scen) if seen(sc)]
        gen = sum(1 for s in range(6) for side in ("atk", "def")
                  if seen(clutchscen.gen_scenario(cmy, side, 4, "any", random.Random(s))))
        if bad or gen:
            E(f"clutch yard: จุดเริ่มอยู่ในสายตาศัตรู — ฉาก {bad} / ฉากสร้างเอง {gen}/12")
        # ── HUD ──
        br = _start(g, side="atk", n=2)
        per = g._cl_map_cache()
        if not isinstance(g._cl_mini, weakref.WeakKeyDictionary) or g._cl_big_px() not in per \
                or g._cl_mini_px() not in per:
            E("clutch HUD: แมพใหญ่ของ Tab ต้องสร้างตอนตั้งรอบ + cache ต่อตัวแมพ (ไม่ใช่ id)")
        tmp, cm_keep = clutchmap.testyard(), g.cmap
        g.cmap = tmp
        g.clutch_minimap(40)
        n1 = len(g._cl_mini)
        g.cmap = cm_keep
        del tmp
        gc.collect()
        if len(g._cl_mini) != n1 - 1:
            E("clutch HUD: มินิแมพของแมพที่ถูกทิ้งต้องหายจาก cache (id ซ้ำ = ภาพแมพเก่า)")
        # มินิแมพ: ศัตรูที่เพิ่งหลุดสายตาวาด ณ จุดที่เห็นล่าสุด (เดิมตามตัวจริงไปอีก 2 วิ)
        b = br.bots[0]
        b.meta["pseen"], b.meta["pseen_xz"] = g.gt, (b.x, b.z)
        x_real, z_real = b.x, b.z
        b.x, b.z = b.x + 8.0, b.z - 8.0
        s_ = g.hud_scale()

        def S(v):
            return int(round(v * s_))
        mp = g._cl_mini_px()
        mr = pygame.Rect(S(14), S(14), mp, mp)
        img = g.clutch_minimap(mp)
        g.screen.fill((0, 0, 0, 0))
        g.clutch_draw_minimap(mr, img, S)
        ir = img.get_rect(center=mr.center)

        def pix(x, z):
            u, v = _mm_xy(g.cmap, ir, x, z)
            return tuple(g.screen.get_at((int(u), int(v))))[:3]
        if pix(x_real, z_real) != (255, 70, 85) or pix(b.x, b.z) == (255, 70, 85):
            E("clutch minimap: ศัตรูที่หลุดสายตาต้องอยู่ที่จุดที่เห็นล่าสุด ไม่ใช่ตำแหน่งจริง")
        b.x, b.z = x_real, z_real
        # บอทพ้นขอบจอ (ไม่มีจุดใดอยู่ในภาพ) ต้องไม่นับว่าเห็น — เดิมจุดกลาง ×1.05 = เห็นทั้งที่พ้นขอบ ~35 px
        g.cam.pos, g.cam.yaw, g.cam.pitch = [0.0, EYE_Y, 0.0], 0.0, 0.0
        f = g.fl()
        others = [o for o in br.bots if o is not b]
        for o in others:
            o.alive = False
        g.cmap.blocked = lambda p, q: False                 # ลานโล่งสมมติ — เทสเรขาคณิตกรอบภาพล้วน
        try:
            x = g.W / (2.0 * f) * 10.0
            while True:
                b.x, b.z = x, 10.0
                xs = [g.W / 2 + f * c[0] / c[2] for c in (g.cam.to_cam(p) for p in b.points())]
                if min(xs) >= g.W + 5:
                    break
                x += 0.01
            g.clutch_perceive()
            off = b.exposed
            b.x = g.W / (2.0 * f) * 10.0 - 0.3
            g.clutch_perceive()
            on = b.exposed
        finally:
            del g.cmap.blocked
            for o in others:
                o.alive = True
        if off or not on:
            E(f"clutch seen: บอทพ้นขอบจอต้องไม่นับว่าเห็น ({off}) / ชิดขอบในจอต้องเห็น ({on})")
        b.x, b.z = x_real, z_real
        # ค้าง R = เตือนก่อนเริ่มใหม่ (แบบ GUNFIGHT)
        held = type("P", (dict,), {"__missing__": lambda s, k: False})({pygame.K_r: True})
        pygame.key.get_pressed = lambda: held
        g.r_hold_since = pygame.time.get_ticks() - 400
        rh = any("ค้าง R" in s for s, _r in _hud_texts(g, g.draw_hud))
        pygame.key.get_pressed = gp0
        g.r_hold_since = None
        if not rh:
            E("clutch HUD: ค้าง R ต้องมีคำเตือนก่อนเริ่มรอบใหม่")
        # แฟลชโดนยิง (software): ไม่สะสม surface เต็มจอต่อค่า alpha (เดิม ~1.5 GB ที่ 1440p ต่อ ~10 ครั้งที่โดน)
        n0 = len(getattr(g, "_scrim_cache", None) or {})
        for k in range(12):
            g.gun_flash = 0.02 * (k + 1)
            g.draw_hud()
        g.gun_flash = 0.0
        if len(getattr(g, "_scrim_cache", None) or {}) != n0 or getattr(g, "_flash_fill_ov", None) is None:
            E("clutch HUD: แฟลชโดนยิงต้องใช้ surface เดียวซ้ำ (ไม่ใช่ scrim ต่อ alpha)")
        # ป้ายผล/เหตุผล: ATK ตายก่อนวาง = "ตาย" (ไม่ใช่ "หลังวาง") ; ข้อความโค้ชไม่มีอักษรที่ไม่มีในฟอนต์ (→)
        if clutchscen.why_text("atk", "died", planted=False) != clutchscen.WHY_TH["died"] or \
                "หลังวาง" not in clutchscen.why_text("atk", "died"):
            E("clutch why_text: ATK ตายก่อนวางต้องเป็น 'ตาย'")
        g.cl_rt = 312
        if any(ch in UI_FONT_NO_GLYPH for t, _c in g.clutch_facts() for ch in t):
            E("clutch facts: มีอักษรที่ฟอนต์ไม่มี (เป็นกล่อง)")
        # อัตราชนะผู้เล่นจริง: index เก็บเป็น % เสมอ — 0.2% ต้องไม่กลายเป็น 20%
        rw0 = clutchmap.ref_winrates
        clutchmap.ref_winrates = lambda: {"atk": {"5": 0.2, "1": 51.7}}
        try:
            rr = (clutchresults.ref_rate("atk", 5), clutchresults.ref_rate("atk", 1))
        finally:
            clutchmap.ref_winrates = rw0
        if abs(rr[0] - 0.002) > 1e-9 or abs(rr[1] - 0.517) > 1e-9:
            E(f"clutch ref_rate: % ต้องหาร 100 เสมอ ({rr})")
        # ข้อความเมื่อไม่มีโลก 3D: GPU ปิด = เปิดใน SETTINGS ; ตัววาดแมพล้ม = เปิดโปรแกรมใหม่ (ไม่ใช่ "เปิด GPU")
        # ไม่มี moderngl (Python 3.14) = ปุ่ม SETTINGS ไม่มีผล → ต้องบอกให้ลง 3.13 (CI ไม่ลง moderngl จึงเช็กทั้งสองทาง)
        from . import display as _disp
        mgl0 = _disp._mgl
        try:
            _disp._mgl = mgl0 or object()
            r_off = g.clutch_gl_reason()
            _disp._mgl = None
            r_nomgl = g.clutch_gl_reason()
        finally:
            _disp._mgl = mgl0
        g._clutch_gl_off = True
        r_fail = g.clutch_gl_reason()
        g._clutch_gl_off = False
        if "SETTINGS" not in r_off or "SETTINGS" in r_fail or "ใหม่" not in r_fail \
                or "3.13" not in r_nomgl or "SETTINGS" in r_nomgl:
            E(f"clutch GL text: {r_off} / {r_nomgl} / {r_fail}")
        g.state = "pause"
        g.end_game()
        # ── ป้ายบนสุด DEFUSED/BOOM อยู่บนแผ่นรอง ; หมุด spike (DEF 3 วิแรก) ฉายด้วยกล้องที่เด้งรีคอยล์แบบโลก GL ──
        for ww, hh in ((1280, 720), (2560, 1440)):
            g.W, g.H = ww, hh
            g.screen = pygame.Surface((ww, hh), pygame.SRCALPHA)
            br = _start(g, side="def", n=2)
            _put(g, -4.0, 9.5, -math.pi / 2)
            g.gt = 1.0
            g.view_offset = lambda: (0.05, 0.08)
            try:
                got = _hud_texts(g, g.draw_hud)
                sp = g.cl_spike
                p0, y0_ = g.cam.pitch, g.cam.yaw
                g.cam.pitch, g.cam.yaw = p0 + 0.05, y0_ + 0.08
                pr = g.project((sp["x"], sp["y"] + 0.3, sp["z"]), g.fl())
                g.cam.pitch, g.cam.yaw = p0, y0_
            finally:
                del g.view_offset
            lab = [r for s, r in got if s.startswith("SPIKE ")]
            s_ = g.hud_scale()
            if pr is None or not lab or abs(lab[0].centerx - int(pr[0])) > 1 or \
                    abs(lab[0].centery - (int(pr[1]) - int(round(20 * s_)))) > 1:
                E(f"clutch spike pin {ww}x{hh}: ต้องฉายด้วยกล้องที่เด้งรีคอยล์ ({lab[:1]}, {pr})")
            plates = []
            pl0 = g._cl_plate
            g._cl_plate = lambda r, S_: (plates.append(pygame.Rect(r)), pl0(r, S_))
            try:
                for st in ("defused", "detonated"):
                    g.cl_spike["state"] = st
                    plates.clear()
                    got = _hud_texts(g, g.draw_hud)
                    lbl = "DEFUSED" if st == "defused" else "BOOM"
                    tr = [r for s, r in got if s == lbl]
                    top = [p for p in plates if p.top == int(round(8 * s_))]
                    if not tr or not top or not top[0].contains(tr[0]):
                        E(f"clutch top {ww}x{hh}: ป้าย {lbl} ล้นแผ่นรอง ({tr[:1]} / {top[:1]})")
            finally:
                del g._cl_plate
            g.cl_spike["state"] = "planted"
            g.state = "pause"
            g.end_game()
        # ── GPU: สโคป Op ไม่ทิ้งพิกเซล HUD ของ clutch (band 0) ; Tab = แผงเป็น texture (post_fx tabmap) + overlay มีแค่เครื่องหมาย
        #    ที่ mark dirty ครบ และยังอยู่ในขีด dirty-rect (ไม่ตกไปอัพโหลดเต็มจอทุกเฟรม) ──
        g.W, g.H = 1280, 720
        g.screen = pygame.Surface((1280, 720), pygame.SRCALPHA)
        br = _start(g, side="atk", n=2, weapon="operator")
        _run(g, 1.2)
        g._glr, g._world_gpu_frame, g._glr_post_ok, g._post_fx = object(), True, True, None
        try:
            g.gun_rmb(True)
            g.draw_crosshair()
            band = (g._post_fx or {}).get("band")
            g._post_fx = None
            g.gun_rmb(False)
            if band != (0, 0):
                E(f"clutch scope: band ต้องเป็น (0, 0) — HUD ไม่ถูกตัดตอนสโคป (ได้ {band})")
            g.cl_tab = True
            ov = pygame.Surface((1280, 720), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 0))
            g.screen, g._dirty, g._track_dirty = ov, [], True
            g.draw_hud()
            tab = (g._post_fx or {}).get("tabmap")
            dirty = list(g._dirty)
            merged = g._merge_dirty(dirty)
            g._track_dirty, g._post_fx = False, None
            soft = pygame.Surface((1280, 720), pygame.SRCALPHA)
            soft.fill((0, 0, 0, 0))
            g._glr = None
            g.screen = soft
            g.draw_hud()
            pad = int(round(6 * g.hud_scale()))
            bp_ = g._cl_big_px()
            box = pygame.Rect(0, 0, bp_, bp_)
            box.center = (640, 360)
            box.inflate_ip(2 * pad, 2 * pad)
            q = (box.x + max(1, pad // 2), box.centery)
            ok_tab = tab is not None and tuple(tab[1]) == tuple(box) and tab[0].get_size() == box.size
            ok_px = ok_tab and ov.get_at(q)[3] == 0 and soft.get_at(q)[3] > 0 and \
                tuple(tab[0].get_at((q[0] - box.x, q[1] - box.y))) == tuple(soft.get_at(q))
            if not ok_tab or not ok_px or not _covered(ov, dirty) or merged is None:
                E(f"clutch Tab GPU: แผงต้องไปเป็น texture ({ok_tab}, พิกเซล {ok_px}), overlay mark ครบ "
                  f"({_covered(ov, dirty)}), dirty-rect ไม่เกินขีด ({None if merged is None else len(merged)})")
        finally:
            g._glr, g._world_gpu_frame, g._post_fx, g._track_dirty, g._dirty = None, False, None, False, []
            g.cl_tab = False
        g.state = "pause"
        g.end_game()
        # ── นับถอยหลัง: เตรียม nav แบบงบเวลา (หลาย prepare ต่อเฟรม) — สมองปลอมต้อง 3 ครั้ง = พร้อมในเฟรมเดียว ──
        g.S["clutch"] = dict(clutchscen.DEFAULT_CFG, map="yard", site="A")
        g.clutch_start(False)
        g.clutch_countdown_tick()
        if not g.cl_ready or g.brain.prep < 3:
            E(f"clutch countdown: เตรียม nav ต้องใช้งบเวลา ไม่ใช่ครั้งเดียวต่อเฟรม (prep {g.brain.prep})")
        g.begin_play()
        g.state = "pause"
        g.end_game()

        # ── จุดเกิดปลอดภัย (ผู้ใช้ 2026-09-28: 1v5 "เกิดกลางดงศัตรู 2 ตัว ตายทันที") — ฉากที่ศัตรูใกล้/เห็นตั้งแต่เริ่ม
        #    ต้องไม่ถูกเลือก ; ไม่มีฉากปลอดภัยเลย = ฉากสร้างที่จุดเริ่มปลอดภัย ; โหมดสุ่มจุดยืนไม่วางบอทใกล้/เห็นผู้เล่น ──
        import random as _rnd
        cm = clutchmap.ClutchMap.from_ascii(["#" * 42] + ["#" + "." * 40 + "#"] * 40 + ["#" * 42],
                                            sites={"A": {"c": [5.0, 5.0], "plants": [[5.0, 5.0, 1]]}},
                                            spawns={"atk": [1.5, 1.5], "def": [9.0, 9.0]})
        bad = {"t": "atk", "s": "A", "n": 2, "p": [2.0, 2.0, 0.0], "e": [[3.0, 4.0, 0.0], [8.0, 8.0, 0.0]], "left": 60}
        cm.scen = [bad]
        if clutchmap.start_safe(cm, 2.0, 2.0, bad["e"]):
            E("clutch safe-start: ศัตรูห่าง 2.2 ม. เห็นกันโล่ง ต้องไม่นับว่าปลอดภัย")
        i, sc = clutchscen.pick_scenario(cm, "atk", 2, "any", _rnd.Random(3))
        if i != -1:
            E(f"clutch safe-start: เลือกฉากเกิดกลางดง (#{i}) แทนฉากสร้างที่ปลอดภัย")
        cm2 = clutchmap.testyard()
        ok_real = [k for k, s2 in enumerate(cm2.scen or []) if clutchscen.scen_safe(cm2, k)]
        for k in range(len(cm2.scen or [])):
            s2 = cm2.scen[k]
            j, _ = clutchscen.pick_scenario(cm2, s2["t"], int(s2["n"]), "any", _rnd.Random(k))
            if j != -1 and j not in ok_real:
                E(f"clutch safe-start: yard เลือกฉาก #{j} ที่เกิดไม่ปลอดภัย")
    except Exception as ex:
        E(f"clutch fix-checks พัง: {type(ex).__name__}: {ex} {traceback.format_exc(limit=4)}")
    finally:
        pygame.key.get_pressed = gp0
        for a in ("view_offset", "_cl_plate"):
            g.__dict__.pop(a, None)
        g.W, g.H, g.screen = W0, H0, scr0
        g.flow, g.pending_end = None, None
    return errors
