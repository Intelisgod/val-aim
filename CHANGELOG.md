# Changelog

## Unreleased
- (เขียนสิ่งที่แก้ระหว่างพัฒนาไว้ตรงนี้ — publish.py จะย้ายไปใต้เลขเวอร์ชันให้เอง)

## 1.1.2 — 2026-09-27
- เมาส์: กล้องหันได้ไม่จำกัดเสมอ — เดิมถ้าเอาติ๊ก "Raw input" ในหน้า Settings ออก เคอร์เซอร์จะชนขอบหน้าต่างแล้วกล้องหยุดหัน ติ๊กนี้ถอดออกแล้ว (เปิด raw ตลอด เหมือน Valorant ที่ไม่ใช้ accel ของ Windows)

## 1.1.1 — 2026-09-27
- VSync/GPU ที่ตั้งไว้ในหน้า Settings มีผลจริงตอนเปิดเกมใหม่แล้ว (เดิมถูกข้ามแล้วใช้ค่าเริ่มต้นเสมอ)
- DODGE: วง molly วาดบน GPU — ไม่มีเส้นส้มแปลก ๆ พาดกลางจอตอนยืนใกล้วง และเฟรมลื่นขึ้นนิดหน่อย

## 1.1.0 — 2026-09-24
- สำคัญ: PB/สถิติเก่าของ placement, switch, dodge, strafe, gunfight และ spray รุ่นก่อนไม่นับแล้ว (กติกาเปลี่ยน) — ยังอยู่ในไฟล์ครบ
- GUNFIGHT บอทใหม่: แอบหลังมุมกำแพงแล้วโผล่ 6 ท่า ยิงสวนตามแนวสายตา/ที่กำบัง + peeker's advantage 70 ms, HP รีเซ็ตทุกดวล
- GUNFIGHT มีแรงค์ดวล (DUEL/ANGLE/PEEK): ชนะ = บอทถัดไปเก่งขึ้น แพ้ = อ่อนลง บอกแรงค์เมื่อแม่นพอ (~100 ดวล) ก่อนนั้นขึ้น "กำลังวัด"
- ดริลใหม่: ANGLE HOLD, PEEK & STOP, TAP @ RANGE, STRAFING HEADS + reaction แบบ PEEK (หัวโผล่จากขอบกล่อง ต้องโดนหัว)
- ปืนสั้น Ghost และ Classic ใน GUNFIGHT (Classic คลิกขวา = ยิงชุด 3 เม็ด) ระยะดวลตามระยะคิลจริงของปืนนั้น
- การเคลื่อนที่แบบเกม: ความแม่น deadzone 27.5%, ปล่อยปุ่มหยุดสนิท ~165 ms, Shift เดิน, Ctrl/C หมอบ — วิ่งยิงกระจายจริง
- หัวเป้า PLACEMENT/SWITCH/DODGE อยู่ระดับหัวจริง ; BEAM ของ DODGE กวาดเข้ามาหยุดที่เส้นที่เห็นล่วงหน้า (หลบได้จริง)
- รีคอยล์ Vandal/Phantom ตามแพตช์ 11.08 — สลับซ้าย/ขวากลางแม็กได้จริงตอนกดค้าง
- การ์ด "วันนี้" บนเมนู + ปุ่ม ROUTINE/WARMUP: สลับลำดับดริลแบบสุ่ม, ปุ่ม NEXT ใหญ่ (ENTER), นับวันซ้อม x/4 ต่อสัปดาห์
- ROUTINE: flick/precision/switch ถึงเป้า 2 รอบติด → รอบฝึกถัดไปเป้าเล็กลงเอง (รอบแรกของวันเล่นขนาดตามแผนเสมอ)
- SPRAY: Radiant เอื้อมถึงได้จริง และ Phantom มีบันไดแรงค์ของตัวเอง
- Insight: aim bias และคำแนะนำดริลมีช่วงความมั่นใจ ขึ้น "ยังสรุปไม่ได้" แทนการเดา — เลิกบอก "ยิงหลุดทางบน" ผิดๆ
- หน้าผลบอกเวลาเฟรม/FPS เทียบรีเฟรชจอ + ทิป latency ครั้งเดียว ; เมนู/หน้าผล/หน้าพัก/HUD GUNFIGHT สเกลตามขนาดหน้าต่าง
- GUNFIGHT: แตะ R = รีโหลด, ค้าง R 0.8 วิ = เริ่มใหม่ ; ลำตัวบอทเป็นทรงกระบอก (เฉียดข้างหัวไม่ได้ดาเมจตัวฟรี)
- รอบ benchmark ไม่ปนประวัติ ; ไฟล์หลักที่ถูกล็อกชั่วคราวไม่ทำให้ค่าตั้งย้อนกลับ
- เครื่องมือ dev: `tools/duel_sim.py`, `tools/peek_react_fit.py`, `rank_ceiling_sim.py fit-spray / reach-spray / fit-size`
- อัปเดตใหญ่: สมจริงแบบเกม + GUNFIGHT แรงค์ดวล + ดริลใหม่ + ชุดซ้อมรายวัน

## 1.0.2 — 2026-09-13
- update.py: a stray untracked file no longer blocks git updates
- Thai text can no longer crash the updater/publisher on a non-UTF-8 console
- canonical repo URL (Intelisgod) - no redirect per request

## 1.0.1 — 2026-09-13
- CI: show git push / gh release errors as annotations
- actions checkout v5 + setup-python v6

## 1.0.0 — 2026-09-13
- First public release

