/****************************************************************
 *
 *        Copyright 2013-2014, Big Switch Networks, Inc.
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
 * @brief AIM Logging Infrastructure
 *
 *
 * @addtogroup aim-log
 * @{
 *
 *****************************************************************************/
#ifndef __AIM_LOG_H__
#define __AIM_LOG_H__

#include <AIM/aim_map.h>
#include <AIM/aim_valist.h>
#include <AIM/aim_pvs.h>
#include <AIM/aim_rl.h>
#include <AIM/aim_utils.h>
#include <AIM/aim_log_util.h>
#include <AIM/aim_pvs_file.h>


/******************************************************************************
 *
 * Common Logging Flags and Options
 *
 *
 *****************************************************************************/

/* <auto.start.enum(aim_log_bit).header> */
/** aim_log_bit */
typedef enum aim_log_bit_e {
    AIM_LOG_BIT_MSG = (1 << AIM_LOG_FLAG_MSG),
    AIM_LOG_BIT_FATAL = (1 << AIM_LOG_FLAG_FATAL),
    AIM_LOG_BIT_ERROR = (1 << AIM_LOG_FLAG_ERROR),
    AIM_LOG_BIT_WARN = (1 << AIM_LOG_FLAG_WARN),
    AIM_LOG_BIT_INFO = (1 << AIM_LOG_FLAG_INFO),
    AIM_LOG_BIT_VERBOSE = (1 << AIM_LOG_FLAG_VERBOSE),
    AIM_LOG_BIT_TRACE = (1 << AIM_LOG_FLAG_TRACE),
    AIM_LOG_BIT_INTERNAL = (1 << AIM_LOG_FLAG_INTERNAL),
    AIM_LOG_BIT_BUG = (1 << AIM_LOG_FLAG_BUG),
    AIM_LOG_BIT_FTRACE = (1 << AIM_LOG_FLAG_FTRACE),
    AIM_LOG_BIT_SYSLOG_EMERG = (1 << AIM_LOG_FLAG_SYSLOG_EMERG),
    AIM_LOG_BIT_SYSLOG_ALERT = (1 << AIM_LOG_FLAG_SYSLOG_ALERT),
    AIM_LOG_BIT_SYSLOG_CRIT = (1 << AIM_LOG_FLAG_SYSLOG_CRIT),
    AIM_LOG_BIT_SYSLOG_ERROR = (1 << AIM_LOG_FLAG_SYSLOG_ERROR),
    AIM_LOG_BIT_SYSLOG_WARN = (1 << AIM_LOG_FLAG_SYSLOG_WARN),
    AIM_LOG_BIT_SYSLOG_NOTICE = (1 << AIM_LOG_FLAG_SYSLOG_NOTICE),
    AIM_LOG_BIT_SYSLOG_INFO = (1 << AIM_LOG_FLAG_SYSLOG_INFO),
    AIM_LOG_BIT_SYSLOG_DEBUG = (1 << AIM_LOG_FLAG_SYSLOG_DEBUG),
} aim_log_bit_t;

/** Enum names. */
const char* aim_log_bit_name(aim_log_bit_t e);

/** Enum values. */
int aim_log_bit_value(const char* str, aim_log_bit_t* e, int substr);

/** Enum descriptions. */
const char* aim_log_bit_desc(aim_log_bit_t e);

/** Enum validator. */
int aim_log_bit_valid(aim_log_bit_t e);

/** validator */
#define AIM_LOG_BIT_VALID(_e) \
    (aim_log_bit_valid((_e)))

/** aim_log_bit_map table. */
extern aim_map_si_t aim_log_bit_map[];
/** aim_log_bit_desc_map table. */
extern aim_map_si_t aim_log_bit_desc_map[];
/* <auto.end.enum(aim_log_bit).header> */

/* <auto.start.enum(aim_log_option).header> */
/** aim_log_option */
typedef enum aim_log_option_e {
    AIM_LOG_OPTION_ENABLE,
    AIM_LOG_OPTION_FILE_LINE,
    AIM_LOG_OPTION_FUNC,
    AIM_LOG_OPTION_TIMESTAMP,
} aim_log_option_t;

/** Enum names. */
const char* aim_log_option_name(aim_log_option_t e);

/** Enum values. */
int aim_log_option_value(const char* str, aim_log_option_t* e, int substr);

/** Enum descriptions. */
const char* aim_log_option_desc(aim_log_option_t e);

/** Enum validator. */
int aim_log_option_valid(aim_log_option_t e);

/** validator */
#define AIM_LOG_OPTION_VALID(_e) \
    (aim_log_option_valid((_e)))

/** aim_log_option_map table. */
extern aim_map_si_t aim_log_option_map[];
/** aim_log_option_desc_map table. */
extern aim_map_si_t aim_log_option_desc_map[];
/* <auto.end.enum(aim_log_option).header> */

/* <auto.start.enum(aim_log_option_bit).header> */
/** aim_log_option_bit */
typedef enum aim_log_option_bit_e {
    AIM_LOG_OPTION_BIT_ENABLE = (1 << AIM_LOG_OPTION_ENABLE),
    AIM_LOG_OPTION_BIT_FILE_LINE = (1 << AIM_LOG_OPTION_FILE_LINE),
    AIM_LOG_OPTION_BIT_FUNC = (1 << AIM_LOG_OPTION_FUNC),
    AIM_LOG_OPTION_BIT_TIMESTAMP = (1 << AIM_LOG_OPTION_TIMESTAMP),
} aim_log_option_bit_t;

/** Enum names. */
const char* aim_log_option_bit_name(aim_log_option_bit_t e);

/** Enum values. */
int aim_log_option_bit_value(const char* str, aim_log_option_bit_t* e, int substr);

/** Enum descriptions. */
const char* aim_log_option_bit_desc(aim_log_option_bit_t e);

/** Enum validator. */
int aim_log_option_bit_valid(aim_log_option_bit_t e);

/** validator */
#define AIM_LOG_OPTION_BIT_VALID(_e) \
    (aim_log_option_bit_valid((_e)))

/** aim_log_option_bit_map table. */
extern aim_map_si_t aim_log_option_bit_map[];
/** aim_log_option_bit_desc_map table. */
extern aim_map_si_t aim_log_option_bit_desc_map[];
/* <auto.end.enum(aim_log_option_bit).header> */



/**************************************************************************//**
 *
 * Each Module Instantiates this structure.
 *
 *
 *****************************************************************************/
