// SPDX-License-Identifier: GPL-2.0-only
/*
 * Jailhouse, a Linux-based partitioning hypervisor
 *
 * Copyright (c) Glorhop, 2026
 *
 * Authors:
 *  Glorhop <1150595033@qq.com>
 *
 * This work is licensed under the terms of the GNU GPL, version 2.  See
 * the COPYING file in the top-level directory.
 *
 * XZB100 CPU7 Linux inmate; virtual console and ivshmem only.
 * See Documentation/arm64-xz100.md for the required boot/resource audit.
 */

#include <jailhouse/types.h>
#include <jailhouse/cell-config.h>

struct {
	struct jailhouse_cell_desc header;
	__u64 cpus[1];
	struct jailhouse_memory mem_regions[12];
	struct jailhouse_irqchip irqchips[1];
	struct jailhouse_pci_device pci_devices[2];
} __attribute__((packed)) config = {
	.header = {
		.signature = JAILHOUSE_CELL_DESC_SIGNATURE,
		.revision = JAILHOUSE_CONFIG_REVISION,
		.architecture = JAILHOUSE_ARM64,
		.name = "xzb100-linux",
		.flags = JAILHOUSE_CELL_PASSIVE_COMMREG |
			 JAILHOUSE_CELL_VIRTUAL_CONSOLE_PERMITTED |
			 JAILHOUSE_CELL_VIRTUAL_CONSOLE_ACTIVE,
		.cpu_set_size = sizeof(config.cpus),
		.num_memory_regions = ARRAY_SIZE(config.mem_regions),
		.num_irqchips = ARRAY_SIZE(config.irqchips),
		.num_pci_devices = ARRAY_SIZE(config.pci_devices),
		.vpci_irq_base = 588 - 32,
	},

	.cpus = { 0x80 },

	.mem_regions = {
		/* ivshmem state table */
		{
			.phys_start = 0xc1000000,
			.virt_start = 0xc1000000,
			.size = 0x1000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
		},
		/* ivshmem common R/W area */
		{
			.phys_start = 0xc1001000,
			.virt_start = 0xc1001000,
			.size = 0x9000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_ROOTSHARED,
		},
		/* ivshmem peer 0 output */
		{
			.phys_start = 0xc100a000,
			.virt_start = 0xc100a000,
			.size = 0x2000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
		},
		/* ivshmem peer 1 output (unused) */
		{
			.phys_start = 0xc100c000,
			.virt_start = 0xc100c000,
			.size = 0x2000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
		},
		/* ivshmem peer 2 output */
		{
			.phys_start = 0xc100e000,
			.virt_start = 0xc100e000,
			.size = 0x2000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_ROOTSHARED,
		},
		/* veth state table */
		{
			.phys_start = 0xc1100000,
			.virt_start = 0xc1100000,
			.size = 0x1000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
		},
		/* veth common area (empty) */
		{
			.phys_start = 0x0,
			.virt_start = 0x0,
			.size = 0x0,
			.flags = 0,
		},
		/* veth peer 0 output */
		{
			.phys_start = 0xc1101000,
			.virt_start = 0xc1101000,
			.size = 0x7f000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
		},
		/* veth peer 1 output */
		{
			.phys_start = 0xc1180000,
			.virt_start = 0xc1180000,
			.size = 0x7f000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_ROOTSHARED,
		},
		/* Loader alias */
		{
			.phys_start = 0xc2000000,
			.virt_start = 0x0,
			.size = 0x10000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_LOADABLE,
		},
		/* Private inmate RAM */
		{
			.phys_start = 0xc2010000,
			.virt_start = 0xc2010000,
			.size = 0x1fff0000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_LOADABLE,
		},
		/* Communication page */
		{
			.phys_start = 0x0,
			.virt_start = 0x80000000,
			.size = 0x1000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_COMM_REGION,
		},
	},

	.irqchips = {
		{
			.address = 0x0f400000,
			.pin_base = 544,
			.pin_bitmap = {
				0x00000000, 0x00003000, 0x00000000, 0x00000000,
			},
		},
	},

	.pci_devices = {
		{
			.type = JAILHOUSE_PCI_TYPE_IVSHMEM,
			.domain = 0x10,
			.bdf = 0 << 3,
			.bar_mask = JAILHOUSE_IVSHMEM_BAR_MASK_INTX,
			.shmem_regions_start = 0,
			.shmem_dev_id = 2,
			.shmem_peers = 3,
			.shmem_protocol = JAILHOUSE_SHMEM_PROTO_UNDEFINED,
		},
		{
			.type = JAILHOUSE_PCI_TYPE_IVSHMEM,
			.domain = 0x10,
			.bdf = 1 << 3,
			.bar_mask = JAILHOUSE_IVSHMEM_BAR_MASK_INTX,
			.shmem_regions_start = 5,
			.shmem_dev_id = 1,
			.shmem_peers = 2,
			.shmem_protocol = JAILHOUSE_SHMEM_PROTO_VETH,
		},
	},
};
