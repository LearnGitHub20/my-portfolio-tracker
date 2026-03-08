import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# --- CONFIG ---
st.set_page_config(layout="wide", page_title="Universal Portfolio")

# Initialize session state for the portfolio if it doesn't exist
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame()

def clean_and_map_broker(df):
    """Fuzzy match columns and normalize data."""
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

    # Clean numbers (remove ₹, commas, etc.)
    for col in ['qty', 'avg_price']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace('[^0-9.]', '', regex=True), errors='coerce')
    
    # Normalize Symbols
    df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
    df['symbol'] = df['symbol'].apply(lambda x: x + ".NS" if "." not in x else x)
    
    return df[['symbol', 'qty', 'avg_price']].dropna()

# --- APP LAYOUT ---
st.title("💼 Global Multi-Asset Tracker")

# We define the tabs
tab_dash, tab_upload = st.tabs(["📊 Dashboard", "📤 Upload Holdings"])

# --- TAB: UPLOAD ---
with tab_upload:
    st.header("Upload Statements")
    file = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'])
    
    if file:
        raw_df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        cleaned = clean_and_map_broker(raw_df)
        
        if not cleaned.empty:
            # Merge Duplicates (Sum Qty, Weighted Avg Price)
            cleaned['total_cost'] = cleaned['qty'] * cleaned['avg_price']
            final = cleaned.groupby('symbol').agg({'qty': 'sum', 'total_cost': 'sum'}).reset_index()
            final['avg_price'] = final['total_cost'] / final['qty']
            
            # CRITICAL: Save to session state
            st.session_state.portfolio = final[['symbol', 'qty', 'avg_price']]
            st.success("✅ Portfolio successfully saved to session!")
            
            # Show a preview so you KNOW it's there
            st.subheader("Data Preview")
            st.dataframe(st.session_state.portfolio)
        else:
            st.error("❌ Could not detect columns. Check your headers.")

# --- TAB: DASHBOARD ---
with tab_dash:
    # Check if session state actually has data
    if st.session_state.portfolio.empty:
        st.warning("⚠️ No data found. Please go to the 'Upload' tab and upload your file first.")
    else:
        df = st.session_state.portfolio.copy()
        
        with st.spinner("Fetching Live Prices..."):
            tickers = df['symbol'].tolist()
            # Fetch prices
            try:
                live_data = yf.download(tickers, period="1d", progress=False)['Close']
                if len(tickers) == 1:
                    df['live_price'] = live_data.iloc[-1]
                else:
                    df['live_price'] = df['symbol'].map(lambda x: live_data[x].iloc[-1])
            except:
                st.error("Failed to fetch live prices. Using purchase price.")
                df['live_price'] = df['avg_price']

        # Analysis
        df['current_value'] = df['qty'] * df['live_price']
        df['gain_loss'] = ((df['live_price'] - df['avg_price']) / df['avg_price']) * 100
        
        # Display Metrics
        c1, c2 = st.columns(2)
        c1.metric("Total Portfolio Value", f"₹{df['current_value'].sum():,.2f}")
        c2.metric("Portfolio Return", f"{df['gain_loss'].mean():.2f}%")
        
        st.divider()
        st.dataframe(df.style.format(precision=2), use_container_width=True)
        
        # Allocation Chart
        fig = px.pie(df, values='current_value', names='symbol', hole=0.4, title="Asset Allocation")
        st.plotly_chart(fig, use_container_width=True)
