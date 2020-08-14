#!/usr/bin/env python3

from aws_cdk import core

from iot_playground.iot_playground_stack import IotPlaygroundStack
from iot_playground.code_pipeline_stack import CodePipelineStack
from iot_playground.device_defender_stack import DeviceDefenderStack

props = {'namespace': 'iot-playground'}

app = core.App()
base = IotPlaygroundStack(app, "iot-playground", props)
CodePipelineStack(app, "codepipeline", base.outputs)
DeviceDefenderStack(app, "devicedefender", base.outputs)

app.synth()
