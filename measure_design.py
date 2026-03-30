#!/usr/bin/env python3
# coding=utf-8
"""
measure_design.py — 精确像素级测量设计稿的描边宽度、颜色、偏移量

方法:
1. 找到文字区域(排除灰色辅助线)
2. 沿多条水平/垂直扫描线从文字边缘向内扫描
3. 检测颜色跳变点，测量每个颜色带的像素宽度
4. 扣除背景色(#1a1a1a)影响：
   - 在辅助线区域和文字区域交界处，颜色会被抗锯齿混合
   - 只取纯净区域(距离边界5+像素)的颜色
5. 通过多条扫描线取中位数，消除噪声
6. 将像素宽度转换为 info.json 坐标(基于 text_size=160)

偏移量测量:
- 比较文字上/下/左/右外围的非背景色分布
- 计算重心偏移
"""
import os
import numpy as np
from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "花字参考图")
BG = np.array([26, 26, 26])  # #1a1a1a


def rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def is_bg(c, threshold=30):
    """判断像素是否是背景色"""
    return max(abs(int(c[0])-26), abs(int(c[1])-26), abs(int(c[2])-26)) < threshold


def is_gray(c, threshold=20):
    """判断像素是否是灰色(辅助线)"""
    return abs(int(c[0]) - int(c[1])) < threshold and abs(int(c[1]) - int(c[2])) < threshold


def color_distance(c1, c2):
    """欧氏距离"""
    return np.sqrt(sum((int(a)-int(b))**2 for a, b in zip(c1, c2)))


def find_text_bbox(arr, w, h):
    """找到文字的精确边界框(排除灰色辅助线)"""
    # 彩色像素 = 饱和度 > 30 或 亮度 > 200
    sat = arr.max(axis=2).astype(float) - arr.min(axis=2).astype(float)
    bright = arr.max(axis=2).astype(float)

    # 文字像素: 彩色(饱和度>30) 或 很亮(>200) 且 不是灰色
    gray_mask = np.abs(arr[:,:,0].astype(float) - arr[:,:,1].astype(float)) < 15
    gray_mask &= np.abs(arr[:,:,1].astype(float) - arr[:,:,2].astype(float)) < 15

    text_mask = ((sat > 30) | (bright > 200)) & (~gray_mask | (bright > 230))

    # 对于发光效果，发光区域也是文字的一部分
    # 但发光区域可能被辅助线遮挡，需要用中心区域来估算

    rows = np.where(text_mask.any(axis=1))[0]
    cols = np.where(text_mask.any(axis=0))[0]

    if len(rows) < 10 or len(cols) < 10:
        # 退回到简单检测
        diff = np.abs(arr.astype(float) - BG).max(axis=2)
        mask = diff > 40
        rows = np.where(mask.any(axis=1))[0]
        cols = np.where(mask.any(axis=0))[0]

    return cols[0], rows[0], cols[-1], rows[-1]


