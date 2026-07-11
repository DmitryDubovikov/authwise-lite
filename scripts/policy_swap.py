"""Тонкий транспорт: ручной swap alias champion ↔ challenger на pa-routing-policy (iter 6).
Повторный запуск возвращает исходное состояние (swap — обмен, не промоушен-механика)."""

from app.config import get_settings
from app.persistence.routing_policy import MODEL_NAME
from app.workflow.policy import swap_policy


def main() -> None:
    settings = get_settings()
    champion_version, challenger_version = swap_policy(tracking_uri=settings.mlflow_tracking_uri)
    print(
        f"{MODEL_NAME}: champion → v{champion_version}, challenger → v{challenger_version} "
        f"(обмен; повторный swap вернёт исходное)"
    )


if __name__ == "__main__":
    main()
