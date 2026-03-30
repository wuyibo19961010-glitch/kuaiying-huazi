#!/usr/bin/env python3
# coding=utf-8
"""
style_matcher.py — 风格库最近邻匹配（v15）

v14 改进：
  1. 特征向量增加结构维度（发光强度/边缘软硬/外围亮度/颜色复杂度/径向梯度）
     → 让霓虹发光样本和普通描边样本在结构上拉开距离，避免纯粹按颜色错配

v15 改进（核心修复）：
  颜色替换策略从"HSV 距离最近色"改为"排名对应（rank-based）"：
  - 新图各区域调色板按像素占比排序（主色第一）
  - 原样本第 i 个颜色位置 → 新调色板第 i 个颜色（循环取余）
  - 完全不依赖原始颜色的 HSV 值，彻底解决白色 text_color 在含白色高光
    的调色板中"自我映射"回白色而非粉色等新图主色的角色颠倒问题

  分层策略保持 v14 的区域划分：
    - text_color / colorgradient → text_palette（文字区主色）
    - stroke 层 → stroke_palette（描边区主色）
    - shadows 层 → glow_palette（外围发光区主色）
    - innerShadows 层 → text_palette（内阴影贴近文字区）
    - multi_text_layer → full_palette
"""
import os
import json
import copy
import pickle
import colorsys
import numpy as np
from PIL import Image, ImageFilter

# ──────────────────────────────────────────────────────────────
# 路径常量
# ──────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STYLE_BASE = os.path.join(_THIS_DIR, "..", "..", "参考汇总")
STYLE_BASE = os.path.normpath(STYLE_BASE)
FLOWER_RESULTS = os.path.join(_THIS_DIR, "..", "花字输出结果")
FLOWER_RESULTS = os.path.normpath(FLOWER_RESULTS)
INDEX_PATH     = os.path.join(_THIS_DIR, "style_index.pkl")

# ──────────────────────────────────────────────────────────────
# 颜色工具
# ──────────────────────────────────────────────────────────────
def hex_to_rgb(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

def rgb_to_hsv(r, g, b):
    r_, g_, b_ = r/255.0, g/255.0, b/255.0
    h, s, v = colorsys.rgb_to_hsv(r_, g_, b_)
    return h*360, s*255, v*255

def hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h/360.0, s/255.0, v/255.0)
    return int(r*255), int(g*255), int(b*255)

def hue_dist(h1, h2):
    """色相循环距离 0~180"""
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)

def color_luminance(r, g, b):
    return 0.299*r + 0.587*g + 0.114*b

def color_saturation(r, g, b):
    mx, mn = max(r,g,b), min(r,g,b)
    return (mx - mn) / mx if mx > 0 else 0

# 标准封面蒙版路径（白色=主体字区域，黑色=外围区域）
MASK_PATH = os.path.join(_THIS_DIR, "..", "字体资源", "标准封面.png")
MASK_PATH = os.path.normpath(MASK_PATH)

_mask_cache = None

def _get_text_mask(size: tuple) -> np.ndarray:
    """
    返回主体字蒙版（float32，0~1），已缩放到指定 size=(W,H)。
    白色区域=主体字=1.0，黑色区域=外围=0.0。
    """
    global _mask_cache
    if _mask_cache is None or _mask_cache[0] != size:
        if os.path.exists(MASK_PATH):
            mask_img = Image.open(MASK_PATH).convert('L').resize(size, Image.LANCZOS)
            arr = np.array(mask_img, dtype=np.float32) / 255.0
        else:
            arr = np.zeros((size[1], size[0]), dtype=np.float32)
            h, w = size[1], size[0]
            arr[int(h*0.31):int(h*0.67), int(w*0.15):int(w*0.85)] = 1.0
        _mask_cache = (size, arr)
    return _mask_cache[1]


