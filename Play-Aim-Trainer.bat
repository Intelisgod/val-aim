@echo off
cd /d "%~dp0"
title VAL-AIM Launcher

rem ---- apply a launcher update staged by update.py (never overwrite a running .bat) ----
rem      ทั้งบรรทัดถูก parse ก่อนรัน: move แล้ว call ตัวใหม่ แล้ว exit ทันที ไม่อ่านไฟล์เดิมต่อ
if exist "%~f0.new" ( move /y "%~f0.new" "%~f0" >nul && ( call "%~f0" %* & exit /b ) )

rem ---- find Python (py launcher first, then python) ----
rem      เลือกเวอร์ชันที่ moderngl มี wheel ก่อน (3.13 ลงไป) — `py -3` หยิบตัวใหม่สุดเสมอ
rem      เครื่องที่มีทั้ง 3.14 + 3.13 เลยได้ 3.14 = ไม่มี GPU = เล่น CLUTCH ไม่ได้ แม้ลง 3.13 แล้ว
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do if not defined PY ( py -%%V -c "exit()" >nul 2>&1 && set "PY=py -%%V" )
if not defined PY py -3 -c "exit()" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "exit()" >nul 2>&1 && set "PY=python"
if not defined PY goto nopython

rem ---- auto update (update.py) — ดึงจาก branch `release` ที่ผ่าน selftest บน GitHub Actions แล้วเท่านั้น ----
rem      โคลนด้วย git  -> fetch + fast-forward (ไม่ทับไฟล์ที่ผู้ใช้แก้เอง; data/ อยู่ใน .gitignore)
rem      โหลด zip มา   -> เทียบ VERSION แล้ว overlay ไฟล์ ยกเว้น data/ + ลบไฟล์เก่าตาม MANIFEST
rem      ไฟล์ที่ถูกแทนที่สำรองไว้ใน .prev/ -> ถ้าเกมพังหลังอัปเดต จะถามให้ย้อนกลับ
rem      ออฟไลน์/ล้มเหลว -> ข้าม เล่นเวอร์ชันเดิม
rem      exit 3 = มีของใหม่ -> เปิด launcher ใหม่ (ทั้งบล็อกในวงเล็บถูกอ่านจบก่อนรัน
rem      ดังนั้นต่อให้ไฟล์ .bat นี้ถูกเขียนทับระหว่าง update ก็ไม่อ่านไฟล์เดิมต่อ)
(
    %PY% update.py
    if errorlevel 3 (
        if exist "%~f0.new" move /y "%~f0.new" "%~f0" >nul
        echo Restarting launcher with the new version...
        call "%~f0" %*
        exit /b
    )
)

rem ---- install pygame-ce on first run (must be -ce: upstream pygame has no
rem      mouse.set_relative_mode -> raw input silently dead)
rem      --only-binary: หยุด pip ไม่ให้คอมไพล์เอง (เครื่องไม่มี compiler = ค้างยาวแล้วพัง) ----
%PY% -c "import pygame, sys; sys.exit(0 if hasattr(pygame.mouse, 'set_relative_mode') else 1)" >nul 2>&1
if errorlevel 1 (
    echo Installing pygame-ce, please wait...
    %PY% -m pip uninstall -y pygame >nul 2>&1
    %PY% -m pip install --only-binary=:all: pygame-ce
    if errorlevel 1 goto nowheel
)

rem ---- moderngl = GPU rendering (ไม่บังคับ)
rem      Python 3.14 ยังไม่มี wheel ของ moderngl -> ลงไม่ได้ก็ข้ามไปเลย
rem      เกม fallback เป็น software rendering เองแล้วเล่นได้ครบทุกโหมด ----
%PY% -c "import moderngl" >nul 2>&1
if errorlevel 1 (
    echo Installing moderngl [GPU, optional]...
    %PY% -m pip install --only-binary=:all: moderngl
    if errorlevel 1 (
        echo.
        echo  [i] moderngl has no build for this Python version - this is NOT an error.
        echo      The game runs in software rendering mode - every mode EXCEPT CLUTCH works.
        echo      CLUTCH needs GPU mode: install Python 3.13, then open this file again
        echo        py install 3.13
        echo      or download "Python 3.13" from https://www.python.org/downloads/windows/
        echo.
    )
)

rem ---- launch the game (code อยู่ใน src/, รับ arg เช่น --mode flick ส่งต่อได้) ----
%PY% src\aim_trainer.py %*
if errorlevel 1 (
    rem เกมจบด้วย error: ถ้าเพิ่งอัปเดตมา update.py จะถามว่าจะย้อนกลับเวอร์ชันก่อนหน้าไหม
    %PY% update.py --crashed
    pause
)
exit /b 0

:nowheel
echo.
echo  [!] pygame-ce could not be installed - your Python may be too new.
echo      Fix: install Python 3.13 with     py install 3.13
echo      then double-click this file again.
echo.
pause
exit /b 1

:nopython
echo.
echo  [!] Python is not installed on this PC.
echo      Opening the download page now...
echo      IMPORTANT: tick "Add Python to PATH" during install,
echo      then double-click this file again.
echo.
start https://www.python.org/downloads/
pause
exit /b 1
