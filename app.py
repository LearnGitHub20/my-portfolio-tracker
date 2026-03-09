import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import numpy as np
import os

# --- PERSISTENCE CONFIG ---
DB_FILE = "portfolio_db.csv"

# --- INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Universal Wealth Tracker", page_icon="📈")
mf = Mftool()

# --- DATA PERSISTENCE ---
def load_stored_data():
    if os.path.exists(DB_FILE):
        try:
            # Added error skipping to handle the "Line 34" issue automatically
            df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
            return df
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

def save_to_disk(df):
    df.to_csv(DB_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_stored_data()

# --- CALLBACKS ---
def delete_stock_callback(idx):
    st.session_state.portfolio = st.session_state.portfolio.drop(idx).reset_index(drop=True)
    save_to_disk(st.session_state.portfolio)

# --- UTILS ---
def map_and_clean(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    patterns = {
        'symbol': ['symbol', 'ticker', 'isin', 'scrip'],
        'qty': ['qty', 'quantity', 'units'],
        'avg_price': ['price', 'avg', 'cost', 'buy']
    }
    col_map = {}
    for target, aliases in patterns.items():
        for actual_col in df.columns:
            if any(alias in actual_col for alias in aliases):
                col_map[actual_col] = target
                break
    df = df.rename(columns=col_map)
    required = ['symbol', 'qty', 'avg_price']
    if all(k in df.columns for k in required):
        df['qty'] = pd.to_numeric(df['qty'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
        df['avg_price'] = pd.to_numeric(df['avg_price'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
        df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
        # Ensure .NS for Indian stocks
        df['symbol'] = df['symbol'].apply(lambda x: x + ".NS" if ("." not in x and not x.isdigit()) else x)
        return df[required].dropna()
    return pd.DataFrame()

# --- TOP INDICES ---
@st.cache_data(ttl=600)
def fetch_indices():
    idx_map = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "FTSE 100": "^FTSE"}
    data = yf.download(list(idx_map.values()), period="2d", progress=False)['Close']
    res = {}
    for name, ticker in idx_map.items():
        try:
            val = ((data[ticker].iloc[-1] - data[ticker].iloc[-2]) / data[ticker].iloc[-2]) * 100
            res[name] = val
        except: res[name] = 0.0
    return res

# 1. Show Indices at the very top
idx_data = fetch_indices()
idx_cols = st.columns(len(idx_data))
for i, (name, val) in enumerate(idx_data.items()):
    idx_cols[i].metric(name, f"{val:.2f}%", delta=f"{val:.2f}%")

st.divider()

# --- MAIN NAVIGATION ---
tab_dash, tab_upload = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tab_upload:
    st.header("Upload Holdings")
    uploaded_file = st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'])
    if uploaded_file:
        raw_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('csv') else pd.read_excel(uploaded_file)
        cleaned = map_and_clean(raw_df)
        if not cleaned.empty:
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, cleaned]).reset_index(drop=True)
            save_to_disk(st.session_state.portfolio)
            st.success("Portfolio Updated!")
            st.rerun()

with tab_dash:
    if st.session_state.portfolio.empty:
        st.warning("No data found. Please upload a file in the 'Bulk Upload' tab.")
    else:
        df = st.session_state.portfolio.copy()
        # Ensure mapping is applied to the loaded CSV data
        df = map_and_clean(df)

        with st.status("Fetching Live Prices...", expanded=False) as status:
            tickers = df['symbol'].unique().tolist()
            market_data = yf.download(tickers, period="5d", progress=False)['Close']
            
            def get_stats(sym):
                try:
                    s = market_data[sym].dropna() if len(tickers) > 1 else market_data.dropna()
                    return s.iloc[-1], s.iloc[-2]
                except: return 0.0, 0.0
            
            stats = df['symbol'].apply(lambda x: pd.Series(get_stats(x)))
            df['ltp'], df['prev'] = stats[0], stats[1]
            status.update(label="Pricing Complete!", state="complete")

        # Portfolio Math
        df['invested'] = df['qty'] * df['avg_price']
        df['market_val'] = df['qty'] * df['ltp']
        df['day_gain_pct'] = np.where(df['prev'] > 0, ((df['ltp'] - df['prev']) / df['prev']) * 100, 0.0)
        df['total_gain_pct'] = np.where(df['avg_price'] > 0, ((df['ltp'] - df['avg_price']) / df['avg_price']) * 100, 0.0)
        df['day_gain_val'] = (df['ltp'] - df['prev']) * df['qty']

        # 2. Top Level Metrics (Now with Invested Amount)
        t_inv = df['invested'].sum()
        t_mkt = df['market_val'].sum()
        t_day = df['day_gain_val'].sum()
        t_ret = ((t_mkt - t_inv) / t_inv * 100) if t_inv > 0 else 0.0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Invested Amount", f"₹{t_inv:,.2f}")
        m2.metric("Portfolio Value", f"₹{t_mkt:,.2f}")
        m3.metric("Today's Gain/Loss", f"₹{t_day:,.2f}", delta=f"{df['day_gain_pct'].mean():.2f}%")
        m4.metric("Total Returns", f"{t_ret:.2f}%")

        st.divider()

        # 3. Individual Holdings Table with Delete Option
        st.subheader(f"Holdings Detail ({len(df)} Assets)")
        
        # Table Header
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
        for col, text in zip([h1, h2, h3, h4, h5, h6, h7, h8], ["#", "Symbol", "Qty", "LTP", "Day Gain %", "Market Val", "Total Gain %", "Del"]):
            col.write(f"**{text}**")

        # Table Rows
        for i, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
            c1.write(f"{i+1}")
            c2.write(row['symbol'])
            c3.write(f"{row['qty']:.2f}")
            c4.write(f"₹{row['ltp']:.2f}")
            
            d_col = "green" if row['day_gain_pct'] >= 0 else "red"
            c5.markdown(f":{d_col}[{row['day_gain_pct']:.2f}%]")
            
            c6.write(f"₹{row['market_val']:,.2f}")
            
            t_col = "green" if row['total_gain_pct'] >= 0 else "red"
            c7.markdown(f":{t_col}[{row['total_gain_pct']:.2f}%]")
            
            # The Callback Deletion Fix
            c8.button("🗑️", key=f"del_{row['symbol']}_{i}", on_click=delete_stock_callback, args=(i,))

        # Allocation Chart
        st.divider()
        fig = px.pie(df, values='market_val', names='symbol', hole=0.5, title="Asset Composition")
        st.plotly_chart(fig, use_container_width=True)
