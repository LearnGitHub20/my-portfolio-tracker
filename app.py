import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os
from datetime import datetime

# --- INITIAL SETUP ---
DB_FILE = "portfolio_db.csv"
HIST_FILE = "history_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

# --- NAVIGATION LOGIC ---
NAV_OPTIONS = {
    "📊 Summary": "Summary",
    "🇮🇳 India": "India",
    "🇺🇸 US": "US",
    "🇬🇧 London": "London",
    "🇪🇺 Europe": "Europe",
    "🇨🇭 Switzerland": "Switzerland",
    "⚙️ Settings": "Settings"
}

if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "📊 Summary"

# --- SIDEBAR: GLOBAL INDICES ---
st.sidebar.header("🌍 Market Indices")

@st.cache_data(ttl=3600)
def fetch_indices():
    indices = {"^NSEI": "Nifty 50", "^GSPC": "S&P 500", "^FTSE": "FTSE 100", "^SSMI": "SMI (Swiss)"}
    try:
        data = yf.download(list(indices.keys()), period="2d", interval="1d", progress=False, threads=False)['Close']
        results = []
        for ticker, name in indices.items():
            curr = float(data[ticker].iloc[-1])
            prev = float(data[ticker].iloc[-2])
            change = ((curr - prev) / prev) * 100
            results.append({"name": name, "price": curr, "change": change})
        return results
    except:
        return []

index_data = fetch_indices()
if index_data:
    c1, c2 = st.sidebar.columns(2)
    for i, idx in enumerate(index_data):
        target_col = c1 if i % 2 == 0 else c2
        target_col.metric(idx['name'], f"{idx['price']:,.0f}", f"{idx['change']:+.2f}%")

st.sidebar.divider()

# --- SIDEBAR: NAVIGATION LINKS ---
st.sidebar.header("📍 Quick Navigation")
def set_tab(name):
    st.session_state.active_tab = name

for label in NAV_OPTIONS.keys():
    st.sidebar.button(label, on_click=set_tab, args=(label,), use_container_width=True)

st.sidebar.divider()

# --- SIDEBAR: CONTROLS ---
st.sidebar.header("🔍 Controls")
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
st.session_state.search_query = st.sidebar.text_input("Search Company/Ticker", value=st.session_state.search_query).upper()

st.sidebar.header("💱 Display Currency")
display_curr = st.sidebar.selectbox("Show Summary In:", ["GBP", "USD", "INR", "EUR", "CHF"], index=0)
curr_icons = {"GBP": "£", "USD": "$", "INR": "₹", "EUR": "€", "CHF": "Fr."}

if st.sidebar.button("Force Refresh All Data"):
    st.cache_data.clear()
    st.rerun()

