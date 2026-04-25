from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isnan
from typing import Any


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_accents.replace("_", " ").replace("-", " ").split())


@dataclass(frozen=True)
class TransitionRecord:
    event: str
    normalized_event: str
    from_state: str
    to_state: str


@dataclass(frozen=True)
class ValidationResult:
    entity_type: str
    initial_state: str
    current_state: str
    valid: bool
    history: list[TransitionRecord]
    errors: list[str]


@dataclass(frozen=True)
class Automaton:
    entity_type: str
    initial_state: str
    states: frozenset[str]
    transitions: dict[tuple[str, str], str]
    aliases: dict[str, str]

    def normalize_state(self, state: str) -> str:
        key = normalize_label(state)
        resolved = self.aliases.get(key, key)
        if resolved not in self.states:
            raise ValueError(f"Etat inconnu pour {self.entity_type}: {state}")
        return resolved

    def normalize_event(self, event: str) -> str:
        key = normalize_label(event)
        return self.aliases.get(key, key)


CAPTEUR = Automaton(
    entity_type="capteur",
    initial_state="inactif",
    states=frozenset({"inactif", "actif", "signale", "en maintenance", "hors service"}),
    transitions={
        ("inactif", "installation"): "actif",
        ("actif", "detection anomalie"): "signale",
        ("actif", "panne"): "hors service",
        ("signale", "reparation"): "en maintenance",
        ("signale", "panne"): "hors service",
        ("en maintenance", "reparation"): "actif",
        ("en maintenance", "panne"): "hors service",
    },
    aliases={
        "incatif": "inactif",
        "inactive": "inactif",
        "hors service": "hors service",
        "horsservice": "hors service",
        "en maintenance": "en maintenance",
        "maintenance": "en maintenance",
        "signale": "signale",
        "signalee": "signale",
        "detection d'anomalie": "detection anomalie",
        "detection anomalie": "detection anomalie",
        "detecter anomalie": "detection anomalie",
        "anomalie": "detection anomalie",
        "reparer": "reparation",
        "repare": "reparation",
    },
)

INTERVENTION = Automaton(
    entity_type="intervention",
    initial_state="demande",
    states=frozenset(
        {"demande", "tech1 assigne", "tech2 valide", "ia valide", "termine"}
    ),
    transitions={
        ("demande", "assigner tech1"): "tech1 assigne",
        ("tech1 assigne", "valider tech2"): "tech2 valide",
        ("tech2 valide", "valider ia"): "ia valide",
        ("ia valide", "cloturer"): "termine",
    },
    aliases={
        "demandee": "demande",
        "tech1 assigne": "tech1 assigne",
        "technicien 1 assigne": "tech1 assigne",
        "tech2 valide": "tech2 valide",
        "technicien 2 valide": "tech2 valide",
        "ia valide": "ia valide",
        "terminee": "termine",
        "termine": "termine",
        "assigner tech1": "assigner tech1",
        "assigner technicien 1": "assigner tech1",
        "assigner tech 1": "assigner tech1",
        "valider tech2": "valider tech2",
        "valider technicien 2": "valider tech2",
        "valider tech 2": "valider tech2",
        "valider ia": "valider ia",
        "cloture": "cloturer",
        "cloturer": "cloturer",
    },
)

VEHICULE = Automaton(
    entity_type="vehicule",
    initial_state="stationne",
    states=frozenset({"stationne", "en route", "en panne", "arrive"}),
    transitions={
        ("stationne", "demarre"): "en route",
        ("en route", "panne"): "en panne",
        ("en panne", "reparer"): "en route",
        ("en route", "arrive"): "arrive",
        ("arrive", "stationne"): "stationne",
    },
    aliases={
        "stationnee": "stationne",
        "en route": "en route",
        "en panne": "en panne",
        "arrivee": "arrive",
        "demarrer": "demarre",
        "demarre": "demarre",
        "demare": "demarre",
        "reparation": "reparer",
        "repare": "reparer",
        "arriver": "arrive",
        "arrive": "arrive",
        "stationner": "stationne",
    },
)

