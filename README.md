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

## Other commands

```
sudo usermod -a -G wireshark {your username}
newgrp wireshark
bash
dumpcap -i lo "tcp port 10002" -w 10002.run.05.pcapng
```

```
./pvinspect.sh 10002.run.05.pcapng | jq '.' > 10002.run.05.inspect.jsonl
```
