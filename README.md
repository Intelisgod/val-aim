# VAL//AIM — ตัวฝึกเล็งสไตล์ Aim Lab สำหรับ Valorant

[![test-and-release](https://github.com/Intelisgod/val-aim/actions/workflows/test-and-release.yml/badge.svg)](https://github.com/Intelisgod/val-aim/actions) [![release](https://img.shields.io/github/v/release/Intelisgod/val-aim?label=version)](https://github.com/Intelisgod/val-aim/releases)

10+ โหมด: flick · precision · tracking · reaction (static/flick/peek) · strafe · sniper ·
spray (vandal/phantom) · dodge · placement · switch · gunfight (6 ปืน · 8 ดริล · recoil จริงจากข้อมูลในเกม
· บอทแอบมุมแล้วยิงสวนตามแนวสายตา · แรงค์ดวล)
การเคลื่อนที่/ความแม่นแบบเกม (deadzone 27.5%, Shift เดิน, หมอบ), มีแรงค์ให้ไต่ต่อโหมด, ตั้ง DPI/Sens ให้ตรงกับในเกม,
การ์ด "วันนี้" + ปุ่ม WARMUP บนเมนู

> **อัปเดต ก.ย. 2026 เปลี่ยนกติกาหลายโหมดให้เหมือนเกมขึ้น** — PB/สถิติเก่าของ placement, switch, dodge, strafe, gunfight
> และ spray รุ่นก่อนจึงไม่นับแล้ว (ยังอยู่ในไฟล์ครบ) ดูรายละเอียดใน [CHANGELOG.md](CHANGELOG.md)

> **อัปเดตอัตโนมัติ** — ทุกครั้งที่เปิดเกม launcher จะเช็ก GitHub แล้วดึงเวอร์ชันใหม่ให้เอง พร้อมเด้งบอกว่ามีอะไรใหม่
> ทุกเวอร์ชันผ่านการทดสอบอัตโนมัติก่อนถึงมือคุณ, ประวัติซ้อม (`data/`) ไม่ถูกแตะ, และถ้าเกมพังหลังอัปเดต
> จะถามให้ย้อนกลับเวอร์ชันเดิมได้ทันที — ดูว่าแต่ละเวอร์ชันแก้อะไรใน [CHANGELOG.md](CHANGELOG.md)

## ติดตั้ง (Windows)

**1. ต้องมี Python** — ถ้ายังไม่มี โหลดจาก <https://www.python.org/downloads/>
   *ตอนติดตั้งต้องติ๊ก "Add Python to PATH"* — แนะนำ Python 3.13 (ดูหัวข้อด้านล่าง)

**2. โหลดเกม** เลือกวิธีใดวิธีหนึ่ง

| วิธี | ทำยังไง | อัปเดตยังไง |
|---|---|---|
| **A. ZIP** (ง่ายสุด) | กดปุ่มเขียว **Code → Download ZIP** แล้วแตกไฟล์ออกมาทั้งโฟลเดอร์ | `update.py` เช็กให้เองตอนเปิดเกม |
| **B. git** | `git clone -b release https://github.com/Intelisgod/val-aim.git` | ดึง branch `release` ให้เองตอนเปิดเกม |

**3. ดับเบิลคลิก `Play-Aim-Trainer.bat`**
   ครั้งแรกจะลง `pygame-ce` ให้เอง (~10 MB) รอสักครู่ แล้วเกมจะเปิดขึ้นมา

## ครั้งแรกช้าเป็นเรื่องปกติ

ที่ช้าไม่ใช่ตัวเกม (ทั้งชุดไม่ถึง 1 MB) แต่เป็น Python เอง (30–60 MB จาก python.org)
กับ pygame-ce (~10 MB จาก PyPI) — โหลดครั้งเดียวจบ ครั้งต่อไปเปิดปุ๊บติดปั๊บ

ถ้าแถบจุด `..........` นิ่งหลายนาทีไม่ขยับ = ค้างจริง กด Ctrl+C แล้วเปิดใหม่ (โหลดต่อจากเดิมได้)
หรือโหลด installer .exe จาก python.org ตรง ๆ แทน

## เลือกเวอร์ชัน Python

Python 3.14 เล่นได้ปกติ แต่ยังไม่มี `moderngl` (โหมด GPU) รองรับ — เกมจะสลับเป็น
software rendering ให้เอง เล่นได้ครบทุกโหมด อยากได้ GPU mode พิมพ์ในหน้าต่างดำ:

```
py install 3.13
```

แล้วดับเบิลคลิก `Play-Aim-Trainer.bat` ใหม่

## ปุ่มพื้นฐาน

- คลิกซ้าย = ยิง | ESC = กลับเมนู / หยุดพัก
- ตั้งค่า **DPI + Sens** ในหน้า SETTINGS ให้ตรงกับใน Valorant ก่อนเริ่มซ้อม
  (ค่าเริ่มต้น DPI 800 / Sens 0.40)
- strafe / dodge / gunfight: WASD เดิน · SHIFT เดิน (แม่นกว่าวิ่ง) · CTRL หรือ C หมอบ (strafe/gunfight)
  — ต้องหยุดก่อนยิงเหมือนในเกม
- gunfight: RMB สโคป/ADS · R รีโหลด · ค้าง R 0.8 วิ = เริ่มใหม่ · ในเมนู V สลับปืน / B สลับดริล
- strafe กับ sniper ไม่มีแรงค์ (นับจำนวนที่ยิงโดน) ให้ดู acc% แทน ; gunfight มีแรงค์ดวลใน DUEL / ANGLE / PEEK
  (ขึ้นหลังดวลราว 100 ครั้ง — ก่อนนั้นบอก "กำลังวัด") ดริลอื่นดู K/D · TTK · ACC
- ปุ่ม **WARMUP** บนการ์ด "วันนี้" = ไล่ซ้อมชุดวอร์ม (flick → spray → reaction) อัตโนมัติ โหมดละ 2 รอบ —
  จบรอบกด **NEXT** หรือ ENTER ต่อ

## ผลซ้อมเก็บที่ไหน

`data/aim_trainer_data.json` — โปรแกรมสร้างเองตอนเล่นจบรอบแรก
เริ่มนับแรงค์จากศูนย์ของตัวเอง ไม่มีสถิติของใครติดมา และตัวอัปเดตจะไม่แตะโฟลเดอร์นี้

## ถ้าเปิดไม่ขึ้น

| อาการ | แก้ |
|---|---|
| ขึ้นว่าไม่มี Python | ติดตั้งตามข้อ 1 แล้วติ๊ก Add to PATH ให้ครบ |
| ลง pygame-ce ไม่สำเร็จ | `py install 3.13` แล้วลองใหม่ |
| เคยลง pygame ตัวปกติไว้ | `py -m pip uninstall pygame` แล้ว `py -m pip install pygame-ce` (ต้องเป็น **-ce** ไม่งั้น raw input ไม่ทำงาน) |
| อัปเดตไม่ขึ้น | เปิดไฟล์ `VERSION` แล้วแก้เป็น `0.0.0` แล้วเปิดเกมใหม่ (จะโหลดใหม่ทั้งชุด) หรือโหลด ZIP มาแตกทับ (ยกเว้น `data/`) |
| เกมพังหลังอัปเดต | launcher จะถามเองว่าย้อนกลับไหม ตอบ Yes แล้วเปิดใหม่ — เวอร์ชันที่พังจะถูกข้ามจนกว่าจะมีตัวใหม่กว่า (ไฟล์ `.hold`) |

## เปิดเข้าโหมดตรง ๆ (ไม่ผ่านเมนู)

```
Play-Aim-Trainer.bat --mode flick
Play-Aim-Trainer.bat --mode spray --variant vandal
Play-Aim-Trainer.bat --mode reaction --variant peek
Play-Aim-Trainer.bat --mode gun --variant vandal --drill peek
Play-Aim-Trainer.bat --warmup
```
