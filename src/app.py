import pandas as pd
import streamlit as st
from pathlib import Path

from event_loader import load_event_json
from chart_builder import build_chart

OUTPUT_DIR = Path("output")


def main():
    st.set_page_config(page_title="SL Event Viewer", layout="wide")
    st.title("SL Event Viewer")

    # ---------------- Sidebar: event selection ----------------
    st.sidebar.header("Event Selection")

    event_files = sorted(OUTPUT_DIR.glob("*.json"))

    if not event_files:
        st.sidebar.error(f"No event JSON files in {OUTPUT_DIR}/")
        st.stop()

    labels = [f.name for f in event_files]
    selected = st.sidebar.selectbox("Choose event", labels)
    selected_path = OUTPUT_DIR / selected

    # Load event JSON
    event = load_event_json(selected_path)

    # Build dataframe from embedded candles
    df_5m = pd.DataFrame(event.get("ohlc_5m", []))
    if not df_5m.empty:
        df_5m["ts_event"] = pd.to_datetime(df_5m["ts_event"], utc=True)

    # ---------------- Sidebar: summary ----------------
    st.sidebar.markdown("---")
    st.sidebar.subheader("Summary")

    summary = event.get("summary", {}) or {}
    hourly = event.get("hourly_fvg", {}) or {}

    hourly_id = hourly.get("fvg_hour_id", "N/A")
    hourly_start = hourly.get("start_time", "N/A")
    hourly_end = hourly.get("end_time", "N/A")
    hourly_dir = hourly.get("direction", "N/A")
    hourly_end_bound = hourly.get("end_bound", "N/A")

    st.sidebar.write(f"**Event ID:** {event.get('event_id', 'N/A')}")
    st.sidebar.write(f"**Status:** {summary.get('status', 'N/A')}")

    # Summary counts (these are the numbers you just added)
    st.sidebar.write(f"**5m FVGs:** {summary.get('fvg_5m_count', 'N/A')}")
    st.sidebar.write(f"**5m BOS events:** {summary.get('bos_5m_count', 'N/A')}")
    st.sidebar.write(f"**Trade signals:** {summary.get('signal_count', 'N/A')}")

    st.sidebar.markdown("---")
    st.sidebar.write(f"**Hourly FVG ID:** {hourly_id}")
    st.sidebar.write(f"**Hourly FVG start:** {hourly_start}")
    st.sidebar.write(f"**Hourly FVG end:** {hourly_end}")

    # Big colored arrow for direction
    if hourly_dir == "up":
        arrow_html = """
        <div style="display:flex;align-items:center;gap:8px;">
          <span><strong>Hourly FVG direction:</strong> up</span>
          <span style="color:#00cc44; font-size:26px; line-height:1;">▲</span>
        </div>
        """
    elif hourly_dir == "down":
        arrow_html = """
        <div style="display:flex;align-items:center;gap:8px;">
          <span><strong>Hourly FVG direction:</strong> down</span>
          <span style="color:#ff3333; font-size:26px; line-height:1;">▼</span>
        </div>
        """
    else:
        arrow_html = f"**Hourly FVG direction:** {hourly_dir}"

    st.sidebar.markdown(arrow_html, unsafe_allow_html=True)
    st.sidebar.write(f"**Hourly FVG end_bound:** {hourly_end_bound}")

    # ---- Pre / Post windows in sidebar ----
    pre_start = hourly.get("pretouch_window_start", "N/A")
    pre_end = hourly.get("pretouch_window_end", "N/A")
    post_start = hourly.get("posttouch_window_start", "N/A")
    post_end = hourly.get("posttouch_window_end", "N/A")

    st.sidebar.markdown("### Windows")
    st.sidebar.write(f"**Pre-touch window:** {pre_start} → {pre_end}")
    st.sidebar.write(f"**Post-touch window:** {post_start} → {post_end}")

    # ---------------- Trades + metrics ----------------
    trade_signals = event.get("trade_signals", []) or []

    if not trade_signals:
        st.sidebar.markdown("---")
        st.sidebar.write("**Trades:** None")
    else:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### Trade Details")

        for sig in trade_signals:
            signal_type = sig.get("signal", "N/A")
            entry_ts = sig.get("entry_ts")
            entry_price = sig.get("entry_price")
            stop_loss = sig.get("stop_loss")
            take_profit = sig.get("take_profit")
            exit_type = sig.get("exit_signal")
            exit_ts = sig.get("exit_ts")
            exit_price = sig.get("exit_price")

            st.sidebar.write(f"**Type:** {signal_type}")
            st.sidebar.write(f"**Entry Time:** {entry_ts or 'N/A'}")
            st.sidebar.write(f"**Entry Price:** {entry_price if entry_price is not None else 'N/A'}")
            st.sidebar.write(f"**Stop Loss:** {stop_loss if stop_loss is not None else 'N/A'}")
            st.sidebar.write(f"**Take Profit:** {take_profit if take_profit is not None else 'N/A'}")
            st.sidebar.write(f"**Exit Type:** {exit_type or 'N/A'}")
            st.sidebar.write(f"**Exit Time:** {exit_ts or 'N/A'}")
            st.sidebar.write(f"**Exit Price:** {exit_price if exit_price is not None else 'N/A'}")

            # ---- Derived metrics: R, PnL, PnL in R ----
            R = None
            pnl_points = None
            pnl_R = None

            if (
                entry_price is not None
                and stop_loss is not None
                and exit_price is not None
            ):
                # 1R based on distance to stop
                R = abs(entry_price - stop_loss)

                # Long vs short PnL in points
                if signal_type == "buy_long":
                    pnl_points = exit_price - entry_price
                elif signal_type == "sell_short":
                    pnl_points = entry_price - exit_price

                if R and pnl_points is not None:
                    pnl_R = pnl_points / R

            # Only show metrics if we could compute them
            if R is not None:
                st.sidebar.write(f"**R (risk per trade):** {R:.2f}")
            if pnl_points is not None:
                st.sidebar.write(f"**PnL (points):** {pnl_points:.2f}")
            if pnl_R is not None:
                st.sidebar.write(f"**PnL (R):** {pnl_R:.2f}")

            st.sidebar.markdown("---")

    # ---------------- Main Chart ----------------
    st.subheader("Event Chart")
    fig = build_chart(df_5m, event)
    st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
