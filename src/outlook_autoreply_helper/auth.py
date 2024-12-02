import logging

import msal

from .settings import AppRegistrationSettings

log = logging.getLogger(__name__)


def get_access_token(
    settings: AppRegistrationSettings, token_cache: msal.TokenCache
) -> str:
    """
    Acquire an access token for Microsoft Graph API using MSAL.

    This function attempts to retrieve an access token using the following strategies:
    1. First, try to get a token silently from the token cache.
    2. If no cached token is available, use either device code or interactive authentication flow, and initialize the
       cache.

    Args:
        settings (AppRegistrationSettings): Application registration settings
        token_cache: A persistent token cache for storing and retrieving tokens

    Returns:
        str: A valid access token for Microsoft Graph API

    Raises:
        RuntimeError: If token acquisition fails
    """
    # Create MSAL public client application with persistent token cache.
    msal_app = msal.PublicClientApplication(
        settings.client_id,
        authority=f"https://login.microsoftonline.com/{settings.tenant_id}",
        token_cache=token_cache,
    )

    # Attempt to retrieve tokens from cache.
    accounts = msal_app.get_accounts()
    result = None
    if accounts:
        log.info(f"Found {len(accounts)} account(s) in cache.")
        # Try to acquire token silently for the first cached account.
        result = msal_app.acquire_token_silent(settings.scopes, account=accounts[0])

    # If no suitable token found in cache, proceed with authentication.
    if not result:
        log.info("No suitable token in cache. Initiating authentication.")

        # Choose authentication flow based on settings.
        if settings.auth_flow == "device_code":
            # Device code flow: User authenticates on another device.
            log.info("Using device code authentication flow.")
            flow = msal_app.initiate_device_flow(scopes=settings.scopes)

            if "user_code" not in flow:
                raise ValueError(f"Failed to create device flow. Response: {flow}")

            log.info(flow["message"])

            # Flush log handlers to ensure message is displayed
            for handler in logging.root.handlers:
                handler.flush()

            result = msal_app.acquire_token_by_device_flow(flow)
        else:
            # Interactive authentication flow: User authenticates in the browser.
            log.info("Using interactive authentication flow.")
            result = msal_app.acquire_token_interactive(
                scopes=settings.scopes,
                prompt="select_account",  # Force account selection.
            )

    # Validate and return token.
    if "access_token" in result:
        return result["access_token"]
    else:
        log.error("Token acquisition failed.")
        if "error" in result:
            log.error(f"Error: {result['error']}")
            if "error_description" in result:
                log.error(f"Error description: {result['error_description']}")

        raise RuntimeError("Failed to acquire authentication token.")
