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
import archive
import engine
import exemptions
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


@st.cache_resource
def tick_archive():
    """The tick archive, if collect.py has been building one.

    Optional by design: without it the tool falls back to a single live 1-hour
    bucket per item, which is one sample of a quantity that swings with the
    time of day. With it, throughput is averaged over days.
    """
    try:
        store = archive.Archive()
        if store.summary()["buckets"] == 0:
            store.close()
            return None
        return store
    except Exception:
        return None


def volume_lookup():
    store = tick_archive()
    if store is None:
        return None

    def lookup(item_id):
        estimate = store.volume_ewma(item_id)
        if estimate is None or not estimate.usable:
            return None
        return estimate.high_per_hour, estimate.low_per_hour
    return lookup


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


def sidebar_config(capital: int, nature_cost: int) -> "tuple[filters.FilterConfig, int]":
    with st.sidebar:
        slots = st.selectbox("GE offer slots", [engine.F2P_SLOTS, engine.MEMBER_SLOTS],
                             format_func=lambda s: "{} — {}".format(
                                 s, "free-to-play" if s == engine.F2P_SLOTS
                                 else "members"),
                             help="Slots are the real bottleneck. Capital is "
                                  "split across them in proportion to score, "
                                  "not equally.")
        st.metric("Budget", engine.format_gp(capital) + " gp",
                  delta="{} gp per flip if split evenly".format(
                      engine.format_gp(engine.capital_per_slot(capital, slots))),
                  delta_color="off", help="{:,} gp".format(capital))
        if st.button("Change budget"):
            del st.session_state["capital"]
            st.rerun()

        include_members = st.checkbox("Include members items", value=False)

        st.header("Display filters")
        st.caption("These hide rows. Everything tradable is scored and shrunk "
                   "first, so narrowing the view never reorders what is left.")
        min_depth = st.slider("Min undercut room (gp)", 0, 50, 0,
                              help="Price improvement you can afford per side. "
                                   "At 0 you cannot outbid anyone and wait in "
                                   "the queue — the air rune trap. This is now "
                                   "priced into the fill time rather than "
                                   "filtered out, so leaving it at 0 is fine.")
        max_age = st.slider("Max quote age (s)", 0, 3_600, 0, step=30,
                            help="0 = no limit. Age of the OLDER of the two "
                                 "/latest sides. Staleness is scored against "
                                 "the item's own volatility, so this is a view "
                                 "preference, not a correctness gate.")
        min_vol = st.slider("Min thin-side volume / 1h", 0, 10_000, 0, step=20,
                            help="Units traded on the quieter side of the book. "
                                 "Thin volume already costs an item heavily in "
                                 "both fill time and shrinkage.")
        min_roi = st.slider("Min ROI after tax (%)", 0.0, 10.0, 0.0, step=0.1)
        col_lo, col_hi = st.columns(2)
        min_price_raw = col_lo.text_input("Min price", value="",
                                          placeholder="e.g. 100")
        max_price_raw = col_hi.text_input("Max price", value="",
                                          placeholder="e.g. 10k")
        tax_free = st.checkbox("Tax-free items only", value=False,
                               help="Sells under 50 gp round the 2% tax down "
                                    "to zero, as do ~57 exempt items "
                                    "(tax_exempt.json).")
        top_n = st.slider("Rows", 10, 100, 50, step=10)
        st.caption("Nature rune {:,} gp (live) — the cost side of the high-alch "
                   "floor. Prices refetch at most once per 30 s (wiki "
                   "acceptable-use policy).".format(nature_cost))

    def parse_price(raw):
        try:
            return engine.parse_gp(raw)
        except ValueError:
            return None

    return filters.FilterConfig(
        capital=capital, slots=slots, include_members=include_members,
        nature_rune_cost=nature_cost,
        max_quote_age=max_age or None, min_thin_volume_1h=min_vol,
        min_roi=min_roi / 100, min_undercut_depth=min_depth,
        min_price=parse_price(min_price_raw) or 1,
        max_price=parse_price(max_price_raw),
        tax_free_only=tax_free), top_n


