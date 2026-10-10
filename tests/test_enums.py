import pytest
from src.models.enums import ChangeType, Language, ReviewSeverity


def test_change_type_values():
    assert ChangeType.ADDED == "added"
    assert ChangeType.MODIFIED == "modified"
    assert ChangeType.DELETED == "deleted"
    assert isinstance(ChangeType.ADDED, str)


def test_language_values():
    assert Language.PYTHON == "python"
    assert Language.TYPESCRIPT == "typescript"
    assert Language.JAVASCRIPT == "javascript"
    assert Language.GO == "go"
    assert Language.JAVA == "java"
    assert Language.RUST == "rust"
    assert isinstance(Language.PYTHON, str)


def test_review_severity_values():
    assert ReviewSeverity.INFO == "info"
    assert ReviewSeverity.WARNING == "warning"
    assert ReviewSeverity.CRITICAL == "critical"
    assert isinstance(ReviewSeverity.CRITICAL, str)


def test_enum_invalid_value():
    with pytest.raises(ValueError):
        ChangeType("invalid_type")

    with pytest.raises(ValueError):
        Language("unsupported_language")

    with pytest.raises(ValueError):
        ReviewSeverity("unknown_severity")
