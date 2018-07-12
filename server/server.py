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
    APPLICATION_URL = os.environ['APPLICATION_URL']

except KeyError:
    print("Environmental variables BANDWIDTH_USER_ID, BANDWIDTH_API_TOKEN, BANDWIDTH_API_SECRET, GOOGLE_APPLICATION_CREDENTIALS, and APPLICATION_URL must be set")
    sys.exit(-1)


app_url = "https://api.catapult.inetwork.com/v1/users/<userId>/applications/".replace("<userId>", BANDWIDTH_USER_ID)
token = BANDWIDTH_API_TOKEN
secret = BANDWIDTH_API_SECRET
u_auth = (token, secret)
application_name = APPLICATION_URL + " Cluecon Demo"

current_applications = requests.get(app_url, auth=u_auth).json()
app_exists = False
for application in current_applications:
    if application['name'] == application_name:
        app_exists = True
        break

if not app_exists:
    body = {
        "name": APPLICATION_URL + " Cluecon Demo",
        "incomingCallUrl": APPLICATION_URL + "/voice",
        "incomingMessageUrl": APPLICATION_URL + "/messages",
        "autoAnswer": "false",
        "callbackHttpMethod": "POST"
    }
    requests.post(
        app_url,
        auth=u_auth,
        json=body,
    )

"""
Dictionary to hold flow json for trigger types: Call, SMS, and Now
    Call = execute flow on voice callback
    SMS = execute flow on messaging callback
    Now = execute flow immediately
"""
flows = {}

"""
Subscriptions list for SSEs
"""
subscriptions = [Queue()]

"""
Global variables for waiting on outside events
    Ex: A speak event needs to wait for an end event
"""
waitingOn = ""
waitOnEventJSONString = ""
recordingIndex = 0
toNumber = ""
fromNumber = ""
message = ""

"""
Mapping of events to relevant IDs
"""
event_to_last_id = {
    'incomingcall': 'callId',
    'gather': 'callId',
    'speak': 'callId',
    'recording': 'callId',
    'answer': 'callId',
}

"""
Storage of relevant IDs
"""
last_ids = {
    'default': '',
}

"""
Main engine that processes flow json and sends requests or performs
specified actions defined by flow.
"""

def executeFlow(flow, nodeid, request, trigger_method, trigger_id=""):
    def notify(node):
        for sub in subscriptions[:]:
            sub.put(node)

    nodes = flow['nodes']
    seeking = True

    for i, node in enumerate(nodes):

        """
        Seek specified node logic
        """
        if seeking == True and node['node-id'] != nodeid:
           continue
        else: 
           seeking = False

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
            global waitOnEventJSONString    
            global waitingOn
            global last_ids
            global event_to_last_id
            global fromNumber
            global toNumber
            global message

            url = node['url'].replace("<user_id>", BANDWIDTH_USER_ID)
            token = BANDWIDTH_API_TOKEN
            secret = BANDWIDTH_API_SECRET
            u_auth = (token, secret)
            last_id = None
            

            if 'text' in node['body']:
                if node['body']['from'] == "":
                    node['body']['from'] = toNumber
                if node['body']['to'] == "":
                    node['body']['to'] = fromNumber   
                if node['body']['text'] == "":
                    node['body']['text'] = message      
            if 'waitOnEvent' in node:
                event = node['waitOnEvent']
                if event in event_to_last_id and event_to_last_id[event] in last_ids:
                    last_id = event_to_last_id[event]
                else:
                    last_id = 'default'

                waitingOn = node['waitOnEvent']
                trigger_id = last_ids[last_id]
                if waitingOn == "gather": 
                    nextNode = node['node-id']
                elif waitingOn == "answer" and i+1 < len(nodes):
                    nextNode = nodes[i+1]['node-id']
                elif waitingOn == "speak" and i+1 < len(nodes):
                    nextNode = nodes[i+1]['node-id']
                elif waitingOn == "playback" and i+1 < len(nodes):
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
            else:
                waitOnEventJSONString = ''
                waitingOn = ""
            
            url = url.replace("<trigger_id>", trigger_id)

            if method.lower() == 'get':
                r = requests.get(
                    url,
                    auth=u_auth,
                )
            elif method.lower() == 'post':
                body = node['body']
                if 'calls' in url:
                    body['callbackUrl'] = APPLICATION_URL + "/voice"
                r = requests.post(
                    url,
                    auth=u_auth,
                    json=body,
                )

                if "Location" in r.headers:
                   return_url = r.headers['Location']
                   if last_id is not None and last_id != 'default':
                       last_ids[last_id] = return_url.split("/")[-1]
            else:
                print("Only GET and POST http methods are supported")
                exit(-1)

            if len(waitOnEventJSONString) > 0:
                return '', 200
        time.sleep(1)
    return '', 200 

