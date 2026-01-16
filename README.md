# protoview

- Viewing protocol messages.
- Beginning with HTTP.

## motivation

There are a number of pcap (packet capture) based tools available like
tshark and ngrep. While these are good at capturing packet information 
we would want to present the captured information in a way that is easy 
to read, search, traverse, parse and display.

## The proposed mechanism (subject to change)

### capture 

Here messages that are sent and received from a set of servers (currently
HTTP) are captured an stored in a file. **dumpcap** is currently to be used
for this process.

### list-events

Here the messages stored in the capture phase are presented in jsonl format
using **tshark**.

### render

#### Markdown

This makes it easy to 
- view
- search (grep, etc..)
- traverse (using ctags)

#### D3
#### mermaid

## The implementation

**TODO**

## resources

- <https://github.com/PiRogueToolSuite/pcapng-utils>
- <https://pts-project.org/>
- <https://github.com/gaainf/pcaper>

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
  ./pvrrdump -P xxx. 10002.jsonl
  ```
  Will create files with the prefix 'xxx.'


