FROM python:3.9-slim-buster

COPY ./requirements.txt ./requirements.txt

RUN apt-get update && \
    apt-get install git gcc -y -q && \
    rm -rf /var/lib/apt/lists/* && \
    pip install -U pip --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir && \
    rm -rf /root/.cache/pip/* && \
    apt-get clean

EXPOSE 8080

WORKDIR /live/bot

COPY . .

ENV PYTHONPATH=/live

CMD ["python", "main.py"]