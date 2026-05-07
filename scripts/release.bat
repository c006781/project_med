@echo off
if "%1"=="" (
    echo Usage: release.bat [patch^|minor^|major]
    exit /b 1
)
echo Обновление requirements.txt...
call scripts\pip_freeze.bat
git add requirements.txt
git diff --quiet --cached || git commit -m "Обновление зависимостей"
python scripts\version.py %1
set /p NEW_VERSION=<VERSION
set TAG=v%NEW_VERSION%
git add VERSION
git commit -m "Bump version to %NEW_VERSION%"
git tag -a "%TAG%" -m "Release %TAG%"
echo Тег %TAG% создан. Запустите:
echo git push origin %TAG%
echo git push origin main