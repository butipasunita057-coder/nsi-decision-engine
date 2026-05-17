"""NSI 决策引擎 · Streamlit 最小骨架（T1）

本文件仅作为黑客松 MVP 的初始骨架，渲染项目标题、副标题与占位文本。
核心 NSI 分析逻辑（数据读取、ASIN 输入、NSI 计算、红黄绿分类、
排序、整体健康度评分、三色卡片、详情展开、错误兜底等）将在后续
T2~T12 任务中现场实现。本任务严禁加入任何业务逻辑。
"""

import streamlit as st


def main() -> None:
    """渲染最小骨架页面。

    本函数当前只展示静态标题、副标题与占位文本，验证现场环境
    可以正常通过 `streamlit run app.py` 启动。
    """
    st.set_page_config(page_title="NSI 决策引擎", page_icon="🟢", layout="centered")

    st.title("NSI 决策引擎")
    st.subheader("先改哪个，怎么改")

    st.write(
        "这是 NSI 决策引擎黑客松 MVP 的初始 Streamlit 骨架（T1）。"
        "当前页面仅用于验证现场环境与启动命令是否可用。"
    )
    st.info(
        "核心 NSI 分析功能（数据读取、ASIN 输入、NSI 计算、红黄绿分类、"
        "排序、整体健康度评分、三色卡片、详情展开、错误提示等）将在后续 "
        "T2~T12 任务中现场实现。"
    )


if __name__ == "__main__":
    main()
