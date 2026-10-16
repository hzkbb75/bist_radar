import os
import io
import re
import json
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# Ortam Değişkenleri
ONEDRIVE_LINK = os.getenv("ONEDRIVE_SHARE_LINK")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# Kritik Bildirim Filtresi (Fiyata etki edebilecek gelişmeler)
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

def fetch_live_kap_feed():
    """Engelsiz ve hızlı Bigpara KAP akışını tarar."""
    url = "https://bigpara.hurriyet.com.tr/kap-haberleri/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    items = []
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"Besleme yanıt kodu: {r.status_code}")
            return items

        soup = BeautifulSoup(r.text, "html.parser")
        
        # KAP haber bloklarını topla
        rows = soup.find_all("li", class_="cell01")
        if not rows:
            rows = soup.select(".kapNewsList li, .newsList li")

        for row in rows:
            link_tag = row.find("a")
            if not link_tag:
                continue

            full_title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            if not href.startswith("http"):
                href = f"https://bigpara.hurriyet.com.tr{href}"

            # Benzersiz kimlik
            disc_id = href.rstrip("/").split("-")[-1].replace("/", "")

            items.append({
                "id": disc_id,
                "title": full_title,
                "link": href
            })

        print(f"Canlı akıştan {len(items)} adet KAP bildirimi başarıyla çekildi.")
    except Exception as e:
        print(f"Haber akışı alınırken hata oluştu: {e}")

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
    disclosures = fetch_live_kap_feed()

    if not disclosures:
        print("Haber listesi boş döndü.")
        return

    for item in disclosures:
        disc_id = item["id"]
        title = item["title"]
        link = item["link"]

        # 1. Açık hisselerimizden birine ait mi?
        eslesen_hisse = None
        for hisse in acik_hisseler:
            # Örn: 'THYAO' ibaresini kelime olarak ara
            if re.search(rf"\b{re.escape(hisse)}\b", title.upper()):
                eslesen_hisse = hisse
                break

        if not eslesen_hisse:
            continue

        print(f"Açık hisseyle eşleşti: {eslesen_hisse} -> {title}")

        # 2. Daha önce iletildi mi?
        if disc_id in sent_ids:
            continue

        # 3. Kritik filtreye uyuyor mu?
        if not is_critical_disclosure(title, ""):
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
                print(f"Webhook hatası: {ex}")

        new_sent_ids.append(disc_id)

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-300:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
