#ifndef __CUSTOM_NETIF__
#define __CUSTOM_NETIF__

#include <tai.h>

typedef enum _tai_network_interface_dsp_oper_status_t
{
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_UNKNOWN,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_NO_MODULE,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_WAITING_CONFIGURATION,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_BOOTING_FIRST_HALF,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_WAITING_ACO_MODULE,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_BOOTING_ACO_MODULE,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_WAITING_RX_SIGNAL,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_BOOTING_SECOND_HALF,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_READY,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_MISC_CONFIG,
    TAI_NETWORK_INTERFACE_DSP_OPER_STATUS_MAX
} tai_network_interface_dsp_oper_status_t;

typedef enum _tai_network_interface_hd_fec_type_t
{
    TAI_NETWORK_INTERFACE_HD_FEC_TYPE_NONE,
    TAI_NETWORK_INTERFACE_HD_FEC_TYPE_GFEC,
    TAI_NETWORK_INTERFACE_HD_FEC_TYPE_HGFEC,
    TAI_NETWORK_INTERFACE_HD_FEC_TYPE_MAX
} tai_network_interface_hd_fec_type_t;

typedef enum _tai_network_interface_sd_fec_type_t
{
    TAI_NETWORK_INTERFACE_SD_FEC_TYPE_NONE,
    TAI_NETWORK_INTERFACE_SD_FEC_TYPE_ON,
    TAI_NETWORK_INTERFACE_SD_FEC_TYPE_MAX
} tai_network_interface_sd_fec_type_t;

typedef enum _tai_network_interface_mld_t
{
    TAI_NETWORK_INTERFACE_MLD_UNKNOWN,
    TAI_NETWORK_INTERFACE_MLD_4_LANES,
    TAI_NETWORK_INTERFACE_MLD_20_LANES,
    TAI_NETWORK_INTERFACE_MLD_MAX
} tai_network_interface_mld_t;

typedef enum _custom_network_interface_attr_t
{
    /** Custom range for the NLD0670APB adapter */
    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_NLD0670_START = TAI_NETWORK_INTERFACE_ATTR_CUSTOM_NLD0670_TRB100_START,

    /**
     * @brief loss of signal detection setting
     *
     * @type bool
     * @flags CREATE_AND_SET
     * @default false
     */
    TAI_NETWORK_INTERFACE_ATTR_LOSI,

    /**
     * @type bool
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_SYNC_ERROR,

    /**
     * @type #tai_u32_list_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_RMS,

    /**
     * @type #tai_uint32_t
     * @flags CREATE_AND_SET
     * @default 10000000
     */
    TAI_NETWORK_INTERFACE_ATTR_BER_PERIOD,

    /**
     * @type #tai_float_list_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_CURRENT_SD_FEC_BER,

    /**
     * @type #tai_float_list_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_CURRENT_HD_FEC_BER,

    /**
     * @type #tai_network_interface_dsp_oper_status_t
     */
    TAI_NETWORK_INTERFACE_ATTR_DSP_OPER_STATUS,

    /**
     * @type #tai_attr_value_list_t #tai_s8_list_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_CONSTELLATION,

    /**
     * @type bool
     * @default false
     */
    TAI_NETWORK_INTERFACE_ATTR_DISABLE_CONSTELLATION,

    /**
     * @type #tai_u16_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_RX_COARSE_SKEW,

    /**
     * @type #tai_s16_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_RX_FINE_SKEW,

    /**
     * @type #tai_u16_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_TX_COARSE_SKEW,

    /**
     * @type #tai_s16_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_TX_FINE_SKEW,

    /**
     * @type #tai_attr_value_list_t #tai_float_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_TX_TAP,

    /**
     * @type #tai_u16_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_TX_EQL_AMP,

    /**
     * @type #tai_u32_range_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_ACCEPTABLE_RMS_RANGE,

    /**
     * @brief TIA/VGA RF output target adjust
     *
     * Corresponds to OIF CFP2ACO spec 0xBBCC register
     *
     * @type #tai_u16_list_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_TIA_VGA_RF_OUTPUT_TARGET,

    /**
     * @brief HD-FEC type
     *
     * @type #tai_network_interface_hd_fec_type_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_HD_FEC_TYPE,

    /**
     * @brief SD-FEC type
     *
     * @type #tai_network_interface_sd_fec_type_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_SD_FEC_TYPE,

    /**
     * @brief MLD setting
     *
     * @type #tai_network_interface_mld_t
     * @flags CREATE_AND_SET
     */
    TAI_NETWORK_INTERFACE_ATTR_MLD,

    /**
     * @brief PRBS in-sync
     *
     * @type bool
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_PRBS_IN_SYNC,

    /**
     * @brief The loaded libaco library name
     *
     * @type #tai_char_list_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_LOADED_LIBACO,

    /**
     * @brief RX LOS alarm
     *
     * @type bool
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_RX_LOS,

    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_NLD0670_END = TAI_NETWORK_INTERFACE_ATTR_CUSTOM_NLD0670_START + 0x7FFF,

    /** Custom range for the TRB100 adapter */
    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_TRB100_START,

    /**
     * @brief TAI independent command interface
     *
     * @type #tai_pointer_t
     */
    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_TRB100_CMD = TAI_NETWORK_INTERFACE_ATTR_CUSTOM_TRB100_START,

    /**
     * @brief The RX power low warning threshold in dBm
     *
     * @type #tai_float_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_TRB100_RX_POWER_LOW_WARNING_THRESHOLD,

    /**
     * @brief The RX power low alarm threshold in dBm
     *
     * @type #tai_float_t
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_TRB100_RX_POWER_LOW_ALARM_THRESHOLD,

    /**
     * @brief RX Loss of Signal
     *
     * @type bool
     * @flags READ_ONLY
     */
    TAI_NETWORK_INTERFACE_ATTR_CUSTOM_TRB100_RX_LOS,

} custom_network_interface_attr_t;

#endif
