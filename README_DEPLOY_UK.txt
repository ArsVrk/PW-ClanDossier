PW CLAN DOSSIER — окрема хмарна версія

ВАЖЛИВО
- Це окремий сайт для окремого Supabase-проєкту PW Clan Dossier.
- Не запускайте міграцію в старому проєкті PWResoCop Project.
- Файл PW_ClanDossier.sqlite3 та DATABASE_URL не потрібно комітити в GitHub.
- Для хмарного сайту DOSSIER_PASSWORD обов'язковий: без нього сервер не стартує.

СТРУКТУРА ПАКЕТА
- server.py — сайт; використовує PostgreSQL, якщо задано DATABASE_URL, або SQLite для локального запуску.
- schema_supabase.sql — схема нової бази.
- migrate_sqlite_to_supabase.py — переносить players/scans/stats/equipment із SQLite до нового Supabase.
- requirements.txt — залежності.
- render.yaml — шаблон конфігурації Render.

МІГРАЦІЯ (виконується один раз із комп'ютера)
1. У Supabase відкрийте НОВИЙ проєкт PW Clan Dossier -> Connect -> Database connection string.
2. Оберіть Session pooler (не Direct connection: Render може працювати лише через IPv4). Скопіюйте URI приватно й замініть placeholder паролем нової бази. Не надсилайте його в чат і не додавайте до GitHub.
3. На Windows установіть Python 3.11+ (якщо ще не встановлений).
4. Відкрийте CMD у папці цього проєкту й виконайте:
   py -m pip install -r requirements.txt
5. Задайте змінні лише для поточного вікна CMD (вставте URI у лапках; замініть <...> своїм рядком):
   set "DATABASE_URL=<ВАШ POSTGRES URI НОВОГО ПРОЄКТУ>"
   set "DOSSIER_SQLITE=<ПОВНИЙ ШЛЯХ ДО PW_ClanDossier.sqlite3>"
6. Виконайте:
   py migrate_sqlite_to_supabase.py
7. Перевірте в консолі кількість перенесених рядків. Очікувано для наданої бази: players 524, scans 81, stats 74, equipment 1309.

УВАГА: міграційний скрипт очищає відповідні таблиці в цільовому проєкті перед імпортом. Запускайте його тільки в НОВІЙ базі PW Clan Dossier. Він не звертається до старого Supabase-проєкту.

RENDER
- Створіть новий Web Service з окремого GitHub-репозиторію для цього сайту.
- Build Command: pip install -r requirements.txt
- Start Command: python server.py
- Додайте Environment Variables:
  DATABASE_URL = PostgreSQL URI саме нового проєкту PW Clan Dossier
  DOSSIER_PASSWORD = довгий унікальний пароль доступу до сайту
- Не використовуйте Supabase service_role key як DATABASE_URL. Потрібен саме PostgreSQL connection string.
- /healthz — відкритий службовий endpoint для перевірки Render; інші сторінки захищені Basic Auth (логін: officer, пароль: DOSSIER_PASSWORD).
- Render Free може засинати після періоду без активності; перший запит після простою може бути повільним.

ПОСТІЙНІ ДАНІ
Вибір скану за замовчуванням і кеш назв предметів зберігаються в таблицях app_settings та item_metadata нової Supabase-бази. Кеш іконок залишається локальним кешем: якщо Render очистить файлову систему, іконки завантажаться повторно за потреби.
