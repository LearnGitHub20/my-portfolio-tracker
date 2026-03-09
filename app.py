import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import numpy as np
import os

# --- CONFIG ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

# --- 1. DATA LOADING & CLEANING ---
def load_and_clean_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        if df.empty: return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
        
        df.columns = [str(c).strip().lower() for c in df.columns]
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
        
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            df['qty'] = pd.to_numeric(df['qty'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            df['avg_price'] = pd.to_numeric(df['avg_price'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            return df[['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
    except Exception as e:
        st.error(f"Load Error: {e}")
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

# --- 2. CATEGORIZATION LOGIC ---
def categorize_stock(symbol):
    sym = str(symbol).upper()
    if any(sym.endswith(s) for s in ['.L', '.DE', '.PA', '.AS', '.MI', '.MC']): return "European"
    elif sym.endswith('.NS') or sym.endswith('.BO'): return "Indian"
    elif "." not in sym or sym.endswith('.US'): return "US"
    return "Others"

# --- 3. UI HEADER & REFRESH ---
st.title("🌍 Global Multi-Market Tracker")

# Global Refresh Button
if st.button("🔄 Refresh All Market Prices"):
    st.cache_data.clear()
    st.rerun()

# --- 4. PROCESSING ---
portfolio = load_and_clean_data()

if not portfolio.empty:
    master_df = portfolio.copy()
    master_df['region'] = master_df['symbol'].apply(categorize_stock)

    # Tabs
    sum_tab, in_tab, us_tab, eu_tab, set_tab = st.tabs(["📈 Summary", "🇮🇳 Indian", "🇺🇸 US", "🇪🇺 European", "⚙️ Settings"])

    # Region Helper
    def render_region(df_subset, region_name, currency_symbol):
        if df_subset.empty:
            st.info(f"No holdings found for {region_name}.")
            return 0, 0, 0 # Return values for summary
            
        tickers = df_subset['symbol'].unique().tolist()
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

        df_subset['invested'] = df_subset['qty'] * df_subset['avg_price']
        df_subset['mkt_val'] = df_subset['qty'] * df_subset['ltp']
        df_subset['day_chg'] = (df_subset['ltp'] - df_subset['prev']) / df_subset['prev'] * 100
        
        # Display Table with Serial Number starting from 1
        df_display = df_subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'day_chg']].reset_index(drop=True)
        df_display.index += 1
        
        st.subheader(f"{region_name} Holdings")
        st.dataframe(df_display.style.format({
            'avg_price': f"{currency_symbol}{{:.2f}}",
            'ltp': f"{currency_symbol}{{:.2f}}",
            'mkt_val': f"{currency_symbol}{{:.2f}}",
            'day_chg': "{:.2f}%"
        }), use_container_width=True)
        
        return df_subset['invested'].sum(), df_subset['mkt_val'].sum(), region_name

    # Render Regional Tabs and Capture Data for Summary
    with in_tab: in_stats = render_region(master_df[master_df['region'] == "Indian"], "Indian", "₹")
    with us_tab: us_stats = render_region(master_df[master_df['region'] == "US"], "US", "$")
    with eu_tab: eu_stats = render_region(master_df[master_df['region'] == "European"], "European", "€")

    # --- 5. SUMMARY TAB ---
    with sum_tab:
        st.header("Global Portfolio Summary")
        
        # Prepare Summary DataFrame (Note: This is nominal value; does not handle FX conversion)
        summary_data = []
        for stats in [in_stats, us_stats, eu_stats]:
            if stats: # Check if region had data
                summary_data.append({
                    "Region": stats[2],
                    "Invested": stats[0],
                    "Market Value": stats[1],
                    "Return %": ((stats[1]-stats[0])/stats[0]*100) if stats[0]>0 else 0
                })
        
        sum_df = pd.DataFrame(summary_data)
        
        if not sum_df.empty:
            # Metrics Row
            cols = st.columns(len(sum_df))
            for i, row in sum_df.iterrows():
                cols[i].metric(f"{row['Region']} Value", f"{row['Market Value']:,.2f}", f"{row['Return %']:.2f}%")
            
            st.divider()
            
            # Allocation Chart
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("Regional Allocation (%)")
                fig = px.pie(sum_df, values='Market Value', names='Region', hole=0.5, 
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                st.subheader("Portfolio Breakdown")
                st.table(sum_df.style.format({
                    'Invested': "{:,.2f}", 
                    'Market Value': "{:,.2f}", 
                    'Return %': "{:.2f}%"
                }))
        else:
            st.info("No data available for summary.")

    with set_tab:
        st.header("Settings")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            df.to_csv(DB_FILE, index=False)
            st.success("File uploaded to system. Refreshing...")
            st.rerun()

else:
    st.info("No data found. Please go to the 'Settings' tab to upload your `portfolio_db.csv`.")
