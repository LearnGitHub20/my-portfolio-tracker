import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px

# --- INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Universal Portfolio")
mf = Mftool()

def clean_and_map_broker(df):
    """Fuzzy match columns for Angel, ICICI, and Global."""
    # Standardize column names: stringify, strip, and lowercase
    original_cols = df.columns.tolist()
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Matching keywords - ADDED 'price' HERE
    col_map = {}
    patterns = {
        'symbol': ['symbol', 'trading symbol', 'stock code', 'scrip', 'ticker'],
        'qty': ['qty', 'quantity', 'total qty', 'demat allocation', 'units'],
        'avg_price': ['avg. price', 'average price', 'average cost', 'buy price', 'price', 'cost']
    }
    
    for target, aliases in patterns.items():
        for actual_col in df.columns:
            if any(alias == actual_col or alias in actual_col for alias in aliases):
                col_map[actual_col] = target
                break
    
    df = df.rename(columns=col_map)
    
    # Check for missing columns and show debug info if failing
    required = ['symbol', 'qty', 'avg_price']
    found = [col for col in required if col in df.columns]
    
    if len(found) < 3:
        st.error(f"Mapping Failed! Found: {found}. Expected: {required}")
        st.write("Headers detected in your file:", original_cols)
        return pd.DataFrame()

    # Numeric cleanup (removes commas or currency symbols)
    for col in ['qty', 'avg_price']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
    
    # Symbol cleanup
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    # Add .NS only if no suffix exists
    df['symbol'] = df['symbol'].apply(lambda x: x + ".NS" if "." not in x else x)
    
    return df[required].dropna()

def merge_holdings(df):
    df['total_cost'] = df['qty'] * df['avg_price']
    grouped = df.groupby('symbol').agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
    grouped['avg_price'] = grouped['total_cost'] / grouped['qty']
    return grouped[['symbol', 'qty', 'avg_price']]

# --- APP LAYOUT ---
st.title("💼 Global Multi-Asset Tracker")
tabs = st.tabs(["📊 Dashboard", "📤 Upload Holdings"])

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame()

# TAB: UPLOAD
with tabs[1]:
    st.header("Upload Statements")
    file = st.file_uploader("Upload Angel One, ICICI, or Global CSV/Excel", type=['csv', 'xlsx'])
    
    if file:
        try:
            # Handle both CSV and Excel
            if file.name.endswith('csv'):
                raw_df = pd.read_csv(file)
            else:
                raw_df = pd.read_excel(file)
                
            cleaned_df = clean_and_map_broker(raw_df)
            
            if not cleaned_df.empty:
                st.session_state.portfolio = merge_holdings(cleaned_df)
                st.success(f"Successfully loaded {len(st.session_state.portfolio)} assets.")
                st.dataframe(st.session_state.portfolio.head())
        except Exception as e:
            st.error(f"Error processing file: {e}")

# TAB: DASHBOARD
with tabs[0]:
    if st.session_state.portfolio.empty:
        st.info("Upload a file in the 'Upload' tab to start.")
    else:
        df = st.session_state.portfolio.copy()
        
        with st.spinner("Fetching Live Prices..."):
            tickers = df['symbol'].tolist()
            # Fetching 2 days to calculate 'Today's Change'
            data = yf.download(tickers, period="2d", interval="1d", progress=False)['Close']
            
            if len(tickers) == 1:
                df['live_price'] = data.iloc[-1]
                df['prev_close'] = data.iloc[-2]
            else:
                df['live_price'] = df['symbol'].map(lambda x: data[x].iloc[-1])
                df['prev_close'] = df['symbol'].map(lambda x: data[x].iloc[-2])

        # Calculations
        df['current_value'] = df['qty'] * df['live_price']
        df['total_gain_%'] = ((df['live_price'] - df['avg_price']) / df['avg_price']) * 100
        df['today_gain_%'] = ((df['live_price'] - df['prev_close']) / df['prev_close']) * 100
        df['weight_%'] = (df['current_value'] / df['current_value'].sum()) * 100

        # Metrics
        c1, c2, c3 = st.columns(3)
