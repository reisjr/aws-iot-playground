from __future__ import print_function

import datetime
import json
import logging
import os
import sys
import traceback
from random import choice
from string import ascii_uppercase

import boto3
import botocore
from botocore.client import Config
from botocore.exceptions import ClientError

# CONSTANTS
# https://aws.timwang.space/blog/?p=343

LOG_LEVEL_DEFAULT = "INFO"
LOG_LEVEL = str(os.environ.get("LOG_LEVEL", "DEBUG")).upper()
SUBNET_1 = os.getenv("SUBNET_1", "dreis-sandbox-temp")
SUBNET_2 = os.getenv("SUBNET_2", "dreis-sandbox-temp")
SEC_GROUP = os.getenv("SEC_GROUP", "dreis-sandbox-temp")
BUCKET_NAME = os.getenv("BUCKET_NAME", "dreis-sandbox-temp")
ECS_CLUSTER = os.getenv("ECS_CLUSTER", "DeviceFleetInfra")
ECS_TASK_DEF = os.getenv("ECS_TASK_DEF", "myFlaskApp-task-definition:3")
DDB_TABLE_DEVICE_CATALOG = os.getenv("DDB_TABLE_DEVICE_CATALOG", "DeviceFactoryCatalog")
PREFIX = "dev"

# Loading boto3 clients

iot_cli = boto3.client("iot")
iot_data_cli = boto3.client("iot-data")
ecs_cli = boto3.client("ecs")
s3_cli = boto3.client("s3")
ddb_res = boto3.resource("dynamodb")

# Load logger
logger = logging.getLogger()


def setup_log(level):
    try:
        logging.root.setLevel(level)
    except ValueError:
        logging.root.error('Invalid log level: %s', level)
        level = LOG_LEVEL_DEFAULT
        logging.root.setLevel(level)

    boto_level = "ERROR" # LOG_LEVEL_DEFAULT

    try:
        logging.getLogger('boto').setLevel(boto_level)
        logging.getLogger('boto3').setLevel(boto_level)
        logging.getLogger('botocore').setLevel(boto_level)
    except ValueError:
        logging.root.error('Invalid log level: %s', boto_level)


def create_random_name(size=8):
    return ''.join(choice(ascii_uppercase) for i in range(size))


def include_device_in_catalog(dev_name, iot_endpoint, certificate_pem, container_data):
    table = ddb_res.Table(DDB_TABLE_DEVICE_CATALOG)
    
    table.put_item(Item={
        "id": dev_name,
        "iot_endpoint": iot_endpoint,
        "cert": certificate_pem,
        "ts": datetime.datetime.now().isoformat(),
        "Status": "PROV",
        "TaskArn": container_data["taskArn"],
        "ClusterArn": container_data["clusterArn"]
    })

    return


def update_device_in_catalog(dev_name, status):
    table = ddb_res.Table(DDB_TABLE_DEVICE_CATALOG)
    
    table.update_item(
        Key={
            "id": dev_name
        },
        UpdateExpression="set #stt = :s",
        ExpressionAttributeNames={
            '#stt': "Status"
        },
        ExpressionAttributeValues={
            ':s': status
        }
    )

    return


def get_device_in_catalog(dev_name):
    table = ddb_res.Table(DDB_TABLE_DEVICE_CATALOG)
    
    r = table.get_item(
        Key={"id": str(dev_name)}
    )

    return r["Item"]


def create_container(dev_name, cfg_file_url):
    logger.debug(">create_container")

    response = ecs_cli.run_task(
        cluster=ECS_CLUSTER,
        taskDefinition=ECS_TASK_DEF,
        overrides={
            "containerOverrides": [
                {
                    "name": "DeviceContainer",
                    "environment": [
                        {
                            "name": "CONFIG_FILE_URL",
                            "value": cfg_file_url
                        }
                    ]
                }
            ]
        },
        count=1,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": [
                    SUBNET_1, SUBNET_2
                ],
                "securityGroups": [
                    SEC_GROUP
                ],
                "assignPublicIp": "ENABLED"
            }
        },
        startedBy=dev_name,
        enableECSManagedTags=False
    )

    check_error_response(response, "Error launching task")
    
    return { 
        "taskArn": response["tasks"][0]["taskArn"],
        "clusterArn": response["tasks"][0]["clusterArn"]
    }


