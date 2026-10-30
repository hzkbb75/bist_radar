import os
import json
import io
import time
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# ==========================================
MAKE_WEBHOOK_URL = (
    os.getenv("MAKE_WEBHOOK_URL") 
    or "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j"
)
ONEDRIVE_EXCEL_URL = (
    os.getenv("ONEDRIVE_EXCEL_URL") 
    or "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJO2pbYOw?e=Obf4U8"
)

# OSE motorunun ürettiği güncel veri tablosu ve durum dosyaları
OSE_CSV_PATH = "ziraat_carpanlar.csv"   # veya GitHub deponuzdaki tam yolu
KAP_CSV_OUTPUT = "kap_haberler.csv"
STATE_FILE = "son_bildirimler.json"

FILTRE_KELIMELER = [
    "yeni iş ilişkisi",
    "sözleşme",
    "ihale",
    "sipariş",
    "finansal rapor",
    "faaliyet raporu",
    "sorumluluk beyanı",
    "sermaye artırımı",
    "bedelli",
    "bedelsiz",
    "kâr payı",
    "temettü",
    "geri alım",
    "pay alım satım",
    "özel durum açıklaması (genel)",
    "yatırım",
    "birleşme",
    "devralma"
]

def download_excel_file(url):
    session = requests.Session()
    target_url = url if "download=1" in url else f"{url}&download=1"
    try:
        res = session.get(target_url, allow_redirects=True, timeout=25)
        if "view.aspx" in res.url:
            direct_url = res.url.replace("view.aspx", "download.aspx")
            res = session.get(direct_url, timeout=25)
        if res.content.startswith(b'PK'):
            return res.content
        live_download_url = "https://onedrive.live.com/download?cid=CB9E9D1C772EF382&resid=CB9E9D1C772EF382!s4cf55af6200c480e929aeaeafbd84749"
        res_live = session.get(live_download_url, allow_redirects=True, timeout=25)
        if res_live.content.startswith(b'PK'):
            return res_live.content
    except Exception as e:
        print(f"Excel indirme hatası: {e}")
    return None

def get_open_positions():
    """OneDrive Excel'den durumu AÇIK olan hisseleri çeker."""
    try:
        content = download_excel_file(ONEDRIVE_EXCEL_URL)
        if not content:
            return set()
        excel_file = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
        target_sheet = next((s for s in excel_file.sheet_names if "İŞLEM" in s.upper() or "ISLEM" in s.upper()), excel_file.sheet_names[0])
        df = pd.read_excel(excel_file, sheet_name=target_sheet)
        df.columns = [str(c).strip() for c in df.columns]

        hisse_col = next((c for c in df.columns if c.upper() in ["HİSSE", "HISSE", "SEMBOL", "KOD"]), None)
        durum_col = next((c for c in df.columns if "DURUM" in c.upper()), None)

        if not hisse_col:
            return set()

        if durum_col:
            df_acik = df[df[durum_col].astype(str).str.strip().str.upper().isin(["AÇIK", "ACIK"])]
            semboller = set(df_acik[hisse_col].dropna().astype(str).str.strip().str.upper())
        else:
            semboller = set(df[hisse_col].dropna().astype(str).str.strip().str.upper())

        return {s for s in semboller if s and s != "NAN"}
    except Exception as e:
        print(f"OneDrive okuma hatası: {e}")
        return set()

def get_top_ose_stocks(limit=15):
    """OSE Motorundan çıkan 'Çekirdek' hisseleri izleme listesine ekler."""
    if not os.path.exists(OSE_CSV_PATH):
        return set()
    try:
        df = pd.read_csv(OSE_CSV_PATH)
        # Veto yememiş ve Portfoy_Statusu Çekirdek olanlar veya en yüksek OSE skoru alanlar
        mask = (df["Veto_Durum"].astype(str).str.contains("GEÇTİ|GECTI", case=False, na=False))
        df_filtered = df[mask]
        
        if "OSE_Skor" in df_filtered.columns:
            df_sorted = df_filtered.sort_values(by="OSE_Skor", ascending=False)
            top_stocks = set(df_sorted["Hisse"].dropna().head(limit).astype(str).str.strip().str.upper())
            return top_stocks
    except Exception as e:
        print(f"OSE CSV okuma hatası: {e}")
    return set()

def load_seen_ids():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_ids(seen_ids):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids)[-1000:], f, ensure_ascii=False, indent=2)

def fetch_from_bigpara(session, hisse):
    url = f"https://bigpara.hurriyet.com.tr/api/v1/hisse/kaphaberleri/{hisse}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://bigpara.hurriyet.com.tr/"
    }
    res = session.get(url, headers=headers, timeout=12)
    if res.status_code == 200:
        data = res.json()
        raw_list = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        sonuclar = []
        for d in raw_list:
            b_id = str(d.get("id") or d.get("disclosureIndex") or "")
            if not b_id:
                continue
            sonuclar.append({
                "id": b_id,
                "symbol": hisse,
                "title": d.get("title") or d.get("baslik") or "KAP Bildirimi",
                "date": d.get("date") or d.get("tarih") or datetime.now().strftime("%d.%m.%Y %H:%M"),
                "summary": d.get("spot") or d.get("ozet") or d.get("title") or "",
                "link": d.get("url") or f"https://www.kap.org.tr/tr/Bildirim/{b_id}"
            })
        return sonuclar
    return []

