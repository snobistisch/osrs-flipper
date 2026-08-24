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
import merch

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
            "Live members-first decision terminal for OSRS Wiki real-time "
            "prices. Members get an actionable eight-slot plan by default. "
            "Margins are "
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
        st.header("Trading setup")
        account = st.radio(
            "Account", [engine.AccountType.MEMBERS,
                        engine.AccountType.FREE_TO_PLAY], horizontal=True,
            format_func=lambda value: ("Members · 8 slots" if value is
                                       engine.AccountType.MEMBERS
                                       else "Free-to-play · 3 slots"),
            help="Account type determines both GE slots and item access; "
                 "they cannot contradict each other.")
        mode = st.radio(
            "Strategy", [engine.TradeMode.ACTIVE, engine.TradeMode.OVERNIGHT],
            horizontal=True,
            format_func=lambda value: ("Active" if value is
                                       engine.TradeMode.ACTIVE else "Overnight"),
            help="Active maximizes expected GP per occupied slot-hour. "
                 "Overnight leaves buy offers while you are away, then models "
                 "a separate sell window after you return.")
        overnight_hours = engine.DEFAULT_OVERNIGHT_HOURS
        if mode is engine.TradeMode.OVERNIGHT:
            overnight_hours = st.select_slider(
                "Back in", options=list(engine.OVERNIGHT_HORIZON_PRESETS),
                value=engine.DEFAULT_OVERNIGHT_HOURS,
                format_func=lambda value: "{:.0f} hours".format(value))
        slots = account.slots
        st.metric("Budget", engine.format_gp(capital) + " gp",
                  delta="pooled across {} slots; not pre-split".format(slots),
                  delta_color="off", help="{:,} gp".format(capital))
        if st.button("Change budget"):
            del st.session_state["capital"]
            st.rerun()

        st.header("Optional filters")
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
        hide_botted = st.checkbox(
            "Hide bot-supplied items", value=False,
            help="Free-to-play, buy limit over 10,000, under 100 gp. They rank "
                 "well and clear fast; the supply curve is a script that "
                 "answers a price rise by producing more.")
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
        capital=capital, account=account, trade_mode=mode,
        overnight_hours=overnight_hours,
        nature_rune_cost=nature_cost,
        max_quote_age=max_age or None, min_thin_volume_1h=min_vol,
        min_roi=min_roi / 100, min_undercut_depth=min_depth,
        min_price=parse_price(min_price_raw) or 1,
        max_price=parse_price(max_price_raw),
        tax_free_only=tax_free, hide_botted=hide_botted), top_n


def ranked_table(rows, top_n, config):
    overnight = config.trade_mode is engine.TradeMode.OVERNIGHT
    time_heading = "Buy by return" if overnight else "Round trip"
    probability_heading = "P(full buy) %" if overnight else "P(full trip) %"
    df = pd.DataFrame([{
        "Item": r.name, "Buy": r.buy, "List at": r.sell_listed_at,
        "Qty": r.allocated_quantity or r.qty_per_window,
        "Expected profit": round(r.allocated_expected_gp if
                                  r.allocated_expected_gp is not None
                                  else r.expected_gp),
        "ROI %": r.roi * 100,
        time_heading: ("{:.0f}h away + {:.0f}h sell window".format(
            r.horizon_hours, r.liquidation_hours) if overnight else
            engine.format_duration(r.expected_total_seconds)),
        probability_heading: r.p_fill * 100,
        "Fill range": "{:,.0f}–{:,.0f}".format(r.fill_low_qty, r.fill_high_qty),
        "Model confidence": filters.confidence_label(r),
        "Decision value": round(r.ranking_value),
    } for r in rows[:top_n]])
    gp = st.column_config.NumberColumn(format="localized")
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Buy": gp, "Qty": gp, "Expected profit": gp, "Decision value": gp,
        "List at": st.column_config.NumberColumn(
            format="localized",
            help="Where to place the sell offer. The GE tax rounds down, so "
                 "every price inside a 50 gp band nets the seller the same — "
                 "the lowest one buys queue priority for free."),
        time_heading: st.column_config.TextColumn(
            help=("Buy offer rests while you are away; liquidation starts only "
                  "after you return." if overnight else
                  "Expected time for both sequential legs at the shown prices.")),
        probability_heading: st.column_config.NumberColumn(
            format="%.0f%%", help=("Chance the full buy order fills before return."
                                    if overnight else
                                    "Chance the full planned quantity clears on both legs.")),
        "ROI %": st.column_config.NumberColumn(format="%.1f%%"),
    })


