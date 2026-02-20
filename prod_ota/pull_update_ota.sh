#!/bin/bash
cd /home/qadmin/ota_api
docker compose pull ota_api
docker compose up -d ota_api
