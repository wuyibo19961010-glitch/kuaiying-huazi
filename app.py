#!/usr/bin/env python3
# coding=utf-8
"""
app.py — 文生花字生成器
运行: streamlit run python/app.py
"""

import sys, json, zipfile, random, io, copy
from pathlib import Path

import streamlit as st
from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from render_covers import render_cover as _render_cover

OUTPUT_DIR = Path("/tmp") / "huazi_output"

# ════════════════════════════════════════════════════════════════
# 颜色库（基于真实参考调色）
# ════════════════════════════════════════════════════════════════
COLOR_PALETTES = {
    "粉": [
        ("#ffd6e8", "#ff85b3", "#ff1f7d", "#7a0046", "#3a0020"),
        ("#ffe0f0", "#ffb3d9", "#ff69b4", "#c2185b", "#880e4f"),
        ("#fce4ec", "#f48fb1", "#e91e63", "#880e4f", "#3e0026"),
        ("#fff0f5", "#ffadd2", "#f50057", "#9e003a", "#4a001a"),
    ],
    "金": [
        ("#fffdd1", "#ffc86e", "#c87e2a", "#7a4a00", "#402a00"),
        ("#fff9c4", "#ffee58", "#fdd835", "#f9a825", "#4e2900"),
        ("#fff8e1", "#ffe082", "#ffb300", "#e65100", "#3e1500"),
        ("#fffff0", "#ffe66d", "#ffa500", "#cc7000", "#4e2900"),
    ],
    "蓝": [
        ("#6098fe", "#006df4", "#021eaa", "#00118a", "#000051"),
        ("#e3f2fd", "#90caf9", "#2196f3", "#0d47a1", "#001a57"),
        ("#63aeff", "#1a78ff", "#0033cc", "#001a88", "#000040"),
        ("#c9e8ff", "#5ec5ff", "#1a8fff", "#005bcc", "#001f66"),
    ],
    "紫": [
        ("#f3e5f5", "#ce93d8", "#9c27b0", "#4a148c", "#1a0033"),
        ("#ede7f6", "#b39ddb", "#673ab7", "#311b92", "#12005e"),
        ("#bb66ff", "#8833cc", "#5500aa", "#330066", "#1a0033"),
        ("#e8d5ff", "#c080ff", "#8000ff", "#5000cc", "#200055"),
    ],
    "红": [
        ("#ffebee", "#ef9a9a", "#f44336", "#b71c1c", "#4a0000"),
        ("#ff8a80", "#ff1744", "#d50000", "#9b0000", "#4a0000"),
        ("#ff6b6b", "#ee0000", "#aa0000", "#660000", "#330000"),
        ("#ffd0d0", "#ff6666", "#cc0000", "#880000", "#440000"),
    ],
    "绿": [
        ("#e8f5e9", "#a5d6a7", "#4caf50", "#1b5e20", "#002200"),
        ("#ccff90", "#76ff03", "#1b5e20", "#003300", "#001500"),
        ("#e0f2f1", "#80cbc4", "#009688", "#004d40", "#001a17"),
    ],
    "橙": [
        ("#fff3e0", "#ffcc80", "#ff9800", "#e65100", "#4e1a00"),
        ("#ffd180", "#ff6d00", "#dd2c00", "#8d1000", "#3e0500"),
        ("#ffe0b2", "#ff8f00", "#e65100", "#bf360c", "#3e0000"),
    ],
    "青": [
        ("#e0f7fa", "#80deea", "#00bcd4", "#006064", "#00212a"),
        ("#b2ebf2", "#4dd0e1", "#0097a7", "#004d57", "#001c21"),
    ],
    "黑白": [
        ("#ffffff", "#e0e0e0", "#9e9e9e", "#424242", "#000000"),
        ("#ffffff", "#cccccc", "#666666", "#222222", "#000000"),
    ],
}