def slot_plan(rows, config):
    planned = [row for row in rows[:config.slots]
               if (row.allocated_quantity or 0) > 0 and row.expected_gp > 0]
    st.subheader("Best GE setup right now")
    objective = ("expected GP per occupied slot-hour" if config.trade_mode is
                 engine.TradeMode.ACTIVE else
                 "risk-adjusted profit over {:.0f} unattended hours".format(
                     config.horizon_hours))
    st.caption("{} account · {} slots · ranked on {}.".format(
        "Members" if config.account is engine.AccountType.MEMBERS else "F2P",
        config.slots, objective))
    if not planned:
        st.info("No defensible positive-EV setup is available right now. Keep "
                "the slots open, loosen optional filters, switch strategy, or "
                "refresh when the market changes.")
        return
    for start in range(0, len(planned), 4):
        columns = st.columns(4)
        for offset, row in enumerate(planned[start:start + 4]):
            slot = start + offset + 1
            with columns[offset]:
                st.markdown("**SLOT {} · {}**".format(slot, row.name))
                st.code("BUY  {:,} × {:,}\nSELL {:,}\nBANK  {}".format(
                    row.buy, row.allocated_quantity, row.sell_listed_at,
                    engine.format_gp(row.allocated_capital or 0)))
                expected = (row.allocated_expected_gp if
                            row.allocated_expected_gp is not None else
                            row.expected_gp)
                if config.trade_mode is engine.TradeMode.OVERNIGHT:
                    timing = ("buy {:,.0f} expected ({:,.0f}–{:,.0f}) by return; "
                              "then {:.0f}h to sell"
                              .format(row.expected_buy_qty, row.fill_low_qty,
                                      row.fill_high_qty, row.liquidation_hours))
                    fill_label = "full buy"
                else:
                    timing = "{} ETA · {:,.0f}–{:,.0f} completed".format(
                        engine.format_duration(row.expected_total_seconds),
                        row.fill_low_qty, row.fill_high_qty)
                    fill_label = "full trip"
                st.caption("EV {:,.0f} gp · {} {:.0%} · {} · {} model confidence"
                           .format(expected, fill_label, row.p_fill, timing,
                                   filters.confidence_label(row)))
                if st.button("Inspect", key="slot-{}-{}".format(slot,
                                                                  row.item_id)):
                    st.session_state.selected_item_id = row.item_id
    unused = config.slots - len(planned)
    if unused:
        st.warning("{} slot{} better left open: the remaining candidates do "
                   "not have positive risk-adjusted EV or cannot buy one "
                   "executable unit.".format(unused, "" if unused == 1 else "s"))
    st.caption(("Horizon EV ranks expected post-return liquidation profit and "
                "inventory downside; no sell is assumed while you are offline. "
                if config.trade_mode is engine.TradeMode.OVERNIGHT else
                "EV/slot/h ranks expected completed profit divided by occupied "
                "slot time. ") +
               "Scores are shrunk toward the market average; confidence is "
               "model evidence, not an execution guarantee.")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def watchlist_views(_client_key: str):
    """A year of daily history for the watchlist, cached for six hours.

    The underlying client caches to disk as well, so this survives a restart.
    Returns plain dicts rather than dataclasses because Streamlit's cache
    pickles the result and the views hold nested frozen dataclasses.
    """
    client = wiki_client()
    items = client.mapping()
    quotes = client.latest()
    views, problems = {}, []
    for item_id in merch.WATCHLIST_IDS:
        item = items.get(item_id)
        if item is None:
            problems.append("{}: not in /mapping".format(item_id))
            continue
        quote = quotes.get(item_id)
        price = ((quote.high + quote.low) / 2
                 if quote is not None and quote.high and quote.low else None)
        try:
            points = client.timeseries(item_id, merch.TREND_TIMESTEP)
        except api.ApiError as exc:
            problems.append("{}: {}".format(item.name, exc))
            continue
        views[item_id] = merch.daily_view(points, price=price)
    views = merch.apply_market_context(views)

    rows = []
    for item_id, view in views.items():
        item = items[item_id]
        trend = view.trend
        rows.append({
            "Item": item.name,
            "Price": view.price,
            "Trend/yr %": trend.annualised_pct if trend else None,
            "R²": trend.r_squared if trend else None,
            "Noise %": trend.noise_probability * 100 if trend else None,
            "vs 14d %": view.depth * 100 if view.depth is not None else None,
            "Vol": view.volume_ratio,
            "Supply %": (view.volume_change_relative * 100
                         if view.volume_change_relative is not None else None),
            "Type": " ".join(merch.classify_item(
                item_id, view.price or 0, item.members, item.limit,
                trend=trend, crash=view.crash, supply=view.supply)) or "—",
            "Merch": round(merch.merch_score(
                trend, item.limit,
                merch.is_botted(view.price or 0, item.members, item.limit))),
            "Why it is on the list": merch.THESIS_BY_ID.get(item_id, ""),
        })
    drift = next((v.market_drift for v in views.values()
                  if v.market_drift is not None), None)
    return rows, problems, drift