def fetch_from_tradingview(session, hisse):
    url = f"https://news-headlines.tradingview.com/v2/headlines?lang=tr&symbol=BIST%3A{hisse}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
    res = session.get(url, headers=headers, timeout=12)
    if res.status_code == 200:
        data = res.json()
        items = data.get("items", []) if isinstance(data, dict) else []
        sonuclar = []
        for it in items:
            b_id = str(it.get("id") or "")
            pub_ts = it.get("published")
            pub_str = datetime.fromtimestamp(pub_ts).strftime("%d.%m.%Y %H:%M") if pub_ts else datetime.now().strftime("%d.%m.%Y %H:%M")
            link = it.get("link") or (f"https://www.tradingview.com{it.get('storyPath')}" if it.get("storyPath") else "")
            sonuclar.append({
                "id": b_id,
                "symbol": hisse,
                "title": it.get("title") or "KAP Bildirimi",
                "date": pub_str,
                "summary": it.get("shortDescription") or it.get("title") or "",
                "link": link
            })
        return sonuclar
    return []

def fetch_company_disclosures(session, hisse):
    try:
        veriler = fetch_from_bigpara(session, hisse)
        if veriler:
            return veriler
    except Exception:
        pass
    try:
        veriler = fetch_from_tradingview(session, hisse)
        if veriler:
            return veriler
    except Exception:
        pass
    return []

def send_to_make(payload):
    if not MAKE_WEBHOOK_URL:
        return False
    try:
        res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=15)
        return res.status_code == 200
    except Exception:
        return False

def filtreye_uyuyor_mu(baslik, ozet):
    if not FILTRE_KELIMELER:
        return True
    birlesik = f"{baslik} {ozet}".lower()
    return any(k in birlesik for k in FILTRE_KELIMELER)

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Birleşik KAP Taraması Başlatıldı.")

    # 1. Takip Listesi Oluşturma (Açık Pozisyonlar + OSE Liderleri)
    acik_hisseler = get_open_positions()
    ose_liderleri = get_top_ose_stocks(limit=15)
    tum_takip = acik_hisseler.union(ose_liderleri)

    if not tum_takip:
        print("Takip edilecek hisse bulunamadı.")
        return

    print(f"Toplam Takip Edilen Hisse Sayısı: {len(tum_takip)}")
    print(f"Hisseler: {', '.join(sorted(tum_takip))}")

    seen_ids = load_seen_ids()
    session = requests.Session()
    yeni_bildirim_sayisi = 0
    
    # Power BI için toplanan tüm geçerli haber havuzu
    pbi_haber_listesi = []

    for hisse in tum_takip:
        bildirimler = fetch_company_disclosures(session, hisse)
        for item in bildirimler:
            bildirim_id = str(item.get("id") or "")
            sembol = str(item.get("symbol") or hisse).strip().upper()
            baslik = item.get("title") or "KAP Bildirimi"
            zaman = item.get("date") or datetime.now().strftime("%d.%m.%Y %H:%M")
            ozet = str(item.get("summary") or baslik).strip()
            link = item.get("link") or f"https://www.kap.org.tr/tr/Bildirim/{bildirim_id}"

            if filtreye_uyuyor_mu(baslik, ozet):
                # Power BI tablosuna her zaman ekle (tarihsel arşiv)
                pbi_haber_listesi.append({
                    "Hisse": sembol,
                    "Tarih": zaman,
                    "Baslik": baslik,
                    "Ozet": ozet,
                    "KAP_Linki": link
                })

                # Yeni ise Make.com / Telegram'a ilet
                if bildirim_id and bildirim_id not in seen_ids:
                    payload = {
                        "sembol": sembol,
                        "baslik": baslik,
                        "zaman": zaman,
                        "kap_link": link,
                        "ozet": ozet
                    }
                    if send_to_make(payload):
                        seen_ids.add(bildirim_id)
                        yeni_bildirim_sayisi += 1
            else:
                if bildirim_id:
                    seen_ids.add(bildirim_id)

    # 2. Power BI için CSV Kaydetme
    # 2. Power BI için CSV Kaydetme (Haber olmasa bile dosya boş şablonla oluşsun)
    if pbi_haber_listesi:
        df_pbi = pd.DataFrame(pbi_haber_listesi).drop_duplicates(subset=["Hisse", "Baslik"])
    else:
        df_pbi = pd.DataFrame(columns=["Hisse", "Tarih", "Baslik", "Ozet", "KAP_Linki"])

    df_pbi.to_csv(KAP_CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[Power BI] {len(df_pbi)} adet haber '{KAP_CSV_OUTPUT}' dosyasına yazıldı.")

    save_seen_ids(seen_ids)
    print(f"Tarama bitti. {yeni_bildirim_sayisi} yeni bildirim Telegram'a fırlatıldı.")

if __name__ == "__main__":
    main()
