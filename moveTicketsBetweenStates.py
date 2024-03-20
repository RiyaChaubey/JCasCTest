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
    # TODO: CP new project names
    payload = "{ \n  \"jql\": \"project in (XSWG, XRBI, XCSB, XSSP, PEZTE) AND Status = " + state + "\"\n}"
    multilog.info("get_issues_of_state payload - {}".format(payload))
    response = request_jira(url_params, "POST", url, payload)
    data = json.loads(response.text.encode('utf-8'))["issues"]
    multilog.debug("get_issues_of_state() total issues:".format(len(data)))
    return data

def trans_from_jira(issue, to_state, multilog, url_params):
    try:
        url = f"issue/{issue}/transitions"
        response = request_jira(url_params, "GET", url)
        data = json.loads(response.text.encode())
        for trans in data['transitions']:
            multilog.debug(f"{trans['id']} - to {trans['to']['name']}")
            if trans['to']['name'] == to_state:
                return trans['id']
    except Exception as e:
        multilog.info("Failed getting transitions for ticket {} - {}".format(issue, str(e)))
    return None


def get_issue_transition(issue, from_state, to_state, multilog, url_params):
    new_trans = trans_from_jira(issue, to_state, multilog, url_params)
    if new_trans is not None:
        return new_trans

def get_issue_tech_domains(issue, multilog, url_params):
    url = "issue/{}".format(issue)
    response = request_jira(url_params, "GET", url)
    # multilog.debug(f"get_issue_tech_domain response: {response.text.encode()}")
    data = json.loads(response.text.encode())
    tech_domain_field = "customfield_12549" # CP Jira Tech Domain
    if tech_domain_field in data["fields"]:
        multilog.debug(f"Ticket has property: {data['fields'][tech_domain_field]}")
        tech_domains = [str(x["value"]) for x in data["fields"][tech_domain_field]]
        multilog.debug(f"get_issue_tech_domain type: {tech_domains}")
        return tech_domains
    return ""


def transition_ticket(issue, from_state, to_state, multilog, url_params, assigneeId, specialAssigneeId):
    multilog.debug("transition_ticket() issueNum{}\n".format(issue) )
    transition = get_issue_transition(issue=issue, from_state=from_state, to_state=to_state,multilog=multilog, url_params=url_params)
    response = True
    if transition is not None:
        multilog.debug("transition_ticket() transition string {}".format(transition))
        url = "issue/{}/transitions".format(issue)
        payload = '{\n\t"transition": {\n\t\t"id":"' + str(transition) + '"\n\t}\t\n}'
        multilog.debug("The payload is: {}".format(payload))
        response = request_jira(url_params, "POST", url, payload)
        if response.status_code == 204:
            multilog.debug("transition_ticket() response ok")
            response = True
        else:
            multilog.debug("transition_ticket() response fail")
            response = False

        if assigneeId is not None:
            if specialAssigneeId is not None:
                try:
                    multilog.debug(f"Consider special assignee {specialAssigneeId}")
                    parts = specialAssigneeId.split(":")
                    if len(parts) == 2:
                        tech_domain = parts[0]
                        tech_assignee = parts[1]
                        multilog.debug(f"The specialAssigneeId is: {parts[0]} and {parts[1]}")
                        ticket_tech_domains = get_issue_tech_domains(issue, multilog, url_params)
                        multilog.debug(f"The tech domain: {ticket_tech_domains}")
                        if len(ticket_tech_domains) > 0:
                            if tech_domain in ticket_tech_domains:
                                multilog.debug(f"Ticket has special tech domain - use {tech_assignee} as assignee")
                                assigneeId = tech_assignee
                    else:
                        multilog.debug(f"Invalid special assignee parameter {specialAssigneeId}. Ignoring")
                except:
                    multilog.debug(f"exception raised working on case {issue}")
            payload = '{"fields":{"customfield_12554": {"accountId": "' + str(assigneeId) + '" }}}' # CP Jira - Testing owner
            multilog.debug("The payload is: {}".format(payload))
            url = "issue/{}".format(issue)
            response = request_jira(url_params, "PUT", url, payload)
            if response.status_code < 400:
                multilog.debug("Setting testing owner passed OK")
                response = True
            else:
                multilog.debug("Setting testing owner failed")
                response = False
    else:
        multilog.fatal("transition_ticket failed finding transition for issue {}".format(issue))
        return False
    return response


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    parser = argparse.ArgumentParser()
    parser.add_argument('--fromState', required=True, help='The state to move from')
    parser.add_argument('--toState', required=True, help='The state to move to')
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
    print("Lets go!")
    print("{}-{}-log.txt".format(args.fromState, args.toState))
    multilog = prepare_multi_log("{}-{}-log.txt".format(args.fromState, args.toState))
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
        try:
            multilog.debug("MainLoop: working on case {}".format(key))
            summary = str(issue["fields"]["summary"])
            multilog.debug("Case desc {}".format(summary))
            if transition_ticket(key, args.fromState, args.toState, multilog, url_params, args.assigneeId, args.specialAssigneeId):
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
