#!/usr/bin/env python3
# coding=utf-8
"""
name_gen.py — 根据花字 info.json 参数自动生成四字中文命名

命名规则:
  字1: 主色调 (基于 text_color 或渐变主色)
  字2: 风格关键词 (基于描边层数/thickness/shadows)
  字3+4: 效果特征词 (基于发光/偏移/渐变方向等)
"""

import math


def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 8:
        h = h[2:]
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def color_hue(c):
    """返回色相 0~360"""
    r, g, b = c[0]/255, c[1]/255, c[2]/255
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0
    d = mx - mn
    if mx == r:
        h = (g - b) / d % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def color_saturation(c):
    r, g, b = c[0]/255, c[1]/255, c[2]/255
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == 0:
        return 0
    return (mx - mn) / mx


def color_brightness(c):
    return max(c) / 255


def dominant_color(info):
    """提取主色 RGB"""
    gradients = info.get("colorgradient", [])
    if gradients and info.get("gradientIndex", -1) == 0:
        stops = gradients[0].get("lineargradient", [])
        if stops:
            # 取饱和度最高的色（最能代表视觉主色）
            best = max(stops, key=lambda s: color_saturation(hex_to_rgb(s["color"])))
            return hex_to_rgb(best["color"])
    return hex_to_rgb(info.get("text_color", "#ffffff"))


# ─── 字1: 色调词 ───────────────────────────────────
COLOR_WORDS = {
    # 红
    (0, 20):    "赤",
    (340, 360): "赤",
    # 橙
    (20, 45):   "橙",
    # 金/黄
    (45, 70):   "金",
    (70, 90):   "黄",
    # 黄绿
    (90, 140):  "翠",
    # 绿
    (140, 180): "碧",
    # 青
    (180, 210): "青",
    # 蓝
    (210, 260): "蓝",
    # 紫
    (260, 300): "紫",
    # 粉
    (300, 340): "粉",
}

def hue_word(c):
    sat = color_saturation(c)
    bright = color_brightness(c)
    if sat < 0.18:
        if bright > 0.85:
            return "白"
        elif bright < 0.25:
            return "墨"
        else:
            return "灰"
    h = color_hue(c)
    for (lo, hi), w in COLOR_WORDS.items():
        if lo <= h < hi:
            return w
    return "彩"


# ─── 字2: 风格词 ───────────────────────────────────
def style_word(info):
    thickness = info.get("thickness", 0)
    strokes = info.get("stroke", [])
    shadows = info.get("shadows", [])
    inner_shadows = info.get("innerShadows", [])
    multi_layer = info.get("multi_text_layer", [])
    
    has_glow = bool(shadows)
    has_3d = thickness > 0.5
    has_offset = bool(multi_layer)
    has_inner = bool(inner_shadows)
    n_stroke = len(strokes)
    
    if has_3d and n_stroke >= 3:
        return "浮"
    if has_3d and has_inner:
        return "雕"
    if has_3d:
        return "立"
    if has_offset:
        return "影"
    if has_glow and not strokes:
        return "虹"
    if n_stroke >= 3:
        return "描"
    if n_stroke == 2:
        return "框"
    if n_stroke == 1:
        return "边"
    if has_glow:
        return "光"
    return "素"


# ─── 字3: 渐变/质感词 ─────────────────────────────
def texture_word(info):
    gradients = info.get("colorgradient", [])
    shadows = info.get("shadows", [])
    
    if not gradients:
        return "纯"
    
    stops = gradients[0].get("lineargradient", [])
    if len(stops) < 2:
        return "纯"
    
    start_c = hex_to_rgb(stops[0]["color"])
    end_c   = hex_to_rgb(stops[-1]["color"])
    start_b = color_brightness(start_c)
    end_b   = color_brightness(end_c)
    
    diff_b = start_b - end_b  # 正 = 上亮下暗
    
    # 渐变跨越色相
    start_h = color_hue(start_c)
    end_h   = color_hue(end_c)
    hue_diff = abs(start_h - end_h)
    if hue_diff > 180:
        hue_diff = 360 - hue_diff
    
    if hue_diff > 40:
        return "彩"
    if diff_b > 0.25:
        return "晕"   # 上亮下暗
    if diff_b < -0.25:
        return "焰"   # 上暗下亮
    if abs(diff_b) < 0.1 and len(stops) <= 2:
        return "匀"
    return "渐"