# ──────────────────────────────────────────────────────────────
# 特征提取（v14：颜色 25 维 + 结构 5 维 = 30 维）
# ──────────────────────────────────────────────────────────────
def extract_features(img: Image.Image, n_colors: int = 6) -> np.ndarray:
    """
    从图像提取特征向量（用于风格匹配）。

    特征维度：
      颜色特征（25维，与 v13 相同）：
      - 主色1~6 的 HSV（6×3=18维）
      - 亮度均值/方差（2维）
      - 饱和度均值/方差（2维）
      - 暗色占比/亮色占比/彩色占比（3维）
      结构特征（5维，v14新增）：
      - glow_score: 外围区域的中高亮度像素占比（检测发光/霓虹）
      - edge_softness: 文字边缘的梯度平滑度（软边缘=发光，硬边缘=描边）
      - outer_brightness: 外围区域平均亮度（发光样本外围更亮）
      - color_complexity: 有效颜色簇数量（归一化）
      - radial_gradient: 从文字区到外围的亮度衰减率
    共 30 维
    """
    SIZE = (120, 120)
    img_rgb = img.convert("RGB").resize(SIZE, Image.LANCZOS)
    arr_2d = np.array(img_rgb).astype(float)   # (H, W, 3)
    arr = arr_2d.reshape(-1, 3)                 # (H*W, 3)

    # 过滤背景色（接近 #1a1a1a 的暗灰色）
    bg_mask = (arr[:, 0] < 50) & (arr[:, 1] < 50) & (arr[:, 2] < 50)
    foreground = arr[~bg_mask]
    if len(foreground) < 20:
        foreground = arr

    # K-means 聚类提取主色
    from sklearn.cluster import MiniBatchKMeans
    n = min(n_colors, len(foreground))
    kmeans = MiniBatchKMeans(n_clusters=n, random_state=42, n_init=3)
    kmeans.fit(foreground)

    labels = kmeans.labels_
    centers = kmeans.cluster_centers_
    counts = np.bincount(labels, minlength=n)
    order = np.argsort(-counts)
    top_colors = centers[order]

    # ── 颜色特征（18维 HSV + 7维统计 = 25维）──
    hsv_feats = []
    for i in range(n_colors):
        if i < len(top_colors):
            r, g, b = top_colors[i]
            h, s, v = rgb_to_hsv(r, g, b)
            hsv_feats.extend([h/360.0, s/255.0, v/255.0])
        else:
            hsv_feats.extend([0, 0, 0])

    lums = 0.299*foreground[:,0] + 0.587*foreground[:,1] + 0.114*foreground[:,2]
    mx = foreground.max(axis=1); mn = foreground.min(axis=1)
    sats = np.where(mx > 0, (mx-mn)/mx, 0)

    lum_mean = float(lums.mean()) / 255.0
    lum_std  = float(lums.std())  / 255.0
    sat_mean = float(sats.mean())
    sat_std  = float(sats.std())
    dark_ratio    = float((lums < 60).mean())
    bright_ratio  = float((lums > 200).mean())
    colorful_ratio = float((sats > 0.3).mean())

    # ── 结构特征（5维，v14新增）──
    mask = _get_text_mask(SIZE)  # (H, W) 0~1

    # 各区域亮度
    lum_2d = 0.299*arr_2d[:,:,0] + 0.587*arr_2d[:,:,1] + 0.114*arr_2d[:,:,2]
    text_lum = lum_2d[mask > 0.5]
    outer_lum = lum_2d[mask < 0.3]

    # 1) glow_score: 外围区域中高亮度（>40）像素占比
    #    纯描边/普通样本外围几乎全黑, 霓虹/发光样本外围有漫射光
    if len(outer_lum) > 0:
        glow_score = float((outer_lum > 40).mean())
    else:
        glow_score = 0.0

    # 2) edge_softness: 图像梯度在蒙版边缘区域的平均值
    #    发光效果有柔和渐变，描边效果有锐利边缘
    gray = img_rgb.convert('L')
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges, dtype=float)
    edge_zone = (mask > 0.2) & (mask < 0.8)  # 蒙版边缘过渡区
    if edge_zone.sum() > 0:
        edge_vals = edge_arr[edge_zone]
        # 高值=锐利边缘, 低值=软边缘; 归一化到 0~1
        edge_softness = 1.0 - min(float(edge_vals.mean()) / 120.0, 1.0)
    else:
        edge_softness = 0.5

    # 3) outer_brightness: 外围区域平均亮度（归一化 0~1）
    outer_brightness = float(outer_lum.mean()) / 255.0 if len(outer_lum) > 0 else 0.0

    # 4) color_complexity: 占比 > 5% 的有效颜色簇数量（归一化到 0~1）
    ratios = counts[order].astype(float) / counts.sum()
    effective_colors = int((ratios > 0.05).sum())
    color_complexity = effective_colors / n_colors  # 0~1

    # 5) radial_gradient: 文字区亮度 vs 外围亮度的比值差
    #    有偏移阴影/立体感的样本会有明显的方向性亮度差
    text_mean_lum = float(text_lum.mean()) / 255.0 if len(text_lum) > 0 else 0.5
    radial_gradient = max(0.0, text_mean_lum - outer_brightness)

    feat = np.array(
        hsv_feats + [lum_mean, lum_std, sat_mean, sat_std,
                     dark_ratio, bright_ratio, colorful_ratio,
                     glow_score, edge_softness, outer_brightness,
                     color_complexity, radial_gradient],
        dtype=np.float32
    )
    return feat


