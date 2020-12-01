FROM python:3.9-slim-buster

WORKDIR /live/bot

COPY . .

RUN apt-get update && apt-get install git gcc -y && rm -rf /var/lib/apt/lists/* && pip install -U pip --no-cache-dir && pip install -r requirements.txt --no-cache-dir

EXPOSE 8080

ENV PYTHONPATH=/live

CMD ["python", "main.py"]