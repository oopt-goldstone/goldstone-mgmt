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

#define MAX_PAYLOAD_SIZE 10000

char *intfIp;

volatile int exit_application = 0;

static const std::string SONIC_PORT_MODULE_NAME = "sonic-port";
static const std::string SONIC_INTERFACE_MODULE_NAME = "sonic-interface";

/* holder for curl fetch */
struct
curl_fetch_st
{
  char *payload;
  size_t size;
};

/*****************************************************************************
* Function Name : sigint_handler                                             *
* Description   : To handle the signal interrupt                             *
* Input         : int signum                                                 *
* Output        : void                                                       *
*****************************************************************************/
static void
sigint_handler (int signum)
{
  (void) signum;
  exit_application = 1;
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
                     libyang::S_Data_Node& parent,
                     const std::string& name,
                     const std::string& path,
                     const std::string& value)
{
  std::stringstream xpath;
  xpath << name << "/" <<  path;
  parent->new_path (ctx, xpath.str().c_str(),
                    value.c_str(),
                    LYD_ANYDATA_CONSTSTRING, 0);
  return SR_ERR_OK;
}

/*****************************************************************************
* Function Name : get_index_of_yang                                          *
* Description   : To get the primary key of yang data                        *
* Input         : libyang::S_Data_Node &parent                               *
* Output        : char                                                       *
*****************************************************************************/
char
*get_index_of_yang (libyang::S_Data_Node &parent)
{
  struct lyd_node *lyd = parent->C_lyd_node();
  struct lys_node *lys = lyd->schema;

  while (lys->nodetype != LYS_LEAF)
    {
      lys = lys->child;
    }
  return (char *)lys->name;
}

