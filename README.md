# Outlook Autoreply Helper

A Python package that automatically manages Outlook auto-reply settings via the Microsoft Graph API. Perfect for scheduling out-of-office messages during vacations or other absences.

[![PyPI](https://img.shields.io/pypi/v/outlook-autoreply-helper)](https://pypi.org/project/outlook-autoreply-helper/)
![Python Support](https://img.shields.io/pypi/pyversions/outlook_autoreply_helper) 
![PyPI Downloads](https://img.shields.io/pypi/dd/outlook_autoreply_helper)

## Features

- 🔄 Automatic detection of vacation events from your Outlook calendar
- 📅 Smart handling of adjacent or overlapping vacation periods
- ✨ Customizable auto-reply messages using Jinja2 templates
- 🌐 Uses Microsoft Graph API
- 🔑 Persistent token cache for unattended operation
- 🔒 Supports local and Azure Key Vault cache storage
- ☁️ Flexible configuration storage:
  - Local machine (environment variables / .env file)
  - Azure Key Vault (for unattended server deployments)
- 🔐 Supports multiple authentication flows for initial setup:
  - Interactive browser-based authentication
  - Device code flow for headless environments

## Installation

```bash
pip install outlook-autoreply-helper
```

Alternatively, you can skip the explicit installation and use `uv` to run the application in an ephemeral Python environment; see below.

## Quick Start

1. Register an application in Azure AD:
   - Go to Azure Portal > Azure Entra ID > Manage > App registrations.
   - Create a new registration "Outlook Autoreply Helper".
   - Go to Manage -> Authentication and add the "Mobile and desktop applications" platform.
   - Add the redirect URI: `http://localhost` to the platform. This is needed for initial authentication when using the Interactive Flow. You do not need this setting if you are using the Device Code Flow.
   - In the "Implicit grant and hybrid flows" section, ensure that "Access tokens (used for implicit flows)" is selected.
   - Add Microsoft Graph API permissions: `Calendars.Read`, `MailboxSettings.ReadWrite`. Ensure you add delegated permissions, not application permissions, as the application needs to access data on behalf of the user.
   - Note down the Application (client) ID and Directory (tenant) ID.

2. Create a configuration file (`.env`):
   ```env
   app__tenant_id=<your-tenant-id>
   app__client_id=<your-client-id>
   app__auth_flow=interactive  # or 'device_code'
   absence__keyword=Vacation  # Keyword to look for in the subject of the calendar event
   ```

3. Initialize the application:
   ```bash
   outlook-autoreply-helper init
   ```
   You will be prompted to authenticate and consent to the application accessing your calendar and mailbox settings.

   If you are using `uv`, you also run the application via
   ```bash
   uvx outlook_autoreply_helper init
   ```

4. Run the application:
   ```bash
   outlook-autoreply-helper run
   ```
   The application will check for upcoming events and update your mailbox settings accordingly.

   Again, using `uv` this can also be done via
   ```bash
   uvx outlook_autoreply_helper run
   ```

## Configuration

The application supports different options for storing configuration and state (e.g. access tokens) that should be shared between runs.

### Local Configuration

Store settings in environment variables or a `.env` file:

```env
# App Registration Settings
app__tenant_id=<tenant-id>
app__client_id=<client-id>
app__auth_flow=interactive  # or 'device_code'
absence__keyword=Vacation  # Keyword to look for in the subject of the calendar event
```

The remaining settings have sensible defaults and can be left out; see [.env.example](./.env.example).

By default, the application uses the local file system to store state. For example, access tokens are 
cached in a local file in the current working directory to reduce the need for re-authentication. See 
the example in [examples/local/](./examples/local/).

### Using Azure Key Vault for Caches

For unattended server deployments, state that should be shared between runs can be stored in an Azure Key Vault.
Just modify the .env file to use the keyvault cache type and provide the URL of the key vault:

```env
...
cache__type=keyvault
cache__keyvault_url=https://<your-keyvault>.vault.azure.net
```

When you run locally, you may be prompted to login to the Azure account that hosts the key vault. You can do this e.g. 
via the Azure CLI:

```bash
az login
````

When the application runs in an unattended environment, you need to ensure the application can access the key vault as well. If you
are deploying to an Azure Function, then you need to add an appropriate role assignment for the role *Key Vault Secrets Officer* for the corresponding Function App's managed identity in the key vault's IAM settings.

Note that the Azure tenant that hosts the key vault and the app registration that the application uses to manage the 
calendar and mailbox settings for a user may reside in different tenants. See
[examples/az_keyvault_cache/](./examples/az_keyvault_cache/) for an example.

### Using Azure Key Vault for Configuration

In addition to storing caches in Azure Key Vault, you can also store all or parts of the configuration there.
Simply set the environment variable `AZURE_KEY_VAULT_URL` to the URL of the corresponding key vault.
Each setting can then be stored as a secret in the key vault; see the [Pydantic documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#azure-key-vault) for details. This is particularly useful to store the auto-reply templates for unattended operation, since they can still be easily changed by the user without the need to redeploy the application.

See
[./examples/az_keyvault_cache_and_settings/](examples/az_keyvault_cache_and_settings/) for an example.

## Auto-reply Templates

Customize your auto-reply messages using Jinja2 templates. Variables available in templates:
- `vacation_start`: Start date of absence
- `vacation_end`: End date of absence

Example template:
```jinja
I am out of office from {{ vacation_start | date }} to {{ vacation_end | date }}.
I will respond to your message after my return.
```

The custom filter `date` formats the date in the desired format. You can change it to any format supported by Python's `strftime` function via the àbsence__date_format` setting in the configuration:

```env
...
absence__date_format=%Y-%m-%d
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Apache License, Version 2.0 - see the [LICENSE](LICENSE) file for details.
