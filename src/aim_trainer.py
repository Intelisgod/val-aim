# -*- coding: utf-8 -*-
"""VAL//AIM — entry point (โครงหลักแตกเป็น package `aim/`)
รัน:  py src\\aim_trainer.py                   | เทสต์ในตัว: py src\\aim_trainer.py --selftest
      (เครื่องนี้ต้องใช้ `py` — `python` เป็น 3.10 ที่ไม่มี pygame-ce/moderngl)
เปิดเข้าโหมดเลย (deep-link จาก dashboard):
     py src\\aim_trainer.py --mode flick       | --mode reaction --variant flick|static|peek
     --mode gun --variant vandal --drill peek  | ดริล: duel hold quick repo angle peek tap adad
     --mode spray --variant vandal             | โหมด: flick precision tracking reaction
     --warmup = คิววอร์มต่อเนื่องตามแผน          strafe sniper spray dodge placement switch
     --duration 30 --size medium = ล็อก config อ้างอิงจาก dashboard (ใช้คู่ --mode;
     ค่าเพี้ยน/ไม่ส่ง = ค่าเมนูเดิม — fail-open แบบเดียวกับ aim/plan.py)
     --plan-item b1 --rid r-yyyymmdd-xxxx = ปุ่มคันโยก/แผนที่เป็นดริลเดียวกับรายการในชุดซ้อม: รอบนี้นับเข้ารายการนั้น
     (plan.deeplink_src ตรวจกับไฟล์แผนก่อน ไม่ตรง = รอบอิสระ)
ตะเข็บเสียบโมดูลเสริม: ดู aim/registry.py
"""
import sys

MODES = ("flick", "precision", "tracking", "reaction", "strafe",
         "sniper", "spray", "dodge", "placement", "switch", "gun")

def _arg(name, argv=None):
    """คืนค่าที่ตามหลัง --name ใน argv (ค่าตั้ง = sys.argv) หรือ None"""
    argv = sys.argv if argv is None else argv
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1].lower()
    return None


def apply_deeplink(g, argv=None):
    """ตั้งโหมด/variant/ดริล/config ตาม --mode … (deep-link จาก dashboard) แล้วเริ่มนับถอยหลัง — คืน True ถ้า --mode
    เป็นโหมดที่รู้จัก ; ค่าเพี้ยน = คงค่าเมนูเดิม (fail-open) — id ชุดเดียวกับ aim/plan.py และ server aimlink"""
    mode = _arg("--mode", argv)
    if mode not in MODES:
        return False
    g.mode = mode
    variant = _arg("--variant", argv)
    from aim.config import REACTION_VARIANTS
    if mode == "reaction" and variant in REACTION_VARIANTS:
        g.reaction_variant = variant
    if mode == "spray" and variant in ("vandal", "phantom"):
        g.spray_weapon = variant
    if mode == "gun":
        from aim.guns import WEAPON_ORDER, DRILL_ORDER
        if variant in WEAPON_ORDER:
            g.gun_weapon = variant
        drill = _arg("--drill", argv)
        if drill in DRILL_ORDER:
            g.gun_drill = drill     # คู่ปืน/ดริลที่เล่นไม่ได้ (Op+TAP) → gun_fix_drill ตอนเริ่มรอบย้ายไป DUEL
    # config อ้างอิงจาก dashboard — ไม่ตั้งตามนี้ session จะตกนอก config ที่
    # dashboard วัดฟอร์ม (ไม่ถูกนับ) เหตุผลเดียวกับ cfg lock ใน aim/plan.py
    from aim.config import DURATIONS, SIZE_TH
    try:
        d = int(_arg("--duration", argv) or 0)
        if d in DURATIONS:
            g.duration = d
    except ValueError:
        pass
    sz = _arg("--size", argv)
    if sz in SIZE_TH:
        g.size_key = sz
    # ปุ่มคันโยก/แผนที่ตรงกับรายการใน routine/แผน (--plan-item/--rid) = รอบนี้นับเข้าชุดซ้อมวันนี้ + วันซ้อมตามแผน
    # plan.deeplink_src ตรวจกับไฟล์แผนจริง (สด + id มีจริง + ดริลเดียวกับที่เปิด) ไม่ตรง = รอบอิสระ (fail-open)
    item = _arg("--plan-item", argv)
    if item:
        try:
            from aim import plan as _plan
            src = _plan.deeplink_src(g.mode, {"reaction": g.reaction_variant, "spray": g.spray_weapon,
                                              "gun": g.gun_weapon}.get(g.mode, ""),
                                     g.gun_drill if g.mode == "gun" else None, item, _arg("--rid", argv))
        except Exception:
            src = None
        if src:
            g.next_src = src
    g.start_countdown()   # ข้ามเมนู เข้าโหมดที่สั่งมาเลย (ESC กลับเมนูได้ตามปกติ)
    return True

_MUTEX_H = None  # ถือ handle ไว้ตลอดอายุโปรเซส — Windows ปล่อยเองเมื่อจบ/แครช

def _single_instance_guard():
    """กันเปิดเทรนเนอร์ซ้อน (เช่น .bat + ปุ่ม dashboard พร้อมกัน) — ตัวที่ปิดทีหลังจะเซฟ
    aim_trainer_data.json ทับทั้งไฟล์ ลบ session ของอีกตัว; server มี guard (AIM_PROC)
    เฉพาะตัวที่มันเปิดเอง ตรงนี้คือ guard ฝั่งเทรนเนอร์ที่ครอบทุกทางเข้า
    ใช้ named mutex ของ Windows; ผิดพลาดอะไรก็ตาม = ไม่บล็อกการเล่น (fail-open)"""
    global _MUTEX_H
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p   # กัน handle โดนตัดเหลือ 32 bit
        h = k32.CreateMutexW(None, False, "VAL_AIM_TRAINER_SINGLE_INSTANCE")
        if h and ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            msg = "VAL//AIM เปิดอยู่แล้ว — สลับไปหน้าต่างเดิมได้เลย (เปิดซ้อนจะเซฟทับกันเอง)"
            print(msg, file=sys.stderr)
            if len(sys.argv) == 1:
                # เปิดเองจาก .bat/ดับเบิลคลิก → เด้งกล่องบอก; ถ้ามาจาก dashboard (--mode/--warmup)
                # ต้อง exit ทันทีให้ launch_aim_trainer เห็นภายใน 0.6 วิ แล้วโชว์ข้อความฝั่งเว็บแทน
                ctypes.windll.user32.MessageBoxW(None, msg, "VAL//AIM", 0x40030)  # WARN|TOPMOST
            sys.exit(1)
        _MUTEX_H = h
    except SystemExit:
        raise
    except Exception:
        pass

if __name__ == "__main__":
    # stderr ตอนถูก dashboard spawn คือไฟล์ last_launch_error.log ที่ server อ่านกลับเป็น utf-8 —
    # ถ้าไม่ reconfigure ข้อความไทย (เช่น mutex "เปิดอยู่แล้ว") จะถูกเขียนเป็น \uXXXX escapes
    # ตาม encoding ระบบ แล้วโชว์เป็น gibberish บนเว็บ; ต้องทำก่อน print/import ใดๆ ทั้งหมด
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--selftest" in sys.argv:
        from aim.selftest import selftest
        selftest()
    else:
        _single_instance_guard()
        from aim.game import Game
        g = Game()
        if "--warmup" in sys.argv:
            from aim import plan
            plan.start_warmup(g)  # คิววอร์มตามแผนจาก dashboard (ไม่มีแผน = ชุด default)
        else:
            apply_deeplink(g)
        g.run()
