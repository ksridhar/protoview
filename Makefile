CUR_DIR := $(shell pwd)

all: xxx.seqd.html # test

xxx.seqd.html: pvseqdtempl.html xxx.seqd.puml
	@echo
	# (plantuml sequence diagram) -> (html sequence diagram)
	./pvgenseqdhtml.sh --template-html $< --puml-source xxx.seqd.puml > $@

xxx.seqd.puml: xxx.pvrrenumi_map.csv
	@echo
	# ((request, response) interaction with httpbody as csv) -> (plantuml sequence diagram)
	python3 pvrrenumitopuml.py --folder-path $(CUR_DIR) $< > $@

xxx.pvrrenumi_map.csv: xxx.pvrrdump_map.csv
	@echo
	# ((request, response) csv) -> ((request, response) interaction with httpbody as csv)
	./pvrrenumi.sh $< > $@

xxx.pvrrdump_map.csv: 10002.run.05.jsonl
	@echo
	# (json-lines (jsonl)) -> ((request, response) files, (request, response) csv)
	./pvrrdump.sh -P xxx 10002.run.05.jsonl > $@

10002.run.05.jsonl: 10002.run.05.pcapng
	@echo
	# (packet capture (pcapng)) -> (json-lines (jsonl))
	./pvinspect.sh -p 10002 $< > $@

10002.run.05.pcapng:
	@echo
	# unzip (A2UI process interaction packet capture zip)
	unzip 10002.run.05.pcapng.zip

#----------------------------------------------------------------------------

test: xxx.testseqd.01.html xxx.testseqd.02.html

xxx.testseqd.01.html: pvseqdtempl.html pvtestseqd1.puml
	./pvgenseqdhtml.sh --template-html $< --puml-source pvtestseqd1.puml > $@

xxx.testseqd.02.html: pvseqdtempl.html pvtestseqd2.puml
	./pvgenseqdhtml.sh --template-html $< --puml-source pvtestseqd2.puml > $@

#----------------------------------------------------------------------------

THIS_FILE := $(lastword $(MAKEFILE_LIST))

make.tree.txt: $(THIS_FILE)
	@command -v make2graph >/dev/null 2>&1 || { echo "Warning: make2graph is not installed.";}
	@if [ ! -d "../makefile2graph" ]; then \
		echo "ERROR: Directory '../makefile2graph' not present!"; \
		exit 1; \
	else \
		echo "INFO: Directory '../makefile2graph' present!"; \
	fi
	make -Bnd | ../makefile2graph/make2graph | graph-easy --as_ascii > $@

#----------------------------------------------------------------------------

.PHONY: clean 

clean:
	rm -rfv xxx.*
	rm -rfv 10002.run.05.jsonl
	rm -rfv 10002.run.05.pcapng
