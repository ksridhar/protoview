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
HTTP) are captured an stored in a file. **tshark** is currently to be used
for this process.

### list-events

Here the messages stored in the capture phase are presented in [PVTS](./PVTS.md) 
format. 

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

## Running the program

[See RUN.md](./RUN.md)

## resources

- <https://github.com/PiRogueToolSuite/pcapng-utils>
- <https://pts-project.org/>
- <https://github.com/gaainf/pcaper>

## Other commands

```
tshark -r 10002.pcapng -Y "http" -T json   -e http.request.method -e http.request.uri -e http.response.code -e http.file_data 
```
