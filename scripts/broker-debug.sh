#!/bin/bash

AWS_ROOT_CA_1="https://www.amazontrust.com/repository/AmazonRootCA1.pem"
AWS_ROOT_CA_2="https://www.amazontrust.com/repository/AmazonRootCA2.pem"
AWS_ROOT_CA_3="https://www.amazontrust.com/repository/AmazonRootCA3.pem"
AWS_ROOT_CA_4="https://www.amazontrust.com/repository/AmazonRootCA4.pem"
AWS_ROOT_SYMANTEC="https://www.symantec.com/content/en/us/enterprise/verisign/roots/VeriSign-Class%203-Public-Primary-Certification-Authority-G5.pem"

CRED_ENDPOINT=`aws iot describe-endpoint \
    --endpoint-type iot:Data-ATS \
    --output text --query endpointAddress`

ALIAS="$AWS_PROFILE-$AWS_DEFAULT_REGION"

source .config-$ALIAS

echo -en "$CERTIFICATE_PEM" > "/tmp/broker-debug-cert.pem"
echo -en "$PRIVATE_KEY" > "/tmp/broker-debug-key.pem"

if [ -f "root-ca.pem" ]; then
    echo ""
    echo "WARN: ROOT CA cert exists. Ignoring download..."
    echo ""
else
    echo ""
    echo "Downloading root cert..."
    wget "$AWS_ROOT_CA_1" --quiet -O root-ca.pem
fi

mosquitto_sub \
       --cafile root-ca.pem \
       --cert "/tmp/broker-debug-cert.pem" \
       --key "/tmp/broker-debug-key.pem" \
       -h $CRED_ENDPOINT \
       -p 8883 \
       -d -v \
       -t "dt/ac/company1/area1/#" \
       -t "#" \
       -i "broker-debug"
#       --tls-version tlsv1.2 \