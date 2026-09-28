# -*- coding: utf-8 -*-
"""สมองบอทโหมด CLUTCH 1vN บนแมพจำลอง (pure python — ไม่มี pygame, py3.10) ตาม CLUTCH_DESIGN §4 + §10.2/§10.3 + §11.1

สัญญา §11.1: โหมดเติม PlayerView ทุกเฟรม → ClutchBrain.update(dt, t, pv) คืน events ; บอทไม่อ่าน Game เลย
บอท = guns.Bot (hitbox/y0/หมอบ/take) + meta ; เดินด้วย movement.step + ClutchMap.move (ตกขอบ = แรงโน้มถ่วงเอง)
  สายตา   FOV 103° รอบ yaw ปัจจุบัน + LOS ถึงจุดตัวอย่าง 7 จุดที่ออฟเซ็ต "ตั้งฉากแนวสายตา" (body_points) ;
          ผู้เล่นโผล่ใน ±12° ของจุดเล็ง = โมเดล reaction ที่สอบเทียบแล้ว (duel.tier_params ดริล "peek" = ยืนเฝ้าไม่ได้
          เล็งรอ — นาฬิกาเริ่มเมื่อหัวผู้เล่นพ้นขอบแบบที่ฟิตไว้ / "angle" = เล็งรอ·โผล่ซ้ำจุดเดิม·กำลังขยับ) + เวลาหัน
          off/360°/s เมื่อเกิน 10° ± peeker's advantage ;
          นอก ±12° แต่ใน FOV = ทอยสังเกตเห็นทุก 0.25 วิ (ตาราง CS bot: ส่วนตัวที่โผล่ × ความเร็ว × ท่า × ระยะ ;
          วิ่ง = เห็นแน่) แล้วบวก 6 ms/° ที่เกิน 10° (≤ 0.25 วิ) ; e0 สุ่มใหม่ทุกขอบขาขึ้นของ LOS, เล็งหัวสุ่มต่อการปะทะ
  ยิง      เล็งตำแหน่งผู้เล่นเมื่อ lag วิก่อน (trail มีระดับพื้น) + คลาด/หด/สั่นแบบ gunbots + Stability ของปืนบอท ;
          จุดที่ตั้งใจเล็งถูกบัง = ยิงส่วนที่โผล่ ; กระสุน = รังสีแมพ (cmap.ray) เทียบ humanoid_zone(y0=เท้าผู้เล่น) —
          กำแพงใกล้กว่า = ไม่โดน ; แม็ก/รีโหลดตามปืน ; โดนยิง = ช้าลง ×0.275 ฟื้นใน 0.5 วิ (tagging)
  ได้ยิน    เท้าวิ่ง FOOTSTEP_R 32 ม. (ถูกบัง ×0.6) · ปืนทุกนัด ±3 ม. หลัง 0.3 วิ (ทั้งแมพ) · เริ่มวาง/กู้ spike เฉพาะใน
          SPIKE_SND_R · วางเสร็จ = รู้ทุกตัว · รีโหลด 12 ม. ; เดิน Shift/หมอบเงียบ ; ได้ยิน = ตำแหน่งล่าสุด ±2 ม.
  ทีม      เห็น/โดนยิง/ตาย → เพื่อนได้ตำแหน่งหลัง 0.6–1.2 วิ ; โผล่แวบ ≥ 0.1 วิ = บอทจำจุดนั้น (ส่งหลัง reaction)
  พฤติกรรม hold (มองสลับ ≤ 3 ทิศ) · reposition · swing · rotate · hunt (≤ 1 ตัว) · retake (แบ่งทางเข้า รอที่จุดรวมพล
          แล้วเข้าพร้อมกัน ตัวที่สองตามหลัง 3 ม. ; มีคนปะทะ = เข้าเทรด) · กู้เอง · ฝั่ง DEF: เฝ้าจุด post-plant, ได้ยินกู้
          ยาว ≥ DEFUSE_COMMIT ถึงโผล่ (กู้ครั้งนั้นไม่ทันแล้ว = ไม่สน) — เคลียร์ "บริเวณคนกู้" (จุดยืนกู้ได้ใกล้เสียง) ไม่ใช่
          ตัว spike ; เคลียร์แล้วเสียงยังดัง = ดันเข้าถึง spike ; ทอยไม่ไป (ไกล) แล้วเสียงยังดัง = ทอยใหม่ ·
          โดนยิงไม่เห็นคนยิง = หยุด หันหาผู้ยิง ~1 วิ ทุกสถานะ
  realism v2 (§13 "บอทเล่นเหมือนคน"): เดินทาง = เคลียร์มุมแบบ pie (รังสีระดับตาหาขอบมุมข้างหน้า เล็งขอบระดับหัว) ·
          Shift เดิน 10 ม. สุดท้าย · ยิงกันแล้วหลุดสายตา = ย้าย off-angle / หยุดเฝ้ามุม (ถ้ากำลังเดินทาง) · เพื่อนตาย
          ≤ 12 ม. = ออกเทรด · swing พาเพื่อนตามหลัง 3 ม. · ข้อมูลไกล = collapse ไปจุดเฝ้าที่เห็นบริเวณนั้น (crossfire) ·
          จิ้มไหล่หาข้อมูล · ถอยเมื่ออยู่คนเดียว · ได้ยินเริ่มวาง = ออกหยุด (ไกล = หมุนมา) · เล่นตามเวลา (รอบ/spike
          เหลือน้อย = ไม่โผล่หาเอง) · ตื่นตัวนาน 20 วิ · ส่าย ADAD ระหว่างชุด (ยิงเมื่อเข้า deadzone เท่านั้น) · แตะไกล/
          สเปรย์ใกล้ · รีเทคนัดเข้าพร้อมกัน + คนแรกรอเพื่อนคุมก่อนกู้ · spike บนกล่องกู้จากพื้นข้างกล่อง ·
          ตัวบอทหันตามจุดเล็งด้วย BOT_TURN (ไม่วาร์ปทิศตอนยิง) · เสียงลงพื้นดัง (pv.land_t/land_loud) = เสียงเท้า
  meta ให้ภาพ/เสียง (§13.2): yaw pitch vel (vx, vz) walk (ไม่วิ่ง = เงียบ) reload air (ลอย/กำลังตก) state_s
  ตำแหน่งเสียงจากโหมด (on_player_reload/on_plant_start/on_defuse_start/on_bot_*) = (x, z) หรือ (x, y, z) ที่ y ใดก็ได้
          (ตา/เท้า) — ใช้แค่ x, z ; ความสูงต้นเสียง = พื้นใต้ตัว + ค่าคงที่ของเสียงนั้น
งานต่อเฟรม (core_api): nav ≤ 1 งาน/เฟรม — next_waypoint หนึ่งบอท (วนคิว) หรือ DistField.step(500) หนึ่งครั้ง หรือ
astar ≤ 400 โหนด ; ของหนักทำใน prepare() ช่วงนับถอยหลัง ; ตัวเลขฝีมือ/เวลาอยู่ duel.py (ห้ามเดาแก้ — ปรับด้วย sim)
ค่าคงที่ของเสียง/สังเกตเห็น = ค่าประมาณ (ไม่มีตัวเลขทางการ) รวมไว้บล็อกเดียวด้านล่าง ; tools/clutch_sim.py ขับ headless
กำหนดแน่นอน: สุ่มทุกอย่างจาก rng ที่โหมดส่งมา (Stability/cone_offset ที่สุ่มด้วย random ระดับโมดูลเรียกผ่าน _own_random) ;
ไม่วนลูป set/dict ที่คีย์เป็น object — seed + อินพุตเดียวกัน = ผลเดียวกันทุกบิต (selftest 10c, clutch_sim det)"""
import heapq
import itertools
import math
import random
import time

from . import arena, duel, guns, movement
from .clutchmap import BOT_R, PLAYER_R, SAFE_START_R, ClutchMap, FLOOR, H0, VOID, start_seen, testyard
from .config import EYE_Y
from .gunbots import BOT_CROUCH_HOLD, BOT_CROUCH_P, TRAIL_KEEP
from .guns import BODY_HW, BODY_Y0, BODY_Y1, CROUCH_DROP, HEAD_R, HEAD_Y, WALK_KNEE, WEAPONS, Bot
from .stability import Stability, cone_offset, patched_block

# ───────────────── ค่าคงที่ (§10.2 ตารางตรวจแล้ว · §10.3 ยืม CS bot/งานวิจัย — ปรับด้วย clutch_sim ไม่ใช่เดา) ─────────────────
BOT_FOV = 103.0              # องศา FOV แนวนอนของเกม — สังเกตเห็นได้เฉพาะในกรวยนี้รอบ yaw ปัจจุบัน
BOT_TURN = 360.0             # องศา/วิ หันตัว (flick) — 90° ≈ 0.25 วิ ใกล้ CS bot
AIM_CONE = 12.0              # ±องศารอบจุดเล็ง = โมเดล reaction ที่สอบเทียบ (ไม่ต้องทอยสังเกตเห็น)
PREAIM_T = 0.3              # ข้อมูลต้องมาก่อนเห็นอย่างน้อยเท่านี้ถึงนับว่าบอท "เล็งรอ" แล้ว
PREAIM_CONE = 10.0           # ผู้เล่นโผล่ในนี้ + บอทตื่นตัว = "angle" ; เกินนี้บวกเวลาหัน (และ 6 ms/° ถ้าอยู่นอก AIM_CONE)
OFFAIM_S, OFFAIM_CAP = 0.006, 0.25   # รอบนอกสายตาช้าลง ~6 ms/° (PMC3893571) ไม่เกิน 0.25 วิ
NOTICE_DT = 0.25             # ทอยสังเกตเห็นนอกกรวยทุก ๆ (CS bot)
NOTICE_NEAR, NOTICE_FAR = 8.0, 27.0  # ระยะผสมของตารางสังเกตเห็น (CS 300/1000 u ÷ 250 u/s × 6.75 m/s)
STILL_V = 0.6                # ม./วิ — ช้ากว่านี้ = "ยืนนิ่ง" ในตารางสังเกตเห็น
LOS_MAX = 70.0               # ไกลกว่านี้ไม่คิด LOS (งบเฟรม)
SHOULDER_EXTRA = 0.3         # ดริล peek เห็นแค่ไหล่ค้าง: ยิงใส่ส่วนที่เห็นหลัง rt + นี้ (หัวไม่โผล่เลย)
QUICK_PEEK = 0.1             # โผล่ให้บอทที่สังเกตเห็นแล้วเห็นนานเท่านี้ = บอทจำจุด (ส่งหลัง reaction)
FOOTSTEP_R = 32.0            # เสียงเท้าวิ่ง (ม.) — derived: ในรัศมีระเบิด 36 ม. นิดหน่อย ; ห้ามเกิน ~35
BLOCKED_K = 0.6              # เส้นตรงถูกบัง = ระยะได้ยิน × นี้ (ตัวแทนการกรองเสียงของกำแพง)
SPIKE_SND_R = FOOTSTEP_R     # เสียงเริ่มวาง/เริ่มกู้/กำลังกู้ — ได้ยินเฉพาะในรัศมีนี้ (วางเสร็จ = รู้ทุกตัว)
RELOAD_SND_R = 12.0          # เสียงรีโหลด (เดา — ไม่มีตัวเลข)
SHOT_DELAY, SHOT_NOISE = 0.3, 3.0    # เสียงปืน: ทุกตัวรู้ตำแหน่งผู้ยิง ±3 ม. หลัง 0.3 วิ
HEARD_NOISE = 2.0            # ตำแหน่งที่ได้ยิน ±ม.
CALL_NOISE = 1.5             # callout บอกเป็นพื้นที่ ±ม.
CALLOUT_DELAY = (0.6, 1.2)   # วิ — เพื่อนได้ข้อมูลหลังช่วงนี้ (เดา)
TAG_SLOW, TAG_REC = 0.275, 0.5       # โดนยิง = ความเร็ว ×0.275 ฟื้นแบบนุ่มใน ~0.5 วิ (§10.2)
PLANT_T, DEFUSE_T, DEFUSE_HALF, SPIKE_T = 4.0, 7.0, 3.5, 45.0
DEFUSE_R, DEFUSE_DY = 2.4, 1.0       # ระยะกู้แนวราบ / ต่างระดับ (+ ต้องเห็น spike จากตา)
DEFUSE_REACH_UP = 1.6        # ม. spike บนกล่อง (ผู้เล่นกระโดดขึ้นไปวาง §13.1) กู้จากพื้นข้างกล่องได้ถ้าสูงกว่าเท้าไม่เกินนี้
#                              (ในเกมจริงคนกู้ spike บนกล่องจากพื้น ; บอทกระโดดไม่ได้ — ไม่งั้นวางบนกล่อง = กู้ไม่ได้เลย)
KNIFE_SPEED, KNIFE_EQUIP = 6.75, 1.0 # คนวางตาย: บอทวิ่งมีดไปกู้ + เวลาชักของ
DEFUSE_COMMIT = (0.0, 0.8)   # วิ Iron → Radiant: เสียงกู้ต้องยาวเท่านี้บอทถึงยอมโผล่ (กู้หลอก/แตะหลอกฝึกได้)
DEFUSE_MARGIN = 2.0          # รีเทค: เริ่มกู้ให้ทันต้องเหลือ ≥ เดินถึง + 7 + นี้
DEFUSE_RINGS = (0.0, 0.8, 1.6, 2.3)  # ม. วงรอบ spike ที่วางจุดตัวอย่างยืนกู้ (≤ DEFUSE_R ; ห่างกันตามวง ~0.9 ม.)
CLEAR_NEAR = 0.8             # จุดยืนกู้ที่ "น่าจะเป็น" = ห่างจุดที่ได้ยิน ≤ HEARD_NOISE + นี้
CLEAR_FRAC = 0.75            # เห็นหัว (ระดับยืน) ของจุดยืนกู้ที่น่าจะเป็นเท่านี้ = เคลียร์บริเวณคนกู้แล้ว
PEEK_STOP = 0.9              # โผล่เคลียร์คนกู้: เดินตามทางสู่ spike หยุดเมื่อเห็นบริเวณ หรือถึง spike ในรัศมีนี้
RECOMMIT_T = 1.0             # เคลียร์แล้ว (ไม่เห็นใคร) แต่เสียงกู้ยังดังนานเท่านี้ = ดันเข้าไปถึง spike
RECOMMIT_SKIP = 2.0          # ทอยไม่โผล่ (ไกล) แต่เสียงกู้ยังดังนานเท่านี้ = ทอยใหม่ (โอกาสตามระยะเดิม)
PUSH_MAX = 3                 # ดัน/ทอยใหม่ได้ไม่เกินนี้ต่อการกู้หนึ่งครั้ง
TAG_TURN = 1.0               # โดนยิงแต่ไม่เห็นคนยิง: หยุด หันหาผู้ยิงนานเท่านี้หลังนัดล่าสุด (ทับทิศมองของทุกสถานะ)
GLANCE, GLANCE_OP = (1.0, 2.0), (5.0, 10.0)   # คนเฝ้าสลับทิศมองทุก ๆ (Op นานกว่า)
RELOAD_LOW = 0.4             # ว่างมือ (ไม่ปะทะ) และกระสุน < 40% แม็ก = รีโหลด
RELOAD_IDLE = 2.0            # ไม่ปะทะนานเท่านี้ถึงนับว่าว่าง
ROTATE_FAR = 25.0            # ห่างเป้าหมายเกินนี้ตอนเกิด = หมุนเข้าหาเป้า
RUN_FAR = 20.0               # หมุน: ห่างตำแหน่งล่าสุดของผู้เล่นเกินนี้วิ่ง ไม่งั้นเดินเงียบ
DEST_R = 18.0                # จุดเฝ้าปลายทางของตัวที่หมุนมา ต้องอยู่ใกล้เป้าหมายไม่เกินนี้
RETAKE_WALK = 15.0           # รีเทค: 15 ม. สุดท้ายเดิน
RETAKE_STAGGER = (0.0, 3.0)  # เริ่มรีเทคห่างกัน
PLAN_WAIT = 3.0              # รีเทค: รอสนามระยะ spike/จุดรวมพลเสร็จนานสุดเท่านี้ก่อนวางแผนด้วยค่าประมาณ
ENTRY_R = 12.0               # ทางเข้าไซต์ = จุดที่เส้นทางเข้าใกล้ศูนย์ไซต์ถึงระยะนี้
STAGE_BACK, STAGE_BACK_MAX = 7.0, 14.0   # จุดรวมพล = ถอยจากทางเข้าตามเส้นทาง (ต้องไม่เห็นจาก spike)
SPREAD_PEN = 10.0            # ม. — ค่าปรับต่อบอทที่อยู่ทางเข้าเดียวกันแล้ว (กระจายทางเข้า)
TRADE_GAP = 3.0              # ตัวที่สองในทางเข้าเดียวกันตามหลัง (ม.)
STAGE_WAIT = (3.0, 9.0)      # วิ Iron → Radiant รอเพื่อนที่จุดรวมพลนานสุดหลังตัวแรกถึง
TRICKLE_P = (0.6, 0.05)      # โอกาสใจร้อนเข้าเลยไม่รอเพื่อน (แรงค์ต่ำไหลเข้าทีละตัว)
GO_JITTER = (1.2, 0.2)       # ความไม่พร้อมกันตอนเข้า (วิ)
RETAKE_SYNC = (0.3, 1.0)     # Iron → Radiant: สัดส่วนของส่วนต่างเวลาเดินที่กลุ่มใกล้รอกลุ่มไกล (เข้าไซต์พร้อมกัน) — เดา
COVER_WAIT = (0.0, 4.0)      # วิ Iron → Radiant: ถึง spike คนแรก (ไม่รู้ตำแหน่งคนวาง) รอเพื่อนเข้ามาคุมก่อนกู้นานสุด — เดา
RETAKE_SYNC_MAX = 8.0        # วิ รอกลุ่มไกลนานสุด
CONTACT_HOLD = (1.5, 3.0)    # หลุดสายตาแล้วค้างเล็งจุดนั้นก่อนทำอย่างอื่น
ENGAGE_GAP = 1.5             # หลุดสายตาเกินนี้แล้วเห็นใหม่ = การปะทะใหม่ (spotted, สุ่มเล็งหัวใหม่)
REPEEK_T = 8.0               # เห็นใหม่ที่จุดเดิม (≤ 3 ม.) ภายในนี้ = "angle"
ALERT_KEEP = 6.0             # ข้อมูลอายุไม่เกินนี้ = ตื่นตัว เล็งรอทางที่ข้อมูลมา
ALERT_LONG, ALERT_LONG_P = 20.0, 0.7   # เก่ากว่านั้นแต่ไม่เกินนี้ = ยังเฝ้าทางนั้นเป็นหลัก (70% ของรอบมอง) — คนที่ได้ยินการยิง
#                                        ใกล้ ๆ ไม่กลับไปมองเรื่อยเปื่อยใน 6 วิ (C6: ไม่ลดระดับการตื่นตัว) ; เดา — ปรับด้วย sim
NEW_INFO_T, NEW_INFO_D = 4.0, 6.0    # ข้อมูลใหม่ (ห่างเวลา/ระยะจากเดิม) = ตัดสินใจพฤติกรรมใหม่
SWING_MAX = 15.0             # swing ไปจุดข้อมูลที่ไม่ไกลกว่านี้
REPO_R, REPO_P = 6.0, 0.2    # ย้ายจุดเฝ้า ≤ 6 ม.
HUNT_K, HUNT_D, HUNT_WALK = 0.5, 54.0, 40.0   # ล่า: p = K·(1−d/54)·(1−min(.5, .05·เพื่อน)) ไม่ไกลกว่า 40 ม.
AGGR = (0.08, 0.35)          # ความก้าวร้าวต่อตัว (โอกาส swing เมื่อได้ข้อมูล)
STOP_LEAD = 0.08             # หยุด (counter-strafe) ก่อนจังหวะยิงเท่านี้
STUCK_GIVEUP = 2.8           # วิ เดินไม่คืบ 0.3 ม. นานเท่านี้ (หลังถอยออกแล้ว) = ล้มเลิกทางนี้ (sim ตรวจติด > 3 วิ)
ASTAR_NODES = 400            # งบ astar ในเฟรม (core_api)
FIELD_STEP = 500             # งบ DistField.step ในเฟรม
FIELD_MAX = 10               # จำ DistField ไม่เกินนี้ (ด่านจริง ~2 MB/ตัว)
WP_REFRESH = 0.3             # ขอ waypoint ใหม่ทุก ๆ (ถึงจุดก่อน = ขอด่วน)
SHOT_RANGE = 80.0            # ปลายเส้นกระสุนที่ไม่ชนอะไร (เส้น tracer)
# ── realism pass v2 (§13 — "บอทเล่นเหมือนคน") : ค่าประมาณจากนิสัยคนเล่นจริง/CS bot (เดา = ปรับด้วย clutch_sim) ──
LAND_R = FOOTSTEP_R          # เสียงลงพื้นหลังกระโดด/ตก (§13.1: ได้ยินใน FOOTSTEP_R เว้นแต่กด Shift ตอนลง = land_loud False)
CORNER_DT = 0.25             # เดินอยู่: สแกนหามุมอับข้างหน้าทุก ๆ (วิ/บอท ; หนึ่งบอทต่อเฟรม — งบรังสี)
# มุมรังสีสแกน (องศารอบทิศเดิน ระดับตา) — ถี่ใกล้ทิศเดิน (ประตูไกลเห็นเป็นมุมแคบ) ห่างที่ข้าง ; ขอบที่ระยะกระโดดจากใกล้→ไกล
# และรังสีไกลทะลุแนวผนัง = มุมที่คนอาจเฝ้า
CORNER_FAN = (-65.0, -48.0, -34.0, -23.0, -14.0, -8.0, -3.5, 0.0, 3.5, 8.0, 14.0, 23.0, 34.0, 48.0, 65.0)
CORNER_RANGE = 22.0          # ม. ความยาวรังสีสแกน (มุมไกลกว่านี้ยังไม่ต้องเช็ค)
CORNER_JUMP = 4.0            # ม. ระยะที่ต่างกันระหว่างรังสีข้างกันถึงนับเป็น "ขอบมุม"
CORNER_NEAR = 16.0           # ม. ขอบมุมต้องใกล้กว่านี้ (ไกลกว่า = ยังไม่ต้องเล็ง)
CORNER_CLEAR = 0.35          # วิ เห็นจุดหลังมุมนานเท่านี้ = เคลียร์แล้ว (เท่ากับผู้เล่นสคริปต์ของ sim)
CORNER_MEMO = 8.0            # วิ มุมที่เคลียร์แล้วไม่เช็คซ้ำ (CS bot 10 วิ — ทางเดินเราสั้นกว่า)
CORNER_MAX = 2.5             # วิ เล็งมุมเดียวนานสุด (แล้วหามุมใหม่)
WALK_LAST = 10.0             # ม. หมุน/เดินทางโดยไม่รู้ว่าผู้เล่นอยู่ไหน: ทางที่เหลือถึงปลายทางน้อยกว่านี้ = Shift เดิน (เงียบ)
TRADE_R = 12.0               # ม. เพื่อนตายในระยะนี้ = เข้าเทรดได้ (เห็น/ได้ยินเพื่อนตายทันที ไม่ต้องรอ callout)
TRADE_P = (0.30, 0.80)       # โอกาสเทรด Iron → Radiant (E9: เทรด 14% ของการตายทั้งรอบในล็อบบี้ผู้ใช้ — ในระยะใกล้สูงกว่า)
TRADE_DELAY = ((0.6, 1.6), (0.2, 0.7))   # วิ Iron → Radiant ก่อนออกเทรด (ตัดสินใจ + หันออก)
FOLLOW_P = (0.15, 0.45)      # โอกาสที่เพื่อนใกล้ (≤ FOLLOW_R) ตามไปด้วยตอนตัวหนึ่ง swing — เว้นระยะเทรด TRADE_GAP
FOLLOW_R = 10.0
SWAP_P = (0.15, 0.55)        # หลุดสายตาหลังยิงกัน: โอกาสย้ายจุดเฝ้า (off-angle ใหม่) แทนเฝ้า/โผล่จุดเดิม
SWAP_R = (2.5, 6.0)          # ม. ระยะจุดใหม่ (ต้องยังเห็นบริเวณเดิมของผู้เล่น)
JIGGLE_P = (0.10, 0.45)      # ส่วนของ swing ที่เป็นแค่จิ้มไหล่หาข้อมูล (แรงค์สูงจิ้มบ่อย)
JIGGLE_T = (0.25, 0.45)      # วิ ออกไปนานเท่านี้แล้วกลับ
FALLBACK_P = 0.15            # ได้ข้อมูลใกล้ (≤ SWING_MAX) และไม่มีเพื่อนใกล้ = ถอยไปจุดเฝ้าลึกกว่า
DEATH_SWING_K = 0.25         # ข้อมูลจากเพื่อนตาย (พ้นช่วงเทรด): โอกาส swing ×นี้ (ไม่ dry-peek มุมที่ผู้เล่นเล็งรออยู่)
ADAD_P = (0.0, 0.55)         # ระหว่างชุด (ปืนออโต้): โอกาสส่าย ADAD Iron → Radiant แล้ว counter-strafe ก่อนชุดถัดไป
ADAD_T = (0.12, 0.22)        # วิ ส่ายนานเท่านี้ต่อครั้ง
BURST_FAR, BURST_NEAR = 22.0, 7.0   # ม. ไกลกว่า = แตะ (ชุด ≤ ครึ่ง) ; ใกล้กว่า = สเปรย์ (+SPRAY_ADD นัด)
SPRAY_ADD = 3
LATE_T = 20.0                # วิ ฝ่ายรับ (ผู้เล่น ATK ก่อนวาง): เวลารอบเหลือน้อยกว่านี้ = เวลาเป็นของเรา ไม่ swing/ล่า
POST_LATE_T = 15.0           # วิ ฝ่ายบุกหลังวาง (ผู้เล่น DEF): spike เหลือน้อยกว่านี้ = เล่นเวลา ไม่ swing ตามเสียง
EARLY_T = 45.0              # วิ เหลือมากกว่านี้ = เล่นเฉย (ล่า ×0.5)
COLLAPSE_P = (0.25, 0.60)    # ได้ข้อมูลไกลเกิน swing: โอกาสย้ายไปจุดเฝ้าที่เห็นบริเวณนั้น (ตั้ง crossfire) Iron → Radiant
COLLAPSE_D = (10.0, 40.0)    # ม. ระยะข้อมูลที่ทำแบบนี้ (ใกล้กว่า = swing/เฝ้า ; ไกลกว่า = ไม่เกี่ยว)
COLLAPSE_GAP = 8.0           # วิ ต่อบอท — ไม่วิ่งวนตามข้อมูลทุกชิ้น
PLANT_SWING_P = (0.55, 0.85)   # ได้ยินเสียงเริ่มวาง (≤ PLANT_SWING_R): โอกาสออกไปหยุดการวาง Iron → Radiant — เดา
PLANT_SWING_R = 28.0           # ม. (วิ่ง 5.4 ม./วิ ~4 วิ = เวลาวาง)
PLANT_ROT_R = 20.0          # ม. ได้ข่าว "กำลังวาง" แล้วอยู่ไกลกว่านี้ = หมุนไปไซต์นั้น (วิ่ง)
BOT_GRAVITY = 18.9           # ม./วิ² ตกขอบ (§13.1 clutchscen.GRAVITY ของผู้เล่น — UNVERIFIED ; ให้บอทตกเท่าผู้เล่น)
FOV_HALF = math.radians(BOT_FOV / 2.0)
_TWO_PI = 2.0 * math.pi
# น้ำหนัก "ส่วนตัวที่โผล่" ของจุดตัวอย่าง (CS: อก 40 หัว 10 ข้างละ 20 เท้า 10) — ลำดับเดียวกับ body_points
PT_W = (0.05, 0.40, 0.20, 0.20, 0.025, 0.025, 0.10)


def _lerp(a, b, u):
    return a + (b - a) * u


def _wrap(a):
    return (a + math.pi) % _TWO_PI - math.pi


def _xz(p):
    return float(p[0]), float(p[2] if len(p) > 2 else p[1])


