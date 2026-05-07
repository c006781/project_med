@echo off
echo === Установка окружения разработки ===
if exist "venv_project_med" (
    echo Виртуальное окружение venv_project_med уже существует.
    set /p answer="Пересоздать его? (y/N): "
    if /i "!answer!"=="y" (
        rmdir /s /q venv_project_med
        python -m venv venv_project_med
        echo Окружение пересоздано.
    ) else (
        echo Используем существующее окружение.
    )
) else (
    echo Создание venv_project_med...
    python -m venv venv_project_med
)
call venv_project_med\Scripts\activate.bat
pip install --upgrade pip
if exist requirements.txt pip install -r requirements.txt
if exist requirements-dev.txt pip install -r requirements-dev.txt
echo Готово. Для активации: venv_project_med\Scripts\activate
pause