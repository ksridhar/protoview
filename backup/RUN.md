# protoview

## Prelude

```
sudo apt install tshark
chmod +x protoview.py
```

## Execution examples

### Capture phase

```
./protoview.py --verbose 5173 10002
```

This gave rise to the following output

```
$ ./protoview.py capture --verbose 5173 10002
[protoview] ports          : [5173, 10002]
[protoview] bpf filter     : tcp and (port 5173 or port 10002)
[protoview] output capture : 2026-01-08-19-54-11.pcapng
[protoview] interface      : lo
[protoview] transport      : tcp
[protoview] capturer       : dumpcap
[protoview] format         : pcapng (default)
[protoview] exec           : dumpcap -i lo -f 'tcp and (port 5173 or port 10002)' -w 2026-01-08-19-54-11.pcapng
Capturing on 'Loopback: lo'
dumpcap: The capture session could not be initiated on interface 'lo' (You don't have permission to capture on that device).
Please check to make sure you have sufficient permissions.

On Debian and Debian derivatives such as Ubuntu, if you have installed Wireshark from a package, try running

    sudo dpkg-reconfigure wireshark-common

selecting "<Yes>" in response to the question

    Should non-superusers be able to capture packets?

adding yourself to the "wireshark" group by running

    sudo usermod -a -G wireshark {your username}

and then logging out and logging back in again.
[protoview] dumpcap exit code: 1
ERROR: dumpcap failed.
If you expected this to work without sudo, your system may not be configured
to allow non-root packet capture (e.g., dumpcap capabilities / wireshark group).
```

After performing the above step, the following error was encountered

```
$ command -v dumpcap
/usr/bin/dumpcap
$ which dumpcap
$ ./protoview.py capture --verbose 5173 10002
[protoview] ports          : [5173, 10002]
[protoview] bpf filter     : tcp and (port 5173 or port 10002)
[protoview] output capture : 2026-01-08-22-27-52.pcapng
[protoview] interface      : lo
[protoview] transport      : tcp
[protoview] capturer       : dumpcap
[protoview] format         : pcapng (default)
[protoview] exec           : dumpcap -i lo -f 'tcp and (port 5173 or port 10002)' -w 2026-01-08-22-27-52.pcapng
Traceback (most recent call last):
  File "./protoview.py", line 201, in <module>
    raise SystemExit(main(sys.argv[1:]))
  File "./protoview.py", line 197, in main
    return int(args.func(args))
  File "./protoview.py", line 134, in cmd_capture
    proc = subprocess.Popen(dumpcap_cmd)
  File "/usr/lib/python3.8/subprocess.py", line 858, in __init__
    self._execute_child(args, executable, preexec_fn, close_fds,
  File "/usr/lib/python3.8/subprocess.py", line 1704, in _execute_child
    raise child_exception_type(errno_num, err_msg, err_filename)
PermissionError: [Errno 13] Permission denied: 'dumpcap'
```

A lot of deliberations followed 

```
sudo usermod -a -G wireshark $(whoami)
id -nG                          # did not show wireshark
getcap /usr/bin/dumpcap
command -v dumpcap; echo $?;
which dumpcap                   # does not show. but command did !
echo $PATH | grep '/usr/bin'    # dumpcap in path !
```

Finally this worked

```
newgrp wireshark
bash
id -nG
./protoview.py capture --verbose 5173 10002
```

The real-world packaging situation on your machine: dumpcap is executable 
only for the wireshark group, and your login session wasn’t actually in 
that group. newgrp wireshark is a correct workaround; the long-term fix 
is to make group membership effective at login (but that’s OS/admin 
territory, not protoview code).

