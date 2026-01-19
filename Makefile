CUR_DIR := $(shell pwd)

all: xxx.seqd.html xxx.testseqd.01.html xxx.testseqd.02.html

xxx.seqd.html: pvseqdtempl.html xxx.seqd.puml
	./pvgenseqdhtml.sh --template-html $< --puml-source xxx.seqd.puml > $@

xxx.seqd.puml: xxx.pvrrenumi_map.csv
	python3 pvrrenumitopuml.py --folder-path $(CUR_DIR) $< > $@

xxx.pvrrenumi_map.csv: xxx.pvrrdump_map.csv
	./pvrrenumi.sh $< > $@

xxx.pvrrdump_map.csv: 10002.run.05.jsonl
	./pvrrdump.sh -P xxx 10002.run.05.jsonl > $@

10002.run.05.jsonl: 10002.run.05.pcapng
	./pvinspect.sh -p 10002 $< > $@

10002.run.05.pcapng:
	unzip 10002.run.05.pcapng.zip

test: xxx.testseqd.01.html xxx.testseqd.02.html

xxx.testseqd.01.html: pvseqdtempl.html pvtestseqd1.puml
	./pvgenseqdhtml.sh --template-html $< --puml-source pvtestseqd1.puml > $@

xxx.testseqd.02.html: pvseqdtempl.html pvtestseqd2.puml
	./pvgenseqdhtml.sh --template-html $< --puml-source pvtestseqd2.puml > $@


.PHONY: clean 
clean:
	rm -rfv xxx.pvrrenumi_map.csv
	rm -rfv xxx.pvrrdump_map.csv
	rm -rfv xxx.*.json
	rm -rfv xxx.testseqd.01.html
	rm -rfv xxx.testseqd.02.html
	rm -rfv 10002.run.05.jsonl
	rm -rfv 10002.run.05.pcapng
	rm -rfv xxx.seqd.html
	rm -rfv xxx.seqd.puml