STYLE_COLOR_MAP = {
    "粉": ["粉"], "少女": ["粉"], "可爱": ["粉"], "甜": ["粉"], "玫": ["粉"], "桃": ["粉"],
    "樱": ["粉"], "浪漫": ["粉", "紫"], "梦幻": ["粉", "紫"],
    "金": ["金"], "贵": ["金"], "豪华": ["金"], "奢": ["金"], "鎏金": ["金"],
    "华丽": ["金", "紫"], "古风": ["金", "紫"], "国风": ["金", "紫"],
    "蓝": ["蓝"], "科技": ["蓝", "青"], "冷": ["蓝", "青"], "未来": ["蓝", "青"],
    "赛博": ["蓝", "紫"], "电子": ["蓝", "青"],
    "紫": ["紫"], "神秘": ["紫"], "魔法": ["紫", "粉"],
    "红": ["红"], "热血": ["红", "橙"], "喜庆": ["红"], "危险": ["红"],
    "火": ["红", "橙"], "热情": ["红", "橙"],
    "绿": ["绿"], "清新": ["绿", "青"], "自然": ["绿"], "森林": ["绿"],
    "橙": ["橙"], "活力": ["橙", "红"], "夏日": ["橙", "粉"],
    "青": ["青"], "清爽": ["青", "绿"], "海洋": ["青", "蓝"],
    "黑": ["黑白"], "白": ["黑白"], "简约": ["黑白"], "极简": ["黑白"],
    "经典": ["黑白", "金"],
}

EFFECT_TYPES = [
    "霓虹发光", "厚描边", "3D立体", "浮雕",
    "双色渐变", "多层描边", "错位投影", "简约",
]

CONFIG_JSON = {"animationPath": "animation.json", "stylePath": "info.json", "type": "template", "version": "1"}
ANIMATION_JSON = []


# ════════════════════════════════════════════════════════════════
# 颜色工具
# ════════════════════════════════════════════════════════════════
def darken(h: str, f: float = 0.4) -> str:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{max(0,int(r*f)):02x}{max(0,int(g*f)):02x}{max(0,int(b*f)):02x}"

def lighten(h: str, f: float = 1.5) -> str:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{min(255,int(r*f)):02x}{min(255,int(g*f)):02x}{min(255,int(b*f)):02x}"

def pick_colors(style_desc: str, rng: random.Random):
    matched = []
    for kw, color_keys in STYLE_COLOR_MAP.items():
        if kw in style_desc:
            matched.extend(color_keys)
    if not matched:
        matched = list(COLOR_PALETTES.keys())
    key = rng.choice(list(set(matched)))
    return rng.choice(COLOR_PALETTES[key])


