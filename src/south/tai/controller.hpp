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

#include "taiclient.hpp"
#include "tai.h"

struct object_info {
    tai_object_id_t oid;
    taish::TAIObjectType type;
    std::string xpath_prefix;
};

class TAIController : public sysrepo::Callback {
    public:
        TAIController(sysrepo::S_Session& sess);
        ~TAIController();
        void loop();

        int module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data);
        int oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data);

    private:
        int oper_get_single_item(sysrepo::S_Session session, const object_info& info, const char *request_xpath, libyang::S_Data_Node &parent);
        object_info object_info_from_xpath(const std::string& xpath);
        sysrepo::S_Session m_sess;
        sysrepo::S_Subscribe m_subscribe;
        TAIClient m_client;
        std::map<std::string, taish::Module> m_modules;
        bool _initialized;
};

#endif // __CONTROLLER_HPP__
