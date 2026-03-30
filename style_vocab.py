# style_vocab.py — 整合所有词库，提供语义匹配接口
# 合并 vocab_01 ~ vocab_20，共约 2000+ 词条

from vocab_01 import VOCAB_01
from vocab_02 import VOCAB_02
from vocab_03 import VOCAB_03
from vocab_04 import VOCAB_04
from vocab_05 import VOCAB_05
from vocab_06 import VOCAB_06
from vocab_07 import VOCAB_07
from vocab_08 import VOCAB_08
from vocab_09 import VOCAB_09
from vocab_10 import VOCAB_10
from vocab_11 import VOCAB_11
from vocab_12 import VOCAB_12
from vocab_13 import VOCAB_13
from vocab_14 import VOCAB_14
from vocab_15 import VOCAB_15
from vocab_16 import VOCAB_16
from vocab_17 import VOCAB_17
from vocab_18 import VOCAB_18
from vocab_19 import VOCAB_19
from vocab_20 import VOCAB_20

# 合并所有词库为单一字典
STYLE_VOCAB = {}
STYLE_VOCAB.update(VOCAB_01)
STYLE_VOCAB.update(VOCAB_02)
STYLE_VOCAB.update(VOCAB_03)
STYLE_VOCAB.update(VOCAB_04)
STYLE_VOCAB.update(VOCAB_05)
STYLE_VOCAB.update(VOCAB_06)
STYLE_VOCAB.update(VOCAB_07)
STYLE_VOCAB.update(VOCAB_08)
STYLE_VOCAB.update(VOCAB_09)
STYLE_VOCAB.update(VOCAB_10)
STYLE_VOCAB.update(VOCAB_11)
STYLE_VOCAB.update(VOCAB_12)
STYLE_VOCAB.update(VOCAB_13)
STYLE_VOCAB.update(VOCAB_14)
STYLE_VOCAB.update(VOCAB_15)
STYLE_VOCAB.update(VOCAB_16)
STYLE_VOCAB.update(VOCAB_17)
STYLE_VOCAB.update(VOCAB_18)
STYLE_VOCAB.update(VOCAB_19)
STYLE_VOCAB.update(VOCAB_20)


def match_style(text: str) -> dict | None:
    """
    从用户输入文本中提取词库匹配，返回匹配度最高的配置。
    支持：精确匹配 > 子串包含匹配
    返回 None 表示未找到匹配。
    """
    text = text.strip()

    # 1. 精确匹配
    if text in STYLE_VOCAB:
        return STYLE_VOCAB[text]

    # 2. 子串匹配（词条是用户输入的子串）
    matched_key = None
    matched_len = 0
    for key in STYLE_VOCAB:
        if key in text and len(key) > matched_len:
            matched_key = key
            matched_len = len(key)

    if matched_key:
        return STYLE_VOCAB[matched_key]

    return None


def match_all_styles(text: str) -> list[dict]:
    """
    返回文本中所有匹配的词条配置（按匹配长度降序），用于多关键词融合。
    """
    text = text.strip()
    results = []

    # 精确匹配优先
    if text in STYLE_VOCAB:
        return [{"key": text, **STYLE_VOCAB[text]}]

    # 子串匹配所有命中词
    for key in STYLE_VOCAB:
        if key in text:
            results.append({"key": key, "match_len": len(key), **STYLE_VOCAB[key]})

    # 按匹配长度降序
    results.sort(key=lambda x: x["match_len"], reverse=True)
    return results


def build_style_from_text(text: str) -> dict:
    """
    从用户输入文本推断最佳花字配置。
    多词命中时：
    - palette 对所有命中词的配色做加权平均混色（命中词越长权重越高）
    - effect 取匹配最长的主词
    - glow 任一命中词为 True 则整体发光

    返回格式：
    {
        "palette": [...],
        "effect": "效果类型",
        "glow": True/False,
        "matched_keys": [...]
    }
    """
    all_matches = match_all_styles(text)

    if not all_matches:
        return {
            "palette": ["#ffffff", "#ffd54f", "#ff8f00", "#ff6d00", "#ff3d00"],
            "effect": "双色渐变",
            "glow": False,
            "matched_keys": []
        }

    # 主配置取匹配长度最大的词
    primary = all_matches[0]
    glow = any(m.get("glow", False) for m in all_matches)

    # ── 多词调色板融合（加权平均混色）──
    if len(all_matches) == 1:
        blended = primary["palette"]
    else:
        # 权重 = 匹配词长度（精确匹配 match_len 不存在时设为 len(key)）
        def get_weight(m):
            return m.get("match_len", len(m["key"]))

        total_w = sum(get_weight(m) for m in all_matches)
        # 找出最长 palette 的长度，不足的补末位色
        max_len = max(len(m["palette"]) for m in all_matches)

        def pad_palette(p, n):
            while len(p) < n:
                p = p + [p[-1]]
            return p[:n]

        def hex_to_rgb(h):
            h = h.lstrip("#")
            if len(h) == 3:
                h = "".join(c*2 for c in h)
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

        def rgb_to_hex(r, g, b):
            return "#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b))

        blended = []
        for idx in range(max_len):
            r_acc, g_acc, b_acc = 0.0, 0.0, 0.0
            for m in all_matches:
                pal = pad_palette(list(m["palette"]), max_len)
                w = get_weight(m) / total_w
                try:
                    r, g, b = hex_to_rgb(pal[idx])
                except Exception:
                    r, g, b = 255, 255, 255
                r_acc += r * w
                g_acc += g * w
                b_acc += b * w
            blended.append(rgb_to_hex(r_acc, g_acc, b_acc))

    return {
        "palette": blended,
        "effect": primary["effect"],
        "glow": glow,
        "matched_keys": [m["key"] for m in all_matches]
    }


if __name__ == "__main__":
    # 快速测试
    tests = [
        "爱国",
        "低饱和伤感",
        "赛博朋克霓虹",
        "春天樱花",
        "黑暗末日",
        "多巴胺配色",
        "金属质感浮雕",
        "YYDS",
        "新年快乐",
        "夏日炎炎",
    ]
    print(f"词库总词数: {len(STYLE_VOCAB)}")
    print("-" * 50)
    for t in tests:
        result = build_style_from_text(t)
        keys = result["matched_keys"]
        print(f"输入: '{t}'")
        print(f"  命中词: {keys}")
        print(f"  配色: {result['palette']}")
        print(f"  效果: {result['effect']}, 发光: {result['glow']}")
        print()