# ════════════════════════════════════════════════════════════════
# 参数生成引擎（基于知识库 v3 真实数值）
# ════════════════════════════════════════════════════════════════
def build_info(style_desc: str, effect_type: str, seed: int) -> dict:
    rng = random.Random(seed)
    c0, c1, c2, c3, c4 = pick_colors(style_desc, rng)

    # gradientIndex=0 → 文字主体用渐变（text_color 被覆盖，无需单独设置）
    info = {
        "text_color": c0,
        "colorgradient": [],
        "gradientIndex": 0,
        "gradientDegree": 90.0001,
        "stroke": [],
        "shadows": [],
        "innerShadows": [],
        "multi_text_layer": [],
        "thickness": 0.0001,
    }

    if effect_type == "霓虹发光":
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": c0},
            {"anchor": 1.0, "color": c1},
        ]}]
        info["stroke"] = [
            {"color": darken(c2, 0.3), "width": rng.uniform(2.3, 3.2)},
            {"color": c2, "width": rng.uniform(6.4, 9.6)},
        ]
        n_glow = rng.randint(3, 6)
        base = rng.uniform(0.4, 0.6)
        info["shadows"] = [
            {"color": c1, "intensity": max(0.04, base - i * 0.06), "shift": {}}
            for i in range(n_glow)
        ]
        info["shadows"].append({
            "color": darken(c2, 0.5),
            "intensity": rng.uniform(0.35, 0.6),
            "shift": {"x": 0, "y": rng.randint(6, 12)},
        })

    elif effect_type == "厚描边":
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": lighten(c0, 1.3)},
            {"anchor": 1.0, "color": c1},
        ]}]
        info["stroke"] = [
            {"color": darken(c2, 0.3), "width": rng.uniform(2.3, 3.8)},
            {"color": c2,              "width": rng.uniform(7.0, 11.2)},
            {"color": lighten(c0, 1.6),"width": rng.uniform(13.0, 17.6)},
        ]
        info["innerShadows"] = [
            {"color": lighten(c0, 1.8), "intensity": rng.uniform(1.0, 3.0),
             "shift": {"x": 0, "y": rng.randint(1, 3)}},
        ]

    elif effect_type == "3D立体":
        info["thickness"] = 1.6   # 加大，让3D感更明显
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": lighten(c0, 1.4)},
            {"anchor": 1.0, "color": c2},
        ]}]
        info["stroke"] = [
            {"color": darken(c3, 0.4), "width": rng.uniform(2.4, 3.5)},
            {"color": c2,              "width": rng.uniform(8.0, 11.2)},
            {"color": c1,              "width": rng.uniform(14.4, 18.0)},
            {"color": lighten(c0, 1.8),"width": rng.uniform(22.4, 28.0)},
        ]
        info["innerShadows"] = [
            {"color": lighten(c0, 2.0), "intensity": rng.uniform(4.0, 8.0),
             "shift": {"x": 0, "y": rng.randint(2, 4)}},
        ]

    elif effect_type == "浮雕":
        info["thickness"] = rng.choice([0.8, 1.2])
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": lighten(c0, 1.3)},
            {"anchor": 0.5, "color": c1},
            {"anchor": 1.0, "color": c2},
        ]}]
        info["stroke"] = [
            {"color": darken(c3, 0.3), "width": rng.uniform(2.0, 3.2)},
            {"color": c2,              "width": rng.uniform(7.0, 11.2)},
            {"color": c1,              "width": rng.uniform(13.0, 16.0)},
            {"color": lighten(c0, 1.5),"width": rng.uniform(17.6, 22.4)},
        ]
        info["innerShadows"] = [
            {"color": lighten(c0, 2.2), "intensity": rng.uniform(3.0, 6.0),
             "shift": {"x": 0, "y": rng.randint(1, 4)}},
        ]
        info["shadows"] = [
            {"color": c1, "intensity": rng.uniform(0.3, 0.5), "shift": {}},
        ]

    elif effect_type == "双色渐变":
        all_keys = list(COLOR_PALETTES.keys())
        alt_key = rng.choice(all_keys)
        alt_c = rng.choice(COLOR_PALETTES[alt_key])
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": c0},
            {"anchor": 0.5, "color": c1},
            {"anchor": 1.0, "color": alt_c[2]},
        ]}]
        info["gradientDegree"] = rng.choice([90.0001, 45.0, 0.0001])
        info["stroke"] = [
            {"color": darken(c2, 0.3), "width": rng.uniform(2.3, 3.5)},
            {"color": c2,              "width": rng.uniform(8.0, 12.8)},
        ]
        info["shadows"] = [
            {"color": c1, "intensity": rng.uniform(0.3, 0.5), "shift": {}},
        ]

    elif effect_type == "多层描边":
        n = rng.randint(4, 5)
        widths = [rng.uniform(2.3, 4.0), rng.uniform(7.0, 11.2),
                  rng.uniform(12.8, 16.0), rng.uniform(18.0, 22.4),
                  rng.uniform(24.0, 28.0)]
        colors = [darken(c4, 0.4), c3, c2, c1, lighten(c0, 1.5)]
        info["stroke"] = [{"color": colors[i], "width": widths[i]} for i in range(n)]
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": lighten(c0, 1.3)},
            {"anchor": 1.0, "color": c1},
        ]}]
        info["innerShadows"] = [
            {"color": lighten(c0, 1.8), "intensity": rng.uniform(0.5, 2.0),
             "shift": {"x": 0, "y": 2}},
        ]

    elif effect_type == "错位投影":
        ox = rng.choice([-14.4, -11.2, 11.2, 14.4])
        oy = rng.choice([-14.4, -11.2, 11.2, 14.4])
        info["multi_text_layer"] = [{
            "color": darken(c2, 0.5),
            "offset_x": ox,
            "offset_y": oy,
            "alpha": 255,
            "gradientIndex": -1,
            "BlendMode": 0,
            "fullfillBias": {},
        }]
        info["stroke"] = [
            {"color": darken(c1, 0.3), "width": rng.uniform(2.3, 3.5)},
            {"color": c1,              "width": rng.uniform(9.6, 12.8)},
        ]
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": c0},
            {"anchor": 1.0, "color": c1},
        ]}]

    elif effect_type == "简约":
        info["colorgradient"] = [{"lineargradient": [
            {"anchor": 0.0, "color": lighten(c0, 1.2)},
            {"anchor": 1.0, "color": c2},
        ]}]
        info["stroke"] = [
            {"color": darken(c1, 0.4), "width": rng.uniform(2.3, 4.0)},
            {"color": c1,              "width": rng.uniform(7.0, 11.2)},
        ]
        info["shadows"] = [
            {"color": c1, "intensity": rng.uniform(0.2, 0.4), "shift": {}},
        ]

    return info


