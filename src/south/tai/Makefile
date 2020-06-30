PROJECT_DIR := ../../../
TAI_DIR := $(PROJECT_DIR)/sm/oopt-tai
TAISH_DIR := $(TAI_DIR)/tools/taish/

.DEFAULT_GOAL := all

INCLUDE := -I $(TAI_DIR)/inc -I $(PROJECT_DIR)/include

all: main

LIB := `pkg-config --libs protobuf grpc++ grpc`

OBJS := taish.grpc.pb.o taish.pb.o main.o taiclient.o

CC := g++
CFLAGS := -std=c++11

ifeq ($(VERBOSE),1)

CFLAGS += -g -O0

endif

.cc.o:
	$(CC) $(CFLAGS) $(INCLUDE) -c -o $@ $<

.cpp.o:
	$(CC) $(CFLAGS) $(INCLUDE) -c -o $@ $<

GRPC_FILES := taish.pb.cc taish.pb.h taish.grpc.pb.cc taish.grpc.pb.h

$(GRPC_FILES): $(TAISH_DIR)/proto/taish/taish.proto
	protoc --cpp_out=. -I $(TAISH_DIR)/proto/taish taish.proto
	protoc --grpc_out=. --plugin=protoc-gen-grpc=`which grpc_cpp_plugin` -I $(TAISH_DIR)proto/taish taish.proto

main: $(GRPC_FILES) Makefile $(OBJS)
	g++ -g -std=c++11 -o main $(OBJS) -lyang-cpp -lsysrepo-cpp $(LIB) -lgrpc++_reflection -lpthread -lyang -lsysrepo

clean:
	$(RM) $(GRPC_FILES) main *.o
