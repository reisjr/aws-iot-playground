#!/bin/bash 

ALIAS="$AWS_PROFILE-$AWS_DEFAULT_REGION"

if [ -f ".config-$ALIAS" ]; then
       echo ""
       echo "WARN: .config-$ALIAS exists. Ignoring debug setup step..."
       echo "broker debug agent configured. Run ./scripts/broker-debug.sh"
       echo ""
       exit 0
else
       echo "Starting config..."
       aws iot create-keys-and-certificate \
              --set-as-active \
              --certificate-pem-outfile "/tmp/broker-debug-cert.pem" \
              --public-key-outfile "/tmp/broker-debug-pub.pem" \
              --private-key-outfile "/tmp/broker-debug-key.pem" --output json > "/tmp/config-$ALIAS.txt"

       CERTIFICATE_ARN=`cat "/tmp/config-$ALIAS.txt" | jq .certificateArn | sed 's/"//g'`
       CERTIFICATE_ID=`cat "/tmp/config-$ALIAS.txt" | jq .certificateId`
       CERTIFICATE_PEM=`cat "/tmp/config-$ALIAS.txt" | jq .certificatePem`
       PRIVATE_KEY=`cat "/tmp/config-$ALIAS.txt" | jq .keyPair.PrivateKey`

       echo "CERTIFICATE_ARN=\"$CERTIFICATE_ARN\"" > .config-$ALIAS
       echo "CERTIFICATE_ID=$CERTIFICATE_ID" >> .config-$ALIAS
       echo "CERTIFICATE_PEM=$CERTIFICATE_PEM" >> .config-$ALIAS
       echo "PRIVATE_KEY=$PRIVATE_KEY" >> .config-$ALIAS

       aws iot create-policy \
              --policy-name "broker-debug-policy" \
              --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":{\"Effect\":\"Allow\",\"Action\":\"iot:*\",\"Resource\":\"*\"}}"

       aws iot attach-policy \
       --policy-name "broker-debug-policy" \
       --target "$CERTIFICATE_ARN"

       echo "BROKER_DEBUG_POLICY=broker-debug-policy" >> .config-$ALIAS

       echo "broker debug agent configured. Run ./scripts/broker-debug.sh"
fi