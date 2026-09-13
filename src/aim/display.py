# -*- coding: utf-8 -*-
"""[Module 2 + GPU phase 2] display + frame pacing + GPU world renderer — DisplayMixin

- GPU world (ดู aim/glrender.py): วาดฉาก 3D (sky/floor/walls/grid/pillars/sniper) บน GPU
  ส่วนเป้า/effects/HUD/เมนู วาด pygame บน overlay (SRCALPHA) แล้ว composite ทับด้วย alpha blend
- ถ้าไม่มี glrender/GL → phase-1 (อัปทั้งเฟรม) ; ไม่มี GL เลย → software เดิม (fallback ทุกชั้น)
- คงของ Module 2: clock-proxy frame cap, present() hook, ไม่ใช้ SCALED
- upload overlay = zero-copy ผ่าน get_buffer (surface เป็น RGBA ตรง byte order)
"""

import os
import sys
import array
import pygame

from . import registry
from .config import *
from .data import save_data

try:
    import moderngl as _mgl
except Exception:
    _mgl = None

try:
    from . import glrender as _glrender
    if _mgl is None:
        _glrender = None
except Exception:
    _glrender = None

FPS_CAP_CHOICES = [("60", 60), ("144", 144), ("240", 240), ("Unlimited", 0)]
_FPS_CAP_VALUES = frozenset(c[1] for c in FPS_CAP_CHOICES)   # get_frame_cap ถูกเรียกทุกเฟรม — ห้ามสร้าง genexp ซ้ำ
RENDER_SCALE_CHOICES = [("100%", 1.0), ("85%", 0.85), ("70%", 0.7), ("50%", 0.5)]
DEFAULT_FPS_CAP = 240
# escape hatch: ตั้ง VALAIM_FULL_UPLOAD=1 เพื่อปิด dirty-rect upload (กลับไปอัพโหลดเต็มเฟรมแบบเดิม)
# ใช้ debug ถ้าสงสัยว่ามีภาพค้าง (ghost) จาก draw site ที่ไม่ได้ mark_dirty
_FORCE_FULL_UPLOAD = os.environ.get("VALAIM_FULL_UPLOAD") == "1"
DEFAULT_VSYNC = True
DEFAULT_GPU = True
DEFAULT_RENDER_SCALE = 1.0
MIN_W, MIN_H = 900, 560
RGBA_MASKS = (0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000)

_QUAD_VS = """
#version 330
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main(){ v_uv = in_uv; gl_Position = vec4(in_pos, 0.0, 1.0); }
"""
_QUAD_FS = """
#version 330
uniform sampler2D tex;
uniform vec4 u_scope;      // cx, cy (px, top=0), r, on — สโคป Op: ทิ้ง overlay นอกวง (บอท/รอยกระสุน) ยกเว้นแถบ HUD
uniform vec2 u_band;       // y ล่างของแถบ HUD บน, y บนของแถบสถานะล่าง (px, top=0)
uniform float u_winh;
in vec2 v_uv;
out vec4 f_color;
void main(){
    if (u_scope.w > 0.5) {
        vec2 p = vec2(gl_FragCoord.x, u_winh - gl_FragCoord.y);
        if (distance(p, u_scope.xy) > u_scope.z && p.y > u_band.x && p.y < u_band.y) discard;
    }
    f_color = texture(tex, v_uv);
}
"""

_to_bytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring


class _PacedClock:
    __slots__ = ("_real", "_game")

    def __init__(self, real_clock, game):
        self._real = real_clock
        self._game = game

    def tick(self, _ignored=0):
        return self._real.tick(self._game.get_frame_cap())

    def tick_busy_loop(self, _ignored=0):
        return self._real.tick_busy_loop(self._game.get_frame_cap())

    def __getattr__(self, name):
        return getattr(self._real, name)


