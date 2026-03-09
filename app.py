import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import numpy as np
import os

# --- SETTINGS ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Universal Wealth Tracker")

# --- 1. THE DATA LOADER ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            # We read the file WITH the header
            df = pd.read_csv(DB_FILE)
            return df
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
    return pd.DataFrame()

# --- 2. THE MAPPING LOGIC (Uses your headers) ---
def map_columns(df):
    if df.empty: return df
    
    # Standardize headers to lowercase for easy matching
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Logic to find your "Symbol, Qty, Price" even if case is different
    patterns = {
        'symbol': ['symbol', 'ticker', 'isin'],
        'qty': ['qty', 'quantity', 'units'],
        'avg_price': ['price', 'avg', 'cost']
    }
    
    col_map = {}
    for target, aliases in patterns.items():
        for actual in df.columns:
            if any(a in actual for a in aliases):
                col_map[actual] = target
                break
                
    df = df.rename(columns=col_map)
    
    # Final cleanup of numbers
    if 'qty' in df.columns and 'avg_price' in df.columns:
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
        df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce')
        
    return df

# --- UI START ---
st.title("📈 Portfolio Dashboard")

# Load and Process
raw_data = load_data()
portfolio = map_columns(raw_data)

# --- DEBUG SIDEBAR ---
with st.sidebar:
    st.header("🔍 File Debugger")
    if os.path.exists(DB_FILE):
        st.success(f"Found `{DB_FILE}`")
        st.write("First 3 rows of your file:")
        st.write(raw_data.head(3)) # This shows you what the app "sees"
    else:
        st.error(f"`{DB_FILE}` NOT found in root!")

# --- MAIN DASHBOARD ---
if portfolio.empty or 'symbol' not in portfolio.columns:
    st.warning("No valid data found. Check the 'File Debugger' in the sidebar.")
    st.info("Ensure your CSV has a header row like: **Symbol, Qty, Price**")
else:
    # (Market Fetching Logic)
    with st.status("Fetching Live Prices...", expanded=False) as status:
        tickers = portfolio['symbol'].unique().tolist()
        # Ensure they have .NS if they are Indian stocks
        tickers = [t if ('.' in str(t) or str(t).isdigit()) else f"{t}.NS" for t in tickers]
        
        market_data = yf.download(tickers, period="2d", progress=False)['Close']
        
        def get_ltp(sym):
            try:
                # Handle single vs multiple ticker return format
                tick = sym if ('.' in str(sym) or str(sym).isdigit()) else f"{sym}.NS"
                val = market_data[tick] if len(tickers) > 1 else market_data
                return val.iloc[-1], val.iloc[-2]
            except: return 0.0, 0.0

        stats = portfolio['symbol'].apply(lambda x: pd.Series(get_ltp(x)))
        portfolio['ltp'], portfolio['prev'] = stats[0], stats[1]
        status.update(label="Prices Synced!", state="complete")

    # Metrics & Calculations
    portfolio['mkt_val'] = portfolio['qty'] * portfolio['ltp']
    portfolio['invested'] = portfolio['qty'] * portfolio['avg_price']
    portfolio['day_gain'] = (portfolio['ltp'] - portfolio['prev']) * portfolio['qty']
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Invested", f"₹{portfolio['invested'].sum():,.2f}")
    m2.metric("Portfolio Value", f"₹{portfolio['mkt_val'].sum():,.2f}")
    m3.metric("Today's Gain", f"₹{portfolio['day_gain'].sum():,.2f}")

    st.divider()
    st.dataframe(portfolio[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val']], use_container_width=True)
