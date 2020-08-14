import setuptools


with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="iot_playground",
    version="0.0.1",

    description="An empty CDK Python app",
    long_description=long_description,
    long_description_content_type="text/markdown",

    author="author",

    package_dir={"": "iot_playground"},
    packages=setuptools.find_packages(where="iot_playground"),

    install_requires=[
        "aws-cdk.core",
        "aws-cdk.aws-cloudformation",
        "aws-cdk.aws-codepipeline",
        "aws-cdk.aws-codepipeline-actions",
        "aws-cdk.aws-dynamodb",
        "aws-cdk.aws-events",
        "aws-cdk.aws-events-targets",
        "aws-cdk.aws-lambda",
        "aws-cdk.aws-s3",
        "aws-cdk.aws-s3-assets",
        "aws-cdk.aws-ec2",
        "aws-cdk.aws-ecs-patterns",
        "aws-cdk.aws-ecr",
        "aws-cdk.aws-ecr-assets",
        "aws-cdk.aws-certificatemanager",
        "aws-cdk.aws-apigateway",
        "aws-cdk.aws-cloudwatch",
        "aws-cdk.aws-cloud9",
        "aws-cdk.aws-sns",
        "aws-cdk.aws-iot",
        "cdk.watchful",
        "aws-cdk.aws-sqs",
        "aws-cdk.aws-ssm",
        "aws-cdk.cx-api",
        "aws-cdk.region-info",
        "boto3"
    ],

    python_requires=">=3.6",

    classifiers=[
        "Development Status :: 4 - Beta",

        "Intended Audience :: Developers",

        "License :: OSI Approved :: Apache Software License",

        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",

        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",

        "Typing :: Typed",
    ],
)
