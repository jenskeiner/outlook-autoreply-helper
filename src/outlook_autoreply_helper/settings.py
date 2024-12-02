import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from msal import SerializableTokenCache
from msal_extensions import (
    PersistedTokenCache,
    FilePersistenceWithDataProtection,
    FilePersistence,
)
from pydantic import BaseModel, Field, AliasChoices
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
    AzureKeyVaultSettingsSource,
)

log = logging.getLogger(__name__)


class TimeZoneCache(BaseModel):
    """
    Cache for mapping a Windows time zone to an IANA time zone.
    """

    windows_tz: str
    iana_tz: str


class AbstractCacheSettings(ABC, BaseModel):
    """
    Abstract base class for cache-related settings.

    Defines an interface for token/timezone cache management with methods for retrieving and storing.
    """

    @abstractmethod
    def get_token_cache(self) -> SerializableTokenCache:
        """Retrieve a token cache."""
        pass

    @abstractmethod
    def put_token_cache(self, token_cache: SerializableTokenCache) -> None:
        """Store a token cache."""
        pass

    @abstractmethod
    def get_tz_cache(self) -> TimeZoneCache | None:
        """Retrieve a token cache."""
        pass

    @abstractmethod
    def put_tz_cache(self, tz_cache: TimeZoneCache) -> None:
        """Store a token cache."""
        pass


class LocalCacheSettings(AbstractCacheSettings):
    """
    Local file-based token cache settings with optional encryption.

    Supports storing tokens in a local file, with the option to use
    data protection for enhanced security.
    """

    type: Literal["local"] = "local"
    token_cache_file: Path = Field(
        default=Path("token_cache.bin"),
        validation_alias=AliasChoices("token_cache_file", "token-cache-file"),
    )
    fallback_to_plaintext: bool = Field(
        default=True,
        validation_alias=AliasChoices("fallback_to_plaintext", "fallback-to-plaintext"),
    )
    tz_cache_file: Path = Field(
        default=Path("tz_cache.json"),
        validation_alias=AliasChoices("tz_cache_file", "tz-cache-file"),
    )

    def get_token_cache(self) -> SerializableTokenCache:
        """
        Create a persistent token cache with optional encryption.

        Falls back to plaintext storage if encryption is unavailable.
        """
        try:
            persistence = FilePersistenceWithDataProtection(self.token_cache_file)
        except Exception as e:
            if not self.fallback_to_plaintext:
                raise RuntimeError(
                    "Failed to initialize token cache with encryption."
                ) from e
            log.warning("Encryption unavailable. Falling back to plaintext: %s", str(e))
            persistence = FilePersistence(self.token_cache_file)

        log.info("Using persistence type: %s", persistence.__class__.__name__)
        log.info("Persistence encryption status: %s", persistence.is_encrypted)

        return PersistedTokenCache(persistence)

    def put_token_cache(self, token_cache: SerializableTokenCache) -> None:
        """
        No-op method for local cache storage.

        The token cache is automatically persisted by the cache implementation.
        """
        pass

    def get_tz_cache(self) -> TimeZoneCache | None:
        """
        Retrieve a time zone cache from a local file.
        """
        try:
            if not self.tz_cache_file.exists():
                return None
            with open(self.tz_cache_file) as f:
                return TimeZoneCache.model_validate_json(f.read())
        except Exception as e:
            raise RuntimeError("Failed to read time zone cache.") from e

    def put_tz_cache(self, tz_cache: TimeZoneCache) -> None:
        """
        Store a time zone cache in a local file.
        """
        with open(self.tz_cache_file, "w") as f:
            f.write(tz_cache.model_dump_json())


class KeyVaultCacheSettings(AbstractCacheSettings):
    """
    Azure Key Vault-based token cache settings.

    Manages token caching using Azure Key Vault for secure storage and retrieval.
    """

    type: Literal["keyvault"] = "keyvault"
    key_vault_url: str = Field(
        validation_alias=AliasChoices("key_vault_url", "key-vault-url")
    )
    token_cache_secret_name: str = Field(
        default="token-cache",
        validation_alias=AliasChoices(
            "token_cache_secret_name", "token-cache-secret-name"
        ),
    )
    tz_cache_secret_name: str = Field(
        default="tz-cache",
        validation_alias=AliasChoices("tz_cache_secret_name", "tz-cache-secret-name"),
    )

    def get_token_cache(self) -> SerializableTokenCache:
        """
        Retrieve or create a token cache from Azure Key Vault.

        Creates a new cache if no existing cache is found.
        """
        credential = DefaultAzureCredential()
        secret_client = SecretClient(
            vault_url=self.key_vault_url, credential=credential
        )

        # Initialize empty cache.
        cache = SerializableTokenCache()

        try:
            secret = secret_client.get_secret(self.token_cache_secret_name)
        except ResourceNotFoundError:
            # Return empty cache.
            return cache

        # Deserialize cache from secret value.
        try:
            cache.deserialize(secret.value)
        except Exception as e:
            raise RuntimeError("Failed to deserialize token cache from secret.") from e

        return cache

    def put_token_cache(self, token_cache: SerializableTokenCache) -> None:
        """
        Store the token cache in Azure Key Vault.

        Args:
            token_cache: The token cache to be serialized and stored
        """
        credential = DefaultAzureCredential()
        secret_client = SecretClient(
            vault_url=self.key_vault_url, credential=credential
        )
        secret_client.set_secret(self.token_cache_secret_name, token_cache.serialize())

    def get_tz_cache(self) -> TimeZoneCache | None:
        """
        Retrieve a time zone cache from Azure Key Vault.
        """
        credential = DefaultAzureCredential()
        secret_client = SecretClient(
            vault_url=self.key_vault_url, credential=credential
        )

        try:
            secret = secret_client.get_secret(self.tz_cache_secret_name)
        except ResourceNotFoundError:
            return None

        print(f"secret.value: {secret.value}")

        try:
            return TimeZoneCache.model_validate_json(secret.value)
        except Exception as e:
            raise RuntimeError("Failed to read time zone cache.") from e

    def put_tz_cache(self, tz_cache: TimeZoneCache) -> None:
        """
        Store a time zone cache in Azure Key Vault.
        """
        credential = DefaultAzureCredential()
        secret_client = SecretClient(
            vault_url=self.key_vault_url, credential=credential
        )
        secret_client.set_secret(self.tz_cache_secret_name, tz_cache.model_dump_json())


