from jira import JIRA
import pprint
from collections import Counter
from typing import cast
from jira.client import ResultList
from jira.resources import Issue
import os
import argparse
import json
import sys
import traceback


print("DO I EVEN START???")
parser = argparse.ArgumentParser(
                    prog = 'Get JIRA Cases',
                    description = 'Query JiRA for Pull Cases',
                    epilog = 'Text at the bottom of help')
parser.add_argument('--jira_pwd', dest='jira_pwd',required=True  )      # option that takes a value
parser.add_argument('--jiracases_filename', dest='jiracases_filename',required=True  )      # option that takes a value
parser.add_argument('--dryRun', action='store_true' )      # option that takes a value
parser.add_argument('--fixed_in_build', dest='fixed_in_build', required=False)

args = parser.parse_args()

dryRun = args.dryRun
#dryRun=False

if not os.path.isfile(args.jiracases_filename):
    print("File not found {}".format(args.jiracases_filename))
    sys.exit(1)

data = None
try:
  # 1. Read JSON file
  f = open(args.jiracases_filename)

  data = json.load(f)
except:
  print("[FATAL] Unable to read JSON aborting")
  sys.exit(1)

# 2. For Each Case in the JSON File Move it to CI-VERIFIED

jira = None
try:
    jira = JIRA(
    basic_auth=("ericom.build.machine@gmail.com", args.jira_pwd),  # a username/password tuple [Not recommended]
    server="https://cradlepoint.atlassian.net" )
except:
    print("[FATAL] cannot connect jira verify username and password")
    sys.exit(1)
    

# Function use to move Cases
def getNextTransition(issue,name):
    transitions = jira.transitions(issue)
    for t in transitions:
        #print (t['id'], t['name']) 
        if (t['to']['name']==name):
            return t['id']
        
def moveCastState(issue,newState):
    NextStateNumber=getNextTransition(issue,newState)
    if dryRun:
        print ("[DEBUG] Dry Run - Going to change state to cases {} to {}".format(issue,NextStateNumber))
    else:
        jira.transition_issue(issue,NextStateNumber)

def update_fixed_in_build(issue, fixed_in_build):
    issue.update(fields={'customfield_12542': fixed_in_build}) # CP Jira - Fixed in Build

for x in data['cases']:
    try:
        issue=jira.issue(x)
        issue_type = issue.fields.issuetype.name
        
        if x.startswith("SHIELD-") or x.startswith("AC-"):
            print("Moving case:{} to CI-Verified".format(x))
            moveCastState(x,"CI-Verified")
            if args.fixed_in_build is not None:
                update_fixed_in_build(issue, args.fixed_in_build)
        elif issue_type == "Escalation":
            print("Moving {} type issue - case:{} to Pending Release".format(issue_type, x))
            moveCastState(x,"Pending Release")
        else:
            print("Moving {} type issue - case:{} to Review/In Test".format(issue_type, x))
            moveCastState(x,"Review/In Test")        
    except:
        print ("Exception While trying to move the case {} to CI-Verified or Review/In Test state".format(x))
        traceback.print_exc()
