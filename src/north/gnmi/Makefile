.PHONY: proto

ORIG_BASE := ../../../sm/gnmi/proto
OUT_BASE := goldstone/north/gnmi/proto

proto:
	mkdir -p $(OUT_BASE)
	cp $(ORIG_BASE)/gnmi/gnmi.proto $(OUT_BASE)
	cp $(ORIG_BASE)/gnmi_ext/gnmi_ext.proto $(OUT_BASE)
	sed -i -e 's/import "github\.com\/openconfig\/gnmi\/proto\/gnmi_ext\/gnmi_ext\.proto"/import "goldstone\/north\/gnmi\/proto\/gnmi_ext.proto"/' $(OUT_BASE)/gnmi.proto
	python -m grpc_tools.protoc -I=. --python_out=. --grpc_python_out=. $(OUT_BASE)/gnmi.proto $(OUT_BASE)/gnmi_ext.proto
	touch $(OUT_BASE)/__init__.py

clean:
	rm -rf $(OUT_BASE)