typedef struct aim_log_s {

    /** Module Name */
    const char* name;

    /** AIM Options */
    uint32_t options;

    /** Common flags */
    uint32_t common_flags;

    /** Custom flag map (optional) */
    aim_map_si_t* custom_map;

    /** Custom flag bits */
    uint32_t custom_flags;

    /** Output log function */
    aim_log_f logf;

    /** Cookie to be passed to output log function */
    void* log_cookie;

    /** Internal */
    struct aim_log_s* next;

    /** Internal */
    uint32_t env;

    /** Internal */
    const char* logf_desc;

} aim_log_t;

/**
 * Declare and initialize your log struct with this macro.
 */
#define AIM_LOG_STRUCT_DEFINE(_options, _common_flags,       \
                              _custom_map, _custom_flags)    \
    aim_log_t AIM_LOG_STRUCT = {                             \
        .name = AIM_LOG_MODULE_NAME_STR,                     \
        .options = _options,                                 \
        .common_flags = _common_flags,                       \
        .custom_map = _custom_map,                           \
        .custom_flags = _custom_flags,                       \
        .logf = aim_pvs_logf,                                \
        .log_cookie = &aim_pvs_stderr,                       \
        .next = NULL,                                        \
        .env = 0,                                            \
        .logf_desc = "{stderr}",                             \
    }

/**
 * Baseline log settings
 */
#define AIM_LOG_BITS_BASELINE                                     \
    (AIM_LOG_BIT_FATAL + AIM_LOG_BIT_ERROR + AIM_LOG_BIT_WARN +   \
     AIM_LOG_BIT_BUG + AIM_LOG_BIT_INTERNAL + AIM_LOG_BIT_MSG +   \
     AIM_LOG_BIT_SYSLOG_EMERG + AIM_LOG_BIT_SYSLOG_ALERT +        \
     AIM_LOG_BIT_SYSLOG_CRIT + AIM_LOG_BIT_SYSLOG_ERROR +         \
     AIM_LOG_BIT_SYSLOG_WARN + AIM_LOG_BIT_SYSLOG_NOTICE +        \
     AIM_LOG_BIT_SYSLOG_INFO + AIM_LOG_BIT_SYSLOG_DEBUG)

/**
 * Reasonable default log settings
 */
#define AIM_LOG_BITS_DEFAULT (AIM_LOG_BITS_BASELINE + AIM_LOG_BIT_INFO)


/**
 * Reasonable default option settings.
 */
#ifndef AIM_LOG_OPTIONS_DEFAULT
#define AIM_LOG_OPTIONS_DEFAULT                        \
    ( AIM_LOG_OPTION_BIT_ENABLE +                      \
      AIM_LOG_OPTION_BIT_TIMESTAMP )
#endif




/**
 * @brief Add a log object to the global log list.
 * @param log The log object pointer.
 */
void aim_log_register(aim_log_t* log);

/**
 * @brief Find the log object handle for the given module name.
 * @param name The name.
 * @returns The log object handle for the given name.
 */
aim_log_t* aim_log_find(const char* name);

/**
 * @brief Get the list of all registered log objects.
 */
aim_log_t* aim_log_list(void);

/**
 * @brief Show information about a log object.
 * @param lobj The log object.
 * @param pvs The output PVS.
 */
void aim_log_show(aim_log_t* lobj, aim_pvs_t* pvs);

/**
 * @brief Set a log object's PVS
 * @param lobj The log object.
 * @param pvs The new PVS.
 * @returns The old PVS.
 */
aim_pvs_t* aim_log_pvs_set(aim_log_t* lobj, aim_pvs_t* pvs);


/**
 * @brief Set every log object's PVS
 * @param pvs The new PVS.
 */
void aim_log_pvs_set_all(aim_pvs_t* pvs);

/**
 * @brief Get a log object's PVS
 * @param lobj The log object.
 * @returns The current PVS.
 */
aim_pvs_t* aim_log_pvs_get(aim_log_t* lobj);


/**
 * @brief Set a log object's log function.
 * @param lobj The log object.
 * @param desc The logging function's string description.
 * @param logf The logging function to be used when generating logs.
 * @param cookie To be passed to the logging function when invoked.
 */
void aim_logf_set(aim_log_t* lobj, char* desc,
                  aim_log_f logf, void* cookie);

/**
 * @brief Set every log object's log function.
 * @param desc The logging function's string description.
 * @param logf The logging function to be used when generating logs.
 * @param cookie To be passed to the logging function when invoked.
 */
void aim_logf_set_all(char* desc, aim_log_f logf, void* cookie);

/**
 * @brief Get a log object's log function and cookie.
 * @param lobj The log object.
 * @param logf Pointer to the logging function to be used when generating logs.
 * @param cookie Pointer to the cookie to be passed to the logging function.
 */
void aim_logf_get(aim_log_t* lobj, aim_log_f* logf, void** cookie);


/**
 * @brief Get a log flag (by name).
 * @param lobj The log object.
 * @param flag The flag name. This can be either a common or custom name.
 * @returns 0 If the flag is set to zero.
 * @returns 1 If the flag is set to one.
 * @returns -1 If the flag does not exist.
 */
int aim_log_flag_get(aim_log_t* lobj, const char* flag);

/**
 * @brief Set the log flag (by name).
 * @param lobj The log object.
 * @param flag The flag name. This can be either a common or custom name.
 * @param value The new value for the flag.
 * @returns 1 if successful.
 * @returns 0 if the flag does not exist.
 */
int aim_log_flag_set(aim_log_t* lobj, const char* flag, int value);

/**
 * @brief Set the log flag (by name) for all logs.
 * @param flag The flag name.
 * @param value The new value for the flag.
 */
int aim_log_flag_set_all(const char* flag, int value);


/**
 * @brief Get a common log flag.
 * @param lobj The log object.
 * @param fid The common flag id.
 * @returns 0 If the flag is set to zero.
 * @returns 1 If the flag is set to one.
 * @returns -1 If the flag is invalid.
 */
int aim_log_fid_get(aim_log_t* lobj, aim_log_flag_t fid);

/**
 * @brief Set a common log flag.
 * @param lobj The log object.
 * @param fid The common flag id.
 * @param value The new value.
 */
int aim_log_fid_set(aim_log_t* lobj, aim_log_flag_t fid, int value);

/**
 * @brief Set a common log flag for all logs.
 * @param fid The common flag id.
 * @param value The new value.
 */
int aim_log_fid_set_all(aim_log_flag_t fid, int value);



/**
 * @brief Get a custom log flag.
 * @param lobj The log object.
 * @param fid The custom flag id.
 * @returns 0 If the flag is set to zero.
 * @returns 1 If the flag is set to one.
 * @returns -1 If the flag is invalid.
 */
int aim_log_custom_fid_get(aim_log_t* lobj, int fid);

/**
 * @brief Set a custom log flag.
 * @param lobj The log object.
 * @param fid The custom flag id.
 * @param value The new value
 */
