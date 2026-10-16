import os
import io
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

# Ortam Değişkenleri
ONEDRIVE_LINK = os.getenv("ONEDRIVE_SHARE_LINK")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# Kritik Bildirim Filtresi (Rutin bürokratik evrakları eler)
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # Doğrudan indirme parametresi ekleme
    separator = "&" if "?" in sharing_url else "?"
    download_url = f"{sharing_url}{separator}download=1" if "download=1" not in sharing_url else sharing_url

    resp = session.get(download_url, allow_redirects=True, timeout=30)
    resp.raise_for_status()

    # Eğer önizleme web sayfasına yönlendirildiyse download.aspx'e çevir
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

    acik_mask = df["Pozisyon Durumu"].astype(str).str.strip().str.upper() == "AÇIK"
    acik_hisseler = df.loc[acik_mask, "Hisse"].dropna().unique().tolist()
    return [str(h).strip().upper() for h in acik_hisseler]

def is_critical_disclosure(title, summary):
    """Bildirim başlığı veya özetinde kritik anahtar kelimeler var mı denetler."""
    metin = f"{title} {summary}".upper()
    return any(kelime in metin for kelime in KRITIK_KATEGORILER)

def run_kap_scanner():
    acik_hisseler = get_open_positions()
    print(f"Takip Edilen Açık Pozisyonlar: {acik_hisseler}")

    if not acik_hisseler:
        print("Portföyde açık hisse bulunamadı veya liste boş. Tarama tamamlandı.")
        return

    # Gönderilmiş bildirimlerin hafızası (Mükerrer önleme)
    cache_file = "son_bildirimler.json"
    sent_ids = []
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            try:
                sent_ids = json.load(f)
            except Exception:
                sent_ids = []

    new_sent_ids = list(sent_ids)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # Son 3 günün aralığı
    from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")

    for hisse in acik_hisseler:
        print(f"--- {hisse} taranıyor ---")
        api_url = "https://www.kap.org.tr/tr/api/disclosures"
        params = {
            "stockCodes": hisse,
            "fromDate": from_date,
            "toDate": to_date
        }

        try:
            r = requests.get(api_url, params=params, headers=headers, timeout=20)
            disclosures = r.json()
        except Exception as e:
            print(f"{hisse} API hatası: {e}")
            continue

        for item in disclosures:
            disclosure_id = str(item.get("disclosureId"))
            title = item.get("title", "")
            summary = item.get("summary", "")

            # 1. Kontrol: Daha önce işlendi mi?
            if disclosure_id in sent_ids:
                continue

            # 2. Kontrol: Kritik başlık mı?
            if not is_critical_disclosure(title, summary):
                print(f"Elenen rutin bildirim: {hisse} - {title}")
                new_sent_ids.append(disclosure_id)
                continue

            # Kritik bildirim yakalandı -> Make.com'a gönder
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
                    requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=10)
                    print(f"KRİTİK BİLDİRİM İLETİLDİ: {hisse} - {title}")
                except Exception as ex:
                    print(f"Webhook gönderim hatası: {ex}")

            new_sent_ids.append(disclosure_id)

    # Son 200 bildirimi yerel dosyaya kaydet
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-200:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
