#!/bin/bash

# Move this script one folder up before starting!

echo 'Starting api...'

uvicorn api.main:app --host 0.0.0.0 --port 8000

sleep 50