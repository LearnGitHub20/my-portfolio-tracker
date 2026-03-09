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

def load_stored_data():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_csv(DB_FILE)
            # Ensure basic columns exist
            for col in ['symbol', 'qty', 'avg_price']:
                if col not in df.columns: df[col] = 0
            return df
        except:
            return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

def save_to_disk(df):
    df.to_csv(DB_FILE, index=False)

# Initialize Session State
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_stored_data()

# --- CALLBACKS ---
def delete_stock_callback(idx):
    st.session_state.portfolio = st.session_state.portfolio.drop(idx).reset_index(drop=True)
    save_to_disk(st.session_state.portfolio)

# --- UTILS ---
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

# --- TOP NAVIGATION & INDICES ---
@st.cache_data(ttl=600)
def fetch_global_indices():
    indices = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "FTSE 100": "^FTSE"}
    data = yf.download(list(indices.values()), period="2d", progress=False)['Close']
    res = {}
    for name, ticker in indices.items():
        try:
            change = ((data[ticker].iloc[-1] - data[ticker].iloc[-2]) / data[ticker].iloc[-2]) * 100
            res[name] = change
        except: res[name] = 0.0
    return res

# 1. Index Bar
idx_data = fetch_global_indices()
idx_cols = st.columns(len(idx_data))
for i, (name, val) in enumerate(idx_data.items()):
    idx_cols[i].metric(name, f"{val:.2f}%", delta=f"{val:.2f}%")

st.divider()

# --- MAIN APP ---
tabs = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tabs[1]:
    st.header("Bulk Upload Settings")
    uploaded_file = st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'])
    if uploaded_file:
        raw_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('csv') else pd.read_excel(uploaded_file)
        cleaned = clean_and_map_broker(raw_df)
        if not cleaned.empty:
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, cleaned]).reset_index(drop=True)
            save_to_disk(st.session_state.portfolio)
            st.success(f"Added {len(cleaned)} items. Please refresh dashboard.")
            st.rerun()

with tabs[0]:
    if st.session_state.portfolio.empty:
        st.warning("No data found in portfolio_db.csv. Please upload a file.")
    else:
        df = st.session_state.portfolio.copy()
        
        # --- ASYNC-STYLE PRICE FETCHING ---
        # We show the table structure immediately, then fill prices
        if 'live_df' not in st.session_state:
            st.session_state.live_df = None

        with st.status("Updating 85+ Assets...", expanded=False) as status:
            tickers = df['symbol'].tolist()
            stock_tickers = [t for t in tickers if not t.isdigit()]
            
            if stock_tickers:
                try:
                    # Bulk fetch for speed
                    market_data = yf.download(stock_tickers, period="5d", progress=False)['Close']
                    
                    def get_stats(sym):
                        try:
                            s = market_data[sym].dropna() if len(stock_tickers) > 1 else market_data.dropna()
                            return s.iloc[-1], s.iloc[-2]
                        except: return 0.0, 0.0
                    
                    stats = df['symbol'].apply(lambda x: pd.Series(get_stats(x)))
                    df['ltp'], df['prev_close'] = stats[0], stats[1]
                except Exception as e:
                    st.error(f"Network Error: {e}")
                    df['ltp'], df['prev_close'] = 0, 0
            
            status.update(label="Pricing Update Complete!", state="complete")

        # Calculations
        df['invested'] = df['qty'] * df['avg_price']
        df['current_val'] = df['qty'] * df['ltp']
        df['day_gain_pct'] = np.where(df['prev_close'] > 0, ((df['ltp'] - df['prev_close']) / df['prev_close']) * 100, 0.0)
        df['total_gain_pct'] = np.where(df['avg_price'] > 0, ((df['ltp'] - df['avg_price']) / df['avg_price']) * 100, 0.0)
        df['day_gain_val'] = (df['ltp'] - df['prev_close']) * df['qty']

        # Metrics Top Bar
        m1, m2, m3, m4 = st.columns(4)
        total_inv = df['invested'].sum()
        total_mkt = df['current_val'].sum()
        m1.metric("Invested", f"₹{total_inv:,.2f}")
        m2.metric("Portfolio Value", f"₹{total_mkt:,.2f}")
        m3.metric("Day Change", f"₹{df['day_gain_val'].sum():,.2f}", delta=f"{df['day_gain_pct'].mean():.2f}%")
        m4.metric("Total Return", f"{((total_mkt-total_inv)/total_inv*100 if total_inv>0 else 0):.2f}%")

        st.divider()

        # --- THE HOLDINGS TABLE ---
        st.subheader(f"Detailed Holdings ({len(df)} Assets)")
        
        # Use st.dataframe for large lists (better scrolling/memory than columns)
        # We style it to make it look like a dashboard
        display_df = df[['symbol', 'qty', 'avg_price', 'ltp', 'day_gain_pct', 'current_val', 'total_gain_pct']].copy()
        display_df.index += 1 # 1-based index
        
        st.dataframe(
            display_df.style.format({
                'qty': "{:.2f}",
                'avg_price': "₹{:.2f}",
                'ltp': "₹{:.2f}",
                'day_gain_pct': "{:.2f}%",
                'current_val': "₹{:,.2f}",
                'total_gain_pct': "{:.2f}%"
            }),
            use_container_width=True,
            height=500
        )

        # Deletion Area (Below table for cleaner UI with 85 stocks)
        with st.expander("🗑️ Manage / Delete Assets"):
            del_target = st.selectbox("Select symbol to remove", df['symbol'].unique())
            if st.button("Confirm Delete"):
                idx = df[df['symbol'] == del_target].index[0]
                delete_stock_callback(idx)
                st.rerun()

        # Allocation Chart
        st.divider()
        fig = px.pie(df, values='current_val', names='symbol', hole=0.5, title="Asset Allocation")
        st.plotly_chart(fig, use_container_width=True)
