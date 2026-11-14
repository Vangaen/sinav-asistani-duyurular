# Duyuru onayı (taslak -> yayın)

1. GitHub'da (telefondan da) bu depoda `duyurular.json` dosyasını aç, kalem simgesine dokun.
2. `"status": "draft"` olan kaydı bul. Başlık, metin ve TARİHLERİ resmi kaynakla karşılaştır.
3. Doğruysa `"draft"` -> `"published"` yap. Yanlışsa düzelt ya da kaydı sil.
3b. `"category"` alanı Gündem sekmesindeki süzgeci belirler: `deneme` (yaklaşan genel deneme), `sonuc` (açıklanan sonuç), `osym` (ÖSYM / resmî duyuru), `diger`. Boş ya da yazılmazsa `diger` sayılır.
4. Resmi sınav günü kaydıysa `"exam_day": true` ekle (uygulama tarih seçicide kısayol önerir).
5. "Commit changes" ile kaydet. Uygulama en geç 6 saat sonra yeni haliyle çeker.

Elle duyuru eklemek için `tools/news/inbox.json` dosyasına
`{"exam":"yks","source_name":"ÖSYM","url":"https://...","title":"...","text":"resmi metin"}` ekle;
sonraki günlük çalıştırmada özetlenip taslak olarak eklenir.

Süresi dolan haberi SİLME: uygulama bunları Gündem sekmesinde arşiv olarak gösterir (ana ekran kartından kalkar). Akış en çok 200 kayıt tutar; araç en eskileri kendisi atar.
