#include <iostream>
#include <chrono>
#include <thread>
#include <csignal>
#include <queue>
#include "controller.hpp"

//#include <swss-common/redispipeline.h>
//#include <swss-common/dbconnector.h>


volatile int exit_application = 0;

static const std::string SONIC_INTERFACE_MODULE_NAME= "goldstone-sonic-interface";

static void
sigint_handler(int signum)
{
    (void)signum;

    exit_application = 1;
}

static int _populate_oper_data(libyang::S_Context& ctx, libyang::S_Data_Node& parent, const std::string& name, const std::string& path, const std::string& value) {
    std::stringstream xpath;
    xpath << "/goldstone-sonic-interface:sonic-interfaces-state/sonic-interface-state[ifname='" << name << "']" << path;
    parent->new_path(ctx, xpath.str().c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
    return 0;
}

int SonicController::oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data) {
    sr_xpath_ctx_t xpath_ctx;
    auto ly_ctx = session->get_context();
    auto n = sr_xpath_key_value(const_cast<char*>(request_xpath), "sonic-interface-state", "ifname", &xpath_ctx);
    if ( n == nullptr ) {
        std::cout << "no name" << std::endl;
        return SR_ERR_OK;
    }

    auto name = std::string(n);
    lyd_node *tree = nullptr;
    std::stringstream ss;
    ss << "/goldstone-sonic-interface:sonic-interfaces-state/sonic-interface-state[ifname='" << name << "']";
    auto xpath = ss.str();
    _populate_oper_data(ly_ctx, parent, name, "/admin-status", "UP");
    _populate_oper_data(ly_ctx, parent, name, "/oper-status", "UP");
    _populate_oper_data(ly_ctx, parent, name, "/ifindex", "1");
    session->apply_changes();

    return SR_ERR_OK;
}

static void
print_current_config(sysrepo::S_Session session, const char *module_name)
{
   char select_xpath[100];
   try {
      snprintf(select_xpath, 100, "/%s:*//.", module_name);
      auto values = session->get_items(&select_xpath[0]);
      if (values == nullptr)
         return;
      for(unsigned int i = 0; i < values->val_cnt(); i++)
         std::cout << values->val(i)->to_string();
   } 
   catch( const std::exception& e ) {
      std::cout << e.what() << std::endl;
   }
}

int SonicController::module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data) {
    std::cout << "\n\n ========== EVENT CHANGES: ====================================\n\n" << std::endl;
    print_current_config(session, module_name);
    return SR_ERR_OK;
}

SonicController::SonicController(sysrepo::S_Session& sess) : m_sess(sess), m_subscribe(new sysrepo::Subscribe(sess)) {
    auto mod_name = SONIC_INTERFACE_MODULE_NAME.c_str();
    auto callback = sysrepo::S_Callback(this);

    m_subscribe->module_change_subscribe(mod_name, callback);
    /* read running config */
    std::cout << "\n\n ========== READING RUNNING CONFIG: ==========\n" << std::endl;
    print_current_config(sess, mod_name);
    m_subscribe->oper_get_items_subscribe(mod_name, "/goldstone-sonic-interface:sonic-interfaces-state/sonic-interface-state", callback);

}

SonicController::~SonicController() {
}

void SonicController::loop() {
    /* loop until ctrl-c is pressed / SIGINT is received */
    signal(SIGINT, sigint_handler);
    signal(SIGPIPE, SIG_IGN);
    while (!exit_application) {
        std::this_thread::sleep_for(std::chrono::seconds(1000));
    }
}

//using namespace swss;
int main() {

    sysrepo::Logs().set_stderr(SR_LL_DBG);
    sysrepo::S_Connection conn(new sysrepo::Connection);
    sysrepo::S_Session sess(new sysrepo::Session(conn));
    sysrepo::S_Subscribe subscribe(new sysrepo::Subscribe(sess));

#if 0
    //swss::Logger::linkToDbNative("sonic-mgmtd");
    DBConnector db(0, DBConnector::DEFAULT_UNIXSOCKET, 0); // APPL_DB
    RedisPipeline pipeline(&db);
    DBConnector stateDb(6, DBConnector::DEFAULT_UNIXSOCKET, 0); // STATE_DB

    m_stateMgmtPortTable(state_db, STATE_MGMT_PORT_TABLE_NAME);

    FieldValueTuple fv("oper_status", oper ? "up" : "down");
    vector<FieldValueTuple> fvs;
    fvs.push_back(fv);
    m_stateMgmtPortTable.set(key, fvs);
#endif

    auto controller = SonicController(sess);

    controller.loop();

    std::cout << "Application exit requested, exiting." << std::endl;

    return 0;
}
