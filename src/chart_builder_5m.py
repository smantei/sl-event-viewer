import pandas as pd
import plotly.graph_objects as go


# -------------------------------------------------------
# Timestamp parsing
# -------------------------------------------------------
def parse_ts(value: str):
    """
    Safely parse a timestamp string (handles 'T' vs ' ').
    All returned as UTC-aware.
    """
    if value is None:
        return None
    return pd.to_datetime(value, utc=True, errors="coerce")


# -------------------------------------------------------
# Determine the visual time-window for the chart
# -------------------------------------------------------
def get_time_window(event: dict):
    """
    Decide what time range to show on the 5m chart.

    Uses:
      - hourly_fvg.pretouch_window_start / _end
      - hourly_fvg.posttouch_window_start / _end
      - hourly_fvg.start_time
      - fvg_5m.start_time / touch_ts / entry_ts
      - bos_5m.ts_event
      - trade_signals.entry_ts / exit_ts   (FIX)

    Final clamp to OHLC range is done later.
    """
    candidates_start = []
    candidates_end = []

    hourly = event.get("hourly_fvg") or {}

    # Hourly / window-based hints
    for key in ["pretouch_window_start", "posttouch_window_start"]:
        ts = parse_ts(hourly.get(key))
        if ts is not None:
            candidates_start.append(ts)

    for key in ["pretouch_window_end", "posttouch_window_end"]:
        ts = parse_ts(hourly.get(key))
        if ts is not None:
            candidates_end.append(ts)

    # Also consider the hourly start_time itself
    ts_hourly_start = parse_ts(hourly.get("start_time"))
    if ts_hourly_start is not None:
        candidates_start.append(ts_hourly_start)
        candidates_end.append(ts_hourly_start)

    # 5m FVGs
    for f in event.get("fvg_5m", []):
        for key in ["start_time", "touch_ts", "entry_ts"]:
            st = parse_ts(f.get(key))
            if st is not None:
                candidates_start.append(st)
                candidates_end.append(st)

    # BOS 5m
    for b in event.get("bos_5m", []):
        ts = parse_ts(b.get("ts_event"))
        if ts is not None:
            candidates_start.append(ts)
            candidates_end.append(ts)

    # ✅ FIX: trade signals (entry + exit) must influence the visual window
    for sig in event.get("trade_signals", []):
        et = parse_ts(sig.get("entry_ts"))
        xt = parse_ts(sig.get("exit_ts"))
        if et is not None:
            candidates_start.append(et)
            candidates_end.append(et)
        if xt is not None:
            candidates_start.append(xt)
            candidates_end.append(xt)

    if not candidates_start or not candidates_end:
        return None, None

    t_min = min(candidates_start)
    t_max = max(candidates_end)

    padding = pd.Timedelta(hours=1)
    return t_min - padding, t_max + padding


