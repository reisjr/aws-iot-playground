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
DDB_TABLE_DEVICE_CATALOG = os.getenv("DDB_TABLE_DEVICE_CATALOG", "DeviceFactoryCatalog")

# Loading boto3 clients
# BUG WA - https://github.com/boto/boto3/issues/1982
config = Config(s3={'addressing_style': 'path'})

iot_cli = boto3.client("iot")
iot_data_cli = boto3.client("iot-data")
ecs_cli = boto3.client("ecs")
s3_cli = boto3.client("s3", config=config)
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


def update_device_in_catalog(dev_name, status, ip):
    table = ddb_res.Table(DDB_TABLE_DEVICE_CATALOG)
    
    table.update_item(
        Key={
            "id": dev_name
        },
        UpdateExpression="SET #stt = :s, #attr_ip = :ip",
        ExpressionAttributeNames={
            "#stt": "Status",
            "#attr_ip": "ip"
        },
        ExpressionAttributeValues={
            ":s": status,
            ":ip": ip
        }
    )

    return

def check_error_response(response, msg="No additional info"):
    http_code = 0
    
    if "ResponseMetadata" in response and "HTTPStatusCode" in response["ResponseMetadata"]:
        http_code = response["ResponseMetadata"]["HTTPStatusCode"]
    
    if http_code != 200:
        logger.debug(response)
        raise Exception('Invalid response code {} / {}'.format(http_code, msg))


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

    dev_name = event.get("device")
    ip = event.get("ip")
    
    update_device_in_catalog(dev_name, "RUNNING", ip)
    
    return "OK"