# ════════════════════════════════════════════════════════════════
# 渲染工具
# ════════════════════════════════════════════════════════════════
def render_to_pil(info: dict) -> Image.Image:
    tmp_path = Path("/tmp") / "_tmp_render.webp"
    _render_cover(info, str(tmp_path))
    return Image.open(tmp_path).copy()

def simple_name(idx: int, effect_type: str) -> str:
    return f"{effect_type}{idx:03d}"


# ════════════════════════════════════════════════════════════════
# Streamlit 界面
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="文生花字", page_icon="🎨", layout="wide")

# ── 暗色主题 CSS（蓝紫系）──────────────────────────────────────
st.markdown("""
<style>
/* 隐藏顶部白色工具栏 */
header[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }
.stDeployButton { display: none !important; }

/* 整体背景：深灰近黑 */
.stApp { background-color: #16161e; color: #c8cad4; }
.block-container { padding-top: 1.5rem !important; }

/* 侧栏 */
section[data-testid="stSidebar"] { background-color: #0f0f17; border-right: 1px solid #2a2a3a; }
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span { color: #a0a2b0 !important; }

/* 输入框 */
textarea, input[type="text"], input[type="number"] {
    background-color: #1e1e2e !important;
    color: #c8cad4 !important;
    border: 1px solid #3a3a5a !important;
    border-radius: 6px !important;
}

/* 主按钮：蓝紫色，强制白色文字 */
button[kind="primary"],
button[kind="primary"] p,
button[kind="primary"] span {
    background: #5c6bc0 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 6px !important;
}
button[kind="primary"]:hover { background: #7986cb !important; }

/* 次要按钮 */
button[kind="secondary"] {
    background: #1e1e2e !important;
    color: #a0a2b0 !important;
    border: 1px solid #3a3a5a !important;
    border-radius: 6px !important;
}
button[kind="secondary"]:hover { border-color: #5c6bc0 !important; color: #c8cad4 !important; }

/* 下载按钮文字强制白色 */
[data-testid="stDownloadButton"] button,
[data-testid="stDownloadButton"] button p,
[data-testid="stDownloadButton"] button span {
    color: #ffffff !important;
}

/* caption */
.stCaptionContainer p { color: #606270 !important; font-size: 11px !important; }

/* 分割线 */
hr { border-color: #2a2a3a !important; }

/* 进度条 */
.stProgress > div > div { background-color: #5c6bc0 !important; }

/* 下载按钮 */
[data-testid="stDownloadButton"] button {
    background: #5c6bc0 !important;
    color: #fff !important;
    border: none !important;
}
</style>
""", unsafe_allow_html=True)