def check_error_response(response, msg="No additional info"):
    http_code = 0
    
    if "ResponseMetadata" in response and "HTTPStatusCode" in response["ResponseMetadata"]:
        http_code = response["ResponseMetadata"]["HTTPStatusCode"]
    
    if http_code != 200:
        logger.debug(response)
        raise Exception('Invalid response code {} / {}'.format(http_code, msg))


def upload_file_to_s3(filename):
    s3_cli.upload_file("/tmp/{}".format(filename), BUCKET_NAME, filename)

    return


def load_iot_policy():
    data = None
    
    with open('iot_default_policy.json') as json_file:
        data = json.load(json_file)

    return data


def create_presigned_s3_url(filename):
    try:
        response = s3_cli.generate_presigned_url('get_object',
                    Params={'Bucket': BUCKET_NAME,'Key': filename},
                    ExpiresIn=3600)
        logger.debug(response)

        return response
    except ClientError as e:
        logging.error("S3 presigned error", e)
        return None


def prepare_config_file(dev_name, iot_endpoint, cert_pem, key_pem, device_type):
    cfg = {
        "device_name": dev_name,
        "iot_endpoint": iot_endpoint,
        "cert": cert_pem,
        "key": key_pem,
        "device-type": device_type,
        "root_ca": "-----BEGIN CERTIFICATE-----\nMIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF\nADA5MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6\nb24gUm9vdCBDQSAxMB4XDTE1MDUyNjAwMDAwMFoXDTM4MDExNzAwMDAwMFowOTEL\nMAkGA1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJv\nb3QgQ0EgMTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALJ4gHHKeNXj\nca9HgFB0fW7Y14h29Jlo91ghYPl0hAEvrAIthtOgQ3pOsqTQNroBvo3bSMgHFzZM\n9O6II8c+6zf1tRn4SWiw3te5djgdYZ6k/oI2peVKVuRF4fn9tBb6dNqcmzU5L/qw\nIFAGbHrQgLKm+a/sRxmPUDgH3KKHOVj4utWp+UhnMJbulHheb4mjUcAwhmahRWa6\nVOujw5H5SNz/0egwLX0tdHA114gk957EWW67c4cX8jJGKLhD+rcdqsq08p8kDi1L\n93FcXmn/6pUCyziKrlA4b9v7LWIbxcceVOF34GfID5yHI9Y/QCB/IIDEgEw+OyQm\njgSubJrIqg0CAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC\nAYYwHQYDVR0OBBYEFIQYzIU07LwMlJQuCFmcx7IQTgoIMA0GCSqGSIb3DQEBCwUA\nA4IBAQCY8jdaQZChGsV2USggNiMOruYou6r4lK5IpDB/G/wkjUu0yKGX9rbxenDI\nU5PMCCjjmCXPI6T53iHTfIUJrU6adTrCC2qJeHZERxhlbI1Bjjt/msv0tadQ1wUs\nN+gDS63pYaACbvXy8MWy7Vu33PqUXHeeE6V/Uq2V8viTO96LXFvKWlJbYK8U90vv\no/ufQJVtMVT8QtPHRh8jrdkPSHCa2XV4cdFyQzR1bldZwgJcJmApzyMZFo6IQ6XU\n5MsI+yMRQ+hDKXJioaldXgjUkK642M4UwtBV8ob2xJNDd2ZhwLnoQdeXeGADbkpy\nrqXRfboQnoZsG4q5WTP468SQvvG5\n-----END CERTIFICATE-----\n"
    }

    with open("/tmp/{}.cfg".format(dev_name), "w") as dev_file:
        dev_file.write("%s" % json.dumps(cfg))

    return "{}.cfg".format(dev_name)


