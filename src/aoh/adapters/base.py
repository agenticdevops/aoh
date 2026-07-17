from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from aoh.pack import Binding, Pack


@dataclass(frozen=True)
class MaterializeRequest:
    pack: Pack
    output_dir: Path
    role_name: str | None = None
    binding: Binding | None = None
    profile: str | None = None
    model_hint: str | None = None
    workdir: str | None = None
    options: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterResult:
    runtime: str
    output_dir: Path
    generated_files: list[Path]
    diagnostics: list[str] = field(default_factory=list)
    artifact_map: dict[str, str] = field(default_factory=dict)
    transform_id: str = "identity-v1"


class RuntimeAdapter(Protocol):
    name: str

    def materialize(self, request: MaterializeRequest) -> AdapterResult: ...


ADAPTERS: dict[str, RuntimeAdapter] = {}
