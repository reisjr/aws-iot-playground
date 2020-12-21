from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import json
import boto3
import time
import datetime
import os
import sys
import random
import string
import psutil as ps
from enum import Enum
import metrics
import socket


if sys.version[0:1] == '3':
    import urllib.request as urllib
else:
    import urllib as urllib


DEFAULT_MQTT_PORT = 8883
DEFAULT_SAMPLING_DELAY = 60
## 300 (5 minutes) is the Default Device Metrics sampling best-practice, more frequent than this and you get throttled
DEFAULT_DEVICE_METRICS_SAMPLING_DELAY = 300
LOG_SIZE = 15000


class JobStatus(Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"
    CANCELED = "CANCELED"
    TIMED_OUT = "TIMED_OUT"
    REJECTED = "REJECTED"
    REMOVED = "REMOVED"


class VirtualDevice:

    _stop = False
    _sampling_delay = DEFAULT_SAMPLING_DELAY
    _device_metrics_sampling_delay = DEFAULT_DEVICE_METRICS_SAMPLING_DELAY
    _next_message_time = datetime.datetime.now()
    _next_device_defender_telemetry = datetime.datetime.now()
    _mqtt_client = None
    _lwt_topic = None
    _lwt_message = None
    _clean_disconnect = True
    _log = None
    _force_reconnect = False
    _pending_payloads = []

    # Class Attributes
    endpoint = "ep"
    name = "name"
    mqtt_port = DEFAULT_MQTT_PORT
    mqtt_telemetry_topic = "dt/ac/company1/area1/{}/temp"
    mqtt_device_defender_telemetry_topic = "$aws/things/{}/defender/metrics/json"

    shadow = {}
    unit = "metric" # "imperial"
    payload = { "temp" : 30 }


    def __init__(self, name, endpoint):
        self.name = name
        self.endpoint = endpoint
        self.mqtt_port = DEFAULT_MQTT_PORT
        self._log = MaxSizeList(LOG_SIZE)
        self.first_sample = True

        self.log("New virtual device...")
        self.log("CLIENT_ID: '{}'".format(name))
        self.log("ENDPOINT : '{}'".format(endpoint))
        ## The Device Defender scripts were written starting from: https://github.com/aws-samples/aws-iot-device-defender-agent-sdk-python/blob/master/AWSIoTDeviceDefenderAgentSDK/collector.py
        # Keep a copy of the last metric, if there is one, so we can calculate change in some metrics.
        self._last_metric = None
        

        # Logging method to print on stdout and store in memory for browser consumption
    def log(self, msg):
        ts = datetime.datetime.utcnow().isoformat()
        msg_formatted = "{} - {}".format(ts, str(msg))

        print(msg_formatted)
        self._log.push(msg_formatted)
    

    def log_enter_callback(self, function_name, payload, topic, qos):
        self.log(">{} - Received message '{}' on topic '{}' with QoS {}".format(function_name, str(payload), topic, str(qos)))


    def get_log_list(self):
        return self._log.get_list()


    def set_sampling_delay(self, sampling_delay):
        self.log(">set_sampling_delay '{}'".format(sampling_delay))

        self._sampling_delay = sampling_delay
        self._next_message_time = datetime.datetime.now()

        return

    def set_device_metrics_sampling_delay(self, device_metrics_sampling_delay):
        self.log(">set_device_metrics_sampling_delay '{}'".format(device_metrics_sampling_delay))

        self._device_metrics_sampling_delay = device_metrics_sampling_delay
        self._next_device_defender_telemetry = datetime.datetime.now()

        return

    def force_reconnect(self):
        self._force_reconnect = True


    def set_clean_disconnect(self, clean):
        self._clean_disconnect = clean


    def get_shadow(self, thing_name):
        self.log(">get_shadow")
        self._mqtt_client.publish("$aws/things/{}/shadow/get".format(thing_name), "", 0)

        return self.shadow


    def get_jobs(self, thing_name):
        self.log(">get_jobs / Publishing empty message to '{}'".format("$aws/things/{}/jobs/get".format(thing_name)))
        self._mqtt_client.publish("$aws/things/{}/jobs/get".format(thing_name), "", 0)


    def start_next_queued_job(self):
        self.log(">start_next_queued_job / Publish message to '{}'".format("$aws/things/{}/jobs/start-next".format(self.name)))

        req = {
            "statusDetails": {
                "string": JobStatus.IN_PROGRESS.name
            },
            "stepTimeoutInMinutes": 1,
        }

        self._mqtt_client.publish("$aws/things/{}/jobs/start-next".format(self.name), json.dumps(req), 0)
        self.log("<start_next_queued_job".format())

        return


    def generate_job_start_response_doc(self, response, version, timeout):
        status = JobStatus.FAILED

        if response:
            status = JobStatus.SUCCEEDED

        req = {
            "status": status.name,
            "expectedVersion": version,
            "stepTimeoutInMinutes": timeout,
        }

        return req


    def handle_jobs_start_next_callback(self, client, mid, message):
        self.log_enter_callback("handle_jobs_start_next_callback", message.payload, message.topic, message.qos)
        self.log(" handle_jobs_start_next_callback - Doing stuff...")

        my_json = message.payload.decode("utf8").replace("'", '"')
        payload = json.loads(my_json)

        self.log(" handle_jobs_start_next_callback\n{}".format(json.dumps(payload, indent=4, sort_keys=True)))

        job_id = payload["execution"]["jobId"]
        job_doc = payload["execution"]["jobDocument"]
        version = payload["execution"]["versionNumber"]

        self.log(" handle_jobs_start_next_callback - JOB_ID: '{}' JOB_VERSION: '{}'".format(job_id, version))
        self.log(" handle_jobs_start_next_callback - JOB_DOC:\n\n{}\n\n".format(json.dumps(job_doc, indent=4, sort_keys=True)))

        if "action" in job_doc:
            action = job_doc["action"]

            if action.lower() == "rotate-cert":
                self.log(" handle_jobs_start_next_callback - Rotating cert...")
                response = self.rotate_certificate(job_doc)
            elif action.lower() == "change-unit":
                self.log(" handle_jobs_start_next_callback - Changing unit...")
                response = self.change_unit(job_doc)
            elif action.lower() == "update-firmware":
                self.log(" handle_jobs_start_next_callback - Updating firmware...")
                response = self.update_firmware(job_doc)
            else:
                self.log(" handle_jobs_start_next_callback - Unknown action '{}'".format(action))
                response = False

        req = self.generate_job_start_response_doc(response, version, 1)

        self.log(" handle_jobs_start_next_callback - Finished the requested action - Success? {}".format(response))
        self.log(" handle_jobs_start_next_callback - Response Doc: \n\n{}\n\n".format(json.dumps(req, indent=4, sort_keys=True)))

        self._mqtt_client.publish("$aws/things/{}/jobs/{}/update".format(self.name, job_id), json.dumps(req), 0)

        self.log("<handle_jobs_start_next_callback - Notified / Published message to '{}'".format("$aws/things/{}/jobs/{}/update".format(self.name, job_id)))


    def stop(self):
        self.log(">stop")
        self._stop = True


    def change_unit(self, job_doc):
        self.log(">change_unit")

        if "unit" in job_doc:
            self.log("Changing unit...")
            self.unit = job_doc["unit"]

        self.log("<change_unit")

        return


    def handle_shadow_update_callback(self, client, mid, message):
        self.log_enter_callback("handle_shadow_update_callback", message.payload, message.topic, message.qos)

        my_json = message.payload.decode("utf8").replace("'", '"')
        payload = json.loads(my_json)

        self.shadow = payload

        with open("/tmp/shadow", "w") as file:
            file.write("%s" % json.dumps(payload))

        if "state" in payload:
            if "desired" in payload["state"]:
                self.log(payload["state"]["desired"])

        self.log("<handle_shadow_update_callback")

        return


    def handle_cmd_reply_callback(self, client, mid, message):
        self.log_enter_callback("handle_cmd_reply_callback", message.payload, message.topic, message.qos)

        my_json = message.payload.decode("utf8").replace("'", '"')
        payload = json.loads(my_json)

        if "type" in payload:
            type = payload["type"]
            session_id = payload["session-id"]
            response_topic = payload["response-topic"]

            #get_cmd_id()
            #do_stuff()
            #publish_reply(id)

            resp = {
                "session-id": session_id,
                "status": "OK"
            }

            self._mqtt_client.publish(response_topic, json.dumps(resp), 0)


        self.log("<handle_cmd_reply_callback")
        return


    def last_will(self):
        return


    def handle_shadow_get_callback(self, client, mid, message):
        self.log_enter_callback("handle_shadow_get_callback", message.payload, message.topic, message.qos)

        topic = str(message.topic)

        if "rejected" in topic:
            self.log(" handle_shadow_get_callback - Shadow get rejected")
        else:
            self.log(" handle_shadow_get_callback - Shadow get accepted")
            my_json = message.payload.decode("utf8").replace("'", '"')
            payload = json.loads(my_json)

            self.shadow = payload

            with open("/tmp/shadow", "w") as file:
                file.write("%s" % json.dumps(payload))

            if "state" in payload:
                if "desired" in payload["state"]:
                    self.log(payload["state"]["desired"])

        self.log("<handle_shadow_get_callback")

        return


    def handle_jobs_get_callback(self, client, mid, message):
        self.log_enter_callback("handle_jobs_get_callback", message.payload, message.topic, message.qos)

        my_json = message.payload.decode("utf8").replace("'", '"')
        payload = json.loads(my_json)
        queue_jobs = payload.get("queuedJobs")
        in_progress_jobs = payload.get("inProgressJobs")

        self.log(" handle_jobs_get_callback - CLIENT_ID '{}'".format(self.name))
        self.log(" handle_jobs_get_callback - QUEUE_JOBS '{}'".format(queue_jobs))
        self.log(" handle_jobs_get_callback - IN_PROGRESS_JOBS '{}'".format(in_progress_jobs))

        if queue_jobs:
            self.log(" handle_jobs_get_callback - There are jobs queued. Starting...")
            self.start_next_queued_job()
        elif in_progress_jobs:
            self.log(" handle_jobs_get_callback - There are jobs in progress...")
        else:
            self.log(" handle_jobs_get_callback - No outstanding jobs found")

        return


    def handle_jobs_notify_next_callback(self, client, mid, message):
        self.log_enter_callback("handle_jobs_notify_next_callback", message.payload, message.topic, message.qos)

        my_json = message.payload.decode("utf8").replace("'", '"')
        payload = json.loads(my_json)

        if 'execution' in payload :
            self.log("<handle_jobs_notify_next_callback - Pending jobs found, processing...")
            self.start_next_queued_job()
        else:
            self.log("<handle_jobs_notify_next_callback - NO PENDING JOB, NOTHING TO DO")

        return


    def handle_job_get_callback(self, client, mid, message):
        self.log_enter_callback("handle_job_get_callback", message.payload, message.topic, message.qos)

        my_json = message.payload.decode("utf8").replace("'", '"')
        payload = json.loads(my_json)

        return


    def update_firmware(self, job_doc):
        self.log(">update_firmware")

        success = False

        try: # Trying to be more resilient
            if 'firmware_file_url' not in job_doc:
                self.log(" update_firmware - firmware file not found")
                success = False
            else:
                firmware_file_url = job_doc['firmware_file_url']

                self.log(" update_firmware - Downloading firmware from '{}'".format(firmware_file_url))
                response = urllib.urlopen(firmware_file_url)
                self.log(" update_firmware - Downloaded\n{}".format(response.read()))

                # Doing stuff
                for i in range(1, 4):
                    self.log(" update_firmware - Installing... {}".format(i))
                    time.sleep(2)

                self.log(" update_firmware - Installed".format())

                success = True
        except Exception as e:
            self.log(e)
            success = False

        return success


    def rotate_certificate(self, job_doc):
        self.log(">rotate_certificate")

        success = False

        try: # Trying to be more resilient
            if 'config_file_url' not in job_doc:
                self.log(" rotate_certificate - config file not found")
                success = False
            else:
                cfg_file_url = job_doc['config_file_url']

                response = urllib.urlopen(cfg_file_url)
                cfg_file = json.loads(response.read())

                self.backup_files()
                self.prepare_files(json.dumps(cfg_file))
                self.force_reconnect()

                success = True

        except Exception as e:
            self.log(e)
            success = False

        return success


    # Connect to AWS IoT
    def connect(self, mqtt_shadow_client):
        self.log(">connect")

        connect_count = 0
        r = None

        try:
            self.log(" connect - Trying to connect '{}' '{}'...".format(self.endpoint, self.mqtt_port))
            r = mqtt_shadow_client.connect(30)
        except Exception as e:
            self.log(" connect - FAILED")
            self.log(e)

        while(not r and connect_count <= 10):
            try:
                time.sleep(5)
                self.log(" connect - Trying to connect '{}' '{}'...".format(self.endpoint, self.mqtt_port))
                r = mqtt_shadow_client.connect()
                connect_count += 1
            except Exception as e:
                self.log(" connect - FAILED")
                self.log(e)

        connected = False

        if (r):
            self.log(" connect - Device '{}' connected!".format(self.name))
            connected = True
        else:
            self.log(" connect - ERROR: Device '{}' NOT connected!".format(self.name))

        return connected


    '''
    SHADOW TOPICS
        $aws/things/{}/shadow/update/accepted
        $aws/things/{}/shadow/update/delta
        $aws/things/{}/shadow/update/documents
        $aws/things/{}/shadow/get/accepted
    '''
    def setup_shadow_callbacks(self, thing_name):
        # Subscribing only to accepted topics. In a production environment, the device should handle rejected messages as well.
        self._mqtt_client.subscribe("$aws/things/{}/shadow/get/+".format(thing_name), 0, self.handle_shadow_get_callback)
        self._mqtt_client.subscribe("$aws/things/{}/shadow/update/accepted".format(thing_name), 0, self.handle_shadow_update_callback)


    def setup_jobs_callbacks(self, thing_name):
        self.log("Subscribing to '{}' with callback '{}'".format("$aws/things/{}/jobs/notify-next".format(thing_name), "handle_jobs_notify_next_callback"))
        self._mqtt_client.subscribe("$aws/things/{}/jobs/notify-next".format(thing_name), 0, self.handle_jobs_notify_next_callback)

        self.log("Subscribing to '{}' with callback '{}'".format("$aws/things/{}/jobs/get/#".format(thing_name), "handle_jobs_get_callback"))
        self._mqtt_client.subscribe("$aws/things/{}/jobs/get/#".format(thing_name), 0, self.handle_jobs_get_callback)

        self.log("Subscribing to '{}' with callback '{}'".format("$aws/things/{}/jobs/+/get/+".format(thing_name), "handle_job_get_callback"))
        self._mqtt_client.subscribe("$aws/things/{}/jobs/+/get/+".format(thing_name), 0, self.handle_job_get_callback)

        self.log("Subscribing to '{}' with callback '{}'".format("$aws/things/{}/jobs/start-next/#".format(thing_name), "handle_jobs_start_next_callback"))
        self._mqtt_client.subscribe("$aws/things/{}/jobs/start-next/#".format(thing_name), 0, self.handle_jobs_start_next_callback)

        #self._mqtt_client.subscribe("$aws/things/{}/jobs/get/accepted".format(client_id), 1, handle_jobs_get_callback)
        #self._mqtt_client.subscribe("$aws/things/{}/jobs/get/rejected".format(client_id), 1, handle_jobs_get_callback)

        return


    def backup_files(self):
        self.log(">backup_files")

        os.rename("/tmp/iot_endpoint", "/tmp/iot_endpoint.bkp")
        os.rename("/tmp/device_name", "/tmp/device_name.bkp")
        os.rename("/tmp/cert", "/tmp/cert.bkp")
        os.rename("/tmp/key", "/tmp/key.bkp")
        os.rename("/tmp/rootCA.pem", "/tmp/rootCA.pem.bkp")

        self.log("<backup_files")

        return


    def prepare_files(self, cfg_file_str):
        cfg_file = json.loads(cfg_file_str)

        iot_endpoint = cfg_file["iot_endpoint"]

        with open("/tmp/iot_endpoint", "w") as file:
            file.write("%s" % iot_endpoint)

        dev_name = cfg_file["device_name"]

        with open("/tmp/device_name", "w") as file:
            file.write("%s" % dev_name)

        cert = cfg_file["cert"]

        with open("/tmp/cert", "w") as file:
            file.write("%s" % cert)

        key = cfg_file["key"]

        with open("/tmp/key", "w") as file:
            file.write("%s" % key)

        root_ca = cfg_file["root_ca"]

        with open("/tmp/rootCA.pem", "w") as file:
            file.write("%s" % root_ca)

        return


    def publish_external_ip(self):
        self.log(">publish_external_ip")
        external_ip = ""

        try:
            external_ip = urllib.urlopen('https://ident.me').read().decode('utf8')
            
            msg = {
                "device": self.name,
                "ip": str(external_ip)
            }

            payload = json.dumps(msg)

            self.log(" publish_external_ip - Publishing...")
            self._mqtt_client.publish("cmd/{}/event".format(self.name), payload, 0)
        except Exception as e:
            self.log(" publish_external_ip - Error getting IP '{}'".format(str(e)))
        
        self.log("<publish_external_ip - '{}'".format(external_ip))


    def publish(self, msg):
        self.log(">publish")
        
        try:
            payload = json.dumps(msg)
            topic = self.mqtt_telemetry_topic.format(self.name)

            self.log(" publish - Sending payload '{}' notification to '{}'...".format(payload, topic))
            self._mqtt_client.publish(topic, payload, 0)
        except Exception as e:
            self.log(" publish - Error" + str(e))
        
        self.log("<publish")


    def force_auth_error(self):
        self.log(">force_auth_error")
        
        try:
            payload = json.dumps({"auth": "error"})
            topic = "invalid-topic-for-error"

            self.log(" force_auth_error - Sending payload '{}' notification to '{}'...".format(payload, topic))
            self._mqtt_client.publish(topic, payload, 0)
        except Exception as e:
            self.log(" force_auth_error - Error" + str(e))
        
        self.log("<force_auth_error")

    def tamper(self):
        self.log(">tamper")
        
        try:
            msg = {
                "device": self.name,
                "tamper_type": "enclosure_violated"
            }

            payload = json.dumps(msg)
            topic = "cmd/{}/tamper".format(self.name)

            self.log(" tamper - Sending tamper notification to '{}'...".format(topic))
            self._mqtt_client.publish(topic, payload, 0)
        except Exception as e:
            self.log(" tamper - Error" + str(e))
        
        self.log("<tamper")


    def setup(self):
        self.log(">setup")

        mqtt_shadow_client = AWSIoTMQTTShadowClient(self.name)
        mqtt_shadow_client.disableMetricsCollection()

        # Configurations
        # For TLS mutual authentication
        mqtt_shadow_client.configureEndpoint(self.endpoint, self.mqtt_port)
        mqtt_shadow_client.configureCredentials("/tmp/rootCA.pem", "/tmp/key", "/tmp/cert")

        self._mqtt_client = mqtt_shadow_client.getMQTTConnection()
        self._mqtt_client.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
        self._mqtt_client.configureDrainingFrequency(2)  # Draining: 2 Hz
        self._mqtt_client.configureConnectDisconnectTimeout(10)  # 10 sec
        self._mqtt_client.configureMQTTOperationTimeout(5)  # 5 sec

        if self._lwt_topic:
            self.log(" setup - Setting LWT... '{}' / '{}'".format(self._lwt_topic, self._lwt_message))
            mqtt_shadow_client.configureLastWill(self._lwt_topic, self._lwt_message, 1)

        if not self.connect(mqtt_shadow_client):
            return

        # Create a deviceShadow with persistent subscription
        #deviceShadowHandler = myMQTTShadowClient.createShadowHandlerWithName(client_id, True)
        #shadowCallbackContainer_Bot = shadowCallbackContainer(deviceShadowHandler)

        time.sleep(2)

        #JOBS
        self.setup_jobs_callbacks(self.name)

        #SHADOW TOPICS
        self.setup_shadow_callbacks(self.name)

        #COMMAND / REPLY PATTERN
        self._mqtt_client.subscribe("cmd/ac/{}/req".format(self.name), 0, self.handle_cmd_reply_callback)

        return


    def start(self):
        self.log(">start")

        # reporting current ip
        self.publish_external_ip()

        # check any pending job
        self.log(" start - Checking for pending jobs...")
        self.get_jobs(self.name)

        # get shadow status
        self.log(" start - Getting shadow status...")
        self.get_shadow(self.name)

        #moving to self to allow fast configuration change
        self._next_message_time = datetime.datetime.now()

        while True:
            current_time = datetime.datetime.now()

            if self._next_message_time <= current_time:
                #payload = { "temp" : 30 }
                self.log(" start - Sampling delay {}".format(self._sampling_delay))
                topic = self.mqtt_telemetry_topic.format(self.name)

                self.log(" start - Sending to '{}' the payload below\n{}".format(topic, self.payload))
                self._mqtt_client.publish(topic, json.dumps(self.payload), 0)
                self._next_message_time = current_time + datetime.timedelta(0, self._sampling_delay)

            if self._next_device_defender_telemetry <= current_time and self.first_sample is not True:
                self.log(" start - Device Defender telemetry delay {}".format(self._device_metrics_sampling_delay))
                device_defender_metrics_topic = self.mqtt_device_defender_telemetry_topic.format(self.name)
                self.device_defender_metrics_payload = self.collect_metrics()
                self.log(" start - Sending to '{}' the payload below\n{}".format(device_defender_metrics_topic, self.device_defender_metrics_payload.to_json_string()))
                self._mqtt_client.publish(device_defender_metrics_topic, self.device_defender_metrics_payload.to_json_string(),0)
                self._next_device_defender_telemetry = current_time + datetime.timedelta(0, self._device_metrics_sampling_delay)
            
            if self.first_sample is True:
                self.collect_metrics()
                self.first_sample = False

            if self._pending_payloads:
                try:
                    p = self._pending_payloads.pop()
                    self._mqtt_client.publish(p.get("topic"), p.get("payload"), 0)
                except Exception:
                    self.log("Error")

            if self._stop: # Using next_message to stop the thread properly
                self.log(" start - Stopping...")
                if self._clean_disconnect:
                    self.log(" start - Disconnecting from the broker...")
                    self._mqtt_client.disconnect()
                    self.log("<start - Disconnected")
                else:
                    self.log("<start - Sudden disconnect...")

                break

            if self._force_reconnect:
                self.log(" start - Forcing reconnect...")
                self._mqtt_client.configureCredentials("/tmp/rootCA.pem", "/tmp/key", "/tmp/cert")
                self.connect(self._mqtt_client)
                self._force_reconnect = False

            time.sleep(0.5)


    def register_last_will_and_testament(self, topic, message):
        self.log(">register_last_will_and_testament")

        self._lwt_topic = topic
        self._lwt_message = message

        return ""
    
    @staticmethod
    def __get_interface_name(address):

        if address == '0.0.0.0' or address == '::':
            return address

        for iface in ps.net_if_addrs():
            for snic in ps.net_if_addrs()[iface]:
                if snic.address == address:
                    return iface

    def listening_ports(self, metrics):
        """
        Iterate over all inet connections in the LISTEN state and extract port and interface.
        """
        udp_ports = []
        tcp_ports = []
        for conn in ps.net_connections(kind='inet'):
            iface = self.__get_interface_name(conn.laddr.ip)
            if conn.status == "LISTEN" and conn.type == socket.SOCK_STREAM:
                if iface:
                    tcp_ports.append({'port': conn.laddr.port, 'interface': iface})
                else:
                    tcp_ports.append({'port': conn.laddr.port})
            if conn.type == socket.SOCK_DGRAM:  # on Linux, udp socket status is always "NONE"
                if iface:
                    udp_ports.append({'port': conn.laddr.port, 'interface': iface})
                else:
                    udp_ports.append({'port': conn.laddr.port})

        metrics.add_listening_ports("UDP", udp_ports)
        metrics.add_listening_ports("TCP", tcp_ports)

    @staticmethod
    def network_stats(metrics):
        net_counters = ps.net_io_counters(pernic=False)
        metrics.add_network_stats(
            net_counters.bytes_recv,
            net_counters.packets_recv,
            net_counters.bytes_sent,
            net_counters.packets_sent)

    @staticmethod
    def network_connections(metrics):
        protocols = ['tcp']
        for protocol in protocols:
            for c in ps.net_connections(kind=protocol):
                try:
                    if c.status == "ESTABLISHED" or c.status == "BOUND":
                        metrics.add_network_connection(c.raddr.ip, c.raddr.port,
                                                       VirtualDevice.__get_interface_name(c.laddr.ip),
                                                       c.laddr.port)
                except Exception as ex:
                    print('Failed to parse network info for protocol: ' + protocol)
                    print(ex)

    def collect_metrics(self):
        """Sample system metrics and populate a metrics object suitable for publishing to Device Defender."""
        metrics_current = metrics.Metrics(last_metric=self._last_metric)

        self.network_stats(metrics_current)
        self.listening_ports(metrics_current)
        self.network_connections(metrics_current)

        self._last_metric = metrics_current
        return metrics_current


class VirtualSwitch(VirtualDevice):

    target_device = "dev-NANN"

    def __init__(self, name, endpoint):
        VirtualDevice.__init__(self, name, endpoint)


    def set_target_device(self, target_device):
        self.target_device = target_device


    def press_on(self):
        self.log(">press_on")
        payload = json.dumps({"state": {"desired": {"status": "on"}}})
        self._mqtt_client.publish("$aws/things/{}/shadow/update".format(self.target_device), payload, 0)

        return


    def press_off(self):
        self.log(">press_off")
        payload = json.dumps({"state": {"desired": {"status": "off"}}})
        self._mqtt_client.publish("$aws/things/{}/shadow/update".format(self.target_device), payload, 0)

        return


class VirtualBulb(VirtualDevice):

    is_on = False

    def __init__(self, name, endpoint):
        VirtualDevice.__init__(self, name, endpoint)


class RogueDevice(VirtualDevice):

    def __init__(self, name, endpoint):
        VirtualDevice.__init__(self, name, endpoint)
        self.log(self.__class__)

    def start(self):
        self.log(">start")

        # reporting current ip
        self.publish_external_ip()

        # check any pending job
        self.log(" start - Checking for pending jobs...")
        self.get_jobs(self.name)

        # get shadow status
        self.log(" start - Getting shadow status...")
        self.get_shadow(self.name)

        #moving to self to allow fast configuration change
        self._next_message_time = datetime.datetime.now()

        while True:
            current_time = datetime.datetime.now()

            if self._next_message_time <= current_time:
                #payload = { "temp" : 30 }
                self.log(" start - Sampling delay {}".format(self._sampling_delay))
                topic = self.mqtt_telemetry_topic.format(self.name)

                self.log(" start - Sending to '{}' the payload below\n{}".format(topic, self.payload))
                self._mqtt_client.publish(topic, json.dumps(self.payload), 0)
                self._next_message_time = current_time + datetime.timedelta(0, self._sampling_delay)

            if random.randint(0, 1000) == 100:
                # do random rogue stuff
                act = random.randint(0, 2)

                if act == 0:
                    self.force_auth_error()
                elif act == 1:
                    letters = string.ascii_lowercase
                    msg = ''.join(random.choice(letters) for i in range(500))
                    payload = { "payload": msg }
                    self.publish(payload)
                elif act == 2:
                    self.tamper()

            if self._stop: # Using next_message to stop the thread properly
                self.log(" start - Stopping...")
                if self._clean_disconnect:
                    self.log(" start - Disconnecting from the broker...")
                    self._mqtt_client.disconnect()
                    self.log("<start - Disconnected")
                else:
                    self.log("<start - Sudden disconnect...")

                break

            if self._force_reconnect:
                self.log(" start - Forcing reconnect...")
                self._mqtt_client.configureCredentials("/tmp/rootCA.pem", "/tmp/key", "/tmp/cert")
                self.connect(self._mqtt_client)
                self._force_reconnect = False

            time.sleep(0.5)

class MaxSizeList(object):
    def __init__(self, size_limit):
        self.list = [None] * size_limit
        self.next = 0


    def push(self, item):
        self.list[self.next % len(self.list)] = item
        self.next += 1


    def get_list(self):
        if self.next < len(self.list):
            return self.list[:self.next]
        else:
            split = self.next % len(self.list)
            return self.list[split:] + self.list[:split]


# if __name__ == '__main__':
#     vd = VirtualDevice("dev-DDQA", "a1x30szgyfp50b-ats.iot.us-east-1.amazonaws.com")
#     vd.setup()
#     vd.start()
