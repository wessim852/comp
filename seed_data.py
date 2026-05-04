from __future__ import annotations

import random
from datetime import datetime, timedelta


CAPTEUR_TYPES = ["pollution", "temperature", "humidite", "bruit"]
CAPTEUR_STATES = ["inactif", "actif", "signale", "en maintenance", "hors service"]
VEHICLE_STATES = ["stationne", "en route", "en panne", "arrive"]
INTERVENTION_STATES = ["demande", "en_cours", "terminee"]
LOCATIONS = [
    "Centre Ville Tunis",
    "Lac 1 Tunis",
    "Sousse Corniche",
    "Sfax Medina",
    "Monastir Centre",
    "Nabeul Plage",
    "Ariana Centre",
    "Bizerte Port",
]
LAST_NAMES = ["Ben Salem", "Trabelsi", "Mansouri", "Jaziri", "Gharbi", "Mejri"]
FIRST_NAMES = ["Amine", "Sarra", "Youssef", "Meriem", "Khalil", "Nour"]
ADDRESSES = ["Tunis", "Sousse", "Sfax", "Nabeul", "Monastir", "Ariana"]
VEHICLE_MODELS = [
    "Renault Kangoo",
    "Peugeot Partner",
    "Citroen Berlingo",
    "Fiat Doblo",
    "Toyota Proace",
]

REFERENCE_CITIZENS = [
    ("Ben Salem", "Amine", "Tunis", "20112233"),
    ("Trabelsi", "Sarra", "Sousse", "22114455"),
    ("Mansouri", "Youssef", "Sfax", "24112233"),
    ("Jaziri", "Meriem", "Nabeul", "28110022"),
    ("Gharbi", "Khalil", "Monastir", "29113344"),
]

REFERENCE_VEHICLES = [
    ("TU-2401", "Renault Kangoo", "stationne", "2022-03-15"),
    ("TU-2402", "Peugeot Partner", "en route", "2021-09-10"),
    ("TU-2403", "Citroen Berlingo", "arrive", "2023-01-20"),
    ("TU-2404", "Fiat Doblo", "en panne", "2020-07-05"),
]

REFERENCE_MEASURES = [
    (78.4, "AQI", "pollution", "2026-04-23 08:00:00"),
    (26.1, "C", "temperature", "2026-04-23 08:00:00"),
    (63.5, "%", "humidite", "2026-04-23 08:00:00"),
    (72.8, "dB", "bruit", "2026-04-23 08:00:00"),
    (None, "AQI", "pollution", "2026-04-23 09:30:00"),
    (54.7, "AQI", "pollution", "2026-04-23 10:00:00"),
]


def sensor_measure_profile(sensor_type: str) -> tuple[str, float, float]:
    profiles = {
        "pollution": ("AQI", 35.0, 120.0),
        "temperature": ("C", 14.0, 39.0),
        "humidite": ("%", 35.0, 92.0),
        "bruit": ("dB", 38.0, 95.0),
    }
    return profiles.get(sensor_type, ("unite", 0.0, 100.0))


def _token() -> int:
    return random.randint(100000, 999999)


def generate_citizen_rows(count: int) -> list[tuple[str, str, str, str]]:
    return [
        (
            random.choice(LAST_NAMES),
            random.choice(FIRST_NAMES),
            random.choice(ADDRESSES),
            f"{random.randint(20_000_000, 29_999_999)}",
        )
        for _ in range(count)
    ]


def generate_vehicle_rows(count: int) -> list[tuple[str, str, str, str]]:
    now = datetime.now()
    return [
        (
            f"TU-{now.strftime('%H%M%S')}-{index}-{_token()}",
            random.choice(VEHICLE_MODELS),
            random.choice(VEHICLE_STATES),
            (now - timedelta(days=random.randint(30, 2500))).date().isoformat(),
        )
        for index in range(count)
    ]


def generate_single_measure_row(
    sensor_type: str | None = None,
    sensor_state: str | None = None,
) -> tuple[float | None, str, str, datetime]:
    resolved_type = sensor_type or random.choice(CAPTEUR_TYPES)
    unit, low, high = sensor_measure_profile(resolved_type)
    timestamp = datetime.now().replace(second=0, microsecond=0) - timedelta(
        minutes=random.randint(0, 180)
    )
    if sensor_state == "hors service":
        return (None, unit, resolved_type, timestamp)
    return (round(random.uniform(low, high), 2), unit, resolved_type, timestamp)


def generate_live_measure_row(
    sensor_type: str,
    sensor_state: str,
    current_value: float | None = None,
    timestamp: datetime | None = None,
) -> tuple[float | None, str, str, datetime]:
    resolved_timestamp = (timestamp or datetime.now()).replace(second=0, microsecond=0)
    unit, low, high = sensor_measure_profile(sensor_type)

    if sensor_state == "hors service":
        return (None, unit, sensor_type, resolved_timestamp)

    baseline = random.uniform(low, high) if current_value is None else float(current_value)
    if sensor_type == "pollution":
        variation = random.uniform(-8.0, 8.0)
        if 7 <= resolved_timestamp.hour <= 9 or 17 <= resolved_timestamp.hour <= 20:
            variation += random.uniform(8.0, 18.0)
        upper_bound = high + 40.0
    elif sensor_type == "temperature":
        variation = random.uniform(-2.5, 2.5)
        if 11 <= resolved_timestamp.hour <= 16:
            variation += random.uniform(1.0, 3.0)
        elif 0 <= resolved_timestamp.hour <= 5:
            variation -= random.uniform(1.0, 2.5)
        upper_bound = high
    elif sensor_type == "humidite":
        variation = random.uniform(-6.0, 6.0)
        upper_bound = high
    elif sensor_type == "bruit":
        variation = random.uniform(-5.0, 5.0)
        if 8 <= resolved_timestamp.hour <= 18:
            variation += random.uniform(3.0, 8.0)
        upper_bound = high
    else:
        variation = random.uniform(-4.0, 4.0)
        upper_bound = high

    value = max(low, min(upper_bound, baseline + variation))
    return (round(value, 2), unit, sensor_type, resolved_timestamp)