int aim_log_custom_fid_set(aim_log_t* lobj, int fid, int value);

/**
 * @brief Set a custom log flag for all logs.
 * @param fid The custom flag id.
 * @param value The new value.
 */
int aim_log_custom_fid_set_all(int fid, int value);


/**
 * @brief Get a log option by name.
 * @param lobj The log object.
 * @param name The name.
 * @returns 1 If the option is set.
 * @returns 0 If the option is not set.
 * @returns -1 If the option name is invalid.
 */
int aim_log_option_name_get(aim_log_t* lobj, const char* name);

/**
 * @brief Set a log option by name.
 * @param lobj The log object.
 * @param name The name of the option.
 * @param value The value.
 *
 * @returns > 0 If successsful.
 * @returns < 0 If the option does not exist.
 */
int aim_log_option_name_set(aim_log_t* lobj, const char* name, int value);

/**
 * @brief Set a log option by name for all logs.
 * @param name The name of the option.
 * @param value The value.
 */
int aim_log_option_name_set_all(const char* name, int value);



/**
 * @brief Get a log option.
 * @param lobj The log object.
 * @param option The option.
 * @returns The option's value.
 */
int aim_log_option_get(aim_log_t* lobj, aim_log_option_t option);

/**
 * @brief Set a log option.
 * @param lobj The log object.
 * @param option The option.
 * @param value The value.
 */
int aim_log_option_set(aim_log_t* lobj, aim_log_option_t option, int value);

/**
 * @brief Set a log option for all logs.
 * @param option The option.
 * @param value The value.
 */
int aim_log_option_set_all(aim_log_option_t option, int value);



/**************************************************************************//**
 *
 * Logging Output Routines
 *
 *
 *****************************************************************************/

/**
 * @brief Output a common log message.
 * @param l The log object.
 * @param flag The AIM common log identifier.
 * @param rl The aim ratelimiter (optional)
 * @param time The current time (optional, applies to rate limiter only)
 * @param fname The function name.
 * @param file The file name.
 * @param line The line number.
 * @param fmt The message format string.
 */
void aim_log_common(aim_log_t* l, aim_log_flag_t flag,
                    aim_ratelimiter_t* rl, uint64_t time,
                    const char* fname, const char* file, int line,
                    const char* fmt, ...);

/**
 * @brief Output a common log message (vararg version).
 * @param l The log object.
 * @param flag The AIM common log identifier.
 * @param rl The aim ratelimiter (optional)
 * @param time The current time (optional, applies to rate limiter only)
 * @param fname The function name.
 * @param file The file name.
 * @param line The line number.
 * @param fmt The message format string.
 * @param vargs The arguments.
 */
void aim_log_vcommon(aim_log_t* l, aim_log_flag_t flag,
                     aim_ratelimiter_t* rl, uint64_t time,
                     const char* fname, const char* file, int line,
                     const char* fmt, va_list vargs);

/**
 * @brief Output a custom log message.
 * @param l The log object.
 * @param flag The custom log identifier.
 * @param rl The aim ratelimiter (optional)
 * @param time The current time (optional, applies to rate limiter only)
 * @param fname The function name.
 * @param file The file name.
 * @param line The line number.
 * @param fmt The message format string.
 */
void aim_log_custom(aim_log_t* l, int flag,
                    aim_ratelimiter_t* rl, uint64_t time,
                    const char* fname, const char* file, int line,
                    const char* fmt, ...);

/**
 * @brief Output a custom log message (vararg version)
 * @param l The log object.
 * @param flag The custom log identifier.
 * @param rl The aim ratelimiter (optional)
 * @param time The current time (optional, applies to rate limiter only)
 * @param fname The function name.
 * @param file The file name.
 * @param line The line number.
 * @param fmt The message format string.
 * @param vargs The arguments.
 */
void aim_log_vcustom(aim_log_t* l, int flag,
                     aim_ratelimiter_t* rl, uint64_t time,
                     const char* fname, const char* file, int line,
                     const char* fmt, va_list vargs);


/**
 * @brief Returns whether a log type is currently enabled.
 * @param l The log object.
 * @param flag The log flag;
 * @returns 1 if enabled.
 * @returns 0 if disabled.
 */
int aim_log_enabled(aim_log_t* l, aim_log_flag_t flag);

/**
 * @brief Returns whether a custom log type is currently enabled.
 * @param l The log object.
 * @param fid The custom flag id.
 */
int aim_log_custom_enabled(aim_log_t* l, int fid);


/**
 * Every Module that uses this log must define it's own unique module
 * name before including this header.
 */
#ifdef AIM_LOG_MODULE_NAME


#ifndef AIM_LOG_PREFIX1
/** Optional first prefix for your module's log messages */
#define AIM_LOG_PREFIX1 ""
#endif

#ifndef AIM_LOG_PREFIX2
/** Optional second prefix for your module's log messages */
#define AIM_LOG_PREFIX2 ""
#endif


/** This will be the name of your private log structure. */
#define AIM_LOG_STRUCT __AIM_LOG_STRUCT(AIM_LOG_MODULE_NAME)
/** internal */
#define ___AIM_LOG_STRUCT(_name) __aim_log_##_name##__
/** internal */
#define __AIM_LOG_STRUCT(_name) ___AIM_LOG_STRUCT(_name)

/** Reference the pointer to your log struct */
#define AIM_LOG_STRUCT_POINTER (& AIM_LOG_STRUCT)
/** Your module's name string */
#define AIM_LOG_MODULE_NAME_STR AIM_STRINGIFY(AIM_LOG_MODULE_NAME)


/**
 * Log handle must be externed or defined.
 */
#ifndef AIM_LOG_STRUCT_NO_EXTERN
extern aim_log_t AIM_LOG_STRUCT;
#endif

/**
 * You can register your log structure using this macro
 */
#define AIM_LOG_STRUCT_REGISTER() \
    aim_log_register(AIM_LOG_STRUCT_POINTER)

/**
 * Determine whether a log setting is enabled.
 */
