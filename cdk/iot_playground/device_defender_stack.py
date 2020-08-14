from aws_cdk import (
    aws_ssm,
    aws_sns,
    aws_cloud9,
    aws_lambda,
    aws_iam,
    aws_iot,
    core
)
from aws_cdk.core import App, Duration
import json


TARGET_POLICY_NAME_PREFIX="WS_AUDIT_"


class DeviceDefenderStack(core.Stack):
    def __init__(self, app: core.App, id: str, props, **kwargs) -> None:
        super().__init__(app, id, **kwargs)

        #cloud9 - Created manually because of permissions
        # cloud9 = aws_cloud9.CfnEnvironmentEC2(self, "IoT_Lab_Cloud9",
        #     instance_type="t2.small",
        #     automatic_stop_time_minutes=30,
        #     description="A Cloud9 env for doing the workshop"  #,
        #     #owner_arn="arn:aws:iam::*:user/virginia"
        # )

        # SNS
        topic_dda = aws_sns.Topic(self, "SNS_DDA_Findings",
        display_name="DDA_Findings",
        topic_name="DDA_Findings")

        role_dda = aws_iam.Role(self, 'DDA_to_SNS_Role',
            assumed_by=aws_iam.ServicePrincipal('iot.amazonaws.com')
        )
        
        policy_stmt_dda = aws_iam.PolicyStatement(
            actions=["sns:Publish"],
            resources=[topic_dda.topic_arn]
        )

        role_dda.add_to_policy(policy_stmt_dda)

        #permissive iot policy
        # permissive_policy = {
        #     "Version": "2012-10-17",
        #    "Statement": [{ 
        #       "Effect": "Allow",
        #       "Action": [
        #         "iot:Connect",
        #         "iot:Publish",
        #         "iot:Subscribe",
        #         "iot:Receive"
        #       ],
        #       "Resource": "*"
        #    }]
        # }

        # Removed. It will be created during the workshop
        #aws_iot.CfnPolicy(self, 
        #    "PermissivePolicy",
        #    policy_document=permissive_policy,
        #    policy_name="AUDIT_WS_PermisivePolicy")

        # Lambda
        function_dda = aws_lambda.Function(self, "DDA_FindingsProcessorLambda",
            runtime=aws_lambda.Runtime.PYTHON_3_7,
            handler="lambda_function.lambda_handler",
            code=aws_lambda.Code.asset("../lambdas/dda_findings_processor_lambda"),
            timeout=Duration.minutes(5))

        function_dda.add_environment("LOG_LEVEL", "DEBUG")
        function_dda.add_environment("TARGET_POLICY_NAME_PREFIX", TARGET_POLICY_NAME_PREFIX)
        
        # PolicyName: DeviceDefenderListResultsPolicy
        function_dda.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=[
                #"iot:DescribeAccountAuditConfiguration",
                #"iot:DescribeAuditTask",
                #"iot:ListAuditTasks",
                #"iot:ListScheduledAudits",
                "iot:ListAuditFindings"
            ],
            resources=["*"]
        ))

        # PolicyName: IoTUpdatePolicy
        function_dda.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=[
                "iot:CreatePolicyVersion",
                "iot:DeletePolicyVersion",
                "iot:ListPolicyVersions",
                "iot:SetDefaultPolicyVersion"
            ],
            resources=["arn:aws:iot:*:*:policy/{}*".format(TARGET_POLICY_NAME_PREFIX)]
        ))

        #function_dda.add_to_role_policy(aws_iam.PolicyStatement(
        #    effect=aws_iam.Effect.ALLOW,
        #    actions=["s3:PutObject", "s3:GetObject"],
        #    resources=["arn:aws:s3:::dreis-sandbox-temp/*"]
        #))

        #function_dda.add_to_role_policy(aws_iam.PolicyStatement(
        #    effect=aws_iam.Effect.ALLOW,
        #    actions=["iam:PassRole"],
        #    resources=["arn:aws:iam::*:role/*"]
        #))

        role_iot_logging = aws_iam.Role(self, 'AWSIoTLogging_Role',
            assumed_by=aws_iam.ServicePrincipal('iot.amazonaws.com')
        )
        
        policy_iot_logging = aws_iam.PolicyStatement(
            actions=[
                "logs:CreateLogGroup", 
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:PutMetricFilter",
                "logs:PutRetentionPolicy"
            ],
            resources=["arn:aws:logs:*:*:log-group:*:log-stream:*"]
        )

        role_iot_logging.add_to_policy(policy_iot_logging)

        # SNS
        topic_ddd = aws_sns.Topic(self, "SNS_DDD_Alerts",
        display_name="DDD_Alerts",
        topic_name="DDD_Alerts")

        role_ddd = aws_iam.Role(self, 'DDD_to_SNS_Role',
            assumed_by=aws_iam.ServicePrincipal('iot.amazonaws.com')
        )
        
        policy_stmt_ddd = aws_iam.PolicyStatement(
            actions=["sns:Publish"],
            resources=[topic_ddd.topic_arn]
        )

        role_ddd.add_to_policy(policy_stmt_ddd)

        # Lambda
        function_ddd = aws_lambda.Function(self, "DDD_AlertsProcessorLambda",
            runtime=aws_lambda.Runtime.PYTHON_3_7,
            handler="lambda_function.lambda_handler",
            code=aws_lambda.Code.asset("../lambdas/DDD_Alerts_processor_lambda"),
            timeout=Duration.minutes(5))

        function_ddd.add_environment("LOG_LEVEL", "DEBUG")

        # PolicyName: IoTUpdatePolicy
        function_ddd.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=[
                "iot:CreateThingGroup", # Required for WA
                "iot:AddThingToThingGroup",
                "iot:UpdateThingGroupsForThing",
                "iot:UpdateThingShadow"
            ],
            resources=["arn:aws:iot:*:*:*"]
        ))

        
        # cfn output
        # core.CfnOutput(
        #     self, "PipelineOut",
        #     description="Pipeline",
        #     value=pipeline.pipeline_name
        # )