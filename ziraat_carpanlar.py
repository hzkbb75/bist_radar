from datetime import datetime, timedelta
import json
import os
import requests
import pdfplumber

WEBHOOK_URL = "https://hook.eu1.make.com/wa77gag3g9hqdubo8tn401h7yssknf7c"
PDF_ADI = "bulten.pdf"

# ==============================================================================
# 1. BÜLTEN İNDİRME MOTORU (ZİRAAT YATIRIM)
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
    print("🔍 Son işlem gününün bülteni taranıyor...")
    
    for i in range(7):
        tarih = bugun - timedelta(days=i)
        tarih_str = tarih.strftime("%d%m%Y")
        url = f"https://www.ziraatyatirim.com.tr/documents/category/GG_{tarih_str}.pdf"

        try:
            cevap = requests.get(url, headers=headers, timeout=15)
            if cevap.status_code == 200 and len(cevap.content) > 5000:
                print(f"🎯 Güncel bülten bulundu: GG_{tarih_str}.pdf")
                with open(hedef_dosya, "wb") as f:
                    f.write(cevap.content)
                print(f"✅ Bülten indirildi: {hedef_dosya} ({len(cevap.content) // 1024} KB)")
                return True
            else:
                print(f"⏳ GG_{tarih_str}.pdf pas geçildi (Durum: {cevap.status_code})")
        except Exception as e:
            print(f"⚠️ {url} taranırken hata: {e}")

    return False

# ==============================================================================
# 2. TABLO OKUMA VE MAKE.COM'A AKTARMA MOTORU
# ==============================================================================
def sayi_donustur(deger):
    if not deger or deger == "a.d.":
        return 0.0
    temiz = str(deger).replace("%", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(temiz)
    except:
        return 0.0

def carpanlari_isle_ve_gonder():
    if not bulten_indir():
        raise FileNotFoundError("Son 7 güne ait bülten indirilemedi!")

    bist100_hisseleri = [
        "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFYE", "AKSA", "AKSEN",
        "ALARK", "ALBRK", "ALTNY", "ANHYT", "ANSGR", "ARCLK", "ASELS", "ASTOR",
        "AYGAZ", "BERA", "BIMAS", "BINHO", "BRSAN", "BRYAT", "BTCIM", "CANTE",
        "CCOLA", "CIMSA", "CVKMD", "CWENE", "DOAS", "DOHOL", "ECILC", "ECZYT",
        "EGEEN", "EGGUB", "EKGYO", "ENERY", "ENJSA", "ENKAI", "ENTRA", "EREGL",
        "EUREN", "FENER", "FROTO", "GARAN", "GLRMK", "GLYHO", "GRSEL", "GUBRF",
        "GWIND", "HALKB", "HEKTS", "ISCTR", "ISDMR", "ISMEN", "KARSN", "KATMR",
        "KCAER", "KCHOL", "KORDS", "KRDMD", "LMKDC", "MAVI", "MGROS", "MPARK",
        "OBAMS", "ODAS", "OTKAR", "OYAKC", "PAHOL", "PETKM", "PGSUS", "RGYAS",
        "RYSAS", "SAHOL", "SASA", "SISE", "SNGYO", "SOKM", "TABGD", "TAVHL",
        "TCELL", "TCKRC", "THYAO", "TKFEN", "TOASO", "TRALT", "TRENJ", "TRGYO",
        "TRMET", "TSKB", "TTKOM", "TTRAK", "TUKAS", "TUPRS", "TURSG", "ULKER",
        "VAKBN", "VESTL", "YKBNK", "ZOREN"
    ]

    print("📄 Ziraat Bülteni okunuyor...")
    pdf_satirlari = {}

    with pdfplumber.open(PDF_ADI) as pdf:
        for page in pdf.pages:
            metin = page.extract_text()
            if not metin:
                continue
            for satir in metin.split("\n"):
                parcalar = satir.split()
                if parcalar:
                    kod = parcalar[-1].upper()
                    if kod in bist100_hisseleri:
                        pdf_satirlari[kod] = parcalar

    # L2:N101 aralığı için matris (100 satır x 3 sütun: F/K, PD/DD, Değerleme)
    l_m_n_matrisi = []

    for hisse in bist100_hisseleri:
        satir = pdf_satirlari.get(hisse, None)
        if satir:
            try:
                fk = round(sayi_donustur(satir[-6]), 2)
                pddd = round(sayi_donustur(satir[-5]), 2)
            except:
                fk, pddd = 0.0, 0.0
        else:
            fk, pddd = 0.0, 0.0

        # Değerleme Durumu
        if (0 < fk < 12) and (0 < pddd < 3):
            durum = "🎯 İskontolu"
        elif fk > 25 or pddd > 7:
            durum = "⚠️ Pahalı"
        else:
            durum = "⚖️ Dengeli"

        l_m_n_matrisi.append([fk, pddd, durum])

    print(f"📊 Hazırlanan Satır Sayısı: {len(l_m_n_matrisi)} / {len(bist100_hisseleri)}")

    # Microsoft Graph API formatı (Values doğrudan 2D matris)
    hazir_json_body = json.dumps({
        "values": l_m_n_matrisi
    }, ensure_ascii=False)

    payload = {
        "islem_turu": "Haftalik_Carpan_Guncelleme",
        "tarih": datetime.now().strftime("%d.%m.%Y"),
        "hazir_body": hazir_json_body
    }

    res = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"})
    if res.status_code == 200:
        print("🎉 100 hisselik matris Make.com'a başarıyla iletildi!")
    else:
        print(f"⚠️ Hata Kodu: {res.status_code}")

if __name__ == "__main__":
    carpanlari_isle_ve_gonder()