def ranked_table(rows, top_n):
    df = pd.DataFrame([{
        "Item": r.name, "Buy": r.buy, "List at": r.sell_listed_at,
        "Margin": r.margin, "ROI %": r.roi * 100, "Room": r.undercut_depth,
        "Qty": r.qty_per_window, "Tied up": r.capital_needed,
        "Round trip": engine.format_duration(r.expected_total_seconds),
        "P(fill) %": r.p_fill * 100,
        "Alch floor %": (r.alch_distance * 100
                         if r.alch_distance is not None else None),
        "Fill %": r.fill_share * 100 if r.deep_checked else None,
        "Reverts": r.mean_reverting if r.deep_checked else None,
        "Measured": round(r.raw_gp_per_slot_hour),
        "EV/slot/h": round(r.gp_per_slot_hour),
    } for r in rows[:top_n]])
    gp = st.column_config.NumberColumn(format="localized")
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Buy": gp, "Margin": gp, "Qty": gp, "Tied up": gp, "EV/slot/h": gp,
        "List at": st.column_config.NumberColumn(
            format="localized",
            help="Where to place the sell offer. The GE tax rounds down, so "
                 "every price inside a 50 gp band nets the seller the same — "
                 "the lowest one buys queue priority for free."),
        "Room": st.column_config.NumberColumn(
            help="Gp of price improvement you can afford per side. 0 means you "
                 "cannot outbid the queue, which the fill time now prices."),
        "Round trip": st.column_config.TextColumn(
            help="Expected time for both legs at your queue position. This is "
                 "the denominator of EV/slot/h."),
        "P(fill) %": st.column_config.NumberColumn(
            format="%.0f%%", help="Chance both legs clear inside 4 hours."),
        "Alch floor %": st.column_config.NumberColumn(
            format="%.0f%%", help="How far the buy price sits above the high "
            "alchemy value. Negative means alching pays more than the market — "
            "a guaranteed exit. Small positive means limited downside."),
        "Fill %": st.column_config.NumberColumn(
            format="%.0f%%", help="Share of the last 14 days' volume that "
            "traded at your prices — the last print is not the market."),
        "Reverts": st.column_config.CheckboxColumn(
            help="Whether the fitted OU process mean-reverts significantly. "
                 "Where it does not, 'above its median' carries no prediction."),
        "Measured": st.column_config.NumberColumn(
            format="localized", help="Score before shrinkage."),
        "ROI %": st.column_config.NumberColumn(format="%.1f%%"),
    })
    st.caption("EV/slot/h ranks the table: expected profit divided by the time "
               "the slot is actually occupied, then shrunk toward the market "
               "average by an amount set by how much volume the estimate rests "
               "on. A wide Measured-to-EV gap means the measured number was "
               "mostly thin data. Blank Fill/Reverts = outside the "
               "deep-checked shortlist.")