# -------------------------------------------------------
# MAIN CHART BUILDER
# -------------------------------------------------------
def build_chart(df_5m: pd.DataFrame, event: dict) -> go.Figure:
    """
    Build Plotly candlestick chart with event markers, using the new schema:

      - event["hourly_fvg"]
      - event["fvg_5m"]
      - event["bos_5m"]
      - event["trade_signals"]
      - event["ohlc_5m"]
      - event["summary"]["status"]
    """
    hourly = event.get("hourly_fvg") or {}
    fvg_5m = event.get("fvg_5m", [])
    bos_5m = event.get("bos_5m", [])
    trade_signals = event.get("trade_signals", [])

    # ---- Prepare df_5m ----
    if df_5m is None or df_5m.empty:
        fig = go.Figure()
        fig.update_layout(
            title=f"Event {event.get('event_id', '')} – no OHLC data",
            height=600,
        )
        return fig

    df_5m = df_5m.copy()
    df_5m["ts_event"] = pd.to_datetime(df_5m["ts_event"], utc=True)

    # Keep a full copy for index-based lookups
    df_full = df_5m.sort_values("ts_event")

    # ---- Determine visual window ----
    start_ts, end_ts = get_time_window(event)
    data_min, data_max = df_full["ts_event"].min(), df_full["ts_event"].max()

    if (
        start_ts is None
        or end_ts is None
        or end_ts < data_min
        or start_ts > data_max
    ):
        start_ts, end_ts = data_min, data_max

    # Force x-axis start to pretouch_window_start (clamped to data_min)
    pre_start = parse_ts(hourly.get("pretouch_window_start"))
    if pre_start is not None:
        start_ts = max(pre_start, data_min)

    # Clamp to available OHLC data
    start_ts = max(start_ts, data_min)
    end_ts = min(end_ts, data_max)

    df = df_full[
        (df_full["ts_event"] >= start_ts)
        & (df_full["ts_event"] <= end_ts)
    ].copy()

    if df.empty:
        df = df_full.copy()

    # ========================================================
    # Build the chart
    # ========================================================
    fig = go.Figure()

    # Candlesticks
    fig.add_trace(
        go.Candlestick(
            x=df["ts_event"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="",
        )
    )

    # Keep axis aligned to the sliced window (now includes exit_ts)
    fig.update_xaxes(range=[df["ts_event"].min(), df["ts_event"].max()])

    # ========================================================
    # HTF TOUCH MARKER (from hourly_fvg)
    # ========================================================
    touch_ts = parse_ts(hourly.get("touch_ts"))
    touch_price = hourly.get("touch_price")  # pure HTF touch price

    if touch_ts is not None and touch_price is not None:
        fig.add_vline(x=touch_ts, line=dict(width=1, dash="dash"))

        label = f"HTF touch @ {touch_price}"
        fig.add_trace(
            go.Scatter(
                x=[touch_ts],
                y=[touch_price],
                mode="markers+text",
                text=[label],
                textposition="top center",
                marker=dict(symbol="x", size=10),
                name="HTF touch",
            )
        )

    # ========================================================
    # BOS markers
    # ========================================================
    bos_x, bos_y, bos_lbl = [], [], []
    for b in bos_5m:
        ts = parse_ts(b.get("ts_event"))
        if ts is not None:
            bos_x.append(ts)
            bos_y.append(b.get("trigger_close"))
            bos_lbl.append(b.get("bos_direction"))

    if bos_x:
        fig.add_trace(
            go.Scatter(
                x=bos_x,
                y=bos_y,
                mode="markers+text",
                text=bos_lbl,
                textposition="top center",
                marker=dict(size=10, symbol="triangle-up"),
                name="BOS",
            )
        )

    # ========================================================
    # 5m FVG rectangles + markers (LTF)
    # ========================================================
    x1_rect = df["ts_event"].max()
    for f in fvg_5m:
        st = parse_ts(f.get("start_time"))
        lo, hi = f.get("begin_bound"), f.get("end_bound")

        if st is None or lo is None or hi is None:
            continue

        # FVG zone rect
        fig.add_shape(
            type="rect",
            x0=st,
            x1=x1_rect,
            y0=min(lo, hi),
            y1=max(lo, hi),
            fillcolor="rgba(173,216,230,0.22)",
            line=dict(width=0),
            layer="below",
        )

        # Label at FVG creation
        mid = (lo + hi) / 2.0
        fig.add_trace(
            go.Scatter(
                x=[st],
                y=[mid],
                mode="markers+text",
                text=[f"FVG{f['fvg_5m_id']}"],
                textposition="bottom center",
                marker=dict(size=8, symbol="square", color="blue"),
                name="FVG5m",
            )
        )

        # ---------------------------------------------
        # FIRST TOUCH (FT) + VALID CLOSE (VC) markers
        # ---------------------------------------------
        ft_ts = parse_ts(f.get("touch_ts"))
        vc_ts = parse_ts(f.get("entry_ts"))  # VC candle = entry candle

        def _candle_mid(ts_val):
            row = df_full[df_full["ts_event"] == ts_val]
            if row.empty:
                return None
            high = float(row.iloc[0]["high"])
            low = float(row.iloc[0]["low"])
            return (high + low) / 2.0

        if ft_ts is not None:
            y_ft = _candle_mid(ft_ts)
            if y_ft is not None:
                fig.add_trace(
                    go.Scatter(
                        x=[ft_ts],
                        y=[y_ft],
                        mode="markers+text",
                        text=[f"FT ({f.get('index_first_touch')})"],
                        textposition="bottom center",
                        marker=dict(size=10, symbol="diamond", color="#FFA500"),
                        name="First Touch",
                    )
                )

        if vc_ts is not None:
            y_vc = _candle_mid(vc_ts)
            if y_vc is not None:
                fig.add_trace(
                    go.Scatter(
                        x=[vc_ts],
                        y=[y_vc],
                        mode="markers+text",
                        text=[f"VC ({f.get('index_valid_close_after_touch')})"],
                        textposition="top center",
                        marker=dict(size=10, symbol="diamond-open", color="#008000"),
                        name="Valid Close",
                    )
                )

    # ========================================================
    # TRADE SIGNAL MARKERS (entry + exit)
    # ========================================================
    for sig in trade_signals:
        et = parse_ts(sig.get("entry_ts"))
        ep = sig.get("entry_price")
        sig_name = sig.get("signal")

        if et is not None and ep is not None:
            fig.add_vline(x=et, line=dict(width=1, dash="dash"))
            fig.add_trace(
                go.Scatter(
                    x=[et],
                    y=[ep],
                    mode="markers+text",
                    text=[sig_name or ""],
                    textposition="top center",
                    marker=dict(size=12, symbol="triangle-up", color="#FF00FF"),
                    name="Entry",
                )
            )

        xt = parse_ts(sig.get("exit_ts"))
        xp = sig.get("exit_price")
        exit_sig = sig.get("exit_signal")
        if xt is not None and xp is not None:
            fig.add_vline(x=xt, line=dict(width=1, dash="dot"))
            fig.add_trace(
                go.Scatter(
                    x=[xt],
                    y=[xp],
                    mode="markers+text",
                    text=[exit_sig or ""],
                    textposition="bottom center",
                    marker=dict(size=12, symbol="triangle-down", color="#FF0000"),
                    name="Exit",
                )
            )

    # ========================================================
    # HOURLY FVG band
    # ========================================================
    lo, hi = hourly.get("begin_bound"), hourly.get("end_bound")
    if lo is not None and hi is not None:
        fig.add_shape(
            type="rect",
            x0=df["ts_event"].min(),
            x1=df["ts_event"].max(),
            y0=min(lo, hi),
            y1=max(lo, hi),
            fillcolor="rgba(200,200,200,0.20)",
            line=dict(width=0),
            layer="below",
        )

    # ========================================================
    # Layout
    # ========================================================
    fig.update_layout(
        title=f"Event {event.get('event_id', '')} – 5m Chart",
        xaxis_title="UTC Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        height=900,
    )

    fig.update_yaxes(
        tickformat=",.0f",
        showexponent="none",
    )

    return fig
