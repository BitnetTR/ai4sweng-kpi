"""ai4sweng KPI paketini keşfetmek için birkaç örnek. `python test.py` ile çalıştırın."""

from ai4sweng import KPI


# 0) List KIOx
print("KIOx listesi:", KPI.list_kios())

# 1) Bir KIOx'nun hangi KPI'lara sahip olduğu
# 1) Which KPIs are available for a KIOx
print("Attribute isimleri:", dir(KPI.KIO2))


# 2) Her metriğin tam detayı 
# 2) Full details of each metric
for metric in KPI.KIO2:
    print(f"\n--- {metric.attr} ---")
    print(f"  id          : {metric.id}")
    print(f"  name        : {metric.name}")
    print(f"  definition  : {metric.definition}")
    print(f"  unit        : {metric.unit}")
    print(f"  baseline    : {metric.baseline}")
    print(f"  target      : {metric.target}")
    print(f"  kios        : {metric.kios}")  # bu KPI'nın bağlı olduğu diğer KIO'lar


# 3) Metriklerin veri yapılarını OTel enstrümantasyon kontratı içerisinden incelemek — dashboard'a nasıl gönderileceğini gösterir.
# 3) Inspect the data structures of metrics from the OTel instrumentation contract — shows how they will be sent to the dashboard.
metric = KPI.KIO2.code_generation_speed

# DİKKAT: burada iki farklı "isim" var, birbiriyle karıştırılmamalı:
# NOTE: there are two different "names" here, don't confuse them:
print("metric.name       (iş/rapor katmanı, D1.1 tablosundaki insan-okunur ad) :", metric.name)
print("metric.otel.name  (telemetri katmanı, kio_simulator.py'nin gerçekten gönderdiği teknik ad):", metric.otel.name)
print()

print(metric.otel)
print("instrument         :", metric.otel.instrument)
print("otel adı           :", metric.otel.name)
print("ham OTel birimi    :", metric.otel.unit)
print("zorunlu attribute'lar:", metric.otel.required_attributes)


# 5) help() ile daha ayrıntılı açıklama + kullanım örneğine bakmak
# 5) Use help() to see more detailed description + usage example
# help(KPI.KIO2.customer_reported_issues.record)



# 6) Bir metriği kaydetmek (pip install ai4sweng[otel] gerektirir)
# 6) Record a metric (requires pip install ai4sweng[otel])
# try:
#     sonuc = KPI.KIO2.code_generation_speed.record(
#         82.0, source="manual-test", llm="qwen2.5:3b", task_type="bugfix"
#     )
#     print("Kaydedilen attribute'lar:", sonuc)
# except ImportError as e:
#     print("OTel kurulu değil, atlanıyor:", e)
