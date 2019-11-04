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
 ***************************************************************/
/************************************************************//**
 *
 * @file
 * @brief Semaphore Abstractions
 *
 ***************************************************************/
#ifndef __AIM_SEM_H__
#define __AIM_SEM_H__

#include <AIM/aim_config.h>

/**
 * Semaphore handle.
 */
typedef struct aim_sem_s* aim_sem_t;

/**
 * @brief Create a semaphore.
 * @param count Initial count.
 */
aim_sem_t aim_sem_create(int count);

/**
 * Specify this flag in aim_sem_create_flags() if you plan to
 * used timeouts with your semaphore. This option
 * will implement true relative timeouts that are immune
 * to clock adjustments (but will not perform as well).
 */
#define AIM_SEM_CREATE_F_TRUE_RELATIVE_TIMEOUTS 0x1

/**
 * @brief Create a semaphore.
 * @param count Initial count.
 * @param ... Optional uint32_t creation flags.
 */
aim_sem_t aim_sem_create_flags(int count, uint32_t flags);


/**
 * @brief Destroy a semaphore.
 * @param sem The semaphore.
 */
void aim_sem_destroy(aim_sem_t sem);

/**
 * @brief Take a semaphore
 * @param sem The semaphore.
 */
int aim_sem_take(aim_sem_t sem);

/**
 * @brief Give a semaphore.
 * @param sem The semaphore.
 */
void aim_sem_give(aim_sem_t sem);

/**
 * @brief Take a semaphore (with timeout).
 * @param sem The semaphore.
 * @param to usecs timeout in usecs
 * @returns 0 on success. -1 on timeout.
 */
int aim_sem_take_timeout(aim_sem_t sem, uint64_t usecs);


#endif /* __AIM_SEM_H__ */
