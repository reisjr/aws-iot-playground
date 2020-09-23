#!/bin/bash

while [ 1 ]; do 
    ./scripts/cp-query-thing.sh "$1" | jq '.["dev-name"],.data.Status,.data.ip'; 
    sleep 5; 
done