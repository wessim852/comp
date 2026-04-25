from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


DEFAULT_MODEL = "local-deterministic"
DEFAULT_SYSTEM_PROMPT = (
    "Tu es un assistant d'exploitation Smart City. "
    "Redige un rapport operationnel concis en francais et propose des actions prioritaires."
)
POLLUTION_WARNING_THRESHOLD = 80.0
POLLUTION_CRITICAL_THRESHOLD = 100.0


@dataclass(frozen=True)
class AIProviderConfig:
    api_key: str = ""
    base_url: str = ""
    model: str = DEFAULT_MODEL
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "AIProviderConfig":
        return cls(
            api_key=os.getenv("AI_REPORT_API_KEY", ""),
            base_url=os.getenv("AI_REPORT_BASE_URL", ""),
            model=os.getenv("AI_REPORT_MODEL", DEFAULT_MODEL),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key.strip() and self.base_url.strip() and self.model.strip())


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.to_dict("records")


def build_report_context(
    sensors: pd.DataFrame,
    interventions: pd.DataFrame,
    top_polluted_zones: pd.DataFrame,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now()
    sensor_records = _records(sensors)
    intervention_records = _records(interventions)
    polluted_records = _records(top_polluted_zones)

    out_of_service = [
        row for row in sensor_records if str(row.get("etat_capteur", "")).lower() == "hors service"
    ]
    signaled = [
        row for row in sensor_records if str(row.get("etat_capteur", "")).lower() == "signale"
    ]
    missing_values = [
        row for row in sensor_records if _safe_float(row.get("valeur")) is None
    ]
    critical_pollution = [
        row
        for row in polluted_records
        if (_safe_float(row.get("moyenne_pollution")) or 0.0) >= POLLUTION_CRITICAL_THRESHOLD
    ]
    warning_pollution = [
        row
        for row in polluted_records
        if POLLUTION_WARNING_THRESHOLD
        <= (_safe_float(row.get("moyenne_pollution")) or 0.0)
        < POLLUTION_CRITICAL_THRESHOLD
    ]
    active_interventions = [
        row
        for row in intervention_records
        if str(row.get("statut_intervention", "")).lower() in {"demande", "en_cours"}
    ]

    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "counts": {
            "capteurs": len(sensor_records),
            "capteurs_hors_service": len(out_of_service),
            "capteurs_signales": len(signaled),
            "mesures_sans_valeur": len(missing_values),
            "interventions_ouvertes": len(active_interventions),
            "zones_pollution_critique": len(critical_pollution),
            "zones_pollution_surveillance": len(warning_pollution),
        },
        "top_polluted_zones": polluted_records[:5],
        "out_of_service_sensors": out_of_service[:10],
        "signaled_sensors": signaled[:10],
        "missing_value_sensors": missing_values[:10],
        "active_interventions": active_interventions[:10],
    }


def suggest_actions(context: dict[str, Any]) -> list[dict[str, str]]:
    counts = context["counts"]
    actions: list[dict[str, str]] = []

    if counts["zones_pollution_critique"] > 0:
        actions.append(
            {
                "priorite": "haute",
                "categorie": "pollution",
                "action": "Declencher une intervention terrain dans les zones avec moyenne pollution >= 100 AQI.",
            }
        )
    elif counts["zones_pollution_surveillance"] > 0:
        actions.append(
            {
                "priorite": "moyenne",
                "categorie": "pollution",
                "action": "Surveiller les zones entre 80 et 100 AQI et verifier la calibration des capteurs.",
            }
        )

    if counts["capteurs_hors_service"] > 0:
        actions.append(
            {
                "priorite": "haute",
                "categorie": "capteurs",
                "action": "Planifier une maintenance corrective pour les capteurs hors service.",
            }
        )

    if counts["capteurs_signales"] > 0:
        actions.append(
            {
                "priorite": "moyenne",
                "categorie": "capteurs",
                "action": "Qualifier les anomalies signalees et ouvrir les demandes d'intervention necessaires.",
            }
        )

    if counts["mesures_sans_valeur"] > 0:
        actions.append(
            {
                "priorite": "moyenne",
                "categorie": "donnees",
                "action": "Controler les flux de mesures sans valeur et relancer les capteurs concernes.",
            }
        )

    if counts["interventions_ouvertes"] > 0:
        actions.append(
            {
                "priorite": "basse",
                "categorie": "interventions",
                "action": "Suivre les interventions ouvertes jusqu'a validation technique et IA.",
            }
        )

    if not actions:
        actions.append(
            {
                "priorite": "basse",
                "categorie": "exploitation",
                "action": "Maintenir la surveillance normale; aucune anomalie prioritaire detectee.",
            }
        )

    return actions


def generate_local_report(context: dict[str, Any], actions: list[dict[str, str]]) -> str:
    counts = context["counts"]
    top_zones = context["top_polluted_zones"]
    generated_at = context["generated_at"].replace("T", " ")

    lines = [
        f"Rapport Smart City genere le {generated_at}.",
        (
            "Synthese: "
            f"{counts['capteurs']} capteurs suivis, "
            f"{counts['capteurs_hors_service']} hors service, "
            f"{counts['capteurs_signales']} signales, "
            f"{counts['interventions_ouvertes']} interventions ouvertes."
        ),
    ]

    if top_zones:
        zone_fragments = []
        for row in top_zones[:3]:
            value = _safe_float(row.get("moyenne_pollution"))
            rendered_value = "n/a" if value is None else f"{value:.1f}"
            zone_fragments.append(f"{row.get('localisation', 'zone inconnue')} ({rendered_value} AQI)")
        lines.append("Qualite de l'air: zones les plus exposees: " + ", ".join(zone_fragments) + ".")
    else:
        lines.append("Qualite de l'air: aucune mesure de pollution exploitable disponible.")

    if counts["mesures_sans_valeur"]:
        lines.append(
            f"Donnees: {counts['mesures_sans_valeur']} capteurs ont une mesure courante sans valeur."
        )

    lines.append("Actions recommandees:")
    for index, action in enumerate(actions, start=1):
        lines.append(
            f"{index}. [{action['priorite']}] {action['categorie']}: {action['action']}"
        )

    return "\n".join(lines)


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL du fournisseur IA invalide: scheme non autorise.")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def generate_remote_report(
    context: dict[str, Any],
    actions: list[dict[str, str]],
    config: AIProviderConfig,
) -> str:
    if not config.enabled:
        raise ValueError("Configuration IA incomplete.")

    prompt = {
        "context": context,
        "actions_recommandees": actions,
        "instruction": "Produis un rapport en francais de 8 a 12 lignes avec actions prioritaires.",
    }
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, default=str)},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        _chat_completions_url(config.base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        body = json.loads(response.read().decode("utf-8"))
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Reponse IA invalide.") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Reponse IA vide.")
    return content.strip()


def generate_ai_report(
    context: dict[str, Any],
    config: AIProviderConfig | None = None,
) -> dict[str, Any]:
    actions = suggest_actions(context)
    provider = config or AIProviderConfig.from_env()
    started_at = time.perf_counter()
    source = "local"
    error = ""

    try:
        report = generate_remote_report(context, actions, provider)
        source = provider.model
    except (ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
        report = generate_local_report(context, actions)
        if provider.enabled:
            error = str(exc)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "report": report,
        "actions": actions,
        "source": source,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }
