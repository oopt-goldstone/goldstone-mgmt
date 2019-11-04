/****************************************************************
 *
 *        Copyright 2013,2014,2015,2016 Big Switch Networks, Inc.
 *
 * Licensed under the Eclipse Public License, Version 1.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *        http://www.eclipse.org/legal/epl-v10.html
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
 * either express or implied. See the License for the specific
 * language governing permissions and limitations under the
 * License.
 *
 ****************************************************************/
#ifndef __AIM_LOG_HANDLER_H__
#define __AIM_LOG_HANDLER_H__

/* <auto.start.enum(aim_log_handler_option).define> */
/** aim_log_handler_option */
typedef enum aim_log_handler_option_e {
    AIM_LOG_HANDLER_OPTION_TO_DBGLOG,
    AIM_LOG_HANDLER_OPTION_TO_SYSLOG,
    AIM_LOG_HANDLER_OPTION_TO_STDOUT,
    AIM_LOG_HANDLER_OPTION_TO_STDERR,
    AIM_LOG_HANDLER_OPTION_LAST = AIM_LOG_HANDLER_OPTION_TO_STDERR,
    AIM_LOG_HANDLER_OPTION_COUNT,
    AIM_LOG_HANDLER_OPTION_INVALID = -1,
} aim_log_handler_option_t;
/* <auto.end.enum(aim_log_handler_option).define> */

/* <auto.start.enum(aim_log_handler_flag).define> */
/** aim_log_handler_flag */
typedef enum aim_log_handler_flag_e {
    AIM_LOG_HANDLER_FLAG_TO_DBGLOG = (1 << AIM_LOG_HANDLER_OPTION_TO_DBGLOG),
    AIM_LOG_HANDLER_FLAG_TO_SYSLOG = (1 << AIM_LOG_HANDLER_OPTION_TO_SYSLOG),
    AIM_LOG_HANDLER_FLAG_TO_STDOUT = (1 << AIM_LOG_HANDLER_OPTION_TO_STDOUT),
    AIM_LOG_HANDLER_FLAG_TO_STDERR = (1 << AIM_LOG_HANDLER_OPTION_TO_STDERR),
} aim_log_handler_flag_t;
/* <auto.end.enum(aim_log_handler_flag).define> */


/**
 * Configuration block.
 */
typedef struct aim_log_handler_config_s {
    /** Flags: see AIM_LOG_HANDLER_FLAG_* above */
    uint32_t flags;

    /** Name of debug log file, optionally with full or relative path */
    char* debug_log_name;

    /** Maximum number of bytes beyond which the debug log will be rotated */
    uint32_t max_debug_log_size;

    /** Maximum number of rotated debug logs, excluding the actual debug log */
    uint32_t max_debug_logs;

    /** Syslog facility to use (if applicable) */
    uint32_t syslog_facility;

} aim_log_handler_config_t;


typedef struct aim_log_handler_s* aim_log_handler_t;


/**
 * @brief Initialize the AIM log handler system.
 */
void aim_log_handler_init(void);

/**
 * @brief Deinitialize the AIM log handler system.
 */
void aim_log_handler_denit(void);


/**
 * Create an AIM log handler instance.
 * @param config The handler configurtion.
 * @returns Object pointer.
 */

aim_log_handler_t aim_log_handler_create(aim_log_handler_config_t* config);

/**
 * Destroy an AIM log handler instance.
 */
void aim_log_handler_destroy(aim_log_handler_t handler);


/**
 * @brief AIM log handler callback.
 * @param Cookie log handler cookie. Must be an aim_log_handler_t.
 * @param flag The AIM log flag.
 * @param str The log message.
 */
void aim_log_handler_logf(void* cookie, aim_log_flag_t flag, const char* str);



/**
 * @brief Basic initialization for console and daemonized clients.
 * @param ident The syslog ident to use (optional)
 * @param debug_log_file  The name of the debug log file (optional)
 * @param max_debug_size   Maximum debug log size.
 * @param max_debug_count  Maximum number of rotated debug logs.
 *
 * @note This is designed to be a simple and generic initialization
 * for both daemonized and console-based clients.
 */
int aim_log_handler_basic_init_all(const char* ident,
                                   const char* debug_log_file,
                                   int max_debug_log_size,
                                   int max_debug_logs);

/**
 * @brief Deinitialize basic log handling support.
 */
void aim_log_handler_basic_denit_all(void);




/* <auto.start.enum(tag:log_handler).supportheader> */
/** Enum names. */
const char* aim_log_handler_flag_name(aim_log_handler_flag_t e);

/** Enum values. */
int aim_log_handler_flag_value(const char* str, aim_log_handler_flag_t* e, int substr);

/** Enum descriptions. */
const char* aim_log_handler_flag_desc(aim_log_handler_flag_t e);

/** Enum validator. */
int aim_log_handler_flag_valid(aim_log_handler_flag_t e);

/** validator */
#define AIM_LOG_HANDLER_FLAG_VALID(_e) \
    (aim_log_handler_flag_valid((_e)))

/** aim_log_handler_flag_map table. */
extern aim_map_si_t aim_log_handler_flag_map[];
/** aim_log_handler_flag_desc_map table. */
extern aim_map_si_t aim_log_handler_flag_desc_map[];

/** Strings macro. */
#define AIM_LOG_HANDLER_OPTION_STRINGS \
{\
    "to_dbglog", \
    "to_syslog", \
    "to_stdout", \
    "to_stderr", \
}
/** Enum names. */
const char* aim_log_handler_option_name(aim_log_handler_option_t e);

/** Enum values. */
int aim_log_handler_option_value(const char* str, aim_log_handler_option_t* e, int substr);

/** Enum descriptions. */
const char* aim_log_handler_option_desc(aim_log_handler_option_t e);

/** validator */
#define AIM_LOG_HANDLER_OPTION_VALID(_e) \
    ( (0 <= (_e)) && ((_e) <= AIM_LOG_HANDLER_OPTION_TO_STDERR))

/** aim_log_handler_option_map table. */
extern aim_map_si_t aim_log_handler_option_map[];
/** aim_log_handler_option_desc_map table. */
extern aim_map_si_t aim_log_handler_option_desc_map[];
/* <auto.end.enum(tag:log_handler).supportheader> */

#endif /* __AIM_LOG_HANDLER_H__ */
/* @}*/
