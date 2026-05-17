"""NSI 决策引擎 · Streamlit 主应用（T3~T12 阶段）

T1 骨架 + T3~T8 核心算法（数据加载、ASIN 输入、NSI 计算、颜色分类、
排序、整体健康度）保持原样，本轮在 UI 上叠加：
- T9  分析概览（标题 / ASIN / 类目 / 摘要 / 健康度 / 红黄绿灰计数）
- T10 彩色特征卡片（emoji + NSI + 计数 + 归因 + 推荐动作）
- T11 详情展开（examples / diagnosis / action / listing_rewrite）
- T12 友好错误兜底（数据缺失、字段缺失、ASIN 错误、空特征等）
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


# --------------------------------------------------------------------------
# 常量（颜色阈值集中定义，全文件唯一来源，不得重复硬编码）
# --------------------------------------------------------------------------
RED_THRESHOLD: float = -0.5
YELLOW_THRESHOLD: float = 0.0

# 颜色 emoji 映射（T10 卡片左侧大字符）
COLOR_EMOJI: dict[str, str] = {
    "red": "🔴",
    "yellow": "🟡",
    "green": "🟢",
    "gray": "⚪",
}

# 颜色对应的中文档位标签（T10 卡片副标题用）
COLOR_LABEL: dict[str, str] = {
    "red": "紧急修复",
    "yellow": "持续优化",
    "green": "保持卖点",
    "gray": "数据缺失",
}

# 归因 P / L / S / M 的中文解释（T10 卡片归因徽标用）
ATTRIBUTION_TEXT: dict[str, str] = {
    "P": "Product · 产品本身问题",
    "L": "Listing · 页面表达问题",
    "S": "Service · 服务 / 物流问题",
    "M": "Malicious · 疑似恶意评论",
}

# 顶部 / 底部展示的本地演示声明（黑客松合规说明）
DEMO_DISCLAIMER: str = (
    "本 Demo 使用本地预置演示数据，不连接真实亚马逊接口，不做爬虫，"
    "重点展示评论洞察到改品决策的最小闭环。"
)


# --------------------------------------------------------------------------
# T3 · 数据加载
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data(path: str = "demo_data.json") -> dict:
    """从本地 JSON 读取演示数据。

    设计原则：
    - 仅使用 Python 标准库 json，不引入额外依赖。
    - 用 @st.cache_data 缓存，避免每次交互都重读文件。
    - 文件缺失 / 解析失败 / 格式异常时不抛异常，返回 {} 并打印友好中文错误。
    - 不把 demo_data.json 内容硬编码进 Python，路径默认相对当前目录。
    """
    file_path = Path(path)
    if not file_path.exists():
        st.error(f"找不到本地数据文件：{path}。请确认 demo_data.json 与 app.py 位于同一目录。")
        return {}

    try:
        with file_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except json.JSONDecodeError as exc:
        st.error(f"本地数据文件格式不合法（JSON 解析失败）：{exc.msg}")
        return {}
    except OSError as exc:
        st.error(f"读取本地数据文件失败：{exc}")
        return {}

    if not isinstance(data, dict):
        st.error("本地数据文件结构异常：根节点必须是以 ASIN 为 key 的字典。")
        return {}
    return data


# --------------------------------------------------------------------------
# T5 · NSI 计算
# --------------------------------------------------------------------------
def calc_nsi(positive: int, negative: int, total: int) -> float | None:
    """计算单个特征的 NSI。

    NSI = (positive - negative) / total

    返回 None 的情况：
    - total <= 0（数据缺失或异常）
    - positive 或 negative 为负数（显然非法）

    本函数只做数值计算，不做四舍五入、不做颜色分类，
    保证逻辑职责单一，便于 T6 / T7 / T8 复用。
    """
    if total is None or total <= 0:
        return None
    if positive is None or negative is None:
        return None
    if positive < 0 or negative < 0:
        return None
    return (positive - negative) / total


# --------------------------------------------------------------------------
# T6 · 红黄绿（含灰）分类
# --------------------------------------------------------------------------
def classify_color(nsi: float | None) -> str:
    """根据 NSI 返回颜色标签。

    阈值统一从模块常量读取，不允许在其他位置重复硬编码：
    - None             -> "gray"
    - nsi < -0.5       -> "red"
    - -0.5 <= nsi < 0  -> "yellow"
    - nsi >= 0         -> "green"
    """
    if nsi is None:
        return "gray"
    if nsi < RED_THRESHOLD:
        return "red"
    if nsi < YELLOW_THRESHOLD:
        return "yellow"
    return "green"


# --------------------------------------------------------------------------
# T7 · 特征排序
# --------------------------------------------------------------------------
def sort_features(features: list[dict]) -> list[dict]:
    """对特征列表做排序，并附加 _nsi、_color 字段。

    设计原则：
    - 不修改原列表与原字典（用浅拷贝 dict(f)）。
    - 排序键：先按"是否有有效 NSI"分两段（有效在前），
      再按 NSI 升序（越负越靠前 = 越红越靠前），
      NSI 相同则按 feature_name 字典序稳定排序。
    """
    enriched: list[dict] = []
    for feature in features or []:
        copy = dict(feature) if isinstance(feature, dict) else {}
        nsi = calc_nsi(
            copy.get("positive"),
            copy.get("negative"),
            copy.get("total"),
        )
        copy["_nsi"] = nsi
        copy["_color"] = classify_color(nsi)
        enriched.append(copy)

    def _key(item: dict):
        nsi = item.get("_nsi")
        is_invalid = 1 if nsi is None else 0
        sort_nsi = nsi if nsi is not None else 0.0
        return (is_invalid, sort_nsi, str(item.get("feature_name", "")))

    enriched.sort(key=_key)
    return enriched


# --------------------------------------------------------------------------
# T8 · 整体健康度评分
# --------------------------------------------------------------------------
def health_score(features: list[dict]) -> int | None:
    """根据所有有效 NSI 计算整体健康度评分（0~100 整数）。

    score = round((average_nsi + 1) * 50)
    """
    if not features:
        return None
    valid: list[float] = []
    for f in features:
        if not isinstance(f, dict):
            continue
        nsi = f.get("_nsi")
        if nsi is None:
            nsi = calc_nsi(f.get("positive"), f.get("negative"), f.get("total"))
        if nsi is not None:
            valid.append(nsi)
    if not valid:
        return None
    avg = sum(valid) / len(valid)
    return round((avg + 1) * 50)


def health_label(score: int | None) -> str:
    """把整体健康度评分映射到中文档位标签。"""
    if score is None:
        return "无数据"
    if score >= 75:
        return "健康"
    if score >= 50:
        return "一般"
    return "危险"


# --------------------------------------------------------------------------
# T4 · ASIN 输入解析
# --------------------------------------------------------------------------
def _resolve_asin(manual_input: str, sample_asin: str | None) -> str | None:
    """根据"手动输入优先"规则解析最终用于分析的 ASIN。"""
    cleaned = (manual_input or "").strip()
    if cleaned:
        return cleaned.upper()
    if sample_asin:
        return sample_asin
    return None


def _count_colors(sorted_features: list[dict]) -> dict:
    """统计排序后各颜色的特征数量。"""
    buckets = {"red": 0, "yellow": 0, "green": 0, "gray": 0}
    for f in sorted_features:
        color = f.get("_color", "gray")
        buckets[color] = buckets.get(color, 0) + 1
    return buckets


def _safe_text(value, fallback: str = "暂无") -> str:
    """T12 兜底：把缺失 / 空白字段统一渲染成『暂无』，避免 None 直显或抛异常。"""
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _format_nsi(nsi: float | None) -> str:
    """T10 卡片用：把 NSI 数值统一格式化为 2 位小数字符串，None → 'N/A'。"""
    if nsi is None:
        return "N/A"
    try:
        return f"{nsi:.2f}"
    except (TypeError, ValueError):
        return "N/A"


# --------------------------------------------------------------------------
# T9 · 概览渲染
# --------------------------------------------------------------------------
def _render_overview(asin: str, asin_data: dict, sorted_feats: list[dict]) -> None:
    """T9：分析概览（产品标题 / ASIN / 类目 / 摘要 / 健康度 / 红黄绿灰计数）。"""
    score = health_score(sorted_feats)
    label = health_label(score)
    counts = _count_colors(sorted_feats)

    st.header("分析概览")
    st.subheader(_safe_text(asin_data.get("title"), asin))

    info_cols = st.columns(3)
    info_cols[0].markdown(f"**ASIN**：`{_safe_text(asin_data.get('asin'), asin)}`")
    info_cols[1].markdown(f"**类目**：{_safe_text(asin_data.get('category'))}")
    info_cols[2].markdown(f"**特征数**：{len(sorted_feats)}")

    summary = asin_data.get("summary")
    if summary:
        st.caption(_safe_text(summary))

    st.markdown("---")

    metric_cols = st.columns(2)
    metric_cols[0].metric(
        "整体健康度评分",
        "无数据" if score is None else f"{score} / 100",
    )
    metric_cols[1].metric("健康度档位", label)

    count_cols = st.columns(4)
    count_cols[0].metric("🔴 红色（紧急修复）", counts["red"])
    count_cols[1].metric("🟡 黄色（持续优化）", counts["yellow"])
    count_cols[2].metric("🟢 绿色（保持卖点）", counts["green"])
    count_cols[3].metric("⚪ 灰色（数据缺失）", counts["gray"])

    if score is None:
        st.info("当前 ASIN 没有任何有效 NSI 值，可能是 total 全部为 0 或字段缺失，已按『无数据』处理。")
    elif counts["red"] > 0:
        st.warning(f"检测到 {counts['red']} 个红色特征，建议优先修复（见下方红色卡片）。")


# --------------------------------------------------------------------------
# T10 + T11 · 彩色卡片 + 详情展开
# --------------------------------------------------------------------------
def _render_feature_card(index: int, feat: dict) -> None:
    """T10：单个特征的彩色卡片；T11：内嵌 expander 显示详情。"""
    color = feat.get("_color", "gray")
    emoji = COLOR_EMOJI.get(color, "⚪")
    color_zh = COLOR_LABEL.get(color, "未知")

    nsi = feat.get("_nsi")
    nsi_str = _format_nsi(nsi)

    feature_name = _safe_text(feat.get("feature_name"), "（未命名特征）")
    attribution_raw = _safe_text(feat.get("attribution"), "")
    attribution_key = attribution_raw.upper() if attribution_raw and attribution_raw != "暂无" else ""
    attribution_label = ATTRIBUTION_TEXT.get(attribution_key, f"未知归因（{attribution_raw}）")

    positive = feat.get("positive", 0) or 0
    negative = feat.get("negative", 0) or 0
    total = feat.get("total", 0) or 0

    action = _safe_text(feat.get("action"))
    diagnosis = _safe_text(feat.get("diagnosis"))
    listing_rewrite = _safe_text(feat.get("listing_rewrite"))
    examples = feat.get("examples") or []

    # 卡片主体：用 container(border=True) 实现轻量分隔；不引入 CSS。
    with st.container(border=True):
        head_cols = st.columns([1, 6, 2])
        head_cols[0].markdown(f"<div style='font-size:34px;line-height:1'>{emoji}</div>", unsafe_allow_html=True)
        head_cols[1].markdown(
            f"### {index}. {feature_name}\n"
            f"**{color_zh}** · Echo Score = `{nsi_str}` · 归因：`{attribution_key or '?'}` — {attribution_label}"
        )
        head_cols[2].metric("Echo Score", nsi_str)

        meta_cols = st.columns(3)
        meta_cols[0].markdown(f"👍 正面提及：**{positive}**")
        meta_cols[1].markdown(f"👎 负面提及：**{negative}**")
        meta_cols[2].markdown(f"📊 相关评论：**{total}**")

        st.markdown(f"**🛠 推荐动作**：{action}")

        # T11 · 详情展开
        with st.expander("📂 查看详情：原始评论示例 / 诊断 / Listing 改写"):
            st.markdown("**🩺 诊断**")
            st.write(diagnosis)

            st.markdown("**🛠 推荐动作**")
            st.write(action)

            st.markdown("**📝 Listing 改写建议**")
            st.write(listing_rewrite)

            st.markdown("**💬 评论示例**")
            if not examples:
                st.write("暂无")
            else:
                for ex in examples:
                    if not isinstance(ex, dict):
                        continue
                    polarity = (ex.get("polarity") or "").strip().lower()
                    text = _safe_text(ex.get("text"))
                    # 恶意归因下的 negative 视为可疑，用 ⚠️
                    if attribution_key == "M" and polarity == "negative":
                        icon = "⚠️"
                    elif polarity == "negative":
                        icon = "❌"
                    elif polarity == "positive":
                        icon = "✅"
                    elif polarity in {"neutral", "suspicious", "unknown"}:
                        icon = "⚠️"
                    else:
                        icon = "•"
                    st.markdown(f"- {icon} {text}")


def _render_feature_cards(sorted_feats: list[dict]) -> None:
    """T10：按 sort_features() 顺序输出所有彩色卡片。"""
    if not sorted_feats:
        st.info("该 ASIN 暂无特征数据。")
        return
    st.header("特征改品清单（按紧急度排序）")
    st.caption("排序逻辑：红色（紧急修复）→ 黄色（持续优化）→ 绿色（保持卖点）→ 灰色（数据缺失）。")
    for i, feat in enumerate(sorted_feats, start=1):
        _render_feature_card(i, feat)


# --------------------------------------------------------------------------
# 单 ASIN 渲染入口（包裹 T9 + T10 + T11，并 try/except 做最后一层 T12 兜底）
# --------------------------------------------------------------------------
def _render_result(asin: str, asin_data: dict) -> None:
    """渲染单个 ASIN 的完整分析结果。"""
    try:
        if not isinstance(asin_data, dict):
            st.warning(f"ASIN `{asin}` 的数据结构异常，已跳过渲染。")
            return

        raw_features = asin_data.get("features")
        if raw_features is None:
            features: list[dict] = []
        elif not isinstance(raw_features, list):
            st.warning(f"ASIN `{asin}` 的 features 字段不是数组，已按空处理。")
            features = []
        else:
            features = [f for f in raw_features if isinstance(f, dict)]

        sorted_feats = sort_features(features)

        _render_overview(asin, asin_data, sorted_feats)
        st.markdown("---")
        _render_feature_cards(sorted_feats)
    except Exception as exc:  # T12 最终兜底，避免任何未预期异常把页面打穿
        st.error("渲染分析结果时出现意外错误，已为你拦截，避免页面崩溃。")
        st.caption(f"错误类型：{type(exc).__name__}（已对终端用户屏蔽堆栈）")


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Echofy", page_icon="🟢", layout="wide")

    st.title("Echofy")
    st.subheader("把评论噪音变成改品优先级")
    st.caption(
        "Echo Score 基于正负向评论提及差异和总提及量计算，"
        "用来衡量某个产品特征的评论健康度。"
    )
    st.caption(DEMO_DISCLAIMER)

    data = load_data()
    asin_options: list[str] = sorted(data.keys()) if data else []

    with st.container(border=True):
        st.markdown("**🔎 选择或输入要分析的 ASIN**")
        sample_asin = st.selectbox(
            "选择示例 ASIN",
            options=asin_options,
            index=0 if asin_options else None,
            placeholder="（暂无示例数据）" if not asin_options else None,
        )
        manual_input = st.text_input(
            "或手动输入 ASIN（手动输入优先，自动 strip + 大写）",
            value="",
            placeholder="例如 B0DEMO-CUP",
        )
        analyze_clicked = st.button("Analyze", type="primary")

    # 状态：用 session_state 持久化已分析的 ASIN，避免后续 rerun 丢失
    if "analyzed_asin" not in st.session_state:
        st.session_state["analyzed_asin"] = None

    if analyze_clicked:
        st.session_state["analyzed_asin"] = _resolve_asin(manual_input, sample_asin)

    target_asin = st.session_state["analyzed_asin"]

    # T12 · 用户尚未点击或输入
    if target_asin is None:
        if analyze_clicked:
            st.info("请先选择一个示例 ASIN，或在输入框中填写要分析的 ASIN。")
        else:
            st.info("👈 在上方选择示例 ASIN 或手动输入，然后点击 Analyze 开始分析。")
        st.caption(DEMO_DISCLAIMER)
        return

    # T12 · 数据未加载成功（load_data 已 st.error，避免重复报错）
    if not data:
        st.caption(DEMO_DISCLAIMER)
        return

    # T12 · ASIN 不在演示数据集
    if target_asin not in data:
        st.warning(
            f"未找到 ASIN：**{target_asin}**。当前演示数据仅包含："
            + "、".join(asin_options)
            + "。本 MVP 不连接亚马逊真实接口，请选择上方示例。"
        )
        st.caption(DEMO_DISCLAIMER)
        return

    _render_result(target_asin, data[target_asin])

    st.markdown("---")
    st.caption(DEMO_DISCLAIMER)


if __name__ == "__main__":
    main()
