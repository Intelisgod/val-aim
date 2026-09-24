# -*- coding: utf-8 -*-
"""selftest ในตัว (ย้าย verbatim) — เรียกผ่าน python aim_trainer.py --selftest"""

import os
import sys
import math
import pygame

from .config import *
from .data import trim_history
from .ranks import *
from .data import DATA_FILE
from .game import Game


def aim_at(g, t):
    dx = t.pos[0] - g.cam.pos[0]
    dy = t.pos[1] - g.cam.pos[1]
    dz = t.pos[2] - g.cam.pos[2]
    g.cam.yaw = math.atan2(dx, dz)
    g.cam.pitch = math.atan2(dy, math.hypot(dx, dz))


def realism_selftest(g, aim_at, aim_head):
    """แกน realism 2026-09-23 (คืน list ข้อผิดพลาด): หัวเป้าระดับจริง · ฟิสิกส์เดิน/เบรก · ความแม่นขณะเคลื่อนที่ ·
    ตัวสุ่มสเปรดเดียว (กระจายสม่ำเสมอ) · รีคอยล์แพตช์ 11.08 + yaw switch ระหว่างกดค้าง · BEAM ของ dodge หลบได้/โดนได้จริง"""
    import random
    from . import guns, movement
    from .camera import Camera
    from .riot_data import RIOT
    from .stability import Stability, cone_offset, patched_block
    from .target import Target
    errors = []
    rng_state = random.getstate()
    random.seed(20260923)
    try:
        # 1) หัวเป้า PLACEMENT/SWITCH/DODGE: ศูนย์หัวต้องอยู่ ±0.5° จากเส้นขอบฟ้าที่ 11 ม. ทุกขนาด
        #    (เดิมใจกลางลำตัวอยู่ระดับตา หัวลอยขึ้นไปอีก 1.15R = 1.9–3.0° สำหรับขนาดกลาง)
        for md in ("placement", "switch", "dodge"):
            for size in SIZES:
                g.mode, g.size_key, g.duration = md, size, 30
                g.start_countdown(); g.begin_play()
                worst = 0.0
                for _ in range(30):
                    g.targets = []
                    {"placement": g.spawn_placement, "switch": g.spawn_switch_wave,
                     "dodge": g.spawn_dodge_target}[md]()
                    for t in g.targets:
                        worst = max(worst, abs(math.degrees(math.atan2(t.head_pos()[1] - EYE_Y, 11.0))))
                if worst > 0.5:
                    errors.append(f"{md}/{size}: หัวเป้าห่างเส้นขอบฟ้า {worst:.2f}° ที่ 11 ม. (ต้อง ≤ 0.5°)")
        # 2) ฟิสิกส์เดิน: ปล่อยปุ่มหยุดสนิท 160–170 ms, counter-strafe ถึง deadzone 55–70 ms ทุก FPS, Shift เดิน
        errors += movement.selftest()
        # 3) ความแม่นขณะเคลื่อนที่ (Vandal): deadzone 27.5% · วิ่งเต็มสปีดยิงหัวที่ 17 ม. โดน < 2% · ยืนโดนเสมอ ·
        #    หมอบเดินโทษ +0.8° (ไม่ใช่ +3° แบบเดิน) · Sheriff หมอบเดิน +0.5° · Op deadzone 15%
        run = guns.WEAPONS["vandal"]["run_speed"]
        if guns.move_error_deg("vandal", 0.27 * run) != 0.0 or guns.move_error_deg("vandal", 0.29 * run) <= 0.0:
            errors.append("guns: deadzone ของ Vandal ต้องเป็น 27.5% ของความเร็ววิ่ง")
        if guns.move_error_deg("operator", 0.14 * 5.13) != 0.0 or guns.move_error_deg("operator", 0.2 * 5.13) <= 0.0:
            errors.append("guns: deadzone ของ Operator ต้องเป็น 15%")
        if (guns.move_error_deg("vandal", 2.0, crouch=True), guns.move_error_deg("sheriff", 2.0, crouch=True),
                guns.move_error_deg("vandal", run), guns.move_error_deg("sheriff", run)) != (0.8, 0.5, 6.0, 3.0):
            errors.append("guns: โทษหมอบเดิน/วิ่งต้องตรง wiki (Vandal 0.8/6, Sheriff 0.5/3)")
        cam = Camera()
        bot = guns.Bot(0.0, 17.0)
        cam.pitch = math.atan2(guns.HEAD_Y - cam.pos[1], 17.0)

        def head_rate(speed, crouch=False, n=4000):
            hit = 0
            for _ in range(n):
                st = Stability("vandal", guns.WEAPONS["vandal"]["rps"])
                po, yo, fe = st.shoot(0.0, crouch=crouch)
                sp = guns.spread_deg("vandal", 1.0, speed, crouch, firing_err=fe)
                hit += bot.hit_zone(cam, Stability.shot_dir(po, yo, sp)) == "head"
            return hit / n
        p_run, p_stand = head_rate(run), head_rate(0.0)
        p_walk = head_rate(run * MOVE_WALK_MULT)
        p_crouch = head_rate(run * MOVE_CROUCH_MULT, crouch=True)
        if p_run >= 0.02:
            errors.append(f"accuracy: วิ่งเต็มสปีดยิงหัวที่ 17 ม. โดน {p_run:.1%} (ต้อง < 2%)")
        if p_stand < 0.99:
            errors.append(f"accuracy: ยืนนิ่งนัดแรกยิงหัวที่ 17 ม. โดนแค่ {p_stand:.1%}")
        if not p_walk < p_crouch < p_stand:
            errors.append(f"accuracy: หมอบเดินต้องแม่นกว่าเดิน (walk {p_walk:.1%} crouch {p_crouch:.1%})")
        # 4) STRAFE ใช้ไรเฟิลจริง: วิ่งยิงเป้ากลางโดนน้อย (เดิม 93%) ยืนโดนเสมอ ; บันทึกความเร็วต่อนัด + %นัดขณะเคลื่อนที่
        g.mode, g.size_key, g.duration = "strafe", "medium", 30
        g.start_countdown(); g.begin_play()
        t = g.targets[0]

        def strafe_rate(v, n=600):
            hit = 0
            for _ in range(n):
                g.vel = [v, 0.0]
                g.gt += 0.5                       # แตะห่างกัน = นัดแรกทุกนัด (ไม่มีรีคอยล์สะสม)
                aim_at(g, t)
                hit += t.is_hit(g.cam, shot_dir=g.move_shot_dir())
            return hit / n
        s_run, s_stand = strafe_rate(run), strafe_rate(0.0)
        if s_run >= 0.15 or s_stand < 0.999:
            errors.append(f"strafe: วิ่งยิงโดน {s_run:.0%} / ยืนยิงโดน {s_stand:.0%} (ต้อง <15% / 100%)")
        if g.move_shots != 1200 or g.move_shots_moving != 600:
            errors.append(f"strafe: นับนัดขณะเคลื่อนที่ผิด ({g.move_shots_moving}/{g.move_shots})")
        g.vel = [run, 0.0]
        g.gt += 0.5
        g.strafe_moved = True
        aim_at(g, g.targets[0])
        g.shoot()
        if abs(g.shot_data[-1].get("v", -1) - run) > 1e-6:
            errors.append("strafe: shot_data ต้องบันทึกความเร็วตอนยิง (v)")
        g.end_game()
        e = g.last_entry
        if e.get("moving_pct") != round(601 / 1201 * 100) or e.get("mrev") != MODE_REV["strafe"]:
            errors.append(f"strafe: entry moving_pct/mrev ผิด ({e.get('moving_pct')}, {e.get('mrev')})")
        # 5) ตัวสุ่มสเปรดเดียว กระจายสม่ำเสมอบนพื้นที่กรวย: ครึ่งรัศมีได้ ~25% (ตัวสุ่มเก่าของ strafe/guns ได้ 50%)
        n = 20000
        half = math.radians(0.5)
        f1 = sum(math.hypot(*cone_offset(1.0)) <= half for _ in range(n)) / n
        f2 = sum(math.acos(max(-1.0, min(1.0, Target.sample_dir(math.radians(1.0))[2]))) <= half for _ in range(n)) / n
        f3 = sum(math.acos(max(-1.0, min(1.0, guns.sample_dir(1.0)[2]))) <= half for _ in range(n)) / n
        if not all(0.23 <= f <= 0.27 for f in (f1, f2, f3)):
            errors.append(f"spread sampler: ครึ่งรัศมีกรวยต้องได้ ~25% ({f1:.3f}/{f2:.3f}/{f3:.3f})")
        # 6) รีคอยล์แพตช์ 11.08 (ชั้น override — dump ไม่ถูกแก้) + protected bullets ไม่สลับทิศก่อนนัดที่ 7/9
        v, ph = patched_block("vandal"), patched_block("phantom")
        if (v["yaw_switch_time"], v["yaw_switch"], v["yaw_protected"], ph["yaw_protected"]) != (0.6, 0.10, 6.0, 8.0):
            errors.append("stability: ค่า yaw switch ของ Vandal/Phantom ต้องตามแพตช์ 11.08")
        if RIOT["vandal"]["stability"]["yaw_protected"] != 4.0 or Stability("vandal", 9.75).block() is RIOT["vandal"]["stability"]:
            errors.append("stability: ต้องทับค่าเป็นชั้น override ห้ามแก้ riot_data (dump)")
        for w, prot in (("vandal", 6), ("phantom", 8)):
            early = flips = 0
            rps = guns.WEAPONS[w]["rps"]
            for _ in range(200):
                st = Stability(w, rps)
                tt = 0.0
                st.shoot(tt)
                prev = st.yaw_dir
                for _k in range(24):
                    tt += 1.0 / rps
                    st.update(tt, 1.0 / rps)
                    st.shoot(tt)
                    if st.yaw_dir != prev:
                        flips += 1
                        early += st.burst <= prot
                    prev = st.yaw_dir
            if early or flips < 200:
                errors.append(f"stability {w}: สลับทิศก่อนพ้น protected {early} ครั้ง / สลับทั้งหมด {flips}")
        # SPRAY: กดค้างต้องเห็นทิศ yaw เบลนด์สลับจริงกลางแม็ก (เดิมเดินเวลา Stability เฉพาะตอนไม่ยิง = ไม่เคยสลับ)
        g.spray_weapon, g.mode, g.duration = "vandal", "spray", 30
        g.start_countdown(); g.begin_play()
        g.spray_firing = True
        g.spray_next_shot = g.gt
        changed, prev = False, g.spray_stab.yaw_mult
        for _ in range(600):
            if g.targets:
                aim_at(g, g.targets[0])
            g.update_play(1 / 60)
            ym = g.spray_stab.yaw_mult
            if g.spray_reloading_until == 0.0 and g.spray_stab.burst > 1 and ym != prev:
                changed = True
            prev = ym
        g.spray_firing = False
        if not changed:
            errors.append("spray: กดค้าง 10 วิ ทิศ yaw ไม่เคยสลับเลย (yaw switch ต้องเกิดระหว่างยิง)")
        g.end_game()
        if g.last_entry.get("srev") != SPRAY_SCORE_REV or g.last_entry.get("mrev") != SPRAY_SCORE_REV:
            errors.append("spray: entry ต้องมี srev และ mrev = SPRAY_SCORE_REV")

        # 7) DODGE BEAM: ยืนเฉย = โดน (เดิมไม่มีทางโดน) · เห็นเตือนแล้ววิ่งข้ามเส้นหยุด 0.3 วิ = หลบได้ · วิ่งถอยไปทางขอบ = โดน
        def beam_run(px, react, toward_edge=False):
            g.mode, g.size_key, g.duration = "dodge", "medium", 30
            g.start_countdown(); g.begin_play()
            g.dodge_next_haz = 1e9
            g.cam.pos[0], g.cam.pos[2] = px, 0.0
            g.cam.yaw = 0.0
            g.dodge_hazards = []
            g.spawn_dodge_hazard("beam")
            hz = g.dodge_hazards[0]
            hp0, d0, t0 = g.dodge_hp, g.dodge_dodged, g.gt
            inward = "a" if hz["dir"] < 0 else "d"
            key = {"a": "d", "d": "a"}[inward] if toward_edge else inward
            for _ in range(60 * 3):
                if react is not None and g.gt - t0 >= react:
                    g.keys_down = {key}
                g.update_play(1 / 60)
                if hz not in g.dodge_hazards:
                    break
            return g.dodge_hp < hp0, g.dodge_dodged - d0, hz
        for px in (3.0, -3.0, 0.1):
            hit, dodged, hz = beam_run(px, None)
            if not hit or dodged:
                errors.append(f"dodge beam: ยืนนิ่งที่ x={px} ต้องโดน (hit={hit} dodged={dodged})")
            hit, dodged, hz = beam_run(px, 0.3)
            if hit or dodged != 1:
                errors.append(f"dodge beam: วิ่งข้ามเส้นหยุดหลังเตือน 0.3 วิ ต้องหลบได้ (x={px} hit={hit})")
        hit, dodged, hz = beam_run(3.0, 0.3, toward_edge=True)
        if not hit:
            errors.append("dodge beam: วิ่งถอยไปทางขอบ (สวนลำแสง) ต้องโดน")
    except Exception as ex:
        import traceback
        errors.append(f"realism selftest: {type(ex).__name__}: {ex} {traceback.format_exc(limit=2)}")
    finally:
        random.setstate(rng_state)
        g.keys_down = set()
    return errors


