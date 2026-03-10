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

if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

def load_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
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
            return df[['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
    except: return pd.DataFrame()
    return pd.DataFrame()

def save_history(total_gbp):
    """Saves the current total value to a CSV for historical tracking."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = pd.DataFrame([[now, total_gbp]], columns=["Timestamp", "Total_Value_GBP"])
    if not os.path.exists(HIST_FILE):
        new_entry.to_csv(HIST_FILE, index=False)
    else:
        new_entry.to_csv(HIST_FILE, mode='a', header=False, index=False)

def get_market_label(symbol):
    s = str(symbol).upper()
    if s.endswith('.L'): return "London", "£", "GBP"
    if any(s.endswith(ext) for ext in ['.PA', '.DE', '.AS', '.MI', '.MC', '.LS']): return "Europe", "€", "EUR"
    if s.endswith('.NS') or s.endswith('.BO'): return "India", "₹", "INR"
    return "US", "$", "USD"

def style_gains(val):
    if isinstance(val, (int, float)):
        color = 'red' if val < 0 else 'green' if val > 0 else 'white'
        return f'color: {color}'
    return ''

# --- SIDEBAR ---
st.sidebar.header("🔍 Controls")
st.session_state.search_query = st.sidebar.text_input("Search Symbol", value=st.session_state.search_query).upper()

if st.sidebar.button("Force Global Refresh"):
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("Clear Search"):
    st.session_state.search_query = ""
    st.rerun()

df = load_data()

if not df.empty:
    filtered_df = df[df['symbol'].str.contains(st.session_state.search_query)] if st.session_state.search_query else df
    details = filtered_df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    filtered_df[['market', 'curr_sym', 'curr_code']] = details

    tabs = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])
    regional_data = {}

    def render_market(market_name, tab_obj):
        subset = filtered_df[filtered_df['market'] == market_name].copy()
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings for {market_name}.")
                return None
            
            tickers = subset['symbol'].tolist()
            fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
            
            with st.status(f"Updating {market_name}...", expanded=False):
                data = yf.download(fetch_list, period="2d", progress=False)['Close']
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
            subset['gain_loss_val'] = subset['mkt_val'] - subset['buy_price']
            subset['gain_loss_pct'] = (subset['gain_loss_val'] / subset['buy_price'] * 100).fillna(0)
            subset['day_gain_pct'] = ((subset['ltp'] - subset['prev']) / subset['prev'] * 100).fillna(0)
            
            # Top 10
            st.subheader(f"🔝 Top 10 {market_name}")
            subset['alloc_pct'] = (subset['mkt_val'] / subset['mkt_val'].sum() * 100).fillna(0)
            top_10 = subset.nlargest(10, 'alloc_pct')[['symbol', 'mkt_val', 'alloc_pct']]
            top_10_total = pd.DataFrame([['TOP 10 TOTAL', top_10['mkt_val'].sum(), top_10['alloc_pct'].sum()]], columns=top_10.columns)
            st.dataframe(pd.concat([top_10, top_10_total]), use_container_width=True, hide_index=True)

            # All Shares
            st.subheader("📋 All Shares")
            disp = subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'buy_price', 'gain_loss_val', 'gain_loss_pct', 'day_gain_pct']]
            st.dataframe(disp.style.format({'mkt_val':"{:,.2f}", 'gain_loss_pct':"{:.2f}%", 'day_gain_pct':"{:.2f}%"}).applymap(style_gains, subset=['gain_loss_val', 'gain_loss_pct', 'day_gain_pct']), use_container_width=True, hide_index=True)

            # Pinned Totals
            cur_sym = str(subset['curr_sym'].iloc[0])
            st.table(pd.DataFrame([{'Invested': f"{cur_sym}{subset['buy_price'].sum():,.2f}", 'Value': f"{cur_sym}{subset['mkt_val'].sum():,.2f}", 'Return': f"{subset['gain_loss_pct'].mean():.2f}%"}]))
            return subset

    # Populate Regions
    for i, name in enumerate(["India", "US", "London", "Europe"]):
        regional_data[name] = render_market(name, tabs[i+1])

    # --- SUMMARY TAB ---
    with tabs[0]:
        st.header("Global Portfolio Summary")
        try:
            fx = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
            rates = {"USD": fx["GBPUSD=X"].iloc[-1], "INR": fx["GBPINR=X"].iloc[-1], "EUR": fx["GBPEUR=X"].iloc[-1], "GBP": 1.0}
        except: rates = {"USD": 1.3, "INR": 105.0, "EUR": 1.18, "GBP": 1.0}

        summary_rows = []
        for m_name, m_df in regional_data.items():
            if m_df is not None and not m_df.empty:
                mkt_gbp = m_df['mkt_val'].sum() / rates[m_df['curr_code'].iloc[0]]
                summary_rows.append({"Market": m_name, "Market Value (£)": mkt_gbp})
        
        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_gbp = sum_df['Market Value (£)'].sum()
            save_history(total_gbp) # AUTO-LOGGING

            st.metric("Total Global Value", f"£{total_gbp:,.2f}")
            
            # Line Chart for History
            if os.path.exists(HIST_FILE):
                hist_df = pd.read_csv(HIST_FILE)
                if len(hist_df) > 1:
                    st.subheader("📈 Total Value Over Time (GBP)")
                    fig_line = px.line(hist_df, x="Timestamp", y="Total_Value_GBP", markers=True, template="plotly_dark")
                    st.plotly_chart(fig_line, use_container_width=True)
            
            # Donut Chart
            fig_pie = px.pie(sum_df, values='Market Value (£)', names='Market', hole=0.5, title="Market Allocation")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tabs[5]:
        st.header("Settings")
        uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
        if uploaded:
            with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
            st.success("Uploaded!")
        if st.button("Reset History Data"):
            if os.path.exists(HIST_FILE): os.remove(HIST_FILE)
            st.rerun()
