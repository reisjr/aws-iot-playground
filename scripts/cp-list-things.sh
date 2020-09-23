#!/bin/bash

DV_ENDPOINT=`aws ssm get-parameter --name iot-playground-devicefactoryendpoint --query "Parameter.Value" --output text`
curl -sS "$DV_ENDPOINT" -d '{"operation" : "list-devices"}'
