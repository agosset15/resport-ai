# Отчёт о пересборке маршрутизации

Сгенерирован `tools/retier.py`. **Требует ревью врача до беты.**

Красные флаги (`rf_emergency_*`) и правила «к врачу сегодня» (`today_*`) не менялись.
Понижены только правила из явных списков `DEMOTE_PLANNED` и `DEMOTE_UNCLEAR`;
любой другой `reason_code` остался направлением к специалисту.

- сценариев изменено: 15
- правил `planned_*` переведено в самостоятельное восстановление: 120
- правил `unclear_*` удалено: 132
- правил оставлено без изменений: 541

## adductor_strain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_ad_location` | planned -> self_rehab (watch_ad_location) | план self_rehab_guarded |
| `planned_ad_onset` | planned -> self_rehab (watch_ad_onset) | план self_rehab_guarded |
| `planned_ad_walk` | planned -> self_rehab (watch_ad_walk) | план self_rehab_guarded |
| `planned_ad_recurrence` | planned -> self_rehab (watch_ad_recurrence) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_ad_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_ad_onset` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_ad_recurrence` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 40 правил.

## ankle_sprain.yaml  (version 2 → 3)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_a_swelling` | planned -> self_rehab (watch_a_swelling) | план self_rehab_guarded |
| `planned_a_instability` | planned -> self_rehab (watch_a_instability) | план self_rehab_guarded |
| `planned_a_course` | planned -> self_rehab (watch_a_course) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_a_mechanism` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_a_course` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 41 правил.

## basketball.finger_sprain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_f_which` | planned -> self_rehab (watch_f_which) | план self_rehab_guarded |
| `planned_f_course` | planned -> self_rehab (watch_f_course) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_which` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_mechanism` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_pinch` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_course` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 38 правил.

## basketball.hamstring_strain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_h_moment` | planned -> self_rehab (watch_h_moment) | план self_rehab_guarded |
| `planned_h_location` | planned -> self_rehab (watch_h_location) | план self_rehab_guarded |
| `planned_h_walk` | planned -> self_rehab (watch_h_walk) | план self_rehab_guarded |
| `planned_h_recurrence` | planned -> self_rehab (watch_h_recurrence) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_h_moment` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_h_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_h_recurrence` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 38 правил.

## basketball.patellar_tendinopathy.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_pt_location` | planned -> self_rehab (watch_pt_location) | план self_rehab_guarded |
| `planned_pt_trigger` | planned -> self_rehab (watch_pt_trigger) | план self_rehab_guarded |
| `planned_pt_warmup` | planned -> self_rehab (watch_pt_warmup) | план self_rehab_guarded |
| `planned_pt_progression` | planned -> self_rehab (watch_pt_progression) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_onset` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_trigger` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_warmup` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_progression` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 35 правил.

## basketball.patellofemoral_pain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_pf_location` | planned -> self_rehab (watch_pf_location) | план self_rehab_guarded |
| `planned_pf_onset` | planned -> self_rehab (watch_pf_onset) | план self_rehab_guarded |
| `planned_pf_when` | planned -> self_rehab (watch_pf_when) | план self_rehab_guarded |
| `planned_pf_load_response` | planned -> self_rehab (watch_pf_load_response) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_onset` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_when` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_load_response` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 38 правил.

## basketball.quadriceps_strain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_qd_mechanism` | planned -> self_rehab (watch_qd_mechanism) | план self_rehab_guarded |
| `planned_qd_location` | planned -> self_rehab (watch_qd_location) | план self_rehab_guarded |
| `planned_qd_walk` | planned -> self_rehab (watch_qd_walk) | план self_rehab_guarded |
| `planned_qd_relapse` | planned -> self_rehab (watch_qd_relapse) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_qd_mechanism` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_qd_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_qd_relapse` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 39 правил.

