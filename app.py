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
        data = yf.download(list(indices.values()), period="2d", progress=False)['Close']
        for name, ticker in indices.items():
            try:
                current = data[ticker].iloc[-1]
                prev = data[ticker].iloc[-2]
                change = ((current - prev) / prev) * 100
                results[name] = change
            except:
                results[name] = 0.0
    return results

# --- APP LAYOUT ---
# 1. GLOBAL INDEX BAR
idx_cols = st.columns(5)
idx_data = get_indices()
for i, (name, change) in enumerate(idx_data.items()):
    color = "inverse" if change < 0 else "normal"
    idx_cols[i].metric(name, f"{change:.2f}%", delta=f"{change:.2f}%", delta_color=color)

st.divider()

tabs = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tabs[1]:
    st.header("Bulk Upload")
    file = st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'])
    if file:
        # (Assuming your clean_and_map_broker function is defined above)
        # raw_df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        # st.session_state.portfolio = clean_and_map_broker(raw_df)
        st.success("✅ Portfolio Loaded!")

with tabs[0]:
    if st.session_state.portfolio.empty:
        st.info("Portfolio is empty. Upload data to see the dashboard.")
    else:
        df = st.session_state.portfolio.copy()
        
        # Live Price Fetching
        with st.spinner("Updating Live Market Data..."):
            tickers = df['symbol'].tolist()
            stock_tickers = [t for t in tickers if not t.isdigit()]
            
            if stock_tickers:
                market_data = yf.download(stock_tickers, period="2d", progress=False)['Close']
                
                def get_stock_stats(sym):
                    try:
                        if isinstance(market_data, pd.Series):
                            return market_data.iloc[-1], market_data.iloc[-2]
                        return market_data[sym].iloc[-1], market_data[sym].iloc[-2]
                    except: return 0, 0
                
                df[['ltp', 'prev_close']] = df['symbol'].apply(lambda x: pd.Series(get_stock_stats(x)))
            else:
                df['ltp'], df['prev_close'] = 0, 0

        # Calculations
        df['current_value'] = df['qty'] * df['ltp']
        df['day_gain_val'] = (df['ltp'] - df['prev_close']) * df['qty']
        df['day_gain_pct'] = np.where(df['prev_close'] > 0, ((df['ltp'] - df['prev_close']) / df['prev_close']) * 100, 0.0)
        df['total_gain_pct'] = np.where(df['avg_price'] > 0, ((df['ltp'] - df['avg_price']) / df['avg_price']) * 100, 0.0)

        # 2. TOP LEVEL PORTFOLIO METRICS
        m1, m2, m3 = st.columns(3)
        total_val = df['current_value'].sum()
        total_day_gain = df['day_gain_val'].sum()
        avg_total_return = df['total_gain_pct'].mean()
        
        m1.metric("Portfolio Value", f"₹{total_val:,.2f}")
        m2.metric("Today's Total Gain/Loss", f"₹{total_day_gain:,.2f}", delta=f"{df['day_gain_pct'].mean():.2f}%")
        m3.metric("Total Returns", f"{avg_total_return:.2f}%")

        st.divider()

        # 3. HOLDINGS TABLE WITH DAY GAIN
        st.subheader("Holdings Detail")
        
        # Header
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
        headers = ["#", "Symbol", "Qty", "LTP", "Day Gain %", "Current Value", "Total Gain %", "Action"]
        for col, text in zip([h1, h2, h3, h4, h5, h6, h7, h8], headers):
            col.write(f"**{text}**")

        # Rows
        for i, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
            c1.write(f"{i+1}")
            c2.write(row['symbol'])
            c3.write(f"{row['qty']:.2f}")
            c4.write(f"{row['ltp']:.2f}")
            
            # Day Gain % Column
            d_color = "green" if row['day_gain_pct'] >= 0 else "red"
            c5.markdown(f":{d_color}[{row['day_gain_pct']:.2f}%]")
            
            c6.write(f"{row['current_value']:,.2f}")
            
            # Total Gain % Column
            t_color = "green" if row['total_gain_pct'] >= 0 else "red"
            c7.markdown(f":{t_color}[{row['total_gain_pct']:.2f}%]")
            
            if c8.button("🗑️", key=f"del_{i}"):
                st.session_state.portfolio = st.session_state.portfolio.drop(i).reset_index(drop=True)
                st.rerun()

        # Analytics
        fig = px.pie(df, values='current_value', names='symbol', hole=0.4, title="Asset Allocation")
        st.plotly_chart(fig, use_container_width=True)
