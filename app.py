import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- INITIAL SETUP ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

def load_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {
            'symbol':['symbol','ticker'], 
            'qty':['qty','quantity'], 
            'avg_price':['price','avg','cost'], 
            'sector':['sector','industry']
        }
        inv_map = {col: target for target, aliases in mapping.items() for col in df.columns if any(a in col for a in aliases)}
        df = df.rename(columns=inv_map)
        
        if 'sector' not in df.columns: df['sector'] = 'General'
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
            df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce')
            return df.dropna(subset=['symbol'])
    except: return pd.DataFrame()
    return pd.DataFrame()

# --- THE AGGRESSIVE DISPATCHER ---
def get_market_label(symbol):
    s = str(symbol).upper()
    # 1. LONDON (Must be .L)
    if s.endswith('.L'):
        return "London", "£", "GBP"
    # 2. EUROPE (Must be Paris, Germany, Amsterdam, etc.)
    if any(s.endswith(ext) for ext in ['.PA', '.DE', '.AS', '.MI', '.MC', '.LS']):
        return "Europe", "€", "EUR"
    # 3. INDIA
    if s.endswith('.NS') or s.endswith('.BO'):
        return "India", "₹", "INR"
    # 4. DEFAULT US
    return "US", "$", "USD"

# --- UI ---
st.title("🌍 Global Multi-Market Tracker")

if st.sidebar.button("Force Global Refresh"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    # Assign labels
    details = df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    df[['market', 'curr_sym', 'curr_code']] = details

    # TABS
    t_sum, t_in, t_us, t_lon, t_eu, t_set = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])

    regional_data = {}

    def render_market(market_name, tab_obj):
        subset = df[df['market'] == market_name].copy()
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings currently listed for {market_name}.")
                return None
            
            tickers = subset['symbol'].tolist()
            fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
            
            with st.status(f"Updating {market_name} Prices...", expanded=False):
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
            subset['day_gain'] = (subset['ltp'] - subset['prev']) * subset['qty']

            # METRICS (With safety check for currency symbol)
            cur = subset['curr_sym'].iloc[0] if not subset.empty else ""
            m1, m2, m3 = st.columns(3)
            m1.metric("Invested", f"{cur}{subset['invested'].sum():,.2f}")
            m2.metric("Market Value", f"{cur}{subset['mkt_val'].sum():,.2f}")
            m3.metric("Today's Gain", f"{cur}{subset['day_gain'].sum():,.2f}")

            # TABLE
            disp = subset[['symbol', 'sector', 'qty', 'avg_price', 'ltp', 'mkt_val']].reset_index(drop=True)
            disp.index += 1
            st.dataframe(disp.style.format({
                'avg_price':"{:.2f}", 'ltp':"{:.2f}", 'mkt_val':"{:,.2f}"
            }), use_container_width=True)
            return subset

    # Processing Regional Tabs
    regional_data["India"] = render_market("India", t_in)
    regional_data["US"] = render_market("US", t_us)
    regional_data["London"] = render_market("London", t_lon)
    regional_data["Europe"] = render_market("Europe", t_eu)

    # --- SUMMARY TAB: THE FIX FOR GBP CONVERSION ---
    with t_sum:
        st.header("Global Summary (Converted to GBP)")
        
        # Fetch Live Rates
        with st.spinner("Fetching live FX rates..."):
            rates_df = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
            rates = {
                "USD": rates_df["GBPUSD=X"].iloc[-1], 
                "INR": rates_df["GBPINR=X"].iloc[-1], 
                "EUR": rates_df["GBPEUR=X"].iloc[-1], 
                "GBP": 1.0
            }

        summary_rows = []
        all_for_sector = []
        
        for m_name, m_df in regional_data.items():
            if m_df is not None and not m_df.empty:
                code = m_df['curr_code'].iloc[0]
                inv_gbp = m_df['invested'].sum() / rates[code]
                mkt_gbp = m_df['mkt_val'].sum() / rates[code]
                
                summary_rows.append({
                    "Market": m_name,
                    "Invested (£)": inv_gbp,
                    "Market Value (£)": mkt_gbp,
                    "Total Gain (£)": mkt_gbp - inv_gbp
                })
                # Add a converted value for sector analysis
                m_df['mkt_val_gbp'] = m_df['mkt_val'] / rates[code]
                all_for_sector.append(m_df)

        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_portfolio_gbp = sum_df['Market Value (£)'].sum()
            sum_df['Allocation %'] = (sum_df['Market Value (£)'] / total_portfolio_gbp) * 100
            
            # Global Metrics Row
            g1, g2, g3 = st.columns(3)
            g1.metric("Total Global Value", f"£{total_portfolio_gbp:,.2f}")
            g2.metric("Total Global Invested", f"£{sum_df['Invested (£)'].sum():,.2f}")
            g3.metric("Overall Return %", f"{((total_portfolio_gbp - sum_df['Invested (£)'].sum()) / sum_df['Invested (£)'].sum() * 100):.2f}%")

            st.divider()
            
            # FINAL SUMMARY TABLE
            st.subheader("Regional Allocation Breakdown")
            st.dataframe(sum_df.style.format({
                'Invested (£)': "£{:,.2f}", 
                'Market Value (£)': "£{:,.2f}",
