from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ArtifactReference:
    """Portable reference exchanged by services; never an ORM object or binary."""
    artifact_id: str
    artifact_type: str
    uri: str
    checksum: str = ""
    schema_version: str = "1.0"
    metadata: dict = field(default_factory=dict)

    def payload(self):
        return asdict(self)
