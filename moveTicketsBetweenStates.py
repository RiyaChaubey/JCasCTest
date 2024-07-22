import requests
import json
from requests.auth import HTTPBasicAuth
import sys
import traceback
import argparse
import urllib3

# Setting up Logging class to send output to both CONSOLE and FILE
import logging
from logging import handlers
import os


# Setting up Logger
def prepare_multi_log(out_file_mname):
    multilog = logging.getLogger('')
    multilog.setLevel(logging.DEBUG)
    Fileformat = logging.Formatter("%(asctime)-15s [%(levelname)s] %(funcName)s: %(lineno)d  %(message)s" )
    Consoleformat = logging.Formatter("{\"msg\":\"%(message)s\" ,\"name\":\"defaultLogger\",\"hostname\":\"" +
        str(os.environ.get('HOSTNAME')) + "\",\"pid\":13,\"logType\":\"flow\",\"logSystemID\":\"" + str(os.environ.get('CLUSTER_SYSTEM_ID')) +
        "\", \"MessageType\": \"operational\",\"Component\":\"logstash\", \"level\":50,\"time\":\"%(asctime)-15s\",\"v\":0} ",datefmt="%m-%d-%Y,%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(Consoleformat)
    multilog.addHandler(ch)

    fh = handlers.RotatingFileHandler(out_file_mname, maxBytes=(1048576*5), backupCount=7)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(Fileformat)
    multilog.addHandler(fh)
    logging.getLogger("requests").setLevel(logging.WARNING)
    return multilog


def request_jira(url_params, method, url, data=""):
    if data != "":
        return requests.request(method, "{}/{}".format(url_params['baseUrl'], url), headers=url_params['headers'], auth=HTTPBasicAuth(url_params['username'], url_params['password']), data=data)
    else:
        return requests.request(method, "{}/{}".format(url_params['baseUrl'], url), headers=url_params['headers'], auth=HTTPBasicAuth(url_params['username'], url_params['password']))


def get_issues_of_state(state, multilog, url_params):
    multilog.debug("get_issues_of_state - {}".format(state))
    url = "search"
    payload = "{ \n  \"jql\": \"project in (PEZTE) AND Status = '" + state + "'\"\n}"
    multilog.info("get_issues_of_state payload - {}".format(payload))
    response = request_jira(url_params, "POST", url, payload)
    data = json.loads(response.text.encode('utf-8'))["issues"]
    multilog.debug("get_issues_of_state() total issues:".format(len(data)))
    return data


def add_labels_to_tickets(issue, multilog, url_params, new_label):
    url = "issue/{}".format(issue)
    response = request_jira(url_params, "GET", url)
    data = json.loads(response.text.encode())
    if "labels" in data["fields"]:
        payload = '{"fields": {"labels": ["' + new_label + '"]}}'
        multilog.debug("The payload is: {}".format(payload))
        response = request_jira(url_params, "PUT", url, payload)
        if response.status_code < 400:
            multilog.debug("add_labels_to_tickets() response ok")
            response = True
        else:
            multilog.debug("add_labels_to_tickets() response fail")
            response = False


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    parser = argparse.ArgumentParser()
    parser.add_argument('--fromState', required=True, help='The state to move from')
    parser.add_argument('--addLabel', required=True, help='Label to add to Tickets')
    parser.add_argument('--password', required=True, help='The users password')
    parser.add_argument('--changeLogFile', required=True, help='The file to write the log to')
    parser.add_argument('--assigneeId', required=False, help='The ID of the person to assign to. Will not assign if not provided')
    parser.add_argument('--specialAssigneeId', required=False, help='Pair of tech domain and assignee ID, seperated by ":". If the ticket has this tech domain - use this assignne')
    parser.add_argument('--ticketIDsFile', required=False, help='The file to write the list of ticket IDs to')
    args = parser.parse_args()
    url_params = {'username': "ericom.build.machine@gmail.com",
                  'password': args.password,
                  'baseUrl': 'https://cradlepoint.atlassian.net/rest/api/3',
                  'headers': {
                      'Content-Type': 'application/json'
                  }
                  }
    multilog = prepare_multi_log("{}-log.txt".format(args.fromState.replace('/In ', '')))
    handled_issues = {}
    issues = get_issues_of_state(args.fromState, multilog, url_params)
    if len(issues) == 0:
        multilog.info("No tickets in state {}".format(args.fromState))
        return
    for issue in issues:
        if issue is None or not 'key' in issue:
            multilog.fatal("issue is incompatible JSON format")
            continue

        key = str(issue["key"])
        # remove this; only for testing
        if key not in ('PEZTE-1013', 'PEZTE-1015', 'PEZTE-1039'):
            continue
        try:
            multilog.debug("MainLoop: working on case {}".format(key))
            summary = str(issue["fields"]["summary"])
            multilog.debug("Case desc {}".format(summary))
            if add_labels_to_tickets(key, multilog, url_params, args.addLabel):
                handled_issues[key] = summary
        except:
            multilog.fatal("exception raised working on case {}".format(key))
            traceback.print_exc()

    to_print = ""
    for key, value in handled_issues.items():
        to_print += "- " + key.replace("\\", "") + " - " + value + " \\n"
    to_print = to_print.replace("\'", "")
    to_print = to_print.replace("\"", "")
    to_print = to_print.replace("\$", "")
    print(to_print)
    file1 = open(args.changeLogFile, 'w')
    file1.write(to_print)
    file1.close()
    try:
        if args.ticketIDsFile is not None:
            with open(args.ticketIDsFile, "w") as tickets_file:
                tickets_file.write( ",".join(handled_issues.keys()))
    except Exception as e:
        multilog.fatal("Failed saving ticket numbers - {}".format(str(e)))


if __name__ == '__main__':
    main()
