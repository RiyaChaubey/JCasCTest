import requests
import json
from requests.auth import HTTPBasicAuth
import sys
import traceback
import os
import git
import argparse
import pprint
import logging
from logging.handlers import RotatingFileHandler
from logging import handlers
import os
import urllib3
from jira import JIRA
import pprint
from collections import Counter
from typing import cast
from jira.client import ResultList
from jira.resources import Issue
import logging
from logging.handlers import RotatingFileHandler
from logging import handlers
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TODO: Make sure build.sbt file exists or abort
# TODO: Make sure environment variable BUILD_NUMBER exists

# Credentials for Jira 
username = "ericom.build.machine@gmail.com"
ticketTypes = ['SHIELD-', 'AC-', 'XSWG-', 'XRBI-', 'XCSB-', 'XSSP-', 'PEZTE-']


def should_be_included(issue):
    issue_state = issue.fields.status.name.lower()
    if issue_state in ("pull", "ready", "dev-done", "in review"):
        return True
    else:
        return False


#######                    MAIN                    #######
parser = argparse.ArgumentParser(
                    prog='Get JIRA Cases',
                    description='Query JiRA for Pull Cases',
                    epilog='Text at the bottom of help')
parser.add_argument('--jira_pwd', dest='jira_pwd')      # option that takes a value
parser.add_argument('--versionNum', dest='versionNum')      # option that takes a value
parser.add_argument('--ticketsFile', dest='ticketsFile', required=False)
args = parser.parse_args()

# Setting up Logging class to send output to both CONSOLE and FILE
# Setting up Logger

multilog = logging.getLogger('')
multilog.setLevel(logging.DEBUG)
Fileformat = logging.Formatter("%(asctime)-15s [%(levelname)s] %(funcName)s: %(lineno)d  %(message)s" )
Consoleformat = logging.Formatter("{\"msg\":\"%(message)s\" ,\"name\":\"defaultLogger\",\"hostname\":\"" +
    str(os.environ.get('HOSTNAME')) + "\",\"pid\":13,\"logType\":\"flow\",\"logSystemID\":\"" + str(os.environ.get('CLUSTER_SYSTEM_ID')) +
    "\", \"MessageType\": \"operational\",\"Component\":\"logstash\", \"level\":50,\"time\":\"%(asctime)-15s\",\"v\":0} ",datefmt="%m-%d-%Y,%H:%M:%S")


# ch = logging.StreamHandler(sys.stdout)
# ch.setLevel(logging.INFO)
# ch.setFormatter(Consoleformat)
# multilog.addHandler(ch)
#
fh = handlers.RotatingFileHandler("updateJiraTicket_trace.txt", maxBytes=(1048576*5), backupCount=7)
fh.setLevel(logging.DEBUG)
fh.setFormatter(Fileformat)
multilog.addHandler(fh)
logging.getLogger("requests").setLevel(logging.WARNING)

jira = JIRA(
    basic_auth=("ericom.build.machine@gmail.com", args.jira_pwd),  # a username/password tuple [Not recommended]
    server="https://cradlepoint.atlassian.net")
jira.myself()

IssuesInPull = []
if args.ticketsFile is not None:
    ticketsList = []
    with open(args.ticketsFile, 'r') as ticketsFile:
        ticketsList = json.load(ticketsFile)
    for ticket in ticketsList:
        multilog.info(f"Checking ticket: {ticket}")
        # TODO: CP new project names
        if any(ticket.startswith(part) for part in ticketTypes):
            try:
                issue = jira.issue(ticket)
                if should_be_included(issue):
                    multilog.info(f"Ticket {ticket} should be included")
                    IssuesInPull.append(issue)
                else:
                    multilog.info(f"Ticket {ticket} should not be included (not in pull or dev-done)")
                if hasattr(issue.fields, 'parent'):
                    multilog.info(f"Ticket {ticket} has parent - {issue.fields.parent}")
                    parent = jira.issue(issue.fields.parent)
                    if should_be_included(parent):
                        multilog.info(f"Parent {parent.key} should be included")
                        IssuesInPull.append(parent)
                    else:
                        multilog.info(f"Parent {parent.key} should not be included (not in pull or dev-done)")
                else:
                    multilog.info(f"Ticket {ticket} does not have a parent")
            except Exception as e:
                multilog.info(f"Failed getting information for ticket {ticket} - {str(e)}")
        else:
            multilog.info(f"Invalid ticket name: {ticket}")
else:
    # TODO: CP new project names
    IssuesInPull = jira.search_issues("project in (SHIELD, AC, XSWG, XRBI, XCSB, XSSP, PEZTE) AND Resolution = Done AND Status in ('In Review', Pull)")

workspace = os.getenv('WORKSPACE')
myJson = {}
myJson['cases'] = []
for x in IssuesInPull:
    jira.add_comment(x.key, "compiled on shieldbuild {}".format(os.getenv('BUILD_NUMBER')))
    myJson['cases'].append(x.key)

# If no cases in POOL
myJson['shield-build'] = os.getenv('BUILD_NUMBER')
# Init Repo
repo = git.Repo(workspace)
#/home/jenkins/workdir/workspace/SB/shield-build
myJson['commitID'] = repo.head.object.hexsha
# Read JSON
with open(workspace+'/build.sbt', 'r') as fcc_file:
    fcc_data = json.load(fcc_file)

# Tagim shieldBuild.jenkinsfile
myJson['tags'] = {}

for x in fcc_data['rootKey']:
    myJson['tags'][x]=args.versionNum

print(json.dumps(myJson))