def body_points(eye, x, z, feet=0.0, crouch=0.0):
    """จุดตัวอย่าง 7 จุดบนหุ่นที่ (x, z) ยืนบนพื้น feet — ข้างหัว/ไหล่ออฟเซ็ต "ตั้งฉากกับแนว eye→ตัว" (humanoid_points
    ออฟเซ็ตตามแกน x ของโลก: มองตามแกน x แล้วไหล่ยุบทับแนวสายตา) ; เรียง หัว, อก, ไหล่ซ้าย/ขวา, ข้างหัว, สะโพก
    (หัว/อกก่อน — any_visible หยุดที่จุดแรกที่เห็น) ; ใช้ได้ทั้งบอทมองผู้เล่นและผู้เล่นมองบอท"""
    drop = CROUCH_DROP * crouch - feet
    dx, dz = x - eye[0], z - eye[2]
    L = math.hypot(dx, dz)
    if L < 1e-6:
        px, pz = 1.0, 0.0
    else:
        px, pz = dz / L, -dx / L
    hy, sy = HEAD_Y - drop, BODY_Y1 - 0.06 - drop
    return [(x, hy, z), (x, (BODY_Y0 + BODY_Y1) / 2 - drop, z),
            (x - px * BODY_HW, sy, z - pz * BODY_HW), (x + px * BODY_HW, sy, z + pz * BODY_HW),
            (x - px * HEAD_R, hy, z - pz * HEAD_R), (x + px * HEAD_R, hy, z + pz * HEAD_R),
            (x, BODY_Y0 - drop, z)]


def _step_on(cm, df, wp, x, z):
    """next_waypoint คืนโหนดเริ่มที่อยู่ห่างตัว < 0.3 ม. ได้ (ตัวเยื้องจากโหนดเล็กน้อยตรงปลายกำแพง แล้วโหนดถัดไปในสาย
    เดินตรงไม่ผ่าน walk_clear) — ถ้าเดินไปจุดนั้นจะไม่คืบเลย ; ให้มุ่งโหนดถัดไปในสายแทน (move ไถลผ่านมุมได้ ; ขอบ
    nav s→n เดินตรงได้จากตัวโหนด)"""
    if wp is df.goal or (wp[0] - x) ** 2 + (wp[1] - z) ** 2 >= 0.09:
        return wp
    n = cm.nav_node(wp[0], wp[1])
    if n is None or df.nxt[n] < 0:
        return wp
    p = cm.nav_pos(df.nxt[n])
    return (p[0], p[2])


def _nearest_node(cm, df, x, z):
    """โหนด nav ที่ใกล้สุดซึ่ง DistField รู้ระยะแล้ว (ห่าง > 5 ซม.) — ใช้เมื่อ next_waypoint คืน None (ไม่มีโหนดเดินตรงถึง)"""
    for dz in (0.0, 0.5, -0.5):
        for dx in (0.0, 0.5, -0.5):
            n = cm.nav_node(x + dx, z + dz)
            if n is not None and df.fin[n]:
                p = cm.nav_pos(n)
                if (p[0] - x) ** 2 + (p[2] - z) ** 2 > 0.0025:
                    return (p[0], p[2])
    return None


def burst_gap(weapon, m, burst=None):
    """ช่วงถึงนัดถัดไปของบอท = เลขชุดเดียวกับ gunbots.gun_bot_gap (แยกเป็นฟังก์ชันไม่พึ่ง Game — selftest เทียบกัน):
    ปืนออโต้ยิงชุดละ m['p']['burst'] นัดตาม rps แล้วพัก BURST_PAUSE ; ปืนนัดเดียวแตะตาม tap efficiency
    burst = ขนาดชุดที่ใช้แทน (clutch: แตะที่ไกล/สเปรย์ที่ใกล้ — _fire_ctl) ; None = ของระดับ"""
    w = WEAPONS[weapon]
    if w["auto"]:
        m["burst_i"] += 1
        if m["burst_i"] >= (m["p"]["burst"] if burst is None else burst):
            m["burst_i"] = 0
            return max(duel.BURST_PAUSE, 1.0 / w["rps"])
        return 1.0 / w["rps"]
    tap = (patched_block(weapon) or {}).get("tap_eff") or w["rps"]
    return 1.0 / min(w["rps"], tap)


class PlayerView:
    """ภาพผู้เล่นที่บอทรู้ได้ — โหมดเติมทุกเฟรม (ค่าธรรมดา) ; run_speed = ความเร็ววิ่งของปืนตอนนี้ (รวม ADS) ใช้แบ่ง
    เดิน/วิ่ง (เสียงเท้า) และ deadzone (peeker's advantage)"""

    def __init__(self, x=0.0, z=0.0, feet=0.0, crouch=0.0, vx=0.0, vz=0.0, run_speed=guns.RUN_SPEED, alive=True,
                 weapon="vandal", planting=False, defusing=False, spike_out=False, air=False, land_t=-9.0,
                 land_loud=False, on_box=False):
        self.x, self.z, self.feet, self.crouch = x, z, feet, crouch
        self.vx, self.vz, self.run_speed = vx, vz, run_speed
        self.alive, self.weapon = alive, weapon
        self.planting, self.defusing, self.spike_out = planting, defusing, spike_out
        # §13.2 (ทีม MOVE เติม): ลอยอยู่ · เวลาลงพื้นล่าสุด (−9 = ยังไม่เคย) · การลงครั้งนั้นมีเสียง · ยืนบนกล่อง —
        # สมองอ่านด้วย getattr(..., ค่าเริ่ม) เสมอ (PlayerView สำรองของโหมดอาจไม่มีฟิลด์เหล่านี้)
        self.air, self.land_t, self.land_loud, self.on_box = air, land_t, land_loud, on_box

    def eye(self):
        return (self.x, self.feet + EYE_Y - CROUCH_DROP * self.crouch, self.z)

    def speed(self):
        return math.hypot(self.vx, self.vz)


