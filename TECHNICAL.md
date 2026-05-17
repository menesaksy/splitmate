# Teknik Dokümantasyon — SplitMate

Bu belge SplitMate'in veri modelini, mimari kararlarını, borç
netleştirme algoritmasını ve geliştirme sürecinde karşılaşılan
sorunların çözümlerini açıklar.

---

## 1. Mimari Genel Bakış

SplitMate, Django'nun MVT (Model–View–Template) mimarisini izler:

- **Model katmanı** veri yapısını ve iş mantığını tanımlar.
- **View katmanı** HTTP isteklerini işler; çoğunlukla sınıf tabanlı
  generic view'ler kullanılır.
- **Template katmanı** Bootstrap 5 ile duyarlı arayüzü oluşturur.
- **Service katmanı** (`services.py`) iş mantığını view'den ayırır;
  borç hesaplama ve döviz kuru sorguları burada yapılır.
- **API katmanı** (`api.py`) Django REST Framework ile JSON uç noktaları
  sunar.

İstek akışı:

```
İstemci → urls.py → View → Service/Model → Template/JSON
```

---

## 2. Veri Modeli

Altı model vardır: `Category`, `Group`, `Membership`, `Expense`,
`ExpenseShare`, `Settlement`.

### 2.1 Category

Harcama kategorilerini tutar (Yemek, Ulaşım, Eğlence vb.).
`name` alanı benzersizdir.

### 2.2 Group

Harcama paylaşan kullanıcı grubunu temsil eder.

- `created_by` → `User` ForeignKey (CASCADE): grubu oluşturan yönetici.
- `members` → `User` ManyToManyField, ara tablo olarak `Membership`
  kullanır (`through='Membership'`). Böylece üyelik rolü (admin/üye)
  ara tabloda saklanır.
- `invite_code`: `secrets.token_urlsafe` ile otomatik üretilen benzersiz
  kod. Kullanıcılar bu kodla gruba katılır.
- `currency`: TRY/USD/EUR seçeneği. Çok para birimli destek için
  döviz kuru API'siyle birlikte çalışır.

### 2.3 Membership

`Group` ile `User` arasındaki çoka-çok ilişkinin ara tablosudur.
Standart ManyToManyField yerine `through` parametresiyle kullanılmasının
nedeni, üyelik rolü (admin/member) gibi ek bilgi tutulması gerekliliğidir.
`unique_together = ['user', 'group']` ile aynı kullanıcının aynı gruba
iki kez üye olması engellenir.

### 2.4 Expense

Tek bir harcamayı temsil eder.

- `paid_by` → `User` ForeignKey: harcamayı fiilen ödeyen kişi.
- `group` → `Group` ForeignKey (CASCADE): hangi gruba ait.
- `category` → `Category` ForeignKey (SET_NULL): kategori silinirse
  harcama kaybolmasın diye SET_NULL tercih edildi.
- `split_type`: `equal` / `exact` / `percent` seçenekleri. Paylaşım
  yöntemi `build_expense_shares` servisi tarafından işlenir.

### 2.5 ExpenseShare

Bir harcamanın her üyeye düşen payını saklar.
`unique_together = ['expense', 'user']` ile aynı harcamada bir
kullanıcının iki payı olması engellenir.
Bu tablo olmadan "kim ne kadar borçlu" sorusu yanıtsız kalır.

### 2.6 Settlement

Kullanıcıdan kullanıcıya yapılan ödemeyi kaydeder (borç kapatma).
`from_user` borçluyu, `to_user` alacaklıyı gösterir.
Bu kayıtlar `calculate_balances` fonksiyonunda bakiyeye dahil edilir,
böylece gerçek zamanlı bakiye hesaplanır.

### 2.7 İlişki Özeti

```
User ──1:N──► Group (created_by)
User ◄──M:M──► Group (through Membership)
Group ──1:N──► Expense
Expense ──1:N──► ExpenseShare ──N:1──► User
Group ──1:N──► Settlement ──N:1──► User (from/to)
Expense ──N:1──► Category
```

---

## 3. Borç Netleştirme Algoritması

Bu, SplitMate'in teknik açıdan en özgün bölümüdür.

### Problem

N kişilik bir grupta M harcama yapıldığında, naif yaklaşımla her kişi
herkese ayrı ayrı ödeme yapabilir (O(N²) transfer). Ancak minimum
sayıda transferle tüm borçlar kapatılabilir (en fazla N-1 transfer).

### Algoritma: Minimum Cash Flow (Greedy)

`services.py` içindeki `simplify_debts` fonksiyonu şu adımları izler:

1. **Net bakiye hesapla:** `calculate_balances` fonksiyonu her kullanıcı
   için toplam ödediği tutardan toplam payını çıkarır, ödeme geçmişini
   de dahil eder.
   - Pozitif bakiye → alacaklı (başkaları ona borçlu)
   - Negatif bakiye → borçlu (o başkasına ödeyecek)

2. **Alacaklı ve borçluları ayır**, büyükten küçüğe sırala.

3. **Greedy eşleştirme:** En çok borçlu ile en çok alacaklıyı eşleştir,
   ikisinin minimumunu transfer et. Biri sıfırlanınca bir sonrakine geç.
   Bu işlemi tüm bakiyeler sıfırlanana kadar tekrarla.

4. **Sonuç:** `(from_user_id, to_user_id, amount)` üçlüleri listesi.

```python
# Örnek: Alice +60, Bob -30, Carol -30
# Sonuç: [(Bob, Alice, 30), (Carol, Alice, 30)]
# Yani 3 kişi için 2 transfer — optimum.
```

