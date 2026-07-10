from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum

from app.models import Language, VideoGender, VideoType


DEFAULT_BATCH_SIZE = 6
MAX_BATCH_SIZE = 24
MAX_SCHEDULE_TIMES = 12
TOOLS_TOKEN = "tools"

# Dos vueltas completas por los tipos 1, 2 y 3; despues entra un video de
# herramientas y la secuencia vuelve a empezar.
ROTATION: tuple[str, ...] = ("1", "2", "3", "1", "2", "3", TOOLS_TOKEN)


class BatchItemKind(str, Enum):
    GENERATED = "generated"
    TOOLS = "tools"


@dataclass(frozen=True)
class BatchLane:
    language: Language
    gender: VideoGender
    initial_rotation_index: int


@dataclass(frozen=True)
class BatchItem:
    position: int
    kind: BatchItemKind
    language: Language
    gender: VideoGender
    video_type: VideoType | None = None

    @property
    def short_label(self) -> str:
        if self.kind == BatchItemKind.TOOLS:
            return f"herramientas {self.language.value.upper()}"
        gender = "mujer" if self.gender == VideoGender.FEMALE else "hombre"
        return (
            f"tipo {self.video_type.value} {self.language.value.upper()} "
            f"({gender})"
        )


# El primer lote reproduce exactamente el orden pedido. En los siguientes
# lotes cada posicion avanza de forma independiente por ROTATION.
DEFAULT_LANES: tuple[BatchLane, ...] = (
    BatchLane(Language.ES, VideoGender.MALE, 0),  # tipo 1 ES
    BatchLane(Language.ES, VideoGender.MALE, 1),  # tipo 2 ES
    BatchLane(Language.EN, VideoGender.MALE, 2),  # tipo 3 EN
    BatchLane(Language.ES, VideoGender.MALE, 6),  # herramientas ES
    BatchLane(Language.EN, VideoGender.MALE, 0),  # tipo 1 EN
    BatchLane(Language.ES, VideoGender.FEMALE, 1),  # mujer tipo 2 ES
)


def build_batch_plan(count: int, phase: int) -> list[BatchItem]:
    if count < 1 or count > MAX_BATCH_SIZE:
        raise ValueError(
            f"La cantidad debe estar entre 1 y {MAX_BATCH_SIZE} videos."
        )
    normalized_phase = max(0, int(phase)) % len(ROTATION)
    plan: list[BatchItem] = []
    for index in range(count):
        lane = DEFAULT_LANES[index % len(DEFAULT_LANES)]
        token = ROTATION[
            (lane.initial_rotation_index + normalized_phase) % len(ROTATION)
        ]
        if token == TOOLS_TOKEN:
            plan.append(
                BatchItem(
                    position=index + 1,
                    kind=BatchItemKind.TOOLS,
                    language=lane.language,
                    gender=lane.gender,
                )
            )
            continue
        plan.append(
            BatchItem(
                position=index + 1,
                kind=BatchItemKind.GENERATED,
                language=lane.language,
                gender=lane.gender,
                video_type=VideoType(token),
            )
        )
    return plan


def normalize_schedule_time(raw_value: str) -> str:
    pieces = str(raw_value or "").strip().split(":")
    if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
        raise ValueError(f"Hora no valida: {raw_value}. Usa HH:MM, por ejemplo 08:00.")
    hour, minute = (int(piece) for piece in pieces)
    if hour not in range(24) or minute not in range(60):
        raise ValueError(f"Hora no valida: {raw_value}. Usa HH:MM, por ejemplo 08:00.")
    return f"{hour:02d}:{minute:02d}"


def parse_schedule_values(
    raw_values: list[str],
    *,
    default_count: int = DEFAULT_BATCH_SIZE,
) -> tuple[int, list[str]]:
    values = [str(value).strip() for value in raw_values if str(value).strip()]
    if not values:
        raise ValueError("Faltan las horas de la programacion.")

    count = default_count
    if values[0].isdigit() and ":" not in values[0]:
        count = int(values.pop(0))
    if count < 1 or count > MAX_BATCH_SIZE:
        raise ValueError(
            f"La cantidad debe estar entre 1 y {MAX_BATCH_SIZE} videos."
        )
    if not values:
        raise ValueError("Faltan las horas. Ejemplo: /schedule 6 08:00 18:00")

    normalized: list[str] = []
    for raw_value in values:
        schedule_time = normalize_schedule_time(raw_value)
        if schedule_time not in normalized:
            normalized.append(schedule_time)
    if len(normalized) > MAX_SCHEDULE_TIMES:
        raise ValueError(
            f"Puedes configurar como maximo {MAX_SCHEDULE_TIMES} horas al dia."
        )
    return count, sorted(normalized)


def schedule_time_to_datetime_time(raw_value: str, tzinfo) -> time:
    normalized = normalize_schedule_time(raw_value)
    hour, minute = (int(piece) for piece in normalized.split(":"))
    return time(hour=hour, minute=minute, tzinfo=tzinfo)
