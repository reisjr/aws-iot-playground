#!/bin/bash

function clean_iot() {
    ACC_ID=`aws sts get-caller-identity --query "Account" --output text --profile $1`
    echo "Cleaning PROFILE $1 / ACC_ID: $ACC_ID"
    
    export AWS_PROFILE="$1"

    export AWS_DEFAULT_REGION="us-east-1"
    python clean_up.py

    export AWS_DEFAULT_REGION="us-east-2"
    python clean_up.py
    
    export AWS_DEFAULT_REGION="us-west-2"
    python clean_up.py    

    export AWS_DEFAULT_REGION="eu-west-1"
    python clean_up.py
}

for i in $(seq -f "%02g" 1 10)
do
  clean_iot "ws$i"
done