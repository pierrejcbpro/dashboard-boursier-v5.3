
# -*- coding: utf-8 -*-
import streamlit as st
from lib import fetch_all_markets

st.set_page_config(page_title="Dash Boursier v5.3 PRO+", layout="wide", initial_sidebar_state="expanded")

st.markdown('''
<style>
:root { --bg:#0f1218; --panel:#1a1f29; --text:#e6e9ef; --muted:#9aa4b2; --acc:#2bb673; --warn:#e6a100; --neg:#e55353;}
.block-container {padding-top: 1rem;}
html, body, [data-testid="stAppViewContainer"] {background: var(--bg); color: var(--text);}
h1, h2, h3 {color: var(--text);}
div[data-testid="stMarkdownContainer"] p {color: var(--muted);}
.stDataFrame {background: var(--panel);}
hr {border: 1px solid #283042;}
.badge {padding:4px 10px; border-radius:12px; font-weight:600; font-size:0.85rem; background:#283042; color:#cbd5e1;}
</style>
''', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Paramètres")
    profil = st.radio("🎯 Profil d’investisseur", ["Agressif","Neutre","Prudent"], index=1)
    if st.button("🔄 Rafraîchir les données"):
        st.cache_data.clear(); st.rerun()
st.session_state["profil"]=profil

st.title("💹 Dash Boursier v5.3 PRO+ — Accueil")
st.caption("IA partout + seuils Entrée/Stop/Objectif (MA20/MA50) + convertisseur LS→Yahoo + profil investisseur.")

try:
    data = fetch_all_markets([("CAC 40",""),("DAX 40",""),("NASDAQ 100",""),("S&P 500",""),("Dow Jones","")], days_hist=30)
    if not data.empty and "pct_1d" in data:
        avg = (data["pct_1d"].mean()*100)
        up = int((data["pct_1d"]>0).sum())
        dn = int((data["pct_1d"]<0).sum())
        st.markdown(f"**Résumé global (Jour)** — Variation moyenne : {avg:.2f}% — {up} hausses / {dn} baisses")
    else:
        st.info("Les données Yahoo Finance sont momentanément indisponibles.")
except Exception as e:
    st.warning(f"Problème de chargement initial: {e}")
