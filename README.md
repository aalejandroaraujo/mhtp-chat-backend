# Mental-Health Chat Backend

A simple FastAPI backend for the Mental-Health Typebot project.

## Quick start



```bash

#LINUX
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

```bash

#WINDOWS
F:\mhtp-chat-backend> python -m venv .venv
uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --reload
ngrok http 8080   # execute on a different shell and copy the HTTPS URL into Typebot, or check in https://dashboard.ngrok.com/endpoints the current endpoints

```

For convenience on Unix systems you can also run `scripts/run_local.sh` which
loads variables from `.env` before starting Uvicorn.

## Folder overview

- `backend/` – FastAPI application code
- `scripts/` – helper scripts for local development
- `docs/` – project documentation
- `.github/workflows/` – CI configuration

