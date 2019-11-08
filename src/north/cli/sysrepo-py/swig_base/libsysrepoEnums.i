%module libsysrepoEnums

%rename("$ignore", "not" %$isenum, "not" %$isenumitem, regextarget=1, fullname=1) "";

%{
#include "./src/sysrepo.h"
%}

%include "./src/sysrepo.h"
