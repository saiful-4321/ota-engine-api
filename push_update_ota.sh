#!/bin/bash
cd /home/qadmin/ota/ota_api
docker compose up --build -d ota_api
docker compose push ota_api
