
# -*- coding: utf-8 -*-
import streamlit as st, pandas as pd, numpy as np, os
from lib import (fetch_prices, compute_metrics, decision_label_from_row, resolve_identifier,
                 load_mapping, save_mapping, get_profile_params, style_variations, price_levels_from_row, guess_yahoo_from_ls)

st.title("💼 Mon Portefeuille — Multi-profils, Convertisseur LS→Yahoo & Seuils IA")

profil = st.session_state.get("profil","Neutre")
volmax = get_profile_params(profil)["vol_max"]

st.sidebar.subheader("💾 Portefeuilles")
profile_name = st.sidebar.selectbox("Portefeuille actif", ["PEA","CTO","Global (personnalisé)"], index=0)
PATH=f"data/portfolio_{'PEA' if profile_name=='PEA' else 'CTO' if profile_name=='CTO' else 'GLOBAL'}.json"

if not os.path.exists(PATH):
    pd.DataFrame(columns=["Name","Ticker","Account","Quantity","PRU"]).to_json(PATH, orient="records", indent=2, force_ascii=False)

port = pd.read_json(PATH)

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

st.subheader("Ajouter une ligne")
with st.form("add_line"):
    raw_id = st.text_input("Identifiant (Ticker / ISIN / WKN / alias)", placeholder="Ex: AIR.PA ou US0378331005 ou TOTB")
    account = st.selectbox("Compte", ["PEA","CTO"], index=0)
    qty = st.number_input("Quantité", min_value=0.0, step=1.0, value=0.0)
    pru = st.number_input("PRU (€)", min_value=0.0, step=0.01, value=0.0)
    submitted = st.form_submit_button("Ajouter")
    if submitted:
        tick, meta = resolve_identifier(raw_id)
        if not tick:
            st.warning("Ticker Yahoo introuvable. Indique-le manuellement :")
            tick = st.text_input("Ticker Yahoo (ex: AIR.PA, AAPL, TTE.PA)", key="manual_ticker_add")
            if tick:
                mapping = load_mapping(); mapping[raw_id.upper()] = tick.upper(); save_mapping(mapping)
                st.info("Correspondance enregistrée.")
        if tick:
            import yfinance as yf
            info = {}
            try:
                t = yf.Ticker(tick)
                info = t.get_info() if hasattr(t,"get_info") else t.info
            except Exception:
                info = {}
            name = info.get("shortName") or info.get("longName") or tick
            new_row = {"Name":name, "Ticker":tick.upper(), "Account":account, "Quantity":qty, "PRU":pru}
            port = pd.concat([port, pd.DataFrame([new_row])], ignore_index=True)
            port.to_json(PATH, orient="records", indent=2, force_ascii=False)
            st.success(f"Ligne ajoutée : {name} ({tick})")

st.subheader("Éditeur du portefeuille")
edited = st.data_editor(port, num_rows="dynamic", use_container_width=True, key=f"port_editor_{profile_name}")

c1,c2,c3=st.columns(3)
with c1:
    if st.button("💾 Sauvegarder"):
        edited.to_json(PATH, orient="records", indent=2, force_ascii=False)
        st.success("Sauvegardé.")
with c2:
    if st.button("🗑 Réinitialiser ce portefeuille"):
        if os.path.exists(PATH): os.remove(PATH)
        for k in list(st.session_state.keys()):
            if k.startswith("port_editor_"): del st.session_state[k]
        st.rerun()
with c3:
    if st.button("🔄 Rafraîchir données"):
        st.cache_data.clear(); st.rerun()

if edited.empty:
    st.info("Ajoutez des lignes (Ticker requis)."); st.stop()

tickers = edited["Ticker"].dropna().unique().tolist()
data = fetch_prices(tickers, days=90)
met = compute_metrics(data)
merged = edited.merge(met, on="Ticker", how="left")

rows=[]
for _,r in merged.iterrows():
    px=float(r.get("Close", np.nan)); q=float(r.get("Quantity",0) or 0); pru=float(r.get("PRU", np.nan) or np.nan)
    levels = price_levels_from_row(r, profil)
    val = (px*q) if np.isfinite(px) else 0.0
    perf = ((px-pru)/pru*100) if (np.isfinite(px) and np.isfinite(pru) and pru>0) else np.nan
    dec = decision_label_from_row(r, held=True, vol_max=volmax)
    rows.append({"Compte":r.get("Account",""),"Nom":r.get("Name", r.get("Ticker","")), "Ticker":r.get("Ticker",""),
                 "Cours":round(px,2) if np.isfinite(px) else None, "PRU":pru, "Qté":q, "Valeur":round(val,2),
                 "Perf%":round(perf,2) if np.isfinite(perf) else None, "Entrée (€)":levels["entry"],
                 "Objectif (€)":levels["target"], "Stop (€)":levels["stop"], "Décision IA":dec})
out=pd.DataFrame(rows)

st.subheader("Vue portefeuille")
st.dataframe(style_variations(out, ["Perf%"]), use_container_width=True, hide_index=True)