# ── 左侧栏：输入 + 操作 ───────────────────────────────────────
with st.sidebar:
    st.markdown('<h1 style="color:#ffffff; font-size:1.4rem; margin-bottom:0.5rem;">🎨 文生花字</h1>', unsafe_allow_html=True)
    style_input = st.text_area(
        "风格描述",
        value="少女风格、粉色系、可爱甜美",
        height=80,
        placeholder="例：鎏金古风 / 赛博蓝 / 危险红光 / 少女粉",
    )
    n_items = st.number_input("生成数量", min_value=1, max_value=200, value=18, step=1)
    generate_btn = st.button("开始生成", type="primary", use_container_width=True)
    st.markdown("---")

    # 选择操作
    if st.session_state.get("results"):
        results = st.session_state.results
        n_sel = len(st.session_state.get("selected", set()))
        st.caption(f"已选 {n_sel} / {len(results)}")
        c1b, c2b, c3b = st.columns(3)
        with c1b:
            if st.button("全选", use_container_width=True):
                st.session_state.selected = {r["idx"] for r in results}
                st.rerun()
        with c2b:
            if st.button("取消", use_container_width=True):
                st.session_state.selected = set()
                st.rerun()
        with c3b:
            if st.button("反选", use_container_width=True):
                all_idx = {r["idx"] for r in results}
                st.session_state.selected = all_idx - st.session_state.get("selected", set())
                st.rerun()

        st.markdown("---")
        selected_results = [r for r in results if r["idx"] in st.session_state.get("selected", set())]
        if selected_results:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for r in selected_results:
                    folder = r["name"]
                    zf.writestr(f"{folder}/config.json",
                                json.dumps(CONFIG_JSON, ensure_ascii=False, indent=4))
                    zf.writestr(f"{folder}/info.json",
                                json.dumps(r["info"], ensure_ascii=False, indent=4))
                    zf.writestr(f"{folder}/animation.json",
                                json.dumps(ANIMATION_JSON, ensure_ascii=False, indent=4))
                    img_buf = io.BytesIO()
                    r["img"].save(img_buf, "WEBP", quality=92)
                    zf.writestr(f"{folder}/{folder}.webp", img_buf.getvalue())
                    inner_buf = io.BytesIO()
                    with zipfile.ZipFile(inner_buf, "w") as izf:
                        izf.writestr("config.json", json.dumps(CONFIG_JSON, ensure_ascii=False, indent=4))
                        izf.writestr("info.json",   json.dumps(r["info"], ensure_ascii=False, indent=4))
                        izf.writestr("animation.json", json.dumps(ANIMATION_JSON, ensure_ascii=False, indent=4))
                    zf.writestr(f"{folder}/output.zip", inner_buf.getvalue())

            st.download_button(
                label=f"下载选中的 {len(selected_results)} 个",
                data=zip_buf.getvalue(),
                file_name="花字包.zip",
                mime="application/zip",
                width='stretch',
                type="primary",
            )
        else:
            st.info("点击图片选择后下载")

