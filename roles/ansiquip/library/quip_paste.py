# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Wes Spinks <wes () redhat.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

import json
import time
import urllib.request
from tempfile import TemporaryFile

#import requests
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six.moves.urllib.parse import urlsplit

HTTPError = urllib.error.HTTPError

__metaclass__ = type

DOCUMENTATION = r"""
---
module: quip_paste
short_description: Live paste content from a Quip document to other Quip documents
description:
     - Insert content from a source Quip document to a list of destination Quip documents
     - Leverages Quip's Automation API 'Live Paste' endpoint:
       https://quip.com/dev/automation/documentation/current
options:
    source_url:
      description: URL of the source Quip document;
      type: str
      required: true
    source_section_id:
      description: The exact section ID of the content to copy
      type: str
      required: true
    destination_urls:
      description: A list of Quip document URLs to paste new content into
      type: list
      required: true
    target_header:
      description: The target header to live paste content after
      type: str
      required: true
    prepend:
      description: If True, posts the live-paste changes BEFORE the target_header
      type: bool
      required: False
      default: False
    base_api_url:
      description: alternate API base URL
      type: str
      required: false
      default: https://platform.quip.com
# informational: requirements for nodes
extends_documentation_fragment:
    - files
    - action_common_attributes
attributes:
    check_mode:
        details: the changed status will reflect comparison to an empty source file
        support: partial
    diff_mode:
        support: none
    platform:
        platforms: posix
notes:
    - Developed on RHEL for Linux environments
seealso:
- module: ansible.builtin.uri
- module: ansible.builtin.get_url
author:
- Wes Spinks (@rhwes)
"""

EXAMPLES = r"""
- name: Example failure using source_url=fail_me
  quip_paste:
    token: 'Quip-API-TOKEN-here'
    source_url: 'fail_me'
    source_section_id: 'temp:C:aaaaXXXXXX33333asdf'
    destination_urls:
        - https://team.quip.com/3XAMPL3D0C/my-demo-doc-name
        - https://org.quip.com/eXAmpl3d0C/another-doc-title
    target_header: 'Header Name'
    prepend: False

- name: Copy Doc1 content to Doc2, after the 'My Section' header
  quip_paste:
    token: !vault |
        $ANSIBLE_VAULT;1.1;AES256
        12345 vaulted secret
        67890 here
    base_api_url: 'https://platform.quip.com'
    source_url: 'http://example.quip.com/documentID/file-name'
    source_section_id: 'temp:C:1234html56789'
    destination_urls:
        - https://team.quip.com/3XAMPL3D0C/my-demo-doc-name
        - example.quip.com/ZZZZZZZZZZ/VERY-REAL-DOC
    target_header: 'My Section'
    prepend: False
"""

RETURN = r"""
# These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: Summary of action(s) attempted
    type: str
    returned: always
    sample: 'Pasting <source doc details> to: ['list of', 'destination docs']
message:
    description: Message about the number of updates were attempted and successful.
    type: str
    returned: always
    sample: '1 of 3 Quip documents were updated successfully'
successful:
    description: A list of successfully updated document URLs
    type: list
    returned: always
    sample: [
        "quip.com/abcANVVmKbJ#temp:C:abcdf50e480d4997444da8b3bb123",
        "quip.com/zyxwkANVVm#temp:C:defg50e480d4999444da8b3bb555",
    ]
unsuccessful:
    description: A list of unsuccessful document URLs
    type: list
    returned: always
    sample: [
        "quip.com/abcANVVmKbJ",
        "quip.com/zyxwkANVVm",
    ]
"""

from ansible.module_utils import bs4


def parse_quipHTML(html, target_header) -> str:
    """Expects str(html_content) and a str(target_header)
    Returns an H1 or H2 section ID where the target_header is found
    """
    soup = bs4.BeautifulSoup(html, "html.parser")
    query = "string='{}'".format(target_header)
    header_section = soup.find(query)
    try:
        response = header_section.find_parent("h1").get("id")
    except AttributeError:
        try:
            response = header_section.find_parent("h2").get("id")
        except AttributeError:
            return None
    return response


