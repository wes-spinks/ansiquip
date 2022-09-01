# -*- coding: utf-8 -*-

# Copyright: (c) 2022, Wes Spinks <wes () redhat.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
---
module: quip_update_cell
short_description: Patch a specific string (find/replace) in a target table header or cell
description:
     - Find a specific string in a target table's headers or cells and replace with new value
     - Leverages Quip's Automation API endpoints:
       https://quip.com/dev/automation/documentation/current
options:
    quip_urls:
      description: list of target Quip document url(s)
      type: list
      required: true
    sheet_name:
      description: The name, or sheet tab, of the target spreadsheet
      type: str
      required: true
    find:
      description: The exact string that you want to find and replace
      type: str
      required: true
    replace:
      description: The exact string you want to update the target cell's value to
      type: str
      required: true
    markdown:
      descriptions: One of "bold" or "italic"
      type: str
      required: false
    base_api_url:
      description: alternate API base URL
      type: str
      required: false
      default: https://platform.quip.com
    token:
      description: token in ansible-vault (recommended) or plain-text string
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
- Wes Spinks (@wes-spinks)
"""

EXAMPLES = r"""
- name: Example failure using find=fail_me
  quip_update_cell:
    token: 'Quip-API-TOKEN-here'
    find: 'fail_me'
    replace: 'Demo value'
    quip_urls:
        - https://team.quip.com/3XAMPL3D0C/my-demo-doc-name
        - https://org.quip.com/eXAmpl3d0C/another-doc-title

- name: Update the value of a header cell
  quip_update_cell:
    token: !vault |
        $ANSIBLE_VAULT;1.1;AES256
        12345 vaulted secret
        67890 here
    quip_urls:
        - 'http://example.quip.com/documentID/file-name'
    find: 'Demoo Value'
    markdown: 'bold'
    replace: 'Demo Value'
"""

RETURN = r"""
# These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: Summary of action(s) attempted
    type: str
    returned: always
    sample: ''
message:
    description: Message about the number of updates were attempted and successful.
    type: str
    returned: always
    sample: '1 of 3 cells were updated successfully'
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

import json
import urllib.request

from ansible.module_utils.bs4 import BeautifulSoup

Request = urllib.request.Request
urlencode = urllib.parse.urlencode
urlsplit = urllib.parse.urlsplit
urlopen = urllib.request.urlopen
HTTPError = urllib.error.HTTPError
iteritems = dict.items


def get_cell_id(html, findstring) -> str:
    """Expects the str(HTML), str(to find);
    Uses beautifulsoup to parse the html and return the id of the cell with findstring
    Returns the str(cell_id), or None
    """
    try:
        parse_soup = BeautifulSoup(html, "html.parser")
        string_location = parse_soup.find(string=findstring)
        cell_id = string_location.find_parent("td").find("span").get("id")
    except AttributeError:
        # when the string_location was not found, and cell_id has no parent
        return None
    except Exception as err:
        # not sure what exceptions to expect from bs4
        raise err
        return None
    return str(cell_id)


def get_quip_html(
    token, quip_ids, base_api_url="https://platform.quip.com", params=None
):
    """GET call to destination doc HTML
    Expects API token, list of destination doc objects;
      - token - str
      - quip_ids - list of destination document IDs
        [
            'DOCID1ONE','DOCIDTWO','DOCTHREE'
        ]
    Returns:
      - dict of destination documents' HTML {dest_doc_id : html}
        {
            'DOCID1ONE': '<html><p><br></p>...',
            'DOCIDTWO': 'failed',
            'DOCTHREE': ...
        }

    Quip API documentation:
    https://quip.com/dev/automation/documentation/current#operation/getThreadHtmlV2
    """

    return_dict = dict()
    header = {"Authorization": f"Bearer {token}"}
    for id in quip_ids:
        endpoint = base_api_url + "/2/threads/" + id + "/html"
        req = Request(url=endpoint, headers=header)
        try:
            result = json.loads(urlopen(req, timeout=30).read().decode())
        except HTTPError as error:
            raise error
        try:
            return_dict[id] = result["html"]
        except KeyError:
            return_dict[id] = "failed"
    return return_dict


def post_changes(token, target_dict, payload, **args) -> dict:
    """Take a list of targets (thread and section IDs) and the find/replace values
    Expects:
      - token - str - Plain text string or Vaulted value
      - target_dict - dict - contains thread_id and cell_id. Example:
            {
            'DOCID1ONE':'temp:C:examplesectionidhere'
            }
      - payload - str - '<b>NEW CELL VALUE</b>'

    Returns:
      - dict of target document {thread/doc id : success | fail}
            {
            'DOCID1ONE': 'success',
            }
    """
    output = {}
    for k, v in target_dict.items():
        try:
            result = edit_document(
                token, k, payload, operation=4, format="html", section_id=v
            )
        except HTTPError as error:
            raise error
        if result:
            output[k] = "success"
        else:
            output[k] = "fail"
    return output


