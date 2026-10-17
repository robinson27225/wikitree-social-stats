"""WikiTree Social Stats dashboard.   Run:  streamlit run app.py"""
from __future__ import annotations

import calendar
import math
import sqlite3
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from wtstats import __version__, config, quality
from wtstats.series import daily_series, yoy_table, ytd_vs_prior

INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#6f6e69"
GRID = "#e8e7e3"
SURFACE = "#fcfcfb"
BLUE = config.COLORS["facebook"]

st.set_page_config(page_title="WikiTree Social Stats", page_icon=str(config.LOGO) if config.LOGO.exists() else "📊", layout="wide")
if config.LOGO.exists():
    st.logo(str(config.LOGO), size="large")
st.markdown(
    """<style>
    .block-container {padding-top: 2rem; max-width: 1280px;}
    [data-testid="stMetricValue"] {font-size: 1.6rem;}
    </style>""",
    unsafe_allow_html=True,
)


# --- data access ------------------------------------------------------------

def _db_version() -> float:
    return config.DB_PATH.stat().st_mtime if config.DB_PATH.exists() else 0.0


def _query(sql: str, params=()) -> pd.DataFrame:
    conn = sqlite3.connect(config.DB_PATH)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


@st.cache_data
def load_daily(version: float) -> pd.DataFrame:
    """Account-level numbers, minus values flagged as bad."""
    df = _query(
        """SELECT d.platform, d.granularity, d.period_start, d.metric, d.value
           FROM daily_metrics d
           LEFT JOIN data_flags f ON f.scope = 'daily' AND f.platform = d.platform
                AND f.period_start = d.period_start AND f.metric = d.metric
           WHERE f.metric IS NULL"""
    )
    df["period_start"] = pd.to_datetime(df["period_start"])
    return df


@st.cache_data
def load_posts(version: float) -> pd.DataFrame:
    df = _query("SELECT platform, channel, date, metric, value FROM post_day_metrics")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    wide = df.pivot_table(index=["platform", "date"], columns="metric", values="value", aggfunc="sum").reset_index()
    return wide


@st.cache_data
def load_youtube(version: float) -> pd.DataFrame:
    """One row per video, period and metric."""
    df = _query(
        """SELECT s.video_id, v.title, v.published_date, v.series, s.period_start, s.period_end, s.metric, s.value
           FROM youtube_stats s JOIN youtube_videos v USING (video_id)"""
    )
    df["published_date"] = pd.to_datetime(df["published_date"])
    return df


# --- series building --------------------------------------------------------

