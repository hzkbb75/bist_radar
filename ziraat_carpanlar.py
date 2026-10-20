# ==============================================================================
# HAFTALIK ZİRAAT PİYASA ÇARPANLARI & TELEGRAM BÜLTEN MOTORU
# ==============================================================================
import os
import json
import requests
from datetime import datetime, timedelta

# --- 1. KURULUM KONTROLÜ ---
try:
    import pdfplumber
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "pdfplumber"])
    import pdfplumber

# --- 2. AYARLAR & ENTEGRASYONLAR ---
MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/wa77gag3g9hqdubo8tn401h7yssknf7c"

# Telegram Bildirimi (GitHub Secrets veya doğrudan değer)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PDF_DOSYA_ADI = "bulten.pdf"

bist100_hisseleri = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFYE", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALTNY", "ANHYT", "ANSGR", "ARCLK", "ASELS", "ASTOR", "AYGAZ", "BERA", "BIMAS", "BINHO",
    "BRSAN", "BRYAT", "BTCIM", "CANTE", "CCOLA", "CIMSA", "CVKMD", "CWENE", "DOAS", "DOHOL",
    "ECILC", "ECZYT", "EGEEN", "EGGUB", "EKGYO", "ENERY", "ENJSA", "ENKAI", "ENTRA", "EREGL",
    "EUREN", "FENER", "FROTO", "GARAN", "GLRMK", "GLYHO", "GRSEL", "GUBRF", "GWIND", "HALKB",
    "HEKTS", "ISCTR", "ISDMR", "ISMEN", "KARSN", "KATMR", "KCAER", "KCHOL", "KORDS", "KRDMD",
    "LMKDC", "MAVI", "MGROS", "MPARK", "OBAMS", "ODAS", "OTKAR", "OYAKC", "PAHOL", "PETKM",
    "PGSUS", "RGYAS", "RYSAS", "SAHOL", "SASA", "SISE", "SNGYO", "SOKM", "TABGD", "TAVHL",
    "TCELL", "TCKRC", "THYAO", "TKFEN", "TOASO", "TRALT", "TRENJ", "TRGYO", "TRMET", "TSKB",
    "TTKOM", "TTRAK", "TUKAS", "TUPRS", "TURSG", "ULKER", "VAKBN", "VESTL", "YKBNK", "ZOREN"
]

hisse_sektor = {
    "AKBNK": "Bankacılık", "ALBRK": "Bankacılık", "GARAN": "Bankacılık", "HALKB": "Bankacılık",
    "ISCTR": "Bankacılık", "TSKB": "Bankacılık", "VAKBN": "Bankacılık", "YKBNK": "Bankacılık",
    "ISMEN": "Menkul Değerler", "ANHYT": "Sigorta", "ANSGR": "Sigorta", "TURSG": "Sigorta",
    "AGHOL": "Holding", "ALARK": "Holding", "BERA": "Holding", "DOHOL": "Holding",
    "ECZYT": "Holding", "GLYHO": "Holding", "KCHOL": "Holding", "PAHOL": "Holding", "SAHOL": "Holding",
    "THYAO": "Havayolu", "PGSUS": "Havayolu", "TAVHL": "Havayolu", "GRSEL": "Lojistik", "RYSAS": "Lojistik",
    "AHGAZ": "Enerji", "AKFYE": "Enerji", "AKSEN": "Enerji", "ASTOR": "Enerji", "AYGAZ": "Enerji",
    "CANTE": "Enerji", "CWENE": "Enerji", "ENERY": "Enerji", "ENJSA": "Enerji", "ENTRA": "Enerji",
    "GWIND": "Enerji", "ODAS": "Enerji", "TUPRS": "Petrol & Kimya", "ZOREN": "Enerji",
    "AEFES": "İçecek", "CCOLA": "İçecek", "BIMAS": "Perakende", "MGROS": "Perakende", "SOKM": "Perakende",
    "OBAMS": "Gıda", "TABGD": "Gıda", "TUKAS": "Gıda", "ULKER": "Gıda",
    "DOAS": "Otomotiv", "FROTO": "Otomotiv", "KARSN": "Otomotiv", "KATMR": "Otomotiv",
    "OTKAR": "Otomotiv", "TOASO": "Otomotiv", "TTRAK": "Otomotiv",
    "BRSAN": "Demir Çelik", "BRYAT": "Holding", "EREGL": "Demir Çelik", "ISDMR": "Demir Çelik",
    "KCAER": "Demir Çelik", "KRDMD": "Demir Çelik", "AKCNS": "Çimento", "BTCIM": "Çimento",
    "CIMSA": "Çimento", "LMKDC": "Çimento", "OYAKC": "Çimento", "EUREN": "Cam & Seramik", "SISE": "Cam & Seramik",
    "AKSA": "Kimya", "GUBRF": "Kimya", "HEKTS": "Kimya", "KORDS": "Kimya", "PETKM": "Petrol & Kimya", "SASA": "Kimya",
    "ASELS": "Savunma", "ALTNY": "Savunma", "BINHO": "Holding", "TCELL": "Telekom", "TTKOM": "Telekom",
    "EKGYO": "GYO", "RGYAS": "GYO", "SNGYO": "GYO", "TRGYO": "GYO", "CVKMD": "Madencilik",
    "EGEEN": "Otomotiv Yan Sanayi", "EGGUB": "Kimya", "TRALT": "Madencilik", "TRMET": "Madencilik",
    "ECILC": "İlaç & Sağlık", "MPARK": "İlaç & Sağlık", "MAVI": "Perakende", "ARCLK": "Dayanıklı Tüketim",
    "VESTL": "Dayanıklı Tüketim", "ENKAI": "İnşaat", "FENER": "Spor", "GLRMK": "İnşaat",
    "TCKRC": "Demir Çelik", "TKFEN": "Holding", "TRENJ": "Enerji"
}

