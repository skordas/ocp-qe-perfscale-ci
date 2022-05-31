#!/usr/bin/env python3

import sys
import json
import yaml
import pathlib
import subprocess
import argparse
import requests
import urllib3
import datetime


# disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# directory constants 
ROOT_DIR = str(pathlib.Path(__file__).parent.parent)
SCRIPT_DIR = ROOT_DIR + '/scripts'
DATA_DIR = ROOT_DIR + '/data'

# NOPE constants
THANOS_URL = ''
TOKEN = ''
YAML_FILE = ''
QUERIES = {}
RESULTS = {}
DEBUG = False

# query constants
IS_RANGE = False
START_TIME = None
END_TIME = None
STEP = None


def run_query(query):

	# construct request
	headers = {"Authorization": f"Bearer {TOKEN}"}
	if IS_RANGE:
		endpoint = f"{THANOS_URL}/api/v1/query_range"
		params = {
			'query': query,
			'start': START_TIME,
			'end': END_TIME,
			'step': STEP
		}
	else:
		endpoint = f"{THANOS_URL}/api/v1/query"
		params = {
			'query': query
		}

	# make request and return data
	data = requests.get(endpoint, headers=headers, params=params, verify=False)
	if DEBUG:
		print(f"\nMade GET request with following URL: {data.request.url}")
	return data.json()


def run_commands(commands, outputs={}):

	# iterate through commands dictionary
	for command in commands:
		if DEBUG:
			print(f"\nExecuting command '{' '.join(commands[command])}' to get {command} data")
		result = subprocess.run(commands[command], capture_output=True, text=True)

		# record command stdout if execution was succesful
		if result.returncode == 0:
			output = result.stdout[1:-1]
			if DEBUG:
				print(f"Got back result: {output}")
			outputs[command] = output

		# otherwise raise an Exception with stderr
		else:
			raise Exception(f"Command '{command}' execution resulted in stderr output: {result.stderr}")

	# if all commands were successful return outputs dictionary
	return outputs


def get_netobserv_env_info():

	# intialize info and base_commands objects
	info = {}
	base_commands = {
		"release": ['oc', 'get', 'pods', '-l', 'app=network-observability-operator', '-o', 'jsonpath="{.items[0].metadata.labels.version}"'],
		"flp_kind": ['oc', 'get', 'flowcollector', '-o', 'jsonpath="{.items[*].spec.flowlogsPipeline.kind}"'],
		"loki_pvc_cap": ['oc', 'get', 'pvc/loki-store', '-o', 'jsonpath="{.status.capacity.storage}"'],
		"agent": ['oc', 'get', 'flowcollector', '-o', 'jsonpath="{.items[*].spec.agent}"']
	}

	# collect data from cluster about netobserv operator and store in info dict
	info = run_commands(base_commands)

	# get agent details based on detected agent (should be ebpf or ipfix)
	agent = info["agent"]
	agent_commands = {
		"sampling": ['oc', 'get', 'flowcollector', '-o', f'jsonpath="{{.items[*].spec.{agent}.sampling}}"'],
		"cache_active_time": ['oc', 'get', 'flowcollector', '-o', f'jsonpath="{{.items[*].spec.{agent}.cacheActiveTimeout}}"'],
		"cache_max_flows": ['oc', 'get', 'flowcollector', '-o', f'jsonpath="{{.items[*].spec.{agent}.cacheMaxFlows}}"']
	}

	# collect data from cluster about agent and append to info dict
	info = run_commands(agent_commands, info)

	# return all collected data
	return info


def main():

	# get operator data
	RESULTS["netobservEnv"] = get_netobserv_env_info()

	# get prometheus data
	for entry in QUERIES:
		metric_name = entry['metricName']
		query = entry['query']
		RESULTS[metric_name] = run_query(query)

	# ensure data directory exists (create if not)
	pathlib.Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

	# write prometheus data to data directory
	with open(DATA_DIR + '/data.json', 'w') as data_file:
		json.dump(RESULTS, data_file)

	# exit if no issues
	print(f"\nData captured successfully and written to {DATA_DIR}")
	sys.exit(0)


