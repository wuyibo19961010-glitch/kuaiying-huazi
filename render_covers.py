#!/usr/bin/env python3
# coding=utf-8
"""
render_covers.py v2 — 精确颜色 + 正确阴影偏移

改进:
1. 颜色全部从设计稿提取，不再猜测
2. 阴影偏移 shift.x/y 正确实现立体感
3. 发光层的 shift 偏移正确应用
4. 3D thickness 方向正确
"""

import os, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.join(HERE, "花字输出结果")


def _find_font() -> str:
    """每次调用时实时定位字体，兼容开发目录和发布包目录"""
    base = os.path.dirname(os.path.abspath(__file__))
    # 优先同级目录
    p = os.path.join(base, "字体资源", "标准字体.ttf")
    if os.path.exists(p):
        return p
    # 兼容开发目录：上一级
    p2 = os.path.join(os.path.dirname(base), "字体资源", "标准字体.ttf")
    if os.path.exists(p2):
        return p2
    return p  # 找不到时返回同级路径，让 Pillow 给出明确报错

W = H = 300
BG = (26, 26, 26)
TEXT = "花字"
FONT_SIZE = 104  # 匹配标准封面


def fnt(sz):
    return ImageFont.truetype(_find_font(), sz)


def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 8:
        h = h[2:]
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def centered_xy(draw, text, f):
    bb = draw.textbbox((0, 0), text, font=f)
    return (W - (bb[2] - bb[0])) // 2 - bb[0], (H - (bb[3] - bb[1])) // 2 - bb[1]


def make_gradient(colors_anchors, degree, size=(W, H)):
    """生成线性渐变图像"""
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    is_vertical = abs(degree - 90) < 45 or abs(degree + 90) < 45

    for i in range(size[1] if is_vertical else size[0]):
        t = i / (size[1] if is_vertical else size[0])
        c = interpolate_color(colors_anchors, t)
        if is_vertical:
            arr[i, :] = c
        else:
            arr[:, i] = c

    return Image.fromarray(arr)


def interpolate_color(colors_anchors, t):
    if not colors_anchors:
        return (255, 255, 255)
    for i in range(len(colors_anchors) - 1):
        a1, c1 = colors_anchors[i]
        a2, c2 = colors_anchors[i + 1]
        if a1 <= t <= a2:
            local_t = (t - a1) / (a2 - a1) if a2 != a1 else 0
            return tuple(int(c1[j] * (1 - local_t) + c2[j] * local_t) for j in range(3))
    if t <= colors_anchors[0][0]:
        return colors_anchors[0][1]
    return colors_anchors[-1][1]


def text_mask(text, f, size=(W, H), offset=(0, 0)):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    bb = d.textbbox((0, 0), text, font=f)
    x = (size[0] - (bb[2] - bb[0])) // 2 - bb[0] + offset[0]
    y = (size[1] - (bb[3] - bb[1])) // 2 - bb[1] + offset[1]
    d.text((x, y), text, font=f, fill=255)
    return m, x, y


