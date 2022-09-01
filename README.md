# ansiquip

Custom Ansible module for Quip document manipulation

## Getting started
1. `git clone https://github.com/wes-spinks/ansiquip.git; cd ansiquip`
2. replace vaulted Quip access token `vim roles/ansiquip/vars/main.yml`
   - `ansible-vault encrypt_string '<YOUR_TOKEN>' --name quip_token`
3. open the playbook (`vim example.yml`) and update the variables:
   - update source table URL and `source_section_id`
   - add Quip destination URLs
   - update `target_header` var for live-paste
4. `ansible-playbook -vvv --ask-vault-password example.yml` # run the demo



Example outputs:

quip_paste:
```
changed: [localhost] => {
    "changed": true,
    "invocation": {
        "module_args": {
            "base_api_url": "https://platform.quip.com",
            "destination_urls": [
                "https://<team>.quip.com/ONIYAy50FPdB/Ansible-Demo-Doc",
                "working.example.quip.com/ZZZZZZZZZZ/VERY-REAL-DOC"
            ],
            "source_section_id": "temp:C:JbVf61bd87474cb45928fb4e7a4b",
            "source_url": "https://<team>.quip.com/E81RAI6kLz88/DEMO-Source-Table",
            "target_header": "Sample Quip Update",
            "token": "VALUE_SPECIFIED_IN_NO_LOG_PARAMETER"
        }
    },
    "message": "1 of 2 Quip documents were updated successfully",
    "original_message": "Pasting <team>.quip.com/E81RAI6kLz88#temp:C:JbVf61bd87474cb45928fb4e7a4b to: ['quip.com/ONIYAy50FPdB#temp:C:eTU1c352fa2b0654896ada4348b7']",
    "successful": [
        "quip.com/ONIYAy50FPdB#temp:C:eTU1c352fa2b0654896ada4348b7"
    ],
    "unsuccessful": [
        "quip.com/ZZZZZZZZZZ"
    ]
}
META: ran handlers
META: ran handlers

PLAY RECAP ********************************************************************************************************************************************************************************
localhost                  : ok=1    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```
