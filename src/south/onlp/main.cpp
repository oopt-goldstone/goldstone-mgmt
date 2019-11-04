#include "controller.hpp"

volatile int exit_application = 0;

static void
sigint_handler(int signum)
{
    (void)signum;

    exit_application = 1;
}

static void
error_print(int sr_error, const char *format, ...)
{
    va_list ap;
    char msg[2048];

    if (!sr_error) {
        sprintf(msg, "sysrepoctl error: %s\n", format);
    } else {
        sprintf(msg, "sysrepoctl error: %s (%s)\n", format, sr_strerror(sr_error));
    }

    va_start(ap, format);
    vfprintf(stderr, msg, ap);
    va_end(ap);
}

static void
error_ly_print(struct ly_ctx *ctx)
{
    struct ly_err_item *e;

    for (e = ly_err_first(ctx); e; e = e->next) {
        error_print(0, "libyang: %s", e->msg);
    }

    ly_err_clean(ctx, NULL);
}

const char *
ev_to_str(sr_event_t ev)
{
    switch (ev) {
    case SR_EV_CHANGE:
        return "change";
    case SR_EV_DONE:
        return "done";
    case SR_EV_ABORT:
    default:
        return "abort";
    }
}

static int
module_change_cb(sr_session_ctx_t *session, const char *module_name, const char *xpath, sr_event_t event,
        uint32_t request_id, void *private_data)
{
    printf("\n\n ========== EVENT %s CHANGES: ====================================\n\n", ev_to_str(event));

    return SR_ERR_OK;
}

