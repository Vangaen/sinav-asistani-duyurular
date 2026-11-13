# Duyuru onayı (taslak -> yayın)

1. GitHub'da (telefondan da) bu depoda `duyurular.json` dosyasını aç, kalem simgesine dokun.
2. `"status": "draft"` olan kaydı bul. Başlık, metin ve TARİHLERİ resmi kaynakla karşılaştır.
3. Doğruysa `"draft"` -> `"published"` yap. Yanlışsa düzelt ya da kaydı sil.
4. Resmi sınav günü kaydıysa `"exam_day": true` ekle (uygulama tarih seçicide kısayol önerir).
5. "Commit changes" ile kaydet. Uygulama en geç 6 saat sonra yeni haliyle çeker.

Elle duyuru eklemek için `tools/news/inbox.json` dosyasına
`{"exam":"yks","source_name":"ÖSYM","url":"https://...","title":"...","text":"resmi metin"}` ekle;
sonraki günlük çalıştırmada özetlenip taslak olarak eklenir.
