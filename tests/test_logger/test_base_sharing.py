# tests/test_logger/test_base_sharing.py

"""
Общий файловый обработчик (мастер/слейв).

В приложении так устроено почти всё: ~1200 логгеров создаются с
``enable_file_logging='system'`` и должны писать в файл логгера 'system'.

Здесь мастер создаётся с ``enable_file_logging=True``. До исправления S1 это было
обязательно (привязка проверяла аргумент конструктора мастера); сейчас достаточно,
чтобы у мастера был открыт файл. Реальная топология приложения — test_app_topology.py.
"""

import logging
import os

import pytest

from tests.test_logger.conftest import make_config, read


@pytest.fixture
def log_file(log_dir):
    return os.path.join(log_dir, 'app.log')


@pytest.fixture
def master_cfg(log_dir):
    return make_config(log_dir, file_enabled='True')


# ---------------------------------------------------------------------------
# Создание связи
# ---------------------------------------------------------------------------

def test_slave_by_enable_file_logging_string(make_logger, master_cfg, log_file):
    master = make_logger(name='m', config=master_cfg, enable_file_logging=True)
    slave = make_logger(name='s', enable_file_logging='m')

    assert slave.has_shared_handler() is True
    assert slave.get_master_logger() is master
    assert slave.file_handler is master.file_handler
    assert slave.file_handler in slave.logger.handlers
    assert set(slave.get_shared_group()) == {master, slave}
    assert set(master.get_shared_group()) == {master, slave}

    master.info('от мастера')
    slave.info('от слейва')
    content = read(log_file)
    assert '[m]' in content and '[s]' in content
    assert content.count('\n') == 2


def test_slave_by_share_file_with(make_logger, master_cfg):
    master = make_logger(name='m2', config=master_cfg, enable_file_logging=True)
    slave = make_logger(name='s2', share_file_with='m2')
    assert slave.get_master_logger() is master


def test_share_file_handler_with_explicit(make_logger, master_cfg):
    master = make_logger(name='m3', config=master_cfg, enable_file_logging=True)
    other = make_logger(name='o3', config=make_config(os.path.dirname(master.base_log_file), LOG_FILE='elsewhere.log'))
    other.share_file_handler_with(master)
    assert other.file_handler is master.file_handler


def test_share_with_self_or_twice_is_noop(make_logger, master_cfg):
    master = make_logger(name='m4', config=master_cfg, enable_file_logging=True)
    slave = make_logger(name='s4', enable_file_logging='m4')
    master.share_file_handler_with(master)
    slave.share_file_handler_with(master)
    master.share_file_handler_with(slave)  # обратная связь не создаётся
    assert master.has_shared_handler() is False
    assert len(master._shared_slaves) == 1


def test_slave_inherits_master_settings(make_logger, log_dir):
    """От мастера копируются параметры файла и log_args, но НЕ уровень (S3).

    Уровень слейв берёт из своего конфига (здесь LOG_LEVEL=DEBUG по умолчанию);
    до исправления S3 он перенимал уровень мастера (WARNING).
    """
    master = make_logger(name='m5', config=make_config(
        log_dir, file_enabled='True', LOG_LEVEL='WARNING', LOG_ARGS='True'),
        enable_file_logging=True)
    slave = make_logger(name='s5', enable_file_logging='m5')
    assert slave.log_level == logging.DEBUG
    assert slave.log_args is True
    assert slave.base_log_file == master.base_log_file


def test_slave_of_master_without_file_gets_nothing(make_logger, log_dir):
    master = make_logger(name='m6', config=make_config(log_dir, file_enabled='False'))
    slave = make_logger(name='s6', enable_file_logging='m6')
    assert slave.has_shared_handler() is False
    assert slave.file_handler is None


def test_slave_of_unknown_master_warns(make_logger, capsys):
    slave = make_logger(name='s7', enable_file_logging='nobody')
    err = capsys.readouterr().err
    assert "ссылается на несуществующий 'nobody'" in err
    assert "'nobody', с которым требуется расшарить обработчик, не найден" in err
    # Ссылка запомнена: файловое логирование включено, но обработчик свой
    assert slave.is_file_enabled() is True
    assert slave.has_shared_handler() is False


def test_existing_instance_shares_on_second_get_instance(make_logger, logger_cls, master_cfg):
    lone = make_logger(name='late')
    assert lone.has_shared_handler() is False
    master = make_logger(name='m8', config=master_cfg, enable_file_logging=True)
    same = logger_cls.get_instance(name='late', share_file_with='m8')
    assert same is lone
    assert lone.get_master_logger() is master


def test_auto_share_same_file_by_default(make_logger, log_dir):
    """Без share_file_with второй логгер с тем же файлом сам цепляется к первому."""
    first = make_logger(name='a1', config=make_config(log_dir, file_enabled='True'))
    second = make_logger(name='a2', config=make_config(log_dir, file_enabled='True'))
    assert second.get_master_logger() is first
    assert second.file_handler is first.file_handler


