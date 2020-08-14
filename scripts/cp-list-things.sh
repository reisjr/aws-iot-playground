#!/bin/bash

DV_ENDPOINT=`aws ssm get-parameter --name iot-playground-devicefactoryendpoint --query "Parameter.Value" --output text`
curl "$DV_ENDPOINT" -d '{"operation" : "describe-device", "device-type": "generic" }'⏎