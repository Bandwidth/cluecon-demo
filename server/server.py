import os
import time
import requests
import sys
import json
import gevent
from gevent.pywsgi import WSGIServer
from gevent.queue import Queue
from flask import Flask, render_template, request, send_from_directory, Response

app = Flask(__name__, static_folder='../static/Build', template_folder='../static')

try:
    BANDWIDTH_USER_ID = os.environ['BANDWIDTH_USER_ID']
    BANDWIDTH_API_TOKEN = os.environ['BANDWIDTH_API_TOKEN']
    BANDWIDTH_API_SECRET = os.environ['BANDWIDTH_API_SECRET']
    NGROK_URL = os.environ['NGROK_URL']

except KeyError:
    print("Environmental variables BANDWIDTH_USER_ID, BANDWIDTH_API_TOKEN, BANDWIDTH_API_SECRET, and NGROK_URL must be set")
    sys.exit(-1)

"""
Dictionary to hold flow json for trigger types: Call, SMS, and Now
    Call = execute flow on voice callback
    SMS = execute flow on messaging callback
    Now = execute flow immediately
"""

flows = {}
subscriptions = [Queue()]

"""
Main engine that processes flow json and sends requests or performs
specified actions defined by flow.
"""

def executeFlow(flow, nodeid, trigger_id, request, trigger_method):
    def notify(node):
        for sub in subscriptions[:]:
            sub.put(node)

    nodes = flow['nodes']
    for i in range(int(nodeid), len(nodes)):
        node = nodes[i]
        gevent.spawn(notify(node))
        method = node['method']
        if method.lower() == 'wait':
            time.sleep(int(node['seconds']))
        else:
            url = node['url'].replace("<trigger_id>", trigger_id)
            url = url.replace("<user_id>", BANDWIDTH_USER_ID)
            token = BANDWIDTH_API_TOKEN
            secret = BANDWIDTH_API_SECRET
            u_auth = (token, secret)

            if 'waitOnEvent' in node:
                waitOnEventJSONString = json.dumps({
                    'waitOnEvent': node['waitOnEvent'],
                    'nextNode': i+1,
                    'triggerMethod': trigger_method,
                    'triggerId': trigger_id,
                })
            else:
                waitOnEventJSONString = ''

            if method.lower() == 'get':
                r = requests.get(
                    url,
                    auth=u_auth,
                )
            elif method.lower() == 'post':
                body = node['body']
                body['tag'] = waitOnEventJSONString
                body['callbackUrl'] = NGROK_URL + '/voice'
                r = requests.post(
                    url,
                    auth=u_auth,
                    json=body,
                )
                if "location" in r.headers:
                   return_url = r.headers['location']
                   trigger_id = return_url.split("/")[-1]
            else:
                print("Only GET and POST http methods are supported")
                exit(-1)

            if len(waitOnEventJSONString) > 0:
                return '', 200

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
       return executeFlow(flow, 0, "", request, 'Now')
    else:
       flows[trigger] = flow
    return '', 200

"""
Route to handle messaging callbacks and pass over to execution
"""

@app.route('/messages')
def executeMessageFlow():
    message_id = request.args.get('messageId')
    return executeFlow(flows['SMS'], 0, messageId, request, 'SMS') 

"""
Route to handle voice callbacks and pass over to execution
"""

@app.route('/voice', methods=['POST'])
def executeCallFlow():
    request_data_json = json.loads(request.data)
    if request_data_json['eventType'] == "incomingcall":
        call_id = request_data_json['callId']
        return executeFlow(flows['Call'], 0, call_id, request, 'Call')

    elif request_data_json['eventType'] == "answer":
        tag = request_data_json['tag']
        tag_json = json.loads(tag)
        return executeFlow(flows[tag_json['triggerMethod']], int(tag_json['nextNode']), tag_json['triggerId'], request, tag_json['triggerMethod'])

    else:
        return '', 200

@app.route('/static/TemplateData/<path:filename>')
def custom_static(filename):
   return send_from_directory('../static/TemplateData', filename)

class ServerSentEvent(object):

    def __init__(self, data):
        self.data = data
        self.event = None
        self.id = None
        self.desc_map = {
            self.data : "data",
            self.event : "event",
            self.id : "id"
        }

    def encode(self):
        if not self.data:
            return ""
        lines = ["%s: %s" % (v, k)
                 for k, v in self.desc_map.items() if k]

        return "%s\n\n" % "\n".join(lines)

@app.route('/sse_push')
def sse_push():
    def gen():
        q = Queue()
        subscriptions.append(q)
        try:
            while True:
                result = q.get()
                ev = ServerSentEvent(str(result))
                yield ev.encode()
        except GeneratorExit:
            subscriptions.remove(q)

    return Response(gen(), mimetype="text/event-stream")

if __name__ == '__main__':
    app.debug = True
    server = WSGIServer(("", 5000), app)
    server.serve_forever()
