import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os
from datetime import datetime

# --- CONFIG ---
st.set_page_config(layout="wide", page_title="Wealth Tracker", page_icon="🌍")

# Global variables for files
DB_FILE = "portfolio_db.csv"
HIST_FILE = "history_db.csv"

# --- SIDEBAR & CURRENCY SETTINGS ---
st.sidebar.header("🌍 Settings")
display_curr = st.sidebar.selectbox("Display Currency", ["GBP", "USD", "INR", "EUR"])
curr_icons = {"GBP": "£", "USD": "$", "INR": "₹", "EUR": "€"}

# --- DATA LOADING ---
def load_and_map_csv():
    if not os.path.exists(DB_FILE):
        return None
    try:
        df = pd.read_csv(DB_FILE)
        df.columns = [str(c).strip().lower() for c in df.columns]
        # Mapping variants to standard names
        mapping = {
            'symbol': ['symbol', 'ticker', 'code'],
            'qty': ['qty', 'quantity', 'shares', 'units'],
            'avg_price': ['avg_price', 'price', 'cost', 'avg']
        }
        for target, aliases in mapping.items():
            for col in df.columns:
                if any(a in col for a in aliases):
                    df = df.rename(columns={col: target})
                    break
        return df[['symbol', 'qty', 'avg_price']]
    except:
        return None

def get_meta(symbol):
    s = str(symbol).upper()
    if s.endswith('.L'): return "London", "GBP"
    if any(s.endswith(e) for e in ['.PA', '.DE', '.AS', '.MI', '.MC']): return "Europe", "EUR"
    if s.endswith('.NS') or s.endswith('.BO'): return "India", "INR"
    return "US", "USD"

# --- CORE LOGIC ---
df = load_and_map_csv()

if df is not None:
    # Metadata
    df['symbol'] = df['symbol'].str.upper()
    meta = df['symbol'].apply(lambda x: pd.Series(get_meta(x)))
    df[['market', 'curr_code']] = meta

    # Tabs
    t_summary, t_india, t_us, t_uk, t_eu, t_settings = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 UK", "🇪🇺 EU", "⚙️ Settings"])

    all_data = []

    def render_region(name, tab):
        subset = df[df['market'] == name].copy()
        with tab:
            if subset.empty:
                st.info(f"No {name} assets.")
                return None
            
            # Fetch prices - FORCE SINGLE THREAD
            tickers = [t if ('.' in t or name != "India") else f"{t}.NS" for t in subset['symbol']]
            try:
                # threads=False is vital here
                raw = yf.download(tickers, period="2d", interval="1d", progress=False, threads=False)
                prices = raw['Close']
                
                def get_p(s):
                    t = s if ('.' in s or name != "India") else f"{s}.NS"
                    p_series = prices[t] if len(tickers) > 1 else prices
                    return float(p_series.iloc[-1]), float(p_series.iloc[-2])
                
                price_data = subset['symbol'].apply(lambda x: pd.Series(get_p(x)))
                subset['ltp'], subset['prev'] = price_data[0], price_data[1]
            except:
                subset['ltp'], subset['prev'] = 0, 0

            subset['mkt_val'] = subset['qty'] * subset['ltp']
            subset['day_chg'] = ((subset['ltp'] - subset['prev']) / subset['prev'] * 100).fillna(0)
            
            st.subheader(f"{name} Holdings")
            st.dataframe(subset[['symbol', 'qty', 'ltp', 'mkt_val', 'day_chg']], hide_index=True)
            return subset

    # Process all
    res_in = render_region("India", t_india)
    res_us = render_region("US", t_us)
    res_uk = render_region("London", t_uk)
    res_eu = render_region("Europe", t_eu)

    processed = [x for x in [res_in, res_us, res_uk, res_eu] if x is not None]

    with t_summary:
        if processed:
            full = pd.concat(processed)
            # FX Rates
            try:
                pairs = [f"{display_curr}{c}=X" for c in ["GBP", "USD", "INR", "EUR"] if c != display_curr]
                fx = yf.download(pairs, period="1d", threads=False, progress=False)['Close']
                rates = {c: fx[f"{display_curr}{c}=X"].iloc[-1] if f"{display_curr}{c}=X" in fx else 1.0 for c in ["GBP", "USD", "INR", "EUR"]}
                rates[display_curr] = 1.0
            except:
                rates = {"GBP": 1, "USD": 1.3, "INR": 105, "EUR": 1.2}

            # Conversion
            full['val_converted'] = full.apply(lambda x: x['mkt_val'] / rates[x['curr_code']], axis=1)
            total = full['val_converted'].sum()
            
            st.metric(f"Total Net Worth ({display_curr})", f"{curr_icons[display_curr]}{total:,.2f}")
            
            # Allocation
            fig = px.pie(full, values='val_converted', names='market', hole=0.4, title="Market Allocation")
            st.plotly_chart(fig, use_container_width=True)

            # Movers
            st.subheader("Today's Movers")
            movers = full[['symbol', 'market', 'day_chg']].sort_values('day_chg', ascending=False)
            c1, c2 = st.columns(2)
            c1.write("📈 Gainers")
            c1.table(movers.head(3))
            c2.write("📉 Losers")
            c2.table(movers.tail(3))
else:
    with t_summary: st.warning("Please upload 'portfolio_db.csv' in the Settings tab.")

with t_settings:
    st.header("Upload Data")
    f = st.file_uploader("Upload CSV", type="csv")
    if f:
        with open(DB_FILE, "wb") as file: file.write(f.getbuffer())
        st.success("File saved! Refresh the page.")
