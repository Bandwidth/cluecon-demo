import os
import time
import requests
import sys
import json
from flask import Flask, render_template, request, send_from_directory

app = Flask(__name__, static_folder='../static/Build', template_folder='../static')

try:
    BANDWIDTH_USER_ID = os.environ['BANDWIDTH_USER_ID']
    BANDWIDTH_API_TOKEN = os.environ['BANDWIDTH_API_TOKEN']
    BANDWIDTH_API_SECRET = os.environ['BANDWIDTH_API_SECRET']

except KeyError:
    print("Environmental variables BANDWIDTH_USER_ID, BANDWIDTH_API_TOKEN, and BANDWIDTH_API_SECRET must be set")
    sys.exit(-1)

"""
Dictionary to hold flow json for trigger types: Call, SMS, and Now
    Call = execute flow on voice callback
    SMS = execute flow on messaging callback
    Now = execute flow immediately
"""

flows = {}

"""
Main engine that processes flow json and sends requests or performs
specified actions defined by flow.
"""

def executeFlow(flow, nodeid, trigger_id, request):
    nodes = flow['nodes']
    for i in range(int(nodeid), len(nodes)):
        node = nodes[i]
        method = node['method']
        if method.lower() == 'wait':
            time.sleep(int(node['seconds']))
        else:
            url = node['url'].replace("<trigger_id>", trigger_id)
            url = url.replace("<user_id>", BANDWIDTH_USER_ID)
            token = BANDWIDTH_API_TOKEN
            secret = BANDWIDTH_API_SECRET
            u_auth = (token, secret)
            if method.lower() == 'get':
                r = requests.get(
                    url,
                    auth=u_auth
                )
                print(r.json())
            elif method.lower() == 'post':
                body = node['body']
                r = requests.post(
                    url,
                    auth=u_auth,
                    json=body
                )
                print(r)
                if "location" in r.headers:
                   return_url = r.headers['location']
                   trigger_id = return_url.split("/")[-1]
            else:
                print("Only GET and POST http methods are supported")
                exit(-1)
    return '', 200 

"""
Route to serve up UI
"""

@app.route('/')
def index():
    return render_template('index.html')

"""
Route to receive flows from UI and stuff them into the flow dictionary by trigger 
"""

@app.route('/', methods=['POST'])
def post():
    trigger = request.form['trigger']
    flow = json.loads(request.form['flow'])
    flows[trigger] = flow
    if trigger == "Now":
       return executeFlow(flow, 0, "", request)
    else:
       flows[trigger] = flow
    return '', 200

"""
Route to handle messaging callbacks and pass over to execution
"""

@app.route('/messages')
def executeMessageFlow():
    message_id = request.args.get('messageId')
    return executeFlow(flows['SMS'], 0, messageId, request) 

"""
Route to handle voice callbacks and pass over to execution
"""

@app.route('/voice')
def executeCallFlow():
    call_id = request.args.get('callId')
    if request.args.get('eventType') == "incomingcall":
        return executeFlow(flows['Call'], 0, call_id, request) 
    else:
        return '', 200

@app.route('/static/TemplateData/<path:filename>')
def custom_static(filename):
    return send_from_directory('../static/TemplateData', filename)

if __name__ == '__main__':
    app.run()
