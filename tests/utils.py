# tests/utils.py
"""
Вспомогательные утилиты для тестирования.
"""

def check_output_lines(output, expected_lines):
    """
    Проверяет, что вывод содержит ожидаемые строки с заданными фрагментами.
    
    :param output: многострочный вывод команды (строка)
    :param expected_lines: список списков строк. Каждый внутренний список содержит
                           фрагменты, которые должны присутствовать в соответствующей
                           строке вывода.
    """
    lines = output.strip().split('\n')
    assert len(lines) == len(expected_lines), \
        f"Количество строк не совпадает: ожидалось {len(expected_lines)}, получено {len(lines)}"
    for i, (line, expected) in enumerate(zip(lines, expected_lines)):
        for part in expected:
            assert part in line, f"Строка {i} не содержит '{part}': {line}"