def detail_view(row):
    left, mid, right, far = st.columns(4)
    left.metric("Est. buy → sell", "{:,} → {:,} gp".format(row.buy, row.sell),
                help="Raw /latest quote: {:,} → {:,} gp. List the sell at "
                     "{:,}.".format(row.latest_low, row.latest_high,
                                    row.sell_listed_at))
    mid.metric("Margin after tax", "{:,} gp".format(row.margin),
               delta="{:.1%} ROI".format(row.roi), delta_color="off",
               help="Tax on this sell price: {:,} gp{}".format(
                   row.tax, " (tax-exempt item)" if row.tax_exempt else ""))
    right.metric("Round trip",
                 engine.format_duration(row.expected_total_seconds),
                 delta="{:.0%} chance both legs clear in 4h".format(row.p_fill),
                 delta_color="off",
                 help="Buy leg {}, sell leg {}. This is the time the slot is "
                      "occupied, and the denominator of the ranking metric."
                      .format(engine.format_duration(row.expected_buy_seconds),
                              engine.format_duration(row.expected_sell_seconds)))
    far.metric("Expected / slot / hour",
               "{:,} gp".format(round(row.gp_per_slot_hour)),
               delta="{:,} before shrinkage".format(
                   round(row.raw_gp_per_slot_hour)),
               delta_color="off",
               help="{:,} units, {:,} gp tied up.".format(
                   row.qty_per_window, row.capital_needed))

    if row.allocated_capital is not None:
        st.info("Score-weighted allocation: commit {} gp of the bank to this "
                "flip rather than an equal {} gp share.".format(
                    engine.format_gp(row.allocated_capital),
                    engine.format_gp(row.capital_needed)), icon="💰")

    with st.expander("Where the score went"):
        st.caption("Each discount is stored separately so a shortfall can be "
                   "attributed to the factor that caused it — the reason the "
                   "journal records these at entry.")
        st.dataframe(pd.DataFrame(
            [{"Factor": name, "Value": "{:.3f}".format(value)}
             for name, value in sorted(row.factors.items())]),
            hide_index=True, width="stretch")

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

    client = wiki_client()
    try:
        items = client.mapping()
        quotes = client.latest()
        activity_5m = client.interval("5m")
        activity_1h = client.interval("1h")
    except api.ApiError as exc:
        st.error("Wiki API error: {}".format(exc))
        st.stop()

    exempt = exemptions.resolve(items)
    nature_cost = exemptions.nature_rune_cost(quotes)
    config, top_n = sidebar_config(st.session_state.capital, nature_cost)

    def fetch_history(item_id):
        try:
            return client.timeseries(item_id, engine.HISTORY_TIMESTEP)
        except api.ApiError:
            return None

    with st.spinner("Scoring every tradable item, then checking the shortlist "
                    "against 14-day history…"):
        result = filters.rank_flips(
            items, quotes, activity_5m, activity_1h, config, now=time.time(),
            fetch_history=fetch_history, top_k=15, exempt=exempt,
            volume_lookup=volume_lookup())

    st.title("🪙 Grand Exchange Flipper")
    funnel = dict(result.funnel)
    funnel["deep-checked vs 14d history"] = result.deep_checked
    st.caption("  →  ".join("{:,} {}".format(v, k)
                            for k, v in funnel.items() if v))
    hidden = {k: v for k, v in result.hidden.items() if v and k != "shown"}
    if hidden:
        st.caption("Hidden by your display filters: " + ", ".join(
            "{:,} {}".format(v, k) for k, v in hidden.items()))
    if exempt.unmatched_names:
        st.warning("tax_exempt.json lists {} names that match no item in "
                   "/mapping — those items are being taxed 2% they may not "
                   "owe: {}".format(len(exempt.unmatched_names),
                                    ", ".join(exempt.unmatched_names)), icon="⚠️")
    if result.shrinkage is not None and not result.shrinkage.informative:
        st.warning("Every difference between today's scores is inside "
                   "estimation noise. The ranking below is not meaningful — "
                   "this is what a market with no edge in it looks like.",
                   icon="⚠️")
    if tick_archive() is None:
        st.caption("No tick archive yet. `python3 collect.py` builds one; it "
                   "is the only input here that competitors polling the same "
                   "API cannot reproduce, and it is worth nothing until it "
                   "has run for months — which is the argument for starting.")

    if st.button("Refresh"):
        st.rerun()
    if not result.rows:
        st.info("Nothing to show. Loosen the display filters in the sidebar, "
                "or the market is genuinely offering nothing right now.")
        st.stop()
    ranked_table(result.rows, top_n)

    st.subheader("Detail")
    row = st.selectbox("Item", result.rows[:top_n],
                       format_func=lambda r: "{} — {:,} gp margin, {:,} gp/slot/h"
                       .format(r.name, r.margin, round(r.gp_per_slot_hour)))
    detail_view(row)


main()
