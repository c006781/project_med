# tests/test_logger/test_decorator.py

"""
Декоратор log_execution_time — в приложении применён ~1300 раз.
"""

import asyncio
import inspect
import logging
import os
import re

import pytest

from tests.test_logger.conftest import make_config, read

START_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in <(?P<func>.+?)>:\t(?P<msg>.*)$')


@pytest.fixture
def lg(make_logger, log_dir):
    return make_logger(name='deco', enable_file_logging=True)


@pytest.fixture
def lines(log_dir):
    def _lines():
        return read(os.path.join(log_dir, 'app.log')).splitlines()
    return _lines


def _msgs(lines):
    return [START_RE.search(line)['msg'] for line in lines]


# ---------------------------------------------------------------------------
# Базовое поведение
# ---------------------------------------------------------------------------

def test_start_and_end_messages(lg, lines):
    @lg.log_execution_time()
    def work(x):
        return x * 2

    assert work(21) == 42
    out = lines()
    assert len(out) == 2
    assert _msgs(out)[0] == '[Начало]'
    assert re.fullmatch(r'\[Завершение: \d+\.\d{4} сек\]', _msgs(out)[1])
    assert all('\tDEBUG\t' in line for line in out)


def test_caller_info_points_to_def_line(lg, lines):
    @lg.log_execution_time()
    def target():
        pass

    def_line = inspect.getsourcelines(target.__wrapped__)[1]
    target()
    m = START_RE.search(lines()[0])
    assert os.path.normcase(m['file']) == os.path.normcase(__file__)
    assert int(m['line']) in (def_line, def_line + 1)  # строка декоратора или def
    assert m['func'] == 'test_caller_info_points_to_def_line.<locals>.target'


def test_description(lg, lines):
    @lg.log_execution_time(description='Загрузка')
    def f():
        pass

    f()
    msgs = _msgs(lines())
    assert msgs[0] == 'Загрузка [Начало]'
    assert msgs[1].startswith('Загрузка [Завершение:')


def test_level_parameter(lg, lines):
    @lg.log_execution_time(level=logging.INFO)
    def f():
        pass

    f()
    assert all('\tINFO\t' in line for line in lines())


def test_preserves_metadata(lg):
    @lg.log_execution_time()
    def documented(a, b=1):
        """Док."""

    assert documented.__name__ == 'documented'
    assert documented.__doc__ == 'Док.'
    assert documented.__wrapped__ is not None


def test_exception_is_logged_and_reraised(lg, lines):
    @lg.log_execution_time()
    def boom():
        raise KeyError('нет ключа')

    with pytest.raises(KeyError, match='нет ключа'):
        boom()
    end = _msgs(lines())[1]
    assert end.startswith('[Завершение:')
    assert end.endswith(": 'нет ключа'")


def test_base_exception_passes_through(lg, lines):
    """BaseException (SystemExit/KeyboardInterrupt) не перехватывается.

    Строка завершения пишется из finally, но без текста ошибки.
    """
    @lg.log_execution_time()
    def stop():
        raise SystemExit(3)

    with pytest.raises(SystemExit):
        stop()
    msgs = _msgs(lines())
    assert len(msgs) == 2
    assert re.fullmatch(r'\[Завершение: \d+\.\d{4} сек\]', msgs[1])


def test_log_return(lg, lines):
    @lg.log_execution_time(log_return=True)
    def f():
        return {'a': 1}

    f()
    assert _msgs(lines())[1].endswith(" -> {'a': 1}")


def test_log_return_none_not_shown(lg, lines):
    @lg.log_execution_time(log_return=True)
    def f():
        return None

    f()
    assert '->' not in _msgs(lines())[1]


# ---------------------------------------------------------------------------
# Аргументы
# ---------------------------------------------------------------------------

