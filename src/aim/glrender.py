# -*- coding: utf-8 -*-
"""[GPU phase 2] ตัววาดฉาก 3D บน GPU (moderngl) — เจ้าของไฟล์นี้คือสายงาน display/GPU

วาด "ฉากพื้นหลังก่อนเป้า" บน GPU: sky/floor (split ที่ horizon แบบเดียวกับ software เป๊ะ),
ผนังข้าง/ผนังหลัง+กริดขอบ, ตารางพื้น, เสา, กำแพง sniper, ฉาก arena, BEAM ของ dodge. ส่วน "เป้า/หัว/spray/dodge อื่น/flash/
crosshair/effects/HUD" ยังวาดด้วย pygame บน overlay surface (โปร่งใส) แล้ว composite ทับ
→ ของที่ซับซ้อน/ฟอนต์ไทยไม่ต้องแตะ, เป้าเดิม draw ทับฉากเสมอ (painter order ตรงกับ software)

การฉายตรงกับ aim/camera.py เป๊ะ: cam = view·p ; screen เท่ากับ project() เดิม
(พิสูจน์ใน selftest: view_matrix·[p,1] == cam.to_cam(p)). GPU clip ที่ระนาบ z=ZNEAR
(ค่าเดียวกับ worlddraw._clip_near ผ่าน uniform u_zn2) → กำแพงที่มีมุมหลังกล้อง
ถูกตัดถูกต้อง ไม่หาย และตัดที่ระยะเดียวกับ software ทุกพิกเซล

ปลอดภัย: ถ้าสร้าง/วาดพลาด ผู้เรียก (worlddraw/display) จับ exception แล้วตกกลับ software เดิม
"""

import math
import array

try:
    import moderngl as _mgl
except Exception:
    _mgl = None

from .config import (C_SKY, C_FLOOR, C_SIDEWALL, C_WALL, C_GRID, EYE_Y, WALL_Z, ROOM_X, ROOM_H,
                     SNIPER_WALL_Z, SNIPER_DOOR_L, SNIPER_DOOR_R, SNIPER_DOOR_H, ZNEAR,
                     DODGE_BEAM_Z, DODGE_BEAM_H, DODGE_AOE_POST_H)
from .gunplay import GUN_ORIGIN_Z, HOLD_WALL_DZ, HOLD_GAP, GUN_GRID_Z0
from .camera import focal_len
from .arena import FACES, FACE_COL, EDGE_COL


def _n(c):
    return (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)


def view_matrix(yaw, pitch, pos):
    """4x4 column-major (สำหรับ moderngl) ของการแปลง world→cam ให้ตรง camera.to_cam เป๊ะ
    R = Rpitch·Ryaw ; translation = -R·pos"""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    # R (row-major): ดู docstring — ตรงกับ to_cam (yaw แล้ว pitch)
    R = (
        (cy,        0.0,  -sy),
        (-sp * sy,  cp,   -sp * cy),
        (cp * sy,   sp,    cp * cy),
    )
    px, py, pz = pos
    tx = -(R[0][0] * px + R[0][1] * py + R[0][2] * pz)
    ty = -(R[1][0] * px + R[1][1] * py + R[1][2] * pz)
    tz = -(R[2][0] * px + R[2][1] * py + R[2][2] * pz)
    # column-major: [col0(x of each row)..., col3 = translation]
    return (
        R[0][0], R[1][0], R[2][0], 0.0,
        R[0][1], R[1][1], R[2][1], 0.0,
        R[0][2], R[1][2], R[2][2], 0.0,
        tx,      ty,      tz,      1.0,
    )


_BG_VS = """#version 330
in vec2 in_pos;
void main(){ gl_Position = vec4(in_pos, 0.0, 1.0); }
"""
_BG_FS = """#version 330
uniform vec3 u_sky;
uniform vec3 u_floor;
uniform float u_horizon;   // screen y (top=0) ที่เส้นขอบฟ้า
uniform float u_winh;      // ความสูง framebuffer (px)
out vec4 f_color;
void main(){
    float y = u_winh - gl_FragCoord.y;   // gl_FragCoord.y นับจากล่าง → กลับให้ top=0 เหมือน pygame
    f_color = vec4((y < u_horizon) ? u_sky : u_floor, 1.0);
}
"""

