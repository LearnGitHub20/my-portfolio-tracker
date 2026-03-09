import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- CONFIG ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Universal Wealth Tracker", page_icon="🌍")

# --- 1. ROBUST DATA LOADER ---
def load_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Mapping headers
        mapping = {
            'symbol': ['symbol', 'ticker'],
            'qty': ['qty', 'quantity', 'units'],
            'avg_price': ['price', 'avg', 'cost'],
            'sector': ['sector', 'industry']
        }
        
        final_cols = {}
        for target, aliases in mapping.items():
            for col in df.columns:
                if any(alias in col for alias in aliases):
                    final_cols[col] = target
                    break
        
        df = df.rename(columns=final_cols)
        
        # Ensure Sector column exists
        if 'sector' not in df.columns:
            df['sector'] = 'Other'
            
        # Clean data types
        df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
        df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce')
        
        return df[['symbol', 'qty', 'avg_price', 'sector']].dropna(subset=['symbol'])
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

# --- 2. THE MARKET DISPATCHER (THE FIX) ---
def get_market_details(symbol):
    s = str(symbol).upper()
    # 1. LONDON CHECK (Highest Priority)
    if s.endswith('.L'):
        return "London", "£", "GBP"
    # 2. INDIA CHECK
    if s.endswith('.NS') or s.endswith('.BO'):
        return "India", "₹", "INR"
    # 3. EUROPE CHECK (Rest of Europe)
    if any(s.endswith(ext) for ext in ['.PA', '.DE', '.AS', '.MI', '.MC', '.LS']):
        return "Europe", "€", "EUR"
    # 4. DEFAULT TO US
    return "US", "$", "USD"

# --- 3. MAIN APP ---
st.title("🌍 Global Multi-Market Tracker")

# Refresh Button at the very top
if st.button("🔄 Refresh All Prices & Exchange Rates"):
    st.cache_data.clear()
    st.rerun()

raw_df = load_data()

