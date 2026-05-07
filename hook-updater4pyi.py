# hook-updater4pyi.py
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Собрать все дочерние модули updater4pyi (на случай динамических импортов)
hiddenimports = collect_submodules('updater4pyi')

# Добавить все файлы данных из пакета (например, cacert.pem и скрипты установки)
datas = collect_data_files('updater4pyi')