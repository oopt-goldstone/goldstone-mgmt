#ifndef __CUSTOM_MODULE__
#define __CUSTOM_MODULE__

#include <tai.h>

typedef enum _custom_module_attr_t
{
    /**
     * @brief backdoor register access
     *
     * @type tai_u32_range_t
     * @flags CREATE_AND_SET
     *
     */
    TAI_MODULE_ATTR_REGISTER = TAI_MODULE_ATTR_CUSTOM_NLD0670_TRB100_START,

    /**
     * @brief backdoor script execution
     *
     * @type tai_char_list_t
     * @flags CREATE_AND_SET
     *
     */
    TAI_MODULE_ATTR_SCRIPT,

    /**
     * @brief IO handler
     *
     * @type tai_pointer_t tai_module_io_handler_t
     * @flags CREATE_ONLY
     *
     */
    TAI_MODULE_ATTR_IO_HANDLER,

    /**
     * @brief The CFP2ACO module vendor name
     *
     * @type #tai_char_list_t
     * @flags READ_ONLY
     */
    TAI_MODULE_ATTR_CFP2ACO_VENDOR_NAME,

    /**
     * @brief The CFP2ACO module vendor OUI
     *
     * @type #tai_uint32_t
     * @flags READ_ONLY
     */
    TAI_MODULE_ATTR_CFP2ACO_VENDOR_OUI,

    /**
     * @brief The list of supported CFP2ACO vendor OUI
     *
     * When the inserted CFP2ACO's vendor OUI doesn't match with any of the OUI in this list,
     * TAI adapter stops bringing up the module to READY state.
     *
     * empty list means it allows any CFP2ACO vendor
     *
     * @type #tai_u32_list_t
     * @flags CREATE_AND_SET
     * @default vendor-specific
     */
    TAI_MODULE_ATTR_SUPPORTED_CFP2ACO_VENDOR_OUI,

    /**
     * @brief The CFP2ACO module vendor's part number
     *
     * @type #tai_char_list_t
     * @flags READ_ONLY
     */
    TAI_MODULE_ATTR_CFP2ACO_VENDOR_PART_NUMBER,

    /**
     * @brief The CFP2ACO module vendor's serial number
     *
     * @type #tai_char_list_t
     * @flags READ_ONLY
     */
    TAI_MODULE_ATTR_CFP2ACO_VENDOR_SERIAL_NUMBER,

    /**
     * @brief The CFP2ACO module firmware version
     *
     * @type #tai_char_list_t
     * @flags READ_ONLY
     */
    TAI_MODULE_ATTR_CFP2ACO_FIRMWARE_VERSION,

    /**
     * @brief The version string of libtai
     *
     * @type #tai_char_list_t
     * @flags READ_ONLY
     */
    TAI_MODULE_ATTR_LIBTAI_VERSION,

} custom_module_attr_t;

#endif
