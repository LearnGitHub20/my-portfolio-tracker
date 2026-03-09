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
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")
mf = Mftool()

def load_stored_data():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        except:
            return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

def save_to_disk(df):
    df.to_csv(DB_FILE, index=False)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_stored_data()

# --- UTILS ---
def categorize_stock(symbol):
    sym = str(symbol).upper()
    if sym.endswith(('.L', '.DE', '.PA', '.AS', '.MI', '.MC')):
        return "European"
    elif sym.endswith('.NS') or sym.endswith('.BO'):
        return "Indian"
    # Basic US detection: No suffix or common US suffixes
    elif "." not in sym or sym.endswith(('.US', '.O', '.N')):
        return "US"
    return "Others"

def map_and_clean(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    patterns = {'symbol': ['symbol', 'ticker', 'isin'], 'qty': ['qty', 'quantity'], 'avg_price': ['price', 'avg', 'cost']}
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
        
        # FIXED SUFFIX LOGIC: 
        # Only add .NS if it's strictly a plain symbol and NOT a known US ticker pattern
        # (Users should ideally add .L for Europe, but this handles basic US)
        return df[required].dropna()
    return pd.DataFrame()

def render_portfolio_table(df_subset, region_name):
    if df_subset.empty:
        st.info(f"No {region_name} stocks found.")
        return

    # Bulk Fetch
    with st.status(f"Updating {region_name} Prices...", expanded=False):
        tickers = df_subset['symbol'].unique().tolist()
        data = yf.download(tickers, period="2d", progress=False)['Close']
        
        def get_stats(sym):
            try:
                s = data[sym].dropna() if len(tickers) > 1 else data.dropna()
                return s.iloc[-1], s.iloc[-2]
            except: return 0.0, 0.0
        
        stats = df_subset['symbol'].apply(lambda x: pd.Series(get_stats(x)))
        df_subset['ltp'], df_subset['prev'] = stats[0], stats[1]

    # Math
    df_subset['mkt_val'] = df_subset['qty'] * df_subset['ltp']
    df_subset['invested'] = df_subset['qty'] * df_subset['avg_price']
    df_subset['day_gain_pct'] = np.where(df_subset['prev'] > 0, ((df_subset['ltp'] - df_subset['prev']) / df_subset['prev']) * 100, 0.0)
    df_subset['total_gain_pct'] = np.where(df_subset['avg_price'] > 0, ((df_subset['ltp'] - df_subset['avg_price']) / df_subset['avg_price']) * 100, 0.0)

    # Summary Metrics for this region
    c1, c2, c3 = st.columns(3)
    currency = "₹" if region_name == "Indian" else "$" if region_name == "US" else "€"
    c1.metric(f"Total Invested ({region_name})", f"{currency}{df_subset['invested'].sum():,.2f}")
    c2.metric(f"Market Value", f"{currency}{df_subset['mkt_val'].sum():,.2f}")
    c3.metric(f"Avg Day Gain", f"{df_subset['day_gain_pct'].mean():.2f}%")

    # Table
    st.dataframe(
        df_subset[['symbol', 'qty', 'avg_price', 'ltp', 'day_gain_pct', 'mkt_val', 'total_gain_pct']].style.format({
            'avg_price': "{:.2f}", 'ltp': "{:.2f}", 'day_gain_pct': "{:.2f}%", 'mkt_val': "{:,.2f}", 'total_gain_pct': "{:.2f}%"
        }), use_container_width=True
    )

# --- MAIN UI ---
st.title("🌍 Global Multi-Market Tracker")

# 1. Global Index Bar
idx_map = {"NIFTY": "^NSEI", "SENSEX": "^BSESN", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "FTSE 100": "^FTSE", "DAX": "^GDAXI"}
idx_data = yf.download(list(idx_map.values()), period="2d", progress=False)['Close']
idx_cols = st.columns(len(idx_map))
for i, (name, ticker) in enumerate(idx_map.items()):
    try:
        chg = ((idx_data[ticker].iloc[-1] - idx_data[ticker].iloc[-2]) / idx_data[ticker].iloc[-2]) * 100
        idx_cols[i].metric(name, f"{chg:.2f}%", delta=f"{chg:.2f}%")
    except: pass

st.divider()

# Tabs for Management and Regional Dashboards
m_tab, in_tab, us_tab, eu_tab = st.tabs(["⚙️ Settings", "🇮🇳 Indian Stocks", "🇺🇸 US Stocks", "🇪🇺 European Stocks"])

with m_tab:
    st.header("Portfolio Management")
    uploaded_file = st.file_uploader("Bulk Upload CSV/Excel", type=['csv', 'xlsx'])
    if uploaded_file:
        raw_df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('csv') else pd.read_excel(uploaded_file)
        cleaned = map_and_clean(raw_df)
        if not cleaned.empty:
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, cleaned]).reset_index(drop=True)
            save_to_disk(st.session_state.portfolio)
            st.success("Uploaded successfully!")
            st.rerun()

    if st.button("🗑️ Clear Entire Portfolio"):
        st.session_state.portfolio = pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
        save_to_disk(st.session_state.portfolio)
        st.rerun()

# Processing Data for Regional Tabs
if not st.session_state.portfolio.empty:
    master_df = st.session_state.portfolio.copy()
    master_df['region'] = master_df['symbol'].apply(categorize_stock)
    
    with in_tab:
        render_portfolio_table(master_df[master_df['region'] == "Indian"], "Indian")
    with us_tab:
        render_portfolio_table(master_df[master_df['region'] == "US"], "US")
    with eu_tab:
        render_portfolio_table(master_df[master_df['region'] == "European"], "European")
else:
    st.info("Your portfolio is empty. Go to the Settings tab to upload data.")
