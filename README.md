# 🤖 Telegram-бот расписания Альметьевского политехнического техникума (almetpt.ru)

Бот предназначен для быстрого и удобного получения расписания занятий студентов и преподавателей с официального сайта **[almetpt.ru](https://almetpt.ru)**.

## 🚀 Возможности бота

- 📅 **Расписание на сегодня и завтра** в один клик.
- 🗓 **Выбор любой доступной даты** (динамический список дат с сайта).
- 👥 **Привязка группы**: бот запоминает выбранную группу студента в базе данных.
- 🔍 **Умный поиск групп**: поиск по названию или номеру (`АВ-261`, `261`, `БУР-261` и др.), в том числе при неверной раскладке клавиатуры.
- 👨‍🏫 **Расписание преподавателей**: поиск по фамилии или по первой букве.
- 🔔 **Расписание звонков**: время начала/окончания пар и перемен.
- 📨 **Уведомления** о публикации и изменении расписания (включаются `ENABLE_NOTIFICATIONS=true`). Уже опубликованное расписание новым подписчикам не рассылается, оно только запоминается.
- 🔄 **Кнопка «Обновить»** прямо под сообщением (расписание кэшируется на ~45 секунд, чтобы не нагружать сайт).
- 🌐 **Ссылка на сайт** almetpt.ru в каждом сообщении с расписанием.
- 🐳 **Готов к деплою в Docker**: встроенные `Dockerfile` и `docker-compose.yml`.

### Для администраторов

- `/admin` — панель: технический перерыв, статистика, сброс кэша сайта, рассылки, бэкап базы.
- `/statadmin`, `/stats` — панель статистики (доступна также стат-администраторам, только чтение).
- **Рассылки**: мгновенные, отложенные (`ЧЧ:ММ`, `ДД.ММ ЧЧ:ММ`, `ДД.ММ.ГГГГ ЧЧ:ММ`) и ежедневные, с закреплением сообщения. Только текст до 4096 символов; время указывается по часовому поясу `TIMEZONE`.
- `/addadmin`, `/deladmin`, `/admins`, `/addstatadmin`, `/delstatadmin`, `/statadmins` — управление правами по Telegram ID.
- `/backup` — снимок базы данных; `/restore` — восстановление из закреплённого сообщения канала бэкапов; файл `bot.db`, отправленный в чат, тоже восстанавливает базу. Во время восстановления бот ведёт себя как при техническом перерыве.

---

## ⚙️ Настройка (`.env`)

Скопируйте `.env.example` в `.env`. Все переменные описаны в самом файле. Главные:

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | токен от @BotFather (обязательно) |
| `ADMIN_IDS`, `STAT_ADMIN_IDS` | Telegram ID администраторов и стат-администраторов |
| `TIMEZONE` | часовой пояс техникума, по умолчанию `Europe/Moscow` (контейнеры живут в UTC, поэтому он задаётся явно) |
| `DATABASE_PATH` | путь к базе SQLite (в Docker — `/app/data/bot.db` на томе) |
| `BACKUP_CHANNEL_ID` | закрытый канал для автобэкапов раз в 30 минут; без него автобэкапов нет |
| `ENABLE_NOTIFICATIONS` | включает фоновые уведомления о расписании |
| `DROP_PENDING_UPDATES` | отбрасывать ли сообщения, накопившиеся за время простоя (по умолчанию `false`) |

---

## 🛠 Стек технологий

- **Python 3.10+** (в Docker используется 3.11)
- **aiogram 3.x**
- **httpx**
- **BeautifulSoup4**
- **aiosqlite** (SQLite)
- **python-dotenv**, **tzdata**
- **Docker / Docker Compose**

---

## 📁 Структура проекта

```text
tgbot/
├── .env.example         # Пример конфигурационного файла
├── .gitignore           # Игнорируемые файлы Git
├── bot.py               # Точка входа, запуск бота и фоновых сервисов
├── config.py            # Конфигурация и переменные окружения
├── timeutil.py          # Текущее время в часовом поясе техникума
├── database.py          # Асинхронная работа с базой данных SQLite
├── handlers.py          # Обработчики команд, сообщений и Callback'ов
├── keyboards.py         # Reply и Inline клавиатуры
├── middlewares.py       # Регистрация пользователей, технический перерыв
├── parser.py            # Парсинг расписания, групп, преподавателей и дат (с кэшем)
├── delivery.py          # Общая отправка сообщений: повторы, блокировки, запасной вариант без эмодзи
├── broadcast_service.py # Рассылки: мгновенные, отложенные, ежедневные
├── notifier.py          # Фоновые уведомления об изменении расписания
├── backup_service.py    # Бэкапы базы в Telegram-канал и восстановление
├── premium_emoji.py     # Идентификаторы премиум-эмодзи
├── tests/               # Автотесты (python -m unittest)
├── requirements.txt     # Зависимости Python
├── Dockerfile           # Сборка Docker-контейнера
├── docker-compose.yml   # Запуск через Docker Compose
├── run.bat              # Запуск на Windows в 1 клик
└── README.md            # Документация проекта
```

---

## 🖥 Развертывание на сервере (VPS / VDS)

### Вариант 1: Через Docker (рекомендуется)

1. Клонируйте репозиторий на сервер:
   ```bash
   git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
   cd tgbot
   ```

2. Создайте файл `.env`:
   ```bash
   cp .env.example .env
   ```
   *(Убедитесь, что внутри указан ваш `BOT_TOKEN`; для администрирования — `ADMIN_IDS`, для бэкапов — `BACKUP_CHANNEL_ID`)*

3. Запустите бота в фоне:
   ```bash
   docker compose up -d --build
   ```

4. Просмотр логов:
   ```bash
   docker compose logs -f
   ```

---

### Вариант 2: Запуск через Python & systemd

1. Клонируйте репозиторий и перейдите в папку:
   ```bash
   git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
   cd tgbot
   ```

2. Создайте виртуальное окружение и установите зависимости:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Скопируйте и настройте `.env`:
   ```bash
   cp .env.example .env
   ```

4. Запустите бота:
   ```bash
   python bot.py
   ```

5. (Опционально) Автозапуск через systemd. Бот не должен работать от root, создайте отдельного пользователя:
   ```bash
   sudo useradd --system --create-home --home-dir /opt/tgbot --shell /usr/sbin/nologin tgbot
   sudo cp -r . /opt/tgbot && sudo chown -R tgbot:tgbot /opt/tgbot
   ```
   Создайте файл `/etc/systemd/system/tgbot.service`:
   ```ini
   [Unit]
   Description=AlmetPT Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=tgbot
   Group=tgbot
   WorkingDirectory=/opt/tgbot
   ExecStart=/opt/tgbot/venv/bin/python bot.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
   Активируйте службу:
   ```bash
   systemctl daemon-reload
   systemctl enable tgbot
   systemctl start tgbot
   ```

---

## 🧪 Тесты

Тесты не требуют `.env` и токена:

```bash
python -m unittest discover -s tests -v
```
