#!/bin/bash

function deploy_bootstrap() {
    ACC_ID=`aws sts get-caller-identity --query "Account" --output text --profile $1`
    echo "Deploying to PROFILE $1 / ACC_ID: $ACC_ID"
    cdk bootstrap "aws://$ACC_ID/us-east-1" --profile $1
    cdk bootstrap "aws://$ACC_ID/us-west-2" --profile $1
    cdk bootstrap "aws://$ACC_ID/us-east-2" --profile $1
    cdk bootstrap "aws://$ACC_ID/eu-west-1" --profile $1
}

deploy_bootstrap "ws01"
deploy_bootstrap "ws02"
deploy_bootstrap "ws03"
deploy_bootstrap "ws04"
deploy_bootstrap "ws05"
deploy_bootstrap "ws06"
deploy_bootstrap "ws07"
deploy_bootstrap "ws08"
