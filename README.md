# 🤖 Telegram-бот расписания Альметьевского политехнического техникума (almetpt.ru)

Бот предназначен для быстрого и удобного получения расписания занятий студентов и преподавателей с официального сайта **[almetpt.ru](https://almetpt.ru)**.

## 🚀 Возможности бота

- 📅 **Расписание на сегодня и завтра** в один клик.
- 🗓 **Выбор любой доступной даты** (динамический список дат с сайта).
- 👥 **Привязка группы**: бот запоминает выбранную группу студента в базе данных.
- 🔍 **Умный поиск групп**: поиск по названию или номеру (`АВ-261`, `261`, `БУР-261` и др.).
- 👨‍🏫 **Расписание преподавателей**: поиск по фамилии преподавателя.
- 🔔 **Расписание звонков**: время начала/окончания пар и перемен.
- 🔄 **Кнопка «Обновить»** прямо под сообщением.
- 🌐 **Ссылка на сайт** almetpt.ru в каждом сообщении с расписанием.
- 🐳 **Готов к деплою в Docker**: встроенные `Dockerfile` и `docker-compose.yml`.

---

## 🛠 Стек технологий

- **Python 3.10+**
- **aiogram 3.x**
- **httpx**
- **BeautifulSoup4**
- **aiosqlite** (SQLite)
- **python-dotenv**
- **Docker / Docker Compose**

---

## 📁 Структура проекта

```text
tgbot/
├── .env.example       # Пример конфигурационного файла
├── .gitignore         # Игнорируемые файлы Git
├── bot.py             # Точка входа, запуск бота
├── config.py          # Конфигурация и переменные окружения
├── database.py        # Асинхронная работа с базой данных SQLite
├── handlers.py        # Обработчики команд, сообщений и Callback'ов
├── keyboards.py       # Reply и Inline клавиатуры
├── parser.py          # Парсинг расписания, групп, преподавателей и дат
├── requirements.txt   # Зависимости Python
├── Dockerfile         # Сборка Docker-контейнера
├── docker-compose.yml # Запуск через Docker Compose
├── run.bat            # Запуск на Windows в 1 клик
└── README.md          # Документация проекта
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
   *(Убедитесь, что внутри указан ваш `BOT_TOKEN`)*

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

5. (Опционально) Автозапуск через systemd:
   Создайте файл `/etc/systemd/system/tgbot.service`:
   ```ini
   [Unit]
   Description=AlmetPT Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/root/tgbot
   ExecStart=/root/tgbot/venv/bin/python bot.py
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