Bu algoritmanın karmaşıklığı O(N log N)'dir (sıralama baskın).

### Neden önemli?

Splitwise, Tricount gibi uygulamaların temel algoritmasıdır. Gerçek
dünya problemini çözen, test edilmiş ve dokümante edilmiş bir
implementasyon sunmak projenin "innovative" boyutunu oluşturur.

---

## 4. View Tasarımı

CRUD işlemleri için Django'nun sınıf tabanlı generic view'leri
kullanılmıştır.

### Erişim Kontrolü

- `LoginRequiredMixin`: tüm view'ler oturum açmış kullanıcı gerektirir.
- `UserPassesTestMixin` + `test_func`: kullanıcının yalnızca üyesi
  olduğu gruplara erişmesini sağlar. Yetkisiz erişim HTTP 403 veya
  yönlendirme ile sonuçlanır.

### Sorgu Verimliliği

`GroupDetailView` içinde `select_related('paid_by', 'category')` ve
`prefetch_related('shares')` kullanılarak N+1 sorgu problemi önlenmiştir.
`GroupListView`'da `annotate` ile harcama sayısı ve toplamı tek sorguda
çekilir.

---

## 5. Servis Katmanı

`services.py` dosyası üç temel fonksiyon içerir:

- **`calculate_balances(group)`**: Ham bakiyeleri hesaplar.
- **`simplify_debts(group)`**: Minimum transfer listesi üretir.
- **`build_expense_shares(expense, split_type, members, custom)`**:
  Harcama paylarını oluşturur. Eşit, tutar veya yüzde modunda çalışır.
  Yuvarlama artıklarını ilk kişiye ekleyerek toplam tutarın korunmasını
  sağlar.
- **`get_exchange_rate(from_currency, to_currency)`**: Frankfurter.app
  API'sinden anlık döviz kuru çeker. Hata durumunda `None` döner,
  uygulama çökmez.

View'den ayrı tutulmasının nedeni: test edilebilirlik ve bakım
kolaylığı. Algoritma view'e bağımlı olmadan bağımsız test edilebilir.

---

## 6. REST API

Django REST Framework'ün `ReadOnlyModelViewSet` yapısı kullanılır.
Yazma işlemleri kasıtlı olarak devre dışıdır — veri değişikliği web
arayüzünden yapılır, API yalnızca veri okuma ve entegrasyon amaçlıdır.

Her viewset `get_queryset` metodunda sorguyu istek sahibinin verisiyle
sınırlar. `IsAuthenticated` ve özel `IsMember` izin sınıfları
kullanılır.

`/api/groups/{id}/balances/` ucu `@action` dekoratörüyle eklenmiş
özel bir endpoint'tir; borç netleştirme sonuçlarını JSON olarak sunar.

---

## 7. Frontend Kararları

- **Bootstrap 5** CDN üzerinden dahil edilir.
- Tüm şablonlar `base.html`'den miras alır.
- Favori işaretleme ve hızlı ödeme Fetch API ile AJAX üzerinden yapılır.
- **Chart.js** dahil edilmiş ancak dashboard grafikleri ileriki geliştirme
  için ayrılmıştır.

---

## 8. Dış Entegrasyonlar

### Döviz Kuru (Frankfurter.app)

Ücretsiz, API anahtarı gerektirmeyen bir döviz kuru servisidir.
`https://api.frankfurter.app/latest?from=USD&to=TRY` formatında
istek atılır. Yanıt önbelleklenmez; her dashboard yüklemesinde
taze veri çekilir. Servis erişilemezse `None` dönüp kullanıcı
arayüzü etkilenmez.

### PDF Export (ReportLab)

ReportLab kütüphanesiyle grup özeti PDF'i oluşturulur. İçerik:
üyeler ve rolleri, harcama tablosu, bakiyeler. PDF tarayıcıdan
indirme olarak sunulur (`Content-Disposition: attachment`).

---

## 9. Karşılaşılan Sorunlar ve Çözümleri

**N+1 sorgu problemi.** Harcama listesinde her harcama için ayrı
kategori ve pay sorgusu atılıyordu. `select_related` ve
`prefetch_related` kullanılarak tek sorguda çözüldü.

**Bakiye hesabında yuvarlama hatası.** Ondalıklı bölmeler küçük
artıklar bırakıyordu. `Decimal` sınıfı ve `.quantize(Decimal('0.01'))`
kullanılarak sabit noktalı aritmetik uygulandı.

**Pagination ile queryset çakışması.** `expenses` değişkeni
pagination'dan önce tanımlandığında `UnboundLocalError` hatası
alındı. Queryset `qs` adıyla yeniden adlandırılıp pagination
uygulandıktan sonra context'e `page_obj` olarak gönderildi.

**Döviz kuru API timeout.** Yavaş ağ koşullarında dashboard yavaş
yükleniyordu. `timeout=5` parametresi eklendi; hata durumunda
`except Exception` bloğu `None` döndürüp uygulama çökmesini önledi.

**Duplicate import hatası.** `get_exchange_rate` iki farklı satırda
import edilmişti. Tüm import'lar dosyanın üstünde tek yerde toplandı.

---

## 10. Olası Geliştirmeler

- Harcama güncelleme (UpdateView) eklenmesi.
- Bakiye grafiği (Chart.js ile çubuk veya pasta grafik).
- Aylık harcama özeti ve istatistik sayfası.
- E-posta bildirimi (yeni harcama eklenince).
- Recurring (tekrarlayan) harcamalar.
- Koleksiyon paylaşımı (gruba dışarıdan görüntüleme linki).