def generate_standalone_measure_rows(
    count: int,
) -> list[tuple[float | None, str, str, datetime]]:
    return [generate_single_measure_row() for _ in range(count)]


def generate_capteur_rows(
    measure_ids: list[int],
) -> list[tuple[str, str, str, str, int]]:
    now = datetime.now()
    return [
        (
            random.choice(CAPTEUR_TYPES),
            random.choice(LOCATIONS),
            (now - timedelta(days=random.randint(1, 900))).date().isoformat(),
            random.choice(CAPTEUR_STATES),
            measure_id,
        )
        for measure_id in measure_ids
    ]


def generate_measure_and_capteur_rows(
    count: int,
) -> tuple[
    list[tuple[float | None, str, str, datetime]],
    list[tuple[str, str, str, str]],
]:
    measure_rows: list[tuple[float | None, str, str, datetime]] = []
    sensor_rows_without_measure_id: list[tuple[str, str, str, str]] = []
    now = datetime.now()

    for _ in range(count):
        sensor_type = random.choice(CAPTEUR_TYPES)
        sensor_state = random.choice(CAPTEUR_STATES)
        measure_rows.append(generate_single_measure_row(sensor_type, sensor_state))
        sensor_rows_without_measure_id.append(
            (
                sensor_type,
                random.choice(LOCATIONS),
                (now - timedelta(days=random.randint(1, 900))).date().isoformat(),
                sensor_state,
            )
        )

    return measure_rows, sensor_rows_without_measure_id


def attach_measure_ids_to_capteurs(
    sensor_rows_without_measure_id: list[tuple[str, str, str, str]],
    measure_ids: list[int],
) -> list[tuple[str, str, str, str, int]]:
    return [
        (*sensor_row, measure_id)
        for sensor_row, measure_id in zip(sensor_rows_without_measure_id, measure_ids)
    ]


def generate_intervention_rows(
    capteur_ids: list[int],
    count: int,
) -> list[tuple[datetime, datetime | None, datetime | None, str, int]]:
    now = datetime.now().replace(second=0, microsecond=0)
    rows: list[tuple[datetime, datetime | None, datetime | None, str, int]] = []
    for _ in range(count):
        status = random.choice(INTERVENTION_STATES)
        date_demande = now - timedelta(days=random.randint(0, 30), hours=random.randint(0, 12))
        date_debut = None
        date_fin = None
        if status in {"en_cours", "terminee"}:
            date_debut = date_demande + timedelta(hours=random.randint(1, 4))
        if status == "terminee" and date_debut is not None:
            date_fin = date_debut + timedelta(hours=random.randint(1, 8))
        rows.append((date_demande, date_debut, date_fin, status, random.choice(capteur_ids)))
    return rows


def generate_measure_rows(
    sensor_records: list[tuple[int, str, str]],
    per_sensor: int,
    step_minutes: int,
) -> tuple[list[tuple[float, str, str, datetime]], list[tuple[int, int]]]:
    rows: list[tuple[float, str, str, datetime]] = []
    current_links: list[tuple[int, int]] = []
    now = datetime.now().replace(second=0, microsecond=0)

    for sensor_id, sensor_type, sensor_state in sensor_records:
        if sensor_state == "hors service":
            continue
        unit, low, high = sensor_measure_profile(sensor_type)
        anchor = random.uniform(low, high)
        last_generated_index = -1
        for offset in range(per_sensor):
            timestamp = now - timedelta(minutes=offset * step_minutes)
            drift = random.uniform(-6.0, 6.0)
            if sensor_type == "pollution":
                hour_boost = 18 if 7 <= timestamp.hour <= 9 or 17 <= timestamp.hour <= 20 else 0
                value = max(low, min(high + 40, anchor + drift + hour_boost))
            elif sensor_type == "temperature":
                daytime = 8 if 11 <= timestamp.hour <= 16 else -3
                value = max(low, min(high, anchor + drift + daytime))
            elif sensor_type == "humidite":
                value = max(low, min(high, anchor + drift + random.uniform(3.0, 10.0)))
            elif sensor_type == "bruit":
                rush = 10 if 8 <= timestamp.hour <= 18 else -8
                value = max(low, min(high, anchor + drift + rush))
            else:
                value = max(low, min(high, anchor + drift))
            rows.append((round(value, 2), unit, sensor_type, timestamp))
            if offset == 0:
                last_generated_index = len(rows) - 1
        if last_generated_index >= 0:
            current_links.append((sensor_id, last_generated_index))
    return rows, current_links
