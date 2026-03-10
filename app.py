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

# --- SIDEBAR ---
st.sidebar.header("🔍 Controls")
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

st.session_state.search_query = st.sidebar.text_input("Search Symbol", value=st.session_state.search_query).upper()

st.sidebar.divider()
st.sidebar.header("💱 Global Display Currency")
display_curr = st.sidebar.selectbox("Show Summary In:", ["GBP", "USD", "INR", "EUR"], index=0)
curr_icons = {"GBP": "£", "USD": "$", "INR": "₹", "EUR": "€"}

if st.sidebar.button("Force Global Refresh"):
    st.cache_data.clear()
    st.rerun()

# --- ROBUST DATA LOADER ---
def load_data():
    if not os.path.exists(DB_FILE):
        return None, "File 'portfolio_db.csv' not found. Please upload it in Settings."
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Flexible mapping
        mapping = {
            'symbol': ['symbol', 'ticker', 'code', 'stock'],
            'qty': ['qty', 'quantity', 'units', 'shares'],
            'avg_price': ['price', 'avg', 'cost', 'buy price', 'average']
        }
        
        rename_dict = {}
        for target, aliases in mapping.items():
            for col in df.columns:
                if any(alias in col for alias in aliases):
                    rename_dict[col] = target
                    break
        
        df = df.rename(columns=rename_dict)
        
        if 'symbol' not in df.columns or 'qty' not in df.columns:
            return None, f"Missing required columns. Found: {list(df.columns)}"
            
        df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
        df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
        df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce').fillna(0)
        
        clean_df = df[df['symbol'] != 'NAN'][['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
        return clean_df, "Success"
    except Exception as e:
        return None, f"Error reading CSV: {str(e)}"

def save_history(total_val, curr_code):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        new_entry = pd.DataFrame([[now, total_val, curr_code]], columns=["Timestamp", "Value", "Currency"])
        if not os.path.exists(HIST_FILE):
            new_entry.to_csv(HIST_FILE, index=False)
        else:
            hist_df = pd.read_csv(HIST_FILE)
            if hist_df.empty or str(hist_df.iloc[-1]['Timestamp']) != now:
                new_entry.to_csv(HIST_FILE, mode='a', header=False, index=False)
    except: pass

def get_market_label(symbol):
    s = str(symbol).upper()
    if s.endswith('.L'): return "London", "£", "GBP"
    if any(s.endswith(ext) for ext in ['.PA', '.DE', '.AS', '.MI', '.MC', '.LS']): return "Europe", "€", "EUR"
    if s.endswith('.NS') or s.endswith('.BO'): return "India", "₹", "INR"
    return "US", "$", "USD"

def style_gains(val):
    if isinstance(val, (int, float)):
        return 'color: red' if val < 0 else 'color: green' if val > 0 else ''
    return ''

# --- MAIN LOGIC ---
df, status_msg = load_data()

# Use Tabs as the main structure
t_sum, t_in, t_us, t_lon, t_eu, t_set = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])

if df is not None and not df.empty:
    # Filter by search
    if st.session_state.search_query:
        df = df[df['symbol'].str.contains(st.session_state.search_query)]

    # Add market metadata
    meta = df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    df[['market', 'curr_sym', 'curr_code']] = meta

    all_processed = []

    def process_market(market_name, tab_obj):
        subset = df[df['market'] == market_name].copy()
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings found for {market_name}.")
                return None
            
            tickers = subset['symbol'].tolist()
            fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
            
            try:
                data = yf.download(fetch_list, period="2d", progress=False, threads=False)['Close']
                def fetch_price(sym):
                    t = sym if ('.' in sym or market_name != "India") else f"{sym}.NS"
                    col = data[t] if len(fetch_list) > 1 else data
                    return float(col.iloc[-1]), float(col.iloc[-2])
                
                prices = subset['symbol'].apply(lambda x: pd.Series(fetch_price(x)))
                subset['ltp'], subset['prev'] = prices[0].fillna(0), prices[1].fillna(0)
            except:
                subset['ltp'], subset['prev'] = 0.0, 0.0

            subset['buy_val'] = subset['qty'] * subset['avg_price']
            subset['mkt_val'] = subset['qty'] * subset['ltp']
            subset['gain_val'] = subset['mkt_val'] - subset['buy_val']
            subset['gain_pct'] = (subset['gain_val'] / subset['buy_val'] * 100).fillna(0)
            subset['day_pct'] = ((subset['ltp'] - subset['prev']) / subset['prev'] * 100).fillna(0)
            
            c_sym = subset['curr_sym'].iloc[0]
            
            # Top 10
            st.subheader(f"🔝 Top 10 {market_name}")
            subset['alloc'] = (subset['mkt_val'] / subset['mkt_val'].sum() * 100).fillna(0)
            top10 = subset.nlargest(10, 'alloc')[['symbol', 'mkt_val', 'alloc']].reset_index(drop=True)
            total_row = pd.DataFrame([['**TOTAL**', top10['mkt_val'].sum(), top10['alloc'].sum()]], columns=top10.columns)
            st.dataframe(pd.concat([top10, total_row], ignore_index=True).style.format({'mkt_val': f"{c_sym}{{:,.2f}}", 'alloc': "{:.2f}%"}), use_container_width=True, hide_index=True)
            
            st.divider()
            # All Shares
            st.subheader("📋 All Shares")
            st.dataframe(subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'gain_val', 'gain_pct', 'day_pct']].style.format({
                'mkt_val': f"{c_sym}{{:,.2f}}", 'gain_pct': "{:.2f}%", 'day_pct': "{:.2f}%"
            }).applymap(style_gains, subset=['gain_val', 'gain_pct', 'day_pct']), use_container_width=True, hide_index=True)
            
            return subset

    # Run for each market
    m_in = process_market("India", t_in)
    m_us = process_market("US", t_us)
    m_lon = process_market("London", t_lon)
    m_eu = process_market("Europe", t_eu)
    
    all_processed = [x for x in [m_in, m_us, m_lon, m_eu] if x is not None]

    # --- SUMMARY TAB ---
    with t_sum:
        if all_processed:
            full = pd.concat(all_processed, ignore_index=True)
            try:
                pairs = [f"{display_curr}{c}=X" for c in ["GBP", "USD", "INR", "EUR"] if c != display_curr]
                fx = yf.download(pairs, period="1d", progress=False, threads=False)['Close']
                rates = {c: fx[f"{display_curr}{c}=X"].iloc[-1] if f"{display_curr}{c}=X" in fx else 1.0 for c in ["GBP", "USD", "INR", "EUR"]}
                rates[display_curr] = 1.0
            except: rates = {"GBP":1.0, "USD":1.3, "INR":105.0, "EUR":1.18}

            summary_data = []
            for m_name, m_df in zip(["India", "US", "London", "Europe"], [m_in, m_us, m_lon, m_eu]):
                if m_df is not None:
                    val_conv = m_df['mkt_val'].sum() / rates[m_df['curr_code'].iloc[0]]
                    summary_data.append({"Market": m_name, "Currency": m_df['curr_sym'].iloc[0], "Market Value (Local)": m_df['mkt_val'].sum(), f"Value ({display_curr})": val_conv})
            
            sum_df = pd.DataFrame(summary_data)
            total_global = sum_df[f"Value ({display_curr})"].sum()
            sum_df['Allocation %'] = (sum_df[f"Value ({display_curr})"] / total_global * 100)
            
            st.subheader(f"🌍 Global Overview ({display_curr})")
            st.dataframe(sum_df.style.format({f"Value ({display_curr})": f"{curr_icons[display_curr]}{{:,.2f}}", 'Allocation %': "{:.2f}%"}), use_container_width=True, hide_index=True)
            
            st.divider()
            # Movers
            st.subheader("🚀 Daily Movers")
            movers = full[['symbol', 'market', 'day_pct']].sort_values('day_pct', ascending=False)
            c1, c2 = st.columns(2)
            c1.write("🟢 **Top Gainers**")
            c1.dataframe(movers.head(5), hide_index=True)
            c2.write("🔴 **Top Losers**")
            c2.dataframe(movers.tail(5), hide_index=True)
            
            st.divider()
            # Charts
            c3, c4 = st.columns(2)
            c3.plotly_chart(px.pie(sum_df, values=f"Value ({display_curr})", names='Market', hole=0.5, title="Allocation"), use_container_width=True)
            with c4:
                st.metric("Total Net Worth", f"{curr_icons[display_curr]}{total_global:,.2f}")
                if os.path.exists(HIST_FILE):
                    h_df = pd.read_csv(HIST_FILE)
                    match_h = h_df[h_df['Currency'] == display_curr]
                    if len(match_h) > 1:
                        st.plotly_chart(px.line(match_h, x="Timestamp", y="Value", title="History"), use_container_width=True)
            
            save_history(total_global, display_curr)
        else:
            st.warning("No data found in the CSV. Ensure symbols and quantities are provided.")

else:
    with t_sum: st.error(status_msg)

# --- SETTINGS ---
with t_set:
    st.header("Settings")
    uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
    if uploaded:
        with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
        st.success("File saved! Refresh the page.")
    if st.button("Reset All History"):
        if os.path.exists(HIST_FILE): os.remove(HIST_FILE)
        st.rerun()
