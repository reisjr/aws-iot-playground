#!/bin/bash -e

DV_CLUSTERNAME=`aws ssm get-parameter --name iot-playground-clustername --query "Parameter.Value" --output text`
ECS_CLI_PS=`ecs-cli ps --cluster ${DV_CLUSTERNAME} --region ${AWS_DEFAULT_REGION}`
DV_WEBPAGE_URL=`sed -r '/\n/!s/[0-9.]+/\n&\n/;/^([0-9]{1,3}\.){3}[0-9]{1,3}/P;D' <<<"$ECS_CLI_PS"`
for i in {1..10}
do
    curl -s -X POST -F 'action=large' "http://$DV_WEBPAGE_URL/actions" > /dev/null | echo "Sent large payload to AWS IoT via Virtual Device!"
    sleep 1
done