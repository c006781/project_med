# tests/test_logger/test_class_config.py

"""
Настройка наследника BaseAppLogger в объявлении класса:
console_output / outputs / log_format (параметры или атрибуты), свой реестр.
"""

import logging
import os
import re

import pytest

from app.utils.logger.base_logger import BaseAppLogger, CallableHandler
from tests.test_logger.conftest import make_config, read

LINE_RE = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}\t[A-Z]+\t\[[^\]]+\]\t>* File ".+", line \d+, in <.+>:\t.*$')


@pytest.fixture
def make_cls(logger_cls, log_dir):
    """Фабрика наследников с конфигом из tmp_path; все созданные закрываются после теста."""
    created = []

    def _make(**class_kwargs):
        cfg = make_config(log_dir, file_enabled='True')

        class Custom(BaseAppLogger, **class_kwargs):
            @classmethod
            def get_default_config(cls):
                return dict(cfg)

        created.append(Custom)
        return Custom

    yield _make
    for c in created:
        c.close_all()


# ---------------------------------------------------------------------------
# Свой реестр
# ---------------------------------------------------------------------------

def test_subclass_gets_own_registry_automatically(make_cls):
    """Раньше наследник без _instances = {} делил реестр с родителем."""
    A = make_cls()
    B = make_cls()
    assert '_instances' in A.__dict__ and '_instances' in B.__dict__
    a = A.get_instance('same')
    b = B.get_instance('same')
    assert a is not b
    assert A._instances is not B._instances


def test_grandchild_gets_own_registry(make_cls):
    A = make_cls()

    class Child(A):
        pass

    assert Child._instances is not A._instances
    assert Child.get_instance('x') is not A.get_instance('x')


def test_explicit_registry_kept(logger_cls):
    """Явный _instances = {} (как в AppLogger) не перезаписывается."""
    shared = {}

    class Explicit(BaseAppLogger):
        _instances = shared

    assert Explicit._instances is shared


# ---------------------------------------------------------------------------
# console_output
# ---------------------------------------------------------------------------

def test_console_output_param_replaces_stderr(make_cls, capsys):
    got = []
    Cls = make_cls(console_output=got.append)
    lg = Cls.get_instance('c1')
    lg.info('в функцию вместо консоли')
    assert capsys.readouterr().err == ''
    assert len(got) == 1
    assert isinstance(lg.console_handler, CallableHandler)


def test_console_output_keeps_log_format(make_cls, log_dir):
    """Функция-консоль получает ту же строку, что пишется в файл."""
    got = []
    lg = make_cls(console_output=got.append).get_instance('c2')
    lg.warning('один формат')
    file_line = read(os.path.join(log_dir, 'app.log')).splitlines()[-1]
    assert got == [file_line]
    assert LINE_RE.match(got[0])


def test_console_output_attribute(logger_cls, log_dir):
    got = []

    class AttrLogger(BaseAppLogger):
        CONSOLE_OUTPUT = got.append

        @classmethod
        def get_default_config(cls):
            return make_config(log_dir)

    try:
        AttrLogger.get_instance('a').info('атрибут')
        assert len(got) == 1
    finally:
        AttrLogger.close_all()


def test_console_output_plain_function_not_bound(make_cls):
    """Обычная функция как атрибут класса не превращается в метод (self не передаётся)."""
    got = []

    def sink(text):
        got.append(text)

    make_cls(console_output=sink).get_instance('pf').info('x')
    assert len(got) == 1 and got[0].endswith('x')


def test_console_output_respects_console_flags_and_levels(make_cls):
    got = []
    lg = make_cls(console_output=got.append).get_instance('c3')
    lg.disable_console()
    lg.info('нет')
    lg.enable_console()
    lg.reconfigure(console_level='ERROR')
    lg.warning('нет')
    lg.error('да')
    assert len(got) == 1 and got[0].endswith('да')


def test_console_output_on_reload(make_cls, log_dir):
    got = []
    lg = make_cls(console_output=got.append).get_instance('c4')
    lg.reload_from_config(make_config(log_dir, console_enabled='True', LOG_LEVEL='INFO'))
    lg.info('после перезагрузки')
    assert got[-1].endswith('после перезагрузки')


# ---------------------------------------------------------------------------
# outputs (общие выводы класса)
# ---------------------------------------------------------------------------

def test_class_outputs_one_handler_for_all_loggers(make_cls):
    got = []
    Cls = make_cls(outputs=[got.append])
    a, b = Cls.get_instance('oa'), Cls.get_instance('ob')
    ha = [h for h in a.logger.handlers if isinstance(h, CallableHandler)]
    hb = [h for h in b.logger.handlers if isinstance(h, CallableHandler)]
    assert ha == hb and len(ha) == 1
    a.info('1')
    b.info('2')
    assert [g.rsplit('\t', 1)[-1] for g in got] == ['1', '2']


