#ifndef __CONTROLLER_HPP__
#define __CONTROLLER_HPP__


#include <map>
#include <vector>
#include <sstream>

#include <libyang/Libyang.hpp>
#include <sysrepo-cpp/Sysrepo.hpp>
#include <sysrepo-cpp/Connection.hpp>
#include <sysrepo-cpp/Session.hpp>
#include <sysrepo-cpp/Xpath.hpp>

extern "C" {

#include <onlp/onlp.h>
#include <onlp/oids.h>
#include <onlp/fan.h>
#include <onlp/psu.h>
#include <onlp/thermal.h>
#include <onlp/sys.h>
#include <onlp/led.h>

}

class ONLPController : public sysrepo::Callback {
    public:
        ONLPController(sysrepo::S_Session& sess);
        ~ONLPController();
        void loop();

        int module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data);
        int oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data);

    private:
        sysrepo::S_Session m_sess;
        sysrepo::S_Subscribe m_subscribe;
        std::map<std::string, onlp_oid_t> m_component_map;

        void _init(libyang::S_Context& ctx, std::map<onlp_oid_type_t, std::vector<onlp_oid_t>>& map, libyang::S_Data_Node& parent, const std::string& prefix, onlp_oid_type_t type);
};

#endif // __CONTROLLER_HPP__