def family_series(daily: pd.DataFrame, family: str, rollup: str) -> pd.DataFrame:
    """Rows of (platform, bucket, value) for one metric family, rolled up to Day / Week / Month."""
    _, comps, _ = config.FAMILIES[family]
    out = []
    for platform, metrics in comps.items():
        d = daily_series(daily, platform, metrics)
        if rollup == "Day":
            s = d
        elif rollup == "Week":
            s = d.groupby(d.index.to_period("W-SUN").start_time).sum()
        else:
            s = d.groupby(d.index.to_period("M").start_time).sum()
            names = [n for m in metrics for n in m.split("|")]
            sub = daily[(daily.platform == platform) & (daily.metric.isin(names))]
            m = sub[sub.granularity == "month"].groupby("period_start")["value"].sum()
            s = pd.concat([s, m[~m.index.isin(s.index)]]).sort_index()  # monthly history fills months with no daily data
        if not s.empty:
            out.append(pd.DataFrame({"platform": platform, "bucket": s.index, "value": s.values}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["platform", "bucket", "value"])


def metric_series(daily: pd.DataFrame, platform: str, metric: str, rollup: str) -> pd.Series:
    sub = daily[(daily.platform == platform) & (daily.metric == metric) & (daily.granularity == "day")]
    d = sub.set_index("period_start")["value"].sort_index()
    how = "last" if metric in config.NON_ADDITIVE_METRICS else "sum"   # a running total is not summed
    if rollup == "Week":
        d = d.groupby(d.index.to_period("W-SUN").start_time).agg(how)
    elif rollup == "Month":
        d = d.groupby(d.index.to_period("M").start_time).agg(how)
    return d


# --- charts -----------------------------------------------------------------

def multiples(panels: list[dict], ncols: int = 2, panel_height: int = 230) -> go.Figure:
    """Small multiples: one panel per series, each on its own y axis."""
    n = len(panels)
    nrows = math.ceil(n / ncols)
    fig = make_subplots(
        rows=nrows, cols=ncols, subplot_titles=[p["title"] for p in panels],
        vertical_spacing=0.34 / nrows if nrows > 1 else 0.1, horizontal_spacing=0.07,
    )
    fig.update_annotations(font=dict(size=13, color=INK))  # the panel titles; set before any other annotation is added
    for i, p in enumerate(panels):
        r, c = divmod(i, ncols)
        x, y = p["x"], p["y"]
        few = len(x) <= 24
        if p.get("avg") is not None:
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=p["color"], width=1),
                                     opacity=0.35, name=p["title"], showlegend=False,
                                     hovertemplate="%{x|%b %d, %Y}<br>%{y:,.0f} (day)<extra></extra>"), row=r + 1, col=c + 1)
            fig.add_trace(go.Scatter(x=x, y=p["avg"], mode="lines", line=dict(color=p["color"], width=2.5),
                                     name=p["title"], showlegend=False,
                                     hovertemplate="%{x|%b %d, %Y}<br>%{y:,.0f} (7-day average)<extra></extra>"), row=r + 1, col=c + 1)
        else:
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers" if few else "lines",
                                     line=dict(color=p["color"], width=2), marker=dict(size=8, line=dict(color=SURFACE, width=2)),
                                     name=p["title"], showlegend=False,
                                     hovertemplate="%{x|%b %d, %Y}<br>%{y:,.0f}<extra></extra>"), row=r + 1, col=c + 1)
        lo = min(0, float(pd.Series(y).min())) if len(y) else 0
        fig.update_yaxes(rangemode="tozero" if lo == 0 else "normal", row=r + 1, col=c + 1)
        axis = i + 1 if i else ""  # the i-th panel's axes are x/y, x2/y2, ...
        for when, note in p.get("breaks", []):  # a dotted line where the measure changes
            if len(x) and pd.Timestamp(x.min()) < pd.Timestamp(when) <= pd.Timestamp(x.max()):
                fig.add_shape(type="line", x0=when, x1=when, y0=0, y1=1, xref=f"x{axis}", yref=f"y{axis} domain",
                              line=dict(color=INK_3, width=1.5, dash="dot"))
                fig.add_annotation(x=when, y=1, xref=f"x{axis}", yref=f"y{axis} domain", text=note, showarrow=False,
                                   xanchor="left", yanchor="top", xshift=4, font=dict(size=11, color=INK_2))
    fig.update_layout(
        height=max(panel_height * nrows, 260), margin=dict(l=8, r=8, t=36, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
        hoverlabel=dict(bgcolor=SURFACE, font=dict(color=INK, size=12), bordercolor=GRID),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=INK_3))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=INK_3), separatethousands=True)
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


def smooth7(s: pd.Series) -> pd.Series:
    full = s.asfreq("D")
    return full.rolling(7, min_periods=4).mean().reindex(s.index)


def pct_change(cur: float, prev: float):
    return None if not prev else f"{(cur - prev) / prev:+.0%}"


# Sequential blue, oldest year lightest to newest darkest (steps 250-700 of the palette's blue ramp).
YEAR_RAMP = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


def year_colors(years: list[int]) -> dict[int, str]:
    """One colour per year, the same in every panel; the latest year is the darkest."""
    if len(years) == 1:
        return {years[0]: YEAR_RAMP[-3]}
    return {y: YEAR_RAMP[round(i * (len(YEAR_RAMP) - 1) / (len(years) - 1))] for i, y in enumerate(years)}


def position_label(pos: int, roll: str) -> str:
    return calendar.month_abbr[int(pos)] if roll == "Month" else f"Week {int(pos)}"