sektor_medyanlari = {
    "Bankacılık": {"fk": 5.23, "pddd": 1.01},
    "Holding": {"fk": 14.01, "pddd": 0.71},
    "Demir Çelik": {"fk": 26.56, "pddd": 0.87},
    "Otomotiv": {"fk": 8.82, "pddd": 1.36},
    "Otomotiv Yan Sanayi": {"fk": 13.33, "pddd": 0.83},
    "Gıda": {"fk": 12.02, "pddd": 1.27},
    "İçecek": {"fk": 11.01, "pddd": 1.52},
    "Perakende": {"fk": 24.02, "pddd": 1.80},
    "Dayanıklı Tüketim": {"fk": 14.07, "pddd": 0.47},
    "Çimento": {"fk": 19.80, "pddd": 0.99},
    "Cam & Seramik": {"fk": 12.20, "pddd": 0.68},
    "Kimya": {"fk": 9.70, "pddd": 0.98},
    "Petrol & Kimya": {"fk": 10.05, "pddd": 1.27},
    "Savunma": {"fk": 24.57, "pddd": 4.79},
    "Telekom": {"fk": 7.92, "pddd": 0.78},
    "Enerji": {"fk": 14.34, "pddd": 1.15},
    "GYO": {"fk": 0.0, "pddd": 0.48},
    "Havayolu": {"fk": 6.77, "pddd": 0.32},
    "Lojistik": {"fk": 67.41, "pddd": 1.29},
    "İlaç & Sağlık": {"fk": 26.01, "pddd": 0.62},
    "İnşaat": {"fk": 11.89, "pddd": 1.32},
    "Madencilik": {"fk": 13.89, "pddd": 2.47},
    "Menkul Değerler": {"fk": 4.78, "pddd": 0.92},
    "Sigorta": {"fk": 3.93, "pddd": 1.53},
    "Spor": {"fk": 0.0, "pddd": 0.74}
}

# --- 3. BÜLTENİ OTOMATİK İNDİRME ---
def bulten_indir(hedef_dosya="bulten.pdf"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.ziraatyatirim.com.tr/"
    }
    bugun = datetime.today()
    for i in range(7):
        tarih = bugun - timedelta(days=i)
        tarih_str = tarih.strftime("%d%m%Y")
        url = f"https://www.ziraatyatirim.com.tr/documents/category/GG_{tarih_str}.pdf"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200 and len(res.content) > 5000:
                with open(hedef_dosya, "wb") as f:
                    f.write(res.content)
                print(f"🎯 Güncel bülten indirildi: GG_{tarih_str}.pdf ({len(res.content)//1024} KB)")
                return True
        except Exception:
            continue
    return False

