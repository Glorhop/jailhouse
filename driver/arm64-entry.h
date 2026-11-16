/* SPDX-License-Identifier: GPL-2.0-only */
/* Copyright (c) Glorhop, 2026 */
/* ARM64 Linux mapping only; EL2 mappings remain owned by the hypervisor. */
#include <crypto/sha2.h>
#include <asm/pgtable.h>
#include "arm64-entry-layout.h"

static struct mm_struct *init_mm_sym;
static bool prepare_only;
module_param(prepare_only, bool, 0600);
MODULE_PARM_DESC(prepare_only, "Verify EL1 mappings without entering EL2");

struct jh_hv_mapping {
	unsigned long base;
	phys_addr_t phys;
	bool protect;
	bool verify;
	unsigned int executable_pages;
	u64 entry_pte;
};

static bool jh_hv_exec_page(unsigned long offset)
{
	unsigned int n;

	for (n = 0; n < ARRAY_SIZE(jh_el1_exec_ranges); n++)
		if (offset >= jh_el1_exec_ranges[n].start &&
		    offset < jh_el1_exec_ranges[n].end)
			return true;
	return false;
}

static int jh_hv_map_page(pte_t *ptep, unsigned long addr, void *data)
{
	struct jh_hv_mapping *map = data;
	unsigned long offset = addr - map->base;
	pte_t expected = pfn_pte((map->phys + offset) >> PAGE_SHIFT,
				PAGE_KERNEL);
	bool executable = jh_hv_exec_page(offset);

	if (!map->protect && !map->verify) {
		if (!pte_none(READ_ONCE(*ptep)))
			return -EINVAL;
		set_pte(ptep, expected);
		return 0;
	}

	if (map->verify && executable)
		expected = pfn_pte((map->phys + offset) >> PAGE_SHIFT,
				   PAGE_KERNEL_ROX);
	if (pte_val(READ_ONCE(*ptep)) != pte_val(expected))
		return -EPERM;

	if (map->protect && executable)
		set_pte(ptep, pfn_pte((map->phys + offset) >> PAGE_SHIFT,
				      PAGE_KERNEL_ROX));
	if (map->verify) {
		map->executable_pages += executable;
		if (offset == (JH_EL1_ENTRY & PAGE_MASK))
			map->entry_pte = pte_val(READ_ONCE(*ptep));
	}
	return 0;
}

static void *jailhouse_hv_ioremap(phys_addr_t phys, unsigned long virt,
				  unsigned long size)
{
	struct vm_struct *vma;
	struct jh_hv_mapping map = { .phys = phys };
	unsigned long end;
	int err;

	if (PAGE_SHIFT != 12 || !PAGE_ALIGNED(phys) || !size ||
	    size != PAGE_ALIGN(size) || phys + size < phys)
		return NULL;
	vma = __get_vm_area(size, VM_IOREMAP, virt ? virt : VMALLOC_START,
			    virt ? virt + size + PAGE_SIZE : VMALLOC_END);
	if (!vma)
		return NULL;
	vma->phys_addr = phys;
	map.base = (unsigned long)vma->addr;
	end = map.base + size;
	/* New, unmapped VA: never split a live ioremap block mapping. */
	err = apply_to_page_range(init_mm_sym, map.base, size,
				  jh_hv_map_page, &map);
	flush_cache_vmap(map.base, end);
	flush_tlb_kernel_range(map.base, end);
	if (err) {
		vunmap(vma->addr);
		return NULL;
	}
	return vma->addr;
}

static int jailhouse_hv_check_firmware(const struct firmware *fw)
{
	u8 digest[SHA256_DIGEST_SIZE];
	const struct jailhouse_header *header = (const void *)fw->data;

	if (PAGE_SHIFT != 12) {
		pr_err("jailhouse: ARM64 entry mapping requires 4 KiB pages\n");
		return -EOPNOTSUPP;
	}
	if (fw->size != JH_EL1_FIRMWARE_SIZE ||
	    fw->size < sizeof(*header) ||
	    header->core_size != JH_EL1_CORE_SIZE ||
	    (unsigned long)header->entry != JH_EL1_ENTRY) {
		pr_err("jailhouse: firmware does not match EL1 RX layout\n");
		return -EINVAL;
	}
	sha256(fw->data, fw->size, digest);
	if (memcmp(digest, jh_el1_firmware_sha256, sizeof(digest))) {
		pr_err("jailhouse: firmware SHA256 does not match EL1 RX layout\n");
		return -EINVAL;
	}
	return 0;
}

static int jailhouse_hv_protect(phys_addr_t phys, unsigned long size)
{
	struct jh_hv_mapping map = {
		.base = (unsigned long)hypervisor_mem, .phys = phys,
		.protect = true,
	};
	unsigned int n;
	int err;

	for (n = 0; n < ARRAY_SIZE(jh_el1_exec_ranges); n++)
		if (!PAGE_ALIGNED(jh_el1_exec_ranges[n].start) ||
		    !PAGE_ALIGNED(jh_el1_exec_ranges[n].end) ||
		    jh_el1_exec_ranges[n].start < PAGE_SIZE ||
		    jh_el1_exec_ranges[n].start >= jh_el1_exec_ranges[n].end ||
		    jh_el1_exec_ranges[n].end > JH_EL1_CORE_SIZE ||
		    jh_el1_exec_ranges[n].end > size)
			return -EINVAL;
	/* All code copies are complete while the entire alias is still RW-NX. */
	flush_icache_range(map.base, map.base + JH_EL1_CORE_SIZE);
	err = apply_to_page_range(init_mm_sym, map.base, size,
				  jh_hv_map_page, &map);
	flush_tlb_kernel_range(map.base, map.base + size);
	if (err)
		return err;
	map.protect = false;
	map.verify = true;
	err = apply_to_page_range(init_mm_sym, map.base, size,
				  jh_hv_map_page, &map);
	if (err)
		return err;
	pr_info("jailhouse: EL1 mapping verified: %u RX pages, %lu RW-NX pages; entry offset 0x%lx PTE 0x%016llx\n",
		map.executable_pages, (size >> PAGE_SHIFT) - map.executable_pages,
		JH_EL1_ENTRY, map.entry_pte);
	return 0;
}