# post-effect เต็มจอบน GPU (วาดหลัง composite overlay): vignette สโคป Op + แฟลชสี (โดนยิง/สกิล)
# แทนการ blit surface 14MB บน CPU + อัพโหลดเต็มเฟรมทุกเฟรม — เดิมทำให้ GUNFIGHT/สโคป Op เฟรมตก
_POST_FS = """#version 330
uniform vec4 u_tint;       // สีแฟลชเต็มจอ (a = 0 → ไม่มี)
uniform vec4 u_scope;      // cx, cy (px, top=0), r (px), on (0/1)
uniform float u_winh;
out vec4 f_color;
void main(){
    vec4 c = u_tint;
    if (u_scope.w > 0.5) {
        vec2 p = vec2(gl_FragCoord.x, u_winh - gl_FragCoord.y);
        float d = distance(p, u_scope.xy);
        if (d > u_scope.z) {
            c = vec4(0.0, 0.0, 0.0, 0.92);               // นอกวง: มืด 235/255 เท่า software
        } else if (d > u_scope.z - 3.0) {
            c = vec4(0.04, 0.04, 0.04, 1.0);             // ขอบวง 3px
        }
    }
    f_color = c;
}
"""

_GEO_VS = """#version 330
uniform mat4 u_view;
uniform float u_fx;   // 2f/W
uniform float u_fy;   // 2f/H
uniform float u_zn2;  // 2*ZNEAR
in vec3 in_pos;
void main(){
    vec3 c = (u_view * vec4(in_pos, 1.0)).xyz;   // cam space
    // w=z → perspective ; z_c = z-2*ZNEAR ทำให้เงื่อนไข clip (z_c >= -w) กลายเป็น z >= ZNEAR
    // ตรงกับ software (_clip_near) — depth test ปิดอยู่ ค่า depth จึงไม่มีผลต่อลำดับวาด
    gl_Position = vec4(c.x * u_fx, c.y * u_fy, c.z - u_zn2, c.z);
}
"""
_GEO_FS = """#version 330
uniform vec3 u_col;
out vec4 f_color;
void main(){ f_color = vec4(u_col, 1.0); }
"""


