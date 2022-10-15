TARGETS = langraph

OBJS =
OBJS += main.o
LIBS ?= -ldl -pthread

$(call allow-override,CC,$(CROSS_COMPILE)gcc)
$(call allow-override,AR,$(CROSS_COMPILE)ar)
$(call allow-override,PKG_CONFIG,pkg-config)
$(call allow-override,LD_SO_CONF_PATH,/etc/ld.so.conf.d/)
$(call allow-override,LDCONFIG,ldconfig)
PKG_CONFIG=pkg-config

EXT = -std=gnu99

LIBTRACEEVENT=libtraceevent
LIBTRACEFS=libtracefs
LIBTRACECMD=libtracecmd

LIBTRACEFS_CFLAGS = $(shell sh -c "$(PKG_CONFIG) --cflags $(LIBTRACEFS)")
LIBTRACEFS_LDLAGS = $(shell sh -c "$(PKG_CONFIG) --libs $(LIBTRACEFS)")
LIBTRACEEVENT_CFLAGS = $(shell sh -c "$(PKG_CONFIG) --cflags $(LIBTRACEEVENT)")
LIBTRACEEVENT_LDLAGS = $(shell sh -c "$(PKG_CONFIG) --libs $(LIBTRACEEVENT)")
LIBTRACECMD_CFLAGS = $(shell sh -c "$(PKG_CONFIG) --cflags $(LIBTRACECMD)")
LIBTRACECMD_LDLAGS = $(shell sh -c "$(PKG_CONFIG) --libs $(LIBTRACECMD)")
ZLIB_LDLAGS = -lz
LIBZSTD_CFLAGS = $(shell sh -c "$(PKG_CONFIG) --cflags libzstd")
LIBZSTD_LDLAGS = $(shell sh -c "$(PKG_CONFIG) --libs libzstd")

INCLUDES += $(LIBTRACEEVENT_CFLAGS)
INCLUDES += $(LIBTRACEFS_CFLAGS)
INCLUDES += $(LIBTRACECMD_CFLAGS)
TRACE_LIBS = $(LIBTRACECMD_LDLAGS)	\
	     $(LIBTRACEEVENT_LDLAGS) $(LIBTRACEFS_LDLAGS)
override CFLAGS += $(INCLUDES)
override CFLAGS += $(udis86-flags) $(blk-flags) $(memfd-flags)
override LDFLAGS += $(udis86-ldflags)

LIBS += $(LIBTRACECMD_LDLAGS) $(LIBTRACEEVENT_LDLAGS) $(LIBTRACEFS_LDLAGS)

LIBS += $(ZLIB_LDLAGS) $(LIBZSTD_LDLAGS)

$(TARGETS): $(OBJS)
	$(CC) $^ -rdynamic -Wl,-rpath=$(libdir) -o $@ $(LDFLAGS) $(CONFIG_LIBS) $(LIBS)

%.o: %.c
	$(CC) -c $(CFLAGS) $(CFLAGS) $(EXT) -fPIC -O0 -g $< -o $@

all: $(TARGETS)

clean:
	$(RM) $(TARGETS) *.o
