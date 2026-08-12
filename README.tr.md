TR Türkçe | EN [English](README.en.md)

# ai4sweng — KIO Modülleri için KPI Arayüzü

KIO modüllerinin sağlaması gereken KPI'ları tek bir arayüzden erişilebilir kılan
Python paketi. `KPI.KIO1`, `KPI.KIO2`, ... `KPI.KIO13` gibi her KIO için, o
modülle ilişkilendirilmiş KPI'lara nokta notasyonuyla erişim sağlar — hem
metadata (tanım, birim, baseline, hedef) hem de doğru etiketlenmiş
OpenTelemetry ölçümü göndermek için.

## Kurulum

Proje içinden (repo klonlanmış haldeyken):

```bash
pip install -e .
```

OpenTelemetry ile ölçüm göndermek (`.record()`) istiyorsanız `otel` extra'sını
da kurun:

```bash
pip install -e ".[otel]"
```

Git üzerinden doğrudan (takım arkadaşları bu şekilde kurabilir):

```bash
pip install "ai4sweng[otel] @ git+https://<repo-url>"
```

## Neden sadece isim yetmiyor

Bir metriğin doğru gönderilmesi için tek başına isim yeterli değil: aynı
değer, yanlış instrument tipiyle (Counter yerine Histogram, ya da tersi) veya
eksik bir attribute ile (`kio.id` resource'ta mı, metrik başına mı; `source`
var mı yok mu) gönderilirse dashboard'da hiç görünmeyebilir ya da yanlış
görünür. Bu paket her KPI için sadece isim değil; **isim + birim + OTel
instrument tipi + zorunlu attribute anahtarlarını** birlikte taşır ve
isteğe bağlı olarak bunları uygulayan bir `.record()` yardımcı metodu sunar.

`kio.id` **resource attribute değil, ölçüm başına (per-datapoint) attribute**
olarak tasarlandı, çünkü bir KPI birden fazla KIO'ya bağlı olabiliyor (örn.
`code_generation_speed` → KIO2, KIO3, KIO4, KIO7). Bu paket `KPI.KIO3.<metrik>`
üzerinden erişilen bir metriği kaydederken `kio.id="KIO3"` değerini
**otomatik olarak** ekler — geliştirici bunu elle yazmaz, dolayısıyla
yanlış/eksik girilemez.

## Kullanım

```python
from ai4sweng import KPI

# Tanımlı tüm KIO'ları listele
print(KPI.list_kios())
# ['KIO1', 'KIO2', ..., 'KIO13']

# KIO7 ile ilişkili bir metriğin metadata'sına eriş
metric = KPI.KIO7.code_generation_speed
print(metric.id)          # "1.1"
print(metric.name)        # "Code generation speed"
print(metric.definition)
print(metric.unit)        # "% of baseline duration"  (raporlama/iş birimi)
print(metric.baseline)    # "100% (~100-120 min)"
print(metric.target)      # "≤ 70% (~30% reduction)"
print(metric.kios)        # ["KIO2", "KIO3", "KIO4", "KIO7"]

# OTel enstrümantasyon kontratı
print(metric.otel.name)                 # "ai4sweng.kpi.code_generation_speed"
print(metric.otel.instrument)           # "Histogram"
print(metric.otel.unit)                 # "s"          (ham OTel ölçüm birimi)
print(metric.otel.required_attributes)  # ["kio.id", "source"]
```

### Ölçüm gönderme (`pip install ai4sweng[otel]` gerektirir)

```python
from ai4sweng import KPI

# kio.id="KIO7" otomatik eklenir çünkü KIO7 üzerinden erişildi.
KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline")

# Counter tipi bir metrik
KPI.KIO2.customer_reported_issues.record(1, source="qa-bot")

# Gauge tipi bir metrik
KPI.KIO13.adoption_rate.record(0.42, source="telemetry-service")

# Zorunlu attribute eksikse net bir hata alırsınız:
KPI.KIO7.code_generation_speed.record(95.0)
# ValueError: Missing required attribute(s) for 'ai4sweng.kpi.code_generation_speed': source. ...

# metrics.json'da otel bloğu tanımlı değilse veya opentelemetry-api kurulu
# değilse .record() da benzer şekilde açıklayıcı bir hata fırlatır.
```

