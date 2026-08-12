TR Türkçe | EN [English](README.md)

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

`metrics.json`'daki `otel.name` / `otel.instrument` / `otel.unit` /
`required_attributes` değerleri, gerçek ve şu an çalışan telemetri
üreticisinden (`kio_simulator.py`'ın `create_histogram("kio.codegen.duration_minutes", ...)`
ve benzerlerinden) alınmıştır, uydurulmamıştır — paketin production'da
gerçekten yayınlanan isimle uyuşmayan bir isim taşıması, bu dosyanın
önlemeye çalıştığı tam olarak o hatayı yeniden yaratır. `required_attributes`,
`kio_simulator.py`'ın her zaman eklediği etiketleri (`kio.id`, `llm`,
`task_type`, `source`) yansıtır.

### Netleşen tasarım kararları

- **KPI 8.2 ("Active usage & satisfaction") iki gerçek OTel metriğine karşılık
  geliyor.** `kio_simulator.py` bunu `kio.adoption.usage_pct` ve
  `kio.adoption.mos_score` olarak yayınlıyor — `otel` şeması bunu liste
  yapacak şekilde genişletildi, ikisi de `.record(value, otel_key=...)` ile
  ayırt ediliyor (yukarıya bakın). `KPIMetric.otel` tek-instrument'lı yaygın
  durum için kısayol olmaya devam ediyor; KPI 8.2 için `None` çünkü
  otomatik birini seçmek sessiz bir tahmin olurdu.
