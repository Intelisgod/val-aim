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
    def dodge_act(i):
        # เดินหลบสลับซ้ายขวา + flick ยิงหัวเป้า
        if i % 50 < 25:
            g.keys_down = {"d"}
        else:
            g.keys_down = {"a"}
        if g.targets and i % 6 == 0:
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

    # menu เลือกโหมดด้วยเลข 1-9,0 (10 โหมด) — จำลอง handle_key
    # ── GUNFIGHT: กติกาปืนตรงตารางเกม + ดริลทั้ง 4 จบรอบได้ ──
    from . import guns as _guns
    stk = {("vandal", "head", 10): 1, ("vandal", "body", 10): 4, ("vandal", "leg", 10): 5,
           ("phantom", "head", 10): 1, ("phantom", "head", 30): 2, ("phantom", "body", 30): 5,
           ("sheriff", "body", 10): 3, ("sheriff", "leg", 10): 4, ("sheriff", "head", 40): 2,
           ("operator", "body", 30): 1, ("operator", "leg", 30): 2}
    for (wp, zone, dist), want in stk.items():
        got = _guns.shots_to_kill(wp, zone, dist)
        if got != want:
            errors.append(f"gun: {wp} {zone} {dist}m = {got} shots (game says {want})")
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
    _rnd.seed(20260911)          # บอท hold สุ่ม peek/jiggle — ล็อก seed ให้เทสต์ทำซ้ำได้
    for wp in _guns.WEAPON_ORDER:
        for drill in ("duel", "hold", "quick", "repo"):
            g.mode = "gun"; g.gun_weapon = wp; g.gun_drill = drill; g.duration = 15
            g.start_countdown(); g.begin_play()
            fr = 0
            while g.state == "play" and fr < 60 * 25:
                fr += 1
                live = [b for b in g.bots if b.alive and b.exposed]
                if live:
                    # hold: บอทโผล่สั้น ต้องยิงหัว (1 นัด) — ดริลอื่นยิงตัวเพื่อทดสอบดาเมจหลายนัด
                    _aim_bot(live[0], _guns.HEAD_Y if drill == "hold" else 1.2)
                    if wp == "operator" and g.gun_zoom == 1.0:
                        g.gun_rmb(True)
                    if fr % 3 == 0:
                        g.shoot()
                if drill == "repo" and g.gun_repo_deadline is not None:
                    g.keys_down.add("a")
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
    for tb in ["flick", "precision", "tracking", "reaction-static", "reaction-flick", "strafe", "sniper",
               "spray", "dodge", "placement", "switch"]:
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
    # พิมพ์ค่า sens ละเอียด 0.37 ได้
    g.text_focus = "sens"
    g.sens_text = "0.37"
    g.commit_sens()
    if abs(g.S["sens"] - 0.37) > 1e-9:
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

    # ── GUNFIGHT กลไกล้วน (fake game — รีวิว 11 ก.ย. 2026): fire rate ไม่ขึ้นกับ FPS/ไม่ยิงตามเก็บหลังค้าง,
    #    REPOSITION ยึด anchor นัดแรก, กำแพง hold บังกระสุนตามแนวยิง ──
    from . import gunplay as _gunplay
    errors += _gunplay.selftest()

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

    pygame.quit()
    if errors:
        print("SELFTEST FAIL")
        for er in errors[:15]:
            print(" -", er)
        sys.exit(1)
    print("SELFTEST OK — ทุกโหมด ทุกหน้าจอ ทำงานครบ")
