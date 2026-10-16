import os
import json
import requests
import pandas as pd
from datetime import datetime

# ==========================================
# AYARLAR VE ÇEVRE DEĞİŞKENLERİ
# ==========================================
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/w2bw4cexf24z4huxs3nikopnofif1t1j"
ONEDRIVE_EXCEL_URL = "https://1drv.ms/x/c/cb9e9d1c772ef382/IQD2WvVMDCAOSJKa6ur72EdJAQ8UWGwRYYQ-zFsJ02pbY0w?e=VA4N5A&download=1"
STATE_FILE = "son_bildirimler.json"

# KAP API Endpoint'i (Son bildirimler)
KAP_API_URL = "https://www.kap.org.tr/tr/api/disclosures"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.kap.org.tr/",
    "Accept": "application/json, text/plain, */*"
}

def get_open_positions():
    """OneDrive üzerindeki Excel'den açık pozisyondaki hisse sembollerini çeker."""
    if not ONEDRIVE_EXCEL_URL:
        print("UYARI: ONEDRIVE_EXCEL_URL tanımlı değil!")
        return set()
    
    try:
        # Excel dosyasını doğrudan indirip oku
        df = pd.read_excel(ONEDRIVE_EXCEL_URL)
        
        # 'Hisse' veya 'Sembol' kolonunu tespit et
        col_name = None
        for col in df.columns:
            if str(col).strip().upper() in ["HISSE", "SEMBOL", "HİSSE", "TICKER", "KOD"]:
                col_name = col
                break
        
        if not col_name:
            col_name = df.columns[0]  # Bulamazsa ilk sütunu baz alır
            
        semboller = set(df[col_name].dropna().astype(str).str.strip().str.upper())
        print(f"Takip edilecek portföy hisseleri ({len(semboller)} adet): {', '.join(semboller)}")
        return semboller
    except Exception as e:
        print(f"OneDrive Excel okuma hatası: {e}")
        return set()

def load_seen_ids():
    """Daha önce Telegram'a gönderilmiş bildirim ID'lerini yükler."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen_ids(seen_ids):
    """İşlenen bildirim ID'lerini kaydeder (Maksimum son 500 ID saklanır)."""
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
        # KAP JSON yapısından verileri ayıkla
        disclosure = item.get("basic", {}) if "basic" in item else item
        
        bildirim_id = str(disclosure.get("disclosureIndex") or disclosure.get("id") or "")
        sembol = str(disclosure.get("stockCodes") or disclosure.get("companyOid") or "").strip().upper()
        baslik = disclosure.get("title") or disclosure.get("disclosureType") or "KAP Bildirimi"
        zaman = disclosure.get("publishDate") or datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # ID yoksa veya daha önce gönderildiyse atla
        if not bildirim_id or bildirim_id in seen_ids:
            continue
            
        # Birden fazla hisse kodu virgülle gelebilir (örn: THYAO, PGSUS)
        ilgili_hisseler = [s.strip() for s in sembol.replace(";", ",").split(",") if s.strip()]
        
        # Portföyümüzdeki hisselerle eşleşme kontrolü
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
            # Portföy dışı bildirimleri de tekrar kontrol etmemek için hafızaya al
            seen_ids.add(bildirim_id)

    save_seen_ids(seen_ids)
    print(f"Tarama tamamlandı. {yeni_sayac} adet yeni bildirim Telegram'a aktarıldı.")

if __name__ == "__main__":
    main()