#define AIM_LOG_ENABLED(_flag)                                          \
    aim_log_enabled(AIM_LOG_STRUCT_POINTER, AIM_LOG_FLAG_##_flag)

/**
 * Quickly determine whether a log setting might be enabled.
 */
#if AIM_CONFIG_LOG_INCLUDE_ENV_VARIABLES == 0
#define AIM_LOG_ENABLED_FAST(_flag) \
    AIM_BIT_GET(AIM_LOG_STRUCT_POINTER->common_flags, AIM_LOG_FLAG_##_flag)
#else
#define AIM_LOG_ENABLED_FAST(_flag) 1
#endif

/**
 * Determine whether a custom log setting is enabled.
 */
#define AIM_LOG_CUSTOM_ENABLED(_fid)                    \
    aim_log_custom_enabled(AIM_LOG_STRUCT_POINTER, _fid)

/**
 * The module can initialize its handle using this macro.
 */
#define AIM_LOG_CREATE(_cf) \
    AIM_LOG_STRUCT_POINTER = aim_log_create(AIM_LOG_MODULE_NAME_STR, _cf)






/**
 * Issue a common log message with rate-limiting.
 */
#define AIM_LOG_MOD_RL_COMMON(_flag, _rl, _time, ...)                       \
    do {                                                                    \
        if (AIM_LOG_ENABLED_FAST(_flag)) {                                  \
            aim_log_common(AIM_LOG_STRUCT_POINTER, AIM_LOG_FLAG_##_flag,    \
                           _rl, _time,                                      \
                           __func__, __FILE__, __LINE__,                    \
                           "[" AIM_LOG_MODULE_NAME_STR "] " AIM_LOG_PREFIX1 AIM_LOG_PREFIX2 \
                           AIM_VA_ARGS_FIRST(__VA_ARGS__) AIM_VA_ARGS_REST(__VA_ARGS__)); \
        }                                                                   \
    } while (0)


/**
 * Issue a common log message, no rate limiting.
 */
#define AIM_LOG_MOD_COMMON(_flag, ...) AIM_LOG_MOD_RL_COMMON(_flag, NULL, 0, __VA_ARGS__)






/**
 * Issue a custom log message, with rate-limiting
 */
#define AIM_LOG_MOD_RL_CUSTOM(_fid, _fname, _rl, _time, ...)            \
    aim_log_custom(AIM_LOG_STRUCT_POINTER, _fid,                        \
                   _rl, _time,                                          \
                   __func__, __FILE__, __LINE__,                        \
                   "[" AIM_LOG_MODULE_NAME_STR "] " AIM_LOG_PREFIX1 AIM_LOG_PREFIX2 \
                   ": " _fname ": " AIM_VA_ARGS_FIRST(__VA_ARGS__) AIM_VA_ARGS_REST(__VA_ARGS__))

/**
 * Issue a custom log message, no rate limiting
 */
#define AIM_LOG_MOD_CUSTOM(_fid, _fname, ...) AIM_LOG_MOD_RL_CUSTOM(_fid, _fname, NULL, 0, __VA_ARGS__)





/**
 * Issue a common object log message with rate limiting.
 */
#define AIM_LOG_OBJ_RL_COMMON(_obj, _flag, _rl, _time, ...)             \
    aim_log_common(AIM_LOG_STRUCT_POINTER, AIM_LOG_FLAG_##_flag,        \
                   _rl, _time,                                          \
                   __func__, __FILE__, __LINE__,                        \
                   "[" AIM_LOG_MODULE_NAME_STR "] " AIM_LOG_PREFIX1 AIM_LOG_PREFIX2 "(%s)" \
                   AIM_VA_ARGS_FIRST(__VA_ARGS__),  (_obj)->log_string AIM_VA_ARGS_REST(__VA_ARGS__))


/**
 * Issue a common object log message, no rate limiting.
 */
#define AIM_LOG_OBJ_COMMON(_obj, _flag, ...) AIM_LOG_OBJ_RL_COMMON(_obj, _flag, NULL, 0, __VA_ARGS__)




/**
 * Issue a common object log message with rate limiting.
 */
#define AIM_LOG_OBJ_RL_CUSTOM(_obj, _fid, _fname, _rl, _time, ...)      \
    aim_log_custom(AIM_LOG_STRUCT_POINTER, _fid,                        \
                   _rl, _time,                                          \
                   __func__, __FILE__, __LINE__,                        \
                   "[" AIM_LOG_MODULE_NAME_STR "] " AIM_LOG_PREFIX1 AIM_LOG_PREFIX2 "(%s)" \
                   ": " _fname ": " AIM_VA_ARGS_FIRST(__VA_ARGS__),  (_obj)->log_string AIM_VA_ARGS_REST(__VA_ARGS__))


/**
 * Issue a common object log message, no rate limiting.
 */
#define AIM_LOG_OBJ_CUSTOM(_obj, _fid, _fname, ...)                     \
    AIM_LOG_OBJ_RL_CUSTOM(_obj, _fid, _fname, NULL, 0, __VA_ARGS__)


/* <auto.start.aim_common_log_macro(ALL).header> */

/******************************************************************************
 *
 * Common Module Log Macros
 *
 *****************************************************************************/

/** Log a module-level msg */
#define AIM_LOG_MOD_MSG(...) \
    AIM_LOG_MOD_COMMON(MSG, __VA_ARGS__)
/** Log a module-level msg with ratelimiting */
#define AIM_LOG_MOD_RL_MSG(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(MSG, _rl, _time, __VA_ARGS__)


/** Log a module-level fatal */
#define AIM_LOG_MOD_FATAL(...) \
    AIM_LOG_MOD_COMMON(FATAL, __VA_ARGS__)
/** Log a module-level fatal with ratelimiting */
#define AIM_LOG_MOD_RL_FATAL(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(FATAL, _rl, _time, __VA_ARGS__)


/** Log a module-level error */
#define AIM_LOG_MOD_ERROR(...) \
    AIM_LOG_MOD_COMMON(ERROR, __VA_ARGS__)
/** Log a module-level error with ratelimiting */
#define AIM_LOG_MOD_RL_ERROR(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(ERROR, _rl, _time, __VA_ARGS__)


/** Log a module-level warn */
#define AIM_LOG_MOD_WARN(...) \
    AIM_LOG_MOD_COMMON(WARN, __VA_ARGS__)
/** Log a module-level warn with ratelimiting */
#define AIM_LOG_MOD_RL_WARN(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(WARN, _rl, _time, __VA_ARGS__)


/** Log a module-level info */
#define AIM_LOG_MOD_INFO(...) \
    AIM_LOG_MOD_COMMON(INFO, __VA_ARGS__)
/** Log a module-level info with ratelimiting */
#define AIM_LOG_MOD_RL_INFO(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(INFO, _rl, _time, __VA_ARGS__)


/** Log a module-level verbose */
#define AIM_LOG_MOD_VERBOSE(...) \
    AIM_LOG_MOD_COMMON(VERBOSE, __VA_ARGS__)
/** Log a module-level verbose with ratelimiting */
#define AIM_LOG_MOD_RL_VERBOSE(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(VERBOSE, _rl, _time, __VA_ARGS__)


/** Log a module-level trace */
#define AIM_LOG_MOD_TRACE(...) \
    AIM_LOG_MOD_COMMON(TRACE, __VA_ARGS__)
/** Log a module-level trace with ratelimiting */
#define AIM_LOG_MOD_RL_TRACE(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(TRACE, _rl, _time, __VA_ARGS__)


/** Log a module-level internal */
#define AIM_LOG_MOD_INTERNAL(...) \
    AIM_LOG_MOD_COMMON(INTERNAL, __VA_ARGS__)
/** Log a module-level internal with ratelimiting */
#define AIM_LOG_MOD_RL_INTERNAL(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(INTERNAL, _rl, _time, __VA_ARGS__)


/** Log a module-level bug */
#define AIM_LOG_MOD_BUG(...) \
    AIM_LOG_MOD_COMMON(BUG, __VA_ARGS__)
/** Log a module-level bug with ratelimiting */
#define AIM_LOG_MOD_RL_BUG(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(BUG, _rl, _time, __VA_ARGS__)


/** Log a module-level ftrace */
#define AIM_LOG_MOD_FTRACE(...) \
    AIM_LOG_MOD_COMMON(FTRACE, __VA_ARGS__)
/** Log a module-level ftrace with ratelimiting */
#define AIM_LOG_MOD_RL_FTRACE(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(FTRACE, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_emerg */
#define AIM_LOG_MOD_SYSLOG_EMERG(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_EMERG, __VA_ARGS__)
/** Log a module-level syslog_emerg with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_EMERG(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_EMERG, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_alert */
#define AIM_LOG_MOD_SYSLOG_ALERT(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_ALERT, __VA_ARGS__)
/** Log a module-level syslog_alert with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_ALERT(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_ALERT, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_crit */
#define AIM_LOG_MOD_SYSLOG_CRIT(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_CRIT, __VA_ARGS__)
/** Log a module-level syslog_crit with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_CRIT(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_CRIT, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_error */
#define AIM_LOG_MOD_SYSLOG_ERROR(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_ERROR, __VA_ARGS__)
/** Log a module-level syslog_error with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_ERROR(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_ERROR, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_warn */
#define AIM_LOG_MOD_SYSLOG_WARN(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_WARN, __VA_ARGS__)
/** Log a module-level syslog_warn with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_WARN(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_WARN, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_notice */
#define AIM_LOG_MOD_SYSLOG_NOTICE(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_NOTICE, __VA_ARGS__)
/** Log a module-level syslog_notice with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_NOTICE(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_NOTICE, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_info */
#define AIM_LOG_MOD_SYSLOG_INFO(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_INFO, __VA_ARGS__)
/** Log a module-level syslog_info with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_INFO(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_INFO, _rl, _time, __VA_ARGS__)


/** Log a module-level syslog_debug */
#define AIM_LOG_MOD_SYSLOG_DEBUG(...) \
    AIM_LOG_MOD_COMMON(SYSLOG_DEBUG, __VA_ARGS__)
/** Log a module-level syslog_debug with ratelimiting */
#define AIM_LOG_MOD_RL_SYSLOG_DEBUG(_rl, _time, ...)           \
    AIM_LOG_MOD_RL_COMMON(SYSLOG_DEBUG, _rl, _time, __VA_ARGS__)


/******************************************************************************
 *
 * Common Object Log Macros
 *
 *****************************************************************************/

/** Log an object-level msg */
#define AIM_LOG_OBJ_MSG(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, MSG, __VA_ARGS__)
/** Log an object-level msg with ratelimiting */
#define AIM_LOG_OBJ_RL_MSG(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, MSG, _rl, _time, __VA_ARGS__)


/** Log an object-level fatal */
#define AIM_LOG_OBJ_FATAL(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, FATAL, __VA_ARGS__)
/** Log an object-level fatal with ratelimiting */
#define AIM_LOG_OBJ_RL_FATAL(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, FATAL, _rl, _time, __VA_ARGS__)


/** Log an object-level error */
#define AIM_LOG_OBJ_ERROR(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, ERROR, __VA_ARGS__)
/** Log an object-level error with ratelimiting */
#define AIM_LOG_OBJ_RL_ERROR(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, ERROR, _rl, _time, __VA_ARGS__)


/** Log an object-level warn */
#define AIM_LOG_OBJ_WARN(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, WARN, __VA_ARGS__)
/** Log an object-level warn with ratelimiting */
#define AIM_LOG_OBJ_RL_WARN(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, WARN, _rl, _time, __VA_ARGS__)


/** Log an object-level info */
#define AIM_LOG_OBJ_INFO(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, INFO, __VA_ARGS__)
/** Log an object-level info with ratelimiting */
#define AIM_LOG_OBJ_RL_INFO(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, INFO, _rl, _time, __VA_ARGS__)


/** Log an object-level verbose */
#define AIM_LOG_OBJ_VERBOSE(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, VERBOSE, __VA_ARGS__)
/** Log an object-level verbose with ratelimiting */
#define AIM_LOG_OBJ_RL_VERBOSE(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, VERBOSE, _rl, _time, __VA_ARGS__)


/** Log an object-level trace */
#define AIM_LOG_OBJ_TRACE(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, TRACE, __VA_ARGS__)
/** Log an object-level trace with ratelimiting */
#define AIM_LOG_OBJ_RL_TRACE(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, TRACE, _rl, _time, __VA_ARGS__)


/** Log an object-level internal */
#define AIM_LOG_OBJ_INTERNAL(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, INTERNAL, __VA_ARGS__)
/** Log an object-level internal with ratelimiting */
#define AIM_LOG_OBJ_RL_INTERNAL(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, INTERNAL, _rl, _time, __VA_ARGS__)


/** Log an object-level bug */
#define AIM_LOG_OBJ_BUG(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, BUG, __VA_ARGS__)
/** Log an object-level bug with ratelimiting */
#define AIM_LOG_OBJ_RL_BUG(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, BUG, _rl, _time, __VA_ARGS__)


/** Log an object-level ftrace */
#define AIM_LOG_OBJ_FTRACE(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, FTRACE, __VA_ARGS__)
/** Log an object-level ftrace with ratelimiting */
#define AIM_LOG_OBJ_RL_FTRACE(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, FTRACE, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_emerg */
#define AIM_LOG_OBJ_SYSLOG_EMERG(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_EMERG, __VA_ARGS__)
/** Log an object-level syslog_emerg with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_EMERG(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_EMERG, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_alert */
#define AIM_LOG_OBJ_SYSLOG_ALERT(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_ALERT, __VA_ARGS__)
/** Log an object-level syslog_alert with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_ALERT(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_ALERT, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_crit */
#define AIM_LOG_OBJ_SYSLOG_CRIT(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_CRIT, __VA_ARGS__)
/** Log an object-level syslog_crit with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_CRIT(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_CRIT, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_error */
#define AIM_LOG_OBJ_SYSLOG_ERROR(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_ERROR, __VA_ARGS__)
/** Log an object-level syslog_error with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_ERROR(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_ERROR, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_warn */
#define AIM_LOG_OBJ_SYSLOG_WARN(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_WARN, __VA_ARGS__)
/** Log an object-level syslog_warn with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_WARN(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_WARN, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_notice */
#define AIM_LOG_OBJ_SYSLOG_NOTICE(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_NOTICE, __VA_ARGS__)
/** Log an object-level syslog_notice with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_NOTICE(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_NOTICE, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_info */
#define AIM_LOG_OBJ_SYSLOG_INFO(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_INFO, __VA_ARGS__)
/** Log an object-level syslog_info with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_INFO(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_INFO, _rl, _time, __VA_ARGS__)


/** Log an object-level syslog_debug */
#define AIM_LOG_OBJ_SYSLOG_DEBUG(_obj, ...) \
    AIM_LOG_OBJ_COMMON(_obj, SYSLOG_DEBUG, __VA_ARGS__)
/** Log an object-level syslog_debug with ratelimiting */
#define AIM_LOG_OBJ_RL_SYSLOG_DEBUG(_obj, _rl, _time, ...) \
    AIM_LOG_OBJ_RL_COMMON(_obj, SYSLOG_DEBUG, _rl, _time, __VA_ARGS__)


/******************************************************************************
 *
 * Default Macro Mappings
 *
 *****************************************************************************/
#ifdef AIM_LOG_OBJ_DEFAULT

/** MSG -> OBJ_MSG */
#define AIM_LOG_MSG AIM_LOG_OBJ_MSG
/** RL_MSG -> OBJ_RL_MSG */
#define AIM_LOG_RL_MSG AIM_LOG_OBJ_RL_MSG


/** FATAL -> OBJ_FATAL */
#define AIM_LOG_FATAL AIM_LOG_OBJ_FATAL
/** RL_FATAL -> OBJ_RL_FATAL */
#define AIM_LOG_RL_FATAL AIM_LOG_OBJ_RL_FATAL


/** ERROR -> OBJ_ERROR */
#define AIM_LOG_ERROR AIM_LOG_OBJ_ERROR
/** RL_ERROR -> OBJ_RL_ERROR */
#define AIM_LOG_RL_ERROR AIM_LOG_OBJ_RL_ERROR


/** WARN -> OBJ_WARN */
#define AIM_LOG_WARN AIM_LOG_OBJ_WARN
/** RL_WARN -> OBJ_RL_WARN */
#define AIM_LOG_RL_WARN AIM_LOG_OBJ_RL_WARN


/** INFO -> OBJ_INFO */
#define AIM_LOG_INFO AIM_LOG_OBJ_INFO
/** RL_INFO -> OBJ_RL_INFO */
#define AIM_LOG_RL_INFO AIM_LOG_OBJ_RL_INFO


/** VERBOSE -> OBJ_VERBOSE */
#define AIM_LOG_VERBOSE AIM_LOG_OBJ_VERBOSE
/** RL_VERBOSE -> OBJ_RL_VERBOSE */
#define AIM_LOG_RL_VERBOSE AIM_LOG_OBJ_RL_VERBOSE


/** TRACE -> OBJ_TRACE */
#define AIM_LOG_TRACE AIM_LOG_OBJ_TRACE
/** RL_TRACE -> OBJ_RL_TRACE */
#define AIM_LOG_RL_TRACE AIM_LOG_OBJ_RL_TRACE


/** INTERNAL -> OBJ_INTERNAL */
#define AIM_LOG_INTERNAL AIM_LOG_OBJ_INTERNAL
/** RL_INTERNAL -> OBJ_RL_INTERNAL */
#define AIM_LOG_RL_INTERNAL AIM_LOG_OBJ_RL_INTERNAL


/** BUG -> OBJ_BUG */
#define AIM_LOG_BUG AIM_LOG_OBJ_BUG
/** RL_BUG -> OBJ_RL_BUG */
#define AIM_LOG_RL_BUG AIM_LOG_OBJ_RL_BUG


/** FTRACE -> OBJ_FTRACE */
#define AIM_LOG_FTRACE AIM_LOG_OBJ_FTRACE
/** RL_FTRACE -> OBJ_RL_FTRACE */
#define AIM_LOG_RL_FTRACE AIM_LOG_OBJ_RL_FTRACE


/** SYSLOG_EMERG -> OBJ_SYSLOG_EMERG */
#define AIM_LOG_SYSLOG_EMERG AIM_LOG_OBJ_SYSLOG_EMERG
/** RL_SYSLOG_EMERG -> OBJ_RL_SYSLOG_EMERG */
#define AIM_LOG_RL_SYSLOG_EMERG AIM_LOG_OBJ_RL_SYSLOG_EMERG


/** SYSLOG_ALERT -> OBJ_SYSLOG_ALERT */
#define AIM_LOG_SYSLOG_ALERT AIM_LOG_OBJ_SYSLOG_ALERT
/** RL_SYSLOG_ALERT -> OBJ_RL_SYSLOG_ALERT */
#define AIM_LOG_RL_SYSLOG_ALERT AIM_LOG_OBJ_RL_SYSLOG_ALERT


/** SYSLOG_CRIT -> OBJ_SYSLOG_CRIT */
#define AIM_LOG_SYSLOG_CRIT AIM_LOG_OBJ_SYSLOG_CRIT
/** RL_SYSLOG_CRIT -> OBJ_RL_SYSLOG_CRIT */
#define AIM_LOG_RL_SYSLOG_CRIT AIM_LOG_OBJ_RL_SYSLOG_CRIT


/** SYSLOG_ERROR -> OBJ_SYSLOG_ERROR */
#define AIM_LOG_SYSLOG_ERROR AIM_LOG_OBJ_SYSLOG_ERROR
/** RL_SYSLOG_ERROR -> OBJ_RL_SYSLOG_ERROR */
#define AIM_LOG_RL_SYSLOG_ERROR AIM_LOG_OBJ_RL_SYSLOG_ERROR


/** SYSLOG_WARN -> OBJ_SYSLOG_WARN */
#define AIM_LOG_SYSLOG_WARN AIM_LOG_OBJ_SYSLOG_WARN
/** RL_SYSLOG_WARN -> OBJ_RL_SYSLOG_WARN */
#define AIM_LOG_RL_SYSLOG_WARN AIM_LOG_OBJ_RL_SYSLOG_WARN


/** SYSLOG_NOTICE -> OBJ_SYSLOG_NOTICE */
#define AIM_LOG_SYSLOG_NOTICE AIM_LOG_OBJ_SYSLOG_NOTICE
/** RL_SYSLOG_NOTICE -> OBJ_RL_SYSLOG_NOTICE */
#define AIM_LOG_RL_SYSLOG_NOTICE AIM_LOG_OBJ_RL_SYSLOG_NOTICE


/** SYSLOG_INFO -> OBJ_SYSLOG_INFO */
#define AIM_LOG_SYSLOG_INFO AIM_LOG_OBJ_SYSLOG_INFO
/** RL_SYSLOG_INFO -> OBJ_RL_SYSLOG_INFO */
#define AIM_LOG_RL_SYSLOG_INFO AIM_LOG_OBJ_RL_SYSLOG_INFO


/** SYSLOG_DEBUG -> OBJ_SYSLOG_DEBUG */
#define AIM_LOG_SYSLOG_DEBUG AIM_LOG_OBJ_SYSLOG_DEBUG
/** RL_SYSLOG_DEBUG -> OBJ_RL_SYSLOG_DEBUG */
#define AIM_LOG_RL_SYSLOG_DEBUG AIM_LOG_OBJ_RL_SYSLOG_DEBUG


#else

/** MSG -> MOD_MSG */
#define AIM_LOG_MSG AIM_LOG_MOD_MSG
/** RL_MSG -> MOD_RL_MSG */
#define AIM_LOG_RL_MSG AIM_LOG_MOD_RL_MSG

/** FATAL -> MOD_FATAL */
#define AIM_LOG_FATAL AIM_LOG_MOD_FATAL
/** RL_FATAL -> MOD_RL_FATAL */
#define AIM_LOG_RL_FATAL AIM_LOG_MOD_RL_FATAL

/** ERROR -> MOD_ERROR */
#define AIM_LOG_ERROR AIM_LOG_MOD_ERROR
/** RL_ERROR -> MOD_RL_ERROR */
#define AIM_LOG_RL_ERROR AIM_LOG_MOD_RL_ERROR

/** WARN -> MOD_WARN */
#define AIM_LOG_WARN AIM_LOG_MOD_WARN
/** RL_WARN -> MOD_RL_WARN */
#define AIM_LOG_RL_WARN AIM_LOG_MOD_RL_WARN

/** INFO -> MOD_INFO */
#define AIM_LOG_INFO AIM_LOG_MOD_INFO
/** RL_INFO -> MOD_RL_INFO */
#define AIM_LOG_RL_INFO AIM_LOG_MOD_RL_INFO

/** VERBOSE -> MOD_VERBOSE */
#define AIM_LOG_VERBOSE AIM_LOG_MOD_VERBOSE
/** RL_VERBOSE -> MOD_RL_VERBOSE */
#define AIM_LOG_RL_VERBOSE AIM_LOG_MOD_RL_VERBOSE

/** TRACE -> MOD_TRACE */
#define AIM_LOG_TRACE AIM_LOG_MOD_TRACE
/** RL_TRACE -> MOD_RL_TRACE */
#define AIM_LOG_RL_TRACE AIM_LOG_MOD_RL_TRACE

/** INTERNAL -> MOD_INTERNAL */
#define AIM_LOG_INTERNAL AIM_LOG_MOD_INTERNAL
/** RL_INTERNAL -> MOD_RL_INTERNAL */
#define AIM_LOG_RL_INTERNAL AIM_LOG_MOD_RL_INTERNAL

/** BUG -> MOD_BUG */
#define AIM_LOG_BUG AIM_LOG_MOD_BUG
/** RL_BUG -> MOD_RL_BUG */
#define AIM_LOG_RL_BUG AIM_LOG_MOD_RL_BUG

/** FTRACE -> MOD_FTRACE */
#define AIM_LOG_FTRACE AIM_LOG_MOD_FTRACE
/** RL_FTRACE -> MOD_RL_FTRACE */
#define AIM_LOG_RL_FTRACE AIM_LOG_MOD_RL_FTRACE

/** SYSLOG_EMERG -> MOD_SYSLOG_EMERG */
#define AIM_LOG_SYSLOG_EMERG AIM_LOG_MOD_SYSLOG_EMERG
/** RL_SYSLOG_EMERG -> MOD_RL_SYSLOG_EMERG */
#define AIM_LOG_RL_SYSLOG_EMERG AIM_LOG_MOD_RL_SYSLOG_EMERG

/** SYSLOG_ALERT -> MOD_SYSLOG_ALERT */
#define AIM_LOG_SYSLOG_ALERT AIM_LOG_MOD_SYSLOG_ALERT
/** RL_SYSLOG_ALERT -> MOD_RL_SYSLOG_ALERT */
#define AIM_LOG_RL_SYSLOG_ALERT AIM_LOG_MOD_RL_SYSLOG_ALERT

/** SYSLOG_CRIT -> MOD_SYSLOG_CRIT */
#define AIM_LOG_SYSLOG_CRIT AIM_LOG_MOD_SYSLOG_CRIT
/** RL_SYSLOG_CRIT -> MOD_RL_SYSLOG_CRIT */
#define AIM_LOG_RL_SYSLOG_CRIT AIM_LOG_MOD_RL_SYSLOG_CRIT

/** SYSLOG_ERROR -> MOD_SYSLOG_ERROR */
#define AIM_LOG_SYSLOG_ERROR AIM_LOG_MOD_SYSLOG_ERROR
/** RL_SYSLOG_ERROR -> MOD_RL_SYSLOG_ERROR */
#define AIM_LOG_RL_SYSLOG_ERROR AIM_LOG_MOD_RL_SYSLOG_ERROR

/** SYSLOG_WARN -> MOD_SYSLOG_WARN */
#define AIM_LOG_SYSLOG_WARN AIM_LOG_MOD_SYSLOG_WARN
/** RL_SYSLOG_WARN -> MOD_RL_SYSLOG_WARN */
#define AIM_LOG_RL_SYSLOG_WARN AIM_LOG_MOD_RL_SYSLOG_WARN

/** SYSLOG_NOTICE -> MOD_SYSLOG_NOTICE */
#define AIM_LOG_SYSLOG_NOTICE AIM_LOG_MOD_SYSLOG_NOTICE
/** RL_SYSLOG_NOTICE -> MOD_RL_SYSLOG_NOTICE */
#define AIM_LOG_RL_SYSLOG_NOTICE AIM_LOG_MOD_RL_SYSLOG_NOTICE

/** SYSLOG_INFO -> MOD_SYSLOG_INFO */
#define AIM_LOG_SYSLOG_INFO AIM_LOG_MOD_SYSLOG_INFO
/** RL_SYSLOG_INFO -> MOD_RL_SYSLOG_INFO */
#define AIM_LOG_RL_SYSLOG_INFO AIM_LOG_MOD_RL_SYSLOG_INFO

/** SYSLOG_DEBUG -> MOD_SYSLOG_DEBUG */
#define AIM_LOG_SYSLOG_DEBUG AIM_LOG_MOD_SYSLOG_DEBUG
/** RL_SYSLOG_DEBUG -> MOD_RL_SYSLOG_DEBUG */
#define AIM_LOG_RL_SYSLOG_DEBUG AIM_LOG_MOD_RL_SYSLOG_DEBUG

#endif
/* <auto.end.aim_common_log_macro(ALL).header> */


/** Function Trace Enter */
#define AIM_LOG_FENTER(...)                                             \
    AIM_LOG_MOD_COMMON(FTRACE, "%s:ENTER " AIM_VA_ARGS_FIRST(__VA_ARGS__), __func__ AIM_VA_ARGS_REST(__VA_ARGS__))
/** Function Trace Enter with ratelimiting */
#define AIM_LOG_RL_FENTER(_rl, _time, ...)                              \
    AIM_LOG_MOD_RL_COMMON(FTRACE, _rl, _time, "%s:ENTER " AIM_VA_ARGS_FIRST(__VA_ARGS__), __func__ AIM_VA_ARGS_REST(__VA_ARGS__))

/** Function Trace Exit */
 #define AIM_LOG_FEXIT(...)                                              \
    AIM_LOG_MOD_COMMON(FTRACE, "%s:EXIT " AIM_VA_ARGS_FIRST(__VA_ARGS__), __func__ AIM_VA_ARGS_REST(__VA_ARGS__))
/** Function Trace Exit with ratelimiting */
#define AIM_LOG_RL_FEXIT(_rl, _time, ...)                               \
    AIM_LOG_MOD_RL_COMMON(FTRACE, _rl, _time, "%s:EXIT " AIM_VA_ARGS_FIRST(__VA_ARGS__), __func__ AIM_VA_ARGS_REST(__VA_ARGS__))

#endif /* AIM_LOG_MODULE_NAME */


/**
 * All messages sent through the AIM_SYSLOG mechanism are embedded as
 * self-documenting strings in the compiled binary.
 *
 * The format of the string is as follows:
 * AIM_SYSLOG_REFERENCE:{ python dictionary key/value pairs }
 *
 * The python dictionary contains the following keys:
 *   module: The name of the module generating the message.
 *   level: The SYSLOG level for the message.
 *   file: The source file name.
 *   line: The source line number.
 *   format: The human-readable format string for the message.
 *   doc: The message documentation.
 *
 * These self-documenting strings can be extracted from a binary using
 * the infra/tools/asre.py script for autogenerating documentation.
 *
 */
extern char* aim_syslog_reference;

#define __PYTHON_KV(_key, _value)               \
    "'" #_key "': \"\"\"" _value "\"\"\","

#define __AIM_SYSLOG_REFERENCE_FINAL(_level, _h, _doc, _line)           \
    aim_syslog_reference = "AIM_SYSLOG_REFERENCE:{" \
        __PYTHON_KV(module, AIM_LOG_MODULE_NAME_STR) \
        __PYTHON_KV(level, _level) \
        __PYTHON_KV(file, __FILE__) \
        __PYTHON_KV(line, #_line) \
        __PYTHON_KV(format, _h)  \
        __PYTHON_KV(doc, _doc) "}"

#define __AIM_SYSLOG_REFERENCE_LINE(_level, _h, _doc, _line) __AIM_SYSLOG_REFERENCE_FINAL(_level, _h, _doc, _line)
#define AIM_SYSLOG_REFERENCE(_level, _h, _doc) __AIM_SYSLOG_REFERENCE_LINE(#_level, _h, _doc, __LINE__)


/* Syslog macros */
#define AIM_SYSLOG_EMERG(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(EMERG,_human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_EMERG(__VA_ARGS__);                              \
    } while(0)

#define AIM_SYSLOG_RL_EMERG(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(EMERG, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_EMERG(__VA_ARGS__);                           \
    } while(0)

#define AIM_SYSLOG_ALERT(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(ALERT, _human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_ALERT(__VA_ARGS__);                              \
    } while(0)

