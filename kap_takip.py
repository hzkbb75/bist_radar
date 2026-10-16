import os
import io
import re
import json
import requests
import pandas as pd
from datetime import datetime
import xml.etree.ElementTree as ET

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

def get_recent_kap_disclosures():
    """KAP bildirimlerini RSS akışı üzerinden zaman aşımına takılmadan çeker."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    })

    # 1. Öncelik: KAP Resmi RSS Beslemesi
    rss_url = "https://www.kap.org.tr/tr/rss/bildirimler"
    try:
        resp = session.get(rss_url, timeout=20)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall(".//item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                desc = item.findtext("description", "")
                
                # Linkten bildirim ID'sini al (örn: /tr/Bildirim/123456 -> 123456)
                disc_id = link.rstrip("/").split("/")[-1] if "/" in link else title
                items.append({
                    "disclosureId": disc_id,
                    "title": title,
                    "summary": desc,
                    "link": link
                })
            print(f"KAP RSS üzerinden {len(items)} adet güncel bildirim çekildi.")
            return items
    except Exception as e:
        print(f"RSS akışı alınamadı ({e}), genel akış deneniyor...")

    # 2. Yedek Öncelik: Genel Bildirimler JSON akışı (parametresiz)
    try:
        json_url = "https://www.kap.org.tr/tr/api/disclosures"
        resp = session.get(json_url, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            print(f"KAP API üzerinden {len(data)} adet bildirim çekildi.")
            return [{
                "disclosureId": str(d.get("disclosureId")),
                "title": d.get("title", ""),
                "summary": d.get("summary", ""),
                "link": f"https://www.kap.org.tr/tr/Bildirim/{d.get('disclosureId')}"
            } for d in data]
    except Exception as e:
        print(f"Genel bildirim akışı da alınamadı: {e}")

    return []

def run_kap_scanner():
    acik_hisseler = get_open_positions()
    print(f"Takip Edilen Açık Pozisyonlar: {acik_hisseler}")

    if not acik_hisseler:
        print("Portföyde açık hisse bulunamadı. Tarama tamamlandı.")
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
    disclosures = get_recent_kap_disclosures()

    if not disclosures:
        print("İncelenecek bildirim akışı alınamadı.")
        return

    for item in disclosures:
        disc_id = str(item.get("disclosureId"))
        title = item.get("title", "")
        summary = item.get("summary", "")
        link = item.get("link", "")

        # Bu bildirim açık hisselerimizden birine mi ait?
        eslesen_hisse = None
        for hisse in acik_hisseler:
            # Hisse kodunun kelime olarak başlıkta veya özette geçip geçmediğini kontrol eder
            pattern = rf"\b{re.escape(hisse)}\b"
            if re.search(pattern, title.upper()) or re.search(pattern, summary.upper()):
                eslesen_hisse = hisse
                break

        if not eslesen_hisse:
            continue

        print(f"Açık hisseyle eşleşti: {eslesen_hisse} -> {title}")

        # Daha önce gönderildi mi?
        if disc_id in sent_ids:
            continue

        # Kritik filtre kontrolü
        if not is_critical_disclosure(title, summary):
            print(f"Elenen rutin bildirim: {eslesen_hisse} - {title}")
            new_sent_ids.append(disc_id)
            continue

        # Make.com Webhook iletimi
        payload = {
            "disclosure_id": disc_id,
            "sembol": eslesen_hisse,
            "baslik": title,
            "ozet": summary,
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

    # Son 300 bildirimi hafızada sakla
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(new_sent_ids[-300:], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_kap_scanner()
