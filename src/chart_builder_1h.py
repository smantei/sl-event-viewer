import pandas as pd
import plotly.graph_objects as go


def parse_ts(value: str):
    if value is None:
        return None
    return pd.to_datetime(value, utc=True, errors="coerce")


def _get_trade(event: dict):
    trade = (event.get("trade_signals") or [])
    return trade[0] if trade else None


def _add_vline_with_label(fig: go.Figure, x, label: str, dash: str = "dash"):
    """
    Draw a vertical line at x using a shape, and add a label using an annotation.
    Avoids Plotly Timestamp averaging issues.
    """
    if x is None:
        return

    fig.add_shape(
        type="line",
        x0=x,
        x1=x,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line=dict(width=1, dash=dash),
        layer="above",
    )

    if label:
        fig.add_annotation(
            x=x,
            y=1.02,
            xref="x",
            yref="paper",
            text=label,
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
        )


def build_chart_1h(df_1h: pd.DataFrame, event: dict) -> go.Figure:
    if df_1h is None or df_1h.empty:
        fig = go.Figure()
        fig.update_layout(title="1h – no OHLC data", height=450)
        return fig

    sig = _get_trade(event)
    if not sig:
        fig = go.Figure()
        fig.update_layout(title="1h – no trade_signals in event", height=450)
        return fig

    entry_ts = parse_ts(sig.get("entry_ts"))
    exit_ts = parse_ts(sig.get("exit_ts"))
    entry_price = sig.get("entry_price")
    exit_price = sig.get("exit_price")
    sig_name = sig.get("signal")
    exit_sig = sig.get("exit_signal")

    hourly = event.get("hourly_fvg") or {}
    h_start = parse_ts(hourly.get("start_time"))

    df_1h = df_1h.copy()
    df_1h["ts_event"] = pd.to_datetime(df_1h["ts_event"], utc=True, errors="coerce")
    df_full = df_1h.dropna(subset=["ts_event"]).sort_values("ts_event")

    if df_full.empty:
        fig = go.Figure()
        fig.update_layout(title="1h – no valid ts_event in OHLC data", height=450)
        return fig

    data_min = df_full["ts_event"].min()
    data_max = df_full["ts_event"].max()

    # -------------------------------
    # Window (but don't let it hide entry/exit)
    # -------------------------------
    start_ts = h_start if h_start is not None else data_min
    start_ts = max(start_ts, data_min)

    if exit_ts is not None:
        end_ts = exit_ts + pd.Timedelta(hours=2)
    elif entry_ts is not None:
        end_ts = entry_ts + pd.Timedelta(hours=6)
    else:
        end_ts = data_max

    # IMPORTANT: don't clamp end_ts to data_max here, or you can hide exit lines.
    # We'll clamp the *data slice* but keep the axis range later.

    df = df_full[(df_full["ts_event"] >= start_ts) & (df_full["ts_event"] <= min(end_ts, data_max))].copy()
    if df.empty:
        df = df_full.copy()

    fig = go.Figure()
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

    # ===============================
    # HTF FVG band (grey)
    # ===============================
    lo, hi = hourly.get("begin_bound"), hourly.get("end_bound")
    if lo is not None and hi is not None and not df.empty:
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

    # Entry line + marker
    if entry_ts is not None:
        _add_vline_with_label(fig, entry_ts, sig_name or "entry", dash="dash")
    if entry_ts is not None and entry_price is not None:
        fig.add_trace(
            go.Scatter(
                x=[entry_ts],
                y=[entry_price],
                mode="markers",
                marker=dict(size=11, symbol="triangle-up"),
                name="Entry",
            )
        )

    # Exit line + marker
    if exit_ts is not None:
        _add_vline_with_label(fig, exit_ts, exit_sig or "exit", dash="dot")
    if exit_ts is not None and exit_price is not None:
        fig.add_trace(
            go.Scatter(
                x=[exit_ts],
                y=[exit_price],
                mode="markers",
                marker=dict(size=11, symbol="triangle-down"),
                name="Exit",
            )
        )

    # -------------------------------
    # ✅ Axis range must include entry/exit even if OHLC doesn't
    # -------------------------------
    x_candidates = [df["ts_event"].min(), df["ts_event"].max()]
    if entry_ts is not None:
        x_candidates.append(entry_ts)
    if exit_ts is not None:
        x_candidates.append(exit_ts)

    x_min = min(x_candidates)
    x_max = max(x_candidates)

    # small padding so labels aren't glued to edges
    pad = pd.Timedelta(minutes=30)
    fig.update_xaxes(range=[x_min - pad, x_max + pad])

    fig.update_layout(
        title=f"Event {event.get('event_id', '')} – 1h Chart",
        xaxis_title="UTC Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        height=450,
    )
    fig.update_yaxes(tickformat=",.0f", showexponent="none")

    return fig
