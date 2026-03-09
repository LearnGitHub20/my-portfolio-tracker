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
st.set_page_config(layout="wide", page_title="Universal Wealth Tracker")
mf = Mftool()

# --- DATA PERSISTENCE FUNCTIONS ---
def load_stored_data():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except:
            return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

def save_to_disk(df):
    df.to_csv(DB_FILE, index=False)

# Initialize Session State from Disk
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_stored_data()

# --- CALLBACK FUNCTIONS (For Actions) ---
def delete_stock_callback(idx):
    st.session_state.portfolio = st.session_state.portfolio.drop(idx).reset_index(drop=True)
    save_to_disk(st.session_state.portfolio)

def add_stock_callback(s, q, p):
    if s:
        new_row = pd.DataFrame([{'symbol': s.upper().strip(), 'qty': q, 'avg_price': p}])
        # Merge if exists or append
        combined = pd.concat([st.session_state.portfolio, new_row]).reset_index(drop=True)
        st.session_state.portfolio = combined
        save_to_disk(st.session_state.portfolio)

# --- DATA FETCHING ---
@st.cache_data(ttl=300)
def get_global_indices():
    indices = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "FTSE 100": "^FTSE", "S&P 500": "^GSPC", "NASDAQ": "^IXIC"}
    results = {}
    try:
        data = yf.download(list(indices.values()), period="5d", progress=False)['Close']
        for name, ticker in indices.items():
            valid = data[ticker].dropna()
            change = ((valid.iloc[-1] - valid.iloc[-2]) / valid.iloc[-2]) * 100
            results[name] = change
    except:
        return {k: 0.0 for k in indices.keys()}
    return results

def clean_and_map_broker(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    patterns = {
        'symbol': ['symbol', 'trading symbol', 'stock code', 'scrip', 'ticker', 'isin'],
        'qty': ['qty', 'quantity', 'total qty', 'units'],
        'avg_price': ['avg. price', 'average price', 'average cost', 'buy price', 'price', 'cost']
    }
    col_map = {}
    for target, aliases in patterns.items():
        for actual_col in df.columns:
            if any(alias == actual_col or alias in actual_col for alias in aliases):
                col_map[actual_col] = target
                break
    df = df.rename(columns=col_map)
    if not all(k in df.columns for k in ['symbol', 'qty', 'avg_price']):
        return pd.DataFrame()
    
    for col in ['qty', 'avg_price']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
    
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    df['symbol'] = df['symbol'].apply(lambda x: x + ".NS" if ("." not in x and not x.isdigit()) else x)
    return df[['symbol', 'qty', 'avg_price']].dropna()

# --- UI LAYOUT ---

# 1. Global Index Ticker
idx_data = get_global_indices()
cols = st.columns(len(idx_data))
for i, (name, val) in enumerate(idx_data.items()):
    cols[i].metric(name, f"{val:.2f}%", delta=f"{val:.2f}%")

st.divider()

# 2. Tabs
tab_dash, tab_upload = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tab_upload:
    st.header("Upload Holdings")
    uploaded_file = st.file_uploader("Upload CSV/Excel (Angel, ICICI, or Custom)", type=['csv', 'xlsx'])
    if uploaded_file:
        raw_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('csv') else pd.read_excel(uploaded_file)
        cleaned = clean_and_map_broker(raw_df)
        if not cleaned.empty:
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, cleaned]).reset_index(drop=True)
            save_to_disk(st.session_state.portfolio)
            st.success("Portfolio updated and saved to system!")
            st.rerun()

with tab_dash:
    # Manual Add Section
    with st.expander("➕ Add Asset Manually"):
        c1, c2, c3 = st.columns(3)
        msym = c1.text_input("Symbol (e.g. RELIANCE.NS)")
        mqty = c2.number_input("Quantity", min_value=0.0, step=1.0)
        mprc = c3.number_input("Avg Price", min_value=0.0, step=0.01)
        if st.button("Add to Portfolio"):
            add_stock_callback(msym, mqty, mprc)
            st.rerun()

    if st.session_state.portfolio.empty:
        st.info("Portfolio is empty. Upload a file or add a stock manually.")
    else:
        df = st.session_state.portfolio.copy()
        
        # Live Data Fetching
        with st.spinner("Fetching Market Prices..."):
            tickers = df['symbol'].tolist()
            stock_tickers = [t for t in tickers if not t.isdigit()]
            
            if stock_tickers:
                market_data = yf.download(stock_tickers, period="5d", progress=False)['Close']
                
                def get_live_info(sym):
                    try:
                        # Extract series for specific ticker
                        s_data = market_data[sym].dropna() if len(stock_tickers) > 1 else market_data.dropna()
                        return s_data.iloc[-1], s_data.iloc[-2]
                    except: return 0.0, 0.0

                stats = df['symbol'].apply(lambda x: pd.Series(get_live_info(x)))
                df['ltp'] = stats[0]
                df['prev_close'] = stats[1]
            else:
                df['ltp'], df['prev_close'] = 0.0, 0.0

        # Calculations
        df['invested_val'] = df['qty'] * df['avg_price']
        df['market_val'] = df['qty'] * df['ltp']
        df['day_gain_pct'] = np.where(df['prev_close'] > 0, ((df['ltp'] - df['prev_close']) / df['prev_close']) * 100, 0.0)
        df['total_gain_pct'] = np.where(df['avg_price'] > 0, ((df['ltp'] - df['avg_price']) / df['avg_price']) * 100, 0.0)
        df['day_gain_val'] = (df['ltp'] - df['prev_close']) * df['qty']

        # --- TOP LEVEL METRICS ---
        t_inv = df['invested_val'].sum()
        t_mkt = df['market_val'].sum()
        t_day = df['day_gain_val'].sum()
        t_ret = ((t_mkt - t_inv) / t_inv * 100) if t_inv > 0 else 0.0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Invested Amount", f"₹{t_inv:,.2f}")
        m2.metric("Portfolio Value", f"₹{t_mkt:,.2f}")
        m3.metric("Day Gain/Loss", f"₹{t_day:,.2f}", delta=f"{df['day_gain_pct'].mean():.2f}%")
        m4.metric("Total Returns", f"{t_ret:.2f}%")

        st.divider()

        # --- DATA TABLE ---
        st.subheader("Current Holdings")
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
        for col, text in zip([h1, h2, h3, h4, h5, h6, h7, h8], ["#", "Symbol", "Qty", "LTP", "Day Gain %", "Market Value", "Total Gain %", "Action"]):
            col.write(f"**{text}**")

        for i, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([0.5, 2, 1, 1, 1, 1, 1, 0.5])
            c1.write(f"{i+1}")
            c2.write(row['symbol'])
            c3.write(f"{row['qty']:.2f}")
            c4.write(f"{row['ltp']:.2f}")
            
            d_col = "green" if row['day_gain_pct'] >= 0 else "red"
            c5.markdown(f":{d_col}[{row['day_gain_pct']:.2f}%]")
            
            c6.write(f"{row['market_val']:,.2f}")
            
            t_col = "green" if row['total_gain_pct'] >= 0 else "red"
            c7.markdown(f":{t_col}[{row['total_gain_pct']:.2f}%]")
            
            c8.button("🗑️", key=f"del_{row['symbol']}_{i}", on_click=delete_stock_callback, args=(i,))

        # --- CHARTS ---
        st.divider()
        fig = px.pie(df, values='market_val', names='symbol', hole=0.5, title="Asset Allocation")
        st.plotly_chart(fig, use_container_width=True)
