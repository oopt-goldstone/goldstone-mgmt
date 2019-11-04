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
 *  /module/inc/AIM/aim_compiler.h
 *
 * @file
 * @brief Macros wrapping compiler-specific functionality
 *
 * @addtogroup aim-compiler
 * @{
 *
 *****************************************************************************/
#ifndef __AIM_COMPILER_H__
#define __AIM_COMPILER_H__

#include <AIM/aim_config.h>

/* Promise GCC that the returned pointer will not alias any other pointer */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_MALLOC __attribute__((__malloc__))
#else
/* No-op default implementation */
#define AIM_COMPILER_ATTR_MALLOC
#endif

/* Promise GCC that the function will not return */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_NORETURN __attribute__((__noreturn__))
#else
/* No-op default implementation */
#define AIM_COMPILER_ATTR_NORETURN
#endif

/* This variable may be unused */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_UNUSED __attribute__((__unused__))
#else
/* No-op default implementation */
#define AIM_COMPILER_ATTR_UNUSED
#endif

/* Don't inline this function */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_NOINLINE __attribute__((__noinline__))
#else
/* No-op default implementation */
#define AIM_COMPILER_ATTR_NOINLINE
#endif

/* Warn if the result of this function is unused */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_WARN_UNUSED_RESULT __attribute__((__warn_unused_result__))
#else
/* No-op default implementation */
#define AIM_COMPILER_ATTR_WARN_UNUSED_RESULT
#endif

/*
 * These attributes don't allow for a no-op fallback. Leave them undefined to
 * create an error if used and allow users to check if they're available.
 */

/* Tightly pack a struct */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_PACKED __attribute__((__packed__))
#endif

/* A pointer to this type may alias pointers to other types */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_MAY_ALIAS __attribute__((__may_alias__))
#endif

/* This symbol may be overridden by a non-weak symbol from another compilation unit */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_WEAK __attribute__((__weak__))
#endif

/* Force alignment to N bytes */
#ifdef __GNUC__
#define AIM_COMPILER_ATTR_ALIGNED __attribute__((__aligned__ (N)))
#endif

#endif /* __AIM_COMPILER_H__ */
/*@}*/
