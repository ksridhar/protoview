# protoview

- Viewing protocol messages.
- Beginning with HTTP.

## motivation

There are a number of pcap (packet capture) based tools available like
tshark and ngrep. While these are good at capturing packet information 
we would want to present the captured information in a way that is easy 
to read, search, traverse, parse and display.

## The proposed mechanism (subject to change)

### gather 

Here messages that are sent and received from a set of servers (currently
HTTP) are gathered an stored in a file. **tshark** is currently to be used
for this process.

### list

Here the messages stored in the gather phase are presented in a markdown
format. This makes it easy to 
- view
- search (grep, etc..)
- traverse (using ctags)

### display

The markdown generated above is used for visual display using **D3** or 
**mermaid**.

## The implementation

**TODO**

