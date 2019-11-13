#include <iostream>
#include <csignal>
#include <thread>

#include "controller.hpp"

#include "tai.h"

volatile int exit_application = 0;

static const std::string PLATFORM_MODULE_NAME = "goldstone-tai";

static inline void ltrim(std::string &s) {
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), [](int ch) {
        return ch != '"';
    }));
}

static inline void rtrim(std::string &s) {
    s.erase(std::find_if(s.rbegin(), s.rend(), [](int ch) {
        return ch != '"';
    }).base(), s.end());
}

static inline void trim(std::string &s) {
    ltrim(s);
    rtrim(s);
}

static void
sigint_handler(int signum)
{
    (void)signum;

    exit_application = 1;
}

const char *
ev_to_str(sr_event_t ev)
{
    switch (ev) {
    case SR_EV_CHANGE:
        return "change";
    case SR_EV_DONE:
        return "done";
    case SR_EV_ENABLED:
        return "enabled";
    case SR_EV_ABORT:
    default:
        return "abort";
    }
}

int TAIController::module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data) {
    std::cout << "\n\n ========== EVENT " << ev_to_str(event) << " CHANGES: ====================================\n\n" << std::endl;
    return SR_ERR_OK;
}

static int _populate_oper_data(libyang::S_Context& ctx, libyang::S_Data_Node& parent, const std::string& name, const std::string& path, const std::string& value) {
    std::stringstream xpath;
    xpath << "/goldstone-tai:modules/module[name='" << name << "']/" << path;
    parent->new_path(ctx, xpath.str().c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
    return 0;
}

int TAIController::oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data) {
    auto ly_ctx = session->get_context();
    sysrepo::Xpath_Ctx xpath_ctx;
    std::string m, n, h;
    auto ptr = xpath_ctx.key_value(const_cast<char*>(request_xpath), "module", "name");
    if ( ptr != nullptr ) {
        m = std::string(ptr);
    }
    xpath_ctx.recover();
    ptr = xpath_ctx.key_value(const_cast<char*>(request_xpath), "network-interface", "name");
    if ( ptr != nullptr ) {
        n = std::string(ptr);
    }
    xpath_ctx.recover();
    ptr = xpath_ctx.key_value(const_cast<char*>(request_xpath), "host-interface", "name");
    if ( ptr != nullptr ) {
        h = std::string(ptr);
    }
    if ( m == "" ) {
        std::cout << "get all" << std::endl;
        return SR_ERR_OK;
    }
    if ( n == "" && h == "" ) {
        auto it = m_modules.find(m);
        if ( it == m_modules.end() ) {
            std::cout << "no module found with location: " << m << std::endl;
        }
        auto oid = it->second.oid();
        {
            std::string value;
            m_client.GetAttribute(oid, TAI_MODULE_ATTR_ADMIN_STATUS, value);
            if ( value != "" ) {
                trim(value);
                parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/admin-status").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
            }
        }
        m_client.GetAttribute(oid, TAI_MODULE_ATTR_VENDOR_PART_NUMBER, value);
        if ( value != "" ) {
            parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/vendor-part-number").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        m_client.GetAttribute(oid, TAI_MODULE_ATTR_VENDOR_SERIAL_NUMBER, value);
        if ( value != "" ) {
            parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/vendor-serial-number").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        m_client.GetAttribute(oid, TAI_MODULE_ATTR_FIRMWARE_VERSION, value);
        if ( value != "" ) {
            parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/firmware-version").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        m_client.GetAttribute(oid, TAI_MODULE_ATTR_OPER_STATUS, value);
        if ( value != "" ) {
            trim(value);
            parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/oper-status").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        m_client.GetAttribute(oid, TAI_MODULE_ATTR_TEMP, value);
        if ( value != "" ) {
            parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/temparature").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        m_client.GetAttribute(oid, TAI_MODULE_ATTR_POWER, value);
        if ( value != "" ) {
            parent->new_path(ly_ctx, ("/goldstone-tai:modules/module[name='" + m + "']/state/power-supply-voltage").c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
    }

    return SR_ERR_OK;
}

TAIController::TAIController(sysrepo::S_Session& sess) : m_sess(sess), m_subscribe(new sysrepo::Subscribe(sess)), m_client(grpc::CreateChannel("localhost:50051", grpc::InsecureChannelCredentials())) {
    std::vector<tai::Module> modules;
    m_client.ListModule(modules);

    auto ly_ctx = sess->get_context();
    libyang::S_Data_Node data = nullptr;
    for (auto& module : modules ) {
        std::stringstream ss;
        ss << "/goldstone-tai:modules/module[name='" << module.location() << "']/";
        auto xpath = ss.str();
        if ( data == nullptr ) {
            data = libyang::S_Data_Node(new libyang::Data_Node(ly_ctx, (xpath + "config/name").c_str(), module.location().c_str(), LYD_ANYDATA_CONSTSTRING, 0));
        } else {
            data->new_path(ly_ctx, (xpath + "config/name").c_str(), module.location().c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        for (auto& netif : module.netifs() ) {
            data->new_path(ly_ctx, (xpath + "network-interface[name='" + std::to_string(netif.index()) + "']/config/name").c_str(), std::to_string(netif.index()).c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        for (auto& hostif : module.hostifs() ) {
            data->new_path(ly_ctx, (xpath + "host-interface[name='" + std::to_string(hostif.index()) + "']/config/name").c_str(), std::to_string(hostif.index()).c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        }
        m_modules[module.location()] = module;
    }

    auto mod_name = PLATFORM_MODULE_NAME.c_str();
    auto callback = sysrepo::S_Callback(this);

    m_subscribe->module_change_subscribe(mod_name, callback);

    sess->replace_config(data, SR_DS_RUNNING, mod_name);

    sess->session_switch_ds(SR_DS_OPERATIONAL);

    for (auto& module : modules ) {
        std::stringstream ss;
        ss << "/goldstone-tai:modules/module[name='" << module.location() << "']/";
        auto xpath = ss.str();
        sess->set_item_str((xpath + "state/id").c_str(), std::to_string(module.oid()).c_str());
        std::string value;
        m_client.GetAttribute(module.oid(), TAI_MODULE_ATTR_VENDOR_NAME, value);
        sess->set_item_str((xpath + "state/vendor-name").c_str(), value.c_str());
        m_subscribe->oper_get_items_subscribe(mod_name, (xpath + "state").c_str(), callback);
        m_subscribe->oper_get_items_subscribe(mod_name, (xpath + "network-interface[name='0']/state").c_str(), callback);
        m_subscribe->oper_get_items_subscribe(mod_name, (xpath + "host-interface[name='0']/state").c_str(), callback);
    }
    sess->apply_changes();
}

TAIController::~TAIController() {
}

void TAIController::loop() {
    /* loop until ctrl-c is pressed / SIGINT is received */
    signal(SIGINT, sigint_handler);
    signal(SIGPIPE, SIG_IGN);
    while (!exit_application) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
}

void log_callback(LY_LOG_LEVEL level, const char *msg, const char *path) {
    std::cout << "msg: " << msg << std::endl;
    std::cout << "path: " << path << std::endl;
}

int main() {

    sysrepo::Logs().set_stderr(SR_LL_DBG);
    sysrepo::S_Connection conn(new sysrepo::Connection);
    sysrepo::S_Session sess(new sysrepo::Session(conn));

//    libyang::set_log_verbosity(LY_LLDBG);
//    libyang::set_log_options(LY_LOLOG);
//    ly_set_log_clb(log_callback, 0);

    try {
        auto controller = std::shared_ptr<TAIController>(new TAIController(sess));
        controller->loop();
        std::cout << "Application exit requested, exiting." << std::endl;
    } catch (...) {
        std::cout << "hello exception" << std::endl;
    }
}