# ── session state 初始化 ──────────────────────────────────────
for k, v in [("results", []), ("selected", set()), ("tune_idx", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── 生成逻辑 ─────────────────────────────────────────────────
if generate_btn and style_input.strip():
    results = []
    progress = st.progress(0)
    status = st.empty()
    for i in range(n_items):
        effect = EFFECT_TYPES[i % len(EFFECT_TYPES)]
        seed = hash(style_input + str(i)) % (2 ** 31)
        info = build_info(style_input, effect, seed)
        name = simple_name(i + 1, effect)
        status.text(f"生成 {i+1}/{n_items}…")
        try:
            img = render_to_pil(info)
            results.append({"idx": i, "name": name, "info": info, "img": img, "effect": effect})
        except Exception as e:
            st.warning(f"第{i+1}个失败: {e}")
        progress.progress((i + 1) / n_items)
    st.session_state.results = results
    st.session_state.selected = {r["idx"] for r in results}  # 默认全选
    st.session_state.tune_idx = None
    status.empty()
    progress.empty()
    st.rerun()

# ── 主区域：图片网格 ─────────────────────────────────────────
if not st.session_state.results:
    st.markdown("""
<div style="display:flex; flex-direction:column; align-items:center; justify-content:center;
            height:60vh; color:#3a3a5a; text-align:center;">
  <div style="font-size:3rem;">←</div>
  <div style="font-size:1.1rem; margin-top:0.5rem; color:#4a4a6a;">在左侧输入风格描述，点击「开始生成」</div>
</div>
""", unsafe_allow_html=True)
if st.session_state.results:
    results = st.session_state.results
    selected = st.session_state.selected

    cols_per_row = 6
    rows = [results[i:i+cols_per_row] for i in range(0, len(results), cols_per_row)]

    from PIL import ImageDraw as _ID
    import base64

    def img_to_b64(img):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()

    for row in rows:
        cols = st.columns(cols_per_row)
        for col, r in zip(cols, row):
            with col:
                is_selected = r["idx"] in selected
                border_css = "2px solid #7986cb; box-shadow: 0 0 10px rgba(121,134,203,0.45);" if is_selected else "2px solid #2a2a3a;"
                b64 = img_to_b64(r["img"])
                st.markdown(f"""
<div style="background:#1e1e2e; border-radius:8px; padding:6px; margin-bottom:4px; border:{border_css}">
  <img src="data:image/png;base64,{b64}" style="width:100%; border-radius:4px; display:block;"/>
  <div style="color:#606270; font-size:11px; text-align:center; margin-top:4px;">{r['name']}</div>
</div>
""", unsafe_allow_html=True)
                ba, bb = st.columns(2)
                with ba:
                    if st.button(
                        "已选" if is_selected else "选中",
                        key=f"sel_{r['idx']}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                    ):
                        if is_selected:
                            st.session_state.selected.discard(r["idx"])
                        else:
                            st.session_state.selected.add(r["idx"])
                        st.rerun()
                with bb:
                    if st.button("调参", key=f"tune_{r['idx']}", use_container_width=True):
                        st.session_state.tune_idx = r["idx"]
                        st.rerun()

# ── 调参弹窗（用 st.dialog）─────────────────────────────────
if st.session_state.get("tune_idx") is not None:
    tidx = st.session_state.tune_idx
    tr = next((r for r in st.session_state.results if r["idx"] == tidx), None)

    if tr:
        @st.dialog(f"调参 — {tr['name']}（{tr['effect']}）", width="large")
        def tune_dialog():
            info = copy.deepcopy(tr["info"])
            left, right = st.columns([3, 1])

            with left:
                # ── 渐变颜色 ──────────────────────────────
                grad = info.get("colorgradient") or []
                if grad and grad[0].get("lineargradient"):
                    stops = grad[0]["lineargradient"]
                    st.markdown("**渐变颜色**")
                    ga, gb, gc_ = st.columns(3)
                    with ga:
                        gc1 = st.color_picker("起色", stops[0]["color"], key=f"gc1_{tidx}")
                    mid_stops = [s for s in stops if 0 < s["anchor"] < 1]
                    if mid_stops:
                        with gb:
                            gcm = st.color_picker("中间色", mid_stops[0]["color"], key=f"gcm_{tidx}")
                        with gc_:
                            gc2 = st.color_picker("终色", stops[-1]["color"], key=f"gc2_{tidx}")
                        new_stops = [{"anchor": 0.0, "color": gc1},
                                     {"anchor": 0.5, "color": gcm},
                                     {"anchor": 1.0, "color": gc2}]
                    else:
                        with gb:
                            gc2 = st.color_picker("终色", stops[-1]["color"], key=f"gc2_{tidx}")
                        new_stops = [{"anchor": 0.0, "color": gc1},
                                     {"anchor": 1.0, "color": gc2}]
                    info["colorgradient"] = [{"lineargradient": new_stops}]

                    deg_map = {"从上到下": 90.0001, "从左到右": 0.0001, "斜45度": 45.0}
                    cur_deg = info.get("gradientDegree", 90.0001)
                    cur_label = min(deg_map, key=lambda k: abs(deg_map[k] - cur_deg))
                    sel_deg = st.radio("渐变方向", list(deg_map.keys()),
                                       index=list(deg_map.keys()).index(cur_label),
                                       horizontal=True, key=f"gd_{tidx}")
                    info["gradientDegree"] = deg_map[sel_deg]

                # ── 描边 ──────────────────────────────────
                strokes = list(info.get("stroke") or [])
                if strokes:
                    st.markdown("**描边（从内到外）**")
                    n_stroke = st.slider("描边层数", 1, 5, len(strokes), key=f"ns_{tidx}")
                    while len(strokes) < n_stroke:
                        strokes.append(copy.deepcopy(strokes[-1]))
                    new_strokes = []
                    for si in range(n_stroke):
                        sa, sb = st.columns([2, 1])
                        with sa:
                            sw = st.slider(f"第{si+1}层宽度", 1.0, 30.0,
                                           float(strokes[si].get("width", 5.0)),
                                           step=0.8, key=f"sw_{tidx}_{si}")
                        with sb:
                            sc = st.color_picker(f"第{si+1}层颜色",
                                                 strokes[si].get("color", "#ffffff"),
                                                 key=f"sc_{tidx}_{si}")
                        new_strokes.append({"color": sc, "width": sw})
                    info["stroke"] = new_strokes

                # ── 外发光 ────────────────────────────────
                shadows = list(info.get("shadows") or [])
                if shadows:
                    st.markdown("**外发光**")
                    fa, fb = st.columns(2)
                    with fa:
                        gi = st.slider("强度", 0.04, 0.8,
                                       float(min(shadows[0].get("intensity", 0.5), 0.8)),
                                       step=0.04, key=f"gi_{tidx}")
                    with fb:
                        gc = st.color_picker("颜色", shadows[0].get("color", "#ffffff"),
                                             key=f"gcolor_{tidx}")
                    for s in info["shadows"]:
                        s["intensity"] = gi
                        s["color"] = gc

                # ── 内阴影 ────────────────────────────────
                inner = list(info.get("innerShadows") or [])
                if inner:
                    st.markdown("**内高光**")
                    ia, ib, ic = st.columns(3)
                    with ia:
                        ii = st.slider("强度", 0.5, 8.0,
                                       float(min(inner[0].get("intensity", 2.0), 8.0)),
                                       step=0.5, key=f"ii_{tidx}")
                    with ib:
                        ic_col = st.color_picker("颜色", inner[0].get("color", "#ffffff"),
                                                 key=f"icolor_{tidx}")
                    with ic:
                        iy = st.slider("Y偏移", 0, 8,
                                       int(inner[0].get("shift", {}).get("y", 2)),
                                       key=f"iy_{tidx}")
                    for s in info["innerShadows"]:
                        s["intensity"] = ii
                        s["color"] = ic_col
                        s["shift"] = {"x": 0, "y": iy}

                # ── 错位投影 ──────────────────────────────
                multi = list(info.get("multi_text_layer") or [])
                if multi:
                    st.markdown("**错位投影**")
                    ma, mb, mc = st.columns(3)
                    with ma:
                        mx = st.slider("X偏移", -20.0, 20.0,
                                       float(multi[0].get("offset_x", 14.4)),
                                       step=1.6, key=f"mx_{tidx}")
                    with mb:
                        my = st.slider("Y偏移", -20.0, 20.0,
                                       float(multi[0].get("offset_y", 14.4)),
                                       step=1.6, key=f"my_{tidx}")
                    with mc:
                        mc_col = st.color_picker("投影颜色", multi[0].get("color", "#000000"),
                                                 key=f"mc_{tidx}")
                    info["multi_text_layer"] = [{
                        **multi[0], "offset_x": mx, "offset_y": my, "color": mc_col
                    }]

                # ── 3D厚度 ────────────────────────────────
                st.markdown("**3D厚度**")
                thick_map = {"平面": 0.0001, "轻微": 0.8, "明显": 1.6, "夸张": 2.5}
                cur_thick = info.get("thickness", 0.0001)
                cur_tlabel = min(thick_map, key=lambda k: abs(thick_map[k] - cur_thick))
                sel_thick = st.radio("厚度", list(thick_map.keys()),
                                     index=list(thick_map.keys()).index(cur_tlabel),
                                     horizontal=True, key=f"thick_{tidx}")
                info["thickness"] = thick_map[sel_thick]

            with right:
                try:
                    st.image(render_to_pil(info), caption="预览", use_container_width=True)
                except Exception as e:
                    st.error(f"预览失败: {e}")

                if st.button("应用", key=f"apply_{tidx}", use_container_width=True, type="primary"):
                    for r in st.session_state.results:
                        if r["idx"] == tidx:
                            r["info"] = info
                            try:
                                r["img"] = render_to_pil(info)
                            except Exception:
                                pass
                    st.session_state.tune_idx = None
                    st.rerun()

                if st.button("关闭", key=f"close_{tidx}", use_container_width=True):
                    st.session_state.tune_idx = None
                    st.rerun()

        tune_dialog()