def test_no_auto_share_with_use_name_in_filename(make_logger, log_dir):
    make_logger(name='a3', config=make_config(log_dir, file_enabled='True'))
    second = make_logger(name='a4', config=make_config(log_dir, file_enabled='True'),
                         use_name_in_filename=True)
    assert second.has_shared_handler() is False


def test_slave_chain(make_logger, master_cfg, log_file):
    """Слейв слейва пишет в тот же файл."""
    root = make_logger(name='r', config=master_cfg, enable_file_logging=True)
    mid = make_logger(name='mid', enable_file_logging='r')
    leaf = make_logger(name='leaf', enable_file_logging='mid')
    assert leaf.file_handler is root.file_handler
    leaf.info('лист')
    assert '[leaf]' in read(log_file)


def test_cyclic_refs_do_not_recurse_forever(make_logger, log_dir, capsys):
    """B1: раньше цикл ссылок a→b→a давал RecursionError."""
    a = make_logger(name='cyc_a', enable_file_logging='cyc_b')
    b = make_logger(name='cyc_b', enable_file_logging='cyc_a')
    assert a.effective_enable_file_logging() in (True, False)
    assert a.effective_use_name_in_filename() in (True, False)
    assert 'Циклическая ссылка' in capsys.readouterr().err

    # оба логгера остаются рабочими
    a.reload_from_config(make_config(log_dir, file_enabled='True'))
    b.reconfigure(level='INFO')
    a.info('из цикла')
    assert 'из цикла' in read(os.path.join(log_dir, 'app.log'))


# ---------------------------------------------------------------------------
# Изменения на мастере
# ---------------------------------------------------------------------------

@pytest.fixture
def pair(make_logger, master_cfg):
    master = make_logger(name='M', config=master_cfg, enable_file_logging=True)
    slave = make_logger(name='S', enable_file_logging='M')
    return master, slave


def test_master_level_change_does_not_touch_slave(pair, log_file):
    """S3: уровень мастера не навязывается слейву и не заглушает его в общем файле.

    До исправления слейв получал уровень мастера (здесь ERROR) и его warning не писался.
    Групповая смена уровня — через reconfigure_group() или конфиг.
    """
    master, slave = pair
    master.reconfigure(level='ERROR')
    assert slave.log_level == logging.DEBUG
    master.warning('мастер скрыт')
    slave.warning('слейв виден')
    content = read(log_file)
    assert 'мастер скрыт' not in content and 'слейв виден' in content


def test_master_reload_level_does_not_touch_slave(pair, log_dir):
    master, slave = pair
    master.reload_from_config(make_config(log_dir, file_enabled='True', LOG_LEVEL='CRITICAL'))
    assert slave.log_level == logging.DEBUG


def test_master_move_file_moves_slave(pair, tmp_path, log_file):
    master, slave = pair
    new_dir = tmp_path / 'moved'
    master.reconfigure(base_log_FILE=str(new_dir) + os.sep)
    assert slave.file_handler is master.file_handler
    slave.info('переехал')
    assert 'переехал' in read(new_dir / 'app.log')
    assert 'переехал' not in read(log_file)


def test_master_disable_with_full_sync_disables_slave_flag(make_logger, master_cfg, capsys):
    master = make_logger(name='Mf', config=master_cfg, enable_file_logging=True, sync_full_state=True)
    slave = make_logger(name='Sf', enable_file_logging='Mf')
    # от мастера копируется True, но get_instance(sync_full_state=False) перетирает
    assert slave._sync_full_state is False
    master.disable()
    # мастер без обработчика → _update_shared_slaves ничего не делает
    assert slave.is_enabled() is True


def test_master_file_off_stops_slaves(pair, log_file):
    """S2: раньше слейв продолжал писать через закрытый обработчик мастера."""
    master, slave = pair
    master.reconfigure(file_enabled=False)
    assert master.file_handler is None
    assert slave.file_handler is None
    assert slave.file_handler not in slave.logger.handlers
    open(log_file, 'w').close()
    slave.info('не должно попасть в файл')
    assert read(log_file) == ''


def test_master_file_off_keeps_link(pair):
    """Связь мастер/слейв сохраняется: когда мастер снова откроет файл, слейв подключится."""
    master, slave = pair
    master.reconfigure(file_enabled=False)
    assert slave.get_master_logger() is master
    master.reconfigure(file_enabled=True)
    assert slave.file_handler is master.file_handler