class DisplayMixin:
    def get_frame_cap(self):
        try:
            v = self.S.get("fps_cap", DEFAULT_FPS_CAP)
        except Exception:
            v = DEFAULT_FPS_CAP
        return v if v in _FPS_CAP_VALUES else DEFAULT_FPS_CAP

    @property
    def clock(self):
        return self._paced_clock

    @clock.setter
    def clock(self, real_clock):
        self._paced_clock = real_clock if isinstance(real_clock, _PacedClock) else _PacedClock(real_clock, self)

    def vsync_enabled(self):
        try:
            return bool(self.S.get("vsync", DEFAULT_VSYNC))
        except Exception:
            return DEFAULT_VSYNC

    def gpu_enabled(self):
        if self.headless or _mgl is None:
            return False
        try:
            return bool(self.S.get("gpu", DEFAULT_GPU))
        except Exception:
            return DEFAULT_GPU

    def gpu_world_active(self):
        """GPU วาดฉากจริง (มี glrender + สร้าง GLWorld สำเร็จ)"""
        return getattr(self, "gpu", False) and getattr(self, "_glr", None) is not None

    def render_scale(self):
        try:
            v = float(self.S.get("render_scale", DEFAULT_RENDER_SCALE))
        except Exception:
            v = DEFAULT_RENDER_SCALE
        return v if v in (c[1] for c in RENDER_SCALE_CHOICES) else DEFAULT_RENDER_SCALE

    def scale_mouse(self, pos):
        ww = getattr(self, "_win_w", 0)
        wh = getattr(self, "_win_h", 0)
        if not ww or not wh or (ww == self.W and wh == self.H):
            return pos
        return (pos[0] * self.W / ww, pos[1] * self.H / wh)

    def _warn_once(self, key, msg):
        seen = getattr(self, "_warned", None)
        if seen is None:
            seen = set(); self._warned = seen
        if key not in seen:
            seen.add(key)
            print(f"[VAL//AIM] {msg}", file=sys.stderr)

    # ───────── dirty-rect overlay upload (เฉพาะเฟรม play บน GPU world) ─────────
    # แนวคิด: ตอนเล่น overlay มีของแค่ ~10-25% ของจอ (HUD/เป้า/crosshair/effects)
    # แทนที่จะอัพโหลด texture เต็มจอ (~14MB ที่ 1440p) + เคลียร์เต็มจอ ทุกเฟรม
    # → อัพโหลด/เคลียร์เฉพาะสี่เหลี่ยมที่ถูกวาดจริง (เฟรมนี้ ∪ เฟรมก่อน กันภาพค้าง)
    # เปิดโดย worlddraw.draw_world เฉพาะ state play ปกติ; state อื่นทุกอันใช้เส้นทางอัพโหลดเต็มแบบเดิมเป๊ะ
    _DIRTY_MAX_RECTS = 24     # rect เยอะเกิน → อัพโหลดเต็มถูกกว่า (ค่า overhead ต่อ glTexSubImage2D)
    _DIRTY_MAX_AREA = 0.55    # พื้นที่รวมเกิน 55% ของจอ → อัพโหลดเต็มถูกกว่า (tobytes ต้อง copy ต่อ rect)

    def mark_dirty(self, r):
        """บันทึกพื้นที่ overlay ที่ถูกวาดเฟรมนี้ — no-op เมื่อไม่ได้ติดตาม (state อื่น/software/headless)"""
        if self._track_dirty and r.w > 0 and r.h > 0:
            # เก็บสำเนา — Game.text คืน rect ตัวเดียวกันให้ผู้เรียก ถ้าใคร mutate ทีหลังจะเลื่อนพื้นที่ track เพี้ยน
            self._dirty.append(pygame.Rect(r))

    def mark_full(self):
        """บังคับเฟรมนี้อัพโหลดเต็ม (เช่น effect เต็มจออย่าง dodge flash)"""
        self._track_dirty = False

    def _merge_dirty(self, rects):
        """clip เข้าจอ + รวม rect ที่ทับกัน (ทรานซิทีฟ); คืน None = เกินขีด ใช้อัพโหลดเต็มแทน"""
        merged = []
        if rects:
            bound = pygame.Rect(0, 0, self.W, self.H)
            for r in rects:
                r = r.clip(bound)
                if r.w <= 0 or r.h <= 0:
                    continue
                r = pygame.Rect(r)
                while True:
                    hit = r.collidelist(merged)
                    if hit < 0:
                        break
                    r.union_ip(merged.pop(hit))
                merged.append(r)
                if len(merged) > self._DIRTY_MAX_RECTS:
                    return None
            if sum(r.w * r.h for r in merged) > self._DIRTY_MAX_AREA * self.W * self.H:
                return None
        return merged

    def scrim(self, rgba):
        """surface สีทึบแสงเต็มจอจาก cache (คีย์ ขนาด+สี → resize แล้วสร้างใหม่เอง)
        แทนการ alloc+fill surface 14MB ใหม่ทุกเฟรมใน countdown/pause/resume_cd
        ห้ามผู้เรียกแก้ surface ที่คืนไป — ใช้ blit อย่างเดียว"""
        cache = getattr(self, "_scrim_cache", None)
        if cache is None:
            cache = {}
            self._scrim_cache = cache
        key = (self.W, self.H, rgba)
        s = cache.get(key)
        if s is None:
            if len(cache) > 6:
                # ทิ้งเฉพาะขนาดจอเก่า (หลัง resize) — คงชุดขนาดปัจจุบันไว้ ไม่ต้องสร้างใหม่
                for k in [k for k in cache if (k[0], k[1]) != (self.W, self.H)]:
                    del cache[k]
            s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            s.fill(rgba)
            cache[key] = s
        return s

    # ───────── GL setup ─────────
    def _init_gl(self, render_size, win_size):
        ctx = _mgl.create_context()
        ctx.blend_func = _mgl.SRC_ALPHA, _mgl.ONE_MINUS_SRC_ALPHA   # ค่าคงที่ — ไม่ต้องตั้งซ้ำทุกเฟรม
        prog = ctx.program(vertex_shader=_QUAD_VS, fragment_shader=_QUAD_FS)
        verts = array.array("f", [
            -1.0,  1.0, 0.0, 0.0,
             1.0,  1.0, 1.0, 0.0,
            -1.0, -1.0, 0.0, 1.0,
             1.0, -1.0, 1.0, 1.0,
        ])
        vbo = ctx.buffer(verts.tobytes())
        vao = ctx.vertex_array(prog, [(vbo, "2f 2f", "in_pos", "in_uv")])
        tex = ctx.texture(render_size, 4)
        tex.filter = (_mgl.LINEAR, _mgl.LINEAR)
        tex.swizzle = "RGBA"
        prog["tex"] = 0
        prog["u_scope"].value = (0.0, 0.0, 0.0, 0.0)
        prog["u_band"].value = (0.0, 0.0)
        prog["u_winh"].value = float(render_size[1])
        self._quad_scope_on = False
        ctx.viewport = (0, 0, win_size[0], win_size[1])
        self._gl = ctx
        self._gl_prog = prog
        self._gl_vbo = vbo
        self._gl_vao = vao
        self._gl_tex = tex
        # ตัววาดฉาก 3D บน GPU (ถ้ามี glrender)
        self._glr = None
        if _glrender is not None:
            try:
                self._glr = _glrender.GLWorld(ctx)
            except Exception as ex:
                self._warn_once("glworld_init", f"สร้าง GPU world ไม่ได้ ({ex}) — ใช้ upload ทั้งเฟรมแทน")
                self._glr = None

    def _teardown_gl(self):
        glr = getattr(self, "_glr", None)
        if glr is not None:
            try:
                glr.release()
            except Exception:
                pass
        self._glr = None
        for a in ("_gl_tex", "_gl_vao", "_gl_vbo", "_gl_prog", "_gl"):
            o = getattr(self, a, None)
            if o is not None:
                try:
                    o.release()
                except Exception:
                    pass
            setattr(self, a, None)

    def _gl_present(self):
        ctx = self._gl
        # ── เลือกเส้นทางอัพโหลด: dirty-rect (เฟรม play ที่ติดตามครบ) หรือเต็มเฟรม (ทุกกรณีอื่น) ──
        # _dirty_prev=None คือ sentinel "texture มีของเก่าที่ไม่รู้ขอบเขต" (เฟรมแรก/หลัง resize/หลัง state อื่น)
        # → ต้องอัพโหลดเต็มหนึ่งเฟรมก่อน แล้วค่อยเข้าโหมด dirty ได้
        track = self._track_dirty and not _FORCE_FULL_UPLOAD
        self.screen.set_clip(None)   # กัน clip ค้างจากผู้วาด (fill/subsurface ด้านล่างต้องเห็นทั้ง overlay ไม่งั้นภาพค้าง)
        cur = self._merge_dirty(self._dirty) if track else None
        rects = None
        if cur is not None and self._dirty_prev is not None:
            rects = self._merge_dirty(cur + self._dirty_prev)
        if rects is not None:
            # อัพโหลดเฉพาะบริเวณที่วาดเฟรมนี้ + บริเวณของเฟรมก่อน (ตอนนี้โปร่งใสแล้ว = ลบภาพเก่าใน texture)
            for r in rects:
                self._gl_tex.write(_to_bytes(self.screen.subsurface(r), "RGBA"),
                                   viewport=(r.x, r.y, r.w, r.h))
        elif getattr(self, "_screen_is_rgba", False):
            try:
                self._gl_tex.write(self.screen.get_buffer())
            except Exception:
                self._gl_tex.write(_to_bytes(self.screen, "RGBA"))
        else:
            self._gl_tex.write(_to_bytes(self.screen, "RGBA"))
        ctx.screen.use()
        if not getattr(self, "_world_gpu_frame", False):
            ctx.clear(0.0, 0.0, 0.0, 1.0)     # 2D state: ไม่มี world บน GPU → เคลียร์พื้น
        # post-effect บน GPU (เฉพาะเฟรมที่ world วาดบน GPU): สโคป Op = vignette "ก่อน" overlay + overlay ทิ้งพิกเซล
        # นอกวง (ยกเว้นแถบ HUD) ; แฟลชสี = tint "หลัง" overlay — แทน scrim 14MB บน CPU + อัพโหลดเต็มเฟรม
        glr = getattr(self, "_glr", None)
        fx = getattr(self, "_post_fx", None) if (glr is not None and getattr(self, "_world_gpu_frame", False)) else None
        scope = fx.get("scope") if fx else None
        try:
            if scope:
                glr.post(self, {"scope": scope})
                self._gl_prog["u_scope"].value = (float(scope[0]), float(scope[1]), float(scope[2]), 1.0)
                self._gl_prog["u_band"].value = (float(fx.get("band", (0, 0))[0]), float(fx.get("band", (0, 0))[1]))
                self._gl_prog["u_winh"].value = float(self.H)
                self._quad_scope_on = True
            elif getattr(self, "_quad_scope_on", False):
                self._gl_prog["u_scope"].value = (0.0, 0.0, 0.0, 0.0)
                self._quad_scope_on = False
        except Exception as ex:
            self._warn_once("glpost", f"GPU post-effect fail ({ex}) - overlay")
            self._glr_post_ok = False
        ctx.enable(_mgl.BLEND)                # blend_func คงที่ ตั้งครั้งเดียวใน _init_gl
        self._gl_tex.use(0)
        self._gl_vao.render(_mgl.TRIANGLE_STRIP)
        ctx.disable(_mgl.BLEND)
        if fx and fx.get("tint"):
            try:
                glr.post(self, {"tint": fx["tint"]})
            except Exception as ex:
                self._warn_once("glpost", f"GPU post-effect fail ({ex}) - overlay")
                self._glr_post_ok = False
        self._post_fx = None
        # สถิติสำหรับ perf HUD (S['fps']): เส้นทางอัพโหลด overlay ของเฟรมนี้
        if rects is not None:
            area = sum(r.w * r.h for r in rects)
            self._perf_path = f"GPU dirty {len(rects)}r {100.0 * area / (self.W * self.H):.0f}%"
        else:
            self._perf_path = "GPU full-upload" if getattr(self, "_world_gpu_frame", False) else "GPU full (2D)"
        pygame.display.flip()
        self._world_gpu_frame = False
        # เคลียร์ overlay ให้เฟรมถัดไปเริ่มสะอาด (กัน HUD/UI ซ้อน)
        # โหมด dirty: เคลียร์เฉพาะจุดที่วาดเฟรมนี้ก็พอ (จุดอื่นโปร่งใสอยู่แล้ว) — ประหยัด ~14MB memset/เฟรม
        if rects is not None:
            for r in cur:
                self.screen.fill((0, 0, 0, 0), r)
            self._dirty_prev = cur
        else:
            self.screen.fill((0, 0, 0, 0))
            # อัพโหลดเต็มไปแล้ว: ถ้าเฟรมนี้ติดตาม rect ครบ ใช้เป็นฐานของเฟรมถัดไปได้เลย
            self._dirty_prev = cur if track else None
        self._dirty = []
        self._track_dirty = False

    def gpu_post_available(self):
        """True = เฟรมนี้วาด world บน GPU และ post-effect shader ใช้ได้ → ผู้วาดข้าม scrim เต็มจอบน CPU ได้
        (เรียกจาก draw_gun_scope/แฟลช ระหว่างวาด overlay — หลัง draw_world ก่อน present)"""
        return (getattr(self, "_world_gpu_frame", False) and getattr(self, "_glr", None) is not None
                and getattr(self, "_glr_post_ok", True))

    def post_fx_add(self, tint=None, scope=None, band=None):
        """ขอ post-effect สำหรับเฟรมนี้ (ผสมกับที่ขอไว้ก่อนหน้าในเฟรมเดียวกัน)
        scope=(cx, cy, r_px) + band=(y_top_band_end, y_bottom_band_start): overlay นอกวงถูกทิ้ง ยกเว้นในแถบ HUD"""
        fx = getattr(self, "_post_fx", None) or {}
        if tint:
            fx["tint"] = tint
        if scope:
            fx["scope"] = scope
            fx["band"] = band or (0, 0)
        self._post_fx = fx

    def present(self):
        if getattr(self, "gpu", False):
            try:
                self._gl_present()
                return
            except Exception as ex:
                self._warn_once("present", f"GL present ล้มเหลว ({ex}) — สลับไป software")
                self._fallback_to_software()
        self._perf_path = "software"
        pygame.display.flip()
        self._dirty = []
        self._track_dirty = False

    def _fallback_to_software(self):
        self._teardown_gl()
        self._reset_dirty()
        self.gpu = False
        self.W, self.H = self._win_w, self._win_h
        try:
            self.screen = self._software_mode((self.W, self.H),
                                               pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE)
        except Exception:
            self.screen = pygame.display.set_mode((self.W, self.H))

    # ───────── window creation ─────────
    def _software_mode(self, size, base_flags):
        if self.vsync_enabled() and not self.headless:
            try:
                surf = pygame.display.set_mode(size, base_flags | pygame.DOUBLEBUF, vsync=1)
                self.vsync_active = True
                return surf
            except Exception as ex:
                self._warn_once("vsync", f"เปิด vsync ไม่ได้ ({ex}) — ใช้โหมดไม่มี vsync")
        surf = pygame.display.set_mode(size, base_flags)
        self.vsync_active = False
        return surf

    def _make_window(self, win_size, base_flags):
        self._teardown_gl()
        self._world_gpu_frame = False
        self._reset_dirty()
        if self.gpu_enabled():
            vs = 1 if (self.vsync_enabled() and not self.headless) else 0
            try:
                disp = pygame.display.set_mode(win_size, base_flags | pygame.OPENGL | pygame.DOUBLEBUF, vsync=vs)
                aw, ah = disp.get_size()          # ขนาด framebuffer จริง (fullscreen อาจต่างจากที่ขอ)
                self._win_w, self._win_h = aw, ah
                sc = 1.0 if _glrender is not None else self.render_scale()
                rsize = (max(2, int(round(aw * sc))), max(2, int(round(ah * sc))))
                self._init_gl(rsize, (aw, ah))
                self.W, self.H = rsize
                try:
                    self.screen = pygame.Surface(rsize, pygame.SRCALPHA, 32, RGBA_MASKS)
                    self._screen_is_rgba = True
                except Exception:
                    self.screen = pygame.Surface(rsize, pygame.SRCALPHA)
                    self._screen_is_rgba = False
                self.gpu = True
                self.vsync_active = bool(vs)
                return
            except Exception as ex:
                self._warn_once("gpu", f"เปิด GPU/OpenGL ไม่ได้ ({ex}) — ใช้ software แทน")
                self._teardown_gl()
        self.gpu = False
        surf = self._software_mode(win_size, base_flags)
        aw, ah = surf.get_size()
        self._win_w, self._win_h = aw, ah
        self.W, self.H = aw, ah
        self.screen = surf

    def default_window_size(self):
        if self.headless:
            return self.DEFAULT_W, self.DEFAULT_H
        try:
            info = pygame.display.Info()
            mw, mh = info.current_w, info.current_h
        except Exception:
            mw, mh = self.DEFAULT_W, self.DEFAULT_H
        w = min(self.DEFAULT_W, mw - 80)
        h = min(self.DEFAULT_H, mh - 120)
        return max(MIN_W, w), max(MIN_H, h)

    def _reset_dirty(self):
        """ล้างสถานะ dirty-rect — เรียกทุกครั้งที่ overlay/texture ถูกสร้างใหม่ (เนื้อหาเก่าเชื่อไม่ได้แล้ว)"""
        self._dirty = []
        self._dirty_prev = None
        self._track_dirty = False

    def init_display(self):
        self.fullscreen = False
        self.gpu = False
        self.vsync_active = False
        self._gl = None
        self._glr = None
        self._world_gpu_frame = False
        self._reset_dirty()
        win = self.default_window_size()
        self._make_window(win, pygame.RESIZABLE)
        pygame.display.set_caption("VAL//AIM — Aim Trainer")

    def _resize_gl_targets(self, w, h):
        """ปรับ texture/overlay/viewport เท่า framebuffer ใหม่ บน GL context เดิม (ไม่สร้าง context ใหม่ → กันจอค้าง)"""
        sc = 1.0 if _glrender is not None else self.render_scale()
        rsize = (max(2, int(round(w * sc))), max(2, int(round(h * sc))))
        self._win_w, self._win_h = w, h
        try:
            if getattr(self, "_gl_tex", None) is not None:
                self._gl_tex.release()
        except Exception:
            pass
        self._gl_tex = self._gl.texture(rsize, 4)
        self._gl_tex.filter = (_mgl.LINEAR, _mgl.LINEAR)
        self._gl_tex.swizzle = "RGBA"
        self._gl.viewport = (0, 0, w, h)
        self.W, self.H = rsize
        try:
            self.screen = pygame.Surface(rsize, pygame.SRCALPHA, 32, RGBA_MASKS)
            self._screen_is_rgba = True
        except Exception:
            self.screen = pygame.Surface(rsize, pygame.SRCALPHA)
            self._screen_is_rgba = False
        self._world_gpu_frame = False
        self._reset_dirty()

    def handle_resize(self, e):
        if self.fullscreen:
            return
        w, h = max(MIN_W, e.w), max(MIN_H, e.h)
        if getattr(self, "gpu", False) and getattr(self, "_gl", None) is not None:
            try:
                self._resize_gl_targets(w, h)   # ปรับบน context เดิม ไม่ set_mode ใหม่
            except Exception as ex:
                self._warn_once("resize", f"resize (GPU) fail ({ex})")
            return
        self._make_window((w, h), pygame.RESIZABLE)

    def _desktop_size(self):
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return sizes[0]
        except Exception:
            pass
        try:
            info = pygame.display.Info()
            return (info.current_w, info.current_h)
        except Exception:
            return self.default_window_size()

    def toggle_fullscreen(self):
        # GPU: สลับในที่ (pygame.display.toggle_fullscreen) — ไม่สร้าง GL context ใหม่ → ไม่ค้าง
        if getattr(self, "gpu", False) and getattr(self, "_gl", None) is not None:
            try:
                pygame.display.toggle_fullscreen()
                self.fullscreen = not self.fullscreen
                try:
                    nw, nh = pygame.display.get_window_size()
                except Exception:
                    nw, nh = self._win_w, self._win_h
                self._resize_gl_targets(nw, nh)
            except Exception as ex:
                self._warn_once("fs", f"toggle fullscreen (GPU) fail ({ex})")
            return
        # software / ไม่มี GL: set_mode เดิม
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self._make_window(self._desktop_size(), pygame.FULLSCREEN)
        else:
            self._make_window(self.default_window_size(), pygame.RESIZABLE)

    def apply_display_settings(self):
        win = (self._win_w, self._win_h)
        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        self._make_window(win, flags)


