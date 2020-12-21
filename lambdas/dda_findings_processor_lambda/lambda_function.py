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
TARGET_POLICY_NAME_PREFIX = os.environ["TARGET_POLICY_NAME_PREFIX"]
LOG_LEVEL = str(os.environ.get("LOG_LEVEL", "DEBUG")).upper()

# CONST
MAX_VERSIONS = 5
LOG_LEVEL_DEFAULT = "INFO"

iot = boto3.client("iot")
logger = logging.getLogger()


def load_iot_policy():
    data = None
    
    with open('iot_default_policy.json') as json_file:
        data = json.load(json_file)

    return data


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

# INIT 

def handle_security_issue(task_id, issue_name):
    logger.warn("The following problem '{}' on task '{}' will not be mitigated.".format(issue_name, task_id))


def get_policy_info(policy_name, policy_version):
    r = iot.list_policy_versions(
        policyName=policy_name
    )
    
    default_version = '0'
    older_version = '0'
    count = 0
    found = False

    for v in r['policyVersions']:
        if not v['isDefaultVersion']:
            older_version = v['versionId']
        else:
            default_version = v['versionId']
        
        if policy_version == v['versionId']:
            found = True
        
        count += 1

    return default_version, older_version, count, found


'''
This method replaces the permissive policy by a default restrictive one. It handles different cases:

* Policy not found
* Number of policy versions equals maximum number of policies allowed by AWS IoT (currently: 5) 
  requiring to delete an older version to create a new one
* The current default version is the offending version and cannot be deleted
'''
def fix_overly_permissive_policy(policy_name, policy_version):
    logger.debug(">fix_overly_permissive_policy '{}/{}'".format(policy_name, policy_version))
    
    restrictive_default_policy = load_iot_policy()

    try:
        current_default_policy, older_version, count, found = get_policy_info(policy_name, policy_version)
        new_policy_version = ""

        if not found:
            logger.warn("Reported policy version does not exist. Check if it was already deleted.")
            return 

        if count < MAX_VERSIONS:
            logger.info("Creating a new default policy...")

            # Create new default version
            r = iot.create_policy_version(
                policyName=policy_name,
                policyDocument=json.dumps(restrictive_default_policy),
                setAsDefault=True
            )

            new_policy_version = r['policyVersionId']

            logger.info("Deleting the offending policy '{}/{}'...".format(policy_name, policy_version))
            
            r = iot.delete_policy_version(
                policyName=policy_name,
                policyVersionId=policy_version
            )

        else: # Number of current versions = max versions, need to delete an existing version first
            
            if policy_version == current_default_policy:        
                logger.warn("The current policy is the default one and it cannot be deleted. Deleting an old policy...")
 
                r = iot.delete_policy_version(
                    policyName=policy_name,
                    policyVersionId=older_version
                )
            else:
                logger.info("Deleting the offending policy '{}/{}'...".format(policy_name, policy_version))

                r = iot.delete_policy_version(
                    policyName=policy_name,
                    policyVersionId=policy_version
                )

            logger.info("Creating a new default policy...")
            r = iot.create_policy_version(
                policyName=policy_name,
                policyDocument=json.dumps(restrictive_default_policy),
                setAsDefault=True
            )

            new_policy_version = r['policyVersionId']
        
        logger.info("Issue mitigated for policy '{}/{}', new default policy '{}/{}'.".format(policy_name, policy_version, policy_name, new_policy_version))

    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        logger.error("Issue NOT mitigated '{}/{}'. Please check the logs for details.".format(policy_name, policy_version), e)

    return 


def process_finding(resource):
    if resource['resourceType'] == "IOT_POLICY":
        id = resource['resourceIdentifier']['policyVersionIdentifier']
        policy_name = id['policyName']
        policy_version = id['policyVersionId']
        logger.debug("policyName: {} policyVersionId: {}".format(id['policyName'], id['policyVersionId']))
        
        # Restricting mitigation to a specific policy avoiding undesired changes
        if policy_name.startswith(TARGET_POLICY_NAME_PREFIX):
            fix_overly_permissive_policy(policy_name, policy_version) 
        else:
            logger.warn("The Policy '{}' was ignored.".format(policy_name))


def handle_overly_permissive_policy(task_id):
    logger.debug(">handle_overly_permissive_policy()")

    r = iot.list_audit_findings(taskId=task_id, checkName='IOT_POLICY_OVERLY_PERMISSIVE_CHECK')
    
    for f in r['findings']:
        process_finding(f['nonCompliantResource'])
    
    # If there are more Findings
    while 'nextToken' in r:
        r = iot.list_audit_findings(taskId=task_id, checkName='IOT_POLICY_OVERLY_PERMISSIVE_CHECK', nextToken=r['nextToken'])
        for f in r['findings']:
            process_finding(f['nonCompliantResource'])


def list_impacted_things(policy_name):
    r = iot.list_policy_principals(pageSize=10, policyName=policy_name)
    
    thing_list = []

    for principal in r['principals']:
        things = iot.list_principal_things(maxResults=10,principal=principal)
        thing_list.append(things['things']) 

    return thing_list


def lambda_handler(event, context):
    setup_log(LOG_LEVEL)

    logger.debug("Input:\n{}".format(json.dumps(event)))

    msg = json.loads(event['Records'][0]['Sns']['Message'])
    task_id = msg['taskId']

    logger.info("TaskId: {}".format(task_id))

    # Check if TARGET_POLICY_NAME_PREFIX is defined
    if not TARGET_POLICY_NAME_PREFIX:
        return "TARGET_POLICY_NAME_PREFIX not defined"

    for audit in msg['auditDetails']:

        if audit['checkRunStatus'] != "COMPLETED_COMPLIANT":
            issue_name = audit['checkName']
            logger.info("Analyzing the following issue '{}'...".format(issue_name))

            if issue_name == "IOT_POLICY_OVERLY_PERMISSIVE_CHECK":
                handle_overly_permissive_policy(task_id)
            else:
                handle_security_issue(task_id, issue_name)

    return "OK"