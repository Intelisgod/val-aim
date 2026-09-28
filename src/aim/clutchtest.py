# -*- coding: utf-8 -*-
"""selftest ของโหมด CLUTCH 1vN (hook ใน aim/selftest.py ด้วย Game headless ตัวเดียวกัน — ตัวตรวจ glyph ครอบ g.text อยู่แล้ว)
เล่นจริงทั้งรอบบน Training Yard ด้วยสมองบอท/ตัววาด GL "ปลอม" ตามสัญญา §11.1/§11.2 (ของจริงเป็นของทีมอื่น — เทสนี้ต้อง
ไม่พึ่งมัน): วางแล้วระเบิด, เก็บครบ, หมดเวลา, ตาย (ก่อน/หลังวาง — ตัดสินด้วย can_bots_defuse), บอทกู้, กู้สำเร็จ/ninja/
เก็บครึ่งทาง/กู้หลอก, spike ระเบิดตอน DEF, จบรอบจากหน้าพัก, หลุดโฟกัส, ฉากเดิม/ฉากใหม่, คืนเมนู, ฟิลด์ history + mrev,
หน้าผล/หน้าตั้งค่า 3 ขนาดจอ (zone ไม่ล้น/ไม่ทับ), ข้อความ HUD ไม่ทับกัน, dirty-rect ครอบทุกพิกเซลที่ HUD วาด, GL ล้มแล้ว
ถอยไปภาพสำรองเฉพาะ clutch, ภาพสำรองไม่วาดห้องซ้อม — คืน list ข้อความ error (ว่าง = ผ่าน)"""
import math
import random
import time
import traceback

import pygame

from .config import EYE_Y, MODE_REV, mode_current
from . import clutchaudio, clutchmap, clutchscen, guns, online, routine
from .clutchresults import wilson_lb


class FakeBrain:
    """สมองบอทปลอมตามสัญญา §11.1 — บอทยืนนิ่งตามฉาก ; เหตุการณ์ยิง/กู้ = สคริปต์ที่เทสใส่ (self.script)"""
    def __init__(self, cmap, scen, side, tier, weapon, rng, t0, placement="real"):
        self.args = (side, tier, weapon, placement, t0)
        self.bots, self.calls, self.script = [], [], []
        self.can, self.seen, self.defusing, self.prep = True, 0, None, 0
        self.pv = None
        for e in scen.get("e") or []:
            b = guns.Bot(e[0], e[1])
            b.y0 = cmap.support_y(e[0], e[1], clutchmap.BOT_R) or 0.0
            b.weapon = weapon
            b.meta = {"yaw": e[2], "pitch": 0.0, "state": "hold", "sees": False}
            self.bots.append(b)

    def prepare(self, max_nodes=500):
        self.prep += 1
        return self.prep >= 3

    def update(self, dt, t, pv):
        self.pv = (pv.x, pv.z, pv.feet, pv.crouch, pv.alive, pv.planting, pv.defusing, pv.spike_out, pv.eye())
        out = [ev for tt, ev in self.script if tt <= t]
        self.script = [(tt, ev) for tt, ev in self.script if tt > t]
        return out

    def bot_defuse(self):
        return self.defusing

    def can_bots_defuse(self, t, spike_xz, spike_left):
        self.calls.append(("can", round(spike_left, 2)))
        return self.can

    def seen_count(self):
        return self.seen

    def __getattr__(self, name):
        if name.startswith("on_"):
            return lambda *a: self.calls.append((name,) + a)
        raise AttributeError(name)


class FakeGL:
    KEYS = {"map", "yaw", "pitch", "pos", "f", "W", "H", "t", "bots", "spike", "tracers", "flashes", "marks",
            "zone_hint", "vm"}
    BOT_KEYS = {"x", "y", "z", "yaw", "crouch", "alive", "dead_t", "flash", "vx", "vz", "pitch", "walk", "reload", "weapon"}
    VM_KEYS = {"weapon", "equip", "equip_k", "reload_k", "ads", "crouch", "speed", "air", "fire_t", "planting",
               "defusing", "kick"}     # §13.2 viewmodel

    def __init__(self, ok=True):
        self.ok, self.views, self.bad = ok, 0, []

    def draw_clutch_world(self, game, view):
        self.views += 1
        if set(view) != self.KEYS or any(set(b) != self.BOT_KEYS for b in view["bots"]) or                 set(view["vm"]) != self.VM_KEYS:
            self.bad.append(sorted(view))
        return self.ok