def test_slave_file_off_detaches_shared_handler(pair, log_file):
    """Слейв выключил себе файл через reload — общий обработчик отцеплен, но не закрыт."""
    master, slave = pair
    slave.reload_from_config(make_config(os.path.dirname(log_file), S_file_enabled='False'))
    assert slave.file_handler is None
    open(log_file, 'w').close()
    slave.info('нет')
    master.info('да')
    content = read(log_file)
    assert '[S]' not in content and '[M]' in content


def test_master_turn_off_file_logging_unshares_slaves(pair, log_file):
    """turn_off_file_logging у мастера отвязывает слейвов: те создают свой обработчик."""
    master, slave = pair
    master.disable_file()
    assert slave.has_shared_handler() is False
    assert slave.file_handler is not None
    assert slave.file_handler is not master.file_handler
    slave.info('свой файл')
    assert 'свой файл' in read(log_file)


# ---------------------------------------------------------------------------
# Изменения на слейве
# ---------------------------------------------------------------------------

def test_slave_reconfigure_level_is_local(pair):
    """S3: уровень слейва меняется у слейва. Раньше весь вызов уходил мастеру."""
    master, slave = pair
    slave.reconfigure(level='CRITICAL')
    assert slave.log_level == logging.CRITICAL
    assert master.log_level == logging.DEBUG


def test_slave_reconfigure_file_params_go_to_master(pair, tmp_path):
    """Параметры общего файла меняет только мастер — слейв перенаправляет их ему."""
    master, slave = pair
    new_dir = tmp_path / 'by_slave'
    slave.reconfigure(base_log_FILE=str(new_dir) + os.sep, level='ERROR')
    assert master.base_log_file == str(new_dir) + os.sep
    assert slave.file_handler is master.file_handler
    assert slave.log_level == logging.ERROR
    assert master.log_level == logging.DEBUG
    slave.error('в новом файле')
    assert 'в новом файле' in read(new_dir / 'app.log')


def test_slave_disable_console_is_independent(pair, capsys):
    master, slave = pair
    slave.disable_console()
    assert slave.is_console_enabled() is False
    assert master.is_console_enabled() is True


def test_slave_disable_keeps_master(pair, log_file):
    master, slave = pair
    slave.disable()
    slave.info('нет')
    master.info('да')
    content = read(log_file)
    assert '[S]' not in content and '[M]' in content


def test_slave_enable_after_disable_restores_shared_file(pair, log_file):
    master, slave = pair
    slave.disable()
    slave.enable()
    assert slave.file_handler is master.file_handler
    slave.info('вернулся')
    assert '[S]' in read(log_file)


def test_slave_disable_file_unshares_and_stops_writing(pair, log_file):
    master, slave = pair
    slave.disable_file()
    assert slave.has_shared_handler() is False
    assert slave.file_handler is None
    slave.info('не в файл')
    assert '[S]' not in read(log_file)
    # общий обработчик мастера не закрыт
    master.info('мастер пишет')
    assert '[M]' in read(log_file)


def test_slave_enable_file_after_disable_file(pair, log_file):
    """enable_file() у бывшего слейва создаёт собственный обработчик на тот же файл.

    До исправления R2 обработчик не создавался: effective_enable_file_logging()
    возвращал True от мастера, и метод считал файл «уже включённым».
    """
    master, slave = pair
    slave.disable_file()
    slave.enable_file()
    assert slave.file_handler is not None
    slave.info('снова')
    assert '[S]' in read(log_file)


def test_unshare_creates_own_handler_same_file(pair, log_file):
    master, slave = pair
    slave.unshare_file_handler()
    assert slave.has_shared_handler() is False
    assert slave.file_handler is not None
    assert slave.file_handler is not master.file_handler
    assert slave.file_handler.baseFilename == master.file_handler.baseFilename
    assert all(r() is not slave for r in master._shared_slaves)


def test_unshare_when_not_shared_is_noop(make_logger):
    lg = make_logger()
    lg.unshare_file_handler()
    assert lg.has_shared_handler() is False


def test_slave_reload_from_config_uses_master_values(pair, log_dir):
    """Слейв без собственного {name}_KEY берёт значения у мастера, а не из LOG_KEY."""
    master, slave = pair
    slave.reload_from_config(make_config(log_dir, LOG_LEVEL='ERROR', M_LEVEL='DEBUG'))
    assert slave.log_level == logging.DEBUG


def test_slave_reload_own_key_wins(pair, log_dir):
    master, slave = pair
    slave.reload_from_config(make_config(log_dir, M_LEVEL='DEBUG', S_LEVEL='ERROR'))
    assert slave.log_level == logging.ERROR


def test_dead_slaves_are_cleaned(make_logger, master_cfg, logger_cls):
    import gc
    master = make_logger(name='Mg', config=master_cfg, enable_file_logging=True)
    slave = make_logger(name='Sg', enable_file_logging='Mg')
    del logger_cls._instances['Sg']
    del slave
    gc.collect()
    master.reconfigure(level='INFO')
    assert master._shared_slaves == []
