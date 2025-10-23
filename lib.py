
# -*- coding: utf-8 -*-
import os, json, math
import pandas as pd, numpy as np, requests, yfinance as yf
from functools import lru_cache
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer

DATA_DIR = "data"
MAPPING_PATH = os.path.join(DATA_DIR, "id_mapping.json")
UA = {"User-Agent":"Mozilla/5.0"}

os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(MAPPING_PATH):
    with open(MAPPING_PATH,"w",encoding="utf-8") as f: json.dump({}, f)

# VADER
try:
    nltk.data.find("sentiment/vader_lexicon.zip")
except LookupError:
    try: nltk.download("vader_lexicon")
    except Exception: pass
try:
    SIA = SentimentIntensityAnalyzer()
except Exception:
    SIA = None

PROFILE_PARAMS = {
    "Agressif": {"vol_max": 0.08, "target_mult": 1.10, "stop_mult": 0.92, "entry_mult": 0.99},
    "Neutre":   {"vol_max": 0.05, "target_mult": 1.07, "stop_mult": 0.95, "entry_mult": 0.99},
    "Prudent":  {"vol_max": 0.03, "target_mult": 1.05, "stop_mult": 0.97, "entry_mult": 0.995},
}
def get_profile_params(profile: str) -> dict:
    return PROFILE_PARAMS.get(profile or "Neutre", PROFILE_PARAMS["Neutre"])

