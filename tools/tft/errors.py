"""Every failure the tool reports, one class per cause."""


class TftError(Exception):
    """Base for anything this tool raises."""


class ConfigError(TftError):
    """tft.toml is unreadable or malformed."""


class SchemaError(TftError):
    """An entry.yaml violates the schema."""


class MissingField(SchemaError):
    """A mandatory field is absent."""


class UnknownField(SchemaError):
    """A field not in the schema is present, usually a typo."""


class BadValue(SchemaError):
    """A field is present but its value is of the wrong type or domain."""


class UnknownTopic(SchemaError):
    """A topic is not listed in taxonomy/topics.yaml."""


class OverleafError(TftError):
    """Cloning or pulling the Overleaf project failed."""


class CompileError(TftError):
    """The document could not be compiled."""


class ExtractError(TftError):
    """A thesis's metadata could not be read from its LaTeX source."""


class UnsafeOutputDir(TftError):
    """--out names a directory that is not a previous build."""


class RegistryError(TftError):
    """A DOI lookup failed: malformed DOI, unknown to both registries, or the network."""
