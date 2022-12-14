#define _GNU_SOURCE
#include <sched.h>
#include <stdlib.h>
#include <getopt.h>
#include <trace-cmd.h>
#include <event-parse.h>
#include <tracefs.h>
#include <stdlib.h>

struct private_data {
	int		cpu;
	const char	*file;
};

static int
trace_stack_handler(struct tracecmd_input *handle, struct tep_event *event,
		       struct tep_record *record, int cpu, void *_data)
{
	struct tep_format_field *field;
	unsigned long long addr;
	const char *func;
	int long_size;
	static struct trace_seq seq;
	void *data = record->data;

	if (!seq.buffer)
		trace_seq_init(&seq);

	field = tep_find_any_field(event, "caller");
	if (!field) {
		trace_seq_printf(&seq, "<CANT FIND FIELD %s>", "caller");
		return 0;
	}

	trace_seq_puts(&seq, "<stack trace >\n");

	long_size = tep_get_long_size(event->tep);

	for (data += field->offset; data < record->data + record->size;
	     data += long_size) {
		addr = tep_read_number(event->tep, data, long_size);

		if ((long_size == 8 && addr == (unsigned long long)-1) ||
		    ((int)addr == -1))
			break;

		func = tep_find_function(event->tep, addr);
		#if 0
		if (func)
			trace_seq_printf(&seq, "!=> %s (%llx)\n", func, addr);
		else
			trace_seq_printf(&seq, "!=> %llx\n", addr);
		#endif
	}

	 trace_seq_terminate(&seq);
	 trace_seq_do_printf(&seq);

	return 0;
}

static int print_events(struct tracecmd_input *handle,
						    struct tep_record *record, int cpu, void *data)
{
	static struct trace_seq seq;
	struct tep_handle *tep = tracecmd_get_tep(handle);
	struct private_data *pdata = tracecmd_get_private(handle);
	struct tep_event *event = tep_find_event_by_record(tep, record);

	unsigned long long common_pid;
	unsigned long long common_flags;
	unsigned long long common_preempt_count;
	unsigned long long common_type;

	/* For multi handles we need this */
	if (pdata->cpu >= 0 && pdata->cpu != record->cpu)
		return 0;

	if (!seq.buffer)
		trace_seq_init(&seq);

	trace_seq_reset(&seq);
	if (tep_get_common_field_val(&seq, event, "common_pid", record, &common_pid, 1))
		return -1;
	if (tep_get_common_field_val(&seq, event, "common_flags", record, &common_flags, 1))
		return -1;
	if (tep_get_common_field_val(&seq, event, "common_preempt_count", record, &common_preempt_count, 1))
		return -1;
	if (tep_get_common_field_val(&seq, event, "common_type", record, &common_type, 1))
		return -1;

	trace_seq_printf(&seq, "%s: pid %lld, flags 0x%llx, preempt_count 0x%llx, type %llx : ", pdata->file, common_pid, common_flags,
				     common_preempt_count, common_type);
	tep_print_event(tep, &seq, record, "%6.1000d [%03d] %s-%d %s\n",
			TEP_PRINT_TIME, TEP_PRINT_CPU, TEP_PRINT_COMM, TEP_PRINT_PID,
			TEP_PRINT_NAME);

	trace_seq_terminate(&seq);
	trace_seq_do_printf(&seq);
	return 0;
}

static int print_event(struct tracecmd_input *handle, struct tep_event *event,
		       struct tep_record *record, int cpu, void *data)
{
	return print_events(handle, record, cpu, data);
}

static void usage(const char *argv0)
{
	printf("usage: [-c cpu][-f filter][-e event] %s trace.dat [trace.dat ...]\n",
	       argv0);
	exit(-1);
}

int main(int argc, char **argv)
{
	struct tracecmd_input **handles = NULL;
	const char *filter_str = NULL;
	const char *argv0 = argv[0];
	char *filename;
	struct private_data *priv;
	cpu_set_t *cpuset = NULL;
	char *event = NULL;
	size_t cpusize = 0;
	int nr_handles = 0;
	int cpu = -1;
	int i;
	int c;

	while ((c = getopt(argc, argv, "c:f:e:")) >= 0) {
		switch (c) {
		case 'c':
			/* filter all trace data to this one CPU. */
			cpu = atoi(optarg);
			break;
		case 'f':
			filter_str = optarg;
			break;
		case 'e':
			event = optarg;
			break;
		default:
			usage(argv0);
		}
	}
	argc -= optind;
	argv += optind;

	if (argc == 0) {
		argv[i] = "trace.dat";
		argc++;
	}

	for (i = 0; i < argc; i++) {
		handles = realloc(handles, sizeof(*handles) * (nr_handles + 1));
		if (!handles)
			exit(-1);
		handles[nr_handles] = tracecmd_open(argv[i], 0);
		if (!handles[nr_handles]) {
			perror(argv[i]);
			exit(-1);
		}

		if (filter_str) {
			if (tracecmd_filter_add(handles[nr_handles], filter_str, false) == NULL) {
				perror("adding filter");
				exit(-1);
			}
		}
		priv = calloc(1, sizeof(*priv));
		if (!priv)
			exit(-1);
		priv->file = argv[i];
		priv->cpu = cpu;
		tracecmd_set_private(handles[nr_handles], priv);
#if 0
		if (tracecmd_follow_event(handles[nr_handles], "ftrace", "user_stack", trace_stack_handler, NULL) < 0) {
			printf("Could not follow event %s for file %s\n", event, argv[i]);
			exit(-1);
		}
		if (tracecmd_follow_event(handles[nr_handles], "ftrace", "kernel_stack", trace_stack_handler, NULL) < 0) {
			printf("Could not follow event %s for file %s\n", event, argv[i]);
			exit(-1);
		}
#endif
		nr_handles++;
	}

	/* Shortcut */
	if (nr_handles == 1) {
		if (cpu >= 0) {
			cpuset = CPU_ALLOC(cpu + 1);
			if (!cpuset)
				exit(-1);
			cpusize = CPU_ALLOC_SIZE(cpu + 1);
			CPU_SET_S(cpu, cpusize, cpuset);
		}
		if (event)
			tracecmd_iterate_events(handles[0], cpuset, cpusize, NULL, NULL);
		else
			tracecmd_iterate_events(handles[0], cpuset, cpusize, print_events, NULL);
	} else {
		if (event)
			tracecmd_iterate_events_multi(handles, nr_handles, NULL, NULL);
		else
			tracecmd_iterate_events_multi(handles, nr_handles, print_events, NULL);
	}

	for (i = 0; i < nr_handles; i++) {
		priv = tracecmd_get_private(handles[i]);
		free(priv);
		tracecmd_close(handles[i]);
	}
	free(handles);
}
