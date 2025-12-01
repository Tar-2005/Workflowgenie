FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python -m pip install --upgrade pip
RUN pip install -r requirements.txt

ENV PORT=8080
EXPOSE 8080

# IMPORTANT: Use sh -c so $PORT expands

CMD ["sh", "-c", "gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT legacy.server_flask:app"]
