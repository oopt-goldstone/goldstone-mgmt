/***************************************************************
*  File name    : main.cpp                                     *
*  Description  : This file is the south bound application used*
*                 to register yang files for sonic submodules. *
***************************************************************/
#include <chrono>
#include <thread>
#include <csignal>
#include <queue>
#include "controller.hpp"
#include <sys/time.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <fstream>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <curl/curl.h>
#include <getopt.h>
#include <regex>

volatile int exit_application = 0;

/* holder for curl fetch */
struct
curl_fetch_st {
    char *payload;
    size_t size;
};

/*****************************************************************************
* Function Name : func                                                       *
* Description   : regular expression func for url                            *
* Input         : string &x                                                  *
* Output        : string                                                     *
*****************************************************************************/
std::string
xpath_to_url (std::string &xpath) {

    std::regex reg ("\\[+\\.+\\=+\\'.*\\'+\\]");
    std::string str, str2, url;
    std::regex_replace(back_inserter(str), xpath.begin(), xpath.end(),reg,  "");

    std::regex reg1 ("\\[[a-z]+[=]\\'");
    std::regex_replace(back_inserter(str2), str.begin(), str.end(),reg1,  "=");
    std::regex l("']");
    std::regex_replace(back_inserter(url), str2.begin(), str2.end(),l,  "");
    std::cout << " xpath_to_url  [URL]:   " << url.c_str() << '\n';
    return url;
}

/*****************************************************************************
* Function Name : curl_callback                                              *
* Description   : Callback for curl fetch                                    *
* Input         : void *contents                                             *
*                 size_t size                                                *
*                 size_t nmemb                                               *
*                 void *userp                                                *
* Output        : size_t                                                     *
*****************************************************************************/
size_t
curl_callback (void *contents, size_t size, size_t nmemb, void *userp) {
    size_t realsize = size * nmemb;
    struct curl_fetch_st *p = (struct curl_fetch_st *) userp;
    p->payload = (char *) realloc (p->payload, p->size + realsize + 1);

    /* check buffer */
    if (p->payload == NULL){
        fprintf (stderr, "ERROR: Failed to expand buffer in curl_callback");
        /* free buffer */
        free (p->payload);
        /* return */
        return size;
    }

    /* copy contents to buffer */
    memcpy (&(p->payload[p->size]), contents, realsize);
    /* set new buffer size */
    p->size += realsize;
    /* ensure null termination */
    p->payload[p->size] = 0;
    /* return size */
    return realsize;
}

json
SonicController::get_data_from_sonic (const char *xpath) {
    std::stringstream url;
    json j;
    CURL *curl;
    CURLcode res;
    curl_fetch_st curl_fetch;
    curl_fetch_st *fetch = &curl_fetch;

    fetch->payload = (char *) calloc (1, sizeof(fetch->payload));

    /* check payload */
    if (fetch->payload == NULL) {
        /* log error */
        fprintf (stderr, "ERROR: Failed to allocate payload in curl_fetch_url");
        /* return error */
        return j;
    }
    fetch->size = 0;
    curl = curl_easy_init ();

    if (curl) {
        std::string str = xpath;
        std::string url_path = xpath_to_url (str);
        url << m_port << "://" << m_mgmt_server << "/restconf/data" << url_path;


        curl_easy_setopt (curl, CURLOPT_URL, url.str().c_str());
        curl_easy_setopt (curl, CURLOPT_SSL_VERIFYPEER, false);
        curl_easy_setopt (curl, CURLOPT_SSL_VERIFYHOST, 0);

        curl_easy_setopt (curl, CURLOPT_WRITEFUNCTION, curl_callback);
        curl_easy_setopt (curl, CURLOPT_WRITEDATA, (void *) fetch);
        /* Perform the request, res will get the return code */
        res = curl_easy_perform (curl);

        /* Check for errors */
        if (res != CURLE_OK) {
            fprintf (stderr, "curl_easy_perform() failed: %s\n",
                     curl_easy_strerror(res));
        }
        /* always cleanup */
        curl_easy_cleanup (curl);
    }

    if (fetch->payload != NULL)
        printf ("CURL Returned: \n%s\n", fetch->payload);

    if (!strncmp (fetch->payload, "404 page not found", 18))
        return j;

    j = json::parse (fetch->payload);
    return j;
}

