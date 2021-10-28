.PHONY: proto

proto:
	python -m grpc_tools.protoc -Iproto --python_out=. --python_grpc_out=. ./proto/goldstone/south/sonic/bcmd.proto

clean:
	rm -rf goldstone/south/sonic/bcmd_*.py