def selftest():
    # stdout ที่ถูก pipe บนคอนโซล cp1252 ทำ print ไทยตอนสรุปผล (ทั้ง branch OK และ FAIL)
    # พัง UnicodeEncodeError → เทสผ่านหมดแต่ exit 1 (สัญญาณหลอก) — แบบเดียวกับ valorant_server.py
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    # ── แยกไฟล์เซฟตอนเทส (Module 0): ใช้ temp file -> history เริ่มว่างเสมอ
    #    และไม่แตะ aim_trainer_data.json จริงของผู้เล่น (ตรรกะเทสคงเดิมทุกเคส) ──
    import tempfile
    from . import data as _data
    global DATA_FILE
    DATA_FILE = os.path.join(tempfile.gettempdir(), "valaim_selftest_data.json")
    _data.DATA_FILE = DATA_FILE
    # ต้อง redirect BACKUP_FILE ด้วย — ไม่งั้น save_data ระหว่างเทสจะเอา "ข้อมูลเทสใน temp"
    # ไปเขียนทับ aim_trainer_data.backup.json จริงของผู้เล่น (ทำลายเส้นทางกู้ข้อมูล)
    _data.BACKUP_FILE = DATA_FILE.replace(".json", ".backup.json")
    for _p in (DATA_FILE, _data.BACKUP_FILE):
        try:
            os.remove(_p)
        except OSError:
            pass
    g = Game(headless=True)
    errors = []
    # ── ข้อความที่วาดทุกหน้าระหว่างเทสต้องไม่มีตัวที่ฟอนต์ UI ไม่มี glyph (ขึ้นเป็นกล่อง) ──
    #    เดิมหลุดมาเรื่อย ๆ (→ ใน GUNFIGHT/แผง raw input, ✓ ในการ์ดวันนี้) ; ครอบ g.text ตัวเดียว = ทุกจุดที่วาดตัวหนังสือ
    #    verify3: รายการตายตัว (config.UI_FONT_NO_GLYPH) ตกยุคได้ (▲ ▼ ← ★ ● ■ ▶ ⚠ Δ μ … ก็เป็นกล่อง) → เครื่องที่มีฟอนต์ UI จริง
    #    (Leelawadee UI) เช็คทุกตัวที่ไม่ใช่ ASCII/ไทย ด้วยการ render เทียบ U+E000 (ไม่มี glyph แน่ ๆ ; cache ต่อตัว ปกติ + หนา) ;
    #    เครื่องที่ใช้ฟอนต์ fallback อื่นเช็คแค่รายการ (กันเทสล้มเพราะฟอนต์ของเครื่องนั้น)
    _glyph_bad = []
    _glyph_ok = {}
    _text_real = g.text
    _glyph_fonts = [g.font(24), g.font(24, True)] if pygame.font.match_font("leelawadeeui") else []

    def _glyph_sig(f, ch):
        s = f.render(ch, True, (255, 255, 255))
        return s.get_size(), pygame.image.tobytes(s, "RGBA")
    _glyph_none = [_glyph_sig(f, "") for f in _glyph_fonts]

    def _no_glyph(ch):
        if ch in UI_FONT_NO_GLYPH:
            return True
        if not _glyph_fonts or ord(ch) < 128 or "฀" <= ch <= "๿" or ch.isspace():
            return False
        if ch not in _glyph_ok:
            _glyph_ok[ch] = not any(_glyph_sig(f, ch) == nd for f, nd in zip(_glyph_fonts, _glyph_none))
        return not _glyph_ok[ch]

    def _text_glyph_check(s, *a, **k):
        if any(_no_glyph(ch) for ch in str(s)):
            _glyph_bad.append(str(s))
        return _text_real(s, *a, **k)
    g.text = _text_glyph_check

    def play_round(mode, frames=600, do=None):
        g.mode = mode
        g.duration = 15
        g.start_countdown()
        g.begin_play()
        for i in range(frames):
            if g.state != "play":
                break
            if do:
                do(i)
            g.update_play(1 / 60)
        return g.state

    # flick / precision / tracking
    for md in ("flick", "precision", "tracking"):
        def act(i, md=md):
            if g.targets and i % 5 == 0:
                aim_at(g, g.targets[0])
                if not g.targets[0].is_hit(g.cam):
                    errors.append(f"{md}: aimed shot not registered")
                g.shoot()
        play_round(md, 30, act)
        if g.hits == 0:
            errors.append(f"{md}: no hits")
        # ปล่อยจนหมดเวลา
        play_round(md, 1200)
        if g.state != "results":
            errors.append(f"{md}: did not reach results")
        elif g.last_entry.get("mrev") != MODE_REV.get(md, 1):
            errors.append(f"{md}: history entry must record mrev (every new entry)")

    # reaction
    def react_act(i):
        if g.targets:
            aim_at(g, g.targets[0])
            g.shoot()
    play_round("reaction", 1500, react_act)
    if g.state != "results":
        errors.append("reaction: did not finish 5 targets")
    if len(g.data["history"]) == 0:
        errors.append("history not saved")
    if g.history_for("flick", duration=30):
        errors.append("history duration filter wrong (เล่นแต่ 15s แต่กรอง 30s แล้วเจอข้อมูล)")
    if not g.history_for("flick", duration=15, size="medium"):
        errors.append("history config filter wrong (กรอง config ที่เล่นจริงแล้วไม่เจอ)")

    # strafe
    # โทษกดก่อนเป้าโผล่ (reaction เวอร์ชันเข้ม)
    g.mode = "reaction"
    g.duration = 15
    g.start_countdown()
    g.begin_play()
    g.shoot()    # ยังไม่มีเป้า → TOO EARLY
    if g.early_clicks != 1 or g.early_penalty_ms != 100.0:
        errors.append("early click penalty not applied")
    for _ in range(600):
        g.update_play(1 / 60)
        if g.targets:
            break
    if g.targets:
        aim_at(g, g.targets[0])
        g.shoot()
        if not g.reaction_times or g.reaction_times[-1] < 100:
            errors.append("early penalty not added to next rt")
    else:
        errors.append("reaction target did not spawn within 10s")

    # ช่องไฟ reaction: ไม่ต่ำกว่า REACTION_GAP_MIN และไม่ปล่อยเป้าขณะยังกดปุ่มค้าง (นิ้วยังไม่กลับที่)
    g.mode = "reaction"
    g.duration = 15
    g.start_countdown()
    g.begin_play()
    if not (g.next_spawn_at - g.gt >= REACTION_GAP_MIN - 1e-6):
        errors.append("reaction: first gap shorter than REACTION_GAP_MIN")
    for _ in range(600):
        g.update_play(1 / 60)
        if g.targets:
            break
    aim_at(g, g.targets[0])
    g.lmb_down = True                      # จำลองผู้เล่นกดปุ่มแล้วยังไม่ปล่อย
    g.shoot()
    t_hit = g.gt
    if not (g.next_spawn_at - t_hit >= REACTION_GAP_MIN - 1e-6):
        errors.append("reaction: gap after hit shorter than REACTION_GAP_MIN")
    for _ in range(int(60 * (REACTION_GAP_MAX + 1))):
        g.update_play(1 / 60)
    if g.targets:
        errors.append("reaction: target spawned while mouse button still held")
    class _E:  # เหตุการณ์ปล่อยปุ่มปลอม (handle_mouse_up ไม่ได้ใช้ field ใดของ e)
        pass
    g.handle_mouse_up(_E())
    t_up = g.gt
    for _ in range(int(60 * (REACTION_RELEASE_GAP - 0.1))):
        g.update_play(1 / 60)
    if g.targets:
        errors.append("reaction: target spawned sooner than REACTION_RELEASE_GAP after release")
    for _ in range(60 * 5):
        g.update_play(1 / 60)
        if g.targets:
            break
    if not g.targets:
        errors.append("reaction: target did not spawn after release")
    elif g.gt - t_up < REACTION_RELEASE_GAP - 1 / 60:
        errors.append("reaction: spawn timing after release wrong")

    def strafe_act(i):
        if i % 60 < 25:
            g.keys_down.add("d")
        else:
            g.keys_down.discard("d")
        if g.targets and g.strafe_speed() < 0.5 and i % 10 == 0:
            aim_at(g, g.targets[0])
            g.shoot()
    play_round("strafe", 900, strafe_act)
    if g.hits == 0:
        errors.append("strafe: no hits")

    # sniper
    def sniper_act(i):
        for t in g.targets:
            if t.visible and SNIPER_DOOR_L < t.pos[0] < SNIPER_DOOR_R:
                aim_at(g, t)
                g.shoot()
                break
    st = play_round("sniper", 3000, sniper_act)
    if st != "results":
        errors.append(f"sniper: did not end (state={st}, spawned={g.sniper_spawned})")
    if g.sniper_hits == 0:
        errors.append("sniper: no hits")

    # ───────── โหมดใหม่ + head/body ─────────
    def aim_head(gg, t):
        hp = t.head_pos()
        dx, dy, dz = hp[0] - gg.cam.pos[0], hp[1] - gg.cam.pos[1], hp[2] - gg.cam.pos[2]
        gg.cam.yaw = math.atan2(dx, dz)
        gg.cam.pitch = math.atan2(dy, math.hypot(dx, dz))

    # --- head/body hitzone (classic mode, toggle ON) ---
    g.S["headshots"] = True
    g.mode = "flick"
    g.duration = 15
    g.start_countdown()
    g.begin_play()
    if g.targets:
        t0 = g.targets[0]
        # หัวต้องอยู่เหนือลำตัว และ is_head_hit แยกจาก body
        if t0.head_pos()[1] <= t0.pos[1]:
            errors.append("head_pos not above body")
        aim_head(g, t0)
        if not t0.is_head_hit(g.cam):
            errors.append("aim_head: head hit not registered")
        before_hs = g.headshots
        g.shoot()
        if g.headshots != before_hs + 1:
            errors.append("headshot not counted in classic mode (toggle ON)")
    # body hit (เล็งลำตัวล่างให้พลาดหัวแต่โดน body)
    g.mode = "flick"
    g.start_countdown(); g.begin_play()
    if g.targets:
        t0 = g.targets[0]
        bx, by, bz = t0.pos
        dx, dy, dz = bx - g.cam.pos[0], (by - t0.radius * 0.2) - g.cam.pos[1], bz - g.cam.pos[2]
        g.cam.yaw = math.atan2(dx, dz)
        g.cam.pitch = math.atan2(dy, math.hypot(dx, dz))
        hs_b = g.headshots
        if t0.is_hit(g.cam):
            g.shoot()
            # อาจ headshot ถ้าหัวคลุม — แค่ยืนยันว่าไม่ crash และนับ hit
    g.S["headshots"] = False   # คืนค่าเริ่มต้น

    # --- SPRAY (vandal + phantom) ---
    for wp in ("vandal", "phantom"):
        g.spray_weapon = wp
        g.mode = "spray"
        g.duration = 15
        g.start_countdown()
        g.begin_play()
        if not g.targets:
            errors.append(f"spray({wp}): no bot spawned")
        # เล็งลำตัวแล้วกดยิงค้าง — จำลองผู้เล่นดึงสวนรีคอยล์ลงทุกเฟรม
        for i in range(360):
            if g.state != "play":
                break
            if g.targets:
                # ดึงสวน: เล็งลำตัวใหม่ทุกเฟรม (หักล้าง recoil)
                aim_at(g, g.targets[0])
            g.spray_firing = (i % 80 < 50)   # ยิงเป็นชุด
            if g.spray_firing and g.spray_next_shot == 0.0:
                g.spray_next_shot = g.gt
            g.update_play(1 / 60)
        play_round_left = 1200
        g.spray_firing = False
        for _ in range(1200):
            if g.state != "play":
                break
            g.update_play(1 / 60)
        if g.state != "results":
            errors.append(f"spray({wp}): did not reach results (state={g.state})")
        if g.spray_shots == 0:
            errors.append(f"spray({wp}): no bullets fired")
        if g.spray_onbody == 0:
            errors.append(f"spray({wp}): no bullets on target")
        if g.spray_onbody > 0 and g.score == 0:
            errors.append(f"spray({wp}): score stayed 0 despite on-target hits")
        if g.last_entry.get("mode") != "spray" or g.last_entry.get("variant") != wp:
            errors.append(f"spray({wp}): history entry wrong")
    # recoil ต้องสะสมเมื่อยิงโดยไม่ดึงสวน แล้วฟื้นเมื่อปล่อย
    g.spray_weapon = "vandal"
    g.mode = "spray"
    g.start_countdown(); g.begin_play()
    g.cam.pitch = 0.0
    g.spray_firing = True
    g.spray_next_shot = g.gt
    for _ in range(20):
        g.update_play(1 / 60)
    if g.recoil_pitch <= 0:
        errors.append("spray recoil pitch did not accumulate")
    peak = g.recoil_pitch
    g.spray_firing = False
    for _ in range(120):
        g.update_play(1 / 60)
    if g.recoil_pitch >= peak:
        errors.append("spray recoil did not recover after release")
    # reload-burst regression: ถือปุ่มค้างผ่านรีโหลด — เฟรมที่รีโหลดจบต้องยิงได้ไม่เกิน 1 นัด
    # (บั๊กเดิม: spray_next_shot ค้างที่เวลาแม็กหมด ลูปตามเก็บ ~11 นัดในเฟรมเดียว คะแนนเฟ้อ ~42%)
    g.spray_weapon = "vandal"
    g.mode = "spray"
    g.duration = 30
    g.start_countdown(); g.begin_play()
    g.spray_firing = True
    g.spray_next_shot = g.gt
    burst_max, seen_reload = 0, False
    for _ in range(600):            # 10 วิ: แม็ก 25 นัดหมดใน ~2.6 วิ + รีโหลด 1.2 วิ + ยิงต่อ
        if g.state != "play":
            break
        if g.targets:
            aim_at(g, g.targets[0])
        was_reloading = g.spray_reloading_until > 0
        before = g.spray_shots
        g.update_play(1 / 60)
        if was_reloading and g.spray_reloading_until == 0.0:
            seen_reload = True
            burst_max = max(burst_max, g.spray_shots - before)
    if not seen_reload:
        errors.append("spray: reload never completed within 10s")
    elif burst_max > 1:
        errors.append(f"spray reload-burst regression: {burst_max} shots in the frame reload ended")
    g.spray_firing = False
    g.end_game()
    if g.last_entry.get("mode") == "spray" and g.last_entry.get("srev") != SPRAY_SCORE_REV:
        errors.append("spray history entry missing current srev")

    # --- DODGE ---
    from . import guns as _gn

    dodge_want = [False]

    def dodge_act(i):
        # เดินหลบสลับซ้ายขวา + ถึงรอบยิงแล้ว counter-strafe จนเข้า deadzone ก่อน flick ยิงหัว (dodge rev 2 วิ่งยิงกระจาย 6°)
        if g.targets and i % 30 == 0:
            dodge_want[0] = True
        if dodge_want[0] and not _gn.is_accurate(STRAFE_WEAPON, g.strafe_speed()):
            g.keys_down = {"a"} if g.vel[0] * math.cos(g.cam.yaw) - g.vel[1] * math.sin(g.cam.yaw) > 0 else {"d"}
            return
        g.keys_down = {"d"} if i % 50 < 25 else {"a"}
        if dodge_want[0] and g.targets:
            dodge_want[0] = False
            aim_head(g, g.targets[0])
            g.shoot()
    play_round("dodge", 900, dodge_act)
    if g.state != "results":
        errors.append(f"dodge: did not reach results (state={g.state})")
    if g.dodge_total_haz == 0:
        errors.append("dodge: no hazards spawned")
    if g.hits == 0:
        errors.append("dodge: no kills")
    if g.headshots == 0:
        errors.append("dodge: no headshots despite aiming head")
    # hazard lifecycle: telegraph→active→resolve ต้องเพิ่ม dodged หรือ HP ลด
    if g.dodge_dodged == 0 and g.dodge_hp == DODGE_HP_MAX:
        errors.append("dodge: no hazard resolved (neither dodged nor hit)")
    # จุดเกิด hazard (2026-09-07): molly ตกข้างหน้าเสมอและผู้เล่นยังอยู่ในวง / ลูกพุ่งเวลาบินคงที่ทุกตำแหน่งยืน
    for pz0 in (-2.0, 0.0, 3.0):
        g.mode = "dodge"
        g.start_countdown(); g.begin_play()
        g.cam.pos[0], g.cam.pos[2] = 0.0, pz0
        g.dodge_hazards = []
        for _ in range(60):
            g.spawn_dodge_hazard()
        kinds = {h["kind"] for h in g.dodge_hazards}
        if kinds != {"proj", "aoe", "beam"}:
            errors.append(f"dodge spawn: kinds seen {kinds}")
        for h in g.dodge_hazards:
            if h["kind"] == "aoe":
                d = math.hypot(h["cx"] - 0.0, h["cz"] - pz0)
                if d >= DODGE_AOE_R:
                    errors.append(f"dodge aoe: player outside ring at spawn (d={d:.2f}, pz={pz0})")
                if pz0 <= 1.5 and not (DODGE_AOE_AHEAD[0] - 1e-9 <= h["cz"] - pz0 <= DODGE_AOE_AHEAD[1] + 1e-9):
                    errors.append(f"dodge aoe: not ahead of player (dz={h['cz'] - pz0:.2f}, pz={pz0})")
            elif h["kind"] == "proj":
                t = (h["z"] - pz0) / h["speed"]
                if abs(t - DODGE_PROJ_FLIGHT) > 1e-6:
                    errors.append(f"dodge proj: flight time {t:.3f}s != {DODGE_PROJ_FLIGHT} (pz={pz0})")
            elif h["kind"] == "beam":
                # BEAM (2026-09-23): เริ่มนอกขอบโซนแล้วกวาด "เข้า" หาเส้นหยุดที่เลยตัวผู้เล่นไปทางกลาง — เดิมวิ่งออกนอกสนาม
                inward = (h["stop_x"] - h["beam_x"]) * h["dir"] > 0
                past = (0.0 - h["stop_x"]) * h["dir"] < 0 and abs(h["stop_x"]) <= DODGE_ZONE_X
                if not inward or abs(h["beam_x"]) < DODGE_ZONE_X or not past:
                    errors.append(f"dodge beam: must enter from the edge and stop past the player "
                                  f"(x={h['beam_x']:.2f} stop={h['stop_x']:.2f} dir={h['dir']})")
        # วาด telegraph ทุกชนิดได้ทั้งช่วง warn และ active (headless surface) — ต้องไม่ throw
        try:
            g.draw_world(); g.draw_hud()
            g.gt += DODGE_TELEGRAPH + 0.05
            g.update_play(1 / 60)
            g.draw_world(); g.draw_hud()
        except Exception as ex:
            errors.append(f"dodge draw with hazards failed: {type(ex).__name__}: {ex}")
        g.dodge_hazards = []

    # --- PLACEMENT ---
    def place_act(i):
        if g.targets:
            aim_head(g, g.targets[0])
            g.shoot()
    play_round("placement", 900, place_act)
    if g.state != "results":
        errors.append(f"placement: did not reach results (state={g.state})")
    if g.hits == 0:
        errors.append("placement: no kills")
    if not g.placement_preaim:
        errors.append("placement: pre-aim error not recorded")
    # มิสในโหมด placement: เล็งออกนอกจอแล้วยิง
    g.mode = "placement"
    g.start_countdown(); g.begin_play()
    for _ in range(60):
        g.update_play(1 / 60)
        if g.targets:
            break
    if g.targets:
        g.cam.yaw = g.cam.yaw + math.pi   # หันหลังให้เป้า
        m0 = g.misses
        g.shoot()
        if g.misses != m0 + 1:
            errors.append("placement: miss not counted")

    # --- SWITCH ---
    def switch_act(i):
        if g.targets:
            aim_at(g, g.targets[0])
            g.shoot()
    play_round("switch", 1200, switch_act)
    if g.state != "results":
        errors.append(f"switch: did not reach results (state={g.state})")
    if g.hits == 0:
        errors.append("switch: no kills")
    if g.switch_waves_cleared == 0:
        errors.append("switch: no wave cleared")
    if not g.switch_kill_times:
        errors.append("switch: switch-time not recorded")

    # ───────── แกน realism (2026-09-23) ─────────
    errors += realism_selftest(g, aim_at, aim_head)

    # results/HUD/radar ของทุกโหมดใหม่ต้องวาดได้ไม่ crash
    for md in ("spray", "dodge", "placement", "switch"):
        g.mode = md
        g.start_countdown(); g.begin_play()
        for _ in range(40):
            if g.state != "play":
                break
            if g.targets and md != "spray":
                aim_at(g, g.targets[0]); g.shoot()
            g.update_play(1 / 60)
        g.end_game()
        g.zones = []
        try:
            g.draw_results()
        except Exception as ex:
            errors.append(f"draw_results {md}: {type(ex).__name__}: {ex}")
        g.state = "play"; g.zones = []
        try:
            g.draw_world(); g.draw_hud()
        except Exception as ex:
            errors.append(f"draw play {md}: {type(ex).__name__}: {ex}")
        if g.results_radar_axes() is None:
            errors.append(f"{md}: radar axes missing")
        # ตรวจ history มีฟิลด์ hs
        if "hs" not in g.last_entry:
            errors.append(f"{md}: history missing 'hs' field")
        # ทุก entry ใหม่มี mrev = กติการุ่นปัจจุบันของโหมด (config.MODE_REV) — PB/leaderboard/dashboard ใช้แยกรอบเก่า
        if g.last_entry.get("mrev") != MODE_REV.get(md, 1) or not mode_current(g.last_entry):
            errors.append(f"{md}: history entry mrev {g.last_entry.get('mrev')} != MODE_REV {MODE_REV.get(md, 1)}")

    # menu เลือกโหมดด้วยเลข 1-9,0 (10 โหมด) — จำลอง handle_key
    # ── GUNFIGHT: กติกาปืนตรงตารางเกม + ดริลทั้ง 4 จบรอบได้ ──
    from . import guns as _guns
    stk = {("vandal", "head", 10): 1, ("vandal", "body", 10): 4, ("vandal", "leg", 10): 5,
           ("phantom", "head", 10): 1, ("phantom", "head", 30): 2, ("phantom", "body", 30): 5,
           ("sheriff", "body", 10): 3, ("sheriff", "leg", 10): 4, ("sheriff", "head", 40): 2,
           ("sheriff", "body", 40): 3,                          # 3×50 = 150 พอดี (ต้องตาย — ปัดทศนิยม apply_damage)
           ("operator", "body", 30): 1, ("operator", "leg", 30): 2,
           # ปืนสั้นใหม่ vs เกราะหนัก (บอททุกตัว): Ghost 1 หัวไม่พอ (105 < 150) — 2 หัว / 5 ตัว (5×30 = 150 พอดี)
           ("ghost", "head", 10): 2, ("ghost", "body", 10): 5, ("ghost", "leg", 10): 6,
           ("ghost", "head", 40): 2, ("ghost", "body", 40): 6, ("ghost", "leg", 40): 8,
           ("classic", "head", 10): 2, ("classic", "body", 10): 6, ("classic", "leg", 10): 7,
           ("classic", "head", 40): 3, ("classic", "body", 40): 7, ("classic", "leg", 40): 9}
    for (wp, zone, dist), want in stk.items():
        got = _guns.shots_to_kill(wp, zone, dist)
        if got != want:
            errors.append(f"gun: {wp} {zone} {dist}m = {got} shots (game says {want})")
    # ไม่ใส่เกราะ (รอบปืนสั้นจริง): Ghost หัวเดียวจบ ≤30 ม. / 4 ตัว, Classic 2 หัว / 4 ตัว, Sheriff 1 หัวทุกระยะ
    # เกราะเบา 25: Ghost/Classic 2 หัว / 5 ตัว
    for (wp, zone, dist, sh), want in {("ghost", "head", 10, 0): 1, ("ghost", "body", 10, 0): 4,
                                       ("ghost", "head", 40, 0): 2, ("classic", "head", 10, 0): 2,
                                       ("classic", "body", 10, 0): 4, ("sheriff", "head", 40, 0): 1,
                                       ("ghost", "head", 10, 25): 2, ("ghost", "body", 10, 25): 5,
                                       ("classic", "head", 10, 25): 2, ("classic", "body", 10, 25): 5}.items():
        got = _guns.shots_to_kill(wp, zone, dist, shield=sh)
        if got != want:
            errors.append(f"gun: {wp} {zone} {dist}m shield {sh} = {got} shots (game says {want})")
    # ชุดผสมที่รวมพอดี/เฉียด 150: Phantom ≤20 ม. 3 ตัว + 1 ขา (39·3 + 33.15) ต้องตาย ; Sheriff 1 ตัว + 2 ขา ไม่ตาย
    for wp, zones, dead in (("phantom", ("body", "body", "body", "leg"), True),
                            ("sheriff", ("body", "leg", "leg"), False),
                            ("ghost", ("head", "body", "body"), True)):          # 105 + 30 + 30 = 165
        hp, sh = _guns.PLAYER_HP, _guns.PLAYER_SHIELD
        for z in zones:
            hp, sh = _guns.apply_damage(hp, sh, _guns.damage_for(wp, z, 10))
        if (hp <= 0) != dead:
            errors.append(f"gun: {wp} {'+'.join(zones)} ต้อง{'ตาย' if dead else 'รอด'} (เหลือ HP {hp})")
    if _guns.spread_deg("operator", 2.5, 0.0, False, 0.0) != 0.0:
        errors.append("gun: scoped Op standing still must be 0° spread")
    if _guns.spread_deg("operator", 1.0, 0.0, False, 0.0) < 4.5:
        errors.append("gun: hipfire Op must be ~5° spread")
    if not (_guns.spread_deg("vandal", 1.0, 5.0, False, 0.0) > _guns.spread_deg("vandal", 1.0, 2.0, False, 0.0)
            > _guns.spread_deg("vandal", 1.0, 0.0, False, 0.0)):
        errors.append("gun: spread must grow stand < walk < run")
    if abs(_guns.zoom_sens_mult(2.5) - 0.4) > 1e-9 or _guns.zoom_sens_mult(1.0) != 1.0:
        errors.append("gun: zoom sens multiplier must scale 1/zoom")
    from .camera import Camera as _Cam
    cam0 = _Cam()
    bot0 = _guns.Bot(0.0, 20.0)
    cam0.pitch = math.atan2(_guns.HEAD_Y - cam0.pos[1], 20.0)
    if bot0.hit_zone(cam0) != "head":
        errors.append("gun: aiming at head center must register head")
    cam0.pitch = math.atan2(1.2 - cam0.pos[1], 20.0)
    if bot0.hit_zone(cam0) != "body":
        errors.append("gun: aiming at chest must register body")
    cam0.pitch = math.atan2(2.2 - cam0.pos[1], 20.0)
    if bot0.hit_zone(cam0) is not None:
        errors.append("gun: aiming above head must miss")
    # ลำตัวปลายตัดที่ BODY_Y1 (ไม่ใช่แคปซูลโดมสูงถึง 1.68 ม.): นัดเฉียดข้างหัวที่ระดับหัว = พลาด ไม่ใช่ body 40
    # (เดิม 0.15 ม. ข้างศูนย์หัวที่ 20 ม. = body) ; ขอบลำตัวใต้ไหล่ยังโดนตามปกติ
    for (lat, yy), want in {(0.10, _guns.HEAD_Y): "head", (0.13, _guns.HEAD_Y): "head",
                            (0.15, _guns.HEAD_Y): None, (0.17, _guns.HEAD_Y): None, (0.20, 1.52): None,
                            (0.20, 1.40): "body", (0.20, 1.2): "body", (0.0, 1.0): "body",
                            (0.25, 1.2): None}.items():
        cam0.yaw = math.atan2(lat, 20.0)
        cam0.pitch = math.atan2(yy - cam0.pos[1], math.hypot(lat, 20.0))
        got = bot0.hit_zone(cam0)
        if got != want:
            errors.append(f"gun hitbox: {lat} m ข้าง / สูง {yy} m ที่ 20 m ได้ {got} (ต้อง {want})")
    cam0.yaw = 0.0

    def _aim_bot(b, y):
        dx, dz = b.x - g.cam.pos[0], b.z - g.cam.pos[2]
        g.cam.yaw = math.atan2(dx, dz)
        g.cam.pitch = math.atan2(y - g.cam.pos[1], math.hypot(dx, dz))
        # "เล็งสมบูรณ์" รวมดึงสวนรีคอยล์: หัก pattern offset ของนัดถัดไปออก (สิ่งที่ผู้เล่นเก่งทำ)
        st = g.gun_stab
        st.update(g.gt)
        g.cam.pitch -= math.radians(st.pitch_off)
        g.cam.yaw -= math.radians(st.yaw_off)
    import random as _rnd
    from .gunplay import drills_for as _drills_for
    from . import arena as _arena
    _rnd.seed(20260911)          # บอท hold สุ่ม peek/jiggle — ล็อก seed ให้เทสต์ทำซ้ำได้
    for wp in _guns.WEAPON_ORDER:
        for drill in _drills_for(wp):            # Ghost/Classic ไม่มี OP HOLD (guns.WEAPON_DRILLS)
            g.mode = "gun"; g.gun_weapon = wp; g.gun_drill = drill; g.duration = 15
            g.start_countdown(); g.begin_play()
            fr = 0
            while g.state == "play" and fr < 60 * 25:
                fr += 1
                live = [b for b in g.bots if b.alive and b.exposed]
                if live:
                    # ยิงหัว (ตามท่าบอท — บางตัวหมอบตอนเริ่มยิง) เฉพาะตอนแนวยิงไม่ติดที่กำบัง — บอท v2 โผล่จากมุม
                    # ยิงใส่ไหล่ที่เพิ่งโผล่ = ยิงกำแพง ; "เล็งสมบูรณ์" จึงรอหัวพ้นขอบก่อน (Sheriff/Ghost ต้องหัว ตัวช้าเกิน)
                    lb = live[0]
                    aim_pt = (lb.x, lb.head_y(), lb.z)
                    _aim_bot(lb, aim_pt[1])
                    if wp == "operator" and g.gun_zoom == 1.0:
                        g.gun_rmb(True)
                    # ปืนสั้น: คนเล็งสมบูรณ์แตะเมื่อสเปรดฟื้นเป็นนัดแรกแล้ว (รัว Classic/Ghost สเปรดโต 0.4→1.8° = วัดดวง)
                    w = _guns.WEAPONS[wp]
                    ready = w["kind"] != "pistol" or g.gun_stab.spread(g.gt) <= w["spread"]["stand"] + 1e-6
                    # คนเล็งสมบูรณ์ยิงเมื่อนิ่งใน deadzone แล้ว (PEEK: เพิ่งปล่อยปุ่มหลังโผล่ — Op หลุด deadzone 15% ง่าย)
                    ready = ready and _guns.is_accurate(wp, g.gun_speed())
                    if fr % 3 == 0 and ready and not _arena.segment_blocked(tuple(g.cam.pos), aim_pt, g.gun_covers):
                        g.shoot()
                if drill == "repo" and g.gun_repo_deadline is not None:
                    g.keys_down.add("a")
                elif drill == "peek":
                    # PEEK & STOP: ต้องโผล่เองจากหลังกำแพง (กดทิศไปทางขอบ) จนเห็นบอท แล้วปล่อยปุ่มให้เบรกก่อนยิง
                    g.cam.yaw = 0.0 if not live else g.cam.yaw
                    g.keys_down = {g.gun_peek_key()} if (g.bots and not live) else set()
                else:
                    g.keys_down.discard("a")
                g.update_play(1 / 60)
            if g.state != "results":
                errors.append(f"gun {wp}/{drill}: round did not end")
                continue
            if g.gun_kills == 0 and drill != "repo":
                errors.append(f"gun {wp}/{drill}: no kills with perfect aim")
            e = g.last_entry
            if e.get("mode") != "gun" or e.get("variant") != wp or e.get("drill") != drill:
                errors.append(f"gun {wp}/{drill}: history entry missing weapon/drill")
            g.draw_results()
    # fire-rate cap: Op ยิงถี่กว่า 0.6 นัด/วิ ไม่ได้ ; วงจรรีโหลดต้องเติมแม็ก
    g.mode = "gun"; g.gun_weapon = "operator"; g.gun_drill = "duel"; g.duration = 15
    g.start_countdown(); g.begin_play()
    for _ in range(60):
        g.update_play(1 / 60)
    g.bots = []; g.gun_next_bot_at = None      # เทสต์กลไกปืนล้วน — ไม่ให้บอทยิงสวนจนตายกลางเทสต์
    for _ in range(10):
        g.shoot()
    if g.gun_shots != 1:
        errors.append(f"gun: Op fire-rate cap broken ({g.gun_shots} shots in one frame)")
    g.gun_mag = 0
    g.shoot()                          # แม็กหมด → เริ่มรีโหลดเอง
    if g.gun_reload_until <= 0:
        errors.append("gun: empty mag did not start reload")
    for _ in range(int(60 * 3.8)):
        g.update_play(1 / 60)
    if g.gun_mag != _guns.WEAPONS["operator"]["mag"]:
        errors.append("gun: reload did not refill magazine")
    # สโคป Op: RMB วน 2.5 → 5 → ออก และยิงแล้วหลุดสโคป
    g.gun_rmb(True)
    if g.gun_zoom != 2.5:
        errors.append("gun: first RMB must scope 2.5x")
    g.gun_rmb(True)
    if g.gun_zoom != 5.0:
        errors.append("gun: second RMB must scope 5x")
    g.gun_rmb(True)
    if g.gun_zoom != 1.0:
        errors.append("gun: third RMB must unscope")
    g.gun_rmb(True)
    g.gun_last_shot = -9.0
    g.gun_next_shot_at = 0.0           # ข้าม fire-rate gate (ตารางเวลานัดถัดไป — ดู gunplay.gun_shoot)
    g.shoot()
    if g.gun_zoom != 1.0:
        errors.append("gun: Op must unscope after firing")
    # รีคอยล์แบบเกมจริง (stability.py): ไรเฟิลกดค้าง 10 นัด — crosshair ต้อง "ไม่ขยับ" แต่ pattern offset
    # ต้องไต่ตามเส้นโค้ง PitchRecoil ของ Vandal ในไฟล์เกม (~7.5° ที่นัด 10) แล้วรีเซ็ตใน ~0.4 วิหลังปล่อย
    from .stability import curve_at as _cat, pattern_table as _ptab, Stability as _StCls
    from .riot_data import RIOT as _RIOT
    Stability_shot_dir = _StCls.shot_dir
    g.mode = "gun"; g.gun_weapon = "vandal"; g.gun_drill = "duel"; g.duration = 15
    g.start_countdown(); g.begin_play()
    for _ in range(60):
        g.update_play(1 / 60)
    g.bots = []; g.gun_next_bot_at = None
    p0 = g.cam.pitch
    g.gun_firing = True
    fr = 0
    while g.gun_shots < 10 and fr < 240:
        g.update_play(1 / 60); fr += 1
    g.gun_firing = False
    if abs(math.degrees(g.cam.pitch - p0)) > 1e-6:
        errors.append("gun: crosshair must stay put while spraying (Valorant recoil is a bullet pattern, not camera kick)")
    expect = _cat(_RIOT["vandal"]["stability"]["pitch"], 9)
    off = g.gun_stab.pitch_off
    if not (expect * 0.9 <= off <= expect * 1.1):
        errors.append(f"gun: vandal pattern offset after 10 shots {off:.2f}° (riot curve says {expect:.2f}°)")
    for _ in range(int(60 * 0.6)):
        g.update_play(1 / 60)
    if g.gun_stab.pitch_off > 1e-6 or g.recoil_pitch < 0:
        errors.append(f"gun: pattern did not reset 0.6s after release ({g.gun_stab.pitch_off:.2f}° left)")
    # ตารางเส้นโค้ง: นัด 8 ของ Vandal = 7.6° ตรงไฟล์เกม, ADS ×0.7
    pt = _ptab("vandal", 8)
    if abs(pt[-1][1] - 7.6) > 1e-6 or abs(_ptab("vandal", 8, ads=True)[-1][1] - 7.6 * 0.7) > 1e-6:
        errors.append(f"stability: vandal pattern table wrong ({pt[-1]})")
    # ไม่ดึงสวน = นัดหลังๆ ข้ามหัวบอทไป / ดึงสวนเท่า pattern = กลับมาโดน
    from .guns import Bot as _B
    g.gun_stab.reset()
    bot = _B(0.0, g.cam.pos[2] + 12.0)
    g.cam.yaw = 0.0
    hx, hy, hz = g.cam.to_cam((bot.x, _guns.BODY_Y1 - 0.2, bot.z))
    g.cam.pitch = math.atan2(hy, math.hypot(hx, hz))     # เล็งอก
    import random as _rnd_st
    _rnd_st.seed(11)
    hits_static = 0; hits_pulled = 0
    t = g.gt
    for i in range(8):
        po, yo, sp = g.gun_stab.shoot(t + i / 9.75)
        d = Stability_shot_dir(po, yo, 0.0)
        if bot.hit_zone(g.cam, d):
            hits_static += 1
        # ดึงสวน: ทิศกระสุนที่หักล้าง pattern แล้ว = ตรงอก
        if bot.hit_zone(g.cam, Stability_shot_dir(0.0, 0.0, 0.0)):
            hits_pulled += 1
    if hits_static >= 7:
        errors.append(f"stability: spraying without pulling down should climb off the body ({hits_static}/8 hit)")
    if hits_pulled != 8:
        errors.append(f"stability: pulled-down spray must stay on body ({hits_pulled}/8)")
    # Sheriff: กล้อง 'เด้ง' ที่ตาเห็น ≥1.5° ในเฟรมถัดจากนัด (pop 8°×0.5 + ตามรีคอยล์ 80%) แล้วคืนภายใน 0.6 วิ
    g.gun_weapon = "sheriff"; g.start_countdown(); g.begin_play()
    for _ in range(60):
        g.update_play(1 / 60)
    g.bots = []; g.gun_next_bot_at = None
    p0 = g.cam.pitch
    g.shoot()
    g.update_play(1 / 60)
    vo = math.degrees(g.gun_view_offset()[0])
    if vo < 1.5:
        errors.append(f"gun: Sheriff visual kick {vo:.2f}° (< 1.5°) one frame after the shot")
    if abs(g.cam.pitch - p0) > 1e-9:
        errors.append("gun: Sheriff kick must be visual only (aim direction unchanged)")
    for _ in range(40):
        g.update_play(1 / 60)
    if abs(math.degrees(g.gun_view_offset()[0])) > 0.05:
        errors.append("gun: Sheriff visual kick did not settle within 0.6s")
    # กติกาสเปรด/ฟื้นจากตาราง Riot
    from .stability import Stability as _St
    s = _St("vandal", 9.75)
    if abs(s.shoot(0.0, ads=True)[2] - 0.1575) > 1e-6:
        errors.append("stability: vandal ADS first bullet must be 0.1575° (0.25×1.15−0.13)")
    s = _St("vandal", 9.75); tt = 0.0; taps = []
    for _ in range(5):
        tt += 0.25; taps.append(round(s.shoot(tt)[2], 4))
    if any(v != 0.25 for v in taps):
        errors.append(f"stability: vandal tapped at 4/s must stay first-bullet accurate {taps}")
    s = _St("sheriff", 4.0); tt = 0.0; spam = []
    for _ in range(3):
        tt += 0.25; spam.append(round(s.shoot(tt)[2], 3))
    if spam != [0.25, 1.1, 2.75]:
        errors.append(f"stability: sheriff spam spread must be 0.25→1.1→2.75 got {spam}")
    s = _St("operator", 0.6)
    a = s.shoot(0.0, zoomed=True)[2]; b = s.spread(0.05, zoomed=True); c = s.spread(1.0, zoomed=True)
    if a != 0.0 or abs(b - 1.0) > 1e-6 or c != 0.0:
        errors.append(f"stability: Op scoped spread first 0 / right after 1.0 / reset later — got {a},{b},{c}")
    if abs(_St("operator", 0.6).spread(0.0) - 5.0) > 1e-6:
        errors.append("stability: Op hipfire spread must be 5°")
    # หน้าเว็บ/ระบบอื่นยังอ้าง sniper ได้ (โหมด legacy นอกกริดเมนู)
    if "sniper" not in MODE_NAME or MODES[5][0] != "gun":
        errors.append("gun: MODES[5] must be gun and sniper must stay in MODE_NAME")

    class _Ev:
        def __init__(s, key, uni=""):
            s.key = key; s.unicode = uni
    g.state = "menu"
    g.handle_key(_Ev(pygame.K_7))   # โหมดที่ 7 = spray
    if g.mode != MODES[6][0]:
        errors.append("menu key 7 did not select 7th mode")
    g.handle_key(_Ev(pygame.K_0))   # โหมดที่ 10 = switch
    if g.mode != MODES[9][0]:
        errors.append("menu key 0 did not select 10th mode")
    g.handle_key(_Ev(pygame.K_1))
    if g.mode != MODES[0][0]:
        errors.append("menu key 1 did not select 1st mode")
    if len(MODES) != 10:
        errors.append(f"expected 10 modes, got {len(MODES)}")

    # วาดทุกหน้า
    for state, fn in [("menu", g.draw_menu), ("settings", g.draw_settings), ("ranks", g.draw_ranks),
                      ("insight", g.draw_insight), ("results", g.draw_results), ("pause", g.draw_pause),
                      ("countdown", g.draw_countdown)]:
        g.state = state
        g.zones = []
        g.sliders = {}
        try:
            fn()
        except Exception as ex:
            errors.append(f"draw {state}: {type(ex).__name__}: {ex}")
    # insight ทุกแท็บ (รวมโหมดใหม่)
    for tb in ["flick", "precision", "tracking", "reaction-static", "reaction-flick", "reaction-peek", "strafe",
               "sniper", "spray", "dodge", "placement", "switch"]:
        g.insight_tab = tb
        g.zones = []
        try:
            g.draw_insight()
        except Exception as ex:
            errors.append(f"insight {tb}: {type(ex).__name__}: {ex}")
    # save score + rank logic
    # ทดสอบลาก slider (บั๊กเดิม: sliders ถูกเคลียร์ก่อน event)
    g.state = "settings"
    g.zones = []
    g.draw_settings()
    g.drag = "sens"
    r, lo, hi, step, obj, key = g.sliders["sens"]
    g.drag_slider(r.x + r.w)
    if abs(obj[key] - hi) > 1e-6:
        errors.append(f"slider drag failed: {obj[key]} != {hi}")
    g.drag_slider(r.x)
    if abs(obj[key] - lo) > 1e-6:
        errors.append(f"slider drag to min failed: {obj[key]} != {lo}")
    g.drag = None
    obj[key] = 0.4
    try:
        g.toggle_fullscreen()
        g.toggle_fullscreen()
    except Exception as ex:
        errors.append(f"fullscreen toggle: {ex}")
    # HUD scale ทุกขนาดจอ + capture_screen
    for ww, hh in [(900, 560), (1280, 720), (2560, 1440)]:
        g.W, g.H = ww, hh
        g.screen = pygame.Surface((ww, hh))
        g.state = "play"
        g.mode = "flick"
        g.zones = []
        try:
            g.draw_hud()
        except Exception as ex:
            errors.append(f"draw_hud {ww}x{hh}: {type(ex).__name__}: {ex}")
        try:
            g.draw_results()
        except Exception as ex:
            errors.append(f"draw_results {ww}x{hh}: {type(ex).__name__}: {ex}")
    g.shot_saved_until = 0
    g.capture_screen()
    if g.shot_saved_until <= pygame.time.get_ticks():
        errors.append("capture_screen did not set confirmation")
    # rank emblem ทุกเทียร์ + parse
    if parse_rank("Gold III") != ("Gold", 3) or parse_rank("Radiant") != ("Radiant", 0):
        errors.append("parse_rank wrong")
    for rn in ["Iron I", "Bronze II", "Silver III", "Gold I", "Platinum II",
               "Diamond III", "Ascendant I", "Immortal", "Radiant", "TRAINING"]:
        try:
            g.draw_rank_emblem(60, 60, 30, rn, "#D4AF37")
        except Exception as ex:
            errors.append(f"emblem {rn}: {type(ex).__name__}: {ex}")
    import glob as _glob
    for _p in _glob.glob(os.path.join(os.path.dirname(DATA_FILE), "valaim_*.png")):
        try:
            os.remove(_p)
        except Exception:
            pass
    # พิมพ์ค่า sens ละเอียด 3 ตำแหน่ง (0.315) ได้
    g.text_focus = "sens"
    g.sens_text = "0.315"
    g.commit_sens()
    if abs(g.S["sens"] - 0.315) > 1e-9:
        errors.append(f"sens text input failed: {g.S['sens']}")
    g.S["sens"] = 0.4

    # ── unit test ของ export (Module 5) — hook ตรงนี้เพราะต้องมี Game + DATA_FILE
    #    ถูก redirect ไป temp แล้ว (argv-gate แบบ benchmark/sensitivity ใช้ไม่ได้:
    #    ตอน import ยังสร้าง Game ไม่ได้ และไฟล์ data ยังชี้ไปของจริง) ──
    from . import export as _export
    errors += _export.selftest(g)

    # ── unit test แผนซ้อม/คิววอร์ม (cfg lock + base restore + hardening) — pure logic
    #    ใช้ไฟล์ temp ของตัวเอง ไม่แตะ train_plan.json จริง (plan.register ตอนสร้าง Game
    #    อ่านไฟล์จริงแบบ read-only อยู่แล้ว ไม่เกี่ยวกัน) ──
    from . import plan as _plan
    errors += _plan.selftest()
    # ── routine (ลำดับสลับข้อ deterministic ตาม seed, แท็ก, ทำแล้ววันนี้, ความยากปรับเอง, วันซ้อม) + latency — pure ──
    from . import routine as _routine, latency as _latency
    errors += _routine.selftest()
    errors += _latency.selftest()
    # ── การ์ด "วันนี้" + เมนู/หน้าผลตาม ui_scale: ทุก zone อยู่ในจอ ไม่ทับกัน ที่ 900×560 / 1280×720 / 2560×1440
    #    (ไฟล์แผน temp ของตัวเอง — plan.PLAN_FILE คืนค่าเดิมเสมอ) ──
    import json as _json
    import tempfile as _tf
    import time as _time
    _pf_orig = _plan.PLAN_FILE
    _fd, _pf = _tf.mkstemp(suffix=".json")
    os.close(_fd)
    W0, H0, scr0 = g.W, g.H, g.screen
    try:
        with open(_pf, "w", encoding="utf-8") as f:
            _json.dump({"updated": _time.time(), "v": 2, "plan": [], "lever": {"title": "ตายให้ Op บ่อย"},
                        "routine": {"id": "r-selftest", "items": [
                            {"id": "w1", "phase": "warm", "mode": "flick", "rounds": 1,
                             "cfg": {"duration": 15, "size": "medium"}},
                            {"id": "b1", "phase": "block", "mode": "gun", "variant": "vandal", "rounds": 2,
                             "cfg": {"duration": 15, "size": "medium", "drill": "peek"}, "why": "พีคแล้วหยุดก่อนยิง"},
                            {"id": "m1", "phase": "maint", "mode": "placement", "rounds": 1, "target": "Diamond II",
                             "cfg": {"duration": 15, "size": "medium"}, "why": "คงฟอร์ม"}]}}, f)
        _plan.PLAN_FILE = _pf
        _plan.refresh(force=True)
        for ww, hh in ((900, 560), (1280, 720), (2560, 1440)):
            g.W, g.H = ww, hh
            g.screen = pygame.Surface((ww, hh))
            scr_r = pygame.Rect(0, 0, ww, hh)
            for md in ("flick", "gun"):
                g.state, g.mode, g.zones = "menu", md, []
                g.draw_menu()
                zs = [z for z, _f in g.zones]
                if not all(scr_r.contains(z) for z in zs) or \
                        any(a.colliderect(b) for i, a in enumerate(zs) for b in zs[i + 1:]):
                    errors.append(f"menu {ww}x{hh} {md}: zone ล้นจอ/ทับกัน")
        g.W, g.H = 1280, 720
        g.screen = pygame.Surface((1280, 720))
        _plan.start_warmup(g)                   # routine: รอบแรก = วอร์ม ; หน้าผลมีบรรทัด ข้อ k/n + ปุ่ม NEXT
        g.begin_play(); g.end_game(); g.zones = []
        g.draw_results()
        if not g.plan_queue or _plan.next_info(g) is None or not (_plan.result_lines(g) or ("",))[0].startswith(
                "ROUTINE · ข้อ 1/3"):
            errors.append(f"results routine: ไม่มีบรรทัดข้อ/ปุ่ม NEXT ({_plan.result_lines(g)})")
        g.plan_queue = []
        g.data["history"] = [e for e in g.data["history"] if e.get("rid") != "r-selftest"]
    except Exception as ex:
        import traceback
        errors.append(f"menu/results scale: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    finally:
        g.W, g.H, g.screen = W0, H0, scr0
        _plan.PLAN_FILE = _pf_orig
        _plan.refresh(force=True)
        try:
            os.unlink(_pf)
        except OSError:
            pass

    # ── GUNFIGHT กลไกล้วน (fake game — รีวิว 11 ก.ย. 2026): fire rate ไม่ขึ้นกับ FPS/ไม่ยิงตามเก็บหลังค้าง,
    #    REPOSITION ยึด anchor นัดแรก, กำแพง hold บังกระสุนตามแนวยิง ──
    from . import gunplay as _gunplay
    errors += _gunplay.selftest()

    # ── REACTION · PEEK (reaction v2): ช่วงรอ exponential, catch trial, ตัดคลิกเดา <100 ms, หัวโผล่ 15–40° ──
    from . import reactpeek as _rpeek
    errors += _rpeek.selftest(g)
    # ผลลัพธ์/HUD/เรดาร์/การ์ดส่งออกของ reaction·peek และดริล GUNFIGHT ใหม่ต้องวาดได้ (software, หลายขนาดจอ)
    from . import export as _exp
    W0, H0, scr0 = g.W, g.H, g.screen
    try:
        for ww, hh in ((900, 560), (1920, 1080)):
            g.W, g.H = ww, hh
            g.screen = pygame.Surface((ww, hh))
            g.mode, g.reaction_variant = "reaction", "peek"
            g.start_countdown(); g.begin_play()
            for _ in range(144 * 3):
                g.update_play(1 / 144)
            g.draw_world(); g.draw_crosshair(); g.draw_hud()
            g.end_game(); g.zones = []
            g.draw_results()                    # ไม่มีคลิก = ไม่มีเรดาร์ (แบบ static/flick) — ต้องวาดได้ไม่พัง
            _exp.build_score_card(g)
            for drill in ("angle", "peek", "tap", "adad"):
                g.mode, g.gun_weapon, g.gun_drill, g.duration = "gun", "sheriff", drill, 15
                g.start_countdown(); g.begin_play()
                for _ in range(144 * 4):
                    g.gun_hp = 10 ** 6
                    g.update_play(1 / 144)
                g.draw_world(); g.draw_crosshair(); g.draw_hud()
                g.end_game(); g.zones = []
                g.draw_results()
                _exp.build_score_card(g)
                g.state, g.zones = "menu", []
                g.draw_menu()
                g.state, g.insight_tab, g.zones = "insight", "gun", []
                g.draw_insight()
    except Exception as ex:
        import traceback
        errors.append(f"draw new drills: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    finally:
        g.W, g.H, g.screen = W0, H0, scr0

    # ── ข้อความบนจอต้องไม่ทับกัน/ไม่ตกขอบ (review 2026-09-24 ที่ 2560×1440): HUD + สถานะ GUNFIGHT ทุกดริล (เดิมพิกเซล
    #    ตายตัว บรรทัดบอท/TAP ถูก 'PB …' ของ HUD ที่ขยายแล้วทับ) · เมนู GUNFIGHT/REACTION·PEEK (กติกาดริลเคยตกขอบล่าง) ──
    W0, H0, scr0, txt0 = g.W, g.H, g.screen, g.text
    pb0 = getattr(g, "pb_display", None)
    caught = []

    def _cap(s, *a, **k):
        r = txt0(s, *a, **k)
        if k.get("surf") is None and str(s).strip():
            caught.append((str(s), pygame.Rect(r)))
        return r
    try:
        g.text = _cap
        for ww, hh in ((1280, 720), (2560, 1440)):
            g.W, g.H = ww, hh
            g.screen = pygame.Surface((ww, hh))
            scr_r = pygame.Rect(0, 0, ww, hh)
            g.pb_display = "PB 1,977"
            for drill in ("duel", "hold", "quick", "repo", "angle", "peek", "tap", "adad"):
                wpn = "operator" if drill == "hold" else "vandal"
                g.mode, g.gun_weapon, g.gun_drill, g.duration = "gun", wpn, drill, 15
                g.start_countdown(); g.begin_play()
                g.update_play(1 / 144)
                caught.clear()
                g.draw_hud()
                hit = [(a[0], b[0]) for i, a in enumerate(caught) for b in caught[i + 1:] if a[1].colliderect(b[1])]
                if hit:
                    errors.append(f"gun HUD {ww}x{hh} {drill}: ข้อความทับกัน {hit[:2]}")
                g.end_game()
            for md, var in (("gun", "peek"), ("gun", "angle"), ("reaction", "peek")):
                g.state, g.mode, g.zones = "menu", md, []
                if md == "gun":
                    g.gun_weapon, g.gun_drill = "vandal", var
                else:
                    g.reaction_variant = var
                caught.clear()
                g.invalidate_panels()           # ตารางแรงค์/การ์ดต้องวาดจริง — เฟรม blit จากแคช (cached_panel) ไม่เรียก text
                g.draw_menu()
                out = [s for s, r in caught if not scr_r.contains(r)]
                if out:
                    errors.append(f"menu {ww}x{hh} {md}·{var}: ข้อความตกขอบจอ {out[:2]}")
                if md == "reaction" and not any(s.startswith("> ") and s != "> 350ms" for s, _r in caught):
                    errors.append(f"menu reaction·peek: แถว Iron I ต้องอิงขีดของ variant ไม่ใช่ '> 350ms' ตายตัว")
                if md == "gun":
                    from .gunplay import GUN_DRILL_RULE as _GR
                    if not any(s == _GR[var] for s, _r in caught):
                        errors.append(f"menu gun·{var}: ไม่มีบรรทัดกติกาดริล")
            g.state, g.mode, g.gun_drill = "countdown", "gun", "peek"
            g.countdown = 2.0
            caught.clear()
            g.draw_countdown()
            if not any("PEEK:" in s for s, _r in caught):
                errors.append(f"countdown {ww}x{hh} gun·peek: ไม่มีกติกาดริลใต้เลขนับ")
    except Exception as ex:
        import traceback
        errors.append(f"text layout test: {type(ex).__name__}: {ex} {traceback.format_exc(limit=3)}")
    finally:
        g.text = txt0
        g.W, g.H, g.screen = W0, H0, scr0
        g.pb_display = pb0
        g.state, g.mode, g.reaction_variant = "menu", "flick", "static"

    # ── แคชแผงเมนู (cached_panel: การ์ด "วันนี้" + ตารางแรงค์): เฟรมที่ blit จากแคชต้องเท่าการวาดจริงทุกพิกเซลบน overlay RGBA
    #    แบบ GPU — พึ่ง set_alpha(None) = copy ตรง ; pygame-ce รุ่นอื่นที่ CI/เครื่องเพื่อนลงต้องให้ผลเดียวกัน ──
    W0, H0, scr0 = g.W, g.H, g.screen
    try:
        from .display import RGBA_MASKS as _RM
        g.W, g.H = 1280, 720
        g.screen = pygame.Surface((1280, 720), pygame.SRCALPHA, 32, masks=_RM)
        for md in ("flick", "gun", "reaction"):
            g.state, g.mode = "menu", md
            _cp = g.cached_panel
            g.cached_panel = lambda _s, _k, _r, draw, ref=None: draw()
            try:
                g.zones = []
                g.draw_menu()
            finally:
                g.cached_panel = _cp
            want = pygame.image.tobytes(g.screen, "RGBA")
            g.invalidate_panels()
            for _ in range(2):                  # เฟรมแรกวาดจริง+จับภาพ, เฟรมสองมาจากแคช
                g.zones = []
                g.draw_menu()
            if pygame.image.tobytes(g.screen, "RGBA") != want:
                errors.append(f"menu cache ({md}): เฟรมจากแคชไม่เท่าการวาดจริง")
    except Exception as ex:
        errors.append(f"menu cache test: {type(ex).__name__}: {ex}")
    finally:
        g.W, g.H, g.screen = W0, H0, scr0
        g.state, g.mode = "menu", "flick"

    # ── dirty-rect ครอบทุกพิกเซลที่ draw_bot วาด (ใกล้/ไกล/ตาย): บน GPU path overlay อัพโหลด+เคลียร์เฉพาะกรอบที่
    #    mark_dirty — พิกเซลนอกกรอบไม่เคยถูกอัพโหลด (ลำตัวหาย) และไม่เคยถูกเคลียร์ (ทิ้งเศษค้างเป็นแถบตามทางเดินบอท)
    #    ของจริง 11 ก.ย. 2026: ผู้ใช้เห็นหัวลอยเหนือขา + แถบจุดแดง-ขาวค้างกลางจอในดริล hold ──
    g.mode = "gun"; g.gun_weapon = "vandal"; g.gun_drill = "duel"; g.duration = 15
    g.start_countdown(); g.begin_play()
    g.bots = []; g.gun_next_bot_at = None
    g.cam.yaw = 0.0; g.cam.pitch = 0.0
    _old = (g.screen, g._track_dirty, list(g._dirty))
    try:
        for dist, alive in ((4.0, True), (27.8, True), (12.0, False)):
            bb = _guns.Bot(0.7, g.gun_origin[2] + dist); bb.alive = alive
            surf = pygame.Surface((g.W, g.H), pygame.SRCALPHA); surf.fill((0, 0, 0, 0))
            g.screen = surf; g._track_dirty = True; g._dirty = []
            g.draw_bot(bb, g.fl())
            painted = surf.get_bounding_rect()
            cover = pygame.Rect(g._dirty[0]).unionall(g._dirty[1:]) if g._dirty else pygame.Rect(0, 0, 0, 0)
            if not painted.w:
                errors.append(f"gun: draw_bot ({dist}m) ไม่วาดอะไรเลย")
            elif not cover.contains(painted):
                errors.append(f"gun: draw_bot ({dist}m alive={alive}) วาดนอกกรอบ dirty {painted} vs mark {cover} → ภาพค้าง/ลำตัวหายบน GPU")
    except Exception as ex:
        errors.append(f"gun: draw_bot dirty-coverage test พัง: {type(ex).__name__}: {ex}")
    finally:
        g.screen, g._track_dirty, g._dirty = _old[0], _old[1], _old[2]

    g.save_score()
    if not g.data["leaderboard"]:
        errors.append("leaderboard save failed")
    # history cap: เกิน HISTORY_MAX ตัดหัว (เก่าสุด) / รอบเก่ากว่า HISTORY_SHOTS_KEEP ล่าสุดถูกถอด shots แต่จำ shots_n
    fake = [{"mode": "flick", "score": i, "shots": [(0.0, 0.0)]} for i in range(HISTORY_MAX + 7)]
    trim_history(fake)
    if len(fake) != HISTORY_MAX:
        errors.append(f"trim_history: len {len(fake)} != {HISTORY_MAX}")
    elif fake[0]["score"] != 7:
        errors.append("trim_history: dropped wrong end (must drop oldest)")
    elif fake[0].get("shots") or fake[0].get("shots_n") != 1:
        errors.append("trim_history: old entry must lose shots but keep shots_n")
    elif not fake[-1].get("shots") or not fake[-HISTORY_SHOTS_KEEP].get("shots"):
        errors.append("trim_history: newest HISTORY_SHOTS_KEEP entries must keep shots")
    elif fake[-HISTORY_SHOTS_KEEP - 1].get("shots"):
        errors.append("trim_history: shots boundary off by one")
    small = [{"mode": "flick", "score": 0, "shots": [(0.0, 0.0)]}]
    trim_history(small)
    if not small[0]["shots"]:
        errors.append("trim_history: must not touch a short history")
    if get_rank(9999, 30, "medium", "flick")[1] != "Diamond I":
        errors.append("rank scale wrong")
    if get_rank(0, 30, "medium", "flick")[1] != "Iron I":
        errors.append("rank floor wrong")
    if get_rt_rank(140, "static")[1] != "Radiant":
        errors.append("rt rank wrong")

    # ── [GPU phase 2] พิสูจน์ตาม docstring ของ glrender.py: view_matrix·[p,1] == cam.to_cam(p)
    #    คณิตล้วน ไม่ต้องมี GL context — รัน headless ได้เสมอ (moderngl ไม่มีก็รันได้) ──
    from .glrender import view_matrix
    from .camera import Camera
    import random as _random
    _rng = _random.Random(0x56414C)   # deterministic — รันซ้ำได้ผลเดิม
    _cam = Camera()
    _worst = 0.0
    for _ in range(5000):
        _cam.yaw = _rng.uniform(-math.pi, math.pi)
        _cam.pitch = _rng.uniform(-1.55, 1.55)
        _cam.pos = [_rng.uniform(-20, 20), _rng.uniform(-5, 12), _rng.uniform(-20, 40)]
        m = view_matrix(_cam.yaw, _cam.pitch, _cam.pos)
        p = (_rng.uniform(-30, 30), _rng.uniform(-10, 20), _rng.uniform(-10, 60))
        # m เป็น column-major: cam_i = Σ_j m[j*4+i]·p_j + m[12+i]
        gl = tuple(m[0 * 4 + i] * p[0] + m[1 * 4 + i] * p[1] + m[2 * 4 + i] * p[2] + m[12 + i]
                   for i in range(3))
        sw = _cam.to_cam(p)
        _worst = max(_worst, max(abs(a - b) for a, b in zip(gl, sw)))
    if _worst >= 1e-9:
        errors.append(f"glrender view_matrix != camera.to_cam (ต่างสุด {_worst:.3g})")

    if _glyph_bad:
        errors.append(f"glyph: ข้อความที่วาดมีตัวที่ฟอนต์ UI ไม่มี ({sorted(set(_glyph_bad))[:4]})")
    # ตัวจับต้องจับได้จริง: รายการในโค้ด + ตัวนอกรายการที่วัดว่าเป็นกล่อง (▲ U+25B2) ; ตัวที่มี glyph (≤ ± × ° · — ∆) ต้องผ่าน
    if _no_glyph("A") or _no_glyph("ก") or any(_no_glyph(c) for c in "≤±×°·—∆") or not _no_glyph("→") \
            or (_glyph_fonts and not _no_glyph("▲")):
        errors.append("glyph: ตัวตรวจ glyph ผิด (ตัวที่มี glyph ถูกจับ หรือ → / ▲ หลุด)")
    # รายการในโค้ดต้องตรงกับฟอนต์จริง (ทุกตัวเป็นกล่องจริง) — กันรายการเพี้ยนจนห้ามตัวที่ใช้ได้
    _listed_ok = [c for c in UI_FONT_NO_GLYPH if _glyph_fonts
                  and not any(_glyph_sig(f, c) == nd for f, nd in zip(_glyph_fonts, _glyph_none))]
    if _listed_ok:
        errors.append(f"glyph: config.UI_FONT_NO_GLYPH มีตัวที่ฟอนต์ UI มี glyph อยู่แล้ว ({''.join(_listed_ok)})")
    g.text = _text_real
    pygame.quit()
    if errors:
        print("SELFTEST FAIL")
        for er in errors[:15]:
            print(" -", er)
        sys.exit(1)
    print("SELFTEST OK — ทุกโหมด ทุกหน้าจอ ทำงานครบ")
