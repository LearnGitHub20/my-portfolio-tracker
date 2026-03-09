import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- INITIAL SETUP ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Portfolio Tracker")

def load_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        # Standardize Columns
        mapping = {'symbol':['symbol','ticker'], 'qty':['qty','quantity'], 'avg_price':['price','avg','cost'], 'sector':['sector','industry']}
        inv_map = {col: target for target, aliases in mapping.items() for col in df.columns if any(a in col for a in aliases)}
        df = df.rename(columns=inv_map)
        if 'sector' not in df.columns: df['sector'] = 'General'
        df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
        return df.dropna(subset=['symbol'])
    except: return pd.DataFrame()

# --- THE AGGRESSIVE DISPATCHER ---
def get_market_label(symbol):
    s = str(symbol).upper()
    if s.endswith('.L'):
        return "London", "£", "GBP"
    if any(s.endswith(ext) for ext in ['.PA', '.DE', '.AS', '.MI', '.MC']):
        return "Europe", "€", "EUR"
    if s.endswith('.NS') or s.endswith('.BO'):
        return "India", "₹", "INR"
    return "US", "$", "USD"

# --- UI ---
st.title("🌍 Global Multi-Market Tracker")

# Manual Override Refresh
if st.sidebar.button("Force Global Refresh"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    # Assign labels
    details = df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    df[['market', 'curr_sym', 'curr_code']] = details

    # TABS - Note: London and Europe are now distinct
    t_sum, t_in, t_us, t_lon, t_eu, t_set = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])

    regional_data = {}

    def render_market(market_name, tab_obj):
        subset = df[df['market'] == market_name].copy()
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings for {market_name}")
                return None
            
            # Fetch Prices
            tickers = subset['symbol'].tolist()
            fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
            
            with st.status(f"Updating {market_name}...", expanded=False):
                data = yf.download(fetch_list, period="2d", progress=False)['Close']
                def get_p(sym):
                    try:
                        t = sym if ('.' in sym or market_name != "India") else f"{sym}.NS"
                        v = data[t] if len(fetch_list) > 1 else data
                        return v.iloc[-1], v.iloc[-2]
                    except: return 0.0, 0.0
                
                prices = subset['symbol'].apply(lambda x: pd.Series(get_p(x)))
                subset['ltp'], subset['prev'] = prices[0], prices[1]

            subset['invested'] = subset['qty'] * subset['avg_price']
            subset['mkt_val'] = subset['qty'] * subset['ltp']
            
            # Metrics
            cur = subset['curr_sym'].iloc[0]
            m1, m2 = st.columns(2)
            m1.metric("Invested", f"{cur}{subset['invested'].sum():,.2f}")
            m2.metric("Market Value", f"{cur}{subset['mkt_val'].sum():,.2f}")

            # Table
            disp = subset[['symbol', 'sector', 'qty', 'avg_price', 'ltp', 'mkt_val']].reset_index(drop=True)
            disp.index += 1
            st.dataframe(disp.style.format({'avg_price':"{:.2f}", 'ltp':"{:.2f}", 'mkt_val':"{:,.2f}"}), use_container_width=True)
            return subset

    regional_data["India"] = render_market("India", t_in)
    regional_data["US"] = render_market("US", t_us)
    regional_data["London"] = render_market("London", t_lon)
    regional_data["Europe"] = render_market("Europe", t_eu)

    # --- SUMMARY TAB: GBP CONVERSION & ALLOCATION ---
    with t_sum:
        st.header("Global Summary (Converted to GBP)")
        
        # Live Rates
        rates_df = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
        rates = {"USD": rates_df["GBPUSD=X"].iloc[-1], "INR": rates_df["GBPINR=X"].iloc[-1], 
                 "EUR": rates_df["GBPEUR=X"].iloc[-1], "GBP": 1.0}

        summary_rows = []
        all_for_sector = []
        
        for m_name, m_df in regional_data.items():
            if m_df is not None:
                code = m_df['curr_code'].iloc[0]
                inv_gbp = m_df['invested'].sum() / rates[code]
                mkt_gbp = m_df['mkt_val'].sum() / rates[code]
                
                summary_rows.append({
                    "Market": m_name,
                    "Invested (£)": inv_gbp,
                    "Market Value (£)": mkt_gbp,
                    "Gain/Loss (£)": mkt_gbp - inv_gbp
                })
                m_df['mkt_val_gbp'] = m_df['mkt_val'] / rates[code]
                all_for_sector.append(m_df)

        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_portfolio = sum_df['Market Value (£)'].sum()
            sum_df['Allocation %'] = (sum_df['Market Value (£)'] / total_portfolio) * 100
            
            # THE REQUESTED SUMMARY TABLE
            st.subheader("Regional Allocation (GBP Converted)")
            st.dataframe(sum_df.style.format({
                'Invested (£)': "£{:,.2f}", 'Market Value (£)': "£{:,.2f}", 
                'Gain/Loss (£)': "£{:,.2f}", 'Allocation %': "{:.2f}%"
            }), use_container_width=True)

            # Global Sector Chart
            all_data = pd.concat(all_for_sector)
            sect_fig = px.bar(all_data.groupby('sector')['mkt_val_gbp'].sum().reset_index().sort_values('mkt_val_gbp'), 
                              x='sector', y='mkt_val_gbp', title="Global Sector exposure (£)", color='sector')
            st.plotly_chart(sect_fig, use_container_width=True)

    with t_set:
        uploaded = st.file_uploader("Upload CSV", type='csv')
        if uploaded:
            with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
            st.success("Uploaded. Reboot app or refresh.")