def feature_distance(f1: np.ndarray, f2: np.ndarray) -> float:
    """
    加权特征距离（v14）。
    颜色维度用循环色相距离 + 加权；
    结构维度单独加权（权重更高，确保结构相似优先）。
    """
    n_colors = 6
    d = 0.0

    # ── 前 18 维：主色 HSV（每3个一组）──
    for i in range(n_colors):
        base = i * 3
        h1, s1, v1 = f1[base], f1[base+1], f1[base+2]
        h2, s2, v2 = f2[base], f2[base+1], f2[base+2]
        dh = min(abs(h1-h2), 1-abs(h1-h2)) * 2.0
        ds = abs(s1 - s2) * 1.5
        dv = abs(v1 - v2) * 1.0
        w = 1.0 / (i + 1)
        d += w * (dh + ds + dv)

    # ── 18~24：7维统计特征 ──
    stat_diff = np.abs(f1[18:25] - f2[18:25])
    d += float(stat_diff.sum()) * 0.5

    # ── 25~29：5维结构特征（v14新增，权重高）──
    # [glow_score, edge_softness, outer_brightness, color_complexity, radial_gradient]
    struct_weights = np.array([4.0, 2.5, 3.0, 1.5, 2.0])
    if len(f1) > 25 and len(f2) > 25:
        struct_diff = np.abs(f1[25:30] - f2[25:30])
        d += float((struct_diff * struct_weights).sum())

    return d


# ──────────────────────────────────────────────────────────────
# 风格索引构建 & 查询
# ──────────────────────────────────────────────────────────────
def _index_one(name: str, cover_path: str, info_path: str, index: dict, skipped: list):
    """把一个样本加入索引（内部辅助）。"""
    try:
        img = Image.open(cover_path).convert("RGB")
        feat = extract_features(img)
        info = json.load(open(info_path, encoding='utf-8'))
        index[name] = {
            'feature': feat,
            'info': info,
            'cover_path': cover_path,
        }
    except Exception as e:
        skipped.append(f"{name}({e})")


