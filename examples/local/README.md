# Example for a local setup

Store all settings and caches locally. Good for development, testing, and initial setup.

1. Copy `.env.example` to `.env`.  
2. Fill in the required tenant and client ID in `.env`.
3. Modify the auto-reply template files as needed.
4. Ensure that the `outlook-autoreply-helper` package is installed in your Python virtual environment. Then run the following command:
    ```bash
    python -m outlook_autoreply_helper run
    ```
5. Alternatively, use `uv` to set up and run in an ephemeral Python environment:
    ```bash
    uv run --with outlook_autoreply_helper -- python -m outlook_autoreply_helper run
    ```
