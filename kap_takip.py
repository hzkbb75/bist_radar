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

def fetch_live_kap_feed():
    """Bigpara KAP akışını etiket bağımsız genel link ve tablo taramasıyla çeker."""
    url = "https://bigpara.hurriyet.com.tr/kap-haberleri/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    items = []
    seen = set()

    try:
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # 1. Yöntem: Sayfadaki tüm KAP haber bağlantılarını tara
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            
            # Sadece haber linklerini al, ana menü veya genel kategori linklerini geç
            if "kap-haber" in href.lower() and len(text) > 10:
                if href in seen or href.rstrip("/").endswith("/kap-haberleri"):
                    continue
                seen.add(href)

                if not href.startswith("http"):
                    href = f"https://bigpara.hurriyet.com.tr{href}"

                disc_id = href.rstrip("/").split("-")[-1].replace("/", "")
                items.append({
                    "id": disc_id if disc_id else href,
                    "title": text,
                    "link": href
                })

        # 2. Yöntem: Tablo (tr/td) yapısı varsa satırları tara
        if len(items) == 0:
            for tr in soup.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all("td") if td.get_text(strip=True)]
                if len(cols) >= 2:
                    row_text = " - ".join(cols)
                    link_tag = tr.find("a")
                    href = link_tag.get("href", "") if link_tag else ""
                    if href and not href.startswith("http"):
                        href = f"https://bigpara.hurriyet.com.tr{href}"
                    
                    disc_id = href if href else str(len(items))
                    if disc_id not in seen:
                        seen.add(disc_id)
                        items.append({
                            "id": disc_id,
                            "title": row_text,
                            "link": href or url
                        })

        print(f"Canlı akıştan {len(items)} adet KAP bildirimi başarıyla çekildi.")
        if items:
            print("Örnek son bildirim:", items[0]["title"])
    except Exception as e:
        print(f"Haber akışı alınırken hata: {e}")

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
        print("Haber akışından bildirim okunamadı.")
        return

    eslesen_sayisi = 0
    for item in disclosures:
        disc_id = str(item["id"])
        title = item["title"]
        link = item["link"]
        title_norm = normalize_tr(title)

        # 1. Açık pozisyon hisselerimizden biriyle eşleşiyor mu?
        eslesen_hisse = None
        for hisse in acik_hisseler:
            if re.search(rf"\b{re.escape(hisse)}\b", title_norm):
                eslesen_hisse = hisse
                break

        if not eslesen_hisse:
            continue

        eslesen_sayisi += 1
        print(f"Açık hisseyle eşleşti: {eslesen_hisse} -> {title}")

        # 2. Daha önce gönderildi mi?
        if disc_id in sent_ids:
            continue

        # 3. Kritik filtreye giriyor mu?
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
        print(f"Canlı akıştaki bildirimlerde takip edilen {acik_hisseler} koduna ait yeni haber bulunamadı.")

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-300:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
