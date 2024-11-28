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
- 🔒 Supports local and Azure KeyVault cache storage
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

The application supports two main configuration approaches:

### Local Configuration

Store settings in environment variables or a `.env` file:

```env
# App Registration Settings
app__tenant_id=<tenant-id>
app__client_id=<client-id>
app__auth_flow=interactive  # or 'device_code'

# Absence Settings
absence__keyword=Vacation  # Calendar event keyword to trigger auto-reply
absence__future_period_days=90  # How far ahead to look for events
absence__date_format=%Y-%m-%d  # Date format in auto-reply messages

# Cache Settings (Local)
cache__type=local
cache__token_cache_file=~/.outlook-autoreply-helper/token_cache.bin
cache__tz_cache_file=~/.outlook-autoreply-helper/tz_cache.json
cache__fallback_to_plaintext=false
```

### Azure Key Vault Configuration

For unattended server deployments, store sensitive data in Azure Key Vault:

```env
AZURE_KEY_VAULT_URL=https://<your-keyvault>.vault.azure.net
cache__type=keyvault
cache__token_cache_secret_name=outlook-autoreply-token-cache
cache__tz_cache_secret_name=outlook-autoreply-tz-cache
```

## Auto-reply Templates

Customize your auto-reply messages using Jinja2 templates. Variables available in templates:
- `vacation_start`: Start date of absence
- `vacation_end`: End date of absence

Example template:
```jinja
I am out of office from {{ vacation_start|date }} to {{ vacation_end|date }}.
I will respond to your message after my return.
```

## Development

### Setup Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/outlook-autoreply-helper.git
   cd outlook-autoreply-helper
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate  # Windows
   ```

3. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

### Running Tests

```bash
pytest
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
