FROM python:3.12-slim-bookworm

RUN apt-get update && \
    apt-get install gcc make -y -q && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

COPY ./requirements.txt ./requirements.txt

RUN pip install -U pip setuptools wheel --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir && \
    rm -rf /root/.cache/pip/*

# disabled since holmes-extractor does not work with Python 3.12
# RUN python3 -m spacy download en_core_web_trf && python3 -m spacy download en_core_web_lg && python3 -m coreferee install en

EXPOSE 8000

WORKDIR /live/api

COPY . .

ENV PYTHONPATH=/live
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]