if not raw_df.empty:
    # Apply Market Grouping
    market_data = raw_df['symbol'].apply(lambda x: pd.Series(get_market_details(x)))
    raw_df[['market_group', 'curr_sym', 'curr_code']] = market_data

    # Create Tabs
    tabs = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])
    
    # Storage for Summary
    regional_dfs = {}

    # --- 4. REGIONAL TAB LOGIC ---
    def render_tab(df_full, market_key, tab_obj):
        subset = df_full[df_full['market_group'] == market_key].copy()
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings found for {market_key}.")
                return None
            
            # Fetch Prices
            tickers = subset['symbol'].tolist()
            # Handle India Suffix if missing
            fetch_list = [t if ('.' in t or market_key != "India") else f"{t}.NS" for t in tickers]
            
            with st.status(f"Fetching {market_key} Prices...", expanded=False):
                data = yf.download(fetch_list, period="2d", progress=False)['Close']
                def get_p(sym):
                    try:
                        t = sym if ('.' in sym or market_key != "India") else f"{sym}.NS"
                        v = data[t] if len(fetch_list) > 1 else data
                        return v.iloc[-1], v.iloc[-2]
                    except: return 0.0, 0.0
                
                prices = subset['symbol'].apply(lambda x: pd.Series(get_p(x)))
                subset['ltp'], subset['prev'] = prices[0], prices[1]

            subset['invested'] = subset['qty'] * subset['avg_price']
            subset['mkt_val'] = subset['qty'] * subset['ltp']
            subset['day_gain'] = (subset['ltp'] - subset['prev']) * subset['qty']
            
            # Tab Header
            sym = subset['curr_sym'].iloc[0]
            m1, m2, m3 = st.columns(3)
            m1.metric(f"Total Invested ({market_key})", f"{sym}{subset['invested'].sum():,.2f}")
            m2.metric("Market Value", f"{sym}{subset['mkt_val'].sum():,.2f}")
            m3.metric("Today's Gain", f"{sym}{subset['day_gain'].sum():,.2f}")
            
            st.divider()
            
            # Regional Table with Serial Number
            disp = subset[['symbol', 'sector', 'qty', 'avg_price', 'ltp', 'mkt_val']].reset_index(drop=True)
            disp.index += 1
            st.dataframe(disp.style.format({'avg_price': f"{sym}{{:.2f}}", 'ltp': f"{sym}{{:.2f}}", 'mkt_val': f"{sym}{{:.2f}}"}), use_container_width=True)
            return subset

    # Render each tab (Except Summary and Settings)
    regional_dfs["India"] = render_tab(raw_df, "India", tabs[1])
    regional_dfs["US"] = render_tab(raw_df, "US", tabs[2])
    regional_dfs["London"] = render_tab(raw_df, "London", tabs[3])
    regional_dfs["Europe"] = render_tab(raw_df, "Europe", tabs[4])

    # --- 5. SUMMARY TAB (WITH GBP CONVERSION) ---
    with tabs[0]:
        st.header("Global Portfolio Summary (Converted to GBP)")
        
        # Live FX Conversion
        fx = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
        rates = {"USD": fx["GBPUSD=X"].iloc[-1], "INR": fx["GBPINR=X"].iloc[-1], "EUR": fx["GBPEUR=X"].iloc[-1], "GBP": 1.0}
        
        sum_rows = []
        full_portfolio_gbp = []
        
        for name, df_reg in regional_dfs.items():
            if df_reg is not None and not df_reg.empty:
                # Get the code for the first stock in this group
                code = df_reg['curr_code'].iloc[0]
                
                inv_local = df_reg['invested'].sum()
                mkt_local = df_reg['mkt_val'].sum()
                
                # Convert to GBP
                inv_gbp = inv_local / rates[code]
                mkt_gbp = mkt_local / rates[code]
                
                sum_rows.append({
                    "Market": name,
                    "Invested (Local)": inv_local,
                    "Mkt Value (Local)": mkt_local,
                    "Invested (£)": inv_gbp,
                    "Mkt Value (£)": mkt_gbp,
                    "Total Return %": ((mkt_gbp - inv_gbp) / inv_gbp * 100) if inv_gbp > 0 else 0
                })
                
                # Prepare for Sector Chart
                df_reg['mkt_val_gbp'] = df_reg['mkt_val'] / rates[code]
                full_portfolio_gbp.append(df_reg)

        if sum_rows:
            sum_df = pd.DataFrame(sum_rows)
            total_gbp = sum_df['Mkt Value (£)'].sum()
            sum_df['Allocation %'] = (sum_df['Mkt Value (£)'] / total_gbp) * 100
            
            # Global Metrics
            g1, g2, g3 = st.columns(3)
            g1.metric("Total Global Value", f"£{total_gbp:,.2f}")
            g2.metric("Total Global Invested", f"£{sum_df['Invested (£)'].sum():,.2f}")
            g3.metric("Global Net Return", f"{((total_gbp - sum_df['Invested (£)'].sum()) / sum_df['Invested (£)'].sum() * 100):.2f}%")
            
            st.divider()
            
            # Final Summary Table
            st.subheader("Regional Allocation and GBP Conversion")
            st.dataframe(sum_df.style.format({
                'Invested (Local)': "{:,.2f}", 'Mkt Value (Local)': "{:,.2f}",
                'Invested (£)': "£{:,.2f}", 'Mkt Value (£)': "£{:,.2f}",
                'Total Return %': "{:.2f}%", 'Allocation %': "{:.2f}%"
            }), use_container_width=True)

            # Sector Diversification Chart
            all_data = pd.concat(full_portfolio_gbp)
            sector_data = all_data.groupby('sector')['mkt_val_gbp'].sum().reset_index()
            fig = px.bar(sector_data.sort_values('mkt_val_gbp', ascending=False), 
                         x='sector', y='mkt_val_gbp', title="Global Sector Exposure (£)", 
                         labels={'mkt_val_gbp': 'Value in GBP'}, color='sector')
            st.plotly_chart(fig, use_container_width=True)

    # --- 6. SETTINGS ---
    with tabs[5]:
        st.header("Data Settings")
        st.info("Ensure CSV has columns: Symbol, Qty, Price, Sector")
        uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
        if uploaded:
            with open(DB_FILE, "wb") as f:
                f.write(uploaded.getbuffer())
            st.success("File uploaded! Click 'Refresh' at the top.")

else:
    st.info("No data found. Please upload your CSV in the Settings tab.")
