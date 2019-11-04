#ifndef __CONTROLLER_HPP__
#define __CONTROLLER_HPP__

extern "C" {

#include <libyang/libyang.h>
#include <sysrepo.h>
#include <sysrepo/xpath.h>
#include <onlp/onlp.h>
#include <onlp/oids.h>
#include <onlp/fan.h>
#include <onlp/psu.h>
#include <onlp/thermal.h>
#include <onlp/sys.h>
#include <onlp/led.h>

}

#include <iostream>
#include <map>
#include <vector>
#include <sstream>
#include <csignal>
#include <unistd.h>

class ONLPController {
    public:
        ONLPController(sr_session_ctx_t* sess);
        ~ONLPController();
        void loop();

        int get_oper_items(sr_session_ctx_t *session, const char *module_name, const char *xpath, const char *request_xpath,
                           uint32_t request_id, lyd_node **parent);

    private:
        sr_session_ctx_t* m_sess;
        sr_subscription_ctx_t* m_subscription;
        std::map<std::string, onlp_oid_t> m_component_map;

        void _init(ly_ctx* ly_ctx, std::map<onlp_oid_type_t, std::vector<onlp_oid_t>>& map, lyd_node* parent, const std::string& prefix, onlp_oid_type_t type);
};

#endif // __CONTROLLER_HPP__