def post_changes(token, src, dest, append, base_api_url="https://platform.quip.com") -> dict:
    """POST the source's content to destinations, after target_header
    Expects:
      - token - str
      - src - dict
        {'thread/document ID':'source section ID'}
      - dest - list of destination objects
        [
            {'doc_id':'DOCID1ONE', 'section':'temp:C:examplesectionidhere'},
            {'doc_id':'DOCID2TWO', 'section':'temp:C:mydemosectionidhere'},
            {'doc_id':'DOCIDTHREE', 'section':'temp:C:anotherectionidhere'}',
            {'doc_id':'DOCID4FOUR', 'section':'temp:C:doesnotexistidhere'}'
      - append - bool
        True will post changes after the section; False will PREPEND changes

    Returns:
      - dict of destination document {thread/doc id : success | fail}
        {
            'DOCID1ONE': 'success',
            'DOCID2TWO': 'fail',
            'DOCIDTHREE': 'fail',
            'DOCID4FOUR': 'fail'
        }
    """
    output = {}
    header = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "Bearer {}".format(token),
    }
    fmt_src = f"source_thread_id={ src['id'] }&source_section_ids={ src['section_id'] }"
    pend = 3 if not append else 2

    for k, v in dest.items():
        fmt_dest = f"destination_thread_id={ k }&destination_section_id={ v }"
        ep = dict(
                source_thread_id=src["id"],
                source_section_ids=src["section_id"],
                destination_thread_id=k,
                destination_section_id=v,
                location=int(pend),
                update_automatic=True,
                )
        endpoint = urllib.parse.urlencode(ep).encode("utf-8")
        #endpoint = f"{ fmt_src }&{ fmt_dest }&location=2&update_automatic=true"
        _url = "{}/1/threads/live-paste".format(base_api_url)
        try:
            req = urllib.request.Request(url=_url, data=endpoint, headers=header)
            result = urllib.request.urlopen(req, timeout=75)
            if int(result.headers['X-Ratelimit-Remaining']) < 10:
                time.sleep(int(result.headers['Retry-After']))
            if result.code == 200:
                output[k] = "success"
            else:
                output[k] = "fail"
        except HTTPError:
            output[k] = "fail"
    return output


def get_destination_HTML(
    token, destination_doc_ids, base_api_url="https://platform.quip.com", params=None
) -> dict:
    """GET call to destination doc HTML
    Expects API token, list of destination doc objects;
      - token - str
      - destination - list of destination document IDs
        [
            'DOCID1ONE','DOCIDTWO','DOCTHREE'
        ]
    Returns:
      - dict of destination documents' HTML {dest_doc_id : html}
        {
            'DOCID1ONE': '<p><br></p>',
            'DOCIDTWO': '<html><td>...',
            'DOCTHREE': '<div>...'
        }

    Quip API documentation:
    https://quip.com/dev/automation/documentation/current#operation/getThreadHtmlV2
    """

    return_dict = dict()
    header = {"Authorization": f"Bearer {token}"}
    for doc_id in destination_doc_ids:
        endpoint = base_api_url + "/2/threads/" + doc_id + "/html"
        #result = requests.get(endpoint, headers=header, params=params)
        try:
            req = urllib.request.Request(url=endpoint, headers=header)
            resp = urllib.request.urlopen(req, timeout=75)
            result = json.loads(resp.read().decode())
            if int(resp.headers['X-Ratelimit-Remaining']) < 10:
                time.sleep(int(result.headers['Retry-After']))
            if result["html"]:
                return_dict[doc_id] = result["html"]
            else:
                return_dict[doc_id] = "failed"
        except HTTPError:
            return_dict[doc_id] = "failed"
    return return_dict


