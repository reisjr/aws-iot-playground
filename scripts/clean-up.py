import boto3
from botocore.exceptions import ClientError
import json
import os

PREFIX = "dev-"

iam_cli = boto3.client("iam")
iot_cli = boto3.client("iot")

PROFILE=os.getenv("AWS_PROFILE", "NONE")
REGION=os.getenv("AWS_DEFAULT_REGION", "NONE")

def print_action(msg):
    print("{}:{} - {}".format(PROFILE, REGION, msg))


def delete_role(role_name):
    print_action(">delete_role")

    try:
        r = iam_cli.list_attached_role_policies(RoleName=role_name)
    
        for ap in r["AttachedPolicies"]:
            iam_cli.detach_role_policy(
                PolicyArn=ap["PolicyArn"],
                RoleName=role_name
            )
            iam_cli.delete_policy(PolicyArn=ap["PolicyArn"])
        
        iam_cli.delete_role(RoleName=role_name)

        print_action("<delete_role OK")
    except Exception as e:
        print_action(e)


def get_role_name_from_role_arn(role_arn):
    role_parts = role_arn.split("/")
    role_name = role_parts[len(role_parts)-1]
    print_action("ROLE NAME {} ".format(role_name)) 

    return role_name


def clean_iot_logging_config():
    print_action(">clean_iot_logging_config")

    try:
        r = iot_cli.get_logging_options()
    
        if "roleArn" in r:
            role_arn = r["roleArn"]
            role_name = get_role_name_from_role_arn(role_arn)
            
            delete_role(role_name)

        iot_cli.set_logging_options(
            loggingOptionsPayload={
                "roleArn": "",
                "logLevel": "DISABLED"
            }
        )
        print_action("<clean_iot_logging_config OK")
    except Exception as e:
        print_action(e)

    try:
        r = iot_cli.get_v2_logging_options()

        if "roleArn" in r:
            role_arn = r["roleArn"]
            role_name = get_role_name_from_role_arn(role_arn)        
            delete_role(role_name)
            
        r = iot_cli.set_v2_logging_level(
            logTarget={
                'targetType': 'DEFAULT'
            },
            logLevel='DISABLED'
        )

        response = iot_cli.set_v2_logging_options(
            roleArn="",
            defaultLogLevel="DISABLED",
            disableAllLogs=True
        )
        print_action("<clean_iot_logging_v2 OK")
    except Exception as e:
        print_action(e)


def delete_security_profiles():
    return


def clean_device_defender_config():
    print_action(">clean_device_defender_config")
    try:
        iot_cli.delete_account_audit_configuration(deleteScheduledAudits=True)
        print_action("<delete_account_audit_configuration OK")
    except Exception as e:
        print_action(e)

    delete_role("AWSIoTDeviceDefenderAudit_Role")


def delete_orphan_policies():
    r = iot_cli.list_policies()

    for p in r["policies"]:
        policy_name = p["policyName"]

        try:
            #p["policyArn"]
            rr = iot_cli.list_targets_for_policy(
                policyName=policy_name
            )
            if rr["targets"]:
                print_action("  {}: NOT EMPTY, IGNORING...".format(policy_name))
                for t in rr["targets"]:
                    print_action(t)
            else:
                print_action("  {}: DELETING...".format(policy_name))
                
                rrr = iot_cli.list_policy_versions(
                   policyName=policy_name
                )

                for v in rrr["policyVersions"]:
                    print_action("  {}: FOUND VERSIONS...".format(policy_name))
                    if not v["isDefaultVersion"]:
                        v_id = v["versionId"]
                        
                        print_action("  {}: DELETING VERSION...".format(policy_name, v_id))
                        
                        iot_cli.delete_policy_version(
                            policyName=policy_name,
                            policyVersionId=v_id
                        )
                    
                # Delete default
                iot_cli.delete_policy(
                    policyName=policy_name
                )
        except Exception as e:
            print_action("  {}: Error processing".format(policy_name))
            print_action("  {}".format(e))

def delete_orphan_certificates():
    r = iot_cli.list_certificates()
    
    for c in r["certificates"]:
        arn = c["certificateArn"]
        cert_id = c["certificateId"]
        try:

            rr = iot_cli.list_attached_policies(
                target=arn,
                recursive=True
            )

            if rr["policies"]:
                print_action("  {}: NOT EMPTY, IGNORING...".format(arn))
                print_action("  Policies:\n{}".format(rr["policies"]))
            else:
                print_action("  {}: DELETING...".format(arn))
                iot_cli.update_certificate(
                    certificateId=cert_id,
                    newStatus='INACTIVE'
                )

                iot_cli.delete_certificate(
                    certificateId=cert_id,
                    forceDelete=True
                )
        except Exception as e:
            print_action(e)
            print_action("ERROR")


def clean_things_and_attached_resources(prefix=PREFIX):
    try:
        next_token = None
        
        r = iot_cli.list_things(
            maxResults=100
        )

        things = r['things']
        
        for thing in things:

            if thing['thingName'].startswith("dev-DDQA"):
                print_action("IGNORING dev-DDQA...")    
            elif not thing['thingName'].startswith(PREFIX):
                print_action("IGNORING {}...".format(thing['thingName']))
            elif thing['thingName'].startswith(PREFIX):
                print_action("\n\nREMOVING {}...".format(thing['thingName']))    
                try:
                    thing_name = thing['thingName']

                    rr = iot_cli.list_thing_principals(
                        thingName=thing_name
                    )

                    principals = rr['principals']

                    for principal in principals: 
                        rrr = iot_cli.list_principal_policies(
                            principal=principal,
                            pageSize=100
                        )

                        policies = rrr['policies']

                        for policy in policies:
                            
                            policy_name = policy["policyName"]
                        
                            #'policyName': 'string',
                            #'policyArn': 'string'

                            print_action("'{}': DETACHING POLICY: '{}'".format(thing_name, policy_name))

                            r = iot_cli.detach_policy(
                                policyName=policy_name,
                                target=principal
                            )

                            print_action("'{}': DELETING  POLICY: '{}'".format(thing_name, policy_name))
                            
                            r = iot_cli.delete_policy(
                                policyName=policy_name
                            )
        
                        print_action("'{}': DETACHING  THING: '{}' from '{}'".format(thing_name, thing_name, principal))
                        r = iot_cli.detach_thing_principal(
                            thingName=thing_name,
                            principal=principal
                        )

                        print_action("'{}'    DELETING THING: '{}'".format(thing_name, thing_name))
                        cert_id = principal.split('/')[1] 

                        r = iot_cli.delete_thing(
                            thingName=thing_name
                        )

                        print_action("       UPDATE CERT: '{}'".format(thing_name))

                        r = iot_cli.update_certificate(
                            certificateId=cert_id,
                            newStatus='INACTIVE'
                        )

                        print_action("DELETING PRINCIPAL: '{}'".format(principal))

                        r = iot_cli.delete_certificate(
                            certificateId=cert_id,
                            forceDelete=True
                        )
                except Exception as e:
                    print_action(e)
        

        if 'nextToken' in r:
            next_token = r['nextToken']

        while next_token is not None:
            r = iot_cli.list_things(
                nextToken=next_token,
                maxResults=100
            )
            
            if 'nextToken' in r:
                next_token = r['nextToken']


    except Exception as e:
        print_action(e)

#delete_orphan_policies()
#delete_orphan_certificates()
clean_device_defender_config()
#delete_mitigation_actions()
#delete_security_profiles()
#clean_iot_logging_config()
#delete_role("IoTMitigationActionErrorLogging_Role")
