import os
import json
import io
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# ==========================================
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j"
ONEDRIVE_EXCEL_URL = "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJO2pbYOw?e=Obf4U8"
STATE_FILE = "son_bildirimler.json"

# KAP API Endpoint'i (Son bildirimler)
KAP_API_URL = "https://www.kap.org.tr/tr/api/disclosures"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.kap.org.tr/",
    "Accept": "application/json, text/plain, */*"
}

def download_excel_file(url):
    """OneDrive bağlantısını doğrudan saf .xlsx verisine dönüştürerek indirir."""
    session = requests.Session()
    target_url = url if "download=1" in url else f"{url}&download=1"
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

    return None

def get_open_positions():
    """OneDrive Excel'in 'İşlem_Günlüğü' sayfasından Pozisyon Durumu 'AÇIK' olan hisseleri çeker."""
    try:
        content = download_excel_file(ONEDRIVE_EXCEL_URL)
        if not content:
            print("HATA: Excel dosyası indirilemedi.")
            return set()

        excel_file = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
        
        # 'İşlem_Günlüğü' sayfasını dinamik olarak yakala
        target_sheet = None
        for name in excel_file.sheet_names:
            if "İŞLEM" in name.upper() or "ISLEM" in name.upper():
                target_sheet = name
                break
        
        if not target_sheet:
            target_sheet = excel_file.sheet_names[0]

        df = pd.read_excel(excel_file, sheet_name=target_sheet)
        df.columns = [str(c).strip() for c in df.columns]

        hisse_col = None
        durum_col = None

        for col in df.columns:
            c_upper = col.upper()
            if c_upper in ["HİSSE", "HISSE", "SEMBOL", "KOD"]:
                hisse_col = col
            if "DURUM" in c_upper:
                durum_col = col

        if not hisse_col:
            print(f"HATA: '{target_sheet}' sayfasında 'Hisse' kolonu bulunamadı.")
            return set()

        # Pozisyon durumu filtresi: Sadece 'AÇIK' olan pozisyonları çek
        if durum_col:
            df_acik = df[df[durum_col].astype(str).str.strip().str.upper().isin(["AÇIK", "ACIK"])]
            semboller = set(df_acik[hisse_col].dropna().astype(str).str.strip().str.upper())
        else:
            semboller = set(df[hisse_col].dropna().astype(str).str.strip().str.upper())

        semboller = {s for s in semboller if s and s != "NAN"}
        print(f"Takip edilecek portföy hisseleri ({len(semboller)} adet): {', '.join(semboller)}")
        return semboller
    except Exception as e:
        print(f"OneDrive Excel okuma hatası: {e}")
        return set()

def load_seen_ids():
    """Daha önce gönderilmiş bildirim ID'lerini yükler."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_ids(seen_ids):
    """İşlenen bildirim ID'lerini kaydeder."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids)[-500:], f, ensure_ascii=False, indent=2)

def fetch_kap_disclosures():
    """KAP üzerinden son bildirimleri çeker."""
    try:
        response = requests.get(KAP_API_URL, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            return response.json()
        print(f"KAP API hatası: HTTP {response.status_code}")
        return []
    except Exception as e:
        print(f"KAP bağlantı hatası: {e}")
        return []

def send_to_make(payload):
    """Eşleşen bildirimi Make.com Webhook'una iletir."""
    if not MAKE_WEBHOOK_URL:
        print("HATA: MAKE_WEBHOOK_URL tanımlı değil!")
        return False
    try:
        res = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"Make.com Webhook gönderim hatası: {e}")
        return False

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Canlı KAP taraması başlatıldı.")
    
    portfoy_sembolleri = get_open_positions()
    if not portfoy_sembolleri:
        print("Açık pozisyon bulunamadı veya liste çekilemedi. Tarama sonlandırılıyor.")
        return

    seen_ids = load_seen_ids()
    bildirimler = fetch_kap_disclosures()
    
    yeni_sayac = 0
    for item in bildirimler:
        disclosure = item.get("basic", {}) if "basic" in item else item
        
        bildirim_id = str(disclosure.get("disclosureIndex") or disclosure.get("id") or "")
        sembol = str(disclosure.get("stockCodes") or disclosure.get("companyOid") or "").strip().upper()
        baslik = disclosure.get("title") or disclosure.get("disclosureType") or "KAP Bildirimi"
        zaman = disclosure.get("publishDate") or datetime.now().strftime("%d.%m.%Y %H:%M")
        
        if not bildirim_id or bildirim_id in seen_ids:
            continue
            
        ilgili_hisseler = [s.strip() for s in sembol.replace(";", ",").split(",") if s.strip()]
        eslesen = any(h in portfoy_sembolleri for h in ilgili_hisseler)
        
        if eslesen:
            kap_link = f"https://www.kap.org.tr/tr/Bildirim/{bildirim_id}"
            payload = {
                "sembol": sembol,
                "baslik": baslik,
                "zaman": zaman,
                "kap_link": kap_link,
                "ozet": disclosure.get("summary") or baslik
            }
            print(f"Eşleşme bulundu: {sembol} - {baslik}")
            basarili = send_to_make(payload)
            if basarili:
                seen_ids.add(bildirim_id)
                yeni_sayac += 1
        else:
            seen_ids.add(bildirim_id)

    save_seen_ids(seen_ids)
    print(f"Tarama tamamlandı. {yeni_sayac} adet yeni bildirim Telegram'a aktarıldı.")

if __name__ == "__main__":
    main()