AUTOMATA = {
    "capteur": CAPTEUR,
    "intervention": INTERVENTION,
    "vehicule": VEHICULE,
}


def get_automaton(entity_type: str) -> Automaton:
    key = normalize_label(entity_type)
    if key not in AUTOMATA:
        raise ValueError(f"Automate inconnu: {entity_type}")
    return AUTOMATA[key]


def validate_sequence(
    entity_type: str,
    events: list[str],
    initial_state: str | None = None,
) -> ValidationResult:
    automaton = get_automaton(entity_type)
    state = (
        automaton.normalize_state(initial_state)
        if initial_state is not None
        else automaton.initial_state
    )
    history: list[TransitionRecord] = []
    errors: list[str] = []

    for index, event in enumerate(events, start=1):
        normalized_event = automaton.normalize_event(event)
        next_state = automaton.transitions.get((state, normalized_event))
        if next_state is None:
            errors.append(
                f"Transition invalide #{index}: etat '{state}' + evenement '{event}'"
            )
            break
        history.append(
            TransitionRecord(
                event=event,
                normalized_event=normalized_event,
                from_state=state,
                to_state=next_state,
            )
        )
        state = next_state

    return ValidationResult(
        entity_type=automaton.entity_type,
        initial_state=automaton.normalize_state(initial_state)
        if initial_state is not None
        else automaton.initial_state,
        current_state=state,
        valid=not errors,
        history=history,
        errors=errors,
    )


def current_state(
    entity_type: str,
    events: list[str],
    initial_state: str | None = None,
) -> str:
    result = validate_sequence(entity_type, events, initial_state)
    if not result.valid:
        raise ValueError(result.errors[0])
    return result.current_state


def evaluate_actions(
    entity_type: str,
    state: str,
    entered_at: datetime,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    automaton = get_automaton(entity_type)
    normalized_state = automaton.normalize_state(state)
    reference_time = now or datetime.now()
    actions: list[dict[str, str]] = []

    if (
        automaton.entity_type == "capteur"
        and normalized_state == "hors service"
        and reference_time - entered_at > timedelta(hours=24)
    ):
        actions.append(
            {
                "type": "alert",
                "code": "capteur_hors_service_24h",
                "message": "Alerte: capteur hors service depuis plus de 24h",
                "state": normalized_state,
            }
        )

    return actions


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return isnan(value)
    return False


def detect_sensor_value_alerts(
    records: list[Mapping[str, Any]],
    now: datetime | None = None,
    threshold: timedelta = timedelta(minutes=1),
) -> list[dict[str, Any]]:
    reference_time = now or datetime.now()
    alerts: list[dict[str, Any]] = []

    for record in records:
        timestamp = _coerce_datetime(record.get("horodatage"))
        if timestamp is None:
            continue

        elapsed = reference_time - timestamp
        sensor_state = normalize_label(str(record.get("etat_capteur", "")))
        has_no_value = _is_missing_value(record.get("valeur"))
        is_off_service = sensor_state == "hors service"

        if elapsed > threshold and (is_off_service or has_no_value):
            minutes_without_value = round(elapsed.total_seconds() / 60, 2)
            alerts.append(
                {
                    "type": "alert",
                    "code": "capteur_sans_valeur_1min",
                    "id_capteur": record.get("id_capteur"),
                    "id_mesure": record.get("id_mesure"),
                    "etat_capteur": record.get("etat_capteur"),
                    "horodatage": timestamp,
                    "minutes_sans_valeur": minutes_without_value,
                    "message": (
                        "Alerte: capteur sans valeur depuis plus de 1 minute"
                    ),
                }
            )

    return alerts


def available_events(entity_type: str, state: str | None = None) -> list[str]:
    automaton = get_automaton(entity_type)
    if state is None:
        return sorted({event for _, event in automaton.transitions})
    normalized_state = automaton.normalize_state(state)
    return sorted(
        event
        for from_state, event in automaton.transitions
        if from_state == normalized_state
    )
