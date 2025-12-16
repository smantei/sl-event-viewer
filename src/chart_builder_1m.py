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
    Avoids Plotly's add_vline(annotation=...) Timestamp averaging issue and avoids
    invalid Scatter props like xref/yref.
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


def build_chart_1m(df_1m: pd.DataFrame, event: dict) -> go.Figure:
    if df_1m is None or df_1m.empty:
        fig = go.Figure()
        fig.update_layout(title="1m – no OHLC data", height=450)
        return fig

    sig = _get_trade(event)
    if not sig:
        fig = go.Figure()
        fig.update_layout(title="1m – no trade_signals in event", height=450)
        return fig

    entry_ts = parse_ts(sig.get("entry_ts"))
    exit_ts = parse_ts(sig.get("exit_ts"))
    entry_price = sig.get("entry_price")
    stop_loss = sig.get("stop_loss")
    take_profit = sig.get("take_profit")
    exit_price = sig.get("exit_price")
    exit_sig = sig.get("exit_signal")
    sig_name = sig.get("signal")

    df_1m = df_1m.copy()
    df_1m["ts_event"] = pd.to_datetime(df_1m["ts_event"], utc=True)
    df_full = df_1m.sort_values("ts_event")

    # Window: entry -> exit, with padding
    data_min = df_full["ts_event"].min()
    data_max = df_full["ts_event"].max()

    if entry_ts is None:
        start_ts = data_min
    else:
        start_ts = max(entry_ts - pd.Timedelta(minutes=15), data_min)

    if exit_ts is None:
        if entry_ts is not None:
            end_ts = min(entry_ts + pd.Timedelta(hours=2), data_max)
        else:
            end_ts = data_max
    else:
        end_ts = min(exit_ts + pd.Timedelta(minutes=15), data_max)

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

    # Entry labeled vline + marker
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

    # Stop/TP horizontal lines
    if stop_loss is not None:
        fig.add_hline(y=stop_loss, line=dict(width=1, dash="dot"))
    if take_profit is not None:
        fig.add_hline(y=take_profit, line=dict(width=1, dash="dot"))

    # Exit labeled vline + marker
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
        title=f"Event {event.get('event_id', '')} – 1m Chart",
        xaxis_title="UTC Time",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        height=450,
    )
    fig.update_yaxes(tickformat=",.0f", showexponent="none")
    return fig