# ─── 字4: 光效词 ──────────────────────────────────
def effect_word(info):
    shadows = info.get("shadows", [])
    inner_shadows = info.get("innerShadows", [])
    multi_layer = info.get("multi_text_layer", [])
    strokes = info.get("stroke", [])
    thickness = info.get("thickness", 0)
    
    # 有偏移阴影
    if multi_layer:
        off = multi_layer[0]
        ox = abs(off.get("offset_x", 0))
        oy = abs(off.get("offset_y", 0))
        if ox + oy > 20:
            return "错"
        return "叠"
    
    # 有发光
    if shadows:
        # 检查是否有偏移发光
        has_shift = any(
            isinstance(s.get("shift"), dict) and
            (abs(s["shift"].get("x", 0)) + abs(s["shift"].get("y", 0))) > 3
            for s in shadows
        )
        if has_shift:
            return "曳"
        # 多层发光
        if len(shadows) >= 4:
            return "霓"
        return "晖"
    
    if inner_shadows:
        return "雕"
    
    if thickness > 0.5 and strokes:
        return "凸"
    
    return "字"


# ─── 主函数 ────────────────────────────────────────
def generate_name(info):
    """根据 info.json 字典生成四字名称"""
    dc = dominant_color(info)
    
    w1 = hue_word(dc)
    w2 = style_word(info)
    w3 = texture_word(info)
    w4 = effect_word(info)
    
    return w1 + w2 + w3 + w4


# ─── 测试 ──────────────────────────────────────────
if __name__ == "__main__":
    # 快速验证
    samples = [
        ("橙金浮雕", {
            "text_color": "#ff8c3d",
            "colorgradient": [{"lineargradient": [
                {"anchor": 0.0, "color": "#ff8c3d"},
                {"anchor": 1.0, "color": "#fffdd1"}
            ]}],
            "stroke": [{"color": "#1a0800", "width": 2.3}, {"color": "#ff8c3d", "width": 8.4}, {"color": "#fffdd1", "width": 14.0}],
            "innerShadows": [{"color": "#fffdd1", "intensity": 3.0, "shift": {"x": 0, "y": 2}}],
            "thickness": 0.8001,
        }),
        ("错位橙影", {
            "text_color": "#f7f57e",
            "colorgradient": [{"lineargradient": [
                {"anchor": 0.0, "color": "#f6f364"},
                {"anchor": 1.0, "color": "#fffbe4"}
            ]}],
            "stroke": [{"color": "#000000", "width": 3.8}, {"color": "#ffffff", "width": 9.9}],
            "multi_text_layer": [{"offset_x": -15.0, "offset_y": 15.0}],
            "thickness": 0.0001,
        }),
        ("淡黄渐变", {
            "text_color": "#fdfcdd",
            "colorgradient": [{"lineargradient": [
                {"anchor": 0.0, "color": "#fdfcdd"},
                {"anchor": 1.0, "color": "#f5ed6d"}
            ]}],
            "stroke": [{"color": "#1a1400", "width": 2.3}, {"color": "#ffffff", "width": 9.9}],
            "thickness": 0.0001,
        }),
        ("纯橙描边", {
            "text_color": "#eeab3d",
            "colorgradient": [],
            "stroke": [{"color": "#000000", "width": 4.6}, {"color": "#ffffff", "width": 11.4}],
            "thickness": 0.0001,
        }),
        ("黄金霓虹", {
            "text_color": "#fff88f",
            "colorgradient": [],
            "shadows": [{"color": "#fff88f", "intensity": 0.6, "shift": {}} for _ in range(5)] + 
                       [{"color": "#9a8e20", "intensity": 0.8, "shift": {"x": 0, "y": 8}}],
            "thickness": 0.0001,
        }),
        ("赤焰霓虹", {
            "text_color": "#e43426",
            "colorgradient": [],
            "shadows": [{"color": "#e43426", "intensity": 0.6, "shift": {}} for _ in range(4)] +
                       [{"color": "#7a0a00", "intensity": 0.8, "shift": {"x": 0, "y": 10}}],
            "thickness": 0.0001,
        }),
    ]
    
    print("原名 → 生成名")
    for orig, info in samples:
        name = generate_name(info)
        print(f"  {orig} → {name}")