def sayi_donustur(deger):
    if not deger or deger == "a.d.":
        return 0.0
    temiz = str(deger).replace("%", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(temiz)
    except:
        return 0.0

# --- 4. MOTOR ÇALIŞTIRMA ---
print("🚀 Haftalık Motor Başlatıldı...")
if not bulten_indir(PDF_DOSYA_ADI):
    raise FileNotFoundError("❌ Ziraat bülteni indirilemedi, işlem durduruldu.")

pdf_satirlari = {}
with pdfplumber.open(PDF_DOSYA_ADI) as pdf:
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
            roa = round(sayi_donustur(satir[-8]) / 100, 4)
            roe = round(sayi_donustur(satir[-7]) / 100, 4)
            fk = round(sayi_donustur(satir[-6]), 2)
            pddd = round(sayi_donustur(satir[-5]), 2)
        except:
            roa, roe, fk, pddd = 0.0, 0.0, 0.0, 0.0

        sektor = hisse_sektor.get(hisse, "Diğer")
        medyan = sektor_medyanlari.get(sektor, {"fk": 12.0, "pddd": 1.5})
        sec_fk = medyan.get("fk", 0.0)
        sec_pddd = medyan.get("pddd", 0.0)

        if sektor in ["GYO", "Bankacılık"]:
            oran = (pddd / sec_pddd) if (pddd > 0 and sec_pddd > 0) else 1.0
        else:
            bilesenler = []
            if fk > 0 and sec_fk > 0:
                bilesenler.append(fk / sec_fk)
            if pddd > 0 and sec_pddd > 0:
                bilesenler.append(pddd / sec_pddd)
            oran = (sum(bilesenler) / len(bilesenler)) if bilesenler else 1.0

        if oran <= 0.85:
            durum = "🟢 İskontolu"
        elif oran <= 1.15:
            durum = "🟡 Dengeli"
        else:
            durum = "🔴 Pahalı"

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

# --- 5. MAKE.COM WEBHOOK İLE EXCEL'E AKTARIM ---
# Excel'deki L (F/K), M (PD/DD), N (Değerleme Durumu) sütunlarına basılacak 2 boyutlu matris
matris_verisi = []
for h in guncellenecek_paketler:
    matris_verisi.append([
        h.get("FK", "-"),
        h.get("PDDD", "-"),
        h.get("Durum", "-")
    ])

payload = {
    "islem_turu": "Haftalik_Carpan_Guncelleme",
    "tarih": datetime.now().strftime("%d.%m.%Y"),
    "hisseler": guncellenecek_paketler,
    "hazir_body_zb": {
        "values": matris_verisi
    }
}

res = requests.post(MAKE_WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"})
if res.status_code == 200:
    print("🎉 Çarpanlar Make.com üzerinden Excel'e aktarıldı!")
else:
    print(f"⚠️ Make.com Yanıt Kodu: {res.status_code}")

# --- 6. TELEGRAM BÜLTENİ GÖNDERİMİ ---
iskontolular = [x for x in guncellenecek_paketler if x["Durum"] == "🟢 İskontolu" and x["FK"] > 0]
iskontolular.sort(key=lambda x: x["FK"])
top_5 = iskontolular[:5]

mesaj = f"📊 *HAFTALIK ZİRAAT BİST 100 DEĞERLEME RAPORU*\n"
mesaj += f"📅 Tarih: {datetime.now().strftime('%d.%m.%Y')}\n\n"
mesaj += "🏆 *Sektörüne Göre En İskontolu 5 Hisse:*\n"
for h in top_5:
    mesaj += f"• *{h['Hisse']}*: F/K: `{h['FK']}` | PD/DD: `{h['PDDD']}` | Pr. F/K: `{h['Prospektif_FK']}`\n"

mesaj += f"\n✅ Toplam `{len(iskontolular)}` hisse sektörüne göre iskontolu bölgede.\n"
mesaj += "📁 Canlı Excel dosyası güncellendi."

BOT_TOKEN = "8897693829:AAEHKHoRKSN-h3RRRU60bDCq3wcuLstivI4"
CHAT_ID = 932085366

tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
try:
    tg_res = requests.post(
        tg_url,
        json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    )
    if tg_res.status_code == 200:
        print("📲 Telegram bülteni başarıyla gönderildi!")
except Exception as e:
    print(f"⚠️ Telegram gönderim hatası: {e}")
