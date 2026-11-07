#!/bin/bash
# Обновление requirements.txt (рабочие зависимости) и requirements-dev.txt (с тестовыми)
# по `pip freeze` активного окружения.
#
# Условные пакеты (pyinstaller и его зависимости ставятся только там, где собирается exe)
# записываются с условием `; sys_platform == "win32"`:
#   * пакет есть в `pip freeze` (Windows) — версия обновляется, условие ставится;
#   * пакета нет (Linux: pyinstaller не установлен) — строка с версией и условием берётся
#     из прежнего файла как есть, чтобы запуск на Linux её не стёр.
# Файлы заменяются целиком и только после успешного `pip freeze` (сначала временные файлы
# рядом, затем `mv`): упал pip — прежние файлы не тронуты. Окончания строк — LF
# (на Windows `pip freeze` может выдать CRLF).
#
# Использование (из любой папки; работает в корне проекта):
#   ./scripts/pip_freeze.sh        # окружение должно быть активировано
set -euo pipefail

cd "$(dirname "$0")/.."

# pefile и pywin32-ctypes — зависимости pyinstaller только на Windows: в файлах их пока нет, но
# запуск на Windows их добавит, и без условия они попали бы в установку на Linux
CONDITIONAL_PACKAGES="pyinstaller altgraph pyinstaller-hooks-contrib pefile pywin32-ctypes"   # имена в каноническом виде
CONDITION='sys_platform == "win32"'                                     # условие установки

# Что не попадает в requirements.txt (имена в каноническом виде)
PROD_EXCLUDED="project-med pytest coverage pluggy iniconfig packaging pygments"
PROD_EXCLUDED_PREFIXES="pytest-"   # плагины pytest (pytest-cov, pytest-mock …)

# merge_requirements <прежний файл> <вывод freeze> <исключённые> <префиксы исключённых>
# печатает новое содержимое requirements: строки freeze без исключённых, условные пакеты
# с условием; условного пакета нет во freeze — строка из прежнего файла на своём месте
merge_requirements() {
    local old_file="$1"   # прежний файл (может не существовать)
    local freeze="$2"     # файл с выводом pip freeze (LF)
    local excluded="$3"   # исключаемые имена через пробел
    local prefixes="$4"   # исключаемые префиксы имён через пробел

    [ -f "$old_file" ] || old_file=/dev/null

    LC_ALL=C awk \
        -v conditional="$CONDITIONAL_PACKAGES" \
        -v condition="$CONDITION" \
        -v excluded="$excluded" \
        -v prefixes="$prefixes" \
        '
        # каноническое имя пакета из строки requirements (-e …#egg=имя — по egg)
        function canon(line,   name) {
            name = line
            if (line ~ /^-e /) {
                if (match(line, /#egg=[^&# \t]+/)) {
                    name = substr(line, RSTART + 5, RLENGTH - 5)
                }
            } else {
                sub(/[ \t=<>~!@;\[].*$/, "", name)
            }
            name = tolower(name)
            gsub(/[_.]/, "-", name)
            return name
        }
        # строка с условием: прежнее условие (если было) заменяется
        function with_condition(line,   base) {
            base = line
            sub(/[ \t]*;.*$/, "", base)
            return base "; " condition
        }
        function is_excluded(name,   i) {
            if (name in drop) return 1
            for (i = 1; i <= n_prefixes; i++) {
                if (index(name, prefix_list[i]) == 1) return 1
            }
            return 0
        }
        BEGIN {
            n_cond = split(conditional, cond_list, " ")
            for (i = 1; i <= n_cond; i++) is_conditional[cond_list[i]] = 1
            n_drop = split(excluded, drop_list, " ")
            for (i = 1; i <= n_drop; i++) drop[drop_list[i]] = 1
            n_prefixes = split(prefixes, prefix_list, " ")
        }
        # 1-й файл — прежний requirements: запоминаем строки условных пакетов
        FILENAME == ARGV[1] {
            line = $0; sub(/\r$/, "", line)
            name = canon(line)
            if ((name in is_conditional) && !(name in old_line)) old_line[name] = with_condition(line)
            next
        }
        # 2-й файл — freeze
        {
            line = $0; sub(/\r$/, "", line)
            if (line == "") next
            name = canon(line)
            if (is_excluded(name)) next
            n_out++
            out_name[n_out] = name
            if (name in is_conditional) {
                out_line[n_out] = with_condition(line)
                in_freeze[name] = 1
            } else {
                out_line[n_out] = line
            }
        }
        END {
            # сохранённые условные пакеты, которых нет во freeze, — по возрастанию имени
            n_keep = 0
            for (name in old_line) {
                if (!(name in in_freeze)) keep[++n_keep] = name
            }
            for (i = 1; i <= n_keep; i++) {
                for (j = i + 1; j <= n_keep; j++) {
                    if (keep[j] < keep[i]) { tmp = keep[i]; keep[i] = keep[j]; keep[j] = tmp }
                }
            }
            k = 1
            for (i = 1; i <= n_out; i++) {
                while (k <= n_keep && keep[k] < out_name[i]) print old_line[keep[k++]]
                print out_line[i]
            }
            while (k <= n_keep) print old_line[keep[k++]]
        }
        ' "$old_file" "$freeze"
}

FREEZE_FILE=$(mktemp ".pip_freeze.XXXXXX")      # вывод pip freeze
NEW_PROD=$(mktemp ".requirements.XXXXXX")       # новый requirements.txt
NEW_DEV=$(mktemp ".requirements-dev.XXXXXX")    # новый requirements-dev.txt
trap 'rm -f "$FREEZE_FILE" "$NEW_PROD" "$NEW_DEV"' EXIT

# pip freeze — до любой записи в requirements: упал или пуст — файлы остаются прежними
# (tr убирает CR: на Windows вывод pip может быть с CRLF; pipefail ловит падение pip)
if ! pip freeze | tr -d '\r' > "$FREEZE_FILE"; then
    echo "Ошибка: pip freeze не выполнился, requirements не изменены." >&2
    exit 1
fi
if [ ! -s "$FREEZE_FILE" ]; then
    echo "Ошибка: pip freeze ничего не вывел, requirements не изменены." >&2
    exit 1
fi

merge_requirements requirements.txt     "$FREEZE_FILE" "$PROD_EXCLUDED" "$PROD_EXCLUDED_PREFIXES" > "$NEW_PROD"
merge_requirements requirements-dev.txt "$FREEZE_FILE" ""              ""                         > "$NEW_DEV"

# замена файлов — после того, как оба готовы
chmod 644 "$NEW_PROD" "$NEW_DEV"
mv "$NEW_PROD" requirements.txt
mv "$NEW_DEV"  requirements-dev.txt

echo "requirements.txt и requirements-dev.txt обновлены"

# ↑ до 2026-11-07 (SC3, В-22): условия не сохранялись; без pipefail упавший pip freeze давал
#   пустой requirements.txt; исключения — grep -v по подстроке (задели бы любой пакет с
#   такой подстрокой в имени)
# pip freeze | grep -v "project_med" | grep -v "pytest" | grep -v "coverage" | grep -v "pluggy" | grep -v "iniconfig" | grep -v "packaging" | grep -v "Pygments" > requirements.txt
# pip freeze > requirements-dev.txt
#
# echo "requirements.txt обновлён"
