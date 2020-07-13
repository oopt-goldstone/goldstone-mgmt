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

#include <iostream>
#include <unordered_map>
#include <json.hpp>

using json = nlohmann::json;

class SonicController : public sysrepo::Callback {
    public:
        SonicController(sysrepo::S_Session& sess);
        ~SonicController();
        void loop();

        int module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data);
        int oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data);

    private:
        sysrepo::S_Connection m_conn;
        sysrepo::S_Session m_sess;
        sysrepo::S_Subscribe m_subscribe;

};

#endif // __CONTROLLER_HPP__
