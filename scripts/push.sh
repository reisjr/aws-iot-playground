#!/bin/bash -e

if [[ -z "${AWS_DEFAULT_REGION}" ]]; then
    echo "AWS_DEFAULT_REGION not defined. Please define your default region before running this script."
    echo "export AWS_DEFAULT_REGION=\"<AWS_REGION>\""
    exit
fi

export ACCOUNT_ID=$(aws sts get-caller-identity | jq -r .Account)
export SOURCE_BUCKET=$(aws ssm get-parameter --name 'iot-playground-bucket' | jq -r .Parameter.Value)
export PIPELINE_NAME=$(aws ssm get-parameter --name 'iot-playground-pipeline' | jq -r .Parameter.Value)

echo "CONFIG"
echo "============================="
echo "   ACCOUNT_ID: $ACCOUNT_ID"
echo "SOURCE_BUCKET: $SOURCE_BUCKET"
echo "PIPELINE_NAME: $PIPELINE_NAME"
echo "       REGION: $AWS_DEFAULT_REGION"

echo "Zipping the code..."
zip -r /tmp/source.zip ./docker

echo "Sending the code to s3://${SOURCE_BUCKET}..."
aws s3 cp /tmp/source.zip s3://${SOURCE_BUCKET}/source.zip

echo "Starting the pipeline ${PIPELINE_NAME}..."
aws codepipeline start-pipeline-execution --name ${PIPELINE_NAME}