def build_index(
    style_base: str = STYLE_BASE,
    flower_results: str = FLOWER_RESULTS,
    index_path: str = INDEX_PATH,
) -> dict:
    """
    构建风格索引。扫描两个目录：
    1. 参考汇总（cover + extracted/info.json）
    2. 花字输出结果（<name>_参考.png + info.json） ← 优先级更高，精度最高
    """
    index = {}
    skipped = []

    # ── 1. 参考汇总目录 ──
    if os.path.isdir(style_base):
        for name in sorted(os.listdir(style_base)):
            p = os.path.join(style_base, name)
            if not os.path.isdir(p):
                continue
            cover_path = None
            for f in os.listdir(p):
                if f.startswith('cover') and (f.endswith('.png') or f.endswith('.webp')):
                    cover_path = os.path.join(p, f)
                    break
            info_path = os.path.join(p, 'extracted', 'info.json')
            if not cover_path or not os.path.exists(info_path):
                skipped.append(name)
                continue
            _index_one(name, cover_path, info_path, index, skipped)

    # ── 2. 花字输出结果（6张 PS 精制参考图，优先级最高）──
    if os.path.isdir(flower_results):
        for name in sorted(os.listdir(flower_results)):
            p = os.path.join(flower_results, name)
            if not os.path.isdir(p):
                continue
            cover_path = os.path.join(p, f"{name}_参考.png")
            if not os.path.exists(cover_path):
                webp = os.path.join(p, f"{name}.webp")
                cover_path = webp if os.path.exists(webp) else None
            info_path = os.path.join(p, 'info.json')
            if not cover_path or not os.path.exists(info_path):
                skipped.append(f"[精制]{name}")
                continue
            key = f"[精制]{name}"
            _index_one(key, cover_path, info_path, index, skipped)
            print(f"  ✓ 精制样本入库: {key}")

    with open(index_path, 'wb') as f:
        pickle.dump(index, f)

    print(f"\n✓ 风格索引构建完成：{len(index)} 个样本入库，跳过 {len(skipped)} 个")
    return index


def load_index(index_path: str = INDEX_PATH) -> dict:
    """加载已有索引，如果不存在则重新构建。"""
    if os.path.exists(index_path):
        with open(index_path, 'rb') as f:
            idx = pickle.load(f)
        # 检查特征维度：如果是旧版（25维）需要重建
        for data in idx.values():
            if len(data['feature']) < 30:
                print("索引特征维度过旧（需要30维），重新构建...")
                return build_index()
            break
        return idx
    print("索引不存在，重新构建...")
    return build_index()


def find_nearest(img: Image.Image, index: dict, top_k: int = 3) -> list:
    """
    找最近邻样本。
    返回 [(name, distance, info), ...] 按距离升序。
    """
    feat = extract_features(img)
    results = []
    for name, data in index.items():
        dist = feature_distance(feat, data['feature'])
        results.append((name, dist, data['info']))
    results.sort(key=lambda x: x[1])
    return results[:top_k]


# ──────────────────────────────────────────────────────────────
# 颜色替换（v14：分层映射）
# ──────────────────────────────────────────────────────────────
def _kmeans_palette(pixels: np.ndarray, n: int) -> list:
    """对像素数组做 K-means，返回 [(R,G,B), ...] 按占比排序。"""
    from sklearn.cluster import MiniBatchKMeans
    n_real = min(n, max(1, len(pixels)))
    if len(pixels) < 2:
        return [(int(pixels[0,0]), int(pixels[0,1]), int(pixels[0,2]))] if len(pixels) else []
    kmeans = MiniBatchKMeans(n_clusters=n_real, random_state=42, n_init=3)
    kmeans.fit(pixels)
    counts = np.bincount(kmeans.labels_, minlength=n_real)
    order = np.argsort(-counts)
    return [(int(kmeans.cluster_centers_[i,0]),
             int(kmeans.cluster_centers_[i,1]),
             int(kmeans.cluster_centers_[i,2])) for i in order]


def extract_palette(img: Image.Image, n: int = 8) -> list:
    """
    从图像提取 n 个主色，返回 [(R,G,B), ...] 按占比排序。
    过滤背景色（接近黑色的暗灰）。
    """
    img_rgb = img.convert("RGB").resize((120, 120), Image.LANCZOS)
    arr = np.array(img_rgb).reshape(-1, 3).astype(float)
    bg_mask = (arr[:, 0] < 50) & (arr[:, 1] < 50) & (arr[:, 2] < 50)
    fg = arr[~bg_mask]
    if len(fg) < 20:
        fg = arr
    return _kmeans_palette(fg, n)