def _put(g, x, z, yaw=None, pitch=0.0):
    f = g.cmap.player_map().support_y(x, z) or 0.0
    g.cam.pos = [x, f + EYE_Y, z]
    g.cl_feet, g.cl_eye, g.cl_vy, g.vel = f, f + EYE_Y, 0.0, [0.0, 0.0]
    g.cl_air = g.cl_tuck = False
    g.cl_sup = f
    if yaw is not None:
        g.cam.yaw, g.cam.pitch = yaw, pitch


def _aim(g, x, y, z):
    dx, dy, dz = x - g.cam.pos[0], y - g.cam.pos[1], z - g.cam.pos[2]
    g.cam.yaw, g.cam.pitch = math.atan2(dx, dz), math.atan2(dy, math.hypot(dx, dz))


def _run(g, secs, dt=1 / 60.0, each=None):
    for _ in range(int(round(secs / dt))):
        if g.state != "play":
            break
        if each:
            each()
        g.update_play(dt)


def _start(g, same=False, **cfg):
    c = dict(clutchscen.DEFAULT_CFG, map="yard", site="A")
    c.update(cfg)
    g.S["clutch"] = c
    g.clutch_start(same)
    g.begin_play()
    return g.brain


def _zones_ok(g, tag, errors):
    scr = pygame.Rect(0, 0, g.W, g.H)
    zs = [z for z, _f in g.zones]
    if not zs:
        errors.append(f"clutch {tag}: ไม่มีปุ่มเลย")
    if not all(scr.contains(z) for z in zs) or any(a.colliderect(b) for i, a in enumerate(zs) for b in zs[i + 1:]):
        errors.append(f"clutch {tag}: zone ล้นจอ/ทับกัน")