if __name__ == '__main__':

	# sanity check that kubeconfig is set
	result = subprocess.run(['oc', 'whoami'], capture_output=True, text=True)
	if result.returncode != 0:
		print("Could not connect to cluster - ensure all the Prerequistie steps in the README were followed")
		sys.exit(1)

	# initialize argument parser
	parser = argparse.ArgumentParser(description='Network Observability Prometheus and Elasticsearch tool (NOPE)')

	# set customization flags
	parser.add_argument("--yaml_file", type=str, default='netobserv-metrics.yaml', help='YAML file from which to source Prometheus queries - defaults to "netobserv-metrics.yaml"')
	parser.add_argument("--user-workloads", default=False, action='store_true', help='Flag to query userWorkload metrics. Ensure FLP service and service-monitor are enabled and some network traffic exists.')
	parser.add_argument("--starttime", type=str, help='Start time for range query - must be used in conjuncture with --endtime and --step')
	parser.add_argument("--endtime", type=str, help='End time for range query - must be used in conjuncture with --starttime and --step')
	parser.add_argument("--step", type=str, help='Step time for range query - must be used in conjuncture with --starttime and --endtime')
	parser.add_argument("--debug", default=False, action='store_true', help='Flag for additional debug messaging')

	# parse arguments
	args = parser.parse_args()

	# check if range query arguments are valid and if so set constants
	START_TIME = args.starttime
	END_TIME = args.endtime
	STEP = args.step
	if all(v is None for v in [START_TIME, END_TIME, STEP]):
		IS_RANGE = False
	elif any(v is None for v in [START_TIME, END_TIME, STEP]):
		print("START_TIME, END_TIME, and STEP must all be used together or not at all")
		sys.exit(1)
	else:
		print("\nParsed Start Time: " + datetime.datetime.fromtimestamp(int(START_TIME)).strftime('%I:%M%p%Z on %m/%d/%Y'))
		print("Parsed End Time:   " + datetime.datetime.fromtimestamp(int(END_TIME)).strftime('%I:%M%p%Z on %m/%d/%Y'))
		IS_RANGE = True

	# determine if running in debug mode or not
	DEBUG = args.debug
	if DEBUG:
		print('\nDebug mode is enabled')

	# get thanos URL from cluster
	THANOS_URL = subprocess.run(['oc', 'get', 'route', 'thanos-querier', '-n', 'openshift-monitoring', '-o', 'jsonpath="{.spec.host}"'], capture_output=True, text=True).stdout
	THANOS_URL = "https://" + THANOS_URL[1:-1]
	print(f"\nTHANOS_URL: {THANOS_URL}")

	# get token from cluster
	user_workloads = args.user_workloads
	if user_workloads:
		TOKEN = subprocess.run(['oc', 'sa', 'get-token', 'prometheus-user-workload', '-n', 'openshift-user-workload-monitoring'], capture_output=True, text=True).stdout
		if TOKEN == '':
			print("No token could be found - ensure all the Prerequistie steps in the README were followed")
			sys.exit(1)
	else:
		TOKEN = subprocess.run(['oc', 'whoami', '-t'], capture_output=True, text=True).stdout
		TOKEN = TOKEN[:-1]
	print(f"TOKEN: {TOKEN}")

	# get YAML file with queries
	YAML_FILE = args.yaml_file
	print(f"YAML_FILE: {YAML_FILE}")

	# set queries constant with data from YAML file
	try:
		with open(SCRIPT_DIR + '/' + YAML_FILE, 'r') as yaml_file:
			QUERIES = yaml.safe_load(yaml_file)
	except Exception as e:
		print(f'Failed to read YAML file {YAML_FILE}: {e}')
		sys.exit(1)

	# begin main program execution
	main()