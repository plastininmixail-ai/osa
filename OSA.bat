@echo off
REM OSA — главный ярлык. Открывает терминал в папке проекта с активированным окружением.
REM Двойной клик = cmd в директории проекта с venv.

cd /d "C:\Users\mixai\Desktop\hermes-projects\agent-framework"

REM Проверяем что uv доступен
where uv >nul 2>nul
if errorlevel 1 (
    echo [OSA] uv не найден в PATH. Установите: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

REM Запускаем интерактивный shell с активированным OSA venv
echo [OSA] Активация venv...
call uv sync --quiet
call .venv\Scripts\activate.bat

echo.
echo  =====================================================
echo   O.S.A. — Операционная Система Агента
echo   Документация: docs\VISION.md
echo  =====================================================
echo.
echo   Команды:
echo     osa init       - инициализировать OSA_HOME
echo     osa goal "..." - поставить цель агенту
echo     osa status     - показать последние цели
echo     osa logs       - показать логи
echo     osa --help     - все команды
echo.

cmd /k