## football.adductor_strain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_ad_location` | planned -> self_rehab (watch_ad_location) | план self_rehab_guarded |
| `planned_ad_onset` | planned -> self_rehab (watch_ad_onset) | план self_rehab_guarded |
| `planned_ad_walk` | planned -> self_rehab (watch_ad_walk) | план self_rehab_guarded |
| `planned_ad_recurrence` | planned -> self_rehab (watch_ad_recurrence) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_ad_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_ad_onset` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_ad_recurrence` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 40 правил.

## football.ankle_sprain.yaml  (version 2 → 3)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_a_swelling` | planned -> self_rehab (watch_a_swelling) | план self_rehab_guarded |
| `planned_a_instability` | planned -> self_rehab (watch_a_instability) | план self_rehab_guarded |
| `planned_a_course` | planned -> self_rehab (watch_a_course) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_a_mechanism` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_a_course` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 41 правил.

## football.finger_sprain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_f_which` | planned -> self_rehab (watch_f_which) | план self_rehab_guarded |
| `planned_f_course` | planned -> self_rehab (watch_f_course) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_which` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_mechanism` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_pinch` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_f_course` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 38 правил.

## football.hamstring_strain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_h_moment` | planned -> self_rehab (watch_h_moment) | план self_rehab_guarded |
| `planned_h_location` | planned -> self_rehab (watch_h_location) | план self_rehab_guarded |
| `planned_h_walk` | planned -> self_rehab (watch_h_walk) | план self_rehab_guarded |
| `planned_h_recurrence` | planned -> self_rehab (watch_h_recurrence) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_h_moment` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_h_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_h_recurrence` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 38 правил.

## football.patellar_tendinopathy.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_pt_location` | planned -> self_rehab (watch_pt_location) | план self_rehab_guarded |
| `planned_pt_trigger` | planned -> self_rehab (watch_pt_trigger) | план self_rehab_guarded |
| `planned_pt_warmup` | planned -> self_rehab (watch_pt_warmup) | план self_rehab_guarded |
| `planned_pt_progression` | planned -> self_rehab (watch_pt_progression) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_onset` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_trigger` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_warmup` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pt_progression` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 35 правил.

## football.patellofemoral_pain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_pf_location` | planned -> self_rehab (watch_pf_location) | план self_rehab_guarded |
| `planned_pf_onset` | planned -> self_rehab (watch_pf_onset) | план self_rehab_guarded |
| `planned_pf_when` | planned -> self_rehab (watch_pf_when) | план self_rehab_guarded |
| `planned_pf_load_response` | planned -> self_rehab (watch_pf_load_response) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_onset` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_when` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_pf_load_response` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 38 правил.

## football.quadriceps_strain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `planned_g_trend` | planned -> self_rehab (watch_g_trend) | план self_rehab_guarded |
| `planned_g_pain_swelling` | planned -> self_rehab (watch_g_pain_swelling) | план self_rehab_guarded |
| `planned_qd_mechanism` | planned -> self_rehab (watch_qd_mechanism) | план self_rehab_guarded |
| `planned_qd_location` | planned -> self_rehab (watch_qd_location) | план self_rehab_guarded |
| `planned_qd_walk` | planned -> self_rehab (watch_qd_walk) | план self_rehab_guarded |
| `planned_qd_relapse` | planned -> self_rehab (watch_qd_relapse) | план self_rehab_guarded |
| `planned_g_history` | planned -> self_rehab (watch_g_history) | план self_rehab_guarded |
| `planned_g_sleep` | planned -> self_rehab (watch_g_sleep) | план self_rehab_guarded |
| `planned_g_program` | planned -> self_rehab (watch_g_program) | план self_rehab_guarded |
| `unclear_g_prior_eval` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_qd_mechanism` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_qd_location` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_qd_relapse` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_history` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_comorbid` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_sleep` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_program` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `unclear_g_help_access` | удалено | ответ «не знаю» больше не ведёт к врачу |
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 39 правил.

## patellar_pain.yaml  (version 1 → 2)

| reason_code | что сделано | примечание |
|---|---|---|
| `default_referral` | default -> self_rehab | план self_rehab_basic |

Без изменений: 3 правил.

