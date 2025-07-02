# Mental-Health Chat Backend

Azure Functions implementing the tools used by the OpenAI Assistants that drive
our Typebot frontend.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
func start
```

Deploy to Azure with:

```bash
func azure functionapp publish <app-name>
```

## Folder overview

- `azure-functions/` – individual Function apps
- `backend/` – shared utilities
- `docs/` – project documentation
- `scripts/` – helper scripts
