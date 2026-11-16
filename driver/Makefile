#
# Jailhouse, a Linux-based partitioning hypervisor
#
# Copyright (c) Siemens AG, 2013-2015
#
# Authors:
#  Jan Kiszka <jan.kiszka@siemens.com>
#  Benjamin Block <bebl@mageta.org>
#
# This work is licensed under the terms of the GNU GPL, version 2.  See
# the COPYING file in the top-level directory.
#

obj-m := jailhouse.o

ccflags-y := -I$(src)/../hypervisor/arch/$(SRCARCH)/include \
	     -I$(src)/../hypervisor/include \
	     -I$(src)/../include/arch/$(SRCARCH) \
	     -I$(src)/../include

jailhouse-y := cell.o main.o sysfs.o
jailhouse-$(CONFIG_PCI) += pci.o
jailhouse-$(CONFIG_OF) += vpci_template.dtb.o

targets += vpci_template.dtb vpci_template.dtb.S

.SECONDARY: \
        $(obj)/vpci_template.dtb.S \
        $(obj)/vpci_template.dtb

ifeq ($(SRCARCH),arm64)
PYTHON3 ?= python3
ccflags-y += -I$(obj)

quiet_cmd_arm64_layout = GEN     $@
      cmd_arm64_layout = $(PYTHON3) $(src)/../scripts/gen-arm64-entry-layout.py \
                         --hypervisor-dir $(obj)/../hypervisor --output $@

targets += arm64-entry-layout.h
$(obj)/arm64-entry-layout.h: $(obj)/../hypervisor/hypervisor.o \
                           $(obj)/../hypervisor/jailhouse.bin \
                           $(src)/../scripts/gen-arm64-entry-layout.py FORCE
	$(call if_changed,arm64_layout)

$(obj)/main.o: $(obj)/arm64-entry-layout.h
endif
