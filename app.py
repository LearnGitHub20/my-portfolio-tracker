import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- CONFIG ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

# --- 1. DATA LOADING & SECTOR MAPPING ---
def load_and_clean_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(columns=['symbol', 'qty', 'avg_price', 'sector'])
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Expanded patterns to include 'sector'
        patterns = {
            'symbol': ['symbol', 'ticker'], 
            'qty': ['qty', 'quantity'], 
            'avg_price': ['price', 'avg', 'cost'],
            'sector': ['sector', 'industry', 'category']
        }
        
        col_map = {actual: target for target, aliases in patterns.items() 
                   for actual in df.columns if any(alias in actual for alias in aliases)}
        df = df.rename(columns=col_map)
        
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            df['qty'] = pd.to_numeric(df['qty'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            df['avg_price'] = pd.to_numeric(df['avg_price'].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
            
            # Fill empty sectors with 'Unknown' if column exists, else create it
            if 'sector' not in df.columns:
                df['sector'] = 'General'
            df['sector'] = df['sector'].fillna('General').astype(str)
            
            return df[['symbol', 'qty', 'avg_price', 'sector']].dropna(subset=['symbol'])
    except: pass
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price', 'sector'])

# --- 2. THE PRIORITY MARKET SELECTOR ---
def get_market_info(symbol):
    sym = str(symbol).upper()
    
    # PRIORITY 1: LONDON (Must be .L)
    if sym.endswith('.L'): 
        return "London", "£", "GBP"
    
    # PRIORITY 2: INDIA
    if sym.endswith('.NS') or sym.endswith('.BO'): 
        return "India", "₹", "INR"
    
    # PRIORITY 3: EUROPE (Excluding .L)
    if any(sym.endswith(s) for s in ['.DE', '.PA', '.AS', '.MI', '.MC', '.LS', '.MA']): 
        return "Europe", "€", "EUR"
    
    # PRIORITY 4: US (Default)
    return "US", "$", "USD"

# --- 3. UI DASHBOARD ---
st.title("🌍 Global Multi-Market Tracker")

if st.button("🔄 Full Market Refresh"):
    st.cache_data.clear()
    st.rerun()

portfolio = load_and_clean_data()

if not portfolio.empty:
    master_df = portfolio.copy()
    m_info = master_df['symbol'].apply(lambda x: pd.Series(get_market_info(x)))
    master_df[['market_group', 'curr_sym', 'curr_code']] = m_info

    # 5 Main Tabs + Settings
    sum_tab, in_tab, us_tab, lon_tab, eu_tab, set_tab = st.tabs([
        "📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"
    ])

    def render_market_tab(df_subset, market_key):
        # We filter the master data specifically by the hard-coded market_group
        filtered_df = df_subset[df_subset['market_group'] == market_key].copy()
        
        if filtered_df.empty:
            st.info(f"No holdings found for {market_key}.")
            return None
        
        tickers = filtered_df['symbol'].unique().tolist()
        fetch_tickers = [t if ('.' in t or market_key != "India") else f"{t}.NS" for t in tickers]
        
        with st.status(f"Fetching {market_key} Prices..."):
            data = yf.download(fetch_tickers, period="2d", progress=False)['Close']
            def get_price(sym):
                try:
                    t = sym if ('.' in sym or market_key != "India") else f"{sym}.NS"
                    val = data[t] if len(fetch_tickers) > 1 else data
                    return val.iloc[-1], val.iloc[-2]
                except: return 0.0, 0.0
            
            prices = filtered_df['symbol'].apply(lambda x: pd.Series(get_price(x)))
            filtered_df['ltp'], filtered_df['prev'] = prices[0], prices[1]

        filtered_df['invested'] = filtered_df['qty'] * filtered_df['avg_price']
        filtered_df['mkt_val'] = filtered_df['qty'] * filtered_df['ltp']
        filtered_df['day_gain'] = (filtered_df['ltp'] - filtered_df['prev']) * filtered_df['qty']

        # Header Metrics
        curr = filtered_df['curr_sym'].iloc[0]
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{market_key} Invested", f"{curr}{filtered_df['invested'].sum():,.2f}")
        m2.metric("Market Value", f"{curr}{filtered_df['mkt_val'].sum():,.2f}")
        m3.metric("Today's Gain", f"{curr}{filtered_df['day_gain'].sum():,.2f}")

        st.divider()

        # Display Table (Including Sector)
        df_disp = filtered_df[['symbol', 'sector', 'qty', 'avg_price', 'ltp', 'mkt_val']].reset_index(drop=True)
        df_disp.index += 1
        st.dataframe(df_disp.style.format({
            'avg_price': f"{curr}{{:.2f}}", 'ltp': f"{curr}{{:.2f}}", 'mkt_val': f"{curr}{{:.2f}}"
        }), use_container_width=True)
        return filtered_df

    # Render Regional Tabs specifically using the market_group keys
    with in_tab: in_df = render_market_tab(master_df, "India")
    with us_tab: us_df = render_market_tab(master_df, "US")
    with lon_tab: lon_df = render_market_tab(master_df, "London")
    with eu_tab: eu_df = render_market_tab(master_df, "Europe")

    # --- 4. SUMMARY & SECTOR ANALYSIS ---
    with sum_tab:
        with st.spinner("Calculating Global GBP Totals..."):
            fx = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
            rates = {"USD": fx["GBPUSD=X"].iloc[-1], "INR": fx["GBPINR=X"].iloc[-1], "EUR": fx["GBPEUR=X"].iloc[-1], "GBP": 1.0}
            
            summary_list = []
            combined_all = []
            for df_reg, name in [(in_df, "India"), (us_df, "USA"), (lon_df, "London"), (eu_df, "Europe")]:
                if df_reg is not None and not df_reg.empty:
                    combined_all.append(df_reg)
                    inv_gbp = df_reg['invested'].sum() / rates[df_reg['curr_code'].iloc[0]]
                    mkt_gbp = df_reg['mkt_val'].sum() / rates[df_reg['curr_code'].iloc[0]]
                    summary_list.append({
                        "Market": name,
                        "Invested (£)": inv_gbp,
                        "Market Value (£)": mkt_gbp,
                        "Return %": ((mkt_gbp - inv_gbp) / inv_gbp * 100) if inv_gbp > 0 else 0
                    })

            if summary_list:
                sum_df = pd.DataFrame(summary_list)
                total_mkt_gbp = sum_df['Market Value (£)'].sum()
                sum_df['Portfolio %'] = (sum_df['Market Value (£)'] / total_mkt_gbp) * 100

                st.subheader("Global Breakdown (£)")
                st.table(sum_df.style.format({
                    'Invested (£)': "£{:,.2f}", 'Market Value (£)': "£{:,.2f}", 
                    'Return %': "{:.2f}%", 'Portfolio %': "{:.2f}%"
                }))

                # SECTOR BREAKDOWN
                st.divider()
                st.subheader("Sector Allocation (Global)")
                full_portfolio = pd.concat(combined_all)
                # Normalize values to GBP for the sector chart
                full_portfolio['val_gbp'] = full_portfolio.apply(lambda x: x['mkt_val'] / rates[x['curr_code']], axis=1)
                
                sector_df = full_portfolio.groupby('sector')['val_gbp'].sum().reset_index()
