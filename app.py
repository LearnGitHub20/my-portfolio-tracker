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

# --- APP LAYOUT ---
tabs = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tabs[1]:
    st.header("Bulk Upload")
    file = st.file_uploader("Upload CSV/Excel", type=['csv', 'xlsx'])
    if file:
        raw_df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        cleaned = clean_and_map_broker(raw_df)
        if not cleaned.empty:
            st.session_state.portfolio = cleaned
            st.success("✅ Portfolio Loaded!")

with tabs[0]:
    st.header("Portfolio Dashboard")
    
    # 1. Manual Add Section
    with st.expander("➕ Add New Stock Manually"):
        c1, c2, c3 = st.columns(3)
        new_s = c1.text_input("Symbol (e.g., AAPL)").upper()
        new_q = c2.number_input("Quantity", min_value=0.0)
        new_p = c3.number_input("Avg Price", min_value=0.0)
        if st.button("Save to Portfolio"):
            new_row = pd.DataFrame([{'symbol': new_s, 'qty': new_q, 'avg_price': new_p}])
            st.session_state.portfolio = pd.concat([st.session_state.portfolio, new_row]).reset_index(drop=True)
            st.rerun()

    if not st.session_state.portfolio.empty:
        df = st.session_state.portfolio.copy()
        
        # 2. Fetch Live Prices (Corrected for first row)
        with st.spinner("Updating Prices..."):
            tickers = df['symbol'].tolist()
            stock_tickers = [t for t in tickers if not t.isdigit()]
            
            # Fetch data with error handling for first row
            if stock_tickers:
                live_data = yf.download(stock_tickers, period="1d", progress=False)['Close']
                
                def get_price(sym):
                    if sym.isdigit():
                        try: return float(mf.get_scheme_quote(sym)['nav'])
                        except: return 0
                    try:
                        # If single stock, live_data is a Series. If multiple, it's a DataFrame.
                        if isinstance(live_data, pd.Series):
                            return live_data.iloc[-1]
                        return live_data[sym].iloc[-1]
                    except: return 0
                
                df['live_price'] = df['symbol'].apply(get_price)
            else:
                df['live_price'] = 0

        # Calculations
        df['current_value'] = df['qty'] * df['live_price']
        df['gain_loss_%'] = np.where(df['avg_price'] > 0, 
                                     ((df['live_price'] - df['avg_price']) / df['avg_price']) * 100, 
                                     0.0)

        # 3. Actionable Table (Row-by-Row)
        st.subheader("Holdings & Actions")
        
        # Header Row
        h1, h2, h3, h4, h5, h6, h7 = st.columns([1, 2, 1, 1, 1, 1, 1])
        h1.write("**#**")
        h2.write("**Symbol**")
        h3.write("**Qty**")
        h4.write("**LTP**")
        h5.write("**Value**")
        h6.write("**Gain %**")
        h7.write("**Action**")

        # Data Rows
        for i, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 2, 1, 1, 1, 1, 1])
            c1.write(f"{i+1}") # Serial number starting from 1
            c2.write(row['symbol'])
            c3.write(f"{row['qty']:.2f}")
            c4.write(f"{row['live_price']:.2f}")
            c5.write(f"{row['current_value']:,.2f}")
            
            # Color coding for gain
            color = "green" if row['gain_loss_%'] >= 0 else "red"
            c6.markdown(f":{color}[{row['gain_loss_%']:.2f}%]")
            
            if c7.button("🗑️", key=f"del_{i}"):
                st.session_state.portfolio = st.session_state.portfolio.drop(i).reset_index(drop=True)
                st.rerun()

        # Summary & Analytics
        st.divider()
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Total Portfolio Value", f"₹{df['current_value'].sum():,.2f}")
        col_m2.metric("Avg Portfolio Return", f"{df['gain_loss_%'].mean():.2f}%")

        fig = px.pie(df, values='current_value', names='symbol', hole=0.5, title="Asset Allocation")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Your portfolio is empty. Upload a file or add a stock manually.")
