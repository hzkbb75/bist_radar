import os
import json
import io
import time
import requests
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def get_radar_candidates(limit=35):
    """Ziraat tablosundan veto yememiş en yüksek puanlı hisseleri alır."""
    if not os.path.exists(OSE_CSV_PATH):
        return set()
    try:
        df = pd.read_csv(OSE_CSV_PATH)
        mask = df["Veto_Durum"].astype(str).str.contains("GEÇTİ|GECTI", case=False, na=False)
        df_filtered = df[mask]
        if "OSE_Skor" in df_filtered.columns:
            df_sorted = df_filtered.sort_values(by="OSE_Skor", ascending=False)
            return set(df_sorted["Hisse"].dropna().head(limit).astype(str).str.strip().str.upper())
        return set(df_filtered["Hisse"].dropna().head(limit).astype(str).str.strip().str.upper())
    except Exception as e:
        print(f"Ziraat çarpanlar okuma hatası: {e}")
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
    try:
        res = session.get(url, headers=headers, timeout=8)
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
    except Exception:
        pass
    return []

def fetch_from_tradingview(session, hisse):
    url = f"https://news-headlines.tradingview.com/v2/headlines?lang=tr&symbol=BIST%3A{hisse}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
    try:
        res = session.get(url, headers=headers, timeout=8)
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

def fetch_company_disclosures(hisse):
    session = requests.Session()
    veriler = fetch_from_bigpara(session, hisse)
    if not veriler:
        veriler = fetch_from_tradingview(session, hisse)
    return hisse, veriler

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
    start_time = datetime.now()
    print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] Paralel KAP Taraması Başlatıldı.")

    # 1. Taranacak Hisseler (Açık Pozisyonlar + Radar Liderleri + AKSA)
    aciklar = get_open_positions()
    radar_liderleri = get_radar_candidates(limit=35)
    
    # Test ettiğiniz hisse ve açık portföy her zaman havuzda yer alır
    tum_takip = aciklar.union(radar_liderleri).union({"AKSA"})

    print(f"Toplam Takip Edilen Hisse Sayısı: {len(tum_takip)}")
    print(f"Hisseler: {', '.join(sorted(tum_takip))}")

    seen_ids = load_seen_ids()
    yeni_bildirim_sayisi = 0
    pbi_haber_listesi = []

    # 2. Paralel Tarama (Tüm hisseleri 4-5 saniyede çeker)
    with ThreadPoolExecutor(max_workers=8) as executor:
        gelecek_sonuclar = {executor.submit(fetch_company_disclosures, h): h for h in tum_takip}
        for future in as_completed(gelecek_sonuclar):
            hisse, bildirimler = future.result()
            for item in bildirimler:
                b_id = item["id"]
                sembol = item["symbol"]
                baslik = item["title"]
                zaman = item["date"]
                ozet = item["summary"]
                link = item["link"]

                # A) Power BI için: Filtreye bakılmaksızın tüm son bildirimler eklenir
                pbi_haber_listesi.append({
                    "Hisse": sembol,
                    "Tarih": zaman,
                    "Baslik": baslik,
                    "Ozet": ozet,
                    "KAP_Linki": link
                })

                # B) Telegram için: Yalnızca yeni VE kritik kelime eşleşmesi olanlar gönderilir
                if b_id and b_id not in seen_ids:
                    if filtreye_uyuyor_mu(baslik, ozet):
                        payload = {
                            "sembol": sembol,
                            "baslik": baslik,
                            "zaman": zaman,
                            "kap_link": link,
                            "ozet": ozet
                        }
                        if send_to_make(payload):
                            seen_ids.add(b_id)
                            yeni_bildirim_sayisi += 1
                    else:
                        seen_ids.add(b_id)

    # 3. Power BI CSV Dosyasını Kaydet
    if pbi_haber_listesi:
        df_pbi = pd.DataFrame(pbi_haber_listesi).drop_duplicates(subset=["Hisse", "Baslik"])
    else:
        df_pbi = pd.DataFrame(columns=["Hisse", "Tarih", "Baslik", "Ozet", "KAP_Linki"])

    df_pbi.to_csv(KAP_CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[Power BI] {len(df_pbi)} adet haber '{KAP_CSV_OUTPUT}' dosyasına başarıyla yazıldı.")

    save_seen_ids(seen_ids)
    print(f"Tarama bitti. {yeni_bildirim_sayisi} yeni kritik bildirim Telegram'a fırlatıldı.")

if __name__ == "__main__":
    main()
