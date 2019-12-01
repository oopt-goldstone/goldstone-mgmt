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

static int _key_value(const std::string& xpath, const std::string& key, int& out) {
    sysrepo::Xpath_Ctx xpath_ctx;
    char tmp[128] = {0};
    xpath.copy(tmp, 128);
    auto ptr = xpath_ctx.key_value(tmp, key.c_str(), "name");
    if ( ptr == nullptr ) {
        return -1;
    }
    try {
        out = std::stoi(std::string(ptr));
    } catch ( ... ) {
        return -1;
    }
    return 0;
}

object_info TAIController::object_info_from_xpath(const std::string& xpath) {
    object_info info = {0};
    info.oid = TAI_NULL_OBJECT_ID;
    int module, netif, hostif;
    const std::string prefix = "/goldstone-tai:modules";
    if ( _key_value(xpath, "module", module) < 0 ) {
        return info;
    }
    auto it = m_modules.find(std::to_string(module));
    if ( it == m_modules.end() ) {
        return info;
    }
    auto n = _key_value(xpath, "network-interface", netif);
    auto h = _key_value(xpath, "host-interface", hostif);
    info.xpath_prefix = prefix + "/module[name='" + it->first + "']";
    if ( n < 0 && h < 0 ) {
        info.type = tai::TAIObjectType::MODULE;
        info.oid = it->second.oid();
        return info;
    }
    if ( n == 0 ) {
        info.type = tai::TAIObjectType::NETIF;
        auto v = it->second.netifs(netif);
        info.oid = v.oid();
        info.xpath_prefix += "/network-interface[name='" + std::to_string(netif) + "']";
        return info;
    }
    info.type = tai::TAIObjectType::HOSTIF;
    auto v = it->second.hostifs(hostif);
    info.oid = v.oid();
    info.xpath_prefix += "/host-interface[name='" + std::to_string(hostif) + "']";
    return info;
}

int TAIController::module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data) {
    if ( event == SR_EV_DONE ) {
        return SR_ERR_OK;
    }
    std::cout << "========== EVENT " << ev_to_str(event) << " CHANGES: ====================================" << std::endl;
    auto it = session->get_changes_iter("//.");
    sysrepo::S_Change change;
    while ( (change = session->get_change_next(it)) != nullptr ) {
        if ( change->oper() == SR_OP_CREATED || change->oper() == SR_OP_MODIFIED ) {
            auto n = change->new_val();
            auto info = object_info_from_xpath(std::string(n->xpath()));
            if ( info.oid == TAI_NULL_OBJECT_ID ) {
                std::cout << "failed to find oid with xpath: " << n->xpath() << std::endl;
                continue;
            }
            std::cout << "xpath: " << n->xpath() << ", oid: " << info.oid << std::endl;
            {
                sysrepo::Xpath_Ctx xpath_ctx;
                char tmp[128] = {0};
                std::string(n->xpath()).copy(tmp, 128);
                auto v = xpath_ctx.node(tmp, "config");
                if ( v == nullptr ) {
                    std::cout << "failed to find config node: " << n->xpath() << std::endl;
                    continue;
                }
                v = xpath_ctx.last_node(nullptr);
                if ( v == nullptr ) {
                    std::cout << "failed to find last node: " << n->xpath() << std::endl;
                    continue;
                }
                if ( m_client.SetAttribute(info.oid, info.type, std::string(v), n->val_to_string()) ) {
                    std::cout << "failed to set attribute: " << v << std::endl;
                    continue;
                }
            }
        }
    }
    return SR_ERR_OK;
}

static int _oper_data_filter(const char *path, tai::TAIObjectType type) {
    std::string v(path);
    switch (type) {
    case tai::TAIObjectType::MODULE:
        if ( v.find("network-interface") != std::string::npos ) {
            return 1;
        }
        if ( v.find("host-interface") != std::string::npos ) {
            return 1;
        }
        break;
    case tai::TAIObjectType::NETIF:
        return (v.find("network-interface") != std::string::npos) ? 0 : 1;
    case tai::TAIObjectType::HOSTIF:
        return (v.find("host-interface") != std::string::npos) ? 0 : 1;
    }
    return 0;
}

