@echo off
chcp 65001 >nul
echo ========================================
echo 🤖 Локальный сервер Man_Bot
echo ========================================
echo.

:: Проверка наличия .env
if not exist .env (
    echo ⚠️  Файл .env не найден!
    echo Создаю из шаблона...
    copy .env.example .env
    echo ✅ Отредактируй .env и вставь свои токены!
    echo.
    pause
    exit /b 1
)

:: Меню
:menu
echo Выберите действие:
echo.
echo 1. 🚀 Запустить всё (docker-compose up)
echo 2. 🛑 Остановить всё (docker-compose down)
echo 3. 📊 Показать логи (logs -f)
echo 4. 🗄️  Подключиться к БД (psql)
echo 5. 🧹 Очистить БД (удалить volumes)
echo 6. 📥 Загрузить техники в БД
echo 7. 🌐 Открыть pgAdmin (http://localhost:5050)
echo 8. 📚 Открыть API docs (http://localhost:8000/docs)
echo 9. ❌ Выход
echo.
set /p choice="Ваш выбор (1-9): "

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto logs
if "%choice%"=="4" goto db
if "%choice%"=="5" goto clean
if "%choice%"=="6" goto load
if "%choice%"=="7" goto pgadmin
if "%choice%"=="8" goto docs
if "%choice%"=="9" goto exit

echo ❌ Неверный выбор
goto menu

:start
echo.
echo 🚀 Запуск локального сервера...
docker-compose -f docker-compose.local.yml up -d
echo.
echo ✅ Сервер запущен!
echo 📱 Telegram бот: готов к работе (если токен указан)
echo 🌐 API: http://localhost:8000
echo 🗄️  База данных: localhost:5433
echo 🖥️  pgAdmin: http://localhost:5050 (admin@admin.com / admin123)
echo.
pause
goto menu

:stop
echo.
echo 🛑 Остановка сервера...
docker-compose -f docker-compose.local.yml down
echo ✅ Остановлено
pause
goto menu

:logs
echo.
echo 📊 Показываю логи (Ctrl+C для выхода)...
docker-compose -f docker-compose.local.yml logs -f
goto menu

:db
echo.
echo 🗄️  Подключение к базе данных...
docker exec -it man_bot_postgres_local psql -U man_admin -d man_vector_db
goto menu

:clean
echo.
echo ⚠️  ВНИМАНИЕ! Это удалит ВСЕ данные из БД!
set /p confirm="Ты уверен? (yes/no): "
if "%confirm%"=="yes" (
    docker-compose -f docker-compose.local.yml down -v
    echo ✅ Данные удалены
) else (
    echo ❌ Отменено
)
pause
goto menu

:load
echo.
echo 📥 Загрузка техник в базу данных...
echo Убедись, что:
echo  1. Сервер запущен (пункт 1)
echo  2. Указан GOOGLE_API_KEY в .env
echo  3. Файлы техник в ../KIMI_OUTPUT/
echo.
pause
docker-compose -f docker-compose.local.yml exec rag-server-local python scripts/load_knowledge.py --source /app/knowledge_files --provider google
echo.
echo ✅ Загрузка завершена!
pause
goto menu

:pgadmin
echo.
echo 🖥️  Открываю pgAdmin...
start http://localhost:5050
goto menu

:docs
echo.
echo 📚 Открываю API документацию...
start http://localhost:8000/docs
goto menu

:exit
echo.
echo 👋 До свидания!
exit /b 0