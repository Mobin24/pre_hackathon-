# Backend

FastAPI service for the DRRCS platform.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Structure

```
app/
├── core/         # config, security, cross-cutting concerns
├── routes/       # API routers
├── models/       # data models
├── schemas/      # pydantic schemas
├── services/     # business logic
├── ml/           # AI / ML modules
└── main.py
```