def test_log_args_function(lg, lines):
    @lg.log_execution_time(log_args=True)
    def f(a, b, c=None):
        pass

    f(1, 'x', c=[2])
    assert _msgs(lines())[0] == "[Начало] with args: (1, 'x', c=[2])"


def test_log_args_method_excludes_self(lg, lines):
    """self в аргументы не попадает (до 2026-10-14 попадал repr(self))."""
    class Svc:
        def __repr__(self):
            return '<Svc>'

        @lg.log_execution_time(log_args=True)
        def run(self, n):
            pass

    Svc().run(5)
    assert _msgs(lines())[0] == '[Начало] with args: (5)'


def test_log_args_never_for_init(lg, lines):
    class Svc:
        @lg.log_execution_time(log_args=True)
        def __init__(self, secret):
            pass

    Svc('пароль')
    assert 'пароль' not in read_all(lines)


def read_all(lines):
    return '\n'.join(lines())


def test_log_args_default_read_at_call_time(make_logger, log_dir, lines):
    """log_args=None — смотрим lg.log_args в момент вызова.

    До 2026-10-14 значение фиксировалось при декорировании (при импорте модуля).
    """
    lg = make_logger(config=make_config(log_dir, LOG_ARGS='True'), enable_file_logging=True)

    @lg.log_execution_time()
    def f(x):
        pass

    f(7)
    lg.log_args = False
    f(8)
    msgs = [m for m in _msgs(lines()) if '[Начало]' in m]
    assert msgs == ['[Начало] with args: (7)', '[Начало]']


def test_log_args_explicit_overrides_logger(lg, lines):
    lg.log_args = True

    @lg.log_execution_time(log_args=False)
    def f(x):
        pass

    f(1)
    assert _msgs(lines())[0] == '[Начало]'


def test_log_args_classmethod_excludes_cls(lg, lines):
    class C:
        @classmethod
        @lg.log_execution_time(log_args=True)
        def make(cls, n):
            return n

    C.make(3)
    assert _msgs(lines())[0] == '[Начало] with args: (3)'


# ---------------------------------------------------------------------------
# Когда декоратор молчит
# ---------------------------------------------------------------------------

def test_level_below_threshold_runs_silently(make_logger, log_dir, lines):
    lg = make_logger(config=make_config(log_dir, LOG_LEVEL='INFO'), enable_file_logging=True)

    @lg.log_execution_time()  # DEBUG
    def f():
        return 'ok'

    assert f() == 'ok'
    assert lines() == []


def test_threshold_checked_at_call_time(lg, lines):
    @lg.log_execution_time()
    def f():
        pass

    lg.reconfigure(level='ERROR')
    f()
    assert lines() == []
    lg.reconfigure(level='DEBUG')
    f()
    assert len(lines()) == 2


def test_disabled_logger_runs_silently(lg, lines):
    @lg.log_execution_time()
    def f():
        return 1

    lg.disable()
    assert f() == 1
    assert lines() == []


def test_disabled_list_runs_silently(logger_cls, lg, lines):
    @lg.log_execution_time()
    def f():
        return 1

    logger_cls.add_disabled_logger('deco')
    assert f() == 1
    assert lines() == []


def test_exception_reraised_when_silent(lg):
    @lg.log_execution_time()
    def boom():
        raise ValueError('x')

    lg.disable()
    with pytest.raises(ValueError):
        boom()


# ---------------------------------------------------------------------------
# Виды функций
# ---------------------------------------------------------------------------

def test_staticmethod_and_classmethod_objects(lg, lines):
    """Декоратор принимает объекты staticmethod/classmethod и разворачивает их."""
    def plain(x):
        return x + 1

    wrapped = lg.log_execution_time()(staticmethod(plain))
    assert wrapped(1) == 2
    assert len(lines()) == 2


def test_decorator_under_staticmethod(lg, lines):
    class C:
        @staticmethod
        @lg.log_execution_time()
        def s(x):
            return x

        @classmethod
        @lg.log_execution_time()
        def c(cls):
            return cls

    assert C.s(3) == 3
    assert C.c() is C
    assert len(lines()) == 4