`KPI.get_kpi("1.1")` ile bir KPI'yı doğrudan id'siyle alırsanız, hangi KIO
üzerinden kaydedileceği belirsiz olduğundan `.record()` yoktur; önce
`.for_kio("KIO3")` ile bağlayın:

```python
kpi = KPI.get_kpi("1.1").for_kio("KIO3")
kpi.record(95.0, source="ci-pipeline")
```

Diğer yardımcılar:

```python
# Bir KIO'nun tüm metriklerinde gezin
for m in KPI.KIO7:
    print(m)

# Bir KIO'nun metriklerini dict olarak al
metrics = KPI.get_kio_metrics("KIO8")

# Tüm KPI'ları listele
all_kpis = KPI.list_kpis()

# metrics.json dosyasını değiştirdikten sonra yeniden yükle
KPI.reload()
```

## Metrikleri düzenleme

Tüm KPI tanımları tek bir dosyada tutulur: [`ai4sweng/metrics.json`](ai4sweng/metrics.json).
Her KPI, ait olduğu tüm KIO'ları `kios` listesinde belirtir — aynı KPI'yı her
KIO için ayrı ayrı tanımlamaya gerek yoktur, paket eşleşmeyi otomatik kurar.

**`metrics.json` içindeki tüm alanlar (isim, tanım, birim, baseline, hedef)
İngilizce olmalı.** Bu dosya kod/veri katmanıdır ve teknik/uluslararası
tüketiciler için (dashboard'lar, diğer servisler, olası açık kaynak
paylaşımı) dile bağımsız kalmalıdır — Türkçe açıklamalar yalnızca bu
README'de ve yorum satırlarında kalsın.

Yeni bir KPI eklemek için listeye şu formatta bir obje ekleyin:

```json
{
  "id": "10.1",
  "name": "Example metric name",
  "attr": "example_metric_name",
  "definition": "What this metric measures.",
  "unit": "unit",
  "baseline": "baseline value",
  "target": "target value",
  "kios": ["KIO3", "KIO7"],
  "otel": {
    "name": "ai4sweng.kpi.example_metric_name",
    "instrument": "Histogram",
    "unit": "s",
    "required_attributes": ["source"]
  }
}
```

- `attr`: Python tarafında `KPI.KIO3.<attr>` şeklinde erişilecek isim (geçerli
  bir identifier olmalı). Belirtilmezse `name` alanından otomatik türetilir.
- `kios`: Bu KPI'nın ilişkili olduğu KIO'ların listesi. Bir KPI birden fazla
  KIO'ya bağlı olabilir.
- `otel.instrument`: `Counter`, `UpDownCounter`, `Histogram` veya `Gauge`
  değerlerinden biri olmalı (`Gauge` için `opentelemetry-api>=1.23` gerekir).
- `otel.unit`: OTel/UCUM tarzı ham ölçüm birimi (örn. `"s"`, `"J"`, `"1"`,
  `"{issue}"`) — tablodaki iş/raporlama birimiyle (`unit`) karıştırmayın.
- `otel.required_attributes`: `kio.id` dışında, çağıran tarafın `.record()`'a
  vermesi zorunlu attribute anahtarları (`kio.id` her zaman otomatik eklenir,
  burada tekrar belirtmenize gerek yok).
- Dosyanın en üstündeki `kios` listesi, henüz hiç metriği olmasa da hangi
  KIO'ların tanımlı olduğunu belirtir (`KPI.list_kios()` çıktısını ve
  `KPI.KIOx` erişimini buradan alır).

Değişiklikten sonra paketi yeniden başlatmanıza gerek yok; `KPI.reload()`
çağırmanız yeterli.

**Buradaki `otel.instrument` / `otel.unit` değerleri, her metriğin ölçüm
semantiğine göre önerilen varsayılanlardır** (süre → Histogram, anlık
oran/skor → Gauge, ayrık olay sayısı → Counter/UpDownCounter). Kendi
telemetry/backend kurulumunuza göre gözden geçirip düzeltmekten çekinmeyin.

## Testleri çalıştırma

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_otel.py`, `opentelemetry-sdk` kuruluysa gerçek bir
`InMemoryMetricReader` ile kayıt davranışını (doğru instrument tipi, doğru
attribute'lar) uçtan uca doğrular.
