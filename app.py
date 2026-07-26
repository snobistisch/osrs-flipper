"""Streamlit dashboard: ranked flips with filter sliders + timeseries detail.

Run from this directory: .venv/bin/streamlit run app.py
Theme colors live in .streamlit/config.toml; the CSS below adds the
Grand Exchange look on top of them.
"""
from __future__ import annotations

import time

import altair as alt
import pandas as pd
import streamlit as st

import api
import engine
import filters

st.set_page_config(page_title="GE Flipper", page_icon="🪙", layout="wide")

# Chart series colors follow the entity across both charts: the instant-buy
# side is always blue, the instant-sell side always orange (validated pair
# for dark surfaces — the theme forces dark mode).
SERIES = {"instant-buy": "#3987e5", "instant-sell": "#d95926", "rule": "#898781"}
BUY_SIDE = "Instant-buy (your sell fills here)"
SELL_SIDE = "Instant-sell (your buy fills here)"

RUNESCAPE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&display=swap');

h1, h2, h3 {
    font-family: 'Cinzel', 'Times New Roman', serif !important;
    color: #ffb83f !important;
    text-shadow: 2px 2px 0 #14100b;
    letter-spacing: 0.03em;
}
[data-testid="stSidebar"] {
    background: #332a1f;
    border-right: 3px solid #14100b;
    box-shadow: inset -1px 0 0 #5c4f3a;
}
.stButton > button, [data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(#4a3d2b, #382e20);
    color: #ffb83f;
    border: 2px solid #14100b;
    border-radius: 3px;
    box-shadow: inset 0 0 0 1px #6b5b40;
    font-weight: 600;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
    border-color: #ffb83f;
    color: #ffe97f;
}
[data-testid="stMetricValue"] {
    color: #ffff00;
    text-shadow: 1px 1px 0 #14100b;
}
[data-testid="stMetricLabel"] { color: #c9b998; }
[data-testid="stMetricDelta"] { color: #c9b998 !important; }
</style>
"""


@st.cache_resource
def wiki_client() -> api.WikiClient:
    return api.WikiClient()


@st.cache_data(ttl=120, show_spinner="Fetching price history…")
def timeseries_frame(item_id: int, timestep: str) -> pd.DataFrame:
    df = pd.DataFrame(wiki_client().timeseries(item_id, timestep))
    if df.empty or "timestamp" not in df.columns:
        return pd.DataFrame()
    df["time"] = pd.to_datetime(df["timestamp"], unit="s")
    return df


def landing():
    """First visit: ask for the player's flipping budget before anything else."""
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title("🪙 Grand Exchange Flipper")
        st.markdown(
            "Live F2P flip finder on OSRS Wiki real-time prices. Margins are "
            "shown after GE tax, capped by buy limits and traded volume, and "
            "priced conservatively so a single outlier trade can't fool you.")
        with st.form("budget"):
            raw = st.text_input("How much gp do you have to flip with?",
                                placeholder="e.g. 250k, 1.5m or 1,000,000")
            submitted = st.form_submit_button("Start flipping")
        if submitted:
            try:
                capital = engine.parse_gp(raw)
            except ValueError:
                st.error("Enter an amount like 250k, 1.5m or 1,000,000.")
                return
            if capital > engine.MAX_CASH_STACK:
                st.error("That's more than the max cash stack "
                         "(2,147,483,647 gp). Enter your real budget.")
                return
            st.session_state.capital = capital
            st.rerun()


def sidebar_config(capital: int) -> "tuple[filters.FilterConfig, int]":
    with st.sidebar:
        slots = st.selectbox("GE offer slots", [engine.F2P_SLOTS, engine.MEMBER_SLOTS],
                             format_func=lambda s: "{} — {}".format(
                                 s, "free-to-play" if s == engine.F2P_SLOTS
                                 else "members"),
                             help="Slots are the real bottleneck. Your budget "
                                  "is split across them.")
        st.metric("Budget", engine.format_gp(capital) + " gp",
                  delta="{} gp per flip".format(engine.format_gp(
                      engine.capital_per_slot(capital, slots))),
                  delta_color="off", help="{:,} gp".format(capital))
        if st.button("Change budget"):
            del st.session_state["capital"]
            st.rerun()
        st.header("Filters")
        min_depth = st.slider("Min undercut room (gp)", 0, 50, 1,
                              help="Price improvement you can afford per side. "
                                   "At 0 you cannot outbid anyone and just wait "
                                   "in the queue — the air rune trap.")
        max_age = st.slider("Max quote age (s)", 30, 3_600, 300, step=30,
                            help="Age of the OLDER of the two /latest sides. "
                                 "Wide margins on stale quotes are dead items.")
        min_vol = st.slider("Min thin-side volume / 1h", 0, 2_000, 120, step=10,
                            help="Units traded on the quieter side of the book "
                                 "in the last hour.")
        min_roi = st.slider("Min ROI after tax (%)", 0.0, 10.0, 1.0, step=0.1)
        include_members = st.checkbox("Include members items", value=False)
        top_n = st.slider("Rows", 10, 100, 50, step=10)
        st.caption("Prices refetch at most once per 30 s "
                   "(wiki acceptable-use policy).")
    return filters.FilterConfig(
        capital=capital, slots=slots, include_members=include_members,
        max_quote_age=max_age, min_thin_volume_1h=min_vol,
        min_roi=min_roi / 100, min_undercut_depth=min_depth), top_n


def ranked_table(rows, top_n):
    df = pd.DataFrame([{
        "Item": r.name, "Buy": r.buy, "Sell": r.sell, "Margin": r.margin,
        "ROI %": r.roi * 100, "Room": r.undercut_depth,
        "Fill %": r.fill_share * 100 if r.deep_checked else None,
        "Trend %": r.trend * 100 if r.deep_checked else None,
        "Elev %": r.elevation * 100 if r.deep_checked else None,
        "Limit": r.limit, "Vol/1h": r.thin_volume_1h,
        "Qty/4h": r.qty_per_window, "Tied up": r.capital_needed,
        "Quoted/4h": r.gross_profit, "EV/slot/h": round(r.gp_per_slot_hour),
    } for r in rows[:top_n]])
    gp = st.column_config.NumberColumn(format="localized")
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Buy": gp, "Sell": gp, "Margin": gp, "Limit": gp, "Vol/1h": gp,
        "Qty/4h": gp, "Tied up": gp, "Quoted/4h": gp, "EV/slot/h": gp,
        "Room": st.column_config.NumberColumn(
            help="Gp of price improvement you can afford per side. 0 means you "
                 "cannot outbid the queue."),
        "Fill %": st.column_config.NumberColumn(
            format="%.0f%%", help="Share of the last 14 days' volume that "
            "traded at your prices — the last print is not the market."),
        "Trend %": st.column_config.NumberColumn(
            format="%.0f%%", help="Recent vs prior multi-day VWAP."),
        "Elev %": st.column_config.NumberColumn(
            format="%.0f%%", help="Quote vs the item's 14-day median level — "
            "high means spike/manipulation risk."),
        "ROI %": st.column_config.NumberColumn(format="%.1f%%"),
    })
    st.caption("EV/slot/h ranks the table: quoted profit discounted for queue "
               "position, drift, staleness, 14-day fill probability and "
               "momentum. Blank Fill/Trend = outside the deep-checked top 15.")


def detail_view(row):
    left, mid, right = st.columns(3)
    left.metric("Est. buy → sell", "{:,} → {:,} gp".format(row.buy, row.sell),
                help="Raw /latest quote: {:,} → {:,} gp".format(
                    row.latest_low, row.latest_high))
    mid.metric("Margin after tax", "{:,} gp".format(row.margin),
               delta="{:.1%} ROI".format(row.roi), delta_color="off",
               help="Tax on this sell price: {:,} gp".format(row.tax))
    right.metric("Expected / slot / hour",
                 "{:,} gp".format(round(row.gp_per_slot_hour)),
                 delta="{:,} gp quoted per 4h".format(row.gross_profit),
                 delta_color="off",
                 help="{:,} units, {:,} gp tied up. Quoted profit is discounted "
                      "for queue position, price drift and quote staleness."
                      .format(row.qty_per_window, row.capital_needed))
    for note in row.warnings:
        st.warning(note, icon="⚠️")

    timestep = st.radio("Timestep", api.TIMESTEPS, index=1, horizontal=True,
                        help="5m ≈ 30h of history, 1h ≈ 15 days, 24h ≈ 1 year")
    try:
        df = timeseries_frame(row.item_id, timestep)
    except api.ApiError as exc:
        st.warning("Could not load history: {}".format(exc))
        return
    if df.empty:
        st.info("The wiki has no {} history for this item.".format(timestep))
        return

    side_scale = alt.Scale(domain=[BUY_SIDE, SELL_SIDE],
                           range=[SERIES["instant-buy"], SERIES["instant-sell"]])
    price = df.melt(id_vars="time",
                    value_vars=["avgHighPrice", "avgLowPrice"],
                    var_name="side", value_name="price").dropna(subset=["price"])
    price["side"] = price["side"].map({"avgHighPrice": BUY_SIDE,
                                       "avgLowPrice": SELL_SIDE})
    hover = alt.selection_point(fields=["time"], nearest=True,
                                on="pointermove", empty=False)
    base = alt.Chart(price).encode(
        x=alt.X("time:T", title=None),
        y=alt.Y("price:Q", title="gp", scale=alt.Scale(zero=False)),
        color=alt.Color("side:N", scale=side_scale,
                        legend=alt.Legend(title=None, orient="top")))
    lines = base.mark_line(strokeWidth=2)
    points = base.mark_point(size=60, filled=True).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("time:T", title="time"),
                 alt.Tooltip("price:Q", title="gp", format=","),
                 alt.Tooltip("side:N", title="side")]).add_params(hover)
    rule = alt.Chart(price).mark_rule(color=SERIES["rule"]).encode(
        x="time:T").transform_filter(hover)
    st.altair_chart((lines + points + rule).properties(height=300),
                    use_container_width=True)

    volume = df.melt(id_vars="time",
                     value_vars=["highPriceVolume", "lowPriceVolume"],
                     var_name="side", value_name="units").dropna(subset=["units"])
    volume["side"] = volume["side"].map({"highPriceVolume": BUY_SIDE,
                                         "lowPriceVolume": SELL_SIDE})
    bars = alt.Chart(volume).mark_bar(opacity=0.9).encode(
        x=alt.X("time:T", title=None),
        y=alt.Y("units:Q", title="volume"),
        color=alt.Color("side:N", scale=side_scale, legend=None),
        tooltip=[alt.Tooltip("time:T", title="time"),
                 alt.Tooltip("units:Q", title="units", format=","),
                 alt.Tooltip("side:N", title="side")])
    st.altair_chart(bars.properties(height=120), use_container_width=True)
    st.caption("A structural margin shows both lines running parallel with "
               "steady volume. A one-off spike shows one line jumping on a "
               "single near-zero-volume bucket.")