- **KPI 4.1 ("Developer productivity") sahipleri arasında `KIO1` listeleniyor**,
  `kio_simulator.py`'ın `KIO_REAL_KPI_ROLE` haritasında KIO1'e hiçbir rol
  atanmamış olsa bile (pratikte `kio.dev_productivity.features_per_day`'i
  gerçekten yayınlayan KIO7'nin `"ai-sysdev"` rolü). Karar: **olduğu gibi
  bırakıldı** — orijinal KPI tablosu (D1.1) KIO1'i hâlâ ortak sahip sayıyor,
  simülatörün henüz bir KIO1 container'ına sırası gelmemiş olması katalogun
  onu düşürmesi gerektiği anlamına gelmiyor. `KPI.KIO1.developer_productivity`
  şu an üreticisi olmayan ama gerçek bir metadata, bug değil.

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

# OTel enstrümantasyon kontratı -- gerçek kio_simulator.py implementasyonuyla
# uyumlu, uydurulmuş değil (yukarıdaki "Neden sadece isim yetmiyor"a bakın).
print(metric.otel.name)                 # "kio.codegen.duration_minutes"
print(metric.otel.instrument)           # "Histogram"
print(metric.otel.unit)                 # "min"        (ham OTel ölçüm birimi)
print(metric.otel.required_attributes)  # ["kio.id", "source", "llm", "task_type"]
```

### Ölçüm gönderme (`pip install ai4sweng[otel]` gerektirir)

```python
from ai4sweng import KPI

# kio.id="KIO7" otomatik eklenir çünkü KIO7 üzerinden erişildi.
KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline", llm="qwen2.5:3b", task_type="generic")

# Counter tipi bir metrik
KPI.KIO2.customer_reported_issues.record(1, source="qa-bot", llm="qwen2.5:3b", task_type="bugfix")

# Zorunlu attribute eksikse net bir hata alırsınız:
KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline")
# ValueError: Missing required attribute(s) for 'kio.codegen.duration_minutes': llm, task_type. ...

# metrics.json'da otel bloğu tanımlı değilse veya opentelemetry-api kurulu
# değilse .record() da benzer şekilde açıklayıcı bir hata fırlatır.
```

Bazı KPI'lar birden fazla gerçek OTel metriğine karşılık gelir — örn. KPI 8.2
("Active usage & satisfaction") `kio_simulator.py`'da aslında iki ayrı
histogram: `kio.adoption.usage_pct` ve `kio.adoption.mos_score`. Bunlar için
hangisini kastettiğinizi `otel_key` ile belirtin:

```python
KPI.KIO13.active_usage_satisfaction.record(62.0, otel_key="usage_pct", source="svc", llm="qwen2.5:3b", task_type="adoption")
KPI.KIO13.active_usage_satisfaction.record(4.1, otel_key="mos_score", source="svc", llm="qwen2.5:3b", task_type="adoption")

# Birden fazla instrument'ı olan bir KPI'de otel_key verilmezse net bir hata alırsınız:
KPI.KIO13.active_usage_satisfaction.record(62.0, source="svc", llm="qwen2.5:3b", task_type="adoption")
# ValueError: KPI '8.2' has multiple OTel instruments: ['usage_pct', 'mos_score']. Pass otel_key=<one of these> to .record().
```

`KPI.get_kpi("1.1")` ile bir KPI'yı doğrudan id'siyle alırsanız, hangi KIO
üzerinden kaydedileceği belirsiz olduğundan `.record()` yoktur; önce
`.for_kio("KIO3")` ile bağlayın:

```python
kpi = KPI.get_kpi("1.1").for_kio("KIO3")
kpi.record(95.0, source="ci-pipeline", llm="qwen2.5:3b", task_type="generic")
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

## Keşfedilebilirlik: docstring'ler, `dir()` ve IDE otomatik tamamlama

`ai4sweng/kpi.py` ve `ai4sweng/otel.py` içindeki her sınıf ve fonksiyonun bir
açıklaması ve çalıştırılabilir bir kullanım örneği içeren docstring'i var.
Herhangi biri için Python'un yerleşik `help()` fonksiyonunu kullanabilirsiniz
(REPL veya notebook içinde):

```python
help(KPI.list_kios)
help(KPI.KIO7.code_generation_speed.record)
```

`KPI.KIO7` ve `KPI.KIO7.code_generation_speed` `metrics.json`'dan dinamik
olarak üretiliyor, ama **gerçek attribute** olarak — `__getattr__` sihriyle
değil — özellikle `dir(KPI)`, `hasattr(...)` ve düz Python REPL /
IPython/Jupyter'da otomatik tamamlamanın bunları hemen görebilmesi için.

Bir kod editörünün otomatik tamamlaması (VS Code + Pylance, PyCharm, mypy)
farklı çalışır: bu araçlar kaynak kodu statik olarak okur, `_load()`'ı hiç
çalıştırmaz — dolayısıyla kendi başlarına `KPI.KIO7`'nin var olduğunu bile
bilemezler. Bunu çözmek için paket, `metrics.json`'dan
[`scripts/gen_stubs.py`](scripts/gen_stubs.py) tarafından üretilen bir tip
stub dosyası taşıyor: [`ai4sweng/__init__.pyi`](ai4sweng/__init__.pyi) (artı
[PEP 561](https://peps.python.org/pep-0561/) `py.typed` işaretçisi). Editörde
`KPI.KIO7.<Tab>` otomatik tamamlamasını asıl çalıştıran bu stub'dır —
**bir KPI/KIO ekleyip, silip ya da yeniden adlandırdığınızda yeniden
çalıştırın**:

```bash
python scripts/gen_stubs.py
```

`tests/test_stubs.py`, commit'lenmiş stub `metrics.json` ile senkron değilse
test suite'i başarısız yapar — böylece bayat bir stub fark edilmeden
sızamaz.

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
  "otel": [
    {
      "name": "kio.example_metric_name",
      "instrument": "Histogram",
      "unit": "s",
      "required_attributes": ["source", "llm", "task_type"]
    }
  ]
}
```

- `attr`: Python tarafında `KPI.KIO3.<attr>` şeklinde erişilecek isim (geçerli
  bir identifier olmalı). Belirtilmezse `name` alanından otomatik türetilir.
- `kios`: Bu KPI'nın ilişkili olduğu KIO'ların listesi. Bir KPI birden fazla
  KIO'ya bağlı olabilir.
- `otel`: **her zaman bir liste**, tek instrument olsa bile (yaygın durum).
  İkinci bir eleman — her biri kendi `key`'iyle — sadece bu KPI gerçekten
  birden fazla OTel metriğine karşılık geliyorsa ekleyin; örnek için
  `metrics.json`'daki KPI 8.2'ye, çağıranın hangisini seçeceği için de
  yukarıdaki `.record(value, otel_key=...)` bölümüne bakın.
- `otel[].instrument`: `Counter`, `UpDownCounter`, `Histogram` veya `Gauge`
  değerlerinden biri olmalı (`Gauge` için `opentelemetry-api>=1.23` gerekir).
- `otel[].unit`: OTel/UCUM tarzı ham ölçüm birimi (örn. `"s"`, `"J"`, `"1"`,
  `"{issue}"`) — tablodaki iş/raporlama birimiyle (`unit`) karıştırmayın.
- `otel[].required_attributes`: `kio.id` dışında, çağıran tarafın `.record()`'a
  vermesi zorunlu attribute anahtarları (`kio.id` her zaman otomatik eklenir,
  burada tekrar belirtmenize gerek yok). Bu projenin kuralı
  `["source", "llm", "task_type"]` — `kio_simulator.py`'ın gerçek etiket
  setini yansıtıyor.
- Dosyanın en üstündeki `kios` listesi, henüz hiç metriği olmasa da hangi
  KIO'ların tanımlı olduğunu belirtir (`KPI.list_kios()` çıktısını ve
  `KPI.KIOx` erişimini buradan alır).

**Uydurulmuş isimler yerine gerçek isimleri tercih edin.** Yeni bir `otel`
girişi eklemeden önce, `kio_simulator.py`'ın (ya da gerçek telemetri
üreticiniz her ne ise) bu KPI'yı zaten bir `kio.*` metrik adı altında
yayınlayıp yayınlamadığını kontrol edin — tahmin etmek yerine o ismi/
instrument'ı/birimi birebir kopyalayın. Sadece `metrics.json`'da var olup
production'da olmayan bir isim, bu dosyanın önlemeye çalıştığı etiketleme
hatasını yeniden yaratır (aşağıya bakın).

Değişiklikten sonra paketi yeniden başlatmanıza gerek yok; `KPI.reload()`
çağırmanız yeterli.

## Testleri çalıştırma

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_otel.py`, `opentelemetry-sdk` kuruluysa gerçek bir
`InMemoryMetricReader` ile kayıt davranışını (doğru instrument tipi, doğru
attribute'lar) uçtan uca doğrular.
