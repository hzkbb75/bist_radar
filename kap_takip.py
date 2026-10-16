import os
import io
import re
import json
import requests
import pandas as pd
from datetime import datetime
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# Ortam Değişkenleri
ONEDRIVE_LINK = os.getenv("ONEDRIVE_SHARE_LINK")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")

# Kritik Bildirim Filtresi
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
    """Engelsiz Borsa ve KAP haber akışını çeker."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*"
    })

    items = []
    seen = set()

    # 1. Kaynak: Mynet Finans Borsa RSS Beslemesi
    rss_urls = [
        "https://finans.mynet.com/borsa/rss/",
        "https://finans.mynet.com/haber/rss/kategori/borsa/"
    ]

    for r_url in rss_urls:
        try:
            r = session.get(r_url, timeout=15)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    if title and link not in seen:
                        seen.add(link)
                        items.append({
                            "id": link.rstrip("/").split("/")[-1],
                            "title": title,
                            "link": link
                        })
        except Exception as e:
            print(f"RSS denemesi geçildi ({r_url}): {e}")

    # 2. Kaynak: Mynet KAP Haberleri Mobil Sayfası
    if len(items) == 0:
        try:
            web_url = "https://finans.mynet.com/borsa/haber/kap-haberleri/"
            r = session.get(web_url, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    title = a.get_text(strip=True)
                    if ("/borsa/haber/" in href or "kap" in href.lower()) and len(title) > 15:
                        if not href.startswith("http"):
                            href = f"https://finans.mynet.com{href}"
                        if href not in seen:
                            seen.add(href)
                            items.append({
                                "id": href.rstrip("/").split("/")[-1],
                                "title": title,
                                "link": href
                            })
        except Exception as ex:
            print(f"Web kazıma denemesi geçildi: {ex}")

    print(f"Haber akışından toplam {len(items)} adet güncel piyasa/KAP bildirimi çekildi.")
    if items:
        print("Örnek son haber başlığı:", items[0]["title"])

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
        title_norm = normalize_tr(title)

        # Açık pozisyon hisselerinden biriyle eşleşme kontrolü
        eslesen_hisse = None
        for hisse in acik_hisseler:
            if re.search(rf"\b{re.escape(hisse)}\b", title_norm):
                eslesen_hisse = hisse
                break

        if not eslesen_hisse:
            continue

        eslesen_sayisi += 1
        print(f"Açık hisseyle eşleşti: {eslesen_hisse} -> {title}")

        if disc_id in sent_ids:
            continue

        if not is_critical_disclosure(title):
            print(f"Elenen rutin bildirim: {eslesen_hisse} - {title}")
            new_sent_ids.append(disc_id)
            continue

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

    if eslesen_sayisi == 0:
        print(f"Piyasa akışındaki haberlerde takip edilen {acik_hisseler} koduna ait yeni haber bulunamadı.")

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-300:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
