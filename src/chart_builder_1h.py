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
    This avoids Plotly's add_vline(annotation=...) Timestamp averaging issue.
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
    df_1h["ts_event"] = pd.to_datetime(df_1h["ts_event"], utc=True)
    df_full = df_1h.sort_values("ts_event")

    data_min = df_full["ts_event"].min()
    data_max = df_full["ts_event"].max()

    # Window: from hourly start_time (or data_min) to after exit (or some context after entry)
    start_ts = h_start if h_start is not None else data_min
    start_ts = max(start_ts, data_min)

    if exit_ts is not None:
        end_ts = min(exit_ts + pd.Timedelta(hours=2), data_max)
    else:
        if entry_ts is not None:
            end_ts = min(entry_ts + pd.Timedelta(hours=6), data_max)
        else:
            end_ts = data_max

    df = df_full[(df_full["ts_event"] >= start_ts) & (df_full["ts_event"] <= end_ts)].copy()
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
    fig.update_xaxes(range=[df["ts_event"].min(), df["ts_event"].max()])

    # Entry line + marker
    if entry_ts is not None:
        _add_vline_with_label(fig, entry_ts, sig_name or "entry", dash="dash")
    if entry_ts is not None and entry_price is not None:
        fig.add_trace(
            go.Scatter(
                x=[entry_ts],
                y=[entry_price],
                mode="markers+text",
                text=[sig_name or ""],
                textposition="top center",
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
                mode="markers+text",
                text=[exit_sig or ""],
                textposition="bottom center",
                marker=dict(size=11, symbol="triangle-down"),
                name="Exit",
            )
        )

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
