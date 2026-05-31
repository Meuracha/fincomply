"""
FinComply Dashboard — Financial Compliance Intelligence Platform
Design direction: Bloomberg Terminal meets modern fintech — dark, data-dense, authoritative
"""

import os
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

API_URL = os.getenv("API_URL", "http://localhost:8010")

st.set_page_config(
    page_title="FinComply",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Design System ────────────────────────────────────────────
COLORS = {
    "bg": "#080c14",
    "surface": "#0d1320",
    "panel": "#111827",
    "border": "#1e2d45",
    "accent": "#0ea5e9",
    "accent2": "#38bdf8",
    "gold": "#f59e0b",
    "green": "#10b981",
    "red": "#ef4444",
    "text": "#e2e8f0",
    "muted": "#4b6280",
    "dim": "#1e3a5f",
}

st.markdown(
    f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

    * {{ box-sizing: border-box; }}

    #MainMenu, footer, header {{ visibility: hidden; }}

    .stApp {{
        background: {COLORS['bg']};
        font-family: 'IBM Plex Sans', sans-serif;
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background: {COLORS['surface']};
        border-right: 1px solid {COLORS['border']};
    }}
    [data-testid="stSidebar"] > div {{
        padding-top: 0 !important;
    }}

    /* Radio buttons */
    [data-testid="stRadio"] label {{
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
        color: {COLORS['muted']} !important;
        letter-spacing: 0.5px;
    }}
    [data-testid="stRadio"] label:hover {{
        color: {COLORS['accent']} !important;
    }}

    /* Metrics */
    [data-testid="metric-container"] {{
        background: {COLORS['panel']};
        border: 1px solid {COLORS['border']};
        border-top: 2px solid {COLORS['accent']};
        border-radius: 4px;
        padding: 16px;
    }}
    [data-testid="metric-container"] label {{
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 10px !important;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: {COLORS['muted']} !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 24px !important;
        color: {COLORS['text']} !important;
        font-weight: 600;
    }}

    /* Text area */
    textarea {{
        background: {COLORS['panel']} !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 4px !important;
        color: {COLORS['text']} !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
        font-size: 14px !important;
    }}
    textarea:focus {{
        border-color: {COLORS['accent']} !important;
        box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.15) !important;
    }}

    /* Primary button */
    .stButton > button[kind="primary"] {{
        background: {COLORS['accent']} !important;
        color: #000 !important;
        border: none !important;
        border-radius: 3px !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        padding: 12px 24px !important;
        transition: all 0.15s !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: {COLORS['accent2']} !important;
        transform: translateY(-1px) !important;
    }}

    /* Secondary button */
    .stButton > button[kind="secondary"] {{
        background: transparent !important;
        border: 1px solid {COLORS['border']} !important;
        color: {COLORS['muted']} !important;
        border-radius: 3px !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 11px !important;
    }}
    .stButton > button[kind="secondary"]:hover {{
        border-color: {COLORS['red']} !important;
        color: {COLORS['red']} !important;
    }}

    /* Expander */
    [data-testid="stExpander"] {{
        background: {COLORS['panel']};
        border: 1px solid {COLORS['border']} !important;
        border-radius: 4px !important;
    }}
    [data-testid="stExpander"] summary {{
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
        color: {COLORS['muted']} !important;
    }}

    /* Slider */
    [data-testid="stSlider"] {{
        padding: 0 !important;
    }}

    /* Dataframe */
    [data-testid="stDataFrame"] {{
        border: 1px solid {COLORS['border']};
        border-radius: 4px;
    }}

    /* Spinner */
    [data-testid="stSpinner"] {{
        color: {COLORS['accent']} !important;
    }}

    /* Info/success/error */
    [data-testid="stAlert"] {{
        border-radius: 4px !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
    }}

    /* Select box */
    [data-testid="stSelectbox"] select {{
        background: {COLORS['panel']} !important;
        border: 1px solid {COLORS['border']} !important;
        color: {COLORS['text']} !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
    }}
</style>
""",
    unsafe_allow_html=True,
)


# ─── Plotly theme ─────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=COLORS["panel"],
    font=dict(family="IBM Plex Mono", color=COLORS["muted"], size=11),
    title_font=dict(family="IBM Plex Mono", color=COLORS["text"], size=13),
    xaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"], tickfont=dict(size=10)),
    yaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"], tickfont=dict(size=10)),
    margin=dict(t=48, b=16, l=8, r=8),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
)


# ─── Health check ─────────────────────────────────────────────
@st.cache_data(ttl=10)
def get_health():
    try:
        return requests.get(f"{API_URL}/health", timeout=3).json()
    except Exception:
        return None


# ─── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"""
    <div style="padding: 24px 16px 20px; border-bottom: 1px solid {COLORS['border']}; margin-bottom: 8px;">
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: {COLORS['muted']}; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 8px;">SYSTEM</div>
        <div style="font-family: 'IBM Plex Sans', sans-serif; font-size: 20px; font-weight: 700; color: {COLORS['text']};">FinComply</div>
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: {COLORS['accent']}; letter-spacing: 1px; margin-top: 4px;">COMPLIANCE INTELLIGENCE v1.0</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "NAV",
        ["Q&A Interface", "Document Manager", "Query Analytics", "Feedback Report"],
        label_visibility="collapsed",
    )

    # System status
    health = get_health()
    st.markdown(
        f"""
    <div style="padding: 16px; margin-top: 16px; border-top: 1px solid {COLORS['border']};">
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: {COLORS['muted']}; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px;">SYSTEM STATUS</div>
    """,
        unsafe_allow_html=True,
    )

    if health:
        status = health.get("status", "unknown")
        components = [
            ("VECTOR DB", health.get("qdrant", False)),
            ("DATABASE", health.get("postgres", False)),
            ("AI MODEL", health.get("model_loaded", False)),
        ]
        for name, ok in components:
            color = COLORS["green"] if ok else COLORS["red"]
            dot = "●" if ok else "○"
            st.markdown(
                f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: {COLORS['muted']}; letter-spacing: 1px;">{name}</span>
                <span style="font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: {color};">{dot} {'OK' if ok else 'ERR'}</span>
            </div>
            """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f'<div style="font-family: IBM Plex Mono; font-size: 11px; color: {COLORS["red"]};">● OFFLINE</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
    </div>
    <div style="padding: 0 16px; margin-top: auto;">
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: {COLORS['border']}; letter-spacing: 1px; line-height: 1.8;">
            ENGINE: bge-m3 + LLaMA 3.3<br>
            STORE: Qdrant · PostgreSQL<br>
            CACHE: Redis
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


# ─── Page header helper ───────────────────────────────────────
def page_header(title: str, subtitle: str, tag: str = ""):
    st.markdown(
        f"""
    <div style="padding: 8px 0 28px; border-bottom: 1px solid {COLORS['border']}; margin-bottom: 28px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 6px;">
            <div style="font-family: 'IBM Plex Sans', sans-serif; font-size: 26px; font-weight: 700; color: {COLORS['text']};">{title}</div>
            {'<div style="font-family: IBM Plex Mono; font-size: 10px; background: ' + COLORS['dim'] + '; color: ' + COLORS['accent'] + '; padding: 3px 10px; border-radius: 2px; letter-spacing: 1px;">' + tag + '</div>' if tag else ''}
        </div>
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: {COLORS['muted']}; letter-spacing: 0.5px;">{subtitle}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


# ─── Page 1: Q&A Interface ────────────────────────────────────
if page == "Q&A Interface":
    page_header("⚖️ Compliance Q&A", "Query indexed regulatory documents using natural language", "RAG PIPELINE")

    examples = [
        "ธุรกรรมที่มีเหตุอันควรสงสัยคืออะไร",
        "สถาบันการเงินมีหน้าที่รายงานอะไรบ้าง",
        "What are the FATF customer due diligence requirements?",
        "How should suspicious transactions be reported?",
    ]

    with st.expander("EXAMPLE QUERIES", expanded=False):
        c1, c2 = st.columns(2)
        for i, ex in enumerate(examples):
            col = c1 if i % 2 == 0 else c2
            if col.button(f"› {ex}", key=ex, use_container_width=True):
                st.session_state["query_input"] = ex
                st.rerun()

    # Query input
    st.markdown(
        f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["muted"]}; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 6px;">QUERY INPUT</div>',
        unsafe_allow_html=True,
    )
    query = st.text_area(
        "query",
        value=st.session_state.get("query_input", ""),
        height=90,
        placeholder="Enter your compliance question...",
        label_visibility="collapsed",
    )

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        st.markdown(
            f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["muted"]}; letter-spacing: 2px; margin-bottom: 4px;">SOURCES</div>',
            unsafe_allow_html=True,
        )
        top_k = st.slider("k", 1, 10, 5, label_visibility="collapsed")
    with col3:
        st.write("")
        st.write("")
        submit = st.button("⟶ EXECUTE QUERY", type="primary", use_container_width=True)

    if submit and query.strip():
        with st.spinner("Searching..."):
            try:
                resp = requests.post(
                    f"{API_URL}/query",
                    json={"query": query, "top_k": top_k},
                    timeout=60,
                ).json()
                st.session_state["last_query_id"] = resp.get("query_id")

                # Answer
                st.markdown(
                    f"""
                <div style="
                    background: {COLORS['panel']};
                    border: 1px solid {COLORS['border']};
                    border-left: 3px solid {COLORS['accent']};
                    border-radius: 4px;
                    padding: 24px 28px;
                    margin: 20px 0;
                    font-family: 'IBM Plex Sans', sans-serif;
                    font-size: 14px;
                    line-height: 1.9;
                    color: {COLORS['text']};
                    position: relative;
                ">
                    <div style="font-family: IBM Plex Mono; font-size: 9px; color: {COLORS['accent']}; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px;">RESPONSE</div>
                    {resp["answer"]}
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # Metrics row
                latency = resp["latency_ms"]
                latency_color = (
                    COLORS["green"] if latency < 3000 else COLORS["gold"] if latency < 8000 else COLORS["red"]
                )
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("LATENCY", f"{latency}ms")
                m2.metric("SOURCES RETRIEVED", len(resp["sources"]))
                m3.metric("MODEL", resp["model"].split("-")[0].upper())
                m4.metric("QUERY ID", resp.get("query_id", "—")[:8] + "...")

                # Sources
                st.markdown(
                    f"""
                <div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS['muted']}; letter-spacing: 2px; text-transform: uppercase; margin: 24px 0 12px;">
                    RETRIEVED DOCUMENTS [{len(resp['sources'])}]
                </div>
                """,
                    unsafe_allow_html=True,
                )

                for i, src in enumerate(resp["sources"], 1):
                    score = src.get("rerank_score", src.get("score", 0))
                    score_pct = int(score * 100) if score <= 1 else int(score)
                    score_color = (
                        COLORS["green"] if score_pct > 70 else COLORS["gold"] if score_pct > 30 else COLORS["muted"]
                    )
                    bar_width = min(score_pct, 100)

                    with st.expander(f"[{i:02d}] {src['filename']}  —  pg.{src['page_num']}  —  {src['source']}"):
                        st.markdown(
                            f"""
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                            <div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS['muted']};">RELEVANCE</div>
                            <div style="flex: 1; height: 3px; background: {COLORS['border']}; border-radius: 2px; overflow: hidden;">
                                <div style="width: {bar_width}%; height: 100%; background: {score_color};"></div>
                            </div>
                            <div style="font-family: IBM Plex Mono; font-size: 11px; color: {score_color}; font-weight: 600;">{score:.3f}</div>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f'<div style="font-size: 13px; color: {COLORS["text"]}; line-height: 1.7; padding: 8px 0;">{src.get("excerpt", src.get("text", ""))}</div>',
                            unsafe_allow_html=True,
                        )

                # Feedback
                st.markdown(
                    f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["muted"]}; letter-spacing: 2px; text-transform: uppercase; margin: 24px 0 10px;">FEEDBACK</div>',
                    unsafe_allow_html=True,
                )
                fb1, fb2 = st.columns(2)
                if fb1.button("↑ MARK HELPFUL", use_container_width=True):
                    requests.post(f"{API_URL}/feedback/{resp['query_id']}", json={"rating": 1})
                    st.success("Feedback recorded.")
                if fb2.button("↓ NEEDS IMPROVEMENT", type="secondary", use_container_width=True):
                    requests.post(f"{API_URL}/feedback/{resp['query_id']}", json={"rating": -1})
                    st.info("Feedback recorded.")

            except Exception as e:
                st.error(f"Query failed: {e}")

    elif submit:
        st.warning("Query field is empty.")