class ClutchBrain:
    """ทีมบอท 1..5 ตัวของฉากหนึ่ง (§11.1) — side = ฝั่ง "ผู้เล่น": 'atk' → บอทเป็นฝ่ายรับก่อนวาง (+ รีเทคหลังวาง),
    'def' → บอทเป็นฝ่ายบุกหลังวาง (spike อยู่ scen['k']) ; placement 'real' = ตำแหน่งในฉาก, 'holds' = สุ่มจุดเฝ้ายอดนิยม"""

    def __init__(self, cmap, scen, side, tier, weapon, rng=None, t0=0.0, placement="real"):
        self.cm = cmap
        self.scen = scen
        self.side = "def" if side == "def" else "atk"
        self.tier = int(tier)
        self.u = max(0.0, min(1.0, self.tier / float(duel.TOP)))
        self.rng = rng if rng is not None else random.Random()
        # Stability/cone_offset (โค้ดร่วมกับปืนผู้เล่น) สุ่มด้วย random ระดับโมดูล — บอทใช้สถานะ global ของตัวเองที่แตกจาก rng
        # (_own_random) : seed เดียวกัน = รอบเดียวกันเสมอ ไม่ว่าเกม/ผู้เล่นกินเลขสุ่ม global ไปเท่าไร และบอทก็ไม่กระทบของเกม
        self._gstate = random.Random(self.rng.getrandbits(64)).getstate()
        self.t0 = self.t = float(t0)
        # บอท Op ยังไม่สอบเทียบ (สเปรด hipfire/จังหวะโบลต์) → ถือ Vandal แบบ gun_bot_weapon ของ GUNFIGHT
        self.bot_weapon = weapon if weapon in WEAPONS and weapon != "operator" else "vandal"
        self.P = {d: duel.tier_params(self.tier, self.bot_weapon, d) for d in ("duel", "peek", "angle")}
        self.site = scen.get("s") or next(iter(cmap.sites), None)
        self.events = []
        self._ev_out = []                   # events จาก on_* นอก update → ส่งพร้อม update ถัดไป
        self._trail = []                    # [(t, x, z, feet, crouch)] ผู้เล่นย้อนหลัง TRAIL_KEEP วิ
        self._q = []                        # heap ข้อมูลที่รอส่ง (t, seq, idx, x, z, kind)
        self._seq = itertools.count()
        self._fields = {}                   # key → DistField
        self._pending = []                  # DistField ที่ยังไม่เสร็จ (ทำทีละ step)
        self._pinned = set()
        self._nav_ok = False
        self.ready = False
        self._plast = -9.0                  # เวลาเสียงเท้าวิ่งผู้เล่นครั้งล่าสุด
        self._snd_chk = 0.0
        self._pre_rr = 0
        self.plant_snd = None
        self.defuse_snd = None
        self.hunter = None
        self.retake = None
        self.defused = False
        self.bot_banked = 0.0
        self._defuser = None
        self.spike = None                   # (x, z) เมื่อรู้ตำแหน่ง spike ; spike_y = พื้นใต้
        self.spike_y = 0.0
        self.spike_goal = None              # จุดเป้า nav ไปกู้ (_spike_goal)
        self._dspots = None                 # (spike, [จุดหัวของที่ยืนกู้ได้]) แคชต่อ spike
        self.explode_t = None
        self._land_heard = -9.0             # land_t ของการลงพื้นที่ประมวลเสียงไปแล้ว
        self.beh = {}                       # นับพฤติกรรมที่เกิด (sim/รายงาน: เทรด/ย้ายจุด/ส่าย ฯลฯ ต่อรอบ)
        self._corner_rr = 0
        # ผู้เล่น ATK ก่อนวาง: หมดเวลารอบ = ฝ่ายรับ (บอท) ชนะ — ใช้เล่นตามเวลา (§13 time-awareness)
        self.round_end = self.t0 + float(scen.get("left", 100.0)) if self.side == "atk" else None
        if self.side == "def" and scen.get("k"):
            self._set_spike(scen["k"])
            self.explode_t = self.t0 + float(scen.get("left", SPIKE_T))
        sc = cmap.sites.get(self.site) or {}
        c = sc.get("c") or (scen.get("k") or [0.0, 0.0])
        self.obj = self.spike if self.spike is not None else (float(c[0]), float(c[1]))
        self.bots = []
        for k, (x, z, yaw) in enumerate(self._placements(placement)):
            self.bots.append(self._spawn(k, x, z, yaw))
        for b in self.bots:
            if math.hypot(b.x - self.obj[0], b.z - self.obj[1]) > ROTATE_FAR:
                b.meta["role"] = "rotator"
                b.meta["state"] = "rotate"

    # ───────────────────────── ตั้งต้น ─────────────────────────
    def _own_random(self, fn, *a, **kw):
        """เรียก fn ขณะ random ระดับโมดูลเป็นสถานะของบอท (สลับเข้า-คืนรอบละ ~10 µs — เฉพาะตอนสร้างบอท/ยิง)"""
        saved = random.getstate()
        random.setstate(self._gstate)
        try:
            return fn(*a, **kw)
        finally:
            self._gstate = random.getstate()
            random.setstate(saved)

    def _set_spike(self, p):
        """spike ที่ (x, z) — y = พื้นใต้ (หลังกล่องถ้าวางบนกล่อง §13.1 ; ไม่ใช้ y ที่ส่งมาเว้นแต่หาไม่ได้) ;
        spike_goal = จุดที่บอทเดินไปกู้ (บนกล่อง = พื้นข้างกล่องที่เอื้อมถึง)"""
        x, z = float(p[0]), float(p[1] if len(p) == 2 else p[2])
        self.spike = (x, z)
        self.spike_y = self._spike_floor(x, z, float(p[1]) if len(p) > 2 else 0.0)
        self.spike_goal = self._spike_goal(x, z, self.spike_y)

    def _spike_floor(self, x, z, fallback=0.0):
        fy = self.cm.floor_y(x, z)
        if fy is not None:
            return fy
        c = self.cm.cell_of(x, z)
        if c is not None:
            top = self.cm.top_y(c[0], c[1])
            if top != float("inf"):
                return top                           # หลังกล่อง (BOX) — ผู้เล่นกระโดดขึ้นไปวาง
        return fallback

    def _reach_ok(self, feet, sy):
        """ระดับเท้า feet กู้ spike ที่ระดับ sy ได้ไหม: spike สูงกว่าเท้าไม่เกิน DEFUSE_REACH_UP (เอื้อมกู้บนกล่องจากพื้น) ;
        ต่ำกว่าไม่เกิน DEFUSE_DY"""
        return -DEFUSE_DY <= sy - feet <= DEFUSE_REACH_UP

    def _spike_goal(self, sx, sz, sy):
        """จุดเป้า nav สำหรับไปกู้: ตัว spike ถ้ายืนบนพื้นตรงนั้นได้และระดับเข้าเกณฑ์ ; ไม่งั้น (วางบนกล่อง — บอทกระโดดไม่ได้)
        = จุดพื้นใกล้สุดในวง ≤ DEFUSE_R − 0.5 ที่ยืนได้ (BOT_R) ระดับเอื้อมถึง และตาเห็น spike ; ไม่มีเลย = ตัว spike"""
        cm = self.cm
        fy = cm.floor_y(sx, sz)
        if fy is not None and self._reach_ok(fy, sy) and cm.disc_clear(sx, sz, BOT_R):
            return (sx, sz)
        tgt = (sx, sy + 0.15, sz)
        for r in (0.6, 0.9, 1.2, 1.5, DEFUSE_R - 0.5):
            for k in range(16):
                a = _TWO_PI * k / 16
                x, z = sx + r * math.sin(a), sz + r * math.cos(a)
                f = cm.floor_y(x, z)
                if (f is not None and self._reach_ok(f, sy) and cm.disc_clear(x, z, BOT_R + 0.05)
                        and not cm.blocked((x, f + EYE_Y, z), tgt)):
                    return (x, z)
        return (sx, sz)

    def _placements(self, placement):
        """[(x, z, yaw)] จุดเกิดบอท — 'real' = scen['e'] ; 'holds' = สุ่มถ่วงน้ำหนักจากจุดเฝ้า (ไม่พอ = เติมจาก scen['e']
        แล้วจุดสุ่มบนพื้นรอบเป้า 8–30 ม.)"""
        e = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in (self.scen.get("e") or [])]
        if placement != "holds":
            return e
        n = int(self.scen.get("n") or len(e) or 1)
        kind = "def" if self.side == "atk" else "atk_post"
        pool = [list(h) for h in ((self.cm.holds.get(self.site) or {}).get(kind) or [])]
        out = []
        rng = self.rng

        p0 = self.scen.get("p")

        def far(x, z):
            """ห่างบอทตัวอื่น ≥ 2 ม. + ไม่ใช่จุดที่ทำให้ผู้เล่น "เกิดกลางดง" (ใกล้ < 10 ม. หรือเห็นผู้เล่นตั้งแต่เริ่ม —
            clutchmap.start_safe ; รายงานผู้ใช้ 2026-09-28)"""
            if not all(math.hypot(x - o[0], z - o[1]) >= 2.0 for o in out):
                return False
            if p0 and (math.hypot(x - p0[0], z - p0[1]) < SAFE_START_R or start_seen(self.cm, p0[0], p0[1], [(x, z)])):
                return False
            return True
        while pool and len(out) < n:
            w = [max(0.01, float(h[3])) if len(h) > 3 and h[3] is not None else 1.0 for h in pool]
            h = rng.choices(pool, weights=w)[0]
            pool.remove(h)
            if far(h[0], h[1]):
                out.append((float(h[0]), float(h[1]), float(h[2])))
        for p in e:
            if len(out) >= n:
                break
            if far(p[0], p[1]):
                out.append(p)
        tries = 0
        while len(out) < n and tries < 2000:
            tries += 1
            a, r = rng.uniform(0, _TWO_PI), rng.uniform(8.0, 30.0)
            x, z = self.obj[0] + r * math.sin(a), self.obj[1] + r * math.cos(a)
            if self.cm.disc_clear(x, z, BOT_R + 0.1) and far(x, z):
                out.append((x, z, math.atan2(self.obj[0] - x, self.obj[1] - z)))
        return out

    def _spawn(self, k, x, z, yaw):
        cm = self.cm
        fy = cm.floor_y(x, z)
        x, z, s = cm.move(x, z, fy if fy is not None else 0.0, [0.0, 0.0], 0.0, BOT_R)   # เกิดทับของแข็ง = ดันออก
        feet = s if s is not None else (fy or 0.0)
        b = Bot(x, z)
        b.y0 = feet
        b.weapon = self.bot_weapon
        b.stab = self._own_random(Stability, b.weapon, WEAPONS[b.weapon]["rps"])
        b.born = None
        b.exposed = False
        rng = self.rng
        P = self.P["duel"]
        yaw = _wrap(yaw)
        fac = self._facings(x, z, feet, yaw)
        b.meta = m = {
            "idx": k, "tier": self.tier, "p": P, "aim_head": rng.random() < P["head_p"],
            "run_shoot": rng.random() < P["run_shoot"], "aggr": rng.uniform(*AGGR),
            "yaw": yaw, "pitch": 0.0, "look": None, "state": "hold", "role": "anchor", "sub": "",
            "home": (x, z, yaw), "facings": fac, "fpitch": [self._face_pitch(x, z, feet, f) for f in fac],
            "glance_i": 0, "glance_t": self.t0 + rng.uniform(*self._glance()),
            # สายตา / การปะทะ
            "vis": False, "vis_t0": None, "sees": False, "noticed": False, "notice_t": None, "roll_t": 0.0,
            "fire_at": None, "rt_wait": None, "next_shot": 0.0, "burst_i": 0, "e0": None, "t_first": None, "crouch_fire": False,
            "crouch_until": None, "last_seen_end": -99.0, "seen_pos": None, "seen_t": -99.0, "peek_q": False,
            "force_notice": -99.0, "contact_t": -99.0, "contact_hold": 0.0, "repeek_at": None, "rt_last": None,
            # ข้อมูล
            "know": None, "alert_t": -99.0, "alert0": -99.0, "preaim": None, "preaim_dirty": False, "heard_t": -99.0,
            "shot_q_t": -99.0, "call_t": -99.0, "psnd": False, "dsnd": False, "commit_at": None, "committed": None,
            "dpos": None, "cand": None, "push": False, "dclr_t": None, "dskip": False, "pushes": 0,
            # ปืน / ตัว
            "mag": WEAPONS[b.weapon]["mag"], "reload_until": 0.0, "tag_t": -99.0, "hit_from": None, "vfall": 0.0,
            "air": False,
            "step_t": -9.0, "defusing": None,
            # การเดิน
            "go": None, "run": False, "brake": False, "final": False, "nav": None, "wp": None, "wp_t": -99.0,
            "wp_retry": 0.0, "wp_fail": 0, "astar_req": None, "path_i": 0, "dest": None, "prog": (self.t0, x, z),
            "until": 0.0, "target": None, "pl_t": -99.0, "pl": None, "moving": False, "esc": None,
            # retake
            "rtp": None, "go_at": None, "stage": None, "entry": None, "start_t": 0.0, "order": 0, "trickled": False,
            # สถิติ
            "shots": 0, "hits": 0, "heads": 0, "spotted": 0, "dead_t": None,
            # §13.2 ให้ภาพ (โหมด → clutch_view) : ความเร็ว ม./วิ · เดินเงียบ (ไม่วิ่ง) · กำลังรีโหลด
            "vel": (0.0, 0.0), "walk": False, "reload": False,
            # realism v2: เช็คมุมระหว่างเดิน · เทรด · ส่าย ADAD · จิ้ม · ชุดยิงตามระยะ
            "corner": None, "corner_t": self.t0 + rng.uniform(0.0, CORNER_DT), "cleared": [], "trade_at": None,
            "trade_pos": None, "adad": None, "adad_dir": 1.0 if rng.random() < 0.5 else -1.0, "jig_until": None,
            "follow": None, "swap_at": None, "strafe": None, "collapse_t": -99.0, "glance_pre": False,
            "hold_try": None, "at_spike_t": 0.0, "esc_n": 0,
        }
        return b

    def _glance(self):
        return GLANCE_OP if self.bot_weapon == "operator" else GLANCE

    def _facings(self, x, z, feet, yaw0):
        """ทิศมองสลับของคนเฝ้า (≤ 3): ทิศจริงของฉาก + ทิศ yaw/yaw2 ของจุดเฝ้า bake ที่ใกล้สุด ≤ 3 ม. ; ไม่มี yaw2 (ด่านที่
        ยังไม่ bake ทิศที่สอง/testyard) = ช่องเปิดใกล้ทิศจริง (รังสีแนวระดับตา ±75° ยอดท้องถิ่นที่โล่ง ≥ 8 ม.)"""
        out = [yaw0]

        def add(y):
            if y is None or len(out) >= 3:
                return
            y = _wrap(float(y))
            if all(abs(_wrap(y - o)) > math.radians(20) for o in out):
                out.append(y)
        best = None
        for hd in (self.cm.holds or {}).values():
            for rows in (hd or {}).values():
                for h in rows or ():
                    d = math.hypot(h[0] - x, h[1] - z)
                    if d <= 3.0 and (best is None or d < best[0]):
                        best = (d, h)
        if best is not None:
            h = best[1]
            add(h[2])
            add(h[4] if len(h) > 4 else None)
        if len(out) < 2:
            eye = (x, feet + EYE_Y, z)
            n = 21
            rays = []
            for k in range(n):
                yw = yaw0 + math.radians(-75.0 + 150.0 * k / (n - 1))
                r = self.cm.ray(eye, (math.sin(yw), 0.0, math.cos(yw)), 40.0)
                rays.append((yw, 40.0 if r is None else r))
            peaks = []
            for k in range(n):
                yw, r = rays[k]
                lo = rays[k - 1][1] if k > 0 else -1.0
                hi = rays[k + 1][1] if k < n - 1 else -1.0
                if r >= 8.0 and r >= lo and r >= hi:
                    peaks.append((abs(_wrap(yw - yaw0)), yw))
            peaks.sort()
            for _d, yw in peaks:
                if abs(_wrap(yw - yaw0)) >= math.radians(25):
                    add(yw)
        return out

    def _face_pitch(self, x, z, feet, yaw):
        """pitch ที่เล็งระดับหัวของพื้นห่างไป 10 ม. ตามทิศ (ยกพื้น/ร่องมองลงถูกระดับ)"""
        px, pz = x + 10.0 * math.sin(yaw), z + 10.0 * math.cos(yaw)
        fy = self.cm.floor_y(px, pz)
        if fy is None:
            return 0.0
        return math.atan2(fy + HEAD_Y - (feet + EYE_Y), 10.0)

    # ───────────────────────── nav ─────────────────────────
    def _field(self, goal, pin=False):
        key = (round(float(goal[0]), 2), round(float(goal[1]), 2))
        df = self._fields.pop(key, None)
        if df is None:
            df = self.cm.dist_field(key)
            if not df.done:
                self._pending.append(df)
        self._fields[key] = df                       # ใช้ล่าสุด = ท้าย dict (LRU)
        if pin:
            self._pinned.add(key)
        if len(self._fields) > FIELD_MAX:
            used = set()
            for b in self.bots:
                nav = b.meta["nav"]
                if nav is not None and nav[0] == "df":
                    used.add(id(nav[1]))
            for k in list(self._fields):
                if len(self._fields) <= FIELD_MAX:
                    break
                old = self._fields[k]
                if k in self._pinned or id(old) in used or old is df:
                    continue
                del self._fields[k]
                if old in self._pending:
                    self._pending.remove(old)
        return df

    def _setup_nav(self):
        """เรียกครั้งแรกที่มี nav: DistField ของเป้าหมาย + จุดเฝ้าปลายทางของตัวที่หมุน (ทำทีละ step ใน prepare)"""
        self._nav_ok = True
        self.cm.ensure_nav()
        df_obj = self._field(self.obj, pin=True)
        if self.side == "atk":                         # จุดรวมพลรีเทคของไซต์ในฉาก (bake) — ทำล่วงหน้าตอนนับถอยหลัง
            for e in self._baked_entries(self.site, "def"):
                self._field(e["stage"], pin=True)
        taken = [b.meta["home"] for b in self.bots if b.meta["role"] != "rotator"]
        for b in self.bots:
            m = b.meta
            if m["role"] != "rotator":
                continue
            h = self._pick_dest(b, taken)
            if h is not None:
                taken.append(h)
                m["dest"] = h
                m["nav"] = ("df", self._field((h[0], h[1]), pin=True), (float(h[0]), float(h[1])), 0.6)
            else:
                m["dest"] = None
                m["nav"] = ("df", df_obj, df_obj.goal, 0.8)

    def _pick_dest(self, b, taken):
        kind = "def" if self.side == "atk" else "atk_post"
        rows = (self.cm.holds.get(self.site) or {}).get(kind) or []
        best = None
        for h in rows:
            if math.hypot(h[0] - self.obj[0], h[1] - self.obj[1]) > DEST_R:
                continue
            if any(math.hypot(h[0] - q[0], h[1] - q[1]) < 3.0 for q in taken):
                continue
            d = math.hypot(h[0] - b.x, h[1] - b.z)
            if best is None or d < best[0]:
                best = (d, h)
        return None if best is None else best[1]

    def prepare(self, max_nodes=FIELD_STEP):
        """งานเตรียม nav แบบหั่นช่วง — เรียกทุกเฟรมตอนนับถอยหลัง ; True = พร้อม (ครั้งแรกสร้างกราฟ nav ถ้ายังไม่มี:
        ด่านจริง ~0.5 วิ — โหมดควรเรียก cmap.ensure_nav() ตอนโหลดด่าน)"""
        if not self._nav_ok:
            self._setup_nav()
            return False
        budget = max_nodes
        while self._pending and budget > 0:
            df = self._pending[0]
            s0 = df.settled
            df.step(budget)
            budget -= max(1, df.settled - s0)
            if df.done:
                self._pending.pop(0)
        self.ready = not self._pending
        return self.ready

    def _nav_tick(self, t):
        """งาน nav หนึ่งงานต่อเฟรม: waypoint ด่วน (ถึงจุดเดิม/ยังไม่มี) → astar ที่ขอไว้ → DistField.step → waypoint ค้าง"""
        urgent = stale = areq = None
        for b in self.bots:
            if not b.alive:
                continue
            m = b.meta
            if m["astar_req"] is not None and areq is None:
                areq = b
            nav = m["nav"]
            if nav is None or nav[0] != "df" or t < m["wp_retry"]:
                continue
            wp = m["wp"]
            near = max(0.35, b.speed() * 0.12)
            if wp is None or (wp is not nav[2] and (b.x - wp[0]) ** 2 + (b.z - wp[1]) ** 2 < near * near):
                if urgent is None or m["wp_t"] < urgent.meta["wp_t"]:
                    urgent = b
            elif t - m["wp_t"] > WP_REFRESH:
                if stale is None or m["wp_t"] < stale.meta["wp_t"]:
                    stale = b
        if urgent is not None:
            self._do_wp(urgent, t)
        elif areq is not None:
            self._do_astar(areq, t)
        elif self._pending:
            df = self._pending[0]
            if df.step(FIELD_STEP):
                self._pending.pop(0)
        elif stale is not None:
            self._do_wp(stale, t)

    def _do_wp(self, b, t):
        m = b.meta
        df = m["nav"][1]
        wp = self.cm.next_waypoint(df, b.x, b.z)
        m["wp_t"] = t
        if wp is None:
            m["wp"] = None
            if df.done:
                m["wp_fail"] += 1
                m["wp_retry"] = t + 0.1
                wp = _nearest_node(self.cm, df, b.x, b.z)
                if wp is not None:                     # ยืนนอกกราฟ (ชิดผนัง/ซอก) — ขยับเข้าหาโหนดใกล้สุดก่อน
                    m["wp"] = wp
            else:
                m["wp_retry"] = t + 0.05              # โหนดแถวนี้ยังไม่ถึงคิวของ DistField
        else:
            m["wp"] = _step_on(self.cm, df, wp, b.x, b.z)
            m["wp_fail"] = 0

    def _do_astar(self, b, t):
        m = b.meta
        tgt, stop_r = m["astar_req"]
        m["astar_req"] = None
        pts = self.cm.astar((b.x, b.z), tgt, ASTAR_NODES)
        if pts is None:
            m["nav"] = ("fail",)
            return
        if self.cm.walk_clear(pts[-1][0], pts[-1][1], tgt[0], tgt[1], BOT_R):
            pts = pts + [tuple(tgt)]
        m["nav"] = ("path", pts, tuple(tgt), stop_r)
        m["path_i"] = 0
        m["prog"] = (t, b.x, b.z)
        m["esc"] = None

    def _nav_df(self, b, goal, stop_r, pin=False):
        m = b.meta
        df = self._field(goal, pin)
        m["nav"] = ("df", df, df.goal, stop_r)
        m["pl"] = None
        m["wp"] = None
        m["wp_retry"] = 0.0
        m["wp_fail"] = 0
        m["prog"] = (self.t, b.x, b.z)
        m["esc"] = None

    def _nav_to(self, b, goal, stop_r=0.6):
        """ใกล้ (≤ 15 ม. ตรง) = astar ≤ 400 โหนด (คิวงานเฟรม) ; ไกล = DistField หั่นช่วง"""
        m = b.meta
        m["esc"] = None
        if math.hypot(goal[0] - b.x, goal[1] - b.z) <= SWING_MAX:
            m["nav"] = ("wait",)
            m["astar_req"] = ((float(goal[0]), float(goal[1])), stop_r)
        else:
            self._nav_df(b, goal, stop_r)

    def _follow(self, b, t):
        """เดินตาม nav ของบอท → 'arrived' / 'moving' / 'wait' / 'fail' (ตั้ง m['go'], m['final'])"""
        m = b.meta
        nav = m["nav"]
        if nav is None or nav[0] == "fail":
            return "fail"
        if nav[0] == "wait":
            return "wait"
        goal, stop_r = nav[2], nav[3]
        if (b.x - goal[0]) ** 2 + (b.z - goal[1]) ** 2 <= stop_r * stop_r:
            return "arrived"
        # ติด: พยายามเดินอยู่ (เฟรมก่อนมีเป้าและไม่ได้เบรก) แต่ 1.5 วิไม่ขยับ 0.3 ม. → ถอยออกจากจุดติด 0.8 ม. นาน 0.7 วิ
        # แล้วขอ waypoint ใหม่ ; STUCK_GIVEUP (2.8 วิ) = ล้มเลิก (รอ DistField/หยุดยิงกันไม่นับ — เดิมนับด้วย บอทรีเทคที่รอสนามระยะเลย
        # "ล้มเหลว" แล้วเข้าไซต์ก่อนเพื่อน) — เดิม 1.5 วิแค่ทิ้ง waypoint: เฟรมถัดไป "wait" = ไม่เดิน = นาฬิกาติดรีเซ็ต
        # แล้วได้ waypoint เดิมซ้ำ ติดขอบ 40+ วิ (Lotus/Ascent: รีเทค 1v1 ปล่อยระเบิด) ; หลังถอยแล้วนาฬิกาเดินต่อจนเจอทางจริง
        pt, px, pz = m["prog"]
        esc = m.get("esc")                                   # None | (ถึงเวลา, (x, z)) | (-1.0, None) = ถอยไปแล้ว
        # คืบจริง = ห่างจุดเริ่มนับ ≥ 0.5 ม. (ตรงกับเกณฑ์ติดของ sim) ; ระหว่างถอยไม่นับ ; ถอยแล้วต้องพ้น 1.2 ม. (เกินระยะถอย
        # 0.8 ม.) — เดิม 0.3 ม. และนับการถอยเป็นความคืบ: ถอย → รีเซ็ต → กลับไปติดที่เดิม → ถอย วนไม่รู้จบ (Lotus/Ascent)
        escaping = esc is not None and esc[1] is not None
        need = 1.2 if esc is not None else 0.5
        moved = not escaping and math.hypot(b.x - px, b.z - pz) > need
        if moved or (not m["moving"] and esc is None):
            if moved and math.hypot(b.x - px, b.z - pz) > 2.0:
                m["esc_n"] = 0                               # พ้นจุดติดจริงแล้ว — ถอยครั้งหน้าเริ่มตรงออกใหม่
            m["prog"] = (t, b.x, b.z)
            m["esc"] = esc = None
        elif t - pt > STUCK_GIVEUP:
            m["esc"] = None
            return "fail"
        elif t - pt > 1.5 and esc is None and nav[0] == "df":
            wp = m["wp"] or m["go"]
            if wp is not None:
                dx, dz = b.x - wp[0], b.z - wp[1]
                L = math.hypot(dx, dz) or 1.0
                # ถอยครั้งแรกตรงออก ; ครั้งต่อ ๆ ไป (ติดที่เดิมซ้ำ — nav กับการชนของแมพไม่ตรงกันตรงขั้นบันได/มุมกล่อง) เบี่ยง
                # ±60° สลับกัน ให้ waypoint ใหม่ได้แนวดึงเส้นคนละแนว
                k = m["esc_n"] = m["esc_n"] + 1
                a = 0.0 if k == 1 else math.radians(60.0) * (1.0 if k % 2 else -1.0)
                ca, sa = math.cos(a), math.sin(a)
                ex, ez = (dx * ca + dz * sa) / L, (-dx * sa + dz * ca) / L
                m["esc"] = esc = (t + 0.7, (b.x + ex * 0.9, b.z + ez * 0.9))
        if esc is not None and esc[1] is not None:
            if t < esc[0]:
                m["go"] = esc[1]
                m["final"] = False
                return "moving"
            m["esc"] = (-1.0, None)
            m["wp"] = None
            m["wp_t"] = -1e9
        if nav[0] == "df":
            if m["wp_fail"] >= 5:
                return "fail"
            wp = m["wp"]
            if wp is None:
                return "wait"
            m["go"] = wp
            m["final"] = wp is goal
            return "moving"
        pts = nav[1]
        i = m["path_i"]
        while i < len(pts) and (b.x - pts[i][0]) ** 2 + (b.z - pts[i][1]) ** 2 < 0.16:
            i += 1
        m["path_i"] = i
        if i >= len(pts):
            return "arrived"
        m["go"] = pts[i]
        m["final"] = i == len(pts) - 1
        return "moving"

    # ───────────────────────── ข้อมูล / เสียง ─────────────────────────
    def _count(self, k):
        self.beh[k] = self.beh.get(k, 0) + 1

    def _alive(self):
        return [b for b in self.bots if b.alive]

    def _emit(self, ev):
        self.events.append(ev)

    def _push(self, t_at, b, x, z, kind):
        heapq.heappush(self._q, (t_at, next(self._seq), b.meta["idx"], x, z, kind))

    def _deliver(self, t):
        q = self._q
        while q and q[0][0] <= t:
            _ta, _s, idx, x, z, kind = heapq.heappop(q)
            b = self.bots[idx]
            if b.alive:
                self._learn(b, t, x, z, kind)

    def _noisy(self, x, z, r):
        a, d = self.rng.uniform(0.0, _TWO_PI), r * math.sqrt(self.rng.random())
        return x + d * math.sin(a), z + d * math.cos(a)

    def _learn(self, b, t, x, z, kind):
        """บอทรู้ตำแหน่งผู้เล่น (x, z) ณ t — ตื่นตัว เล็งรอทางนั้น ; ข้อมูลใหม่จริง (ห่างเวลา/ระยะ) = ตัดสินใจพฤติกรรมใหม่"""
        m = b.meta
        prev = m["know"]
        m["know"] = (x, z, t, kind)
        if t - m["alert_t"] >= ALERT_KEEP:
            m["alert0"] = t                              # เริ่มตื่นตัวรอบใหม่ (ต้องมีเวลาหันไปเล็งก่อนนับว่า "เล็งรอ")
        m["alert_t"] = t
        m["preaim_dirty"] = True
        new = prev is None or t - prev[2] > NEW_INFO_T or math.hypot(x - prev[0], z - prev[1]) > NEW_INFO_D
        if m["state"] == "hunt" and math.hypot(x - m["target"][0], z - m["target"][1]) > 5.0:
            m["target"] = (x, z)
            self._nav_df(b, (round(x), round(z)), 1.5)
        if new and not m["sees"]:
            self._on_info(b, t, x, z, kind)

    def _on_info(self, b, t, x, z, kind):
        m = b.meta
        st = m["state"]
        if m["defusing"] is not None or kind in ("defuse", "trade") or m["trade_at"] is not None:
            return                                   # เสียงกู้ตัดสินที่ _commit (DEFUSE_COMMIT) เท่านั้น — แตะหลอกต้องได้ผล ;
            #                                          เทรดตัดสินที่ on_bot_killed แล้ว
        plant = kind in ("plant", "cplant")
        if st != "hold" and not (plant and st in ("clear", "return", "repo", "peekhold", "rotate")):
            return                                   # เสียงวาง spike ใกล้ ๆ = ด่วน ตัดพฤติกรรมเดิมได้
        pre = self.side == "atk" and self.spike is None           # ฝ่ายรับก่อนวาง
        d = math.hypot(b.x - x, b.z - z)
        if plant and pre and d > max(PLANT_ROT_R, PLANT_SWING_R) and self._nav_ok:
            if self.hunter is b:                     # ได้ยิน/ได้ข่าวว่ากำลังวางไกล ๆ: หมุนไปไซต์นั้น (วิ่งจนห่างข้อมูล RUN_FAR
                self.hunter = None                   # แล้วเดินเงียบ) หยุดเฝ้าเมื่อทางเหลือ ≤ 10 ม. — ไม่ยืนเฝ้าไซต์ผิดทั้งรอบ
            m["state"] = "rotate"
            m["dest"] = None
            m["corner"] = None
            self._nav_df(b, (round(x), round(z)), 0.8)
            self._count("plant_rotate")
            return
        if st != "hold":
            if self.hunter is b:
                self.hunter = None
            self._to_hold(b, t, yaw=m["yaw"])          # หยุดเฝ้าตรงนี้ แล้วตัดสินใจใหม่ด้านล่าง
        # เวลา: รอบเหลือน้อย = เวลาเป็นของฝ่ายรับ (ผู้เล่นต้องเข้ามาวางเอง) → ไม่ล่า ไม่ swing (เว้นเสียงวาง) — เล็งรอ/ย้ายจุดพอ
        late = pre and self.round_end is not None and self.round_end - t < LATE_T
        if self.side == "def" and self.explode_t is not None and self.explode_t - t < POST_LATE_T:
            late = True                              # หลังวาง เหลือเวลา spike น้อย = ฝ่ายบุกเล่นเวลา ไม่โผล่หาเอง (กู้ = _commit)
        if pre and not late and kind in ("heard", "shot", "call") and self._maybe_hunt(b, t, x, z):
            return
        r = self.rng.random()
        p_swing = m["aggr"] * (0.4 if self.side == "def" else 1.0) + (0.3 if plant else 0.0)
        if kind == "death":
            p_swing *= DEATH_SWING_K                  # ผู้เล่นเพิ่งฆ่าจากตรงนั้น = เล็งรออยู่ — ไม่ dry-peek (เทรดตัดสินไปแล้ว)
        if late and not plant:
            p_swing = 0.0
        swing_r = SWING_MAX
        if plant and pre:
            # ได้ยินกำลังวาง: ฝ่ายรับที่อยู่ใกล้พอไปทัน (4 วิ) ออกไปหยุดการวางเกือบทุกคน — สัญญาณสำคัญสุดของฝ่ายรับ
            p_swing = max(p_swing, _lerp(PLANT_SWING_P[0], PLANT_SWING_P[1], self.u))
            swing_r = PLANT_SWING_R
        if d <= swing_r and r < p_swing:
            jig = not plant and self.rng.random() < _lerp(JIGGLE_P[0], JIGGLE_P[1], self.u)
            self._start_swing(b, t, (x, z), sub="jiggle" if jig else "info")
        elif r < p_swing + REPO_P:
            self._start_repo(b, t, (x, z))
        elif (COLLAPSE_D[0] < d <= COLLAPSE_D[1] and t - m["collapse_t"] > COLLAPSE_GAP and kind != "cplant"
              and self.rng.random() < _lerp(COLLAPSE_P[0], COLLAPSE_P[1], self.u) and self._start_collapse(b, t, (x, z))):
            pass
        elif pre and d <= SWING_MAX and self.rng.random() < FALLBACK_P and not any(
                o is not b and o.alive and math.hypot(o.x - b.x, o.z - b.z) <= FOLLOW_R for o in self.bots):
            self._start_repo(b, t, (x, z), back=True)  # ข้อมูลว่าใกล้มาก + อยู่คนเดียว = ถอยไปจุดลึกกว่า รอแทนการโผล่

    def _maybe_hunt(self, b, t, x, z):
        if self.hunter is not None and self.hunter.alive and self.hunter.meta["state"] in ("hunt", "clear"):
            return False
        d = math.hypot(b.x - x, b.z - z)
        if d > HUNT_WALK:
            return False
        friends = len(self._alive()) - 1
        p = HUNT_K * max(0.0, 1.0 - d / HUNT_D) * (1.0 - min(0.5, 0.05 * friends))
        if self.round_end is not None and self.round_end - t > EARLY_T:
            p *= 0.5                                 # ต้นรอบ: ฝ่ายรับเล่นเฉย (เวลายังเหลือเยอะ — ผู้เล่นยังไม่ต้องรีบ)
        if self.rng.random() >= p:
            return False
        self.hunter = b
        self._count("hunt")
        m = b.meta
        m["state"] = "hunt"
        m["target"] = (x, z)
        self._nav_df(b, (round(x), round(z)), 1.5)
        return True

    def _hears(self, b, pos, R):
        e = b.eye()
        d = math.sqrt((e[0] - pos[0]) ** 2 + (e[1] - pos[1]) ** 2 + (e[2] - pos[2]) ** 2)
        if d <= R * BLOCKED_K:
            return True
        if d > R:
            return False
        return not self.cm.blocked(e, pos)

    def _hear_steps(self, t, pv):
        """เสียงเท้าวิ่งผู้เล่น (เกิน WALK_KNEE × ความเร็ววิ่ง — เกณฑ์เดียวกับเสียงเท้าในเทรนเนอร์) จังหวะ 220–400 ms"""
        if not pv.alive:
            return
        lt = getattr(pv, "land_t", -9.0)
        if lt is not None and lt > self._land_heard and t - lt < 0.5:
            self._land_heard = lt                    # ลงพื้นหลังกระโดด/ตก (§13.1) — ดังเท่าเสียงเท้าวิ่ง ; Shift ตอนลง = เงียบ
            if getattr(pv, "land_loud", False):
                self._noise(t, pv, LAND_R)
        if pv.planting or pv.defusing:
            return
        run = max(0.1, pv.run_speed)
        sp = pv.speed()
        if sp <= WALK_KNEE * run + 1e-6 or getattr(pv, "air", False):
            return                                   # ลอยอยู่ = ไม่มีเสียงเท้า (เสียงคือตอนลง)
        if t - self._plast < 0.22 + 0.18 * (1.0 - min(1.0, sp / run)):
            return
        self._plast = t
        self._noise(t, pv, FOOTSTEP_R)

    def _noise(self, t, pv, R):
        """เสียงตัวผู้เล่น (เท้าวิ่ง/ลงพื้น) → บอทที่ได้ยินรู้ตำแหน่ง ±HEARD_NOISE แล้วหันไปเล็งรอทางนั้น"""
        pos = (pv.x, pv.feet + 1.0, pv.z)
        for b in self.bots:
            if not b.alive or b.meta["sees"]:
                continue
            if self._hears(b, pos, R):
                m = b.meta
                if t - m["heard_t"] > 2.0:
                    self._emit({"k": "heard", "bot": b})
                m["heard_t"] = t
                x, z = self._noisy(pv.x, pv.z, HEARD_NOISE)
                self._learn(b, t, x, z, "heard")

    def _spike_sounds(self, t, pv):
        ps, ds = self.plant_snd, self.defuse_snd
        chk = t >= self._snd_chk
        if chk:
            self._snd_chk = t + NOTICE_DT
        if ps is not None and ps["active"] and chk:
            for b in self.bots:
                if b.alive and not b.meta["psnd"] and self._hears(b, ps["pos"], SPIKE_SND_R):
                    b.meta["psnd"] = True
                    x, z = self._noisy(ps["pos"][0], ps["pos"][2], HEARD_NOISE)
                    self._learn(b, t, x, z, "plant")
                    b.meta["call_t"] = -99.0             # ข่าวด่วน: บอกเพื่อนทันที (ไม่ติดเพดาน callout 1 วิ)
                    self._callout(b, t, x, z, "cplant")
        if ds is not None and ds["active"]:
            if chk:
                for b in self.bots:
                    if b.alive and not b.meta["dsnd"] and self._hears(b, ds["pos"], SPIKE_SND_R):
                        self._hear_defuse(b, t)
                for b in self.bots:                  # เสียงกู้ยังดัง + ไม่เห็นคนกู้: เคลียร์แล้ว = ดันเข้าถึง spike ;
                    m = b.meta                       # ทอยไม่โผล่ไว้ = ทอยใหม่
                    if (b.alive and m["dsnd"] and m["dclr_t"] is not None and not m["sees"]
                            and t - m["dclr_t"] >= (RECOMMIT_SKIP if m["dskip"] else RECOMMIT_T)
                            and m["pushes"] < PUSH_MAX and t - m["contact_t"] >= 1.0
                            and m["state"] in ("hold", "peekhold", "rotate", "return", "repo")):
                        m["pushes"] += 1
                        self._commit(b, t, push=not m["dskip"])
            for b in self.bots:
                m = b.meta
                if b.alive and m["commit_at"] is not None and t >= m["commit_at"]:
                    m["commit_at"] = None
                    self._commit(b, t)

    def _commit_s(self):
        return _lerp(DEFUSE_COMMIT[0], DEFUSE_COMMIT[1], self.u)

    def _hear_defuse(self, b, t):
        """ได้ยินเสียงกู้ครั้งแรก (ต่อการกู้หนึ่งครั้ง): จุดที่ได้ยิน ±2 ม. หดเข้าวง DEFUSE_R รอบ spike (คนกู้ต้องอยู่ในนั้น) ;
        กู้ครั้งนี้ไม่ทันแน่ (นับจากเวลา *เริ่ม* กู้ — เดินเข้าระยะเสียงทีหลังก็ยังต้องสน) = ไม่โผล่ ; ไม่งั้นนัด commit"""
        m = b.meta
        ds = self.defuse_snd
        m["dsnd"] = True
        m["dclr_t"] = None
        m["dskip"] = False
        m["pushes"] = 0
        x, z = self._noisy(ds["pos"][0], ds["pos"][2], HEARD_NOISE)
        if self.spike is not None:
            sx, sz = self.spike
            d = math.hypot(x - sx, z - sz)
            if d > DEFUSE_R:
                x, z = sx + (x - sx) * DEFUSE_R / d, sz + (z - sz) * DEFUSE_R / d
        m["dpos"] = (x, z)
        self._learn(b, t, x, z, "defuse")
        need = DEFUSE_HALF if ds["banked"] else DEFUSE_T
        if self.explode_t is not None and self.explode_t - ds["t0"] < need:
            return                                   # กู้ไม่ทันแน่ ๆ — ไม่ต้องโผล่ (ไม่หลงกล)
        m["commit_at"] = max(t, ds["t0"] + self._commit_s())

    def _commit(self, b, t, push=False):
        """เสียงกู้ยาวพอ = เชื่อว่ากู้จริง → เคลียร์ "บริเวณคนกู้" (จุดยืนกู้ได้ใกล้เสียง — _defuse_cand) ไม่ใช่ตัว spike (คนกู้
        หลบหลังมุมได้ไกล 2.4 ม.): เห็นบริเวณนั้นจากที่ยืนแล้ว → เล็งรอ ; ไม่เห็น → โผล่ตามทางสู่ spike จนเห็นบริเวณ (ไกล =
        โอกาสน้อยลง — ทอยไม่ผ่าน = dskip ทอยใหม่ทุก RECOMMIT_SKIP ถ้าเสียงยังดัง) ; push = เคลียร์แล้วแต่เสียงยังดัง →
        เดินเข้าถึง spike (ไม่หยุดเพราะ "เห็นบริเวณ")"""
        m = b.meta
        m["committed"] = t
        if self.spike is None or m["defusing"] is not None or m["state"] == "retake":
            return
        hp = m["dpos"] or self.spike
        cand = self._defuse_cand(hp)
        if not push and m["state"] in ("swing", "peekhold") and m["sub"] == "spike":
            if m["state"] == "swing":                # โผล่อยู่แล้ว (กู้รอบใหม่) = อัปเดตจุดที่ได้ยิน
                m["target"] = (cand[0][0], cand[0][2])
                m["cand"] = cand
            return
        m["dskip"] = False
        if not push and self._clear_ok(b, cand):
            m["preaim"] = arena.angles_to(b.eye(), cand[0])
            m["preaim_dirty"] = False
            m["dclr_t"] = t
            if m["state"] != "hold":
                self._to_hold(b, t, yaw=m["preaim"][0])
            return
        sx, sz = self.spike
        d = math.hypot(b.x - sx, b.z - sz)
        if not push and d > 8.0 and self.rng.random() >= max(0.2, min(1.0, 1.2 - d / 30.0)):
            m["dclr_t"] = t
            m["dskip"] = True
            return
        m["state"] = "swing"
        m["sub"] = "spike"
        m["target"] = (cand[0][0], cand[0][2])
        m["cand"] = cand
        m["push"] = push
        m["dclr_t"] = None
        m["pl_t"] = t
        self._nav_df(b, self.spike, PEEK_STOP, pin=True)

    def _defuse_spots(self):
        """จุดที่คนกู้ยืนได้รอบ spike → [(x, หัวระดับยืน, z)] : วง DEFUSE_RINGS, พื้นต่างระดับ spike ≤ DEFUSE_DY, ยืนได้
        (PLAYER_R), ตาเห็น spike (กติกากู้ของโหมด) — เรขาคณิตล้วน (คนรู้แมพก็รู้) ; แคชต่อ spike"""
        if self._dspots is not None and self._dspots[0] == self.spike:
            return self._dspots[1]
        cm = self.cm
        sx, sz = self.spike
        sy = self.spike_y
        tgt = (sx, sy + 0.15, sz)
        out = []
        for r in DEFUSE_RINGS:
            n = 1 if r <= 0.0 else max(6, int(round(_TWO_PI * r / 0.9)))
            for k in range(n):
                a = _TWO_PI * k / n
                x, z = sx + r * math.sin(a), sz + r * math.cos(a)
                fy = cm.floor_y(x, z)
                if fy is None or not self._reach_ok(fy, sy) or not cm.disc_clear(x, z, PLAYER_R):
                    continue
                if cm.blocked((x, fy + EYE_Y, z), tgt):
                    continue
                out.append((x, fy + HEAD_Y, z))
        self._dspots = (self.spike, out)
        return out

    def _defuse_cand(self, hp):
        """จุดยืนกู้ที่น่าจะเป็นจากเสียงที่ได้ยิน hp (x, z) — ห่าง ≤ HEARD_NOISE + CLEAR_NEAR (น้อยกว่า 4 จุด = 6 จุดใกล้สุด)
        เรียงใกล้ hp ก่อน ([0] = จุดเล็ง/เป้าโผล่) ; ไม่มีจุดยืนกู้เลย (แมพแปลก) = หัวเหนือ hp"""
        spots = self._defuse_spots()
        if not spots:
            fy = self.cm.floor_y(hp[0], hp[1])
            return [(float(hp[0]), (fy if fy is not None else self.spike_y) + HEAD_Y, float(hp[1]))]
        by = sorted(spots, key=lambda p: (p[0] - hp[0]) ** 2 + (p[2] - hp[1]) ** 2)
        R2 = (HEARD_NOISE + CLEAR_NEAR) ** 2
        near = [p for p in by if (p[0] - hp[0]) ** 2 + (p[2] - hp[1]) ** 2 <= R2]
        return near if len(near) >= 4 else by[:6]

    def _clear_ok(self, b, cand):
        """บอทเห็นหัว (ระดับยืน) ของจุดยืนกู้ที่น่าจะเป็น ≥ CLEAR_FRAC แล้วหรือยัง (หยุดเร็วทั้งสองทาง)"""
        n = len(cand)
        need = int(math.ceil(CLEAR_FRAC * n - 1e-9))
        eye = b.eye()
        blocked = self.cm.blocked
        seen = miss = 0
        for p in cand:
            if blocked(eye, p):
                miss += 1
                if n - miss < need:
                    return False
            else:
                seen += 1
                if seen >= need:
                    return True
        return seen >= need

    def _callout(self, src, t, x, z, kind="call"):
        """บอกเพื่อน (หลัง CALLOUT_DELAY, ตำแหน่ง ±CALL_NOISE) — kind 'call' เห็น/โดนยิง · 'death' ตาย (เพื่อนไม่ dry-peek) ·
        'cplant' ได้ยินกำลังวาง (ตัวไกลหมุนมา)"""
        ms = src.meta
        if t - ms["call_t"] < 1.0:
            return
        ms["call_t"] = t
        for b in self.bots:
            if b is src or not b.alive:
                continue
            nx, nz = self._noisy(x, z, CALL_NOISE)
            self._push(t + self.rng.uniform(*CALLOUT_DELAY), b, nx, nz, kind)

    # ───────────────────────── callbacks จากโหมด ─────────────────────────
    def on_player_shot(self, t, pos):
        """ผู้เล่นยิง — ทุกตัวรู้ตำแหน่ง ±3 ม. หลัง 0.3 วิ (เสียงปืนดังทั้งแมพ)"""
        x, z = _xz(pos)
        for b in self.bots:
            m = b.meta
            if b.alive and t - m["shot_q_t"] >= 0.25:
                m["shot_q_t"] = t
                nx, nz = self._noisy(x, z, SHOT_NOISE)
                self._push(t + SHOT_DELAY, b, nx, nz, "shot")

    def on_player_reload(self, t, pos):
        p3 = self._pos3(pos, 1.0)
        for b in self.bots:
            if b.alive and self._hears(b, p3, RELOAD_SND_R):
                nx, nz = self._noisy(p3[0], p3[2], HEARD_NOISE)
                self._learn(b, t, nx, nz, "reload")

    def _pos3(self, pos, up):
        """ต้นเสียงของผู้เล่นที่ pos = (x, z) หรือ (x, y, z) — ไม่ใช้ y (โหมดส่งตา clutch_eye(), sim ส่งเท้า: เดิมบวก up ทับ y
        ที่ส่งมา เสียงจากตาจึงลอย 2.15–2.65 ม. ข้ามกล่อง ได้ยินไกลกว่าที่ sim จูนไว้) → เท้าจริงใต้ (x, z) + up
        (support_y → floor_y → เท้าล่าสุดใน trail)"""
        x, z = _xz(pos)
        fy = self.cm.support_y(x, z, PLAYER_R)
        if fy is None:
            fy = self.cm.floor_y(x, z)
        if fy is None:
            fy = self._trail[-1][3] if self._trail else 0.0
        return (x, fy + up, z)

    def on_plant_start(self, t, pos):
        self.plant_snd = {"t0": t, "pos": self._pos3(pos, 0.5), "active": True}
        self._snd_chk = t                              # เช็คผู้ได้ยินเฟรมถัดไปทันที

    def on_plant_cancel(self, t):
        if self.plant_snd is not None:
            self.plant_snd["active"] = False
        for b in self.bots:
            b.meta["psnd"] = False

    def on_planted(self, t, pos):
        """วางเสร็จ = รู้ทุกตัว (ประกาศ + มินิแมพ) → ฝ่ายรับทุกตัวรีเทค"""
        if self.plant_snd is not None:
            self.plant_snd["active"] = False
        self._set_spike(pos)
        self.explode_t = t + SPIKE_T
        self.obj = self.spike
        for b in self._alive():
            m = b.meta
            m["know"] = (self.spike[0], self.spike[1], t, "planted")
            m["alert_t"] = t
            m["preaim_dirty"] = True
        if self.side == "atk":
            self._retake_start(t)

    def on_defuse_start(self, t, pos, banked):
        self.defuse_snd = {"t0": t, "pos": self._pos3(pos, 1.0), "banked": bool(banked), "active": True}
        self._snd_chk = t

    def on_defuse_stop(self, t):
        if self.defuse_snd is not None:
            self.defuse_snd["active"] = False
        for b in self.bots:
            b.meta["commit_at"] = None
            b.meta["dsnd"] = False

    def on_bot_damaged(self, bot, t, dmg, zone, from_pos):
        """บอทโดนยิง: tagging (×0.275 ฟื้นใน 0.5 วิ) · หยุดกู้ · รู้ทิศผู้ยิงทันที (หยุด หันไปหา TAG_TURN วิ — _think) ·
        เพื่อนได้ callout"""
        m = bot.meta
        bot.vel[0] *= TAG_SLOW
        bot.vel[1] *= TAG_SLOW
        m["tag_t"] = t
        m["hit_from"] = self._pos3(from_pos, 1.4)
        if m["defusing"] is not None:
            self._stop_defuse(bot, t)
        m["force_notice"] = t
        x, z = _xz(from_pos)
        self._learn(bot, t, x, z, "hit")
        self._callout(bot, t, x, z)

    def on_bot_killed(self, bot, t, from_pos):
        m = bot.meta
        bot.alive = False
        m["dead_t"] = t
        m["sees"] = False
        m["vel"] = (0.0, 0.0)
        m["reload"] = False
        if m["defusing"] is not None:
            self._stop_defuse(bot, t)
        x, z = _xz(from_pos)
        m["call_t"] = -99.0
        self._callout(bot, t, x, z, "death")
        # เทรด: เพื่อนที่อยู่ใกล้ (≤ TRADE_R — เห็น/ได้ยินเพื่อนตายเอง ไม่ต้องรอ callout) ออกไปหาคนยิงทันทีตามโอกาสต่อแรงค์
        # ตัวที่กำลังรีเทค (เดินเข้า spike อยู่แล้ว) ไม่นับ — จังหวะเข้าของทีมจัดการเอง
        p = _lerp(TRADE_P[0], TRADE_P[1], self.u)
        lo = _lerp(TRADE_DELAY[0][0], TRADE_DELAY[1][0], self.u)
        hi = _lerp(TRADE_DELAY[0][1], TRADE_DELAY[1][1], self.u)
        for o in self.bots:
            mo = o.meta
            if (o is bot or not o.alive or mo["sees"] or mo["defusing"] is not None or mo["state"] in ("retake", "swing")
                    or math.hypot(o.x - bot.x, o.z - bot.z) > TRADE_R):
                continue
            if self.rng.random() >= p:
                continue
            mo["trade_at"] = t + self.rng.uniform(lo, hi)
            mo["trade_pos"] = self._noisy(x, z, 1.0)
            self._learn(o, t, mo["trade_pos"][0], mo["trade_pos"][1], "trade")

    # ───────────────────────── คำถามจากโหมด ─────────────────────────
    def bot_defuse(self):
        """(บอท, วินาทีที่กู้ไปแล้ว) ระหว่างบอทกู้ (ผู้เล่น ATK หลังวาง) ; ไม่มี = None"""
        b = self._defuser
        if b is None or not b.alive or b.meta["defusing"] is None:
            return None
        return b, self.bot_banked + max(0.0, self.t - b.meta["defusing"])

    def can_bots_defuse(self, t, spike_xz, spike_left):
        """คนวางตาย: บอทที่ยังอยู่วิ่งมีด 6.75 ม./วิ (+ชักของ 1 วิ) ไปถึง spike แล้วเหลือ ≥ 7 วิ (≥ 3.5 ถ้ากู้ครึ่งไว้แล้ว)
        ได้ไหม — ระยะเดินจริงจาก DistField (ยังไม่เสร็จ = ทำให้เสร็จตอนนี้ครั้งเดียว)"""
        alive = self._alive()
        if not alive:
            return False
        need = DEFUSE_HALF if self.bot_banked >= DEFUSE_HALF else DEFUSE_T
        bd = self.bot_defuse()
        if bd is not None and spike_left >= DEFUSE_T - bd[1]:
            return True
        if not self._nav_ok:
            self.cm.ensure_nav()
        sx, sz = _xz(spike_xz) if len(spike_xz) > 2 else (float(spike_xz[0]), float(spike_xz[1]))
        if self.spike is not None and math.hypot(sx - self.spike[0], sz - self.spike[1]) < 0.05:
            goal = self.spike_goal                    # spike บนกล่อง = ระยะถึงจุดพื้นที่เอื้อมกู้ได้ (สอดคล้อง _try_defuse)
        else:
            goal = self._spike_goal(sx, sz, self._spike_floor(sx, sz, self.spike_y))
        df = self._field(goal, pin=True)
        if not df.done:
            df.run()
            if df in self._pending:
                self._pending.remove(df)
        for b in alive:
            L = self.cm.path_len(df, b.x, b.z)
            if L is None:
                continue
            if spike_left - (L / KNIFE_SPEED + KNIFE_EQUIP) >= need:
                return True
        return False

    def seen_count(self):
        return sum(1 for b in self.bots if b.alive and b.meta["sees"])

    # ───────────────────────── retake (ผู้เล่น ATK วางแล้ว) ─────────────────────────
    def _retake_start(self, t):
        df = self._field(self.spike_goal, pin=True)
        # สนามระยะของจุดรวมพล (ทางเข้า bake ของไซต์ที่วางจริง) เข้าคิวตั้งแต่ตอนนี้ — แผนเลือกทางเข้าด้วยระยะเดินจริง
        # (ไซต์ของฉากทำไว้แล้วตอนนับถอยหลัง ; ปกติขาดแค่สนามของ spike)
        site = self.cm.zone_at(self.spike[0], self.spike[1]) or self.site
        sdf = [self._field(e["stage"], pin=True) for e in self._baked_entries(site, "def")]
        self.retake = {"t0": t, "df": df, "plan": False, "groups": [], "go_t": None, "first_staged": None,
                       "wait": _lerp(STAGE_WAIT[0], STAGE_WAIT[1], self.u),
                       "jitter": _lerp(GO_JITTER[0], GO_JITTER[1], self.u),
                       "trickle": _lerp(TRICKLE_P[0], TRICKLE_P[1], self.u), "entries": [], "hurry_t": 0.0,
                       "stage_df": sdf}
        if self.hunter is not None:
            self.hunter = None
        for b in self._alive():
            m = b.meta
            m["state"] = "retake"
            m["rtp"] = "plan"
            m["nav"] = None
            m["astar_req"] = None
            m["start_t"] = t + self.rng.uniform(*RETAKE_STAGGER)
            m["go_at"] = None

    def _baked_entries(self, site, side_key):
        """ทางเข้าที่ bake ไว้ (§10.4: cmap.entries[site][side] = [{"e": [x, z], "stage": [x, z]}, …]) — ไม่มี = []"""
        baked = getattr(self.cm, "entries", None) or {}
        rows = (baked.get(site) or {}).get(side_key) or ((self.cm.sites.get(site) or {}).get("entries") or {}).get(
            side_key) or []
        out = []
        for r in rows:
            try:
                out.append({"e": (float(r["e"][0]), float(r["e"][1])),
                            "stage": (float(r["stage"][0]), float(r["stage"][1]))})
            except (KeyError, TypeError, IndexError, ValueError):
                continue
        return out

    def _entries(self, goal, side_key):
        """ทางเข้าไซต์ [{"e": (x, z), "stage": (x, z)}] — bake ถ้ามี ; มีไม่ถึง 2 = เติมทางเข้าที่คิดจาก nav (ห่าง ≥ 6 ม.)"""
        site = self.cm.zone_at(goal[0], goal[1]) or self.site
        out = self._baked_entries(site, side_key)
        if len(out) < 2:
            for d in self._derive_entries(goal):
                if len(out) >= 3:
                    break
                if all(math.hypot(d["e"][0] - o["e"][0], d["e"][1] - o["e"][1]) >= 6.0 for o in out):
                    out.append(d)
        return out

    def _derive_entries(self, goal):
        """ทางเข้าจาก nav (ด่านไม่มี entries bake): ไล่สายลงเขาของ DistField จากต้นทางหลายจุด (บอท, spawn, ไซต์อื่น,
        callout 15–60 ม.) → จุดแรกที่เข้าใกล้ศูนย์ ENTRY_R = ทางเข้า ; ถอยตามเส้นทาง STAGE_BACK ม. ที่มองไม่เห็นจาก
        ศูนย์ = จุดรวมพล ; รวมทางเข้าที่ห่างกัน < 6 ม. แล้วเลือก ≤ 3 ที่ทิศต่างกัน ≥ 35°"""
        cm = self.cm
        df = self._fields.get((round(goal[0], 2), round(goal[1], 2)))
        if df is None or not df.done:
            return []
        gx, gz = goal
        gy = (cm.floor_y(gx, gz) or self.spike_y) + EYE_Y
        src = [(b.x, b.z) for b in self._alive()]
        src += [tuple(p[:2]) for p in (cm.spawns or {}).values()]
        src += [tuple(s["c"][:2]) for k, s in (cm.sites or {}).items() if "c" in s
                and math.hypot(s["c"][0] - gx, s["c"][1] - gz) > ENTRY_R]
        calls = sorted((math.hypot(c[1] - gx, c[2] - gz), c[1], c[2]) for c in (cm.calls or []))
        src += [(x, z) for d, x, z in calls if 15.0 <= d <= 60.0][:12]     # งานครั้งเดียว ~1–3 ms บนด่านจริง
        cands = []
        seen_n = set()
        for sx, sz in src:
            n = cm.nav_node(sx, sz)
            if n is None or n in seen_n or not df.fin[n] or math.hypot(sx - gx, sz - gz) <= ENTRY_R:
                continue
            seen_n.add(n)
            chain = []
            k = 0
            while n >= 0 and k < 3000:
                chain.append(cm.nav_pos(n))
                n = df.nxt[n]
                k += 1
            idx = next((i for i, p in enumerate(chain) if math.hypot(p[0] - gx, p[2] - gz) <= ENTRY_R), None)
            if not idx:
                continue
            e = chain[idx]
            acc, j, st, last = 0.0, idx, None, -9.0
            while j > 0:
                a, c = chain[j], chain[j - 1]
                acc += math.hypot(a[0] - c[0], a[2] - c[2])
                j -= 1
                if acc >= STAGE_BACK and (acc - last >= 1.0 or acc >= STAGE_BACK_MAX):
                    last = acc                                 # เช็คว่าซ่อนจาก spike ทุก ~1 ม. (งบรังสี)
                    p = chain[j]
                    if acc >= STAGE_BACK_MAX or cm.blocked((gx, gy, gz), (p[0], p[1] + 1.2, p[2])):
                        st = p
                        break
            if st is None:
                st = chain[j]
            cands.append(((e[0], e[2]), (st[0], st[2])))
        clus = []                                     # [นับ, e, stage]
        for e, st in cands:
            for c in clus:
                if math.hypot(e[0] - c[1][0], e[1] - c[1][1]) < 6.0:
                    c[0] += 1
                    break
            else:
                clus.append([1, e, st])
        clus.sort(key=lambda c: -c[0])
        pick = []
        for c in clus:
            ang = math.atan2(c[1][0] - gx, c[1][1] - gz)
            if all(abs(_wrap(ang - a)) >= math.radians(35) for a, _c in pick):
                pick.append((ang, c))
            if len(pick) >= 3:
                break
        return [{"e": c[1], "stage": c[2]} for _a, c in pick]

    def _retake_plan(self, t):
        R = self.retake
        R["plan"] = True
        df = R["df"]
        cm = self.cm
        sx, sz = self.spike
        ents = self._entries(self.spike, "def")
        R["entries"] = ents
        alive = self._alive()
        if not ents:
            for b in alive:
                b.meta["rtp"] = "go_wait"
                b.meta["go_at"] = b.meta["start_t"]
            return
        if df.done:
            slen = [cm.path_len(df, e["stage"][0], e["stage"][1]) for e in ents]
            order = sorted(alive, key=lambda b: cm.path_len(df, b.x, b.z) or 1e9)
        else:                                          # สนามระยะ spike ยังไม่เสร็จ (หมดเวลารอ): ประมาณด้วยระยะตรง × 1.3
            slen = [1.3 * math.hypot(e["stage"][0] - sx, e["stage"][1] - sz) for e in ents]
            order = sorted(alive, key=lambda b: math.hypot(b.x - sx, b.z - sz))
        sdf = [self._field(e["stage"], pin=True) for e in ents]

        def walk(k, b):
            """ระยะเดินจริงบอท → จุดรวมพล k (None = สนามยังไม่เสร็จ/ไปไม่ถึง) — เดิมระยะตรง ×1.25: จุดรวมพลอีกชั้น/หลังกำแพง
            ดูใกล้ บอทเดินอ้อม 60–126 ม. (Split 629: ตรง 3.6 ม. เดินจริง 126 ม.)"""
            return cm.path_len(sdf[k], b.x, b.z) if sdf[k].done else None
        count = [0] * len(ents)
        groups = [[] for _ in ents]
        direct = []                                   # อยู่ในไซต์/ฝั่งไซต์อยู่แล้ว: เฝ้าตรงนั้นแล้วเข้าพร้อมทีม
        for b in order:
            m = b.meta
            if math.hypot(b.x - sx, b.z - sz) <= ENTRY_R + 2.0:
                m["rtp"] = "staged"
                m["entry"] = m["stage"] = None
                direct.append(b)
                continue
            best = None
            wmin = None
            for k, e in enumerate(ents):
                if slen[k] is None:
                    continue
                w = walk(k, b)
                if w is not None:
                    wmin = w if wmin is None else min(wmin, w)
                else:
                    w = math.hypot(b.x - e["stage"][0], b.z - e["stage"][1]) * 1.25
                c = w + slen[k] + SPREAD_PEN * count[k]
                if best is None or c < best[0]:
                    best = (c, k)
            if best is None:
                m["rtp"] = "go_wait"
                m["go_at"] = m["start_t"]
                continue
            dsp = cm.path_len(df, b.x, b.z) if df.done else None
            if dsp is not None and wmin is not None and dsp <= wmin:
                m["rtp"] = "staged"                   # เดินถึง spike ใกล้กว่าถึงทุกจุดรวมพล = อยู่ฝั่งไซต์แล้ว (ไม่ย้อนออกไปรวมพล)
                m["entry"] = m["stage"] = None        # เฝ้าตรงนี้แล้วเข้าพร้อมทีม — ไม่วิ่งเดี่ยวเข้า spike
                direct.append(b)
                continue
            k = best[1]
            count[k] += 1
            groups[k].append(b)
            m["entry"] = ents[k]["e"]
            m["stage"] = ents[k]["stage"]
            m["rtp"] = "to_stage"
            m["order"] = len(groups[k]) - 1
        R["groups"] = [g for g in groups if g]
        if not R["groups"]:                           # ไม่มีใครต้องไปจุดรวมพล = เข้าตามจังหวะเริ่มของแต่ละตัว
            for b in direct:
                b.meta["rtp"] = "go_wait"
                b.meta["go_at"] = b.meta["start_t"]
            return
        if direct:
            R["groups"].append(direct)
        for b in alive:
            if b.meta["rtp"] == "to_stage":
                self._field(b.meta["stage"], pin=True)

    def _retake_tick(self, t):
        R = self.retake
        if not R["plan"]:
            # รอสนามระยะ spike + จุดรวมพล (หั่นช่วงใน _nav_tick ~0.75 วิ/สนาม — ห้าม run() ในเฟรม ~15 ms/สนาม) แล้วค่อยวางแผน
            # ด้วยระยะเดินจริง ; เกิน PLAN_WAIT = วางแผนด้วยค่าประมาณที่มี (บอทช่วงนี้ยืนหันหา spike ในเฟส plan)
            ready = R["df"].done and all(f.done for f in R.get("stage_df") or ())
            if ready or t - R["t0"] >= PLAN_WAIT:
                self._retake_plan(t)
            return
        if R["go_t"] is not None:
            return
        team = [b for g in R["groups"] for b in g if b.alive and b.meta["rtp"] in ("to_stage", "staged")]
        if not team:
            return
        staged = [b for b in team if b.meta["rtp"] == "staged" and b.meta["stage"] is not None]
        if staged and R["first_staged"] is None:
            R["first_staged"] = t
        staged = [b for b in team if b.meta["rtp"] == "staged"]
        walk = movement.speed_cap(WEAPONS[self.bot_weapon]["run_speed"], walk=True)
        hurry = False
        if self.explode_t is not None and t >= R["hurry_t"]:
            R["hurry_t"] = t + 0.5
            for b in team:
                st = b.meta["stage"] or (b.x, b.z)
                L = self.cm.path_len(R["df"], st[0], st[1]) or 20.0
                if self.explode_t - t < L / walk + DEFUSE_T + DEFUSE_MARGIN:
                    hurry = True
                    break
        contact = any(b.meta["sees"] or t - b.meta["contact_t"] < 1.0 for b in self._alive())   # มีคนปะทะ = เข้าช่วยเทรด
        if (len(staged) == len(team) or hurry or (contact and staged)
                or (R["first_staged"] is not None and t - R["first_staged"] >= R["wait"])):
            R["go_t"] = t
            # นัดเข้าพร้อมกัน: กลุ่มที่อยู่ใกล้ spike กว่ารอให้กลุ่มไกลเดินมาถึงขอบไซต์พร้อมกัน (คน "นับ 3 แล้วเข้า" —
            # ผู้วาง spike เห็นหลายคนจากหลายทางพร้อมกัน ไม่ใช่ทีละคนจากทางเดียว) ; แรงค์ต่ำนัดได้ไม่ตรง (RETAKE_SYNC) ;
            # ต้องรีบ/มีคนปะทะแล้ว = ไม่รอ
            run_v = WEAPONS[self.bot_weapon]["run_speed"]

            def eta(b):
                L = self.cm.path_len(R["df"], b.x, b.z)
                if L is None:
                    return 0.0
                return max(0.0, L - RETAKE_WALK) / run_v + min(L, RETAKE_WALK) / walk
            etas = []
            for g in R["groups"]:
                lead = next((b for b in g if b.alive and b.meta["rtp"] in ("to_stage", "staged")), None)
                etas.append(eta(lead) if lead is not None and not hurry and not contact else 0.0)
            e_max = max(etas) if etas else 0.0
            sync = _lerp(RETAKE_SYNC[0], RETAKE_SYNC[1], self.u)
            for gi, g in enumerate(R["groups"]):
                base = t + min(RETAKE_SYNC_MAX, (e_max - etas[gi]) * sync)
                for k, b in enumerate(g):
                    m = b.meta
                    if not b.alive or m["rtp"] not in ("to_stage", "staged"):
                        continue
                    base = base + (TRADE_GAP / walk if k else 0.0)
                    m["go_at"] = base + self.rng.uniform(0.0, R["jitter"])
                    if m["rtp"] == "to_stage":
                        # ยังเดินไปจุดรวมพลไม่ถึง: ทิ้งทางไปจุดรวมพล — 'go' วางทางใหม่สู่ spike เมื่อ nav ว่าง (เดิมเดินทางเก่า
                        # จนถึงจุดรวมพลแล้ว "arrived" = at_spike ทั้งที่ห่าง spike 13–48 ม. ยืนเฉยทั้งรอบ)
                        m["rtp"] = "go_wait"
                        m["nav"] = None
                        m["wp"] = None

    # ───────────────────────── พฤติกรรมต่อเฟรม ─────────────────────────
    def _aim_to(self, b, p):
        return arena.angles_to(b.eye(), p)

    def _idle_look(self, b, t):
        """คนเฝ้า: ข้อมูลสด (< ALERT_KEEP) = เล็งรอทางนั้น ; ข้อมูลเก่ากว่าแต่ < ALERT_LONG = ยังเฝ้าทางนั้นเป็นหลัก
        (ALERT_LONG_P ของรอบมอง) สลับมองทิศอื่นบ้าง ; ไม่มีข้อมูล = มองสลับทิศเฝ้า (≤ 3)"""
        m = b.meta
        age = t - m["alert_t"]
        if m["preaim"] is not None and age < ALERT_KEEP:
            return m["preaim"]
        fs = m["facings"]
        if t >= m["glance_t"]:
            if len(fs) > 1:
                cur = m["glance_i"]
                opts = [k for k in range(len(fs)) if k != cur]
                w = [2.0 if k == 0 else 1.0 for k in opts]
                m["glance_i"] = self.rng.choices(opts, weights=w)[0]
            m["glance_t"] = t + self.rng.uniform(*self._glance())
            m["glance_pre"] = self.rng.random() < ALERT_LONG_P
        if m["preaim"] is not None and age < ALERT_LONG and m["glance_pre"]:
            return m["preaim"]
        i = min(m["glance_i"], len(fs) - 1)
        return fs[i], m["fpitch"][i]

    def _move_look(self, b):
        """มองตามทางเดิน ระดับหัวของพื้นข้างหน้า 6 ม. (ขึ้น/ลงทางลาดมองตามระดับ ไม่เล็งพื้น/ฟ้า)"""
        g = b.meta["go"]
        if g is None:
            return None
        yw = math.atan2(g[0] - b.x, g[1] - b.z)
        fy = self.cm.floor_y(b.x + 6.0 * math.sin(yw), b.z + 6.0 * math.cos(yw))
        if fy is None:
            return yw, 0.0
        return yw, math.atan2(fy + HEAD_Y - (b.y0 + EYE_Y), 6.0)

    def _travel_look(self, b, t, preaim=True):
        """มองระหว่างเดินทางแบบคน: ข้อมูลสด (เล็งรอทางที่ข้อมูลมา) > มุมอับข้างหน้าที่ยังไม่เคลียร์ (pie — เล็งขอบมุมระดับหัว
        ขณะเดินผ่าน) > ตามทางเดิน ; คืน None = ไม่มีอะไรให้มอง"""
        m = b.meta
        if preaim and m["preaim"] is not None and t - m["alert_t"] < ALERT_KEEP:
            return m["preaim"]
        c = self._corner_look(b, t)
        if c is not None:
            return c
        return self._move_look(b)

    def _corner_look(self, b, t):
        """มุมที่กำลังเคลียร์ (จาก _corner_scan) → ทิศเล็ง ; เห็นจุดหลังมุมครบ CORNER_CLEAR / เดินผ่านไปแล้ว / เล็งนานเกิน = เคลียร์"""
        m = b.meta
        c = m["corner"]
        if c is None:
            return None
        P, t_set, vis0, t_chk = c
        done = t - t_set > CORNER_MAX
        sp = b.speed()
        if not done and sp > 0.5:
            hd = math.atan2(b.vel[0], b.vel[1])
            done = abs(_wrap(math.atan2(P[0] - b.x, P[2] - b.z) - hd)) > math.radians(100.0)   # เดินผ่านไปแล้ว
        if not done and t >= t_chk:
            vis = not self.cm.blocked(b.eye(), P)
            vis0 = (vis0 if vis0 is not None else t) if vis else None
            done = vis0 is not None and t - vis0 >= CORNER_CLEAR
            c = m["corner"] = (P, t_set, vis0, t + 0.1)
        if done:
            m["corner"] = None
            m["cleared"].append((P[0], P[2], t))
            return None
        return self._aim_to(b, P)

    def _corner_scan(self, b, t):
        """หามุมอับข้างหน้า: รังสีระดับตาเป็นพัด ±60° รอบทิศเดิน — รังสีข้างกันที่ระยะกระโดดใกล้→ไกล (≥ CORNER_JUMP) = ขอบมุม ;
        จุดเล็ง = เลยขอบไปทางฝั่งไกล 1.5 ม. ที่ระดับหัว (คนหลังมุมจะโผล่ตรงนั้นก่อน) ; เลือกมุมใกล้/ตรงทางเดินที่สุดที่ยัง
        ไม่เคลียร์ใน CORNER_MEMO วิ (CS bot: เช็คจุดอันตรายตามทาง 10° ทุก 10 วิ ; Booth GDC 2004)"""
        m = b.meta
        m["corner_t"] = t + CORNER_DT
        cl = [c for c in m["cleared"] if t - c[2] < CORNER_MEMO]
        m["cleared"] = cl
        if b.speed() > 0.5:
            hd = math.atan2(b.vel[0], b.vel[1])
        elif m["go"] is not None:
            hd = math.atan2(m["go"][0] - b.x, m["go"][1] - b.z)
        else:
            return
        cm = self.cm
        eye = b.eye()
        n = len(CORNER_FAN)
        rays = []
        for a in CORNER_FAN:
            yw = hd + math.radians(a)
            r = cm.ray(eye, (math.sin(yw), 0.0, math.cos(yw)), CORNER_RANGE)
            rays.append((yw, CORNER_RANGE if r is None else r))
        best = None
        for k in range(n - 1):
            (y1, r1), (y2, r2) = rays[k], rays[k + 1]
            if abs(r1 - r2) < CORNER_JUMP:
                continue
            i, j = (k, k + 1) if r1 < r2 else (k + 1, k)          # i = รังสีใกล้ (ผนังมุม), j = รังสีไกล
            h = i - (j - i)                                       # รังสีถัดไปฝั่งผนัง — ใช้หาแนวผนัง
            if h < 0 or h >= n:
                continue
            rn, yn, yf = rays[i][1], rays[i][0], rays[j][0]
            if rn > CORNER_NEAR or rn < 1.0 or rays[h][1] >= CORNER_RANGE:
                continue
            # ผนังตรงยาว (ทางเดิน) ก็ให้ระยะรังสีข้างกันกระโดดได้เมื่อมุมตื้น — นับเป็นมุมเฉพาะเมื่อรังสีไกล "ทะลุ" แนวผนัง
            # (เส้นผ่านจุดชนของรังสี h กับ i) ไปเกิน 1 ม. ; ไม่ตัดแนวผนังเลย (ขนาน/แยกออก = มองไปตามทางเดิน) = ไม่ใช่มุม
            ax, az = math.sin(rays[h][0]) * rays[h][1], math.cos(rays[h][0]) * rays[h][1]
            bx, bz = math.sin(yn) * rn, math.cos(yn) * rn
            fx, fz = math.sin(yf), math.cos(yf)
            ex, ez = bx - ax, bz - az
            den = fx * ez - fz * ex
            if abs(den) < 1e-9:
                continue
            s_hit = (ax * ez - az * ex) / den                   # ระยะตามรังสีไกลที่ชนแนวผนัง
            if s_hit <= 0.0 or rays[j][1] <= s_hit + 1.0:
                continue
            ye = yn + 0.6 * _wrap(yf - yn)
            dist = rn + 1.5
            px, pz = eye[0] + math.sin(ye) * dist, eye[2] + math.cos(ye) * dist
            if any((px - c[0]) ** 2 + (pz - c[1]) ** 2 < 6.25 for c in cl):
                continue
            score = rn + 6.0 * abs(_wrap(ye - hd))
            if best is None or score < best[0]:
                best = (score, px, pz)
        if best is None:
            return
        _s, px, pz = best
        fy = cm.floor_y(px, pz)
        P = (px, (fy if fy is not None and abs(fy - b.y0) < 3.0 else b.y0) + HEAD_Y, pz)
        cur = m["corner"]
        if cur is None or (cur[0][0] - px) ** 2 + (cur[0][2] - pz) ** 2 > 4.0:
            m["corner"] = (P, t, None, t)

    def _corner_tick(self, t):
        """สแกนมุมหนึ่งบอทต่อเฟรม (วนคิว) — เฉพาะตัวที่กำลังเดินทาง ไม่เห็นผู้เล่น"""
        n = len(self.bots)
        for k in range(n):
            b = self.bots[(self._corner_rr + k) % n]
            m = b.meta
            if b.alive and m["moving"] and not m["sees"] and t >= m["corner_t"] and m["state"] != "swing":
                self._corner_scan(b, t)
                self._corner_rr = (self._corner_rr + k + 1) % n
                return

    def _to_hold(self, b, t, x=None, z=None, yaw=None, facings=None):
        m = b.meta
        x = b.x if x is None else x
        z = b.z if z is None else z
        if yaw is None:
            kn = m["know"]
            if kn is not None:
                yaw = math.atan2(kn[0] - x, kn[1] - z)
            elif self.side == "atk":
                sp = (self.cm.spawns or {}).get("atk") or [x, z - 1.0]
                yaw = math.atan2(sp[0] - x, sp[1] - z)
            else:
                yaw = math.atan2(self.obj[0] - x, self.obj[1] - z)
        m["home"] = (x, z, yaw)
        fac = facings or self._facings(x, z, b.y0, yaw)
        m["facings"] = fac
        m["fpitch"] = [self._face_pitch(x, z, b.y0, f) for f in fac]
        m["glance_i"] = 0
        m["glance_t"] = t + self.rng.uniform(*self._glance())
        m["state"] = "hold"
        m["sub"] = ""
        m["nav"] = None

    def _start_swing(self, b, t, target, sub="info"):
        """โผล่ไปดูจุด target — sub 'info' (ข้อมูล) / 'trade' (เพื่อนตาย) / 'jiggle' (จิ้มไหล่แล้วกลับ) / 'follow' (ตามเพื่อน
        ที่ swing ห่าง TRADE_GAP เพื่อเทรด) ; swing จริง ('info') ทอยให้เพื่อนใกล้ ๆ ตามไปด้วย (FOLLOW_P)"""
        m = b.meta
        m["state"] = "swing"
        m["sub"] = sub
        m["target"] = (float(target[0]), float(target[1]))
        m["jig_until"] = None
        m["pl_t"] = t
        m["repeek_at"] = None
        m["corner"] = None
        self._nav_to(b, target, 1.5)
        self._count("swing:" + sub)
        if sub != "info":
            return
        best = None
        for o in self.bots:
            mo = o.meta
            if o is b or not o.alive or mo["state"] != "hold" or mo["sees"] or mo["trade_at"] is not None:
                continue
            d = math.hypot(o.x - b.x, o.z - b.z)
            if d <= FOLLOW_R and (best is None or d < best[0]):
                best = (d, o)
        if best is not None and self.rng.random() < _lerp(FOLLOW_P[0], FOLLOW_P[1], self.u):
            o = best[1]
            run = WEAPONS[o.weapon]["run_speed"]
            self._start_swing(o, t, target, sub="follow")
            o.meta["follow"] = t + TRADE_GAP / run + self.rng.uniform(0.0, 0.3)   # ออกหลังคนนำ ~TRADE_GAP ม.

    def _start_repo(self, b, t, info, back=False):
        """ย้ายไปจุดเฝ้ายอดนิยมใกล้ ๆ (≤ REPO_R) ; back = ถอยไปจุดที่ห่างข้อมูลกว่าเดิม ≥ 4 ม. (≤ 12 ม. จากตัว)"""
        m = b.meta
        kind = "def" if self.side == "atk" else "atk_post"
        taken = [o.meta["home"] for o in self.bots if o is not b and o.alive]
        d0 = math.hypot(b.x - info[0], b.z - info[1])
        best = None
        for s, hd in (self.cm.holds or {}).items():
            for h in (hd or {}).get(kind) or ():
                d = math.hypot(h[0] - b.x, h[1] - b.z)
                if back:
                    if not (1.5 < d <= 12.0) or math.hypot(h[0] - info[0], h[1] - info[1]) < d0 + 4.0:
                        continue
                elif not 1.5 < d <= REPO_R:
                    continue
                if all(math.hypot(h[0] - q[0], h[1] - q[1]) >= 2.0 for q in taken):
                    if best is None or d < best[0]:
                        best = (d, h)
        if best is None:
            return
        h = best[1]
        m["state"] = "repo"
        m["sub"] = "back" if back else ""
        self._count("fallback" if back else "repo")
        # ถอย/ย้าย: หันไปทางข้อมูลเมื่อถึง (ทิศของจุดเฝ้าที่ bake อาจหันไปทางอื่น)
        m["dest"] = (h[0], h[1], math.atan2(info[0] - h[0], info[1] - h[1]) if back else h[2])
        m["corner"] = None
        self._nav_to(b, h[:2], 0.5)

    def _start_collapse(self, b, t, info):
        """เข้าช่วย (collapse): ข้อมูลอยู่ไกลเกิน swing — ย้ายไปจุดเฝ้ายอดนิยมที่ห่างข้อมูล 6–18 ม. และเห็นบริเวณนั้น
        (ตั้ง crossfire กับเพื่อนที่ปะทะอยู่ แทนเฝ้ามุมที่ไม่เกี่ยวต่อ) — เดินเงียบเมื่อใกล้ข้อมูล (RUN_FAR) ; ไม่มีจุด = False"""
        m = b.meta
        cm = self.cm
        kind = "def" if self.side == "atk" else "atk_post"
        taken = [o.meta["home"] for o in self.bots if o is not b and o.alive]
        ix, iz = info
        fi = cm.floor_y(ix, iz)
        tgt = (ix, (fi if fi is not None else b.y0) + HEAD_Y, iz)
        best = None
        for hd in (cm.holds or {}).values():
            for h in (hd or {}).get(kind) or ():
                di = math.hypot(h[0] - ix, h[1] - iz)
                dm = math.hypot(h[0] - b.x, h[1] - b.z)
                if not (6.0 <= di <= 18.0) or dm > COLLAPSE_D[1] or dm < 2.0 or (best is not None and dm >= best[0]):
                    continue
                if any(math.hypot(h[0] - q[0], h[1] - q[1]) < 2.5 for q in taken):
                    continue
                fy = cm.floor_y(h[0], h[1])
                if fy is None or cm.blocked((h[0], fy + EYE_Y, h[1]), tgt):
                    continue
                best = (dm, h)
        if best is None:
            return False
        h = best[1]
        m["collapse_t"] = t
        m["state"] = "repo"
        m["sub"] = "collapse"
        self._count("collapse")
        m["dest"] = (float(h[0]), float(h[1]), math.atan2(ix - h[0], iz - h[1]))
        m["corner"] = None
        self._nav_to(b, h[:2], 0.5)
        return True

    def _start_swap(self, b, t):
        """หลุดสายตาหลังยิงกัน: ย้ายไป off-angle ใหม่ 2.5–6 ม. ที่ยังเห็นบริเวณที่ผู้เล่นอยู่ (ผู้เล่นเล็งจุดเดิมรอ = โดนจากมุม
        ใหม่) — จุดเฝ้า bake ใกล้ ๆ + จุดวงรอบตัว 8 ทิศ ; คะแนน = มุมต่างจากจุดเดิมเมื่อมองจากผู้เล่น (off-angle) ; ไม่มีจุด
        ที่เห็นบริเวณเดิม = เฝ้าต่อที่เดิม"""
        m = b.meta
        sp = m["seen_pos"]
        if sp is None:
            return False
        cm = self.cm
        kind = "def" if self.side == "atk" else "atk_post"
        taken = [o.meta["home"] for o in self.bots if o is not b and o.alive]
        cands = []
        for hd in (cm.holds or {}).values():
            for h in (hd or {}).get(kind) or ():
                if SWAP_R[0] <= math.hypot(h[0] - b.x, h[1] - b.z) <= SWAP_R[1]:
                    cands.append((float(h[0]), float(h[1])))
        a0 = self.rng.uniform(0.0, _TWO_PI)
        for k in range(8):
            a = a0 + k * _TWO_PI / 8
            r = self.rng.uniform(SWAP_R[0], 0.5 * (SWAP_R[0] + SWAP_R[1]))
            cands.append((b.x + r * math.sin(a), b.z + r * math.cos(a)))
        tgt = (sp[0], sp[1] + HEAD_Y, sp[2])
        a_old = math.atan2(b.x - sp[0], b.z - sp[2])
        d_old = math.hypot(b.x - sp[0], b.z - sp[2])
        best = None
        for x, z in cands:
            if any(math.hypot(x - q[0], z - q[1]) < 2.0 for q in taken):
                continue
            dn = math.hypot(x - sp[0], z - sp[2])
            if dn < 4.0 or dn > d_old + 6.0:
                continue                              # ไม่เข้าไปใกล้ผู้เล่น / ไม่ถอยไกลจนเลิกคุมพื้นที่
            fy = cm.floor_y(x, z)
            if fy is None or abs(fy - b.y0) > 1.5 or not cm.disc_clear(x, z, BOT_R + 0.05):
                continue
            off = abs(_wrap(math.atan2(x - sp[0], z - sp[2]) - a_old))
            if off < math.radians(12.0) or (best is not None and off <= best[0]):
                continue
            if not cm.walk_clear(b.x, b.z, x, z, BOT_R) or cm.blocked((x, fy + EYE_Y, z), tgt):
                continue
            best = (off, x, z)
        if best is None:
            return False
        _o, x, z = best
        m["state"] = "repo"
        m["sub"] = "swap"
        self._count("swap")
        m["dest"] = (x, z, math.atan2(sp[0] - x, sp[2] - z))
        m["corner"] = None
        m["repeek_at"] = None
        self._nav_to(b, (x, z), 0.5)
        return True

    def _return_home(self, b, t):
        m = b.meta
        m["state"] = "return"
        self._nav_to(b, m["home"][:2], 0.6)

    def _think(self, b, t, dt, pv):
        m = b.meta
        if m["crouch_until"] is not None and t >= m["crouch_until"]:
            m["crouch_until"] = None
            b.crouch_to = 0.0
        b.update_crouch(dt)
        m["go"] = None
        m["run"] = False
        m["brake"] = False
        m["final"] = False
        m["strafe"] = None
        if m["defusing"] is not None:
            m["brake"] = True
            m["look"] = self._aim_to(b, (self.spike[0], self.spike_y + 0.2, self.spike[1]))
            return
        if m["sees"]:
            m["look"] = self._fight_look(b, t)
            if m["fire_at"] is not None and t >= m["fire_at"] - STOP_LEAD:
                m["contact_t"] = t
                if m["adad"] is not None and t < m["adad"]:
                    dx, dz = pv.x - b.x, pv.z - b.z     # ส่าย ADAD ระหว่างชุด: ตั้งฉากแนวผู้เล่น แล้ว counter-strafe (brake)
                    L = math.hypot(dx, dz) or 1.0      # ก่อนชุดถัดไป — ประตูยิงรอเข้า deadzone เอง (ไม่ยิงขณะวิ่ง)
                    m["strafe"] = (dz / L * m["adad_dir"], -dx / L * m["adad_dir"])
                else:
                    m["brake"] = True
                return
        elif m["trade_at"] is not None and t >= m["trade_at"]:
            m["trade_at"] = None                     # เพื่อนเพิ่งตายใกล้ ๆ: ออกเทรดไปทางคนยิง (swing เร็ว — ตัวขยับ = "angle")
            if m["state"] not in ("retake", "swing") and m["defusing"] is None:
                if self.hunter is b:
                    self.hunter = None
                self._start_swing(b, t, m["trade_pos"], sub="trade")
        elif t - m["tag_t"] < TAG_TURN and m["hit_from"] is not None:
            m["brake"] = True                        # โดนยิงจากที่มองไม่เห็น (หลัง/ข้าง): หยุดวิ่ง หันหาผู้ยิงก่อน — ทับทิศ
            m["look"] = self._aim_to(b, m["hit_from"])   # มองของสถานะเดินทาง (rotate/retake/return/clear ตั้งตามทางเดิน)
            return
        elif t - m["contact_t"] < m["contact_hold"] and m["seen_pos"] is not None:
            sp = m["seen_pos"]
            m["brake"] = True
            m["look"] = self._aim_to(b, (sp[0], sp[1] + HEAD_Y, sp[2]))
            return
        st = m["state"]
        getattr(self, "_st_" + st)(b, t, pv)
        if m["sees"]:
            m["look"] = self._fight_look(b, t)

    def _fight_look(self, b, t):
        """เล็งจุดเดียวกับที่กระสุนจะเล็ง (ตำแหน่งผู้เล่นเมื่อ lag วิก่อน, หัวหรือตัวตามที่ทอยไว้) — ทิศตัวบอทที่วาดจึงตรงกับ
        ทางกระสุน และ _shoot ไม่ต้องวาร์ปทิศ (หันไม่เกิน BOT_TURN เสมอ)"""
        m = b.meta
        p = m["p"]
        px, pz, pf, pc = self._trail_at(t - p["lag"])
        hy = pf + HEAD_Y - CROUCH_DROP * pc
        return self._aim_to(b, (px, hy if m["aim_head"] else hy - p["body_drop"], pz))

    def _st_hold(self, b, t, pv):
        m = b.meta
        if m["swap_at"] is not None and t >= m["swap_at"]:
            m["swap_at"] = None
            if self._start_swap(b, t):
                return
        hx, hz, _hy = m["home"]
        dh = (b.x - hx) ** 2 + (b.z - hz) ** 2
        if dh > 4.0:                                  # หลุดจุดไกล (ถอยหลังยิงกัน/ถูกดัน) = เดินกลับตาม nav
            self._return_home(b, t)
            return
        if dh > 0.36:
            if m["hold_try"] is None:
                m["hold_try"] = t
            if t - m["hold_try"] > 2.0:              # เข้าจุดเดิมไม่ได้ (ชนเพื่อน/ขอบ) = เฝ้าตรงนี้แทน ไม่ดันค้าง
                m["home"] = (b.x, b.z, m["home"][2])
                m["hold_try"] = None
            else:
                m["go"] = (hx, hz)
                m["final"] = True
        else:
            m["hold_try"] = None
        if m["repeek_at"] is not None and t >= m["repeek_at"]:
            m["repeek_at"] = None
            sp = m["seen_pos"]
            if sp is not None and math.hypot(sp[0] - b.x, sp[2] - b.z) <= SWING_MAX:
                self._start_swing(b, t, (sp[0], sp[2]))
                return
        m["look"] = self._idle_look(b, t)

    def _st_rotate(self, b, t, pv):
        m = b.meta
        if m["nav"] is None:
            if self._nav_ok:
                self._to_hold(b, t)
            m["look"] = self._idle_look(b, t)
            return
        res = self._follow(b, t)
        kn = m["know"]
        m["run"] = kn is None or t - kn[2] > 15.0 or math.hypot(kn[0] - b.x, kn[1] - b.z) > RUN_FAR
        if res == "arrived" or res == "fail":
            h = m["dest"]
            if h is not None and res == "arrived":
                self._to_hold(b, t, h[0], h[1], h[2], None)
            else:
                self._to_hold(b, t)
            m["look"] = self._idle_look(b, t)
            return
        if m["nav"][0] == "df" and t - m["pl_t"] > 0.5:
            m["pl_t"] = t
            m["pl"] = L = self.cm.path_len(m["nav"][1], b.x, b.z)
            if m["dest"] is None and L is not None and L <= 10.0:   # ไม่มีจุดเฝ้าปลายทาง: หยุดเมื่อเหลือทางเดินถึงเป้า ≤ 10 ม.
                self._to_hold(b, t)
                m["look"] = self._idle_look(b, t)
                return
        if m["run"] and m["pl"] is not None and m["pl"] <= WALK_LAST:
            m["run"] = False                         # ใกล้ถึงจุดเฝ้า (ไม่รู้ว่าผู้เล่นอยู่ไหน) = Shift เดินเข้า ไม่ให้เสียงเท้าบอกตำแหน่ง
        m["look"] = self._travel_look(b, t, preaim=not m["run"])

    def _st_swing(self, b, t, pv):
        """โผล่ไปดูจุดข้อมูล (วิ่ง, เล็งจุดนั้นรอ = peeker's advantage ของบอท) → เห็นแล้วหยุดยิง / ถึง/มองเห็นจุด =
        ค้างดู 1.5–3 วิ → กลับที่เดิม ; sub 'spike' (เสียงกู้) = เล็งจุดที่ได้ยิน เดินตามทางสู่ spike จนเห็นบริเวณคนกู้
        (_clear_ok — เห็นตัว spike ไม่นับ) หรือถึง spike ≤ PEEK_STOP ; push = ไม่หยุดจนถึง spike"""
        m = b.meta
        tx, tz = m["target"]
        fy = self.cm.floor_y(tx, tz)
        spot = (tx, (fy if fy is not None else b.y0) + HEAD_Y, tz)
        m["look"] = self._aim_to(b, spot)
        sub = m["sub"]
        if sub == "follow" and m["follow"] is not None:
            if t < m["follow"]:
                return                               # รอให้คนนำออกไปก่อน (เว้นระยะเทรด) — เล็งจุดเดียวกันรอ
            m["follow"] = None
            m["prog"] = (t, b.x, b.z)
        res = self._follow(b, t)
        m["run"] = True
        if sub == "jiggle":
            if m["jig_until"] is None and res == "moving":
                m["jig_until"] = t + self.rng.uniform(*JIGGLE_T)
            if (m["jig_until"] is not None and t >= m["jig_until"]) or res in ("arrived", "fail"):
                m["jig_until"] = None                # จิ้มไหล่พอแล้ว — กลับหลังที่กำบัง (เห็นผู้เล่นระหว่างนั้น = ยิงตามปกติ)
                self._return_home(b, t)
            return
        if sub == "spike":
            done = res in ("arrived", "fail")
            if not done and not m["push"] and t - m["pl_t"] > 0.1:
                m["pl_t"] = t
                done = self._clear_ok(b, m["cand"])
            if done:
                m["dclr_t"] = t
        else:
            done = res in ("arrived", "fail") or (t - m["pl_t"] > 0.1 and self._los_spot(b, t, spot))
        if done:
            m["state"] = "peekhold"
            m["until"] = t + self.rng.uniform(1.5, 3.0)
            m["nav"] = None

    def _los_spot(self, b, t, spot):
        m = b.meta
        m["pl_t"] = t
        return not self.cm.blocked(b.eye(), spot)

    def _st_peekhold(self, b, t, pv):
        m = b.meta
        if m["swap_at"] is not None and t >= m["swap_at"]:
            m["swap_at"] = None
            if self._start_swap(b, t):
                return
        tx, tz = m["target"]
        fy = self.cm.floor_y(tx, tz)
        m["look"] = self._aim_to(b, (tx, (fy if fy is not None else b.y0) + HEAD_Y, tz))
        if t >= m["until"]:
            if self.side == "def" and m["sub"] == "spike":
                self._to_hold(b, t, yaw=math.atan2(tx - b.x, tz - b.z))     # เฝ้า spike จากตรงนี้
            else:
                self._return_home(b, t)

    def _st_repo(self, b, t, pv):
        m = b.meta
        res = self._follow(b, t)
        kn = m["know"]
        m["run"] = m["sub"] == "collapse" and (kn is None or math.hypot(kn[0] - b.x, kn[1] - b.z) > RUN_FAR)
        alert = m["preaim"] is not None and t - m["alert_t"] < ALERT_KEEP
        m["look"] = self._travel_look(b, t) if alert else (self._travel_look(b, t, preaim=False) or m["look"])
        if res == "arrived":
            h = m["dest"]
            self._to_hold(b, t, h[0], h[1], h[2])
        elif res == "fail":
            if m["sub"] == "collapse":
                self._to_hold(b, t)                  # ไปจุดคุมไม่ได้ = เฝ้าตรงนี้ (ไม่ย้อนกลับจุดเดิมไกล ๆ)
            else:
                self._return_home(b, t)

    def _st_return(self, b, t, pv):
        m = b.meta
        res = self._follow(b, t)
        m["look"] = self._travel_look(b, t) or self._idle_look(b, t)
        if res == "arrived" or res == "fail":
            hx, hz, hy = m["home"]
            if res == "arrived":
                self._to_hold(b, t, hx, hz, hy, m["facings"])
            else:
                self._to_hold(b, t)

    def _st_hunt(self, b, t, pv):
        """ล่า: เดินเงียบไปตำแหน่งล่าสุดของผู้เล่น → ถึงแล้วกวาดดูรอบ 2 วิ → กลับที่เดิม"""
        m = b.meta
        res = self._follow(b, t)
        m["look"] = (m["preaim"] if m["preaim"] is not None and t - m["alert_t"] < 2.0 else
                     self._travel_look(b, t, preaim=False))
        if res in ("arrived", "fail"):
            m["state"] = "clear"
            m["until"] = t + self.rng.uniform(1.5, 2.5)
            m["nav"] = None
            m["glance_t"] = t

    def _st_clear(self, b, t, pv):
        m = b.meta
        if t >= m["glance_t"]:
            m["glance_t"] = t + 0.6
            m["look"] = (_wrap(m["yaw"] + self.rng.choice((-1.0, 1.0)) * self.rng.uniform(0.9, 2.2)), 0.0)
        if t >= m["until"]:
            if self.hunter is b:
                self.hunter = None
            self._return_home(b, t)

    def _st_retake(self, b, t, pv):
        m = b.meta
        R = self.retake
        ph = m["rtp"]
        sx, sz = self.spike
        m["sub"] = ph
        if ph == "plan":                              # รอแผน (ทางเข้า/สนามระยะ spike)
            m["look"] = self._aim_to(b, (sx, self.spike_y + HEAD_Y, sz))
            return
        if ph == "to_stage":
            if t < m["start_t"]:
                m["look"] = self._aim_to(b, (sx, self.spike_y + HEAD_Y, sz))
                return
            if m["nav"] is None:                      # ตัวที่ k ในทางเข้าเดียวกันหยุดก่อนจุดรวมพล ~1.2 ม./ลำดับ (ต่อแถวตามทาง)
                self._nav_df(b, m["stage"], 1.2 + 1.2 * m["order"], pin=True)
            res = self._follow(b, t)
            m["run"] = math.hypot(b.x - sx, b.z - sz) > RETAKE_WALK + 5.0
            m["look"] = self._travel_look(b, t)
            if res == "arrived" or res == "fail":
                m["nav"] = None
                if res == "fail" or self.rng.random() < R["trickle"]:
                    m["rtp"] = "go_wait"                  # ใจร้อน/ไปจุดรวมพลไม่ได้ = เข้าเลย
                    m["go_at"] = t
                    m["trickled"] = res != "fail"
                else:
                    m["rtp"] = "staged"
            return
        if ph == "staged":
            e = m["entry"]
            if e is None:                             # อยู่ในไซต์อยู่แล้ว: เฝ้า/มองสลับตรงนั้นจนทีมเข้า
                m["look"] = self._idle_look(b, t)
            else:
                fy = self.cm.floor_y(e[0], e[1])
                m["look"] = self._aim_to(b, (e[0], (fy if fy is not None else self.spike_y) + HEAD_Y, e[1]))
            if m["go_at"] is not None and t >= m["go_at"]:
                m["rtp"] = "go"
            return
        if ph == "go_wait":
            m["look"] = self._aim_to(b, (sx, self.spike_y + HEAD_Y, sz))
            if m["go_at"] is not None and t >= max(m["go_at"], m["start_t"]):
                m["rtp"] = "go"
            return
        if ph == "go":
            if m["nav"] is not None and m["nav"][0] == "df" and m["nav"][1] is not R["df"]:
                m["nav"] = None                       # ทางอื่นค้างมา (จุดรวมพล) — 'go' ต้องเดินสู่ spike เท่านั้น (เทียบตัวสนาม
                #                                       ไม่ใช่พิกัด: _field ปัดเป้า 2 ตำแหน่ง ≠ self.spike ดิบ = วางทางใหม่ทุกเฟรม)
            if m["nav"] is None:
                gl = self.spike_goal                  # spike บนกล่อง = เดินไปจุดพื้นข้างกล่องที่เอื้อมกู้ได้
                self._nav_df(b, gl, 0.9 if gl == self.spike else 0.4, pin=True)
            res = self._follow(b, t)
            if t - m["pl_t"] > 0.5:
                m["pl_t"] = t
                m["pl"] = self.cm.path_len(m["nav"][1], b.x, b.z)
            L = m["pl"]
            m["run"] = L is not None and L > RETAKE_WALK
            if L is not None and L <= RETAKE_WALK + 5.0:        # เข้าไซต์: เคลียร์มุมที่ผ่าน (pie) ก่อน ไม่มีแล้วค่อยเล็งแถว spike
                m["look"] = self._corner_look(b, t) or self._aim_to(b, (sx, self.spike_y + HEAD_Y, sz))
            else:
                m["look"] = self._travel_look(b, t)
            if res == "arrived" or (res == "fail" and math.hypot(b.x - sx, b.z - sz) <= DEFUSE_R - 0.3):
                m["nav"] = None
                m["rtp"] = "at_spike"
                m["at_spike_t"] = t
            elif res == "fail":
                m["nav"] = None
            return
        # at_spike: กู้ถ้าไม่เห็นผู้เล่นและทันเวลา ไม่งั้นเฝ้า
        if not self._try_defuse(b, t):
            m["look"] = self._idle_look(b, t) if m["preaim"] is not None else (m["look"] or (m["yaw"], 0.0))

    def _wait_cover(self, b, t, need):
        """รีเทค: ถึง spike คนแรกแต่ไม่รู้ว่าคนวางอยู่ไหน (ไม่มีข้อมูลสด) และเพื่อนกำลังตามมา = เฝ้ารอให้เพื่อนเข้ามาคุมก่อน
        (≤ COVER_WAIT ต่อแรงค์ ; เวลาไม่พอ = กู้เลย) — คนจริงไม่นั่งกู้โล่ง ๆ ทั้งที่คนวางยังเล็งรออยู่ที่ไหนสักแห่ง"""
        m = b.meta
        wait = _lerp(COVER_WAIT[0], COVER_WAIT[1], self.u)
        if wait <= 0.0 or t - m["at_spike_t"] >= wait:
            return False
        if self.explode_t is not None and self.explode_t - t < need + DEFUSE_MARGIN + wait:
            return False
        kn = m["know"]
        if kn is not None and kn[3] not in ("planted",) and t - kn[2] < 4.0:
            return False                             # รู้ว่าคนวางอยู่ไหน (เพิ่งเห็น/ได้ยิน) — ตัดสินจากการปะทะแทน
        sx, sz = self.spike
        coming = covered = False
        for o in self.bots:
            mo = o.meta
            if o is b or not o.alive or mo["state"] != "retake":
                continue
            if math.hypot(o.x - sx, o.z - sz) <= 8.0:
                covered = True
                break
            if mo["rtp"] in ("go", "go_wait", "staged", "to_stage"):
                coming = True
        return coming and not covered

    def _try_defuse(self, b, t):
        m = b.meta
        if self.spike is None or self.defused:
            return False
        if self._defuser is not None and self._defuser is not b and self._defuser.alive:
            return False
        if m["sees"] or t - m["contact_t"] < 1.0:
            return False
        need = DEFUSE_T - self.bot_banked
        if self.explode_t is not None and self.explode_t - t < need:
            return False
        if self.side == "atk" and self._wait_cover(b, t, need):
            return False
        sx, sz = self.spike
        if math.hypot(b.x - sx, b.z - sz) > DEFUSE_R or not self._reach_ok(b.y0, self.spike_y):
            return False
        if self.cm.blocked(b.eye(), (sx, self.spike_y + 0.2, sz)):
            return False
        m["defusing"] = t
        self._defuser = b
        self._emit({"k": "defuse_start", "bot": b})
        return True

    def _stop_defuse(self, b, t):
        m = b.meta
        prog = self.bot_banked + (t - m["defusing"])
        if prog >= DEFUSE_HALF:
            self.bot_banked = DEFUSE_HALF
        m["defusing"] = None
        if self._defuser is b:
            self._defuser = None
        ev = {"k": "defuse_stop", "bot": b}
        (self.events if self._in_update else self._ev_out).append(ev)

    def _defuse_ctl(self, b, t):
        m = b.meta
        if m["defusing"] is None:
            return
        if m["sees"]:
            self._stop_defuse(b, t)
            return
        if self.bot_banked + (t - m["defusing"]) >= DEFUSE_T:
            m["defusing"] = None
            self._defuser = None
            self.defused = True
            self._emit({"k": "defused", "bot": b})
            for o in self._alive():
                if o.meta["state"] == "retake":
                    o.meta["rtp"] = "at_spike"

    # ───────────────────────── ร่างกาย ─────────────────────────
    def _turn(self, b, dt):
        m = b.meta
        lk = m["look"]
        if lk is None:
            if b.speed() > 0.5:
                lk = (math.atan2(b.vel[0], b.vel[1]), 0.0)
            else:
                return
        mx = math.radians(BOT_TURN) * dt
        dy = _wrap(lk[0] - m["yaw"])
        m["yaw"] = _wrap(m["yaw"] + max(-mx, min(mx, dy)))
        dp = lk[1] - m["pitch"]
        m["pitch"] += max(-mx, min(mx, dp))

    def _move(self, b, t, dt):
        m = b.meta
        run_sp = WEAPONS[b.weapon]["run_speed"]
        vx, vz = b.vel
        sp = math.hypot(vx, vz)
        go = m["go"]
        wish = (0.0, 0.0)
        if m["strafe"] is not None:
            wish = m["strafe"]                       # ส่าย ADAD (ยิงไม่ได้จนกว่าจะ counter-strafe เข้า deadzone)
            m["run"] = True
            go = None
        elif m["brake"] or go is None:
            if m["brake"] and sp > 0.3:
                wish = (-vx / sp, -vz / sp)          # counter-strafe ถึง deadzone ~60 ms แบบผู้เล่น
        else:
            dx, dz = go[0] - b.x, go[1] - b.z
            L = math.hypot(dx, dz)
            if m["final"]:
                if L > 0.1 + sp * 0.09:
                    wish = (dx / L, dz / L)
            elif L > 0.35:
                wish = (dx / L, dz / L)
            elif sp > 0.1:
                wish = (vx / sp, vz / sp)             # ถึง waypoint ก่อนได้จุดใหม่: ไหลต่อ ไม่เบรก
            elif L > 0.05:
                wish = (dx / L, dz / L)               # ยืนนิ่งแต่ waypoint ห่าง 0.05–0.35 ม. (next_waypoint คืนจุดเดิมเพราะห่าง
                #                                       ≥ 0.3 ม.) — เดิมไม่เดินเลย ยืนค้างทั้งรอบ (Lotus rotate)
        if wish == (0.0, 0.0) and not m["brake"]:     # ยืนทับเพื่อน (< 0.7 ม. — บอทไม่ชนกันเอง) = เดินแยกออกช้า ๆ
            for o in self.bots:
                if o is b or not o.alive:
                    continue
                dx, dz = b.x - o.x, b.z - o.z
                d2 = dx * dx + dz * dz
                if 1e-8 < d2 < 0.49:
                    d = math.sqrt(d2)
                    wish = (dx / d, dz / d)
                    break
        cap = movement.speed_cap(run_sp, walk=not m["run"], crouch=b.crouch_to >= 0.5)
        dtag = t - m["tag_t"]
        if dtag < TAG_REC:
            u = max(0.0, dtag / TAG_REC)
            cap *= TAG_SLOW + (1.0 - TAG_SLOW) * u * u * (3.0 - 2.0 * u)
        movement.step(b.vel, wish, cap, dt)
        m["moving"] = go is not None and not m["brake"]
        if b.vel[0] or b.vel[1] or m["air"]:
            x, z, s = self.cm.move(b.x, b.z, b.y0, b.vel, dt, BOT_R)
            b.x, b.z = x, z
            if s is not None:
                if s >= b.y0 - 1e-6:
                    b.y0 = s
                    m["vfall"] = 0.0
                    m["air"] = False
                else:
                    m["vfall"] += BOT_GRAVITY * dt
                    b.y0 = max(s, b.y0 - m["vfall"] * dt)
                    m["air"] = b.y0 > s + 1e-6
                    if not m["air"]:
                        m["vfall"] = 0.0
            sp = b.speed()
            if sp > WALK_KNEE * run_sp and t - m["step_t"] >= 0.22 + 0.18 * (1.0 - min(1.0, sp / run_sp)):
                m["step_t"] = t
                self._emit({"k": "step", "bot": b, "pos": (b.x, b.y0, b.z)})

    # ───────────────────────── สายตา / สังเกตเห็น ─────────────────────────
    def _perceive(self, b, t, pv):
        m = b.meta
        vis = False
        eye = pts = None
        if pv.alive:
            dx, dz = pv.x - b.x, pv.z - b.z
            d = math.hypot(dx, dz)
            if d <= LOS_MAX and (m["noticed"] or abs(_wrap(math.atan2(dx, dz) - m["yaw"])) <= FOV_HALF):
                eye = b.eye()
                pts = body_points(eye, pv.x, pv.z, pv.feet, pv.crouch)
                vis = self.cm.any_visible(eye, pts)
        m["vis"] = vis
        if vis:
            if m["vis_t0"] is None:                       # ขอบขาขึ้นของ LOS: คลาดนัดแรกสุ่มใหม่
                m["vis_t0"] = t
                m["e0"] = None
                m["t_first"] = None
                m["roll_t"] = t + self.rng.uniform(0.0, NOTICE_DT)
            if not m["noticed"]:
                off = self._off_deg(m, eye, pv)
                if off <= AIM_CONE or t - m["force_notice"] < 0.5:
                    self._notice(b, t, pv, off, True, eye, pts)
                elif t >= m["roll_t"]:
                    m["roll_t"] = t + NOTICE_DT
                    if self.rng.random() < self._notice_p(pv, eye, pts, d):
                        self._notice(b, t, pv, off, False, eye, pts)
            if m["noticed"]:
                m["seen_pos"] = (pv.x, pv.feet, pv.z)
                m["seen_t"] = t
                if m["rt_wait"] is not None:
                    if self._head_vis(eye, pts):
                        m["fire_at"] = t + m["rt_wait"]    # ดริล peek: นาฬิกาเริ่มเมื่อหัวผู้เล่นพ้นขอบ (แบบที่สอบเทียบ)
                        m["rt_wait"] = None
                    elif t >= m["notice_t"] + m["rt_wait"] + SHOULDER_EXTRA or t - m["tag_t"] < 0.5:
                        m["fire_at"] = t                   # ไหล่โผล่ค้าง/โดนยิงอยู่ = ยิงส่วนที่เห็น
                        m["rt_wait"] = None
                if not m["peek_q"] and t - m["notice_t"] >= QUICK_PEEK:
                    m["peek_q"] = True                     # โผล่แวบให้เห็น → จำจุดนี้หลังตอบสนองทัน
                    due = m["fire_at"] if m["fire_at"] is not None else t + (m["rt_wait"] or 0.0)
                    self._push(max(t, due), b, pv.x, pv.z, "seen")
                if m["fire_at"] is not None and t >= m["fire_at"]:
                    m["know"] = (pv.x, pv.z, t, "seen")
                    m["alert_t"] = t
                    m["preaim_dirty"] = True
        elif m["vis_t0"] is not None:                      # ขอบขาลง
            m["vis_t0"] = None
            if m["noticed"]:
                m["noticed"] = False
                m["last_seen_end"] = t
                reacted = m["fire_at"] is not None and t >= m["fire_at"]
                m["fire_at"] = None
                m["rt_wait"] = None
                if reacted:
                    m["contact_t"] = t
                    m["contact_hold"] = self.rng.uniform(*CONTACT_HOLD)
                    p_swap = _lerp(SWAP_P[0], SWAP_P[1], self.u) * (1.5 if t - m["tag_t"] < 3.0 else 1.0)
                    m["swap_at"] = None
                    if m["state"] in ("rotate", "return", "repo") and m["seen_pos"] is not None:
                        # ปะทะระหว่างเดินทาง: หยุดเฝ้ามุมนั้นตรงนี้ (คนไม่เดินทางเดิมต่อหน้าศัตรูที่เพิ่งยิงกัน) — เดิมเดินต่อ
                        sp = m["seen_pos"]                  # ตามเส้นทางแล้วโดนยิงจากมุมเดิมตอนหันไปทางอื่น
                        if self.hunter is b:
                            self.hunter = None
                        self._to_hold(b, t, yaw=math.atan2(sp[0] - b.x, sp[2] - b.z))
                    if m["state"] == "hold" and self.rng.random() < m["aggr"] * 0.6:
                        m["repeek_at"] = t + m["contact_hold"] + self.rng.uniform(0.2, 1.0)
                    elif m["state"] in ("hold", "peekhold") and self.rng.random() < p_swap:
                        # ยิงกันแล้วหลุดสายตา: ผู้เล่นรู้จุดนี้แล้ว → ย้าย off-angle (ค้างเล็งสั้น ๆ ก่อนขยับ) — โดนยิงมา = ย้ายบ่อยขึ้น
                        m["contact_hold"] = self.rng.uniform(0.3, 0.8)
                        m["swap_at"] = t + m["contact_hold"]
        m["sees"] = vis and m["noticed"]

    @staticmethod
    def _off_deg(m, eye, pv):
        """มุม (องศา) ระหว่างทิศเล็งปัจจุบันของบอทกับหัวผู้เล่น"""
        hy = pv.feet + HEAD_Y - CROUCH_DROP * pv.crouch
        dx, dy, dz = pv.x - eye[0], hy - eye[1], pv.z - eye[2]
        ty, tp = math.atan2(dx, dz), math.atan2(dy, math.hypot(dx, dz))
        c = (math.sin(m["pitch"]) * math.sin(tp) + math.cos(m["pitch"]) * math.cos(tp) * math.cos(ty - m["yaw"]))
        return math.degrees(math.acos(max(-1.0, min(1.0, c))))

    def _notice_p(self, pv, eye, pts, d):
        """โอกาสสังเกตเห็นต่อการทอย (CS bot vision): วิ่ง = 1 ; เดิน ยืน 1.0→0.75 หมอบ 0.9→0.6 ; นิ่ง ยืน 1.0→0.1
        หมอบ 0.8→0.05 (ผสมตามระยะ 8→27 ม.) × ส่วนตัวที่โผล่ × (0.5 + 0.5·ฝีมือ) ขั้นต่ำ 0.1%"""
        sp = pv.speed()
        if sp > WALK_KNEE * max(0.1, pv.run_speed):
            return 1.0
        u = max(0.0, min(1.0, (d - NOTICE_NEAR) / (NOTICE_FAR - NOTICE_NEAR)))
        crouched = pv.crouch >= 0.5
        if sp > STILL_V:
            c = (0.9 - 0.3 * u) if crouched else (1.0 - 0.25 * u)
        else:
            c = (0.8 - 0.75 * u) if crouched else (1.0 - 0.9 * u)
        blocked = self.cm.blocked
        vis = sum(w for p, w in zip(pts, PT_W) if not blocked(eye, p))
        return max(0.001, c * vis * (0.5 + 0.5 * self.u))

    def _head_vis(self, eye, pts):
        blocked = self.cm.blocked
        return not blocked(eye, pts[0]) or not blocked(eye, pts[4]) or not blocked(eye, pts[5])

    def _notice(self, b, t, pv, off, in_cone, eye, pts):
        """ขอบขาขึ้นของ "สังเกตเห็น": ตั้งจังหวะนัดแรก = rt ของดริลที่ตรงสถานการณ์ + เวลาหัน + ช้าจากรอบนอกสายตา ∓ PEEK_ADV
        ดริล "peek" สอบเทียบโดยเริ่มนาฬิกาเมื่อหัวผู้เล่นพ้นขอบ (gundrills see_pts='head') — เห็นแค่ไหล่ = จำได้/บอกเพื่อน
        แต่นาฬิกายิงรอจนหัวโผล่"""
        m = b.meta
        moving = b.speed() > 0.5
        sp = m["seen_pos"]
        repeek = (sp is not None and t - m["seen_t"] < REPEEK_T
                  and math.hypot(pv.x - sp[0], pv.z - sp[2]) < 3.0)
        prea = (t - m["alert_t"] < ALERT_LONG and t - m["alert0"] >= PREAIM_T and off <= PREAIM_CONE) or repeek
        drill = "angle" if (prea or moving) else "peek"
        p = self.P[drill]
        rt = p["rt"]
        if off > PREAIM_CONE:
            rt += off / BOT_TURN
            if not in_cone:
                rt += min(OFFAIM_CAP, OFFAIM_S * (off - PREAIM_CONE))
        w = pv.weapon if pv.weapon in WEAPONS else "vandal"
        if moving:
            pa = -duel.PEEK_ADV                            # บอทเป็นฝ่ายขยับออกมา = เห็นก่อน
        elif pv.speed() > guns.deadzone(w) * max(0.1, pv.run_speed):
            pa = duel.PEEK_ADV                             # ผู้เล่นเป็นฝ่าย peek เข้าหาบอทที่ยืนนิ่ง
        else:
            pa = 0.0
        if drill == "peek" and not self._head_vis(eye, pts):
            m["fire_at"] = None
            m["rt_wait"] = rt + pa
        else:
            m["fire_at"] = t + rt + pa
            m["rt_wait"] = None
        m["rt_last"] = rt + pa
        m["drill"] = drill
        m["p"] = p
        m["noticed"] = True
        m["notice_t"] = t
        m["peek_q"] = False
        m["burst_i"] = 0
        if t - m["last_seen_end"] > ENGAGE_GAP:          # การปะทะใหม่
            m["aim_head"] = self.rng.random() < p["head_p"]
            m["crouch_fire"] = self.rng.random() < BOT_CROUCH_P
            m["spotted"] += 1
            self._count("engage:" + drill + (":moving" if moving else ""))
            self._emit({"k": "spotted", "bot": b})
            self._callout(b, t, pv.x, pv.z)
        if m["defusing"] is not None:
            self._stop_defuse(b, t)

    # ───────────────────────── ยิง / แม็ก ─────────────────────────
    def _trail_at(self, t):
        tr = self._trail
        for i in range(len(tr) - 1, -1, -1):
            if tr[i][0] <= t:
                return tr[i][1:]
        return tr[0][1:]

    def _fire_ctl(self, b, t, pv):
        m = b.meta
        if not m["sees"] or m["fire_at"] is None or t < m["fire_at"] or t < m["next_shot"]:
            return
        if m["reload_until"] or m["defusing"] is not None:
            return
        if m["mag"] <= 0:
            self._reload(b, t)
            return
        if not guns.is_accurate(b.weapon, b.speed()) and not m["run_shoot"]:
            return                                         # ยังเร็วเกิน deadzone — รอ counter-strafe (บอทมีวินัย)
        if m["t_first"] is None and m["crouch_fire"] and m["crouch_until"] is None:
            b.crouch_to = 1.0
            m["crouch_until"] = t + self.rng.uniform(*BOT_CROUCH_HOLD)
            m["crouch_fire"] = False
        self._shoot(b, t, pv)
        m["mag"] -= 1
        m["adad"] = None
        w = WEAPONS[b.weapon]
        burst = None
        if w["auto"]:                                  # ไกล = แตะ/ชุดสั้น ; ใกล้ = สเปรย์ยาว (คนจริงไม่แตะที่ 5 ม.)
            d = math.hypot(pv.x - b.x, pv.z - b.z)
            burst = m["p"]["burst"]
            if d >= BURST_FAR:
                burst = max(1, burst // 2)
            elif d <= BURST_NEAR:
                burst += SPRAY_ADD
        m["next_shot"] = t + burst_gap(b.weapon, m, burst)
        if (w["auto"] and m["burst_i"] == 0 and b.crouch_to < 0.5 and m["mag"] > 0
                and self.rng.random() < _lerp(ADAD_P[0], ADAD_P[1], self.u)):
            m["adad"] = t + self.rng.uniform(*ADAD_T)  # จบชุด: ส่าย ADAD สั้น ๆ (กลับทิศทุกครั้ง) แล้วหยุดก่อนชุดถัดไป
            self._count("adad")
            m["adad_dir"] = -m["adad_dir"]
        if m["mag"] <= 0:
            self._reload(b, t)

    def _shoot(self, b, t, pv):
        """กระสุนบอท 1 นัด (เลขเดียวกับ gunbots.gun_bot_fire) → event "shot" ; กำแพงใกล้กว่าส่วนที่โดน = ไม่โดน"""
        m = b.meta
        p = m["p"]
        px, pz, pf, pc = self._trail_at(t - p["lag"])
        hy = pf + HEAD_Y - CROUCH_DROP * pc
        ay = hy if m["aim_head"] else hy - p["body_drop"]
        eye = b.eye()
        aim = (px, ay, pz)
        if self.cm.blocked(eye, aim):                    # จุดที่ตั้งใจเล็งถูกบัง = ยิงส่วนที่โผล่ (หัว → อก → ไหล่ …)
            for q in body_points(eye, px, pz, pf, pc):
                if not self.cm.blocked(eye, q):
                    aim = q
                    break
        yaw0, pitch0 = arena.angles_to(eye, aim)       # ทิศตัวบอท (yaw/pitch) หันตาม _fight_look ด้วย BOT_TURN — ไม่วาร์ป
        sig = p["sigma"]
        if m["e0"] is None:
            m["e0"] = (self.rng.gauss(0.0, sig), self.rng.gauss(0.0, sig))
            m["t_first"] = t
        k = math.exp(-(t - m["t_first"]) / duel.SETTLE_TAU)
        fl = sig * duel.SETTLE_FLOOR
        ex = m["e0"][0] * k + self.rng.gauss(0.0, fl)
        ey = m["e0"][1] * k + self.rng.gauss(0.0, fl)
        crouch = b.crouch >= 0.5
        po, yo, (dyaw, dpitch) = self._own_random(self._spread, b, t, crouch)
        c = 1.0 - p["comp"]
        d = arena.dir_from_angles(yaw0 + math.radians(ex + yo * c) + dyaw, pitch0 + math.radians(ey + po * c) + dpitch)
        m["shots"] += 1
        zone, tz = guns.humanoid_zone(eye, d, pv.x, pv.z, pv.crouch, y0=pv.feet)
        tw = self.cm.ray(eye, d, tz if zone else SHOT_RANGE)
        if tw is not None and (zone is None or tw < tz):
            zone, tend = None, tw
        elif zone:
            tend = tz
        else:
            tend = SHOT_RANGE
        dmg = 0.0
        if zone:
            m["hits"] += 1
            m["heads"] += zone == "head"
            dmg = guns.damage_for(b.weapon, zone, math.hypot(b.x - pv.x, b.z - pv.z))
        self._emit({"k": "shot", "bot": b, "from": eye, "to": (eye[0] + d[0] * tend, eye[1] + d[1] * tend,
                                                                eye[2] + d[2] * tend),
                    "zone": zone, "dmg": dmg, "dir": d, "wall": tw is not None and zone is None})

    @staticmethod
    def _spread(b, t, crouch):
        """รีคอยล์ (pattern) + สเปรดของนัดนี้ → (pitch_off, yaw_off, (d_yaw, d_pitch)) — ใช้ random ระดับโมดูล (เรียกผ่าน _own_random)"""
        po, yo, sp = b.stab.shoot(t, crouch=crouch)
        sp += guns.move_error_deg(b.weapon, b.speed(), crouch)
        return po, yo, cone_offset(sp)

    def _reload(self, b, t):
        m = b.meta
        m["reload_until"] = t + WEAPONS[b.weapon]["reload"]
        m["burst_i"] = 0
        self._emit({"k": "reload", "bot": b, "pos": (b.x, b.y0, b.z)})

    def _reload_ctl(self, b, t):
        m = b.meta
        if m["reload_until"]:
            if t >= m["reload_until"]:
                m["reload_until"] = 0.0
                m["mag"] = WEAPONS[b.weapon]["mag"]
        elif (not m["sees"] and t - m["contact_t"] > RELOAD_IDLE and m["defusing"] is None
              and m["mag"] < RELOAD_LOW * WEAPONS[b.weapon]["mag"]):
            self._reload(b, t)

    # ───────────────────────── เล็งรอจากข้อมูล ─────────────────────────
    def _preaim_calc(self, b):
        """เล็งรอทางที่ข้อมูลมา: เห็นจุดนั้นตรง ๆ = เล็งหัวที่จุดนั้น ; ไม่เห็น = ช่องเปิด (รังสีระดับตาโล่ง ≥ 0.8 ระยะ
        หรือ 12 ม.) ที่ใกล้ทิศข้อมูลสุด (ทีละ 5° ถึง ±45°) = "ทางเข้า" ที่ผู้เล่นจะโผล่"""
        m = b.meta
        m["preaim_dirty"] = False
        kn = m["know"]
        if kn is None:
            m["preaim"] = None
            return
        cm = self.cm
        tx, tz = kn[0], kn[1]
        eye = b.eye()
        fy = cm.floor_y(tx, tz)
        ty = (fy if fy is not None else b.y0) + HEAD_Y
        d = math.hypot(tx - eye[0], tz - eye[2])
        if d < 0.5:
            return
        if not cm.blocked(eye, (tx, ty, tz)):
            m["preaim"] = arena.angles_to(eye, (tx, ty, tz))
            return
        yaw_t = math.atan2(tx - eye[0], tz - eye[2])
        need = min(d * 0.8, 12.0)
        best = None
        for k in range(1, 10):
            for s in (1.0, -1.0):
                yw = yaw_t + s * math.radians(5.0 * k)
                if cm.ray(eye, (math.sin(yw), 0.0, math.cos(yw)), need) is None:
                    best = yw
                    break
            if best is not None:
                break
        yw = yaw_t if best is None else best
        r = min(d, need)
        f2 = cm.floor_y(eye[0] + math.sin(yw) * r, eye[2] + math.cos(yw) * r)
        py = (f2 if f2 is not None else (fy if fy is not None else b.y0)) + HEAD_Y
        m["preaim"] = (yw, math.atan2(py - eye[1], r))

    def _preaim_tick(self):
        n = len(self.bots)
        done = 0
        for k in range(n):
            b = self.bots[(self._pre_rr + k) % n]
            if b.alive and b.meta["preaim_dirty"]:
                self._preaim_calc(b)
                done += 1
                if done >= 2:
                    self._pre_rr = (self._pre_rr + k + 1) % n
                    return

    # ───────────────────────── เฟรม ─────────────────────────
    def update(self, dt, t, pv):
        """หนึ่งเฟรมของทีมบอท → events (list ของ dict คีย์ "k" — ดู §11.1)"""
        self.t = t
        self.events = self._ev_out
        self._ev_out = []
        self._in_update = True
        if not self._nav_ok:
            self._setup_nav()
        tr = self._trail
        tr.append((t, pv.x, pv.z, pv.feet, pv.crouch))
        cut = t - TRAIL_KEEP
        k = 0
        while k < len(tr) - 2 and tr[k + 1][0] < cut:
            k += 1
        if k:
            del tr[:k]
        self._deliver(t)
        self._hear_steps(t, pv)
        self._spike_sounds(t, pv)
        if self.retake is not None:
            self._retake_tick(t)
        self._nav_tick(t)
        self._preaim_tick()
        self._corner_tick(t)
        for b in self.bots:
            if not b.alive:
                continue
            self._think(b, t, dt, pv)
            self._turn(b, dt)
            self._move(b, t, dt)
            self._perceive(b, t, pv)
            self._fire_ctl(b, t, pv)
            self._reload_ctl(b, t)
            self._defuse_ctl(b, t)
            m = b.meta
            m["state_s"] = m["state"] + (":" + m["sub"] if m["sub"] else "")
            m["vel"] = (b.vel[0], b.vel[1])          # §13.2 ให้ภาพ: ความเร็ว · เดินเงียบ (ท่าเดิน ไม่ใช่วิ่ง) · กำลังรีโหลด
            m["walk"] = not m["run"]
            m["reload"] = bool(m["reload_until"])
        self._in_update = False
        return self.events

    _in_update = False


# ─────────────────────────────── selftest ───────────────────────────────
def _open_map(half=25.0, walls=()):
    """ลานโล่ง (2·half)² ม. พื้น y 0 ขอบ VOID + กำแพง VOID เป็นสี่เหลี่ยม [(x0, z0, x1, z1)] — ไว้ทดสอบที่คุมเรขาคณิตได้"""
    n = int(2 * half / 0.25)
    kind = bytearray([FLOOR]) * (n * n)
    h = bytearray([H0]) * (n * n)
    for j in range(n):
        for i in range(n):
            if i == 0 or j == 0 or i == n - 1 or j == n - 1:
                kind[j * n + i] = VOID
    for x0, z0, x1, z1 in walls:
        for j in range(int((z0 + half) * 4), int((z1 + half) * 4)):
            for i in range(int((x0 + half) * 4), int((x1 + half) * 4)):
                kind[j * n + i] = VOID
    return ClutchMap(n, n, kind, h, x0=-half, z0=-half, slug="open", name="Open",
                     sites={"A": {"c": [0.0, 20.0], "plants": [[0.0, 20.0, 1]]}},
                     spawns={"atk": [0.0, -22.0], "def": [0.0, 22.0]})


def selftest():
    """คืน list ข้อผิดพลาด — ≤ 5 วิ, seed คงที่ (global random ถูกตั้ง/คืน — เทส 10c ตั้ง/กินเลขสุ่ม global เอง)"""
    errors = []
    T0 = time.perf_counter()
    rs = random.getstate()
    random.seed(12345)
    try:
        _selftest_body(errors)
    except Exception as ex:                                  # noqa: BLE001 — selftest ต้องรายงาน ไม่ระเบิด
        import traceback
        errors.append("clutchbots: exception " + "".join(traceback.format_exception_only(type(ex), ex)).strip()
                      + " @ " + traceback.format_exc().strip().splitlines()[-3].strip())
    finally:
        random.setstate(rs)
    print(f"CLUTCHBOTS SELFTEST {'OK' if not errors else 'FAIL'} ({_ST_INFO.get('line', '')} "
          f"total {time.perf_counter() - T0:.1f} s)")
    return errors


_ST_INFO = {}


def _pv(x, z, **kw):
    return PlayerView(x=x, z=z, **kw)


def _brain(cm, e, side="atk", tier=10, weapon="vandal", seed=1, k=None, left=40.0, site="A", t0=0.0):
    """สมองทดสอบ: ทุกตัวเป็นคนเฝ้า (ไม่หมุนเข้าเป้า) และไม่เตรียม nav ล่วงหน้า (สร้าง DistField เมื่อจำเป็นเท่านั้น)"""
    sc = {"t": side, "s": site, "n": len(e), "p": [0.0, 0.0, 0.0], "e": [list(p) for p in e], "left": left}
    if k is not None:
        sc["k"] = list(k)
    br = ClutchBrain(cm, sc, side, tier, weapon, random.Random(seed), t0)
    br._nav_ok = True
    for b in br.bots:
        b.meta.update(state="hold", role="anchor", nav=None, dest=None)
    return br


def _run(br, pv, t, secs, dt=1.0 / 60, fn=None):
    evs = []
    n = int(round(secs / dt))
    for _ in range(n):
        t += dt
        if fn is not None:
            fn(t)
        evs.extend(br.update(dt, t, pv))
    return t, evs


def _selftest_body(errors):
    info = []
    wall = (-0.5, -15.0, 0.5, 15.0)
    cm = _open_map(25.0, [wall])
    cm0 = _open_map(25.0, [])
    BX, BZ = -10.0, -10.0

    def at(deg, r, **kw):
        a = math.radians(deg)
        return _pv(BX + r * math.sin(a), BZ + r * math.cos(a), **kw)
    # ── 1) ด้านหน้าเห็นทันที / ด้านข้างต้องทอย / ข้างหลังไม่เห็น (ลานโล่ง ผู้เล่นยืนนิ่ง = เงียบ) ──
    front, flank, behind, crouch_far = [], [], 0, []
    for s in range(40):
        for case in ("front", "flank", "behind", "crouch"):
            if case == "behind" and s >= 20:
                continue
            br = _brain(cm0, [(BX, BZ, 0.0)], seed=100 + s)
            b = br.bots[0]
            b.meta["facings"] = [0.0]
            b.meta["fpitch"] = [0.0]
            if case == "front":
                pv = at(0, 15)
            elif case == "flank":
                pv = at(45, 15)
            elif case == "behind":
                pv = at(140, 12)
            else:
                pv = at(40, 24, crouch=1.0)
            t, lat = 0.0, None
            for f in range(60 * (3 if case == "behind" else 8)):
                t += 1 / 60
                br.update(1 / 60, t, pv)
                if b.meta["sees"]:
                    lat = f / 60.0
                    break
            if case == "front":
                front.append(lat)
            elif case == "flank":
                flank.append(lat)
            elif case == "behind":
                behind += lat is not None
            else:
                crouch_far.append(8.0 if lat is None else lat)
    if any(x is None or x > 1e-9 for x in front):
        errors.append(f"clutchbots: ด้านหน้า (ในกรวย ±12°) ต้องเห็นเฟรมแรก — {front[:5]}")
    fl = [x for x in flank if x is not None]
    if len(fl) < 38 or min(fl) <= 0.0 or sum(fl) / len(fl) < 0.12:
        errors.append(f"clutchbots: ด้านข้าง 45° ต้องทอยเห็น (ไม่ทันที) — เห็น {len(fl)}/40 เฉลี่ย "
                      f"{sum(fl) / max(1, len(fl)):.2f} วิ ต่ำสุด {min(fl) if fl else None}")
    if behind:
        errors.append(f"clutchbots: ข้างหลัง (นอก FOV) ยืนนิ่งต้องไม่ถูกเห็น — เห็น {behind}/20")
    mc = sum(crouch_far) / len(crouch_far)
    if mc < 1.0:
        errors.append(f"clutchbots: หมอบนิ่ง 24 ม. ด้านข้างต้องเห็นช้า (เฉลี่ย ≥ 1 วิ) — {mc:.2f} วิ")
    info.append(f"notice front 0 s, flank45 {sum(fl) / max(1, len(fl)):.2f} s, crouch24 {mc:.2f} s, behind {behind}/20")

    # ── 2) reaction ต่อระดับ: peek (ยืนเฝ้าไม่รู้ตัว) > angle (ตื่นตัวเล็งรอ) ; Radiant < Iron ──
    rts = {}
    for tier in (0, 12, 22):
        for alert in (False, True):
            br = _brain(cm0, [(BX, BZ, 0.0)], tier=tier, seed=7)
            b = br.bots[0]
            b.meta["facings"] = [0.0]
            b.meta["fpitch"] = [0.0]
            pv = at(0, 15, vx=2.0)                        # ผู้เล่นเดินเร็วกว่า deadzone (peek) → +PEEK_ADV แต่เงียบ
            t = 0.0
            if alert:
                b.meta["aggr"] = 0.0
                br._learn(b, 0.0, pv.x, pv.z, "hit")
                pv.alive = False
                t, _e = _run(br, pv, t, 0.5)                # มีเวลาหันไปเล็งรอ
                pv.alive = True
            br.update(1 / 60, t + 1 / 60, pv)
            rts[(tier, alert)] = b.meta["rt_last"]
            exp = duel.tier_params(tier, "vandal", "angle" if alert else "peek")["rt"] + duel.PEEK_ADV
            if b.meta["rt_last"] is None or abs(b.meta["rt_last"] - exp) > 0.02:
                errors.append(f"clutchbots: rt ระดับ {tier} alert={alert} = {b.meta['rt_last']} (คาด {exp:.3f})")
    if not (rts[(22, False)] < rts[(12, False)] < rts[(0, False)] and rts[(12, True)] < rts[(12, False)]):
        errors.append(f"clutchbots: ลำดับ reaction ผิด {rts}")
    info.append("rt peek Iron/Plat/Rad " + "/".join(f"{rts[(k, False)] * 1000:.0f}" for k in (0, 12, 22)) +
                " angle " + "/".join(f"{rts[(k, True)] * 1000:.0f}" for k in (0, 12, 22)) + " ms")
    # นอกกรวย: บวกเวลาหัน + 6 ms/° (ไม่เกิน 0.25 วิ)
    br = _brain(cm0, [(BX, BZ, 0.0)], tier=12, seed=3)
    b = br.bots[0]
    b.meta["facings"] = [0.0]
    pv = at(40, 15)
    b.meta["force_notice"] = 0.0
    br.update(1 / 60, 1 / 60, pv)
    off = b.meta["rt_last"] - duel.tier_params(12, "vandal", "peek")["rt"]
    if b.meta["rt_last"] is None or not (40 / 360.0 - 0.01 < off < 40 / 360.0 + 0.05):
        errors.append(f"clutchbots: ผู้เล่นโผล่ 40° นอกจุดเล็ง ต้องบวกเวลาหัน ~0.11 วิ — ได้ {off:.3f}")

    # ── 3) ได้ยิน: วิ่ง 30 ม. โล่ง = ได้ยิน, เดิน = ไม่, วิ่งหลังกำแพง 24 ม. = ไม่, 16 ม. = ได้ ──
    def heard(bx, bz, px, pz, v):
        br2 = _brain(cm, [(bx, bz, math.pi)], seed=5)          # หันหลังให้ผู้เล่น (ไม่เห็น)
        b2 = br2.bots[0]
        b2.meta["facings"] = [math.atan2(bx - px, bz - pz)]
        b2.meta["yaw"] = b2.meta["facings"][0]
        pvh = _pv(px, pz, vx=v)
        _t, ev = _run(br2, pvh, 0.0, 0.5)
        return b2.meta["know"] is not None and any(e["k"] == "heard" for e in ev)
    cases = [((-15.0, 20.0, 15.0, 20.0, 5.4), True, "วิ่ง 30 ม. โล่ง"),
             ((-15.0, 20.0, 15.0, 20.0, 2.8), False, "เดิน 30 ม."),
             ((-15.0, 20.0, 19.0, 20.0, 5.4), False, "วิ่ง 34 ม."),
             ((-12.0, 0.0, 12.0, 0.0, 5.4), False, "วิ่ง 24 ม. หลังกำแพง"),
             ((-8.0, 0.0, 8.0, 0.0, 5.4), True, "วิ่ง 16 ม. หลังกำแพง")]
    for args, want, name in cases:
        if heard(*args) != want:
            errors.append(f"clutchbots: ได้ยินเสียงเท้า {name} ต้องเป็น {want}")

    # ── 4) เสียง spike: เริ่มวาง 25 ม. ได้ยิน, 40 ม. ไม่ ; วางเสร็จ = ทุกตัวรู้ ──
    br = _brain(cm, [(-10.0, 20.0, math.pi), (-20.0, -18.0, math.pi)], seed=9)
    near, far_ = br.bots
    for b in br.bots:
        b.meta["facings"] = [math.pi]
    pv = _pv(14.0, 20.0)
    t = 0.0
    br.on_plant_start(t, (14.0, 0.0, 20.0))
    pv.planting = True
    t, _ev = _run(br, pv, t, 0.6)
    if not near.meta["psnd"]:
        errors.append("clutchbots: เริ่มวาง 24 ม. ต้องได้ยิน")
    if far_.meta["psnd"]:
        errors.append("clutchbots: เริ่มวาง 51 ม. ต้องไม่ได้ยิน")
    br.on_planted(t, (14.0, 0.0, 20.0))
    if far_.meta["know"] is None or far_.meta["know"][3] != "planted":
        errors.append("clutchbots: วางเสร็จแล้วทุกตัวต้องรู้ตำแหน่ง")

    # ── 5) กู้: commit ตามระดับ (Radiant 0.8 วิ / Iron 0) · แตะหลอก · กู้ไม่ทัน = ไม่สน · กู้ครึ่งไว้แล้ว ──
    def commit(tier, tap, left, banked=False):
        br3 = _brain(cm, [(-8.0, 5.0, math.pi)], side="def", tier=tier, seed=11, k=(8.0, 5.0), left=left)
        b3 = br3.bots[0]
        pvd = _pv(8.0, 5.0, defusing=True)
        tt = 0.0
        br3.on_defuse_start(tt, (8.0, 0.0, 5.0), banked)
        tt, _e = _run(br3, pvd, tt, tap)
        br3.on_defuse_stop(tt)
        pvd.defusing = False
        tt, _e = _run(br3, pvd, tt, 0.3)
        return b3.meta["committed"] is not None
    if commit(22, 0.3, 40.0):
        errors.append("clutchbots: Radiant ต้องไม่หลงกลแตะกู้ 0.3 วิ")
    if not commit(22, 1.2, 40.0):
        errors.append("clutchbots: Radiant ต้องโผล่เมื่อเสียงกู้ยาว 1.2 วิ")
    if not commit(0, 0.05, 40.0):
        errors.append("clutchbots: Iron ต้องหลงกลแตะกู้ (commit 0 วิ)")
    if commit(12, 2.0, 5.0):
        errors.append("clutchbots: เหลือ 5 วิ กู้ไม่ทัน — บอทต้องไม่สน")
    if not commit(12, 2.0, 5.0, banked=True):
        errors.append("clutchbots: กู้ครึ่งไว้แล้ว เหลือ 5 วิ ยังทัน — บอทต้องตอบสนอง")

    # ── 6) ammo/reload ต่อปืน ──
    for w in ("vandal", "phantom", "sheriff", "ghost", "classic"):
        br = _brain(cm0, [(BX, BZ, 0.0)], weapon=w, tier=16, seed=21)
        b = br.bots[0]
        b.meta["facings"] = [0.0]
        pv = at(0, 12)
        t, ev = _run(br, pv, 0.0, 12.0)
        shots = [e for e in ev if e["k"] == "shot"]
        rel = [e for e in ev if e["k"] == "reload"]
        n_before = next((i for i, e in enumerate(ev) if e["k"] == "reload"), None)
        n_shots_before = sum(1 for e in ev[:n_before] if e["k"] == "shot") if n_before is not None else len(shots)
        if not rel or n_shots_before != WEAPONS[w]["mag"]:
            errors.append(f"clutchbots: {w} ยิง {n_shots_before} นัดก่อนรีโหลด (แม็ก {WEAPONS[w]['mag']})")
        if b.meta["shots"] <= WEAPONS[w]["mag"]:
            errors.append(f"clutchbots: {w} ต้องยิงต่อหลังรีโหลดเสร็จ ({b.meta['shots']} นัดใน 12 วิ)")
    # รีโหลดตามเวลาปืน (วัดตรง)
    br = _brain(cm0, [(BX, BZ, 0.0)], weapon="ghost", seed=22)
    b = br.bots[0]
    br._reload(b, 1.0)
    br._reload_ctl(b, 1.0 + WEAPONS["ghost"]["reload"] - 0.01)
    mid = b.meta["reload_until"] > 0
    br._reload_ctl(b, 1.0 + WEAPONS["ghost"]["reload"] + 0.001)
    if not mid or b.meta["mag"] != WEAPONS["ghost"]["mag"] or b.meta["reload_until"]:
        errors.append("clutchbots: รีโหลด Ghost ต้องใช้ 1.5 วิพอดี")
    # burst_gap = gunbots.gun_bot_gap
    from .gunbots import BotAIMixin
    for w in ("vandal", "phantom", "sheriff", "ghost", "classic", "operator"):
        P = duel.tier_params(8, w)
        m1, m2 = {"p": P, "burst_i": 0}, {"p": P, "burst_i": 0}
        bb = Bot(0.0, 0.0)
        bb.weapon = w
        bb.meta = m2
        a1 = [round(burst_gap(w, m1), 9) for _ in range(9)]
        a2 = [round(BotAIMixin.gun_bot_gap(None, bb), 9) for _ in range(9)]
        if a1 != a2:
            errors.append(f"clutchbots: burst_gap {w} ไม่ตรง gunbots {a1} vs {a2}")

    # ── 7) tagging บนบอท ──
    br = _brain(cm0, [(BX, BZ, 0.0)], seed=31)
    b = br.bots[0]
    b.vel[:] = [0.0, 5.4]
    br.on_bot_damaged(b, 0.0, 40.0, "body", (0.0, 0.0, 30.0))
    b.meta["hit_from"] = None                            # วัดเส้นความเร็ว tagging ล้วน (ไม่หยุดหันหาผู้ยิง — ดู 10g)
    v0 = b.speed()
    b.meta.update(state="rotate", dest=None, nav=("path", [(BX, 20.0)], (BX, 20.0), 0.5), know=None,
                  path_i=0, prog=(0.0, b.x, b.z), preaim=None, alert_t=-99.0)
    pvt = _pv(20.0, 20.0, alive=False)
    sp = []
    t = 0.0
    for _ in range(60):
        t += 1 / 60
        br.update(1 / 60, t, pvt)
        sp.append(b.speed())
    if v0 > 5.4 * TAG_SLOW + 1e-6 or sp[12] > 3.2 or max(sp[45:]) < 5.0:
        errors.append(f"clutchbots: tagging ต้อง ×0.275 แล้วฟื้นใน ~0.5 วิ — {v0:.2f} {sp[12]:.2f} {max(sp[45:]):.2f}")

    # ── 8) ยิงไม่ทะลุกำแพง: ผู้เล่นหลังกำแพงหนา — บังคับยิง 200 นัดต้องไม่โดนเลย ; สุ่มบน testyard ทุกนัดที่โดนต้องไม่ถูกบัง ──
    br = _brain(cm, [(-8.0, 3.0, math.pi / 2)], tier=22, seed=41)
    b = br.bots[0]
    pv = _pv(8.0, 3.0)
    br._trail = [(0.0, pv.x, pv.z, 0.0, 0.0)]
    b.meta["p"] = br.P["angle"]
    b.meta["aim_head"] = True
    hits = 0
    for k in range(200):
        br.events = []
        br._shoot(b, 0.5 + k * 0.3, pv)
        hits += br.events[-1]["zone"] is not None
    if hits:
        errors.append(f"clutchbots: ยิงทะลุกำแพง {hits}/200 นัด")
    ty = testyard()
    rng = random.Random(77)
    pts = []
    while len(pts) < 160:
        x, z = rng.uniform(-19, 19), rng.uniform(-19, 19)
        if ty.disc_clear(x, z, 0.4):
            pts.append((x, z))
    bad = hit_hidden = hit_n = 0
    for k in range(80):
        (bx, bz), (px, pz) = pts[2 * k], pts[2 * k + 1]
        br = ClutchBrain(ty, {"s": "A", "e": [[bx, bz, 0.0]], "n": 1, "left": 60}, "atk", 22, "vandal",
                         random.Random(k), 0.0)
        b = br.bots[0]
        pv = _pv(px, pz, feet=ty.floor_y(px, pz) or 0.0)
        br._trail = [(0.0, px, pz, pv.feet, 0.0)]
        b.meta["p"] = br.P["angle"]
        b.meta["aim_head"] = k % 2 == 0
        eye = b.eye()
        vis = ty.any_visible(eye, body_points(eye, px, pz, pv.feet, 0.0))
        for s in range(6):
            br.events = []
            br._shoot(b, 1.0 + s * 0.35, pv)
            e = br.events[-1]
            if e["zone"] is not None:
                hit_n += 1
                if ty.blocked(e["from"], e["to"]):
                    bad += 1
                if not vis:
                    hit_hidden += 1
    if bad:
        errors.append(f"clutchbots: กระสุนโดนทั้งที่ถูกบัง {bad} นัด")
    info.append(f"wall shots {hits}/200, random {hit_n} hits {bad} blocked ({hit_hidden} on 7-pt-hidden)")

    # ── 9) can_bots_defuse (testyard, spike A) ──
    br = ClutchBrain(ty, {"s": "A", "e": [[-12.0, -8.0, 0.0]], "n": 1, "left": 60}, "atk", 12, "vandal",
                     random.Random(3), 0.0)
    while not br.prepare(100000):
        pass
    spk = (-12.0, 9.5)
    df = br._field(spk)
    df.run()
    L = ty.path_len(df, br.bots[0].x, br.bots[0].z)
    tt = L / KNIFE_SPEED + KNIFE_EQUIP
    ok = [br.can_bots_defuse(0.0, spk, tt + DEFUSE_T + 0.3), not br.can_bots_defuse(0.0, spk, tt + DEFUSE_T - 0.3)]
    br.bot_banked = DEFUSE_HALF
    ok += [br.can_bots_defuse(0.0, spk, tt + DEFUSE_HALF + 0.3), not br.can_bots_defuse(0.0, spk, tt + 3.0)]
    br.bots[0].alive = False
    ok.append(not br.can_bots_defuse(0.0, spk, 44.0))
    if not all(ok):
        errors.append(f"clutchbots: can_bots_defuse ผิด {ok} (ทางเดิน {L:.1f} ม.)")

    # ── 10) รีเทค (testyard A): แบ่งทางเข้า ≥ 2, รอที่จุดรวมพลก่อนเข้า, แล้วกู้สำเร็จเมื่อไม่มีใครขวาง ──
    random.seed(4242)
    e = [[14.5, 9.0, math.pi], [0.0, 16.0, math.pi], [-2.0, -8.0, 0.0], [12.5, 2.0, math.pi]]
    br = ClutchBrain(ty, {"s": "A", "e": e, "n": 4, "left": 80}, "atk", 19, "vandal", random.Random(8), 0.0)
    while not br.prepare(100000):
        pass
    pv = _pv(17.5, -13.0, alive=False)                   # ไม่มีผู้เล่นให้ปะทะ — ทดสอบการประสานรีเทคล้วน ๆ
    t = 0.0
    br.on_planted(t, (-12.0, 0.0, 9.5))
    entered_early, went, first_def, defused_t, n_ent = [], None, None, None, 0
    dt = 1 / 60
    for f in range(int(44 / dt)):
        t += dt
        ev = br.update(dt, t, pv)
        R = br.retake
        if R["plan"] and not n_ent:
            n_ent = len({b.meta["entry"] for b in br.bots if b.meta["entry"] is not None})
        if R["go_t"] is None:
            for b in br.bots:
                if (b.meta["stage"] is not None and not b.meta["trickled"]
                        and math.hypot(b.x + 12.0, b.z - 9.5) < ENTRY_R - 2.5):
                    entered_early.append(b.meta["idx"])
        elif went is None:
            went = t
        for e_ in ev:
            if e_["k"] == "defuse_start" and first_def is None:
                first_def = t
            if e_["k"] == "defused":
                defused_t = t
        if defused_t is not None:
            break
    if n_ent < 2:
        errors.append(f"clutchbots: รีเทคต้องแบ่ง ≥ 2 ทางเข้า (ได้ {n_ent}, entries {br.retake['entries']})")
    if entered_early:
        errors.append(f"clutchbots: บอทเข้าไซต์ก่อนสัญญาณเข้าพร้อมกัน {sorted(set(entered_early))}")
    if went is None or defused_t is None or defused_t > 44.0:
        errors.append(f"clutchbots: รีเทคต้องเข้าพร้อมกันแล้วกู้เสร็จ (go {went}, defused {defused_t})")
    info.append(f"retake entries {n_ent} go {went if went is None else round(went, 1)} s "
                f"defused {defused_t if defused_t is None else round(defused_t, 1)} s")
    # ทางเข้า bake (§10.4 cmap.entries): ใช้จุดรวมพลของ bake — วางแผนเมื่อสนามระยะ spike/จุดรวมพลเสร็จ (หั่นช่วงในเฟรม
    # ไม่ run() รวดเดียว) ภายใน PLAN_WAIT
    ty2 = testyard()
    ty2.entries = {"A": {"def": [{"e": [-10.5, 14.0], "stage": [-7.0, 17.0]}, {"e": [-8.0, 3.0], "stage": [-7.0, -1.0]}]}}
    br = ClutchBrain(ty2, {"s": "A", "e": e, "n": 4, "left": 80}, "atk", 19, "vandal", random.Random(8), 0.0)
    while not br.prepare(100000):
        pass
    br.on_planted(0.0, (-12.0, 0.0, 9.5))
    t2 = 0.0
    while not br.retake["plan"] and t2 < PLAN_WAIT + 0.5:
        t2 += 1 / 60
        br.update(1 / 60, t2, pv)
    stages = {b.meta["stage"] for b in br.bots if b.meta["stage"] is not None}
    if not br.retake["plan"] or not br.retake["df"].done or not stages or \
            not stages <= {(-7.0, 17.0), (-7.0, -1.0)}:
        errors.append(f"clutchbots: entries ที่ bake ต้องถูกใช้ + วางแผนหลังสนามระยะเสร็จ (plan {br.retake['plan']} "
                      f"@{t2:.2f} วิ, stages {stages})")
    # go ระหว่างยังเดินไปจุดรวมพล: ต้องทิ้งทางไปจุดรวมพลแล้วเดินสู่ spike (เดิมเดินทางเก่าจนถึงจุดรวมพล → "at_spike"
    # ห่าง spike 13–48 ม. ยืนเฉยทั้งรอบ ; Split 629) — ทุกตัวที่ถึง at_spike ต้องอยู่ในวงกู้จริง
    br = ClutchBrain(ty, {"s": "A", "e": e, "n": 4, "left": 80}, "atk", 19, "vandal", random.Random(8), 0.0)
    while not br.prepare(100000):
        pass
    br.on_planted(0.0, (-12.0, 0.0, 9.5))
    tg, walker = 0.0, None
    while tg < 8.0 and walker is None:
        tg += 1 / 60
        br.update(1 / 60, tg, pv)
        walker = next((b for b in br.bots if b.meta["rtp"] == "to_stage" and b.meta["nav"] is not None
                       and b.meta["nav"][0] == "df" and b.meta["nav"][1] is not br.retake["df"]), None)
    far_at, to_spike = [], False
    if walker is not None:
        br.retake["first_staged"] = tg - 99.0                  # เพื่อนรอครบเวลา → สัญญาณเข้าเฟรมนี้
        for _ in range(int(25.0 * 60)):
            tg += 1 / 60
            br.update(1 / 60, tg, pv)
            if br.defused:                                      # กู้เสร็จ = ทุกตัวถูกตั้ง at_spike (ไม่นับ)
                break
            nv = walker.meta["nav"]
            to_spike = to_spike or (nv is not None and nv[0] == "df" and nv[1] is br.retake["df"])
            for b in br.bots:
                if b.alive and b.meta["rtp"] == "at_spike" and math.hypot(b.x + 12.0, b.z - 9.5) > DEFUSE_R + 0.5:
                    far_at.append((b.meta["idx"], round(math.hypot(b.x + 12.0, b.z - 9.5), 1)))
    if walker is None or far_at or not to_spike or not br.defused:
        errors.append(f"clutchbots: สัญญาณเข้าระหว่างเดินไปจุดรวมพลต้องเปลี่ยนไปเดินสู่ spike (ตัวเดิน {walker is not None}, "
                      f"เดินสู่ spike {to_spike}, at_spike ไกล {sorted(set(far_at))[:2]}, กู้ {br.defused})")
    # เลือกจุดรวมพลด้วยระยะเดินจริง: S1 ห่างตรง 7 ม. แต่หลังกำแพงยาว (เดินอ้อม ~27 ม.) · S2 ห่างตรง 12 ม. เดินตรง ;
    # ระยะตรง ×1.25 เดิมเลือก S1 — ต้องได้ S2 ; ตัวที่เดินถึง spike ใกล้กว่าทุกจุดรวมพล = เฝ้าฝั่งไซต์ (ไม่ย้อนไปรวมพล)
    cm_s = _open_map(25.0, [(-6.0, -24.0, -5.0, 10.0)])
    s1, s2 = (-3.0, 0.0), (-12.0, 12.0)
    cm_s.entries = {"A": {"def": [{"e": [-1.0, 12.0], "stage": list(s1)}, {"e": [-6.0, 16.0], "stage": list(s2)}]}}
    brs = ClutchBrain(cm_s, {"t": "atk", "s": "A", "n": 2, "p": [0.0, -20.0, 0.0],
                             "e": [[-10.0, 0.0, 0.0], [14.0, 14.0, 0.0]], "left": 60}, "atk", 16, "vandal",
                      random.Random(2), 0.0)
    while not brs.prepare(100000):
        pass
    brs.on_planted(0.0, (0.0, 0.0, 20.0))
    ts = 0.0
    while not brs.retake["plan"] and ts < PLAN_WAIT + 0.5:
        ts += 1 / 60
        brs.update(1 / 60, ts, pv)
    got = [(b.meta["rtp"], b.meta["stage"]) for b in brs.bots]
    if got != [("to_stage", s2), ("staged", None)]:
        errors.append(f"clutchbots: จุดรวมพลต้องเลือกด้วยระยะเดิน (ได้ {got}, ต้อง S2 {s2} + ตัวฝั่งไซต์เฝ้าที่เดิม)")
    # ติดขอบ: 1.5 วิไม่คืบ → ถอยออก 0.8 ม. (ห่าง waypoint) 0.7 วิ ; หลังถอย เฟรม "รอ waypoint" ต้องไม่รีเซ็ตนาฬิกาติด
    # (เดิมทิ้ง waypoint → เฟรมถัดไปไม่เดิน → นาฬิการีเซ็ต → waypoint เดิม วนติด 40+ วิ) → STUCK_GIVEUP ไม่คืบ = ล้มเลิก
    bru = _brain(cm0, [(0.0, 0.0, 0.0)], seed=5)
    bu = bru.bots[0]
    mu = bu.meta
    bru._field((10.0, 0.0)).run()
    bru._nav_df(bu, (10.0, 0.0), 0.6)
    mu["wp"], mu["moving"] = (1.0, 0.0), True
    r1, g1 = bru._follow(bu, 1.6), mu["go"]
    r2 = bru._follow(bu, 2.4)
    mu["moving"] = False
    r3, p3 = bru._follow(bu, 2.5), mu["prog"][0]
    r4 = bru._follow(bu, 4.1)
    if not (r1 == "moving" and g1 is not None and g1[0] < -0.5 and r2 == "wait" and r3 == "wait" and p3 == 0.0
            and r4 == "fail"):
        errors.append(f"clutchbots: ติดขอบต้องถอยออกแล้วล้มเลิกใน 4 วิ ({r1} {g1} → {r2} → {r3} prog {p3} → {r4})")

    # ── 10b) โผล่แวบ: บอทจำจุดหลัง reaction (ไม่ใช่ทันที) ; เพื่อนได้ callout หลัง 0.6–1.2 วิ ──
    br = _brain(cm0, [(BX, BZ, 0.0), (BX, BZ - 12.0, math.pi)], tier=12, seed=51)
    b0, b1 = br.bots
    for b in br.bots:
        b.meta["facings"] = [b.meta["yaw"]]
        b.meta["fpitch"] = [0.0]
    pv = at(0, 15)
    t, _e = _run(br, pv, 0.0, 0.15)                      # โผล่ให้เห็น 0.15 วิ แล้วหายไป
    t_seen = b0.meta["notice_t"]
    fire_at = t_seen + b0.meta["rt_last"] if t_seen is not None else None
    early = b0.meta["know"]
    pv.alive = False
    call_t = None
    for _ in range(120):
        t += 1 / 60
        br.update(1 / 60, t, pv)
        if call_t is None and b1.meta["know"] is not None:
            call_t = t
    kn = b0.meta["know"]
    if t_seen is None or early is not None or kn is None or kn[3] != "seen" or abs(kn[2] - fire_at) > 0.05:
        errors.append(f"clutchbots: โผล่แวบต้องจำจุดหลัง reaction ({t_seen}, ก่อน {early}, หลัง {kn}, rt {fire_at})")
    if call_t is None or not (CALLOUT_DELAY[0] - 0.02 <= call_t - t_seen <= CALLOUT_DELAY[1] + 0.02):
        errors.append(f"clutchbots: callout ต้องถึงเพื่อนใน {CALLOUT_DELAY} วิ (ได้ {call_t} − {t_seen})")

    # ── 10c) กำหนดแน่นอน: seed + อินพุตเดียวกัน = ทุกบิตเหมือนเดิม แม้ random ระดับโมดูลถูกตั้ง/กินต่างกัน (โหมดเห็นบางรอบ
    #        แยกทางแล้วผู้เล่นตายคนละเฟรม) ; บอทต้องไม่แตะเลขสุ่ม global ของเกมเลย — ผู้เล่นวิ่งเข้าไซต์ ยิง ฆ่า วาง ตาย แล้วต่อ ──
    sc5 = [s for s in ty.scen if s["t"] == "atk" and s["n"] == 5][0]
    site_c = tuple(ty.sites["A"]["c"])
    dfp = ty.dist_field(site_c).run()

    def det_run(gseed, noise):
        random.seed(gseed)
        g0 = random.getstate()
        br = ClutchBrain(ty, sc5, "atk", 16, "vandal", random.Random(99), 0.0)
        while not br.prepare(5000):
            if noise:
                random.random()
        pv = _pv(float(sc5["p"][0]), float(sc5["p"][1]), feet=ty.floor_y(sc5["p"][0], sc5["p"][1]) or 0.0)
        hp, sh = guns.PLAYER_HP, guns.PLAYER_SHIELD
        out, t, dt, died, shots, planted, p_t0 = [], 0.0, 1 / 60, None, 0, False, 0.0
        for f in range(900):
            t += dt
            for _ in range(f % 3 if noise else 0):
                random.random()                              # เกม/ปืนผู้เล่นกินเลขสุ่ม global เป็นจังหวะอื่น
            if pv.alive and not pv.planting and not planted:
                wp = ty.next_waypoint(dfp, pv.x, pv.z)
                if wp is not None and math.hypot(wp[0] - pv.x, wp[1] - pv.z) > 0.2:
                    L = math.hypot(wp[0] - pv.x, wp[1] - pv.z)
                    pv.vx, pv.vz = 5.4 * (wp[0] - pv.x) / L, 5.4 * (wp[1] - pv.z) / L
                    pv.x, pv.z = pv.x + pv.vx * dt, pv.z + pv.vz * dt
                    pv.feet = ty.floor_y(pv.x, pv.z) or pv.feet
                elif f > 60:
                    pv.vx = pv.vz = 0.0
                    pv.planting = True
                    br.on_plant_start(t, (pv.x, pv.feet, pv.z))
                    p_t0 = t
            elif pv.alive and pv.planting and t - p_t0 >= PLANT_T:
                pv.planting, planted = False, True
                br.on_planted(t, (pv.x, pv.feet, pv.z))
            if f % 45 == 20 and pv.alive:
                br.on_player_shot(t, (pv.x, pv.feet, pv.z))
            if f == 150 and br.bots[0].alive:                # ผู้เล่นฆ่าบอทตัวแรก (ลำดับเดียวกับโหมด: take → alive False → callback)
                b0 = br.bots[0]
                b0.take(80.0, "body")
                br.on_bot_damaged(b0, t, 80.0, "body", pv.eye())
                b0.take(200.0, "head")
                br.on_bot_killed(b0, t, pv.eye())
            if f == 700 and pv.alive:
                pv.alive = False
                died = f
            ev = br.update(dt, t, pv)
            for e in ev:
                if e["k"] == "shot":
                    shots += 1
                    if e["zone"] and pv.alive:
                        hp, sh = guns.apply_damage(hp, sh, e["dmg"])
                        if hp <= 0:
                            pv.alive, pv.planting, died = False, False, f
                            if planted:
                                br.can_bots_defuse(t, (pv.x, pv.z), 40.0)
            out.append(repr(([(b.x, b.z, b.y0, b.meta["yaw"], b.meta["pitch"], b.alive, b.meta["state_s"], b.meta["mag"],
                               b.meta["sees"]) for b in br.bots],
                             [(e["k"], e["bot"].meta["idx"], e.get("zone"), e.get("dmg"), e.get("to")) for e in ev])))
        clean = random.getstate() == g0
        return out, died, shots, clean
    ra, died, shots, clean = det_run(1, False)
    rb, _d, _s, _c = det_run(987, True)
    if ra != rb:
        k = next((i for i, (x, y) in enumerate(zip(ra, rb)) if x != y), len(ra))
        errors.append(f"clutchbots: seed เดียวกันแต่ผลต่าง (เฟรม {k}) เมื่อ random ระดับโมดูลต่างกัน — บอทต้องไม่พึ่งมัน")
    if not clean:
        errors.append("clutchbots: บอทกินเลขสุ่ม global ของเกม (Stability/cone_offset ต้องผ่าน _own_random)")
    if not shots or died is None:
        errors.append(f"clutchbots: เทสกำหนดแน่นอนต้องมีการยิง ({shots}) และผู้เล่นตาย ({died})")
    info.append(f"determinism {len(ra)} frames, {shots} bot shots, player died f{died}, same={ra == rb}")

    # ── 10d) คนกู้หลบหลังมุม (≤ 2.4 ม. จาก spike, ตาเห็น spike): บอทที่ commit ต้องเคลียร์ "บริเวณคนกู้" ไม่ใช่แค่เห็น spike —
    #        A เห็น spike จากจุดเฝ้าอยู่แล้ว · B ต้องโผล่ (3 seed) · C อยู่อีกฝั่งมุม 3.3 ม. (เดิม "ถึง" รัศมี 4 ม. ทันที) ──
    def corner(cmc, spk, pl, bot, seed):
        sc = {"t": "def", "s": "A", "n": 1, "p": [0.0, -20.0, 0.0], "k": list(spk), "e": [list(bot)], "left": 30.0}
        brc = ClutchBrain(cmc, sc, "def", 22, "vandal", random.Random(seed), 0.0)
        while not brc.prepare(100000):
            pass
        pvc = _pv(pl[0], pl[1], defusing=True)
        brc.on_defuse_start(0.0, pvc.eye(), False)       # โหมดส่งตา (clutch_eye) — y ต้องไม่มีผล
        tt, n_shot = 0.0, 0
        while tt < DEFUSE_T - 0.05 and not n_shot:
            tt += 1 / 60
            n_shot += sum(1 for e_ in brc.update(1 / 60, tt, pvc) if e_["k"] == "shot")
        return n_shot, round(tt, 2), brc.bots[0].meta["state_s"]
    cm_a = _open_map(25.0, [(-10.0, 0.0, 0.0, 10.0)])
    cm_b = _open_map(25.0, [(-4.0, 0.0, 0.0, 6.0)])
    cm_c = _open_map(25.0, [(0.0, 0.0, 10.0, 10.0)])
    cases = [("A", cm_a, (0.8, -0.6), (1.0, 1.5), (-8.0, -6.0, 0.9), 5)]
    cases += [("B%d" % s, cm_b, (0.8, -0.6), (1.0, 1.5), (-5.0, 3.0, 1.57), s) for s in (1, 2, 3)]
    cases += [("C", cm_c, (-0.8, 1.2), (-1.5, 2.5), (2.0, -0.6, 0.0), 1)]
    cres = []
    for name, cmc, spk, pl, bot, seed in cases:
        ok_geo = cmc.floor_y(*pl) is not None and not cmc.blocked((pl[0], EYE_Y, pl[1]), (spk[0], 0.15, spk[1]))
        n_shot, tt, st = corner(cmc, spk, pl, bot, seed)
        cres.append(f"{name} {tt}s")
        if not ok_geo or not n_shot:
            errors.append(f"clutchbots: คนกู้หลังมุม {name} — บอท commit แล้วต้องหาเจอและยิงก่อนกู้เสร็จ (ยิง {n_shot}, "
                          f"สถานะ {st}, geo {ok_geo})")
    info.append("corner defuse first shot " + " ".join(cres))
    # จุดยืนกู้: ทุกจุดตาเห็น spike, อยู่ในวงกู้, ไม่อยู่ในของแข็ง
    brs = ClutchBrain(cm_a, {"s": "A", "n": 1, "k": [0.8, -0.6], "e": [[-8.0, -6.0, 0.9]], "left": 30}, "def", 12,
                      "vandal", random.Random(1), 0.0)
    sp_ = brs._defuse_spots()
    if not sp_ or any(math.hypot(p[0] - 0.8, p[2] + 0.6) > DEFUSE_R + 1e-6 or not cm_a.disc_clear(p[0], p[2], PLAYER_R)
                      for p in sp_):
        errors.append(f"clutchbots: _defuse_spots ผิด ({len(sp_)} จุด)")

    # ── 10e) ได้ยินเสียงกู้ช้า (เดินเข้าระยะระหว่างกู้) แต่กู้ครั้งนั้นยังทัน → ต้อง commit (เดิมเทียบ explode − เวลาที่ได้ยิน) ──
    cm_l = _open_map(30.0, [(-8.0, -2.0, -6.0, 14.0)])
    cm_l.holds = {"A": {"atk_post": [[-12.0, 8.0, math.atan2(12.0, -8.0), 1]]}}
    brl = ClutchBrain(cm_l, {"t": "def", "s": "A", "n": 1, "p": [0.0, -20.0, 0.0], "k": [0.0, 0.0],
                             "e": [[-26.0, 26.0, 2.3]], "left": 7.5}, "def", 16, "vandal", random.Random(3), 0.0)
    while not brl.prepare(100000):
        pass
    pvl = _pv(0.0, 1.5, defusing=True)
    brl.on_defuse_start(0.0, (0.0, 0.0, 1.5), False)
    tl, heard_t = 0.0, None
    while tl < 6.9:
        tl += 1 / 60
        brl.update(1 / 60, tl, pvl)
        if heard_t is None and brl.bots[0].meta["dsnd"]:
            heard_t = tl
    if heard_t is None or heard_t < 1.0 or brl.bots[0].meta["committed"] is None:
        errors.append(f"clutchbots: ได้ยินเสียงกู้ที่ {heard_t} วิ (กู้เสร็จ 7.0 < ระเบิด 7.5) ต้อง commit — "
                      f"{brl.bots[0].meta['committed']}")
    # ทอยไม่โผล่ (ไกล 18.5 ม. หลังกำแพง — ยังได้ยินใน 19.2 ม. : p 0.58) แต่เสียงกู้ดังต่อ = ทอยใหม่ทุก 2 วิ → เกือบทุกตัว
    # ต้องออกไปดูภายในการกู้ 7 วิ (ทอยครั้งเดียวแบบเดิม ≈ 58%)
    went = 0
    for s in range(8):
        brk = _brain(cm, [(-10.5, 5.0, 0.0)], side="def", tier=22, seed=60 + s, k=(8.0, 5.0), left=40.0)
        pvk = _pv(8.0, 6.5, defusing=True)
        brk.on_defuse_start(0.0, pvk.eye(), False)
        tk = 0.0
        while tk < DEFUSE_T - 0.1:
            tk += 1 / 60
            brk.update(1 / 60, tk, pvk)
            if brk.bots[0].meta["state"] == "swing":
                went += 1
                break
    if went < 7:
        errors.append(f"clutchbots: เสียงกู้ดังต่อ บอทที่ทอยไม่โผล่ต้องทอยใหม่ — ออกไปดู {went}/8")
    info.append(f"far bot re-roll went {went}/8")

    # ── 10f) ความสูงต้นเสียง: โหมดส่งตา / sim ส่งเท้า / (x, z) ต้องได้ที่เดียวกัน = พื้น + ค่าเสียง ; กล่อง 1.1 ม. หน้าผู้เล่น
    #        บังเสียงเริ่มวาง/กู้ที่ 25 ม. (ถูกบัง = ×0.6 → 19.2 ม.) ไม่ว่าส่ง y แบบไหน ──
    rows = ["".join("#" if i in (0, 199) or j in (0, 39) else ("b" if i in (141, 142) else ".") for i in range(200))
            for j in range(40)]
    cm_h = ClutchMap.from_ascii(rows, x0=-25.0, z0=-5.0, sites={"A": {"c": [12.5, 0.0], "plants": [[12.5, 0.0, 1]]}},
                                spawns={"atk": [-20.0, 0.0], "def": [20.0, 0.0]})
    brh = _brain(cm_h, [(-12.5, 0.0, math.pi)], seed=3)
    p3 = {brh._pos3(p, 1.0) for p in ((12.5, EYE_Y, 0.0), (12.5, 0.0, 0.0), (12.5, 0.0), (12.5, 7.0, 0.0))}
    if p3 != {(12.5, 1.0, 0.0)}:
        errors.append(f"clutchbots: _pos3 ต้องไม่ใช้ y ที่ส่งมา — {sorted(p3)}")
    for yy in (0.0, EYE_Y):
        brh = _brain(cm_h, [(-12.5, 0.0, math.pi)], side="atk", seed=3)
        brh.on_plant_start(0.0, (12.5, yy, 0.0))
        _run(brh, _pv(12.5, 0.0, planting=True), 0.0, 0.5)
        brd = _brain(cm_h, [(-12.5, 0.0, math.pi)], side="def", seed=3, k=(13.5, 0.0), left=40.0)
        brd.on_defuse_start(0.0, (12.5, yy, 0.0), False)
        _run(brd, _pv(12.5, 0.0, defusing=True), 0.0, 0.5)
        if brh.bots[0].meta["psnd"] or brd.bots[0].meta["dsnd"]:
            errors.append(f"clutchbots: เสียงวาง/กู้หลังกล่อง 1.1 ม. ที่ 25 ม. ต้องไม่ได้ยิน (y={yy}: "
                          f"{brh.bots[0].meta['psnd']}, {brd.bots[0].meta['dsnd']})")

    # ── 10g) โดนยิงข้างหลังระหว่างเดินทาง (rotate วิ่ง 22 ม. / retake to_stage 11 ม.): ต้องหยุด หันกลับ ยิงสวน ──
    cm_r = _open_map(40.0, [])
    back = []
    for kind, gap in (("rotate", 22.0), ("retake", 11.0)):
        fired = 0
        for s in range(3):
            brr = ClutchBrain(cm_r, {"t": "atk", "s": "A", "n": 1, "p": [0.0, -30.0, 0.0], "e": [[0.0, -12.0, 0.0]],
                                     "left": 60.0}, "atk", 16, "vandal", random.Random(s), 0.0)
            while not brr.prepare(100000):
                pass
            br_b = brr.bots[0]
            pvr = _pv(0.0, -12.0 - gap)
            if kind == "retake":
                brr.on_planted(0.0, (0.0, 0.0, 20.0))
            tr_, _e = _run(brr, pvr, 0.0, 1.0)
            st0 = br_b.meta["state_s"]
            first = None
            for f in range(int(3.0 * 60)):
                tr_ += 1 / 60
                if f % 24 == 0 and br_b.hp > 40:
                    br_b.take(12.0, "leg")
                    brr.on_bot_damaged(br_b, tr_, 12.0, "leg", pvr.eye())
                for e_ in brr.update(1 / 60, tr_, pvr):
                    if e_["k"] == "shot" and first is None:
                        first = tr_
                pvr.z = br_b.z - gap                        # ผู้ยิงตามหลังระยะคงที่
            ok_st = st0.startswith("rotate") if kind == "rotate" else st0 == "retake:to_stage"
            fired += first is not None and ok_st
        back.append(f"{kind} {fired}/3")
        if fired < 3:
            errors.append(f"clutchbots: โดนยิงข้างหลังระหว่าง {kind} ({gap:.0f} ม.) ต้องหันกลับยิงสวน — {fired}/3")
    info.append("shot in back fired " + ", ".join(back))

    _selftest_real(errors, info, cm0)

    # ── 11) งบเวลา: 5 บอทบน testyard ผู้เล่นวิ่งผ่าน (ค่าเฉลี่ยต่อเฟรม — เป้า ≤ 1.5 ms ; เช็คหลวม 3 ms กันเครื่อง CI ช้า) ──
    sc = [s for s in ty.scen if s["t"] == "atk" and s["n"] == 5][0]
    br = ClutchBrain(ty, sc, "atk", 16, "vandal", random.Random(2), 0.0)
    while not br.prepare(100000):
        pass
    pv = _pv(0.0, -16.5, vz=5.4)
    t = 0.0
    tm = []
    for f in range(600):
        t += 1 / 144
        pv.z = -16.5 + min(25.0, 5.4 * t)
        pv.x = 0.0 + 5.0 * math.sin(t)
        q = time.perf_counter()
        br.update(1 / 144, t, pv)
        tm.append((time.perf_counter() - q) * 1000)
        for b in br.bots:
            if b.alive and not ty.disc_clear(b.x, b.z, BOT_R - 0.02, b.y0):
                errors.append(f"clutchbots: บอท {b.meta['idx']} จมของแข็งที่ ({b.x:.2f}, {b.z:.2f})")
                break
            if b.meta["sees"] and not ty.any_visible(b.eye(), body_points(b.eye(), pv.x, pv.z, pv.feet, pv.crouch)):
                errors.append("clutchbots: บอท 'เห็น' ทั้งที่ any_visible บอกว่าบัง")
    tm.sort()
    mean = sum(tm) / len(tm)
    if mean > 3.0:
        errors.append(f"clutchbots: update 5 บอท เฉลี่ย {mean:.2f} ms/เฟรม (เป้า ≤ 1.5)")
    info.append(f"update 5 bots mean {mean:.2f} ms p99 {tm[int(0.99 * len(tm))]:.2f} ms")
    _ST_INFO["line"] = " | ".join(info) + " |"

def _selftest_real(errors, info, cm0):
    """12) realism pass v2 (§13): สัญญาข้อมูลให้ภาพ · เสียงลงพื้น · หันไม่เกิน BOT_TURN · เคลียร์มุมระหว่างเดิน · เทรด ·
    ส่าย ADAD แต่ไม่ยิงขณะวิ่ง · ย้าย off-angle หลังยิงกัน"""
    # ── 12a) PlayerView ฟิลด์ใหม่ + PlayerView เก่าที่ไม่มีฟิลด์ (getattr) ไม่พัง ; meta vel/walk/reload ──
    pv0 = PlayerView()
    if (pv0.air, pv0.land_t, pv0.land_loud, pv0.on_box) != (False, -9.0, False, False):
        errors.append("clutchbots: PlayerView §13.2 ค่าเริ่มต้นผิด")
    br = _brain(cm0, [(0.0, 0.0, 0.0)], seed=3)
    b = br.bots[0]
    b.meta.update(state="rotate", dest=None, nav=("path", [(0.0, 20.0)], (0.0, 20.0), 0.5), know=None, path_i=0,
                  prog=(0.0, 0.0, 0.0), preaim=None, alert_t=-99.0)
    old = PlayerView(x=20.0, z=-20.0, alive=False)
    for k in ("air", "land_t", "land_loud", "on_box"):
        delattr(old, k)
    t, _e = _run(br, old, 0.0, 1.0)
    m = b.meta
    if (m["vel"] != (b.vel[0], b.vel[1]) or math.hypot(*m["vel"]) < 4.0 or m["walk"] or m["reload"]
            or not isinstance(m["pitch"], float)):
        errors.append(f"clutchbots: meta vel/walk/reload (§13.2) ผิด — {m['vel']} walk {m['walk']} reload {m['reload']}")
    br._reload(b, t)
    t, _e = _run(br, old, t, 0.1)
    if not m["reload"]:
        errors.append("clutchbots: meta['reload'] ต้องเป็น True ระหว่างรีโหลด")

    # ── 12b) เสียงลงพื้น: ดัง (land_loud) 20 ม. ข้างหลัง = ได้ยิน ; Shift ลง (เงียบ) = ไม่ ──
    for loud in (True, False):
        br = _brain(cm0, [(0.0, 0.0, math.pi)], seed=5)
        b = br.bots[0]
        b.meta["facings"] = [math.pi]
        pvl = PlayerView(x=0.0, z=20.0)
        t, _e = _run(br, pvl, 0.0, 0.3)
        pvl.land_t, pvl.land_loud = t, loud
        t, ev = _run(br, pvl, t, 0.3)
        got = b.meta["know"] is not None and any(e["k"] == "heard" for e in ev)
        if got != loud:
            errors.append(f"clutchbots: เสียงลงพื้น land_loud={loud} บอทได้ยิน {got}")

    # ── 12c) หันไม่เกิน BOT_TURN ระหว่างยิงกัน (ผู้เล่นส่ายด้านข้าง 8 ม.) — เดิม _shoot วาร์ปทิศไปจุดเล็งทุกนัด ──
    br = _brain(cm0, [(0.0, 0.0, 0.0)], tier=22, seed=7)
    b = br.bots[0]
    b.meta["facings"] = [0.0]
    pvt = PlayerView(x=-3.0, z=8.0, vx=4.0)
    t, worst, shots = 0.0, 0.0, 0
    for f in range(int(3.0 * 144)):
        t += 1 / 144
        pvt.x = -3.0 + 6.0 * abs(((t * 0.8) % 2.0) - 1.0)
        pvt.vx = 4.8 if ((t * 0.8) % 2.0) < 1.0 else -4.8
        y0, p0 = b.meta["yaw"], b.meta["pitch"]
        shots += sum(1 for e in br.update(1 / 144, t, pvt) if e["k"] == "shot")
        worst = max(worst, abs(_wrap(b.meta["yaw"] - y0)), abs(b.meta["pitch"] - p0))
    if worst > math.radians(BOT_TURN) / 144 * 1.001 + 1e-9 or not shots:
        errors.append(f"clutchbots: หันเร็วเกิน BOT_TURN {math.degrees(worst) * 144:.0f}°/วิ (ยิง {shots} นัด)")

    # ── 12d) เคลียร์มุม: เดินตามทางเดินผ่านประตูด้านขวา → ก่อนถึงประตูต้องหันเล็งขอบประตู (≥ 20° ขวา) ระดับหัว ; ผ่านแล้ว
    #         กลับมามองทางเดิน ──
    cmd = _open_map(25.0, [(-3.0, -24.0, -1.0, 24.0), (1.0, -24.0, 3.0, 0.0), (1.0, 3.0, 3.0, 24.0)])
    br = _brain(cmd, [(0.0, -14.0, 0.0)], seed=9)
    b = br.bots[0]
    b.meta.update(state="rotate", dest=None, nav=("path", [(0.0, 18.0)], (0.0, 18.0), 0.5), know=None, path_i=0,
                  prog=(0.0, 0.0, -14.0), preaim=None, alert_t=-99.0)
    pvd = PlayerView(x=20.0, z=-20.0, alive=False)
    t, pre, after, pit = 0.0, 0.0, [], []
    while t < 8.0 and b.z < 16.0:
        t += 1 / 60
        br.update(1 / 60, t, pvd)
        yd = math.degrees(_wrap(b.meta["yaw"]))
        if b.z < -0.5:
            pre = max(pre, yd)
            if yd > 20.0:
                pit.append(math.degrees(b.meta["pitch"]))
        elif b.z > 8.0:
            after.append(abs(yd))
    if pre < 20.0 or not after or min(after) > 25.0 or (pit and max(abs(p) for p in pit) > 10.0):
        errors.append(f"clutchbots: เดินผ่านประตูต้องเล็งขอบประตูก่อน (ขวาสุด {pre:.0f}°, pitch {pit[:1]}) แล้วกลับมามองทาง "
                      f"({min(after) if after else None})")
    info.append(f"corner pre-aim {pre:.0f}° right before the door")

    # ── 12e) เทรด: เพื่อนตายห่าง 4 ม. → Radiant ออกเทรด (swing:trade) บ่อย, Iron น้อยกว่า ; ไม่เกิน ~1.6 วิ ──
    res = {}
    for tier in (0, 22):
        n_tr = 0
        for s in range(12):
            br = _brain(cm0, [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0)], tier=tier, seed=200 + s)
            v, o = br.bots
            pvk = PlayerView(x=0.0, z=14.0, alive=False)
            t, _e = _run(br, pvk, 0.0, 0.1)
            v.take(500.0, "head")
            br.on_bot_killed(v, t, (0.0, 1.65, 14.0))
            ok = False
            for _ in range(int(1.8 * 60)):
                t += 1 / 60
                br.update(1 / 60, t, pvk)
                ok = ok or o.meta["state_s"] == "swing:trade"
            n_tr += ok
        res[tier] = n_tr
    if not (res[22] >= 7 and res[0] < res[22]):
        errors.append(f"clutchbots: เทรดเมื่อเพื่อนตายใกล้ ๆ — Radiant {res[22]}/12, Iron {res[0]}/12")
    info.append(f"trade Iron {res[0]}/12 Rad {res[22]}/12")

    # ── 12f) ส่าย ADAD ระหว่างชุด (Radiant) แต่ทุกนัดยิงใน deadzone (ไม่ run-and-gun) ──
    n_str, bad_mv, n_sh = 0, 0, 0
    for s in range(3):
        br = _brain(cm0, [(0.0, 0.0, 0.0)], tier=22, seed=300 + s)
        b = br.bots[0]
        b.meta["facings"] = [0.0]
        b.meta["run_shoot"] = False
        pvs = PlayerView(x=0.0, z=16.0)
        t = 0.0
        for _ in range(int(4.0 * 144)):
            t += 1 / 144
            for e in br.update(1 / 144, t, pvs):
                if e["k"] == "shot":
                    n_sh += 1
                    bad_mv += not guns.is_accurate(b.weapon, b.speed())
            n_str += b.meta["strafe"] is not None
    if not n_str or bad_mv or n_sh < 10:
        errors.append(f"clutchbots: ADAD ส่าย {n_str} เฟรม, ยิงขณะเร็วเกิน deadzone {bad_mv}/{n_sh} นัด")
    info.append(f"adad frames {n_str}, moving shots {bad_mv}/{n_sh}")

    # ── 12g) ยิงกันแล้วผู้เล่นหลบ → Radiant ย้าย off-angle บางครั้ง ; จุดใหม่ยังเห็นจุดที่ผู้เล่นอยู่ และมุมต่างจากเดิม ──
    cmw = _open_map(25.0, [(3.0, 6.0, 8.0, 14.0)])
    n_sw, bad_sw = 0, 0
    for s in range(10):
        br = _brain(cmw, [(0.0, -6.0, 0.0)], tier=22, seed=400 + s)
        b = br.bots[0]
        b.meta["facings"] = [0.0]
        b.meta["aggr"] = 0.0                          # ไม่ re-peek — ดูเฉพาะการย้ายจุด
        pvw = PlayerView(x=1.5, z=10.0)
        t, _e = _run(br, pvw, 0.0, 0.8)               # เห็นกัน ยิงใส่
        pvw.x = 9.5                                   # หลบหลังกำแพง
        home = (b.x, b.z)
        t, _e = _run(br, pvw, t, 3.0)
        if b.meta["state"] == "repo" or math.hypot(b.x - home[0], b.z - home[1]) > 2.0:
            n_sw += 1
            d = b.meta["dest"] or (b.x, b.z)
            if cmw.blocked((d[0], EYE_Y, d[1]), (1.5, HEAD_Y, 10.0)):
                bad_sw += 1
    if not n_sw or bad_sw:
        errors.append(f"clutchbots: ย้าย off-angle หลังยิงกัน {n_sw}/10 (จุดใหม่มองไม่เห็นบริเวณเดิม {bad_sw})")
    info.append(f"swap after contact {n_sw}/10")

    # ── 12h) spike บนกล่อง 1.1 ม. (ผู้เล่นกระโดดขึ้นไปวาง §13.1): บอทต้องเดินไปพื้นข้างกล่องแล้วกู้ได้ ; can_bots_defuse
    #         ตอบตามระยะเดินจริงถึงจุดนั้น (เดิม |Δy| ≤ 1.0 + nav ไปยอดกล่องไม่ได้ = spike บนกล่องกู้ไม่ได้เลย) ──
    rows = []
    for j in range(60):
        rows.append("".join("#" if i in (0, 59) or j in (0, 59) else ("b" if 28 <= i < 36 and 28 <= j < 36 else ".")
                            for i in range(60)))
    cmb = ClutchMap.from_ascii(rows, x0=-7.5, z0=-7.5, sites={"A": {"c": [0.0, 0.0], "plants": [[0.0, 0.0, 1]]}},
                               spawns={"atk": [-6.0, -6.0], "def": [6.0, 6.0]})
    brb = ClutchBrain(cmb, {"t": "atk", "s": "A", "n": 1, "p": [-6.0, -6.0, 0.0], "e": [[5.5, 5.5, 0.0]], "left": 60},
                      "atk", 16, "vandal", random.Random(4), 0.0)
    while not brb.prepare(100000):
        pass
    top = 1.1
    brb.on_planted(0.0, (0.5, top, -0.5))                  # กล่อง x −0.5..1.5, z −1.5..0.5 (rows[0] = เหนือ)
    gx, gz = brb.spike_goal
    ok_goal = abs(brb.spike_y - top) < 0.06 and math.hypot(gx - 0.5, gz + 0.5) <= DEFUSE_R and cmb.floor_y(gx, gz) is not None
    can = brb.can_bots_defuse(0.0, (0.5, -0.5), 40.0)
    pvb = PlayerView(x=-6.5, z=-6.5, alive=False)
    tb, dfd = 0.0, False
    while tb < 30.0 and not dfd:
        tb += 1 / 60
        dfd = any(e["k"] == "defused" for e in brb.update(1 / 60, tb, pvb))
    if not (ok_goal and can and dfd):
        errors.append(f"clutchbots: spike บนกล่อง — จุดเป้า {ok_goal} ({gx:.2f}, {gz:.2f}) y {brb.spike_y:.2f}, "
                      f"can_bots_defuse {can}, กู้สำเร็จ {dfd} @{tb:.1f} วิ")
    info.append(f"box-top spike defused {dfd} @{tb:.1f}s")
