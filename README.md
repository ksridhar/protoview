# protoview

- Viewing protocol messages.
- Beginning with HTTP.

## resources

- <https://github.com/PiRogueToolSuite/pcapng-utils>
- <https://pts-project.org/>
- <https://github.com/gaainf/pcaper>
- <https://kroki.io/>
- <https://www.wireshark.org/>
- <https://plantuml.com/link>

## Phases

- pvcapture : capture protocol messages exchanged between applications
  (typically HTTP clients and servers)
- pvinspect : inspect the captured messages produced by pvcaptured and
  dump them as jsonl
- pvrrdump  : perform a request, response file dumps using the inspected 
  jsonl obtained using pvinspect
- pvrender  : TODO: render to D3, mermaid, graphviz
 
## How to Run

- Run these commands to capture messages on port 10002 on the local machine
  ```
  sudo usermod -a -G wireshark {your username}
  newgrp wireshark
  bash
  ./pvcapture.sh 10002 > 10002.pcapng
  ```
- Run the applications
- Stop the applications
- Stop the pvcapture (CTRL+C)
- Dump HTTP messages pertaining to port 10002
  ```
  ./pvinspect -p 10002 10002.pcapng > 10002.jsonl
  ```
- Create separate json files for request and responses
  ```
  ./pvrrdump -P xxx. 10002.jsonl > 10002.rr.csv
  ```
  Will create files with the prefix 'xxx.' and store the
  request,response file table in 10002.rr.csv
- Enumerate the interactions using pvrrenumi.sh
  ```
  ./pvrrenumi 10002.rr.csv > 10002.enumi.csv
  ```
- There is a sample Makefile that can be looked at to 
  run commands starting from pvinspect onwards.



