# -*- coding: utf-8 -*-
"""การ์ด "วันนี้" บนสุดของเมนู — TodayCardMixin (วาดอย่างเดียว ; ข้อมูลจาก plan.today, ตรรกะอยู่ plan.py/routine.py)

phase-1 ux-review: ปุ่มแผนเดิมเป็นปุ่มเล็ก 176 px ใต้ START ป้ายบอกแค่ชื่อโหมด ไม่บอกเหตุผล/เป้า และแผนเก่าหายเงียบ
การ์ดนี้ขึ้นเป็นสิ่งแรกของเมนู: ซ้าย = รายการ routine (✓ ทำแล้ววันนี้ · ชนิดข้อ · โหมด · ทำไม · แรงค์ตอนนี้ → เป้า ;
คลิกแถว = เล่นข้อนั้น) ขวา = ปุ่มใหญ่ ROUTINE พร้อมเวลาจริงของรอบที่เหลือ + ซ้อม x/4 วันสัปดาห์นี้
ทุกขนาดคูณ s (ui_scale) ที่ผู้เรียกส่งมา — การ์ดสูง 190 × s พอดี 7 แถว (วอร์ม 1 + หลัก 2 + คงฟอร์ม 4 = routine เต็มของ server)
"""

import pygame

from .config import C_RED, C_TEXT, C_DIM, C_GOLD, C_GREEN, C_BORDER, C_PALE_GOLD, RANKS
from .ranks import hexrgb
from . import plan as _plan
from . import routine as _routine

PHASE_COL = {"warm": C_DIM, "block": C_RED, "maint": C_GOLD}
CARD_BG = (20, 33, 46)


def _readable(rgb):
    """สีแรงค์ที่มืดเกิน (Iron #5C5C5C) บนพื้นการ์ดมืดอ่านไม่ออก — ยกความสว่างขึ้น"""
    return tuple(min(255, int(c + (255 - c) * 0.35)) for c in rgb) if sum(rgb) < 330 else tuple(rgb)


def _rank_col(i):
    return _readable(hexrgb(RANKS[i][2])) if isinstance(i, int) and 0 <= i < len(RANKS) else C_DIM


