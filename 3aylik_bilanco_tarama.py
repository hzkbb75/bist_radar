# ==============================================================================
# KOD: BIST QUANT ENGINE - ÇEYREKLİK BİLANÇO & OTOMATİK EXCEL KÖPRÜSÜ
# ==============================================================================
import os
import fitz
import re
import json
import time
from datetime import datetime
import numpy as np
import pandas as pd
import requests
import yfinance as yf
import urllib3

# Güvenlik uyarılarını gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. Canlı Make.com Webhook Adresi
MAKE_BILANCO_WEBHOOK = "https://hook.eu1.make.com/wa77gag3g9hqdubo8tn401h7yssknf7c"

# ==============================================================================
# 2. HİSSE LİSTESİNİ ZİRAAT PDF'İNDEN ANLIK ÇEKME (Bot Koruması Aşıldı)
# ==============================================================================
bist100_yedek = [
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

print("🔍 Ziraat Bülteni PDF'i Bilanço Motoru için anlık taranıyor...")
try:
    url = "https://www.ziraatyatirim.com.tr/arastirma-raporlari/haftalik-hisse-senedi-carpanlari"
    
    # Gerçek bir tarayıcı gibi davranması için kimlik ekliyoruz
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    res = requests.get(url, headers=headers, verify=False, timeout=15)
    pdf_link_match = re.search(r'href="(/Files/.*?\.pdf)"', res.text)
    
    if not pdf_link_match:
        raise ValueError("PDF linki bulunamadı. Ziraat bot koruması aktif olabilir.")
        
    pdf_url = "https://www.ziraatyatirim.com.tr" + pdf_link_match.group(1)
    
    pdf_res = requests.get(pdf_url, headers=headers, verify=False, timeout=15)
    with open("temp_bilanco_ziraat.pdf", "wb") as f:
        f.write(pdf_res.content)
        
    doc = fitz.open("temp_bilanco_ziraat.pdf")
    all_text = ""
    for page in doc:
        all_text += page.get_text("text") + "\n"
        
    tarama_listesi = []
    satirlar = all_text.split("\n")
    for i in range(len(satirlar) - 2):
        row = satirlar[i].strip()
        if re.match(r'^[A-Z]{4,5}$', row) and len(row) <= 5:
            try:
                pddd_kontrol = satirlar[i+2].strip().replace(",", ".")
                if pddd_kontrol != "0.0" and pddd_kontrol != "A.D.":
                    if row not in tarama_listesi:
                        tarama_listesi.append(row)
            except:
                continue
                
    if len(tarama_listesi) > 100:
        print(f"✅ Ziraat PDF'inden güncel {len(tarama_listesi)} hisse başarıyla çıkarıldı.")
    else:
        raise ValueError("PDF'den yeterli hisse okunamadı.")
        
except Exception as e:
    print(f"⚠️ PDF anlık okunamadı, yedeğe geçiliyor: {e}")
    tarama_listesi = bist100_yedek

# ==============================================================================
# 3. VERİ SÖZLÜKLERİ VE FONKSİYONLAR
# ==============================================================================
finans_hisseleri = [
    "AKBNK", "GARAN", "ISCTR", "YKBNK", "VAKBN", "HALKB", 
    "TSKB", "ALBRK", "ISMEN", "ANSGR", "TURSG", "ANHYT",
]

sektor_haritasi = {
    "AKBNK": "Bankacılık", "ALBRK": "Bankacılık", "GARAN": "Bankacılık",
    "HALKB": "Bankacılık", "ISCTR": "Bankacılık", "TSKB": "Bankacılık",
    "VAKBN": "Bankacılık", "YKBNK": "Bankacılık", "ISMEN": "Aracı Kurum / Menkul Değer",
    "ANHYT": "Sigorta / Emeklilik", "ANSGR": "Sigorta", "TURSG": "Sigorta",
    "AGHOL": "Holding", "ALARK": "Holding", "BERA": "Holding",
    "DOHOL": "Holding", "ECZYT": "Holding / Yatırım", "GLYHO": "Holding",
    "KCHOL": "Holding", "PAHOL": "Holding", "SAHOL": "Holding",
    "THYAO": "Ulaştırma / Havacılık", "PGSUS": "Ulaştırma / Havacılık",
    "TAVHL": "Havalimanı Hizmetleri", "GRSEL": "Taşımacılık / Ulaştırma",
    "RYSAS": "Lojistik / Depolama", "AHGAZ": "Gaz Dağıtım / Enerji",
    "AKFYE": "Yenilenebilir Enerji", "AKSEN": "Elektrik / Enerji",
    "ASTOR": "Elektrik Ekipmanları", "AYGAZ": "LPG / Gaz Dağıtım",
    "CANTE": "Elektrik Üretimi", "CWENE": "Yenilenebilir Enerji / Güneş",
    "ENERY": "Gaz Dağıtım / Enerji", "ENJSA": "Elektrik Dağıtım / Enerji",
    "ENTRA": "Yenilenebilir Enerji", "GWIND": "Yenilenebilir Enerji",
    "ODAS": "Elektrik Üretimi / Madencilik", "TUPRS": "Petrol Rafineri",
    "ZOREN": "Elektrik / Enerji", "AEFES": "İçecek / Meşrubat",
    "BIMAS": "Perakende Ticaret", "CCOLA": "İçecek / Meşrubat",
    "MGROS": "Perakende Ticaret", "OBAMS": "Gıda Üretimi",
    "SOKM": "Perakende Ticaret", "TABGD": "Restoran / Gıda",
    "TUKAS": "Gıda İmalatı", "ULKER": "Gıda / Atıştırmalık",
    "DOAS": "Otomotiv Dağıtım", "FROTO": "Otomotiv Üretim",
    "KARSN": "Otomotiv Üretim", "KATMR": "Araç Üstü Ekipman / Savunma",
    "OTKAR": "Otomotiv / Savunma", "TOASO": "Otomotiv Üretim",
    "TTRAK": "Traktör / İş Makineleri", "BRSAN": "Boru / Çelik",
    "BRYAT": "Borusan Yatırım / Sanayi", "EREGL": "Demir Çelik",
    "ISDMR": "Demir Çelik", "KCAER": "Çelik Profil",
    "KRDMD": "Demir Çelik", "AKCNS": "Çimento",
    "BTCIM": "Çimento", "CIMSA": "Çimento",
    "LMKDC": "Çimento", "OYAKC": "Çimento",
    "EUREN": "Cam / Yapı Malzemeleri", "SISE": "Cam Sanayi",
    "AKSA": "Kimya / Elyaf", "GUBRF": "Kimyevi Gübre",
    "HEKTS": "Tarım Kimyasalları", "KORDS": "Endüstriyel İplik / Kord Bezi",
    "PETKM": "Petrokimya", "SASA": "Polyester / Kimya",
    "ASELS": "Savunma Sanayi", "ALTNY": "Teknoloji / Savunma",
    "BINHO": "Teknoloji / Yatırım", "TCELL": "Telekomünikasyon",
    "TTKOM": "Telekomünikasyon", "EKGYO": "Gayrimenkul Yatırım Ort.",
    "RGYAS": "Gayrimenkul Yatırım Ort.", "SNGYO": "Gayrimenkul Yatırım Ort.",
    "TRGYO": "Gayrimenkul Yatırım Ort.", "CVKMD": "Madencilik",
    "EGEEN": "Otomotiv Yan Sanayi", "EGGUB": "Gübre / Limancılık",
    "TRALT": "Madencilik / Altın", "TRMET": "Metal / Maden",
    "ECILC": "İlaç / Sağlık", "MPARK": "Sağlık Hizmetleri",
    "MAVI": "Tekstil / Hazır Giyim", "ARCLK": "Dayanıklı Tüketim",
    "VESTL": "Dayanıklı Tüketim / Elektronik", "ENKAI": "İnşaat / Taahhüt / Enerji",
    "FENER": "Spor Kulübü", "GLRMK": "İnşaat / Ağır Sanayi",
    "TCKRC": "Dayanıklı Tüketim", "TKFEN": "İnşaat / Taahhüt / Tarım",
    "TRENJ": "Enerji / Sanayi",
}

def getir_deger(df, kalem, idx=0):
    if df is not None and not df.empty and kalem in df.index:
        try:
            val = df.loc[kalem].iloc[idx]
            return float(val) if pd.notna(val) else 0.0
        except Exception:
            return 0.0
    return 0.0

# ==============================================================================
# 4. YF BİLANÇO MOTORU (TÜM PİYASA TARAMASI)
# ==============================================================================
master_veritabani = []
print("🚀 Çeyreklik Bilanço Motoru Başlatıldı...")

for sira, hisse in enumerate(tarama_listesi, 1):
    ticker = yf.Ticker(f"{hisse}.IS")

    # --- A. FİNANS HİSSELERİ ---
    if hisse in finans_hisseleri:
        roa_val, roe_val = 0.0, 0.0
        try:
            info = ticker.info
            roa_val = round(float(info.get("returnOnAssets", 0.0) or 0.0), 4) if info else 0.0
            roe_val = round(float(info.get("returnOnEquity", 0.0) or 0.0), 4) if info else 0.0
        except Exception:
            pass

        p_roe = 50 if roe_val >= 0.35 else (35 if roe_val >= 0.25 else (20 if roe_val >= 0.15 else (5 if roe_val > 0 else 0)))
        p_roa = 50 if roa_val >= 0.03 else (35 if roa_val >= 0.02 else (20 if roa_val >= 0.01 else (5 if roa_val > 0 else 0)))

        master_veritabani.append({
            "Hisse": hisse, "Piotroski_Skor": "-", "Altman_Z": "-", "ROA": roa_val,
            "Brut_Marj": 0.0, "ROE": roe_val, "Net_Kar_Marji": 0.0, "Aktif_Devir": 0.0,
            "Kaldirac": 0.0, "Temel_Skor": int(p_roe + p_roa), "Iliskili_Taraf": "✅ Finans / Muaf"
        })
        time.sleep(0.15)
        continue

    # --- B. SANAYİ VE DİĞER ŞİRKETLER ---
    try:
        bs = ticker.quarterly_balance_sheet
        cf = ticker.quarterly_cashflow
        inc = ticker.quarterly_financials

        if bs.empty or inc.empty:
            raise ValueError("Mali tablo boş")

        idx_t = 0
        idx_t1 = 4 if bs.shape[1] > 4 else (1 if bs.shape[1] > 1 else 0)

        varlik_t = getir_deger(bs, "Total Assets", idx_t)
        varlik_t1 = getir_deger(bs, "Total Assets", idx_t1)
        donen_t = getir_deger(bs, "Current Assets", idx_t)
        donen_t1 = getir_deger(bs, "Current Assets", idx_t1)
        kisa_borc_t = getir_deger(bs, "Current Liabilities", idx_t)
        kisa_borc_t1 = getir_deger(bs, "Current Liabilities", idx_t1)
        uzun_borc_t = getir_deger(bs, "Long Term Debt", idx_t)
        uzun_borc_t1 = getir_deger(bs, "Long Term Debt", idx_t1)
        toplam_borc_t = getir_deger(bs, "Total Debt", idx_t)
        if toplam_borc_t == 0.0: toplam_borc_t = kisa_borc_t + uzun_borc_t
        ozkaynak_t = getir_deger(bs, "Stockholders Equity", idx_t)
        gecmis_kar_t = getir_deger(bs, "Retained Earnings", idx_t)

        diger_alacak_t = getir_deger(bs, "Other Receivables", idx_t)
        alacak_orani = (diger_alacak_t / donen_t) if donen_t > 0 else 0.0

        if alacak_orani > 0.15: iliskili_durumu = f"🚨 RİSKLİ (%{alacak_orani*100:.1f})"
        elif alacak_orani > 0.05: iliskili_durumu = f"⚠️ Dikkat (%{alacak_orani*100:.1f})"
        else: iliskili_durumu = "✅ Temiz"

        hasilat_t = getir_deger(inc, "Total Revenue", idx_t)
        hasilat_t1 = getir_deger(inc, "Total Revenue", idx_t1)
        brut_kar_t = getir_deger(inc, "Gross Profit", idx_t)
        brut_kar_t1 = getir_deger(inc, "Gross Profit", idx_t1)
        net_kar_t = getir_deger(inc, "Net Income", idx_t)
        net_kar_t1 = getir_deger(inc, "Net Income", idx_t1)
        ebit_t = getir_deger(inc, "EBIT", idx_t)

        net_kar_ttm = net_kar_t * 4
        if "Net Income" in inc.index:
            nks = inc.loc["Net Income"].dropna()
            if len(nks) >= 4: net_kar_ttm = float(nks.iloc[:4].sum())

        roa_hesap = round(net_kar_ttm / varlik_t, 4) if varlik_t else 0.0
        roe_hesap = round(net_kar_ttm / ozkaynak_t, 4) if ozkaynak_t else 0.0
        brut_marj = round(brut_kar_t / hasilat_t, 4) if hasilat_t else 0.0
        net_kar_marji = round(net_kar_t / hasilat_t, 4) if hasilat_t else 0.0
        aktif_devir = round(hasilat_t / varlik_t, 2) if varlik_t else 0.0
        kaldirac = round(toplam_borc_t / varlik_t, 2) if varlik_t else 0.0

        cfo_t = getir_deger(cf, "Operating Cash Flow", idx_t) if (cf is not None and not cf.empty) else net_kar_t

        f1 = 1 if (net_kar_t / varlik_t if varlik_t else 0) > 0 else 0
        f2 = 1 if cfo_t > 0 else 0
        f3 = 1 if (net_kar_t / varlik_t if varlik_t else 0) > (net_kar_t1 / varlik_t1 if varlik_t1 else 0) else 0
        f4 = 1 if cfo_t >= net_kar_t else 0
        f5 = 1 if (uzun_borc_t / varlik_t if varlik_t else 0) < (uzun_borc_t1 / varlik_t1 if varlik_t1 else 0) else 0
        f6 = 1 if (donen_t / kisa_borc_t if kisa_borc_t else 0) > (donen_t1 / kisa_borc_t1 if kisa_borc_t1 else 0) else 0
        f7 = 1
        f8 = 1 if (brut_kar_t / hasilat_t if hasilat_t else 0) > (brut_kar_t1 / hasilat_t1 if hasilat_t1 else 0) else 0
        f9 = 1 if (hasilat_t / varlik_t if varlik_t else 0) > (hasilat_t1 / varlik_t1 if varlik_t1 else 0) else 0
        piotroski = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9

        x1 = (donen_t - kisa_borc_t) / varlik_t if varlik_t else 0.0
        x2 = gecmis_kar_t / varlik_t if varlik_t else 0.0
        x3 = ebit_t / varlik_t if varlik_t else 0.0
        x4 = ozkaynak_t / toplam_borc_t if toplam_borc_t else 0.0
        z_val = max(min((6.56 * x1) + (3.26 * x2) + (6.72 * x3) + (1.05 * x4), 15.0), -5.0)

        p_pio = round((piotroski / 9.0) * 20.0)
        p_alt = 15 if z_val >= 2.99 else (8 if z_val >= 1.81 else 0)
        p_roe_s = 20 if roe_hesap >= 0.30 else (12 if roe_hesap >= 0.15 else (5 if roe_hesap >= 0.0 else 0))
        p_roa_s = 15 if roa_hesap >= 0.10 else (10 if roa_hesap >= 0.05 else (4 if roa_hesap >= 0.0 else 0))
        p_marj = 10 if net_kar_marji >= 0.15 else (6 if net_kar_marji >= 0.07 else (2 if net_kar_marji > 0 else 0))
        p_kald = 10 if kaldirac <= 0.50 else (5 if kaldirac <= 0.70 else 0)
        p_devir = 10 if aktif_devir >= 1.0 else (6 if aktif_devir >= 0.6 else 2)

        temel_skor = p_pio + p_alt + p_roe_s + p_roa_s + p_marj + p_kald + p_devir
        if alacak_orani > 0.05: temel_skor = max(0, temel_skor - 25)

        master_veritabani.append({
            "Hisse": hisse, "Piotroski_Skor": int(piotroski), "Altman_Z": round(z_val, 2),
            "ROA": roa_hesap, "Brut_Marj": brut_marj, "ROE": roe_hesap, "Net_Kar_Marji": net_kar_marji,
            "Aktif_Devir": aktif_devir, "Kaldirac": kaldirac, "Temel_Skor": int(temel_skor),
            "Iliskili_Taraf": iliskili_durumu
        })
    except Exception:
        master_veritabani.append({
            "Hisse": hisse, "Piotroski_Skor": "-", "Altman_Z": "-", "ROA": 0.0, "Brut_Marj": 0.0,
            "ROE": 0.0, "Net_Kar_Marji": 0.0, "Aktif_Devir": 0.0, "Kaldirac": 0.0,
            "Temel_Skor": 0, "Iliskili_Taraf": "✅ Temiz"
        })

    time.sleep(0.15)

# ==============================================================================
# 5. DOSYALARI KAYDETME VE MAKE.COM'A GÖNDERME
# ==============================================================================
df_m = pd.DataFrame(master_veritabani)
df_m.to_csv("master_bilanco_bist_tum.csv", index=False, encoding="utf-8-sig")

sablon = pd.DataFrame()
sablon["Hisse"] = df_m["Hisse"]
sablon["Piotroski Skoru"] = df_m["Piotroski_Skor"]
sablon["Altman Z"] = df_m["Altman_Z"]
sablon["ROA"] = df_m["ROA"]
sablon["Brüt Marj"] = df_m["Brut_Marj"]
sablon["ROE"] = df_m["ROE"]
sablon["Net Kar Marjı"] = df_m["Net_Kar_Marji"]
sablon["Aktif Devir Hızı"] = df_m["Aktif_Devir"]
sablon["Kaldıraç Oranı"] = df_m["Kaldirac"]
sablon["Sektör"] = df_m["Hisse"].map(sektor_haritasi).fillna("Sanayi")
sablon["Temel Skor"] = df_m["Temel_Skor"]
sablon["İlişkili Taraf Durumu"] = df_m["Iliskili_Taraf"]

sablon.to_excel("Temel_Analiz_Omurga.xlsx", sheet_name="Temel_Analiz", index=False)

print("📡 Canlı Excel için Make.com Webhook'una veri gönderiliyor...")
blok_ham_veri = sablon[[
    "Hisse", "Piotroski Skoru", "Altman Z", "ROA", "Brüt Marj", "ROE", 
    "Net Kar Marjı", "Aktif Devir Hızı", "Kaldıraç Oranı", "Sektör", 
    "Temel Skor", "İlişkili Taraf Durumu"
]].values.tolist()

bitis_satiri = len(blok_ham_veri) + 1
dinamik_aralik = f"A2:L{bitis_satiri}"

payload = {
    "islem_turu": "Ceyreklik_Bilanco_Guncelleme",
    "range_adresi": dinamik_aralik,
    "hazir_body_bilanco": json.dumps({"values": blok_ham_veri})
}

try:
    resp = requests.post(MAKE_BILANCO_WEBHOOK, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
    if resp.status_code == 200:
        print(f"🎉 Bilanço verileri ({dinamik_aralik} aralığına) Make.com'a başarıyla gönderildi!")
    else:
        print(f"⚠️ Webhook Başarısız! HTTP Kodu: {resp.status_code}")
except Exception as e:
    print(f"⚠️ Webhook gönderim hatası: {e}")