def create_device(thing_group_name="AC"):
    logger.debug(">create_device '{}'".format(thing_group_name))
    
    response = {}

    try:
        r = iot_cli.create_keys_and_certificate(setAsActive=True)

        certificate_arn = r['certificateArn']
        certificate_id = r['certificateId']
        certificate_pem = r['certificatePem']
        private_key = r['keyPair']['PrivateKey']

        logger.info("CERT ARN: {}\nCERT ID : {}\nCERT PEM:\n{}".format(certificate_arn, certificate_id, certificate_pem))

        serial_number = create_random_name(4)
        dev_name = "{}-{}".format(PREFIX, serial_number)
        
        response['dev_name'] = dev_name

        logger.info("DEV NAME: {}".format(dev_name))

        with open("/tmp/device_name.{}".format(dev_name), "w") as dev_file:
            dev_file.write("%s" % dev_name)

        with open("/tmp/{}.pem.cer".format(dev_name), "w") as cert_file:
            cert_file.write("%s" % certificate_pem)

        with open("/tmp/{}.pem.key".format(dev_name), "w") as key_file:
            key_file.write("%s" % private_key)

        try:
            r = iot_cli.create_thing_group(
                    thingGroupName=thing_group_name,
                    thingGroupProperties={
                        "thingGroupDescription": "This is group for {} devices".format(thing_group_name)
                    }
            )
        except Exception as e:
            traceback.print_tb(e, limit=10, file=sys.stdout)
            logger.debug("Error creating thing group")

        r = iot_cli.create_thing(
            thingName=dev_name,
            #thingTypeName='AC',
            attributePayload={
                "attributes": {
                    "Location": "Brazil",
                    "SerialNumber": serial_number
                }
            }
        )

        policy_name = "{}-{}".format(dev_name, "Policy")

        default_iot_policy = load_iot_policy()

        r = iot_cli.create_policy(
            policyName=policy_name,
            policyDocument=json.dumps(default_iot_policy)
        )

        #attach

        r = iot_cli.attach_thing_principal(
            thingName=dev_name,
            principal=certificate_arn
        )

        r = iot_cli.attach_policy(
            policyName=policy_name,
            target=certificate_arn
        )

        r = iot_cli.add_thing_to_thing_group(
            thingGroupName=thing_group_name,
            #thingGroupArn='string',
            thingName=dev_name,
            #thingArn='string',
            #overrideDynamicGroups=True|False
        )

        r = iot_data_cli.update_thing_shadow(
            thingName=dev_name,
            payload='{"state":{"desired":{"debug":"off"}}}'
        )

        r = iot_cli.describe_endpoint(
            endpointType='iot:Data-ATS'
        )

        iot_endpoint = r["endpointAddress"]
        device_type = thing_group_name

        cfg_file = prepare_config_file(dev_name, iot_endpoint, certificate_pem, private_key, device_type)
        upload_file_to_s3(cfg_file)
        cfg_file_url = create_presigned_s3_url(cfg_file)
        container_data = create_container(dev_name, cfg_file_url)
        include_device_in_catalog(dev_name, iot_endpoint, certificate_pem, container_data)

        response['endpoint'] = iot_endpoint
        response['task_arn'] = container_data["taskArn"] 
        response['cluster_arn'] = container_data["clusterArn"]
        response['config_file_url'] = cfg_file_url
        response['result'] = "OK"

    except ClientError as e:
        #if e.response['Error']['Code'] == 'EntityAlreadyExists':
        logger.error("Unexpected error", e)
        
        response['result'] = "ERROR"
        response['error-msg'] = e

        return generate_error_response(response)

    return generate_response(response)


def shutdown_task(cluster, task_id):
    r = ecs_cli.stop_task(
        task=task_id, 
        cluster=cluster
    )

    check_error_response(r, "Error shutdown task")

    return True


