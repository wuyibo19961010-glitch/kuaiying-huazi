#!/usr/bin/env python3
# coding=utf-8
"""
app_combined.py — 花字生成器（文生花字 + 图生花字 合并版）
运行: streamlit run python/app_combined.py
"""
import sys, json, zipfile, random, io, copy, base64
from pathlib import Path

import streamlit as st
from PIL import Image
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from render_covers import render_cover as _render_cover
from name_gen import generate_name
from style_vocab import STYLE_VOCAB
from measure_design import (
    find_text_bbox, measure_stroke_layers, measure_glow_extent,
    measure_offset, measure_vertical_gradient,
    rgb_to_hex, is_bg, is_gray
)

# ════════════════════════════════════════════════════════════════
# 基础工具
# ════════════════════════════════════════════════════════════════
def render_to_pil(info: dict) -> Image.Image:
    buf = io.BytesIO()
    _render_cover(info, buf)
    buf.seek(0)
    return Image.open(buf).copy()

def img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()

CONFIG_JSON    = {"animationPath": "animation.json", "stylePath": "info.json",
                  "type": "template", "version": "1"}
ANIMATION_JSON = []

def sk(color, width):
    return {"BlendMode":0,"alpha":255,"color":color,"fullfillBias":{},"gradientIndex":-1,"width":width}

def sh(color, intensity, shift=None):
    return {"BlendMode":0,"alpha":255,"color":color,"fullfillBias":{},"gradientIndex":-1,
            "intensity":intensity,"shift":shift or {}}

def ins(color, intensity, sy=2, sx=0):
    return {"alpha":255,"color":color,"intensity":intensity,"shift":{"x":float(sx),"y":float(sy)}}

def ml(color, ox, oy, alpha=255):
    return {"BlendMode":0,"alpha":alpha,"color":color,"fullfillBias":{},"gradientIndex":-1,
            "offset_x":float(ox),"offset_y":float(oy)}

def grad_stops(*stops):
    return [{"lineargradient":[{"anchor":a,"color":c} for a,c in stops]}]

BASE_INFO = {
    "align_type":1,"effectType":0,"fullfile_image":[],"hideText":False,
    "italic_degree":0.0001,"letterSpace":1.0001,"lineSpace":1.0001,
    "loopEnd":0,"loopNum":-1,"loopStart":0,"text":"花字",
    "textColorAlpha":255,"textFillBlendMode":0,"textFullFillBlendMode":0,
    "textFullfillBias":{},"text_size":160,"version":1,
    "colorgradient":[],"gradientIndex":-1,"gradientDegree":90.0001,
    "stroke":[],"shadows":[],"innerShadows":[],"multi_text_layer":[],"thickness":0.0001,
    "text_color":"#ffffff",
}

def make_info(**kw):
    d = copy.deepcopy(BASE_INFO)
    d.update(kw)
    return d

# ════════════════════════════════════════════════════════════════
# 颜色工具
# ════════════════════════════════════════════════════════════════
def darken(h, f=0.4):
    h=h.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return f"#{max(0,int(r*f)):02x}{max(0,int(g*f)):02x}{max(0,int(b*f)):02x}"

def lighten(h, f=1.5):
    h=h.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return f"#{min(255,int(r*f)):02x}{min(255,int(g*f)):02x}{min(255,int(b*f)):02x}"

# ════════════════════════════════════════════════════════════════
# 色板
# ════════════════════════════════════════════════════════════════
COLOR_PALETTES = {
    "粉": [("#ffd6e8","#ff85b3","#ff1f7d","#7a0046","#3a0020"),
           ("#ffe0f0","#ffb3d9","#ff69b4","#c2185b","#880e4f"),
           ("#fce4ec","#f48fb1","#e91e63","#880e4f","#3e0026")],
    "金": [("#fffdd1","#ffc86e","#c87e2a","#7a4a00","#402a00"),
           ("#fff9c4","#ffee58","#fdd835","#f9a825","#4e2900"),
           ("#fff8e1","#ffe082","#ffb300","#e65100","#3e1500")],
    "蓝": [("#6098fe","#006df4","#021eaa","#00118a","#000051"),
           ("#e3f2fd","#90caf9","#2196f3","#0d47a1","#001a57"),
           ("#c9e8ff","#5ec5ff","#1a8fff","#005bcc","#001f66")],
    "紫": [("#f3e5f5","#ce93d8","#9c27b0","#4a148c","#1a0033"),
           ("#bb66ff","#8833cc","#5500aa","#330066","#1a0033"),
           ("#e8d5ff","#c080ff","#8000ff","#5000cc","#200055")],
    "红": [("#ffebee","#ef9a9a","#f44336","#b71c1c","#4a0000"),
           ("#ff6b6b","#ee0000","#aa0000","#660000","#330000")],
    "绿": [("#e8f5e9","#a5d6a7","#4caf50","#1b5e20","#002200"),
           ("#e0f2f1","#80cbc4","#009688","#004d40","#001a17")],
    "橙": [("#fff3e0","#ffcc80","#ff9800","#e65100","#4e1a00"),
           ("#ffd180","#ff6d00","#dd2c00","#8d1000","#3e0500")],
    "青": [("#e0f7fa","#80deea","#00bcd4","#006064","#00212a"),
           ("#b2ebf2","#4dd0e1","#0097a7","#004d57","#001c21")],
    "黑白": [("#ffffff","#e0e0e0","#9e9e9e","#424242","#000000"),
             ("#ffffff","#cccccc","#666666","#222222","#000000")],
}
STYLE_COLOR_MAP = {
    "粉":["粉"],"少女":["粉"],"可爱":["粉"],"甜":["粉"],"玫":["粉"],"桃":["粉"],
    "樱":["粉"],"浪漫":["粉","紫"],"梦幻":["粉","紫"],
    "金":["金"],"贵":["金"],"豪华":["金"],"奢":["金"],"鎏金":["金"],
    "华丽":["金","紫"],"古风":["金","紫"],"国风":["金","紫"],
    "蓝":["蓝"],"科技":["蓝","青"],"冷":["蓝","青"],"未来":["蓝","青"],
    "赛博":["蓝","紫"],"电子":["蓝","青"],
    "紫":["紫"],"神秘":["紫"],"魔法":["紫","粉"],
    "红":["红"],"热血":["红","橙"],"喜庆":["红"],"危险":["红"],
    "火":["红","橙"],"热情":["红","橙"],
    "绿":["绿"],"清新":["绿","青"],"自然":["绿"],"森林":["绿"],
    "橙":["橙"],"活力":["橙","红"],"夏日":["橙","粉"],
    "青":["青"],"清爽":["青","绿"],"海洋":["青","蓝"],
    "黑":["黑白"],"白":["黑白"],"简约":["黑白"],"极简":["黑白"],"经典":["黑白","金"],
}
EFFECT_TYPES = ["霓虹发光","厚描边","3D立体","浮雕","双色渐变","多层描边","错位投影","简约"]
RANDOM_STYLES = [
    "少女粉色甜美可爱","鎏金古风华丽","赛博朋克蓝紫","危险红光霓虹",
    "森林清新绿色","海洋青蓝渐变","夕阳橙红热情","极简黑白经典",
    "梦幻紫色神秘","活力橙色夏日","冷酷蓝色科技","喜庆红色国风",
]
ALL_VOCAB_KEYS = list(STYLE_VOCAB.keys())

