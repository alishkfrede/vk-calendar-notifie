# VK Calendar Notifier

Сервис уведомлений о событиях календаря через ВКонтакте. Автоматический мониторинг Google Calendar, обработка событий по заданным правилам и отправка персонализированных уведомлений в личные сообщения VK.

## 📋 Содержание

- [Архитектура системы](#архитектура-системы)
- [Технологический стек](#технологический-стек)
- [Структура проекта](#структура-проекта)
- [Переменные окружения](#переменные-окружения)
- [Инструкция по запуску](#инструкция-по-запуску)
- [Спецификация REST API](#спецификация-rest-api)
- [Бизнес-логика](#бизнес-логика)
- [Тестирование](#тестирование)
- [Демонстрация работы](#демонстрация-работы)

---

## 🏗 Архитектура системы

Система построена по модульному принципу с разделением ответственности:

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI (REST API)                       │
│  /users  /events  /sync  /notify  /settings  /admin             │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Google Cal    │    │ Notification     │    │ VK API Client    │
│ Service       │    │ Engine           │    │ + LongPoll       │
│ (OAuth+Sync)  │    │ (бизнес-логика)  │    │                  │
└───────────────┘    └──────────────────┘    └──────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │   APScheduler        │
                    │  (фоновые задачи)    │
                    └──────────────────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │   SQLAlchemy ORM     │
                    │   + SQLite/PostgreSQL│
                    └──────────────────────┘
```

### Потоки данных

1. **Авторизация пользователя**: VK user → REST API → Google OAuth → сохранение токенов в БД
2. **Синхронизация**: REST API → Google Calendar API → парсинг событий → сохранение в БД
3. **Генерация уведомлений**: APScheduler (каждую минуту) → NotificationEngine → VK API
4. **Обработка команд**: VK LongPoll → парсинг команд → обновление БД → ответ пользователю

---

## 🛠 Технологический стек

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Язык | Python | 3.14 |
| Веб-фреймворк | FastAPI | 0.115.0 |
| ASGI-сервер | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.35 |
| СУБД | SQLite (dev) / PostgreSQL (prod) | - |
| Планировщик | APScheduler | 3.10.4 |
| Google API | google-api-python-client | 2.147.0 |
| VK API | vk-api | 11.9.9 |
| Валидация | Pydantic | 2.9.2 |
| Шифрование | cryptography | 43.0.1 |
| Тестирование | pytest | 8.3.3 |

---

## 📁 Структура проекта

```
vk-calendar-notifier/
├── app/
│   ├── __init__.py
│   ├── main.py                     # Точка входа FastAPI
│   ├── config.py                   # Конфигурация из .env
│   ├── database.py                 # Подключение к БД
│   ├── models.py                   # SQLAlchemy модели
│   ├── schemas.py                  # Pydantic схемы
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                 # Зависимости (DI)
│   │   └── routes.py               # REST эндпоинты
│   ├── services/
│   │   ├── __init__.py
│   │   ├── google_cal.py           # Интеграция с Google Calendar
│   │   ├── vk_client.py            # Отправка сообщений VK
│   │   ├── vk_longpoll.py          # Обработка входящих команд
│   │   ├── notification_engine.py  # Бизнес-логика уведомлений
│   │   └── scheduler_service.py    # APScheduler задачи
│   └── utils/
│       ├── __init__.py
│       ├── crypto.py               # Шифрование токенов
│       └── logger.py               # Логирование
├── tests/
│   ├── test_grouping.py            # Тесты группировки
│   ├── test_silence_mode.py        # Тесты режима тишины
│   ├── test_conflicts.py           # Тесты конфликтов
│   └── test_snooze.py              # Тесты команд snooze
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🔐 Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `GOOGLE_CLIENT_ID` | OAuth Client ID из Google Cloud Console | `123456.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | OAuth Client Secret из Google Cloud | `GOCSPX-...` |
| `GOOGLE_REDIRECT_URI` | Callback URL для OAuth | `http://localhost:8000/auth/google/callback` |
| `VK_SERVICE_TOKEN` | Серверный токен сообщества VK | `vk1.a....` |
| `VK_GROUP_ID` | Числовой ID сообщества VK | `240010601` |
| `DATABASE_URL` | Строка подключения к БД | `sqlite:///./notifications.db` |
| `ENCRYPTION_KEY` | Ключ шифрования токенов (32+ символа) | `my-super-secret-key-1234567890` |
| `DEBUG` | Режим отладки | `True` |

---

## 🚀 Инструкция по запуску

### Предварительные требования

- Python 3.10+
- Git
- Аккаунт Google (с доступом к Google Calendar)
- Аккаунт ВКонтакте с созданным сообществом

### 1. Клонирование репозитория

```bash
git clone https://github.com/your-username/vk-calendar-notifier.git
cd vk-calendar-notifier
```

### 2. Создание виртуального окружения

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
```

### 3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните значения:

```bash
cp .env.example .env
```

#### Получение Google OAuth credentials:
1. Перейти в [Google Cloud Console](https://console.cloud.google.com/)
2. Создать проект → включить Google Calendar API
3. Настроить OAuth consent screen (External, добавить тестового пользователя)
4. Создать OAuth Client ID (Web application) с redirect URI `http://localhost:8000/auth/google/callback`

#### Получение VK Service Token:
1. Создать сообщество в VK
2. Управление → Работа с API → Создать серверный токен
3. Скопировать числовой ID сообщества из URL (`vk.com/club123456` → `123456`)

### 5. Запуск сервера

```bash
python -m app.main
```

Сервер запустится на `http://127.0.0.1:8000`. Swagger UI доступен по адресу `http://127.0.0.1:8000/docs`.

### 6. Запуск тестов

```bash
pytest tests/ -v
```

---

## 📡 Спецификация REST API

### Управление пользователями

#### `POST /users` — Создание пользователя

**Request:**
```json
{
  "vk_user_id": 317752976,
  "timezone": "Europe/Moscow"
}
```

**Response (201):**
```json
{
  "id": 1,
  "vk_user_id": 317752976,
  "timezone": "Europe/Moscow",
  "is_active": true
}
```

#### `GET /users/{vk_user_id}` — Получение пользователя

**Response (200):**
```json
{
  "id": 1,
  "vk_user_id": 317752976,
  "timezone": "Europe/Moscow",
  "is_active": true
}
```

### Авторизация Google Calendar

#### `GET /auth/google/login?vk_user_id={id}` — Начало OAuth

Перенаправляет пользователя на страницу авторизации Google.

#### `GET /auth/google/callback?code={code}` — Callback от Google

**Response (200):**
```json
{
  "status": "success",
  "message": "Google Calendar connected successfully"
}
```

### Синхронизация и события

#### `POST /sync/{vk_user_id}` — Синхронизация календаря

**Response (200):**
```json
{
  "status": "success",
  "synced_events": 15,
  "message": "Synced 15 events"
}
```

#### `GET /events/{vk_user_id}` — Получение событий

**Response (200):**
```json
[
  {
    "id": 1,
    "external_id": "abc123",
    "title": "Встреча с клиентом",
    "description": "Обсуждение проекта",
    "start_time": "2026-07-05T14:00:00+03:00",
    "end_time": "2026-07-05T15:00:00+03:00",
    "location": "Офис",
    "status": "confirmed",
    "is_conflict": false
  }
]
```

### Уведомления

#### `POST /notify/{vk_user_id}?message={text}` — Отправка уведомления

**Response (200):**
```json
{
  "status": "success",
  "message": "Notification sent"
}
```

#### `GET /notifications/{vk_user_id}` — История уведомлений

**Response (200):**
```json
[
  {
    "id": 1,
    "message_text": "🔔 Напоминание: Встреча",
    "sent_at": "2026-07-03T10:00:00",
    "status": "sent",
    "vk_message_id": 12345,
    "error_message": null
  }
]
```

### Настройки

#### `GET /settings/{vk_user_id}` — Получение настроек

**Response (200):**
```json
{
  "reminder_intervals": [60, 15, 5],
  "silence_start": "23:00",
  "silence_end": "08:00",
  "priority_keywords": ["врач", "срочно", "семья", "дедлайн"],
  "grouping_window_minutes": 120,
  "weekly_summary_day": "monday",
  "weekly_summary_time": "09:00"
}
```

#### `PUT /settings/{vk_user_id}` — Обновление настроек

**Request:**
```json
{
  "reminder_intervals": [30, 10, 5],
  "silence_start": "22:00",
  "priority_keywords": ["срочно", "дедлайн"]
}
```

### Администрирование

#### `POST /admin/weekly-summary` — Ручной запуск еженедельной сводки

#### `GET /health` — Проверка работоспособности

**Response (200):**
```json
{
  "status": "ok",
  "version": "1.0"
}
```

---

## 🧠 Бизнес-логика

### 1. Группировка уведомлений по временным окнам

Если несколько событий начинаются в пределах настраиваемого интервала (по умолчанию 2 часа), формируется одно сводное сообщение.

**Пример:** События в 10:00, 11:00 и 11:30 будут сгруппированы в одно сообщение:
```
📅 Сводка ближайших событий:

• 10:00 - Встреча с клиентом
• 11:00 - Звонок руководителю
• 11:30 - Презентация проекта
```

### 2. Режим ограничения уведомлений

Пользователь задаёт интервал тишины (например, 23:00–08:00). В этот период стандартные уведомления блокируются, но приоритетные события (содержащие ключевые слова "врач", "срочно", "семья", "дедлайн") отправляются независимо.

### 3. Еженедельная аналитическая сводка

Раз в неделю (по умолчанию понедельник в 09:00) сервис генерирует план на 7 дней с общим количеством событий, выделением приоритетных встреч и указанием свободных окон.

### 4. Обработка команд откладывания

Пользователь может ответить на уведомление в VK:
- `+10` — отложить на 10 минут
- `+1ч` — отложить на 1 час
- `+30м` — отложить на 30 минут
- `завтра` — отложить на завтра
- `отмена` — отменить уведомление
- `статус` — показать отложенные уведомления
- `помощь` — показать справку

### 5. Автоматическое обнаружение конфликтов

Система сравнивает интервалы [начало, конец] всех событий. При пересечении отправляется предупреждение за 1 час до начала первого конфликтующего события:
```
⚠️ КОНФЛИКТ РАСПИСАНИЯ!

Следующие события пересекаются:

1️⃣ Встреча с клиентом
   ⏰ 10:00 - 11:00

2️⃣ Звонок руководителю
   ⏰ 10:30 - 11:30

Пожалуйста, проверьте расписание.
```

### Правила взаимодействия функций

- Группировка применяется после проверки режима тишины и исключения конфликтующих событий
- Предупреждения о конфликтах отправляются отдельным сообщением
- Команда откладывания применяется к конкретному уведомлению
- Еженедельная сводка отражает актуальное состояние с учётом всех отложенных уведомлений

---

## 🧪 Тестирование

### Покрытие тестами

| Модуль | Тестов | Статус |
|--------|--------|--------|
| Группировка событий | 4 | ✅ PASSED |
| Режим тишины | 4 | ✅ PASSED |
| Обнаружение конфликтов | 3 | ✅ PASSED |
| Команды snooze | 6 | ✅ PASSED |
| **Итого** | **17** | **100%** |

### Запуск тестов

```bash
pytest tests/ -v
```

### Пример отчёта

```
tests/test_conflicts.py::test_detect_overlapping_events PASSED
tests/test_conflicts.py::test_detect_non_overlapping_events PASSED
tests/test_conflicts.py::test_format_conflict_warning PASSED
tests/test_grouping.py::test_grouping_close_events PASSED
tests/test_grouping.py::test_grouping_separated_events PASSED
tests/test_grouping.py::test_format_grouped_message_single_event PASSED
tests/test_grouping.py::test_format_grouped_message_multiple_events PASSED
tests/test_silence_mode.py::test_silence_mode_during_night PASSED
tests/test_silence_mode.py::test_silence_mode_during_day PASSED
tests/test_silence_mode.py::test_priority_event_bypasses_silence PASSED
tests/test_silence_mode.py::test_regular_event_blocked_during_silence PASSED
tests/test_snooze.py::test_parse_snooze_minutes PASSED
tests/test_snooze.py::test_parse_snooze_hours PASSED
tests/test_snooze.py::test_parse_snooze_tomorrow PASSED
tests/test_snooze.py::test_parse_snooze_cancel PASSED
tests/test_snooze.py::test_apply_snooze PASSED
tests/test_snooze.py::test_apply_cancel PASSED
```

---

## 📸 Демонстрация работы

### Пример логов при запуске

```
2026-07-03 06:36:07 | INFO | app | Инициализация БД...
2026-07-03 06:36:07 | INFO | app | БД готова.
2026-07-03 06:36:07 | INFO | app | Запуск VK LongPoll...
2026-07-03 06:36:07 | INFO | app | VK LongPoll запущен
2026-07-03 06:36:07 | INFO | app | Запуск планировщика задач...
2026-07-03 06:36:07 | INFO | app | Планировщик задач запущен
INFO:     Application startup complete.
```

### Пример обработки команды пользователя

```
2026-07-03 06:40:23 | INFO | app | Получено сообщение от 317752976: +10
2026-07-03 06:40:23 | INFO | app | Уведомление 1 отложено до 2026-07-03 06:50:23
2026-07-03 06:40:23 | INFO | app | Команда snooze обработана для 317752976: +10
```

### Пример отправки отложенного уведомления

```
2026-07-03 06:50:24 | INFO | app | Отправлено отложенное уведомление для 317752976
```

---

## 📌 Примечания

- Для production-окружения рекомендуется использовать PostgreSQL вместо SQLite
- Токены Google OAuth шифруются с использованием Fernet (AES-128-CBC)
- Реализована защита от повторной отправки (проверка в окне 5 минут)
- Поддерживается экспоненциальная задержка при сбоях VK API (до 3 попыток)

## 📄 Лицензия

Учебный проект. Разработан в рамках курсовой работы.