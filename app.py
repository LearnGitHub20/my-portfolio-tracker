import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px

# --- INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Universal Portfolio")
mf = Mftool()

# --- HELPER FUNCTIONS ---
def clean_and_map_broker(df):
    """Fuzzy match columns for Angel, ICICI, and Global."""
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Matching keywords
    col_map = {}
    patterns = {
        'symbol': ['symbol', 'trading symbol', 'stock code', 'scrip'],
        'qty': ['qty', 'quantity', 'total qty', 'demat allocation'],
        'avg_price': ['avg. price', 'average price', 'average cost', 'buy price']
    }
    
    for target, aliases in patterns.items():
        for actual_col in df.columns:
            if any(alias in actual_col for alias in aliases):
                col_map[actual_col] = target
                break
    
    df = df.rename(columns=col_map)
    
    # Ensure mandatory columns exist
    if not all(k in df.columns for k in ['symbol', 'qty', 'avg_price']):
        return pd.DataFrame()

    # Numeric cleanup
    df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
    df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce')
    
    # Symbol cleanup (Indian Stocks)
    df['symbol'] = df['symbol'].astype(str).str.upper()
    df['symbol'] = df['symbol'].apply(lambda x: x + ".NS" if not ("." in x) else x)
    
    return df[['symbol', 'qty', 'avg_price']].dropna()

def merge_holdings(df):
    df['total_cost'] = df['qty'] * df['avg_price']
    grouped = df.groupby('symbol').agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
    grouped['avg_price'] = grouped['total_cost'] / grouped['qty']
    return grouped[['symbol', 'qty', 'avg_price']]

# --- APP LAYOUT ---
st.title("💼 Global Multi-Asset Tracker")

# Fix: Defining the tabs variable clearly
tabs = st.tabs(["📊 Dashboard", "📤 Upload Holdings"])

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame()

# TAB 1: UPLOAD (We do this first so data is available)
with tabs[1]:
    st.header("Upload Statements")
    file = st.file_uploader("Upload Angel One, ICICI, or Global CSV", type=['csv', 'xlsx'])
    
    if file:
        raw_df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        cleaned_df = clean_and_map_broker(raw_df)
        
        if not cleaned_df.empty:
            st.session_state.portfolio = merge_holdings(cleaned_df)
            st.success(f"Loaded {len(st.session_state.portfolio)} unique symbols!")
        else:
            st.error("Error: Could not find required columns (Symbol, Qty, Price).")

# TAB 0: DASHBOARD
with tabs[0]:
    if st.session_state.portfolio.empty:
        st.info("Please upload a file in the 'Upload' tab to see your analysis.")
    else:
        df = st.session_state.portfolio.copy()
        
        # Live Price Fetching
        with st.spinner("Updating Market Prices..."):
            tickers = df['symbol'].tolist()
            try:
                data = yf.download(tickers, period="1d", progress=False)['Close']
                # If only one ticker, yf returns a Series; if many, a DataFrame
                if len(tickers) == 1:
                    df['live_price'] = data.iloc[-1]
                else:
                    df['live_price'] = df['symbol'].map(lambda x: data[x].iloc[-1])
            except:
                st.warning("Could not fetch live prices. Using purchase price as fallback.")
                df['live_price'] = df['avg_price']

        # Analysis
        df['current_value'] = df['qty'] * df['live_price']
        df['profit_loss'] = ((df['live_price'] - df['avg_price']) / df['avg_price']) * 100
        
        m1, m2 = st.columns(2)
        m1.metric("Total Portfolio Value", f"₹{df['current_value'].sum():,.2f}")
        m2.metric("Portfolio Gain/Loss", f"{df['profit_loss'].mean():.2f}%")

        st.dataframe(df.style.format(precision=2), use_container_width=True)
        
        # Allocation Chart
        fig = px.pie(df, values='current_value', names='symbol', hole=0.4, title="Asset Allocation")
        st.plotly_chart(fig, use_container_width=True)
