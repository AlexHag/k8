FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Serve Flask app via gunicorn (app object is `app` in main.py)
CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]


