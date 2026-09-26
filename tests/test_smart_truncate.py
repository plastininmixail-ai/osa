"""Тесты умной обрезки Telegram."""

from __future__ import annotations

from osa.transports.telegram import TelegramBot


def test_no_truncate_for_short_text() -> None:
    """Короткий текст не обрезается."""
    text = "Short answer."
    result, truncated = TelegramBot._smart_truncate(text, max_len=100)
    assert result == text
    assert truncated is False


def test_truncate_by_section_break() -> None:
    """Обрезка по \n\n (границе секции)."""
    text = "Section 1\n\n" + "x" * 1000 + "\n\nSection 2\n\n" + "y" * 1000
    result, truncated = TelegramBot._smart_truncate(text, max_len=500)
    assert truncated is True
    # Должен обрезаться по \n\n между секциями
    assert "Section 1" in result
    assert "Section 2" not in result
    # Маркер обрезки
    assert "обрезано" in result


def test_truncate_by_word_boundary() -> None:
    """Если нет \n\n — обрезка по последнему пробелу."""
    text = "word " * 1000  # 5000 символов без \n\n
    result, truncated = TelegramBot._smart_truncate(text, max_len=500)
    assert truncated is True
    # Должен обрезаться по пробелу, не посреди слова
    assert not result.split("\n\n")[0].endswith("wo")  # не 'wo' на конце


def test_truncate_shows_size_info() -> None:
    """Маркер обрезки показывает размер оригинала."""
    text = "x" * 5000
    result, truncated = TelegramBot._smart_truncate(text, max_len=500)
    assert "5000" in result  # оригинальный размер


def test_truncate_handles_small_budget() -> None:
    """Если budget слишком мал — текст обрезается но marker всё равно добавляется."""
    text = "x" * 100
    result, truncated = TelegramBot._smart_truncate(text, max_len=50)
    assert truncated is True
    # Длина результата может превышать max_len из-за marker'а,
    # но сам контент (без marker'а) должен быть обрезан
    assert text[:50] in result
    assert "обрезано" in result
