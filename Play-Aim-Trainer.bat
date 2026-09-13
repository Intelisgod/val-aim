@echo off
cd /d "%~dp0"
title VAL-AIM Launcher

rem ---- apply a launcher update staged by update.py (never overwrite a running .bat) ----
rem      ทั้งบรรทัดถูก parse ก่อนรัน: move แล้ว call ตัวใหม่ แล้ว exit ทันที ไม่อ่านไฟล์เดิมต่อ
if exist "%~f0.new" ( move /y "%~f0.new" "%~f0" >nul && ( call "%~f0" %* & exit /b ) )

rem ---- find Python (py launcher first, then python) ----
set "PY="
py -3 -c "exit()" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "exit()" >nul 2>&1 && set "PY=python"
if not defined PY goto nopython

rem ---- auto update (update.py) ----
rem      โคลนด้วย git  -> git pull --ff-only (ไม่ทับไฟล์ที่ผู้ใช้แก้เอง; data/ อยู่ใน .gitignore)
rem      โหลด zip มา   -> เทียบ VERSION กับ GitHub แล้ว overlay ไฟล์ทั้งหมด ยกเว้น data/
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
        echo      The game runs in software rendering mode, all modes playable.
        echo      Want GPU mode? Install Python 3.13:   py install 3.13
        echo.
    )
)

rem ---- launch the game (code อยู่ใน src/, รับ arg เช่น --mode flick ส่งต่อได้) ----
%PY% src\aim_trainer.py %*
if errorlevel 1 pause
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
