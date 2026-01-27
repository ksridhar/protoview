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
- <https://www.jsonrpc.org/specification>

## Phases

| Phase | Command | Comment |
|-------|---------|---------|
| 1     | pvcapture | capture protocol messages exchanged between applications (typically HTTP clients and servers) |
| 2     | pvinspect | captured messages -> json-lines |
| 3     | pvrrdump  | json-lines -> (requests and response files + correlating csv) |
| 4     | pvrrenumi | (correlating csv) -> (request, response with body csv) |
| 5     | pvrrenumitopuml | (request, response with body csv) -> (plantuml diagram) |
| 6     | pvgenseqdhtml   | (platuml diagram) -> html |

See [make dependency tree](./make.tree.txt)

## Running

### Capturing packets

- Run these commands to capture messages on port 10002 on the local machine
  ```
  sudo usermod -a -G wireshark {your username}
  newgrp wireshark
  bash
  ./pvcapture.sh 10002 > 10002.pcapng   # 10002 is the server port number
  ```
- Run the applications
- Stop the applications
- Stop the pvcapture (CTRL+C)

- [captured sample](./10002.run.05.pcapng.zip)

### Creating a sequence diagram in HTML

```
make
```
Ouputs the following
```
# unzip (A2UI process interaction packet capture zip)
unzip 10002.run.05.pcapng.zip
Archive:  10002.run.05.pcapng.zip
  inflating: 10002.run.05.pcapng     

# (packet capture (pcapng)) -> (json-lines (jsonl))
./pvinspect.sh -p 10002 10002.run.05.pcapng > 10002.run.05.jsonl

# (json-lines (jsonl)) -> ((request, response) files, (request, response) csv)
./pvrrdump.sh -P xxx 10002.run.05.jsonl > xxx.pvrrdump_map.csv

# ((request, response) csv) -> ((request, response) interaction with httpbody as csv)
./pvrrenumi.sh xxx.pvrrdump_map.csv > xxx.pvrrenumi_map.csv

# ((request, response) interaction with httpbody as csv) -> (plantuml sequence diagram)
python3 pvrrenumitopuml.py --folder-path /home/sridhar/github_projects/protoview xxx.pvrrenumi_map.csv > xxx.seqd.puml

# (plantuml sequence diagram) -> (html sequence diagram)
./pvgenseqdhtml.sh --template-html pvseqdtempl.html --puml-source xxx.seqd.puml > seqd.html
```
Output : [html sequence diagram](https://htmlpreview.github.io/?https://github.com/ksridhar/protoview/blob/main/seqd.html)

### A view of make dependencies

```
make xxx.make.tree.txt
```
Output : [make dependency tree](./make.tree.txt)

