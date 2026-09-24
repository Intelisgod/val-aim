# -*- coding: utf-8 -*-
"""VAL//AIM — Integration Contract (ตะเข็บกลาง)

โมดูล 1–5 append ตัวเองเข้าลิสต์เหล่านี้ผ่าน register(game) ในไฟล์ของตัวเอง
โดย game.py จะ iterate ลิสต์เหล่านี้ตอนวาด/อัปเดต — โมดูลอื่นห้ามแก้ game.py

สัญญา (signature ที่ใช้จริง):
  MENU_EXTRAS     : list[dict]  — แต่ละตัว {"label": str, "on_click": fn(game)}
                    → draw_menu วาดเป็นปุ่มรองแถวบนขวา (ก่อน INSIGHT/SETTINGS) กว้างตามป้าย ; "disabled": True = ปุ่มเทา
  SETTINGS_PANELS : list[callable] — แต่ละตัวเป็น fn(game, x, y, w) -> ความสูงที่ใช้ (px)
                    → draw_settings เรียกในคอลัมน์ขวาที่กันไว้ แล้วเลื่อน y ตามค่าที่คืน
  RESULTS_ACTIONS : list[dict]  — แต่ละตัว {"label": str, "on_click": fn(game)}
                    → draw_results วาดต่อท้ายแถวปุ่มเดิม (จัดกึ่งกลางทั้งแถว หดตามจอ) ; ปุ่ม NEXT ของคิวแผนไม่อยู่ที่นี่
  FLOWS           : dict        — name -> factory(game) คืน object ที่มี .update(dt) และ .draw()
                    → ใน run() ถ้า game.flow ถูกเซ็ต จะ delegate update/draw ไปที่ game.flow แทน state ปกติ
                      ออกได้ด้วย ESC (ตั้ง game.flow=None, กลับ state="menu"); flow มี .on_exit() (ไม่บังคับ) ได้

ข้อมูล game ที่โมดูลอื่นอ้างอิงได้ (ห้ามเปลี่ยนชื่อ):
  game.S (alias ของ data["settings"]: dpi, sens, ch, sound, fps, headshots, pillars)
  game.last_entry (mode,variant,score,acc,rt,duration,size,streak,hs,ts,...)
  game.res_acc / res_avg_rt / res_hs / res_pb / res_onbody / score / mode
  game.capture_screen() / game.copy_to_clipboard(surface)
  game.text(s,size,color,pos,center=,bold=,right=,surf=) / game.button(rect,label,fn,...) / game.draw_rank_emblem(...)
  game.state ∈ {menu,settings,ranks,insight,countdown,play,pause,results} / game.start_countdown()
"""

MENU_EXTRAS = []      # [{"label": str, "on_click": fn(game)}]
SETTINGS_PANELS = []  # [fn(game, x, y, w) -> int(height_px)]
RESULTS_ACTIONS = []  # [{"label": str, "on_click": fn(game)}]
FLOWS = {}            # {name: factory(game) -> obj(.update(dt), .draw())}
