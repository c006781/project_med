# _dev/tools/photo_relocate_check.py
"""
Проверка первого запуска новой версии на КОПИИ рабочей базы и папки фото (Ф3.6).

Копирует clinic.db и photos/ во временную папку, мигрирует копию, переносит старые фото
(PhotoService.relocate_legacy_files — тот же код, что при запуске), сверяет содержимое и ссылки,
повторно запускает перенос, сверяет папку (check_storage). Выводит только числа и формы путей
(без имён и персональных данных). Временную папку удаляет в конце (--keep — оставить).

Запуск: <venv>/bin/python -X utf8 _dev/tools/photo_relocate_check.py <clinic.db> <photos> [--keep]
"""
import hashlib, os, re, shutil, sqlite3, sys, tempfile
from collections import Counter

if len(sys.argv) < 3:
    sys.exit('Запуск: photo_relocate_check.py <clinic.db> <папка фото> [--keep]')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src_db, src_ph = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
work = tempfile.mkdtemp(prefix='photo_reloc_')
os.environ['PROJECT_MED_ENV_DIR'] = work
os.environ['APP_CONFIG_PATH'] = os.path.join(work, 'config.msgpack')
sys.path.insert(0, ROOT)
os.chdir(work)
db_copy = os.path.join(work, 'clinic.db')
ph_copy = os.path.join(work, 'photos')
shutil.copy2(src_db, db_copy)
shutil.copytree(src_ph, ph_copy)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory(root):
    out = {}
    for folder, _d, names in os.walk(root):
        for n in names:
            p = os.path.join(folder, n)
            out[os.path.relpath(p, root).replace('\\', '/')] = sha(p)
    return out


def shape(name):
    n = name
    if re.match(r'^[A-Za-z]:', n) or n.startswith('\\\\'):
        return 'абсолютный Windows'
    if n.startswith('/'):
        return 'абсолютный POSIX'
    if '..' in n.split('/'):
        return 'с ..'
    if re.match(r'^\d{8}_\d{6}(_\d+)?(\.[a-z0-9]+)?$', n):
        return 'новый вид'
    if '\\' in n:
        return 'app_N\\имя (обратная косая)'
    if re.match(r'^app_-?\d+/[^/]+$', n):
        return 'app_N/имя' if not n.startswith('app_-') else 'app_-N/имя'
    return 'иное'


inv0 = inventory(ph_copy)
con = sqlite3.connect(db_copy)
rows0 = [r[0] for r in con.execute('select file_path from photos')]
con.close()
print('файлов в photos до:', len(inv0), '| уникальных содержимых:', len(set(inv0.values())))
print('строк photos до:', len(rows0), '| уникальных путей:', len(set(rows0)))
print('формы путей в photos до:', dict(Counter(shape(r) for r in rows0)))
print('папки верхнего уровня до:', dict(Counter(k.split('/')[0] if '/' in k else '(корень)' for k in inv0)).__len__(), 'шт;',
      'файлов в корне:', sum('/' not in k for k in inv0))
print('папка app_-N (число файлов):', sum(k.startswith('app_-') for k in inv0))

from app.database.database import Database
from app.dependencies import PHOTO_CONFIG
from app.services.services_all import PhotoService

db = Database(f'sqlite:///{db_copy}')
svc = PhotoService(db, ph_copy, field_configs=PHOTO_CONFIG)
con = sqlite3.connect(db_copy)
print('photo_files после миграции:', con.execute('select count(*) from photo_files').scalar() if False else con.execute('select count(*) from photo_files').fetchone()[0])
con.close()
rep1 = svc.relocate_legacy_files()
print('перенос #1:', rep1)


def state():
    con = sqlite3.connect(db_copy)
    ph = [r[0] for r in con.execute('select file_path from photos')]
    pf = [r[0] for r in con.execute('select file_path from photo_files')]
    dump = hashlib.sha256(repr(sorted(con.execute('select * from photos').fetchall())
                               + sorted(con.execute('select file_path, created_at from photo_files').fetchall())).encode()).hexdigest()
    fk = con.execute('pragma foreign_key_check').fetchall()
    con.close()
    return ph, pf, dump, fk


ph1, pf1, dump1, fk1 = state()
inv1 = inventory(ph_copy)
print('строк photos:', len(ph1), '| photo_files:', len(pf1), '| foreign_key_check:', len(fk1))
print('формы путей в photos после:', dict(Counter(shape(r) for r in ph1)))
print('формы путей в photo_files после:', dict(Counter(shape(r) for r in pf1)))
from app.database.file_actions import photo_file_path
missing = [r for r in set(ph1) if not os.path.isfile(photo_file_path(ph_copy, r) or '')]
print('ссылок photos на несуществующий файл:', len(missing))
print('photos со строкой не в photo_files:', len(set(ph1) - set(pf1)))
print('photo_files без ссылок photos:', len(set(pf1) - set(ph1)))
print('файлов после:', len(inv1), '| в корне:', sum('/' not in k for k in inv1), '| в app_*:', sum('/' in k for k in inv1))
print('множества sha256: до == после:', set(inv0.values()) == set(inv1.values()),
      '| до-после:', len(set(inv0.values()) - set(inv1.values())), '| после-до:', len(set(inv1.values()) - set(inv0.values())))
print('sha256 ссылок (множество содержимого по photos) входит в исходные:',
      {inv1[r] for r in set(ph1) if r in inv1} <= set(inv0.values()))
# что осталось в старых папках
left = [k for k in inv1 if '/' in k]
print('осталось в старых папках файлов:', len(left), '| из них с ссылкой в photos:', sum(k in set(ph1) for k in left))
print('осталось по папкам: app_-N:', sum(k.startswith('app_-') for k in left), '| app_N:', sum(k.startswith('app_') and not k.startswith('app_-') for k in left))
# повтор
mt1 = {k: os.path.getmtime(os.path.join(ph_copy, k)) for k in inv1}
rep2 = svc.relocate_legacy_files()
ph2, pf2, dump2, fk2 = state()
inv2 = inventory(ph_copy)
print('перенос #2:', rep2, '| БД без изменений:', dump1 == dump2, '| файлы без изменений:', inv1 == inv2)
chk = svc.check_storage(min_age=0)
print('check_storage(min_age=0): extra', len(chk['extra']), '| fresh', len(chk['fresh']), '| empty_dirs', len(chk['empty_dirs']), '| missing', len(chk['missing']))
chk2 = svc.check_storage()
print('check_storage(по умолчанию): extra', len(chk2['extra']), '| fresh', len(chk2['fresh']), '| empty_dirs', len(chk2['empty_dirs']), '| missing', len(chk2['missing']))
print('extra: формы:', dict(Counter(shape(x) for x in chk['extra'])), '| в app_-N:', sum(x.startswith('app_-') for x in chk['extra']),
      '| sha дублируют ссылочный файл:', sum(inv1[x] in {inv1[r] for r in set(ph1) if r in inv1} for x in chk['extra']))
print('бэкапы базы рядом:', len([f for f in os.listdir(work) if '.bak-' in f]))
if '--keep' not in sys.argv:
    db.engine.dispose()
    shutil.rmtree(work)
    print('временная папка удалена')
else:
    print('папка:', work)
