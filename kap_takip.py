import os
import json
import io
import base64
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# ==========================================
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j"
ONEDRIVE_EXCEL_URL = "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJ02pbY0w?e=VA4N5A"
STATE_FILE = "son_bildirimler.json"

# KAP API Endpoint'i (Son bildirimler)
KAP_API_URL = "https://www.kap.org.tr/tr/api/disclosures"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.kap.org.tr/",
    "Accept": "application/json, text/plain, */*"
}

def get_onedrive_direct_url(url):
    """OneDrive linkini doğrudan dosya indiren Microsoft API adresine dönüştürür."""
    clean_url = url.split('&download=')[0].split('?download=')[0]
    encoded = base64.b64encode(clean_url.encode('utf-8')).decode('utf-8')
    encoded_url = encoded.replace('/', '_').replace('+', '-').rstrip('=')
    return f"https://api.onedrive.com/v1.0/shares/u!{encoded_url}/root/content"

def get_open_positions():
    """OneDrive üzerindeki Excel'i indirip açık pozisyondaki hisse sembollerini çeker."""
    if not ONEDRIVE_EXCEL_URL:
        print("UYARI: ONEDRIVE_EXCEL_URL tanımlı değil!")
        return set()
    
    try:
        direct_url = get_onedrive_direct_url(ONEDRIVE_EXCEL_URL)
        res = requests.get(direct_url, headers={"User-Agent": HEADERS["User-Agent"]}, allow_redirects=True, timeout=25)
        
        # Eğer API yönlendirmesi başarılı olmadıysa klasik linki dene
        if res.status_code != 200 or not res.content.startswith(b'PK'):
            fallback_url = ONEDRIVE_EXCEL_URL if "download=1" in ONEDRIVE_EXCEL_URL else f"{ONEDRIVE_EXCEL_URL}&download=1"
            res = requests.get(fallback_url, headers={"User-Agent": HEADERS["User-Agent"]}, allow_redirects=True, timeout=25)

        # Gelen dosyanın gerçek zip/xlsx olup olmadığını doğrula
        if not res.content.startswith(b'PK'):
            print(f"HATA: İndirilen dosya Excel değil. İlk 100 karakter: {res.text[:100]}")
            return set()

        df = pd.read_excel(io.BytesIO(res.content), engine="openpyxl")
        
        col_name = None
        for col in df.columns:
            if str(col).strip().upper() in ["HISSE", "SEMBOL", "HİSSE", "TICKER", "KOD"]:
                col_name = col
                break
        
        if not col_name:
            col_name = df.columns[0]
            
        semboller = set(df[col_name].dropna().astype(str).str.strip().str.upper())
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