"""
Default function to play when user input during a gather or record is not understood
"""

def execute_input_not_understood():
    global last_ids
    token = BANDWIDTH_API_TOKEN
    secret = BANDWIDTH_API_SECRET
    u_auth = (token, secret)

    url = 'https://api.catapult.inetwork.com/v1/users/<user_id>/calls/<trigger_id>/audio'
    url = url.replace("<user_id>", BANDWIDTH_USER_ID)
    url = url.replace("<trigger_id>", last_ids['callId'])
    body = {
        'gender': 'female', 
        'locale': 'en_US', 
        'sentence': 'Your response was not understood. Please retry', 
        'voice': 'susan'
    }

    r = requests.post(
        url,
        auth=u_auth,
        json=body
    )

    time.sleep(3)

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
    print(flow)
    if trigger == "Now":
       return executeFlow(flow, flow['nodes'][0]['node-id'], request, 'Now')
    else:
       flows[trigger] = flow
    return '', 200

"""
Route to handle messaging callbacks and pass over to execution
"""

@app.route('/messages', methods=['POST'])
def executeMessageFlow():
    global fromNumber
    global toNumber
    global message
    request_data_json = json.loads(request.data)
    message = request_data_json['text']
    fromNumber = request_data_json['from']
    toNumber = request_data_json['to']
    return executeFlow(flows['SMS'], flows['SMS']['nodes'][0]['node-id'], request, 'SMS') 

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

    if request_data_json['eventType'] == "incomingcall":
        id_to_set = event_to_last_id["incomingcall"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id
        recordingIndex = 0
        return executeFlow(flows['Call'], flows['Call']['nodes'][0]['node-id'], request, 'Call', trigger_id=call_id)

    elif request_data_json['eventType'] == "answer" and waitingOn == "answer":
        id_to_set = event_to_last_id["answer"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id
        tag_json = json.loads(waitOnEventJSONString)
        return executeFlow(flows[tag_json['triggerMethod']], tag_json['nextNode'], request, tag_json['triggerMethod'], trigger_id=call_id)

    elif request_data_json['eventType'] == "gather" and waitingOn == "gather":
        id_to_set = event_to_last_id["gather"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id
        tag_json = json.loads(waitOnEventJSONString)
        #seek for node id...if we don't find node id:
        # post a speak prompt
        # reexecute listen node
        found = False
        nextNode = ""
        if 'digits' in request_data_json:
            for node in flows[tag_json['triggerMethod']]['nodes']:
                nextNode = tag_json['nextNode'] + ":" + request_data_json['digits']
                for node in flows[tag_json['triggerMethod']]['nodes']:
                    if node['node-id'] == nextNode:
                       found = True
                       break

        if not found:
            execute_input_not_understood()
            nextNode = tag_json['nextNode']

        return executeFlow(flows[tag_json['triggerMethod']], nextNode, request, tag_json['triggerMethod'], trigger_id=call_id)

    elif request_data_json['eventType'] == "speak" and request_data_json['state']=="PLAYBACK_STOP" and waitingOn == "speak":
        id_to_set = event_to_last_id["speak"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id
        tag_json = json.loads(waitOnEventJSONString)
        return executeFlow(flows[tag_json['triggerMethod']], tag_json['nextNode'], request, tag_json['triggerMethod'], trigger_id=call_id)   

    elif request_data_json['eventType'] == "playback" and request_data_json['status']=="done" and waitingOn == "playback":
        id_to_set = event_to_last_id["playback"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id
        tag_json = json.loads(waitOnEventJSONString)
        return executeFlow(flows[tag_json['triggerMethod']], tag_json['nextNode'], request, tag_json['triggerMethod'], trigger_id=call_id) 

    elif request_data_json['eventType'] == "recording" and waitingOn == "recording":
        print("recording")
        id_to_set = event_to_last_id["recording"]
        call_id = request_data_json[id_to_set]
        last_ids[id_to_set] = call_id
        word = transcribe_file(request_data_json['callId'])
        tag_json = json.loads(waitOnEventJSONString)
        #seek for node id...if we don't find node id:
        # post a speak prompt
        # reexecute listen node
        nextNode = tag_json['nextNode'] + ":" + word.strip()
        found = False
        for node in flows[tag_json['triggerMethod']]['nodes']:
            if node['node-id'] == nextNode:
               found = True
               break

        if not found:
            execute_input_not_understood()
            nextNode = tag_json['nextNode']

        return executeFlow(flows[tag_json['triggerMethod']], nextNode, request, tag_json['triggerMethod'], trigger_id=call_id)    

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
   #test timeout of recordIndex
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
    transcription = ''
   except sr.RequestError as e:
    print("Could not request results from Google Cloud Speech service; {0}".format(e))
    transcription = ''
   
   os.remove(audio_file)

   return str(transcription).lower()

   

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
