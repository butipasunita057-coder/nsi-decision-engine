"""NSI 决策引擎 · Streamlit 主应用（T3~T8 阶段）

本文件在 T1 骨架基础上加入：
- T3 数据加载（load_data, @st.cache_data）
- T4 ASIN 输入与示例选择（selectbox + text_input + Analyze 按钮）
- T5 NSI 计算函数（calc_nsi）
- T6 红黄绿分类（classify_color + 阈值常量）
- T7 特征排序（sort_features）
- T8 整体健康度评分（health_score + health_label）

UI 仅做最小可验收版本：标题、副标题、选择控件、健康度指标、
红黄绿灰计数、排序后的特征表。彩色卡片、详情展开等留给 T9~T11。
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
        copy = dict(feature)
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
        # None 值殿后：第一个分量 1，否则 0
        is_invalid = 1 if nsi is None else 0
        # NSI 为 None 时给一个占位值（仅用于排序稳定，不影响分组），
        # 同 NSI 时按 feature_name 字典序，feature_name 缺失则用空串。
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

    若没有任何有效 NSI 值（features 为空，或所有 total<=0），返回 None。
    本函数依赖 sort_features 已附加的 _nsi 字段；若调用方未排序，
    则自行调用 calc_nsi 兜底，保证可独立使用。
    """
    if not features:
        return None
    valid: list[float] = []
    for f in features:
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
# T4 · ASIN 输入与分析触发
# --------------------------------------------------------------------------
def _resolve_asin(manual_input: str, sample_asin: str | None) -> str | None:
    """根据"手动输入优先"规则解析最终用于分析的 ASIN。

    - 手动输入非空（去空白后）→ 使用手动输入，并 strip().upper() 标准化。
    - 否则使用 selectbox 当前选中的示例 ASIN。
    - 两者都为空 → 返回 None。
    """
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


def _render_result(asin: str, asin_data: dict) -> None:
    """渲染单个 ASIN 的最小分析结果（T3-T8 验收级别，不含 T9-T11 卡片）。"""
    features = asin_data.get("features", []) or []
    sorted_feats = sort_features(features)
    score = health_score(sorted_feats)
    label = health_label(score)
    counts = _count_colors(sorted_feats)

    # 基本信息
    st.markdown(f"### {asin_data.get('title', asin)}")
    info_cols = st.columns(3)
    info_cols[0].markdown(f"**ASIN**：`{asin_data.get('asin', asin)}`")
    info_cols[1].markdown(f"**类目**：{asin_data.get('category', '-')}")
    info_cols[2].markdown(f"**特征数**：{len(sorted_feats)}")

    summary = asin_data.get("summary")
    if summary:
        st.caption(summary)

    # 整体健康度
    metric_cols = st.columns(2)
    metric_cols[0].metric("整体健康度评分", "无数据" if score is None else f"{score} / 100")
    metric_cols[1].metric("健康度档位", label)

    # 红黄绿灰计数
    count_cols = st.columns(4)
    count_cols[0].metric("🟥 红色（紧急修复）", counts["red"])
    count_cols[1].metric("🟨 黄色（持续优化）", counts["yellow"])
    count_cols[2].metric("🟩 绿色（保持卖点）", counts["green"])
    count_cols[3].metric("⬜ 灰色（数据缺失）", counts["gray"])

    # 简单排序表（T9 才升级为彩色卡片）
    table_rows = []
    for f in sorted_feats:
        nsi = f.get("_nsi")
        table_rows.append(
            {
                "feature_name": f.get("feature_name", ""),
                "NSI": "N/A" if nsi is None else round(nsi, 2),
                "color": f.get("_color", "gray"),
                "attribution": f.get("attribution", ""),
                "positive": f.get("positive", 0),
                "negative": f.get("negative", 0),
                "total": f.get("total", 0),
            }
        )
    if table_rows:
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
    else:
        st.info("该 ASIN 暂无特征数据。")


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="NSI 决策引擎", page_icon="🟢", layout="centered")

    st.title("NSI 决策引擎")
    st.subheader("先改哪个，怎么改")

    data = load_data()
    asin_options: list[str] = sorted(data.keys()) if data else []

    # 输入区
    sample_asin = st.selectbox(
        "选择示例 ASIN",
        options=asin_options,
        index=0 if asin_options else None,
        placeholder="（暂无示例数据）" if not asin_options else None,
    )
    manual_input = st.text_input(
        "或手动输入 ASIN（手动输入优先）",
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
    if target_asin is None:
        if analyze_clicked:
            st.info("请先选择一个示例 ASIN，或在输入框中填写要分析的 ASIN。")
        return

    if not data:
        # load_data 已通过 st.error 提示，这里不再重复报错
        return

    if target_asin not in data:
        st.warning(
            f"未找到 ASIN：{target_asin}。当前演示数据仅包含："
            + "、".join(asin_options)
            + "。本 MVP 不连接亚马逊真实接口，请选择上方示例。"
        )
        return

    _render_result(target_asin, data[target_asin])


if __name__ == "__main__":
    main()
