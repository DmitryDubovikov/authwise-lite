"""Реестр routing-policy (решение «Г», iter 6): промпты — в Prompt Registry, external
LoggedModel пинит их конкретные версии (params + штатный link_prompt_version_to_model),
alias champion/challenger — на версиях registered model: собственных alias у LoggedModel
нет, регистрация его в Model Registry (source = models:/<model_id>) — штатный мост MLflow 3.
Единственное место, знающее этот драйвер (правило 6); tracking_uri приходит аргументом с
boundary. Все ensure_* идемпотентны: ищут существующую сущность, прежде чем создавать;
alias не перевешиваются (повторный сид не откатывает swap).
"""

import json
from dataclasses import dataclass

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

MODEL_NAME = "pa-routing-policy"  # registered model = «одна сущность» под alias
EXPERIMENT_NAME = "pa-routing-policy"  # эксперимент-дом LoggedModel-версий
CHAMPION = "champion"
CHALLENGER = "challenger"

# «alias не разрешается»: отсутствующий alias — INVALID_PARAMETER_VALUE, отсутствующая
# registered model — RESOURCE_DOES_NOT_EXIST. Остальные MlflowException (сервер недоступен
# и т.п.) — громко наверх, а не ложный диагноз «стор не засеян».
_ALIAS_MISSING_CODES = {"RESOURCE_DOES_NOT_EXIST", "INVALID_PARAMETER_VALUE"}


def _connect(tracking_uri: str) -> MlflowClient:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)  # Prompt/Model Registry живут в том же сторе
    return MlflowClient()


def ensure_prompt_version(name: str, template: str, *, tracking_uri: str) -> int:
    """Версия промпта с точно таким шаблоном; нет ни одной — регистрируется новая."""
    _connect(tracking_uri)
    latest = mlflow.genai.load_prompt(f"prompts:/{name}@latest", allow_missing=True)
    if latest is not None:
        for version in range(1, latest.version + 1):
            if mlflow.genai.load_prompt(name, version=version).template == template:
                return version
    return mlflow.genai.register_prompt(name=name, template=template).version


def ensure_policy_version(pins: dict[str, int], *, tracking_uri: str) -> str:
    """External LoggedModel с точно такими пинами промптов (params); нет — создаётся,
    и запиненные версии линкуются штатно (тег mlflow.linkedPrompts — витрина в UI)."""
    client = _connect(tracking_uri)
    params = {name: str(version) for name, version in pins.items()}
    experiment = client.get_experiment_by_name(EXPERIMENT_NAME)
    experiment_id = (
        experiment.experiment_id if experiment else client.create_experiment(EXPERIMENT_NAME)
    )
    existing = mlflow.search_logged_models(
        experiment_ids=[experiment_id],
        filter_string=f"name = '{MODEL_NAME}'",
        output_format="list",
    )
    for model in existing:
        # строгий матч: params = ровно пины (resolve интерпретирует каждый param как пин)
        if (model.params or {}) == params:
            return model.model_id
    model = mlflow.create_external_model(
        name=MODEL_NAME, params=params, experiment_id=experiment_id
    )
    for name, version in pins.items():
        client.link_prompt_version_to_model(name, str(version), model.model_id)
    return model.model_id


def ensure_registered_version(model_id: str, *, tracking_uri: str) -> int:
    """Версия registered model с source = этот LoggedModel; нет — регистрируется."""
    client = _connect(tracking_uri)
    source = f"models:/{model_id}"
    for candidate in client.search_model_versions(f"name = '{MODEL_NAME}'"):
        if candidate.source == source:
            return int(candidate.version)
    return int(mlflow.register_model(source, MODEL_NAME).version)


def alias_version(alias: str, *, tracking_uri: str) -> int | None:
    """Версия registered model под alias; None — alias не разрешается (стор не засеян)."""
    client = _connect(tracking_uri)
    try:
        return int(client.get_model_version_by_alias(MODEL_NAME, alias).version)
    except MlflowException as exc:
        if exc.error_code not in _ALIAS_MISSING_CODES:
            raise
        return None


def set_alias(alias: str, version: int, *, tracking_uri: str) -> None:
    """Переназначить alias на версию (атомарно для одного alias — штатный механизм)."""
    _connect(tracking_uri).set_registered_model_alias(MODEL_NAME, alias, str(version))


@dataclass(frozen=True)
class ResolvedPolicy:
    """Разрешённая по alias версия routing-policy — всё из стора (правило 9)."""

    alias: str
    registered_version: int
    model_id: str
    prompt_versions: dict[str, int]  # имя промпта → запиненная версия (params LoggedModel)
    templates: dict[str, str]  # имя промпта → шаблон запиненной версии из Prompt Registry


def resolve(alias: str, *, tracking_uri: str) -> ResolvedPolicy | None:
    """alias → версия registered model → LoggedModel → пины → шаблоны; None — alias
    не разрешается (стор не засеян). Консистентность двух кодировок пинов (params и штатный
    тег mlflow.linkedPrompts) — драйверное знание, проверяется здесь: расхождение и битый
    source — ValueError (стор неконсистентен, а не «не засеян»)."""
    client = _connect(tracking_uri)
    try:
        version = client.get_model_version_by_alias(MODEL_NAME, alias)
    except MlflowException as exc:
        if exc.error_code not in _ALIAS_MISSING_CODES:
            raise
        return None
    if not version.source or not version.source.startswith("models:/"):
        raise ValueError(
            f"{MODEL_NAME} v{version.version} (alias {alias!r}) не ссылается на "
            f"LoggedModel: source={version.source!r}"
        )
    model_id = version.source.rsplit("/", 1)[-1]
    model = client.get_logged_model(model_id)
    pins = {name: int(v) for name, v in (model.params or {}).items()}
    linked = {
        entry["name"]: int(entry["version"])
        for entry in json.loads(model.tags.get("mlflow.linkedPrompts", "[]"))
    }
    if linked != pins:
        raise ValueError(
            f"{MODEL_NAME} v{version.version} (alias {alias!r}): linkedPrompts {linked} "
            f"расходится с params {pins}"
        )
    templates = {
        name: mlflow.genai.load_prompt(name, version=v).template for name, v in pins.items()
    }
    return ResolvedPolicy(
        alias=alias,
        registered_version=int(version.version),
        model_id=model_id,
        prompt_versions=pins,
        templates=templates,
    )
