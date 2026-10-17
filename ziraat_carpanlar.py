from datetime import datetime, timedelta
import json
import os
import requests
import pdfplumber

WEBHOOK_URL = "https://hook.eu1.make.com/wa77gag3g9hdubo8tn401h7yssknf7c"
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
    # Bülteni otomatik indir
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

    # Master dosyasından Piotroski skorlarını büyüme çarpanı olarak çek
    piotroski_sozluk = {}
    if os.path.exists("master_bilanco_bist100.csv"):
        import pandas as pd
        df_m = pd.read_csv("master_bilanco_bist100.csv")
        for _, r in df_m.iterrows():
            piotroski_sozluk[r["Hisse"]] = r["Piotroski_Skor"]

    guncellenecek_paketler = []

    for hisse in bist100_hisseleri:
        if hisse in pdf_satirlari:
            satir = pdf_satirlari[hisse]
            try:
                # Hizalama: [-8]: ROA, [-7]: ROE, [-6]: F/K, [-5]: PD/DD
                roa = round(sayi_donustur(satir[-8]) / 100, 4)
                roe = round(sayi_donustur(satir[-7]) / 100, 4)
                fk = round(sayi_donustur(satir[-6]), 2)
                pddd = round(sayi_donustur(satir[-5]), 2)
            except:
                roa, roe, fk, pddd = 0.0, 0.0, 0.0, 0.0

            # Matematiksel İskonto Değerlemesi
            if (0 < fk < 12) and (0 < pddd < 3):
                durum = "🎯 İskontolu"
            elif fk > 25 or pddd > 7:
                durum = "⚠️ Pahalı"
            else:
                durum = "⚖️ Dengeli"

            # Matematiksel Prospektif F/K (Büyüme İvmesi Modeli)
            f_skor = piotroski_sozluk.get(hisse, "-")
            try:
                skor_num = float(f_skor)
                g = (skor_num - 4.5) * 0.06
                prospektif_fk = round(fk / (1.0 + g), 2) if fk > 0 else 0.0
                prospektif_fk = max(prospektif_fk, 0.5) if fk > 0 else 0.0
            except:
                prospektif_fk = fk

            guncellenecek_paketler.append({
                "Hisse": hisse,
                "ROA": roa,
                "ROE": roe,
                "FK": fk,
                "PDDD": pddd,
                "Durum": durum,
                "Prospektif_FK": prospektif_fk
            })

    print(f"✅ PDF'ten Çekilen: {len(guncellenecek_paketler)} / {len(bist100_hisseleri)} hisse")

    # Make.com'a Gönderim
    payload = {
        "islem_turu": "Haftalik_Carpan_Guncelleme",
        "tarih": datetime.now().strftime("%d.%m.%Y"),
        "hisseler": guncellenecek_paketler
    }

    res = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"})
    if res.status_code == 200:
        print("🎉 Haftalık çarpanlar Make.com üzerinden Excel'e aktarıldı!")
    else:
        print(f"⚠️ Hata Kodu: {res.status_code}")

if __name__ == "__main__":
    carpanlari_isle_ve_gonder()
