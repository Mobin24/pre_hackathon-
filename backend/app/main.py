"""FastAPI application entry point."""
from fastapi import FastAPI

app = FastAPI(title="DRRCS API")


@app.get("/")
def root():
    return {"status": "ok"}
