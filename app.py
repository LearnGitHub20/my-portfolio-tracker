import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Global Wealth Tracker")
mf = Mftool()

# --- BROKER MAPPING & CLEANING ---
def normalize_indian_stocks(df):
    """Detects broker and maps columns to standard format with debugging."""
    # Convert column names to lowercase and strip whitespace
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # --- DEBUGGING: Uncomment the line below to see your columns in the app ---
    # st.write("Columns found in file:", df.columns.tolist())
    
    # Logic for ICICIdirect vs Angel One
    # We look for unique identifiers in the columns to guess the broker
    if any('stock' in c or 'cost' in c for c in df.columns): # ICICI
        mapping = {'stock code': 'symbol', 'quantity': 'qty', 'average cost': 'avg_price'}
        df = df.rename(columns=mapping)
    else: # Angel or General
        # Angel One often uses 'trading symbol' or 'scrip name'
        # We try to map common Angel variations
        mapping = {
            'trading symbol': 'symbol', 
            'scrip name': 'symbol', 
            'symbol': 'symbol',
            'average price': 'avg_price', 
            'buy price': 'avg_price',
            'avg. price': 'avg_price',
            'total qty': 'qty', 
            'quantity': 'qty'
        }
        df = df.rename(columns=mapping)
    
    # Ensure we have the required columns, if not, throw an error
    required = ['symbol', 'qty', 'avg_price']
    if not all(col in df.columns for col in required):
        st.error(f"Could not map columns. Found: {df.columns.tolist()}")
        return pd.DataFrame()
        
    # Add .NS for Indian Tickers
    df['symbol'] = df['symbol'].str.upper().apply(lambda x: f"{x}.NS" if not x.endswith(('.NS', '.BO')) else x)
    return df[required]

# --- Update your Uploader Section ---
with tab_in:
    up_in = st.file_uploader("Upload ICICI/Angel CSV/Excel", type=['csv', 'xlsx'])
    if up_in:
        try:
            # Detect file type and read
            if up_in.name.endswith('.xlsx'):
                raw_in = pd.read_excel(up_in)
            else:
                raw_in = pd.read_csv(up_in)
                
            norm_in = normalize_indian_stocks(raw_in)
            if not norm_in.empty:
                st.session_state.in_df = merge_holdings(norm_in)
                st.success("File uploaded successfully!")
        except Exception as e:
            st.error(f"Error reading file: {e}")

def merge_holdings(df, symbol_col='symbol'):
    """Merges duplicates and calculates Weighted Average Price."""
    if df.empty: return df
    df['total_cost'] = df['qty'] * df['avg_price']
    grouped = df.groupby(symbol_col).agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
    grouped['avg_price'] = grouped['total_cost'] / grouped['qty']
    return grouped

# --- DATA FETCHING ---
@st.cache_data(ttl=3600)
def get_live_data(tickers):
    if not tickers: return {}
    data = yf.download(tickers, period="2d", interval="1d", progress=False)
    results = {}
    for t in tickers:
        try:
            current = data['Close'][t].iloc[-1]
            prev_close = data['Close'][t].iloc[-2]
            day_change = ((current - prev_close) / prev_close) * 100
            results[t] = {'price': current, 'change': day_change}
        except: results[t] = {'price': 0, 'change': 0}
    return results

@st.cache_data(ttl=3600)
def get_fx_rates():
    rates = {'USD': 1.0, 'GBP': 1.0, 'EUR': 1.0}
    for curr in rates.keys():
        rates[curr] = yf.Ticker(f"{curr}INR=X").fast_info['last_price']
    return rates

# --- MAIN UI ---
st.title("💼 Universal Portfolio Manager")
st.markdown("---")

tab_sum, tab_in, tab_mf, tab_gl = st.tabs(["Summary", "India Stocks", "India MFs", "Global Stocks"])

# Persistent State
for key in ['in_df', 'mf_df', 'gl_df']:
    if key not in st.session_state: st.session_state[key] = pd.DataFrame()

