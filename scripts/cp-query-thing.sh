#!/bin/bash

DV_ENDPOINT=`aws ssm get-parameter --name iot-playground-devicefactoryendpoint --query "Parameter.Value" --output text`
curl -sS "$DV_ENDPOINT" -d "{\"operation\" : \"describe-device\", \"device-id\": \"$1\" }"

# while [ 1 ]; do 
#     ./scripts/cp-query-thing.sh dev-TUSE | jq '.["dev-name"],.data.Status,.data.ip'; 
#     sleep 5; 
# done