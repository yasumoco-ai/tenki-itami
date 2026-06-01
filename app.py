import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
import pytz

JST = pytz.timezone("Asia/Tokyo")

# ── 気圧変化の警告レベル（6時間あたりの降下量） ───────────────
LEVEL_DANGER  = -6   # hPa  危険
LEVEL_CAUTION = -3   # hPa  注意

st.set_page_config(page_title="低気圧お知らせアプリ", page_icon="🌀", layout="centered")

# モバイル向けCSS
st.markdown("""
<style>
/* フォントサイズ・余白をスマホ向けに調整 */
@media (max-width: 640px) {
    h1 { font-size: 1.4rem !important; }
    .stMetric label { font-size: 0.75rem !important; }
    .stMetric [data-testid="metric-container"] { padding: 8px !important; }
    .block-container { padding: 1rem 0.75rem !important; }
}
/* メトリクスカードをタイル風に */
[data-testid="metric-container"] {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 10px;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

st.title("🌀 低気圧お知らせアプリ")
st.caption("気圧の急降下を48時間先まで予測して、天気痛・頭痛・倦怠感を事前にお知らせします。")


# ── ユーティリティ ─────────────────────────────────────────────
def geocode(city: str) -> tuple[float, float, str]:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": city, "language": "ja", "count": 1}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        raise ValueError(f"「{city}」が見つかりませんでした。別の地名で試してください。")
    res = data["results"][0]
    label = res.get("name", city)
    if res.get("admin1"):
        label = f"{res['admin1']} {label}"
    return res["latitude"], res["longitude"], label


def fetch_pressure(lat: float, lon: float) -> pd.DataFrame:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "surface_pressure",
        "forecast_days": 3,
        "timezone": "Asia/Tokyo",
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame({
        "time": pd.to_datetime(data["hourly"]["time"]),
        "pressure": data["hourly"]["surface_pressure"],
    })
    # 今から48時間分に絞る
    now = datetime.now(JST).replace(tzinfo=None)
    df = df[df["time"] >= now].head(49).reset_index(drop=True)
    # 6時間後との差（マイナス = 降下）
    df["change_6h"] = df["pressure"].shift(-6) - df["pressure"]
    return df


def warning_level(change: float) -> tuple[str, str, str]:
    """(ラベル, 色, アドバイス) を返す"""
    if change <= LEVEL_DANGER:
        return "🔴 危険", "#FF4B4B", "頭痛薬・酔い止めを準備。無理な外出は避け、こまめに休憩を。"
    if change <= LEVEL_CAUTION:
        return "🟡 注意", "#FFA500", "いつもより体が重くなりやすい時間帯です。水分補給と軽めのストレッチを。"
    return "🟢 安全", "#21BA45", "気圧は安定しています。いつも通りの生活でOKです。"


# ── UI ────────────────────────────────────────────────────────
city = st.text_input("地名を入力（例：恵庭、札幌、東京）", value="恵庭")

if st.button("🔍 予報を取得", type="primary", use_container_width=True) or city:
    try:
        with st.spinner("データ取得中…"):
            lat, lon, place_name = geocode(city)
            df = fetch_pressure(lat, lon)

        st.success(f"📍 {place_name} の気圧予報（48時間）")

        # ── 現在の状況 ─────────────────────────────────────
        now_row = df.iloc[0]
        worst_idx = df["change_6h"].idxmin()
        worst_row = df.loc[worst_idx]
        worst_change = worst_row["change_6h"]
        label, color, advice = warning_level(worst_change)

        # スマホで見やすいよう 2+1 配置
        col1, col2 = st.columns(2)
        with col1:
            st.metric("現在の気圧", f"{now_row['pressure']:.1f} hPa")
        with col2:
            worst_time = worst_row["time"].strftime("%m/%d %H:%M")
            st.metric("最大降下タイミング", worst_time)
        st.metric("最大降下量（6時間）", f"{worst_change:+.1f} hPa",
                  delta_color="inverse")

        # ── 警告バナー ──────────────────────────────────────
        st.markdown(
            f"""<div style="background:{color}22; border-left:6px solid {color};
            padding:16px; border-radius:8px; margin:12px 0">
            <span style="font-size:1.4em; font-weight:bold; color:{color}">{label}</span><br>
            <span style="font-size:1em">{advice}</span></div>""",
            unsafe_allow_html=True,
        )

        # ── 気圧グラフ ──────────────────────────────────────
        fig = go.Figure()

        # 危険帯の背景
        fig.add_hrect(y0=0, y1=df["pressure"].min() - 5,
                      fillcolor="red", opacity=0.05, line_width=0)

        # 気圧折れ線
        fig.add_trace(go.Scatter(
            x=df["time"], y=df["pressure"],
            mode="lines+markers",
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=4),
            name="気圧 (hPa)",
            hovertemplate="%{x|%m/%d %H:%M}<br>%{y:.1f} hPa<extra></extra>",
        ))

        # 最大降下点をマーク
        fig.add_trace(go.Scatter(
            x=[worst_row["time"]], y=[worst_row["pressure"]],
            mode="markers",
            marker=dict(size=14, color=color, symbol="star"),
            name="最大降下点",
            hovertemplate=f"{worst_time}<br>{worst_row['pressure']:.1f} hPa<extra>最大降下点</extra>",
        ))

        fig.update_layout(
            xaxis_title="時刻",
            yaxis_title="気圧 (hPa)",
            hovermode="x unified",
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── 時間別一覧（6時間ごと） ─────────────────────────
        st.markdown("#### 時間帯別の警告レベル")
        step_df = df.iloc[::6].copy()
        for _, row in step_df.iterrows():
            if pd.isna(row["change_6h"]):
                continue
            lv, cl, _ = warning_level(row["change_6h"])
            time_str = row["time"].strftime("%m/%d %H:%M")
            chg = row["change_6h"]
            st.markdown(
                f"""<div style="padding:10px 14px; border-radius:8px; margin:6px 0;
                background:{cl}15; border-left:5px solid {cl}">
                <div style="font-weight:bold; font-size:1rem">{lv}　{time_str}</div>
                <div style="font-size:0.9rem; margin-top:4px; color:#555">
                  気圧 {row['pressure']:.1f} hPa　変化 <b style="color:{cl}">{chg:+.1f} hPa/6h</b>
                </div></div>""",
                unsafe_allow_html=True,
            )

    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"データ取得に失敗しました：{e}")

st.divider()
st.caption(
    "気象データ：[Open-Meteo](https://open-meteo.com/)（無料・商用利用可）　"
    "⚠️ 本アプリは医療情報ではありません。体調が優れない場合は医師にご相談ください。"
)
