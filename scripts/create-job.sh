#!/bin/bash

export LC_CTYPE=C
JOB_ID=`cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 10 | head -n 1`

echo "Creating job $JOB_ID"

if [ $1 = "rc" ]; then
    ACTION="rotate-cert"
    
    CERT_LOCATION="\${aws:iot:s3-presigned-url:https://s3.amazonaws.com/dreis-sandbox-temp/dev-DDQA.json}"
    CERT_LOCATION="\${aws:iot:s3-presigned-url:https://s3.amazonaws.com/dreis-sandbox-temp/dev-DDQA.3590.cfg}"

    JSON_STRING=$(jq -n \
                    --arg ac "$ACTION" \
                    --arg cl "$CERT_LOCATION" \
                    '{action: $ac, config_file_url: $cl}' )
else
    ACTION="update-firmware"
    FIRMWARE_LOCATION="\${aws:iot:s3-presigned-url:https://s3.amazonaws.com/dreis-sandbox-temp/sample_job.json}"

    JSON_STRING=$(jq -n \
                    --arg ac "$ACTION" \
                    --arg fl "$FIRMWARE_LOCATION" \
                    '{action: $ac, firmware_file_url: $fl}' )
fi

echo "JOB ACTION $ACTION"
echo $JSON_STRING > "/tmp/$JOB_ID.json"

aws s3 cp "/tmp/$JOB_ID.json" "s3://dreis-sandbox-temp/$JOB_ID.json"

aws iot create-job \
    --job-id $JOB_ID \
    --targets "arn:aws:iot:us-east-1:255847889927:thing/dev-DDQA" \
    --presigned-url-config roleArn="arn:aws:iam::255847889927:role/AWS_IoT_Dev_Mgmt_Presigned_URL_Role",expiresInSec=3600 \
    --document-source "s3://dreis-sandbox-temp/$JOB_ID.json"


for i in {1..3}
do
   echo "$i - Check job..."
   aws iot describe-job \
        --job-id $JOB_ID
   sleep 3
done

echo "Deleting job $JOB_ID"

aws iot delete-job \
    --job-id $JOB_ID \
    --force