def render_cover(info, output_path, text_str=None):
    global TEXT
    if text_str:
        TEXT = text_str
    f = fnt(FONT_SIZE)
    img = Image.new("RGBA", (W, H), (*BG, 255))
    d_tmp = ImageDraw.Draw(img)
    cx, cy = centered_xy(d_tmp, TEXT, f)

    text_color = hex_to_rgb(info.get('text_color', '#ffffff'))
    thickness = info.get('thickness', 0)
    strokes = info.get('stroke') or []
    shadows = info.get('shadows') or []
    inner_shadows = info.get('innerShadows') or []
    multi_layers = info.get('multi_text_layer') or []
    gradient_idx = info.get('gradientIndex', -1)
    gradient_degree = info.get('gradientDegree', 90)
    color_gradients = info.get('colorgradient') or []

    def parse_gradient(gi):
        if gi < 0 or gi >= len(color_gradients):
            return None
        lg = color_gradients[gi].get('lineargradient', [])
        return [(p['anchor'], hex_to_rgb(p['color'])) for p in lg]

    # ── 1. 外发光 (shadows with shift) ──
    for shadow in shadows:
        s_color = hex_to_rgb(shadow.get('color', '#ffffff'))
        intensity = shadow.get('intensity', 0.5)
        shift = shadow.get('shift', {})
        sx = float(shift.get('x', 0)) if isinstance(shift, dict) else 0
        sy = float(shift.get('y', 0)) if isinstance(shift, dict) else 0
        s_alpha = shadow.get('alpha', 255)

        # 发光半径与 intensity 成正比
        blur_radius = max(2, int(intensity * 35))
        expand = max(1, int(intensity * 10))

        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        # 应用 shift 偏移
        gx = cx + int(sx * FONT_SIZE / 160)
        gy = cy + int(sy * FONT_SIZE / 160)
        gd.text((gx, gy), TEXT, font=f, fill=(*s_color, s_alpha),
                stroke_width=expand, stroke_fill=(*s_color, s_alpha))

        glow = glow.filter(ImageFilter.GaussianBlur(blur_radius))
        img = Image.alpha_composite(img, glow)

    # ── 2. multi_text_layer (偏移文字层) ──
    for ml in multi_layers:
        ml_color = hex_to_rgb(ml.get('color', '#000000'))
        ml_alpha = ml.get('alpha', 255)
        ox = float(ml.get('offset_x', 0))
        oy = float(ml.get('offset_y', 0))
        ml_gi = ml.get('gradientIndex', -1)

        # 缩放偏移到当前字号
        scale = FONT_SIZE / 160
        pox = int(ox * scale)
        poy = int(oy * scale)

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        lx = cx + pox
        ly = cy + poy

        # 偏移层也画描边
        for s in reversed(strokes):
            sw = max(1, int(s.get('width', 0) * scale))
            sc = hex_to_rgb(s.get('color', '#000000'))
            sa = s.get('alpha', 255)
            ld.text((lx, ly), TEXT, font=f,
                    fill=(0, 0, 0, 0), stroke_width=sw, stroke_fill=(*sc, sa))

        # 渐变或纯色填充
        if ml_gi >= 0:
            grad_colors = parse_gradient(ml_gi)
            if grad_colors:
                grad_img = make_gradient(grad_colors, gradient_degree)
                mask, _, _ = text_mask(TEXT, f, offset=(pox, poy))
                grad_rgba = grad_img.convert("RGBA")
                grad_arr = np.array(grad_rgba)
                grad_arr[:, :, 3] = np.array(mask)
                grad_layer = Image.fromarray(grad_arr)
                layer = Image.alpha_composite(layer, grad_layer)
        else:
            ld.text((lx, ly), TEXT, font=f, fill=(*ml_color, ml_alpha))

        img = Image.alpha_composite(img, layer)

    # ── 3. 3D厚度侧面（在主体之前画） ──
    if thickness > 0.01:
        depth = max(1, int(thickness * 5 * FONT_SIZE / 160))
        for d in range(depth, 0, -1):
            side = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sd_draw = ImageDraw.Draw(side)
            darken = 0.35 + 0.25 * (d / depth)
            side_color = tuple(int(c * darken) for c in text_color)

            # 描边侧面
            for s in reversed(strokes):
                sw = max(1, int(s.get('width', 0) * FONT_SIZE / 160))
                sc = hex_to_rgb(s.get('color', '#ffffff'))
                sc_dark = tuple(int(c * darken) for c in sc)
                sd_draw.text((cx, cy + d), TEXT, font=f,
                             fill=(0, 0, 0, 0), stroke_width=sw,
                             stroke_fill=(*sc_dark, 255))

            sd_draw.text((cx, cy + d), TEXT, font=f, fill=(*side_color, 255))
            img = Image.alpha_composite(img, side)

    # ── 4. 描边（从外到内渲染） ──
    scale = FONT_SIZE / 160
    for s in reversed(strokes):
        sw = max(1, int(s.get('width', 0) * scale))
        sc = hex_to_rgb(s.get('color', '#ffffff'))
        sa = s.get('alpha', 255)

        stroke_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd_draw = ImageDraw.Draw(stroke_layer)
        sd_draw.text((cx, cy), TEXT, font=f,
                     fill=(0, 0, 0, 0), stroke_width=sw, stroke_fill=(*sc, sa))

        img = Image.alpha_composite(img, stroke_layer)

    # ── 5. 文字主体 ──
    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    if gradient_idx >= 0:
        grad_colors = parse_gradient(gradient_idx)
        if grad_colors:
            grad_img = make_gradient(grad_colors, gradient_degree)
            mask, _, _ = text_mask(TEXT, f)
            grad_rgba = grad_img.convert("RGBA")
            grad_arr = np.array(grad_rgba)
            grad_arr[:, :, 3] = np.array(mask)
            text_layer = Image.fromarray(grad_arr)
    else:
        td = ImageDraw.Draw(text_layer)
        td.text((cx, cy), TEXT, font=f, fill=(*text_color, 255))

    img = Image.alpha_composite(img, text_layer)

    # ── 6. 内阴影（精确偏移） ──
    for ishadow in inner_shadows:
        is_color = hex_to_rgb(ishadow.get('color', '#000000'))
        is_intensity = ishadow.get('intensity', 1.0)
        is_shift = ishadow.get('shift', {})
        is_sx = float(is_shift.get('x', 0)) if isinstance(is_shift, dict) else 0
        is_sy = float(is_shift.get('y', 0)) if isinstance(is_shift, dict) else 0

        # 缩放 shift 到当前字号
        psx = int(is_sx * scale)
        psy = int(is_sy * scale)

        mask_orig, _, _ = text_mask(TEXT, f)
        mask_shifted, _, _ = text_mask(TEXT, f, offset=(psx, psy))

        orig_arr = np.array(mask_orig).astype(float)
        shifted_arr = np.array(mask_shifted).astype(float)
        shadow_arr = np.clip(orig_arr - shifted_arr, 0, 255)

        blur = max(1, int(is_intensity * 1.5))
        shadow_mask = Image.fromarray(shadow_arr.astype(np.uint8))
        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur))

        alpha_factor = min(1.0, is_intensity / 5.0)
        shadow_mask_arr = np.array(shadow_mask).astype(float) * alpha_factor
        shadow_mask = Image.fromarray(shadow_mask_arr.clip(0, 255).astype(np.uint8))

        inner_layer = Image.new("RGBA", (W, H), (*is_color, 0))
        inner_arr = np.array(inner_layer)
        inner_arr[:, :, 3] = np.array(shadow_mask)
        inner_layer = Image.fromarray(inner_arr)

        img = Image.alpha_composite(img, inner_layer)

    # 保存（支持文件路径或 BytesIO）
    final = img.convert("RGB")
    if hasattr(output_path, 'write'):
        final.save(output_path, "PNG")
    else:
        final.save(output_path, "WEBP", quality=92)


def main():
    for name in sorted(os.listdir(PKG_DIR)):
        sub = os.path.join(PKG_DIR, name)
        if not os.path.isdir(sub):
            continue
        info_path = os.path.join(sub, "info.json")
        if not os.path.exists(info_path):
            continue

        with open(info_path, encoding='utf-8') as fp:
            info = json.load(fp)

        cover_path = os.path.join(sub, f"{name}.webp")
        try:
            render_cover(info, cover_path)
            # 同时生成 PNG 预览
            Image.open(cover_path).save(
                os.path.join(sub, f"{name}_preview.png"), "PNG")
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n封面渲染完成 → {PKG_DIR}")


if __name__ == "__main__":
    main()