def _settings_panel(game, x, y, w):
    s = game.ui_scale()

    def S(v):
        return int(round(v * s))

    y0 = y
    game.text("FRAME PACING / GPU", S(13), C_RED, (x, y), bold=True)
    y += S(22)
    game.text("Frame Cap (FPS)", S(11), C_DIM, (x, y))
    y += S(18)
    gap = S(6)
    n = len(FPS_CAP_CHOICES)
    bw = (w - gap * (n - 1)) // n
    bh = S(26)
    cur = game.get_frame_cap()
    bx = x
    for label, val in FPS_CAP_CHOICES:
        def setcap(v=val):
            game.S["fps_cap"] = v
            save_data(game.data)
        game.button((bx, y, bw, bh), label, setcap, active=(val == cur), size=S(11))
        bx += bw + gap
    y += bh + S(10)

    von = game.vsync_enabled()

    def toggle_vsync():
        game.S["vsync"] = not von
        save_data(game.data)   # มีผลตอนเปิดเกมใหม่ (ไม่ rebuild สด กันจอเพี้ยน/ค้าง)

    vlbl = "VSync: ไม่รองรับ" if (von and not getattr(game, "vsync_active", False)) else ("VSync: เปิด" if von else "VSync: ปิด")
    game.button((x, y, S(150), bh), vlbl, toggle_vsync, active=von, size=S(11))

    def toggle_gpu():
        game.S["gpu"] = not bool(game.S.get("gpu", DEFAULT_GPU))
        save_data(game.data)   # มีผลตอนเปิดเกมใหม่

    if _mgl is None:
        glbl = "GPU: ไม่มี moderngl"
    elif bool(game.S.get("gpu", DEFAULT_GPU)) and not getattr(game, "gpu", False):
        glbl = "GPU: เปิดไม่ได้"
    elif game.gpu_world_active():
        glbl = "GPU: วาดฉากบน GPU"
    else:
        glbl = "GPU(present): เปิด" if getattr(game, "gpu", False) else "GPU: ปิด"
    game.button((x + S(160), y, S(180), bh), glbl, toggle_gpu, active=getattr(game, "gpu", False), size=S(11))
    y += bh + S(10)

    # render scale: ใช้เฉพาะตอน GPU present-only (ไม่มี glrender world)
    if getattr(game, "gpu", False) and not game.gpu_world_active():
        game.text("Render Scale (เร่ง FPS)", S(11), C_DIM, (x, y))
        y += S(18)
        cur_sc = game.render_scale()
        n2 = len(RENDER_SCALE_CHOICES)
        bw2 = (w - gap * (n2 - 1)) // n2
        bx = x
        for label, val in RENDER_SCALE_CHOICES:
            def setsc(v=val):
                game.S["render_scale"] = v
                save_data(game.data)   # มีผลตอนเปิดเกมใหม่
            game.button((bx, y, bw2, bh), label, setsc, active=(abs(val - cur_sc) < 1e-6), size=S(11))
            bx += bw2 + gap
        y += bh + S(6)
    else:
        y += S(2)

    game.text("* VSync / GPU / Render Scale มีผลตอนเปิดเกมใหม่", S(10), C_DIM, (x, y))
    y += S(16)
    return y - y0


if _settings_panel not in registry.SETTINGS_PANELS:
    registry.SETTINGS_PANELS.append(_settings_panel)