static int
oper_get_items_cb(sr_session_ctx_t *session, const char *module_name, const char *xpath, const char *request_xpath,
        uint32_t request_id, struct lyd_node **parent, void *private_data)
{
    auto ctrl = static_cast<ONLPController*>(private_data);
    return ctrl->get_oper_items(session, module_name, xpath, request_xpath, request_id, parent);
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
        r = sr_set_item_str(sess, (xpath + #type "/state/capability").c_str(), #value, NULL, 0); \
        if (r) { \
            error_print(r, "Failed to set capability"); \
        } \
    }

ONLPController::ONLPController(sr_session_ctx_t* sess) : m_sess(sess) {
    onlp_init();
    std::map<onlp_oid_type_t, std::vector<onlp_oid_t>> map;
    onlp_oid_iterate(0, static_cast<onlp_oid_type_t>(0), iter__, &map);

    auto ly_ctx = (struct ly_ctx *)sr_get_context(sr_session_get_connection(sess));
    auto xpath = "/goldstone-onlp:components/component[name='sys']/config/name";
    auto v = strdup("sys");
    m_component_map["sys"] = ONLP_OID_SYS;
    auto data = lyd_new_path(nullptr, ly_ctx, xpath, v, LYD_ANYDATA_STRING, 0);
    _init(ly_ctx, map, data, "fan", ONLP_OID_TYPE_FAN);
    _init(ly_ctx, map, data, "thermal", ONLP_OID_TYPE_THERMAL);
    _init(ly_ctx, map, data, "psu", ONLP_OID_TYPE_PSU);
    _init(ly_ctx, map, data, "led", ONLP_OID_TYPE_LED);
    _init(ly_ctx, map, data, "module", ONLP_OID_TYPE_MODULE);
    _init(ly_ctx, map, data, "rtc", ONLP_OID_TYPE_RTC);

    auto mod_name = PLATFORM_MODULE_NAME.c_str();

    auto r = sr_module_change_subscribe(sess, mod_name, nullptr, module_change_cb, NULL, 0, 0, &m_subscription);
    if (r != SR_ERR_OK) {
        error_print(r, "Failed to subscribe module change");
    }

    r = sr_replace_config(sess, mod_name, data, sr_session_get_ds(sess), 0);
    if (r) {
        error_print(r, "Replace config failed");
    }

    r = sr_session_switch_ds(sess, SR_DS_OPERATIONAL);
    if (r) {
        error_print(r, "Failed to switch DS to operational");
    }

    for (auto m : m_component_map) {
        std::string type;
        auto name = m.first;
        auto oid = m.second;

        std::stringstream ss;
        ss << "/goldstone-onlp:components/component[name='" << name << "']/";
        auto xpath = ss.str();

        r = sr_set_item_str(sess, (xpath + "state/id").c_str(), std::to_string(oid).c_str(), NULL, 0);
        if (r) {
            error_print(r, "Failed to set type");
        }

        switch (ONLP_OID_TYPE_GET(oid)) {
        case ONLP_OID_TYPE_SYS:
            type = "SYS";
            break;
        case ONLP_OID_TYPE_THERMAL:
            type = "THERMAL";
            {
                onlp_thermal_info_t info;
                onlp_thermal_info_get(oid, &info);
                sr_set_item_str(sess, (xpath + "state/description").c_str(), info.hdr.description, NULL, 0);
                sr_set_item_str(sess, (xpath + "thermal/state/thresholds/warning").c_str(), std::to_string(info.thresholds.warning).c_str(), NULL, 0);
                sr_set_item_str(sess, (xpath + "thermal/state/thresholds/error").c_str(), std::to_string(info.thresholds.error).c_str(), NULL, 0);
                sr_set_item_str(sess, (xpath + "thermal/state/thresholds/shutdown").c_str(), std::to_string(info.thresholds.shutdown).c_str(), NULL, 0);
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
                sr_set_item_str(sess, (xpath + "state/description").c_str(), info.hdr.description, NULL, 0);
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
                sr_set_item_str(sess, (xpath + "state/description").c_str(), info.hdr.description, NULL, 0);
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
                sr_set_item_str(sess, (xpath + "state/description").c_str(), info.hdr.description, NULL, 0);
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
        r = sr_set_item_str(sess, (xpath + "state/type").c_str(), type.c_str(), NULL, 0);
        if (r) {
            error_print(r, "Failed to set type");
        }
    }

    r = sr_apply_changes(sess, 0);
    if (r) {
        error_print(r, "Failed to apply changes");
    }

    r = sr_oper_get_items_subscribe(sess, mod_name, "/goldstone-onlp:components/component[name='sys']/state", oper_get_items_cb, this, 0, &m_subscription);
    if (r != SR_ERR_OK) {
        error_print(r, "Failed to subscribe oper get");
    }
}

ONLPController::~ONLPController() {
    sr_unsubscribe(m_subscription);
}

void ONLPController::loop() {
    /* loop until ctrl-c is pressed / SIGINT is received */
    signal(SIGINT, sigint_handler);
    signal(SIGPIPE, SIG_IGN);
    while (!exit_application) {
        sleep(1000);
    }
}

static int _populate_oper_data(ly_ctx *ctx, lyd_node *parent, const std::string& name, const std::string& path, const std::string& value) {
    std::stringstream xpath;
    xpath << "/goldstone-onlp:components/component[name='" << name << "']/" << path;
    auto v = strdup(value.c_str());
    lyd_new_path(parent, nullptr, xpath.str().c_str(), v, LYD_ANYDATA_STRING, 0);
    if ( ly_errno ) {
        std::cout << "xpath: " << xpath.str() << ", value: " << value << std::endl;
        error_ly_print(ctx);
        return -1;
    }
    return 0;
}

#define SET_OPER_STATUS(type, prefix, value) \
    if ( (info.status & prefix ## _ ## value) > 0 ) { \
        _populate_oper_data(ly_ctx, parent, name, #type "/state/status", #value); \
    }

static int _populate_oper_data_oid(ly_ctx *ly_ctx, lyd_node *parent, const std::string& name, onlp_oid_t oid) {
    switch (ONLP_OID_TYPE_GET(oid)) {
    case ONLP_OID_TYPE_THERMAL:
        {
            onlp_thermal_info_t info;
            onlp_thermal_info_get(oid, &info);
            _populate_oper_data(ly_ctx, parent, name, "thermal/state/temperature", std::to_string(info.mcelsius));
            if ( (info.status & ONLP_THERMAL_STATUS_PRESENT) > 0 ) {
                _populate_oper_data(ly_ctx, parent, name, "thermal/state/status", "PRESENT");
            }
            if ( (info.status & ONLP_THERMAL_STATUS_FAILED) > 0 ) {
                _populate_oper_data(ly_ctx, parent, name, "thermal/state/status", "FAILED");
            }
        }
        break;
    case ONLP_OID_TYPE_FAN:
        {
            std::cout << "FAN" << std::endl;
            onlp_fan_info_t info;
            onlp_fan_info_get(oid, &info);
            _populate_oper_data(ly_ctx, parent, name, "fan/state/rpm", std::to_string(info.rpm));
            _populate_oper_data(ly_ctx, parent, name, "fan/state/percentage", std::to_string(info.percentage));
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
                _populate_oper_data(ly_ctx, parent, name, "fan/state/mode", mode);
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
            _populate_oper_data(ly_ctx, parent, name, "psu/state/input-current", std::to_string(info.miin));
            _populate_oper_data(ly_ctx, parent, name, "psu/state/output-current", std::to_string(info.miout));
            _populate_oper_data(ly_ctx, parent, name, "psu/state/input-voltage", std::to_string(info.mvin));
            _populate_oper_data(ly_ctx, parent, name, "psu/state/output-voltage", std::to_string(info.mvout));
            _populate_oper_data(ly_ctx, parent, name, "psu/state/input-power", std::to_string(info.mpin));
            _populate_oper_data(ly_ctx, parent, name, "psu/state/output-power", std::to_string(info.mpout));
            _populate_oper_data(ly_ctx, parent, name, "psu/state/model", info.model);
            _populate_oper_data(ly_ctx, parent, name, "psu/state/serial", info.serial);
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
                _populate_oper_data(ly_ctx, parent, name, "led/state/mode", mode);
            }
            _populate_oper_data(ly_ctx, parent, name, "led/state/character", std::to_string(info.character));
        }
    }
    return SR_ERR_OK;
}

int ONLPController::get_oper_items(sr_session_ctx_t *session, const char *module_name, const char *xpath, const char *request_xpath,
                                   uint32_t request_id, lyd_node **parent) {
    auto ly_ctx = (struct ly_ctx*)sr_get_context(sr_session_get_connection(session));
    sr_xpath_ctx_t xpath_ctx;
    auto n = sr_xpath_key_value(const_cast<char*>(request_xpath), "component", "name", &xpath_ctx);
    std::cout << "xpath: " << xpath << ", request_xpath: " << request_xpath << std::endl;
    if ( n == nullptr ) {
        for ( auto& v : m_component_map ) {
            _populate_oper_data_oid(ly_ctx, *parent, v.first, v.second);
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
    return _populate_oper_data_oid(ly_ctx, *parent, name, oid);
}

void ONLPController::_init(ly_ctx* ly_ctx, std::map<onlp_oid_type_t, std::vector<onlp_oid_t>>& map, lyd_node* parent, const std::string& prefix, onlp_oid_type_t type) {
   std::stringstream xpath, value;
    for ( int i = 0; i < map[type].size(); i++ ) {
        std::stringstream xpath, value;
        value << prefix << i;
        xpath << "/goldstone-onlp:components/component[name='" << value.str() << "']/config/name";
        auto v = strdup(value.str().c_str());
        lyd_new_path(parent, ly_ctx, xpath.str().c_str(), v, LYD_ANYDATA_STRING, 0);
        m_component_map[value.str()] = map[type][i];
    }
}

int main() {

    sr_conn_ctx_t *conn = NULL;
    sr_session_ctx_t *sess = NULL;
    sr_datastore_t ds = SR_DS_RUNNING;
    sr_log_stderr(SR_LL_DBG);
    int r;

    if ((r = sr_connect(0, &conn)) != SR_ERR_OK) {
        error_print(r, "Failed to connect");
        return -1;
    }

    /* create session */
    if ((r = sr_session_start(conn, ds, &sess)) != SR_ERR_OK) {
        error_print(r, "Failed to start a session");
        sr_disconnect(conn);
        return -1;
    }

    auto controller = ONLPController(sess);

    controller.loop();

    printf("Application exit requested, exiting.\n");

    sr_session_stop(sess);
    sr_disconnect(conn);
    return 0;
}
