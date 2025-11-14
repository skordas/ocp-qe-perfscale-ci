import json
import os
import requests

# TODOs
# add upgrades to rehearse_history

version_to_check = os.getenv("OCP_XY_VERSION")
prow_url = "https://prow.ci.openshift.org"
trt_version_url = f"https://amd64.ocp.releases.ci.openshift.org/api/v1/releasestreams/approvals?team=trt&prefix={version_to_check}.0-0.nightly&index=0"
name_pattern = rf"^{version_to_check}\.0-0\.nightly-\d{{4}}-\d{{2}}-\d{{2}}-\d{{6}}$"  # Match ex: 4.21.0-0.nightly-2025-11-13-055313
print(f"Version to check: {version_to_check}")
job_id =  ""

rehearses = {
    "control-plane-120nodes": {
        "history_url" : f"{prow_url}/job-history/gs/test-platform-results/logs/periodic-ci-openshift-eng-ocp-qe-perfscale-ci-main-aws-{version_to_check}-nightly-x86-control-plane-120nodes",
        "job_url" : f"{prow_url}/view/gs/test-platform-results/logs/periodic-ci-openshift-eng-ocp-qe-perfscale-ci-main-aws-{version_to_check}-nightly-x86-control-plane-120nodes/{job_id}"
    },
    "data-path-9nodes": {
        "history_url": f"{prow_url}/job-history/gs/test-platform-results/logs/periodic-ci-openshift-eng-ocp-qe-perfscale-ci-main-aws-{version_to_check}-nightly-x86-data-path-9nodes",
        "job_url": f"{prow_url}/view/gs/test-platform-results/logs/periodic-ci-openshift-eng-ocp-qe-perfscale-ci-main-aws-{version_to_check}-nightly-x86-data-path-9nodes/{job_id}"
        }
}

def get_current_trt_version() -> str:
    response = requests.get(trt_version_url)
    try:
        trt_versions = response.json()
        return trt_versions["name"]
    except requests.exceptions.JSONDecodeError:
        print(f"#### NO AVAILABLE NIGHTLY BUILD FOR {version_to_check} WITH TRT LABEL ####")
        exit(1)

def get_rehearse_history(rehearse_history_url) -> list: 
    response = requests.get(rehearse_history_url)
    history = response.text
    # print(history)
    all_bulids = []
    lines = history.splitlines()
    for line in lines:
        if "allBuilds" in line:
            all_bulids = json.loads(line[:-1].strip().replace("var allBuilds = ", "")) #Remove semicolon at the end, remove spaces and remove variable assigment
            break
        else:
            pass
    return all_bulids

jobs = get_rehearse_history(rehearses["control-plane-120nodes"]["history_url"])
print(jobs)
print(type(jobs))

for job in jobs: 
    print(job)
    print(f"{prow_url}{job["SpyglassLink"]}")

print(get_current_trt_version())
