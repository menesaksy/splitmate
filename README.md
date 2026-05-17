# SplitMate — Grup Harcama Takip Uygulaması

SplitMate, arkadaşlar, ev arkadaşları veya seyahat grupları arasındaki
ortak harcamaları takip eden, borçları otomatik hesaplayan ve minimum
transfer sayısıyla netleştiren çok kullanıcılı bir web uygulamasıdır.
Django ile geliştirilmiştir.

> Yeditepe Üniversitesi — Django Dönem Projesi

**Canlı Uygulama:** [`<RENDER_URL>`](https://splitmate-p3ku.onrender.com)
**Kaynak Kod:** `https://github.com/menesaksy/splitmate`

---

## İçindekiler

- [Özellikler](#özellikler)
- [Teknoloji Yığını](#teknoloji-yığını)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [REST API](#rest-api)
- [Testler](#testler)
- [Proje Yapısı](#proje-yapısı)

---

## Özellikler

- **Kullanıcı Hesapları** — Kayıt olma, giriş ve çıkış (Django auth).
- **Yetkilendirme** — Her kullanıcı yalnızca üyesi olduğu grupları görür ve düzenleyebilir.
- **Grup Yönetimi** — Grup oluşturma, düzenleme, silme ve davet kodu ile katılma.
- **Harcama CRUD** — Harcama ekleme, listeleme, detay görüntüleme ve silme.
- **Esnek Paylaşım** — Eşit, birebir tutar veya yüzdelik paylaşım seçenekleri.
- **Borç Netleştirme** — Minimum Cash Flow algoritması ile en az transfer sayısında borç kapatma.
- **Arama ve Filtreleme** — Başlık/açıklama araması ve kategori/tarih filtresi.
- **Sayfalama** — Harcama listesi sayfa sayfa görüntülenir.
- **AJAX** — Hızlı ödeme kaydı, sayfa yenilenmeden gerçekleşir.
- **REST API** — Django REST Framework ile grup, harcama ve ödeme uç noktaları.
- **Döviz Kuru** — Frankfurter.app üzerinden anlık USD/EUR → TRY kuru.
- **PDF Export** — Grup özeti (harcamalar, üyeler, bakiyeler) PDF olarak indirilebilir.
- **Duyarlı Arayüz** — Bootstrap 5 ile mobil, tablet ve masaüstü uyumu.

---

## Teknoloji Yığını

| Katman      | Teknoloji                          |
|-------------|------------------------------------|
| Backend     | Python 3, Django 6                 |
| API         | Django REST Framework              |
| Veritabanı  | SQLite (geliştirme)                |
| Frontend    | HTML, Bootstrap 5, Bootstrap Icons |
| Dinamik UI  | Vanilla JavaScript (Fetch API)     |
| Dış API     | Frankfurter.app (döviz kuru)       |
| PDF         | ReportLab                          |
| Dağıtım     | Gunicorn, WhiteNoise, Render       |

---

## Kurulum

### Gereksinimler

- Python 3.10 veya üzeri
- pip ve venv

### Adımlar

```bash
# 1. Depoyu klonla
git clone https://github.com/menesaksy/splitmate.git
cd splitmate

# 2. Sanal ortam oluştur ve etkinleştir
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 3. Bağımlılıkları yükle
pip install -r requirements.txt

# 4. Ortam değişkenlerini ayarla
cp .env.example .env
# .env dosyasını düzenle: SECRET_KEY değerini doldur

# 5. Veritabanını hazırla
python manage.py migrate

# 6. Yönetici hesabı oluştur
python manage.py createsuperuser

# 7. Sunucuyu başlat
python manage.py runserver
```

Uygulama `http://127.0.0.1:8000` adresinde çalışır.

### Ortam Değişkenleri

`.env.example` dosyasını kopyalayarak `.env` oluşturun:

```
SECRET_KEY=uzun-rastgele-bir-anahtar
DEBUG=True
```

---

## Kullanım

1. `/signup` üzerinden hesap oluştur veya `/accounts/login/` ile giriş yap.
2. **Yeni Grup** ile bir grup oluştur (para birimi seç: TRY/USD/EUR).
3. Davet kodunu arkadaşlarınla paylaş; onlar `/groups/join/` üzerinden katılsın.
4. **Harcama Ekle** ile harcama gir; paylaşım yöntemini seç (eşit/tutar/yüzde).
5. Grup detay sayfasında **Önerilen Ödemeler** bölümü kimin kime ne kadar ödeyeceğini gösterir.
6. Ödeme yapıldığında **✓** butonuna tıkla (AJAX ile kayıt yapılır).
7. **PDF İndir** ile ay sonu özetini PDF olarak al.

---

## REST API

Tüm uç noktalar oturum açmış kullanıcı gerektirir.

| Yöntem | Uç Nokta                          | Açıklama                            |
|--------|-----------------------------------|-------------------------------------|
| GET    | `/api/groups/`                    | Kullanıcının grupları               |
| GET    | `/api/groups/{id}/`               | Grup detayı                         |
| GET    | `/api/groups/{id}/balances/`      | Grup bakiyeleri + önerilen ödemeler |
| GET    | `/api/expenses/`                  | Kullanıcının gruplarındaki harcamalar |
| GET    | `/api/settlements/`               | Ödemeler                            |

Tarayıcıdan test etmek için `/api-auth/login/` üzerinden giriş yapıp
`/api/` adresini ziyaret edebilirsiniz (DRF Browsable API).

---

## Testler

```bash
python manage.py test
```

Test paketi şunları kapsar: model davranışları, borç netleştirme
algoritması, view erişim ve yetkilendirme, davet kodu akışı, AJAX
endpoint'i ve REST API.

```
Ran 21 tests in ~24s
OK
```

---

## Proje Yapısı

```
splitmate/
├── config/              # Proje ayarları ve kök URL yapılandırması
│   ├── settings.py
│   └── urls.py
├── expenses/            # Ana uygulama
│   ├── models.py        # Group, Membership, Expense, ExpenseShare, Settlement, Category
│   ├── views.py         # CRUD view'leri, AJAX ve PDF export
│   ├── forms.py         # Form sınıfları
│   ├── services.py      # Borç netleştirme algoritması + döviz kuru
│   ├── serializers.py   # REST API serializer'ları
│   ├── api.py           # REST API viewset'leri
│   ├── urls.py          # Uygulama URL'leri
│   ├── admin.py         # Yönetim paneli yapılandırması
│   ├── tests.py         # Test paketi (21 test)
│   └── templates/       # HTML şablonları
├── static/css/          # Özel stiller
├── .env.example         # Örnek ortam değişkenleri
├── requirements.txt
└── manage.py
```

---

## Notlar

- Render ücretsiz plan kullanıldığı için ilk yüklemede 30-50 saniye
  bekleme süresi olabilir (spin down durumundan uyanma).
- Döviz kuru özelliği yalnızca USD veya EUR para birimli gruplarda
  dashboard'da görünür.
