# Example for storing caches in an Azure KeyVault

Store all settings locally and caches in an Azure KeyVault. Good for production and unattended operation. You still need
to keep the auto-reply templates in files though.

1. Copy `.env.example` to `.env`.  
2. Fill in the required tenant, client ID, and Azure KeyVault URL in `.env`.
3. Modify the auto-reply template files as needed.
4. Ensure that the `outlook-autoreply-helper` package is installed in your Python virtual environment. Then run the following command:
    ```bash
    python -m outlook_autoreply_helper run
    ```
5. Alternatively, use `uv` to set up and run in an ephemeral Python environment:
    ```bash
    uv run --with outlook_autoreply_helper -- python -m outlook_autoreply_helper run
    ```
