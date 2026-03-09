import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import plotly.express as px
import numpy as np
import os

# --- FILE PATH FOR PERSISTENCE ---
DB_FILE = "my_portfolio_data.csv"

# --- INITIALIZATION & PERSISTENCE LOGIC ---
st.set_page_config(layout="wide", page_title="Universal Portfolio Tracker")
mf = Mftool()

def save_data(df):
    """Saves the current portfolio to a local CSV file."""
    df.to_csv(DB_FILE, index=False)

def load_data():
    """Loads the portfolio from the local CSV file if it exists."""
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except Exception:
            return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])
    return pd.DataFrame(columns=['symbol', 'qty', 'avg_price'])

# Load saved data into session state on startup
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_data()

# --- TOP LEVEL SUMMARY ---
# (Indices and logic from the previous step)
# ... [Insert index fetching code here] ...

# --- MODIFIED TABS & ACTIONS ---
tabs = st.tabs(["📊 Dashboard", "📤 Bulk Upload"])

with tabs[1]:
    st.header("Bulk Upload")
    file = st.file_uploader("Upload CSV/Excel (Adds to existing holdings)", type=['csv', 'xlsx'])
    if file:
        raw_df = pd.read_csv(file) if file.name.endswith('csv') else pd.read_excel(file)
        # Assuming your clean_and_map_broker function is present
        cleaned = clean_and_map_broker(raw_df) 
        if not cleaned.empty:
            # Merge with existing data
            combined = pd.concat([st.session_state.portfolio, cleaned])
            st.session_state.portfolio = combined.groupby('symbol').agg({'qty': 'sum', 'avg_price': 'mean'}).reset_index()
            
            # CRITICAL: Save to system immediately
            save_data(st.session_state.portfolio)
            st.success("✅ Portfolio Updated and Saved to System!")

with tabs[0]:
    # ... [Insert Dashboard logic] ...
    
    # Inside the "Action" column button logic:
    if st.button("🗑️", key=f"del_{i}"):
        st.session_state.portfolio = st.session_state.portfolio.drop(i).reset_index(drop=True)
        # CRITICAL: Update the saved file after deletion
        save_data(st.session_state.portfolio)
        st.rerun()