int
SonicController::set_data_to_sonic (const char *xpath, const char* json_data, const char *method) {
    CURL *curl;
    CURLcode res;
    struct curl_slist *headers = NULL;
    libyang::S_Data_Node tree;
    std::stringstream url;
    std::string str = xpath;
        std::string url_path= xpath_to_url (str);
        url.str("");
        url << m_port << "://" << m_mgmt_server << "/restconf/data" << url_path;

        curl = curl_easy_init ();

        if (curl) {
            headers = curl_slist_append (headers, "accept: application/yang-data+json");
            std::cout << "url   : "  << url.str().c_str() << '\n';
            std::cout << "method : " << method << "  -  " << json_data << '\n';
            curl_easy_setopt (curl, CURLOPT_URL, url.str().c_str());
            curl_easy_setopt (curl, CURLOPT_SSL_VERIFYPEER, false);
            curl_easy_setopt (curl, CURLOPT_SSL_VERIFYHOST, 0);

            /* To execute the CURL PUT operation*/
            curl_easy_setopt (curl, CURLOPT_CUSTOMREQUEST, method);
            curl_easy_setopt (curl, CURLOPT_FAILONERROR, true);
            curl_easy_setopt (curl, CURLOPT_HTTPHEADER, headers);
            if ( !strcmp(method, "DELETE")) {
                curl_easy_setopt (curl, CURLOPT_HTTPHEADER, headers);
            }
            else {
                headers = curl_slist_append (headers, "Content-Type: application/yang-data+json");
                curl_easy_setopt (curl, CURLOPT_HTTPHEADER, headers);
                curl_easy_setopt (curl, CURLOPT_POSTFIELDS, json_data);
            }

            /* Perform the request, res will get the return code */
            res = curl_easy_perform (curl);

            /* Check for errors */
            if (res != CURLE_OK) {
                fprintf (stderr, "curl_easy_perform() failed: %s\n",
                         curl_easy_strerror(res));
                return -1;
            }

            /* always cleanup */
            curl_easy_cleanup (curl);
        }
    return 0;

}

/*****************************************************************************
* Function Name : sigint_handler                                             *
* Description   : To handle the signal interrupt                             *
* Input         : int signum                                                 *
* Output        : void                                                       *
*****************************************************************************/
static void
sigint_handler (int signum) {
    (void) signum;
    exit_application = 1;
}

