import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os

# --- INITIAL SETUP ---
DB_FILE = "portfolio_db.csv"
st.set_page_config(layout="wide", page_title="Global Wealth Tracker", page_icon="🌍")

def load_data():
    if not os.path.exists(DB_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_csv(DB_FILE, on_bad_lines='skip', engine='python')
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapping = {
            'symbol':['symbol','ticker'], 
            'qty':['qty','quantity'], 
            'avg_price':['price','avg','cost'], 
            'sector':['sector','industry']
        }
        inv_map = {col: target for target, aliases in mapping.items() for col in df.columns if any(a in col for a in aliases)}
        df = df.rename(columns=inv_map)
        
        if 'sector' not in df.columns: df['sector'] = 'General'
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].astype(str).str.upper().str.strip()
            df['qty'] = pd.to_numeric(df['qty'], errors='coerce').fillna(0)
            df['avg_price'] = pd.to_numeric(df['avg_price'], errors='coerce').fillna(0)
            return df.dropna(subset=['symbol'])
    except: return pd.DataFrame()
    return pd.DataFrame()

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

# --- UI ---
st.title("🌍 Global Multi-Market Tracker")

if st.sidebar.button("Force Global Refresh"):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    details = df['symbol'].apply(lambda x: pd.Series(get_market_label(x)))
    df[['market', 'curr_sym', 'curr_code']] = details

    t_sum, t_in, t_us, t_lon, t_eu, t_set = st.tabs(["📊 Summary", "🇮🇳 India", "🇺🇸 US", "🇬🇧 London", "🇪🇺 Europe", "⚙️ Settings"])
    regional_data = {}

    def render_market(market_name, tab_obj):
        subset = df[df['market'] == market_name].copy()
        with tab_obj:
            if subset.empty:
                st.info(f"No holdings listed for {market_name}.")
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
                subset['ltp'] = prices[0].fillna(0)
                subset['prev'] = prices[1].fillna(0)

            subset['buy_price'] = subset['qty'] * subset['avg_price']
            subset['mkt_val'] = subset['qty'] * subset['ltp']
            subset['gain_loss_val'] = subset['mkt_val'] - subset['buy_price']
            subset['gain_loss_pct'] = (subset['gain_loss_val'] / subset['buy_price'] * 100).fillna(0)
            subset['day_gain_pct'] = ((subset['ltp'] - subset['prev']) / subset['prev'] * 100).fillna(0)

            # METRICS
            cur_sym = str(subset['curr_sym'].iloc[0])
            st.subheader(f"{market_name} Market Overview")
            m1, m2 = st.columns(2)
            m1.metric("Total Invested", f"{cur_sym}{float(subset['buy_price'].sum()):,.2f}")
            m2.metric("Market Value", f"{cur_sym}{float(subset['mkt_val'].sum()):,.2f}")

            st.divider()
            
            # --- INDIVIDUAL TAB DATASET ---
            disp = subset[['symbol', 'sector', 'qty', 'avg_price', 'ltp', 'mkt_val', 'buy_price', 'gain_loss_val', 'gain_loss_pct', 'day_gain_pct']].copy()
            
            # TOTAL ROW
            totals = pd.Series({
                'symbol': 'TOTAL', 'sector': '-', 'qty': subset['qty'].sum(),
                'mkt_val': subset['mkt_val'].sum(), 'buy_price': subset['buy_price'].sum(),
                'gain_loss_val': subset['gain_loss_val'].sum(),
                'gain_loss_pct': (subset['gain_loss_val'].sum() / subset['buy_price'].sum() * 100) if subset['buy_price'].sum() != 0 else 0,
                'day_gain_pct': ((subset['mkt_val'].sum() - (subset['prev'] * subset['qty']).sum()) / (subset['prev'] * subset['qty']).sum() * 100) if (subset['prev'] * subset['qty']).sum() != 0 else 0
            })
            disp = pd.concat([disp, totals.to_frame().T], ignore_index=True)
            
            styled_df = disp.style.format({
                'avg_price':"{:.2f}", 'ltp':"{:.2f}", 'mkt_val':"{:,.2f}", 
                'buy_price':"{:,.2f}", 'gain_loss_val':"{:,.2f}", 
                'gain_loss_pct':"{:.2f}%", 'day_gain_pct':"{:.2f}%"
            }).applymap(style_gains, subset=['gain_loss_val', 'gain_loss_pct', 'day_gain_pct'])
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            return subset

    # Processing Regional Tabs
    regional_data["India"] = render_market("India", t_in)
    regional_data["US"] = render_market("US", t_us)
    regional_data["London"] = render_market("London", t_lon)
    regional_data["Europe"] = render_market("Europe", t_eu)

    # --- SUMMARY TAB ---
    with t_sum:
        st.header("Global Portfolio Summary")
        try:
            rates_df = yf.download(["GBPUSD=X", "GBPINR=X", "GBPEUR=X"], period="1d", progress=False)['Close']
            rates = {"USD": rates_df["GBPUSD=X"].iloc[-1], "INR": rates_df["GBPINR=X"].iloc[-1], "EUR": rates_df["GBPEUR=X"].iloc[-1], "GBP": 1.0}
        except:
            rates = {"USD": 1.3, "INR": 105.0, "EUR": 1.18, "GBP": 1.0}

        summary_rows = []
        for m_name, m_df in regional_data.items():
            if m_df is not None and not m_df.empty:
                code = m_df['curr_code'].iloc[0]
                sym = m_df['curr_sym'].iloc[0]
                
                inv_local = m_df['buy_price'].sum()
                mkt_local = m_df['mkt_val'].sum()
                mkt_gbp = mkt_local / rates[code]
                
                summary_rows.append({
                    "Market": m_name,
                    "Currency": sym,
                    "Invested (Local)": inv_local,
                    "Market Value (Local)": mkt_local,
                    "Market Value (£)": mkt_gbp
                })

        if summary_rows:
            sum_df = pd.DataFrame(summary_rows)
            total_gbp = sum_df['Market Value (£)'].sum()
            sum_df['Allocation %'] = (sum_df['Market Value (£)'] / total_gbp * 100)
            
            # --- SUMMARY TABLE ---
            st.dataframe(sum_df.style.format({
                'Invested (Local)': "{:,.2f}", 
                'Market Value (Local)': "{:,.2f}", 
                'Market Value (£)': "£{:,.2f}", 
                'Allocation %': "{:.2f}%"
            }), use_container_width=True, hide_index=True)

            st.divider()
            
            # --- DONUT PIE CHART ---
            c1, c2 = st.columns([2, 1])
            with c1:
                fig = px.pie(sum_df, values='Market Value (£)', names='Market', 
                             hole=0.5, title="Global Asset Allocation (GBP Value)",
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.metric("Total Portfolio Value", f"£{total_gbp:,.2f}")
                st.write("Allocation calculated based on current live exchange rates.")

    with t_set:
        uploaded = st.file_uploader("Upload portfolio_db.csv", type='csv')
        if uploaded:
            with open(DB_FILE, "wb") as f: f.write(uploaded.getbuffer())
            st.success("File uploaded. Click Refresh.")
else:
    st.info("Portfolio empty. Upload CSV in Settings.")