def parse_quip_url(url) -> tuple:
    """Attempts to resolve base and document IDs from given URLs
    Expects a string; returns tuple of (base_url, doc_ID) or None
    """
    document_id = None
    base = None
    if not "://" in url and not url.startswith("/"):
        url = "%s%s" % ("https://", url)
    if "quip.com" in url:
        _url = urlsplit(url)
        document_id = _url.path.split("/")[1]
        base = _url.netloc

    return base, document_id


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        source_url=dict(type="str", required=True, default=None),
        source_section_id=dict(type="str", required=True, default=None),
        destination_urls=dict(type="list", required=True, default=None),
        target_header=dict(type="str", required=True, default=None),
        token=dict(type="str", required=True, no_log=True, default=None),
        prepend=dict(type="bool", required=False, default=False),
        base_api_url=dict(
            type="str", required=False, default="https://platform.quip.com"
        ),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        original_message="",
        unsuccessful=list(),
        successful=list(),
        message="",
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # copy input parameters to vars
    params = module.params
    source_url = params["source_url"]
    source_section_id = params["source_section_id"]
    destination_urls = params["destination_urls"]
    target_header = params["target_header"]
    token = params["token"]
    prepend = params["prepend"]
    base_api_url = params["base_api_url"]

    # temp list of destinations for parsing
    _dest_list = list()

    # final list of destinations to attempt POST
    destination_list = list()

    # parse each provided destination URL to determine the document ID that we need to POST
    for dest_url in destination_urls:
        _dest = parse_quip_url(dest_url)
        # if the URL was parsed, _dest[1] should be the doc ID
        if _dest[0] and _dest[1]:
            _dest_list.append(_dest[1])
        # if we're unable to resolve the document ID from the URL, then append it to unsuccessful response
        else:
            result["unsuccessful"].append("{}".format(dest_url))
    parsed_src = parse_quip_url(source_url)
    if not parsed_src:
        result[
            "original_message"
        ] += "Failed to identify a Quip document ID from {}".format(source_url)
        module.fail_json(
            msg="The source document ID could not be parsed from provided source URL",
            **result,
        )
    else:
        src_dict = {
            "base": parsed_src[0],
            "id": parsed_src[1],
            "section_id": source_section_id,
        }
        result["original_message"] += "Pasting {}/{}#{} to: ".format(
            src_dict["base"], src_dict["id"], src_dict["section_id"]
        )

    # GET all the destination document HTMLs
    # If the GET failed then there is no HTML to parse, so append the key to unsuccessful response
    get_htmls = get_destination_HTML(
        token, destination_doc_ids=_dest_list, base_api_url=base_api_url, params=None
    )
    failed_htmls = {k: v for k, v in get_htmls.items() if v == "failed"}
    dest_htmls = {k: v for k, v in get_htmls.items() if v != "failed"}

    # append the 'failed to resolve document ID' docs to unsuccessful list
    for doc in failed_htmls.items():
        result["unsuccessful"].append("quip.com/{} - failed to get HTML".format(doc[0]))

    # loop through actual destination docs with valid section_ids
    # nesting try/excepts to hit H1-H3 - really need to refactor this
    # create a destination_dict of {ID:section} for each doc
    for k, v in dest_htmls.items():
        try:
            parsed_section_id = (
                bs4.BeautifulSoup(v, "html.parser")
                .find(string=target_header)
                .find_parent("h1")
                .get("id")
            )
            destination_list.append({k: parsed_section_id})
            continue
        except AttributeError:
            try:
                parsed_section_id = (
                    bs4.BeautifulSoup(v, "html.parser")
                    .find(string=target_header)
                    .find_parent("h2")
                    .get("id")
                )
                destination_list.append({k: parsed_section_id})
            except AttributeError:
                try:
                    parsed_section_id = (
                        bs4.BeautifulSoup(v, "html.parser")
                        .find(string=target_header)
                        .find_parent("h3")
                        .get("id")
                    )
                    destination_list.append({k: parsed_section_id})
                except AttributeError:
                    result["unsuccessful"].append("quip.com/{} - target header not found".format(k))


    # perform the needed actions, log the outcome to successful or unsuccessful results

    if prepend:
        append = False
    else:
        append = True

    for destination in destination_list:
        # do the POST
        try:
            post_resp = post_changes(
                token, src_dict, destination, append, base_api_url="https://platform.quip.com"
            )
        except HTTPError as err:
            post_resp = {destination: 'fail'}
        # look at success | fail
        for k, v in post_resp.items():
            if v == "fail":
                # append the failed live pastes to unsuccessful
                result["unsuccessful"].append(
                    "quip.com/{}#{} - POST failed".format(k, destination[k])
                )
            else:
                # append the successfully live pasted destinations to both
                # successful and original_message
                result["successful"].append("quip.com/{}#{}".format(k, destination[k]))

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    success_int = len(result["successful"])
    if success_int > 0:
        result["changed"] = True
        result["original_message"] += str(result["successful"])
        result[
            "message"
        ] = f"{success_int} of {len(destination_urls)} Quip documents were updated successfully"
    else:
        result["changed"] = False
        result[
            "original_message"
        ] = "No valid destinations identified while attempting live paste from {}/{}#{}".format(
            src_dict["base"], src_dict["id"], src_dict["section_id"]
        )
        result[
            "message"
        ] = f"{success_int} of {len(destination_urls)} were updated successfully"
        module.fail_json(msg="No Quip documents were successfully updated", **result)

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    if source_url == "fail me":
        module.fail_json(msg="You requested this to fail", **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
