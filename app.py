import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- CONFIG ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

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

# --- 2. REGION & CURRENCY DETECTION ---
def get_market_info(symbol):
    sym = str(symbol).upper()
    if sym.endswith('.L'): 
        return "London", "£", "GBP"
    if any(sym.endswith(s) for s in ['.DE', '.PA', '.AS', '.MI', '.MC']): 
        return "Europe", "€", "EUR"
    if sym.endswith('.NS') or sym.endswith('.BO'): 
        return "India", "₹", "INR"
    return "US", "$", "USD"

# --- 3. UI ---
st.title("🌍 Global Multi-Market Tracker")
if st.button("🔄 Refresh Market Data"):
    st.cache_data.clear()
    st.rerun()

portfolio = load_and_clean_data()

if not portfolio.empty:
    master_df = portfolio.copy()
    m_info = master_df['symbol'].apply(lambda x: pd.Series(get_market_info(x)))
    master_df[['region', 'curr_sym', 'curr_code']] = m_info

    # Updated Tabs to include London and Europe separately
    sum_tab, in_tab, us_tab, lon_tab, eu_tab, set_tab = st.tabs([
        "📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"
    ])

    def render_market_tab(df_subset, region_name):
        if df_subset.empty:
            st.info(f"No {region_name} holdings found.")
            return None
        
        tickers = df_subset['symbol'].unique().tolist()
        # Add .NS for Indian stocks if missing
        fetch_tickers = [t if ('.' in t or region_name != "India") else f"{t}.NS" for t in tickers]
        
        with st.status(f"Updating {region_name} Prices..."):
            data = yf.download(fetch_tickers, period="2d", progress=False)['Close']
            def get_price(sym):
                try:
                    t = sym if ('.' in sym or region_name != "India") else f"{sym}.NS"
                    val = data[t] if len(fetch_tickers) > 1 else data
                    return val.iloc[-1], val.iloc[-2]
                except: return 0.0, 0.0
            
            prices = df_subset['symbol'].apply(lambda x: pd.Series(get_price(x)))
            df_subset['ltp'], df_subset['prev'] = prices[0], prices[1]

        df_subset['invested'] = df_subset['qty'] * df_subset['avg_price']
        df_subset['mkt_val'] = df_subset['qty'] * df_subset['ltp']
        df_subset['gain_loss'] = df_subset['mkt_val'] - df_subset['invested']
        df_subset['day_gain'] = (df_subset['ltp'] - df_subset['prev']) * df_subset['qty']

        # Regional Header Metrics
        curr = df_subset['curr_sym'].iloc[0]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Invested", f"{curr}{df_subset['invested'].sum():,.2f}")
        m2.metric("Today Value", f"{curr}{df_subset['mkt_val'].sum():,.2f}")
        m3.metric("Total Gains", f"{curr}{df_subset['gain_loss'].sum():,.2f}")
        m4.metric("Today Gain/Loss", f"{curr}{df_subset['day_gain'].sum():,.2f}")

        st.divider()

        # Display Table
        df_disp = df_subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'day_gain']].reset_index(drop=True)
        df_disp.index += 1
        st.dataframe(df_disp.style.format({
            'avg_price': f"{curr}{{:.2f}}", 'ltp': f"{curr}{{:.2f}}", 
            'mkt_val': f"{curr}{{:.2f}}", 'day_gain': f"{curr}{{:.2f}}"
        }), use_container_width=True)
        return df_subset

    # Render Regional Tabs
    with in_tab: in_df = render_market_tab(master_df[master_df['region'] == "India"], "India")
    with us_tab: us_df = render_market_tab(master_df[master_df['region'] == "US"], "US")
    with lon_tab: lon_df = render_market_tab(master_df[master_df['region'] == "London"], "London")
    with eu_tab: eu_df = render_market_tab(master_df[master_df['region'] == "Europe"], "Europe")

    # --- 4. SUMMARY TAB (Converted to GBP) ---
    with sum_tab:
        with st.spinner("Calculating Global Totals..."):
            fx = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
            rates = {"USD": fx["GBPUSD=X"].iloc[-1], "INR": fx["GBPINR=X"].iloc[-1], "EUR": fx["GBPEUR=X"].iloc[-1], "GBP": 1.0}
            
            summary_list = []
            for df_reg, name in [(in_df, "India"), (us_df, "USA"), (lon_df, "London"), (eu_df, "Europe")]:
                if df_reg is not None and not df_reg.empty:
                    for curr_code, group in df_reg.groupby('curr_code'):
                        inv_gbp = group['invested'].sum() / rates[curr_code]
                        mkt_gbp = group['mkt_val'].sum() / rates[curr_code]
                        summary_list.append({
                            "Market": f"{name} ({curr_code})",
                            "Invested (Local)": group['invested'].sum(),
                            "Market Value (Local)": group['mkt_val'].sum(),
                            "Invested (£)": inv_gbp,
                            "Market Value (£)": mkt_gbp,
                            "Return %": ((mkt_gbp - inv_gbp) / inv_gbp * 100) if inv_gbp > 0 else 0
                        })

            if summary_list:
                sum_df = pd.DataFrame(summary_list)
                total_inv_gbp = sum_df['Invested (£)'].sum()
                total_mkt_gbp = sum_df['Market Value (£)'].sum()

                # Global Totals in GBP
                g1, g2, g3 = st.columns(3)
                g1.metric("Total Global Invested", f"£{total_inv_gbp:,.2f}")
                g2.metric("Total Global Value", f"£{total_mkt_gbp:,.2f}")
                g3.metric("Total Global Return", f"{((total_mkt_gbp-total_inv_gbp)/total_inv_gbp*100):.2f}%")

                st.divider()
                st.subheader("Regional Breakdown (£)")
                st.dataframe(sum_df.style.format({
                    'Invested (Local)': "{:,.2f}", 'Market Value (Local)': "{:,.2f}",
                    'Invested (£)': "£{:,.2f}", 'Market Value (£)': "£{:,.2f}", 'Return %': "{:.2f}%"
                }), use_container_width=True)

                c1, c2 = st.columns(2)
                with c1:
                    fig_pie = px.pie(sum_df, values='Market Value (£)', names='Market', hole=0.4, title="Asset Allocation by Market (£)")
                    st.plotly_chart(fig_pie, use_container_width=True)
                with c2:
                    fig_bar = px.bar(sum_df, x='Market', y='Return %', title="Market Performance (%)", color='Return %', color_continuous_scale='RdYlGn')
                    st.plotly_chart(fig_bar, use_container_width=True)

    with set_tab:
        st.header("Settings")
        uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
        if uploaded_file:
            pd.read_csv(uploaded_file).to_csv(DB_FILE, index=False)
            st.success("Portfolio updated! Click Refresh to see changes.")

else:
    st.info("No data found. Please upload your CSV in the Settings tab.")
