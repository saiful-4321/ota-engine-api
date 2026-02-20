#!/bin/bash

# Stop api service containers
i=1
while [ $i -le 1 ]; do
    docker stop ota_api-ota_api-$i
    i=$((i+1))
done

# Wait for 10 seconds
sleep 10

# Start api service containers
i=1
while [ $i -le 1 ]; do
    docker start ota_api-ota_api-$i
    i=$((i+1))
done