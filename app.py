import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import numpy as np

# --- CONFIG ---
st.set_page_config(layout="wide", page_title="Global Wealth Tracker")
mf = Mftool()

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

# --- DATA FETCHING HELPERS ---
def get_indices():
    """Fetch global market index performance."""
    indices = {
        "NIFTY 50": "^NSEI",
        "SENSEX": "^BSESN",
        "FTSE 100": "^FTSE",
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC"
    }
    results = {}
    with st.spinner("Fetching Indices..."):
        # We fetch 5 days to ensure we get 2 valid trading days across different global timezones
        data = yf.download(list(indices.values()), period="5d", progress=False)['Close']
        for name, ticker in indices.items():
            try:
                valid_data = data[ticker].dropna()
                current = valid_data.iloc[-1]
                prev = valid_data.iloc[-2]
                change = ((current - prev) / prev) * 100
                results[name] = change
            except:
                results[name] = 0.0
    return results

# --- APP LAYOUT ---

# 1. GLOBAL INDEX BAR (TOP)
idx_data = get_indices()
idx_cols = st.columns(len(idx_data))
for i, (name, change) in enumerate(idx_data.items()):
    idx_cols[i].metric(name, f"{change:.2f}%", delta=f"{change:.2f}%")

st.divider()

# 2. MAIN TABS
tabs = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tabs[1]:
    st.header("Bulk Upload Holdings")
    st.info("Ensure your file has headers: Symbol, Qty, Price")
    # (Existing clean_and_map_broker logic would go here)
    st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'])

with tabs[0]:
    if st.session_state.portfolio.empty:
        st.warning("Portfolio is empty. Add stocks manually or via Bulk Upload.")
    else:
        df = st.session_state.portfolio.copy()
        
        # Live Price Fetching
        with st.spinner("Updating Market Data..."):
            tickers = df['symbol'].tolist()
            stock_tickers = [t for t in tickers if not t.isdigit()]
            
            if stock_tickers:
                market_data = yf.download(stock_tickers, period="5d", progress=False)['Close']
                
                def get_stock_stats(sym):
                    try:
                        if sym.isdigit(): # Mutual Fund Logic
                            quote = mf.get_scheme_quote(sym)
                            return float(quote['nav']), float(quote['nav']) # MF day gain usually N/A in this view
                        
                        s_data = market_data[sym].dropna() if len(stock_tickers) > 1 else market_data.dropna()
                        return s_data.iloc[-1], s_data.iloc[-2]
                    except: return 0.0, 0.0
                
                stats = df['symbol'].apply(lambda x: pd.Series(get_stock_stats(x)))
                df['ltp'] = stats[0]
                df['prev_close'] = stats[1]
            else:
                df['ltp'], df['prev_close'] = 0.0, 0.0

        # Calculations
        df['invested_val'] = df['qty'] * df['avg_price']
        df['current_val'] = df['qty'] * df['ltp']
        df['day_gain_val'] = (df['ltp'] - df['prev_close']) * df['qty']
        df['day_gain_pct'] = np.where(df['prev_close'] > 0, ((df['ltp'] - df['prev_close']) / df['prev_close']) * 100, 0.0)
        df['total_gain_pct'] = np.where(df['avg_price'] > 0, ((df['ltp'] - df['avg_price']) / df['avg_price']) * 100, 0.0)

        # --- TOP LEVEL SUMMARY METRICS ---
        total_invested = df['invested_val'].sum()
        total_current = df['current_val'].sum()
        total_day_gain = df['day_gain_val'].sum()
        avg_day_gain_pct = df['day_gain_pct'].mean()
        overall_gain_pct = ((total_current - total_invested) / total_invested * 100) if total_invested > 0 else 0.0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Invested Amount", f"₹{total_invested:,.2f}")
        m2.metric("Portfolio Value", f"₹{total_current:,.2f}")
        m3.metric("Today's Gain/Loss", f"₹{total_day_gain:,.2f}", delta=f"{avg_day_gain_pct:.2f}%")
        m4.metric("Total Returns", f"{overall_gain_pct:.2f}%")

        st.divider()

        # --- HOLDINGS TABLE ---
        st.subheader("Holdings Detail")
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
        headers = ["#", "Symbol", "Qty", "LTP", "Day Gain %", "Market Value", "Total Gain %", "Action"]
        for col, text in zip([h1, h2, h3, h4, h5, h6, h7, h8], headers):
            col.write(f"**{text}**")

        for i, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
            c1.write(f"{i+1}")
            c2.write(row['symbol'])
            c3.write(f"{row['qty']:.2f}")
            c4.write(f"{row['ltp']:.2f}")
            
            # Color coding
            d_color = "green" if row['day_gain_pct'] >= 0 else "red"
            c5.markdown(f":{d_color}[{row['day_gain_pct']:.2f}%]")
            
            c6.write(f"{row['current_val']:,.2f}")
            
            t_color = "green" if row['total_gain_pct'] >= 0 else "red"
            c7.markdown(f":{t_color}[{row['total_gain_pct']:.2f}%]")
            
            if c8.button("🗑️", key=f"del_{i}"):
                st.session_state.portfolio = st.session_state.portfolio.drop(i).reset_index(drop=True)
                st.rerun()

        # Charting
        st.divider()
        fig = px.pie(df, values='current_val', names='symbol', hole=0.5, title="Portfolio Composition")
        st.plotly_chart(fig, use_container_width=True)
