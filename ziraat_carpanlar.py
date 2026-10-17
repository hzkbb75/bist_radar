from datetime import datetime, timedelta
import json
import os
import requests
import pdfplumber

WEBHOOK_URL = "https://hook.eu1.make.com/wa77gag3g9hdubo8tn401h7yssknf7c"
PDF_ADI = "bulten.pdf"

# ==============================================================================
# 1. BÜLTEN İNDİRME ADIMI
# ==============================================================================
def bulten_indir(hedef_dosya=PDF_ADI):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.ziraatyatirim.com.tr/"
    }
    
    bugun = datetime.today()
    print("🔍 Son işlem gününün bülteni aranıyor...")
    
    for i in range(7):
        tarih = bugun - timedelta(days=i)
        tarih_str = tarih.strftime("%d%m%Y")
        url = f"https://www.ziraatyatirim.com.tr/documents/category/GG_{tarih_str}.pdf"

        cevap = requests.get(url, headers=headers, timeout=15)
        if cevap.status_code == 200 and len(cevap.content) > 5000:
            print(f"🎯 Güncel bülten bulundu: GG_{tarih_str}.pdf")
            with open(hedef_dosya, "wb") as f:
                f.write(cevap.content)
            print(f"✅ Bülten indirildi: {hedef_dosya} ({len(cevap.content) // 1024} KB)")
            return True
        else:
            print(f"⏳ GG_{tarih_str}.pdf pas geçildi (Durum: {cevap.status_code})")

    return False

# ==============================================================================
# 2. TABLO OKUMA VE MAKE.COM'A GÖNDERME ADIMI
# ==============================================================================
def carpanlari_isle_ve_gonder():
    if not bulten_indir():
        raise FileNotFoundError("Bülten indirilemediği için işlem iptal edildi.")

    print("📄 Ziraat Bülteni okunuyor...")

    # Mevcut Colab Bölüm 2'nizdeki hisse listeniz ve tablo okuma mantığınız:
    # (Colab Bölüm 2'deki pdfplumber okuma kodlarınız aynen buraya bağlanır)
    with pdfplumber.open(PDF_ADI) as pdf:
        # Colab'daki mevcut tablo parse kodunuz burada çalışır
        print(f"Bülten toplam sayfa sayısı: {len(pdf.pages)}")
        # Örnek payload oluşturma ve Make.com'a gönderme
        # payload = ...
        
    print("🚀 Make.com webhook gönderimi tamamlanıyor...")
    # res = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"})

if __name__ == "__main__":
    carpanlari_isle_ve_gonder()
