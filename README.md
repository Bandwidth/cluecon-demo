# cluecon-demo

## Installation

### User requirements
* You must have a Bandwidth account (https://app.bandwidth.com/)
* You must have a Google Cloud account (???)
* You must have a Ngrok account (https://ngrok.com/)

### System requirements
* Python version = 3.7.0
* Ngrok
* git

Instructions for downloading Python 3.7.0 can be found here https://www.python.org/downloads/

Instructions for downloading Ngrok can be found here https://ngrok.com/download

Git can be downloaded by running the following command
```
sudo apt-get install git
```

### Launching Ngrok
After installing Ngrok, it can be launched by running the following command:
```
ngrok http 5000
```

You will see a screen that looks like this:

![alt text](images/ngrok_url_example.png)

Take note of the HTTPS Forwarding URL. You will need this later in setting up the demo.

Leave this command running, and open a new terminal window

### Repo setup

1. Navigate to the directory that will hold the project
2. Run the following commands to setup the repo
```
git clone git@github.com:Bandwidth/cluecon-demo.git
cd cluecon-demo
pip install virtualenv
virtualenv -p python3 cluecon-demo-virtualenv
source cluecon-demo-virtualenv/bin/activate
pip install -r requirements.txt
```

If done properly, the beginning of your prompt should look like this:
```
(cluecon-demo-virtualenv)
```

And running the command
```
pip freeze
```
should result in an output like this:
```
alabaster==0.7.11
Babel==2.6.0
cachetools==2.1.0
certifi==2018.4.16
chardet==3.0.4
click==6.7
dill==0.2.8.2
docutils==0.14
Flask==1.0.2
future==0.16.0
gevent==1.3.4
google-api-core==0.1.4
google-api-python-client==1.7.3
google-auth==1.5.0
google-auth-httplib2==0.0.3
google-cloud-core==0.25.0
google-cloud-language==1.0.2
google-cloud-monitoring==0.28.1
google-cloud-resource-manager==0.28.1
google-cloud-runtimeconfig==0.28.1
google-cloud-speech==0.34.0
google-cloud-storage==1.6.0
google-cloud-translate==1.3.1
google-resumable-media==0.3.1
googleapis-common-protos==1.5.3
greenlet==0.4.13
httplib2==0.11.3
idna==2.7
imagesize==1.0.0
itsdangerous==0.24
Jinja2==2.10
MarkupSafe==1.0
nine==1.0.0
oauth2client==3.0.0
packaging==17.1
ply==3.8
protobuf==3.6.0
pyasn1==0.4.3
pyasn1-modules==0.2.2
Pygments==2.2.0
pyparsing==2.2.0
pytz==2018.5
requests==2.19.1
rsa==3.4.2
seven==1.0.0
six==1.11.0
snowballstemmer==1.2.1
SpeechRecognition==3.8.1
Sphinx==1.7.5
sphinxcontrib-websupport==1.1.0
style==1.1.0
update==0.0.1
uritemplate==3.0.0
urllib3==1.23
Werkzeug==0.14.1
```

### Environmental variables

The following environmental variables must be set

```
BANDWIDTH_USER_ID
BANDWIDTH_API_TOKEN
BANDWIDTH_API_SECRET 
GOOGLE_APPLICATION_CREDENTIALS
URL
```

Your Bandwidth credentials can be found here https://app.bandwidth.com/account/profile

![alt text](images/bandwidth_credentials.png)

Your Google application credentials can be found here ???
<images showing how to download the file>

The url to set is your Ngrok URL shown above

### Launching the application
Once setup with Ngrok, the cluecon-demo-virtualenv virtual environment, and the environmental variables, launch the application by running
```
python server/server.py
```

You should be able to go to your https Ngrok url and see the home page of the application
