# Example for storing settings and caches in an Azure KeyVault

Store (some) settings and caches in an Azure KeyVault. Good for production and unattended operation. You can move 
auto-reply templates into the KeyVault to remove the need to keep them in the target environment's file system.

1. Copy `.env.example` to `.env`.  
2. Fill in the required tenant, client ID, and Azure KeyVault URL in `.env`.
3. Modify the auto-reply template files as needed.
4. Configure the auto-reply templates as secrets in the Azure KeyVault. You can use e.g. the Azure CLI:
    ```bash
    az keyvault secret set --vault-name "<KEY_VAULT_NAME>" --name "internal-reply-template--type" --value "string"
    az keyvault secret set --vault-name "<KEY_VAULT_NAME>" --name "internal-reply-template--content" --file internal_reply_template.html.in
    az keyvault secret set --vault-name "<KEY_VAULT_NAME>" --name "external-reply-template--type" --value "string"
    az keyvault secret set --vault-name "<KEY_VAULT_NAME>" --name "external-reply-template--content" --file external_reply_template.html.in
    ```
   You can store other settings there as well, just replace `_` in environment variable names with '-'. Storing the 
   templates in a KeyVault is particularly useful if you cannot rely on local storage in files. For other settings, 
   using an .env file or environment variables may still be a good option.
5. Ensure that the environment variable `AZURE_KEY_VAULT_URL` is set to the URL of the Azure KeyVault before running the 
   application. 
6. Ensure that the `outlook-autoreply-helper` package is installed in your Python virtual environment. Then run the following command:
    ```bash
    python -m outlook_autoreply_helper run
    ```
7. Alternatively, use `uv` to set up and run in an ephemeral Python environment:
    ```bash
    uv run --with outlook_autoreply_helper -- python -m outlook_autoreply_helper run
    ```

Note: The KeyVault used for caches and for storing settings need not be the same. But it makes most sense for unattended
operation as the application will typically only have a single credential to access Azure resources for loading settings
and storing caches.