def test_async_function(lg, lines):
    @lg.log_execution_time(log_return=True)
    async def coro(x):
        await asyncio.sleep(0)
        return x

    assert inspect.iscoroutinefunction(coro)
    assert asyncio.run(coro(5)) == 5
    msgs = _msgs(lines())
    assert msgs[0] == '[Начало]'
    assert msgs[1].endswith(' -> 5')


def test_async_exception(lg, lines):
    @lg.log_execution_time()
    async def coro():
        raise RuntimeError('async boom')

    with pytest.raises(RuntimeError):
        asyncio.run(coro())
    assert _msgs(lines())[1].endswith(': async boom')


def test_async_silent_when_disabled(lg, lines):
    @lg.log_execution_time()
    async def coro():
        return 1

    lg.disable()
    assert asyncio.run(coro()) == 1
    assert lines() == []


# ---------------------------------------------------------------------------
# Глубина вложенности (show_depth)
# ---------------------------------------------------------------------------

def _indent(line):
    return len(re.search(r'\]\t(>*) File', line).group(1))


def test_show_depth_nested_sync(lg, lines):
    """D1: раньше глубина в синхронном коде всегда была 0."""
    @lg.log_execution_time(show_depth=True)
    def outer():
        inner()

    @lg.log_execution_time(show_depth=True)
    def inner():
        pass

    outer()
    depths = [_indent(line) for line in lines()]
    assert depths == [1, 2, 2, 1]


def test_show_depth_restored_after_exception(lg, lines):
    @lg.log_execution_time(show_depth=True)
    def boom():
        raise ValueError('x')

    @lg.log_execution_time(show_depth=True)
    def ok():
        pass

    with pytest.raises(ValueError):
        boom()
    ok()
    assert [_indent(line) for line in lines()] == [1, 1, 1, 1]
    assert lg._get_current_depth() == 0


def test_show_depth_independent_per_thread(lg, lines):
    import threading

    @lg.log_execution_time(show_depth=True)
    def in_thread():
        pass

    @lg.log_execution_time(show_depth=True)
    def outer():
        t = threading.Thread(target=in_thread)
        t.start()
        t.join()

    outer()
    thread_lines = [line for line in lines() if 'in_thread' in line]
    assert [_indent(line) for line in thread_lines] == [1, 1]


def test_show_depth_independent_per_async_task(lg, lines):
    @lg.log_execution_time(show_depth=True)
    async def leaf(name):
        await asyncio.sleep(0)

    @lg.log_execution_time(show_depth=True)
    async def branch(name):
        await leaf(name)

    async def main():
        await asyncio.gather(branch('a'), branch('b'))

    asyncio.run(main())
    leaf_depths = [_indent(line) for line in lines() if '.leaf>' in line]
    assert leaf_depths == [2, 2, 2, 2]


def test_show_call_depth_logger_flag_uses_stack(make_logger, log_dir, lines):
    """При show_call_depth=True у логгера отступ считается по стеку и в декораторе."""
    lg = make_logger(config=make_config(log_dir, show_call_depth='True'), enable_file_logging=True)

    @lg.log_execution_time()
    def f():
        pass

    f()
    depths = [_indent(line) for line in lines()]
    assert depths[0] > 0 and depths[0] == depths[1]


@pytest.mark.parametrize('level, name', [('INFO', 'INFO'), ('warning', 'WARNING'), (logging.ERROR, 'ERROR')])
def test_level_as_string_or_int(lg, lines, level, name):
    """P7: уровень декоратора можно передать строкой."""
    @lg.log_execution_time(level=level)
    def f():
        pass

    f()
    assert all(f'\t{name}\t' in line for line in lines())


def test_bad_level_raises_at_decoration(lg):
    with pytest.raises(ValueError):
        lg.log_execution_time(level='TRACE')