def _luminance(hex_color):
    """计算颜色亮度 0~255"""
    h = hex_color.lstrip("#")
    r,g,b = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return 0.299*r + 0.587*g + 0.114*b


def _bright_color(hex_color):
    """如果颜色太暗（亮度<60），返回其浅色版本；否则原样返回"""
    if _luminance(hex_color) < 60:
        return lighten(hex_color, 3.0)
    return hex_color


def collect_palettes(style, rng, force=False):
    """收集所有匹配的色板列表。force=True时随机取2套不同色系。
    返回 list of palette_5tuple，长度 >= 1。"""
    all_keys = list(COLOR_PALETTES.keys())
    if force:
        k1, k2 = rng.sample(all_keys, 2)
        return [
            rng.choice(COLOR_PALETTES[k1]),
            rng.choice(COLOR_PALETTES[k2]),
        ]

    palettes = []
    seen_pals = set()

    # 词库匹配（子串，每个命中词贡献一套色板）
    for key in STYLE_VOCAB:
        if key in style:
            entry = STYLE_VOCAB[key]
            pal = list(entry.get("palette", []))
            if pal:
                while len(pal) < 5:
                    pal.append(pal[-1])
                t = tuple(pal[:5])
                if t not in seen_pals:
                    seen_pals.add(t)
                    palettes.append(t)

    # STYLE_COLOR_MAP 匹配（和词库结果合并，不互斥）
    matched = []
    for kw, ks in STYLE_COLOR_MAP.items():
        if kw in style: matched.extend(ks)
    for k in list(dict.fromkeys(matched)):
        pal = rng.choice(COLOR_PALETTES[k])
        if pal not in seen_pals:
            seen_pals.add(pal)
            palettes.append(pal)

    if palettes:
        return palettes
    return [rng.choice(COLOR_PALETTES[rng.choice(all_keys)])]


# ════════════════════════════════════════════════════════════════
# 文生花字参数生成
# ════════════════════════════════════════════════════════════════
def _assign_palettes(palettes, rng):
    """打乱色板列表，返回 (fill_pal, stroke_pal, glow_pal)。
    只有1套时三者相同；有多套时随机分配不同套给不同图层类型。"""
    if len(palettes) == 1:
        p = palettes[0]
        return p, p, p
    shuffled = palettes[:]
    rng.shuffle(shuffled)
    # 循环取：填充 → shuffled[0], 描边 → shuffled[1], 发光 → shuffled[2%n]
    n = len(shuffled)
    return shuffled[0], shuffled[1 % n], shuffled[2 % n]


def build_info(style, effect, seed, force=False):  # noqa: C901
    rng = random.Random(seed)
    palettes = collect_palettes(style, rng, force)
    fp, sp, gp = _assign_palettes(palettes, rng)   # fill / stroke / glow 三套色板
    # 各套色板取对应位置色
    c0,c1,c2,c3,c4 = fp       # 填充色
    s0,s1,s2 = sp[0],sp[1],sp[2]  # 描边色
    g0,g1,g2 = gp[0],gp[1],gp[2]  # 发光/阴影色
    # 暗色保护：外层描边确保可见
    s_outer = _bright_color(s2)  # 最外描边用亮色

    if effect == "霓虹发光":
        n = rng.randint(4,6); base = rng.uniform(0.45,0.65)
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,c0),(1,c1)),
            stroke=[sk(darken(s2,0.25),rng.uniform(2.0,3.2)), sk(s_outer,rng.uniform(7.0,10.0))],
            shadows=[sh(g1, max(0.04, base-i*0.08)) for i in range(n)] +
                    [sh(darken(g2,0.6), rng.uniform(0.5,0.75), {"x":0,"y":rng.randint(6,14)})],
        )
    elif effect == "厚描边":
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,lighten(c0,1.3)),(1,c1)),
            stroke=[sk(darken(s2,0.25),rng.uniform(2.0,3.5)),
                    sk(s2,rng.uniform(7.0,11.0)),
                    sk(s_outer,rng.uniform(13.0,17.0))],
            innerShadows=[ins(lighten(c0,1.8), rng.uniform(1.5,3.5), rng.randint(1,3))],
        )
    elif effect == "3D立体":
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,lighten(c0,1.4)),(1,c2)),
            stroke=[sk(darken(s2,0.35),rng.uniform(2.2,3.5)),
                    sk(s2,rng.uniform(8.0,11.0)),
                    sk(s1,rng.uniform(14.0,18.0)),
                    sk(s_outer,rng.uniform(22.0,27.0))],
            innerShadows=[ins(lighten(c0,2.0), rng.uniform(4.0,8.0), rng.randint(2,4))],
            thickness=rng.choice([1.2,1.6]),
        )
    elif effect == "浮雕":
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,lighten(c0,1.3)),(0.5,c1),(1,c2)),
            stroke=[sk(darken(s2,0.25),rng.uniform(2.0,3.2)),
                    sk(s2,rng.uniform(7.0,11.0)),
                    sk(s1,rng.uniform(13.0,16.0)),
                    sk(s_outer,rng.uniform(17.0,22.0))],
            innerShadows=[ins(lighten(c0,2.2), rng.uniform(3.0,6.0), rng.randint(1,4))],
            shadows=[sh(g1, rng.uniform(0.25,0.5))],
            thickness=rng.choice([0.8,1.2]),
        )
    elif effect == "双色渐变":
        return make_info(
            text_color=c0, gradientIndex=0,
            gradientDegree=rng.choice([90.0001,45.0,0.0001]),
            colorgradient=grad_stops((0,c0),(0.5,c1),(1,c3)),
            stroke=[sk(darken(s2,0.25),rng.uniform(2.0,3.5)),
                    sk(s2,rng.uniform(8.0,12.0))],
            shadows=[sh(g1, rng.uniform(0.25,0.45))],
        )
    elif effect == "多层描边":
        n = rng.randint(4,5)
        ws = [rng.uniform(2.0,3.8),rng.uniform(7.0,10.0),rng.uniform(12.0,15.0),rng.uniform(17.0,21.0),rng.uniform(23.0,27.0)]
        cs = ([darken(sp[4],0.35),sp[3],s2,s1,s_outer] if len(sp)>4
              else [darken(s2,0.35),s2,s1,s0,s_outer])
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,lighten(c0,1.3)),(1,c1)),
            stroke=[sk(cs[i],ws[i]) for i in range(n)],
            innerShadows=[ins(lighten(c0,1.8), rng.uniform(0.5,2.0), 2)],
        )
    elif effect == "错位投影":
        ox = rng.choice([-14.4,-11.2,11.2,14.4]); oy = rng.choice([-14.4,-11.2,11.2,14.4])
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,c0),(1,c1)),
            stroke=[sk(darken(s2,0.25),rng.uniform(2.0,3.5)), sk(s2,rng.uniform(9.0,13.0))],
            multi_text_layer=[ml(darken(g2,0.5), ox, oy)],
        )
    else:  # 简约
        return make_info(
            text_color=c0, gradientIndex=0, gradientDegree=90.0001,
            colorgradient=grad_stops((0,lighten(c0,1.2)),(1,c2)),
            stroke=[sk(darken(s1,0.35),rng.uniform(2.0,4.0)), sk(s1,rng.uniform(7.0,11.0))],
            shadows=[sh(g1, rng.uniform(0.15,0.35))],
        )

