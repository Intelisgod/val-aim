@echo off
cd /d "%~dp0"
title VAL-AIM Launcher

rem ---- apply a launcher update staged by update.py (never overwrite a running .bat) ----
rem      ทั้งบรรทัดถูก parse ก่อนรัน: move แล้ว call ตัวใหม่ แล้ว exit ทันที ไม่อ่านไฟล์เดิมต่อ
if exist "%~f0.new" ( move /y "%~f0.new" "%~f0" >nul && ( call "%~f0" %* & exit /b ) )

rem ---- find Python: ตัวที่ moderngl (GPU) มี wheel ก่อน (3.13 ลงไป) แล้วค่อยตัวใหม่สุด ----
rem      GOT313 ต้องล้างทุกครั้ง: launcher ที่ call ตัวเองซ้ำได้ env ของตัวแม่มาด้วย (ไม่ล้าง = วนเปิดใหม่ไม่จบ)
set "GOT313="
call :findpy
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

rem ---- moderngl = GPU rendering — ทุกโหมดเล่นแบบ software ได้ ยกเว้น CLUTCH (ต้องวาดแมพ 3D บน GPU)
rem      Python 3.14 ยังไม่มี wheel ของ moderngl -> ถามแล้วลง Python 3.13 ข้าง ๆ ให้เอง (ไม่ถอนตัวเดิม) ----
%PY% -c "import moderngl" >nul 2>&1
if errorlevel 1 (
    echo Installing moderngl [GPU]...
    %PY% -m pip install --only-binary=:all: moderngl
    if errorlevel 1 call :nogpu
)
if defined GOT313 ( call "%~f0" %* & exit /b )

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
call :ask313
if defined GOT313 ( call "%~f0" %* & exit /b )
echo      Fix: install Python 3.13 with     py install 3.13
echo      then double-click this file again.
echo.
pause
exit /b 1

:nopython
echo.
echo  [!] Python is not installed on this PC.
call :ask313
if defined GOT313 ( call "%~f0" %* & exit /b )
echo      Opening the download page now...
echo      IMPORTANT: tick "Add Python to PATH" during install,
echo      then double-click this file again.
echo.
start https://www.python.org/downloads/
pause
exit /b 1

:nogpu
echo.
if defined PYOK (
    echo  [i] moderngl could not be installed - offline? It will retry on the next launch.
    echo      Every mode works in software rendering EXCEPT CLUTCH.
    echo.
    exit /b 0
)
echo  [i] moderngl has no build for this Python version - this is NOT an error.
echo      Every mode works in software rendering EXCEPT CLUTCH, which needs GPU mode = Python 3.13.
call :ask313
if defined GOT313 exit /b 0
echo      For CLUTCH later: run   py install 3.13   (or get Python 3.13 from python.org), then open this file again.
echo.
exit /b 0

rem ---- :findpy -> PY (+ PYOK = เป็น 3.10-3.13 ที่ลง moderngl ได้) ----
rem      มี Python install manager (ค่าเริ่มต้นของ python.org ตั้งแต่ 3.14): ห้ามลอง `py -3.13` ตรง ๆ
rem      เพราะรุ่นที่ยังไม่มีมันจะโหลดมาลงเองเงียบ ๆ -> ใช้ `pymanager list` ที่แค่ดู ไม่ลง
rem      `py -3` หยิบตัวใหม่สุดเสมอ = เครื่องที่มีทั้ง 3.14 + 3.13 ได้ 3.14 = ไม่มี GPU
:findpy
set "PY="
set "PYOK="
where pymanager >nul 2>&1
if errorlevel 1 (
    for %%V in (3.13 3.12 3.11 3.10) do if not defined PY ( py -%%V -c "exit()" >nul 2>&1 && set "PY=py -%%V" )
) else (
    for %%V in (3.13 3.12 3.11 3.10) do if not defined PY for /f "delims=" %%E in ('pymanager list -1 -f^=exe %%V 2^>nul') do if exist "%%E" set "PY="%%E""
)
rem      winget ลงแบบรายผู้ใช้แล้ว py อาจยังไม่อยู่ใน PATH ของหน้าต่างนี้ -> ชี้ไฟล์ตรง
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python313\python.exe""
if defined PY set "PYOK=1"
if not defined PY py -3 -c "exit()" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "exit()" >nul 2>&1 && set "PY=python"
exit /b 0

rem ---- :ask313 -> ถามแล้วลง Python 3.13 (ตอบ N = จำไว้ใน data\.no-py313 ไม่ถามอีก) ; สำเร็จ = GOT313 + PY ชี้ 3.13 ----
:ask313
set "GOT313="
if defined PYOK exit /b 0
if exist "data\.no-py313" exit /b 0
echo.
echo      Python 3.13 can be installed for you now (~30 MB from python.org).
echo      It installs next to any Python you already have - nothing is removed.
choice /c YN /t 30 /d Y /m "     Install Python 3.13 now? [auto-yes in 30 s]"
if errorlevel 2 (
    if not exist data mkdir data
    type nul > "data\.no-py313"
    echo      OK - will not ask again. Delete data\.no-py313 to be asked again.
    exit /b 0
)
where pymanager >nul 2>&1
if errorlevel 1 goto ask313_winget
echo Installing Python 3.13 with the Python install manager...
pymanager install -y 3.13
goto ask313_check
:ask313_winget
where winget >nul 2>&1
if errorlevel 1 (
    echo  [!] No installer found on this PC [pymanager / winget].
    exit /b 0
)
echo Installing Python 3.13 with winget...
winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
:ask313_check
call :findpy
if defined PYOK (
    set "GOT313=1"
    echo Python 3.13 is ready - restarting the launcher...
    exit /b 0
)
echo  [!] Python 3.13 could not be installed automatically.
exit /b 0