def selftest(g):
    errors = []
    t_start = time.perf_counter()
    rs = random.getstate()
    random.seed(20260927)
    keep = (g.W, g.H, g.screen, g.S.get("clutch"), g.mode, g.gun_weapon, g.gun_drill, g.gpu, g._gl, g.text)
    mods = dict(clutchscen._MODS)
    g.clutch_brain_factory = FakeBrain
    g.plan_queue, g.plan_menu_state = [], None      # คิวแผนที่เทสก่อนหน้าทิ้งค้าง — go_menu (plan.leave) จะคืนค่าเมนูของมันทับ
    E = errors.append
    try:
        # ── แกน: ค่าตั้ง/ฉาก/Wilson ──
        if clutchscen.norm_cfg({"n": 9, "side": "x", "tier": 12, "map": "../x"}) != dict(clutchscen.DEFAULT_CFG, tier=12):
            E("clutch norm_cfg: ค่าเพี้ยนต้องกลับค่าเริ่มต้นทีละคีย์")
        if not (0.0 < wilson_lb(5, 10) < 0.5 < wilson_lb(90, 100) < 0.9) or wilson_lb(0, 0) != 0.0:
            E("clutch wilson_lb ผิด")
        cm = clutchscen.load_map("yard")
        for side, n in (("atk", 4), ("def", 5)):
            i, sc = clutchscen.pick_scenario(cm, side, n, "any", random.Random(3))
            ok = i == -1 and len(sc["e"]) == n and all(cm.disc_clear(e[0], e[1], clutchmap.BOT_R) for e in sc["e"])
            ok = ok and cm.walkable(sc["p"][0], sc["p"][1]) and (side == "atk" or cm.walkable(*sc["k"]))
            if not ok:
                E(f"clutch gen_scenario {side}{n}: ฉากสร้างเองไม่ถูกต้อง {sc}")
        # ── ATK: หยิบ spike, วาง (ยกเลิก = เริ่มใหม่), rooted, ระเบิด = ชนะ ──
        g.mode, g.gun_weapon, g.gun_drill = "gun", "sheriff", "tap"
        br = _start(g, side="atk", n=2)
        if g.state != "play" or g.mode != "clutch" or not isinstance(br, FakeBrain) or br.prep < 3:
            E(f"clutch start: state {g.state} mode {g.mode} prep {getattr(br, 'prep', None)}")
        if g.bots is not br.bots or len(g.bots) != 2 or g.gun_drill != "duel" or br.args[1] != g.clutch_tier:
            E("clutch start: self.bots ต้องเป็นลิสต์ของสมองบอท + ดริล duel + ระดับบอทตามตั้งค่า")
        _put(g, -12.0, 9.5, 0.0)
        g.clutch_key(pygame.K_4, True)
        g.lmb_down = True
        _run(g, 0.3)
        if g.cl_plant_t0 is not None:
            E("clutch: วางได้ก่อนหยิบ spike เสร็จ (SPIKE_EQUIP_T)")
        _run(g, 0.4)
        g.keys_down = {"w"}
        p0 = list(g.cam.pos)
        _run(g, 1.5)
        if g.cl_plant_t0 is None or abs(g.cam.pos[0] - p0[0]) + abs(g.cam.pos[2] - p0[2]) > 1e-6:
            E("clutch: คลิกค้างในไซต์ต้องเริ่มวาง + ยืนนิ่ง (rooted)")
        g.lmb_down = False
        _run(g, 0.1)
        g.keys_down = set()
        if g.cl_plant_t0 is not None or not any(c[0] == "on_plant_cancel" for c in br.calls):
            E("clutch: ปล่อยคลิก = ยกเลิกวาง + แจ้ง on_plant_cancel")
        g.lmb_down = True
        _run(g, 3.9)
        if g.cl_spike["state"] != "carried":
            E("clutch: วางใหม่ต้องนับ 4 วิจากศูนย์ (ความคืบหน้ารีเซ็ต)")
        _run(g, 0.3)
        g.lmb_down = False
        if g.cl_spike["state"] != "planted" or not any(c[0] == "on_planted" for c in br.calls) or g.cl_equip != "gun":
            E(f"clutch: วางไม่สำเร็จ ({g.cl_spike['state']})")
        if g.cl_plant_left is None:
            E("clutch: ไม่จดเวลาเหลือตอนเริ่มวาง")
        _run(g, 46.0, 1 / 30.0)
        _run(g, 2.0)
        e = g.last_entry if g.state == "results" else {}
        if e.get("why") != "detonated" or e.get("win") != 1 or e.get("score") != 1250:
            E(f"clutch ATK: วางแล้วระเบิดต้องชนะ 1250 ({e.get('why')}, {e.get('score')})")
        need = {"variant", "drill", "site", "win", "why", "kills", "deaths", "hs", "shots_fired", "acc", "rt", "t_used",
                "tier_bot", "weapon", "heard", "multi", "moving_pct", "plant_t", "defuse_t", "scen", "score"}
        if not need <= set(e) or e.get("variant") != "yard" or e.get("drill") != "atk2" or e.get("duration") != 0 \
                or e.get("size") != "" or e.get("mrev") != MODE_REV["clutch"] or not mode_current(e):
            E(f"clutch history: ฟิลด์ไม่ครบ/ผิด {sorted(set(need) - set(e))} {e.get('drill')} mrev {e.get('mrev')}")
        if len(str(e)) > 700 or "shots" in e and len(e["shots"]) > 60:
            E("clutch history: entry ต้องเล็ก (ไม่มีเส้นทาง)")
        if not g.same_config(e) or online.collect_pbs([e]) or routine.rank_index(e) is not None:
            E("clutch: same_config/online ข้าม/ไม่มีแรงค์ ผิด")
        # ── จอผล 3 ขนาด + การ์ดส่งออก + ปุ่มฉากเดิม/ฉากใหม่ ──
        from . import export
        for ww, hh in ((900, 560), (1280, 720), (2560, 1440)):
            g.W, g.H = ww, hh
            g.screen = pygame.Surface((ww, hh))
            g.zones = []
            g.draw_results()
            _zones_ok(g, f"results {ww}x{hh}", errors)
        export.build_score_card(g)
        seed, sci = g.clutch_seed, g.clutch_scen_i
        g.clutch_start(True)
        if g.clutch_seed != seed or g.clutch_scen_i != sci:
            E("clutch: ฉากเดิมอีกครั้ง ต้องใช้ seed/ฉากเดิม")
        g.clutch_start(False)
        if g.clutch_seed == seed:
            E("clutch: เล่นต่อ (ฉากใหม่) ต้องสุ่ม seed ใหม่")
        # ── เมนู: คืนโหมด/ปืน/ดริลเดิม ──
        g.go_menu()
        if (g.mode, g.gun_weapon, g.gun_drill) != ("gun", "sheriff", "tap"):
            E(f"clutch go_menu: ต้องคืน gun/sheriff/tap ได้ {(g.mode, g.gun_weapon, g.gun_drill)}")
        # ── ATK: หมดเวลา · เก็บครบ (ยิงจริง + แจ้ง on_bot_damaged/killed) · กำแพงบังกระสุน ──
        br = _start(g, side="atk", n=2)
        g.cl_round_left = 0.5
        _run(g, 3.0)
        if g.last_entry.get("why") != "time" or g.last_entry.get("win") != 0:
            E(f"clutch: หมดเวลาก่อนวางต้องแพ้ time ({g.last_entry.get('why')})")
        br = _start(g, side="atk", n=2)
        _run(g, 1.1)
        b1 = br.bots[1]
        _put(g, -2.0, 7.0)
        _aim(g, b1.x, b1.head_y(), b1.z)
        g.shoot()
        if b1.hp != guns.PLAYER_HP or not g.cl_marks or g.cl_marks[-1][1] != (1.0, 0.0, 0.0):
            E(f"clutch: กำแพงแมพต้องบังกระสุน + รอยมี normal ของหน้ากำแพง ({b1.hp}, {g.cl_marks[-1:] })")
        _put(g, -10.5, 9.5)
        _run(g, 0.3)
        for b in br.bots:
            _aim(g, b.x, b.body_y0() + 0.3, b.z)
            g.gun_next_shot_at = 0.0
            g.shoot()
            _run(g, 0.3)
            _aim(g, b.x, b.head_y(), b.z)
            g.gun_next_shot_at = 0.0
            g.shoot()
            _run(g, 0.05)
        names = [c[0] for c in br.calls]
        if "on_bot_damaged" not in names or names.count("on_bot_killed") != 2 or "on_player_shot" not in names:
            E(f"clutch: ต้องแจ้งสมองบอท on_bot_damaged/on_bot_killed/on_player_shot ({sorted(set(names))})")
        _run(g, 2.0)
        if g.last_entry.get("why") != "elim" or g.last_entry.get("kills") != 2:
            E(f"clutch: เก็บครบต้องชนะ elim ({g.last_entry.get('why')}, kills {g.last_entry.get('kills')})")
        # ── ATK: โดนยิง (ดาเมจ/เกราะ/tagging/ลูกศรทิศ) แล้วตายก่อนวาง = แพ้ ──
        br = _start(g, side="atk", n=2)
        _run(g, 0.2)
        b0 = br.bots[0]
        g.keys_down = {"w"}
        _run(g, 0.5)
        shot = {"k": "shot", "bot": b0, "from": b0.eye(), "to": tuple(g.cam.pos), "zone": "body", "dmg": 40.0}
        br.script = [(g.gt, dict(shot))]
        _run(g, 1 / 60.0)
        hp, sh = guns.apply_damage(guns.PLAYER_HP, guns.PLAYER_SHIELD, 40.0)
        if (g.gun_hp, g.gun_shield) != (hp, sh) or not g.cl_dmg_ind or g.clutch_tag_mult() > 0.4 or not g.cl_tracers:
            E(f"clutch: โดนยิงต้องลด HP/เกราะ + tagging + ลูกศรทิศ + tracer ({g.gun_hp}, {g.gun_shield})")
        g.keys_down = set()
        br.script = [(g.gt, dict(shot, zone="head", dmg=160.0))]
        _run(g, 3.0)
        if g.last_entry.get("why") != "died" or g.last_entry.get("deaths") != 1:
            E(f"clutch: ตายก่อนวางต้องแพ้ died ({g.last_entry.get('why')})")
        # ── ATK ตายหลังวาง: ตัดสินด้วย can_bots_defuse · บอทกู้สำเร็จ = แพ้ ──
        for can, want in ((True, (0, "died")), (False, (1, "detonated"))):
            br = _start(g, side="atk", n=2)
            g.cl_spike.update(state="planted", x=-12.0, y=0.0, z=9.5, left=30.0)
            br.can = can
            br.script = [(0.5, {"k": "shot", "bot": br.bots[0], "from": br.bots[0].eye(), "to": tuple(g.cam.pos),
                                "zone": "head", "dmg": 999.0})]
            _run(g, 3.0)
            got = (g.last_entry.get("win"), g.last_entry.get("why"))
            if got != want or not any(c[0] == "can" for c in br.calls):
                E(f"clutch dead-planter can={can}: ได้ {got} ต้อง {want}")
        br = _start(g, side="atk", n=2)
        g.cl_spike.update(state="planted", x=-12.0, y=0.0, z=9.5, left=30.0)
        br.script = [(0.3, {"k": "defused", "bot": br.bots[0]})]
        _run(g, 3.0)
        if (g.last_entry.get("win"), g.last_entry.get("why"), g.last_entry.get("score")) != (0, "defused", 250):
            E(f"clutch: บอทกู้ spike ต้องแพ้ defused คะแนน 250 ({g.last_entry.get('why')}, {g.last_entry.get('score')})")
        # ── DEF: ระยะ/LOS กู้ · กู้หลอก · เก็บครึ่งทาง 3.5 วิ · ninja / defused · spike ระเบิด ──
        br = _start(g, side="def", n=2)
        _run(g, 0.1)
        if g.cl_spike["state"] != "planted" or abs(g.cl_spike["x"] + 12.0) > 1e-6:
            E("clutch DEF: spike ต้องลงที่ scen k ตั้งแต่เริ่ม")
        _put(g, -12.0, 13.0)
        if g.clutch_can_defuse():
            E("clutch DEF: 3.5 ม. จาก spike ต้องกู้ไม่ได้ (DEFUSE_R 2.4)")
        _put(g, -11.0, 9.5)
        if not g.clutch_can_defuse():
            E("clutch DEF: 1 ม. จาก spike + เห็นกัน ต้องกู้ได้")
        g.clutch_key(pygame.K_f, True)
        _run(g, 0.5)
        g.clutch_key(pygame.K_f, False)
        _run(g, 0.05)
        g.clutch_key(pygame.K_4, True)
        _run(g, 4.0)
        g.clutch_key(pygame.K_4, False)
        _run(g, 0.05)
        if g.cl_fake != 1 or g.cl_defuse_base != 3.5:
            E(f"clutch DEF: กู้หลอก {g.cl_fake} (ต้อง 1) / เก็บครึ่งทาง {g.cl_defuse_base} (ต้อง 3.5)")
        starts = [c for c in br.calls if c[0] == "on_defuse_start"]
        g.clutch_key(pygame.K_f, True)
        _run(g, 3.4)
        if g.cl_result is not None:
            E("clutch DEF: กู้ต่อจากครึ่งทางต้องใช้อีก 3.5 วิ")
        _run(g, 0.3)
        g.clutch_key(pygame.K_f, False)
        _run(g, 2.0)
        e = g.last_entry
        if (e.get("win"), e.get("why"), e.get("score"), e.get("fake")) != (1, "ninja", 1250, 1) or len(starts) != 2 \
                or [c for c in br.calls if c[0] == "on_defuse_start"][-1][3] is not True:
            E(f"clutch DEF: กู้สำเร็จขณะศัตรูยังอยู่ = ninja 1250 ({e.get('why')}, {e.get('score')}, fake {e.get('fake')})")
        br = _start(g, side="def", n=2)
        for b in br.bots:
            b.alive = False
        _put(g, -11.0, 9.5)
        g.clutch_key(pygame.K_4, True)
        _run(g, 9.0)
        g.clutch_key(pygame.K_4, False)
        if g.last_entry.get("why") != "defused" or g.last_entry.get("win") != 1:
            E(f"clutch DEF: เก็บครบแล้วกู้ = defused ({g.last_entry.get('why')})")
        br = _start(g, side="def", n=2)
        g.cl_spike["left"] = 0.4
        _run(g, 3.0)
        if (g.last_entry.get("win"), g.last_entry.get("why")) != (0, "detonated"):
            E(f"clutch DEF: spike ระเบิดต้องแพ้ ({g.last_entry.get('why')})")
        # ── จบรอบจากหน้าพัก = แพ้ · หลุดโฟกัส = พัก + ล้างปุ่ม · R ระหว่างพัก = ฉากเดิม ──
        br = _start(g, side="atk", n=2)
        _run(g, 0.2)
        g.keys_down, g.cl_hold, g.lmb_down, g.gun_firing = {"w", "shift"}, {"f"}, True, True
        g.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        if g.state != "pause" or g.keys_down or g.cl_hold or g.lmb_down or g.gun_firing:
            E("clutch: หลุดโฟกัสต้องพัก + ล้างปุ่มที่ค้าง")
        seed = g.clutch_seed
        g.start_countdown(restart=True)
        if g.clutch_seed != seed:
            E("clutch: R ระหว่างพักต้องเริ่มฉากเดิม")
        g.begin_play()
        g.state = "pause"
        g.end_game()
        if (g.last_entry.get("win"), g.last_entry.get("why")) != (0, "quit"):
            E("clutch: จบรอบจากหน้าพักต้องนับแพ้ (quit)")
        # ── ปืน: Op สโคป (ซูม fl() + บอทถือ Vandal) / หยิบ spike = หลุดสโคป + RMB ใช้ไม่ได้ · Classic คลิกขวาแจ้งสมองบอท ──
        br = _start(g, side="atk", n=2, weapon="operator")
        f0 = g.fl()
        g.gun_rmb(True)
        if g.gun_zoom != 2.5 or abs(g.fl() - f0 * 2.5) > 1e-6 or br.args[2] != "vandal":
            E(f"clutch Op: สโคป/ซูม fl()/บอทถือ Vandal ผิด ({g.gun_zoom}, {br.args[2]})")
        g.draw_world(); g.draw_crosshair(); g.draw_hud()
        g.clutch_key(pygame.K_4, True)
        g.gun_rmb(True)
        if g.gun_zoom != 1.0 or g.cl_equip != "spike":
            E("clutch: หยิบ spike ต้องหลุดสโคป และ RMB ใช้ไม่ได้")
        g.state = "pause"
        g.end_game()
        br = _start(g, side="atk", n=2, weapon="classic")
        _run(g, 0.2)
        g.gun_rmb(True)
        if g.gun_shots != 3 or not any(c[0] == "on_player_shot" for c in br.calls):
            E(f"clutch Classic: คลิกขวาต้องยิงชุด 3 เม็ด + แจ้ง on_player_shot ({g.gun_shots})")
        g.state = "pause"
        g.end_game()
        # ── ภาพ: GL ปลอม (สัญญา view) + dirty-rect ครอบทุกพิกเซลของ HUD + ข้อความ HUD ไม่ทับกัน + ภาพสำรอง ──
        errors += _draw_checks(g)
        # ── ข้อบกพร่องจาก review รวมทีม 2026-09-28 (กติกา/โฟกัส/เลือกฉาก/HUD/ประสิทธิภาพ) ──
        from .clutchfixtest import _fix_checks
        errors += _fix_checks(g)
        # ── realism pass v2 (§13): กระโดด/หดขาขึ้นกล่อง/ตก/ดาเมจตก/โทษความแม่นลอย-แตะพื้น/เสียงลงพื้น/ข้อมูลข้ามทีม ──
        from .clutchmovetest import _move_checks
        errors += _move_checks(g)
        # ── หน้าตั้งค่า: 3 ขนาดจอ + START ปิดเมื่อไม่มี GPU + ESC คืนเมนู ──
        from . import clutchsetup
        g.go_menu()
        g.mode, g.gun_weapon, g.gun_drill = "flick", "vandal", "duel"
        for ww, hh in ((900, 560), (1280, 720), (2560, 1440)):
            g.W, g.H = ww, hh
            g.screen = pygame.Surface((ww, hh))
            clutchsetup.open_setup(g)
            g.zones = []
            g.flow.draw()
            _zones_ok(g, f"setup {ww}x{hh}", errors)
        g.flow._start()
        if g.mode != "flick" or g.flow is None or not g.flow.msg:
            E("clutch setup: ไม่มี GPU ต้องกด START ไม่ได้ + บอกเหตุ")
        g.flow.on_exit()
        g.flow, g.state = None, "menu"
        # ── ไม่มีสมองบอท = หุ่นนิ่ง (โหมดยังเล่นได้) ──
        g.clutch_brain_factory = None
        clutchscen._MODS["bots"] = None
        _start(g, side="atk", n=3)
        if not isinstance(g.brain, clutchscen._DummyBrain) or len(g.bots) != 3 or not g.cl_warn:
            E("clutch: ไม่มี clutchbots ต้องได้หุ่นนิ่ง + ข้อความเตือน")
        _run(g, 1.0)
        g.state = "pause"
        g.end_game()
        # ── เสียง (mixer จริงของเครื่อง/ dummy) ──
        if pygame.mixer.get_init() and len(clutchaudio._bank() or {}) < 9:
            E("clutch audio: สร้างเสียงไม่ครบ")
    except Exception as ex:
        E(f"clutch selftest พัง: {type(ex).__name__}: {ex} {traceback.format_exc(limit=4)}")
    finally:
        g.clutch_brain_factory = None
        clutchscen._MODS.clear()
        clutchscen._MODS.update(mods)
        (g.W, g.H, g.screen, cs, g.mode, g.gun_weapon, g.gun_drill, g.gpu, g._gl, g.text) = keep
        if cs is None:
            g.S.pop("clutch", None)
        else:
            g.S["clutch"] = cs
        g.flow, g.state, g.pending_end = None, "menu", None
        g.clutch_saved = None
        random.setstate(rs)
    g.clutch_selftest_ms = round((time.perf_counter() - t_start) * 1000)
    return errors