# --- SECTION: INDIA STOCKS ---
with tab_in:
    up_in = st.file_uploader("Upload ICICI/Angel CSV", type=['csv', 'xlsx'])
    if up_in:
        raw_in = pd.read_csv(up_in) if up_in.name.endswith('.csv') else pd.read_excel(up_in)
        norm_in = normalize_indian_stocks(raw_in)
        st.session_state.in_df = merge_holdings(norm_in)

    if not st.session_state.in_df.empty:
        df = st.session_state.in_df
        live = get_live_data(df['symbol'].tolist())
        df['current_price'] = df['symbol'].map(lambda x: live.get(x, {}).get('price', 0))
        df['today_gain_%'] = df['symbol'].map(lambda x: live.get(x, {}).get('change', 0))
        df['total_value'] = df['qty'] * df['current_price']
        df['overall_gain_%'] = ((df['current_price'] - df['avg_price']) / df['avg_price']) * 100
        st.dataframe(df.style.format(precision=2), use_container_width=True)

# --- SECTION: MUTUAL FUNDS ---
with tab_mf:
    up_mf = st.file_uploader("Upload MF CSV (Scheme Code, Units, Avg NAV)", type=['csv'])
    if up_mf:
        raw_mf = pd.read_csv(up_mf)
        raw_mf.columns = ['symbol', 'qty', 'avg_price'] # Standardize internal names
        st.session_state.mf_df = merge_holdings(raw_mf)

    if not st.session_state.mf_df.empty:
        df = st.session_state.mf_df
        # Fetch NAVs
        nav_list = []
        for code in df['symbol']:
            try: nav_list.append(float(mf.get_scheme_quote(str(code))['nav']))
            except: nav_list.append(0)
        df['current_price'] = nav_list
        df['total_value'] = df['qty'] * df['current_price']
        df['overall_gain_%'] = ((df['current_price'] - df['avg_price']) / df['avg_price']) * 100
        st.dataframe(df.style.format(precision=2), use_container_width=True)

# --- SECTION: GLOBAL STOCKS ---
with tab_gl:
    up_gl = st.file_uploader("Upload Global CSV (Ticker, Qty, Avg Price, Currency)", type=['csv'])
    if up_gl:
        raw_gl = pd.read_csv(up_gl)
        raw_gl.columns = ['symbol', 'qty', 'avg_price', 'currency']
        st.session_state.gl_df = merge_holdings(raw_gl)

    if not st.session_state.gl_df.empty:
        df = st.session_state.gl_df
        live_gl = get_live_data(df['symbol'].tolist())
        df['current_price'] = df['symbol'].map(lambda x: live_gl.get(x, {}).get('price', 0))
        df['total_value_local'] = df['qty'] * df['current_price']
        st.dataframe(df.style.format(precision=2), use_container_width=True)

# --- SUMMARY & ANALYTICS ---
with tab_sum:
    fx = get_fx_rates()
    in_val = st.session_state.in_df['total_value'].sum() if not st.session_state.in_df.empty else 0
    mf_val = st.session_state.mf_df['total_value'].sum() if not st.session_state.mf_df.empty else 0
    
    gl_val = 0
    if not st.session_state.gl_df.empty:
        df_gl = st.session_state.gl_df
        df_gl['total_value_inr'] = df_gl.apply(lambda x: x['total_value_local'] * fx.get(x['currency'], 1), axis=1)
        gl_val = df_gl['total_value_inr'].sum()

    total_portfolio = in_val + mf_val + gl_val
    
    if total_portfolio > 0:
        c1, c2, c3 = st.columns(3)
        c1.metric("Net Worth (INR)", f"₹{total_portfolio:,.0f}")
        c2.metric("Total Stocks", f"₹{(in_val + gl_val):,.0f}")
        c3.metric("Total MFs", f"₹{mf_val:,.0f}")

        # Analytics
        st.divider()
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("Asset Allocation")
            fig = px.pie(values=[in_val, mf_val, gl_val], 
                         names=['Indian Stocks', 'Mutual Funds', 'Global Stocks'], hole=0.6)
            st.plotly_chart(fig, use_container_width=True)
            
        with col_right:
            st.subheader("Portfolio Weighting")
            # Combine all for weight analysis
            weights = pd.concat([st.session_state.in_df[['symbol', 'total_value']], 
                                 st.session_state.mf_df[['symbol', 'total_value']]])
            fig_bar = px.bar(weights.sort_values('total_value', ascending=False).head(10), 
                             x='symbol', y='total_value', color='symbol')
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Upload your holdings in the tabs above to see the summary.")