def extract_palette_masked(img: Image.Image, n_text: int = 4, n_stroke: int = 5) -> dict:
    """
    利用标准封面蒙版，分别提取：
      - text_palette:   主体字区域（白色区域）的主色
      - stroke_palette: 外围描边区域（黑色区域）的主色
      - glow_palette:   外围区域中亮度>40的像素主色（发光/阴影色）
      - full_palette:   全图主色（fallback）
    """
    SIZE = (120, 120)
    img_rgb = img.convert("RGB").resize(SIZE, Image.LANCZOS)
    arr = np.array(img_rgb).astype(float)  # (H, W, 3)

    mask = _get_text_mask(SIZE)  # (H, W) 0~1

    text_pixels = arr[mask > 0.5].reshape(-1, 3)
    stroke_pixels = arr[mask < 0.3].reshape(-1, 3)

    def filter_bg(px):
        lum = 0.299*px[:,0] + 0.587*px[:,1] + 0.114*px[:,2]
        return px[lum > 30]

    text_pixels   = filter_bg(text_pixels)   if len(text_pixels)   > 10 else text_pixels
    stroke_pixels_filtered = filter_bg(stroke_pixels) if len(stroke_pixels) > 10 else stroke_pixels

    # 发光区域：外围中亮度 > 40 的像素（不含纯黑背景）
    if len(stroke_pixels) > 10:
        lum = 0.299*stroke_pixels[:,0] + 0.587*stroke_pixels[:,1] + 0.114*stroke_pixels[:,2]
        glow_pixels = stroke_pixels[lum > 40]
    else:
        glow_pixels = np.empty((0, 3))

    full_pixels = arr.reshape(-1, 3)
    full_pixels = filter_bg(full_pixels) if len(full_pixels) > 10 else full_pixels

    text_pal   = _kmeans_palette(text_pixels,   n_text)   if len(text_pixels)   >= 2 else []
    stroke_pal = _kmeans_palette(stroke_pixels_filtered, n_stroke) if len(stroke_pixels_filtered) >= 2 else []
    glow_pal   = _kmeans_palette(glow_pixels, 4) if len(glow_pixels) >= 2 else []
    full_pal   = _kmeans_palette(full_pixels,   max(n_text+n_stroke, 8))

    return {
        'text_palette':   text_pal,
        'stroke_palette': stroke_pal,
        'glow_palette':   glow_pal,
        'full_palette':   full_pal,
    }


def _color_role(r, g, b) -> str:
    """判断颜色在 info.json 中的角色"""
    lum = color_luminance(r, g, b)
    sat = color_saturation(r, g, b)
    if lum < 60:
        return "dark"
    if sat < 0.15 and lum > 180:
        return "white"
    if sat > 0.4:
        return "vivid"
    return "mid"


def _find_closest_in_palette(target_hex: str, palette: list,
                               prefer_role: str = None) -> tuple:
    """
    在调色板中找与 target_hex 最近的颜色（同角色优先）。
    返回 (R,G,B)。
    """
    if not palette:
        return hex_to_rgb(target_hex)
    tr, tg, tb = hex_to_rgb(target_hex)
    th, ts, tv = rgb_to_hsv(tr, tg, tb)
    t_role = _color_role(tr, tg, tb)
    role = prefer_role or t_role

    same_role = [(r,g,b) for r,g,b in palette if _color_role(r,g,b) == role]
    candidates = same_role if same_role else palette

    best = None
    best_dist = float('inf')
    for r, g, b in candidates:
        h, s, v = rgb_to_hsv(r, g, b)
        dh = hue_dist(th, h) / 180.0
        ds = abs(ts - s) / 255.0
        dv = abs(tv - v) / 255.0
        dist = dh * 2.0 + ds + dv
        if dist < best_dist:
            best_dist = dist
            best = (r, g, b)
    return best or palette[0]


def _map_colors_to_palette(hex_colors: list, palette: list) -> dict:
    """把一组 hex 颜色映射到 palette 中最近的颜色，返回 {orig_hex: new_hex}。"""
    mapping = {}
    for orig_hex in hex_colors:
        pure_hex = orig_hex[:7] if len(orig_hex) >= 7 else orig_hex
        new_c = _find_closest_in_palette(pure_hex, palette)
        mapping[orig_hex.lower()] = rgb_to_hex(*new_c)
    return mapping


