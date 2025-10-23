
# -*- coding: utf-8 -*-
import streamlit as st, pandas as pd, altair as alt, numpy as np, yfinance as yf
from lib import (resolve_identifier, load_mapping, save_mapping, compute_metrics, news_summary,
                 decision_label_from_row, get_profile_params, price_levels_from_row, guess_yahoo_from_ls)

st.title("🔎 Recherche Universelle (Nom / Ticker / ISIN / WKN) — avec seuils & MA")

profil = st.session_state.get("profil","Neutre")
volmax = get_profile_params(profil)["vol_max"]

st.subheader("🔁 Convertisseur LS Exchange → Yahoo")
ls = st.text_input("Ticker LS (ex: AIR, ORA, MC, TTE, BN)")
if ls:
    guess = guess_yahoo_from_ls(ls) or ""
    st.write(f"Proposition : **{guess or '—'}**")
    if st.button("✅ Enregistrer cette correspondance"):
        if guess:
            m = load_mapping(); m[ls.upper()] = guess; save_mapping(m)
            st.success(f"Association enregistrée : {ls.upper()} → {guess}")
        else:
            st.warning("Aucune proposition valable.")

raw = st.text_input("Identifiant (ex: AIR.PA, AAPL, US0378331005, TOTB)").strip().upper()
if not raw: st.stop()

tick, meta = resolve_identifier(raw)
if not tick:
    st.warning("Identifiant non reconnu automatiquement.")
    manual = st.text_input("Indiquez le ticker Yahoo à associer :", key="manual_search")
    if manual:
        mapping = load_mapping(); mapping[raw] = manual.upper(); save_mapping(mapping)
        tick = manual.upper()
        st.success(f"Association enregistrée : {raw} → {tick}")

if not tick: st.stop()

st.info(f"Analyse de **{tick}**")

try:
    h = yf.download(tick, period="70d", interval="1d", auto_adjust=False, progress=False)
except Exception as e:
    st.error(f"Impossible de récupérer l'historique: {e}"); st.stop()
if h.empty:
    st.warning("Aucune donnée pour ce ticker."); st.stop()

d = h.tail(30).copy().reset_index()
d["MA20"] = d["Close"].rolling(20, min_periods=5).mean()
d["MA50"] = d["Close"].rolling(50, min_periods=10).mean()

m = compute_metrics(h.assign(Ticker=tick))
if not m.empty:
    row = m.tail(1).iloc[0]
else:
    row = pd.Series({"Close": float(d["Close"].iloc[-1]) if not d.empty else np.nan, "MA20": float(d["MA20"].iloc[-1]) if not d["MA20"].isna().all() else np.nan})

levels = price_levels_from_row(row, profil)
entry, target, stop = levels["entry"], levels["target"], levels["stop"]

base = alt.Chart(d).mark_line(color="#2bb673").encode(
    x=alt.X("Date:T", title=""), y=alt.Y("Close:Q", title="Cours"),
    tooltip=["Date:T","Close:Q"]
).properties(title=f"{tick} — 30 jours", height=340)
ma20_line = alt.Chart(d).mark_line(color="#4FC3F7").encode(x="Date:T", y="MA20:Q")
ma50_line = alt.Chart(d).mark_line(color="#81D4FA").encode(x="Date:T", y="MA50:Q")
entry_line = alt.Chart(pd.DataFrame({"y":[entry]})).mark_rule(color="#e6a100").encode(y="y:Q")
target_line = alt.Chart(pd.DataFrame({"y":[target]})).mark_rule(color="#2bb673").encode(y="y:Q")
stop_line = alt.Chart(pd.DataFrame({"y":[stop]})).mark_rule(color="#e55353").encode(y="y:Q")
st.altair_chart(base + ma20_line + ma50_line + entry_line + target_line + stop_line, use_container_width=True)

st.markdown(f"**Seuils IA ({profil})** — 📈 Entrée: **{entry} €** · 🎯 Objectif: **{target} €** · 🛑 Stop: **{stop} €**")

txt,score,items = news_summary(tick, tick)
dec = decision_label_from_row(row, held=False, vol_max=volmax)
st.subheader("Analyse IA")
st.write(f"**Décision** : {dec} — Sentiment: {score:+.2f}")
st.write(f"Actu: {txt}")
st.subheader("📰 Articles")
if items:
    for t,u in items[:5]:
        st.markdown(f"- [{t}]({u})")
else:
    st.caption("Aucune actualité saillante.")
