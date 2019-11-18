all: sysrepo.py _sysrepo.so

SYSREPO_DIR := ../../../../../sm/sysrepo

PYTHON_HEADER_DIR := /usr/include/python3.4
PYTHON_LIB := python3.4m

sysrepo.py sysrepo_wrap.cxx: sysrepo.i Makefile
	swig -threads -c++ -python -I/usr/local/include -I$(SYSREPO_DIR) -I$(SYSREPO_DIR)/swig/cpp/src sysrepo.i

_sysrepo.so: sysrepo_wrap.cxx Makefile
	g++ -std=c++11 -fPIC -shared -I$(SYSREPO_DIR)/swig/cpp/src -I$(SYSREPO_DIR)  -I$(SYSREPO_DIR)/src -I$(PYTHON_HEADER_DIR) -I../../build -I../../modules ./sysrepo_wrap.cxx -o _sysrepo.so -lSysrepo-cpp -lsysrepo -l$(PYTHON_LIB)

clean:
	$(RM) -r _sysrepo.so *.o sysrepo_wrap.c sysrepo.py* sysrepo_wrap.cxx __pycache__