def delete_device(device_id):
    # get data from DDB
    r = get_device_in_catalog(device_id)
    logger.debug(r)

    # shutdown container
    task_id = r["TaskArn"]
    cluster = r["ClusterArn"]
    shutdown_task(cluster, task_id)

    # remove thing from aws iot
    r = iot_cli.describe_thing()

    # remove policy
    r = iot_cli.delete_policy(
        policyName=policy_name
    )

    # update DDB
    update_device_in_catalog(device_id, "TERMINATED")
    
    p = {
        "dev-name": device_id,
        "result": "TERMINATED"
    }    
    
    return generate_response(p)


def describe_device(device_id):
    r = get_device_in_catalog(device_id)
    
    p = {
        "dev-name": device_id
    }

    return generate_response(p)


def link_devices(source_device_id, target_device_id):
    control_policy = {
        "Version": "2012-10-17",
        "Statement": [
        { 
            "Effect": "Allow",
            "Action": [
            "iot:GetPendingJobExecutions",
            "iot:GetThingShadow",
            "iot:UpdateThingShadow",
            "iot:StartNextPendingJobExecution"
            ],
            "Resource": [
            "arn:aws:iot:us-east-1:*:thing/{}".format(target_device_id)
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
            "iot:Publish"
            ],
            "Resource": [
            "arn:aws:iot:us-east-1:*:topic/$aws/things/{}/shadow/*".format(target_device_id),
            ]
        }
        ]
    }

    policy_name = "{}-att-{}-Policy".format(source_device_id, target_device_id)

    r = iot_cli.create_policy(
        policyName=policy_name,
        policyDocument=json.dumps(control_policy)
    )
    
    r = iot_cli.list_thing_principals(
        thingName=source_device_id
    )

    principal = r["principals"][0]
    logger.debug("Principal '{}'".format(principal))

    r = iot_cli.attach_policy(
        policyName=policy_name,
        target=principal
    )

    p = {
        "source-device-id": source_device_id,
        "target-device-id": target_device_id,
        "policy-name": policy_name
    }
    
    return generate_response(p)


def generate_response(params):
    return {
        'statusCode': 200,
        'body': json.dumps(params)
    }


def generate_error_response(op):
    return {
        'statusCode': 500,
        'body': json.dumps({
            "error-message": op
        })
    }


def lambda_handler(event, context):
    setup_log(LOG_LEVEL)
    logger.debug(">lambda_handler\nevent:\n{}".format(json.dumps(event)))

    response = {}

    op = ""
    body = {}
    
    if "body" in event:
        try:
            body = json.loads(event["body"])
            if "operation" in body:
                op = body["operation"]
        except Exception as e:
            logger.error("No operation found", e)

    try:
        if op == "create-device":
            device_type = "generic"
            prov_type = "DEFAULT"
            
            if "device-type" in body:
                device_type = body["device-type"]
            
            if "prov-type" in body:
                prov_type = body["prov-type"]
            
            response = create_device(device_type)
        elif op == "describe-device":
            device_id = ""
            
            if "device-id" in body:
                device_id = body["device-id"]
                response = describe_device(device_id)
            else:
                response = generate_error_response("device_id not found")                
        elif op == "delete-device":
            device_id = ""

            if "device-id" in body:
                device_id = body["device-id"]
                response = delete_device(device_id)
            else:
                response = generate_error_response("device_id not found")    
        elif op == "link-devices":            
            source_device_id = ""
            target_device_id = ""

            if "source-device-id" in body:
                source_device_id = body["source-device-id"]
            
            if "target-device-id" in body:
                target_device_id = body["target-device-id"]
            
            response = link_devices(source_device_id, target_device_id)
        else:
            response = generate_error_response(op)
    except Exception as e:
        traceback.print_exc()
        logger.error("General error", e)
        response = generate_error_response(e)
    
    logger.info("RESPONSE: {}".format(response))

    return response