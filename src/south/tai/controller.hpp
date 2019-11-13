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

class TAIController : public sysrepo::Callback {
    public:
        TAIController(sysrepo::S_Session& sess);
        ~TAIController();
        void loop();

        int module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data);
        int oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data);

    private:
        sysrepo::S_Session m_sess;
        sysrepo::S_Subscribe m_subscribe;
        TAIClient m_client;
        std::map<std::string, tai::Module> m_modules;
};

#endif // __CONTROLLER_HPP__
