from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


ERROR_TYPE_LABELS = {
    "WRONG_SEQUENCE": "нарушена последовательность действий",
    "WRONG_EQUIPMENT": "выбрано неправильное оборудование",
    "WRONG_ACTION_TYPE": "выбран неправильный тип действия",
    "WRONG_PARAMETER_VALUE": "задано неправильное значение параметра",
    "DELAYED_ACTION": "действие выполнено с задержкой",
    "MISSED_ACTION": "обязательное действие пропущено",
    "REGULATORY_VIOLATION": "нарушено требование регламента",
}


def error_to_dict(error: Any) -> dict:
    """
    Преобразует ErrorEvent или обычный словарь в dict.
    """

    if isinstance(error, dict):
        return error

    if hasattr(error, "model_dump"):
        return error.model_dump()

    if is_dataclass(error):
        return asdict(error)

    if hasattr(error, "__dict__"):
        return vars(error)

    raise TypeError(
        "Ошибка должна быть словарём или объектом ErrorEvent."
    )


def value_to_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, Enum):
        value = value.value

    return str(value).strip()


def build_search_query(error: Any) -> str:
    """
    Формирует смысловой запрос для RAG-поиска.
    """

    data = error_to_dict(error)

    error_type = value_to_text(
        data.get("error_type")
    )

    operator_action = value_to_text(
        data.get("operator_action")
    )

    expected_action = value_to_text(
        data.get("expected_action")
    )

    cause = value_to_text(
        data.get("cause")
    )

    consequence = value_to_text(
        data.get("consequence")
    )

    if not any([
        operator_action,
        expected_action,
        cause,
        consequence,
    ]):
        raise ValueError(
            "В ошибке нет данных для RAG-поиска."
        )

    parts = []

    if error_type:
        error_label = ERROR_TYPE_LABELS.get(
            error_type,
            error_type,
        )

        parts.append(
            f"Тип ошибки: {error_label}."
        )

    if operator_action:
        parts.append(
            f"Фактическое действие оператора: "
            f"{operator_action}."
        )

    if expected_action:
        parts.append(
            f"Ожидаемое правильное действие: "
            f"{expected_action}."
        )

    if cause:
        parts.append(
            f"Описание ошибки: {cause}."
        )

    if consequence:
        parts.append(
            f"Возможное последствие: {consequence}."
        )

    parts.append(
        "Найти в производственных документах требования "
        "к правильным действиям оператора в этой ситуации."
    )

    return "\n".join(parts)


if __name__ == "__main__":
    test_error = {
        "error_type": "WRONG_SEQUENCE",
        "severity": "HIGH",
        "timestamp": 45.2,
        "operator_action": (
            "SET_VALUE для исправного клапана "
            "со значением 0.8"
        ),
        "expected_action": (
            "Прекратить попытки регулирования "
            "неисправным клапаном"
        ),
        "cause": (
            "Нарушена последовательность действий "
            "после подтверждения отказа клапана"
        ),
        "consequence": (
            "Продолжение снижения расхода и уровня К-1"
        ),
    }

    print(build_search_query(test_error))
    