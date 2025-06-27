#!/usr/bin/env bash
export $(grep -v '^#' .env | xargs)   # carga variables locales
uvicorn backend.app.main:app --reload
