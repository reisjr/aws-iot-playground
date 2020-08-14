from aws_cdk import (
    core, aws_dynamodb, aws_lambda, aws_ec2, aws_ecs,
    aws_apigateway, aws_iam, aws_s3, aws_ecr, aws_ssm, aws_codebuild
)
from aws_cdk.aws_ec2 import SubnetType, Vpc
from aws_cdk.core import App, Construct, Duration
from random import choice
from string import ascii_uppercase


def create_random_name(size=8):
    return ''.join(choice(ascii_uppercase) for i in range(size))


class IotPlaygroundStack(core.Stack):

    def __init__(self, scope: core.App, id: str, props, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        subnets = []
        subnets.append(aws_ec2.SubnetConfiguration(name="DeviceSubnet", 
            subnet_type = aws_ec2.SubnetType.PUBLIC, 
            cidr_mask = 24)
        )

        vpc = aws_ec2.Vpc(self, "DeviceVpc",
            max_azs=2,
            subnet_configuration=subnets
        )
        
        # Iterate the private subnets
        selection = vpc.select_subnets(
            subnet_type=aws_ec2.SubnetType.PUBLIC
        )

        sg = aws_ec2.SecurityGroup(self, id="FarGateSecGroup", 
            vpc=vpc, 
            allow_all_outbound=True, 
            description="Allow access to virtual device", 
            security_group_name="Virtual Device Security Group")

        sg.add_ingress_rule(
            peer=aws_ec2.Peer.any_ipv4(),
            connection=aws_ec2.Port.tcp(80)
        )

        rnd_suffix = create_random_name(4).lower()

        # pipeline requires versioned bucket
        bucket = aws_s3.Bucket(
            self, "SourceBucket",
            bucket_name="{}-{}-{}".format(props['namespace'].lower(), 
                core.Aws.ACCOUNT_ID, core.Aws.REGION),
            versioned=True,
            removal_policy=core.RemovalPolicy.DESTROY)

        # ssm parameter to get bucket name later
        bucket_param = aws_ssm.StringParameter(
            self, "ParameterBucketName",
            parameter_name=f"{props['namespace']}-bucket",
            string_value=bucket.bucket_name,
            description='IoT playground pipeline bucket'
        )

        # ecr repo to push docker container into
        ecr = aws_ecr.Repository(
            self, "ECR",
            repository_name=f"{props['namespace']}",
            removal_policy=core.RemovalPolicy.DESTROY
        )

        # codebuild project meant to run in pipeline
        cb_docker_build = aws_codebuild.PipelineProject(
            self, "DockerBuild",
            project_name=f"{props['namespace']}-Docker-Build",
            build_spec=aws_codebuild.BuildSpec.from_source_filename(
                filename='docker/docker_build_buildspec.yml'),
                environment=aws_codebuild.BuildEnvironment(
                privileged=True,
            ),
            
            # pass the ecr repo uri into the codebuild project so codebuild knows where to push
            environment_variables={
                'ecr': aws_codebuild.BuildEnvironmentVariable(
                    value=ecr.repository_uri),
                'tag': aws_codebuild.BuildEnvironmentVariable(
                    value='virtual_device')
            },
            description='Pipeline for CodeBuild',
            timeout=core.Duration.minutes(10),
        )
        # codebuild iam permissions to read write s3
        bucket.grant_read_write(cb_docker_build)

        # codebuild permissions to interact with ecr
        ecr.grant_pull_push(cb_docker_build)

        ecs_cluster = aws_ecs.Cluster(
            self, 'DeviceCluster',
            vpc=vpc
        )
        
        fargate_task_def = aws_ecs.FargateTaskDefinition(self, 'DeviceTaskDef', 
            cpu=512,
            memory_limit_mib=1024
            #network_mode=aws_ecs.NetworkMode.AWS_VPC,
        )

        # fargate_task_def.add_to_task_role_policy(aws_iam.PolicyStatement(
        #     effect=aws_iam.Effect.ALLOW,
        #     actions=[
        #         "s3:PutObject"],
        #     resources=["*"]
        # ))

        fargate_task_def.add_to_execution_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "logs:CreateLogStream",
                "logs:PutLogEvents"],
            resources=["*"]
        ))

        container_image = aws_ecs.EcrImage(
            repository=ecr, 
            tag="virtual_device"
        )
        
        logging = aws_ecs.AwsLogDriver(
            stream_prefix="virtual_device"
        )

        container = fargate_task_def.add_container("DeviceContainer",
            image=container_image,
            cpu=512,
            memory_limit_mib=1024,
            logging=logging,
            essential=True
        )

        port_mapping = aws_ecs.PortMapping(
            container_port=80,
            host_port=80,
            protocol=aws_ecs.Protocol.TCP
        )
        
        container.add_port_mappings(port_mapping)

        # The code that defines your stack goes here
        table = aws_dynamodb.Table(self, "DeviceFactoryCatalog",
            partition_key=aws_dynamodb.Attribute(name="id", type=aws_dynamodb.AttributeType.STRING),
            read_capacity=3,
            write_capacity=3)

        function = aws_lambda.Function(self, "DeviceFactoryLambda",
            runtime=aws_lambda.Runtime.PYTHON_3_7,
            handler="lambda_function.lambda_handler",
            code=aws_lambda.Code.asset("../lambdas/device_factory_lambda"),
            timeout=Duration.minutes(1))

        function.add_environment("BUCKET_NAME", bucket.bucket_name)
        function.add_environment("ECS_CLUSTER", ecs_cluster.cluster_name)
        function.add_environment("ECS_TASK_DEF", fargate_task_def.task_definition_arn)
        function.add_environment("DDB_TABLE_DEVICE_CATALOG", table.table_name)
        function.add_environment("SUBNET_1", selection.subnets[0].subnet_id)
        function.add_environment("SUBNET_2", selection.subnets[1].subnet_id)
        function.add_environment("SEC_GROUP", sg.security_group_id)

        table.grant_read_write_data(function)

        function.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=["iot:*"],
            resources=["*"]
        ))

        function.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=["s3:PutObject", "s3:GetObject"],
            resources=["{}/*".format(bucket.bucket_arn)]
        ))

        function.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=["iam:PassRole"],
            resources=["arn:aws:iam::*:role/*"]
        ))

        function.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=["ecs:RunTask", "ecs:StopTask"],
            resources=["*"]
        ))              

        api_gtw = aws_apigateway.LambdaRestApi(self, 
            id="DeviceFactoryApi", 
            rest_api_name="DeviceFactoryApi",
            handler=function)

        # ssm parameter to get api endpoint later
        bucket_param = aws_ssm.StringParameter(
            self, "ParameterDeviceFactoryEndpoint",
            parameter_name=f"{props['namespace']}-devicefactoryendpoint",
            string_value=api_gtw.url,
            description='IoT playground device factory endpoint'
        )

        # ssm parameter to get api endpoint later
        bucket_param = aws_ssm.StringParameter(
            self, "ParameterEcrUri",
            parameter_name=f"{props['namespace']}-ecruri",
            string_value=ecr.repository_uri,
            description='IoT playground ECR URI'
        )

        # ssm parameter to get cluster name
        bucket_param = aws_ssm.StringParameter(
            self, "ParameterClusterName",
            parameter_name=f"{props['namespace']}-clustername",
            string_value=ecs_cluster.cluster_name,
            description='IoT playground Cluster Name'
        )

        core.CfnOutput(
            self, "EcrUri",
            description="ECR URI",
            value=ecr.repository_uri,
        )
        
        core.CfnOutput(
            self, "S3Bucket",
            description="S3 Bucket",
            value=bucket.bucket_name
        )

        core.CfnOutput(
            self, "DeviceFactoryEndpoint",
            description="Device Factory Endpoint",
            value=api_gtw.url
        )

        self.output_props = props.copy()
        self.output_props['bucket']= bucket
        self.output_props['cb_docker_build'] = cb_docker_build

    # pass objects to another stack
    @property
    def outputs(self):
        return self.output_props