#ifndef __CUSTOM_HOSTIF__
#define __CUSTOM_HOSTIF__

#include <tai.h>

typedef enum _custom_host_interface_attr_t
{
    /** Custom range for the NLD0670APB adapter */
    TAI_HOST_INTERFACE_ATTR_CUSTOM_NLD0670_START = TAI_HOST_INTERFACE_ATTR_CUSTOM_NLD0670_TRB100_START,

    /**
     * @brief Host interface alarm notification
     *
     * @type #tai_notification_handler_t
     * @flags CREATE_AND_SET
     * @default NULL
     */
    TAI_HOST_INTERFACE_ATTR_ALARM_NOTIFICATION,

} custom_host_interface_attr_t;

#endif
