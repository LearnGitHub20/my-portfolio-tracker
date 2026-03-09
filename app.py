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

# --- 2. CATEGORIZATION & CURRENCY LOGIC ---
def get_region_info(symbol):
    sym = str(symbol).upper()
    if sym.endswith('.L'): return "European", "£", "GBP"
    if any(sym.endswith(s) for s in ['.DE', '.PA', '.AS', '.MI', '.MC']): return "European", "€", "EUR"
    if sym.endswith('.NS') or sym.endswith('.BO'): return "Indian", "₹", "INR"
    if "." not in sym or sym.endswith('.US'): return "US", "$", "USD"
    return "Others", "$", "USD"

# --- 3. UI HEADER & REFRESH ---
st.title("🌍 Global Multi-Market Tracker")

if st.button("🔄 Refresh All Market Prices"):
    st.cache_data.clear()
    st.rerun()

# --- 4. PROCESSING ---
portfolio = load_and_clean_data()

if not portfolio.empty:
    master_df = portfolio.copy()
    # Apply region and currency mapping
    region_info = master_df['symbol'].apply(lambda x: pd.Series(get_region_info(x)))
    master_df['region'], master_df['currency_sym'], master_df['currency_code'] = region_info[0], region_info[1], region_info[2]

    sum_tab, in_tab, us_tab, eu_tab, set_tab = st.tabs(["📈 Summary", "🇮🇳 Indian", "🇺🇸 US", "🇪🇺 European", "⚙️ Settings"])

    # Region Helper
    def render_region(df_subset, region_name):
        if df_subset.empty:
            st.info(f"No holdings found for {region_name}.")
            return None
            
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
        df_subset['day_gain_val'] = (df_subset['ltp'] - df_subset['prev']) * df_subset['qty']
        df_subset['total_gain_val'] = df_subset['mkt_val'] - df_subset['invested']
        df_subset['day_chg_pct'] = ((df_subset['ltp'] - df_subset['prev']) / df_subset['prev'] * 100).fillna(0)
        df_subset['total_chg_pct'] = (df_subset['total_gain_val'] / df_subset['invested'] * 100).fillna(0)

        # Regional Top Summary Metrics
        m1, m2, m3, m4 = st.columns(4)
        # Use primary currency of the region for the header
        prim_sym = df_subset['currency_sym'].iloc[0] 
        m1.metric("Invested", f"{prim_sym}{df_subset['invested'].sum():,.2f}")
        m2.metric("Today Value", f"{prim_sym}{df_subset['mkt_val'].sum():,.2f}")
        m3.metric("Total Gains", f"{prim_sym}{df_subset['total_gain_val'].sum():,.2f}", f"{df_subset['total_chg_pct'].mean():.2f}%")
        m4.metric("Today Gain/Loss", f"{prim_sym}{df_subset['day_gain_val'].sum():,.2f}", f"{df_subset['day_chg_pct'].mean():.2f}%")

        st.divider()

        # Display Table with Serial Number
        df_display = df_subset.reset_index(drop=True)
        df_display.index += 1
        
        # Formatting helper to handle mixed currencies in the same tab (e.g. London £ vs Paris €)
        def format_row(row, col):
            return f"{row['currency_sym']}{row[col]:,.2f}"

        # We display the dataframe with custom formatting per row
        st.dataframe(df_display[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'day_chg_pct']].style.format({
            'day_chg_pct': "{:.2f}%"
        }), use_container_width=True)
        
        return df_subset

    # Render Regional Tabs
    with in_tab: in_df = render_region(master_df[master_df['region'] == "Indian"], "Indian")
    with us_tab: us_df = render_region(master_df[master_df['region'] == "US"], "US")
    with eu_tab: eu_df = render_region(master_df[master_df['region'] == "European"], "European")

    # --- 5. SUMMARY TAB ---
    with sum_tab:
        st.header("Global Portfolio Summary (Converted to GBP)")
        
        # Fetch Live Exchange Rates for GBP
        with st.spinner("Fetching Exchange Rates..."):
            fx = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
            # Rates are 1 GBP to X, so to get GBP we divide local / rate
            rates = {
                "USD": fx["GBPUSD=X"].iloc[-1],
                "INR": fx["GBPINR=X"].iloc[-1],
                "EUR": fx["GBPEUR=X"].iloc[-1],
                "GBP": 1.0
            }

        summary_rows = []
        for df_reg, name in [(in_df, "India"), (us_df, "USA"), (eu_df, "Europe")]:
            if df_reg is not None and not df_reg.empty:
                # Group by currency within region to handle FX correctly
                for curr, group in df_reg.groupby('currency_code'):
                    inv_gbp = group['invested'].sum() / rates[curr]
                    mkt_gbp = group['mkt_val'].sum() / rates[curr]
                    summary_rows.append({
                        "Region": f"{name} ({curr})",
                        "Invested (Local)": group['invested'].sum(),
                        "Mkt Value (Local)": group['mkt_val'].sum(),
                        "Invested (£)": inv_gbp,
                        "Mkt Value (£)": mkt_gbp,
                        "Return %": ((mkt_gbp - inv_gbp) / inv_gbp * 100) if inv_gbp > 0 else 0
                    })

        sum_df = pd.DataFrame(summary_rows)
        if not sum_df.empty:
            total_gbp_inv = sum_df['Invested (£)'].sum()
            total_gbp_mkt = sum_df['Mkt Value (£)'].sum()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Invested (£)", f"£{total_gbp_inv:,.2f}")
            col2.metric("Total Market Value (£)", f"£{total_gbp_mkt:,.2f}")
            col3.metric("Overall Return", f"{((total_gbp_mkt-total_gbp_inv)/total_gbp_inv*100):.2f}%")

            st.divider()
            
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("Regional Breakdown (£)")
                fig = px.pie(sum_df, values='Mkt Value (£)', names='Region', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                st.subheader("Currency Adjusted Breakdown")
                st.table(sum_df.style.format({
                    'Invested (Local)': "{:,.2f}", 'Mkt Value (Local)': "{:,.2f}",
                    'Invested (£)': "£{:,.2f}", 'Mkt Value (£)': "£{:,.2f}", 'Return %': "{:.2f}%"
                }))
        else:
            st.info("No data available. Ensure your symbols have correct suffixes.")

    with set_tab:
        st.header("Settings")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            df.to_csv(DB_FILE, index=False)
            st.success("File updated. Please refresh.")
            st.rerun()

else:
    st.info("No data found. Please upload your CSV in Settings.")
