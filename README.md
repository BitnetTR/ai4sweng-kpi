# ai4sweng - KPI Interface for KIO Modules

KIO modüllerinin sağlaması gereken KPI'ları tek bir arayüzden erişilebilir kılan
Python paketi. `KPI.KIO1`, `KPI.KIO2`, ... `KPI.KIO13` gibi her KIO için, o modülle
ilişkilendirilmiş KPI'lara nokta notasyonuyla erişim sağlar.

## Kurulum

Proje içinden (repo klonlanmış haldeyken):

```bash
pip install -e .
```

Git üzerinden doğrudan (takım arkadaşları bu şekilde kurabilir):

```bash
pip install git+https://<repo-url>
```

## Kullanım

```python
from ai4sweng import KPI

# Tanımlı tüm KIO'ları listele
print(KPI.list_kios())
# ['KIO1', 'KIO2', ..., 'KIO13']

# KIO7 ile ilişkili bir metriğe eriş
metric = KPI.KIO7.code_generation_speed
print(metric.id)          # "1.1"
print(metric.name)        # "Code generation speed"
print(metric.definition)
print(metric.unit)        # "% baseline süre"
print(metric.baseline)    # "100% (~100-120 dk)"
print(metric.target)      # "≤ 70% (~%30 azalma)"
print(metric.kios)        # ["KIO2", "KIO3", "KIO4", "KIO7"]

# Bir KIO'nun tüm metriklerinde gezin
for m in KPI.KIO7:
    print(m)

# Bir KIO'nun metriklerini dict olarak al
metrics = KPI.get_kio_metrics("KIO8")

# KPI id'sine göre doğrudan eriş
kpi = KPI.get_kpi("9.2")

# Tüm KPI'ları listele
all_kpis = KPI.list_kpis()

# metrics.json dosyasını değiştirdikten sonra yeniden yükle
KPI.reload()
```

## Metrikleri düzenleme

Tüm KPI tanımları tek bir dosyada tutulur: [`ai4sweng/metrics.json`](ai4sweng/metrics.json).
Her KPI, ait olduğu tüm KIO'ları `kios` listesinde belirtir — aynı KPI'yı her KIO için
ayrı ayrı tanımlamaya gerek yoktur, paket eşleşmeyi otomatik olarak kurar.

Yeni bir KPI eklemek için listeye şu formatta bir obje ekleyin:

```json
{
  "id": "10.1",
  "name": "Example metric name",
  "attr": "example_metric_name",
  "definition": "Metriğin ne ölçtüğünün açıklaması.",
  "unit": "birim",
  "baseline": "başlangıç değeri",
  "target": "hedef değer",
  "kios": ["KIO3", "KIO7"]
}
```

- `attr`: Python tarafında `KPI.KIO3.<attr>` şeklinde erişilecek isim (geçerli bir
  identifier olmalı). Belirtilmezse `name` alanından otomatik türetilir.
- `kios`: Bu KPI'nın ilişkili olduğu KIO'ların listesi. Bir KPI birden fazla KIO'ya
  bağlı olabilir.
- Dosyanın en üstündeki `kios` listesi, henüz hiç metriği olmasa da hangi KIO'ların
  tanımlı olduğunu belirtir (`KPI.list_kios()` çıktısını ve `KPI.KIOx` erişimini
  buradan alır).

Değişiklikten sonra paketi yeniden başlatmanıza gerek yok; `KPI.reload()` çağırmanız
yeterli.
