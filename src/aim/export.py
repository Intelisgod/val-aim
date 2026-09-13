# -*- coding: utf-8 -*-
"""[Module 5] Export score card เป็นรูป

จากหน้า results: ปุ่ม "บันทึกการ์ด" → สร้าง "การ์ดสรุปผล" สวย ๆ
(rank / โหมด+config / คะแนน / acc / RT / headshot% / ป้าย PERSONAL BEST / วันที่)
แล้วเซฟเป็น PNG + ก๊อปลง clipboard ไปอวด/แชร์ได้ทันที

ขอบเขต: แก้ไฟล์นี้ไฟล์เดียว เชื่อมต่อผ่าน registry.RESULTS_ACTIONS (ดู aim/registry.py)
- ฟอนต์ไทย leelawadee ผ่าน game.text/game.font, ไม่มี emoji, ไม่ใช้ numpy
- ดึงข้อมูลจาก game.res_* / game.score / game.mode ตรง ๆ (ไม่ recompute ใหม่)
- draw_rank_emblem วาดลง game.screen → ใช้ screen-swap ชั่วคราวเพื่อวาดลงการ์ด
"""

import os
import glob
import datetime

import pygame

from .config import (C_BG, C_DARKER, C_RED, C_TEXT, C_DIM, C_GOLD, C_GREEN,
                     C_PANEL, C_BORDER, MODE_NAME, SIZE_TH, SNIPER_TOTAL)
from .ranks import get_rank, get_rt_rank, hexrgb, parse_rank, VALID_TIERS
from . import data, registry   # อ้าง data.DATA_FILE แบบ dynamic — ตอนเทส aim/selftest.py redirect ไป temp

CARD_W, CARD_H = 1200, 630   # สัดส่วนโซเชียล (เช่น OG image / การ์ดทวิตเตอร์)
_MARGIN = 56
_LABEL = "บันทึก/แชร์การ์ด"


