#ifndef __CONTROLLER_HPP__
#define __CONTROLLER_HPP__

extern "C" {

#include <libyang/libyang.h>
#include <sysrepo.h>
#include <sysrepo/xpath.h>

}

#include <iostream>
#include <map>
#include <vector>
#include <sstream>
#include <csignal>
#include <unistd.h>

class OpenConfigConverter {
    public:
        OpenConfigConverter(sr_session_ctx_t* sess);
        ~OpenConfigConverter();
        void loop();

        int get_oper_items(sr_session_ctx_t *session, const char *module_name, const char *xpath, const char *request_xpath,
                           uint32_t request_id, lyd_node **parent);

    private:
        sr_session_ctx_t* m_sess;
        sr_subscription_ctx_t* m_subscription;
};

#endif // __CONTROLLER_HPP__
