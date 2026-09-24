FROM python:3.12

# Write print() output straight through, so `docker compose logs` shows the
# API's and worker's lines when they happen rather than when a buffer fills
# or the process exits.
ENV PYTHONUNBUFFERED=1

WORKDIR /project-chinese-story-generator

COPY pyproject.toml ./
COPY story_generator ./story_generator
RUN pip install --no-cache-dir .

COPY main.py alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --no-create-home app
USER app

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"]