def build_score_card(game):
    """สร้าง 'การ์ดสรุปผล' ขนาดคงที่ 1200x630 บน Surface แยก แล้วคืน pygame.Surface
    ใช้ธีมสี C_* + ฟอนต์เดิม; ไม่ยุ่ง clipboard/ไฟล์ (ดู _save_card)"""
    CW, CH, M = CARD_W, CARD_H, _MARGIN
    card = pygame.Surface((CW, CH))

    # ----- พื้นหลังธีม: ไล่เฉดบน→ล่าง + ลายเป้าจาง ๆ + แถบ accent บนสุด -----
    for i in range(CH):
        t = i / CH
        card.fill((int(C_BG[0] * (1 - t) + C_DARKER[0] * t),
                   int(C_BG[1] * (1 - t) + C_DARKER[1] * t),
                   int(C_BG[2] * (1 - t) + C_DARKER[2] * t)),
                  (0, i, CW, 1))
    motif = pygame.Surface((CW, CH), pygame.SRCALPHA)
    mcx, mcy = 905, 322
    pygame.draw.circle(motif, (*C_BORDER, 80), (mcx, mcy), 215, 3)
    pygame.draw.circle(motif, (*C_BORDER, 55), (mcx, mcy), 150, 2)
    pygame.draw.line(motif, (*C_RED, 36), (mcx - 250, mcy), (mcx + 250, mcy), 2)
    pygame.draw.line(motif, (*C_RED, 36), (mcx, mcy - 250), (mcx, mcy + 250), 2)
    card.blit(motif, (0, 0))
    pygame.draw.rect(card, C_RED, (0, 0, CW, 8))

    # ----- โลโก้ VAL//AIM + วันที่ -----
    cx = M
    for s, col in (("VAL", C_TEXT), ("//", C_RED), ("AIM", C_TEXT)):
        cx = game.text(s, 46, col, (cx, 38), bold=True, surf=card).right
    game.text("VALORANT AIM TRAINER", 15, C_DIM, (M + 2, 94), surf=card)
    game.text(datetime.datetime.now().strftime("%d %b %Y  ·  %H:%M"),
              16, C_DIM, (CW - M, 52), right=True, surf=card)
    pygame.draw.line(card, C_BORDER, (M, 128), (CW - M, 128), 1)

    # ----- แรงค์ + คะแนนใหญ่ (ตรรกะเดียวกับ draw_results — ไม่ recompute) -----
    md = game.mode
    if md == "reaction":
        _, rname, rcol = get_rt_rank(getattr(game, "res_avg_rt", 0),
                                     getattr(game, "reaction_variant", "static"))
        big, score_label = f"{getattr(game, 'res_avg_rt', 0)}", "AVG REACTION (ms)"
    elif md == "strafe":
        rname, rcol = "TRAINING", "#7F9BB5"
        big, score_label = f"{getattr(game, 'hits', 0)}", "TARGETS HIT"
    elif md == "sniper":
        rname, rcol = "SNIPER TRAINING", "#B97FE0"
        big, score_label = f"{getattr(game, 'sniper_hits', 0)}/{SNIPER_TOTAL}", "BALLS HIT"
    else:
        _, rname, rcol = get_rank(getattr(game, "score", 0), getattr(game, "duration", 30),
                                  getattr(game, "size_key", "medium"), md)
        big, score_label = f"{getattr(game, 'score', 0):,}", "SCORE"
    rcol_rgb = hexrgb(rcol) if isinstance(rcol, str) else rcol

    # บรรทัด config โหมด
    cfg = [MODE_NAME.get(md, str(md).upper())]
    if md == "reaction":
        cfg.append(getattr(game, "reaction_variant", "static").upper())
    elif md == "spray":
        cfg += [getattr(game, "spray_weapon", "vandal").upper(), f"{getattr(game, 'duration', 30)}s"]
    elif md == "strafe":
        cfg.append(f"{getattr(game, 'duration', 30)}s")
    elif md != "sniper":
        cfg += [f"{getattr(game, 'duration', 30)}s", SIZE_TH.get(getattr(game, "size_key", "medium"), "")]
    cfg.append(f"SENS {game.S.get('sens', 0.4):g}")
    game.text("  ·  ".join(p for p in cfg if p), 22, C_DIM, (M, 148), surf=card)

    # ป้าย PERSONAL BEST (ถ้า res_pb)
    if getattr(game, "res_pb", False):
        ptxt = "PERSONAL BEST"
        pill = pygame.Rect(0, 0, game.font(18, True).size(ptxt)[0] + 40, 38)
        pill.topright = (CW - M, 146)
        pygame.draw.rect(card, C_GOLD, pill, border_radius=19)
        game.text(ptxt, 18, C_DARKER, pill.center, center=True, bold=True, surf=card)

    # ----- emblem แรงค์ (ซ้าย) — draw_rank_emblem วาดลง game.screen จึง swap ชั่วคราว -----
    emb_cx, emb_cy, emb = M + 64, 300, 128
    has_emblem = parse_rank(rname)[0] in VALID_TIERS
    prev_screen = game.screen
    game.screen = card
    try:
        if has_emblem:
            game.draw_rank_emblem(emb_cx, emb_cy, emb, rname, rcol_rgb)
    finally:
        game.screen = prev_screen
    if has_emblem:
        game.text(rname, 38, rcol_rgb, (emb_cx + emb // 2 + 26, emb_cy - 24), bold=True, surf=card)
        game.text("RANK", 15, C_DIM, (emb_cx + emb // 2 + 28, emb_cy + 22), surf=card)
    else:
        game.text(rname, 34, rcol_rgb, (M, emb_cy - 18), bold=True, surf=card)

    # ----- คะแนนใหญ่ (ขวา) -----
    game.text(score_label, 18, C_DIM, (CW - M, 214), right=True, surf=card)
    game.text(big, 100, C_TEXT, (CW - M, 236), right=True, bold=True, surf=card)

    # ----- แถบสถิติ acc / RT / HS% -----
    def acc_col(p):
        return C_GREEN if p >= 70 else C_GOLD if p >= 45 else C_RED
    res_acc = getattr(game, "res_acc", 0)
    res_rt = getattr(game, "res_avg_rt", 0)
    res_hs = getattr(game, "res_hs", 0)
    chips = [("ACCURACY", f"{res_acc}%", acc_col(res_acc)),
             ("AVG REACT", f"{res_rt} ms", C_TEXT),
             ("HEADSHOT %", f"{res_hs}%", acc_col(res_hs))]
    cy0, chh, gap = 430, 120, 20
    cw = (CW - M * 2 - gap * 2) // 3
    for i, (lab, val, col) in enumerate(chips):
        rect = pygame.Rect(M + i * (cw + gap), cy0, cw, chh)
        pygame.draw.rect(card, C_PANEL, rect, border_radius=10)
        pygame.draw.rect(card, C_BORDER, rect, 1, border_radius=10)
        game.text(val, 46, col, (rect.centerx, rect.y + 34), center=True, bold=True, surf=card)
        game.text(lab, 16, C_DIM, (rect.centerx, rect.y + 88), center=True, surf=card)

    # ----- footer: ชื่อผู้เล่น + ลายน้ำ -----
    nm = (game.data.get("name") or "").strip()
    if nm:
        game.text("PLAYER  " + nm.upper(), 16, C_GOLD, (M, 578), bold=True, surf=card)
    game.text("VAL//AIM", 16, C_DIM, (CW - M, 578), right=True, bold=True, surf=card)
    return card


def _save_card(game):
    """on_click ของปุ่มหน้า results: สร้างการ์ด → เซฟ PNG (โฟลเดอร์เดียวกับ DATA_FILE)
    + ก๊อปลง clipboard (ข้ามตอน headless) → โชว์ข้อความยืนยันแบบเดียวกับ capture_screen"""
    try:
        card = build_score_card(game)
    except Exception:
        game.shot_saved_msg = "สร้างการ์ดไม่สำเร็จ"
        game.shot_saved_until = pygame.time.get_ticks() + 3500
        return
    fn = os.path.join(os.path.dirname(data.DATA_FILE),
                      "valaim_card_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".png")
    saved = False
    try:
        pygame.image.save(card, fn)
        saved = True
    except Exception:
        saved = False
    copied = game.copy_to_clipboard(card) if not getattr(game, "headless", False) else False
    if copied and saved:
        game.shot_saved_msg = "ก๊อปการ์ดลง clipboard แล้ว (Ctrl+V แปะได้เลย) + เซฟไฟล์: " + os.path.basename(fn)
    elif copied:
        game.shot_saved_msg = "ก๊อปการ์ดลง clipboard แล้ว — Ctrl+V แปะอวดได้เลย"
    elif saved:
        game.shot_saved_msg = "บันทึกการ์ดแล้ว: " + os.path.basename(fn)
    else:
        game.shot_saved_msg = "บันทึกการ์ดไม่สำเร็จ"
    game.shot_saved_until = pygame.time.get_ticks() + 3500


def register(game):
    """ถูกเรียกครั้งเดียวตอนสร้าง Game (auto จาก Game.__init__) — append ปุ่มลง RESULTS_ACTIONS
    แบบ idempotent (กันซ้ำเมื่อมีหลาย Game instance ในโปรเซสเดียว เช่นตอนเทส)"""
    for a in registry.RESULTS_ACTIONS:
        if a.get("_id") == "export_card":
            return
    registry.RESULTS_ACTIONS.append({"label": _LABEL, "on_click": _save_card, "_id": "export_card"})


def selftest(game=None):
    """เทส headless: build_score_card คืน Surface 1200x630 + ปุ่ม action ไม่ crash (ไม่ยุ่ง clipboard จริง)
    เรียกได้ 2 แบบ:
      export.selftest(g)  — ใช้ game ที่มีอยู่ (hook จริงใน aim/selftest.py: errors += export.selftest(g))
      export.selftest()   — สร้าง Game(headless=True) เอง (รันเดี่ยว: python -m aim.export)
    คืน list[str] ของ error (ว่าง = ผ่าน); ลบเฉพาะไฟล์การ์ดที่เทสสร้างเอง"""
    errs = []
    own = False
    # การ์ดที่ผู้ใช้ export เก็บไว้ก่อนหน้าอยู่โฟลเดอร์เดียวกัน — จดไว้ก่อน แล้วลบเฉพาะไฟล์ที่เทสสร้างเอง
    card_glob = os.path.join(os.path.dirname(data.DATA_FILE), "valaim_card_*.png")
    pre = set(glob.glob(card_glob))
    if game is None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from .game import Game
        game = Game(headless=True)
        own = True
    try:
        card = build_score_card(game)
        if not isinstance(card, pygame.Surface):
            errs.append("build_score_card did not return a Surface")
        elif card.get_size() != (CARD_W, CARD_H):
            errs.append("score card size wrong: %s" % (card.get_size(),))
        game.shot_saved_until = 0
        _save_card(game)   # headless → ข้าม clipboard จริง
        if getattr(game, "shot_saved_until", 0) <= pygame.time.get_ticks():
            errs.append("export_card action did not set confirmation")
    except Exception as ex:
        errs.append("export selftest: %s: %s" % (type(ex).__name__, ex))
    finally:
        for p in set(glob.glob(card_glob)) - pre:
            try:
                os.remove(p)
            except Exception:
                pass
        if own:
            pygame.quit()
    return errs


if __name__ == "__main__":
    import sys
    _e = selftest()
    print("EXPORT SELFTEST", "OK" if not _e else "FAIL")
    for _x in _e:
        print(" -", _x)
    sys.exit(1 if _e else 0)

