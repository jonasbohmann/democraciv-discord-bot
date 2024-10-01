FROM python:3.12-slim-bookworm

RUN apt-get update && \
    apt-get install git gcc -y -q && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

COPY ./requirements.txt ./requirements.txt

RUN pip install -U pip setuptools wheel --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir && \
    rm -rf /root/.cache/pip/*

EXPOSE 8080

WORKDIR /live/bot

COPY . .

ENV PYTHONPATH=/live
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]