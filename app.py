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
# This dictionary maps the display names to internal keys
NAV_OPTIONS = {
    "📊 Summary": "Summary",
    "🇮🇳 India": "India",
    "🇺🇸 US": "US",
    "🇬🇧 London": "London",
    "🇪🇺 Europe": "Europe",
    "⚙️ Settings": "Settings"
}

if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "📊 Summary"

# --- SIDEBAR: GLOBAL INDICES ---
st.sidebar.header("🌍 Market Indices")

@st.cache_data(ttl=3600)
def fetch_indices():
    indices = {"^NSEI": "Nifty 50", "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^FTSE": "FTSE 100"}
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

# --- SIDEBAR: NAVIGATION LINKS (FIXED) ---
st.sidebar.header("📍 Quick Navigation")

def set_tab(name):
    st.session_state.active_tab = name

# Create buttons that update the session state
for label in NAV_OPTIONS.keys():
    st.sidebar.button(label, on_click=set_tab, args=(label,), use_container_width=True)

st.sidebar.divider()

# --- SIDEBAR: CONTROLS ---
st.sidebar.header("🔍 Controls")
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

st.session_state.search_query = st.sidebar.text_input("Search Symbol", value=st.session_state.search_query).upper()

st.sidebar.header("💱 Display Currency")
display_curr = st.sidebar.selectbox("Show Summary In:", ["GBP", "USD", "INR", "EUR"], index=0)
curr_icons = {"GBP": "£", "USD": "$", "INR": "₹", "EUR": "€"}

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

    # Determine Active Tab content
    active_tab = st.session_state.active_tab

    def render_market_view(market_name):
        subset = filtered_df[filtered_df['market'] == market_name].copy()
        if subset.empty:
            st.info(f"No holdings for {market_name}.")
            return None
        
        tickers = subset['symbol'].tolist()
        fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
        
        with st.status(f"Updating {market_name} Prices...", expanded=False):
            data = yf.download(fetch_list, period="2d", progress=False, threads=False)['Close']
            def get_p(sym):
                try:
                    t = sym if ('.' in sym or market_name != "India") else f"{sym}.NS"
                    v = data[t] if len(fetch_list) > 1 else data
                    return float(v.iloc[-1]), float(v.iloc[-2])
                except: return 0.0, 0.0
            prices = subset['symbol'].apply(lambda x: pd.Series(get_p(x)))
            subset['ltp'], subset['prev'] = prices[0].fillna(0), prices[1].fillna(0)

        subset['buy_price'] = subset['qty'] * subset['avg_price']
        subset['mkt_val'] = subset['qty'] * subset['ltp']
        subset['gain_val'] = subset['mkt_val'] - subset['buy_price']
        subset['day_pct'] = ((subset['ltp'] - subset['prev']) / subset['prev'] * 100).fillna(0)
        cur_sym = str(subset['curr_sym'].iloc[0])

        st.subheader(f"🔝 Top 10 {market_name} Holdings")
        subset['alloc_pct'] = (subset['mkt_val'] / subset['mkt_val'].sum() * 100).fillna(0)
        top_10 = subset.nlargest(10, 'alloc_pct')[['symbol', 'mkt_val', 'alloc_pct']]
        st.dataframe(top_10.style.format({'mkt_val': f"{cur_sym}{{:,.2f}}", 'alloc_pct': "{:.2f}%"}), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader(f"📋 All {market_name} Shares")
        disp = subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'gain_val', 'day_pct']]
        st.dataframe(disp.style.format({'avg_price':"{:.2f}", 'ltp':"{:.2f}", 'mkt_val': f"{cur_sym}{{:,.2f}}", 'gain_val': f"{cur_sym}{{:,.2f}}", 'day_pct':"{:.2f}%"}).applymap(style_gains, subset=['gain_val', 'day_pct']), use_container_width=True, hide_index=True)
        
        st.table(pd.DataFrame([{
            'Total Invested': f"{cur_sym}{subset['buy_price'].sum():,.2f}",
            'Current Value': f"{cur_sym}{subset['mkt_val'].sum():,.2f}",
            'Net Gain/Loss': f"{cur_sym}{subset['gain_val'].sum():,.2f}",
            'Total Return': f"{(subset['gain_val'].sum()/subset['buy_price'].sum()*100):.2f}%" if subset['buy_price'].sum() != 0 else "0.00%"
        }]))
        return subset

    # --- ROUTING ENGINE ---
    if active_tab == "📊 Summary":
        st.header(f"Global Portfolio Summary ({display_curr})")
        # Pre-fetch all regional data for summary calculation
        regional_results = {}
        for m in ["India", "US", "London", "Europe"]:
            # Logic here is stripped down for the summary tab to avoid double rendering
            subset_m = filtered_df[filtered_df['market'] == m].copy()
            if not subset_m.empty:
                tickers_m = subset_m['symbol'].tolist()
                fetch_m = [t if ('.' in t or m != "India") else f"{t}.NS" for t in tickers_m]
                data_m = yf.download(fetch_m, period="1d", progress=False, threads=False)['Close']
                def get_p_quick(sym):
                    try:
                        t = sym if ('.' in sym or m != "India") else f"{sym}.NS"
                        v = data_m[t] if len(fetch_m) > 1 else data_m
                        return float(v.iloc[-1])
                    except: return 0.0
                subset_m['mkt_val'] = subset_m['qty'] * subset_m['symbol'].apply(get_p_quick)
                regional_results[m] = subset_m

        try:
            pairs = [f"{display_curr}{c}=X" for c in ["GBP", "USD", "INR", "EUR"] if c != display_curr]
            fx = yf.download(pairs, period="1d", progress=False, threads=False)['Close']
            rates = {c: fx[f"{display_curr}{c}=X"].iloc[-1] if f"{display_curr}{c}=X" in fx else 1.0 for c in ["GBP", "USD", "INR", "EUR"]}
            rates[display_curr] = 1.0
        except: rates = {"USD": 1.25, "INR": 105.0, "EUR": 1.15, "GBP": 1.0}

        summary_rows = []
        for m_name, m_df in regional_results.items():
            m_curr = m_df['curr_code'].iloc[0]
            local_val = m_df['mkt_val'].sum()
            conv_val = local_val / rates[m_curr]
            summary_rows.append({"Market": m_name, "Currency": m_df['curr_sym'].iloc[0], "Market Value (Local)": local_val, f"Value ({display_curr})": conv_val})
        
        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_global = sum_df[f"Value ({display_curr})"].sum()
            sum_df['Allocation %'] = (sum_df[f"Value ({display_curr})"] / total_global * 100)
            st.subheader("🌍 Global Asset Distribution")
            st.dataframe(sum_df.style.format({'Market Value (Local)': "{:,.2f}", f"Value ({display_curr})": f"{curr_icons[display_curr]}{{:,.2f}}", 'Allocation %': "{:.2f}%"}), use_container_width=True, hide_index=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Total Portfolio Value", f"{curr_icons[display_curr]}{total_global:,.2f}")
                st.plotly_chart(px.pie(sum_df, values=f"Value ({display_curr})", names='Market', hole=0.4), use_container_width=True)
            with c2:
                if os.path.exists(HIST_FILE):
                    h_df = pd.read_csv(HIST_FILE)
                    h_df['Timestamp'] = pd.to_datetime(h_df['Timestamp'])
                    match_h = h_df[h_df['Currency'] == display_curr].sort_values('Timestamp')
                    if len(match_h) > 1:
                        st.plotly_chart(px.line(match_h, x="Timestamp", y="Value"), use_container_width=True)
            save_history(total_global, display_curr)

    elif active_tab == "🇮🇳 India":
        render_market_view("India")
    elif active_tab == "🇺🇸 US":
        render_market_view("US")
    elif active_tab == "🇬🇧 London":
        render_market_view("London")
    elif active_tab == "🇪🇺 Europe":
        render_market_view("Europe")
    elif active_tab == "⚙️ Settings":
        st.header("⚙️ Settings")
        uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
        if uploaded:
            with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
            st.success("File uploaded! Please refresh.")
        if st.button("Clear History"):
            if os.path.exists(HIST_FILE): os.remove(HIST_FILE)
            st.rerun()

else:
    st.info("Upload your portfolio_db.csv in the Settings tab to begin.")
