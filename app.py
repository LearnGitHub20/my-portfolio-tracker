import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import numpy as np

# --- INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Universal Portfolio")
mf = Mftool()

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

# --- HELPER FUNCTIONS ---
def clean_and_map_broker(df):
    df.columns = [str(c).strip().lower() for c in df.columns]
    col_map = {}
    patterns = {
        'symbol': ['symbol', 'trading symbol', 'stock code', 'scrip', 'ticker'],
        'qty': ['qty', 'quantity', 'total qty', 'units'],
        'avg_price': ['avg. price', 'average price', 'average cost', 'buy price', 'price', 'cost']
    }
    for target, aliases in patterns.items():
        for actual_col in df.columns:
            if any(alias == actual_col or alias in actual_col for alias in aliases):
                col_map[actual_col] = target
                break
    df = df.rename(columns=col_map)
    if not all(k in df.columns for k in ['symbol', 'qty', 'avg_price']):
        return pd.DataFrame()

    for col in ['qty', 'avg_price']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
    
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    df['symbol'] = df['symbol'].apply(lambda x: x + ".NS" if ("." not in x and not x.isdigit()) else x)
    return df[['symbol', 'qty', 'avg_price']].dropna()

def merge_holdings(df):
    df['total_cost'] = df['qty'] * df['avg_price']
    grouped = df.groupby('symbol').agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
    # Avoid division by zero
    grouped['avg_price'] = np.where(grouped['qty'] > 0, grouped['total_cost'] / grouped['qty'], 0)
    return grouped[['symbol', 'qty', 'avg_price']]

# --- SIDEBAR: MANUAL CONTROLS ---
st.sidebar.header("➕ Manual Management")
with st.sidebar.expander("Add / Update Single Stock"):
    new_sym = st.text_input("Symbol (e.g. AAPL or RELIANCE.NS)").upper()
    new_qty = st.number_input("Quantity", min_value=0.0, step=1.0)
    new_prc = st.number_input("Avg Price", min_value=0.0, step=0.1)
    if st.button("Add to Portfolio"):
        new_row = pd.DataFrame([{'symbol': new_sym, 'qty': new_qty, 'avg_price': new_prc}])
        st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row])
        st.session_state.portfolio = merge_holdings(st.session_state.portfolio)
        st.success(f"Updated {new_sym}")

with st.sidebar.expander("🗑️ Delete Stock"):
    if not st.session_state.portfolio.empty:
        del_sym = st.selectbox("Select Symbol to Remove", st.session_state.portfolio['symbol'].tolist())
        if st.button("Delete"):
            st.session_state.portfolio = st.session_state.portfolio[st.session_state.portfolio['symbol'] != del_sym]
            st.rerun()
    else:
        st.write("No stocks to delete.")

# --- APP LAYOUT ---
tabs = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tabs[1]:
    st.header("Bulk Upload Statements")
    file = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'])
    if file:
        raw_df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        cleaned = clean_and_map_broker(raw_df)
        if not cleaned.empty:
            st.session_state.portfolio = merge_holdings(cleaned)
            st.success("✅ Bulk Portfolio Loaded!")
        else:
            st.error("❌ Column mapping failed.")

with tabs[0]:
    if st.session_state.portfolio.empty:
        st.info("Portfolio is empty. Add stocks via Sidebar or Upload tab.")
    else:
        df = st.session_state.portfolio.copy()
        
        with st.spinner("Fetching Live Prices..."):
            tickers = df['symbol'].tolist()
            try:
                # Filter out numeric AMFI codes for yfinance
                stock_tickers = [t for t in tickers if not t.isdigit()]
                live_data = yf.download(stock_tickers, period="1d", progress=False)['Close']
                
                def get_price(sym):
                    if sym.isdigit(): # Mutual Fund Logic
                        try: return float(mf.get_scheme_quote(sym)['nav'])
                        except: return 0
                    if len(stock_tickers) == 1: return live_data.iloc[-1]
                    return live_data[sym].iloc[-1]

                df['live_price'] = df['symbol'].apply(get_price)
            except Exception as e:
                st.error(f"Price Fetch Error: {e}")
                df['live_price'] = df['avg_price']

        # Calculations
        df['current_value'] = df['qty'] * df['live_price']
        
        # Fixing the INF% Issue: Use numpy to handle division by zero
        df['gain_loss_%'] = np.where(df['avg_price'] > 0, 
                                     ((df['live_price'] - df['avg_price']) / df['avg_price']) * 100, 
                                     0.0)
        
        # Display Metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Value", f"₹{df['current_value'].sum():,.2f}")
        c2.metric("Portfolio Return", f"{df['gain_loss_%'].mean():.2f}%")
        c3.metric("Assets", f"{len(df)}")
        
        st.divider()

        # --- FIX: SERIAL NUMBER STARTING FROM 1 ---
        display_df = df.copy()
        display_df.index = np.arange(1, len(display_df) + 1) # Shift index to start at 1
        st.subheader("Holdings Detail")
        st.dataframe(display_df.style.format(precision=2), use_container_width=True)
        
        # Chart
        fig = px.pie(df, values='current_value', names='symbol', hole=0.4, title="Allocation Donut")
        st.plotly_chart(fig, use_container_width=True)