def merch_table():
    rows, problems, drift = watchlist_views(merch.TREND_TIMESTEP)
    if not rows:
        st.info("No history available for the watchlist right now.")
        return
    df = pd.DataFrame(rows).sort_values("Merch", ascending=False)
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Price": st.column_config.NumberColumn(format="localized"),
        "Trend/yr %": st.column_config.NumberColumn(
            format="%+.0f%%", help="Compounded from a least-squares fit through "
            "a year of log prices."),
        "R²": st.column_config.NumberColumn(
            format="%.2f", help="How much of the price movement the trend line "
            "explains."),
        "Noise %": st.column_config.NumberColumn(
            format="%.0f%%", help="Share of items with NO trend at all that "
            "would look at least this trendy. Read this before the trend "
            "column."),
        "vs 14d %": st.column_config.NumberColumn(format="%+.0f%%"),
        "Vol": st.column_config.NumberColumn(
            format="%.1fx", help="Latest comparable day's volume against its "
            "normal recent level."),
        "Supply %": st.column_config.NumberColumn(
            format="%+.0f%%", help="Volume against six months ago, with the "
            "market-wide move divided out."),
        "Merch": st.column_config.NumberColumn(
            help="Annual rate discounted by how much of the movement the trend "
                 "explains. Zero unless the item is rising."),
    })
    st.caption(
        "Noise is the column to read first. A year of daily prices with no "
        "trend in it still wanders far enough to look like a 40%/yr riser, so "
        "a headline +50%/yr that four in ten trendless items would also show "
        "is not a finding — which is why several rows here say SIDEWAYS with a "
        "large-looking rate.")
    if drift is not None:
        st.caption(
            "Market-wide volume moved {:+.0%} over six months. Supply has that "
            "divided out, so it shows only what belongs to the item.".format(drift))
    for problem in problems:
        st.caption("No history for {}".format(problem))


def crash_table(rows):
    crashed = [(row, merch.crash_context(row)) for row in rows]
    crashed = [(row, ctx) for row, ctx in crashed
               if ctx.signal is not None and ctx.signal.score > 0]
    if not crashed:
        st.info("Nothing among the deep-checked candidates is standing far "
                "enough from its own median to call. That is the normal state "
                "of the market.")
        return
    crashed.sort(key=lambda pair: -pair[1].recovery)
    df = pd.DataFrame([{
        "Item": row.name, "Buy": row.buy,
        "vs 14d %": ctx.signal.depth * 100,
        "Vol": ctx.volume_ratio,
        "Fill %": (row.fill_share or 0) * 100,
        "Reverts": bool(row.mean_reverting),
        "Badge": merch.BADGE_LABELS[ctx.signal.kind],
        "Recovery": round(ctx.recovery),
    } for row, ctx in crashed])
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Buy": st.column_config.NumberColumn(format="localized"),
        "vs 14d %": st.column_config.NumberColumn(format="%+.0f%%"),
        "Vol": st.column_config.NumberColumn(format="%.1fx"),
        "Fill %": st.column_config.NumberColumn(format="%.0f%%"),
    })
    st.caption(
        "Recovery ranks depth by how much of it you can actually trade: a 70% "
        "collapse nobody deals in scores below a 25% dip on a liquid item that "
        "mean-reverts. This covers the candidates the flip ranking "
        "deep-checked, not every item in the game — scanning all of them would "
        "mean the per-item polling the wiki asks people not to do.")


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
    active = row.trade_mode is engine.TradeMode.ACTIVE
    if active:
        right.metric("Round trip",
                     engine.format_duration(row.expected_total_seconds),
                     delta="{:.0%} full quantity clears".format(row.p_fill),
                     delta_color="off",
                     help="Buy leg {}, sell leg {}; expected completed range "
                          "{:,.0f}–{:,.0f}.".format(
                              engine.format_duration(row.expected_buy_seconds),
                              engine.format_duration(row.expected_sell_seconds),
                              row.fill_low_qty, row.fill_high_qty))
    else:
        right.metric("Return workflow",
                     "{:.0f}h away + {:.0f}h sell".format(
                         row.horizon_hours, row.liquidation_hours),
                     delta="{:.0%} full buy by return".format(row.p_fill),
                     delta_color="off",
                     help="Expected bought {:,.0f} ({:,.0f}–{:,.0f}); expected "
                          "sold after return {:,.0f}.".format(
                              row.expected_buy_qty, row.fill_low_qty,
                              row.fill_high_qty, row.expected_sell_qty))
    far.metric("Expected / slot / hour" if active else
               "Expected after liquidation",
               "{:,} gp".format(round(row.gp_per_slot_hour if active else
                                      row.ranking_value)),
               delta="{:,} before shrinkage".format(round(
                   row.raw_gp_per_slot_hour if active else
                   row.raw_ranking_value)),
               delta_color="off",
               help="{:,} units, {:,} gp tied up.".format(
                   row.qty_per_window, row.capital_needed))

    if not active:
        st.warning("About {:.0%} of planned quantity may remain after the "
                   "post-return sell window; the model subtracts {:,.0f} gp "
                   "of stress downside from Overnight EV.".format(row.p_stranded,
                                           row.downside_risk_gp))

    if row.allocated_capital is not None:
        st.info("Executable portfolio allocation: commit {} gp ({} units) "
                "to this slot; buy limits, fillable quantity and whole-item "
                "rounding are already applied.".format(
                    engine.format_gp(row.allocated_capital),
                    row.allocated_quantity or 0), icon="💰")

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


