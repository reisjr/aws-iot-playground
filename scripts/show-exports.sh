#!/bin/bash

PROFILE=ws02
#URL=`aws s3 presign --expires-in 300000 s3://dreis-sandbox-temp/dev-DDQA.json --profile $PROFILE`
URL=`aws s3 presign --expires-in 300000 s3://dreis-ws02-temp/dev-RPTG.cfg --profile $PROFILE`
PORT=8080

echo "export AWS_PROFILE=$PROFILE"
echo "export CONFIG_FILE_URL=\"$URL\""
echo "export PORT=$PORT"