def load_mapping() -> dict:
    try:
        with open(MAPPING_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
def save_mapping(m: dict):
    with open(MAPPING_PATH,"w",encoding="utf-8") as f: json.dump(m, f, ensure_ascii=False, indent=2)

def _norm(s:str) -> str: return (s or "").strip().upper()

def guess_yahoo_from_ls(ticker: str):
    if not ticker: return None
    t=_norm(ticker)
    if "." in t: return t
    if len(t)<=6 and t.isalnum(): return f"{t}.PA"
    return None

def maybe_guess_yahoo(s: str):
    s=_norm(s)
    m=load_mapping().get(s)
    if m: return m
    return guess_yahoo_from_ls(s)

def resolve_identifier(id_or_ticker: str):
    raw=_norm(id_or_ticker)
    if not raw: return None, {}
    mapping=load_mapping()
    if raw in mapping: return mapping[raw], {"source":"mapping"}
    guess=maybe_guess_yahoo(raw)
    if guess:
        try:
            hist=yf.download(guess, period="5d", interval="1d", progress=False, threads=False)
            if not hist.empty:
                mapping[raw]=guess; save_mapping(mapping)
                return guess, {"source":"heuristic"}
        except Exception: pass
    return None, {}

# Constituents
@lru_cache(maxsize=32)
def _read_tables(url: str):
    html=requests.get(url, headers=UA, timeout=20).text
    return pd.read_html(html)

def _extract_name_ticker(tables):
    table=None
    for df in tables:
        cols={str(c).lower() for c in df.columns}
        if (("company" in cols or "name" in cols) and ("ticker" in cols or "symbol" in cols)):
            table=df.copy(); break
    if table is None: table=tables[0].copy()
    table.rename(columns={c:str(c).lower() for c in table.columns}, inplace=True)
    tcol=next((c for c in table.columns if "ticker" in c or "symbol" in c), table.columns[0])
    ncol=next((c for c in table.columns if "company" in c or "name" in c), table.columns[1])
    out=table[[tcol,ncol]].copy(); out.columns=["ticker","name"]
    out["ticker"]=out["ticker"].astype(str).str.strip()
    return out.dropna().drop_duplicates(subset=["ticker"])

@lru_cache(maxsize=8)
def members_cac40():
    df=_extract_name_ticker(_read_tables("https://en.wikipedia.org/wiki/CAC_40"))
    df["ticker"]=df["ticker"].apply(lambda x: x if "." in x else f"{x}.PA")
    df["index"]="CAC 40"; return df
@lru_cache(maxsize=8)
def members_dax40():
    df=_extract_name_ticker(_read_tables("https://en.wikipedia.org/wiki/DAX"))
    df["ticker"]=df["ticker"].apply(lambda x: x if "." in x else f"{x}.DE")
    df["index"]="DAX 40"; return df
@lru_cache(maxsize=8)
def members_nasdaq100():
    df=_extract_name_ticker(_read_tables("https://en.wikipedia.org/wiki/NASDAQ-100"))
    df["index"]="NASDAQ 100"; return df
@lru_cache(maxsize=8)
def members_sp500():
    df=_extract_name_ticker(_read_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"))
    df["index"]="S&P 500"; return df
@lru_cache(maxsize=8)
def members_dowjones():
    df=_extract_name_ticker(_read_tables("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"))
    df["index"]="Dow Jones"; return df
def members(index_name: str):
    if index_name=="CAC 40": return members_cac40()
    if index_name=="DAX 40": return members_dax40()
    if index_name=="NASDAQ 100": return members_nasdaq100()
    if index_name=="S&P 500": return members_sp500()
    if index_name=="Dow Jones": return members_dowjones()
    return pd.DataFrame(columns=["ticker","name","index"])

# Prices & indicators
from functools import lru_cache as _lc
@_lc(maxsize=64)
def fetch_prices_cached(tickers_tuple: tuple, period="120d"):
    tickers=list(tickers_tuple)
    if not tickers: return pd.DataFrame()
    try:
        data=yf.download(tickers, period=period, interval="1d", auto_adjust=False, group_by="ticker", threads=False, progress=False)
    except Exception:
        return pd.DataFrame()
    if data is None or len(data)==0: return pd.DataFrame()
    frames=[]
    if isinstance(data, pd.DataFrame) and {"Open","High","Low","Close"}.issubset(data.columns):
        df=data.copy(); df["Ticker"]=tickers[0]; frames.append(df)
    else:
        for t in tickers:
            try:
                if t in data and isinstance(data[t], pd.DataFrame):
                    df=data[t].copy(); df["Ticker"]=t; frames.append(df)
            except Exception: continue
    if not frames: return pd.DataFrame()
    out=pd.concat(frames); out.reset_index(inplace=True)
    return out
def fetch_prices(tickers, days=120): return fetch_prices_cached(tuple(tickers), period=f"{days}d")

def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Ticker","Date","Close","ATR14","MA20","MA50","pct_1d","pct_7d","pct_30d"])
    df=df.copy()
    if "Date" not in df.columns:
        df=df.reset_index().rename(columns={df.index.name or "index":"Date"})
    need={"Ticker","Date","High","Low","Close"}
    if need - set(df.columns):
        return pd.DataFrame(columns=["Ticker","Date","Close","ATR14","MA20","MA50","pct_1d","pct_7d","pct_30d"])
    df=df.sort_values(["Ticker","Date"])
    df["PrevClose"]=df.groupby("Ticker")["Close"].shift(1)
    df["TR"]=np.maximum(df["High"]-df["Low"],
                np.maximum((df["High"]-df["PrevClose"]).abs(), (df["Low"]-df["PrevClose"]).abs()))
    df["ATR14"]=df.groupby("Ticker")["TR"].transform(lambda s:s.rolling(14,min_periods=5).mean())
    df["MA20"]=df.groupby("Ticker")["Close"].transform(lambda s:s.rolling(20,min_periods=5).mean())
    df["MA50"]=df.groupby("Ticker")["Close"].transform(lambda s:s.rolling(50,min_periods=10).mean())
    def change(s,n): return (s.iloc[-1]/s.iloc[-(n+1)])-1 if len(s)>n else np.nan
    p1=df.groupby("Ticker")["Close"].apply(lambda x:(x.iloc[-1]/x.iloc[-2])-1 if len(x)>=2 else np.nan).rename("pct_1d")
    p7=df.groupby("Ticker")["Close"].apply(lambda x:change(x,7)).rename("pct_7d")
    p30=df.groupby("Ticker")["Close"].apply(lambda x:change(x,22)).rename("pct_30d")
    last=df.groupby("Ticker").tail(1)[["Ticker","Date","Close","ATR14","MA20","MA50"]]
    out=(last.merge(p1,left_on="Ticker",right_index=True)
              .merge(p7,left_on="Ticker",right_index=True)
              .merge(p30,left_on="Ticker",right_index=True))
    return out.reset_index(drop=True)

# News & IA
@lru_cache(maxsize=256)
def google_news_titles(query: str, lang="fr"):
    url=f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl={lang}-{lang.upper()}&gl={lang.upper()}&ceid={lang.upper()}:{lang.upper()}"
    try:
        xml=requests.get(url, headers=UA, timeout=12).text
        import xml.etree.ElementTree as ET
        root=ET.fromstring(xml)
        items=[]
        for it in root.iter("item"):
            title=it.findtext("title") or ""
            link=it.findtext("link") or ""
            items.append((title, link))
        return items[:6]
    except Exception:
        return []

def news_summary(name: str, ticker: str, lang="fr"):
    items=google_news_titles(f"{name} {ticker}", lang) or google_news_titles(name, lang)
    titles=[t for t,_ in items]
    if not titles:
        return ("Pas d’actualité saillante — mouvement technique / macro.", 0.0, [])
    POS=["résultats","bénéfice","contrat","relève","guidance","record","upgrade","partenariat","dividende","approbation"]
    NEG=["profit warning","retard","procès","amende","downgrade","abaisse","enquête","rappel","départ","incident"]
    scores=[]
    for t in titles:
        s=0.0
        if SIA:
            try: s=SIA.polarity_scores(t.lower())["compound"]
            except Exception: s=0.0
        tl=t.lower()
        if any(k in tl for k in POS): s+=0.2
        if any(k in tl for k in NEG): s-=0.2
        scores.append(s)
    m=float(np.mean(scores)) if scores else 0.0
    if m>0.15: txt="Hausse soutenue par des nouvelles positives."
    elif m<-0.15: txt="Baisse liée à des nouvelles défavorables."
    else: txt="Actualité mitigée/neutre — mouvement surtout technique."
    return (txt, m, items)

def decision_label_from_row(row, held=False, vol_max=0.05):
    px=float(row.get("Close", math.nan))
    ma20=float(row.get("MA20", math.nan)) if pd.notna(row.get("MA20", math.nan)) else math.nan
    ma50=float(row.get("MA50", math.nan)) if pd.notna(row.get("MA50", math.nan)) else math.nan
    atr=float(row.get("ATR14", math.nan)) if pd.notna(row.get("ATR14", math.nan)) else math.nan
    pru=float(row.get("PRU", math.nan)) if "PRU" in row else math.nan
    if not math.isfinite(px): return "👁️ Surveiller"
    vol=(atr/px) if (math.isfinite(atr) and px>0) else 0.03
    trend=(1 if math.isfinite(ma20) and px>=ma20 else 0)+(1 if math.isfinite(ma50) and px>=ma50 else 0)
    score=0.0
    score+=0.4*(1 if trend==2 else 0 if trend==1 else -1)
    if math.isfinite(pru) and pru>0: score+=0.2*(1 if px>pru*1.02 else -1 if px<pru*0.98 else 0)
    score+=0.2*(-1 if vol>vol_max else 1)
    if held:
        if score>0.4: return "🟢 Acheter"
        if score<-0.2: return "🔴 Vendre"
        return "🟠 Garder"
    else:
        if score>0.3: return "🟢 Acheter"
        if score<-0.2: return "🚫 Éviter"
        return "👁️ Surveiller"

def price_levels_from_row(row, profile="Neutre"):
    params = get_profile_params(profile)
    px = float(row.get("Close", math.nan))
    ma20 = float(row.get("MA20", math.nan)) if pd.notna(row.get("MA20", math.nan)) else math.nan
    base = ma20 if math.isfinite(ma20) else px
    if not math.isfinite(base): 
        return {"entry": math.nan, "target": math.nan, "stop": math.nan}
    target = base * params["target_mult"]
    stop   = base * params["stop_mult"]
    entry  = base * params["entry_mult"]
    return {"entry": round(entry,2), "target": round(target,2), "stop": round(stop,2)}

def style_variations(df: pd.DataFrame, cols: list[str]):
    def color_var(v):
        if pd.isna(v): return ""
        if v>0: return "background-color:#14302A; color:#2bd680"
        if v<0: return "background-color:#3A2326; color:#ff7b85"
        return "background-color:#2a313d; color:#cbd5e1"
    sty=df.style
    for c in cols:
        if c in df.columns:
            sty=sty.applymap(color_var, subset=[c])
    return sty

def fetch_all_markets(markets_and_watchlists, days_hist=90) -> pd.DataFrame:
    frames=[]
    for (idx, wl) in markets_and_watchlists:
        mem=members(idx)
        if mem.empty: continue
        px=fetch_prices(mem["ticker"].tolist(), days=days_hist)
        if px.empty: continue
        met=compute_metrics(px).merge(mem, left_on="Ticker", right_on="ticker", how="left")
        met["Indice"]=idx
        frames.append(met)
    if not frames: return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)
