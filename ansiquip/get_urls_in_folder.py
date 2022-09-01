#!/usr/bin/env python3
import argparse
import json
import urllib.request

parser = argparse.ArgumentParser(
        description="Retrieve a YAML list of Quip document URLs from a Quip folder ID"
        )

parser.add_argument("--id", required=True)
parser.add_argument("--token", required=True)

args = parser.parse_args()

# get the thread_ids for docs in folder
_url = "https://platform.quip.com/1/folders/{}".format(args.id)
header = {"Authorization": "Bearer {}".format(args.token)}
req = urllib.request.Request(url=_url, headers=header)
response = urllib.request.urlopen(req, timeout=15)
docs_list = json.load(response)["children"]

for doc in docs_list:
    did = doc["thread_id"]
    # get URLs from thread_ids in response
    try:
        thread_req = urllib.request.Request(url="https://platform.quip.com/2/threads/{}".format(did), headers=header)
        thread_response = urllib.request.urlopen(thread_req, timeout=15)
        # pad leading whitespace simplfy copy/paste into Ansible playbook
        print("        - " + json.load(thread_response)["thread"]["link"])
    except Exception:
        raise Exception