const char *
ev_to_str(sr_event_t ev) {
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

const char *
oper_to_str (sr_change_oper_e oper) {
    switch (oper) {
    case SR_OP_CREATED:
        return "created";
    case SR_OP_MODIFIED:
        return "modified";
    case SR_OP_DELETED:
        return "deleted";
    case SR_OP_MOVED:
        return "moved";
    default:
        return "unknow";
    }
}

/*****************************************************************************
* Function Name : _populate_oper_data                                        *
* Description   : To populate the operational datastore                      *
* Input         : libyang::S_Context& ctx                                    *
*                 libyang::S_Data_Node& parent                               *
*                 const std::string& name                                    *
*                 const std::string& path                                    *
*                 const std::string& value                                   *
* Output        : static int                                                 *
*****************************************************************************/
static int
_populate_oper_data (libyang::S_Context& ctx,
                     libyang::S_Data_Node& data,
                     const std::string& path,
                     const std::string& name,
                     const std::string& value) {
    std::stringstream xpath;
    xpath << path;
    if (strlen(name.c_str()))
      xpath << "/" <<  name;

    data->new_path (ctx, xpath.str().c_str(), value.c_str(), LYD_ANYDATA_CONSTSTRING, 0);
    return SR_ERR_OK;
}

/*****************************************************************************
* Function Name : get_index_of_yang                                          *
* Description   : To get the primary key of yang data                        *
* Input         : libyang::S_Data_Node &parent                               *
* Output        : char                                                       *
*****************************************************************************/
int
get_index_of_yang (libyang::S_Data_Node &parent,
                   const char *path, std::vector<std::shared_ptr<libyang::Schema_Node_Leaf> > *keys) {
    int keys_size = 0;
    auto s = parent->schema();
    auto set = s->find_path(path);
    auto sc = set->schema()[0];
    if ( sc->nodetype() == LYS_LIST ) {
        auto snl = libyang::Schema_Node_List(sc);
        keys_size = snl.keys_size();
        *keys = snl.keys();
    }
    return keys_size;
}


int
is_key_node (libyang::S_Data_Node &parent, const char *path) {
    auto s = parent->schema();
    auto set = s->find_path(path);
    if  (!set)
        return -1;

    auto sc = set->schema()[0];
    if ( sc->nodetype() == LYS_LEAF) {
        auto snl = libyang::Schema_Node_Leaf(sc);
        auto list = snl.is_key();
        if (list != NULL) {
            return 1;
        }
    }
    return 0;
}


int
is_leaf_node (libyang::S_Data_Node &parent, const char *path) {
    auto s = parent->schema();
    auto set = s->find_path(path);
    if (!set)
        return -1;
    auto sc = set->schema()[0];
    if ( sc->nodetype() == LYS_LEAF)
        return 1;
    return 0;
}


/*****************************************************************************
* Function Name : json_to_yang                                               *
* Description   : To decode the received json data                           *
* Input         : json j                                                     *
*                 libyang::S_Context& ly_ctx                                 *
*                 libyang::S_Data_Node &parent                               *
*                 const char *request_xpath                                  *
* Output        : void                                                       *
*****************************************************************************/
void
json_to_yang (json j, libyang::S_Context& ly_ctx,
              libyang::S_Data_Node &parent,
              const char *xpath) {
    std::stringstream path, val;
    int indexed = 0;

    path << xpath;
    if (j.empty())
        return;

    switch (j.type()) {
        case nlohmann::basic_json<>::value_t::object:
            for (auto& x : j.items()) {
                if (x.value().is_primitive()) {
                    std::stringstream tmp_path1;
                    tmp_path1 << path.str().c_str();
                    tmp_path1 << "/" << x.key ();
                    auto is_key = is_key_node (parent, tmp_path1.str().c_str());
                    if (is_key == -1 )
                        return;
                    else if (is_key == 0 ) {
                        if (x.value().is_string()) {
                            _populate_oper_data (ly_ctx, parent,
                                                 path.str().c_str(),
                                                 x.key(),
                                                 x.value());
                        }
                        else if (x.value().is_number()) {
                            val.str("");
                            val << x.value();
                            _populate_oper_data (ly_ctx, parent,
                                                 path.str().c_str(),
                                                 x.key(),
                                                 val.str().c_str());
                        }
                    }
                }
                else {
                    std::stringstream tmp_path;
                    tmp_path << path.str().c_str();
                    path << "/" << x.key();
                    json_to_yang (x.value(), ly_ctx, parent, path.str().c_str());
                    path.str("");
                    path << tmp_path.str().c_str();
                }
            }
            break;
        case nlohmann::basic_json<>::value_t::array:
            if (xpath[strlen(xpath)-1] == ']')
                indexed = 1;
            for (json::iterator it = j.begin(); it != j.end(); ++it) {
                json j1 = *it;
                if (!indexed) {
                    if (j1.type() == nlohmann::detail::value_t::string) {
                        _populate_oper_data (ly_ctx, parent,
                                             xpath,
                                             "", j1);
                    }
                    else {
                        if (!j1.empty()) {
                            std::stringstream tmp_path;
                            tmp_path << path.str().c_str();

                            std::vector<std::shared_ptr<libyang::Schema_Node_Leaf> > keys;
                            auto keys_size = get_index_of_yang(parent, path.str().c_str(), &keys);
                            if ( keys_size > 0 ) {
                                std::string index = j1[keys[0]->name()];
                                path << "[" << keys[0]->name() << "='" << index << "'";
                                for (auto i = 1 ; i < keys_size; i++) {
                                    index = j1[keys[i]->name()];
                                    path << "][" << keys[i]->name() << "='" << index << "'";
                                }
                                path << "]";
                            }
                            json_to_yang (*it, ly_ctx, parent, path.str().c_str());
                            path.str("");
                            path << tmp_path.str().c_str();
                        }
                    }
                }
                else
                    json_to_yang (*it, ly_ctx, parent, path.str().c_str());
            }
            break;
    }
}


/*****************************************************************************
* Function Name : oper_get_items                                             *
* Description   : To get the Operational data                                *
* Input         : sysrepo::S_Session session                                 *
*                 const char *module_name                                    *
*                 const char *path                                           *
*                 const char *request_xpath                                  *
*                 uint32_t request_id                                        *
*                 libyang::S_Data_Node &parent                               *
*                 void *private_data                                         *
* Output        : int                                                        *
*****************************************************************************/
int
SonicController::oper_get_items (sysrepo::S_Session session,
                                 const char *module_name,
                                 const char *path,
                                 const char *request_xpath,
                                 uint32_t request_id,
                                 libyang::S_Data_Node &parent,
                                 void *private_data) {

    json j = get_data_from_sonic (request_xpath);
    libyang::S_Context ly_ctx = session->get_context();
    auto node_name = sr_xpath_node_name(request_xpath);
    if (node_name) {
        const char *node_name1 = strtok (node_name,"[");
        json tmp_j = j[node_name1];
        if (tmp_j.empty()) {
            std::stringstream str;
            str <<  module_name << ":" << node_name1;
            tmp_j = j[str.str().c_str()];
        }
        auto is_leaf = is_leaf_node (parent, request_xpath);
        if (is_leaf) {
            if (tmp_j.is_string())
                _populate_oper_data (ly_ctx, parent,request_xpath, "", tmp_j);
            else if (tmp_j.is_number()) {
                std::stringstream val;
                val.str("");
                val << tmp_j;
                _populate_oper_data (ly_ctx, parent,request_xpath, "", val.str().c_str());
            }
        }
        else
            json_to_yang (tmp_j, ly_ctx, parent, request_xpath);
    }
    else {
        std::string str = request_xpath;
        str.erase (0,1);
        json tmp_j = j[str];
        json_to_yang (tmp_j, ly_ctx, parent, request_xpath);
    }
    session->apply_changes ();
    return SR_ERR_OK;
}

/*****************************************************************************
* Function Name : print_current_config                                       *
* Description   : To print the configured data                               *
* Input         : sysrepo::S_Session session                                 *
*                 const char *module_name                                    *
* Output        : static void                                                *
*****************************************************************************/
static void
print_current_config (sysrepo::S_Session session, const char *module_name)
{
  char select_xpath[100];
  try
    {
      snprintf (select_xpath, 100, "/%s:*//.", module_name);
      auto values = session->get_items (&select_xpath[0]);

      if (values == nullptr)
        {
          return;
        }
      for (unsigned int i = 0; i < values->val_cnt(); i++)
        {
          std::cout << values->val(i)->to_string();
        }
    }
  catch (const std::exception& e)
    {
      std::cout << e.what() << std::endl;
    }
}

/*****************************************************************************
* Function Name : module_change                                              *
* Description   : Callback for set function                                  *
* Input         : sysrepo::S_Session session                                 *
*                 const char *module_name                                    *
*                 const char *xpath                                          *
*                 sr_event_t event                                           *
*                 uint32_t request_id                                        *
*                 void *private_data                                         *
* Output        : int                                                        *
*****************************************************************************/
int
SonicController::module_change (sysrepo::S_Session session,
                                const char *module_name,
                                const char *xpath,
                                sr_event_t event,
                                uint32_t request_id,
                                void *private_data)
{
    CURL *curl;
    CURLcode res;
    struct curl_slist *headers = NULL;
    libyang::S_Data_Node tree;
    std::string json_data;
    std::stringstream url;
    std::cout << "========== EVENT " << ev_to_str(event) << " CHANGES: ====================================" << std::endl;
    if ( event == SR_EV_DONE ) {
        return SR_ERR_OK;
    }

    if ( !_initialized ) {
        return SR_ERR_OK;
    }

    auto it = session->get_changes_iter("//.");
    sysrepo::S_Change change;
    sysrepo::S_Val n;
    int ret;
    while ( (change = session->get_change_next(it)) != nullptr ) {
        std::cout << "Operation : "  << oper_to_str(change->oper()) << std::endl;
        if ( change->oper() == SR_OP_CREATED || change->oper() == SR_OP_MODIFIED ) {
            n = change->new_val();
            tree = std::make_shared<libyang::Data_Node>(nullptr);

            /* To get the subtree of a particular node */
            tree = session->get_subtree (n->xpath(), 0);

            /* To store the yang tree in json format */
            json_data = tree->print_mem (LYD_JSON, 0);
            std::cout << "JSON data from tree: \n" << json_data <<  '\n';

            ret = set_data_to_sonic (n->xpath(), json_data.c_str(), "PATCH");
        }
        else if ( change->oper() == SR_OP_DELETED ) {
            n = change->old_val();
            set_data_to_sonic (n->xpath(), "", "DELETE");
        }
        else
            return SR_ERR_OK;
    }

    std::cout << "\n\n ========== Current running config : ==========\n\n" << std::endl;
    print_current_config (session, module_name);
    std::cout << "\n\n ========== End of current config ==========\n\n" << std::endl;

    return SR_ERR_OK;
}

/*****************************************************************************
* Function Name : SonicController                                            *
* Description   : To subscribe for yang module                               *
* Input         : sysrepo::S_Session& sess) : m_sess(sess)                   *
*                 m_subscribe(new sysrepo::Subscribe(sess)                   *
* Output        :                                                            *
*****************************************************************************/
SonicController::SonicController (sysrepo::S_Session& sess, std::string mgmt_ip, std::string port_no) : m_sess(sess),
                                  m_subscribe(new sysrepo::Subscribe(sess)) {
    auto callback = sysrepo::S_Callback (this);
    auto ly_ctx = sess->get_context();
    libyang::S_Data_Node data[4];

    m_mgmt_server = mgmt_ip;
    m_port = port_no;
    _initialized = false;

    const char *xpaths[] = { "/sonic-port:sonic-port",
                             "/sonic-portchannel:sonic-portchannel",
                             "/sonic-vlan:sonic-vlan",
                             "/sonic-interface:sonic-interface"};
    const char *parent_node[] = { "sonic-port:sonic-port",
                                  "sonic-portchannel:sonic-portchannel",
                                  "sonic-vlan:sonic-vlan",
                                  "sonic-interface:sonic-interface"};
    const char *mod_name[] = { "sonic-port",
                               "sonic-portchannel",
                               "sonic-vlan",
                               "sonic-interface"};

    for (int i = 0; i < 4 ; i++) {
        json tmp_j = get_data_from_sonic (xpaths[i]);
        json j = tmp_j[parent_node[i]];
        data[i] = libyang::S_Data_Node(new libyang::Data_Node(ly_ctx, xpaths[i], "", LYD_ANYDATA_CONSTSTRING, 0));
        json_to_yang (j, ly_ctx, data[i], xpaths[i]);
        m_subscribe->module_change_subscribe(mod_name[i], callback);

        sess->session_switch_ds(SR_DS_RUNNING);

        if ( data[i] != nullptr )
            sess->replace_config(data[i], mod_name[i]);
    }

    /* read running config */
    std::cout << "\n\n ========== READING RUNNING CONFIG: ==========\n" << std::endl;
    for (int i = 0; i < 4 ; i++) {
        print_current_config (sess, mod_name[i]);
    }

    /* To subscribe callback for sysrepo get functionality */
    m_subscribe->oper_get_items_subscribe (mod_name[0],
                                           "/sonic-port:sonic-port/PORT",
                                           callback);
    m_subscribe->oper_get_items_subscribe (mod_name[1],
                                           "/sonic-portchannel:sonic-portchannel",
                                           callback);
    m_subscribe->oper_get_items_subscribe (mod_name[3],
                                           "/sonic-interface:sonic-interface/INTERFACE",
                                           callback);
    m_subscribe->oper_get_items_subscribe (mod_name[2],
                                           "/sonic-vlan:sonic-vlan/VLAN",
                                           callback);
    m_subscribe->oper_get_items_subscribe (mod_name[2],
                                           "/sonic-vlan:sonic-vlan/VLAN_MEMBER",
                                           callback);
    sess->apply_changes();

    _initialized = true;
}

/*****************************************************************************
* Function Name : SonicController                                            *
* Description   : Destructor                                                 *
*****************************************************************************/
SonicController::~SonicController()
{}

/*****************************************************************************
* Function Name : loop                                                       *
* Description   : Used for looping main                                      *
* Input         :                                                            *
* Output        : void                                                       *
*****************************************************************************/
void
SonicController::loop()
{
  /* loop until ctrl-c is pressed / SIGINT is received */
  signal (SIGINT, sigint_handler);
  signal (SIGPIPE, SIG_IGN);

  while (!exit_application)
    {
      std::this_thread::sleep_for (std::chrono::seconds(1000));
    }
}

/*****************************************************************************
* Function Name : main                                                       *
* Description   : Driver function                                            *
* Input         : void                                                       *
* Output        : int                                                        *
*****************************************************************************/
int
main (int argc,char **argv)
{
  int c;
  int verbose = 0;
  std::string mgmt_ip, port_no;
  int option_index = 0;

  static struct option long_options[] =
    {
      { "verbose", no_argument,       0, 'v' },
      { "mgmt_ip", required_argument, 0, 's' },
      { "port_no", required_argument, 0, 'p' }
    };

  while ((c = getopt_long (argc, argv, "v:s:p:", long_options, &option_index)) != -1 )
    {
      switch (c)
        {
          case 'v':
            verbose = 1;
            break;
          case 's':
            mgmt_ip = std::string (optarg);
            break;
          case 'p':
            port_no = std::string (optarg);
            break;
          default:
            std::cout << "usage: " << argv[0]
                      << " -s <mgmt-server-ip> -p <port:https/http>" << std::endl;
            return -1;
        }
    }

  if (argc < 5)
    {
      std::cout << "mgmt_server-ip and port is mandatory" << std::endl;
      std::cout << "usage: " << argv[0]
                << " -s <mgmt-server-ip> -p <port:https/http>" << std::endl;
      exit (1);
    }

  if (verbose)
    {
      sysrepo::Logs().set_stderr (SR_LL_DBG);
    }

  sysrepo::S_Connection conn (new sysrepo::Connection);
  sysrepo::S_Session sess (new sysrepo::Session(conn));
  sysrepo::S_Subscribe subscribe (new sysrepo::Subscribe(sess));

  auto controller = SonicController (sess, mgmt_ip, port_no);

  controller.loop ();
  std::cout << "Application exit requested, exiting." << std::endl;
  return 0;
}