def replace_colors(info: dict, palette: list, masked_palettes: dict = None) -> dict:
    """
    把 info.json 里的所有颜色替换为从新图提取的调色板颜色（v15：排名对应映射）。
    结构参数（描边宽度/层数/shadow强度/thickness）完全保留。

    核心策略（v15）：
    废弃 HSV 距离查找，改用"排名对应"——新图各区域调色板已按像素占比排序，
    原样本各层第 i 个颜色槽 → 直接取新调色板第 i 个颜色（循环取余）。

    这样彻底避免了"原样本 text_color=白色 → 新图 text_palette 含高光白色
    → 映射回白色而非粉色主色"的角色颠倒问题。

    分层策略：
      - text_color / colorgradient → text_palette（文字区主色，rank 0 = 最主要）
      - stroke 层 → stroke_palette（描边区主色）
      - shadows 层 → glow_palette（外围发光区主色），无则降级到 stroke_palette
      - innerShadows 层 → text_palette（内阴影贴近文字区）
      - multi_text_layer → full_palette
    """
    result = copy.deepcopy(info)

    # 获取各区域调色板（已按像素占比排序，主色在前）
    text_pal   = (masked_palettes.get('text_palette')   if masked_palettes else None) or palette
    stroke_pal = (masked_palettes.get('stroke_palette') if masked_palettes else None) or palette
    glow_pal   = (masked_palettes.get('glow_palette')   if masked_palettes else None) or []
    full_pal   = (masked_palettes.get('full_palette')   if masked_palettes else None) or palette

    # 空调色板降级
    if not text_pal:   text_pal   = full_pal
    if not stroke_pal: stroke_pal = full_pal
    if not glow_pal:   glow_pal   = stroke_pal  # glow 是外围子集，降级到 stroke 比 full 更准

    def pal_at(pal, idx):
        """按下标取调色板颜色（自动循环），返回 hex string '#rrggbb'；调色板为空返回 None。"""
        if not pal:
            return None
        r, g, b = pal[idx % len(pal)]
        return rgb_to_hex(int(r), int(g), int(b))

    # ── 1. text_color → text_pal[0]（最主要的文字区颜色）──
    if 'text_color' in result and isinstance(result['text_color'], str) and result['text_color'].startswith('#'):
        c = pal_at(text_pal, 0)
        if c:
            result['text_color'] = c

    # ── 2. colorgradient → text_pal 顺序分配（各渐变色阶依次对应新调色板）──
    grad_idx = 0
    for cg in result.get('colorgradient', []):
        if isinstance(cg, dict):
            for lg in cg.get('lineargradient', []):
                if 'color' in lg and isinstance(lg['color'], str) and lg['color'].startswith('#'):
                    c = pal_at(text_pal, grad_idx)
                    if c:
                        lg['color'] = c
                    grad_idx += 1

    # ── 3. stroke → stroke_pal 顺序分配（第 i 层描边 → stroke_pal[i]）──
    for i, sk in enumerate(result.get('stroke', [])):
        if 'color' in sk and isinstance(sk['color'], str) and sk['color'].startswith('#'):
            c = pal_at(stroke_pal, i)
            if c:
                sk['color'] = c

    # ── 4. shadows → glow_pal 顺序分配（外围发光/阴影区）──
    for i, shadow in enumerate(result.get('shadows', [])):
        if 'color' in shadow and isinstance(shadow['color'], str) and shadow['color'].startswith('#'):
            c = pal_at(glow_pal, i)
            if c:
                shadow['color'] = c

    # ── 5. innerShadows → text_pal 顺序分配（内阴影在文字区内部）──
    for i, ish in enumerate(result.get('innerShadows', [])):
        if 'color' in ish and isinstance(ish['color'], str) and ish['color'].startswith('#'):
            c = pal_at(text_pal, i)
            if c:
                ish['color'] = c

    # ── 6. multi_text_layer → full_pal 顺序分配 ──
    multi_idx = [0]

    def _replace_multi(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k in ('color', 'text_color') and isinstance(v, str) and v.startswith('#'):
                    c = pal_at(full_pal, multi_idx[0])
                    if c:
                        d[k] = c
                    multi_idx[0] += 1
                else:
                    _replace_multi(v)
        elif isinstance(d, list):
            for item in d:
                _replace_multi(item)

    _replace_multi(result.get('multi_text_layer', []))

    return result


# ──────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────
_matcher_instance = None

class StyleMatcher:
    def __init__(self, index_path: str = INDEX_PATH):
        self.index = load_index(index_path)

    def analyze(self, img: Image.Image, top_k: int = 1) -> dict:
        """
        主入口：给定图像，返回最匹配的 info.json（颜色已替换为新图颜色）。

        策略：
        - 距离极小 (< 0.05)：图像与库中某精制样本几乎一致，直接返回原始参数
        - 否则：找最近邻样本，用分层调色板做颜色替换
        """
        matches = find_nearest(img, self.index, top_k=max(top_k, 3))
        if not matches:
            return _fallback_info()

        name, dist, ref_info = matches[0]

        if dist < 0.05:
            result = copy.deepcopy(ref_info)
            result['_matched_style'] = name
            result['_match_distance'] = round(float(dist), 4)
            result['_top_matches'] = [(m[0], round(float(m[1]), 4)) for m in matches[:3]]
            return result

        masked = extract_palette_masked(img)
        palette = masked['full_palette']
        result = replace_colors(ref_info, palette, masked_palettes=masked)

        result['_matched_style'] = name
        result['_match_distance'] = round(float(dist), 4)
        result['_top_matches'] = [(m[0], round(float(m[1]), 4)) for m in matches[:3]]

        return result

    def analyze_top3(self, img: Image.Image) -> list:
        """
        返回 top3 匹配结果，每个都做颜色替换（或直接复用）。
        用于在 UI 上让用户选择。
        """
        matches = find_nearest(img, self.index, top_k=3)
        masked = extract_palette_masked(img)
        palette = masked['full_palette']
        results = []
        for name, dist, ref_info in matches:
            if dist < 0.05:
                info = copy.deepcopy(ref_info)
            else:
                info = replace_colors(ref_info, palette, masked_palettes=masked)
            info['_matched_style'] = name
            info['_match_distance'] = round(float(dist), 4)
            results.append(info)
        return results


def get_matcher() -> StyleMatcher:
    """单例懒加载"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = StyleMatcher()
    return _matcher_instance


def _fallback_info() -> dict:
    """索引为空时的兜底参数"""
    return {
        "text_color": "#ffffff",
        "textColorAlpha": 255,
        "text_size": 160,
        "gradientIndex": -1,
        "gradientDegree": 0,
        "colorgradient": [],
        "stroke": [
            {"BlendMode": 0, "alpha": 255, "color": "#000000",
             "fullfillBias": {}, "gradientIndex": -1,
             "offset_x": 0, "offset_y": 0, "width": 4.0},
        ],
        "shadows": [],
        "innerShadows": [],
        "multi_text_layer": [],
        "thickness": 0.0001,
        "italic_degree": 0.0001,
        "letterSpace": 1.0001,
        "lineSpace": 1.0001,
        "align_type": 1,
        "version": 1,
        "effectType": 0,
        "hideText": False,
    }


# ──────────────────────────────────────────────────────────────
# CLI 工具
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build_index()
    elif len(sys.argv) > 1:
        img = Image.open(sys.argv[1])
        matcher = StyleMatcher()
        result = matcher.analyze(img)
        print(f"匹配风格: {result['_matched_style']} (距离: {result['_match_distance']})")
        print(f"Top3: {result['_top_matches']}")
        print(f"text_color: {result['text_color']}")
        print(f"描边层数: {len(result.get('stroke', []))}")
        print(f"shadow层数: {len(result.get('shadows', []))}")
    else:
        print("用法:")
        print("  python style_matcher.py build          # 构建索引")
        print("  python style_matcher.py <图片路径>     # 测试匹配")
