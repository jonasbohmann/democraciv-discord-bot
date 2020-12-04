FROM python:3.9-slim-buster

COPY ./requirements.txt ./requirements.txt

RUN apt-get update && \
    apt-get install gcc make -y -q && \
    rm -rf /var/lib/apt/lists/* && \
    pip install -U pip --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir && \
    rm -rf /root/.cache/pip/* && \
    apt-get clean

EXPOSE 8000

WORKDIR /live/api

COPY . .

ENV PYTHONPATH=/live

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]