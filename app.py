import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- CONFIG ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker")

# --- 1. DATA LOADING ---
def load_and_clean_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        patterns = {'symbol': ['symbol', 'ticker'], 'qty': ['qty', 'quantity'], 'avg_price': ['price', 'avg']}
        col_map = {actual: target for target, aliases in patterns.items() for actual in df.columns if any(alias in actual for alias in aliases)}
        df = df.rename(columns=col_map)
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            df['qty'] = pd.to_numeric(df['qty'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            df['avg_price'] = pd.to_numeric(df['avg_price'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            return df[['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
    except: pass
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

# --- 2. CURRENCY & REGION MAPPING ---
def get_region_info(symbol):
    sym = str(symbol).upper()
    if sym.endswith('.L'): return "European", "£", "GBP"
    if any(sym.endswith(s) for s in ['.DE', '.PA', '.AS', '.MI', '.MC']): return "European", "€", "EUR"
    if sym.endswith('.NS') or sym.endswith('.BO'): return "Indian", "₹", "INR"
    return "US", "$", "USD"

# --- 3. UI ---
st.title("🌍 Global Wealth Tracker")
if st.button("🔄 Refresh All"):
    st.cache_data.clear()
    st.rerun()

portfolio = load_and_clean_data()

if not portfolio.empty:
    master_df = portfolio.copy()
    region_info = master_df['symbol'].apply(lambda x: pd.Series(get_region_info(x)))
    master_df[['region', 'curr_sym', 'curr_code']] = region_info

    sum_tab, in_tab, us_tab, eu_tab, set_tab = st.tabs(["📈 Summary", "🇮🇳 India", "🇺🇸 US", "🇪🇺 Europe", "⚙️ Settings"])

    def render_region(df_subset, region_name):
        if df_subset.empty:
            st.info(f"No {region_name} stocks.")
            return None
        
        tickers = df_subset['symbol'].unique().tolist()
        fetch_tickers = [t if ('.' in t or region_name != "Indian") else f"{t}.NS" for t in tickers]
        
        with st.status(f"Updating {region_name}..."):
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
        df_subset['day_gain'] = (df_subset['ltp'] - df_subset['prev']) * df_subset['qty']
        
        # TAB SUMMARY
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Invested", f"{df_subset['curr_sym'].iloc[0]}{df_subset['invested'].sum():,.2f}")
        m2.metric("Market Value", f"{df_subset['curr_sym'].iloc[0]}{df_subset['mkt_val'].sum():,.2f}")
        m3.metric("Today Gain", f"{df_subset['curr_sym'].iloc[0]}{df_subset['day_gain'].sum():,.2f}")

        # TABLE
        df_disp = df_subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val']].reset_index(drop=True)
        df_disp.index += 1
        st.dataframe(df_disp, use_container_width=True)
        return df_subset

    with in_tab: in_df = render_region(master_df[master_df['region'] == "Indian"], "Indian")
    with us_tab: us_df = render_region(master_df[master_df['region'] == "US"], "US")
    with eu_tab: eu_df = render_region(master_df[master_df['region'] == "European"], "European")

    # --- SUMMARY LOGIC ---
    with sum_tab:
        fx = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
        rates = {"USD": fx["GBPUSD=X"].iloc[-1], "INR": fx["GBPINR=X"].iloc[-1], "EUR": fx["GBPEUR=X"].iloc[-1], "GBP": 1.0}
        
        summary_rows = []
        for df_reg, name in [(in_df, "India"), (us_df, "USA"), (eu_df, "Europe")]:
            if df_reg is not None:
                for curr, group in df_reg.groupby('curr_code'):
                    inv_gbp = group['invested'].sum() / rates[curr]
                    mkt_gbp = group['mkt_val'].sum() / rates[curr]
                    summary_rows.append({
                        "Region": f"{name} ({curr})",
                        "Invested (Local)": group['invested'].sum(),
                        "Mkt Value (Local)": group['mkt_val'].sum(),
                        "Invested (£)": inv_gbp,
                        "Mkt Value (£)": mkt_gbp
                    })
        
        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            st.subheader("Regional Breakdown (Converted to GBP)")
            st.dataframe(sum_df.style.format({'Invested (£)': "£{:,.2f}", 'Mkt Value (£)': "£{:,.2f}"}))
            
            fig = px.pie(sum_df, values='Mkt Value (£)', names='Region', title="Portfolio Allocation (£)")
            st.plotly_chart(fig)

    with set_tab:
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file:
            pd.read_csv(uploaded_file).to_csv(DB_FILE, index=False)
            st.rerun()