def _draw_checks(g):
    """GL ปลอม + dirty-rect coverage + ข้อความ HUD ไม่ทับ + GL ล้ม → ภาพสำรองเฉพาะ clutch + ไม่วาดห้องซ้อม"""
    errors = []
    E = errors.append
    br = _start(g, side="atk", n=2)
    _run(g, 0.5)
    fake = FakeGL()
    clutchscen._MODS["gl"] = fake
    g.gpu, g._gl = True, object()
    txt0 = g.text
    try:
        for ww, hh in ((900, 560), (1280, 720), (2560, 1440)):
            g.W, g.H = ww, hh
            for side in ("atk", "def"):
                if side == "def":
                    br = _start(g, side="def", n=2)
                    _put(g, -11.0, 9.5, -math.pi / 2)
                    g.gt = 1.0
                    g.cl_defuse_t0, g.cl_tab = g.gt - 1.0, ww == 1280
                else:
                    _put(g, -12.0, 9.5, 0.0)
                    g.gt, g.cl_equip, g.cl_plant_t0 = 1.0, "spike", 0.2
                    g.cl_warn = "ทดสอบข้อความเตือน"
                g.cl_heard_t, g.gun_flash = g.gt, 0.0
                for i in range(4):
                    g.clutch_feed(f"คุณ  HEADSHOT ศัตรู {i + 1}  (12m)", (60, 179, 113))
                g.cl_dmg_ind = [(0.3, g.gt), (2.5, g.gt - 0.5)]
                g.cl_bot_defuse = (br.bots[0], 2.0) if side == "atk" else None
                caught = []

                def cap(s, *a, **k):
                    r = txt0(s, *a, **k)
                    if k.get("surf") is None and str(s).strip():
                        caught.append((str(s), pygame.Rect(r)))
                    return r
                g.text = cap
                surf = pygame.Surface((ww, hh), pygame.SRCALPHA)
                surf.fill((0, 0, 0, 0))
                g.screen, g._dirty, g._track_dirty = surf, [], False
                g.draw_world(); g.draw_crosshair(); g.draw_effects(); g.draw_hud()
                g.text = txt0
                if not g._track_dirty or not g._world_gpu_frame:
                    E(f"clutch GL {ww}x{hh} {side}: ต้องเปิด dirty-track หลังโลก GPU")
                left = surf.copy()
                for r in g._dirty:
                    left.fill((0, 0, 0, 0), r)
                bad = left.get_bounding_rect()
                if bad.w:
                    E(f"clutch HUD {ww}x{hh} {side}: วาดนอกกรอบ dirty {bad} → ภาพค้างบน GPU")
                mp = g._cl_mini_px()
                s = g.hud_scale()
                mbox = pygame.Rect(int(14 * s), int(14 * s), mp, mp).inflate(int(round(6 * s)) * 2 + 2, int(round(6 * s)) * 2 + 2)
                if g.cl_tab:
                    bp = int(min(ww, hh) * 0.78)
                    big = pygame.Rect(0, 0, bp, bp)
                    big.center = (ww // 2, hh // 2)
                    caught = [c for c in caught if not big.inflate(20, 20).colliderect(c[1])]
                rest = [c for c in caught if not mbox.contains(c[1])]
                hit = [(a[0], b[0]) for i, a in enumerate(rest) for b in rest[i + 1:] if a[1].colliderect(b[1])]
                out = [c[0] for c in rest if not pygame.Rect(0, 0, ww, hh).contains(c[1])]
                if hit or out:
                    E(f"clutch HUD {ww}x{hh} {side}: ข้อความทับกัน {hit[:2]} / ตกขอบ {out[:2]}")
                g.cl_plant_t0 = g.cl_defuse_t0 = None
                g.cl_tab = False
        if fake.bad or not fake.views:
            E(f"clutch GL view: คีย์ไม่ตรงสัญญา §11.2 {fake.bad[:1]}")
        # ผลตอนจบ (ป้ายชนะ/แพ้) ก็ต้อง mark ครบ
        g.cl_result = {"win": 1, "why": "elim", "t": g.gt}
        surf = pygame.Surface((g.W, g.H), pygame.SRCALPHA)
        g.screen, g._dirty, g._track_dirty = surf, [], False
        g.draw_world(); g.draw_hud()
        left = surf.copy()
        for r in g._dirty:
            left.fill((0, 0, 0, 0), r)
        if left.get_bounding_rect().w:
            E("clutch HUD result banner: วาดนอกกรอบ dirty")
        g.cl_result = None
        # GL ล้ม (คืน False ติดกัน) → ปิดเฉพาะ clutch GL แล้วใช้ภาพสำรอง ; ห้องซ้อมเดิมห้ามถูกวาด
        fake.ok = False
        calls = []
        bg0, poly0 = g._draw_world_bg, g.poly
        g._draw_world_bg = lambda *a, **k: calls.append("bg")
        g.poly = lambda *a, **k: calls.append("poly")
        glr0 = getattr(g, "_glr", None)
        for _ in range(31):
            g.draw_world()
        g._draw_world_bg, g.poly = bg0, poly0
        if not g._clutch_gl_off or calls or getattr(g, "_glr", None) is not glr0:
            E(f"clutch GL fail: ต้องถอยไปภาพสำรองของ clutch เอง ไม่วาดห้องซ้อม ({calls[:2]}) และไม่แตะ GPU world เดิม")
    finally:
        g.text = txt0
        g.gpu, g._gl = False, None
        g._clutch_gl_off, g._clutch_gl_nok = False, 0
        g._track_dirty, g._dirty, g._world_gpu_frame = False, [], False
        g.state = "pause"
        g.end_game()
    return errors