def yoy_figure(panels: list[tuple[str, pd.DataFrame]], roll: str = "Month", ncols: int = 2, panel_height: int = 250) -> go.Figure:
    """Year over year: one panel per series, one line per year laid over Jan-Dec. Each panel has its own scale."""
    years = sorted({int(y) for _, t in panels for y in t.columns})
    colors = year_colors(years)
    nrows = math.ceil(len(panels) / ncols)
    fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=[t for t, _ in panels],
                        vertical_spacing=0.3 / nrows if nrows > 1 else 0.1, horizontal_spacing=0.07)
    fig.update_annotations(font=dict(size=13, color=INK))
    seen: set[int] = set()
    for y in years:  # oldest first, so the legend reads in year order
        for i, (_, table) in enumerate(panels):
            if y not in table.columns:
                continue
            col = table[y].dropna()
            if col.empty:
                continue
            r, c = divmod(i, ncols)
            x = [pd.Timestamp(2001, int(p), 1) if roll == "Month" else pd.Timestamp(2001, 1, 1) + pd.Timedelta(days=7 * (int(p) - 1))
                 for p in col.index]
            latest = y == years[-1]
            fig.add_trace(go.Scatter(
                x=x, y=col.values, name=str(y), legendgroup=str(y), showlegend=y not in seen,
                mode="lines+markers" if latest and roll == "Month" else "lines",
                line=dict(color=colors[y], width=3 if latest else 1.75), marker=dict(size=8, line=dict(color=SURFACE, width=2)),
                hovertemplate="%{y:,.0f}<extra>" + str(y) + "</extra>"), row=r + 1, col=c + 1)
            seen.add(y)
    fig.update_layout(
        height=max(panel_height * nrows, 300) + 30, margin=dict(l=8, r=8, t=84, b=8), hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
        legend=dict(orientation="h", yref="container", y=1, yanchor="top", x=0, font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor=SURFACE, font=dict(color=INK, size=12), bordercolor=GRID))
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=INK_3), tickformat="%b")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, rangemode="tozero", tickfont=dict(color=INK_3), separatethousands=True)
    return fig


def yoy_tables_view(panels: list[tuple[str, pd.DataFrame]], roll: str) -> pd.DataFrame:
    """All panels' year-over-year tables in one frame (rows: series and month or week; columns: years)."""
    out = pd.concat({t: tb.rename(index=lambda p: position_label(p, roll)) for t, tb in panels}, names=["", ""])
    out.columns = [str(int(c)) for c in out.columns]
    return out


# --- app --------------------------------------------------------------------

if not config.DB_PATH.exists():
    st.title("WikiTree Social Stats")
    st.info("No data yet. Load your exports with:\n\n`python -m wtstats import path/to/file.csv ...`")
    st.stop()

ver = _db_version()
daily, posts, yt = load_daily(ver), load_posts(ver), load_youtube(ver)
day_rows = daily[daily.granularity == "day"]

head_logo, head_title = st.columns([1, 14], vertical_alignment="center")
if config.LOGO.exists():
    head_logo.image(str(config.LOGO), width=64)
head_title.title("WikiTree Social Stats")

