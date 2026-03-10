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
def load_raw_df():
    """Loads the CSV without grouping to allow individual row editing."""
    if not os.path.exists(DB_FILE): return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    try:
        df = pd.read_csv(DB_FILE)
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {'symbol':['symbol','ticker'], 'qty':['qty','quantity'], 'avg_price':['price','avg','cost']}
        inv_map = {col: target for target, aliases in mapping.items() for col in df.columns if any(a in col for a in aliases)}
        df = df.rename(columns=inv_map)
        df['symbol'] = df['symbol'].astype(str).str.upper()
        return df[['symbol', 'qty', 'avg_price']]
    except:
        return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

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
raw_df = load_raw_df()

if not raw_df.empty:
    # Pre-process for UI
    details = raw_df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    raw_df[['market', 'curr_sym', 'curr_code']] = details
    
    tabs = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])
    regional_data = {}

    def render_market(market_name, tab_obj):
        # We work on a copy for the specific tab
        subset = raw_df[raw_df['market'] == market_name].copy()
        
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings for {market_name}.")
                return None
            
            st.subheader(f"🛠️ Manage {market_name} Shares")
            st.caption("Edit cells directly to Amend. Use the checkmark/delete to remove.")
            
            # --- EDITABLE TABLE ---
            # We use an ID to track changes specific to this market
            edited_df = st.data_editor(
                subset,
                column_order=("symbol", "qty", "avg_price"),
                num_rows="dynamic",
                use_container_width=True,
                key=f"editor_{market_name}"
            )
            
            if st.button(f"💾 Save Changes for {market_name}"):
                # Update the main DB: Remove old market entries, add new ones
                other_markets = raw_df[raw_df['market'] != market_name][['symbol', 'qty', 'avg_price']]
                new_full_df = pd.concat([other_markets, edited_df[['symbol', 'qty', 'avg_price']]])
                new_full_df.to_csv(DB_FILE, index=False)
                st.success("Portfolio Updated!")
                st.rerun()

            st.divider()

            # --- LIVE PERFORMANCE VIEW ---
            # Consolidate duplicates for the performance view
            view_df = edited_df.copy()
            view_df['total_cost'] = view_df['qty'] * view_df['avg_price']
            grouped = view_df.groupby('symbol').agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
            grouped['avg_price'] = (grouped['total_cost'] / grouped['qty']).fillna(0)
            
            tickers = grouped['symbol'].tolist()
            fetch_list = [t if ('.' in t or market_name != "India") else f"{t}.NS" for t in tickers]
            
            with st.status(f"Live Update: {market_name}", expanded=False):
                data = yf.download(fetch_list, period="2d", progress=False, threads=False)['Close']
                def get_p(sym):
                    try:
                        t = sym if ('.' in sym or market_name != "India") else f"{sym}.NS"
                        v = data[t] if len(fetch_list) > 1 else data
                        return float(v.iloc[-1]), float(v.iloc[-2])
                    except: return 0.0, 0.0
                prices = grouped['symbol'].apply(lambda x: pd.Series(get_p(x)))
                grouped['ltp'], grouped['prev'] = prices[0].fillna(0), prices[1].fillna(0)

            grouped['mkt_val'] = grouped['qty'] * grouped['ltp']
            grouped['gain_val'] = grouped['mkt_val'] - grouped['total_cost']
            grouped['day_pct'] = ((grouped['ltp'] - grouped['prev']) / grouped['prev'] * 100).fillna(0)
            cur_sym = subset['curr_sym'].iloc[0]

            st.subheader("📋 Performance View (Consolidated)")
            disp = grouped[['symbol', 'qty', 'avg_price', 'ltp', 'mkt_val', 'gain_val', 'day_pct']]
            st.dataframe(disp.style.format({'mkt_val': f"{cur_sym}{{:,.2f}}", 'gain_val': f"{cur_sym}{{:,.2f}}", 'day_pct':"{:.2f}%"}).applymap(style_gains, subset=['gain_val', 'day_pct']), use_container_width=True, hide_index=True)
            
            # Bottom Summary Table
            st.table(pd.DataFrame([{
                'Total Invested': f"{cur_sym}{grouped['total_cost'].sum():,.2f}",
                'Current Value': f"{cur_sym}{grouped['mkt_val'].sum():,.2f}",
                'Net Gain': f"{cur_sym}{grouped['gain_val'].sum():,.2f}",
                'Return': f"{(grouped['gain_val'].sum()/grouped['total_cost'].sum()*100):.2f}%" if grouped['total_cost'].sum() != 0 else "0%"
            }]))
            
            # Pack for summary tab
            grouped['market'] = market_name
            grouped['curr_code'] = subset['curr_code'].iloc[0]
            grouped['curr_sym'] = cur_sym
            return grouped

    for i, name in enumerate(["India", "US", "London", "Europe"]):
        regional_data[name] = render_market(name, tabs[i+1])

    # --- SUMMARY TAB ---
    with tabs[0]:
        st.header(f"Global Portfolio Summary ({display_curr})")
        
        try:
            pairs = [f"{display_curr}{c}=X" for c in ["GBP", "USD", "INR", "EUR"] if c != display_curr]
            fx = yf.download(pairs, period="1d", progress=False, threads=False)['Close']
            rates = {c: fx[f"{display_curr}{c}=X"].iloc[-1] if f"{display_curr}{c}=X" in fx else 1.0 for c in ["GBP", "USD", "INR", "EUR"]}
            rates[display_curr] = 1.0
        except: 
            rates = {"USD": 1.25, "INR": 105.0, "EUR": 1.15, "GBP": 1.0}

        summary_rows = []
        for m_name, m_df in regional_data.items():
            if m_df is not None and not m_df.empty:
                m_curr = m_df['curr_code'].iloc[0]
                local_val = m_df['mkt_val'].sum()
                conv_val = local_val / rates[m_curr]
                summary_rows.append({"Market": m_name, "Currency": m_df['curr_sym'].iloc[0], "Market Value (Local)": local_val, f"Value ({display_curr})": conv_val})
        
        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_global = sum_df[f"Value ({display_curr})"].sum()
            sum_df['Allocation %'] = (sum_df[f"Value ({display_curr})"] / total_global * 100)
            
            st.subheader("📊 Global Asset Distribution")
            st.dataframe(sum_df.style.format({f"Value ({display_curr})": f"{curr_icons[display_curr]}{{:,.2f}}", 'Allocation %': "{:.2f}%"}), use_container_width=True, hide_index=True)

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Total Net Worth", f"{curr_icons[display_curr]}{total_global:,.2f}")
                st.plotly_chart(px.pie(sum_df, values=f"Value ({display_curr})", names='Market', hole=0.4), use_container_width=True)
            with c2:
                if os.path.exists(HIST_FILE):
                    h_df = pd.read_csv(HIST_FILE)
                    h_df['Timestamp'] = pd.to_datetime(h_df['Timestamp'])
                    match_h = h_df[h_df['Currency'] == display_curr].sort_values('Timestamp')
                    if len(match_h) > 1:
                        st.plotly_chart(px.line(match_h, x="Timestamp", y="Value", title="Portfolio History"), use_container_width=True)
            
            save_history(total_global, display_curr)

else:
    st.info("Please upload your portfolio_db.csv in the Settings tab.")

with tabs[5]:
    st.header("Settings")
    uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
    if uploaded:
        with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
        st.success("File uploaded! Please refresh.")
