%module python_base

%ignore Callback;

%ignore sysrepo::Val::Val(int8_t);
%ignore sysrepo::Val::Val(int16_t);
%ignore sysrepo::Val::Val(int32_t);
%ignore sysrepo::Val::Val(uint8_t);
%ignore sysrepo::Val::Val(uint16_t);
%ignore sysrepo::Val::Val(uint32_t);
%ignore sysrepo::Val::Val(uint64_t);

%ignore sysrepo::Val::set(char const *,int8_t);
%ignore sysrepo::Val::set(char const *,int16_t);
%ignore sysrepo::Val::set(char const *,int32_t);
%ignore sysrepo::Val::set(char const *,uint8_t);
%ignore sysrepo::Val::set(char const *,uint16_t);
%ignore sysrepo::Val::set(char const *,uint32_t);
%ignore sysrepo::Val::set(char const *,uint64_t);

%include "../swig_base/base.i"
%include "../swig_base/libsysrepoEnums.i"
