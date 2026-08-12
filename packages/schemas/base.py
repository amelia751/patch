"""Base models every PatchAPI contract derives from."""

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from packages.schemas.config import contract_version


class StrictModel(BaseModel):
    """Rejects unknown fields and freezes instances after validation.

    Contracts cross a trust boundary: an unexpected key is a signal that a
    producer and a consumer disagree, so it is an error rather than something
    to carry along silently. Freezing keeps a validated contract from drifting
    between the agent that produced it and the agent that grades it.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        use_enum_values=False,
        validate_default=True,
    )


class VersionedContract(StrictModel):
    """A top-level agent I/O object carrying its pinned schema version.

    Producers omit `schema_version` and get the pinned value from
    `packages.schemas.config`; consumers that read a document written by an
    older build get a `ValidationError` instead of a silent misparse.
    """

    CONTRACT_NAME: ClassVar[str]

    schema_version: str

    @model_validator(mode="before")
    @classmethod
    def _pin_schema_version(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        pinned = contract_version(cls.CONTRACT_NAME)
        supplied = data.get("schema_version")
        if supplied is None:
            return {**data, "schema_version": pinned}
        if supplied != pinned:
            raise ValueError(
                f"{cls.CONTRACT_NAME} is pinned at schema_version {pinned!r}, got {supplied!r}"
            )
        return data
