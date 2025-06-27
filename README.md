# Mental-Health Chat Backend

A simple FastAPI backend for the Mental-Health Typebot project.

## Quick start

```bash
# clone and enter the repo
$ git clone <this repo url>
$ cd mhtp-chat-backend

# create and activate a virtual environment
$ python -m venv .venv
$ source .venv/bin/activate

# install dependencies
$ pip install -r requirements.txt

# run the API server
$ uvicorn backend.app.main:app --reload
```

For convenience on Unix systems you can also run `scripts/run_local.sh` which
loads variables from `.env` before starting Uvicorn.

## Folder overview

- `backend/` – FastAPI application code
- `scripts/` – helper scripts for local development
- `docs/` – project documentation
- `.github/workflows/` – CI configuration

