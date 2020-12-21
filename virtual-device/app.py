# home.py
from flask import Flask, render_template, request, url_for, redirect, flash, current_app
import os
import sys
import json
import threading
import atexit
import json
import time
import random
import string
from virtual_device import VirtualDevice, VirtualSwitch, VirtualBulb, RogueDevice

# Not a good practice =\
global vd

PORT = int(os.getenv("PORT", "80"))

mqtt_thread = threading.Thread()

def create_app(cfg_file):
    app = Flask(__name__)
    app.secret_key = 'aws-iot-playground'
    app.config['SESSION_TYPE'] = 'filesystem'


    def interrupt():
        current_app.logger.info(">interrupt")

        global mqtt_thread
        global vd

        print(">Stopping virtual device...")
        vd.stop()

        mqtt_thread.join()

        print("<interrupt")

        return


    @app.route("/")
    def home():
        global vd
        name = vd.name
        return render_template("index.html", message="This is IoT Device Playground", name=name, img_file="bulb-off.png", type="bulb_off")

    @app.route("/press_on")
    def press_on():
        global vd
        vd.press_on()
        return render_template("index.html", message="This is IoT Device Playground", img_file="bulb-off.png", type="bulb_off")

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


    @app.route("/config", methods=['GET', 'POST'])
    def config():
        data = ""
        global vd

        if (request.args.get('time') or (request.form.get('fsampling') != '' and request.form.get('fsampling') is not None)):
            time = request.args.get('time') or request.form.get('fsampling')
            print("Changing time to '{}'...".format(time))

            try:
                vd.set_sampling_delay(int(time))
                data = str(time)
            except Exception as e:
                print(e)
                data = e

        if (request.args.get('ddm_sr') or (request.form.get('ddm_sr') != '' and request.form.get('ddm_sr') is not None)):
            device_metrics_time = request.args.get('ddm_sr') or request.form.get('ddm_sr')
            print("Changing Device Metrics topic to '{}'...".format(device_metrics_time))

            try:
                vd.set_device_metrics_sampling_delay(int(device_metrics_time))
                data = str(device_metrics_time)
            except Exception as e:
                print(e)
                data = e        

        if (request.args.get('topic') or (request.form.get('ftopic') != '' and request.form.get('ftopic') is not None)):
            topic = request.args.get('topic') or request.form.get('ftopic')
            print("Changing topic to '{}'...".format(topic))

            try:
                data = topic
                vd.mqtt_telemetry_topic = topic
            except Exception as e:
                print(e)
                data = e
        
        if (request.args.get('payload') or (request.form.get('fpayload') != '' and request.form.get('fpayload') is not None)):
            payload = request.args.get("payload") or request.form.get('fpayload')
            try:
                p = json.loads(payload)
                vd.payload = p
            except Exception as e:
                print(e)
                data = e

        return render_template("config.html", message=data)


    @app.route("/log")
    def log():
        global vd

        log_list = vd.get_log_list()

        return render_template("log.html", log_list=log_list)
    

    @app.route("/help")
    def help():
        return render_template("help.html")


    @app.route("/actions", methods=['GET', 'POST'])
    def actions():
        global vd

        if request.method == 'POST':
            current_app.logger.info(" actions - POST")
            action = request.form['action']
            current_app.logger.info(" actions - POST - {}".format(action))

            if action == "tamper":
                vd.tamper()
                return render_template("tamper.html", img_file="switch.png")
            elif action == "reconnect":                
                current_app.logger.info("Forcing reconnection...")
                vd.force_reconnect()
                flash("Forcing reconnection")
            elif action == "clean":
                current_app.logger.info("Clean disconnect...")
                flash("Clean disconnect")
                try:
                    vd.set_clean_disconnect(True)
                except Exception as e:
                    current_app.logger.info(e)
            elif action == "large":
                current_app.logger.info("Large payload...")
                flash("Large payload")

                letters = string.ascii_lowercase
                msg = ''.join(random.choice(letters) for i in range(500))
                payload = { "payload": msg }
                
                try:
                    vd.publish(payload)
                    current_app.logger.info("Large payload published")
                except Exception as e:
                    current_app.logger.info(e)
                    flash("Error sending payload")
            elif action == "autherr":
                current_app.logger.info("Auth error...")
                flash("Auth error")

                try:
                    vd.force_auth_error()
                    current_app.logger.info("Auth error")
                except Exception as e:
                    current_app.logger.info(e)
                    flash("Error sending payload")

            else:
                flash("Invalid action.")
        else:    
            flash("All the form fields are required.")
        
        return redirect(url_for("home"))
        # return render_template("index.html", message="This is IoT Device Playground", img_file="bulb-off.png", type="bulb_off")

    
    ######## HELPER FUNCTIONS #################


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
        elif dev_type == "rogue":
            vd = RogueDevice(client_id, endpoint)
        else:
            print("unknown device type...")

        lwt = {
            "msg": "Ouch Charlie...that really hurt",
            "device": client_id
        }

        vd.register_last_will_and_testament("cmd/{}/lwt".format(client_id), json.dumps(lwt))

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

    if os.environ.get('DEBUG') == 'true':
        response = open("{}/local/config.json".format(os.path.dirname(os.path.realpath(__file__))), "r")
    else:
        response = urllib.urlopen(os.environ.get('CONFIG_FILE_URL'))
    
    cfg_file = json.loads(response.read())

    app = create_app(cfg_file)
    
    app.debug = True
    app.run(threaded=True, host='0.0.0.0', port=PORT, use_reloader=False)