def measure_stroke_layers(arr, text_bbox, direction="right"):
    """
    从文字内部向外扫描，测量描边层。

    扫描多条线取中位数。
    返回: [(color_rgb, width_px, start_px, end_px), ...]
    """
    left, top, right, bottom = text_bbox
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    h, w = arr.shape[:2]
    text_w = right - left
    text_h = bottom - top

    all_scans = []

    if direction == "right":
        # 从文字中心区域找一个明确在文字内的 x 坐标，然后向右扫
        # 选择几个不同的 y 坐标
        for dy_pct in [0.3, 0.4, 0.5, 0.6, 0.7]:
            scan_y = int(top + text_h * dy_pct)
            if scan_y < 0 or scan_y >= h:
                continue

            # 从中间偏右开始(确保在文字笔画内)，向右扫描
            # 先找到这行上文字的右边界
            line = arr[scan_y, :]
            line_sat = np.max(line, axis=1).astype(float) - np.min(line, axis=1).astype(float)
            line_bright = np.max(line, axis=1).astype(float)

            # 找到从中心向右第一个回到背景的位置
            text_right_edge = cx
            for x in range(cx, min(w, right + 100)):
                c = arr[scan_y, x]
                if is_bg(c, threshold=35) and not is_gray(c):
                    text_right_edge = x
                    break

            if text_right_edge <= cx:
                continue

            # 从文字右边界向左扫描，记录颜色变化
            scan = []
            prev_color = None
            segment_start = text_right_edge
            for x in range(text_right_edge - 1, max(cx - 50, 0), -1):
                c = tuple(arr[scan_y, x])
                if is_bg(c, threshold=35):
                    continue  # 还在背景里

                # 量化颜色(减少噪声)
                cq = (c[0]//12*12, c[1]//12*12, c[2]//12*12)

                if prev_color is None:
                    prev_color = cq
                    segment_start = x
                elif color_distance(cq, prev_color) > 40:
                    # 颜色跳变
                    width = segment_start - x
                    # 取段中点的精确颜色
                    mid_x = (segment_start + x) // 2
                    mid_c = arr[scan_y, mid_x]
                    scan.append((tuple(mid_c), width, x, segment_start))
                    prev_color = cq
                    segment_start = x

            # 最后一段
            if prev_color is not None and segment_start > cx:
                x_end = max(cx - 50, 0)
                width = segment_start - x_end
                mid_x = (segment_start + x_end) // 2
                mid_c = arr[scan_y, mid_x]
                scan.append((tuple(mid_c), width, x_end, segment_start))

            if scan:
                all_scans.append(scan)

    return all_scans


def measure_glow_extent(arr, text_bbox):
    """测量发光效果的范围和衰减"""
    left, top, right, bottom = text_bbox
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    h, w = arr.shape[:2]
    text_w = right - left
    text_h = bottom - top

    # 从文字边界向外采样，看亮度如何衰减
    results = {}
    for direction, dx, dy in [("上", 0, -1), ("下", 0, 1), ("左", -1, 0), ("右", 1, 0)]:
        samples = []
        # 从文字边界开始
        if direction == "上":
            start_x, start_y = cx, top
        elif direction == "下":
            start_x, start_y = cx, bottom
        elif direction == "左":
            start_x, start_y = left, cy
        else:
            start_x, start_y = right, cy

        for dist in range(0, 200, 2):
            sx = start_x + dx * dist
            sy = start_y + dy * dist
            if 0 <= sx < w and 0 <= sy < h:
                c = arr[sy, sx]
                # 扣除背景: 实际亮度 = 像素亮度 - 背景亮度
                actual_bright = max(0, float(max(c)) - 26)
                if actual_bright < 5 and dist > 20:
                    break
                if not is_gray(c, threshold=10):  # 排除辅助线
                    samples.append((dist, tuple(c), actual_bright))

        results[direction] = samples

    return results


def measure_offset(arr, text_bbox):
    """
    测量阴影/发光的偏移方向和幅度。
    方法: 计算文字外围亮度的加权重心偏移。
    """
    left, top, right, bottom = text_bbox
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    h, w = arr.shape[:2]

    # 在文字外围采样
    margin = 80
    weighted_x = 0
    weighted_y = 0
    total_weight = 0

    for y in range(max(0, top - margin), min(h, bottom + margin)):
        for x in range(max(0, left - margin), min(w, right + margin)):
            # 跳过文字内部
            if left < x < right and top < y < bottom:
                continue

            c = arr[y, x]
            # 扣除背景
            bright = max(0, float(max(c)) - 30)
            if bright < 10:
                continue
            if is_gray(c, threshold=12):
                continue

            # 权重 = 亮度
            weighted_x += (x - cx) * bright
            weighted_y += (y - cy) * bright
            total_weight += bright

    if total_weight > 0:
        offset_x = weighted_x / total_weight
        offset_y = weighted_y / total_weight
        return offset_x, offset_y
    return 0, 0


def measure_vertical_gradient(arr, text_bbox):
    """测量文字内部的垂直渐变(顶部到底部颜色变化)"""
    left, top, right, bottom = text_bbox
    cx = (left + right) // 2
    h, w = arr.shape[:2]
    text_h = bottom - top

    results = []
    # 多列采样取平均
    for x_pct in [0.35, 0.45, 0.55, 0.65]:
        x = int(left + (right - left) * x_pct)
        for y_pct in [0.15, 0.3, 0.5, 0.7, 0.85]:
            y = int(top + text_h * y_pct)
            if 0 <= x < w and 0 <= y < h:
                c = arr[y, x]
                if not is_bg(c) and not is_gray(c, threshold=15):
                    results.append((y_pct, tuple(c)))

    # 按 y_pct 分组取中位数
    grouped = {}
    for pct, c in results:
        key = round(pct, 1)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(c)

    gradient = []
    for pct in sorted(grouped.keys()):
        colors = grouped[pct]
        avg = tuple(int(np.median([c[i] for c in colors])) for i in range(3))
        gradient.append((pct, avg))

    return gradient


def analyze_design(img_path, name):
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    arr = np.array(img)

    print(f"\n{'='*70}")
    print(f"【{name}】 {w}x{h}")
    print(f"{'─'*70}")

    # 1. 找到文字区域
    bbox = find_text_bbox(arr, w, h)
    left, top, right, bottom = bbox
    text_w = right - left
    text_h = bottom - top
    print(f"  文字bbox: ({left},{top})-({right},{bottom}) = {text_w}x{text_h}px")

    # 文字宽度占比 → 推算等效 text_size
    # 标准: text_size=160 在 700x700 设计稿上 ≈ 占 60-70%宽度
    text_ratio = text_w / w
    print(f"  文字宽度占比: {text_ratio:.1%}")

    # 像素到 info.json 坐标的换算系数
    # info.json 的 width 单位是基于 text_size 的像素
    # 设计稿 700px 宽 ≈ 对应 text_size=160 的文字
    # 所以 1 info.json 单位 ≈ text_w / (160 * 2) 像素（粗略）
    # 更精确: 描边 width 直接按像素比例换算
    px_per_unit = text_w / 200.0  # 估算: 200单位≈文字区域宽度
    print(f"  换算系数: 1 info.json 单位 ≈ {px_per_unit:.1f}px")

    # 2. 描边层测量
    print(f"\n  ── 描边层测量 (从外向内) ──")
    scans = measure_stroke_layers(arr, bbox, "right")

    if scans:
        # 取最长的扫描结果
        best_scan = max(scans, key=len)
        for i, (color, width_px, start, end) in enumerate(best_scan):
            width_unit = width_px / px_per_unit
            # 扣除背景混合: 如果颜色太暗(max<50)可能是背景混合
            pure = "纯净" if max(color) > 60 else "可能混背景"
            print(f"    层{i}: {rgb_to_hex(*color)} width={width_px}px → {width_unit:.1f}单位  "
                  f"x=[{start}-{end}] {pure}")

        # 所有扫描的层数统计
        layer_counts = [len(s) for s in scans]
        print(f"    ({len(scans)}条扫描线, 层数={layer_counts})")

    # 3. 垂直渐变
    print(f"\n  ── 垂直渐变 ──")
    gradient = measure_vertical_gradient(arr, bbox)
    for pct, c in gradient:
        print(f"    {int(pct*100):>3d}%: RGB({c[0]:>3d},{c[1]:>3d},{c[2]:>3d}) {rgb_to_hex(*c)}")

    # 4. 发光范围
    print(f"\n  ── 发光范围 ──")
    glow = measure_glow_extent(arr, bbox)
    for direction, samples in glow.items():
        if samples:
            max_dist = max(s[0] for s in samples if s[2] > 10) if any(s[2] > 10 for s in samples) else 0
            if max_dist > 5:
                # 取几个关键距离的颜色
                key_samples = [(d, c, b) for d, c, b in samples if d in [5, 15, 30, 50] or d == max_dist]
                for d, c, b in key_samples[:4]:
                    print(f"    {direction} dist={d:>3d}px: {rgb_to_hex(*c)} bright={b:.0f}")
                print(f"    {direction} 最大范围: {max_dist}px → {max_dist/px_per_unit:.1f}单位")

    # 5. 偏移测量
    print(f"\n  ── 偏移量 ──")
    off_x, off_y = measure_offset(arr, bbox)
    off_x_unit = off_x / px_per_unit
    off_y_unit = off_y / px_per_unit
    print(f"    重心偏移: ({off_x:.1f}, {off_y:.1f})px → ({off_x_unit:.1f}, {off_y_unit:.1f})单位")
    if abs(off_x) > 5 or abs(off_y) > 5:
        angle = np.degrees(np.arctan2(off_y, off_x))
        mag = np.sqrt(off_x**2 + off_y**2)
        print(f"    偏移角度: {angle:.0f}° 幅度: {mag:.1f}px → {mag/px_per_unit:.1f}单位")


designs = [
    ("橙金浮雕", "画板 23 拷贝 2.png"),
    ("错位橙影", "画板 23 拷贝 3.png"),
    ("淡黄渐变", "画板 23 拷贝.png"),
    ("纯橙描边", "画板 23 拷贝 4.png"),
    ("黄金霓虹", "画板 23 拷贝 5.png"),
    ("赤焰霓虹", "画板 23 拷贝 6.png"),
]

for name, fname in designs:
    path = os.path.join(SRC, fname)
    if os.path.exists(path):
        analyze_design(path, name)
