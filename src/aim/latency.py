# -*- coding: utf-8 -*-
"""เวลาเฟรมระหว่างรอบ + คำแนะนำ latency บนหน้าผล (ตรรกะล้วน — pygame ใช้แค่ถามรีเฟรชเรตจอ ถ้ามี)

ทำไมต้องโชว์: latency ของระบบคือแต้มต่อที่ซ่อนอยู่ — NVIDIA × KovaaK's (ผู้เล่น 15,000+ คน) latency 25 vs 85 ms
เก็บเป้าได้มากขึ้น 24% ในงานง่าย และมากกว่า 2 เท่าในงาน flick ยาก ; Riot: peeker's advantage ~141 ms ที่ 60 FPS
vs ~71 ms ที่ 144 FPS (phase-1 research §4) — เทรนเนอร์วัดได้แค่เวลาเฟรมของตัวเอง (latency ปลายทางวัดไม่ได้
ถ้าไม่มีฮาร์ดแวร์) จึงโชว์เวลาเฟรมจริง + เตือนเมื่อ FPS ต่ำกว่ารีเฟรชจอ + ทิปครั้งเดียว (settings "tip_latency")
"""

FRAME_KEEP = 20000       # เฟรมสูงสุดที่เก็บต่อรอบ (240 FPS × 60 วิ = 14,400)
MIN_FRAMES = 30          # น้อยกว่านี้ (รอบถูกตัด/เทส) = ไม่สรุป

TIP = "แนะนำ (ใช้กับเกมจริงด้วย): cap FPS สูงกว่ารีเฟรชจอ · เปิด NVIDIA Reflex (On+Boost) · เมาส์สาย/2.4 GHz ไม่ใช่ Bluetooth"
TIP_WHY = "latency ระบบ 25 vs 85 ms ยิงเป้าโดนต่างกัน ~24% (NVIDIA × KovaaK's 15,000 คน)"


def frame_stats(ms):
    """{avg_ms, p99_ms, fps, n} จากเวลาเฟรม (ms) ของรอบ — p99 = "1% ช้าสุด" ; เฟรมน้อยเกิน = None"""
    xs = sorted(m for m in (ms or []) if m > 0)
    if len(xs) < MIN_FRAMES:
        return None
    avg = sum(xs) / len(xs)
    p99 = xs[min(len(xs) - 1, int(0.99 * len(xs)))]
    return {"avg_ms": avg, "p99_ms": p99, "fps": 1000.0 / avg, "n": len(xs)}


def refresh_hz():
    """รีเฟรชเรตจอ (Hz) หรือ None — pygame-ce ≥ 2.4 ; headless/ไม่มีหน้าต่าง = None"""
    try:
        import pygame
        for fn in ("get_current_refresh_rate", "get_desktop_refresh_rates"):
            f = getattr(pygame.display, fn, None)
            if f is None:
                continue
            try:
                v = f()
            except Exception:
                continue
            if isinstance(v, (list, tuple)):
                v = v[0] if v else 0
            if isinstance(v, (int, float)) and v >= 24:
                return int(round(v))
    except Exception:
        pass
    return None


def hygiene(st, hz=None, cap=None, vsync=False):
    """(บรรทัดเวลาเฟรม, คำเตือน | None) — st จาก frame_stats (None = ไม่มีบรรทัด)"""
    if not st:
        return None, None
    parts = [f"เฟรมเทรนเนอร์ {st['avg_ms']:.1f} ms ({st['fps']:.0f} FPS)", f"1% ช้าสุด {st['p99_ms']:.1f} ms"]
    if hz:
        parts.append(f"จอ {hz} Hz")
    parts.append("vsync" if vsync else ("cap " + (str(cap) if cap else "∞")))
    warn = None
    if hz and st["fps"] < 0.95 * hz:
        warn = "FPS ต่ำกว่ารีเฟรชจอ = เมาส์หน่วงเพิ่ม — SETTINGS › FRAME PACING/GPU (ลด Render Scale / เปิด GPU)"
    elif st["p99_ms"] > max(2.5 * st["avg_ms"], st["avg_ms"] + 10):
        warn = "เฟรมกระตุกเป็นช่วง ๆ — ปิดโปรแกรมเบื้องหลัง (browser/overlay/อัดจอ) ก่อนซ้อม"
    return " · ".join(parts), warn


def selftest():
    errors = []
    if frame_stats([4.0] * 10) is not None:
        errors.append("latency: เฟรมน้อยกว่า MIN_FRAMES ต้องไม่สรุป")
    st = frame_stats([4.0] * 99 + [20.0])
    if not st or abs(st["avg_ms"] - 4.16) > 1e-9 or st["p99_ms"] != 20.0 or round(st["fps"]) != 240:
        errors.append(f"latency: frame_stats ผิด ({st})")
    line, warn = hygiene(frame_stats([10.0] * 100), hz=144, cap=240)
    if "100 FPS" not in (line or "") or "จอ 144 Hz" not in line or not warn or "รีเฟรช" not in warn:
        errors.append(f"latency: 100 FPS บนจอ 144 Hz ต้องเตือน ({line} / {warn})")
    line, warn = hygiene(frame_stats([4.0] * 100), hz=144, cap=240)
    if warn is not None or not line.endswith("cap 240"):
        errors.append(f"latency: 240 FPS บนจอ 144 Hz ไม่ต้องเตือน ({line} / {warn})")
    _l, warn = hygiene(frame_stats([4.0] * 95 + [30.0] * 5), hz=None, vsync=True)
    if not warn or "กระตุก" not in warn:
        errors.append(f"latency: เฟรมกระตุกต้องเตือน ({warn})")
    return errors
