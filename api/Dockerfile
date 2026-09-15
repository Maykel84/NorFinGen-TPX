FROM python:3.12-slim

WORKDIR /app

COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Kod usługi (w tym api/static/portal/, zamontowany pod /portal w main.py) +
# docs/ (events.py czyta docs/faza7_life_events_log.csv)
COPY api/ api/
COPY docs/faza7_life_events_log.csv docs/faza7_life_events_log.csv

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
