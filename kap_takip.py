import os
import io
import re
import json
import requests
import pandas as pd
from datetime import datetime

# Ortam Değişkenleri
ONEDRIVE_LINK = os.getenv("ONEDRIVE_SHARE_LINK")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# Türkçe karakter uyumlu kritik kategori listesi
KRITIK_KATEGORILER = [
    "YENI IS ILISKISI",
    "FINANSAL DURAN VARLIK",
    "OZEL DURUM ACIKLAMASI",
    "IHALE",
    "PAY ALIM SATIM",
    "SERMAYE ARTIRIMI",
    "TEMETTU",
    "KAR PAYI",
    "YATIRIM TESVIK",
    "KAPASITE ARTISI"
]

def normalize_tr(metin):
    """Türkçe karakterleri güvenli büyük harfe çevirir."""
    if not metin:
        return ""
    text = str(metin)
    tr_map = {
        "İ": "I", "ı": "I", "i": "I",
        "ğ": "G", "Ğ": "G",
        "ü": "U", "Ü": "U",
        "ş": "S", "Ş": "S",
        "ö": "O", "Ö": "O",
        "ç": "C", "Ç": "C"
    }
    for k, v in tr_map.items():
        text = text.replace(k, v)
    return text.upper()

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

    def durum_acik_mi(deger):
        val = normalize_tr(deger)
        return "ACIK" in val

    acik_mask = df["Pozisyon Durumu"].apply(durum_acik_mi)
    acik_hisseler = df.loc[acik_mask, "Hisse"].dropna().unique().tolist()
    return [normalize_tr(h).strip() for h in acik_hisseler]

def is_critical_disclosure(title):
    """Bildirim başlığında kritik anahtar kelimeler var mı denetler."""
    norm = normalize_tr(title)
    return any(kelime in norm for kelime in KRITIK_KATEGORILER)

def fetch_live_kap_disclosures():
    """Engelsiz Mynet Finans anlık KAP JSON API akışından bildirimleri çeker."""
    url = "https://finans.mynet.com/borsa/haber/kap-haberleri/api/list"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://finans.mynet.com/borsa/haber/kap-haberleri/"
    }
    
    items = []
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            raw_items = data.get("data", []) if isinstance(data, dict) else data
            
            for d in raw_items:
                disc_id = str(d.get("id") or d.get("kapId") or d.get("disclosureId") or "")
                title = d.get("title") or d.get("header") or d.get("subject") or ""
                stock = d.get("stockCode") or d.get("code") or ""
                link = d.get("url") or f"https://www.kap.org.tr/tr/Bildirim/{disc_id}"
                
                if title:
                    items.append({
                        "id": disc_id if disc_id else title,
                        "title": title,
                        "stock": normalize_tr(stock),
                        "link": link
                    })
            print(f"Canlı API üzerinden {len(items)} adet KAP bildirimi başarıyla çekildi.")
            if items:
                print("Son bildirim örneği:", items[0]["title"])
            return items
    except Exception as e:
        print(f"Mynet API çağrısında hata: {e}")

    # Alternatif Açık Uç Nokta (Yedek Besleme)
    try:
        alt_url = "https://bigpara.hurriyet.com.tr/api/v1/kap/news"
        r = requests.get(alt_url, headers=headers, timeout=20)
        if r.status_code == 200:
            alt_data = r.json().get("data", [])
            for d in alt_data:
                items.append({
                    "id": str(d.get("id", "")),
                    "title": d.get("title", ""),
                    "stock": normalize_tr(d.get("stockCode", "")),
                    "link": d.get("url", "")
                })
            print(f"Yedek API üzerinden {len(items)} adet KAP bildirimi çekildi.")
            return items
    except Exception as ex:
        print(f"Yedek API hatası: {ex}")

    return items

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
    disclosures = fetch_live_kap_disclosures()

    if not disclosures:
        print("Haber akışından bildirim alınamadı.")
        return

    eslesen_sayisi = 0
    for item in disclosures:
        disc_id = str(item["id"])
        title = item["title"]
        link = item["link"]
        item_stock = item["stock"]
        title_norm = normalize_tr(title)

        # 1. Açık hisselerden biriyle eşleşme kontrolü
        eslesen_hisse = None
        for hisse in acik_hisseler:
            if (item_stock and hisse == item_stock) or re.search(rf"\b{re.escape(hisse)}\b", title_norm):
                eslesen_hisse = hisse
                break

        if not eslesen_hisse:
            continue

        eslesen_sayisi += 1
        print(f"Açık hisseyle eşleşti: {eslesen_hisse} -> {title}")

        # 2. Mükerrer kontrolü
        if disc_id in sent_ids:
            continue

        # 3. Kritik filtre denetimi
        if not is_critical_disclosure(title):
            print(f"Elenen rutin bildirim: {eslesen_hisse} - {title}")
            new_sent_ids.append(disc_id)
            continue

        # 4. Make.com Webhook iletimi
        payload = {
            "disclosure_id": disc_id,
            "sembol": eslesen_hisse,
            "baslik": title,
            "ozet": title,
            "kap_link": link,
            "zaman": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        if MAKE_WEBHOOK_URL:
            try:
                requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=15)
                print(f"KRİTİK BİLDİRİM İLETİLDİ: {eslesen_hisse} - {title}")
            except Exception as ex:
                print(f"Webhook gönderim hatası: {ex}")

        new_sent_ids.append(disc_id)

    if eslesen_sayisi == 0:
        print(f"Canlı akıştaki bildirimlerde takip edilen {acik_hisseler} hisselerine ait haber bulunamadı.")

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-300:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
