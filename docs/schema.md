# Схема сущностей

## Базовые сущности

### `Hunter`

Карточка исследователя:

- `username`
- `name`
- `created_at`
- `location`
- `website`
- `verified`
- `cleared`
- `open_for_employment`
- `profile_activated`

### `Program`

Программа или команда, с которой у исследователя есть публичный след:

- `program_id`
- `name`
- `handle`
- `state`
- `url`
- `is_private_stub`

`is_private_stub` нужен потому, что HackerOne часто показывает не реальную программу, а агрегат `Private Program`.

### `Report`

Минимальная сущность для disclosed или агрегированно наблюдаемого результата:

- `report_id` nullable
- `hunter_username`
- `program_id` nullable
- `submitted_at` nullable
- `state` nullable
- `visibility` (`public`, `private_aggregate`)
- `reputation_delta` nullable

В текущем тестовом я не строил полный public-report слой, но именно так бы расширял модель дальше.

### `Skill`

Справочник компетенций:

- `skill_id`
- `skill_name`
- `source` (`self_declared`, `derived`, `external`)

### `Activity`

Любой наблюдаемый сигнал во времени:

- `activity_id`
- `hunter_username`
- `program_id` nullable
- `activity_type`
- `activity_date`
- `payload_json`

Через `Activity` удобно хранить и leaderboard-снапшоты, и badges, и thanks, и streak-изменения, и testimonials.

## Связи

ASCII-вариант:

```text
Hunter 1 --- N Activity
Hunter 1 --- N Report
Hunter N --- M Skill
Hunter N --- M Program
Program 1 --- N Report
Program 1 --- N Activity
```

Чуть подробнее:

- один `Hunter` связан со многими `Activity`;
- один `Hunter` может иметь много `Report`;
- один `Hunter` может быть связан с несколькими `Program`;
- один `Program` может фигурировать у многих `Hunter`;
- `Skill` лучше хранить отдельно и связывать через таблицу `hunter_skill`;
- `Activity` играет роль универсального журнала событий.

## Нормализованные таблицы

Если раскладывать это на таблицы, я бы сделал так:

### `hunters`

- `username` PK
- `name`
- `created_at`
- `location`
- `website`
- `verified`
- `cleared`
- `open_for_employment`
- `profile_activated`

### `programs`

- `program_id` PK
- `name`
- `handle`
- `state`
- `url`
- `is_private_stub`

### `reports`

- `report_pk` PK
- `report_id`
- `hunter_username`
- `program_id`
- `submitted_at`
- `state`
- `visibility`
- `reputation_delta`

### `skills`

- `skill_id` PK
- `skill_name`
- `source`

### `hunter_skills`

- `hunter_username`
- `skill_id`

### `activities`

- `activity_id` PK
- `hunter_username`
- `program_id`
- `activity_type`
- `activity_date`
- `payload_json`

### `stat_snapshots`

- `snapshot_id` PK
- `hunter_username`
- `snapshot_type`
- `signal`
- `signal_percentile`
- `impact`
- `impact_percentile`
- `reputation`
- `rank`

### `thanks_items`

- `thanks_item_id` PK
- `hunter_username`
- `program_id`
- `report_count`
- `total_report_count`
- `reputation`
- `rank`
- `is_private_program`

## Формат хранения

Для этой задачи я бы использовал сразу три слоя.

### `JSON`

Для raw-слоя. Хорош тем, что ответы `graphql` уже приходят в богатой вложенной структуре. Ничего не теряется, и через неделю можно допарсить новое поле без повторного похода в сеть.

### `CSV`

Для аналитической витрины. Его удобно открыть глазами, быстро прогнать через pandas или отдать менеджеру / рекрутеру.

### `SQLite`

Для portable-рабочего слоя между raw и production-БД. Если нужно локально делать джойны, фильтры и небольшую историю, это очень удобный компромисс. В тестовом я его не генерировал, чтобы не утяжелять набор файлов, но для боевой задачи добавил бы обязательно.