def main():
    st.markdown(RUNESCAPE_CSS, unsafe_allow_html=True)
    if "capital" not in st.session_state:
        landing()
        st.stop()

    config, top_n = sidebar_config(st.session_state.capital)
    client = wiki_client()
    try:
        items = client.mapping()
        quotes = client.latest()
        activity_5m = client.interval("5m")
        activity_1h = client.interval("1h")
    except api.ApiError as exc:
        st.error("Wiki API error: {}".format(exc))
        st.stop()

    rows, funnel = filters.rank_flips(items, quotes, activity_5m, activity_1h,
                                      config, now=time.time())

    def fetch_history(item_id):
        try:
            return client.timeseries(item_id, engine.HISTORY_TIMESTEP)
        except api.ApiError:
            return None

    with st.spinner("Checking the top 15 against 14-day history…"):
        rows, refined = filters.refine_with_history(rows, fetch_history, 15)
    funnel["deep-checked vs 14d history"] = refined
    st.title("🪙 Grand Exchange Flipper")
    st.caption("  →  ".join("{:,} {}".format(v, k)
                            for k, v in funnel.items() if v))
    if st.button("Refresh"):
        st.rerun()
    if not rows:
        st.info("No flips pass the current filters. Loosen min ROI or "
                "min volume in the sidebar.")
        st.stop()
    ranked_table(rows, top_n)

    st.subheader("Detail")
    row = st.selectbox("Item", rows[:top_n],
                       format_func=lambda r: "{} — {:,} gp margin, {:,} gp/slot/h"
                       .format(r.name, r.margin, round(r.gp_per_slot_hour)))
    detail_view(row)


main()
