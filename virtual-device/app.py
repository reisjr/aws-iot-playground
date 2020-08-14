# home.py
from flask import Flask, render_template, request, url_for
import os
import sys
import json
import threading
import atexit
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import json
import boto3
import time
from virtual_device import VirtualDevice, VirtualSwitch, VirtualBulb

# Not a good practice =\
global vd

PORT = int(os.getenv("PORT", "80"))

mqtt_thread = threading.Thread()


def create_app(cfg_file):
    app = Flask(__name__)

    def interrupt():
        print(">interrupt")

        global mqtt_thread
        global vd

        print(">Stopping virtual device...")
        vd.stop()

        mqtt_thread.join()

        print("<interrupt")

        return


    @app.route("/")
    def home():
        return render_template("index.html", message="This is IoT Device Playground", img_file="bulb_off.png", type="bulb_off")

    @app.route("/press_on")
    def press_on():
        global vd
        vd.press_on()
        return render_template("index.html", message="This is IoT Device Playground", img_file="bulb_off.png", type="bulb_off")

    @app.route("/press_off")
    def press_off():
        global vd
        vd.press_off()
        return render_template("index.html", message="This is IoT Device Playground", img_file="switch.png", type="switch")

    @app.route("/cert")
    def cert():
        data = ""

        with open('/tmp/cert', 'r') as file:
            data = file.read()  #.replace('\n', '')

        return render_template("cert.html", message=data)

    # @app.route("/key")
    def key():
        data = ""

        with open('/tmp/key', 'r') as file:
            data = file.read()  #.replace('\n', '')

        return data


    @app.route("/endpoint")
    def endpoint():
        data = ""

        with open('/tmp/iot_endpoint', 'r') as file:
            data = file.read()  #.replace('\n', '')

        return render_template("endpoint.html", message=data)


    @app.route("/name")
    def name():
        data = ""

        with open('/tmp/device_name', 'r') as file:
            data = file.read()  #.replace('\n', '')

        return data


    @app.route("/shadow")
    def shadow():
        global vd

        data = ""
        data = json.dumps(vd.get_shadow(vd.name))
        print(data)

        #time.sleep(2)

        #with open('/tmp/shadow', 'r') as file:
        #    data = file.read()#.replace('\n', '')

        return render_template("endpoint.html", message=data)


    @app.route("/config")
    def config():
        data = ""
        global vd

        if "time" in request.args:
            time = request.args.get('time')
            print("Changing time to '{}'...".format(time))

            try:
                vd.set_sampling_delay(int(time))
                data = str(time)
            except Exception as e:
                print(e)
                data = e

        if "reconnect" in request.args:
            reconnect = request.args.get('reconnect')
            print("Reconnect '{}'...".format(reconnect))
            vd.force_reconnect()


        if "clean" in request.args:
            clean = request.args.get('clean')
            print("Disconnect clean '{}'...".format(clean))

            try:
                vd.set_clean_disconnect(clean)
            except Exception as e:
                print(e)
                data = e

        if "topic" in request.args:
            topic = request.args.get('topic')
            print("Changing topic to '{}'...".format(topic))

            try:
                vd.mqtt_telemetry_topic = topic
                data = topic
            except Exception as e:
                print(e)
                data = e

        return render_template("config.html", message=data)

    @app.route("/log")
    def log():
        global vd

        log_list = vd.get_log_list()

        return render_template("log.html", log_list=log_list)


    def get_client_id(cfg_file):
        return cfg_file["device_name"]


    def get_endpoint(cfg_file):
        return cfg_file["iot_endpoint"]

    def get_device_type(cfg_file):
        return cfg_file.get("device-type", "generic")

    def run_virtual_device(cfg_file_json):
        global vd

        cfg_file = json.loads(cfg_file_json)

        client_id = get_client_id(cfg_file)
        endpoint = get_endpoint(cfg_file)
        dev_type = get_device_type(cfg_file)

        if dev_type == "generic":
            vd = VirtualDevice(client_id, endpoint)
        elif dev_type == "bulb":
            vd = VirtualBulb(client_id, endpoint)
        elif dev_type == "switch":
            vd = VirtualSwitch(client_id, endpoint)
        else:
            print("unknown device type...")

        lwt = {
            "msg": "Ouch Charlie...that really hurt",
            "device": client_id
        }

        vd.register_last_will_and_testament("lwt", json.dumps(lwt))

        vd.prepare_files(cfg_file_json)
        vd.setup()
        vd.start()

        return

    def start_virtual_device(cfg_file):
        # Do initialisation stuff here
        global mqtt_thread

        # Create your thread
        mqtt_thread = threading.Thread(target=run_virtual_device, args=(json.dumps(cfg_file),))
        mqtt_thread.start()

    # Initiate
    start_virtual_device(cfg_file)

    # When you kill Flask (SIGTERM), clear the trigger for the next thread
    atexit.register(interrupt)

    return app


if __name__ == '__main__':
    print(os.getenv('CONFIG_FILE_URL', ""))

    cfg_file = {
        "iot_endpoint": "a1x30szgyfp50b-ats.iot.us-east-1.amazonaws.com",
        "device_name": "dev-DDQA",
        "cert": "dev-1",
        "root_ca": "root_ca",
        "key": "dev-1",
        "device-type": "generic",
        "controlled-device": ""
    }

    if sys.version[0:1] == '3':
        import urllib.request as urllib
    else:
        import urllib as urllib

    response = urllib.urlopen(os.environ['CONFIG_FILE_URL'])
    cfg_file = json.loads(response.read())

    app = create_app(cfg_file)

    app.run(threaded=True, host='0.0.0.0', port=PORT)