with st.sidebar:
    st.header("View")
    lo, hi = day_rows.period_start.min().date(), day_rows.period_start.max().date()
    lasts = sorted(day_rows.groupby("platform")["period_start"].max())
    end_default = lasts[len(lasts) // 2].date()  # most channels' last day, not the one channel that runs a little longer
    start_default = max(lo, end_default - timedelta(days=89))
    rng = st.date_input("Date range", (start_default, end_default), min_value=lo, max_value=hi,
                        help="Applies to the account-level charts. Data runs to " + hi.strftime("%b %d, %Y") + ".")
    rollup = st.radio("Roll up by", ["Day", "Week", "Month"], horizontal=True, index=0)
    st.caption("Weeks start on Monday. The first and last bucket of a range can be partial.")
    st.divider()
    st.link_button("Social scheduler \u2197", config.SCHEDULER_URL, help="Opens the WikiTree social scheduler in a new tab.")
    st.caption(f"Dates are as exported. Scheduler dates are the published date in {config.TIMEZONE.split('/')[1].replace('_', ' ')} time.")
    st.caption(f"Version {__version__} \u00b7 data through {end_default:%b %d, %Y}")

if isinstance(rng, tuple) and len(rng) == 2:
    d0, d1 = pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
else:
    d0, d1 = pd.Timestamp(start_default), pd.Timestamp(end_default)

tab_over, tab_chan, tab_posts, tab_yt, tab_data = st.tabs(["Overview", "Channels", "Posts", "YouTube", "Data & quality"])

# ---- Overview --------------------------------------------------------------
with tab_over:
    c_a, c_b = st.columns([3, 2])
    fam_key = c_a.selectbox("Measure", list(config.FAMILIES), format_func=lambda k: config.FAMILIES[k][0])
    view = c_b.radio("View", ["Over time", "Year over year"], horizontal=True, key="view_over")
    label, comps, caveat = config.FAMILIES[fam_key]
    if view == "Year over year":
        roll = "Week" if rollup == "Week" else "Month"
        series = {pl: daily_series(daily, pl, comps[pl]) for pl in comps}
        series = {pl: sr for pl, sr in series.items() if not sr.empty}
        st.caption(f"Every year with data, one line per year, whole {roll.lower()}s only. The date range does not apply here. " + caveat)
        cols = st.columns(len(series))
        for col, (pl, sr) in zip(cols, series.items()):
            r = ytd_vs_prior(sr)
            col.metric(f"{config.LABELS[pl]} {r['year']} to {r['last']:%b %d}", f"{r['cur']:,.0f}",
                       pct_change(r["cur"], r["prev"]) if r["prev"] else None,
                       help="Compared with the same dates a year earlier." if r["prev"] else "No data back to the start of last year.")
        panels = [(config.LABELS[pl], yoy_table(sr, roll)) for pl, sr in series.items()]
        panels = [(t, tb) for t, tb in panels if not tb.empty]
        if panels:
            st.subheader(f"{label}, year over year")
            st.caption("One line per year; the latest year is the darkest. Each panel has its own scale.")
            for (fam, pl), breaks in config.CHART_BREAKS.items():
                if fam == fam_key and pl in series:
                    for when, note in breaks:
                        st.caption(f"{config.LABELS[pl]}: {note} from {pd.Timestamp(when):%b %d, %Y}. Years either side are not like for like.")
            show(yoy_figure(panels, roll))
            with st.expander("Table view"):
                st.dataframe(yoy_tables_view(panels, roll).style.format("{:,.0f}", na_rep="–"), width="stretch")
        else:
            st.warning("Not enough complete months of data for a year-over-year view.")
    else:
        span = (d1 - d0).days + 1
        prev0, prev1 = d0 - timedelta(days=span), d0 - timedelta(days=1)
        daily_fam = family_series(daily, fam_key, "Day")
        has_prev = prev1.date() >= lo  # is there any data before the selected range?
        st.caption(f"{d0:%b %d} – {d1:%b %d, %Y} ({span} days)"
                   + (f" compared with the {span} days before it. " if has_prev else "; no earlier data to compare with. ") + caveat)

        cols = st.columns(len(comps))
        for col, platform in zip(cols, comps):
            s = daily_fam[daily_fam.platform == platform].set_index("bucket")["value"]
            cur = s[(s.index >= d0) & (s.index <= d1)].sum()
            prev = s[(s.index >= prev0) & (s.index <= prev1)].sum()
            col.metric(config.LABELS[platform], f"{cur:,.0f}", pct_change(cur, prev) if prev else None)

        fam = family_series(daily, fam_key, rollup)
        fam = fam[(fam.bucket >= d0) & (fam.bucket <= d1)]
        panels = []
        for platform in comps:
            g = fam[fam.platform == platform].sort_values("bucket")
            if g.empty:
                continue
            s = g.set_index("bucket")["value"]
            panels.append(dict(title=config.LABELS[platform], color=config.COLORS[platform], x=g.bucket, y=g.value,
                               avg=smooth7(s).values if rollup == "Day" else None,
                               breaks=config.CHART_BREAKS.get((fam_key, platform), [])))
        if panels:
            st.subheader(f"{label}, by {rollup.lower()}")
            if rollup == "Day":
                st.caption("Thin line: each day. Bold line: 7-day average. Each panel has its own scale.")
            else:
                st.caption("Each panel has its own scale.")
            show(multiples(panels))
            with st.expander("Table view"):
                st.dataframe(fam.pivot(index="bucket", columns="platform", values="value").rename(columns=config.LABELS),
                             width="stretch")
        else:
            st.warning("No data in this date range.")

# ---- Channels --------------------------------------------------------------
with tab_chan:
    platform = st.selectbox("Channel", [p for p in config.PLATFORMS if p in set(day_rows.platform)],
                            format_func=lambda p: config.LABELS[p])
    avail = sorted(day_rows[day_rows.platform == platform].metric.unique())
    default = [m for m in avail if m in {"views", "video_views", "impressions", "interactions", "reach", "viewers",
                                         "total_viewers", "followers_change", "new_followers", "new_likes"}][:4]
    chosen = st.multiselect("Metrics", avail, default=default or avail[:4], format_func=lambda m: m.replace("_", " ").capitalize())
    view_c = st.radio("View", ["Over time", "Year over year"], horizontal=True, key="view_chan")
    if view_c == "Year over year":
        roll = "Week" if rollup == "Week" else "Month"
        skipped = [m for m in chosen if m in config.NON_ADDITIVE_METRICS]
        panels = [(m.replace("_", " ").capitalize(), yoy_table(daily_series(daily, platform, [m]), roll))
                  for m in chosen if m not in config.NON_ADDITIVE_METRICS]
        panels = [(t, tb) for t, tb in panels if not tb.empty]
        st.caption(f"Every year with data, one line per year (latest darkest), whole {roll.lower()}s only. The date range does not apply here."
                   + (" Running totals are left out." if skipped else ""))
        if panels:
            show(yoy_figure(panels, roll))
            with st.expander("Table view"):
                st.dataframe(yoy_tables_view(panels, roll).style.format("{:,.0f}", na_rep="–"), width="stretch")
        else:
            st.warning("Not enough complete months of data for a year-over-year view of these metrics.")
    else:
        show_posts = False
        if not posts.empty and platform in set(posts.platform):
            show_posts = st.checkbox("Mark days a post was published", value=True,
                                     help="Shows the days the scheduler published to this channel (data currently covers only the months you have exported).")
        panels, tables = [], {}
        for m in chosen:
            s = metric_series(daily, platform, m, rollup)
            s = s[(s.index >= d0) & (s.index <= d1)]
            if s.empty:
                continue
            panels.append(dict(title=m.replace("_", " ").capitalize(), color=config.COLORS[platform], x=s.index, y=s.values,
                               avg=smooth7(s).values if rollup == "Day" else None))
            tables[m] = s
        if panels:
            fig = multiples(panels)
            if show_posts and rollup == "Day":
                pdays = posts[(posts.platform == platform) & (posts.date >= d0) & (posts.date <= d1)]
                if not pdays.empty:
                    for i, p in enumerate(panels):
                        r, c = divmod(i, 2)
                        pts =pd.Series(p["y"], index=pd.to_datetime(p["x"])).reindex(pdays.date).dropna()
                        posts_n = pdays.set_index("date")["posts"].reindex(pts.index)
                        fig.add_trace(go.Scatter(
                            x=pts.index, y=pts.values, mode="markers", name="Post published", showlegend=False,
                            marker=dict(size=8, color=SURFACE, line=dict(color=INK, width=2)), customdata=posts_n.values,
                            hovertemplate="%{x|%b %d, %Y}<br>%{y:,.0f}<br>%{customdata:.0f} post(s) published<extra></extra>"),
                            row=r + 1, col=c + 1)
                    st.caption("○ = a day the scheduler published a post to this channel.")
            show(fig)
            with st.expander("Table view"):
                st.dataframe(pd.DataFrame(tables).rename(columns=lambda m: m.replace("_", " ").capitalize()), width="stretch")
        else:
            st.warning("Nothing to show for this selection and range.")

# ---- Posts (scheduler) ------------------------------------------------------
with tab_posts:
    if posts.empty:
        st.info(f"No scheduler exports loaded yet. They come from the [social scheduler]({config.SCHEDULER_URL}).")
    else:
        st.markdown(
            f"Totals for the posts the [social scheduler]({config.SCHEDULER_URL}) published each day, as of the export. These are **not** the same "
            "measure as the account-level charts (they follow the posts, not the calendar day), so they are kept separate. "
            "This tab shows everything loaded; the sidebar date range does not apply here."
        )
        pmin, pmax = posts.date.min().date(), posts.date.max().date()
        c1, c2, c3 = st.columns([2, 2, 3])
        measure = c1.selectbox("Measure", [m for m in ["views", "reach", "viewers", "engagements", "interactions", "likes",
                                                       "comments", "shares", "saves", "link_clicks", "visits", "follows"]
                                           if m in posts.columns], format_func=lambda m: m.replace("_", " ").capitalize())
        per_post = c2.radio("Count", ["Per post", "Total per day"], horizontal=True)
        have = [p for p in config.PLATFORMS if p in set(posts.platform) and posts.loc[posts.platform == p, measure].notna().any()]
        chosen_p = c3.multiselect("Channels", have, default=have, format_func=lambda p: config.LABELS[p])
        pr = posts[(posts.platform.isin(chosen_p)) & posts[measure].notna()].copy()
        pr["v"] = pr[measure] / pr["posts"] if per_post == "Per post" else pr[measure]
        if pr.empty:
            st.warning("Pick at least one channel with this measure.")
        else:
            st.caption(f"Published {pmin:%b %d} – {pmax:%b %d, %Y}. Days with no post have no point (they are not zeros).")
            fig = go.Figure()
            for p in chosen_p:
                g = pr[pr.platform == p].sort_values("date")
                if g.empty:
                    continue
                fig.add_trace(go.Scatter(x=g.date, y=g.v, name=config.LABELS[p], mode="lines+markers",
                                         line=dict(color=config.COLORS[p], width=2),
                                         marker=dict(size=8, color=config.COLORS[p], line=dict(color=SURFACE, width=2)),
                                         hovertemplate="%{x|%b %d}<br>%{y:,.0f}<extra>" + config.LABELS[p] + "</extra>"))
                last = g.iloc[-1]
                fig.add_annotation(x=last.date, y=last.v, text=config.LABELS[p], showarrow=False, xanchor="left", xshift=8,
                                   font=dict(color=INK_2, size=12))
            fig.update_layout(
                height=380, margin=dict(l=8, r=90, t=10, b=8), hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
                legend=dict(orientation="h", y=1.08, x=0, font=dict(color=INK_2)),
                hoverlabel=dict(bgcolor=SURFACE, font=dict(color=INK, size=12), bordercolor=GRID),
                yaxis=dict(gridcolor=GRID, zeroline=False, rangemode="tozero", tickfont=dict(color=INK_3), separatethousands=True),
                xaxis=dict(showgrid=False, linecolor=GRID, tickfont=dict(color=INK_3)),
            )
            show(fig)

        st.subheader("By channel")
        agg = posts[posts.platform.isin(chosen_p)].groupby("platform").agg(
            days=("date", "nunique"), posts=("posts", "sum"),
            views=("views", "sum"), reach=("reach", "sum"), engagements=("engagements", "sum"),
            link_clicks=("link_clicks", "sum"), follows=("follows", "sum"),
        )
        agg["views / post"] = agg["views"].where(agg["views"] > 0) / agg["posts"]
        agg["engagements / post"] = agg["engagements"] / agg["posts"]
        agg["engagements per 1,000 views"] = agg["engagements"] / agg["views"].where(agg["views"] > 0) * 1000
        agg = agg.drop(columns=["reach", "link_clicks", "follows"]).rename(index=config.LABELS)
        agg.index.name = "Channel"
        st.dataframe(agg.style.format({c: "{:,.0f}" for c in agg.columns}, na_rep="–"), width="stretch")
        st.caption("– means the channel does not report that measure (Bluesky and Mastodon give no view counts).")

# ---- YouTube ---------------------------------------------------------------
YT_NAMES = {
    "views": "Views", "watch_time_hours": "Watch time (hours)", "likes": "Likes", "shares": "Shares",
    "subscribers": "Subscribers gained", "thumbnail_impressions": "Thumbnail impressions",
    "chat_messages": "Live chat messages", "reactions": "Live reactions",
}


def span_label(start: pd.Timestamp, end: pd.Timestamp, is_month: bool) -> str:
    if is_month:
        return f"{start:%B %Y}"
    return f"{start:%b} {start.day} – {end:%b} {end.day}, {end.year}"


with tab_yt:
    if yt.empty:
        st.info("No YouTube export loaded yet.")
    else:
        spans = yt[["period_start", "period_end"]].drop_duplicates().copy()
        spans["start"], spans["end"] = pd.to_datetime(spans.period_start), pd.to_datetime(spans.period_end)
        spans["is_month"] = (spans.start.dt.day == 1) & (spans.end == spans.start + pd.offsets.MonthEnd(0))
        spans["label"] = [span_label(s, e, m) for s, e, m in zip(spans.start, spans.end, spans.is_month)]
        spans = spans.sort_values(["is_month", "end"], ascending=False)  # latest month first, then date ranges
        months = spans[spans.is_month].sort_values("end")

        c1, c2 = st.columns(2)
        label = c1.selectbox("Period", spans.label.tolist())
        sel = spans[spans.label == label].iloc[0]
        cur = yt[(yt.period_start == sel.period_start) & (yt.period_end == sel.period_end)]
        wide = cur.pivot(index="video_id", columns="metric", values="value").reset_index().merge(
            yt.drop_duplicates("video_id")[["video_id", "title", "published_date", "series"]], on="video_id")
        have = [m for m in YT_NAMES if m in wide.columns] + [m for m in wide.columns if m not in YT_NAMES and m not in
                                                              {"video_id", "title", "published_date", "series"}]
        name = lambda m: YT_NAMES.get(m, m.replace("_", " ").capitalize())
        metric = c2.selectbox("Measure", have, format_func=name)
        if sel.is_month:
            st.caption(f"{label}: activity during that month only. The export lists each video's top 500 by likes, so a video "
                       "that is missing from a month is not necessarily zero.")
        else:
            st.caption(f"{label}: totals over this whole range. These overlap the monthly figures, so do not add them together.")

        series = wide.groupby("series").agg(videos=("video_id", "count"), **{metric: (metric, "sum")}).dropna().sort_values(metric)
        fig = go.Figure(go.Bar(
            x=series[metric], y=series.index, orientation="h", marker=dict(color=BLUE, cornerradius=4),
            text=[f"{v:,.0f}" for v in series[metric]], textposition="outside", cliponaxis=False,
            textfont=dict(color=INK_2, size=12), customdata=series["videos"],
            hovertemplate="%{y}<br>%{x:,.0f} " + name(metric).lower() + " across %{customdata} videos<extra></extra>"))
        fig.update_layout(
            height=max(300, 34 * len(series) + 60), margin=dict(l=8, r=60, t=10, b=8), bargap=0.35,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
            xaxis=dict(gridcolor=GRID, zeroline=False, tickfont=dict(color=INK_3), separatethousands=True),
            yaxis=dict(tickfont=dict(color=INK)), hoverlabel=dict(bgcolor=SURFACE, font=dict(color=INK, size=12), bordercolor=GRID))
        st.subheader(f"{name(metric)} by series, {label}")
        show(fig)

        in_months = yt[yt.metric == metric].merge(months[["period_start", "period_end", "label"]], on=["period_start", "period_end"])
        order = months.label.tolist()
        if in_months.period_start.nunique() >= 2:
            when = pd.to_datetime(in_months.period_start)
            in_months = in_months.assign(year=when.dt.year, month_no=when.dt.month)
            grain = st.radio("Group the months by", ["Month", "Year", "Year over year"], horizontal=True, key="yt_group")
            st.subheader(f"{name(metric)}, {'month by month' if grain == 'Month' else 'by year' if grain == 'Year' else 'year over year'}")

            def bars(x, y, hover, height=300):
                fig = go.Figure(go.Bar(
                    x=x, y=y, marker=dict(color=BLUE, cornerradius=4), text=[f"{v:,.0f}" for v in y], textposition="outside",
                    cliponaxis=False, textfont=dict(color=INK_2, size=12), customdata=hover,
                    hovertemplate="%{x}<br>%{y:,.0f}<br>%{customdata}<extra></extra>"))
                fig.update_layout(
                    height=height, margin=dict(l=8, r=8, t=24, b=8), bargap=0.45,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
                    yaxis=dict(gridcolor=GRID, zeroline=False, rangemode="tozero", tickfont=dict(color=INK_3), separatethousands=True),
                    xaxis=dict(tickfont=dict(color=INK), type="category"),
                    hoverlabel=dict(bgcolor=SURFACE, font=dict(color=INK, size=12), bordercolor=GRID))
                return fig

            if grain == "Month":
                by_month = in_months.groupby("label")["value"].sum().reindex([m for m in order if m in set(in_months.label)])
                show(bars(by_month.index, by_month.values, [""] * len(by_month)))
                tbl = in_months.pivot_table(index="series", columns="label", values="value", aggfunc="sum")
                tbl = tbl[[m for m in order if m in tbl.columns]]
                table_title = "Series by month (table view)"
            elif grain == "Year":
                by_year = in_months.groupby("year").agg(value=("value", "sum"), months=("period_start", "nunique"))
                show(bars([str(y) for y in by_year.index], by_year["value"].values,
                          [f"{n} of 12 months loaded" if n < 12 else "all 12 months" for n in by_year["months"]]))
                tbl = in_months.pivot_table(index="series", columns="year", values="value", aggfunc="sum")
                tbl.columns = [str(c) for c in tbl.columns]
                table_title = "Series by year (table view)"
            else:
                by_pos = in_months.pivot_table(index="month_no", columns="year", values="value", aggfunc="sum")
                show(yoy_figure([(name(metric), by_pos)], "Month", ncols=1, panel_height=340))
                tbl = by_pos.rename(index=lambda p: position_label(p, "Month"))
                tbl.columns = [str(int(c)) for c in tbl.columns]
                table_title = "Month by year (table view)"
            with st.expander(table_title):
                st.dataframe(tbl.style.format("{:,.0f}", na_rep="–"), width="stretch")
            partial = in_months.groupby("year")["period_start"].nunique()
            st.caption("Each month counts the videos listed in that month's export (up to 500)."
                       + (" Years with fewer than 12 months loaded: " + ", ".join(f"{y} ({n})" for y, n in partial.items() if n < 12) + "."
                          if grain != "Month" and (partial < 12).any() else ""))

        st.subheader("Videos")
        f1, f2 = st.columns([2, 3])
        pick = f1.multiselect("Series", sorted(wide.series.unique()), default=[])
        q = f2.text_input("Title contains")
        v = wide[wide.series.isin(pick)] if pick else wide
        if q:
            v = v[v.title.str.contains(q, case=False, regex=False)]
        v = v.sort_values(metric, ascending=False).head(200)
        show_cols = ["title", "series", "published_date"] + have
        st.dataframe(
            v[show_cols].rename(columns={"title": "Title", "series": "Series", "published_date": "Published", **{m: name(m) for m in have}}),
            width="stretch", hide_index=True,
            column_config={"Published": st.column_config.DateColumn(format="MMM D, YYYY"),
                           **{name(m): st.column_config.NumberColumn(format="%.1f" if m == "watch_time_hours" else "localized")
                              for m in have}})
        if len(months) >= 2:
            with st.expander(f"{name(metric)} per video, month by month"):
                pm = in_months[in_months.video_id.isin(v.video_id)].pivot(index="video_id", columns="label", values="value")
                pm = pm[[m for m in order if m in pm.columns]].reset_index().merge(
                    v[["video_id", "title"]], on="video_id").drop(columns="video_id")
                st.dataframe(pm[["title"] + [c for c in pm.columns if c != "title"]].rename(columns={"title": "Title"}),
                             width="stretch", hide_index=True)

# ---- Data & quality --------------------------------------------------------
with tab_data:
    st.subheader("What is loaded")
    cov = _query(
        """SELECT platform AS Channel, 'Account, ' || granularity AS Source, MIN(period_start) AS First,
                  MAX(period_start) AS Last, COUNT(DISTINCT period_start) AS Periods, COUNT(DISTINCT metric) AS Metrics
           FROM daily_metrics GROUP BY platform, granularity
           UNION ALL
           SELECT platform, 'Scheduler posts', MIN(date), MAX(date), COUNT(DISTINCT date), COUNT(DISTINCT metric)
           FROM post_day_metrics GROUP BY platform
           UNION ALL
           SELECT 'youtube', 'Video stats ' || s.period_start || ' to ' || s.period_end, MIN(v.published_date), MAX(v.published_date),
                  COUNT(DISTINCT s.video_id), COUNT(DISTINCT s.metric)
           FROM youtube_stats s JOIN youtube_videos v USING (video_id) GROUP BY s.period_start, s.period_end
           ORDER BY 1, 2"""
    )
    cov["Channel"] = cov["Channel"].map(config.LABELS)
    st.dataframe(cov, width="stretch", hide_index=True)
    st.caption("For YouTube rows, First/Last are the oldest and newest publish dates among the listed videos, and Periods is the number of videos.")
    st.subheader("Imports")
    st.dataframe(_query("SELECT imported_at AS 'When', kind AS Kind, source_name AS File, rows_loaded AS Rows, notes AS Notes "
                        "FROM import_log ORDER BY id DESC"), width="stretch", hide_index=True)
    st.subheader("Values left out of the charts")
    fl = _query("SELECT platform AS Channel, metric AS Metric, MIN(period_start) AS First, MAX(period_start) AS Last, "
                "COUNT(*) AS Days, reason AS Why FROM data_flags GROUP BY platform, metric, reason ORDER BY platform, First")
    if fl.empty:
        st.write("None.")
    else:
        fl["Channel"] = fl["Channel"].map(config.LABELS)
        st.dataframe(fl, width="stretch", hide_index=True)
    st.subheader("Gaps in the data")
    gaps = quality.find_gaps(sqlite3.connect(config.DB_PATH))
    if gaps.empty:
        st.write("None.")
    else:
        gaps["platform"] = gaps["platform"].map(config.LABELS)
        st.dataframe(gaps.rename(columns={"platform": "Channel", "first_missing": "From", "last_missing": "To",
                                          "days": "Days", "metrics": "Metrics with no value"}),
                     width="stretch", hide_index=True)
        st.caption("A blank is not a zero. Weekly and monthly totals that include these days are understated.")
    st.subheader("Reading the numbers")
    st.markdown(
        "- **Empty rows are skipped.** The sheets are pre-filled with future dates; those aren't zeros.\n"
        "- **Instagram:** a blank *New Followers* is read as 0 (September writes explicit 0s where earlier months left blanks).\n"
        "- **TikTok:** *Followers* was a daily change through August and a running total from Sep 1. The total is stored "
        "separately and the daily change is derived from consecutive days.\n"
        "- **LinkedIn:** the engagement rate is not stored; it can be recomputed from the counts.\n"
        "- **Small negatives** (-1) in TikTok comments and LinkedIn comments or reposts are deletions in the export, and are kept. "
        "Follower changes can go negative too: they are net.\n"
        "- **Scheduler totals** follow each day's posts as of the export and keep growing afterwards, so they are only "
        "comparable with other scheduler rows.\n"
        "- **YouTube** is per video. Each file covers one period (a month, or a date range such as year to date) and lists at most "
        "the top 500 videos by likes. A month is that month's activity only; ranges overlap the months and are never added to them."
    )
