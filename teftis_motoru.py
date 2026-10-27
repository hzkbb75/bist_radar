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
# 3. YF VERİ TOPLAMA VE OPENAI YAPAY ZEKA SORGUSU (HİBRİT MODEL)
# ==============================================================================
for hisse in hedef_hisseler:  
    print(f"\n⚙️ {hisse} için yapay zeka teftiş raporu hazırlanıyor...")
    
    try:
        # --- 1. EXCEL (CSV) SATIRINDAKİ ÖZEL PUANLARIMIZI ÇEKELİM ---
        hisse_verisi = df[df['Hisse'] == hisse].iloc[0]
        
        temel_skor = hisse_verisi.get('Temel_Skor', 'Bilinmiyor')
        altman_z = hisse_verisi.get('Altman_Z', hisse_verisi.get('Altman Z', 'Bilinmiyor'))
        piotroski = hisse_verisi.get('Piotroski_Skoru', hisse_verisi.get('Piotroski Skoru', 'Bilinmiyor'))

        # --- 2. YFINANCE VERİLERİ ---
        ticker = yf.Ticker(f"{hisse}.IS")
        info = ticker.info
        
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
            if current_price > ma_50 and ma_50 > ma_200:
                trend_durumu = "Güçlü Yükseliş Trendi (Fiyat > 50 HO > 200 HO)"
            elif current_price < ma_50 and ma_50 < ma_200:
                trend_durumu = "Düşüş Trendi (Fiyat < 50 HO < 200 HO)"
            else:
                trend_durumu = "Yatay veya Karışık Seyir"

        sirket_ozeti = f"""
        Şirket: {hisse} ({info.get('longName', 'Bilinmiyor')})
        Sektör: {info.get('sector', 'Bilinmiyor')}
        
        --- BİZİM KANTİTATİF (EXCEL) VERİLERİMİZ ---
        Master Temel Puan: {temel_skor} / 100
        Altman Z-Skor (İflas Riski): {altman_z}
        Piotroski F-Skor (Sağlık): {piotroski}
        
        --- YF TEMEL VERİLER ---
        F/K Oranı: {info.get('trailingPE', 'Bilinmiyor')}
        PD/DD Oranı: {info.get('priceToBook', 'Bilinmiyor')}
        Kâr Marjı: {info.get('profitMargins', 'Bilinmiyor')}
        Özkaynak Kârlılığı (ROE): {info.get('returnOnEquity', 'Bilinmiyor')}
        Borç/Özkaynak Oranı: {info.get('debtToEquity', 'Bilinmiyor')}
        
        --- TEKNİK VERİLER ---
        52 Haftalık Zirveye Uzaklık: {zirveye_uzaklik}
        Teknik Trend Durumu: {trend_durumu}
        """
        
        prompt = f"""
        Sen, Serkan Ünal'ın 'Borsa İstanbul İçin Hisse Seçim Rehberi' kitabının TAMAMINA hakim, değer yatırımı prensiplerini uygulayan uzman ve katı bir kantitatif finansal analistsin.
        
        Bana {hisse} kodlu hisse senedi için şık bir 'Hisse Değerlendirme Kartı' (Markdown formatında) yaz. 
        SADECE SORU CEVAPLAYAN BİR MAKİNE OLMA. Serkan Ünal'ın kitabın genelindeki derin sentez, yorumlama ve sektörel vizyon yeteneğini kullanarak her bölümün başında doyurucu bir "Sentez ve Genel Değerlendirme" paragrafı yaz. 
        Ardından, kitabın 213. ve 214. sayfalarındaki soruları kontrol listesi formatında tek tek ve şüpheci bir dille cevapla.
        
        Kullanacağın Veriler:
        {sirket_ozeti}
        
        Aşağıdaki şablonu birebir Markdown formatında kullan:

        ### 📄 HİSSE DEĞERLENDİRME KARTI: {hisse}
        
        **Bölüm 1 — Elemeler (Kırmızı Çizgiler)**
        *Sentez:* [Kitabın genel felsefesiyle şirketin temel risklerini ve kırmızı çizgilerini yorumladığın akıcı bir analist paragrafı]
        * **Halka açıklık oranı ve hâkim ortak payı ne durumda? (Veto eşiği aşılıyor mu?)** [Cevap]
        * **Kâr dağıtımında veya yönetim kurulunda imtiyazlı pay var mı?** [Cevap]
        * **Hâkim ortağın sicili temiz mi? Küçük ortakları zarara uğratma öyküsü var mı?** [Cevap]
        * **İlişkili taraflara sistematik kaynak aktarımı var mı?** [Cevap]
        * **Borç yapısında taşınamaz bir risk (Altman Z skoru, regülasyon, tek müşteri bağımlılığı) var mı?** [Cevap]

        **Bölüm 2 — İş Kalitesi (Hendek ve Yönetim Testi)**
        *Sentez:* [Şirketin rekabet avantajını, vizyonunu, liyakatini ve tek adam riskini kitabın bütününe yayılmış felsefeyle yorumladığın paragraf]
        * **Sektörde pazar payı istikrarlı mı? Pazara tutunabilen yeni güçlü rakip tehdidi var mı?** [Cevap]
        * **Şirket, reel kârlılığını sürekli kılabiliyor mu? Kriz yıllarında dirençli mi?** [Cevap]
        * **Rekabet avantajının (hendeğin) kaynağı nedir ve ne kadar dayanıklı?** [Cevap]
        * **Şirketin kurucusundan bağımsız, liyakatli ve profesyonel bir yönetimi/CEO'su var mı? Tek adam riski taşıyor mu?** [Cevap]
        * **Rakiplerine kıyasla reel büyüme hızı ve kâr marjlarını koruma başarısı nasıl?** [Cevap]

        **Bölüm 3 — Tablolar (Kârın Gerçekliği)**
        *Sentez:* [Bilanço okuma sanatını kullanarak kârın ne kadar gerçek, ne kadar makyajlı olduğunu yorumladığın paragraf]
        * **Şirket açıkladığı kârı neye dönüştürüyor? (Kasa nakdi, temettü, yatırımlar)** [Cevap]
        * **Kârın ne kadarı tekrarlanamaz tek seferlik kalemlerden kaynaklanıyor?** [Cevap]
        * **Dipnotlarda gizlenmiş şarta bağlı yükümlülükler (TRİ) riski var mı?** [Cevap]
        * **Master Temel Puan ve Piotroski Skoru şirketin asıl faaliyet gücünü nasıl yansıtıyor?** [Cevap]

        **Bölüm 4 — Fiyat ve Güvenlik Marjı**
        *Sentez:* [Teknik verileri ve temel çarpanları harmanlayarak hissenin ucuzluk/pahalılık durumunu yorumladığın paragraf]
        * **Mevcut çarpanların paydasındaki rakam (kâr/özkaynak) sürdürülebilir mi?** [Cevap]
        * **Kazanç Getirisi (1 / F/K) ile risksiz faiz arasında yeterli bir güvenlik marjı tamponu var mı?** [Cevap]
        * **Hissenin teknik olarak zirveden düşüş oranı ve hareketli ortalama trendi alım için güvenli bölgeyi işaret ediyor mu?** [Cevap]
        * **Hatalı analiz durumunda yatırımcıyı ayakta tutacak yanılma payı fiyatlanmış mı?** [Cevap]

        **Bölüm 5 — Nihai Karar & Portföy Rejimi**
        *Sentez:* [Tüm analizlerin ışığında yatırımcıya verdiğin nihai yönlendirme paragrafı]
        * **Şirketin nihai kategorisi nedir? (Korunaklı / Kırılgan / Hendeksiz)** [Cevap]
        * **Bu şartlar altında portföyde hedeflenen ağırlık maksimum yüzde kaç olmalıdır?** [Cevap]
        * **Kademeli alım (aşamalandırma) planı nasıl kurgulanmalıdır?** [Cevap]
        * **Hangi şartlar (Hâkim ortak satışı, yönetim bozulması, fiyat şişmesi) gerçekleşirse bu pozisyondan acilen çıkılmalıdır?** [Cevap]
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen usta bir kantitatif ve teknik analistsin."},
                {"role": "user", "content": prompt}
            ]
        )
        rapor_metni = response.choices[0].message.content
        
        dosya_adi = f"TEFTIS_{hisse}.md"
        with open(dosya_adi, "w", encoding="utf-8") as f:
            f.write(rapor_metni)
            
        print(f"✅ {dosya_adi} başarıyla oluşturuldu ve kaydedildi!")
        
    except Exception as e:
        print(f"⚠️ {hisse} teftişinde hata: {e}")

print("\n🚀 Tüm yapay zeka teftiş işlemleri tamamlandı!")
