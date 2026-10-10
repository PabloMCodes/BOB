"""Worksite profile: an immutable, hashed revision of the PPE requirement checkboxes (plan §4)."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from .common import APP_VERSION, REQUIREMENT_RULES, AppVersion, PosInt, Requirement, Sha256, _Model

class WorksiteProfile(_Model):
    """Immutable revision of a worksite's PPE requirements. `sha256` covers every other field."""
    app_version: AppVersion
    msg_type: Literal["worksite_profile"]
    worksite_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    revision: PosInt
    name: str = Field(min_length=1, max_length=200)
    requirements: dict[Requirement, bool]
    sha256: Sha256

    @staticmethod
    def content_sha256(worksite_id: str, revision: int, name: str, requirements: dict[str, bool]) -> str:
        canonical = json.dumps({"worksite_id": worksite_id, "revision": revision, "name": name,
                                "requirements": requirements}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def build(cls, worksite_id: str, revision: int, name: str, requirements: dict[str, bool]) -> WorksiteProfile:
        return cls(app_version=APP_VERSION, msg_type="worksite_profile", worksite_id=worksite_id,
                   revision=revision, name=name, requirements=requirements,
                   sha256=cls.content_sha256(worksite_id, revision, name, requirements))

    @model_validator(mode="after")
    def _hash(self) -> WorksiteProfile:
        if sorted(self.requirements) != sorted(REQUIREMENT_RULES):
            raise ValueError("requirements must list every requirement exactly once")
        if self.sha256 != self.content_sha256(self.worksite_id, self.revision, self.name, dict(self.requirements)):
            raise ValueError("sha256 does not match the profile content")
        return self
