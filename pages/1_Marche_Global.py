
# -*- coding: utf-8 -*-
import streamlit as st, pandas as pd, numpy as np, altair as alt
from lib import fetch_all_markets, news_summary, decision_label_from_row, style_variations, get_profile_params, price_levels_from_row

st.title("🌍 Marché Global — Résumé IA & Top/Low (avec seuils)")

profil = st.session_state.get("profil","Neutre")
volmax = get_profile_params(profil)["vol_max"]

periode = st.radio("Période", ["Jour","7 jours","30 jours"], index=0, horizontal=True)
days_hist = {"Jour":60,"7 jours":90,"30 jours":150}[periode]
value_col = {"Jour":"pct_1d","7 jours":"pct_7d","30 jours":"pct_30d"}[periode]

if st.sidebar.button("🔄 Rafraîchir cette page"):
    st.cache_data.clear(); st.rerun()

MARKETS_AND_WL=[("CAC 40",""),("DAX 40",""),("NASDAQ 100",""),("S&P 500",""),("Dow Jones","")]
data = fetch_all_markets(MARKETS_AND_WL, days_hist=days_hist)
if data.empty: st.warning("Aucune donnée disponible."); st.stop()
if value_col not in data.columns: st.warning("Pas de variations calculables."); st.stop()

valid=data.dropna(subset=[value_col]).copy()
avg = valid[value_col].mean()*100
up = int((valid[value_col]>0).sum())
dn = int((valid[value_col]<0).sum())
st.markdown(f"**Résumé global ({periode})** — Variation moyenne : {avg:.2f}% — {up} hausses / {dn} baisses")

top=valid.sort_values(value_col, ascending=False).head(5)
low=valid.sort_values(value_col, ascending=True).head(5)

def bar(df, title):
    d=df.copy()
    d["Name"]=d.get("name", d.get("Ticker","")).astype(str)
    d["pct"]=d[value_col]*100
    d["color"]=np.where(d["pct"]>=0,"Hausses","Baisses")
    ch=alt.Chart(d).mark_bar().encode(
        x=alt.X("Name:N", sort="-y", title="Société"),
        y=alt.Y("pct:Q", title="Variation (%)"),
        color=alt.Color("color:N", scale=alt.Scale(domain=["Hausses","Baisses"], range=["#2bb673","#e55353"]), legend=None),
        tooltip=["Name","Ticker",alt.Tooltip("pct",format=".2f")]
    ).properties(title=title, height=300)
    st.altair_chart(ch, use_container_width=True)

c1,c2=st.columns(2)
with c1: bar(top, "Top 5 hausses")
with c2: bar(low, "Top 5 baisses")

def table_ai(df):
    rows=[]
    for _,r in df.iterrows():
        name=r.get("name", r.get("Ticker"))
        tick=r.get("Ticker","")
        levels=price_levels_from_row(r, profil)
        txt,score,_=news_summary(str(name), tick)
        dec=decision_label_from_row(r, held=False, vol_max=volmax)
        rows.append({"Nom":name,"Ticker":tick,"Var%":round((r.get(value_col,0) or 0)*100,2),
                     "Entrée (€)":levels["entry"],"Objectif (€)":levels["target"],"Stop (€)":levels["stop"],
                     "Décision IA":dec,"Actu (résumé)":txt,"Sentiment":round(score,2)})
    return pd.DataFrame(rows)

st.subheader("Analyses IA — Top")
df_top = table_ai(top)
st.dataframe(style_variations(df_top, ["Var%","Sentiment"]), use_container_width=True, hide_index=True)
st.subheader("Analyses IA — Low")
df_low = table_ai(low)
st.dataframe(style_variations(df_low, ["Var%","Sentiment"]), use_container_width=True, hide_index=True)