# --- DATA HELPERS ---
def load_data():
    if not os.path.exists(DB_FILE): return pd.DataFrame()
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {'symbol':['symbol','ticker'], 'qty':['qty','quantity'], 'avg_price':['price','avg','cost']}
        inv_map = {col: target for target, aliases in mapping.items() for col in df.columns if any(a in col for a in aliases)}
        df = df.rename(columns=inv_map)
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
            df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce').fillna(0)
            df['total_cost'] = df['qty'] * df['avg_price']
            grouped = df.groupby('symbol').agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
            grouped['avg_price'] = (grouped['total_cost'] / grouped['qty']).fillna(0)
            return grouped[['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
    except: return pd.DataFrame()

def save_history(total_val, curr_code):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = pd.DataFrame([[now, total_val, curr_code]], columns=["Timestamp", "Value", "Currency"])
    if not os.path.exists(HIST_FILE):
        new_entry.to_csv(HIST_FILE, index=False)
    else:
        new_entry.to_csv(HIST_FILE, mode='a', header=False, index=False)

def get_market_label(symbol):
    s = str(symbol).upper()
    if s.endswith('.SW'): return "Switzerland", "Fr.", "CHF"
    if s.endswith('.L'): return "London", "£", "GBP"
    if any(s.endswith(ext) for ext in ['.PA', '.DE', '.AS', '.MI', '.MC']): return "Europe", "€", "EUR"
    if s.endswith('.NS') or s.endswith('.BO'): return "India", "₹", "INR"
    return "US", "$", "USD"

def style_gains(val):
    if isinstance(val, (int, float)):
        color = 'red' if val < 0 else 'green' if val > 0 else 'white'
        return f'color: {color}'
    return ''

# --- MAIN LOGIC ---
df = load_data()

if df is not None and not df.empty:
    filtered_df = df[df['symbol'].str.contains(st.session_state.search_query)] if st.session_state.search_query else df
    details = filtered_df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    filtered_df[['market', 'curr_sym', 'curr_code']] = details

    active_tab = st.session_state.active_tab

    def render_market_view(market_name):
        subset = filtered_df[filtered_df['market'] == market_name].copy()
        if subset.empty:
            st.info(f"No holdings for {market_name}.")
            return None
        
        tickers = subset['symbol'].tolist()
        fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
        
        with st.status(f"Updating {market_name} Data...", expanded=False):
            data = yf.download(fetch_list, period="2d", progress=False, threads=False)['Close']
            
            name_map = {}
            for t in fetch_list:
                try:
                    ticker_obj = yf.Ticker(t)
                    official_name = ticker_obj.info.get('longName') or ticker_obj.info.get('shortName') or t
                    name_map[t] = official_name
                except:
                    name_map[t] = t

            def get_p(sym):
                try:
                    t = sym if ('.' in sym or market_name != "India") else f"{sym}.NS"
                    v = data[t] if len(fetch_list) > 1 else data
                    # Safety check for single vs multi ticker results
                    p_curr = float(v.iloc[-1]) if hasattr(v, 'iloc') else float(v)
                    p_prev = float(v.iloc[-2]) if hasattr(v, 'iloc') and len(v) > 1 else p_curr
                    return p_curr, p_prev, name_map.get(t, sym)
                except: return 0.0, 0.0, sym

            prices = subset['symbol'].apply(lambda x: pd.Series(get_p(x)))
            subset['ltp'], subset['prev'], subset['company_name'] = prices[0].fillna(0), prices[1].fillna(0), prices[2]

        subset['buy_price'] = subset['qty'] * subset['avg_price']
        subset['mkt_val'] = subset['qty'] * subset['ltp']
        subset['gain_val'] = subset['mkt_val'] - subset['buy_price']
        subset['day_pct'] = ((subset['ltp'] - subset['prev']) / subset['prev'] * 100).fillna(0)
        cur_sym = str(subset['curr_sym'].iloc[0])

        st.subheader(f"🔝 Top 10 {market_name} Holdings")
        subset['alloc_pct'] = (subset['mkt_val'] / subset['mkt_val'].sum() * 100).fillna(0)
        top_10 = subset.nlargest(10, 'alloc_pct')[['company_name', 'symbol', 'mkt_val', 'alloc_pct']]
        top_10.columns = ['Company Name', 'Ticker', 'Market Value', 'Allocation %']
        st.dataframe(top_10.style.format({'Market Value': f"{cur_sym}{{:,.2f}}", 'Allocation %': "{:.2f}%"}), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader(f"📋 All {market_name} Shares")
        disp = subset[['company_name', 'symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'gain_val', 'day_pct']]
        disp.columns = ['Company Name', 'Ticker', 'Shares', 'Avg Cost', 'LTP', 'Market Value', 'Net Gain', 'Day Change']
        
        st_styled = disp.style.format({
            'Avg Cost':"{:.2f}", 
            'LTP':"{:.2f}", 
            'Market Value': f"{cur_sym}{{:,.2f}}", 
            'Net Gain': f"{cur_sym}{{:,.2f}}", 
            'Day Change':"{:.2f}%"
        })
        
        if hasattr(st_styled, 'map'):
            st_styled = st_styled.map(style_gains, subset=['Net Gain', 'Day Change'])
        else:
            st_styled = st_styled.applymap(style_gains, subset=['Net Gain', 'Day Change'])

        st.dataframe(st_styled, use_container_width=True, hide_index=True)
        
        st.table(pd.DataFrame([{
            'Total Invested': f"{cur_sym}{subset['buy_price'].sum():,.2f}",
            'Current Value': f"{cur_sym}{subset['mkt_val'].sum():,.2f}",
            'Net Gain/Loss': f"{cur_sym}{subset['gain_val'].sum():,.2f}",
            'Total Return': f"{(subset['gain_val'].sum()/subset['buy_price'].sum()*100):.2f}%" if subset['buy_price'].sum() != 0 else "0.00%"
        }]))

        st.divider()
        st.subheader(f"🚀 {market_name} Daily Movers")
