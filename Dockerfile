FROM python:3.12

WORKDIR /project-chinese-story-generator

COPY pyproject.toml ./
COPY story_generator ./story_generator
RUN pip install --no-cache-dir .

COPY main.py alembic.ini ./
COPY alembic ./alembic

RUN useradd --system --no-create-home app
USER app

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0"]
