import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import numpy as np
import os

# --- CONFIG ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

# --- 1. DATA LOADING & AUTOMATIC CLEANING ---
def load_and_clean_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        if df.empty:
            return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
        
        # Standardize headers to lowercase
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Fuzzy mapping to find the right columns
        patterns = {
            'symbol': ['symbol', 'ticker', 'isin', 'scrip'],
            'qty': ['qty', 'quantity', 'units'],
            'avg_price': ['price', 'avg', 'cost', 'buy']
        }
        
        col_map = {}
        for target, aliases in patterns.items():
            for actual in df.columns:
                if any(alias in actual for alias in aliases):
                    col_map[actual] = target
                    break
        
        df = df.rename(columns=col_map)
        
        # Keep only the required columns and clean them
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            if 'qty' in df.columns:
                df['qty'] = pd.to_numeric(df['qty'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            if 'avg_price' in df.columns:
                df['avg_price'] = pd.to_numeric(df['avg_price'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            
            return df[['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
    except Exception as e:
        st.error(f"Load Error: {e}")
        
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

# Initialize Session State
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_and_clean_data()

# --- 2. REGION CATEGORIZATION ---
def categorize_stock(symbol):
    sym = str(symbol).upper()
    # European Suffixes
    if any(sym.endswith(suffix) for suffix in ['.L', '.DE', '.PA', '.AS', '.MI', '.MC']):
        return "European"
    # Indian Suffixes
    elif sym.endswith('.NS') or sym.endswith('.BO'):
        return "Indian"
    # US Stocks (Usually 1-4 letters, no suffix or .US)
    elif "." not in sym or sym.endswith('.US'):
        return "US"
    return "Others"

# --- 3. UI RENDERING ---
st.title("🌍 Global Multi-Market Tracker")

# Global Index Bar (cached for performance)
@st.cache_data(ttl=600)
def get_indices():
    idx_map = {"NIFTY": "^NSEI", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "FTSE 100": "^FTSE"}
    data = yf.download(list(idx_map.values()), period="2d", progress=False)['Close']
    return data, idx_map

try:
    idx_data, idx_map = get_indices()
    idx_cols = st.columns(len(idx_map))
    for i, (name, ticker) in enumerate(idx_map.items()):
        chg = ((idx_data[ticker].iloc[-1] - idx_data[ticker].iloc[-2]) / idx_data[ticker].iloc[-2]) * 100
        idx_cols[i].metric(name, f"{chg:.2f}%", delta=f"{chg:.2f}%")
except:
    st.write("Indices temporarily unavailable")

st.divider()

# Tabs
m_tab, in_tab, us_tab, eu_tab = st.tabs(["⚙️ Settings", "🇮🇳 Indian", "🇺🇸 US", "🇪🇺 European"])

with m_tab:
    st.header("Upload/Update Portfolio")
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        # Save it to disk so the loader picks it up next time
        df.to_csv(DB_FILE, index=False)
        st.session_state.portfolio = load_and_clean_data()
        st.success("Portfolio Updated!")
        st.rerun()

# --- RENDER LOGIC ---
if not st.session_state.portfolio.empty:
    master_df = st.session_state.portfolio.copy()
    master_df['region'] = master_df['symbol'].apply(categorize_stock)
    
    # Helper to render each tab
    def render_region(df_subset, region_name):
        if df_subset.empty:
            st.info(f"No {region_name} stocks found.")
            return
            
        tickers = df_subset['symbol'].unique().tolist()
        # For Indian stocks without suffix, add .NS for fetching
        fetch_tickers = [t if ('.' in t or region_name != "Indian") else f"{t}.NS" for t in tickers]
        
        with st.status(f"Updating {region_name} Prices..."):
            data = yf.download(fetch_tickers, period="2d", progress=False)['Close']
            
            def get_price(sym):
                try:
                    t = sym if ('.' in sym or region_name != "Indian") else f"{sym}.NS"
                    val = data[t] if len(fetch_tickers) > 1 else data
                    return val.iloc[-1], val.iloc[-2]
                except: return 0.0, 0.0
            
            prices = df_subset['symbol'].apply(lambda x: pd.Series(get_price(x)))
            df_subset['ltp'], df_subset['prev'] = prices[0], prices[1]

        df_subset['mkt_val'] = df_subset['qty'] * df_subset['ltp']
        df_subset['day_chg'] = (df_subset['ltp'] - df_subset['prev']) / df_subset['prev'] * 100
        
        st.subheader(f"{region_name} Portfolio")
        st.dataframe(df_subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'day_chg']], use_container_width=True)

    with in_tab: render_region(master_df[master_df['region'] == "Indian"], "Indian")
    with us_tab: render_region(master_df[master_df['region'] == "US"], "US")
    with eu_tab: render_region(master_df[master_df['region'] == "European"], "European")
else:
    st.info("Upload a CSV in Settings to begin.")
