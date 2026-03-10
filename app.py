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

# --- SIDEBAR CONTROLS ---
st.sidebar.header("🔍 Controls")
st.session_state.search_query = st.sidebar.text_input("Search Symbol", value=st.session_state.search_query).upper()

st.sidebar.divider()
st.sidebar.header("💱 Global Display Currency")
display_curr = st.sidebar.selectbox("Show Summary In:", ["GBP", "USD", "INR", "EUR"], index=0)
curr_icons = {"GBP": "£", "USD": "$", "INR": "₹", "EUR": "€"}

if st.sidebar.button("Force Global Refresh"):
    st.cache_data.clear()
    st.rerun()

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
            return df[['symbol', 'qty', 'avg_price']].dropna(subset=['symbol'])
    except: return pd.DataFrame()
    return pd.DataFrame()

def save_history(total_val, curr_code):
    """Saves total portfolio value in the current display currency."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = pd.DataFrame([[now, total_val, curr_code]], columns=["Timestamp", "Value", "Currency"])
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
            
            with st.status(f"Updating {market_name} Prices...", expanded=False):
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
            
            cur_sym = str(subset['curr_sym'].iloc[0])

            st.subheader(f"🔝 Top 10 {market_name} Holdings")
            subset['alloc_pct'] = (subset['mkt_val'] / subset['mkt_val'].sum() * 100).fillna(0)
            top_10 = subset.nlargest(10, 'alloc_pct')[['symbol', 'mkt_val', 'alloc_pct']]
            top_10_total = pd.DataFrame([['**TOP 10 TOTAL**', top_10['mkt_val'].sum(), top_10['alloc_pct'].sum()]], columns=['symbol', 'mkt_val', 'alloc_pct'])
            top_10_display = pd.concat([top_10, top_10_total])
            
            st.dataframe(top_10_display.style.format({'mkt_val': f"{cur_sym}{{:,.2f}}", 'alloc_pct': "{:.2f}%"})
                         .apply(lambda x: ['font-weight: bold' if x.name == len(top_10_display)-1 else '' for i in x], axis=1), 
                         use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("📋 All Shares")
            disp = subset[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'buy_price', 'gain_loss_val', 'gain_loss_pct', 'day_gain_pct']]
            st.dataframe(disp.style.format({'avg_price':"{:.2f}", 'ltp':"{:.2f}", 'mkt_val': f"{cur_sym}{{:,.2f}}", 'buy_price': f"{cur_sym}{{:,.2f}}", 'gain_loss_val': f"{cur_sym}{{:,.2f}}", 'gain_loss_pct':"{:.2f}%", 'day_gain_pct':"{:.2f}%"}).applymap(style_gains, subset=['gain_loss_val', 'gain_loss_pct', 'day_gain_pct']), use_container_width=True, hide_index=True)

            st.table(pd.DataFrame([{'Invested': f"{cur_sym}{subset['buy_price'].sum():,.2f}", 'Value': f"{cur_sym}{subset['mkt_val'].sum():,.2f}", 'Net Gain': f"{cur_sym}{subset['gain_loss_val'].sum():,.2f}", 'Return': f"{(subset['gain_loss_val'].sum()/subset['buy_price'].sum()*100):.2f}%" if subset['buy_price'].sum() != 0 else "0.00%"}]))
            return subset

    for i, name in enumerate(["India", "US", "London", "Europe"]):
        regional_data[name] = render_market(name, tabs[i+1])

    # --- SUMMARY TAB WITH DYNAMIC CURRENCY ---
    with tabs[0]:
        st.header(f"Global Portfolio Summary ({display_curr})")
        try:
            # Fetch conversion rates relative to display currency
            pairs = [f"{display_curr}{c}=X" for c in ["GBP", "USD", "INR", "EUR"] if c != display_curr]
            fx_data = yf.download(pairs, period="1d", progress=False)['Close']
            
            # rate = 1 unit of display_curr in target_curr
            rates = {c: fx_data[f"{display_curr}{c}=X"].iloc[-1] if f"{display_curr}{c}=X" in fx_data else 1.0 for c in ["GBP", "USD", "INR", "EUR"]}
            rates[display_curr] = 1.0
        except: rates = {"USD": 1.3, "INR": 105.0, "EUR": 1.18, "GBP": 1.0}

        summary_rows = []
        for m_name, m_df in regional_data.items():
            if m_df is not None and not m_df.empty:
                m_curr = m_df['curr_code'].iloc[0]
                mkt_local = m_df['mkt_val'].sum()
                # Convert local to display currency: local / (display_unit_in_local)
                val_display = mkt_local / rates[m_curr]
                summary_rows.append({
                    "Market": m_name, "Currency": m_df['curr_sym'].iloc[0], 
                    "Market Value (Local)": mkt_local, f"Value ({display_curr})": val_display
                })
        
        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_val = sum_df[f"Value ({display_curr})"].sum()
            sum_df['Allocation %'] = (sum_df[f"Value ({display_curr})"] / total_val * 100)
            
            st.dataframe(sum_df.style.format({'Market Value (Local)': "{:,.2f}", f"Value ({display_curr})": f"{curr_icons[display_curr]}{{:,.2f}}", 'Allocation %': "{:.2f}%"}), use_container_width=True, hide_index=True)

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                fig_pie = px.pie(sum_df, values=f"Value ({display_curr})", names='Market', hole=0.5, title=f"Global Allocation ({display_curr})")
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                st.metric(f"Total Portfolio ({display_curr})", f"{curr_icons[display_curr]}{total_val:,.2f}")
                if os.path.exists(HIST_FILE):
                    h_df = pd.read_csv(HIST_FILE)
                    # Filter history to only show records that match current display currency for consistency
                    match_h = h_df[h_df['Currency'] == display_curr]
                    if len(match_h) > 1:
                        fig_line = px.line(match_h, x="Timestamp", y="Value", markers=True, title=f"History in {display_curr}")
                        st.plotly_chart(fig_line, use_container_width=True)
            
            save_history(total_val, display_curr)

    with tabs[5]:
        st.header("Settings")
        uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
        if uploaded:
            with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
            st.success("Uploaded!")
        if st.button("Reset History Data"):
            if os.path.exists(HIST_FILE): os.remove(HIST_FILE)
            st.rerun()
