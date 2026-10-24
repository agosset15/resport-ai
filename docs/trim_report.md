# Отчёт о сокращении опроса

Сгенерирован `tools/trim.py`. **Требует ревью врача до беты.**

Детальные вопросы безопасности сохранены полностью, но задаются после единого
скринера `g_alarm`. Ответ «не знаю» на скринер раскрывает весь каскад, поэтому
чувствительность к красным флагам не падает у тех, кто не уверен.

| сценарий | вопросов до | после | под скринером | удалено | правил убрано |
|---|---|---|---|---|---|
| adductor_strain.yaml | 25 | 25 | 5 | g_sleep | 2 |
| ankle_sprain.yaml | 24 | 24 | 5 | g_sleep | 2 |
| basketball.finger_sprain.yaml | 25 | 24 | 4 | g_dvt, g_sleep | 3 |
| basketball.hamstring_strain.yaml | 24 | 24 | 5 | g_sleep | 2 |
| basketball.patellar_tendinopathy.yaml | 24 | 24 | 5 | g_sleep | 1 |
| basketball.patellofemoral_pain.yaml | 24 | 24 | 5 | g_sleep | 1 |
| basketball.quadriceps_strain.yaml | 25 | 25 | 5 | g_sleep | 2 |
| football.adductor_strain.yaml | 25 | 25 | 5 | g_sleep | 2 |
| football.ankle_sprain.yaml | 24 | 24 | 5 | g_sleep | 2 |
| football.finger_sprain.yaml | 25 | 24 | 4 | g_dvt, g_sleep | 3 |
| football.hamstring_strain.yaml | 24 | 24 | 5 | g_sleep | 2 |
| football.patellar_tendinopathy.yaml | 24 | 24 | 5 | g_sleep | 1 |
| football.patellofemoral_pain.yaml | 24 | 24 | 5 | g_sleep | 1 |
| football.quadriceps_strain.yaml | 25 | 25 | 5 | g_sleep | 2 |
| patellar_pain.yaml | 7 | 7 | 0 | — | 0 |

## Удалённые red flags

Удаляются только вместе со своим вопросом — там, где он не относится к области тела:

- `rf_emergency_g_dvt_breath`

## Переписанные правила

`home_prescribed_program` — вместо конъюнкции на ~25 условий короткая проверка
«есть диагноз этого эпизода и назначена программа». Маршрутизация упорядочена,
поэтому до этого правила доходят только те, кто не задел ни одного правила выше:
перечислять все безопасные ответы заново было избыточно, а после появления
скринера стало ещё и невыполнимо.

`home_observation` — правило и план удалены: наблюдение 48–72 часа покрывает план
`self_rehab_basic`, который выдаёт default-правило.

