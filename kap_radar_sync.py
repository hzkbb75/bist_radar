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

OSE_CSV_PATH = "ziraat_carpanlar.csv"
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
    "özel durum açıklaması",
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

def get_all_bist_stocks():
    """Ziraat çarpanlar dosyasından tüm BIST hisselerini alır."""
    if not os.path.exists(OSE_CSV_PATH):
        return set()
    try:
        df = pd.read_csv(OSE_CSV_PATH)
        if "Hisse" in df.columns:
            return set(df["Hisse"].dropna().astype(str).str.strip().str.upper())
    except Exception as e:
        print(f"Hisse listesi okuma hatası: {e}")
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

def fetch_kap_general_feed(session):
    """Doğrudan KAP'ın son bildirim akışını çeker (Engellenmeyen genel akış)."""
    url = "https://www.kap.org.tr/tr/api/disclosures"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.kap.org.tr/",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        res = session.post(url, headers=headers, json={}, timeout=15)
        if res.status_code == 200:
            data = res.json()
            sonuclar = []
            for item in data:
                b_id = str(item.get("disclosureIndex") or "")
                stock_codes = item.get("stockCodes") or []
                if not stock_codes and item.get("basic", {}).get("stockCode"):
                    stock_codes = [item["basic"]["stockCode"]]
                
                title = item.get("title") or item.get("disclosureType") or "KAP Bildirimi"
                summary = item.get("summary") or title
                date_str = item.get("publishDate") or datetime.now().strftime("%d.%m.%Y %H:%M")

                for code in stock_codes:
                    if code:
                        sonuclar.append({
                            "id": b_id,
                            "symbol": code.strip().upper(),
                            "title": title,
                            "date": date_str,
                            "summary": summary,
                            "link": f"https://www.kap.org.tr/tr/Bildirim/{b_id}"
                        })
            return sonuclar
    except Exception as e:
        print(f"Genel KAP akışı çekme hatası: {e}")
    return []

def fetch_from_tradingview(session, hisse):
    url = f"https://news-headlines.tradingview.com/v2/headlines?client=web&lang=tr&symbol=BIST%3A{hisse}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
    try:
        res = session.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            items = res.json().get("items", [])
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
    except Exception:
        pass
    return []

def send_to_make(payload):
    if not MAKE_WEBHOOK_URL:
        return False
    try:
        res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=12)
        return res.status_code == 200
    except Exception:
        return False

def filtreye_uyuyor_mu(baslik, ozet):
    birlesik = f"{baslik} {ozet}".lower()
    return any(k in birlesik for k in FILTRE_KELIMELER)

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Birleşik KAP Taraması Başlatıldı.")

    acik_hisseler = get_open_positions()
    tum_bist = get_all_bist_stocks()
    seen_ids = load_seen_ids()
    session = requests.Session()

    # Mevcut birikmiş haberleri korumak için eski dosyayı oku (varsa)
    pbi_haberler = []
    if os.path.exists(KAP_CSV_OUTPUT):
        try:
            df_old = pd.read_csv(KAP_CSV_OUTPUT)
            pbi_haberler = df_old.to_dict("records")
        except Exception:
            pbi_haberler = []

    # 1. Genel KAP Akışını Çek (Tüm BIST bildirimleri tek hamlede gelir)
    print("Genel KAP son bildirimleri taranıyor...")
    genel_bildirimler = fetch_kap_general_feed(session)
    print(f"KAP'tan toplam {len(genel_bildirimler)} bildirim çekildi.")

    yeni_telegram_sayisi = 0

    for item in genel_bildirimler:
        b_id = item["id"]
        sembol = item["symbol"]
        baslik = item["title"]
        zaman = item["date"]
        ozet = item["summary"]
        link = item["link"]

        # Power BI tablosuna ekle
        pbi_haberler.append({
            "Hisse": sembol,
            "Tarih": zaman,
            "Baslik": baslik,
            "Ozet": ozet,
            "KAP_Linki": link
        })

        # Telegram Filtresi: Sadece portföydekiler veya kritik anahtar kelime eşleşenler
        if b_id and b_id not in seen_ids:
            if sembol in acik_hisseler or filtreye_uyuyor_mu(baslik, ozet):
                payload = {
                    "sembol": sembol,
                    "baslik": baslik,
                    "zaman": zaman,
                    "kap_link": link,
                    "ozet": ozet
                }
                if send_to_make(payload):
                    yeni_telegram_sayisi += 1
            seen_ids.add(b_id)

    # 2. Portföydeki Açık Hisselerin TradingView Geçmişini Ekle
    for hisse in acik_hisseler:
        tv_haberler = fetch_from_tradingview(session, hisse)
        for th in tv_haberler:
            pbi_haberler.append({
                "Hisse": th["symbol"],
                "Tarih": th["date"],
                "Baslik": th["title"],
                "Ozet": th["summary"],
                "KAP_Linki": th["link"]
            })

    # 3. CSV Dosyasını Kaydet (Tekrarları temizleyerek en güncel 500 haberi saklar)
    if pbi_haberler:
        df_pbi = pd.DataFrame(pbi_haberler).drop_duplicates(subset=["Hisse", "Baslik"])
        df_pbi = df_pbi.tail(500)
    else:
        df_pbi = pd.DataFrame(columns=["Hisse", "Tarih", "Baslik", "Ozet", "KAP_Linki"])

    df_pbi.to_csv(KAP_CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[Power BI] {len(df_pbi)} adet haber '{KAP_CSV_OUTPUT}' dosyasına yazıldı.")

    save_seen_ids(seen_ids)
    print(f"Tarama bitti. {yeni_telegram_sayisi} kritik bildirim Telegram'a fırlatıldı.")

if __name__ == "__main__":
    main()
