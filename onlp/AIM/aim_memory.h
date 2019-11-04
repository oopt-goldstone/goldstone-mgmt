/****************************************************************
 *
 *        Copyright 2013, Big Switch Networks, Inc.
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
 *  /module/inc/AIM/aim_memory.h
 *
 * @file
 * @brief Memory allocation.
 *
 * @addtogroup aim-memory
 * @{
 *
 *****************************************************************************/
#ifndef __AIM_MEMORY_H__
#define __AIM_MEMORY_H__

#include <AIM/aim_config.h>
#include <AIM/aim_compiler.h>

/**
 * @brief Allocate memory.
 * @param size Size.
 *
 * The returned memory is uninitialized.
 * Aborts if allocation fails.
 */
void *aim_malloc(size_t size) AIM_COMPILER_ATTR_MALLOC;

/**
 * @brief Zero'ed memory alloc.
 * @param size Size.
 *
 * Aborts if allocation fails.
 */
void *aim_zmalloc(size_t size) AIM_COMPILER_ATTR_MALLOC;

/**
 * @brief Resize memory.
 * @param ptr Allocated memory.
 * @param size New size.
 *
 * Usual realloc semantics: if ptr is NULL then a new allocation is made, and
 * is size is zero then the memory is freed. Otherwise the memory is resized
 * and possibly moved.
 *
 * Aborts if allocation fails.
 */
void *aim_realloc(void *ptr, size_t size);

/**
 * Free memory allocated by aim_zmalloc()
 * @param data The memory to free.
 */
void aim_free(void *data);

/**
 * @brief Duplicate memory.
 * @param src Source memory.
 * @param size Size.
 * @returns a new copy of the data.
 *
 * Aborts if allocation fails.
 */
void *aim_memdup(void *src, size_t size) AIM_COMPILER_ATTR_MALLOC;

/**
 * @brief Duplicate memory.
 * @param src Source memory;
 * @param src_size Size to copy.
 * @param alloc_size Size to allocate.
 *
 * Aborts if allocation fails.
 */
void *aim_memndup(void *src, size_t src_size, size_t alloc_size) AIM_COMPILER_ATTR_MALLOC;

#endif /* __AIM_MEMORY_H__ */
/*@}*/
