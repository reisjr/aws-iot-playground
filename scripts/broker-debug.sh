#!/bin/bash

DEV=$1

CRED_ENDPOINT=`aws iot describe-endpoint \
    --endpoint-type iot:Data-ATS \
    --output text --query endpointAddress`

 mosquitto_sub \
        --cafile rootCA.pem \
        --cert $DEV.pem.cer \
        --key $DEV.pem.key \
        -h $CRED_ENDPOINT \
        -p 8883 \
        -d -v \
        -t "\$aws/things/$DEV/#" \
        -t "\$aws/things/$DEV/get" \
	    -t "dt/ac/company1/area1/#" \
        -t "#" \
        -i $DEV-debug
 #       --tls-version tlsv1.2 \