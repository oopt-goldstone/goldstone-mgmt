# This map contains interface name, lane number, alias and index
INTERFACE_MAP = {
    "Ethernet1_1": [45, "QSPF1-E1_1", 1],
    "Ethernet2_1": [29, "QSPF2-E5_1", 5],
    "Ethernet3_1": [53, "QSFP3-E9_1", 9],
    "Ethernet4_1": [49, "QSFP4-E13_1", 13],
    "Ethernet5_1": [61, "QSFP5-E17_1", 17],
    "Ethernet6_1": [57, "QSFP6-E21_1", 21],
    "Ethernet7_1": [69, "QSFP7-E25_1", 25],
    "Ethernet8_1": [65, "QSFP8-E29_1", 29],
    "Ethernet9_1": [77, "QSFP9-E33_1", 33],
    "Ethernet10_1": [73, "QSFP10-E37_1", 37],
    "Ethernet11_1": [97, "QSFP10-E41_1", 41],
    "Ethernet12_1": [81, "QSFP11-E45_1", 45],
    "Ethernet13_1": [1, "PIU1-E1", 49],
    "Ethernet14_1": [5, "PIU1-E2", 53],
    "Ethernet15_1": [9, "PIU2-E3", 57],
    "Ethernet16_1": [13, "PIU2-E4", 61],
    "Ethernet17_1": [113, "PIU3-E5", 65],
    "Ethernet18_1": [117, "PIU3-E6", 69],
    "Ethernet19_1": [121, "PIU4-E7", 73],
    "Ethernet20_1": [125, "PIU4-E8", 77],
}

CONFIG_BCM_CONTSTANTS1 = """# wistron ploomtech 20x100G SDK config
os=unix
schan_intr_enable=0
l2_mem_entries=40960
l2xmsg_mode=1
l3_mem_entries=40960
parity_correction=0
parity_enable=0
mmu_lossless=1

#pbmp_oversubscribe=0x444444441111111104444444422222222
pbmp_xport_xe=0x3ffffffffffffffffffffffffffffffffe

#
port_flex_enable=1
phy_enable=1
arl_clean_timeout_usec=15000000
asf_mem_profile=2
bcm_num_cos=8
bcm_stat_flags=1
bcm_stat_jumbo=9236
cdma_timeout_usec=15000000
dma_desc_timeout_usec=15000000
ipv6_lpm_128b_enable=1
l3_alpm_enable=2
lpm_scaling_enable=0
max_vp_lags=0
miim_intr_enable=0
oversubscribe_mode=1

"""

CONFIG_BCM_CONTSTANTS2 = """
serdes_fec_enable_29=2
serdes_fec_enable_46=2
serdes_fec_enable_50=2
serdes_fec_enable_54=2
serdes_fec_enable_58=2
serdes_fec_enable_62=2
serdes_fec_enable_68=2
serdes_fec_enable_72=2
serdes_fec_enable_76=2
serdes_fec_enable_80=2
serdes_fec_enable_84=2
serdes_fec_enable_102=2
"""