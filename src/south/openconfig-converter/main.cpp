#include "controller.hpp"
#include <limits>
#include <bitset>
#include "base64.hpp"
#include <cstdarg>
#include <cstring>

#include <inttypes.h>

volatile int exit_application = 0;

static uint32_t pack754_32(float f) {
    uint32_t *p;
    p = (uint32_t*)&f;
    return *p;
}

static std::string ieeefloat32(float f) {
    auto b = pack754_32(f);
    return base64::encode({ static_cast<base64::byte>((b >> 24) & 0xff), static_cast<base64::byte>((b >> 16) & 0xff), static_cast<base64::byte>((b >> 8) & 0xff), static_cast<base64::byte>(b & 0xff) });
}

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

    switch (value->type) {
    case SR_CONTAINER_T:
    case SR_CONTAINER_PRESENCE_T:
        printf("(container)");
        break;
    case SR_LIST_T:
        printf("(list instance)");
        break;
    case SR_STRING_T:
        printf("= %s", value->data.string_val);
        break;
    case SR_BOOL_T:
        printf("= %s", value->data.bool_val ? "true" : "false");
        break;
    case SR_DECIMAL64_T:
        printf("= %g", value->data.decimal64_val);
        break;
    case SR_INT8_T:
        printf("= %" PRId8, value->data.int8_val);
        break;
    case SR_INT16_T:
        printf("= %" PRId16, value->data.int16_val);
        break;
    case SR_INT32_T:
        printf("= %" PRId32, value->data.int32_val);
        break;
    case SR_INT64_T:
        printf("= %" PRId64, value->data.int64_val);
        break;
    case SR_UINT8_T:
        printf("= %" PRIu8, value->data.uint8_val);
        break;
    case SR_UINT16_T:
        printf("= %" PRIu16, value->data.uint16_val);
        break;
    case SR_UINT32_T:
        printf("= %" PRIu32, value->data.uint32_val);
        break;
    case SR_UINT64_T:
        printf("= %" PRIu64, value->data.uint64_val);
        break;
    case SR_IDENTITYREF_T:
        printf("= %s", value->data.identityref_val);
        break;
    case SR_INSTANCEID_T:
        printf("= %s", value->data.instanceid_val);
        break;
    case SR_BITS_T:
        printf("= %s", value->data.bits_val);
        break;
    case SR_BINARY_T:
        printf("= %s", value->data.binary_val);
        break;
    case SR_ENUM_T:
        printf("= %s", value->data.enum_val);
        break;
    case SR_LEAF_EMPTY_T:
        printf("(empty leaf)");
        break;
    default:
        printf("(unprintable)");
        break;
    }

    switch (value->type) {
    case SR_UNKNOWN_T:
    case SR_CONTAINER_T:
    case SR_CONTAINER_PRESENCE_T:
    case SR_LIST_T:
    case SR_LEAF_EMPTY_T:
        printf("\n");
        break;
    default:
        printf("%s\n", value->dflt ? " [default]" : "");
        break;
    }
}



static void
print_change(sr_change_oper_t op, sr_val_t *old_val, sr_val_t *new_val)
{
    switch(op) {
    case SR_OP_CREATED:
        printf("CREATED: ");
        print_val(new_val);
        break;
    case SR_OP_DELETED:
        printf("DELETED: ");
        print_val(old_val);
        break;
    case SR_OP_MODIFIED:
        printf("MODIFIED: ");
        print_val(old_val);
        printf("to ");
        print_val(new_val);
        break;
    case SR_OP_MOVED:
        printf("MOVED: %s\n", new_val->xpath);
        break;
    }
}

static int
module_change_cb(sr_session_ctx_t *session, const char *module_name, const char *xpath, sr_event_t event,
        uint32_t request_id, void *private_data)
{
    printf("\n\n ========== EVENT %s CHANGES module: %s %s\n", ev_to_str(event), module_name, xpath);
    sr_change_iter_t *it;
    sr_get_changes_iter(session, "//.", &it);

    sr_change_oper_t oper;
    sr_val_t *old_value = NULL, *new_value = NULL;

    int rc = SR_ERR_OK;
    while ((rc = sr_get_change_next(session, it, &oper, &old_value, &new_value)) == SR_ERR_OK) {
        print_change(oper, old_value, new_value);
        sr_free_val(old_value);
        sr_free_val(new_value);
    }

    sr_free_change_iter(it);
    printf("\n\n ========== EVENT %s CHANGES end\n", ev_to_str(event));

    return SR_ERR_OK;
}

static int
oper_get_items_cb(sr_session_ctx_t *session, const char *module_name, const char *xpath, const char *request_xpath,
        uint32_t request_id, struct lyd_node **parent, void *private_data)
{
    auto ctrl = static_cast<OpenConfigConverter*>(private_data);
    return ctrl->get_oper_items(session, module_name, xpath, request_xpath, request_id, parent);
}

static const std::string PLATFORM_MODULE_NAME = "openconfig-platform";