class GLWorld:
    """สร้างจาก moderngl context (อันเดียวกับที่ display ใช้ present)

    geometry ทั้งฉากเป็น static ใน world space (view transform อยู่ใน shader) — สร้าง VBO
    เดียวครั้งเดียวตอน init เรียงตามลำดับ painter เดิมเป๊ะ แล้วต่อเฟรมแค่ตั้ง uniform +
    สั่ง render ตาม segment ที่ active (เสา/กำแพง sniper เลือกจาก offset ไม่ต้อง rebuild)
    เดิม rebuild vertex ใน Python + orphan/write VBO 5-13 ครั้งทุกเฟรม (~0.1-0.25ms ฟรี ๆ)"""
    def __init__(self, ctx):
        self.ctx = ctx
        self.bg_prog = ctx.program(vertex_shader=_BG_VS, fragment_shader=_BG_FS)
        quad = array.array("f", [-1, -1, 1, -1, -1, 1, 1, 1])
        self.bg_vbo = ctx.buffer(quad.tobytes())
        self.bg_vao = ctx.vertex_array(self.bg_prog, [(self.bg_vbo, "2f", "in_pos")])
        self.post_prog = ctx.program(vertex_shader=_BG_VS, fragment_shader=_POST_FS)
        self.post_vao = ctx.vertex_array(self.post_prog, [(self.bg_vbo, "2f", "in_pos")])
        self.geo_prog = ctx.program(vertex_shader=_GEO_VS, fragment_shader=_GEO_FS)
        self.geo_prog["u_zn2"].value = 2.0 * ZNEAR

        # ── สร้าง vertex stream ครั้งเดียว — ค่า/ลำดับชุดเดียวกับที่เคยสร้างต่อเฟรมทุกประการ ──
        data = array.array("f")
        segs = {}

        def _seg(name, verts, mode):
            first = len(data) // 3
            for v in verts:
                data.extend(v)
            segs[name] = (first, len(verts), mode)

        def _quad(p0, p1, p2, p3):
            return [p0, p1, p2, p0, p2, p3]

        def _lines(pairs):
            out = []
            for a, b in pairs:
                out.append(a)
                out.append(b)
            return out

        # ผนังข้าง (ซ้าย+ขวา สีเดียว ติดกัน — รวม segment เดียว ผลพิกเซลเท่าเดิมเพราะปิด blend/depth)
        _seg("side",
             _quad((-ROOM_X, 0, 2), (-ROOM_X, 0, WALL_Z), (-ROOM_X, ROOM_H, WALL_Z), (-ROOM_X, ROOM_H, 2)) +
             _quad((ROOM_X, 0, 2), (ROOM_X, 0, WALL_Z), (ROOM_X, ROOM_H, WALL_Z), (ROOM_X, ROOM_H, 2)),
             _mgl.TRIANGLES)
        # ผนังหลัง + กริดขอบ
        bw = [(-ROOM_X, 0, WALL_Z), (ROOM_X, 0, WALL_Z), (ROOM_X, ROOM_H, WALL_Z), (-ROOM_X, ROOM_H, WALL_Z)]
        _seg("back", _quad(bw[0], bw[1], bw[2], bw[3]), _mgl.TRIANGLES)
        _seg("border", _lines([(bw[0], bw[1]), (bw[1], bw[2]), (bw[2], bw[3]), (bw[3], bw[0])]), _mgl.LINES)
        # ตารางพื้น
        gsegs = []
        for gx in range(-10, 11, 2):
            gsegs.append(((gx, 0, 2), (gx, 0, WALL_Z)))
        for gz in range(2, int(WALL_Z) + 1, 2):
            gsegs.append(((-10, 0, gz), (10, 0, gz)))
        _seg("grid", _lines(gsegs), _mgl.LINES)
        # เสา (วาดเฉพาะเมื่อ S['pillars'] เปิด — เลือกตอน render)
        pil = []
        for px, pz in ((-7, 11), (7, 11), (-7, 4), (7, 4)):
            pil += _quad((px - 0.3, 0, pz), (px + 0.3, 0, pz), (px + 0.3, ROOM_H, pz), (px - 0.3, ROOM_H, pz))
        _seg("pillars", pil, _mgl.TRIANGLES)
        # กำแพง sniper + ประตู (เฉพาะโหมด sniper — เลือกตอน render)
        wz = SNIPER_WALL_Z
        _seg("sniper",
             _quad((-ROOM_X, 0, wz), (SNIPER_DOOR_L, 0, wz), (SNIPER_DOOR_L, ROOM_H, wz), (-ROOM_X, ROOM_H, wz)) +
             _quad((SNIPER_DOOR_R, 0, wz), (ROOM_X, 0, wz), (ROOM_X, ROOM_H, wz), (SNIPER_DOOR_R, ROOM_H, wz)) +
             _quad((SNIPER_DOOR_L, SNIPER_DOOR_H, wz), (SNIPER_DOOR_R, SNIPER_DOOR_H, wz),
                   (SNIPER_DOOR_R, ROOM_H, wz), (SNIPER_DOOR_L, ROOM_H, wz)),
             _mgl.TRIANGLES)
        door = [(SNIPER_DOOR_L, 0, wz), (SNIPER_DOOR_R, 0, wz), (SNIPER_DOOR_R, SNIPER_DOOR_H, wz),
                (SNIPER_DOOR_L, SNIPER_DOOR_H, wz)]
        _seg("door", _lines([(door[0], door[1]), (door[1], door[2]), (door[2], door[3]), (door[3], door[0])]),
             _mgl.LINES)

        # GUNFIGHT: ตารางพื้นส่วนขยาย (z -22..2) + กำแพง hold — static เหมือนกัน (จุดเริ่มผู้เล่นคงที่ GUN_ORIGIN_Z)
        # เดิมวาดบน overlay ทุกเฟรม: bbox ของเส้นเฉียงยาว/กำแพงเต็มจอ ทำ dirty area >55% → อัพโหลดเต็มทุกเฟรม
        gg = []
        for gz in range(GUN_GRID_Z0, 3, 2):
            gg.append(((-10, 0, gz), (10, 0, gz)))
        for gx in range(-10, 11, 2):
            gg.append(((gx, 0, GUN_GRID_Z0), (gx, 0, 2)))
        _seg("gungrid", _lines(gg), _mgl.LINES)
        hz = GUN_ORIGIN_Z + HOLD_WALL_DZ
        hg = HOLD_GAP
        _seg("holdwall",
             _quad((-ROOM_X, 0, hz), (-hg, 0, hz), (-hg, ROOM_H, hz), (-ROOM_X, ROOM_H, hz)) +
             _quad((hg, 0, hz), (ROOM_X, 0, hz), (ROOM_X, ROOM_H, hz), (hg, ROOM_H, hz)),
             _mgl.TRIANGLES)
        hd = [(-hg, 0, hz), (hg, 0, hz), (hg, ROOM_H, hz), (-hg, ROOM_H, hz)]
        _seg("holdgap", _lines([(hd[0], hd[1]), (hd[1], hd[2]), (hd[2], hd[3]), (hd[3], hd[0])]), _mgl.LINES)

        # DODGE BEAM (ตำแหน่ง x ขยับทุกเฟรม): สร้างที่ x = 0 ครั้งเดียว แล้วเลื่อนต่อลำแสงผ่าน u_view (_draw_beams)
        # รูปร่าง/ลำดับเดียวกับ software (worlddraw.draw_dodge_world): รั้วเส้นหยุด → ขอบกำแพงลำแสง → แถบระดับตา + แถบล่าง
        # เดิมวาดบน overlay: กรอบ dirty ของกำแพงยาว z −2.6..7 กินครึ่งจอ → อัพโหลด overlay เกือบเต็มทุกเฟรมที่มีลำแสง
        bz0, bz1 = DODGE_BEAM_Z

        def _wall(y0, y1):
            return [(0.0, y0, bz0), (0.0, y0, bz1), (0.0, y1, bz1), (0.0, y1, bz0)]

        def _edges(q):
            return _lines([(q[0], q[1]), (q[1], q[2]), (q[2], q[3]), (q[3], q[0])])
        _seg("beamfence", _edges(_wall(0.02, DODGE_AOE_POST_H)), _mgl.LINES)
        _seg("beamwall", _edges(_wall(0.02, DODGE_BEAM_H)), _mgl.LINES)
        strips = []
        for hy in (EYE_Y, DODGE_BEAM_H * 0.35):
            q = _wall(hy - 0.03, hy + 0.03)
            strips += _quad(q[0], q[1], q[2], q[3])
        _seg("beamstrips", strips, _mgl.TRIANGLES)

        self.geo_vbo = ctx.buffer(data.tobytes())   # static — ไม่มีการเขียนทับอีก
        self.geo_vao = ctx.vertex_array(self.geo_prog, [(self.geo_vbo, "3f", "in_pos")])
        self._segs = segs
        self._col = {"side": _n(C_SIDEWALL), "back": _n(C_WALL), "grid": _n(C_GRID),
                     "pillars": _n((31, 46, 61)), "sniper": _n((32, 45, 61)), "door": _n((58, 77, 101)),
                     "holdwall": _n((30, 42, 58)), "holdgap": _n((58, 77, 101))}
        # uniform คงที่ตั้งครั้งเดียว; ที่ผูกกับขนาด framebuffer ตั้งใหม่เมื่อ (W,H) เปลี่ยน (resize/F11)
        self.bg_prog["u_sky"].value = _n(C_SKY)
        self.bg_prog["u_floor"].value = _n(C_FLOOR)
        self._last_wh = None
        # ที่กำบังของดวล GUNFIGHT (gunbots — มุมกำแพงเปลี่ยนทุกดวล): VBO แยก สร้างใหม่เฉพาะตอนชุดกล่องเปลี่ยน
        # (game.gun_cover_ver) ต่อเฟรมแค่เลือกหน้าที่หันหาตา + ลำดับไกล→ใกล้ แบบเดียวกับ segment static ด้านบน
        self.cover_vbo = None
        self.cover_vao = None
        self._cover_key = None
        self._cover_segs = []
        self._face_col = {k: _n(v) for k, v in FACE_COL.items()}
        self._edge_col = _n(EDGE_COL)

    def release(self):
        for o in (self.bg_vao, self.bg_vbo, self.bg_prog, self.geo_vao, self.geo_vbo, self.geo_prog,
                  self.post_vao, self.post_prog, self.cover_vao, self.cover_vbo):
            try:
                if o is not None:
                    o.release()
            except Exception:
                pass

    def _build_covers(self, boxes, key):
        """สร้าง VBO ของกล่องชุดใหม่: ต่อหน้า = สามเหลี่ยม 6 จุด + ขอบ 8 จุด (LINES) — เรียกเมื่อ key เปลี่ยนเท่านั้น"""
        for o in (self.cover_vao, self.cover_vbo):
            if o is not None:
                o.release()
        self.cover_vao = self.cover_vbo = None
        data = array.array("f")
        segs = []
        for bx in boxes:
            faces = {}
            for name, _a, _s in FACES:
                p = bx.face_pts(name)
                tri = len(data) // 3
                for v in (p[0], p[1], p[2], p[0], p[2], p[3]):
                    data.extend(v)
                edge = len(data) // 3
                for i in range(4):
                    data.extend(p[i])
                    data.extend(p[(i + 1) % 4])
                faces[name] = (tri, edge)
            segs.append((bx, faces))
        if data:
            self.cover_vbo = self.ctx.buffer(data.tobytes())
            self.cover_vao = self.ctx.vertex_array(self.geo_prog, [(self.cover_vbo, "3f", "in_pos")])
        self._cover_segs = segs
        self._cover_key = key

    def _draw_covers(self, game):
        boxes = [b for b in getattr(game, "gun_covers", ()) if b.draw]
        key = getattr(game, "gun_cover_ver", 0) if boxes else 0
        if key != self._cover_key:
            self._build_covers(boxes, key)
        if self.cover_vao is None:
            return
        eye = (game.cam.pos[0], game.cam.pos[1], game.cam.pos[2])
        for bx, faces in sorted(self._cover_segs, key=lambda s: -s[0].dist2(eye)):
            for name in bx.visible_faces(eye):
                tri, edge = faces[name]
                self.geo_prog["u_col"].value = self._face_col[name]
                self.cover_vao.render(_mgl.TRIANGLES, vertices=6, first=tri)
                self.ctx.line_width = 2.0       # ขอบ 2px เท่า software (draw_cover_box)
                self.geo_prog["u_col"].value = self._edge_col
                self.cover_vao.render(_mgl.LINES, vertices=8, first=edge)
                self.ctx.line_width = 1.0

    def post(self, game, fx):
        """วาด post-effect ทับทุกอย่าง (เรียกจาก display._gl_present หลัง composite overlay)
        fx = game.post_fx(): {"tint": (r,g,b,a) 0-255 หรือ None, "scope": (cx, cy, r_px) หรือ None}"""
        tint = fx.get("tint")
        scope = fx.get("scope")
        if not tint and not scope:
            return
        ctx = self.ctx
        self.post_prog["u_winh"].value = float(game.H)
        if tint:
            self.post_prog["u_tint"].value = (tint[0] / 255.0, tint[1] / 255.0, tint[2] / 255.0, tint[3] / 255.0)
        else:
            self.post_prog["u_tint"].value = (0.0, 0.0, 0.0, 0.0)
        if scope:
            self.post_prog["u_scope"].value = (float(scope[0]), float(scope[1]), float(scope[2]), 1.0)
        else:
            self.post_prog["u_scope"].value = (0.0, 0.0, 0.0, 0.0)
        ctx.enable(_mgl.BLEND)
        self.post_vao.render(_mgl.TRIANGLE_STRIP)
        ctx.disable(_mgl.BLEND)

    def _draw_beams(self, game, beams):
        """DODGE BEAM (game.dodge_beams(): [(beam_x, stop_x, สี)]) — segment beam* อยู่ที่ x = 0 → ต่อชิ้นตั้ง u_view เป็น
        view ของกล้องที่เลื่อน −x (view·T(x)·p = view ของกล้องที่ pos.x − x) ; เส้นหนาเท่า software (รั้ว 2 px, ขอบลำแสง 3 px)
        แถบระดับตา/แถบล่างเป็นสามเหลี่ยม — ยังเห็นชัดแม้ไดรเวอร์ที่บีบ line width เหลือ 1 px ; คืน u_view ของกล้องตอนจบ"""
        cam = game.cam
        ctx = self.ctx
        px, py, pz = cam.pos
        fence = _n((255, 170, 0))
        for bx, sx, col in beams:
            self.geo_prog["u_view"].value = view_matrix(cam.yaw, cam.pitch, (px - sx, py, pz))
            ctx.line_width = 2.0
            self._seg_draw("beamfence", fence)
            c = _n(col)
            self.geo_prog["u_view"].value = view_matrix(cam.yaw, cam.pitch, (px - bx, py, pz))
            ctx.line_width = 3.0
            self._seg_draw("beamwall", c)
            ctx.line_width = 1.0
            self._seg_draw("beamstrips", c)
        self.geo_prog["u_view"].value = view_matrix(cam.yaw, cam.pitch, cam.pos)

    def _seg_draw(self, name, col):
        first, count, mode = self._segs[name]
        self.geo_prog["u_col"].value = col
        self.geo_vao.render(mode, vertices=count, first=first)

    def render(self, game):
        ctx = self.ctx
        W, H = game.W, game.H
        f = game.fl()          # รวม zoom ของ GUNFIGHT — ต้องเท่ากับ overlay (worlddraw) เป๊ะ
        cam = game.cam
        # ── พื้นหลัง sky/floor (ตรง software: split ที่ horizon) ──
        horizon = H / 2 + f * math.tan(cam.pitch) - f * (cam.pos[1] - EYE_Y) / 14
        ctx.disable(_mgl.DEPTH_TEST)
        ctx.disable(_mgl.BLEND)
        if (W, H, f) != self._last_wh:
            self._last_wh = (W, H, f)
            self.bg_prog["u_winh"].value = float(H)
            self.geo_prog["u_fx"].value = 2.0 * f / W
            self.geo_prog["u_fy"].value = 2.0 * f / H
        self.bg_prog["u_horizon"].value = float(horizon)
        self.bg_vao.render(_mgl.TRIANGLE_STRIP)
        # ── เรขาคณิต (ลำดับ painter เหมือน software เป๊ะ — segment เรียงตามลำดับวาดเดิม) ──
        self.geo_prog["u_view"].value = view_matrix(cam.yaw, cam.pitch, cam.pos)
        col = self._col
        self._seg_draw("side", col["side"])
        self._seg_draw("back", col["back"])
        # ขอบหนา 2px ให้ตรง software (worlddraw ใช้ width=2) — glLineWidth>1 บน core profile
        # ขึ้นกับไดรเวอร์: NVIDIA เครื่องนี้รองรับ (ALIASED_LINE_WIDTH_RANGE 1..10, ตรวจแล้ว),
        # ไดรเวอร์ที่เข้มกว่าจะ clamp เหลือ 1px เอง (= พฤติกรรมเดิม ไม่มี error)
        ctx.line_width = 2.0
        self._seg_draw("border", col["grid"])
        ctx.line_width = 1.0
        self._seg_draw("grid", col["grid"])
        if game.S.get("pillars"):
            self._seg_draw("pillars", col["pillars"])
        if game.mode == "sniper" and game.state in ("play", "countdown", "pause"):
            self._seg_draw("sniper", col["sniper"])
            ctx.line_width = 2.0   # ขอบประตู 2px เท่า software
            self._seg_draw("door", col["door"])
            ctx.line_width = 1.0
        # ฉาก arena (พื้นขยาย + กล่อง) : GUNFIGHT ทุกดริล และ reaction·peek (game.arena_on — reactpeek.py)
        arena_on = game.mode == "gun" or (hasattr(game, "rpeek_on") and game.rpeek_on())
        if arena_on and game.state in ("play", "countdown", "pause"):
            self._seg_draw("gungrid", col["grid"])
            if game.mode == "gun" and getattr(game, "gun_drill", "") == "hold":
                self._seg_draw("holdwall", col["holdwall"])
                ctx.line_width = 2.0
                self._seg_draw("holdgap", col["holdgap"])
                ctx.line_width = 1.0
            self._draw_covers(game)
        # DODGE BEAM บนฉาก (ใต้ overlay เป้า/HUD) — worlddraw ข้าม BEAM บน overlay เมื่อเฟรมนี้ world อยู่บน GPU
        if game.mode == "dodge":
            beams = game.dodge_beams()
            if beams:
                self._draw_beams(game, beams)
