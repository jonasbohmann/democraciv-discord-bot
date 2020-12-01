FROM python:3.9-slim-buster

WORKDIR /live/api

COPY . .

RUN apt-get update && apt-get install gcc make -y && rm -rf /var/lib/apt/lists/* && pip install -U pip --no-cache-dir && pip install -r requirements.txt --no-cache-dir

EXPOSE 8000

ENV PYTHONPATH=/live

CMD ["python", "main.py"]