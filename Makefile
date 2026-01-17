# 1. The default goal is now the sentinel file
all: .pvrrdump_done

# 2. This rule runs ONLY if .pvrrdump_done does not exist
.pvrrdump_done: 10002.run.05.jsonl
	./pvrrdump.sh -P xxx. 10002.run.05.jsonl
	touch .pvrrdump_done

10002.run.05.jsonl: 10002.run.05.pcapng
	./pvinspect.sh -p 10002 $< > $@

10002.run.05.pcapng:
	unzip 10002.run.05.pcapng.zip

# 3. Update clean to remove the sentinel and use shell wildcard for the unknown files
.PHONY: clean
clean:
	rm -rfv 10002.run.05.jsonl 10002.run.05.pcapng .pvrrdump_done
	rm -rfv xxx.*.json