OpenConfigConverter::OpenConfigConverter(sr_session_ctx_t* sess) : m_sess(sess) {
    auto mod_name = PLATFORM_MODULE_NAME.c_str();

    auto r = sr_module_change_subscribe(sess, mod_name, nullptr, module_change_cb, NULL, 0, 0, &m_subscription);
    if (r != SR_ERR_OK) {
        error_print(r, "Failed to subscribe module openconfig-platform");
        return;
    }

    auto ly_ctx = (struct ly_ctx *)sr_get_context(sr_session_get_connection(sess));
    auto xpath = "/openconfig-platform:components/component[name='sys']/config/name";
    auto v = strdup("sys");
    auto data = lyd_new_path(nullptr, ly_ctx, xpath, v, LYD_ANYDATA_STRING, 0);
    r = sr_replace_config(sess, mod_name, data, sr_session_get_ds(sess), 0);
    if (r) {
        error_print(r, "Replace config failed");
    }

    r = sr_oper_get_items_subscribe(sess, mod_name, "/openconfig-platform:components/component[name='sys']/state", oper_get_items_cb, this, 0, &m_subscription);
    if (r != SR_ERR_OK) {
        error_print(r, "Failed to subscribe oper get");
        return;
    }
}

OpenConfigConverter::~OpenConfigConverter() {
    sr_unsubscribe(m_subscription);
}

void OpenConfigConverter::loop() {
    /* loop until ctrl-c is pressed / SIGINT is received */
    signal(SIGINT, sigint_handler);
    signal(SIGPIPE, SIG_IGN);
    while (!exit_application) {
        sleep(1000);
    }
}

static int _populate_oper_data(ly_ctx *ctx, lyd_node *parent, const std::string& name, const std::string& path, const char* value) {
    std::stringstream xpath;
    xpath << "/openconfig-platform:components/component[name='" << name << "']/" << path;
    lyd_new_path(parent, nullptr, xpath.str().c_str(), const_cast<char*>(value), LYD_ANYDATA_CONSTSTRING, 0);
    if ( ly_errno ) {
        std::cout << "xpath: " << xpath.str() << ", value: " << value << std::endl;
        error_ly_print(ctx);
        return -1;
    }
    return 0;
}

int OpenConfigConverter::get_oper_items(sr_session_ctx_t *session, const char *module_name, const char *xpath, const char *request_xpath,
                                   uint32_t request_id, lyd_node **parent) {
    auto ly_ctx = (struct ly_ctx*)sr_get_context(sr_session_get_connection(session));
    sr_xpath_ctx_t xpath_ctx;
    auto n = sr_xpath_key_value(const_cast<char*>(request_xpath), "component", "name", &xpath_ctx);
    if ( n == nullptr ) {
        std::cout << "no name" << std::endl;
        return SR_ERR_OK;
    }

    auto name = std::string(n);
    lyd_node *tree = nullptr;
    std::stringstream ss;
    ss << "/goldstone-onlp:components/component[name='" << name << "']";
    auto prefix = ss.str();
    auto r = sr_get_subtree(session, prefix.c_str(), 0, &tree);
    if (r != SR_ERR_OK) {
        error_print(r, "Failed to get goldstone-onlp");
        return r;
    }
    lyd_print_fd(1, tree, LYD_JSON, LYP_WITHSIBLINGS);
    std::cout << std::endl;

    {
        auto s = lyd_find_path(tree, "state/description");
        auto d = reinterpret_cast<lyd_node_leaf_list*>(s->set.d[0]);
        _populate_oper_data(ly_ctx, *parent, name, "state/description", d->value_str);
        ly_set_free(s);

        s = lyd_find_path(tree, "state/id");
        d = reinterpret_cast<lyd_node_leaf_list*>(s->set.d[0]);
        std::stringstream id;
        id << std::hex << "0x" << d->value.uint32;
        _populate_oper_data(ly_ctx, *parent, name, "state/id", id.str().c_str());
        ly_set_free(s);
    }

    auto s = lyd_find_path(tree, "state/type");
    auto d = reinterpret_cast<lyd_node_leaf_list*>(s->set.d[0]);
    auto type = std::string(d->value_str);
    ly_set_free(s);
    if ( type == "THERMAL" ) {
        s = lyd_find_path(tree, "thermal/state/temperature");
        d = reinterpret_cast<lyd_node_leaf_list*>(s->set.d[0]);
        std::stringstream t;
        t << static_cast<float>(d->value.int32/1000);
        ly_set_free(s);
        _populate_oper_data(ly_ctx, *parent, name, "state/temperature/instant", t.str().c_str());
        t.str("");

        s = lyd_find_path(tree, "thermal/state/thresholds/error");
        d = reinterpret_cast<lyd_node_leaf_list*>(s->set.d[0]);

        _populate_oper_data(ly_ctx, *parent, name, "state/temperature/alarm-threshold", t.str().c_str());
        ly_set_free(s);
    }
    return SR_ERR_OK;
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

    try {
        auto controller = OpenConfigConverter(sess);
        controller.loop();
    } catch (...) {
        std::cout << "caught an exception" << std::endl;
    }

    printf("Application exit requested, exiting.\n");

    sr_session_stop(sess);
    sr_disconnect(conn);
    return 0;
}
