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
 * XZB100 root cell; CPUs 0-7 before CPU7 is handed over.
 * See Documentation/arm64-xz100.md for the required boot/resource audit.
 */

#include <jailhouse/types.h>
#include <jailhouse/cell-config.h>

struct {
	struct jailhouse_system header;
	__u64 cpus[1];
	struct jailhouse_memory mem_regions[24];
	struct jailhouse_irqchip irqchips[8];
	struct jailhouse_pci_device pci_devices[2];
} __attribute__((packed)) config = {
	.header = {
		.signature = JAILHOUSE_SYSTEM_SIGNATURE,
		.revision = JAILHOUSE_CONFIG_REVISION,
		.architecture = JAILHOUSE_ARM64,
		.flags = JAILHOUSE_SYS_VIRTUAL_DEBUG_CONSOLE |
			 JAILHOUSE_SYS_HAS_PSCI,
		.hypervisor_memory = {
			.phys_start = 0xc0000000,
			.size = 0x01000000,
		},
		.platform_info = {
			.pci_mmconfig_base = 0x0f800000,
			.pci_mmconfig_end_bus = 0,
			.pci_is_virtual = 1,
			.pci_domain = 0x10,
			.arm = {
				.maintenance_irq = 25,
				.gic_version = 3,
				.gicd_base = 0x0f400000,
				.gicr_base = 0x0f440000,
			},
		},
		.root_cell = {
			.name = "xzb100",
			.cpu_set_size = sizeof(config.cpus),
			.num_memory_regions = ARRAY_SIZE(config.mem_regions),
			.num_irqchips = ARRAY_SIZE(config.irqchips),
			.num_pci_devices = ARRAY_SIZE(config.pci_devices),
			.vpci_irq_base = 590 - 32,
		},
	},

	.cpus = { 0xff },

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
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_ROOTSHARED,
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
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
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
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_ROOTSHARED,
		},
		/* veth peer 1 output */
		{
			.phys_start = 0xc1180000,
			.virt_start = 0xc1180000,
			.size = 0x7f000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_ROOTSHARED,
		},
		/* Root-only peripheral MMIO */
		{
			.phys_start = 0x0,
			.virt_start = 0x0,
			.size = 0xf400000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_IO | JAILHOUSE_MEM_DMA,
		},
		/* Root-only peripheral MMIO */
		{
			.phys_start = 0xf410000,
			.virt_start = 0xf410000,
			.size = 0x30000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_IO | JAILHOUSE_MEM_DMA,
		},
		/* Root-only peripheral MMIO */
		{
			.phys_start = 0xf640000,
			.virt_start = 0xf640000,
			.size = 0x1c0000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_IO | JAILHOUSE_MEM_DMA,
		},
		/* Root-only peripheral MMIO */
		{
			.phys_start = 0xfa00000,
			.virt_start = 0xfa00000,
			.size = 0x70600000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_IO | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x80000000,
			.virt_start = 0x80000000,
			.size = 0x40000000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0xc1010000,
			.virt_start = 0xc1010000,
			.size = 0xf0000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0xc11ff000,
			.virt_start = 0xc11ff000,
			.size = 0xf6bb71000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x102cdf0000,
			.virt_start = 0x102cdf0000,
			.size = 0x200000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x102d700000,
			.virt_start = 0x102d700000,
			.size = 0x100000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x102d980000,
			.virt_start = 0x102d980000,
			.size = 0x280000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x102f000000,
			.virt_start = 0x102f000000,
			.size = 0x1000000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x1032000000,
			.virt_start = 0x1032000000,
			.size = 0x2000000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root RAM / cell load access */
		{
			.phys_start = 0x1049800000,
			.virt_start = 0x1049800000,
			.size = 0x36800000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_EXECUTE | JAILHOUSE_MEM_DMA,
		},
		/* Root-only peripheral MMIO */
		{
			.phys_start = 0x2080000000,
			.virt_start = 0x2080000000,
			.size = 0x1780000000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_IO | JAILHOUSE_MEM_DMA,
		},
		/* Root-only peripheral MMIO */
		{
			.phys_start = 0x3828000000,
			.virt_start = 0x3828000000,
			.size = 0x318000000,
			.flags = JAILHOUSE_MEM_READ | JAILHOUSE_MEM_WRITE |
				 JAILHOUSE_MEM_IO | JAILHOUSE_MEM_DMA,
		},
	},

	.irqchips = {
		{
			.address = 0x0f400000,
			.pin_base = 32,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 160,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 288,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 416,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 544,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 672,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 800,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff,
			},
		},
		{
			.address = 0x0f400000,
			.pin_base = 928,
			.pin_bitmap = {
				0xffffffff, 0xffffffff, 0x00000000, 0x00000000,
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
			.shmem_dev_id = 0,
			.shmem_peers = 3,
			.shmem_protocol = JAILHOUSE_SHMEM_PROTO_UNDEFINED,
		},
		{
			.type = JAILHOUSE_PCI_TYPE_IVSHMEM,
			.domain = 0x10,
			.bdf = 1 << 3,
			.bar_mask = JAILHOUSE_IVSHMEM_BAR_MASK_INTX,
			.shmem_regions_start = 5,
			.shmem_dev_id = 0,
			.shmem_peers = 2,
			.shmem_protocol = JAILHOUSE_SHMEM_PROTO_VETH,
		},
	},
};
