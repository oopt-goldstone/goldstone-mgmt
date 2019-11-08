%module sysrepo

%include <stdint.i>

/* Filter out 'Setting a const char * variable may leak memory' warnings */
%warnfilter(451);

/* Filter out 'Identifier '~Subscribe' redefined by %extend (ignored)'*/
%warnfilter(302);

%{
    extern "C" {
        #include "sysrepo.h"
    }

%}

%include <std_except.i>
%catches(std::runtime_error, std::exception, std::string);

%inline %{
#include <unistd.h>
#include "sysrepo.h"
#include <signal.h>
#include <vector>
#include <memory>

#include "Sysrepo.hpp"
#include "Struct.hpp"
#include "Session.hpp"

/* custom infinite loop */
volatile int exit_application = 0;

static void
sigint_handler(int signum)
{
    exit_application = 1;
}


static void global_loop() {
    /* loop until ctrl-c is pressed / SIGINT is received */
    signal(SIGINT, sigint_handler);
    while (!exit_application) {
        sleep(1000);  /* or do some more useful work... */
    }
}

class Wrap_cb {
public:
    Wrap_cb(PyObject *callback): _callback(nullptr) {

        if (!PyCallable_Check(callback)) {
            throw std::runtime_error("Python Object is not callable.\n");
        }
        else {
            _callback = callback;
            Py_XINCREF(_callback);
        }
    }
    ~Wrap_cb() {
        if(_callback)
            Py_XDECREF(_callback);
    }

    int module_change_subscribe(sr_session_ctx_t *session, const char *module_name, const char *xpath, \
                                sr_event_t event, uint32_t request_id, PyObject *private_ctx) {
        PyObject *arglist;
#if defined(SWIG_PYTHON_THREADS)
        SWIG_Python_Thread_Block safety;
#endif

        sysrepo::Session *sess = (sysrepo::Session *)new sysrepo::Session(session);
        std::shared_ptr<sysrepo::Session> *shared_sess = sess ? new std::shared_ptr<sysrepo::Session>(sess) : 0;
        PyObject *s = SWIG_NewPointerObj(SWIG_as_voidptr(shared_sess), SWIGTYPE_p_std__shared_ptrT_sysrepo__Session_t, SWIG_POINTER_OWN);

        arglist = Py_BuildValue("(OssiiO)", s, module_name, xpath, event, request_id, private_ctx);
        PyObject *result = PyEval_CallObject(_callback, arglist);
        Py_DECREF(arglist);
        sess->~Session();
        Py_DECREF(s);
        if (result == nullptr) {
            throw std::runtime_error("Python callback module_change_subscribe failed.\n");
        } else {
            int ret = SR_ERR_OK;
            if (result && PyInt_Check(result)) {
                ret = PyInt_AsLong(result);
            }
            Py_DECREF(result);
            return ret;
        }
    }

    int oper_get_items_subscribe(sr_session_ctx_t *session, const char *module_name, const char *path, \
                                 const char *request_xpath, uint32_t request_id, struct lyd_node **parent, PyObject *private_ctx) {
        PyObject *arglist;
#if defined(SWIG_PYTHON_THREADS)
        SWIG_Python_Thread_Block safety;
#endif

        sysrepo::Session *sess = (sysrepo::Session *)new sysrepo::Session(session);
        std::shared_ptr<sysrepo::Session> *shared_sess = sess ? new std::shared_ptr<sysrepo::Session>(sess) : 0;
        PyObject *s = SWIG_NewPointerObj(SWIG_as_voidptr(shared_sess), SWIGTYPE_p_std__shared_ptrT_sysrepo__Session_t, SWIG_POINTER_OWN);

        arglist = Py_BuildValue("(OsssiOO)", s, module_name, path, request_xpath, request_id, parent, private_ctx);
        PyObject *result = PyEval_CallObject(_callback, arglist);
        Py_DECREF(arglist);
        sess->~Session();
        Py_DECREF(s);
        if (result == nullptr) {
            sess->~Session();
            throw std::runtime_error("Python callback oper_get_items_subscribe failed.\n");
        } else {
            sess->~Session();
            int ret = SR_ERR_OK;
            if (result && PyInt_Check(result)) {
                ret = PyInt_AsLong(result);
            }
            Py_DECREF(result);
            return ret;
        }
    }

    PyObject *private_ctx;

private:
    PyObject *_callback;
};


static int g_module_change_subscribe_cb(sr_session_ctx_t *session, const char *module_name, const char *xpath,
                                        sr_event_t event, uint32_t request_id, void *private_ctx)
{
    Wrap_cb *ctx = (Wrap_cb *) private_ctx;
    return ctx->module_change_subscribe(session, module_name, xpath, event, request_id, ctx->private_ctx);
}

static int g_oper_get_items_subscribe_cb(sr_session_ctx_t *session, const char *module_name, const char *path,
                                         const char *request_xpath, uint32_t request_id, struct lyd_node **parent, void *private_ctx)
{
    Wrap_cb *ctx = (Wrap_cb *) private_ctx;
    return ctx->oper_get_items_subscribe(session, module_name, path, request_xpath, request_id, parent, ctx->private_ctx);
}

%}

%extend sysrepo::Subscribe {

    void module_change_subscribe(const char *module_name, PyObject *callback, const char *xpath = nullptr, PyObject *private_ctx = nullptr, \
                                 uint32_t priority = 0, sr_subscr_options_t opts = SUBSCR_DEFAULT) {
        /* create class */
        Wrap_cb *class_ctx = nullptr;
        class_ctx = new Wrap_cb(callback);

        self->wrap_cb_l.push_back(class_ctx);
        if (private_ctx) {
            class_ctx->private_ctx = private_ctx;
        } else {
            Py_INCREF(Py_None);
            class_ctx->private_ctx = Py_None;
        }

        int ret = sr_module_change_subscribe(self->swig_sess(), module_name, xpath, g_module_change_subscribe_cb, \
                                             class_ctx, priority, opts, self->swig_sub());
        if (SR_ERR_OK != ret) {
            throw std::runtime_error(sr_strerror(ret));
        }
    };

    void oper_get_items_subscribe(const char *module_name, const char *xpath, PyObject *callback, PyObject *private_ctx = nullptr, \
                                  sr_subscr_options_t opts = SUBSCR_DEFAULT) {
        /* create class */
        Wrap_cb *class_ctx = nullptr;
        class_ctx = new Wrap_cb(callback);

        self->wrap_cb_l.push_back(class_ctx);
        if (private_ctx) {
            class_ctx->private_ctx = private_ctx;
        } else {
            Py_INCREF(Py_None);
            class_ctx->private_ctx = Py_None;
        }

        int ret = sr_oper_get_items_subscribe(self->swig_sess(), module_name, xpath, g_oper_get_items_subscribe_cb, \
                                              class_ctx, opts, self->swig_sub());
        if (SR_ERR_OK != ret) {
            throw std::runtime_error(sr_strerror(ret));
        }
    };

};

%include "libyang/Internal.hpp"
%include "../swig_base/python_base.i"
