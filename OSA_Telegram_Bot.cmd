@echo off
REM OSA Telegram Bot — запуск бота в новом окне через start /B.
REM Это даёт полностью отвязанный процесс.

cd /d "C:\Users\mixai\Desktop\hermes-projects\agent-framework"

REM Создаём venv если нет
if not exist ".venv\Scripts\python.exe" (
    echo [OSA Bot] .venv не найден, uv sync...
    call uv sync >nul
)

REM Загружаем .env через PowerShell (надёжный парсинг)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "load_env.ps1"
if errorlevel 1 (
    echo [OSA Bot] Не удалось загрузить .env
    pause
    exit /b 1
)

echo.
echo   O.S.A. Telegram Bot стартовал
echo   ============================
echo   Allowed users: %OSA_TELEGRAM__ALLOWED_USERS%
echo   LLM provider: %OSA_LLM__PROVIDER%
echo   Bot token: %OSA_TELEGRAM__BOT_TOKEN:~0,10%...
echo.
echo   Бот работает. Можешь закрыть это окно.
echo   Для остановки бота: osa stop (если есть) или Task Manager
echo.

REM start /B запускает в фоне без нового окна, без блокировки текущего
call .venv\Scripts\activate.bat
start "OSA Bot" /B python -m osa serve --transport=telegram

REM Этот cmd закрывается сразу (start /B отвязывает), но python остаётся жить
exit /b 0