int TAIController::oper_get_single_item(sysrepo::S_Session session, const object_info& info, const char *request_xpath, libyang::S_Data_Node &parent) {
    sysrepo::Xpath_Ctx xpath_ctx;
    char tmp[128] = {0};
    std::string(request_xpath).copy(tmp, 128);
    auto v = xpath_ctx.node(tmp, "state");
    if ( v == nullptr ) {
        std::cout << "failed to find state node: " << request_xpath << std::endl;
        return 1;
    }
    v = xpath_ctx.last_node(nullptr);
    if ( v == nullptr ) {
        std::cout << "failed to find last node: " << request_xpath << std::endl;
        return 1;
    }

    tai::AttributeMetadata meta;
    m_client.GetAttributeMetadata(info.type, std::string(v), meta);
    std::string value;
    if ( m_client.GetAttribute(info.oid, meta.attr_id(), value) ) {
        std::cout << "failed to get attribute: " << meta.short_name() << std::endl;
        return -1;
    }
    trim(value);
    auto ly_ctx = session->get_context();
    parent->new_path(ly_ctx, (info.xpath_prefix + "/state/" + meta.short_name()).c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
    return 0;
}

int TAIController::oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data) {
    auto ly_ctx = session->get_context();
    auto info = object_info_from_xpath(std::string(request_xpath));
    if ( info.oid == TAI_NULL_OBJECT_ID ) {
        std::cout << "get all" << std::endl;
        return SR_ERR_OK;
    }
    if ( _oper_data_filter(path, info.type) ) {
        return SR_ERR_OK;
    }

    auto ret = oper_get_single_item(session, info, request_xpath, parent);
    if ( ret == 0 ) {
        return SR_ERR_OK;
    } else if ( ret < 0 ) {
        return SR_ERR_SYS;
    }

    std::vector<tai::AttributeMetadata> list;
    if ( m_client.ListAttributeMetadata(info.type, list) ) {
        std::cout << "failed to get attribute metadata list" << std::endl;
        return SR_ERR_OK;
    }

    std::cout << "path: " << path << "request_xpath: " << request_xpath << ", info: " << info.xpath_prefix  << std::endl;

    int limit;
    if ( info.type == tai::TAIObjectType::MODULE ) {
        limit = TAI_MODULE_ATTR_CUSTOM_RANGE_START;
    } else if ( info.type == tai::TAIObjectType::NETIF ) {
        limit = TAI_NETWORK_INTERFACE_ATTR_CUSTOM_RANGE_START;
    } else {
        limit = TAI_HOST_INTERFACE_ATTR_CUSTOM_RANGE_START;
    }

    for ( const auto& m : list ) {
        std::string value;
        if ( m.attr_id() > limit ) {
            continue;
        }
        if ( m_client.GetAttribute(info.oid, m.attr_id(), value) ) {
            std::cout << "failed to get attribute: " << m.short_name() << std::endl;
            continue;
        }
        trim(value);
        std::cout << "attr: " << m.short_name() << ": " << value << std::endl;
        try {
            parent->new_path(ly_ctx, (info.xpath_prefix + "/state/" + m.short_name()).c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        } catch (...) {
            std::cout << "failed to add path" << std::endl;
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

    if ( data != nullptr ) {
        sess->replace_config(data, SR_DS_RUNNING, mod_name);
    }

    sess->session_switch_ds(SR_DS_OPERATIONAL);

    for (auto& module : modules ) {
        std::stringstream ss;
        ss << "/goldstone-tai:modules/module[name='" << module.location() << "']/";
        auto xpath = ss.str();
        sess->set_item_str((xpath + "state/id").c_str(), std::to_string(module.oid()).c_str());
        std::string value;
        m_client.GetAttribute(module.oid(), TAI_MODULE_ATTR_VENDOR_NAME, value);
        sess->set_item_str((xpath + "state/vendor-name").c_str(), value.c_str());
    }

    std::string xpath = "/goldstone-tai:modules/module/";

    m_subscribe->oper_get_items_subscribe(mod_name, (xpath + "state").c_str(), callback);
    m_subscribe->oper_get_items_subscribe(mod_name, (xpath + "network-interface/state").c_str(), callback);
    m_subscribe->oper_get_items_subscribe(mod_name, (xpath + "host-interface/state").c_str(), callback);

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

    try {
        auto controller = std::shared_ptr<TAIController>(new TAIController(sess));
        controller->loop();
        std::cout << "Application exit requested, exiting." << std::endl;
    } catch (...) {
        std::cout << "hello exception" << std::endl;
    }
}