class AppRegistrationSettings(BaseModel):
    """
    Azure AD application registration settings for authentication.

    Configures client ID and tenant ID for access to the Microsoft Graph API. Optionally, can override the default
    scopes, base URL, and authentication flow to use when no access token is available from a cache.
    """

    tenant_id: str = Field(validation_alias=AliasChoices("tenant_id", "tenant-id"))
    client_id: str = Field(validation_alias=AliasChoices("client_id", "client-id"))
    scopes: list[str] = [
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "https://graph.microsoft.com/MailboxSettings.ReadWrite",
    ]
    base_url: str = Field(
        default="https://graph.microsoft.com/v1.0",
        validation_alias=AliasChoices("base_url", "base-url"),
    )
    auth_flow: Literal["interactive", "device_code"] = Field(
        default="interactive", validation_alias=AliasChoices("auth_flow", "auth-flow")
    )


class AbstractTemplateSource(BaseModel, ABC):
    @abstractmethod
    def get_template(self) -> str:
        """Return template content."""
        pass


class LocalTemplateSource(AbstractTemplateSource):
    """
    Local file-based template source for absence reply messages.

    Reads template content from a local file path.
    """

    type: Literal["local"] = "local"
    path: Path

    def get_template(self) -> str:
        """Read and return template content from file."""
        return self.path.read_text()


class StringTemplateSource(AbstractTemplateSource):
    """
    String-based template source for absence reply messages.

    Allows direct specification of template content.
    """

    type: Literal["string"] = "string"
    content: str

    def get_template(self) -> str:
        """Return template content directly."""
        return self.content


class AbsenceSettings(BaseModel):
    """
    Configuration settings for absence and automatic reply management.

    Controls how absence periods and automatic replies are handled.
    """

    future_period_days: int = Field(
        default=3,
        validation_alias=AliasChoices("future_period_days", "future-period-days"),
    )
    keyword: str = Field(default="Vacation")
    max_delta_hours: int = Field(
        default=12, validation_alias=AliasChoices("max_delta_hours", "max-delta-hours")
    )
    internal_reply_template: LocalTemplateSource | StringTemplateSource = Field(
        default_factory=lambda: LocalTemplateSource(
            path=Path("internal_reply_template.html.in")
        ),
        discriminator="type",
        validation_alias=AliasChoices(
            "internal_reply_template", "internal-reply-template"
        ),
    )
    external_reply_template: LocalTemplateSource | StringTemplateSource = Field(
        default_factory=lambda: LocalTemplateSource(
            path=Path("external_reply_template.html.in")
        ),
        discriminator="type",
        validation_alias=AliasChoices(
            "external_reply_template", "external-reply-template"
        ),
    )
    date_format: str = Field(
        default="%d.%m.%Y", validation_alias=AliasChoices("date_format", "date-format")
    )


class AbstractSettings(BaseSettings, ABC):
    """
    Abstract base class for application settings.
    """

    # Customization of settings loading.
    model_config = SettingsConfigDict(
        env_prefix="",  # No prefix for environment variables.
        env_nested_delimiter="__",  # Use double underscore for nested settings.
        env_file=".env",  # Load settings from .env file.
        extra="ignore",  # Ignore extra settings.
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        Customize settings sources, optionally including Azure Key Vault.

        Adds Azure Key Vault as a settings source if AZURE_KEY_VAULT_URL environment variable is set.
        """
        azure_key_vault_url = os.environ.get("AZURE_KEY_VAULT_URL")
        az_key_vault_settings = (
            AzureKeyVaultSettingsSource(
                settings_cls,
                azure_key_vault_url,
                DefaultAzureCredential(),
            )
            if azure_key_vault_url
            else None
        )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ) + ((az_key_vault_settings,) if az_key_vault_settings else ())


class InitSettings(AbstractSettings):
    """
    Application settings needed for initialization.
    """

    # Cache settings.
    cache: LocalCacheSettings | KeyVaultCacheSettings = Field(
        default_factory=LocalCacheSettings, discriminator="type"
    )

    # App registration settings.
    app: AppRegistrationSettings = Field(default_factory=AppRegistrationSettings)


class RunSettings(InitSettings):
    """
    Application settings needed for running the application.
    """

    # Cache settings.
    cache: LocalCacheSettings | KeyVaultCacheSettings = Field(
        default_factory=LocalCacheSettings, discriminator="type"
    )

    # App registration settings.
    app: AppRegistrationSettings = Field(default_factory=AppRegistrationSettings)

    absence: AbsenceSettings = Field(default_factory=AbsenceSettings)

    dry_run: bool = Field(
        default=False, validation_alias=AliasChoices("dry_run", "dry-run")
    )
