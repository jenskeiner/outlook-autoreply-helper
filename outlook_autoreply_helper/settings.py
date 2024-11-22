from pathlib import Path
from msal_extensions import (
    PersistedTokenCache,
    FilePersistenceWithDataProtection,
    FilePersistence,
)
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from msal import SerializableTokenCache

from pydantic import BaseModel, Field, AliasChoices
from typing import Literal
from abc import abstractmethod, ABC
from pydantic_settings import (
    BaseSettings,
)
import logging

# Configure module-level logger
log = logging.getLogger(__name__)


class CacheSettings(ABC, BaseModel):
    """
    Abstract base class for token cache settings.

    Defines an interface for token cache management with methods for
    retrieving and storing tokens.
    """

    @abstractmethod
    def get_token_cache(self):
        """Retrieve a token cache."""
        pass

    @abstractmethod
    def put_token_cache(self, token_cache):
        """Store a token cache."""
        pass


class LocalCacheSettings(CacheSettings):
    """
    Local file-based token cache settings with optional encryption.

    Supports storing tokens in a local file, with the option to use
    data protection for enhanced security.
    """

    type: Literal["local"] = "local"
    token_cache_file: Path = Field(
        default=Path("token_cache.bin"),
        alias=AliasChoices("token_cache_file", "token-cache-file"),
    )
    auto_reply_settings_cache_file: Path = Field(
        default=Path("auto_reply_settings.json"),
        alias=AliasChoices(
            "auto_reply_settings_cache_file", "auto-reply-settings-cache-file"
        ),
    )
    fallback_to_plaintext: bool = Field(
        default=True,
        alias=AliasChoices("fallback_to_plaintext", "fallback-to-plaintext"),
    )

    def get_token_cache(self):
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

    def put_token_cache(self, token_cache):
        """No-op method for local cache storage."""
        pass


class KeyVaultCacheSettings(CacheSettings):
    """
    Azure Key Vault-based token cache settings.

    Manages token caching using Azure Key Vault for secure storage and retrieval.
    """

    type: Literal["keyvault"] = "keyvault"
    key_vault_url: str = Field(alias=AliasChoices("key_vault_url", "key-vault-url"))
    token_cache_secret_name: str = Field(
        default="token-cache",
        alias=AliasChoices("token_cache_secret_name", "token-cache-secret-name"),
    )
    auto_reply_settings_cache_secret_name: str = Field(
        default="auto-reply-settings-cache",
        alias=AliasChoices(
            "auto_reply_settings_cache_secret_name",
            "auto-reply-settings-cache-secret-name",
        ),
    )

    def get_token_cache(self):
        """
        Retrieve or create a token cache from Azure Key Vault.

        Creates a new cache if no existing cache is found.
        """
        credential = DefaultAzureCredential()
        secret_client = SecretClient(
            vault_url=self.key_vault_url, credential=credential
        )

        # Create secret if it doesn't exist
        if not secret_client.get_secret(self.token_cache_secret_name):
            secret_client.set_secret(self.token_cache_secret_name, "")

        secret = secret_client.get_secret(self.token_cache_secret_name)

        cache = SerializableTokenCache()
        try:
            cache.deserialize(secret.value)
        except Exception as e:
            log.warning(f"Failed to deserialize token cache: {e}")
            cache = SerializableTokenCache()
            log.warning("Creating new token cache.")

        return cache

    def put_token_cache(self, token_cache):
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


class AppRegistrationSettings(BaseModel):
    """
    Azure AD application registration settings for authentication.

    Configures client ID, tenant ID, and authentication scopes.
    """

    tenant_id: str = Field(alias=AliasChoices("tenant_id", "tenant-id"))
    client_id: str = Field(alias=AliasChoices("client_id", "client-id"))
    scopes: list[str] = [
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "https://graph.microsoft.com/MailboxSettings.ReadWrite",
    ]
    base_url: str = Field(
        default="https://graph.microsoft.com/v1.0",
        alias=AliasChoices("base_url", "base-url"),
    )
    auth_flow: Literal["interactive", "device_code"] = Field(
        default="interactive", alias=AliasChoices("auth_flow", "auth-flow")
    )


class LocalTemplateSource(BaseModel):
    """
    Local file-based template source for absence reply messages.

    Reads template content from a local file path.
    """

    type: Literal["local"] = "local"
    path: Path

    def get_template(self):
        """Read and return template content from file."""
        return self.path.read_text()


class StringTemplateSource(BaseModel):
    """
    String-based template source for absence reply messages.

    Allows direct specification of template content.
    """

    type: Literal["string"] = "string"
    content: str

    def get_template(self):
        """Return template content directly."""
        return self.content


class AbsenceSettings(BaseModel):
    """
    Configuration settings for absence and automatic reply management.

    Controls how absence periods and automatic replies are handled.
    """

    future_period_days: int = Field(
        default=3, alias=AliasChoices("future_period_days", "future-period-days")
    )
    keyword: str = Field(default="Urlaub")
    max_delta_hours: int = Field(
        default=12, alias=AliasChoices("max_delta_hours", "max-delta-hours")
    )
    internal_reply_template: LocalTemplateSource | StringTemplateSource = Field(
        default_factory=lambda: LocalTemplateSource(
            path="internal_reply_template.html.in"
        ),
        discriminator="type",
        alias=AliasChoices("internal_reply_template", "internal-reply-template"),
    )
    external_reply_template: LocalTemplateSource | StringTemplateSource = Field(
        default_factory=lambda: LocalTemplateSource(
            path="external_reply_template.html.in"
        ),
        discriminator="type",
        alias=AliasChoices("external_reply_template", "external-reply-template"),
    )


class Settings(BaseSettings):
    """
    Comprehensive application settings aggregating various configuration components.

    Combines cache, app registration, absence, and logging settings.
    Supports multiple configuration sources including environment variables and .env file.
    """

    # Cache settings.
    cache: LocalCacheSettings | KeyVaultCacheSettings = Field(
        default_factory=LocalCacheSettings, discriminator="type"
    )

    # App registration settings.
    app: AppRegistrationSettings = Field(default_factory=AppRegistrationSettings)

    absence: AbsenceSettings = Field(default_factory=AbsenceSettings)

    dry_run: bool = Field(default=False, alias=AliasChoices("dry_run", "dry-run"))
