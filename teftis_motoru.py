import os
import yfinance as yf
import pandas as pd
from openai import OpenAI

# ==============================================================================
# 1. API VE AYARLAR
# ==============================================================================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("❌ HATA: OPENAI_API_KEY bulunamadı! Lütfen GitHub Secrets'a ekleyin.")
    exit(1)

client = OpenAI(api_key=OPENAI_API_KEY)
MIN_TEMEL_PUAN = 60  

# ==============================================================================
# 2. HİSSE FİLTRELEME (GÜÇLÜ RADAR)
# ==============================================================================
print("🔍 Bilanço master dosyası okunuyor...")
try:
    df = pd.read_csv("master_bilanco_bist_tum.csv")
    df['Temel_Skor'] = pd.to_numeric(df['Temel_Skor'], errors='coerce').fillna(0)
    
    hedef_hisseler = df[(df['Temel_Skor'] >= MIN_TEMEL_PUAN) & (df['Iliskili_Taraf'] == "✅ Temiz")]["Hisse"].tolist()
    
    print(f"🎯 Güçlü Radar'a takılan {len(hedef_hisseler)} hisse bulundu: {hedef_hisseler}")
except Exception as e:
    print(f"❌ Veri dosyası okunamadı: {e}")
    exit(1)

if not hedef_hisseler:
    print("✅ Bu hafta teftiş edilecek yeni hisse bulunamadı.")
    exit(0)

# ==============================================================================
# 3. YF VERİ TOPLAMA VE OPENAI YAPAY ZEKA SORGUSU (TEKNİK + KANTİTATİF DESTEKLİ)
# ==============================================================================
for hisse in hedef_hisseler:  
    print(f"\n⚙️ {hisse} için yapay zeka teftiş raporu hazırlanıyor...")
    
    try:
        # --- 1. EXCEL (CSV) SATIRINDAKİ ÖZEL PUANLARIMIZI ÇEKELİM ---
        hisse_verisi = df[df['Hisse'] == hisse].iloc[0]
        
        # Sütun isimlerindeki olası farklılıkları tolere etmek için get() kullanıyoruz.
        temel_skor = hisse_verisi.get('Temel_Skor', 'Bilinmiyor')
        altman_z = hisse_verisi.get('Altman_Z', hisse_verisi.get('Altman Z', 'Bilinmiyor'))
        piotroski = hisse_verisi.get('Piotroski_Skoru', hisse_verisi.get('Piotroski Skoru', 'Bilinmiyor'))

        # --- 2. YFINANCE VERİLERİ ---
        ticker = yf.Ticker(f"{hisse}.IS")
        info = ticker.info
        
        # TEKNİK VERİ HESAPLAMALARI
        current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
        high_52 = info.get('fiftyTwoWeekHigh', 0)
        ma_50 = info.get('fiftyDayAverage', 0)
        ma_200 = info.get('twoHundredDayAverage', 0)
        
        zirveye_uzaklik = "Bilinmiyor"
        if high_52 and current_price:
            dusus_orani = ((high_52 - current_price) / high_52) * 100
            zirveye_uzaklik = f"%{round(dusus_orani, 2)} düşmüş (Zirve: {high_52}, Anlık: {current_price})"
            
        trend_durumu = "Bilinmiyor"
        if current_price and ma_50 and ma_200:
            if current_price > ma_50 and ma_50 > ma_200
