#include <iostream>
#include <chrono>
#include <thread>
#include <csignal>

#include "controller.hpp"

volatile int exit_application = 0;

static void
sigint_handler(int signum)
{
    (void)signum;

    exit_application = 1;
}

static void
error_ly_print(libyang::S_Context& ctx) {
    auto errors = get_ly_errors(ctx);
    for (auto error : errors) {
        std::cout << "err: " << error->err() << std::endl;
        std::cout << "vecode: " << error->vecode() << std::endl;
        std::cout << "errmsg: " << error->errmsg() << std::endl;
        std::cout << "errpath: " << error->errpath() << std::endl;
        std::cout << "errapptag: " << error->errapptag() << std::endl;
    }
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

static void
print_val(const sr_val_t *value)
{
    if (NULL == value) {
        return;
    }

    printf("%s ", value->xpath);
//
//    switch (value->type) {
//    case SR_CONTAINER_T:
//    case SR_CONTAINER_PRESENCE_T:
//        printf("(container)");
//        break;
//    case SR_LIST_T:
//        printf("(list instance)");
//        break;
//    case SR_STRING_T:
//        printf("= %s", value->data.string_val);
//        break;
//    case SR_BOOL_T:
//        printf("= %s", value->data.bool_val ? "true" : "false");
//        break;
//    case SR_DECIMAL64_T:
//        printf("= %g", value->data.decimal64_val);
//        break;
//    case SR_INT8_T:
//        printf("= %" PRId8, value->data.int8_val);
//        break;
//    case SR_INT16_T:
//        printf("= %" PRId16, value->data.int16_val);
//        break;
//    case SR_INT32_T:
//        printf("= %" PRId32, value->data.int32_val);
//        break;
//    case SR_INT64_T:
//        printf("= %" PRId64, value->data.int64_val);
//        break;
//    case SR_UINT8_T:
//        printf("= %" PRIu8, value->data.uint8_val);
//        break;
//    case SR_UINT16_T:
//        printf("= %" PRIu16, value->data.uint16_val);
//        break;
//    case SR_UINT32_T:
//        printf("= %" PRIu32, value->data.uint32_val);
//        break;
//    case SR_UINT64_T:
//        printf("= %" PRIu64, value->data.uint64_val);
//        break;
//    case SR_IDENTITYREF_T:
//        printf("= %s", value->data.identityref_val);
//        break;
//    case SR_INSTANCEID_T:
//        printf("= %s", value->data.instanceid_val);
//        break;
//    case SR_BITS_T:
//        printf("= %s", value->data.bits_val);
//        break;
//    case SR_BINARY_T:
//        printf("= %s", value->data.binary_val);
//        break;
//    case SR_ENUM_T:
//        printf("= %s", value->data.enum_val);
//        break;
//    case SR_LEAF_EMPTY_T:
//        printf("(empty leaf)");
//        break;
//    default:
//        printf("(unprintable)");
//        break;
//    }
//
//    switch (value->type) {
//    case SR_UNKNOWN_T:
//    case SR_CONTAINER_T:
//    case SR_CONTAINER_PRESENCE_T:
//    case SR_LIST_T:
//    case SR_LEAF_EMPTY_T:
//        printf("\n");
//        break;
//    default:
//        printf("%s\n", value->dflt ? " [default]" : "");
//        break;
//    }
}

static void
print_change(sr_change_oper_t op, sr_val_t *old_val, sr_val_t *new_val)
{
//    switch(op) {
//    case SR_OP_CREATED:
//        printf("CREATED: ");
//        print_val(new_val);
//        break;
//    case SR_OP_DELETED:
//        printf("DELETED: ");
//        print_val(old_val);
//        break;
//    case SR_OP_MODIFIED:
//        printf("MODIFIED: ");
//        print_val(old_val);
//        printf("to ");
//        print_val(new_val);
//        break;
//    case SR_OP_MOVED:
//        printf("MOVED: %s\n", new_val->xpath);
//        break;
//    }
}

static int _populate_oper_data(libyang::S_Context& ctx, libyang::S_Data_Node& parent, const std::string& name, const std::string& path, const std::string& value) {
    std::stringstream xpath;
    xpath << "/goldstone-onlp:components/component[name='" << name << "']/" << path;
    parent->new_path(ctx, xpath.str().c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
    return 0;
}

#define SET_OPER_STATUS(type, prefix, value) \
    if ( (info.status & prefix ## _ ## value) > 0 ) { \
        _populate_oper_data(ctx, parent, name, #type "/state/status", #value); \
    }

static int _populate_oper_data_oid(libyang::S_Context& ctx, libyang::S_Data_Node& parent, const std::string& name, onlp_oid_t oid) {
    switch (ONLP_OID_TYPE_GET(oid)) {
    case ONLP_OID_TYPE_THERMAL:
        {
            onlp_thermal_info_t info;
            onlp_thermal_info_get(oid, &info);
            _populate_oper_data(ctx, parent, name, "thermal/state/temperature", std::to_string(info.mcelsius));
            if ( (info.status & ONLP_THERMAL_STATUS_PRESENT) > 0 ) {
                _populate_oper_data(ctx, parent, name, "thermal/state/status", "PRESENT");
            }
            if ( (info.status & ONLP_THERMAL_STATUS_FAILED) > 0 ) {
                _populate_oper_data(ctx, parent, name, "thermal/state/status", "FAILED");
            }
        }
        break;
    case ONLP_OID_TYPE_FAN:
        {
            std::cout << "FAN" << std::endl;
            onlp_fan_info_t info;
            onlp_fan_info_get(oid, &info);
            _populate_oper_data(ctx, parent, name, "fan/state/rpm", std::to_string(info.rpm));
            _populate_oper_data(ctx, parent, name, "fan/state/percentage", std::to_string(info.percentage));
            std::string mode;
            switch (info.mode) {
            case ONLP_FAN_MODE_OFF:
                mode = "OFF";
                break;
            case ONLP_FAN_MODE_SLOW:
                mode = "SLOW";
                break;
            case ONLP_FAN_MODE_NORMAL:
                mode = "NORMAL";
                break;
            case ONLP_FAN_MODE_FAST:
                mode = "FAST";
                break;
            }
            if ( mode.size() > 0 ) {
                _populate_oper_data(ctx, parent, name, "fan/state/mode", mode);
            }
            SET_OPER_STATUS(fan, ONLP_FAN_STATUS, PRESENT)
            SET_OPER_STATUS(fan, ONLP_FAN_STATUS, FAILED)
            SET_OPER_STATUS(fan, ONLP_FAN_STATUS, B2F)
            SET_OPER_STATUS(fan, ONLP_FAN_STATUS, F2B)
        }
        break;
    case ONLP_OID_TYPE_PSU:
        {
            onlp_psu_info_t info;
            onlp_psu_info_get(oid, &info);
            SET_OPER_STATUS(psu, ONLP_PSU_STATUS, PRESENT)
            SET_OPER_STATUS(psu, ONLP_PSU_STATUS, FAILED)
            SET_OPER_STATUS(psu, ONLP_PSU_STATUS, UNPLUGGED)
            _populate_oper_data(ctx, parent, name, "psu/state/input-current", std::to_string(info.miin));
            _populate_oper_data(ctx, parent, name, "psu/state/output-current", std::to_string(info.miout));
            _populate_oper_data(ctx, parent, name, "psu/state/input-voltage", std::to_string(info.mvin));
            _populate_oper_data(ctx, parent, name, "psu/state/output-voltage", std::to_string(info.mvout));
            _populate_oper_data(ctx, parent, name, "psu/state/input-power", std::to_string(info.mpin));
            _populate_oper_data(ctx, parent, name, "psu/state/output-power", std::to_string(info.mpout));
            _populate_oper_data(ctx, parent, name, "psu/state/model", info.model);
            _populate_oper_data(ctx, parent, name, "psu/state/serial", info.serial);
        }
        break;
    case ONLP_OID_TYPE_LED:
        {
            onlp_led_info_t info;
            onlp_led_info_get(oid, &info);
            SET_OPER_STATUS(led, ONLP_LED_STATUS, PRESENT)
            SET_OPER_STATUS(led, ONLP_LED_STATUS, FAILED)
            SET_OPER_STATUS(led, ONLP_LED_STATUS, ON)
            std::string mode;
            switch (info.mode) {
            case ONLP_LED_MODE_OFF:
                mode = "OFF";
                break;
            case ONLP_LED_MODE_ON:
                mode = "ON";
                break;
            case ONLP_LED_MODE_BLINKING:
                mode = "BLINKING";
                break;
            case ONLP_LED_MODE_RED:
                mode = "RED";
                break;
            case ONLP_LED_MODE_RED_BLINKING:
                mode = "RED_BLINKING";
                break;
            case ONLP_LED_MODE_ORANGE:
                mode = "ORANGE";
                break;
            case ONLP_LED_MODE_ORANGE_BLINKING:
                mode = "ORANGE_BLINKING";
                break;
            case ONLP_LED_MODE_YELLOW:
                mode = "YELLOW";
                break;
            case ONLP_LED_MODE_YELLOW_BLINKING:
                mode = "YELLOW_BLINKING";
                break;
            case ONLP_LED_MODE_GREEN:
                mode = "GREEN";
                break;
            case ONLP_LED_MODE_GREEN_BLINKING:
                mode = "GREEN_BLINKING";
                break;
            case ONLP_LED_MODE_BLUE:
                mode = "BLUE";
                break;
            case ONLP_LED_MODE_BLUE_BLINKING:
                mode = "BLUE_BLINKING";
                break;
            case ONLP_LED_MODE_PURPLE:
                mode = "PURPLE";
                break;
            case ONLP_LED_MODE_PURPLE_BLINKING:
                mode = "PURPLE_BLINKING";
                break;
            case ONLP_LED_MODE_AUTO:
                mode = "AUTO";
                break;
            case ONLP_LED_MODE_AUTO_BLINKING:
                mode = "AUTO_BLINKING";
                break;
            }
            if ( mode.size() > 0 ) {
                _populate_oper_data(ctx, parent, name, "led/state/mode", mode);
            }
            _populate_oper_data(ctx, parent, name, "led/state/character", std::to_string(info.character));
        }
    }
    return SR_ERR_OK;
}

int
iter__(onlp_oid_t oid, void* cookie)
{
    auto& map = *static_cast<std::map<onlp_oid_type_t, std::vector<onlp_oid_t>>*>(cookie);
    map[static_cast<onlp_oid_type_t>(ONLP_OID_TYPE_GET(oid))].emplace_back(oid);
    return 0;
}

static const std::string PLATFORM_MODULE_NAME = "goldstone-onlp";

#define SET_CAPS(type, prefix, value) \
    if ( (info.caps & prefix ## _ ## value) > 0 ) { \
        sess->set_item_str((xpath + #type "/state/capability").c_str(), #value); \
    }

int ONLPController::module_change(sysrepo::S_Session session, const char *module_name, const char *xpath, sr_event_t event, uint32_t request_id, void *private_data) {
    std::cout << "\n\n ========== EVENT " << ev_to_str(event) << " CHANGES: ====================================\n\n" << std::endl;
//    sr_change_iter_t *it;
//    sr_get_changes_iter(session, "//.", &it);
//
//    sr_change_oper_t oper;
//    sr_val_t *old_value = NULL, *new_value = NULL;
//
//    int rc = SR_ERR_OK;
//    while ((rc = sr_get_change_next(session, it, &oper, &old_value, &new_value)) == SR_ERR_OK) {
//        print_change(oper, old_value, new_value);
//        sr_free_val(old_value);
//        sr_free_val(new_value);
//    }
//
//    sr_free_change_iter(it);
//    printf("\n\n ========== EVENT %s CHANGES end\n", ev_to_str(event));

    return 0;
}

int ONLPController::oper_get_items(sysrepo::S_Session session, const char *module_name, const char *path, const char *request_xpath, uint32_t request_id, libyang::S_Data_Node &parent, void *private_data) {
    auto ly_ctx = session->get_context();
    sysrepo::Xpath_Ctx xpath_ctx;
    auto n = xpath_ctx.key_value(const_cast<char*>(request_xpath), "component", "name");
    std::cout << "xpath: " << path << ", request_xpath: " << request_xpath << std::endl;
    if ( n == nullptr ) {
        for ( auto& v : m_component_map ) {
            _populate_oper_data_oid(ly_ctx, parent, v.first, v.second);
        }
        return SR_ERR_OK;
    }
    auto name = std::string(n);

    auto it = m_component_map.find(name);
    if ( it == m_component_map.end() ) {
        std::cout << request_xpath << " : not found" << std::endl;
        return SR_ERR_NOT_FOUND;
    }
    auto oid = it->second;
    return _populate_oper_data_oid(ly_ctx, parent, name, oid);
}

ONLPController::ONLPController(sysrepo::S_Session& sess) : m_sess(sess), m_subscribe(new sysrepo::Subscribe(sess)) {
    onlp_init();
    std::map<onlp_oid_type_t, std::vector<onlp_oid_t>> map;
    onlp_oid_iterate(0, static_cast<onlp_oid_type_t>(0), iter__, &map);

    auto ly_ctx = sess->get_context();
    auto xpath = "/goldstone-onlp:components/component[name='sys']/config/name";
    m_component_map["sys"] = ONLP_OID_SYS;

    libyang::S_Data_Node data(new libyang::Data_Node(ly_ctx, xpath, "sys", LYD_ANYDATA_CONSTSTRING, 0));
    _init(ly_ctx, map, data, "fan", ONLP_OID_TYPE_FAN);
    _init(ly_ctx, map, data, "thermal", ONLP_OID_TYPE_THERMAL);
    _init(ly_ctx, map, data, "psu", ONLP_OID_TYPE_PSU);
    _init(ly_ctx, map, data, "led", ONLP_OID_TYPE_LED);
    _init(ly_ctx, map, data, "module", ONLP_OID_TYPE_MODULE);
    _init(ly_ctx, map, data, "rtc", ONLP_OID_TYPE_RTC);


    auto mod_name = PLATFORM_MODULE_NAME.c_str();
    auto callback = sysrepo::S_Callback(this);

    m_subscribe->module_change_subscribe(mod_name, callback);

    sess->replace_config(data, SR_DS_RUNNING, mod_name);

    sess->session_switch_ds(SR_DS_OPERATIONAL);

    for (auto m : m_component_map) {
        std::string type;
        auto name = m.first;
        auto oid = m.second;

        std::stringstream ss;
        ss << "/goldstone-onlp:components/component[name='" << name << "']/";
        auto xpath = ss.str();
        sess->set_item_str((xpath + "state/id").c_str(), std::to_string(oid).c_str());

        switch (ONLP_OID_TYPE_GET(oid)) {
        case ONLP_OID_TYPE_SYS:
            type = "SYS";
            break;
        case ONLP_OID_TYPE_THERMAL:
            type = "THERMAL";
            {
                onlp_thermal_info_t info;
                onlp_thermal_info_get(oid, &info);
                sess->set_item_str((xpath + "state/description").c_str(), info.hdr.description);
                sess->set_item_str((xpath + "thermal/state/thresholds/warning").c_str(), std::to_string(info.thresholds.warning).c_str());
                sess->set_item_str((xpath + "thermal/state/thresholds/error").c_str(), std::to_string(info.thresholds.error).c_str());
                sess->set_item_str((xpath + "thermal/state/thresholds/shutdown").c_str(), std::to_string(info.thresholds.shutdown).c_str());
                SET_CAPS(thermal, ONLP_THERMAL_CAPS, GET_TEMPERATURE)
                SET_CAPS(thermal, ONLP_THERMAL_CAPS, GET_WARNING_THRESHOLD)
                SET_CAPS(thermal, ONLP_THERMAL_CAPS, GET_ERROR_THRESHOLD)
                SET_CAPS(thermal, ONLP_THERMAL_CAPS, GET_SHUTDOWN_THRESHOLD)
            }
            break;
        case ONLP_OID_TYPE_FAN:
            type = "FAN";
            {
                onlp_fan_info_t info;
                onlp_fan_info_get(oid, &info);
                sess->set_item_str((xpath + "state/description").c_str(), info.hdr.description);
                SET_CAPS(fan, ONLP_FAN_CAPS, B2F)
                SET_CAPS(fan, ONLP_FAN_CAPS, F2B)
                SET_CAPS(fan, ONLP_FAN_CAPS, SET_RPM)
                SET_CAPS(fan, ONLP_FAN_CAPS, SET_PERCENTAGE)
                SET_CAPS(fan, ONLP_FAN_CAPS, GET_RPM)
                SET_CAPS(fan, ONLP_FAN_CAPS, GET_PERCENTAGE)
            }
            break;
        case ONLP_OID_TYPE_PSU:
            type = "PSU";
            {
                onlp_psu_info_t info;
                onlp_psu_info_get(oid, &info);
                sess->set_item_str((xpath + "state/description").c_str(), info.hdr.description);
                SET_CAPS(psu, ONLP_PSU_CAPS, AC)
                SET_CAPS(psu, ONLP_PSU_CAPS, DC12)
                SET_CAPS(psu, ONLP_PSU_CAPS, DC48)
                SET_CAPS(psu, ONLP_PSU_CAPS, VIN)
                SET_CAPS(psu, ONLP_PSU_CAPS, VOUT)
                SET_CAPS(psu, ONLP_PSU_CAPS, IIN)
                SET_CAPS(psu, ONLP_PSU_CAPS, IOUT)
                SET_CAPS(psu, ONLP_PSU_CAPS, PIN)
                SET_CAPS(psu, ONLP_PSU_CAPS, POUT)
            }
            break;
        case ONLP_OID_TYPE_MODULE:
            type = "MODULE";
            break;
        case ONLP_OID_TYPE_LED:
            type = "LED";
            {
                onlp_led_info_t info;
                onlp_led_info_get(oid, &info);
                sess->set_item_str((xpath + "state/description").c_str(), info.hdr.description);
                SET_CAPS(led, ONLP_LED_CAPS, ON_OFF)
                SET_CAPS(led, ONLP_LED_CAPS, CHAR)
                SET_CAPS(led, ONLP_LED_CAPS, RED)
                SET_CAPS(led, ONLP_LED_CAPS, RED_BLINKING)
                SET_CAPS(led, ONLP_LED_CAPS, ORANGE)
                SET_CAPS(led, ONLP_LED_CAPS, ORANGE_BLINKING)
                SET_CAPS(led, ONLP_LED_CAPS, YELLOW)
                SET_CAPS(led, ONLP_LED_CAPS, YELLOW_BLINKING)
                SET_CAPS(led, ONLP_LED_CAPS, GREEN)
                SET_CAPS(led, ONLP_LED_CAPS, GREEN_BLINKING)
                SET_CAPS(led, ONLP_LED_CAPS, BLUE)
                SET_CAPS(led, ONLP_LED_CAPS, BLUE_BLINKING)
                SET_CAPS(led, ONLP_LED_CAPS, PURPLE)
                SET_CAPS(led, ONLP_LED_CAPS, PURPLE_BLINKING)
                SET_CAPS(led, ONLP_LED_CAPS, AUTO)
                SET_CAPS(led, ONLP_LED_CAPS, AUTO_BLINKING)
            }
            break;
        }
        sess->set_item_str((xpath + "state/type").c_str(), type.c_str());
    }
    sess->apply_changes();
    m_subscribe->oper_get_items_subscribe(mod_name, "/goldstone-onlp:components/component[name='sys']/state", callback);
}

ONLPController::~ONLPController() {
}

void ONLPController::loop() {
    /* loop until ctrl-c is pressed / SIGINT is received */
    signal(SIGINT, sigint_handler);
    signal(SIGPIPE, SIG_IGN);
    while (!exit_application) {
        std::this_thread::sleep_for(std::chrono::seconds(1000));
    }
}

void ONLPController::_init(libyang::S_Context& ctx, std::map<onlp_oid_type_t, std::vector<onlp_oid_t>>& map, libyang::S_Data_Node& parent, const std::string& prefix, onlp_oid_type_t type) {
   std::stringstream xpath, value;
    for ( int i = 0; i < map[type].size(); i++ ) {
        std::stringstream xpath, value;
        value << prefix << i;
        xpath << "/goldstone-onlp:components/component[name='" << value.str() << "']/config/name";
        parent->new_path(ctx, xpath.str().c_str(), value.str().c_str(), LYD_ANYDATA_CONSTSTRING, 0);
        m_component_map[value.str()] = map[type][i];
    }
}

int main() {

    sysrepo::Logs().set_stderr(SR_LL_DBG);
    sysrepo::S_Connection conn(new sysrepo::Connection);
    sysrepo::S_Session sess(new sysrepo::Session(conn));

    auto controller = ONLPController(sess);

    controller.loop();

    std::cout << "Application exit requested, exiting." << std::endl;

    return 0;
}