def test_class_outputs_dict_spec(make_cls):
    got, errors = [], []
    Cls = make_cls(outputs=[
        got.append,
        {'func': errors.append, 'level': 'ERROR', 'formatter': '%(name)s:%(plain_message)s'},
    ])
    lg = Cls.get_instance('od')
    lg.info('инфо')
    lg.error('ошибка')
    assert len(got) == 2
    assert errors == ['od:ошибка']


def test_class_outputs_keep_log_format(make_cls, log_dir):
    got = []
    lg = make_cls(outputs=[got.append]).get_instance('of')
    lg.info('формат')
    assert got[-1] == read(os.path.join(log_dir, 'app.log')).splitlines()[-1]


def test_class_outputs_each_logger_level(make_cls, log_dir):
    got = []
    Cls = make_cls(outputs=[got.append])
    quiet = Cls.get_instance('q', config=make_config(log_dir, LOG_LEVEL='ERROR'))
    loud = Cls.get_instance('l')
    quiet.info('нет')
    loud.info('да')
    assert len(got) == 1 and '[l]' in got[0]


def test_class_outputs_background(make_cls):
    got = []
    Cls = make_cls(outputs=[{'func': got.append, 'background': True}])
    lg = Cls.get_instance('ob2')
    for i in range(20):
        lg.info(f'm{i}')
    Cls.close_class_outputs()
    assert len(got) == 20


def test_class_outputs_inherited_and_overridden(make_cls):
    parent_got, child_got = [], []
    Parent = make_cls(outputs=[parent_got.append])

    class Inherits(Parent):
        pass

    class Overrides(Parent, outputs=[child_got.append]):
        pass

    try:
        assert Inherits._class_output_handlers() == Parent._class_output_handlers()
        Inherits.get_instance('i').info('наследник')
        Overrides.get_instance('o').info('свой')
        assert len(parent_got) == 1 and parent_got[0].endswith('наследник')
        assert len(child_got) == 1 and child_got[0].endswith('свой')
    finally:
        Inherits.close_all()
        Overrides.close_all()


def test_class_outputs_silent_when_logger_disabled(make_cls):
    got = []
    lg = make_cls(outputs=[got.append]).get_instance('od2')
    lg.disable()
    lg.error('нет')
    assert got == []


def test_close_one_logger_keeps_class_output(make_cls):
    got = []
    Cls = make_cls(outputs=[{'func': got.append, 'background': True}])
    a, b = Cls.get_instance('ca'), Cls.get_instance('cb')
    handler = Cls._class_output_handlers()[0]
    a.close()
    b.info('после close a')
    assert handler.flush(timeout=5)
    assert any(t.endswith('после close a') for t in got)


def test_close_all_closes_class_outputs(make_cls):
    Cls = make_cls(outputs=[{'func': lambda text: None, 'background': True}])
    Cls.get_instance('z')
    handler = Cls._class_output_handlers()[0]
    Cls.close_all()
    assert not handler._thread.is_alive()
    assert '_class_outputs_cache' not in Cls.__dict__


def test_bad_output_spec(make_cls):
    Cls = make_cls(outputs=[{'level': 'ERROR'}])
    with pytest.raises(TypeError, match='func'):
        Cls.get_instance('bad')


# ---------------------------------------------------------------------------
# log_format
# ---------------------------------------------------------------------------

def test_log_format_param(make_cls, log_dir, capsys):
    got = []
    Cls = make_cls(log_format='%(levelname)s|%(plain_message)s', console_output=got.append,
                   outputs=[got.append])
    lg = Cls.get_instance('lf')
    lg.info('коротко')
    assert got == ['INFO|коротко', 'INFO|коротко']
    assert read(os.path.join(log_dir, 'app.log')).strip() == 'INFO|коротко'


def test_app_logger_subclass_like_bot(logger_cls, log_dir):
    """Сценарий из жизни: наследник AppLogger, консоль — в «бота», ошибки — отдельно."""
    from app.utils.logger.logger import AppLogger
    to_bot, to_admin = [], []

    class BotLogger(AppLogger, console_output=to_bot.append,
                    outputs=[{'func': to_admin.append, 'level': 'ERROR',
                              'formatter': '%(levelname)s: %(plain_message)s'}]):
        _app_config = None

    try:
        BotLogger.configure({'LOG_DIR': log_dir, 'LOG_LEVEL': 'INFO'})
        lg = BotLogger.get_instance('bot')
        lg.info('привет')
        lg.error('сломалось')
        assert len(to_bot) == 2
        assert to_admin == ['ERROR: сломалось']
        assert BotLogger._instances is not AppLogger._instances
    finally:
        BotLogger.close_all()
