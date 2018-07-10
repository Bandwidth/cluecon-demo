import os
import time
import requests
import sys
import json
import gevent
import speech_recognition as sr
from gevent.pywsgi import WSGIServer
from gevent.queue import Queue
from flask import Flask, render_template, request, send_from_directory, Response

app = Flask(__name__, static_folder='../static/Build', template_folder='../static')

try:
    BANDWIDTH_USER_ID = os.environ['BANDWIDTH_USER_ID']
    BANDWIDTH_API_TOKEN = os.environ['BANDWIDTH_API_TOKEN']
    BANDWIDTH_API_SECRET = os.environ['BANDWIDTH_API_SECRET']
    GOOGLE_SPEECH_AUTH_FILE = os.environ['GOOGLE_APPLICATION_CREDENTIALS']

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
waitingOn = ""
waitOnEventJSONString = ""
recordingIndex = 0

event_to_last_id = {
    'incomingcall': 'callId',
    'gather': 'callId',
    'speak': 'callId',
    'recording': 'callId',
}

last_ids = {
    #'default': {
    #    'id': '',
    #    'node-id': ''
    #}
    'default': '',
}

"""
Main engine that processes flow json and sends requests or performs
specified actions defined by flow.
"""

def executeFlow(flow, nodeid, request, trigger_method):
    def notify(node):
        for sub in subscriptions[:]:
            sub.put(node)

    nodes = flow['nodes']
    if nodeid != "0":
       seeking = True
    else:
       seeking = False

    for i, node in enumerate(nodes):

        print("seeking:" + nodeid + " in " + node['node-id'])

        if seeking == True and node['node-id'] != nodeid:
           continue
        else: 
           seeking = False
           print(node['node-id'])

        if node['node-id'] == "END":
            return '', 200

        if 'method' in node:
            method = node['method']
        else:
            continue

        gevent.spawn(notify("<NODEON>:"+node['node-id']))

        if method.lower() == 'wait':
            time.sleep(int(node['seconds']))
        else:
            url = node['url'].replace("<user_id>", BANDWIDTH_USER_ID)
            token = BANDWIDTH_API_TOKEN
            secret = BANDWIDTH_API_SECRET
            u_auth = (token, secret)

            global waitOnEventJSONString    
            global waitingOn
            last_id = None
            if 'waitOnEvent' in node:
                global last_ids
                global event_to_last_id
                event = node['waitOnEvent']
                if event in event_to_last_id and event_to_last_id[event] in last_ids:
                    last_id = event_to_last_id[event]
                else:
                    last_id = 'default'
                    waitingOn = node['waitOnEvent']

                trigger_id = last_ids[last_id]
                url = url.replace("<trigger_id>", trigger_id)
                print("waiting on: " + waitingOn)
                if waitingOn == "gather": 
                    nextNode = node['node-id']
                elif waitingOn == "answer" and i+1 < len(nodes):
                    nextNode = nodes[i+1]['node-id']
                elif waitingOn == "speak" and i+1 < len(nodes):
                    nextNode = nodes[i+1]['node-id']
                elif waitingOn == "recording":
                    nextNode = nodes[i-2]['node-id']    
                else:
                    nextNode = None
                waitOnEventJSONString = json.dumps({
                    'waitOnEvent': waitingOn,
                    'nextNode': nextNode,
                    'triggerMethod': trigger_method,
                })
                print(waitOnEventJSONString)
            else:
                waitOnEventJSONString = ''
                waitingOn = ""
                url = url.replace("<trigger_id>", "")

            if method.lower() == 'get':
                r = requests.get(
                    url,
                    auth=u_auth,
                )
            elif method.lower() == 'post':
                body = node['body']
                r = requests.post(
                    url,
                    auth=u_auth,
                    json=body,
                )

                print(url)
                print(r)
                if "location" in r.headers:
                   return_url = r.headers['location']
                   #trigger_id = return_url.split("/")[-1]
                   if last_id is not None and last_id != 'default':
                       last_ids[last_id] = return_url.split("/")[-1]
            else:
                print("Only GET and POST http methods are supported")
                exit(-1)

            if len(waitOnEventJSONString) > 0:
                print('returned')
                return '', 200
        time.sleep(1)
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
    print(request.form['flow'])
    flow = json.loads(request.form['flow'])
    flows[trigger] = flow
    print(flow)
    if trigger == "Now":
       return executeFlow(flow, "0", request, 'Now')
    else:
       flows[trigger] = flow
    return '', 200

