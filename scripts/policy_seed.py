"""Тонкий транспорт: идемпотентный сид routing-policy в MLflow (iter 6) — промпты в Prompt
Registry, LoggedModel-версии с пинами, registered-версии, alias champion/challenger."""

from app.config import get_settings
from app.persistence.routing_policy import MODEL_NAME
from app.workflow.policy import PROMPT_CLASSIFY, PROMPT_POLICY_CHECK, seed_policy


def main() -> None:
    settings = get_settings()
    result = seed_policy(tracking_uri=settings.mlflow_tracking_uri)
    print(f"prompt {PROMPT_CLASSIFY}: v{result.classify_version}")
    print(
        f"prompt {PROMPT_POLICY_CHECK}: v{result.policy_check_version} (код), "
        f"v{result.policy_check_rubber_stamp_version} (rubber-stamp, challenger-фикстура)"
    )
    print(
        f"{MODEL_NAME} v{result.champion_version}: "
        f"classify v{result.classify_version} + policy-check v{result.policy_check_version}"
    )
    print(
        f"{MODEL_NAME} v{result.challenger_version}: classify v{result.classify_version} "
        f"+ policy-check v{result.policy_check_rubber_stamp_version}"
    )
    for alias, was_set in result.aliases_set.items():
        state = "поставлен" if was_set else "уже существовал — не тронут (swap не откатывается)"
        print(f"alias {alias}: {state}")


if __name__ == "__main__":
    main()