def edit_document(
    token, thread_id, content, operation, format="html", section_id=None, **kwargs
):
    """Edits the given document, adding the given content.
    `operation` should be one of the constants described above. If
    `operation` is relative to another section of the document, you must
    also specify the `section_id`.
    """

    # Seems we CANNOT change font/format of cells:
    # https://developer.salesforce.com/forums/?id=9062I000000IZDdQAO

    # Since our cell ids in 10x contain ';', which is a valid cgi
    # parameter separator, we are replacing them with '_' in 10x cell
    # sections. This should be no op for all other sections.
    section_id = None if not section_id else section_id.replace(";", "_")

    args = {
        "thread_id": thread_id,
        "content": content,
        "location": operation,
        "format": format,
        "section_id": section_id,
    }
    return _fetch_json(token, "threads/edit-document", post_data=args)


def _fetch_json(token, path, post_data=None, **args):
    request = Request(url="https://platform.quip.com/1/" + path)
    if post_data:
        post_data = dict(
            (k, v) for k, v in post_data.items() if v or isinstance(v, int)
        )
        request_data = urlencode(_clean(**post_data))
        request.data = request_data.encode()

    request.add_header("Authorization", "Bearer {}".format(token))
    try:
        return json.loads(urlopen(request, timeout=30).read().decode())
    except HTTPError as error:
        try:
            return json.loads(error.read().decode())["error_description"]
        except Exception:
            raise error


def _clean(**args):
    return dict(
        (k, str(v) if isinstance(v, int) else v.encode("utf-8"))
        for k, v in args.items()
        if v or isinstance(v, int)
    )


def parse_quip_url(url):
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
        quip_urls=dict(type="list", required=True, default=None),
        markdown=dict(type="str", required=False, default=None),
        find=dict(type="str", required=True, default=None),
        replace=dict(type="str", required=True, default=None),
        token=dict(type="str", required=True, no_log=True, default=None),
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
    quip_urls = params["quip_urls"]
    find = params["find"]
    replace = params["replace"]
    token = params["token"]
    base_api_url = params["base_api_url"]
    markdown = params["markdown"]

    # final list of destinations to attempt POST
    destination_list = list()
    # temp list of destinations for parsing
    _dest_list = list()

    # parse destination URLs to determine the document ID for POST
    for dest_url in quip_urls:
        _dest = parse_quip_url(dest_url)
        # if the URL was parsed, _dest[1] should be the doc ID
        if _dest[0] and _dest[1]:
            _dest_list.append(_dest[1])
        # if we're unable to resolve the document ID from the URL, then append it to unsuccessful response
        else:
            result["unsuccessful"].append("{}".format(dest_url))
    if not _dest_list:
        result[
            "original_message"
        ] = "Failed to identify Quip document ID(s) from {}".format(quip_urls)
        module.fail_json(
            msg="The Quip document IDs could not be parsed from provided URLs",
            **result,
        )
    else:
        # set original message to describe the action(s) we will attempt to perform
        result[
            "original_message"
        ] += "Attempting find '{}' and replace with '{}' on the following Quip documents: {}".format(
            find, replace, _dest_list
        )

    # GET all the destination document HTMLs
    # If the GET failed then there is no HTML to parse, so append the key to unsuccessful response
    get_htmls = get_quip_html(token, _dest_list, params=None)
    failed_htmls = {k: v for k, v in get_htmls.items() if v == "failed"}
    dest_htmls = {k: v for k, v in get_htmls.items() if v != "failed"}

    # append the 'failed to resolve document ID' docs to unsuccessful list
    for doc in failed_htmls.items():
        result["unsuccessful"].append("quip.com/{}".format(doc[0]))

    # loop through destination_list, dict of {document_ID : document HTML}
    # create a destination_dict of {document_ID : cell_id containing str(find)}
    for k, v in dest_htmls.items():
        cell_id_found = get_cell_id(v, find)
        if not cell_id_found:
            result["unsuccessful"].append("quip.com/{}".format(k))
        else:
            # append to final destination_list where doc_ID = cell_id
            destination_list.append({k: cell_id_found})

    # if markdown is requested, format the replace text to include HTML tags
    if markdown == 'bold':
        markdown_replace = "<b>{}</b>".format(replace)
    elif markdown == 'italic':
        markdown_replace = "<i>{}</i>".format(replace)
    else:
        markdown_replace = None

    # perform the needed actions, log the outcome to successful or unsuccessful results
    for destination in destination_list:
        # do the POST
        post_resp = post_changes(
            token,
            destination,
            markdown_replace if markdown_replace else replace,
        )

        # look at success | fail
        for k, v in post_resp.items():
            if v == "fail":
                # append the failed updates to unsuccessful list
                result["unsuccessful"].append(
                    "quip.com/{}".format(k)
                    # "quip.com/{}#{}".format(k, destination[k])
                )
            else:
                # append the successful destinations to successful msg
                result["successful"].append("quip.com/{}#{}".format(k, destination[k]))

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    success_int = len(result["successful"])
    if success_int > 0:
        result["changed"] = True
        result[
            "message"
        ] = f"{success_int} of {len(quip_urls)} Quip documents were updated successfully"
    else:
        result["changed"] = False
        result[
            "original_message"
        ] = "Failed to find {} and replace with {} in all provided Quip URLs.".format(
            find, replace
        )
        result[
            "message"
        ] = f"{success_int} of {len(quip_urls)} were updated successfully"
        module.fail_json(msg="No Quip documents were successfully updated", **result)

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    if quip_urls == "fail me":
        module.fail_json(msg="You requested this to fail", **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