class TodayCardMixin:
    def draw_check(self, cx, cy, size, col):
        """เครื่องหมายถูกแบบ vector (ฟอนต์ไทยบางตัวไม่มีอักขระ ✓)"""
        pts = [(cx - size * 0.45, cy), (cx - size * 0.12, cy + size * 0.33), (cx + size * 0.5, cy - size * 0.38)]
        pygame.draw.lines(self.screen, col, False, pts, max(2, int(size * 0.2)))

    def draw_arrow(self, xr, cy, w, col):
        """ลูกศรขวาแบบ vector ปลายอยู่ที่ xr (ฟอนต์ UI ไม่มีอักขระ →)"""
        t = max(1, w // 8)
        pygame.draw.line(self.screen, col, (xr - w, cy), (xr, cy), t)
        pygame.draw.lines(self.screen, col, False, [(xr - w * 0.4, cy - w * 0.35), (xr, cy), (xr - w * 0.4, cy + w * 0.35)], t)

    def draw_today_card(self, r, s):
        """วาดผ่าน cached_panel (menudraw): เนื้อหาทั้งการ์ดมาจาก view ของ plan.today ซึ่งเป็น object เดิมจนกว่าไฟล์แผน
        (mtime) / ประวัติ (จำนวนรอบ) / นาที / เวลา·ขนาดเป้าที่เลือก จะเปลี่ยน → คีย์ = id ของ view + สเกล ; hover แถว/ปุ่ม
        cached_panel ตามให้เอง — ปกติทั้งการ์ดเป็น blit เดียวต่อเฟรม (เดิมวาดใหม่หมด ~1.1 ms/เฟรม)"""
        v = _plan.today(self)
        sh = r.union(r.move(int(round(2 * s)), int(round(3 * s))))      # กรอบรวมเงาการ์ด
        self.cached_panel("today", (id(v), s), sh, lambda: self._draw_today_card(v, r, s), ref=v)

    def _draw_today_card(self, v, r, s):
        def S(v):
            return int(round(v * s))
        scr = self.screen
        mouse = pygame.mouse.get_pos()
        pygame.draw.rect(scr, (4, 12, 18), r.move(S(2), S(3)), border_radius=S(6))
        pygame.draw.rect(scr, CARD_BG, r, border_radius=S(6))
        pygame.draw.rect(scr, C_BORDER, r, 1, border_radius=S(6))
        pygame.draw.rect(scr, C_RED, (r.x, r.y + S(12), S(4), r.h - S(24)), border_radius=S(2))
        pad = S(16)
        rw = min(S(300), int(r.w * 0.36))
        cx0 = r.right - pad - rw
        lx0, lx1 = r.x + pad + S(4), cx0 - S(20)

        # ── หัวการ์ด: "วันนี้" + อายุแผน (แผนเก่า/ไม่มีแผน = สีทอง บอกทางแก้) + เรื่องหลักจากโค้ช ──
        tr = self.text("วันนี้", S(19), C_TEXT, (lx0, r.y + S(8)), bold=True)
        warn = v["state"] in ("stale", "none")
        self.text(self.fit_text(v["status"], S(11), lx1 - tr.right - S(12)), S(11), C_GOLD if warn else C_DIM,
                  (tr.right + S(12), r.y + S(16)))
        if v.get("lever"):
            lead = self.text("เรื่องหลักสัปดาห์นี้: ", S(12), C_DIM, (lx0, r.y + S(36)))
            self.text(self.fit_text(v["lever"], S(12), lx1 - lead.right, True), S(12), C_PALE_GOLD,
                      (lead.right, r.y + S(36)), bold=True)
        elif v.get("note"):
            self.text(self.fit_text(v["note"], S(12), lx1 - lx0), S(12), C_DIM, (lx0, r.y + S(36)))

        # ── แถวรายการ ──
        y = r.y + S(58)
        pitch = S(18)
        rows = v["rows"]
        fit_n = max(1, (r.bottom - S(6) - y) // pitch)
        shown = rows if len(rows) <= fit_n else rows[:fit_n - 1]
        for row in shown:
            rr = pygame.Rect(lx0 - S(6), y - S(1), lx1 - lx0 + S(6), pitch)
            self.zone(rr, lambda row=row: _plan.start_row(self, row))
            if rr.collidepoint(mouse):
                pygame.draw.rect(scr, (31, 46, 61), rr, border_radius=S(3))
            done, n = row["done"], row["rounds"]
            if done >= n:
                self.draw_check(lx0 + S(10), y + pitch // 2 - S(1), S(12), C_GREEN)
            else:
                self.text(f"{done}/{n}", S(11), C_GOLD if done else C_DIM, (lx0, y + S(1)), bold=bool(done))
            self.text(_routine.PHASE_TH.get(row["phase"], ""), S(10), PHASE_COL.get(row["phase"], C_DIM),
                      (lx0 + S(34), y + S(2)))
            # แรงค์ตอนนี้ → เป้า (ชิดขวา วาดจากขวาไปซ้าย) — ฟอร์ม = เฉลี่ย 5 รอบล่าสุดที่ config ของรายการ (แบบ dashboard) ;
            # gun = ค่ากลางแรงค์ดวล 5 รอบล่าสุด (duel.recent_tier — เลขเดียวกับแผงโปรไฟล์ในเมนูเดียวกัน)
            tgt, cur = row.get("target"), row.get("cur")
            parts = []
            if tgt:
                parts.append((_routine.short_rank(tgt), _rank_col(_routine.target_index(tgt)), True))
                parts.append((None, C_DIM, False))           # ลูกศร vector (ฟอนต์ไม่มี U+2192)
            if cur is not None:
                parts.append((_routine.short_rank(RANKS[cur][1]), _rank_col(cur), True))
            elif tgt:
                # แรงค์ดวลที่เล่นแล้วแต่ยังไม่นิ่ง (routine.ladder_seeking — ต้องหลายรอบ) ≠ ยังไม่เคยเล่น
                parts.append(("กำลังวัด" if row.get("seek") else "ใหม่", C_DIM, False))
            rx = lx1
            for txt, col, bold in parts:
                if txt is None:
                    self.draw_arrow(rx - S(4), y + pitch // 2 - S(1), S(12), col)
                    rx -= S(18)
                else:
                    rx = self.text(txt, S(11), col, (rx, y + S(1)), right=True, bold=bold).x
            lab_x = lx0 + S(86)
            lr = self.text(self.fit_text(row["label"], S(12), rx - lab_x - S(8), True), S(12),
                           C_TEXT if done < n else C_DIM, (lab_x, y), bold=True)
            why_x = lr.right + S(10)
            if row.get("why") and rx - why_x > S(40):
                self.text(self.fit_text(row["why"], S(11), rx - why_x - S(10)), S(11), C_DIM, (why_x, y + S(1)))
            y += pitch
        if len(shown) < len(rows):
            self.text(f"+ อีก {len(rows) - len(shown)} ข้อ (อยู่ในคิว {v['cta']['title']})", S(10), C_DIM,
                      (lx0 + S(34), y + S(2)))

        # ── ขวา: ปุ่มหลัก ROUTINE/WARMUP (เวลาจริงของรอบที่เหลือ) + วันซ้อมสัปดาห์นี้ ──
        cta = v["cta"]
        br = pygame.Rect(cx0, r.y + S(14), rw, S(64))
        self.zone(br, lambda: cta["on_click"](self))
        hov = br.collidepoint(mouse)
        if cta["done"]:
            pygame.draw.rect(scr, (30, 62, 50) if hov else (22, 48, 40), br, border_radius=S(5))
            pygame.draw.rect(scr, C_GREEN, br, max(1, S(2)), border_radius=S(5))
        else:
            pygame.draw.rect(scr, (224, 48, 64) if hov else C_RED, br, border_radius=S(5))
        self.text(cta["title"], S(21), (255, 255, 255), (br.centerx, br.y + S(22)), center=True, bold=True)
        self.text(self.fit_text(cta["sub"], S(12), rw - S(16)), S(12), C_GREEN if cta["done"] else (255, 255, 255),
                  (br.centerx, br.y + S(47)), center=True)
        a = v["adh"]
        y2 = br.bottom + S(12)
        met = a["days"] >= a["goal"]
        lr = self.text(f"ซ้อม {a['days']}/{a['goal']} วันสัปดาห์นี้", S(13), C_GREEN if met else C_TEXT, (cx0, y2),
                       bold=True)
        for i in range(max(a["goal"], a["days"])):
            c = (lr.right + S(12) + i * S(14) + S(5), lr.centery)
            if i < a["days"]:
                pygame.draw.circle(scr, C_GREEN, c, S(5))
            else:
                pygame.draw.circle(scr, C_BORDER, c, S(5), max(1, S(1)))
        y2 += S(22)
        today = "วันนี้ซ้อมแล้ว" if a["today"] else "วันนี้ยังไม่ได้ซ้อม"
        self.text(self.fit_text(f"7 วันล่าสุดซ้อมตามแผน {a['minutes']:g} นาที · {today}", S(11), rw), S(11), C_DIM,
                  (cx0, y2))
        y2 += S(20)
        # กฎขนาดเป้าเล็กลงเองบอกเฉพาะเมื่อมีข้อหลักที่ขยับได้จริง (plan.today → ladder ; โหมดบนบันได + มีเป้า)
        hints = (["สลับข้อแบบสุ่ม (งานวิจัยส่วนใหญ่: ติดมือทนกว่าเล่นรวด)",
                  "ถึงเป้า 2 รอบติด = ขนาดเป้าเล็กลงเอง · คลิกแถว = เล่นข้อนั้น" if v.get("ladder")
                  else "คลิกแถว = เล่นข้อนั้น"]
                 if v["state"] == "routine" else ["คลิกแถว = เล่นข้อนั้นข้อเดียว"])
        for h in hints:
            self.text(self.fit_text(h, S(10), rw), S(10), C_DIM, (cx0, y2))
            y2 += S(15)
