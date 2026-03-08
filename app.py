import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Global Portfolio Tracker")
mf = Mftool()

# --- HELPER FUNCTIONS ---
def get_fx_rates():
    """Fetch current exchange rates to INR"""
    rates = {'USD': 1.0, 'GBP': 1.0, 'EUR': 1.0, 'INR': 1.0}
    for curr in ['USD', 'GBP', 'EUR']:
        ticker = f"{curr}INR=X"
        data = yf.Ticker(ticker).fast_info['last_price']
        rates[curr] = data
    return rates

def fetch_stock_data(tickers):
    """Fetch real-time and historical data for stocks"""
    if not tickers: return pd.DataFrame()
    data = yf.download(tickers, period="1y", interval="1d", group_by='ticker', progress=False)
    return data

# --- UI LAYOUT ---
st.title("📈 Global Multi-Asset Portfolio Dashboard")
tabs = st.tabs(["Summary & Analytics", "India Stocks", "India Mutual Funds", "International Stocks"])

# Persistent State for Data
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {
        'in_stocks': pd.DataFrame(columns=['Ticker', 'Qty', 'Avg Price']),
        'in_mf': pd.DataFrame(columns=['Scheme Code', 'Units', 'Avg NAV']),
        'global_stocks': pd.DataFrame(columns=['Ticker', 'Qty', 'Avg Price', 'Currency'])
    }

# --- SECTION 1: India Stocks ---
with tabs[1]:
    st.subheader("🇮🇳 Indian Equity Holdings")
    uploaded_file = st.file_uploader("Upload Indian Stocks CSV (Ticker, Qty, Avg Price)", key="in_stocks_up")
    if uploaded_file:
        st.session_state.portfolio['in_stocks'] = pd.read_csv(uploaded_file)
    
    df_in = st.session_state.portfolio['in_stocks']
    if not df_in.empty:
        # Add .NS for Yahoo Finance if not present
        tickers = [t if t.endswith(('.NS', '.BO')) else f"{t}.NS" for t in df_in['Ticker']]
        prices = yf.download(tickers, period="1d")['Close'].iloc[-1]
        df_in['Current Price'] = df_in['Ticker'].apply(lambda x: prices[x+".NS"] if x+".NS" in prices else 0)
        df_in['Total Value'] = df_in['Qty'] * df_in['Current Price']
        df_in['Gain/Loss %'] = ((df_in['Current Price'] - df_in['Avg Price']) / df_in['Avg Price']) * 100
        st.dataframe(df_in.style.format(precision=2))

# --- SECTION 2: India Mutual Funds ---
with tabs[2]:
    st.subheader("🏦 Indian Mutual Funds")
    uploaded_mf = st.file_uploader("Upload MF CSV (Scheme Code, Units, Avg NAV)", key="mf_up")
    if uploaded_mf:
        st.session_state.portfolio['in_mf'] = pd.read_csv(uploaded_mf)
    
    df_mf = st.session_state.portfolio['in_mf']
    if not df_mf.empty:
        # Fetch latest NAVs via mftool
        navs = []
        for code in df_mf['Scheme Code']:
            try:
                d = mf.get_scheme_quote(str(code))
                navs.append(float(d['nav']))
            except: navs.append(0)
        df_mf['Current NAV'] = navs
        df_mf['Total Value'] = df_mf['Units'] * df_mf['Current NAV']
        df_mf['Gain/Loss %'] = ((df_mf['Current NAV'] - df_mf['Avg NAV']) / df_mf['Avg NAV']) * 100
        st.dataframe(df_mf.style.format(precision=2))

# --- SECTION 3: International Stocks ---
with tabs[3]:
    st.subheader("🌎 International Equity (US, UK, Europe)")
    uploaded_global = st.file_uploader("Upload Global Stocks CSV (Ticker, Qty, Avg Price, Currency)", key="global_up")
    if uploaded_global:
        st.session_state.portfolio['global_stocks'] = pd.read_csv(uploaded_global)
    
    df_gl = st.session_state.portfolio['global_stocks']
    if not df_gl.empty:
        gl_tickers = df_gl['Ticker'].tolist()
        gl_prices = yf.download(gl_tickers, period="1d")['Close'].iloc[-1]
        df_gl['Current Price'] = df_gl['Ticker'].apply(lambda x: gl_prices[x] if x in gl_prices else 0)
        df_gl['Total Value (Local)'] = df_gl['Qty'] * df_gl['Current Price']
        st.dataframe(df_gl.style.format(precision=2))

# --- SUMMARY TAB & ANALYTICS ---
with tabs[0]:
    fx = get_fx_rates()
    
    # Calculate Total Portfolio Value in INR
    val_in_stocks = df_in['Total Value'].sum() if not df_in.empty else 0
    val_in_mf = df_mf['Total Value'].sum() if not df_mf.empty else 0
    
    val_global = 0
    if not df_gl.empty:
        df_gl['Total Value (INR)'] = df_gl.apply(lambda x: x['Total Value (Local)'] * fx.get(x['Currency'], 1), axis=1)
        val_global = df_gl['Total Value (INR)'].sum()
    
    total_portfolio = val_in_stocks + val_in_mf + val_global
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Portfolio (INR)", f"₹{total_portfolio:,.2f}")
    col2.metric("India Exposure", f"{( (val_in_stocks + val_in_mf)/total_portfolio * 100 if total_portfolio > 0 else 0):.1f}%")
    col3.metric("Global Exposure", f"{(val_global/total_portfolio * 100 if total_portfolio > 0 else 0):.1f}%")

    # Visuals
    st.divider()
    c1, c2 = st.columns(2)
    
    with c1:
        st.write("### Asset Allocation")
        fig = px.pie(values=[val_in_stocks, val_in_mf, val_global], 
                     names=['India Stocks', 'India MF', 'Global Stocks'],
                     hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig, use_container_width=True)
    
    with c2:
        st.write("### Portfolio vs Benchmarks (1Y)")
        # This is a simplified comparison logic
        benchmarks = yf.download(['^NSEI', '^GSPC'], period="1y")['Close']
        benchmarks = benchmarks / benchmarks.iloc[0] # Normalize
        st.line_chart(benchmarks)

st.sidebar.info("Tip: For UK stocks, use .L (e.g., TSCO.L). For Germany, use .DE (e.g., SAP.DE).")