# ─── Page 2: Document Manager ─────────────────────────────────
elif page == "Document Manager":
    page_header("📁 Document Manager", "Manage regulatory documents indexed in the knowledge base", "KNOWLEDGE BASE")

    try:
        docs = requests.get(f"{API_URL}/documents", timeout=5).json()

        if not docs:
            st.info("No documents indexed. Add PDFs to data/raw/ and run `make ingest`.")
        else:
            df = pd.DataFrame(docs)

            # Top stats bar
            total_chunks = int(df["chunk_count"].fillna(0).sum())
            total_pages = int(df["page_count"].fillna(0).sum())
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("DOCUMENTS", len(df))
            s2.metric("TOTAL CHUNKS", f"{total_chunks:,}")
            s3.metric("TOTAL PAGES", f"{total_pages:,}")
            s4.metric("AVG CHUNKS/DOC", f"{total_chunks // max(len(df), 1):,}")

            st.markdown("<br>", unsafe_allow_html=True)

            col1, col2 = st.columns([3, 2])

            with col1:
                st.markdown(
                    f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["muted"]}; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px;">INDEXED DOCUMENTS</div>',
                    unsafe_allow_html=True,
                )
                display = df.copy()
                display["indexed_at"] = pd.to_datetime(display["indexed_at"]).dt.strftime("%Y-%m-%d %H:%M")
                display["chunk_count"] = display["chunk_count"].fillna(0).astype(int)
                display["page_count"] = display["page_count"].fillna(0).astype(int)
                st.dataframe(
                    display[["filename", "source", "page_count", "chunk_count", "status", "indexed_at"]].rename(
                        columns={
                            "filename": "Document",
                            "source": "Source",
                            "page_count": "Pages",
                            "chunk_count": "Chunks",
                            "status": "Status",
                            "indexed_at": "Indexed At",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown(
                    f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["muted"]}; letter-spacing: 2px; text-transform: uppercase; margin: 20px 0 10px;">REMOVE DOCUMENT</div>',
                    unsafe_allow_html=True,
                )
                to_delete = st.selectbox("doc", [d["filename"] for d in docs], label_visibility="collapsed")
                if st.button("⊗ DELETE DOCUMENT", type="secondary"):
                    resp = requests.delete(f"{API_URL}/documents/{to_delete}", timeout=10)
                    if resp.status_code == 200:
                        st.success(f"Removed: {to_delete}")
                        st.rerun()
                    else:
                        st.error("Deletion failed.")

            with col2:
                # Chunks by document bar chart
                fig1 = go.Figure(
                    go.Bar(
                        x=df["chunk_count"].fillna(0).astype(int),
                        y=df["filename"],
                        orientation="h",
                        marker=dict(
                            color=df["chunk_count"].fillna(0),
                            colorscale=[[0, COLORS["dim"]], [1, COLORS["accent"]]],
                            showscale=False,
                        ),
                        text=df["chunk_count"].fillna(0).astype(int),
                        textposition="outside",
                        textfont=dict(family="IBM Plex Mono", size=11, color=COLORS["muted"]),
                    )
                )
                fig1.update_layout(
                    **CHART_LAYOUT,
                    title="Chunks per Document",
                    height=200,
                    yaxis=dict(tickfont=dict(size=10, family="IBM Plex Mono"), gridcolor=COLORS["border"]),
                )
                st.plotly_chart(fig1, use_container_width=True)

                # Source donut
                by_source = df.groupby("source").size().reset_index(name="count")
                fig2 = go.Figure(
                    go.Pie(
                        labels=by_source["source"],
                        values=by_source["count"],
                        hole=0.6,
                        marker=dict(colors=[COLORS["accent"], COLORS["gold"], COLORS["green"]]),
                        textfont=dict(family="IBM Plex Mono", size=10),
                    )
                )
                fig2.update_layout(
                    **CHART_LAYOUT,
                    title="By Source",
                    height=220,
                    showlegend=True,
                )
                st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"Failed to fetch documents: {e}")


# ─── Page 3: Query Analytics ──────────────────────────────────
elif page == "Query Analytics":
    page_header("📊 Query Analytics", "Performance metrics, latency distribution, query volume", "MONITORING")

    try:
        history = requests.get(f"{API_URL}/query/history?limit=200", timeout=5).json()

        if not history:
            st.info("No queries recorded yet.")
        else:
            df = pd.DataFrame(history)
            df["created_at"] = pd.to_datetime(df["created_at"])
            df["date"] = df["created_at"].dt.date
            df["hour"] = df["created_at"].dt.hour

            positive = int((df["rating"] == 1).sum())
            avg_lat = df["latency_ms"].mean()
            p95_lat = df["latency_ms"].quantile(0.95)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("TOTAL QUERIES", f"{len(df):,}")
            m2.metric("AVG LATENCY", f"{avg_lat:.0f}ms")
            m3.metric("P95 LATENCY", f"{p95_lat:.0f}ms")
            m4.metric("POSITIVE FEEDBACK", f"{positive}/{len(df)}")

            st.markdown("<br>", unsafe_allow_html=True)

            # Row 1: volume + latency over time
            c1, c2 = st.columns(2)
            with c1:
                daily = df.groupby("date").size().reset_index(name="queries")
                fig1 = go.Figure()
                fig1.add_trace(
                    go.Scatter(
                        x=daily["date"],
                        y=daily["queries"],
                        fill="tozeroy",
                        fillcolor=f"rgba(14,165,233,0.12)",
                        line=dict(color=COLORS["accent"], width=2),
                        mode="lines+markers",
                        marker=dict(size=5, color=COLORS["accent"]),
                    )
                )
                fig1.update_layout(**CHART_LAYOUT, title="QUERY VOLUME", height=220)
                st.plotly_chart(fig1, use_container_width=True)

            with c2:
                daily_lat = df.groupby("date")["latency_ms"].agg(["mean", "max", "min"]).reset_index()
                fig2 = go.Figure()
                fig2.add_trace(
                    go.Scatter(
                        x=daily_lat["date"],
                        y=daily_lat["max"],
                        name="MAX",
                        line=dict(color=COLORS["red"], width=1, dash="dot"),
                    )
                )
                fig2.add_trace(
                    go.Scatter(
                        x=daily_lat["date"],
                        y=daily_lat["mean"],
                        name="AVG",
                        line=dict(color=COLORS["gold"], width=2),
                        fill="tonexty",
                        fillcolor="rgba(245,158,11,0.06)",
                    )
                )
                fig2.add_trace(
                    go.Scatter(
                        x=daily_lat["date"],
                        y=daily_lat["min"],
                        name="MIN",
                        line=dict(color=COLORS["green"], width=1, dash="dot"),
                    )
                )
                fig2.update_layout(**CHART_LAYOUT, title="LATENCY TREND (ms)", height=220)
                st.plotly_chart(fig2, use_container_width=True)

            # Row 2: histogram + heatmap
            c3, c4 = st.columns(2)
            with c3:
                fig3 = go.Figure(
                    go.Histogram(
                        x=df["latency_ms"],
                        nbinsx=25,
                        marker=dict(
                            color=df["latency_ms"],
                            colorscale=[[0, COLORS["green"]], [0.5, COLORS["gold"]], [1, COLORS["red"]]],
                            showscale=False,
                        ),
                    )
                )
                fig3.update_layout(**CHART_LAYOUT, title="LATENCY DISTRIBUTION", height=220)
                st.plotly_chart(fig3, use_container_width=True)

            with c4:
                # Hour of day heatmap
                hourly = df.groupby("hour").size().reset_index(name="count")
                all_hours = pd.DataFrame({"hour": range(24)})
                hourly = all_hours.merge(hourly, on="hour", how="left").fillna(0)
                fig4 = go.Figure(
                    go.Bar(
                        x=hourly["hour"],
                        y=hourly["count"],
                        marker=dict(
                            color=hourly["count"],
                            colorscale=[[0, COLORS["panel"]], [1, COLORS["accent"]]],
                            showscale=False,
                        ),
                    )
                )
                fig4.update_layout(
                    **CHART_LAYOUT,
                    title="QUERIES BY HOUR",
                    height=220,
                    xaxis=dict(tickmode="linear", dtick=4, gridcolor=COLORS["border"]),
                )
                st.plotly_chart(fig4, use_container_width=True)

            # Recent queries table
            st.markdown(
                f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["muted"]}; letter-spacing: 2px; text-transform: uppercase; margin: 8px 0 12px;">RECENT QUERIES</div>',
                unsafe_allow_html=True,
            )
            recent = df[["query_text", "latency_ms", "rating", "created_at"]].head(15).copy()
            recent["rating"] = recent["rating"].map({1.0: "↑ YES", -1.0: "↓ NO", None: "—"})
            recent["created_at"] = recent["created_at"].dt.strftime("%H:%M:%S")
            recent.columns = ["Query", "Latency (ms)", "Helpful", "Time"]
            st.dataframe(recent, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Failed to fetch analytics: {e}")


# ─── Page 4: Feedback Report ──────────────────────────────────
elif page == "Feedback Report":
    page_header("💬 Feedback Report", "Answer quality metrics and user satisfaction analysis", "QUALITY")

    try:
        history = requests.get(f"{API_URL}/query/history?limit=500", timeout=5).json()

        if not history:
            st.info("No feedback recorded yet.")
        else:
            df = pd.DataFrame(history)
            df["created_at"] = pd.to_datetime(df["created_at"])
            df["date"] = df["created_at"].dt.date
            rated = df[df["rating"].notna()].copy()

            if rated.empty:
                st.info("No feedback yet. Rate answers in Q&A Interface.")
            else:
                positive = int((rated["rating"] == 1).sum())
                negative = int((rated["rating"] == -1).sum())
                total = len(rated)
                sat_rate = positive / total * 100

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("TOTAL RATED", total)
                m2.metric("↑ POSITIVE", positive)
                m3.metric("↓ NEGATIVE", negative)
                m4.metric(
                    "SATISFACTION",
                    f"{sat_rate:.1f}%",
                    delta=f"+{sat_rate-50:.1f}%" if sat_rate > 50 else f"{sat_rate-50:.1f}%",
                )

                st.markdown("<br>", unsafe_allow_html=True)
                c1, c2 = st.columns(2)

                with c1:
                    # Gauge chart for satisfaction
                    fig1 = go.Figure(
                        go.Indicator(
                            mode="gauge+number",
                            value=sat_rate,
                            number=dict(suffix="%", font=dict(family="IBM Plex Mono", size=32, color=COLORS["text"])),
                            gauge=dict(
                                axis=dict(
                                    range=[0, 100],
                                    tickcolor=COLORS["muted"],
                                    tickfont=dict(family="IBM Plex Mono", size=10, color=COLORS["muted"]),
                                ),
                                bar=dict(
                                    color=(
                                        COLORS["accent"]
                                        if sat_rate > 70
                                        else COLORS["gold"] if sat_rate > 40 else COLORS["red"]
                                    ),
                                    thickness=0.3,
                                ),
                                bgcolor=COLORS["panel"],
                                bordercolor=COLORS["border"],
                                borderwidth=1,
                                steps=[
                                    dict(range=[0, 40], color=COLORS["bg"]),
                                    dict(range=[40, 70], color=COLORS["surface"]),
                                    dict(range=[70, 100], color=COLORS["panel"]),
                                ],
                                threshold=dict(line=dict(color=COLORS["green"], width=2), thickness=0.75, value=70),
                            ),
                            title=dict(
                                text="SATISFACTION RATE",
                                font=dict(family="IBM Plex Mono", size=11, color=COLORS["muted"]),
                            ),
                        )
                    )
                    fig1.update_layout(**CHART_LAYOUT, height=260)
                    st.plotly_chart(fig1, use_container_width=True)

                with c2:
                    rated_daily = rated.copy()
                    rated_daily["date"] = rated_daily["created_at"].dt.date
                    daily = rated_daily.groupby(["date", "rating"]).size().unstack(fill_value=0).reset_index()
                    fig2 = go.Figure()
                    if 1.0 in daily.columns:
                        fig2.add_trace(
                            go.Bar(x=daily["date"], y=daily[1.0], name="Positive", marker_color=COLORS["green"])
                        )
                    if -1.0 in daily.columns:
                        fig2.add_trace(
                            go.Bar(x=daily["date"], y=daily[-1.0], name="Negative", marker_color=COLORS["red"])
                        )
                    fig2.update_layout(**CHART_LAYOUT, title="FEEDBACK OVER TIME", barmode="stack", height=260)
                    st.plotly_chart(fig2, use_container_width=True)

                if negative > 0:
                    st.markdown(
                        f'<div style="font-family: IBM Plex Mono; font-size: 10px; color: {COLORS["red"]}; letter-spacing: 2px; text-transform: uppercase; margin: 16px 0 10px;">⚠ QUERIES NEEDING IMPROVEMENT [{negative}]</div>',
                        unsafe_allow_html=True,
                    )
                    neg_df = rated[rated["rating"] == -1.0][["query_text", "created_at"]].head(10).copy()
                    neg_df["created_at"] = neg_df["created_at"].dt.strftime("%Y-%m-%d %H:%M")
                    neg_df.columns = ["Query", "Time"]
                    st.dataframe(neg_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Failed to fetch feedback: {e}")
