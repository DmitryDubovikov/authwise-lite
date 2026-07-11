"""Тонкий транспорт: verify routing-policy В СТОРЕ (правило 9) — alias, пины и шаблоны
запросами к MLflow API; проверки структурные (инвариантны к swap), вся семантика — в workflow
(PolicyVerification), здесь только печать."""

from app.config import get_settings
from app.persistence.routing_policy import MODEL_NAME
from app.workflow.policy import describe_pins, verify_policy
from scripts.verify_http import report


def main() -> None:
    settings = get_settings()
    result = verify_policy(tracking_uri=settings.mlflow_tracking_uri)
    for alias, policy in result.policies.items():
        print(f"{alias} → {MODEL_NAME} v{policy.registered_version} ({describe_pins(policy)})")
    report(
        result.problems,
        failed="стор не соответствует ожиданиям",
        ok=f"{MODEL_NAME}: alias разрешаются, пины params ↔ linkedPrompts сходятся, "
        f"политики различаются policy-check",
    )


if __name__ == "__main__":
    main()
