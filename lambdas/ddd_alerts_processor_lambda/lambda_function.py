from __future__ import print_function

import boto3
import botocore
from botocore.client import Config
from botocore.exceptions import ClientError
import json
import datetime
import traceback
import sys
import os 
import logging

# ENV VARIABLES
LOG_LEVEL = str(os.environ.get("LOG_LEVEL", "DEBUG")).upper()

# CONST
LOG_LEVEL_DEFAULT = "ERROR"
IOT_QUARANTINE_GROUP = "Quarantine"
IOT_DEFAULT_GROUP = "DEFAULT"

iot_cli = boto3.client("iot")
iot_data_cli = boto3.client('iot-data')
logger = logging.getLogger()


def setup_log(level):
    try:
        logging.root.setLevel(level)
    except ValueError:
        logging.root.error('Invalid log level: %s', level)
        level = LOG_LEVEL_DEFAULT
        logging.root.setLevel(level)

    boto_level = LOG_LEVEL_DEFAULT

    try:
        logging.getLogger('boto').setLevel(boto_level)
        logging.getLogger('boto3').setLevel(boto_level)
        logging.getLogger('botocore').setLevel(boto_level)
    except ValueError:
        logging.root.error('Invalid log level: %s', boto_level)


def get_thing_name(msg):
    thing_name = ""
    
    if "thingName" in msg:
        thing_name = msg["thingName"]

    return thing_name


def create_thing_group():
    logger.debug(">create_thing_group")
    
    try: # TODO: This should be on the CDK, but it is not supported yet
        r = iot_cli.create_thing_group(
            thingGroupName=IOT_QUARANTINE_GROUP
            #parentGroupName='string',
            #thingGroupProperties={
            #    'thingGroupDescription': 'string',
            #    'attributePayload': {
            #        'attributes': {
            #            'string': 'string'
            #        },
            #        'merge': True|False
            #    }
            #},
            #tags=[
            #    {
            #        'Key': 'string',
            #        'Value': 'string'
            #    },
            #]
        )
    except Exception as e:
        logger.error("Error creating thing group", e)


def lambda_handler(event, context):
    setup_log(LOG_LEVEL)

    logger.debug("Input:\n{}".format(json.dumps(event)))

    msg = json.loads(event['Records'][0]['Sns']['Message'])

    thing_name = get_thing_name(msg)

    create_thing_group()

    iot_cli.update_thing_groups_for_thing(
        thingName=thing_name,
        thingGroupsToAdd=[
            IOT_QUARANTINE_GROUP
        ],
        thingGroupsToRemove=[
            IOT_DEFAULT_GROUP
        ]
    )

    payload = json.dumps({'state': { 'desired': { 'quarantine': True } }})

    iot_data_cli.update_thing_shadow(
        thingName=thing_name,
        payload=payload
    )

    return "OK"