#define AIM_SYSLOG_RL_ALERT(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(ALERT, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_ALERT(__VA_ARGS__);                           \
    } while(0)

#define AIM_SYSLOG_CRIT(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(CRIT, _human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_CRIT(__VA_ARGS__);                               \
    } while(0)


#define AIM_SYSLOG_RL_CRIT(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(CRIT, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_CRIT(__VA_ARGS__);                            \
    } while(0)

#define AIM_SYSLOG_ERROR(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(ERROR, _human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_ERROR(__VA_ARGS__);                              \
    } while(0)

#define AIM_SYSLOG_RL_ERROR(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(ERROR, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_ERROR(__VA_ARGS__);                           \
    } while(0)

#define AIM_SYSLOG_WARN(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(WARN, _human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_WARN(__VA_ARGS__);                               \
    } while(0)

#define AIM_SYSLOG_RL_WARN(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(WARN, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_WARN(__VA_ARGS__);                            \
    } while(0)

#define AIM_SYSLOG_NOTICE(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(NOTICE, _human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_NOTICE(__VA_ARGS__);                             \
    } while(0)

#define AIM_SYSLOG_RL_NOTICE(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(NOTICE, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_NOTICE(__VA_ARGS__);                          \
    } while(0)

#define AIM_SYSLOG_INFO(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(INFO, _human_readable_format_str, _documentation); \
        AIM_LOG_SYSLOG_INFO(__VA_ARGS__);                               \
    } while(0)

#define AIM_SYSLOG_RL_INFO(_human_readable_format_str, _documentation, ...) \
    do {                                                                \
        AIM_SYSLOG_REFERENCE(INFO, _human_readable_format_str, _documentation); \
        AIM_LOG_RL_SYSLOG_INFO(__VA_ARGS__);                            \
    } while(0)

#define AIM_SYSLOG_DEBUG(...)                                           \
    do {                                                                \
        AIM_LOG_SYSLOG_DEBUG(__VA_ARGS__);                              \
    } while(0)

#define AIM_SYSLOG_RL_DEBUG(...)                                        \
    do {                                                                \
        AIM_LOG_RL_SYSLOG_DEBUG(__VA_ARGS__);                           \
    } while(0)


/**
 * @brief Map a syslog level string to a set of flags and options
 * @param syslog_str The string being mapped
 * @param flags Pointer for storing flags
 *
 * Valid input strings include:
 * emergencies alerts critical errors warnings notifications
 * informational debugging
 *
 * Also support the non-standard strings verbose == informational and
 * trace == debugging.  Strings must be lower case and complete
 */

extern int aim_log_syslog_level_map(const char *syslog_str,
                                    uint32_t *flags);

#endif /* __AIM_LOG_H__ */
/* @}*/