# ════════════════════════════════════════════════════════════════
# 图生花字：像素分析
# ════════════════════════════════════════════════════════════════
def analyze_image_to_info(img: Image.Image) -> dict:
    img_rgb = img.convert("RGB")
    w, h = img_rgb.size
    arr = np.array(img_rgb)

    bbox = find_text_bbox(arr, w, h)
    left, top, right, bottom = bbox
    text_w = right - left
    text_h = bottom - top
    # 换算系数：参考字体在 text_size=160 时，文字宽度约 200 单位
    # 但实际图片分辨率各异，用 text_w 归一化到 200 单位
    px_per_unit = max(1.0, text_w / 200.0)

    gradient_stops_raw = measure_vertical_gradient(arr, bbox)
    stroke_scans = measure_stroke_layers(arr, bbox, "right")
    glow_data = measure_glow_extent(arr, bbox)
    off_x, off_y = measure_offset(arr, bbox)
    off_x_u = off_x / px_per_unit
    off_y_u = off_y / px_per_unit

    # ── colorgradient ──────────────────────────────────────────
    colorgradient = []; grad_index = -1; main_color = "#ffffff"
    clean = [(p,c) for p,c in gradient_stops_raw
             if not is_bg(c,30) and not is_gray(c,20) and max(c) > 50]
    if len(clean) >= 2:
        # 只取首尾两个节点，渲染更干净
        stops_list = [
            {"anchor":0.0,"color":rgb_to_hex(*clean[0][1])},
            {"anchor":1.0,"color":rgb_to_hex(*clean[-1][1])}
        ]
        # 如果中间色和首尾差异够大，加入中间节点
        if len(clean) >= 3:
            mid = clean[len(clean)//2]
            c0 = clean[0][1]; c1 = clean[-1][1]; cm = mid[1]
            if any(abs(int(cm[i])-int(c0[i]))>25 and abs(int(cm[i])-int(c1[i]))>25 for i in range(3)):
                stops_list = [
                    {"anchor":0.0,"color":rgb_to_hex(*clean[0][1])},
                    {"anchor":round(mid[0],2),"color":rgb_to_hex(*mid[1])},
                    {"anchor":1.0,"color":rgb_to_hex(*clean[-1][1])}
                ]
        colorgradient = [{"lineargradient": stops_list}]
        grad_index = 0
        main_color = rgb_to_hex(*clean[0][1])
    elif clean:
        main_color = rgb_to_hex(*clean[0][1])

    # ── stroke ────────────────────────────────────────────────
    strokes = []
    if stroke_scans:
        best = max(stroke_scans, key=len)
        seen_widths = []
        for color_rgb, width_px, start, end in best:
            if is_bg(color_rgb, 35): continue
            w_u = max(1.5, min(28.0, round(width_px / px_per_unit, 1)))
            # 跳过和已有描边宽度非常接近的（合并相似层）
            if any(abs(w_u - sw) < 1.2 for sw in seen_widths): continue
            seen_widths.append(w_u)
            strokes.append(sk(rgb_to_hex(*color_rgb), w_u))
        strokes = sorted(strokes, key=lambda x: x["width"])[:5]

    # ── shadows（外发光）──────────────────────────────────────
    shadows = []
    best_dir = None; best_dist = 0
    for direction, samples in glow_data.items():
        bright_s = [(d,c,b) for d,c,b in samples if b > 15 and not is_gray(c,12)]
        if not bright_s: continue
        max_d = max(s[0] for s in bright_s)
        if max_d > best_dist:
            best_dist = max_d; best_dir = direction
            best_glow = bright_s
    if best_dist > 8 and best_dir:
        glow_c = rgb_to_hex(*best_glow[0][1])
        base_i = min(0.85, best_dist / 50.0 + 0.3)
        n_layers = min(5, max(2, int(best_dist / 15)))
        for i in range(n_layers):
            factor = 1.0 - i * (0.8/n_layers)
            shift = {}
            if best_dir == "下": shift = {"x":0.0,"y":round(best_dist/px_per_unit*0.25,1)}
            elif best_dir == "右": shift = {"x":round(best_dist/px_per_unit*0.25,1),"y":0.0}
            elif best_dir == "上": shift = {"x":0.0,"y":-round(best_dist/px_per_unit*0.25,1)}
            shadows.append(sh(glow_c, max(0.06, round(base_i*factor, 2)), shift))

    # ── multi_text_layer ──────────────────────────────────────
    multi = []
    if abs(off_x_u) > 5 or abs(off_y_u) > 5:
        sx = int(np.clip((left+right)//2 + off_x, 0, w-1))
        sy_p = int(np.clip((top+bottom)//2 + off_y, 0, h-1))
        sc = tuple(arr[sy_p, sx])
        shadow_c = rgb_to_hex(*sc) if not is_bg(sc,30) else darken(main_color, 0.5)
        multi.append(ml(shadow_c, round(off_x_u,1), round(off_y_u,1)))

    # ── innerShadows ──────────────────────────────────────────
    inner = []
    if colorgradient and strokes:
        top_c = colorgradient[0]["lineargradient"][0]["color"]
        inner.append(ins(lighten(top_c, 1.6), 2.5, 2))

    thickness = 0.0001
    if len(strokes) >= 3 and not shadows:
        thickness = 0.8001

    return make_info(
        text_color=main_color, colorgradient=colorgradient,
        gradientIndex=grad_index, gradientDegree=90.0001,
        stroke=strokes, shadows=shadows, innerShadows=inner,
        multi_text_layer=multi, thickness=thickness,
    )

# ════════════════════════════════════════════════════════════════
# ZIP 打包
# ════════════════════════════════════════════════════════════════
def make_zip(rlist, img_key="img"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for r in rlist:
            folder = r["name"]
            zf.writestr(f"{folder}/config.json",    json.dumps(CONFIG_JSON,   ensure_ascii=False,indent=4))
            zf.writestr(f"{folder}/info.json",       json.dumps(r["info"],     ensure_ascii=False,indent=4))
            zf.writestr(f"{folder}/animation.json",  json.dumps(ANIMATION_JSON,ensure_ascii=False,indent=4))
            ib = io.BytesIO(); r[img_key].save(ib,"WEBP",quality=92)
            zf.writestr(f"{folder}/{folder}.webp", ib.getvalue())
            inner = io.BytesIO()
            with zipfile.ZipFile(inner,"w") as izf:
                izf.writestr("config.json",    json.dumps(CONFIG_JSON,   ensure_ascii=False,indent=4))
                izf.writestr("info.json",      json.dumps(r["info"],     ensure_ascii=False,indent=4))
                izf.writestr("animation.json", json.dumps(ANIMATION_JSON,ensure_ascii=False,indent=4))
            zf.writestr(f"{folder}/output.zip", inner.getvalue())
    return buf.getvalue()

# ════════════════════════════════════════════════════════════════
# CSS
# ════════════════════════════════════════════════════════════════
CSS = """
<style>
header[data-testid="stHeader"],#MainMenu,footer,.stDeployButton{display:none!important}
html,body,[data-testid="stAppViewContainer"],[data-testid="stSidebar"]{
    background:#0e0e1a!important;color:#c8cad4!important}
[data-testid="stSidebar"]{background:#141426!important;border-right:1px solid #2a2a3a!important}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p,
[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p{color:#d0d2e0!important}
.stTextArea textarea,.stNumberInput input{
    background:#1a1a2e!important;color:#e0e2f0!important;border:1px solid #3a3a5a!important}
button[kind="primary"],button[kind="primary"] p{
    background:#5c6bc0!important;color:#fff!important;border:none!important;border-radius:6px!important}
button[kind="primary"]:hover{background:#7986cb!important}
button[kind="secondary"]{background:#1e1e2e!important;color:#9a9cb0!important;
    border:1px solid #3a3a5a!important;border-radius:6px!important}
button[kind="secondary"]:hover{border-color:#5c6bc0!important;color:#c8cad4!important}
[data-testid="stDownloadButton"] button{background:#5c6bc0!important;color:#fff!important;border:none!important}
.stProgress>div>div{background:#5c6bc0!important}
[data-testid="stFileUploader"]{background:#1a1a2e!important;border:1px dashed #3a3a5a!important;border-radius:8px!important}
[data-testid="stFileUploader"] section>div>div>span{font-size:0!important}
[data-testid="stFileUploader"] section>div>div>span::before{font-size:13px!important;content:"拖拽图片到这里，或点击选择文件"}
[data-testid="stFileUploader"] section button{font-size:12px!important}
[data-testid="stModal"] [data-testid="stModalContent"]{background:#141426!important}
[data-testid="stModal"] label,[data-testid="stModal"] p,
[data-testid="stModal"] .stMarkdown p{color:#d0d2e0!important}
/* 置灰区域 */
.disabled-section{opacity:.35;pointer-events:none;user-select:none}
@keyframes bl{0%,100%{transform:translateX(0)}50%{transform:translateX(-14px)}}
.ahl{animation:bl 1.1s ease-in-out infinite;display:inline-block}
</style>
"""

# ════════════════════════════════════════════════════════════════
# UI 初始化
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="花字生成器", page_icon="🎨", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

for k, v in [("results",[]),("selected",set()),("tune_idx",None),
             ("img_results",[]),("img_selected",set()),("img_tune_idx",None),
             ("gen_rand",0),("auto_gen",False),
             ("style_val","")]:
    if k not in st.session_state:
        st.session_state[k] = v

# ════════════════════════════════════════════════════════════════
# 通用调参弹窗 — 完全相同结构，没启用的可点击启用
# ════════════════════════════════════════════════════════════════
def tune_dialog(tidx, rlist, list_key, img_key="img", orig_key=None):
    tr = next((r for r in rlist if r["idx"]==tidx), None)
    if not tr: return

    @st.dialog(f"调参 — {tr['name']}", width="large")
    def _dlg():
        sk_n = f"tune_{list_key}_{tidx}"
        if sk_n not in st.session_state:
            st.session_state[sk_n] = copy.deepcopy(tr["info"])
        nfo = st.session_state[sk_n]

        # 启用状态 key
        def enabled_key(field): return f"en_{list_key}_{tidx}_{field}"

        # 初始化启用状态
        for field in ["grad","shadows","innerShadows","multi_text_layer"]:
            ek = enabled_key(field)
            if ek not in st.session_state:
                if field == "grad":
                    st.session_state[ek] = bool(nfo.get("colorgradient") and nfo.get("gradientIndex",- 1) >= 0)
                else:
                    st.session_state[ek] = bool(nfo.get(field))

        # 布局：参数左 预览右
        L, R = st.columns([11, 4])

        # ── 右侧：预览（始终固定）──────────────────────────────
        with R:
            # 参考图 + 效果图横排
            if orig_key and tr.get(orig_key):
                pc1, pc2 = st.columns(2)
                with pc1:
                    st.image(tr[orig_key].resize((150,150)), caption="参考", use_container_width=True)
                with pc2:
                    with st.spinner("渲染中…"):
                        try:
                            st.image(render_to_pil(nfo), caption="效果", use_container_width=True)
                        except Exception as e:
                            st.error(f"失败: {e}")
            else:
                with st.spinner("渲染中…"):
                    try:
                        st.image(render_to_pil(nfo), caption="当前效果", use_container_width=True)
                    except Exception as e:
                        st.error(f"渲染失败: {e}")
            if st.button("应用并关闭", key=f"apply_{list_key}_{tidx}",
                         use_container_width=True, type="primary"):
                for r in rlist:
                    if r["idx"] == tidx:
                        r["info"] = copy.deepcopy(nfo)
                        try: r[img_key] = render_to_pil(nfo)
                        except: pass
                st.session_state[f"{list_key}_tune_idx"] = None
                st.rerun()
            if st.button("关闭", key=f"cls_{list_key}_{tidx}", use_container_width=True):
                st.session_state[f"{list_key}_tune_idx"] = None
                st.rerun()

        # ── 左侧：参数（所有花字完全一致）──────────────────────
        with L:
            grad_enabled = st.session_state[enabled_key("grad")]

            grad = nfo.get("colorgradient") or []
            if grad and grad[0].get("lineargradient"):
                stops = grad[0]["lineargradient"]
                c_start = stops[0]["color"]
                c_end   = stops[-1]["color"]
            else:
                c_start = nfo.get("text_color","#ffffff")
                c_end   = darken(c_start, 0.6)

            # ── 渐变颜色行（实时生效，无确认按钮）───────────────
            deg_opts = {"上↓下":90.0001,"左→右":0.0001,"斜45°":45.0}
            cur_d = nfo.get("gradientDegree",90.0001)
            cur_lbl = min(deg_opts, key=lambda k: abs(deg_opts[k]-cur_d))
            gc1,gc2,gc3,gc4,gc5,gc6 = st.columns([1,1.5,1.5,2.5,1.5,2])
            with gc1: st.markdown("**渐变**")
            with gc2:
                new_cs = st.color_picker("起色", c_start, key=f"cs_{list_key}_{tidx}",
                                          disabled=not grad_enabled)
            with gc3:
                new_ce = st.color_picker("终色", c_end, key=f"ce_{list_key}_{tidx}",
                                          disabled=not grad_enabled)
            with gc4:
                sel_d = st.radio("方向", list(deg_opts.keys()),
                                 index=list(deg_opts.keys()).index(cur_lbl),
                                 horizontal=True, key=f"gd_{list_key}_{tidx}",
                                 disabled=not grad_enabled)
            with gc5:
                tc = st.color_picker("文字主色", nfo.get("text_color","#ffffff"),
                                      key=f"tc_{list_key}_{tidx}")
            with gc6:
                if not grad_enabled:
                    if st.button("启用渐变", key=f"en_grad_{list_key}_{tidx}", use_container_width=True):
                        st.session_state[enabled_key("grad")] = True
                        if not nfo.get("colorgradient"):
                            nfo["colorgradient"] = [{"lineargradient":[
                                {"anchor":0.0,"color":nfo.get("text_color","#ffffff")},
                                {"anchor":1.0,"color":"#000000"}]}]
                        nfo["gradientIndex"] = 0
                        st.session_state[sk_n] = nfo; st.rerun()
                else:
                    if st.button("禁用渐变", key=f"dis_grad_{list_key}_{tidx}", use_container_width=True):
                        st.session_state[enabled_key("grad")] = False
                        nfo["gradientIndex"] = -1
                        st.session_state[sk_n] = nfo; st.rerun()

            # 实时写入渐变
            if grad_enabled:
                nfo["colorgradient"] = [{"lineargradient":[
                    {"anchor":0.0,"color":new_cs},{"anchor":1.0,"color":new_ce}]}]
                nfo["gradientIndex"] = 0
                nfo["gradientDegree"] = deg_opts[sel_d]
            else:
                nfo["gradientIndex"] = -1
            nfo["text_color"] = tc

            # ── 描边──────────────────────────────────────────────
            st.markdown("**描边**")
            strokes = list(nfo.get("stroke") or [])
            if not strokes:
                strokes = [sk("#000000", 3.0), sk("#ffffff", 9.0)]
                nfo["stroke"] = strokes

            n_s = st.slider("层数", 1, 5, min(len(strokes),5),
                            key=f"ns_{list_key}_{tidx}")
            while len(strokes) < n_s:
                strokes.append(copy.deepcopy(strokes[-1]))
            strokes = strokes[:n_s]

            # 颜色+宽度 并排
            cols_s = st.columns(n_s * 2)
            new_strokes = []
            for i in range(n_s):
                with cols_s[i*2]:
                    nc = st.color_picker(f"S{i+1}色", strokes[i].get("color","#fff"),
                                          key=f"sc_{list_key}_{tidx}_{i}")
                with cols_s[i*2+1]:
                    nw = st.slider(f"S{i+1}宽", 0.8, 28.0,
                                   float(strokes[i].get("width",5.0)),
                                   step=0.8, key=f"sw_{list_key}_{tidx}_{i}",
                                   label_visibility="visible")
                new_strokes.append({**strokes[i], "color":nc, "width":nw})
            nfo["stroke"] = new_strokes

            # ── 外发光 ─────────────────────────────────────────
            sh_enabled = st.session_state[enabled_key("shadows")]
            shadows = list(nfo.get("shadows") or [])

            sh_row = st.columns([2,2,2,2,2,3])
            with sh_row[0]: st.markdown("**外发光**")

            if not sh_enabled:
                with sh_row[5]:
                    if st.button("启用外发光", key=f"en_sh_{list_key}_{tidx}",
                                 use_container_width=True):
                        st.session_state[enabled_key("shadows")] = True
                        if not nfo.get("shadows"):
                            c = nfo.get("text_color","#ffffff")
                            nfo["shadows"] = [sh(c,0.5),sh(c,0.35),sh(c,0.2)]
                        st.rerun()
                # 置灰占位
                with sh_row[1]: st.color_picker("颜色", "#888888", key=f"gc_{list_key}_{tidx}", disabled=True)
                with sh_row[2]: st.slider("强度", 0.04, 1.0, 0.5, key=f"gi_{list_key}_{tidx}", disabled=True)
                with sh_row[3]: st.slider("层数", 1, 8, 3, key=f"ng_{list_key}_{tidx}", disabled=True)
                with sh_row[4]: st.slider("Y偏移", -20.0, 20.0, 0.0, key=f"gy_{list_key}_{tidx}", disabled=True)
            else:
                if not shadows:
                    c = nfo.get("text_color","#ffffff")
                    shadows = [sh(c,0.5),sh(c,0.35),sh(c,0.2)]
                with sh_row[1]:
                    gc = st.color_picker("颜色", shadows[0].get("color","#fff"),
                                          key=f"gc_{list_key}_{tidx}")
                with sh_row[2]:
                    gi = st.slider("强度", 0.04, 1.0,
                                   float(min(shadows[0].get("intensity",0.5),1.0)),
                                   step=0.04, key=f"gi_{list_key}_{tidx}")
                with sh_row[3]:
                    ng = st.slider("层数", 1, 8, len(shadows),
                                   key=f"ng_{list_key}_{tidx}")
                with sh_row[4]:
                    last_sh = shadows[-1] if shadows else {}
                    gy_v = float(last_sh.get("shift",{}).get("y",0)) if isinstance(last_sh.get("shift"),dict) else 0.0
                    gy = st.slider("Y偏移", -20.0, 20.0, gy_v,
                                   step=1.0, key=f"gy_{list_key}_{tidx}")
                with sh_row[5]:
                    if st.button("禁用外发光", key=f"dis_sh_{list_key}_{tidx}",
                                 use_container_width=True):
                        st.session_state[enabled_key("shadows")] = False
                        nfo["shadows"] = []
                        st.rerun()

                while len(shadows) < ng: shadows.append(copy.deepcopy(shadows[-1]))
                for i, s in enumerate(shadows[:ng]):
                    s["color"] = gc
                    s["intensity"] = max(0.04, round(gi * (1 - i*0.15), 3))
                if shadows: shadows[-1]["shift"] = {"x":0.0,"y":gy}
                nfo["shadows"] = shadows[:ng]

            # ── 内高光 ─────────────────────────────────────────
            ii_enabled = st.session_state[enabled_key("innerShadows")]
            inner = list(nfo.get("innerShadows") or [])

            ii_row = st.columns([2,2,2,2,2,3])
            with ii_row[0]: st.markdown("**内高光**")

            if not ii_enabled:
                with ii_row[5]:
                    if st.button("启用内高光", key=f"en_ii_{list_key}_{tidx}",
                                 use_container_width=True):
                        st.session_state[enabled_key("innerShadows")] = True
                        if not nfo.get("innerShadows"):
                            c = lighten(nfo.get("text_color","#ffffff"), 1.5)
                            nfo["innerShadows"] = [ins(c, 2.5, 2)]
                        st.rerun()
                with ii_row[1]: st.color_picker("颜色", "#888888", key=f"ic_{list_key}_{tidx}", disabled=True)
                with ii_row[2]: st.slider("强度", 0.5, 12.0, 2.0, key=f"ii_{list_key}_{tidx}", disabled=True)
                with ii_row[3]: st.slider("Y偏移", -8, 8, 2, key=f"iy_{list_key}_{tidx}", disabled=True)
                with ii_row[4]: st.slider("X偏移", -8, 8, 0, key=f"ix_{list_key}_{tidx}", disabled=True)
            else:
                if not inner:
                    c = lighten(nfo.get("text_color","#ffffff"), 1.5)
                    inner = [ins(c, 2.5, 2)]
                with ii_row[1]:
                    ic_c = st.color_picker("颜色", inner[0].get("color","#fff"),
                                            key=f"ic_{list_key}_{tidx}")
                with ii_row[2]:
                    ii_v = st.slider("强度", 0.5, 12.0,
                                     float(min(inner[0].get("intensity",2.0),12.0)),
                                     step=0.5, key=f"ii_{list_key}_{tidx}")
                with ii_row[3]:
                    sft = inner[0].get("shift",{})
                    iy = st.slider("Y偏移", -8, 8,
                                   int(sft.get("y",2) if isinstance(sft,dict) else 2),
                                   key=f"iy_{list_key}_{tidx}")
                with ii_row[4]:
                    ix = st.slider("X偏移", -8, 8,
                                   int(sft.get("x",0) if isinstance(sft,dict) else 0),
                                   key=f"ix_{list_key}_{tidx}")
                with ii_row[5]:
                    if st.button("禁用内高光", key=f"dis_ii_{list_key}_{tidx}",
                                 use_container_width=True):
                        st.session_state[enabled_key("innerShadows")] = False
                        nfo["innerShadows"] = []
                        st.rerun()
                for s in (nfo.get("innerShadows") or [inner[0]]):
                    s["color"] = ic_c; s["intensity"] = ii_v
                    s["shift"] = {"x":float(ix),"y":float(iy)}
                nfo["innerShadows"] = [inner[0]]
                nfo["innerShadows"][0] = {"alpha":255,"color":ic_c,"intensity":ii_v,"shift":{"x":float(ix),"y":float(iy)}}

            # ── 错位投影 ───────────────────────────────────────
            ml_enabled = st.session_state[enabled_key("multi_text_layer")]
            multi = list(nfo.get("multi_text_layer") or [])

            ml_row = st.columns([2,2,2,2,3])
            with ml_row[0]: st.markdown("**错位投影**")

            if not ml_enabled:
                with ml_row[4]:
                    if st.button("启用错位投影", key=f"en_ml_{list_key}_{tidx}",
                                 use_container_width=True):
                        st.session_state[enabled_key("multi_text_layer")] = True
                        if not nfo.get("multi_text_layer"):
                            c = darken(nfo.get("text_color","#ffffff"), 0.5)
                            nfo["multi_text_layer"] = [ml(c, 11.2, 11.2)]
                        st.rerun()
                with ml_row[1]: st.color_picker("颜色", "#888888", key=f"mc_{list_key}_{tidx}", disabled=True)
                with ml_row[2]: st.slider("X偏移", -30.0, 30.0, 11.2, key=f"mx_{list_key}_{tidx}", disabled=True)
                with ml_row[3]: st.slider("Y偏移", -30.0, 30.0, 11.2, key=f"my_{list_key}_{tidx}", disabled=True)
            else:
                if not multi:
                    c = darken(nfo.get("text_color","#ffffff"), 0.5)
                    multi = [ml(c, 11.2, 11.2)]
                with ml_row[1]:
                    mc_c = st.color_picker("颜色", multi[0].get("color","#000"),
                                            key=f"mc_{list_key}_{tidx}")
                with ml_row[2]:
                    mx = st.slider("X偏移", -30.0, 30.0,
                                   float(multi[0].get("offset_x",11.2)),
                                   step=1.6, key=f"mx_{list_key}_{tidx}")
                with ml_row[3]:
                    my = st.slider("Y偏移", -30.0, 30.0,
                                   float(multi[0].get("offset_y",11.2)),
                                   step=1.6, key=f"my_{list_key}_{tidx}")
                with ml_row[4]:
                    if st.button("禁用错位投影", key=f"dis_ml_{list_key}_{tidx}",
                                 use_container_width=True):
                        st.session_state[enabled_key("multi_text_layer")] = False
                        nfo["multi_text_layer"] = []
                        st.rerun()
                nfo["multi_text_layer"] = [{"BlendMode":0,"alpha":255,"color":mc_c,
                    "fullfillBias":{},"gradientIndex":-1,"offset_x":mx,"offset_y":my}]

            # ── 3D厚度（始终显示）──────────────────────────────
            thick_map = {"平面":0.0001,"轻微":0.8,"明显":1.6,"夸张":2.5}
            cur_t = nfo.get("thickness",0.0001)
            cur_tl = min(thick_map, key=lambda k: abs(thick_map[k]-cur_t))
            sel_t = st.radio("3D厚度", list(thick_map.keys()),
                             index=list(thick_map.keys()).index(cur_tl),
                             horizontal=True, key=f"th_{list_key}_{tidx}")
            nfo["thickness"] = thick_map[sel_t]

        st.session_state[sk_n] = nfo

    _dlg()

# ════════════════════════════════════════════════════════════════
# 侧边栏
# ════════════════════════════════════════════════════════════════
HINT = lambda msg, sub: f"""<div style="display:flex;flex-direction:column;align-items:center;
justify-content:center;height:65vh;text-align:center">
<span class="ahl" style="font-size:3.5rem;color:#7986cb">←</span>
<div style="font-size:1.1rem;font-weight:600;color:#9fa8da;margin-top:.8rem">{msg}</div>
<div style="font-size:.85rem;color:#4a4a6a;margin-top:.4rem">{sub}</div></div>"""

with st.sidebar:
    st.markdown('<h1 style="color:#fff;font-size:1.3rem;margin:0 0 .4rem">花字生成器</h1>',
                unsafe_allow_html=True)
    tab_mode = st.radio("", ["文生花字","图生花字"],
                        horizontal=True, label_visibility="collapsed")
    st.markdown("---")

    if tab_mode == "文生花字":
        # ── 风格描述输入框（绑定 key，用户输入直接存入 session_state）──
        st.markdown('<p style="color:#9fa8da;font-size:.82rem;margin:0 0 3px">风格描述</p>', unsafe_allow_html=True)
        # 每次 rerun 前先把 style_val 同步到 widget key（仅当外部修改时）
        if st.session_state.get("_sync_style_input", False):
            st.session_state["style_input_key"] = st.session_state.style_val
            st.session_state._sync_style_input = False
        elif "style_input_key" not in st.session_state:
            st.session_state["style_input_key"] = st.session_state.style_val
        style_inp = st.text_area("风格描述", height=68,
                                  placeholder="例：鎏金古风 / 赛博朋克 / 少女粉\n点下方词库挑词，或点随机一键生成",
                                  key="style_input_key",
                                  label_visibility="collapsed")

        # ── 生成按钮独占一行 ──
        gen_btn = st.button("▶ 开始生成", type="primary", use_container_width=True)

        # ── 两个随机按钮 ──
        rb1, rb2 = st.columns(2)
        with rb1:
            if st.button("🎲随机", use_container_width=True):
                st.session_state.style_val = "完全随机"
                st.session_state._full_rand_style = random.choice(RANDOM_STYLES)
                st.session_state._sync_style_input = True
                st.session_state.auto_gen = True
                st.rerun()
        with rb2:
            if st.button("🎰词库", use_container_width=True):
                rk = random.choice(ALL_VOCAB_KEYS)
                st.session_state.style_val = rk
                st.session_state._sync_style_input = True
                st.session_state.auto_gen = True
                st.rerun()

        st.markdown('<p style="color:#9fa8da;font-size:.82rem;margin:6px 0 3px">生成数量</p>', unsafe_allow_html=True)
        n_gen = st.number_input("生成数量", min_value=1, max_value=200, value=24, step=1, label_visibility="collapsed")
        st.markdown("---")
        res = st.session_state.results
        if res:
            sel = st.session_state.selected
            st.caption(f"已选 {len(sel)} / {len(res)}")
            c1,c2,c3 = st.columns(3)
            with c1:
                if st.button("全选", use_container_width=True): st.session_state.selected={r["idx"] for r in res}; st.rerun()
            with c2:
                if st.button("取消", use_container_width=True): st.session_state.selected=set(); st.rerun()
            with c3:
                if st.button("反选", use_container_width=True): st.session_state.selected={r["idx"] for r in res}-sel; st.rerun()
            st.markdown("---")
            picked = [r for r in res if r["idx"] in sel]
            if picked:
                st.download_button(f"下载 {len(picked)} 个", data=make_zip(picked,"img"),
                    file_name="花字包.zip", mime="application/zip", type="primary", use_container_width=True)
            else: st.info("先选中后下载")
    else:
        st.markdown('<p style="color:#9fa8da;font-size:.82rem;margin:0 0 6px">上传参考图（最多20张）</p>', unsafe_allow_html=True)
        uploaded = st.file_uploader("上传参考图", type=["png","jpg","jpeg","webp"],
                                     accept_multiple_files=True, label_visibility="collapsed")
        if uploaded and len(uploaded) > 20:
            uploaded = uploaded[:20]; st.warning("最多20张，已截取前20")
        analyze_btn = st.button("开始分析生成", type="primary", use_container_width=True)
        st.markdown("---")
        ires = st.session_state.img_results
        if ires:
            isel = st.session_state.img_selected
            st.caption(f"已选 {len(isel)} / {len(ires)}")
            a1,a2,a3 = st.columns(3)
            with a1:
                if st.button("全选 ", use_container_width=True): st.session_state.img_selected={r["idx"] for r in ires}; st.rerun()
            with a2:
                if st.button("取消 ", use_container_width=True): st.session_state.img_selected=set(); st.rerun()
            with a3:
                if st.button("反选 ", use_container_width=True): st.session_state.img_selected={r["idx"] for r in ires}-isel; st.rerun()
            st.markdown("---")
            picked2 = [r for r in ires if r["idx"] in isel]
            if picked2:
                st.download_button(f"下载 {len(picked2)} 个", data=make_zip(picked2,"render"),
                    file_name="图生花字包.zip", mime="application/zip", type="primary", use_container_width=True)

# ════════════════════════════════════════════════════════════════
# 主区域 — 文生花字
# ════════════════════════════════════════════════════════════════
if tab_mode == "文生花字":
    # style_inp 永远从文本框 key 读取（手动输入 + 按钮同步都走这里）
    style_inp = st.session_state.get("style_input_key", "") or st.session_state.style_val
    auto = st.session_state.get("auto_gen", False)
    if auto:
        st.session_state.auto_gen = False

    if (gen_btn or auto) and style_inp.strip():
        results = []; prog = st.progress(0); stat = st.empty()
        is_full_rand = (style_inp == "完全随机")
        # 完全随机时用真实风格字符串生成
        _actual_style = st.session_state.get("_full_rand_style", random.choice(RANDOM_STYLES)) if is_full_rand else style_inp
        for i in range(n_gen):
            eff = EFFECT_TYPES[i % len(EFFECT_TYPES)]
            seed = hash(_actual_style + str(i) + str(st.session_state.gen_rand)) % (2**31)
            if is_full_rand:
                nfo = build_info(_actual_style, eff, seed, force=True)
            else:
                nfo = build_info(style_inp, eff, seed, force=False)
            name = generate_name(nfo)
            stat.text(f"生成 {i+1}/{n_gen}…")
            try: img = render_to_pil(nfo)
            except Exception as e: st.warning(f"第{i+1}个失败: {e}"); continue
            results.append({"idx":i,"name":name,"info":nfo,"img":img})
            prog.progress((i+1)/n_gen)
        prog.empty(); stat.empty()
        st.session_state.results = results
        st.session_state.selected = {r["idx"] for r in results}
        st.session_state.tune_idx = None
        st.session_state.gen_rand = random.randint(0,999999)
        st.rerun()

    res = st.session_state.results
    if not res:
        st.markdown(HINT("在左侧输入风格，点击「开始生成」","不知道写什么？点「词库」挑词，或点「完全随机」/「词库随机」试试"), unsafe_allow_html=True)
    else:
        sel = st.session_state.selected
        CPR = 6
        for row in [res[i:i+CPR] for i in range(0,len(res),CPR)]:
            cols = st.columns(CPR)
            for col, r in zip(cols, row):
                with col:
                    is_s = r["idx"] in sel
                    border = "2px solid #7986cb;box-shadow:0 0 6px rgba(121,134,203,.4)" if is_s else "2px solid #2a2a3a"
                    b64 = img_to_b64(r["img"])
                    st.markdown(f"""<div style="background:#1e1e2e;border-radius:6px;padding:3px;margin-bottom:2px;border:{border}">
<img src="data:image/png;base64,{b64}" style="width:100%;border-radius:3px;display:block"/>
<div style="color:#7a7c9a;font-size:9px;text-align:center;margin-top:2px">{r['name']}</div></div>""", unsafe_allow_html=True)
                    ba, bb = st.columns(2)
                    with ba:
                        if st.button("已选" if is_s else "选中", key=f"s_{r['idx']}",
                                     use_container_width=True, type="primary" if is_s else "secondary"):
                            if is_s: st.session_state.selected.discard(r["idx"])
                            else: st.session_state.selected.add(r["idx"])
                            st.rerun()
                    with bb:
                        if st.button("调参", key=f"t_{r['idx']}", use_container_width=True):
                            st.session_state.results_tune_idx = r["idx"]; st.rerun()

    tidx = st.session_state.get("results_tune_idx")
    if tidx is not None and st.session_state.results:
        tune_dialog(tidx, st.session_state.results, "results", "img")

# ════════════════════════════════════════════════════════════════
# 主区域 — 图生花字
# ════════════════════════════════════════════════════════════════
else:
    if not st.session_state.img_results and not (uploaded and analyze_btn):
        st.markdown(HINT("在左侧上传参考图，点击「开始分析生成」","支持最多20张，自动提取颜色与描边参数"), unsafe_allow_html=True)

    if uploaded and analyze_btn:
        ires = []; prog = st.progress(0); stat = st.empty()
        for i, uf in enumerate(uploaded):
            stat.text(f"分析 {i+1}/{len(uploaded)}: {uf.name}")
            try:
                orig = Image.open(uf).convert("RGB")
                nfo = analyze_image_to_info(orig)
                name = generate_name(nfo)
                rend = render_to_pil(nfo)
                ires.append({"idx":i,"name":name,"info":nfo,"orig":orig,"render":rend})
            except Exception as e: st.warning(f"「{uf.name}」分析失败: {e}")
            prog.progress((i+1)/len(uploaded))
        prog.empty(); stat.empty()
        st.session_state.img_results = ires
        st.session_state.img_selected = {r["idx"] for r in ires}
        st.session_state.img_tune_idx = None
        st.rerun()

    ires = st.session_state.img_results
    if ires:
        isel = st.session_state.img_selected
        CPR = 3
        for row in [ires[i:i+CPR] for i in range(0,len(ires),CPR)]:
            cols = st.columns(CPR)
            for col, r in zip(cols, row):
                with col:
                    is_s = r["idx"] in isel
                    border = "2px solid #7986cb;box-shadow:0 0 6px rgba(121,134,203,.4)" if is_s else "2px solid #2a2a3a"
                    ob = img_to_b64(r["orig"].resize((280,280)))
                    rb = img_to_b64(r["render"])
                    st.markdown(f"""<div style="background:#1e1e2e;border-radius:6px;padding:4px;margin-bottom:3px;border:{border}">
<div style="display:flex;gap:3px">
<div style="flex:1;text-align:center"><img src="data:image/png;base64,{ob}" style="width:100%;border-radius:3px"/>
<div style="color:#606270;font-size:9px;margin-top:2px">参考图</div></div>
<div style="flex:1;text-align:center"><img src="data:image/png;base64,{rb}" style="width:100%;border-radius:3px"/>
<div style="color:#606270;font-size:9px;margin-top:2px">效果</div></div></div>
<div style="color:#7a7c9a;font-size:10px;text-align:center;margin-top:3px">{r['name']}</div></div>""", unsafe_allow_html=True)
                    ba, bb = st.columns(2)
                    with ba:
                        if st.button("已选" if is_s else "选中", key=f"is_{r['idx']}",
                                     use_container_width=True, type="primary" if is_s else "secondary"):
                            if is_s: st.session_state.img_selected.discard(r["idx"])
                            else: st.session_state.img_selected.add(r["idx"])
                            st.rerun()
                    with bb:
                        if st.button("调参 ", key=f"it_{r['idx']}", use_container_width=True):
                            st.session_state.img_tune_idx = r["idx"]; st.rerun()

    tidx = st.session_state.get("img_tune_idx")
    if tidx is not None and st.session_state.img_results:
        tune_dialog(tidx, st.session_state.img_results, "img", "render", orig_key="orig")
