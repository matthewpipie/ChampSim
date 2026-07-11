# dr.mk — DynamoRIO online-feed integration for ChampSim.
#
# Included by the top-level Makefile (via `-include dr.mk`). Confines all
# DynamoRIO compile flags to the single translation unit src/dynamorio_source.cc
# and appends the DynamoRIO link closure (captured verbatim from the offline
# converter's build/CMakeFiles/converter.dir/link.txt) to the global link.
#
# Set DYNAMORIO=1 to enable. DYNAMORIO_HOME points at a prebuilt DynamoRIO tree
# (default: the offline converter repo's vendored+built copy).

ifeq ($(DYNAMORIO),1)

DYNAMORIO_HOME ?= /home/mgiordan/alliance/private-google-workload-traces-v2-to-champsim/dynamorio
DR_BUILD       := $(DYNAMORIO_HOME)/build
DR_DIR         := $(DYNAMORIO_HOME)/clients/drcachesim

# ---- Compile flags: applied ONLY to the DynamoRIO TU -------------------------
# Captured from the offline build's compile_commands.json (main_obj entry).
DR_EXT_DIRS := drbbdup drcallstack drcontainers drcovlib drgui drmf drmgr \
               droption drpttracer drreg drstatecmp drsyms drsyscall drutil \
               drwrap drx
DR_CPPFLAGS := -DLINUX -DX86_64 -DDYNAMORIO_STANDALONE \
  -I$(DR_BUILD)/cmake/../include \
  $(foreach d,$(DR_EXT_DIRS),-I$(DYNAMORIO_HOME)/ext/$(d)) \
  -isystem $(DR_BUILD)/clients/include \
  -isystem $(DR_DIR)/simulator \
  -isystem $(DR_DIR)/common \
  -isystem $(DR_DIR)/reader \
  -isystem $(DR_DIR)/tracer \
  -isystem $(DR_DIR)/scheduler \
  -isystem $(DR_DIR)/tools/common \
  -isystem $(DR_DIR)/tools \
  -isystem $(DYNAMORIO_HOME)/core/ir \
  -isystem $(DR_DIR) \
  -isystem $(DYNAMORIO_HOME)/include \
  -isystem $(DYNAMORIO_HOME)/tools/include

# The DR TU must also see -DENABLE_DYNAMORIO so ChampSim code can #ifdef on it.
$(OBJ_ROOT)/dynamorio_source.o: override CPPFLAGS += $(DR_CPPFLAGS)
$(DEP_ROOT)/dynamorio_source.d: override CPPFLAGS += $(DR_CPPFLAGS)

# main.cc gates the CLI on ENABLE_DYNAMORIO; give it to every base TU (cheap,
# it only guards a few #ifdef blocks and adds no DR headers).
override CPPFLAGS += -DENABLE_DYNAMORIO

# ---- Link closure: captured verbatim from link.txt ---------------------------
DR_LIBDIR_CLIENTS := $(DR_BUILD)/clients/lib64/release
DR_LIBDIR_EXT     := $(DR_BUILD)/ext/lib64/release
DR_LIBDIR_CORE    := $(DR_BUILD)/lib64
DR_LIBDIR_CORE_R  := $(DR_BUILD)/lib64/release

override LDFLAGS += -DDYNAMORIO_STANDALONE -Wl,--hash-style=both \
  -Wl,-rpath,$(DR_LIBDIR_CORE_R) -Wl,-rpath,$(DR_LIBDIR_CLIENTS) -Wl,-rpath,$(DR_LIBDIR_EXT)

override LDLIBS += \
  -L$(DR_LIBDIR_CLIENTS) \
  $(DR_LIBDIR_CLIENTS)/libdrmemtrace.so \
  $(DR_LIBDIR_CLIENTS)/libdrmemtrace_analyzer.a \
  $(DR_LIBDIR_EXT)/libdrcovlib_static.a \
  $(DR_LIBDIR_EXT)/libdrwrap.so \
  $(DR_LIBDIR_EXT)/libdrutil.so \
  $(DR_LIBDIR_EXT)/libdrstatecmp.so \
  $(DR_LIBDIR_EXT)/libdrcovlib.so \
  $(DR_LIBDIR_EXT)/libdrx.so \
  $(DR_LIBDIR_EXT)/libdrbbdup.so \
  $(DR_LIBDIR_EXT)/libdrreg.so \
  $(DR_LIBDIR_EXT)/libdrpttracer.so \
  $(DR_LIBDIR_EXT)/libdrsyscall_record_lib.so \
  $(DR_LIBDIR_EXT)/libdrsyscall.so \
  $(DR_LIBDIR_EXT)/libdrmgr.so \
  $(DR_LIBDIR_EXT)/libdrsyms.so \
  -lxxhash -lsnappy \
  $(DR_LIBDIR_CLIENTS)/libminizip.a \
  -llz4 \
  $(DR_LIBDIR_CLIENTS)/libdirectory_iterator.a \
  $(DR_LIBDIR_CORE)/libdrfrontendlib.a \
  $(DR_LIBDIR_CORE)/libdrlibc.a \
  $(DR_LIBDIR_CORE)/libdrmemfuncs.a \
  $(DR_LIBDIR_CLIENTS)/libdrmemtrace_mutex_dbg_owned.a \
  /usr/lib/x86_64-linux-gnu/libpthread.so \
  /usr/lib/x86_64-linux-gnu/libz.so \
  $(DR_LIBDIR_EXT)/libdrx_static.a \
  $(DR_LIBDIR_EXT)/libdrreg_static.a \
  $(DR_LIBDIR_EXT)/libdrmgr_static.a \
  $(DR_LIBDIR_EXT)/libdrcontainers.a \
  $(DR_LIBDIR_CORE_R)/libdynamorio.so

endif # DYNAMORIO==1
