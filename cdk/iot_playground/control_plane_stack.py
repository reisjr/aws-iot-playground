from aws_cdk import (
    aws_ssm,
    aws_sns,
    aws_cloud9,
    aws_lambda as lambda_,
    aws_iam,
    aws_iot,
    aws_apigateway as apig,
    core
)
from aws_cdk.core import App, Duration
import json


TARGET_POLICY_NAME_PREFIX="WS_AUDIT_"


class ControlPlaneStack(core.Stack):
    def __init__(self, app: core.App, id: str, props, **kwargs) -> None:
        super().__init__(app, id, **kwargs)
        
        handler = lambda_.Function(
            self, "UrlShortenerFunction",
            code=aws_lambda.Code.asset("./lambda"),
            handler="lambda_function.lambda_handler",
            timeout=Duration.minutes(5),
            runtime=aws_lambda.Runtime.PYTHON_3_7)

        # define the API endpoint and associate the handler
        api = apig.LambdaRestApi(
            self, "IoTPgControlPlaneApi",
            handler=handler)

        #self.map_waltersco_subdomain('go', api)