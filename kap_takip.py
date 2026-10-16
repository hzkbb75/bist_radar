import os
import io
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# Ortam Değişkenleri
ONEDRIVE_LINK = os.getenv("ONEDRIVE_SHARE_LINK")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# Kritik Bildirim Filtresi
KRITIK_KATEGORILER = [
    "YENİ İŞ İLİŞKİSİ",
    "FİNANSAL DURAN VARLIK",
    "ÖZEL DURUM AÇIKLAMASI",
    "İHALE",
    "PAY ALIM SATIM",
    "SERMAYE ARTIRIMI",
    "TEMETTÜ",
    "KAR PAYI",
    "YATIRIM TEŞVİK",
    "KAPASİTE ARTIŞI"
]

def download_excel_file(sharing_url):
    """OneDrive linkini doğrudan indirilebilir dosya akışına çevirir."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })

    separator = "&" if "?" in sharing_url else "?"
    download_url = f"{sharing_url}{separator}download=1" if "download=1" not in sharing_url else sharing_url

    resp = session.get(download_url, allow_redirects=True, timeout=30)
    resp.raise_for_status()

    if "html" in resp.headers.get("Content-Type", "").lower() and "view.aspx" in resp.url:
        direct_url = resp.url.replace("view.aspx", "download.aspx")
        resp = session.get(direct_url, allow_redirects=True, timeout=30)
        resp.raise_for_status()

    return resp.content

def get_open_positions():
    """Excel İşlem_Günlüğü sayfasından AÇIK hisseleri çeker."""
    if not ONEDRIVE_LINK:
        print("HATA: ONEDRIVE_SHARE_LINK tanımlanmamış.")
        return []

    content = download_excel_file(ONEDRIVE_LINK)
    excel_file = io.BytesIO(content)
    df = pd.read_excel(excel_file, sheet_name="İşlem_Günlüğü", engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    print(f"Excel toplam satır sayısı: {len(df)}")
    if "Hisse" in df.columns and "Pozisyon Durumu" in df.columns:
        print("Excel'den okunan ilk kayıtlar:")
        print(df[["Hisse", "Pozisyon Durumu"]].dropna(how="all").head())

    def durum_acik_mi(deger):
        val = str(deger).strip().upper().replace("İ", "I").replace("Ç", "C")
        return "ACIK" in val

    acik_mask = df["Pozisyon Durumu"].apply(durum_acik_mi)
    acik_hisseler = df.loc[acik_mask, "Hisse"].dropna().unique().tolist()
    return [str(h).strip().upper() for h in acik_hisseler]

def is_critical_disclosure(title, summary):
    """Bildirim başlığı veya özetinde kritik anahtar kelimeler var mı denetler."""
    metin = f"{title} {summary}".upper()
    return any(kelime in metin for kelime in KRITIK_KATEGORILER)

def fetch_kap_disclosures(session, hisse, from_date, to_date):
    """KAP API'sini zaman aşımına karşı 2 deneme ile güvenli sorgular."""
    api_url = "https://www.kap.org.tr/tr/api/disclosures"
    params = {
        "stockCodes": hisse,
        "fromDate": from_date,
        "toDate": to_date
    }
    
    for attempt in range(1, 3):
        try:
            r = session.get(api_url, params=params, timeout=40)
            if r.status_code == 200:
                return r.json()
            print(f"{hisse} KAP yanıt kodu: {r.status_code} (Deneme {attempt})")
        except requests.exceptions.RequestException as e:
            print(f"{hisse} istek gecikmesi (Deneme {attempt}/2): {e}")
            time.sleep(2)
    return []

def run_kap_scanner():
    acik_hisseler = get_open_positions()
    print(f"Takip Edilen Açık Pozisyonlar: {acik_hisseler}")

    if not acik_hisseler:
        print("Portföyde açık hisse bulunamadı veya liste boş. Tarama tamamlandı.")
        return

    cache_file = "son_bildirimler.json"
    sent_ids = []
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            try:
                sent_ids = json.load(f)
            except Exception:
                sent_ids = []

    new_sent_ids = list(sent_ids)

    # KAP sunucusunun bot filtresine takılmamak için gerçek tarayıcı oturumu
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.kap.org.tr/",
        "Connection": "keep-alive"
    })
    
    from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")

    for hisse in acik_hisseler:
        print(f"--- {hisse} taranıyor ---")
        disclosures = fetch_kap_disclosures(session, hisse, from_date, to_date)
        print(f"{hisse} için bulunan toplam bildirim sayısı: {len(disclosures)}")

        for item in disclosures:
            disclosure_id = str(item.get("disclosureId"))
            title = item.get("title", "")
            summary = item.get("summary", "")

            if disclosure_id in sent_ids:
                continue

            if not is_critical_disclosure(title, summary):
                print(f"Elenen rutin bildirim: {hisse} - {title}")
                new_sent_ids.append(disclosure_id)
                continue

            payload = {
                "disclosure_id": disclosure_id,
                "sembol": hisse,
                "baslik": title,
                "ozet": summary,
                "kap_link": f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
                "zaman": datetime.now().strftime("%Y-%m-%d %H:%M")
            }

            if MAKE_WEBHOOK_URL:
                try:
                    requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=15)
                    print(f"KRİTİK BİLDİRİM İLETİLDİ: {hisse} - {title}")
                except Exception as ex:
                    print(f"Webhook gönderim hatası: {ex}")

            new_sent_ids.append(disclosure_id)

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-200:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