@st.fragment(run_every="60s")
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

    def fetch_recent(item_id):
        try:
            return client.timeseries(item_id, engine.RECENT_EXECUTION_TIMESTEP)
        except api.ApiError:
            return None

    with st.spinner("Scoring every tradable item, then checking the shortlist "
                    "against 14-day and recent execution history…"):
        result = filters.rank_flips(
            items, quotes, activity_5m, activity_1h, config, now=time.time(),
            fetch_history=fetch_history, top_k=15, exempt=exempt,
            volume_lookup=volume_lookup(), fetch_recent=fetch_recent)

    st.title("🪙 Grand Exchange Flipper")
    st.caption("Live snapshot refreshed automatically every 60 seconds · {}"
               .format(time.strftime("%H:%M:%S")))
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
    exemption_age = exemptions.freshness_warning()
    if exemption_age:
        st.warning(exemption_age, icon="⚠️")
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

    flip_tab, merch_tab, crash_tab = st.tabs(
        ["🔄 Flip", "📈 Merch", "🔍 Crash"])

    with flip_tab:
        if not result.rows:
            st.info("No flips meet the current execution and display criteria. "
                    "Loosen optional filters, switch Active ↔ Overnight, or "
                    "refresh when the market changes.")
        else:
            slot_plan(result.rows, config)
            list_column, detail_column = st.columns([0.9, 1.35], gap="large")
            with list_column:
                st.subheader("Ranked opportunities")
                ranked_table(result.rows, top_n, config)
                selected_id = st.session_state.get(
                    "selected_item_id", result.rows[0].item_id)
                choices = result.rows[:top_n]
                index = next((i for i, candidate in enumerate(choices)
                              if candidate.item_id == selected_id), 0)
                row = st.selectbox(
                    "Inspect item", choices, index=index,
                    format_func=lambda candidate: "{} · EV {:,.0f} · fill {:.0%}"
                    .format(candidate.name, candidate.ranking_value,
                            candidate.p_fill))
                st.session_state.selected_item_id = row.item_id
            with detail_column:
                st.subheader("Selected item · chart and execution")
                detail_view(row)

    with merch_tab:
        st.caption("A year of daily prices per item, for positions held over "
                   "weeks. Different horizon from the flip ranking and a "
                   "different scale — the two numbers do not compare.")
        # Gated behind a click because it is the only view that fetches per
        # item: 21 requests the first time, then six hours of cache.
        if st.session_state.get("merch_loaded") or st.button(
                "Load a year of history for {} items".format(
                    len(merch.WATCHLIST_IDS))):
            st.session_state["merch_loaded"] = True
            with st.spinner("Fetching daily history…"):
                merch_table()

    with crash_tab:
        crash_table(result.rows)


main()
