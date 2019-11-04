/****************************************************************
 *
 *        Copyright 2014, Big Switch Networks, Inc.
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

/**************************************************************************//**
 *
 * @file
 * @brief AIM Logging Utilities
 *
 *
 * @addtogroup aim-log
 * @{
 *
 *****************************************************************************/
#ifndef __AIM_LOG_UTIL_H__
#define __AIM_LOG_UTIL_H__


#include <AIM/aim_map.h>


/* <auto.start.enum(aim_log_flag).header> */
/** aim_log_flag */
typedef enum aim_log_flag_e {
    AIM_LOG_FLAG_MSG,
    AIM_LOG_FLAG_FATAL,
    AIM_LOG_FLAG_ERROR,
    AIM_LOG_FLAG_WARN,
    AIM_LOG_FLAG_INFO,
    AIM_LOG_FLAG_VERBOSE,
    AIM_LOG_FLAG_TRACE,
    AIM_LOG_FLAG_INTERNAL,
    AIM_LOG_FLAG_BUG,
    AIM_LOG_FLAG_FTRACE,
    AIM_LOG_FLAG_SYSLOG_EMERG,
    AIM_LOG_FLAG_SYSLOG_ALERT,
    AIM_LOG_FLAG_SYSLOG_CRIT,
    AIM_LOG_FLAG_SYSLOG_ERROR,
    AIM_LOG_FLAG_SYSLOG_WARN,
    AIM_LOG_FLAG_SYSLOG_NOTICE,
    AIM_LOG_FLAG_SYSLOG_INFO,
    AIM_LOG_FLAG_SYSLOG_DEBUG,
    AIM_LOG_FLAG_LAST = AIM_LOG_FLAG_SYSLOG_DEBUG,
    AIM_LOG_FLAG_COUNT,
    AIM_LOG_FLAG_INVALID = -1,
} aim_log_flag_t;

/** Strings macro. */
#define AIM_LOG_FLAG_STRINGS \
{\
    "msg", \
    "fatal", \
    "error", \
    "warn", \
    "info", \
    "verbose", \
    "trace", \
    "internal", \
    "bug", \
    "ftrace", \
    "syslog_emerg", \
    "syslog_alert", \
    "syslog_crit", \
    "syslog_error", \
    "syslog_warn", \
    "syslog_notice", \
    "syslog_info", \
    "syslog_debug", \
}
/** Enum names. */
const char* aim_log_flag_name(aim_log_flag_t e);

/** Enum values. */
int aim_log_flag_value(const char* str, aim_log_flag_t* e, int substr);

/** Enum descriptions. */
const char* aim_log_flag_desc(aim_log_flag_t e);

/** validator */
#define AIM_LOG_FLAG_VALID(_e) \
    ( (0 <= (_e)) && ((_e) <= AIM_LOG_FLAG_SYSLOG_DEBUG))

/** aim_log_flag_map table. */
extern aim_map_si_t aim_log_flag_map[];
/** aim_log_flag_desc_map table. */
extern aim_map_si_t aim_log_flag_desc_map[];
/* <auto.end.enum(aim_log_flag).header> */


/**
 * @brief Log function typedef, to be used by aim_logf_set.
 * @param cookie To be passed to logging function.
 * @param flag Associated log flag.
 * @param str String to log.
 */
typedef void (*aim_log_f)(void* cookie, aim_log_flag_t flag, 
                          const char* str);

#endif /* __AIM_LOG_UTIL_H__ */
/* @}*/
