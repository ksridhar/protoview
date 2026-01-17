all: xxx.pvrrdisp_map.csv

xxx.pvrrdisp_map.csv: xxx.pvrrdump_map.csv
	./pvrrdisp.sh $< > $@

xxx.pvrrdump_map.csv: 10002.run.05.jsonl
	./pvrrdump.sh -P xxx 10002.run.05.jsonl > $@

10002.run.05.jsonl: 10002.run.05.pcapng
	./pvinspect.sh -p 10002 $< > $@

10002.run.05.pcapng:
	unzip 10002.run.05.pcapng.zip

.PHONY: clean 

clean:
	rm -rfv xxx.pvrrdisp_map.csv
	rm -rfv xxx.pvrrdump_map.csv
	rm -rfv xxx.*.json
	rm -rfv 10002.run.05.jsonl
	rm -rfv 10002.run.05.pcapng