/*****************************************************************************
* Function Name : json_decode                                                *
* Description   : To decode the received json data                           *
* Input         : json j                                                     *
*                 libyang::S_Context& ly_ctx                                 *
*                 libyang::S_Data_Node &parent                               *
*                 const char *request_xpath                                  *
* Output        : void                                                       *
*****************************************************************************/
void
json_decode (json j, libyang::S_Context& ly_ctx,
             libyang::S_Data_Node &parent,
             const char *request_xpath)
{
  std::stringstream val;
  std::stringstream xpath;
  switch (j.type())
    {
      case nlohmann::basic_json<>::value_t::object:

        for (auto& x : j.items())
          {
            if (x.value().is_primitive())
              {
                char *primKey = get_index_of_yang(parent);
                std::string index = j[primKey];
                xpath.str("");
                xpath << request_xpath << "[" << primKey << "='" << index << "']";

                if (strcmp(x.key().c_str(), primKey))
                  {
                    if (x.value().is_string())
                      {
                        _populate_oper_data (ly_ctx, parent,
                                             xpath.str().c_str(),
                                             x.key(),
                                             x.value());
                      }
                    else if (x.value().is_number())
                      {
                        val.str("");
                        val << x.value();
                        _populate_oper_data (ly_ctx, parent,
                                             xpath.str().c_str(),
                                             x.key(),
                                             val.str().c_str());
                      }
                  }
              }
            else
              {
                json_decode (x.value(), ly_ctx, parent, request_xpath);
              }
            }
        break;
      case nlohmann::basic_json<>::value_t::array:
        for (json::iterator it = j.begin(); it != j.end(); ++it)
          {
            json_decode (*it, ly_ctx, parent, request_xpath);
          }
      break;
    }
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
curl_callback (void *contents, size_t size, size_t nmemb, void *userp)
{
  size_t realsize = size * nmemb;
  struct curl_fetch_st *p = (struct curl_fetch_st *) userp;
  p->payload = (char *) realloc (p->payload, p->size + realsize + 1);

  /* check buffer */
  if (p->payload == NULL)
    {
      fprintf (stderr, "ERROR: Failed to expand buffer in curl_callback");
      /* free buffer */
      free (p->payload);
      /* return */
      return 1;
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
                                 void *private_data)
{
  std::stringstream url;
  libyang::S_Context ly_ctx = session->get_context();

  CURL *curl;
  CURLcode res;
  struct curl_fetch_st curl_fetch;
  struct curl_fetch_st *fetch = &curl_fetch;
  fetch->payload = (char *) calloc (1, sizeof(fetch->payload));
  char *payload = (char *) calloc (1, MAX_PAYLOAD_SIZE);

  /* check payload */
  if (fetch->payload == NULL)
    {
      /* log error */
      fprintf (stderr, "ERROR: Failed to allocate payload in curl_fetch_url");
      /* return error */
      return 0;
    }
  fetch->size = 0;
  url << "https://" << intfIp << "/restconf/data";
  curl = curl_easy_init ();

  if (curl)
    {
      url << request_xpath;
      curl_easy_setopt (curl, CURLOPT_URL, url.str().c_str());
      curl_easy_setopt (curl, CURLOPT_SSL_VERIFYPEER, false);
      curl_easy_setopt (curl, CURLOPT_SSL_VERIFYHOST, 0);

      curl_easy_setopt (curl, CURLOPT_WRITEFUNCTION, curl_callback);
      curl_easy_setopt (curl, CURLOPT_WRITEDATA, (void *) fetch);
      /* Perform the request, res will get the return code */
      res = curl_easy_perform (curl);

      /* Check for errors */
      if (res != CURLE_OK)
        {
          fprintf (stderr, "curl_easy_perform() failed: %s\n",
                   curl_easy_strerror(res));
        }

      /* always cleanup */
      curl_easy_cleanup (curl);
    }

  if (fetch->payload != NULL)
    {
      printf ("CURL Returned: \n%s\n", fetch->payload);
    }

  json j = json::parse (fetch->payload);
  json_decode (j, ly_ctx, parent, request_xpath);
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

  tree = std::make_shared<libyang::Data_Node>(nullptr);

  /* To get the subtree of a particular node */
  tree = session->get_subtree (xpath, 0);

  /* To store the yang tree in json format */
  json_data = tree->print_mem (LYD_JSON, 0);

  headers = curl_slist_append (headers, "accept: application/yang-data+json");
  headers = curl_slist_append (headers, "Content-Type: application/yang-data+json");
  url << "https://" << intfIp << "/restconf/data";
  curl = curl_easy_init ();

  if (curl)
    {
      url << xpath;
      curl_easy_setopt (curl, CURLOPT_URL, url.str().c_str());
      curl_easy_setopt (curl, CURLOPT_SSL_VERIFYPEER, false);
      curl_easy_setopt (curl, CURLOPT_SSL_VERIFYHOST, 0);

      /* To execute the CURL PUT operation*/
      curl_easy_setopt (curl, CURLOPT_CUSTOMREQUEST, "PUT");
      curl_easy_setopt (curl, CURLOPT_FAILONERROR, true);
      curl_easy_setopt (curl, CURLOPT_HTTPHEADER, headers);
      curl_easy_setopt (curl, CURLOPT_POSTFIELDS, json_data.c_str());

      /* Perform the request, res will get the return code */
      res = curl_easy_perform (curl);
      /* Check for errors */
      if (res != CURLE_OK)
        {
          fprintf (stderr, "curl_easy_perform() failed: %s\n",
                   curl_easy_strerror(res));
        }

      /* always cleanup */
      curl_easy_cleanup (curl);
    }

  std::cout << "\n\n ========== EVENT CHANGES: ==========\n\n" << std::endl;
  print_current_config (session, module_name);
  
  return SR_ERR_OK;
}

/*****************************************************************************
* Function Name : SonicController                                            *
* Description   : To subscribe for yang module                               *
* Input         : sysrepo::S_Session& sess) : m_sess(sess)                   *
*                 m_subscribe(new sysrepo::Subscribe(sess)                   *
* Output        :                                                            *
*****************************************************************************/
SonicController::SonicController (sysrepo::S_Session& sess) : m_sess(sess),
                                  m_subscribe(new sysrepo::Subscribe(sess))
{
  auto mod_name_port = SONIC_PORT_MODULE_NAME.c_str();
  auto mod_name_interface = SONIC_INTERFACE_MODULE_NAME.c_str();
  auto callback = sysrepo::S_Callback (this);

  /* To subscribe callback for sysrepo write functionality*/
  m_subscribe->module_change_subscribe (mod_name_port,
                                        callback,
                                        "/sonic-port:sonic-port/PORT");
  m_subscribe->module_change_subscribe (mod_name_interface,
                                        callback,
                                        "/sonic-interface:sonic-interface/INTERFACE");
  /* read running config */
  std::cout << "\n\n ========== READING RUNNING CONFIG: ==========\n" << std::endl;
  print_current_config (sess, mod_name_port);

  /* To subscribe callback for sysrepo get functionality */
  m_subscribe->oper_get_items_subscribe (mod_name_port,
                                         "/sonic-port:sonic-port/PORT",
                                         callback);
  m_subscribe->oper_get_items_subscribe (mod_name_interface,
                                         "/sonic-interface:sonic-interface/INTERFACE",
                                         callback);
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
main (int argc,char *argv[])
{
  if (argc != 2)
    {
      std::cerr << "Usages: ip_address" << std::endl;
      exit (0);
    }

  /* Management IP address to be passed */
  intfIp = argv[1];

  sysrepo::Logs().set_stderr (SR_LL_DBG);
  sysrepo::S_Connection conn (new sysrepo::Connection);
  sysrepo::S_Session sess (new sysrepo::Session(conn));
  sysrepo::S_Subscribe subscribe (new sysrepo::Subscribe(sess));

  auto controller = SonicController (sess);

  controller.loop ();
  std::cout << "Application exit requested, exiting." << std::endl;
  return 0;
}