"""
Route to handle messaging callbacks and pass over to execution
"""

@app.route('/messages')
def executeMessageFlow():
    message_id = request.args.get('messageId')
    return executeFlow(flows['SMS'], "0", request, 'SMS') 

"""
Route to handle voice callbacks and pass over to execution
"""

@app.route('/voice', methods=["POST"])
def executeCallFlow():
    global waitingOn
    global recordingIndex
    global waitOnEventJSONString
    global last_ids
    request_data_json = json.loads(request.data)
    print(request_data_json)

    if request_data_json['eventType'] == "incomingcall":
        id_to_set = event_to_last_id["incomingcall"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id

        recordingIndex = 0
        return executeFlow(flows['Call'], "0", request, 'Call')

    elif request_data_json['eventType'] == "answer" and waitingOn == "answer":
        id_to_set = event_to_last_id["answer"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id

        tag_json = json.loads(waitOnEventJSONString)
        return executeFlow(flows[tag_json['triggerMethod']], tag_json['nextNode'], request, tag_json['triggerMethod'])

    elif request_data_json['eventType'] == "gather" and waitingOn == "gather":
        id_to_set = event_to_last_id["gather"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id

        tag_json = json.loads(waitOnEventJSONString)
        nextNode = tag_json['nextNode'] + ":" + request_data_json['digits']
        return executeFlow(flows[tag_json['triggerMethod']], nextNode, request, tag_json['triggerMethod'])

    elif request_data_json['eventType'] == "speak" and request_data_json['state']=="PLAYBACK_STOP" and waitingOn == "speak":
        id_to_set = event_to_last_id["speak"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id

        tag_json = json.loads(waitOnEventJSONString)
        return executeFlow(flows[tag_json['triggerMethod']], tag_json['nextNode'], request, tag_json['triggerMethod'])   

    elif request_data_json['eventType'] == "recording" and waitingOn == "recording":
        id_to_set = event_to_last_id["recording"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id

        word = transcribe_file(request_data_json['callId'])
        tag_json = json.loads(waitOnEventJSONString)
        nextNode = tag_json['nextNode'] + ":" + word.strip()
        return executeFlow(flows[tag_json['triggerMethod']], nextNode, request, tag_json['triggerMethod'])    

    else:
        return '', 200

"""
Google Speech
"""
def transcribe_file(callId):
   """
   download speech file
   """
   global recordingIndex
   recordingIndex = recordingIndex + 1
   url = "https://api.catapult.inetwork.com/v1/users/<user_id>/media/" + callId + "-" + str(recordingIndex) + ".wav";
   url = url.replace("<user_id>", BANDWIDTH_USER_ID)
   token = BANDWIDTH_API_TOKEN
   secret = BANDWIDTH_API_SECRET
   u_auth = (token, secret)
   r = requests.get(
       url,
       auth=u_auth
   )
   audio_file = callId+"-"+str(recordingIndex) +".wav"
   open(audio_file, 'wb').write(r.content)
   googleAuth = open(GOOGLE_SPEECH_AUTH_FILE, 'r').read()

   r = sr.Recognizer() 
   with sr.AudioFile(audio_file) as source:
       audio = r.record(source)

   # recognize speech using Google Cloud Speech
   try:
    transcription = r.recognize_google_cloud(audio, googleAuth)
    print("Google Cloud Speech thinks you said " + transcription)
   except sr.UnknownValueError:
    print("Google Cloud Speech could not understand audio")
   except sr.RequestError as e:
    print("Could not request results from Google Cloud Speech service; {0}".format(e))
   
   os.remove(audio_file)

   return str(transcription)

   

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
